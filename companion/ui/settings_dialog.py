"""DeskBot Settings dialog for configuring API keys, wake word, models, startup, and permissions."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

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


class SettingsDialog:
    """Settings modal window for configuring DeskBot user preferences and checking privacy permissions."""

    def __init__(self, parent: Optional[tk.Tk] = None, on_save: Optional[Callable[[], None]] = None):
        self.parent = parent
        self.on_save = on_save
        self.config_mgr = get_config_manager()
        self.cred_store = get_credential_store()

        self.root = tk.Toplevel(parent) if parent else tk.Tk()
        self.root.title("DeskBot Settings")
        self.root.geometry("540x670")
        self.root.resizable(False, False)

        # Center on screen
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"+{x}+{y}")

        self._build_ui()
        self.root.bind("<FocusIn>", lambda _e: self._refresh_permissions())

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding="15 15 15 15")
        main.pack(fill=tk.BOTH, expand=True)

        # Header
        ttk.Label(main, text="Settings", font=("Helvetica", 16, "bold")).pack(anchor="w", pady=(0, 10))

        # --- Section 1: NVIDIA API Key ---
        api_group = ttk.LabelFrame(main, text=" NVIDIA NIM API Credentials ", padding="10 10 10 10")
        api_group.pack(fill="x", pady=(0, 10))

        ttk.Label(api_group, text="API Key:").grid(row=0, column=0, sticky="w", pady=2)
        self.api_var = tk.StringVar(value=self.cred_store.get_api_key() or "")
        self.api_entry = ttk.Entry(api_group, textvariable=self.api_var, show="•", width=34)
        self.api_entry.grid(row=0, column=1, sticky="ew", padx=6, pady=2)

        self.btn_verify = ttk.Button(api_group, text="Verify", command=self._verify_api_key)
        self.btn_verify.grid(row=0, column=2, padx=4, pady=2)

        self.api_status_label = ttk.Label(api_group, text="", font=("Helvetica", 9))
        self.api_status_label.grid(row=1, column=1, columnspan=2, sticky="w", pady=(2, 0))

        # --- Section 2: Speech & AI Engine ---
        engine_group = ttk.LabelFrame(main, text=" Speech & AI Engine ", padding="10 10 10 10")
        engine_group.pack(fill="x", pady=(0, 10))

        # Wake Word
        ttk.Label(engine_group, text="Wake Word:").grid(row=0, column=0, sticky="w", pady=3)
        self.wake_word_var = tk.StringVar(value=self.config_mgr.get("wake_word", "hey_jarvis"))
        wake_combo = ttk.Combobox(engine_group, textvariable=self.wake_word_var, values=["hey_jarvis", "alexa"], state="readonly", width=20)
        wake_combo.grid(row=0, column=1, sticky="w", padx=8, pady=3)

        # Wake Threshold
        ttk.Label(engine_group, text="Wake Sensitivity:").grid(row=1, column=0, sticky="w", pady=3)
        self.thresh_var = tk.DoubleVar(value=float(self.config_mgr.get("wake_threshold", 0.55)))
        thresh_scale = ttk.Scale(engine_group, from_=0.3, to=0.85, variable=self.thresh_var, orient="horizontal", length=160)
        thresh_scale.grid(row=1, column=1, sticky="w", padx=8, pady=3)

        # STT Model
        ttk.Label(engine_group, text="Whisper Model:").grid(row=2, column=0, sticky="w", pady=3)
        self.stt_var = tk.StringVar(value=self.config_mgr.get("stt_model", "base"))
        stt_combo = ttk.Combobox(engine_group, textvariable=self.stt_var, values=["tiny", "base", "small"], state="readonly", width=20)
        stt_combo.grid(row=2, column=1, sticky="w", padx=8, pady=3)

        # Vision Model
        ttk.Label(engine_group, text="Vision Model:").grid(row=3, column=0, sticky="w", pady=3)
        self.vision_var = tk.StringVar(value=self.config_mgr.get("vision_model", "meta/llama-3.2-11b-vision-instruct"))
        vision_entry = ttk.Entry(engine_group, textvariable=self.vision_var, width=30)
        vision_entry.grid(row=3, column=1, sticky="w", padx=8, pady=3)

        # --- Section 3: Permissions & Privacy (macOS & Windows) ---
        perm_group = ttk.LabelFrame(main, text=" Privacy & Permissions ", padding="10 10 10 10")
        perm_group.pack(fill="x", pady=(0, 10))

        # Microphone Row
        self.mic_status_label = ttk.Label(perm_group, text="", font=("Helvetica", 9))
        self.mic_status_label.grid(row=0, column=0, sticky="w", pady=2)
        self.btn_mic_settings = ttk.Button(perm_group, text="Open Settings", command=open_microphone_settings)
        self.btn_mic_settings.grid(row=0, column=1, sticky="e", padx=(12, 0), pady=2)

        # Screen Recording Row
        self.screen_status_label = ttk.Label(perm_group, text="", font=("Helvetica", 9))
        self.screen_status_label.grid(row=1, column=0, sticky="w", pady=2)
        self.btn_screen_settings = ttk.Button(perm_group, text="Open Settings", command=open_screen_recording_settings)
        self.btn_screen_settings.grid(row=1, column=1, sticky="e", padx=(12, 0), pady=2)

        # System Audio Note
        audio_note = ttk.Label(
            perm_group,
            text="• System Audio: Not Required (DeskBot captures screen display only)",
            font=("Helvetica", 8),
            foreground="#666666",
        )
        audio_note.grid(row=2, column=0, columnspan=2, sticky="w", pady=(3, 0))

        perm_group.columnconfigure(0, weight=1)
        self._refresh_permissions()

        # --- Section 4: System & Hardware Options ---
        opts_group = ttk.LabelFrame(main, text=" System Options ", padding="10 10 10 10")
        opts_group.pack(fill="x", pady=(0, 12))

        # Developer Mode
        self.dev_mode_var = tk.BooleanVar(value=bool(self.config_mgr.get("developer_mode", False)))
        ttk.Checkbutton(opts_group, text="Enable Developer Mode (AST inspection & code editing)", variable=self.dev_mode_var).pack(anchor="w", pady=2)

        # Start with System
        self.autostart_var = tk.BooleanVar(value=is_autostart_enabled())
        if is_autostart_supported():
            ttk.Checkbutton(opts_group, text="Start DeskBot automatically when system boots", variable=self.autostart_var).pack(anchor="w", pady=2)

        # TTS Enabled
        self.tts_var = tk.BooleanVar(value=bool(self.config_mgr.get("tts_enabled", True)))
        ttk.Checkbutton(opts_group, text="Enable Text-to-Speech (Spoken responses)", variable=self.tts_var).pack(anchor="w", pady=2)

        # --- Action Buttons ---
        btn_box = ttk.Frame(main)
        btn_box.pack(fill="x", side="bottom", pady=(6, 0))

        ttk.Button(btn_box, text="Save Settings", command=self._save_and_close).pack(side="right", padx=(6, 0))
        ttk.Button(btn_box, text="Cancel", command=self.root.destroy).pack(side="right")

    def _refresh_permissions(self) -> None:
        """Query hardware and OS privacy status non-blockingly and update indicators."""
        try:
            has_mic = has_microphone_permission()
            if has_mic:
                self.mic_status_label.config(text="✓ Microphone Access: Granted", foreground="#188038")
                self.btn_mic_settings.grid_remove()
            else:
                self.mic_status_label.config(text="⚠ Microphone Access: Missing", foreground="#d93025")
                self.btn_mic_settings.grid()

            has_screen = has_screen_capture_permission()
            if has_screen:
                self.screen_status_label.config(text="✓ Screen Recording: Granted", foreground="#188038")
                self.btn_screen_settings.grid_remove()
            else:
                self.screen_status_label.config(text="⚠ Screen Recording: Missing", foreground="#d93025")
                self.btn_screen_settings.grid()
        except Exception:
            pass

    def _verify_api_key(self) -> None:
        key = self.api_var.get().strip()
        if not key:
            self.api_status_label.config(text="Please enter an API key to verify.", foreground="#d93025")
            return

        self.api_status_label.config(text="Verifying with NVIDIA NIM...", foreground="#1a73e8")
        self.btn_verify.config(state="disabled")

        def _worker():
            valid, msg = self.cred_store.validate_api_key(key)
            self.root.after(0, lambda: self._on_verified(valid, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_verified(self, valid: bool, message: str) -> None:
        self.btn_verify.config(state="normal")
        if valid:
            self.api_status_label.config(text="✓ API key verified successfully!", foreground="#188038")
        else:
            self.api_status_label.config(text=f"✗ {message}", foreground="#d93025")

    def _save_and_close(self) -> None:
        key = self.api_var.get().strip()
        if key:
            self.cred_store.set_api_key(key)

        self.config_mgr.update({
            "wake_word": self.wake_word_var.get(),
            "wake_threshold": round(self.thresh_var.get(), 2),
            "stt_model": self.stt_var.get(),
            "vision_model": self.vision_var.get(),
            "developer_mode": self.dev_mode_var.get(),
            "tts_enabled": self.tts_var.get(),
        })

        if is_autostart_supported():
            set_autostart(self.autostart_var.get())

        if self.on_save:
            try:
                self.on_save()
            except Exception:
                pass

        messagebox.showinfo("DeskBot", "Settings saved successfully.", parent=self.root)
        self.root.destroy()


def show_settings_dialog(parent: Optional[tk.Tk] = None, on_save: Optional[Callable[[], None]] = None) -> None:
    """Launch the settings dialog window."""
    dlg = SettingsDialog(parent=parent, on_save=on_save)
    if not parent:
        dlg.root.mainloop()
