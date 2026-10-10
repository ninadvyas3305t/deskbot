"""Devices view for ESP32 hardware auto-discovery, diagnostics, and guided Wi-Fi setup."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from device.discovery import scan_candidate_ports
from device.handshake import probe_port
from ui.bridge import DeskBotBridge, get_ui_bridge
from ui.theme import (
    COLOR_ACCENT_AMBER,
    COLOR_ACCENT_CYAN,
    COLOR_ACCENT_MINT,
    COLOR_BORDER,
    COLOR_SURFACE,
    COLOR_SURFACE_ELEVATED,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


class DevicesView(QWidget):
    """Device management, USB auto-detection, hardware diagnostics, and Wi-Fi setup."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.bridge: DeskBotBridge = get_ui_bridge()
        self._build_ui()
        self._connect_signals()
        self._scan_usb_devices()

    def _build_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)

        # Header
        lbl_title = QLabel("Hardware & Device Management")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(lbl_title)

        lbl_desc = QLabel("Manage your connected ESP32-S3 physical companion and configure wireless modes.")
        lbl_desc.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY};")
        layout.addWidget(lbl_desc)

        # --- Card 1: USB Connection & Auto-Discovery ---
        usb_card = QFrame()
        usb_card.setStyleSheet(
            f"background-color: {COLOR_SURFACE_ELEVATED}; border: 1px solid {COLOR_BORDER}; "
            "border-radius: 12px; padding: 16px;"
        )
        u_layout = QVBoxLayout(usb_card)
        u_layout.setSpacing(12)

        u_header = QHBoxLayout()
        lbl_u_title = QLabel("USB Serial Connection")
        lbl_u_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #FFFFFF;")
        u_header.addWidget(lbl_u_title)
        u_header.addStretch()

        self.pill_usb = QLabel("○ Scanning...")
        self.pill_usb.setStyleSheet(
            "background-color: rgba(255, 179, 0, 0.12); color: #FFB300; border: 1px solid rgba(255, 179, 0, 0.35); "
            "border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
        )
        u_header.addWidget(self.pill_usb)
        u_layout.addLayout(u_header)

        # Port selection & Rescan row
        row_port = QHBoxLayout()
        lbl_port = QLabel("Serial Port:")
        lbl_port.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY}; width: 80px;")
        self.combo_ports = QComboBox()
        self.combo_ports.setMinimumWidth(260)
        self.combo_ports.currentIndexChanged.connect(self._on_port_selected)

        self.btn_rescan = QPushButton("↻ Rescan Ports")
        self.btn_rescan.setStyleSheet(
            f"background-color: {COLOR_SURFACE}; border: 1px solid {COLOR_BORDER}; "
            "color: #FFFFFF; font-weight: 500; font-size: 12px; padding: 6px 14px; border-radius: 6px;"
        )
        self.btn_rescan.clicked.connect(self._scan_usb_devices)

        self.btn_probe = QPushButton("◈ Verify Handshake")
        self.btn_probe.setStyleSheet(
            f"background-color: {COLOR_SURFACE}; border: 1px solid {COLOR_BORDER}; "
            "color: #00E5FF; font-weight: 600; font-size: 12px; padding: 6px 14px; border-radius: 6px;"
        )
        self.btn_probe.clicked.connect(self._verify_handshake_clicked)

        row_port.addWidget(lbl_port)
        row_port.addWidget(self.combo_ports, stretch=1)
        row_port.addWidget(self.btn_rescan)
        row_port.addWidget(self.btn_probe)
        u_layout.addLayout(row_port)

        # Device details status label
        self.lbl_device_info = QLabel("Detecting connected hardware...")
        self.lbl_device_info.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_MUTED};")
        u_layout.addWidget(self.lbl_device_info)

        layout.addWidget(usb_card)

        # --- Card 2: Interactive Hardware Diagnostics ---
        diag_card = QFrame()
        diag_card.setStyleSheet(
            f"background-color: {COLOR_SURFACE_ELEVATED}; border: 1px solid {COLOR_BORDER}; "
            "border-radius: 12px; padding: 16px;"
        )
        d_layout = QVBoxLayout(diag_card)
        d_layout.setSpacing(14)

        lbl_d_title = QLabel("Hardware Diagnostics")
        lbl_d_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #FFFFFF;")
        d_layout.addWidget(lbl_d_title)

        # Microphone Live Level Meter
        mic_row = QVBoxLayout()
        mic_row.setSpacing(4)
        mic_header = QHBoxLayout()
        lbl_mic = QLabel("INMP441 Microphone Audio Level:")
        lbl_mic.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY};")
        self.lbl_mic_pct = QLabel("0%")
        self.lbl_mic_pct.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {COLOR_ACCENT_CYAN};")
        mic_header.addWidget(lbl_mic)
        mic_header.addStretch()
        mic_header.addWidget(self.lbl_mic_pct)
        mic_row.addLayout(mic_header)

        self.mic_bar = QProgressBar()
        self.mic_bar.setRange(0, 100)
        self.mic_bar.setValue(0)
        self.mic_bar.setTextVisible(False)
        self.mic_bar.setFixedHeight(8)
        self.mic_bar.setStyleSheet(
            f"QProgressBar {{ background-color: {COLOR_SURFACE}; border-radius: 4px; border: none; }}"
            f"QProgressBar::chunk {{ background-color: {COLOR_ACCENT_CYAN}; border-radius: 4px; }}"
        )
        mic_row.addWidget(self.mic_bar)
        d_layout.addLayout(mic_row)

        # Diagnostic Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_test_oled = QPushButton("▣ Test Physical OLED Display")
        self.btn_test_oled.setStyleSheet(
            f"background-color: {COLOR_SURFACE}; border: 1px solid {COLOR_BORDER}; "
            "color: #FFFFFF; font-weight: 500; font-size: 12px; padding: 8px 14px; border-radius: 6px;"
        )
        self.btn_test_oled.clicked.connect(self._test_oled_clicked)

        self.lbl_diag_status = QLabel("")
        self.lbl_diag_status.setStyleSheet("font-size: 12px; color: #00E676;")

        btn_row.addWidget(self.btn_test_oled)
        btn_row.addWidget(self.lbl_diag_status)
        btn_row.addStretch()
        d_layout.addLayout(btn_row)

        layout.addWidget(diag_card)

        # --- Card 3: Guided Wi-Fi Connection Management ---
        wifi_card = QFrame()
        wifi_card.setStyleSheet(
            f"background-color: {COLOR_SURFACE_ELEVATED}; border: 1px solid {COLOR_BORDER}; "
            "border-radius: 12px; padding: 16px;"
        )
        w_layout = QVBoxLayout(wifi_card)
        w_layout.setSpacing(14)

        w_header = QHBoxLayout()
        lbl_w_title = QLabel("Guided Wi-Fi Setup")
        lbl_w_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #FFFFFF;")
        w_header.addWidget(lbl_w_title)
        w_header.addStretch()

        self.pill_wifi = QLabel("○ Wi-Fi Standby")
        self.pill_wifi.setStyleSheet(
            "background-color: rgba(100, 116, 139, 0.15); color: #94A3B8; border: 1px solid rgba(100, 116, 139, 0.3); "
            "border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
        )
        w_header.addWidget(self.pill_wifi)
        w_layout.addLayout(w_header)

        lbl_w_desc = QLabel(
            "DeskBot can operate tethered via high-speed USB serial or untethered via local Wi-Fi. "
            "Select your connection mode below:"
        )
        lbl_w_desc.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_SECONDARY};")
        lbl_w_desc.setWordWrap(True)
        w_layout.addWidget(lbl_w_desc)

        # Mode Radio Selection
        mode_box = QHBoxLayout()
        self.radio_station = QRadioButton("Station Mode (ESP32 connects to your Home Wi-Fi)")
        self.radio_station.setChecked(True)
        self.radio_station.setStyleSheet("color: #FFFFFF; font-size: 13px;")

        self.radio_ap = QRadioButton("SoftAP Mode (ESP32 broadcasts its own Wi-Fi Hotspot)")
        self.radio_ap.setStyleSheet("color: #FFFFFF; font-size: 13px;")

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_station, 1)
        self.mode_group.addButton(self.radio_ap, 2)
        self.mode_group.buttonClicked.connect(self._on_wifi_mode_changed)

        mode_box.addWidget(self.radio_station)
        mode_box.addWidget(self.radio_ap)
        mode_box.addStretch()
        w_layout.addLayout(mode_box)

        # Input fields
        self.f_row1 = QHBoxLayout()
        self.lbl_ssid = QLabel("Network SSID:")
        self.lbl_ssid.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY}; min-width: 100px;")
        self.entry_ssid = QLineEdit()
        self.entry_ssid.setPlaceholderText("Enter Wi-Fi network name")
        self.f_row1.addWidget(self.lbl_ssid)
        self.f_row1.addWidget(self.entry_ssid)
        w_layout.addLayout(self.f_row1)

        self.f_row2 = QHBoxLayout()
        self.lbl_pwd = QLabel("Password:")
        self.lbl_pwd.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY}; min-width: 100px;")
        self.entry_pwd = QLineEdit()
        self.entry_pwd.setEchoMode(QLineEdit.Password)
        self.entry_pwd.setPlaceholderText("Enter Wi-Fi network password")
        self.f_row2.addWidget(self.lbl_pwd)
        self.f_row2.addWidget(self.entry_pwd)
        w_layout.addLayout(self.f_row2)

        # Provision Button
        w_btn_row = QHBoxLayout()
        self.btn_provision = QPushButton("◈ Connect & Provision Wi-Fi")
        self.btn_provision.setStyleSheet(
            f"background-color: {COLOR_ACCENT_CYAN}; color: #05080E; "
            "font-weight: 600; font-size: 13px; padding: 8px 18px; border-radius: 6px;"
        )
        self.btn_provision.clicked.connect(self._provision_wifi_clicked)

        self.lbl_wifi_status = QLabel("")
        self.lbl_wifi_status.setStyleSheet("font-size: 12px; color: #8B9BB4;")

        w_btn_row.addWidget(self.btn_provision)
        w_btn_row.addWidget(self.lbl_wifi_status)
        w_btn_row.addStretch()
        w_layout.addLayout(w_btn_row)

        layout.addWidget(wifi_card)
        layout.addStretch()

        scroll.setWidget(container)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _connect_signals(self) -> None:
        self.bridge.speech_level.connect(self._on_audio_level)
        self.bridge.device_status_changed.connect(self._on_device_status_changed)
        self.bridge.wifi_status_changed.connect(self._on_wifi_status_changed)

    def _scan_usb_devices(self) -> None:
        self.combo_ports.clear()
        candidates = scan_candidate_ports()

        best_port = None
        for cand in candidates:
            label = f"{cand.device} ({cand.description})"
            self.combo_ports.addItem(label, userData=cand.device)
            if cand.is_preferred and best_port is None:
                best_port = cand.device

        if candidates:
            self.pill_usb.setText(f"● Found ({len(candidates)})")
            self.pill_usb.setStyleSheet(
                "background-color: rgba(0, 230, 118, 0.12); color: #00E676; border: 1px solid rgba(0, 230, 118, 0.35); "
                "border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
            )
            self.lbl_device_info.setText(f"Candidate device detected. Preferred: {best_port or candidates[0].device}")
        else:
            self.pill_usb.setText("○ Disconnected")
            self.pill_usb.setStyleSheet(
                "background-color: rgba(255, 179, 0, 0.12); color: #FFB300; border: 1px solid rgba(255, 179, 0, 0.35); "
                "border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
            )
            self.lbl_device_info.setText("No ESP32 board detected. Plug in your DeskBot via USB cable.")

    def _on_port_selected(self) -> None:
        port = self.combo_ports.currentData()
        if port:
            self.lbl_device_info.setText(f"Selected port: {port}")

    def _verify_handshake_clicked(self) -> None:
        port = self.combo_ports.currentData()
        if not port:
            self.lbl_device_info.setText("No port selected to probe.")
            return

        self.btn_probe.setEnabled(False)
        self.lbl_device_info.setText(f"Probing handshake with {port}...")

        def _probe():
            ok = probe_port(port, baud=921600, timeout=1.8)
            QTimer.singleShot(0, lambda: self._on_handshake_done(port, ok))

        threading.Thread(target=_probe, daemon=True).start()

    def _on_handshake_done(self, port: str, ok: bool) -> None:
        self.btn_probe.setEnabled(True)
        if ok:
            self.pill_usb.setText("● Verified Connected")
            self.pill_usb.setStyleSheet(
                "background-color: rgba(0, 230, 118, 0.12); color: #00E676; border: 1px solid rgba(0, 230, 118, 0.35); "
                "border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
            )
            self.lbl_device_info.setText(f"✓ ESP32 handshake verified on {port}. Ready for 16kHz audio.")
            self.bridge.notify_device_status(True, port, "ESP32-S3 Verified")
        else:
            self.pill_usb.setText("⚠ Probe Failed")
            self.pill_usb.setStyleSheet(
                "background-color: rgba(255, 61, 113, 0.12); color: #FF3D71; border: 1px solid rgba(255, 61, 113, 0.35); "
                "border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
            )
            self.lbl_device_info.setText(f"Could not confirm streaming protocol on {port}.")

    def _test_oled_clicked(self) -> None:
        port = self.combo_ports.currentData()
        if not port:
            self.lbl_diag_status.setText("Connect USB first.")
            return

        self.lbl_diag_status.setText("Cycling OLED face expressions...")

        def _cycle():
            import serial
            try:
                ser = serial.Serial(port, 921600, timeout=0.5)
                time.sleep(0.05)
                for st in ["STATE_LISTENING\n", "STATE_THINKING\n", "STATE_SPEAKING\n", "STATE_IDLE\n"]:
                    ser.write(st.encode("ascii"))
                    ser.flush()
                    time.sleep(0.4)
                ser.close()
                QTimer.singleShot(0, lambda: self.lbl_diag_status.setText("✓ OLED face cycle completed."))
            except Exception as err:
                QTimer.singleShot(0, lambda: self.lbl_diag_status.setText(f"OLED test failed: {err}"))

        threading.Thread(target=_cycle, daemon=True).start()

    def _on_wifi_mode_changed(self) -> None:
        if self.radio_station.isChecked():
            self.lbl_ssid.setText("Network SSID:")
            self.entry_ssid.setPlaceholderText("Enter home Wi-Fi name")
            self.btn_provision.setText("◈ Connect to Wi-Fi")
        else:
            self.lbl_ssid.setText("Hotspot SSID:")
            self.entry_ssid.setText("DeskBot-AP")
            self.btn_provision.setText("◈ Broadcast DeskBot Hotspot")

    def _provision_wifi_clicked(self) -> None:
        ssid = self.entry_ssid.text().strip()
        pwd = self.entry_pwd.text().strip()
        if not ssid:
            self.lbl_wifi_status.setText("Please enter an SSID.")
            return

        mode = "Station" if self.radio_station.isChecked() else "SoftAP"
        self.btn_provision.setEnabled(False)
        self.lbl_wifi_status.setText(f"Configuring ESP32 in {mode} mode...")

        def _provision():
            # Send Wi-Fi provisioning command over active serial connection
            port = self.combo_ports.currentData()
            ok = False
            err_msg = ""
            if port:
                try:
                    import serial
                    ser = serial.Serial(port, 921600, timeout=1.0)
                    cmd = f"WIFI_CONFIG:{mode}:{ssid}:{pwd}\n"
                    ser.write(cmd.encode("ascii"))
                    ser.flush()
                    ser.close()
                    ok = True
                except Exception as err:
                    err_msg = str(err)
            else:
                err_msg = "USB connection required for initial provisioning"

            QTimer.singleShot(0, lambda: self._on_provision_done(ok, mode, ssid, err_msg))

        threading.Thread(target=_provision, daemon=True).start()

    def _on_provision_done(self, ok: bool, mode: str, target: str, error: str) -> None:
        self.btn_provision.setEnabled(True)
        if ok:
            self.pill_wifi.setText(f"● Wi-Fi {mode} Ready")
            self.pill_wifi.setStyleSheet(
                "background-color: rgba(0, 230, 118, 0.12); color: #00E676; border: 1px solid rgba(0, 230, 118, 0.35); "
                "border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
            )
            self.lbl_wifi_status.setText(f"✓ Provisioned {mode} for '{target}'.")
            self.bridge.notify_wifi_status(True, mode, target)
        else:
            self.lbl_wifi_status.setText(f"Provisioning failed: {error}")

    def _on_audio_level(self, level: float) -> None:
        val = int(level * 100)
        self.mic_bar.setValue(val)
        self.lbl_mic_pct.setText(f"{val}%")

    def _on_device_status_changed(self, connected: bool, port: str, description: str) -> None:
        if connected:
            self.pill_usb.setText("● Connected")
            self.lbl_device_info.setText(f"Connected: {port} ({description})")
        else:
            self.pill_usb.setText("○ Disconnected")
            self.lbl_device_info.setText("ESP32 disconnected.")

    def _on_wifi_status_changed(self, connected: bool, mode: str, target: str) -> None:
        if connected:
            self.pill_wifi.setText(f"● {mode}: {target}")
