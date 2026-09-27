"""First-run setup wizard guiding new users through API key setup and hardware detection."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

try:
    from device.discovery import scan_candidate_ports
    from platform.config_manager import get_config_manager
    from platform.credentials import get_credential_store
    from platform.permissions import check_microphone_permission
except (ImportError, ModuleNotFoundError):
    from companion.device.discovery import scan_candidate_ports
    from companion.platform.config_manager import get_config_manager
    from companion.platform.credentials import get_credential_store
    from companion.platform.permissions import check_microphone_permission


class SetupWizard:
    """One-time onboarding wizard that configures credentials and hardware on first launch."""

    def __init__(self, on_complete: Optional[callable] = None):
        self.on_complete = on_complete
        self.cred_store = get_credential_store()
        self.config_mgr = get_config_manager()

        self.root = tk.Tk()
        self.root.title("DeskBot — Initial Setup")
        self.root.geometry("560x580")
        self.root.resizable(False, False)

        # Center on screen
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"+{x}+{y}")

        self.verified_api_key = False
        self._build_ui()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding="24 24 24 24")
        main.pack(fill=tk.BOTH, expand=True)

        # Header
        ttk.Label(main, text="Welcome to DeskBot!", font=("Helvetica", 20, "bold")).pack(anchor="w")
        ttk.Label(
            main,
            text="Let's get your AI hardware companion ready in less than a minute.",
            font=("Helvetica", 11),
            foreground="#555555",
        ).pack(anchor="w", pady=(4, 16))

        sep = ttk.Separator(main, orient="horizontal")
        sep.pack(fill="x", pady=(0, 16))

        # --- Card 1: NVIDIA API Key ---
        card1 = ttk.LabelFrame(main, text=" 1. NVIDIA Cloud AI Key ", padding="12 12 12 12")
        card1.pack(fill="x", pady=(0, 14))

        ttk.Label(
            card1,
            text="DeskBot uses NVIDIA Nemotron & Llama 3.2 Vision for intelligence.\nGet a free API key from build.nvidia.com.",
            font=("Helvetica", 10),
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        row1 = ttk.Frame(card1)
        row1.pack(fill="x")

        self.key_var = tk.StringVar(value=self.cred_store.get_api_key() or "")
        self.entry_key = ttk.Entry(row1, textvariable=self.key_var, show="•", width=34)
        self.entry_key.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_verify = ttk.Button(row1, text="Verify Key", command=self._verify_key)
        self.btn_verify.pack(side="right")

        self.status_api = ttk.Label(card1, text="", font=("Helvetica", 9))
        self.status_api.pack(anchor="w", pady=(6, 0))

        # If already configured from dev environment, auto-validate display
        if self.key_var.get() and len(self.key_var.get()) > 10:
            self.verified_api_key = True
            self.status_api.config(text="✓ API key loaded from environment/vault", foreground="#188038")

        # --- Card 2: Hardware Detection ---
        card2 = ttk.LabelFrame(main, text=" 2. DeskBot Hardware Detection ", padding="12 12 12 12")
        card2.pack(fill="x", pady=(0, 14))

        row2 = ttk.Frame(card2)
        row2.pack(fill="x")

        self.label_hw = ttk.Label(
            row2,
            text="Checking for connected ESP32-S3 board...",
            font=("Helvetica", 10),
        )
        self.label_hw.pack(side="left", fill="x", expand=True)

        self.btn_rescan = ttk.Button(row2, text="Scan USB", command=self._scan_hardware)
        self.btn_rescan.pack(side="right")

        # --- Card 3: Audio & Permissions ---
        card3 = ttk.LabelFrame(main, text=" 3. Microphone & Permissions ", padding="12 12 12 12")
        card3.pack(fill="x", pady=(0, 18))

        has_mic, mic_msg = check_microphone_permission()
        mic_text = "✓ Microphone access ready" if has_mic else f"⚠ {mic_msg}"
        mic_color = "#188038" if has_mic else "#e37400"
        self.label_mic = ttk.Label(card3, text=mic_text, font=("Helvetica", 10), foreground=mic_color)
        self.label_mic.pack(anchor="w")

        # Footer Buttons
        footer = ttk.Frame(main)
        footer.pack(fill="x", side="bottom")

        self.btn_finish = ttk.Button(
            footer,
            text="Get Started →",
            command=self._finish_setup,
        )
        self.btn_finish.pack(side="right")

        # Initial hardware scan
        self.root.after(200, self._scan_hardware)

    def _verify_key(self) -> None:
        key = self.key_var.get().strip()
        if not key:
            self.status_api.config(text="Please enter your NVIDIA API key.", foreground="#d93025")
            return

        self.status_api.config(text="Verifying with NVIDIA...", foreground="#1a73e8")
        self.btn_verify.config(state="disabled")

        def _run():
            valid, msg = self.cred_store.validate_api_key(key)
            self.root.after(0, lambda: self._on_key_result(valid, msg, key))

        threading.Thread(target=_run, daemon=True).start()

    def _on_key_result(self, valid: bool, message: str, key: str) -> None:
        self.btn_verify.config(state="normal")
        if valid:
            self.verified_api_key = True
            self.status_api.config(text="✓ API key verified successfully!", foreground="#188038")
            self.cred_store.set_api_key(key)
        else:
            self.verified_api_key = False
            self.status_api.config(text=f"✗ {message}", foreground="#d93025")

    def _scan_hardware(self) -> None:
        candidates = scan_candidate_ports()
        if candidates:
            best = candidates[0]
            self.label_hw.config(
                text=f"✓ DeskBot hardware detected on {best.device} ({best.description})",
                foreground="#188038",
            )
        else:
            self.label_hw.config(
                text="Hardware not connected yet. (You can plug it in anytime!)",
                foreground="#555555",
            )

    def _finish_setup(self) -> None:
        key = self.key_var.get().strip()
        if not key:
            messagebox.showwarning(
                "API Key Required",
                "Please enter an NVIDIA API key to use DeskBot's reasoning capabilities.",
                parent=self.root,
            )
            return

        # Store key in secure OS vault
        self.cred_store.set_api_key(key)
        self.config_mgr.set("first_run_completed", True)

        self.root.destroy()
        if self.on_complete:
            try:
                self.on_complete()
            except Exception:
                pass


def maybe_run_first_time_setup() -> bool:
    """Check if setup is needed, and if so, display wizard. Returns True to proceed."""
    cred_store = get_credential_store()
    config_mgr = get_config_manager()

    # If API key already exists in OS Keychain or environment, setup is complete
    if cred_store.has_api_key() and config_mgr.get("first_run_completed", False):
        return True

    # Run onboarding wizard
    wizard = SetupWizard()
    wizard.root.mainloop()
    return cred_store.has_api_key()
