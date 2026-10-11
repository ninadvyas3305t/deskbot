"""Automatic Hybrid Online/Offline Connectivity Manager for DeskBot.

Monitors internet reachability and cloud AI service availability without blocking
the UI or audio pipelines. Distinguishes three states:
- ONLINE: Internet is available and cloud services are reachable.
- OFFLINE: Internet is unavailable; local processing is active.
- DEGRADED: Internet is connected, but the cloud AI service is failing or unreachable.
"""

from __future__ import annotations

import enum
import logging
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, List, Optional, Tuple

# Ensure both top-level 'connectivity' and 'companion.connectivity' share module
if __name__ == "companion.connectivity":
    sys.modules.setdefault("connectivity", sys.modules[__name__])
elif __name__ == "connectivity":
    sys.modules.setdefault("companion.connectivity", sys.modules[__name__])

logger = logging.getLogger(__name__)


class ConnectivityState(str, enum.Enum):
    """The three operating connectivity states of DeskBot."""
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DEGRADED = "DEGRADED"


# Known resilient endpoints for socket connectivity probes
_INTERNET_PROBES: List[Tuple[str, int]] = [
    ("1.1.1.1", 53),      # Cloudflare DNS
    ("8.8.8.8", 53),      # Google DNS
    ("208.67.222.222", 53),  # OpenDNS
]

# NVIDIA NIM / Cloud AI host for TCP reachability probes
_CLOUD_API_HOST = "integrate.api.nvidia.com"
_CLOUD_API_PORT = 443


class ConnectivityManager:
    """Thread-safe connectivity supervisor for DeskBot."""

    def __init__(self, check_interval: float = 20.0, probe_timeout: float = 1.5):
        self._lock = threading.RLock()
        self._check_interval = check_interval
        self._probe_timeout = probe_timeout
        self._state: ConnectivityState = ConnectivityState.ONLINE
        self._details: str = "Initialized"
        self._override_state: Optional[ConnectivityState] = None

        self._consecutive_net_failures: int = 0
        self._consecutive_api_failures: int = 0
        self._last_check_timestamp: float = 0.0

        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._listeners: List[Callable[[ConnectivityState, str], None]] = []

    @property
    def state(self) -> ConnectivityState:
        with self._lock:
            if self._override_state is not None:
                return self._override_state
            return self._state

    @property
    def details(self) -> str:
        with self._lock:
            return self._details

    def is_online(self) -> bool:
        return self.state == ConnectivityState.ONLINE

    def is_offline(self) -> bool:
        return self.state == ConnectivityState.OFFLINE

    def is_degraded(self) -> bool:
        return self.state == ConnectivityState.DEGRADED

    def set_override_state(self, state: Optional[ConnectivityState | str]) -> None:
        """Manually override connectivity state (primarily for automated testing)."""
        with self._lock:
            if state is None:
                self._override_state = None
            elif isinstance(state, str):
                self._override_state = ConnectivityState(state.upper())
            else:
                self._override_state = state
            effective = self._override_state or self._state
            self._notify_listeners(effective, f"Override state: {effective.value}")

    def add_listener(self, callback: Callable[[ConnectivityState, str], None]) -> None:
        """Register a callback for state transition notifications."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[ConnectivityState, str], None]) -> None:
        """Unregister a listener callback."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify_listeners(self, new_state: ConnectivityState, details: str) -> None:
        # Emit to registered callbacks
        for listener in list(self._listeners):
            try:
                listener(new_state, details)
            except Exception as cb_err:
                logger.debug("Connectivity listener error: %s", cb_err)

        # Notify UI bridge if available
        try:
            from ui.bridge import _safe_get_bridge
            bridge = _safe_get_bridge()
            if bridge and hasattr(bridge, "notify_connectivity"):
                bridge.notify_connectivity(new_state.value, details)
        except Exception:
            pass

    def check_internet(self, timeout: Optional[float] = None) -> bool:
        """Probe outbound internet connectivity using short-lived socket connections."""
        to = timeout or self._probe_timeout
        for host, port in _INTERNET_PROBES:
            try:
                sock = socket.create_connection((host, port), timeout=to)
                sock.close()
                return True
            except (socket.timeout, TimeoutError, OSError):
                continue

        # Fallback probe via HTTP to 1.1.1.1
        try:
            req = urllib.request.Request("http://1.1.1.1", headers={"User-Agent": "DeskBot/1.0"})
            with urllib.request.urlopen(req, timeout=to):
                return True
        except Exception:
            pass

        return False

    def check_cloud_api(self, timeout: Optional[float] = None) -> bool:
        """Probe whether the cloud AI host endpoint is reachable via TCP."""
        to = timeout or self._probe_timeout
        try:
            sock = socket.create_connection((_CLOUD_API_HOST, _CLOUD_API_PORT), timeout=to)
            sock.close()
            return True
        except Exception:
            return False

    def evaluate_connectivity(self) -> ConnectivityState:
        """Perform active probe and update the manager state accordingly."""
        with self._lock:
            has_internet = self.check_internet()
            self._last_check_timestamp = time.time()

            if not has_internet:
                self._consecutive_net_failures += 1
                if self._consecutive_net_failures >= 1:
                    new_state = ConnectivityState.OFFLINE
                    details = "No internet connection detected. Local processing active."
            else:
                self._consecutive_net_failures = 0
                # If internet is present, verify API reachability
                api_reachable = self.check_cloud_api()
                if api_reachable and self._consecutive_api_failures == 0:
                    new_state = ConnectivityState.ONLINE
                    details = "Internet and cloud AI services operational."
                else:
                    new_state = ConnectivityState.DEGRADED
                    details = "Internet connected, but cloud AI service is unreachable or failing."

            old_state = self._state
            self._state = new_state
            self._details = details

            if old_state != new_state:
                logger.info(
                    "[CONNECTIVITY] State changed: %s -> %s (%s)",
                    old_state.value,
                    new_state.value,
                    details,
                )
                self._notify_listeners(new_state, details)

            return new_state

    def report_api_success(self) -> None:
        """Report a successful online AI or vision request."""
        with self._lock:
            self._consecutive_api_failures = 0
            if self._state == ConnectivityState.DEGRADED:
                self._state = ConnectivityState.ONLINE
                self._details = "Cloud AI service restored."
                logger.info("[CONNECTIVITY] Cloud AI service confirmed operational. Transitioned to ONLINE.")
                self._notify_listeners(ConnectivityState.ONLINE, self._details)

    def report_api_failure(self, error: Optional[Exception] = None) -> None:
        """Report a failed online AI request (timeout, connection error, 5xx)."""
        with self._lock:
            self._consecutive_api_failures += 1
            err_str = str(error) if error else "Unknown error"

            # If already offline, retain OFFLINE state. Otherwise, API failure means DEGRADED.
            if self._state == ConnectivityState.OFFLINE:
                new_state = ConnectivityState.OFFLINE
                details = f"Offline: {err_str}"
            else:
                new_state = ConnectivityState.DEGRADED
                details = f"Cloud AI API error: {err_str}"

            old_state = self._state
            self._state = new_state
            self._details = details

            if old_state != new_state:
                logger.warning(
                    "[CONNECTIVITY] API failure transition: %s -> %s (%s)",
                    old_state.value,
                    new_state.value,
                    details,
                )
                self._notify_listeners(new_state, details)

    def start_monitoring(self, interval_seconds: Optional[float] = None) -> None:
        """Start non-blocking background thread to periodically monitor connectivity."""
        with self._lock:
            if self._monitor_thread and self._monitor_thread.is_alive():
                return
            if interval_seconds:
                self._check_interval = interval_seconds

            self._stop_event.clear()
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name="DeskBotConnectivityMonitor",
                daemon=True,
            )
            self._monitor_thread.start()
            logger.debug("[CONNECTIVITY] Background connectivity monitor started.")

    def stop_monitoring(self) -> None:
        """Stop background monitoring thread."""
        self._stop_event.set()
        with self._lock:
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_thread.join(timeout=1.0)
            self._monitor_thread = None

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.evaluate_connectivity()
            except Exception as err:
                logger.debug("Connectivity monitor loop exception: %s", err)

            if self._stop_event.wait(timeout=self._check_interval):
                break


_GLOBAL_CONNECTIVITY_MANAGER: Optional[ConnectivityManager] = None
_INIT_LOCK = threading.Lock()


def get_connectivity_manager() -> ConnectivityManager:
    """Retrieve or initialize the global ConnectivityManager singleton."""
    global _GLOBAL_CONNECTIVITY_MANAGER
    if _GLOBAL_CONNECTIVITY_MANAGER is None:
        with _INIT_LOCK:
            alt_name = "connectivity" if __name__ == "companion.connectivity" else "companion.connectivity"
            alt_mod = sys.modules.get(alt_name)
            if alt_mod and getattr(alt_mod, "_GLOBAL_CONNECTIVITY_MANAGER", None) is not None:
                _GLOBAL_CONNECTIVITY_MANAGER = alt_mod._GLOBAL_CONNECTIVITY_MANAGER
            if _GLOBAL_CONNECTIVITY_MANAGER is None:
                _GLOBAL_CONNECTIVITY_MANAGER = ConnectivityManager()
    return _GLOBAL_CONNECTIVITY_MANAGER


def is_online() -> bool:
    """Convenience helper: returns True if DeskBot is fully online with cloud services."""
    return get_connectivity_manager().is_online()


def is_offline() -> bool:
    """Convenience helper: returns True if DeskBot has no internet access."""
    return get_connectivity_manager().is_offline()


def is_degraded() -> bool:
    """Convenience helper: returns True if internet is up but cloud AI is failing."""
    return get_connectivity_manager().is_degraded()
