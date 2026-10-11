"""Google-inspired ambient desktop screen-edge illumination overlay for DeskBot 2.0.

Provides a subtle, crystal-clear, multicolored luminous glass edge glow around
the entire computer screen, synchronized with assistant lifecycle states.
Click-through, non-focus-stealing, and completely transparent at screen center.
"""

from __future__ import annotations

import math
import sys
from typing import Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget


# Google's spectral color stops for luminous glass perimeter glow:
# Blue -> Cyan -> Green -> Yellow -> Warm Red -> Subtle Purple -> Blue
GOOGLE_SPECTRUM_STOPS = [
    (0.000, (66, 133, 244)),   # Google Blue
    (0.167, (36, 212, 236)),   # Aqua / Cyan
    (0.333, (52, 168, 83)),    # Google Green
    (0.500, (251, 188, 5)),    # Google Amber / Yellow
    (0.667, (234, 67, 53)),    # Google Warm Red / Coral
    (0.833, (161, 66, 244)),   # Subtle Purple / Violet
    (1.000, (66, 133, 244)),   # Blue
]

# Warm coral/amber palette for ERROR state
ERROR_SPECTRUM_STOPS = [
    (0.000, (255, 112, 67)),   # Coral Orange
    (0.333, (255, 82, 82)),    # Soft Crimson
    (0.667, (255, 171, 64)),   # Warm Amber
    (1.000, (255, 112, 67)),   # Coral Orange
]


def sample_spectrum_color(
    u: float,
    phase: float,
    is_error: bool = False,
    highlight_boost: float = 1.0,
) -> Tuple[int, int, int]:
    """Sample a smooth, cosine-interpolated color from the Google spectrum."""
    stops = ERROR_SPECTRUM_STOPS if is_error else GOOGLE_SPECTRUM_STOPS
    tau = (u - phase) % 1.0

    for i in range(len(stops) - 1):
        s0, c0 = stops[i]
        s1, c1 = stops[i + 1]
        if s0 <= tau <= s1:
            rel = (tau - s0) / (s1 - s0)
            smooth = 0.5 - 0.5 * math.cos(math.pi * rel)
            r = int(c0[0] + (c1[0] - c0[0]) * smooth)
            g = int(c0[1] + (c1[1] - c0[1]) * smooth)
            b = int(c0[2] + (c1[2] - c0[2]) * smooth)

            # Apply gentle traveling luminous highlight
            if highlight_boost > 0.01:
                hl = 0.09 * highlight_boost * math.sin(2.0 * math.pi * (2.0 * u - phase * 1.4))
                r = min(255, max(0, int(r * (1.0 + hl))))
                g = min(255, max(0, int(g * (1.0 + hl))))
                b = min(255, max(0, int(b * (1.0 + hl))))
            return r, g, b

    c = stops[0][1]
    return c[0], c[1], c[2]


class ScreenEdgeOverlay(QWidget):
    """Transparent, click-through desktop overlay providing Google-inspired perimeter edge illumination."""

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
        self.setFocusPolicy(Qt.NoFocus)

        # Configuration options (customizable in Settings)
        self._enabled: bool = True
        self._glow_intensity: float = 0.70    # 0.20 to 1.00
        self._border_depth: int = 24          # 12 to 48 px inward glow
        self._speed_multiplier: float = 1.0   # 0.4 to 2.0x animation speed

        # Runtime animation state
        self._state: str = "IDLE"
        self._opacity: float = 0.0
        self._target_opacity: float = 0.0
        self._speed_factor: float = 1.0
        self._intensity_factor: float = 1.0

        self._phase: float = 0.0
        self._breath_phase: float = 0.0
        self._temporarily_suppressed: bool = False

        # Fit to primary display and monitor display changes
        self._fit_to_screen()
        primary = QGuiApplication.primaryScreen()
        if primary:
            try:
                primary.geometryChanged.connect(lambda _: self._fit_to_screen())
            except Exception:
                pass

        # 60 FPS animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

        # Apply platform-level click-through safety
        self._apply_native_window_flags()

    def _fit_to_screen(self) -> None:
        """Position overlay across the active primary display screen."""
        screen = QGuiApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())

    def _apply_native_window_flags(self) -> None:
        """Apply OS-level non-activating, click-through window properties where supported."""
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                GWL_EXSTYLE = -20
                WS_EX_TRANSPARENT = 0x00000020
                WS_EX_LAYERED = 0x00080000
                WS_EX_NOACTIVATE = 0x08000000
                WS_EX_TOOLWINDOW = 0x00000080
                user32 = ctypes.windll.user32
                style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(
                    hwnd,
                    GWL_EXSTYLE,
                    style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
                )
            except Exception:
                pass

    # --- Configuration Setters & Getters ---

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Master toggle for desktop edge illumination."""
        self._enabled = bool(enabled)
        if not self._enabled:
            self._target_opacity = 0.0
            self._opacity = 0.0
            self.hide()
            if self._timer.isActive():
                self._timer.stop()
        else:
            if self._state not in ("IDLE", ""):
                self.set_assistant_state(self._state)

    @property
    def glow_intensity(self) -> float:
        return self._glow_intensity

    def set_glow_intensity(self, intensity: float) -> None:
        """Adjust glow intensity (0.20 to 1.00)."""
        self._glow_intensity = max(0.20, min(1.00, float(intensity)))
        if self.isVisible():
            self.update()

    @property
    def edge_thickness(self) -> int:
        return self._border_depth

    def set_edge_thickness(self, thickness: int) -> None:
        """Adjust inward edge illumination depth (12 to 48 px)."""
        self._border_depth = max(12, min(48, int(thickness)))
        if self.isVisible():
            self.update()

    @property
    def animation_speed(self) -> float:
        return self._speed_multiplier

    def set_animation_speed(self, speed: float) -> None:
        """Adjust animation speed multiplier (0.4 to 2.0x)."""
        self._speed_multiplier = max(0.4, min(2.0, float(speed)))

    def load_config(self, config_mgr) -> None:
        """Load user preferences from config manager."""
        if not config_mgr:
            return
        self.set_enabled(bool(config_mgr.get("screen_overlay_enabled", True)))
        self.set_glow_intensity(float(config_mgr.get("overlay_glow_intensity", 0.70)))
        self.set_edge_thickness(int(config_mgr.get("overlay_edge_thickness", 24)))
        self.set_animation_speed(float(config_mgr.get("overlay_animation_speed", 1.0)))

    # --- Assistant State Synchronization ---

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
            self._target_opacity = 0.85
            self._speed_factor = 1.0
            self._intensity_factor = 1.0
            self._start_animation()
        elif clean_state == "FOLLOW_UP":
            self._target_opacity = 0.80
            self._speed_factor = 0.85
            self._intensity_factor = 0.95
            self._start_animation()
        elif clean_state in ("THINKING", "SCREEN_ANALYSIS", "TRANSCRIBING"):
            self._target_opacity = 0.65
            self._speed_factor = 0.50  # Calmer, slower flowing movement
            self._intensity_factor = 0.75
            self._start_animation()
        elif clean_state == "EXECUTING":
            self._target_opacity = 0.95  # Confident, slightly energized intensity
            self._speed_factor = 1.25
            self._intensity_factor = 1.15
            self._start_animation()
        elif clean_state == "SPEAKING":
            self._target_opacity = 0.60
            self._speed_factor = 0.70
            self._intensity_factor = 0.80
            self._start_animation()
        elif clean_state == "ERROR":
            self._target_opacity = 0.80
            self._speed_factor = 0.40
            self._intensity_factor = 0.85
            self._start_animation()
        else:
            self._target_opacity = 0.0

    def _start_animation(self) -> None:
        """Ensure overlay window and timer are active."""
        if not self._temporarily_suppressed and self._enabled:
            if not self.isVisible():
                self.show()
            if not self._timer.isActive():
                self._timer.start(16)

    def suppress_for_screenshot(self, duration_ms: int = 300) -> None:
        """Temporarily hide the overlay so it does not contaminate screen inspection."""
        self._temporarily_suppressed = True
        self.hide()
        QTimer.singleShot(duration_ms, self._restore_after_screenshot)

    def _restore_after_screenshot(self) -> None:
        self._temporarily_suppressed = False
        if self._enabled and self._target_opacity > 0.01:
            self.show()
            if not self._timer.isActive():
                self._timer.start(16)

    def _on_tick(self) -> None:
        """Advance animation phase and interpolate opacity smoothly."""
        # Smooth exponential interpolation towards target opacity
        self._opacity += (self._target_opacity - self._opacity) * 0.12

        # Advance color phase and gentle breathing phase
        delta = 0.0035 * self._speed_multiplier * self._speed_factor
        self._phase = (self._phase + delta) % 1.0
        self._breath_phase = (self._breath_phase + 0.04 * self._speed_multiplier) % (2.0 * math.pi)

        # If fully faded out and target is 0, hide window and suspend timer to save GPU
        if self._opacity < 0.01 and self._target_opacity <= 0.01:
            self._opacity = 0.0
            if self.isVisible():
                self.hide()
            if self._timer.isActive():
                self._timer.stop()
        elif not self.isVisible() and self._enabled and self._opacity > 0.02 and not self._temporarily_suppressed:
            self.show()

        if self.isVisible():
            self.update()

    def paintEvent(self, event) -> None:
        if self._opacity <= 0.01 or self._temporarily_suppressed:
            return

        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        depth = self._border_depth
        L = 2.0 * (w + h)

        # Organic breathing pulse: gentle 10% undulation
        breath = 0.90 + 0.10 * math.sin(self._breath_phase)
        effective_alpha = self._opacity * self._glow_intensity * self._intensity_factor * breath

        base_alpha = int(170 * effective_alpha)
        edge_alpha = int(230 * effective_alpha)
        if base_alpha <= 0 and edge_alpha <= 0:
            return

        is_error = (self._state == "ERROR")

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        num_stops = 12

        # 1. Top Edge Strip
        top_strip = QImage(w, depth, QImage.Format_ARGB32_Premultiplied)
        top_strip.fill(Qt.transparent)
        tsp = QPainter(top_strip)
        tgrad = QLinearGradient(0, 0, w, 0)
        for k in range(num_stops + 1):
            pos = k / float(num_stops)
            u = (pos * w) / L
            r, g, b = sample_spectrum_color(u, self._phase, is_error=is_error)
            tgrad.setColorAt(pos, QColor(r, g, b, base_alpha))
        tsp.fillRect(0, 0, w, depth, tgrad)

        tfade = QLinearGradient(0, 0, 0, depth)
        tfade.setColorAt(0.0, QColor(0, 0, 0, 255))
        tfade.setColorAt(0.35, QColor(0, 0, 0, 130))
        tfade.setColorAt(1.0, QColor(0, 0, 0, 0))
        tsp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        tsp.fillRect(0, 0, w, depth, tfade)
        tsp.end()
        painter.drawImage(0, 0, top_strip)

        # 2. Bottom Edge Strip
        bot_strip = QImage(w, depth, QImage.Format_ARGB32_Premultiplied)
        bot_strip.fill(Qt.transparent)
        bsp = QPainter(bot_strip)
        bgrad = QLinearGradient(0, 0, w, 0)
        for k in range(num_stops + 1):
            pos = k / float(num_stops)
            s = w + h + (1.0 - pos) * w
            u = s / L
            r, g, b = sample_spectrum_color(u, self._phase, is_error=is_error)
            bgrad.setColorAt(pos, QColor(r, g, b, base_alpha))
        bsp.fillRect(0, 0, w, depth, bgrad)

        bfade = QLinearGradient(0, depth, 0, 0)
        bfade.setColorAt(0.0, QColor(0, 0, 0, 255))
        bfade.setColorAt(0.35, QColor(0, 0, 0, 130))
        bfade.setColorAt(1.0, QColor(0, 0, 0, 0))
        bsp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        bsp.fillRect(0, 0, w, depth, bfade)
        bsp.end()
        painter.drawImage(0, h - depth, bot_strip)

        # 3. Left Edge Strip
        left_strip = QImage(depth, h, QImage.Format_ARGB32_Premultiplied)
        left_strip.fill(Qt.transparent)
        lsp = QPainter(left_strip)
        lgrad = QLinearGradient(0, 0, 0, h)
        for k in range(num_stops + 1):
            pos = k / float(num_stops)
            s = 2.0 * w + h + (1.0 - pos) * h
            u = s / L
            r, g, b = sample_spectrum_color(u, self._phase, is_error=is_error)
            lgrad.setColorAt(pos, QColor(r, g, b, base_alpha))
        lsp.fillRect(0, 0, depth, h, lgrad)

        lfade = QLinearGradient(0, 0, depth, 0)
        lfade.setColorAt(0.0, QColor(0, 0, 0, 255))
        lfade.setColorAt(0.35, QColor(0, 0, 0, 130))
        lfade.setColorAt(1.0, QColor(0, 0, 0, 0))
        lsp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        lsp.fillRect(0, 0, depth, h, lfade)
        lsp.end()
        painter.drawImage(0, 0, left_strip)

        # 4. Right Edge Strip
        right_strip = QImage(depth, h, QImage.Format_ARGB32_Premultiplied)
        right_strip.fill(Qt.transparent)
        rsp = QPainter(right_strip)
        rgrad = QLinearGradient(0, 0, 0, h)
        for k in range(num_stops + 1):
            pos = k / float(num_stops)
            s = w + pos * h
            u = s / L
            r, g, b = sample_spectrum_color(u, self._phase, is_error=is_error)
            rgrad.setColorAt(pos, QColor(r, g, b, base_alpha))
        rsp.fillRect(0, 0, depth, h, rgrad)

        rfade = QLinearGradient(depth, 0, 0, 0)
        rfade.setColorAt(0.0, QColor(0, 0, 0, 255))
        rfade.setColorAt(0.35, QColor(0, 0, 0, 130))
        rfade.setColorAt(1.0, QColor(0, 0, 0, 0))
        rsp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        rsp.fillRect(0, 0, depth, h, rfade)
        rsp.end()
        painter.drawImage(w - depth, 0, right_strip)

        # 5. Crisp, delicate 1.5px perimeter contour
        pen_grad = QLinearGradient(0, 0, w, 0)
        for k in range(num_stops + 1):
            pos = k / float(num_stops)
            u = (pos * w) / L
            r, g, b = sample_spectrum_color(u, self._phase, is_error=is_error)
            pen_grad.setColorAt(pos, QColor(r, g, b, edge_alpha))

        painter.setPen(QPen(QBrush(pen_grad), 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(0.75, 0.75, w - 1.5, h - 1.5))

    def closeEvent(self, event) -> None:
        """Clean shutdown and timer suspension."""
        if self._timer.isActive():
            self._timer.stop()
        super().closeEvent(event)


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
        # Automatically load config if config_manager is available
        try:
            from platform_layer.config_manager import get_config_manager
            _GLOBAL_OVERLAY.load_config(get_config_manager())
        except Exception:
            pass
    sys.modules["_deskbot_global_screen_overlay"] = _GLOBAL_OVERLAY
    return _GLOBAL_OVERLAY


# Alias both module paths to avoid duplicate class identities across import styles
import sys
_overlay_mod = sys.modules.get(__name__)
if _overlay_mod:
    sys.modules["ui.edge_overlay"] = _overlay_mod
    sys.modules["companion.ui.edge_overlay"] = _overlay_mod
