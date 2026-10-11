"""Thread-safe event bridge connecting DeskBot backend to PySide6 Desktop GUI."""

from __future__ import annotations

import logging
import sys
import time
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class DeskBotBridge(QObject):
    """Qt Signal bridge for real-time synchronization between the assistant backend and UI.

    Emits thread-safe signals whenever state changes, transcripts arrive, tools execute,
    or device hardware events occur.
    """

    # Assistant & Voice signals
    state_changed = Signal(str, str, str)  # (old_state, new_state, context)
    wake_detected = Signal(float)  # (confidence score)
    touch_triggered = Signal()  # capacitive hardware touch
    speech_start = Signal()  # user began speaking
    speech_end = Signal()  # user stopped speaking
    speech_level = Signal(float)  # mic audio RMS level (0.0 to 1.0)
    transcript_received = Signal(str)  # recognized text
    ai_intent_resolved = Signal(str, str)  # (action, query)
    direct_answer_emitted = Signal(str)  # spoken answer
    tool_executed = Signal(str, bool, str)  # (tool_name, success, message)

    # Device & Hardware signals
    device_status_changed = Signal(bool, str, str)  # (is_connected, port, description)
    device_metrics_updated = Signal(dict)  # {"baud": 921600, "sample_rate": 16000, "gain": 1.2, ...}
    wifi_status_changed = Signal(bool, str, str)  # (is_connected, mode, ip_or_ssid)

    # Activity log stream
    activity_logged = Signal(dict)  # structured event dict for the Activity page

    # Connectivity signals
    connectivity_changed = Signal(str, str)  # (status: "ONLINE"|"OFFLINE"|"DEGRADED", details: str)

    # Overlay control signals
    overlay_visibility_toggled = Signal(bool)
    overlay_state_synced = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._current_state: str = "IDLE"
        self._device_connected: bool = False
        self._current_port: str = ""

    @property
    def current_state(self) -> str:
        return self._current_state

    @property
    def is_device_connected(self) -> bool:
        return self._device_connected

    # --- Emitter Helpers (Safe to call from background threads) ---

    def notify_state_change(self, old_state: str, new_state: str, context: str = "") -> None:
        self._current_state = new_state
        self.state_changed.emit(old_state, new_state, context)
        self.overlay_state_synced.emit(new_state)
        self.log_activity(
            category="STATE",
            title=f"State: {new_state}",
            details=context or f"Transitioned from {old_state}",
            status="info",
        )

    def notify_wake(self, confidence: float = 1.0) -> None:
        self.wake_detected.emit(confidence)
        self.log_activity(
            category="WAKE",
            title="Wake Word Detected",
            details=f"Confidence: {confidence:.2f}",
            status="success",
        )

    def notify_touch(self) -> None:
        self.touch_triggered.emit()
        self.log_activity(
            category="TOUCH",
            title="Hardware Touch Trigger",
            details="Activated via TTP223 capacitive sensor",
            status="success",
        )

    def notify_speech_start(self) -> None:
        self.speech_start.emit()

    def notify_speech_end(self) -> None:
        self.speech_end.emit()

    def notify_speech_level(self, level: float) -> None:
        self.speech_level.emit(max(0.0, min(1.0, float(level))))

    def notify_transcript(self, text: str) -> None:
        self.transcript_received.emit(text)
        self.log_activity(
            category="STT",
            title="Speech Recognized",
            details=f'"{text}"',
            status="info",
        )

    def notify_ai_intent(self, action: str, query: str = "") -> None:
        self.ai_intent_resolved.emit(action, query)
        self.log_activity(
            category="AI",
            title=f"Intent: {action}",
            details=query or "Action intent classified",
            status="info",
        )

    def notify_direct_answer(self, answer: str) -> None:
        self.direct_answer_emitted.emit(answer)
        self.log_activity(
            category="ANSWER",
            title="AI Response",
            details=answer,
            status="success",
        )

    def notify_tool_result(self, tool_name: str, success: bool, message: str = "") -> None:
        self.tool_executed.emit(tool_name, success, message)
        self.log_activity(
            category="TOOL",
            title=f"Tool: {tool_name}",
            details=message or ("Succeeded" if success else "Failed"),
            status="success" if success else "error",
        )

    def notify_device_status(self, connected: bool, port: str = "", description: str = "") -> None:
        self._device_connected = connected
        self._current_port = port
        self.device_status_changed.emit(connected, port, description)
        self.log_activity(
            category="DEVICE",
            title="Hardware Connected" if connected else "Hardware Disconnected",
            details=f"Port: {port} ({description})" if connected else "Waiting for ESP32 connection...",
            status="success" if connected else "warning",
        )

    def notify_wifi_status(self, connected: bool, mode: str = "Station", target: str = "") -> None:
        self.wifi_status_changed.emit(connected, mode, target)
        self.log_activity(
            category="NETWORK",
            title=f"Wi-Fi {mode}: {'Connected' if connected else 'Disconnected'}",
            details=f"Target: {target}" if target else "",
            status="success" if connected else "warning",
        )

    def notify_connectivity(self, status: str, details: str = "") -> None:
        self.connectivity_changed.emit(status, details)
        self.log_activity(
            category="NETWORK",
            title=f"Connectivity: {status}",
            details=details or f"Mode: {status}",
            status="success" if status == "ONLINE" else ("warning" if status == "DEGRADED" else "info"),
        )

    def log_activity(self, category: str, title: str, details: str = "", status: str = "info") -> None:
        event = {
            "timestamp": time.time(),
            "category": category,
            "title": title,
            "details": details,
            "status": status,
        }
        self.activity_logged.emit(event)


# Global singleton instance
_GLOBAL_BRIDGE: Optional[DeskBotBridge] = None


def get_ui_bridge() -> DeskBotBridge:
    """Return the application-wide DeskBotBridge singleton."""
    global _GLOBAL_BRIDGE
    if "_deskbot_global_ui_bridge" in sys.modules:
        return sys.modules["_deskbot_global_ui_bridge"]
    if _GLOBAL_BRIDGE is None:
        _GLOBAL_BRIDGE = DeskBotBridge()
    sys.modules["_deskbot_global_ui_bridge"] = _GLOBAL_BRIDGE
    return _GLOBAL_BRIDGE


def _safe_get_bridge() -> Optional[DeskBotBridge]:
    """Safely return UI bridge instance across modules."""
    try:
        return get_ui_bridge()
    except Exception:
        return None


# Alias both module paths to avoid duplicate class identities across import styles
_current_mod = sys.modules.get(__name__)
if _current_mod:
    sys.modules["ui.bridge"] = _current_mod
    sys.modules["companion.ui.bridge"] = _current_mod
