"""Google Lens-inspired ambient screen-edge illumination overlay for DeskBot 2.0.

Provides an ethereal, non-interactive, click-through border glow around screen edges
synced with voice assistant lifecycle states (Wake, Listening, Thinking, Executing).
"""

from __future__ import annotations

import math
import time
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget


class ScreenEdgeOverlay(QWidget):
    """Transparent, click-through desktop overlay providing perimeter edge lighting."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # Essential transparent, floating, non-interactive window flags
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput
            | Qt.Tool
            | Qt.SubWindow
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._enabled: bool = True
        self._state: str = "IDLE"
        self._opacity: float = 0.0
        self._target_opacity: float = 0.0

        # Colors corresponding to assistant states
        self._color_cyan = QColor(0, 229, 255)
        self._color_violet = QColor(157, 78, 221)
        self._color_emerald = QColor(0, 230, 118)
        self._color_coral = QColor(255, 61, 113)
        self._color_amber = QColor(255, 179, 0)
        self._current_color = self._color_cyan

        # Animation parameters
        self._phase: float = 0.0
        self._border_depth: int = 28  # Pixels inward from edge
        self._temporarily_suppressed: bool = False

        # Fit to primary screen
        self._fit_to_screen()

        # 60 FPS animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(16)

    def _fit_to_screen(self) -> None:
        """Position overlay across the active primary display screen."""
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            self.setGeometry(geo)

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Master toggle for the ambient edge illumination effect."""
        self._enabled = bool(enabled)
        if not self._enabled:
            self._target_opacity = 0.0
            self.hide()
        else:
            if self._state != "IDLE":
                self.show()

    def set_assistant_state(self, state: str) -> None:
        """Sync overlay lighting state with assistant state machine."""
        clean_state = str(state or "").upper().replace("STATE_", "")
        self._state = clean_state

        if not self._enabled:
            self._target_opacity = 0.0
            return

        if clean_state == "IDLE":
            self._target_opacity = 0.0
        elif clean_state in ("LISTENING", "WAKE"):
            self._current_color = self._color_cyan
            self._target_opacity = 0.85
            self.show()
        elif clean_state == "FOLLOW_UP":
            self._current_color = self._color_amber
            self._target_opacity = 0.80
            self.show()
        elif clean_state in ("THINKING", "SCREEN_ANALYSIS", "TRANSCRIBING"):
            self._current_color = self._color_violet
            self._target_opacity = 0.80
            self.show()
        elif clean_state == "EXECUTING":
            self._current_color = self._color_emerald
            self._target_opacity = 0.80
            self.show()
        elif clean_state == "SPEAKING":
            self._current_color = self._color_cyan
            self._target_opacity = 0.55
            self.show()
        elif clean_state == "ERROR":
            self._current_color = self._color_coral
            self._target_opacity = 0.85
            self.show()
        else:
            self._target_opacity = 0.0

    def suppress_for_screenshot(self, duration_ms: int = 300) -> None:
        """Temporarily hide the overlay so it does not contaminate screen inspection."""
        self._temporarily_suppressed = True
        self.hide()
        QTimer.singleShot(duration_ms, self._restore_after_screenshot)

    def _restore_after_screenshot(self) -> None:
        self._temporarily_suppressed = False
        if self._enabled and self._target_opacity > 0.01:
            self.show()

    def _on_tick(self) -> None:
        """Advance pulse phase and smooth opacity interpolation."""
        # Interpolate opacity towards target
        self._opacity += (self._target_opacity - self._opacity) * 0.14

        # Advance travelling animation phase
        if self._state in ("THINKING", "SCREEN_ANALYSIS"):
            self._phase += 0.08
        elif self._state == "EXECUTING":
            self._phase += 0.12
        else:
            self._phase += 0.04

        # If fully faded out and target is 0, hide widget to conserve GPU resources
        if self._opacity < 0.01 and self._target_opacity <= 0.01:
            if self.isVisible():
                self.hide()
        elif not self.isVisible() and self._enabled and self._opacity > 0.02 and not self._temporarily_suppressed:
            self.show()

        if self.isVisible():
            self.update()

    def paintEvent(self, event) -> None:
        if self._opacity <= 0.01 or self._temporarily_suppressed:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()
        depth = self._border_depth

        # Breathing / traveling pulse modulation
        pulse = (math.sin(self._phase) * 0.20 + 0.80) * self._opacity
        alpha = int(255 * pulse)
        r, g, b = self._current_color.red(), self._current_color.green(), self._current_color.blue()

        glow_start = QColor(r, g, b, alpha)
        glow_end = QColor(r, g, b, 0)

        # 1. Top Edge Gradient
        top_grad = QLinearGradient(0, 0, 0, depth)
        top_grad.setColorAt(0.0, glow_start)
        top_grad.setColorAt(1.0, glow_end)
        painter.fillRect(QRectF(0, 0, w, depth), QBrush(top_grad))

        # 2. Bottom Edge Gradient
        bot_grad = QLinearGradient(0, h, 0, h - depth)
        bot_grad.setColorAt(0.0, glow_start)
        bot_grad.setColorAt(1.0, glow_end)
        painter.fillRect(QRectF(0, h - depth, w, depth), QBrush(bot_grad))

        # 3. Left Edge Gradient
        left_grad = QLinearGradient(0, 0, depth, 0)
        left_grad.setColorAt(0.0, glow_start)
        left_grad.setColorAt(1.0, glow_end)
        painter.fillRect(QRectF(0, 0, depth, h), QBrush(left_grad))

        # 4. Right Edge Gradient
        right_grad = QLinearGradient(w, 0, w - depth, 0)
        right_grad.setColorAt(0.0, glow_start)
        right_grad.setColorAt(1.0, glow_end)
        painter.fillRect(QRectF(w - depth, 0, depth, h), QBrush(right_grad))

        # 5. Crisp 1.5px perimeter outline
        painter.setPen(QPen(QColor(r, g, b, int(alpha * 0.9)), 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0))


_GLOBAL_OVERLAY: Optional[ScreenEdgeOverlay] = None


def get_screen_overlay() -> Optional[ScreenEdgeOverlay]:
    """Retrieve application-wide ScreenEdgeOverlay singleton if initialized."""
    import sys
    global _GLOBAL_OVERLAY
    if "_deskbot_global_screen_overlay" in sys.modules:
        return sys.modules["_deskbot_global_screen_overlay"]
    return _GLOBAL_OVERLAY


def initialize_screen_overlay() -> ScreenEdgeOverlay:
    """Initialize the application-wide screen edge illumination overlay."""
    import sys
    global _GLOBAL_OVERLAY
    if "_deskbot_global_screen_overlay" in sys.modules:
        return sys.modules["_deskbot_global_screen_overlay"]
    if _GLOBAL_OVERLAY is None:
        _GLOBAL_OVERLAY = ScreenEdgeOverlay()
    sys.modules["_deskbot_global_screen_overlay"] = _GLOBAL_OVERLAY
    return _GLOBAL_OVERLAY


# Alias both module paths to avoid duplicate class identities across import styles
import sys
_overlay_mod = sys.modules.get(__name__)
if _overlay_mod:
    sys.modules["ui.edge_overlay"] = _overlay_mod
    sys.modules["companion.ui.edge_overlay"] = _overlay_mod
