"""Comprehensive settings view organized into structured configuration cards."""

from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

try:
    import config
except ImportError:
    from companion import config

try:
    from platform_layer.autostart import is_autostart_enabled, is_autostart_supported, set_autostart
    from platform_layer.config_manager import get_config_manager
    from platform_layer.credentials import get_credential_store
    from platform_layer.permissions import (
        has_microphone_permission,
        has_screen_capture_permission,
        open_microphone_settings,
        open_screen_recording_settings,
    )
    from ui.bridge import DeskBotBridge, get_ui_bridge
    from ui.edge_overlay import get_screen_overlay
    from ui.theme import (
        COLOR_ACCENT_CYAN,
        COLOR_ACCENT_MINT,
        COLOR_BORDER,
        COLOR_SURFACE,
        COLOR_SURFACE_ELEVATED,
        COLOR_TEXT_MUTED,
        COLOR_TEXT_PRIMARY,
        COLOR_TEXT_SECONDARY,
    )
except (ImportError, ModuleNotFoundError):
    from companion.platform_layer.autostart import is_autostart_enabled, is_autostart_supported, set_autostart
    from companion.platform_layer.config_manager import get_config_manager
    from companion.platform_layer.credentials import get_credential_store
    from companion.platform_layer.permissions import (
        has_microphone_permission,
        has_screen_capture_permission,
        open_microphone_settings,
        open_screen_recording_settings,
    )
    from companion.ui.bridge import DeskBotBridge, get_ui_bridge
    from companion.ui.edge_overlay import get_screen_overlay
    from companion.ui.theme import (
        COLOR_ACCENT_CYAN,
        COLOR_ACCENT_MINT,
        COLOR_BORDER,
        COLOR_SURFACE,
        COLOR_SURFACE_ELEVATED,
        COLOR_TEXT_MUTED,
        COLOR_TEXT_PRIMARY,
        COLOR_TEXT_SECONDARY,
    )


class SettingsView(QWidget):
    """Structured configuration panel for AI credentials, speech, overlay, and hardware options."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.bridge: DeskBotBridge = get_ui_bridge()
        self.config_mgr = get_config_manager()
        self.cred_store = get_credential_store()

        self._build_ui()
        self._load_saved_values()

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
        lbl_title = QLabel("Application Settings")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(lbl_title)

        lbl_desc = QLabel("Configure your AI credentials, speech models, ambient lighting, and hardware preferences.")
        lbl_desc.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY};")
        layout.addWidget(lbl_desc)

        # --- Section 1: NVIDIA Cloud AI Credentials ---
        api_card = self._create_card("1. NVIDIA Cloud AI Credentials")
        api_layout = QVBoxLayout(api_card)
        api_layout.setSpacing(10)

        lbl_api_desc = QLabel(
            "DeskBot uses NVIDIA Nemotron & Llama 3.2 Vision for deep multi-modal reasoning. "
            "Get a free API key from build.nvidia.com."
        )
        lbl_api_desc.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_SECONDARY};")
        lbl_api_desc.setWordWrap(True)
        api_layout.addWidget(lbl_api_desc)

        api_row = QHBoxLayout()
        self.entry_api = QLineEdit()
        self.entry_api.setEchoMode(QLineEdit.Password)
        self.entry_api.setPlaceholderText("nvapi-••••••••••••••••••••••••••••••••")
        self.btn_verify = QPushButton("Verify Key")
        self.btn_verify.setStyleSheet(
            f"background-color: {COLOR_SURFACE}; border: 1px solid {COLOR_BORDER}; "
            "color: #00E5FF; font-weight: 600; font-size: 12px; padding: 8px 16px; border-radius: 6px;"
        )
        self.btn_verify.clicked.connect(self._verify_api_key)
        api_row.addWidget(self.entry_api, stretch=1)
        api_row.addWidget(self.btn_verify)
        api_layout.addLayout(api_row)

        self.lbl_api_status = QLabel("")
        self.lbl_api_status.setStyleSheet("font-size: 12px;")
        api_layout.addWidget(self.lbl_api_status)

        layout.addWidget(api_card)

        # --- Section 2: Speech & AI Engine ---
        engine_card = self._create_card("2. Speech Recognition & AI Engine")
        engine_layout = QVBoxLayout(engine_card)
        engine_layout.setSpacing(12)

        # Wake word row
        row_wake = QHBoxLayout()
        lbl_wake = QLabel("Wake Word Phrase:")
        lbl_wake.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY}; min-width: 140px;")
        self.combo_wake = QComboBox()
        self.combo_wake.addItems(["hey_jarvis", "alexa"])
        row_wake.addWidget(lbl_wake)
        row_wake.addWidget(self.combo_wake, stretch=1)
        engine_layout.addLayout(row_wake)

        # Wake Sensitivity slider
        row_sens = QHBoxLayout()
        lbl_sens = QLabel("Wake Threshold (lower = more sensitive):")
        lbl_sens.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY}; min-width: 200px;")
        self.slider_sens = QSlider(Qt.Horizontal)
        self.slider_sens.setRange(20, 75)
        self.lbl_sens_val = QLabel("0.38")
        self.lbl_sens_val.setStyleSheet(f"font-size: 12px; color: {COLOR_ACCENT_CYAN}; min-width: 35px;")
        self.slider_sens.valueChanged.connect(lambda v: self.lbl_sens_val.setText(f"{v/100:.2f}"))
        row_sens.addWidget(lbl_sens)
        row_sens.addWidget(self.slider_sens, stretch=1)
        row_sens.addWidget(self.lbl_sens_val)
        engine_layout.addLayout(row_sens)

        # Whisper model row
        row_stt = QHBoxLayout()
        lbl_stt = QLabel("Whisper STT Model:")
        lbl_stt.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY}; min-width: 140px;")
        self.combo_stt = QComboBox()
        self.combo_stt.addItems(["tiny", "base", "small"])
        row_stt.addWidget(lbl_stt)
        row_stt.addWidget(self.combo_stt, stretch=1)
        engine_layout.addLayout(row_stt)

        # Vision model row
        row_vis = QHBoxLayout()
        lbl_vis = QLabel("Vision AI Model:")
        lbl_vis.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY}; min-width: 140px;")
        self.entry_vision = QLineEdit()
        self.entry_vision.setText("meta/llama-3.2-11b-vision-instruct")
        row_vis.addWidget(lbl_vis)
        row_vis.addWidget(self.entry_vision, stretch=1)
        engine_layout.addLayout(row_vis)

        layout.addWidget(engine_card)

        # --- Section 3: Desktop Edge Illumination ---
        overlay_card = self._create_card("3. Desktop Edge Illumination")
        overlay_layout = QVBoxLayout(overlay_card)
        overlay_layout.setSpacing(12)

        self.chk_overlay = QCheckBox("Enable Edge Illumination (Google-inspired screen perimeter glow)")
        self.chk_overlay.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 500;")
        self.chk_overlay.toggled.connect(self._on_overlay_toggled)
        overlay_layout.addWidget(self.chk_overlay)

        # Glow Intensity row
        row_glow = QHBoxLayout()
        lbl_glow = QLabel("Glow Intensity:")
        lbl_glow.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY}; min-width: 140px;")
        self.slider_glow = QSlider(Qt.Horizontal)
        self.slider_glow.setRange(20, 100)
        self.lbl_glow_val = QLabel("85%")
        self.lbl_glow_val.setStyleSheet(f"font-size: 12px; color: {COLOR_ACCENT_CYAN}; min-width: 40px;")
        self.slider_glow.valueChanged.connect(self._on_glow_changed)
        row_glow.addWidget(lbl_glow)
        row_glow.addWidget(self.slider_glow, stretch=1)
        row_glow.addWidget(self.lbl_glow_val)
        overlay_layout.addLayout(row_glow)

        # Edge Thickness row
        row_thick = QHBoxLayout()
        lbl_thick = QLabel("Edge Thickness:")
        lbl_thick.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY}; min-width: 140px;")
        self.slider_thickness = QSlider(Qt.Horizontal)
        self.slider_thickness.setRange(12, 48)
        self.lbl_thickness_val = QLabel("28px")
        self.lbl_thickness_val.setStyleSheet(f"font-size: 12px; color: {COLOR_ACCENT_CYAN}; min-width: 40px;")
        self.slider_thickness.valueChanged.connect(self._on_thickness_changed)
        row_thick.addWidget(lbl_thick)
        row_thick.addWidget(self.slider_thickness, stretch=1)
        row_thick.addWidget(self.lbl_thickness_val)
        overlay_layout.addLayout(row_thick)

        # Animation Speed row
        row_speed = QHBoxLayout()
        lbl_speed = QLabel("Animation Speed:")
        lbl_speed.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY}; min-width: 140px;")
        self.slider_speed = QSlider(Qt.Horizontal)
        self.slider_speed.setRange(40, 200)
        self.lbl_speed_val = QLabel("1.0x")
        self.lbl_speed_val.setStyleSheet(f"font-size: 12px; color: {COLOR_ACCENT_CYAN}; min-width: 40px;")
        self.slider_speed.valueChanged.connect(self._on_speed_changed)
        row_speed.addWidget(lbl_speed)
        row_speed.addWidget(self.slider_speed, stretch=1)
        row_speed.addWidget(self.lbl_speed_val)
        overlay_layout.addLayout(row_speed)

        lbl_over_note = QLabel(
            "Produces a subtle, crystal-clear, multicolored luminous glass perimeter glow inspired by Google. "
            "Click-through, non-focus-stealing, and completely transparent at screen center."
        )
        lbl_over_note.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_MUTED};")
        lbl_over_note.setWordWrap(True)
        overlay_layout.addWidget(lbl_over_note)

        layout.addWidget(overlay_card)

        # --- Section 4: System & Privacy Permissions ---
        perm_card = self._create_card("4. Privacy & Permissions")
        perm_layout = QVBoxLayout(perm_card)
        perm_layout.setSpacing(10)

        # Microphone row
        row_mic = QHBoxLayout()
        self.lbl_perm_mic = QLabel("Microphone Access:")
        self.lbl_perm_mic.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY};")
        self.btn_open_mic = QPushButton("Open Settings")
        self.btn_open_mic.setStyleSheet(
            f"background-color: {COLOR_SURFACE}; border: 1px solid {COLOR_BORDER}; "
            "color: #FFFFFF; font-size: 12px; padding: 4px 12px; border-radius: 6px;"
        )
        self.btn_open_mic.clicked.connect(open_microphone_settings)
        row_mic.addWidget(self.lbl_perm_mic)
        row_mic.addStretch()
        row_mic.addWidget(self.btn_open_mic)
        perm_layout.addLayout(row_mic)

        # Screen recording row
        row_scr = QHBoxLayout()
        self.lbl_perm_scr = QLabel("Screen Recording Access:")
        self.lbl_perm_scr.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY};")
        self.btn_open_scr = QPushButton("Open Settings")
        self.btn_open_scr.setStyleSheet(
            f"background-color: {COLOR_SURFACE}; border: 1px solid {COLOR_BORDER}; "
            "color: #FFFFFF; font-size: 12px; padding: 4px 12px; border-radius: 6px;"
        )
        self.btn_open_scr.clicked.connect(open_screen_recording_settings)
        row_scr.addWidget(self.lbl_perm_scr)
        row_scr.addStretch()
        row_scr.addWidget(self.btn_open_scr)
        perm_layout.addLayout(row_scr)

        # Audio note
        lbl_audio_note = QLabel("• System Audio Recording: Not Required (DeskBot captures video display frames only)")
        lbl_audio_note.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_MUTED};")
        perm_layout.addWidget(lbl_audio_note)

        self._refresh_permissions()
        layout.addWidget(perm_card)

        # --- Section 5: System Options ---
        opts_card = self._create_card("5. System & Developer Options")
        opts_layout = QVBoxLayout(opts_card)
        opts_layout.setSpacing(10)

        self.chk_dev_mode = QCheckBox("Enable Developer Mode (AST inspection, file operations & code debugging)")
        self.chk_dev_mode.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        opts_layout.addWidget(self.chk_dev_mode)

        self.chk_autostart = QCheckBox("Launch DeskBot automatically when system boots")
        self.chk_autostart.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        if not is_autostart_supported():
            self.chk_autostart.setEnabled(False)
        opts_layout.addWidget(self.chk_autostart)

        self.chk_tts = QCheckBox("Enable Text-to-Speech (Spoken responses)")
        self.chk_tts.setStyleSheet("color: #FFFFFF; font-size: 13px;")
        opts_layout.addWidget(self.chk_tts)

        layout.addWidget(opts_card)

        # --- Section 6: About DeskBot & Build Information ---
        about_card = self._create_card("6. About DeskBot & System Build")
        about_layout = QVBoxLayout(about_card)
        about_layout.setSpacing(10)

        app_ver = getattr(config, "APP_VERSION", "2.0.0")
        build_id = getattr(config, "BUILD_ID", "20261012-v2.0-hybrid-edge")
        build_date = getattr(config, "BUILD_DATE", "2026-10-12")

        info_rows = [
            ("Application Version:", f"v{app_ver} (Production Edition)"),
            ("Build Identifier:", build_id),
            ("Build Release Date:", build_date),
            ("System Architecture:", "Hybrid Edge AI (ESP32-S3 On-Device ML + Local Speech + Cloud/Local Intelligence)"),
            ("Installed Bundle Target:", "/Applications/DeskBot.app"),
            ("Hardware Target:", "ESP32-S3 DevKitC-1-N8 (16kHz I2S Mic, SSD1306 OLED, TTP223 Touch)"),
        ]

        for label_text, val_text in info_rows:
            r = QHBoxLayout()
            lbl_k = QLabel(label_text)
            lbl_k.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY}; min-width: 170px;")
            lbl_v = QLabel(val_text)
            is_highlight = "Build" in label_text or "Version" in label_text
            lbl_v.setStyleSheet(
                f"font-size: 13px; color: {COLOR_ACCENT_CYAN if is_highlight else COLOR_TEXT_PRIMARY}; "
                f"font-weight: {'600' if is_highlight else '400'};"
            )
            lbl_v.setWordWrap(True)
            r.addWidget(lbl_k)
            r.addWidget(lbl_v, stretch=1)
            about_layout.addLayout(r)

        layout.addWidget(about_card)

        # Save Button Row
        save_row = QHBoxLayout()
        self.btn_save = QPushButton("✓ Save Settings")
        self.btn_save.setStyleSheet(
            f"background-color: {COLOR_ACCENT_CYAN}; color: #05080E; "
            "font-weight: 600; font-size: 13px; padding: 10px 24px; border-radius: 8px;"
        )
        self.btn_save.clicked.connect(self._save_settings)

        self.lbl_save_status = QLabel("")
        self.lbl_save_status.setStyleSheet("font-size: 12px; color: #00E676;")

        save_row.addWidget(self.btn_save)
        save_row.addWidget(self.lbl_save_status)
        save_row.addStretch()
        layout.addLayout(save_row)
        layout.addStretch()

        scroll.setWidget(container)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _create_card(self, title: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"background-color: {COLOR_SURFACE_ELEVATED}; border: 1px solid {COLOR_BORDER}; "
            "border-radius: 12px; padding: 16px;"
        )
        lbl = QLabel(title)
        lbl.setStyleSheet("font-size: 15px; font-weight: 600; color: #FFFFFF; margin-bottom: 4px;")
        return card

    def _load_saved_values(self) -> None:
        key = self.cred_store.get_api_key() or ""
        self.entry_api.setText(key)
        if key:
            self.lbl_api_status.setText("✓ API key loaded securely from OS Keychain/Vault.")
            self.lbl_api_status.setStyleSheet("color: #00E676;")

        self.combo_wake.setCurrentText(str(self.config_mgr.get("wake_word", "hey_jarvis")))
        thresh = float(self.config_mgr.get("wake_threshold", 0.38))
        if thresh > 0.45:
            thresh = 0.38
            self.config_mgr.set("wake_threshold", 0.38)
        self.slider_sens.setValue(int(thresh * 100))
        self.lbl_sens_val.setText(f"{thresh:.2f}")

        self.combo_stt.setCurrentText(str(self.config_mgr.get("stt_model", "base")))
        self.entry_vision.setText(str(self.config_mgr.get("vision_model", "meta/llama-3.2-11b-vision-instruct")))

        self.chk_overlay.setChecked(bool(self.config_mgr.get("screen_overlay_enabled", True)))
        glow = float(self.config_mgr.get("overlay_glow_intensity", 0.85))
        self.slider_glow.setValue(int(glow * 100))
        self.lbl_glow_val.setText(f"{int(glow * 100)}%")

        thickness = int(self.config_mgr.get("overlay_edge_thickness", 28))
        self.slider_thickness.setValue(thickness)
        self.lbl_thickness_val.setText(f"{thickness}px")

        speed = float(self.config_mgr.get("overlay_animation_speed", 1.0))
        self.slider_speed.setValue(int(speed * 100))
        self.lbl_speed_val.setText(f"{speed:.1f}x")

        self.chk_dev_mode.setChecked(bool(self.config_mgr.get("developer_mode", False)))
        self.chk_autostart.setChecked(is_autostart_enabled())
        self.chk_tts.setChecked(bool(self.config_mgr.get("tts_enabled", True)))

    def _refresh_permissions(self) -> None:
        has_mic = has_microphone_permission()
        if has_mic:
            self.lbl_perm_mic.setText("Microphone Access: ✓ Granted")
            self.lbl_perm_mic.setStyleSheet("color: #00E676; font-size: 13px;")
            self.btn_open_mic.hide()
        else:
            self.lbl_perm_mic.setText("Microphone Access: ⚠ Missing")
            self.lbl_perm_mic.setStyleSheet("color: #FFB300; font-size: 13px;")
            self.btn_open_mic.show()

        has_scr = has_screen_capture_permission()
        if has_scr:
            self.lbl_perm_scr.setText("Screen Recording Access: ✓ Granted")
            self.lbl_perm_scr.setStyleSheet("color: #00E676; font-size: 13px;")
            self.btn_open_scr.hide()
        else:
            self.lbl_perm_scr.setText("Screen Recording Access: ⚠ Missing")
            self.lbl_perm_scr.setStyleSheet("color: #FFB300; font-size: 13px;")
            self.btn_open_scr.show()

    def _verify_api_key(self) -> None:
        key = self.entry_api.text().strip()
        if not key:
            self.lbl_api_status.setText("Please enter an API key.")
            self.lbl_api_status.setStyleSheet("color: #FF3D71;")
            return

        self.btn_verify.setEnabled(False)
        self.lbl_api_status.setText("Verifying with NVIDIA NIM...")
        self.lbl_api_status.setStyleSheet("color: #00E5FF;")

        def _verify():
            valid, msg = self.cred_store.validate_api_key(key)
            QTimer.singleShot(0, lambda: self._on_verified(valid, msg, key))

        threading.Thread(target=_verify, daemon=True).start()

    def _on_verified(self, valid: bool, msg: str, key: str) -> None:
        self.btn_verify.setEnabled(True)
        if valid:
            self.lbl_api_status.setText("✓ API key verified and stored securely!")
            self.lbl_api_status.setStyleSheet("color: #00E676;")
            self.cred_store.set_api_key(key)
        else:
            self.lbl_api_status.setText(f"Verification failed: {msg}")
            self.lbl_api_status.setStyleSheet("color: #FF3D71;")

    def _on_overlay_toggled(self, checked: bool) -> None:
        overlay = get_screen_overlay()
        if overlay:
            overlay.set_enabled(checked)

    def _on_glow_changed(self, val: int) -> None:
        self.lbl_glow_val.setText(f"{val}%")
        overlay = get_screen_overlay()
        if overlay:
            overlay.set_glow_intensity(val / 100.0)

    def _on_thickness_changed(self, val: int) -> None:
        self.lbl_thickness_val.setText(f"{val}px")
        overlay = get_screen_overlay()
        if overlay:
            overlay.set_edge_thickness(val)

    def _on_speed_changed(self, val: int) -> None:
        self.lbl_speed_val.setText(f"{val / 100.0:.1f}x")
        overlay = get_screen_overlay()
        if overlay:
            overlay.set_animation_speed(val / 100.0)

    def _save_settings(self) -> None:
        key = self.entry_api.text().strip()
        if key:
            self.cred_store.set_api_key(key)

        updates = {
            "wake_word": self.combo_wake.currentText(),
            "wake_threshold": round(self.slider_sens.value() / 100.0, 2),
            "stt_model": self.combo_stt.currentText(),
            "vision_model": self.entry_vision.text().strip(),
            "screen_overlay_enabled": self.chk_overlay.isChecked(),
            "overlay_glow_intensity": round(self.slider_glow.value() / 100.0, 2),
            "overlay_edge_thickness": self.slider_thickness.value(),
            "overlay_animation_speed": round(self.slider_speed.value() / 100.0, 2),
            "developer_mode": self.chk_dev_mode.isChecked(),
            "tts_enabled": self.chk_tts.isChecked(),
        }
        self.config_mgr.update(updates)

        if is_autostart_supported():
            set_autostart(self.chk_autostart.isChecked())

        try:
            from tools.developer_tools import set_developer_mode
            set_developer_mode(self.chk_dev_mode.isChecked())
        except Exception:
            pass

        self.lbl_save_status.setText("✓ Settings saved successfully.")
        QTimer.singleShot(3000, lambda: self.lbl_save_status.setText(""))
