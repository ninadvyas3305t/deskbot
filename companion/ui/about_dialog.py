"""About DeskBot dialog displaying hardware specs, AI pipeline, and repository link."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import webbrowser

APP_VERSION = "1.0.0"
GITHUB_URL = "https://github.com/ninadvyas3305t/deskbot"


def show_about_dialog(parent: tk.Tk | None = None) -> None:
    """Display the About DeskBot dialog window."""
    dialog = tk.Toplevel(parent) if parent else tk.Tk()
    dialog.title("About DeskBot")
    dialog.geometry("460x420")
    dialog.resizable(False, False)

    # Center dialog on screen
    dialog.update_idletasks()
    w = dialog.winfo_width()
    h = dialog.winfo_height()
    x = (dialog.winfo_screenwidth() // 2) - (w // 2)
    y = (dialog.winfo_screenheight() // 2) - (h // 2)
    dialog.geometry(f"+{x}+{y}")

    main_frame = ttk.Frame(dialog, padding="20 20 20 20")
    main_frame.pack(fill=tk.BOTH, expand=True)

    # Header
    title_label = ttk.Label(main_frame, text="DeskBot", font=("Helvetica", 20, "bold"))
    title_label.pack(anchor="center", pady=(0, 2))

    version_label = ttk.Label(main_frame, text=f"Version {APP_VERSION}", font=("Helvetica", 11), foreground="#666666")
    version_label.pack(anchor="center", pady=(0, 10))

    desc_label = ttk.Label(
        main_frame,
        text="A cross-platform plug-and-play desktop AI assistant\npowered by an ESP32-S3 and neural AI models.",
        font=("Helvetica", 11),
        justify="center",
    )
    desc_label.pack(anchor="center", pady=(0, 15))

    sep = ttk.Separator(main_frame, orient="horizontal")
    sep.pack(fill="x", pady=(0, 15))

    # Architecture & Hardware specs
    specs_text = """• Hardware: ESP32-S3 (240MHz, 8MB PSRAM, USB-JTAG)
• Audio Input: INMP441 I2S Digital Omnidirectional Mic
• Visual Interface: SSD1306 128x64 I2C OLED Animated Face
• Touch Sensor: TTP223 Capacitive Touch
• Wake Word: openWakeWord ("Hey Jarvis")
• Speech-to-Text: Faster-Whisper (Local Neural Engine)
• Cloud Intelligence: NVIDIA Nemotron & Llama 3.2 Vision"""

    specs_label = ttk.Label(main_frame, text=specs_text, font=("Menlo", 10), justify="left")
    specs_label.pack(anchor="w", pady=(0, 15))

    # GitHub Link
    link_frame = ttk.Frame(main_frame)
    link_frame.pack(fill="x", pady=(0, 15))

    def _open_github(event=None):
        webbrowser.open(GITHUB_URL)

    link_label = tk.Label(
        link_frame,
        text="GitHub: " + GITHUB_URL,
        fg="#1a73e8",
        cursor="hand2",
        font=("Helvetica", 10, "underline"),
    )
    link_label.pack(anchor="center")
    link_label.bind("<Button-1>", _open_github)

    # Close button
    btn_close = ttk.Button(main_frame, text="Close", command=dialog.destroy)
    btn_close.pack(anchor="center", pady=(5, 0))

    if not parent:
        dialog.mainloop()
