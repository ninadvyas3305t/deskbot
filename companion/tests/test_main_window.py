"""Tests for DeskBotMainWindow, navigation, views, and activity logging."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from companion.ui.bridge import get_ui_bridge
from companion.ui.main_window import DeskBotMainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_main_window_structure(qapp):
    win = DeskBotMainWindow()
    assert win.windowTitle() == "DeskBot — Hardware AI Companion"
    assert win.stack.count() == 4
    assert win.width() >= 900
    assert win.height() >= 600


def test_main_window_navigation_switching(qapp):
    win = DeskBotMainWindow()

    # Home
    win.btn_nav_home.click()
    assert win.stack.currentIndex() == 0
    assert win.lbl_page_title.text() == "Home"

    # Devices
    win.btn_nav_devices.click()
    assert win.stack.currentIndex() == 1
    assert win.lbl_page_title.text() == "Devices"

    # Activity
    win.btn_nav_activity.click()
    assert win.stack.currentIndex() == 2
    assert win.lbl_page_title.text() == "Activity"

    # Settings
    win.btn_nav_settings.click()
    assert win.stack.currentIndex() == 3
    assert win.lbl_page_title.text() == "Settings"


def test_activity_logging_and_filtering(qapp):
    win = DeskBotMainWindow()
    bridge = get_ui_bridge()

    bridge.log_activity("WAKE", "Test Wake Detection", "Confidence 0.92")
    bridge.log_activity("STT", "Speech recognized", "Open Spotify")
    bridge.log_activity("TOOL", "Opened Spotify", "Success")

    assert len(win.activity_view._events) >= 3

    # Test filtering
    win.activity_view.entry_filter.setText("Spotify")
    # Feed should contain the filtered items
    assert win.activity_view.feed_layout.count() >= 2

    # Test clear
    win.activity_view._clear_history()
    assert len(win.activity_view._events) == 0


def test_device_status_update(qapp):
    win = DeskBotMainWindow()
    bridge = get_ui_bridge()

    bridge.notify_device_status(True, "/dev/cu.usbmodemTest", "ESP32-S3")
    assert "ESP32-S3" in win.pill_hw.text() or "/dev/cu.usbmodemTest" in win.pill_hw.text()
    assert "Connected" in win.lbl_ds_text.text()

    bridge.notify_device_status(False)
    assert "Standby" in win.pill_hw.text()
