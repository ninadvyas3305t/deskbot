"""DASAI Mochi-inspired expressive animated face engine for DeskBot 2.0.

Renders an organic, emotive digital character closely following the aesthetic and
behavior of the DASAI Mochi robot:
- Luminous capsule / lozenge eyes and expressive curved arcs without mechanical pupils
- Natural breathing float and organic squashing blinks
- Iconic Mochi expressions: joyous smiling crescents (^ ^), alert listening pills,
  quizzical thinking asymmetry, focused execution slants, and speaking bounce
- Sleek obsidian glass visor stage with subtle top specular reflection
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QWidget


@dataclass
class MochiEyeState:
    """Visual geometry parameters for one eye in relative normalized coordinates."""
    width: float = 0.22         # Lozenge width
    height: float = 0.36        # Lozenge height (pill shape)
    corner_radius: float = 0.18 # Half of height for perfect capsule curvature
    center_y: float = 0.50      # Centered vertically (0.0 to 1.0)
    center_x_offset: float = 0.0# Saccadic glance shift
    tilt: float = 0.0           # Angle tilt in degrees
    lid_closure: float = 0.0    # 0.0 = fully open, 1.0 = fully squashed closed (blink)
    is_arc: bool = False        # True for signature Mochi happy smiling crescents (^ ^)
    arc_curve: float = 0.16     # Curvature depth of the smiling arc


class DeskBotFaceWidget(QWidget):
    """DASAI Mochi-inspired expressive vector face widget for DeskBot."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setMinimumSize(280, 160)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)

        # Current assistant state
        self._state: str = "IDLE"

        # Theme colors for the luminous eye core and glow
        self._core_color: QColor = QColor(255, 255, 255)       # Crisp luminous white core
        self._glow_color: QColor = QColor(0, 229, 255)         # Cyber Cyan bloom
        self._visor_bg: QColor = QColor(7, 10, 15)             # Obsidian helmet visor black
        self._visor_border: QColor = QColor(20, 29, 44)        # Subtle dark border

        # Eye parameters (current rendered vs target for smooth interpolation)
        self._cur_left = MochiEyeState()
        self._cur_right = MochiEyeState()
        self._tgt_left = MochiEyeState()
        self._tgt_right = MochiEyeState()

        # Audio reactivity (voice energy)
        self._audio_level: float = 0.0
        self._cur_audio_pulse: float = 0.0

        # Speaking animation
        self._speaking_phase: float = 0.0

        # Animation clock & breathing float
        self._anim_time: float = 0.0
        self._breath_offset_y: float = 0.0

        # Blinking mechanics (smooth squashing slit)
        self._is_blinking: bool = False
        self._blink_start_time: float = 0.0
        self._blink_duration: float = 0.14  # seconds
        self._next_blink_time: float = time.time() + random.uniform(2.5, 4.8)

        # Micro-gaze & idle tilts
        self._saccade_x: float = 0.0
        self._saccade_tilt: float = 0.0
        self._next_saccade_time: float = time.time() + random.uniform(3.0, 6.0)

        # 60 FPS animation loop
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_animation_tick)
        self._timer.start(16)  # ~60 FPS

        self._apply_state_targets("IDLE")

    @property
    def current_state(self) -> str:
        return self._state

    def set_assistant_state(self, new_state: str) -> None:
        """Update facial expression according to the assistant state."""
        clean_state = str(new_state or "").upper().replace("STATE_", "")
        if clean_state != self._state:
            self._state = clean_state
            self._apply_state_targets(clean_state)

    def set_audio_level(self, level: float) -> None:
        """Update live audio level (0.0 to 1.0) for acoustic reactivity."""
        self._audio_level = max(0.0, min(1.0, float(level)))

    def _apply_state_targets(self, state: str) -> None:
        """Apply DASAI Mochi expression targets for each assistant state."""
        # Baseline Mochi capsule proportions
        base_w = 0.22
        base_h = 0.36
        base_rad = 0.18
        base_y = 0.50

        if state == "IDLE":
            self._core_color = QColor(255, 255, 255)
            self._glow_color = QColor(0, 229, 255)
            self._tgt_left = MochiEyeState(
                width=base_w, height=base_h, corner_radius=base_rad,
                center_y=base_y, tilt=0.0, is_arc=False,
            )
            self._tgt_right = MochiEyeState(
                width=base_w, height=base_h, corner_radius=base_rad,
                center_y=base_y, tilt=0.0, is_arc=False,
            )

        elif state == "LISTENING":
            # Alert, wide tall capsules with curious slight inward tilt (/ \)
            self._core_color = QColor(255, 255, 255)
            self._glow_color = QColor(0, 229, 255)
            self._tgt_left = MochiEyeState(
                width=base_w * 0.95, height=base_h * 1.35, corner_radius=base_rad * 1.25,
                center_y=base_y, tilt=3.5, is_arc=False,
            )
            self._tgt_right = MochiEyeState(
                width=base_w * 0.95, height=base_h * 1.35, corner_radius=base_rad * 1.25,
                center_y=base_y, tilt=-3.5, is_arc=False,
            )

        elif state == "TRANSCRIBING":
            # Attentive pupils-equivalent lozenges scanning slightly up
            self._core_color = QColor(240, 245, 255)
            self._glow_color = QColor(124, 77, 255)  # Electric Violet
            self._tgt_left = MochiEyeState(
                width=base_w * 1.05, height=base_h * 1.10, corner_radius=base_rad,
                center_y=base_y - 0.03, center_x_offset=-0.02, tilt=1.0, is_arc=False,
            )
            self._tgt_right = MochiEyeState(
                width=base_w * 1.05, height=base_h * 1.10, corner_radius=base_rad,
                center_y=base_y - 0.03, center_x_offset=-0.02, tilt=-1.0, is_arc=False,
            )

        elif state in ("THINKING", "SCREEN_ANALYSIS"):
            # Iconic Mochi quizzical asymmetry: Left eye soft squint, Right eye inquisitive lift
            self._core_color = QColor(255, 255, 255)
            self._glow_color = QColor(170, 90, 255)  # Amethyst / Violet
            self._tgt_left = MochiEyeState(
                width=base_w * 0.88, height=base_h * 0.80, corner_radius=base_rad * 0.75,
                center_y=base_y + 0.03, tilt=-4.0, is_arc=False,
            )
            self._tgt_right = MochiEyeState(
                width=base_w * 1.05, height=base_h * 1.25, corner_radius=base_rad * 1.10,
                center_y=base_y - 0.05, tilt=4.0, is_arc=False,
            )

        elif state == "EXECUTING":
            # Focused, determined laser lozenges with forward focused slant (\ /)
            self._core_color = QColor(255, 255, 255)
            self._glow_color = QColor(0, 230, 118)  # Neon Emerald
            self._tgt_left = MochiEyeState(
                width=base_w * 1.15, height=base_h * 0.70, corner_radius=base_rad * 0.65,
                center_y=base_y + 0.02, tilt=-5.5, is_arc=False,
            )
            self._tgt_right = MochiEyeState(
                width=base_w * 1.15, height=base_h * 0.70, corner_radius=base_rad * 0.65,
                center_y=base_y + 0.02, tilt=5.5, is_arc=False,
            )

        elif state == "SPEAKING":
            # Bouncing expressive communicative capsules
            self._core_color = QColor(255, 255, 255)
            self._glow_color = QColor(0, 229, 255)
            self._tgt_left = MochiEyeState(
                width=base_w * 1.05, height=base_h * 1.15, corner_radius=base_rad * 1.05,
                center_y=base_y - 0.02, tilt=1.5, is_arc=False,
            )
            self._tgt_right = MochiEyeState(
                width=base_w * 1.05, height=base_h * 1.15, corner_radius=base_rad * 1.05,
                center_y=base_y - 0.02, tilt=-1.5, is_arc=False,
            )

        elif state in ("FOLLOW_UP", "SUCCESS"):
            # THE SIGNATURE DASAI MOCHI HAPPY FACE: Joyous upward-curved smiling crescents (^ ^)
            self._core_color = QColor(255, 255, 255)
            self._glow_color = QColor(0, 229, 255) if state == "FOLLOW_UP" else QColor(0, 230, 118)
            self._tgt_left = MochiEyeState(
                width=base_w * 1.10, height=base_h * 0.85, corner_radius=base_rad,
                center_y=base_y - 0.01, tilt=0.0, is_arc=True, arc_curve=0.18,
            )
            self._tgt_right = MochiEyeState(
                width=base_w * 1.10, height=base_h * 0.85, corner_radius=base_rad,
                center_y=base_y - 0.01, tilt=0.0, is_arc=True, arc_curve=0.18,
            )

        elif state == "ERROR":
            # Puzzled / frustrated downward slant in neon coral
            self._core_color = QColor(255, 255, 255)
            self._glow_color = QColor(255, 61, 113)  # Neon Coral
            self._tgt_left = MochiEyeState(
                width=base_w * 1.05, height=base_h * 0.65, corner_radius=base_rad * 0.65,
                center_y=base_y + 0.02, tilt=14.0, is_arc=False,
            )
            self._tgt_right = MochiEyeState(
                width=base_w * 1.05, height=base_h * 0.65, corner_radius=base_rad * 0.65,
                center_y=base_y + 0.02, tilt=-14.0, is_arc=False,
            )

        elif state in ("SLEEPY", "OFFLINE"):
            # Calm droopy half-closed sleeping lozenge slits (- -)
            self._core_color = QColor(200, 215, 235)
            self._glow_color = QColor(100, 116, 139)  # Dim slate
            self._tgt_left = MochiEyeState(
                width=base_w * 1.05, height=base_h * 0.22, corner_radius=base_rad * 0.20,
                center_y=base_y + 0.06, tilt=0.0, is_arc=False,
            )
            self._tgt_right = MochiEyeState(
                width=base_w * 1.05, height=base_h * 0.22, corner_radius=base_rad * 0.20,
                center_y=base_y + 0.06, tilt=0.0, is_arc=False,
            )

    def _on_animation_tick(self) -> None:
        """Advance animation physics, breathing float, blinking, and spring interpolation."""
        now = time.time()
        self._anim_time += 0.022

        # 1. Natural Breathing Floating Bob (soft gentle vertical oscillation)
        self._breath_offset_y = math.sin(self._anim_time * 2.2) * 2.2

        # 2. Blinking State Machine
        if not self._is_blinking and now >= self._next_blink_time:
            if self._state not in ("ERROR", "SLEEPY", "OFFLINE", "FOLLOW_UP", "SUCCESS"):
                self._is_blinking = True
                self._blink_start_time = now
                self._blink_duration = random.choice([0.13, 0.15, 0.17])
                self._next_blink_time = now + random.uniform(2.6, 5.0)

        current_lid = 0.0
        if self._is_blinking:
            elapsed = now - self._blink_start_time
            if elapsed < self._blink_duration:
                # Sine progress: 0 -> 1 -> 0
                progress = elapsed / self._blink_duration
                current_lid = math.sin(progress * math.pi)
            else:
                self._is_blinking = False
                current_lid = 0.0

        # 3. Idle Micro-Gaze and Tilt
        if self._state == "IDLE":
            if now >= self._next_saccade_time:
                self._saccade_x = random.choice([-0.02, 0.0, 0.02, 0.0])
                self._saccade_tilt = random.choice([-1.5, 0.0, 1.5, 0.0])
                self._next_saccade_time = now + random.uniform(2.5, 5.0)
        else:
            self._saccade_x = 0.0
            self._saccade_tilt = 0.0

        # 4. Audio Reactivity
        target_pulse = self._audio_level if self._state in ("LISTENING", "SPEAKING") else 0.0
        self._cur_audio_pulse += (target_pulse - self._cur_audio_pulse) * 0.25

        # 5. Speaking Animation Phase
        if self._state == "SPEAKING":
            self._speaking_phase += 0.24
        else:
            self._speaking_phase = 0.0

        # 6. Smooth Spring Interpolation (k = 0.18)
        k = 0.18
        self._interpolate_eye(self._cur_left, self._tgt_left, k, current_lid, self._saccade_x, self._saccade_tilt)
        self._interpolate_eye(self._cur_right, self._tgt_right, k, current_lid, self._saccade_x, self._saccade_tilt)

        self.update()

    def _interpolate_eye(
        self,
        cur: MochiEyeState,
        tgt: MochiEyeState,
        k: float,
        lid: float,
        saccade_x: float,
        saccade_tilt: float,
    ) -> None:
        cur.width += (tgt.width - cur.width) * k
        cur.height += (tgt.height - cur.height) * k
        cur.corner_radius += (tgt.corner_radius - cur.corner_radius) * k
        cur.center_y += (tgt.center_y - cur.center_y) * k
        cur.tilt += ((tgt.tilt + saccade_tilt) - cur.tilt) * k
        cur.center_x_offset += ((tgt.center_x_offset + saccade_x) - cur.center_x_offset) * k
        cur.arc_curve += (tgt.arc_curve - cur.arc_curve) * k
        cur.is_arc = tgt.is_arc

        # Apply eyelid closure
        cur.lid_closure += (lid - cur.lid_closure) * 0.50

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        w = self.width()
        h = self.height()

        # 1. Sleek Helmet Visor Backdrop
        self._draw_visor_backdrop(painter, w, h)

        # Scale based on canonical 128x64 aspect ratio
        scale = min(w / 128.0, h / 64.0) * 0.78
        cx = w / 2.0
        cy = (h / 2.0) + self._breath_offset_y

        # Eye X positions: Left center at cx - 25*scale, Right center at cx + 25*scale
        left_cx = cx - (25.0 * scale) + (self._cur_left.center_x_offset * 128.0 * scale)
        right_cx = cx + (25.0 * scale) + (self._cur_right.center_x_offset * 128.0 * scale)

        # 2. Draw DASAI Mochi Eyes
        self._draw_mochi_eye(painter, self._cur_left, left_cx, cy, scale)
        self._draw_mochi_eye(painter, self._cur_right, right_cx, cy, scale)

        # 3. Draw Speaking Mouth (when SPEAKING)
        if self._state == "SPEAKING" or abs(self._speaking_phase) > 0.01:
            self._draw_speaking_mouth(painter, cx, cy, scale)

    def _draw_visor_backdrop(self, painter: QPainter, w: float, h: float) -> None:
        """Draw sleek dark helmet visor container with soft top specular reflection."""
        visor_rect = QRectF(0, 0, w, h)
        radius = 16.0

        painter.save()
        # Visor dark base
        painter.setBrush(QBrush(self._visor_bg))
        painter.setPen(QPen(self._visor_border, 1.2))
        painter.drawRoundedRect(visor_rect, radius, radius)

        # Subtle curved top glass highlight reflection
        glass_grad = QLinearGradient(0, 0, 0, h * 0.40)
        glass_grad.setColorAt(0.0, QColor(255, 255, 255, 14))
        glass_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(glass_grad))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h * 0.40), radius, radius)

        painter.restore()

    def _draw_mochi_eye(
        self,
        painter: QPainter,
        eye: MochiEyeState,
        cx: float,
        cy: float,
        scale: float,
    ) -> None:
        """Render a single DASAI Mochi eye (luminous capsule or smiling arc)."""
        # Calculate eye dimensions in pixels
        eye_w = eye.width * 128.0 * scale * (1.0 + self._cur_audio_pulse * 0.10)
        # Squash factor during blinking
        eye_h = max(2.5 * scale, eye.height * 64.0 * scale * (1.0 - eye.lid_closure * 0.90))

        # In speaking state, add expressive squash-and-stretch bounce
        if self._state == "SPEAKING":
            bounce = math.sin(self._speaking_phase) * 0.12
            eye_h *= (1.0 + bounce)

        eye_y = cy + ((eye.center_y - 0.50) * 64.0 * scale)

        painter.save()

        # Apply tilt
        if abs(eye.tilt) > 0.05:
            painter.translate(cx, eye_y)
            painter.rotate(eye.tilt)
            painter.translate(-cx, -eye_y)

        # CASE A: SIGNATURE MOCHI HAPPY SMILING CRESCENT ARC (^ ^)
        if eye.is_arc and eye.lid_closure < 0.70:
            arc_w = eye_w * 0.95
            arc_h = eye.height * 64.0 * scale * 0.85
            curve_depth = arc_h * eye.arc_curve * 4.0

            x_left = cx - (arc_w / 2.0)
            x_right = cx + (arc_w / 2.0)
            y_base = eye_y + (arc_h * 0.20)
            y_peak = eye_y - curve_depth

            arc_path = QPainterPath()
            arc_path.moveTo(x_left, y_base)
            arc_path.quadTo(cx, y_peak, x_right, y_base)

            # Outer luminous bloom stroke
            bloom_pen = QPen(
                QColor(self._glow_color.red(), self._glow_color.green(), self._glow_color.blue(), 55),
                8.0 * scale,
                Qt.SolidLine,
                Qt.RoundCap,
                Qt.RoundJoin,
            )
            painter.strokePath(arc_path, bloom_pen)

            # Inner intense bloom stroke
            inner_glow_pen = QPen(
                QColor(self._glow_color.red(), self._glow_color.green(), self._glow_color.blue(), 180),
                5.5 * scale,
                Qt.SolidLine,
                Qt.RoundCap,
                Qt.RoundJoin,
            )
            painter.strokePath(arc_path, inner_glow_pen)

            # Core crisp stroke
            core_pen = QPen(
                self._core_color,
                3.8 * scale,
                Qt.SolidLine,
                Qt.RoundCap,
                Qt.RoundJoin,
            )
            painter.strokePath(arc_path, core_pen)

        # CASE B: LUMINOUS CAPSULE / LOZENGE PILL
        else:
            corner_r = min(eye_w, eye_h) / 2.0
            rect = QRectF(cx - eye_w / 2.0, eye_y - eye_h / 2.0, eye_w, eye_h)

            # 1. Soft Luminous Outer Bloom
            bloom_rect = rect.adjusted(-3.5 * scale, -3.5 * scale, 3.5 * scale, 3.5 * scale)
            bloom_color = QColor(self._glow_color.red(), self._glow_color.green(), self._glow_color.blue(), 45)
            painter.setBrush(QBrush(bloom_color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bloom_rect, corner_r + 3.5 * scale, corner_r + 3.5 * scale)

            # 2. Main Glowing Capsule
            capsule_grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            capsule_grad.setColorAt(0.0, self._core_color)
            capsule_grad.setColorAt(0.35, QColor(220, 248, 255))
            capsule_grad.setColorAt(1.0, self._glow_color)

            painter.setBrush(QBrush(capsule_grad))
            glow_outline = QColor(self._glow_color.red(), self._glow_color.green(), self._glow_color.blue(), 160)
            painter.setPen(QPen(glow_outline, 1.2 * scale))
            painter.drawRoundedRect(rect, corner_r, corner_r)

            # 3. Specular Glass Sheen on Top-Half of Capsule (creates live, glassy OLED feel)
            if eye.lid_closure < 0.60 and eye_h > 8.0 * scale:
                gloss_h = eye_h * 0.40
                gloss_rect = QRectF(cx - (eye_w * 0.35), eye_y - (eye_h * 0.40), eye_w * 0.70, gloss_h)
                gloss_grad = QLinearGradient(gloss_rect.topLeft(), gloss_rect.bottomLeft())
                gloss_grad.setColorAt(0.0, QColor(255, 255, 255, 140))
                gloss_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.setBrush(QBrush(gloss_grad))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(gloss_rect, gloss_h / 2.0, gloss_h / 2.0)

        painter.restore()

    def _draw_speaking_mouth(self, painter: QPainter, cx: float, cy: float, scale: float) -> None:
        """Render cute, subtle animated smiling mouth curve during SPEAKING state."""
        mouth_w = 16.0 * scale
        osc = math.sin(self._speaking_phase * 2.0) * 0.5 + 0.5  # 0.0 to 1.0
        mouth_h = (3.5 + osc * 3.5) * scale
        mouth_y = cy + (14.0 * scale)

        rect = QRectF(cx - mouth_w / 2.0, mouth_y, mouth_w, mouth_h)

        painter.save()
        mouth_color = QColor(255, 255, 255, 230)
        painter.setBrush(QBrush(mouth_color))
        painter.setPen(QPen(QColor(self._glow_color.red(), self._glow_color.green(), self._glow_color.blue(), 100), 1.0))
        painter.drawRoundedRect(rect, mouth_h / 2.0, mouth_h / 2.0)
        painter.restore()
