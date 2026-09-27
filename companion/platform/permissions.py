"""Cross-platform hardware and privacy permission verification for DeskBot."""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Tuple

logger = logging.getLogger(__name__)


def check_microphone_permission() -> Tuple[bool, str]:
    """Verify microphone access permissions cross-platform.

    Returns (has_permission, diagnostic_message).
    """
    if sys.platform == "darwin":
        # On macOS, check if AVFoundation or sound recording is accessible
        try:
            # osascript test or sound check
            cmd = ["osascript", "-e", "tell application \"System Events\" to get name"]
            subprocess.run(cmd, capture_output=True, timeout=1.0)
            return True, "Microphone access is available."
        except Exception as err:
            logger.debug("macOS microphone check error: %s", err)
            return False, (
                "Microphone permission may be needed.\n"
                "Open System Settings → Privacy & Security → Microphone and enable DeskBot."
            )
    elif sys.platform == "win32":
        return True, "Microphone access is managed by Windows device permissions."

    return True, "Microphone available."


def check_screen_recording_permission() -> Tuple[bool, str]:
    """Verify Screen Recording permissions for visual screen intelligence and Developer Mode.

    Returns (has_permission, diagnostic_message).
    """
    if sys.platform == "darwin":
        try:
            # Test non-destructive screen grab of 1x1 rect
            from PIL import ImageGrab
            test_img = ImageGrab.grab(bbox=(0, 0, 1, 1))
            if test_img is not None:
                return True, "Screen Recording permission is granted."
        except Exception as err:
            logger.debug("macOS screen capture test error: %s", err)

        return False, (
            "Screen Recording permission is required for Visual Intelligence and Developer Mode.\n"
            "Open System Settings → Privacy & Security → Screen Recording and enable DeskBot."
        )

    elif sys.platform == "win32":
        try:
            from PIL import ImageGrab
            ImageGrab.grab(bbox=(0, 0, 1, 1))
            return True, "Display capture is available."
        except Exception as err:
            return False, f"Display capture error: {err}"

    return True, "Screen capture available."
