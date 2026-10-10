"""Tests for ScreenEdgeOverlay ambient illumination widget."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from companion.ui.edge_overlay import ScreenEdgeOverlay, get_screen_overlay, initialize_screen_overlay


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


def test_edge_overlay_state_changes(qapp):
    overlay = ScreenEdgeOverlay()

    overlay.set_assistant_state("LISTENING")
    assert overlay._target_opacity > 0.0

    overlay.set_assistant_state("THINKING")
    assert overlay._target_opacity > 0.0

    overlay.set_assistant_state("IDLE")
    assert overlay._target_opacity == 0.0


def test_edge_overlay_disable_toggle(qapp):
    overlay = ScreenEdgeOverlay()
    overlay.set_enabled(False)
    assert overlay.is_enabled is False

    overlay.set_assistant_state("LISTENING")
    assert overlay._target_opacity == 0.0

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
