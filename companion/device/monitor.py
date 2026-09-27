"""Hotplug monitor with automatic background reconnect for DeskBot hardware."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from .deskbot_device import DeskBotDevice

logger = logging.getLogger(__name__)


class DeviceMonitor:
    """Monitors USB connection state, detects disconnections, and automatically reconnects."""

    def __init__(
        self,
        device: DeskBotDevice,
        on_connected: Optional[Callable[[str], None]] = None,
        on_disconnected: Optional[Callable[[], None]] = None,
        scan_interval: float = 1.5,
    ):
        self.device = device
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.scan_interval = scan_interval

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the background hotplug monitoring thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._monitor_loop,
                name="DeskBotDeviceMonitor",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop background monitoring."""
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _monitor_loop(self) -> None:
        """Background loop continuously scanning for device connection status."""
        while self._running:
            if not self.device.is_connected:
                # Scan for reconnect candidate
                discovered = self.device.discover(verify_handshake=True)
                if discovered:
                    logger.info("[DEVICE] DeskBot detected on %s", discovered)
                    logger.info("[DEVICE] Handshake successful")
                    if self.device.connect(discovered):
                        logger.info("[DEVICE] Reconnected")
                        logger.info("[DEVICE] Audio restored")
                        if self.on_connected:
                            try:
                                self.on_connected(discovered)
                            except Exception as err:
                                logger.debug("Reconnect callback error: %s", err)
            else:
                # Connected: health check
                pass

            time.sleep(self.scan_interval)

    def notify_disconnected(self) -> None:
        """Manually trigger disconnected state when an I/O error occurs in the audio reader."""
        if self.device.is_connected:
            self.device.disconnect()

        logger.warning("[DEVICE] DeskBot disconnected")
        if self.on_disconnected:
            try:
                self.on_disconnected()
            except Exception as err:
                logger.debug("Disconnect callback error: %s", err)
