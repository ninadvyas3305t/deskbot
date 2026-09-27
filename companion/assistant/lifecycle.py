"""Application and device lifecycle state management for DeskBot."""

from __future__ import annotations

import enum
import logging
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class AppLifecycleState(str, enum.Enum):
    """Macro lifecycle states of the DeskBot application."""
    STARTING = "STARTING"
    INITIALIZING = "INITIALIZING"
    WAITING_FOR_DEVICE = "WAITING_FOR_DEVICE"
    CONNECTING = "CONNECTING"
    READY = "READY"
    RUNNING = "RUNNING"
    DISCONNECTED = "DISCONNECTED"


class AppLifecycleManager:
    """Coordinates application lifecycle transitions and notifies UI listeners (e.g. system tray)."""

    def __init__(self):
        self.state: AppLifecycleState = AppLifecycleState.STARTING
        self._listeners: List[Callable[[AppLifecycleState, str], None]] = []

    @property
    def current_state(self) -> AppLifecycleState:
        return self.state

    def add_listener(self, listener: Callable[[AppLifecycleState, str], None]) -> None:
        """Register a callback for lifecycle state changes."""
        self._listeners.append(listener)

    def transition_to(self, new_state: AppLifecycleState, details: str = "") -> None:
        """Transition application lifecycle state and notify listeners."""
        old_state = self.state
        self.state = new_state

        msg = f"[APP] Lifecycle: {old_state} -> {new_state}"
        if details:
            msg += f" ({details})"
        logger.info(msg)

        for listener in self._listeners:
            try:
                listener(new_state, details)
            except Exception as err:
                logger.debug("Lifecycle listener error: %s", err)

    def get_status_description(self) -> str:
        """Return a human-readable status string suitable for system tray tooltips."""
        if self.state == AppLifecycleState.STARTING:
            return "DeskBot: Starting..."
        elif self.state == AppLifecycleState.INITIALIZING:
            return "DeskBot: Initializing models..."
        elif self.state == AppLifecycleState.WAITING_FOR_DEVICE:
            return "DeskBot: Waiting for hardware..."
        elif self.state == AppLifecycleState.CONNECTING:
            return "DeskBot: Connecting to ESP32..."
        elif self.state in (AppLifecycleState.READY, AppLifecycleState.RUNNING):
            return "DeskBot: Ready - Hey Jarvis"
        elif self.state == AppLifecycleState.DISCONNECTED:
            return "DeskBot: Device Disconnected"
        return "DeskBot: Active"


_GLOBAL_LIFECYCLE_MANAGER: Optional[AppLifecycleManager] = None


def get_lifecycle_manager() -> AppLifecycleManager:
    """Singleton getter for the application lifecycle manager."""
    global _GLOBAL_LIFECYCLE_MANAGER
    if _GLOBAL_LIFECYCLE_MANAGER is None:
        _GLOBAL_LIFECYCLE_MANAGER = AppLifecycleManager()
    return _GLOBAL_LIFECYCLE_MANAGER
