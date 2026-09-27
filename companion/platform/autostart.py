"""Cross-platform 'Start with System' / Login Items integration for DeskBot."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

LAUNCH_AGENT_ID = "com.deskbot.assistant"


def is_autostart_supported() -> bool:
    """Return True if the current operating system supports user-level autostart."""
    return sys.platform in ("win32", "darwin")


def is_autostart_enabled() -> bool:
    """Check whether DeskBot is currently configured to launch on system startup."""
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ,
            ) as key:
                val, _ = winreg.QueryValueEx(key, "DeskBot")
                return bool(val)
        except Exception:
            return False

    elif sys.platform == "darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_ID}.plist"
        return plist_path.is_file()

    return False


def set_autostart(enable: bool, executable_path: Optional[str] = None) -> bool:
    """Enable or disable launching DeskBot when the user logs in."""
    target_exe = executable_path or sys.executable

    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                if enable:
                    winreg.SetValueEx(key, "DeskBot", 0, winreg.REG_SZ, f'"{target_exe}"')
                else:
                    try:
                        winreg.DeleteValue(key, "DeskBot")
                    except FileNotFoundError:
                        pass
            return True
        except Exception as err:
            logger.error("Failed to update Windows autostart: %s", err)
            return False

    elif sys.platform == "darwin":
        plist_dir = Path.home() / "Library" / "LaunchAgents"
        plist_path = plist_dir / f"{LAUNCH_AGENT_ID}.plist"

        if enable:
            try:
                plist_dir.mkdir(parents=True, exist_ok=True)
                plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCH_AGENT_ID}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{target_exe}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
"""
                plist_path.write_text(plist_content, encoding="utf-8")
                return True
            except Exception as err:
                logger.error("Failed to create macOS LaunchAgent: %s", err)
                return False
        else:
            try:
                if plist_path.exists():
                    plist_path.unlink()
                return True
            except Exception as err:
                logger.error("Failed to remove macOS LaunchAgent: %s", err)
                return False

    return False
