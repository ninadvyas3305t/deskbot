"""Primary desktop application window for DeskBot 2.0 with sidebar navigation and system tray."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from ui.bridge import DeskBotBridge, get_ui_bridge
from ui.edge_overlay import get_screen_overlay, initialize_screen_overlay
from ui.icon import create_tray_icon_image
from ui.theme import (
    APPLICATION_STYLESHEET,
    COLOR_ACCENT_CYAN,
    COLOR_ACCENT_MINT,
    COLOR_BORDER,
    COLOR_SURFACE,
    COLOR_SURFACE_HOVER,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
)
from ui.views.activity_view import ActivityView
from ui.views.devices_view import DevicesView
from ui.views.home_view import HomeView
from ui.views.settings_view import SettingsView

logger = logging.getLogger(__name__)


class DeskBotMainWindow(QMainWindow):
    """Main desktop application window for DeskBot."""

    def __init__(self, on_shutdown: Optional[Callable[[], None]] = None):
        super().__init__()
        self.on_shutdown = on_shutdown
        self.bridge: DeskBotBridge = get_ui_bridge()

        self.setWindowTitle("DeskBot — Hardware AI Companion")
        self.resize(980, 660)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(APPLICATION_STYLESHEET)

        # Initialize screen edge illumination overlay
        self.overlay = initialize_screen_overlay()

        self._build_ui()
        self._setup_tray()
        self._connect_signals()

    def _build_ui(self) -> None:
        central_widget = QWidget(self)
        central_widget.setObjectName("MainContent")
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Left Sidebar Navigation
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        s_layout = QVBoxLayout(sidebar)
        s_layout.setContentsMargins(12, 16, 12, 16)
        s_layout.setSpacing(8)

        # Brand / Logo Header
        brand_box = QHBoxLayout()
        lbl_logo = QLabel("◈")
        lbl_logo.setStyleSheet("font-size: 18px; color: #00E5FF; font-weight: 800;")
        lbl_title = QLabel("DeskBot")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.5px;")
        brand_box.addWidget(lbl_logo)
        brand_box.addWidget(lbl_title)
        brand_box.addStretch()
        s_layout.addLayout(brand_box)

        lbl_version = QLabel("Hardware Edition • v2.0")
        lbl_version.setStyleSheet(f"font-size: 10px; color: {COLOR_TEXT_MUTED}; margin-bottom: 12px;")
        s_layout.addWidget(lbl_version)

        # Navigation Buttons (Clean geometric typography)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.btn_nav_home = self._create_nav_button("◈  Home", 0)
        self.btn_nav_devices = self._create_nav_button("⎇  Devices", 1)
        self.btn_nav_activity = self._create_nav_button("◷  Activity", 2)
        self.btn_nav_settings = self._create_nav_button("⟐  Settings", 3)

        s_layout.addWidget(self.btn_nav_home)
        s_layout.addWidget(self.btn_nav_devices)
        s_layout.addWidget(self.btn_nav_activity)
        s_layout.addWidget(self.btn_nav_settings)
        s_layout.addStretch()

        # Micro device status at bottom of sidebar
        device_status_box = QFrame()
        device_status_box.setStyleSheet(
            "background-color: rgba(22, 29, 45, 0.7); border: 1px solid #1A2336; "
            "border-radius: 8px; padding: 8px;"
        )
        ds_layout = QVBoxLayout(device_status_box)
        ds_layout.setContentsMargins(8, 8, 8, 8)
        ds_layout.setSpacing(4)

        lbl_ds_title = QLabel("HARDWARE STATUS")
        lbl_ds_title.setStyleSheet(f"font-size: 9px; font-weight: 700; color: {COLOR_TEXT_MUTED}; letter-spacing: 0.5px;")
        self.lbl_ds_text = QLabel("ESP32-S3 Standby")
        self.lbl_ds_text.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {COLOR_ACCENT_CYAN};")

        ds_layout.addWidget(lbl_ds_title)
        ds_layout.addWidget(self.lbl_ds_text)
        s_layout.addWidget(device_status_box)

        main_layout.addWidget(sidebar)

        # 2. Right Content Area (Header + QStackedWidget)
        content_area = QWidget()
        c_layout = QVBoxLayout(content_area)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(0)

        # Header Bar
        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(48)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 20, 0)
        h_layout.setSpacing(10)

        self.lbl_page_title = QLabel("Home")
        self.lbl_page_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #FFFFFF;")
        h_layout.addWidget(self.lbl_page_title)

        h_layout.addStretch()

        # Cloud AI indicator (restrained, compact, translucent)
        self.pill_cloud = QLabel("● Cloud AI Online")
        self.pill_cloud.setStyleSheet(
            "background-color: rgba(22, 29, 45, 0.75); color: #C4D1EB; "
            "border: 1px solid rgba(255, 255, 255, 0.08); "
            "border-radius: 11px; padding: 3px 12px; font-size: 11px; font-weight: 500;"
        )
        self.pill_cloud.setToolTip("NVIDIA NIM / Nemotron Cloud Intelligence Active")
        h_layout.addWidget(self.pill_cloud)

        # Active hardware indicator (quiet, restrained, professional - never alarming red)
        self.pill_hw = QLabel("○ ESP32 Standby")
        self.pill_hw.setStyleSheet(
            "background-color: rgba(22, 29, 45, 0.75); color: #8B9BB4; "
            "border: 1px solid rgba(255, 255, 255, 0.08); "
            "border-radius: 11px; padding: 3px 12px; font-size: 11px; font-weight: 500;"
        )
        self.pill_hw.setToolTip("Waiting for ESP32-S3 connection via USB serial or Wi-Fi")
        h_layout.addWidget(self.pill_hw)

        c_layout.addWidget(header)

        # Stacked Views
        self.stack = QStackedWidget()
        self.home_view = HomeView()
        self.devices_view = DevicesView()
        self.activity_view = ActivityView()
        self.settings_view = SettingsView()

        self.stack.addWidget(self.home_view)
        self.stack.addWidget(self.devices_view)
        self.stack.addWidget(self.activity_view)
        self.stack.addWidget(self.settings_view)

        c_layout.addWidget(self.stack)
        main_layout.addWidget(content_area, stretch=1)

        # Default to Home
        self.btn_nav_home.setChecked(True)

    def _create_nav_button(self, label: str, index: int) -> QPushButton:
        btn = QPushButton(label)
        btn.setProperty("class", "NavButton")
        btn.setCheckable(True)
        btn.clicked.connect(lambda: self._switch_tab(index, label.split("  ")[-1]))
        self.nav_group.addButton(btn, index)
        return btn

    def _switch_tab(self, index: int, title: str) -> None:
        self.stack.setCurrentIndex(index)
        self.lbl_page_title.setText(title)

    def _setup_tray(self) -> None:
        """Create OS system tray icon and menu."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        # Generate tray icon from PIL icon generator
        try:
            from io import BytesIO
            pil_img = create_tray_icon_image("ready", size=32)
            buf = BytesIO()
            pil_img.save(buf, format="PNG")
            q_pix = QPixmap()
            q_pix.loadFromData(buf.getvalue())
            tray_icon = QIcon(q_pix)
        except Exception:
            tray_icon = self.windowIcon()

        self.tray = QSystemTrayIcon(tray_icon, self)
        self.tray.setToolTip("DeskBot — Hardware AI Companion")

        # Tray Menu
        from PySide6.QtWidgets import QMenu
        menu = QMenu()

        act_show = QAction("Open DeskBot Window", self)
        act_show.triggered.connect(self.show_and_activate)
        menu.addAction(act_show)

        act_ptt = QAction("Trigger Push-To-Talk", self)
        act_ptt.triggered.connect(self.bridge.notify_touch)
        menu.addAction(act_ptt)

        menu.addSeparator()

        act_quit = QAction("Quit Application", self)
        act_quit.triggered.connect(self._quit_application)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def show_and_activate(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_and_activate()

    def _connect_signals(self) -> None:
        self.bridge.device_status_changed.connect(self._on_device_status_changed)
        self.bridge.state_changed.connect(self._on_state_changed)

    def _on_device_status_changed(self, connected: bool, port: str, description: str) -> None:
        if connected:
            self.lbl_ds_text.setText(f"Connected: {port}")
            self.lbl_ds_text.setStyleSheet("font-size: 11px; font-weight: 600; color: #00E676;")
            self.pill_hw.setText(f"● ESP32-S3 ({port})")
            self.pill_hw.setStyleSheet(
                "background-color: rgba(0, 230, 118, 0.10); color: #00E676; "
                "border: 1px solid rgba(0, 230, 118, 0.28); "
                "border-radius: 11px; padding: 3px 12px; font-size: 11px; font-weight: 500;"
            )
            self.pill_hw.setToolTip(f"Connected on {port} ({description}) at 921,600 baud")
        else:
            self.lbl_ds_text.setText("Standby (Waiting for USB)")
            self.lbl_ds_text.setStyleSheet("font-size: 11px; font-weight: 600; color: #8B9BB4;")
            self.pill_hw.setText("○ ESP32 Standby")
            self.pill_hw.setStyleSheet(
                "background-color: rgba(22, 29, 45, 0.75); color: #8B9BB4; "
                "border: 1px solid rgba(255, 255, 255, 0.08); "
                "border-radius: 11px; padding: 3px 12px; font-size: 11px; font-weight: 500;"
            )
            self.pill_hw.setToolTip("Waiting for ESP32-S3 connection via USB serial or Wi-Fi")

    def _on_state_changed(self, old_state: str, new_state: str, context: str) -> None:
        # Sync state with ambient edge overlay
        if self.overlay:
            self.overlay.set_assistant_state(new_state)

    def closeEvent(self, event) -> None:
        """Minimize to tray instead of quitting if tray is available."""
        if hasattr(self, "tray") and self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            self._quit_application()
            event.accept()

    def _quit_application(self) -> None:
        if hasattr(self, "tray"):
            self.tray.hide()
        if self.overlay:
            self.overlay.hide()
        if self.on_shutdown:
            try:
                self.on_shutdown()
            except Exception:
                pass
        self.close()
