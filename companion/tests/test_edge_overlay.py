"""Tests for ScreenEdgeOverlay ambient illumination widget."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from companion.ui.edge_overlay import (
    ScreenEdgeOverlay,
    get_screen_overlay,
    initialize_screen_overlay,
    sample_spectrum_color,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_edge_overlay_initialization(qapp):
    overlay = ScreenEdgeOverlay()
    assert overlay.is_enabled is True
    assert bool(overlay.windowFlags() & Qt.FramelessWindowHint) is True
    assert bool(overlay.windowFlags() & Qt.WindowTransparentForInput) is True
    assert bool(overlay.windowFlags() & Qt.WindowStaysOnTopHint) is True
    assert overlay.glow_intensity == pytest.approx(0.70)
    assert overlay.edge_thickness == 24
    assert overlay.animation_speed == pytest.approx(1.0)


def test_spectrum_color_sampling():
    # Normal Google spectrum sampling
    for u in [0.0, 0.2, 0.5, 0.8, 1.0]:
        r, g, b = sample_spectrum_color(u, phase=0.1, is_error=False)
        assert 0 <= r <= 255
        assert 0 <= g <= 255
        assert 0 <= b <= 255

    # Error spectrum sampling (warm red / amber / coral)
    r_err, g_err, b_err = sample_spectrum_color(0.5, phase=0.0, is_error=True)
    assert r_err > 200
    assert 0 <= g_err <= 255
    assert 0 <= b_err <= 255


def test_edge_overlay_customization_setters(qapp):
    overlay = ScreenEdgeOverlay()

    # Glow intensity with clamping [0.20, 1.00]
    overlay.set_glow_intensity(0.85)
    assert overlay.glow_intensity == pytest.approx(0.85)
    overlay.set_glow_intensity(0.05)
    assert overlay.glow_intensity == pytest.approx(0.20)
    overlay.set_glow_intensity(1.50)
    assert overlay.glow_intensity == pytest.approx(1.00)

    # Edge thickness with clamping [12, 48]
    overlay.set_edge_thickness(32)
    assert overlay.edge_thickness == 32
    overlay.set_edge_thickness(5)
    assert overlay.edge_thickness == 12
    overlay.set_edge_thickness(60)
    assert overlay.edge_thickness == 48

    # Animation speed with clamping [0.4, 2.0]
    overlay.set_animation_speed(1.5)
    assert overlay.animation_speed == pytest.approx(1.5)
    overlay.set_animation_speed(0.1)
    assert overlay.animation_speed == pytest.approx(0.4)
    overlay.set_animation_speed(3.0)
    assert overlay.animation_speed == pytest.approx(2.0)


def test_edge_overlay_load_config(qapp):
    overlay = ScreenEdgeOverlay()

    class MockConfigManager:
        def get(self, key, default=None):
            vals = {
                "screen_overlay_enabled": True,
                "overlay_glow_intensity": 0.85,
                "overlay_edge_thickness": 30,
                "overlay_animation_speed": 1.4,
            }
            return vals.get(key, default)

    overlay.load_config(MockConfigManager())
    assert overlay.is_enabled is True
    assert overlay.glow_intensity == pytest.approx(0.85)
    assert overlay.edge_thickness == 30
    assert overlay.animation_speed == pytest.approx(1.4)


def test_edge_overlay_state_changes(qapp):
    overlay = ScreenEdgeOverlay()

    states = [
        ("LISTENING", True),
        ("WAKE", True),
        ("FOLLOW_UP", True),
        ("THINKING", True),
        ("SCREEN_ANALYSIS", True),
        ("TRANSCRIBING", True),
        ("EXECUTING", True),
        ("SPEAKING", True),
        ("ERROR", True),
        ("IDLE", False),
    ]

    for state_name, should_be_active in states:
        overlay.set_assistant_state(state_name)
        if should_be_active:
            assert overlay._target_opacity > 0.0, f"State {state_name} should have target opacity > 0"
            assert overlay._timer.isActive() is True, f"State {state_name} should start animation timer"
        else:
            assert overlay._target_opacity == 0.0


def test_edge_overlay_disable_toggle(qapp):
    overlay = ScreenEdgeOverlay()
    overlay.set_enabled(False)
    assert overlay.is_enabled is False

    overlay.set_assistant_state("LISTENING")
    assert overlay._target_opacity == 0.0
    assert overlay.isVisible() is False

    overlay.set_enabled(True)
    overlay.set_assistant_state("LISTENING")
    assert overlay._target_opacity > 0.0


def test_edge_overlay_screenshot_suppression(qapp):
    overlay = ScreenEdgeOverlay()
    overlay.set_assistant_state("LISTENING")

    overlay.suppress_for_screenshot(duration_ms=50)
    assert overlay._temporarily_suppressed is True


def test_overlay_singleton(qapp):
    o1 = initialize_screen_overlay()
    o2 = get_screen_overlay()
    assert o1 is o2


def test_edge_overlay_paint_and_power_saving(qapp):
    overlay = ScreenEdgeOverlay()
    overlay.setGeometry(0, 0, 400, 300)
    overlay.set_assistant_state("LISTENING")

    # Simulate ticks to bring opacity up
    for _ in range(30):
        overlay._on_tick()

    assert overlay._opacity > 0.0
    assert overlay.isVisible() is True

    # Render widget into an offscreen QImage to verify paintEvent logic
    img = QImage(400, 300, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    overlay.render(img)

    # Screen center must remain completely transparent
    center_pixel = img.pixelColor(200, 150)
    assert center_pixel.alpha() == 0, f"Center pixel must be 100% transparent, got alpha={center_pixel.alpha()}"

    # Edge pixel should have visible illumination
    edge_pixel = img.pixelColor(200, 2)
    assert edge_pixel.alpha() > 0, f"Top edge pixel should be illuminated, got alpha={edge_pixel.alpha()}"

    # Now transition to IDLE and verify power-saving suspension
    overlay.set_assistant_state("IDLE")
    for _ in range(50):
        overlay._on_tick()

    assert overlay._opacity == 0.0
    assert overlay.isVisible() is False
    assert overlay._timer.isActive() is False, "Timer must stop in IDLE to save CPU/GPU power"
