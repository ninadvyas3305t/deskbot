"""Cross-platform hardware, screen, and privacy permission management for DeskBot."""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


def has_screen_capture_permission() -> bool:
    """Check if DeskBot has macOS Screen & System Audio Recording permission without prompting.

    Uses CoreGraphics CGPreflightScreenCaptureAccess on macOS.
    Does NOT trigger an OS dialog or prompt if permission is missing.
    """
    if sys.platform != "darwin":
        return True

    try:
        import ctypes
        cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        if hasattr(cg, "CGPreflightScreenCaptureAccess"):
            cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
            cg.CGPreflightScreenCaptureAccess.argtypes = []
            return bool(cg.CGPreflightScreenCaptureAccess())
        return True
    except Exception as err:
        logger.debug("Failed checking macOS screen capture preflight permission: %s", err)
        return True


def request_screen_capture_permission() -> bool:
    """Explicitly request Screen Recording access from the user via macOS system dialog.

    Calls CGRequestScreenCaptureAccess on macOS. Should only be called upon user action
    (e.g., user explicitly clicks or requests a screenshot) when permission is not yet granted.
    """
    if sys.platform != "darwin":
        return True

    try:
        import ctypes
        cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        if hasattr(cg, "CGRequestScreenCaptureAccess"):
            cg.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
            cg.CGRequestScreenCaptureAccess.argtypes = []
            return bool(cg.CGRequestScreenCaptureAccess())
        return True
    except Exception as err:
        logger.debug("Failed requesting macOS screen capture access: %s", err)
        return False


def has_microphone_permission() -> bool:
    """Check if DeskBot has microphone device access permission without blocking."""
    if sys.platform != "darwin":
        return True

    try:
        import ctypes
        from ctypes import c_char_p, c_long, c_uint32, c_void_p

        objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
        cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AVFoundation.framework/AVFoundation")

        objc.objc_getClass.restype = c_void_p
        objc.objc_getClass.argtypes = [c_char_p]
        objc.sel_registerName.restype = c_void_p
        objc.sel_registerName.argtypes = [c_char_p]

        cf.CFStringCreateWithCString.restype = c_void_p
        cf.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_uint32]
        cf.CFRelease.restype = None
        cf.CFRelease.argtypes = [c_void_p]

        k_cf_string_encoding_utf8 = 0x08000100
        # "soun" is the four-char code / identifier for AVMediaTypeAudio
        av_audio_str = cf.CFStringCreateWithCString(None, b"soun", k_cf_string_encoding_utf8)
        cls_av_capture = objc.objc_getClass(b"AVCaptureDevice")
        sel_auth = objc.sel_registerName(b"authorizationStatusForMediaType:")

        msg_send = ctypes.cast(objc.objc_msgSend, ctypes.CFUNCTYPE(c_long, c_void_p, c_void_p, c_void_p))
        status = msg_send(cls_av_capture, sel_auth, av_audio_str)
        cf.CFRelease(av_audio_str)

        # 0 = NotDetermined, 1 = Restricted, 2 = Denied, 3 = Authorized
        return status == 3
    except Exception as err:
        logger.debug("Failed checking macOS microphone authorization status: %s", err)
        return True


def open_screen_recording_settings() -> bool:
    """Open macOS System Settings directly to Privacy & Security → Screen & System Audio Recording."""
    if sys.platform == "darwin":
        try:
            subprocess.Popen(
                ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"],
                shell=False,
            )
            return True
        except Exception as err:
            logger.warning("Could not open macOS Screen Recording settings: %s", err)
            return False
    elif sys.platform == "win32":
        try:
            subprocess.Popen(["cmd", "/c", "start", "ms-settings:privacy-screenrecording"], shell=False)
            return True
        except Exception:
            return False
    return False


def open_microphone_settings() -> bool:
    """Open macOS System Settings directly to Privacy & Security → Microphone."""
    if sys.platform == "darwin":
        try:
            subprocess.Popen(
                ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"],
                shell=False,
            )
            return True
        except Exception as err:
            logger.warning("Could not open macOS Microphone settings: %s", err)
            return False
    elif sys.platform == "win32":
        try:
            subprocess.Popen(["cmd", "/c", "start", "ms-settings:privacy-microphone"], shell=False)
            return True
        except Exception:
            return False
    return False


def check_microphone_permission() -> Tuple[bool, str]:
    """Verify microphone access permissions cross-platform.

    Returns (has_permission, diagnostic_message).
    """
    granted = has_microphone_permission()
    if granted:
        return True, "Microphone access is available."

    return False, (
        "Microphone permission is required for voice commands.\n"
        "Open System Settings → Privacy & Security → Microphone and enable DeskBot."
    )


def check_screen_recording_permission() -> Tuple[bool, str]:
    """Verify Screen Recording permissions for visual screen intelligence and Developer Mode.

    Returns (has_permission, diagnostic_message).
    """
    granted = has_screen_capture_permission()
    if granted:
        return True, "Screen Recording permission is granted."

    return False, (
        "Screen Recording permission is required for Visual Intelligence and Screenshots.\n"
        "Open System Settings → Privacy & Security → Screen & System Audio Recording and enable DeskBot."
    )


def get_permissions_summary() -> Dict[str, Dict[str, Any]]:
    """Retrieve structured status of all hardware and OS privacy permissions."""
    return {
        "microphone": {
            "name": "Microphone",
            "granted": has_microphone_permission(),
            "description": "Voice command input & wake-word detection",
            "settings_pane": "Privacy_Microphone",
        },
        "screen_recording": {
            "name": "Screen Recording",
            "granted": has_screen_capture_permission(),
            "description": "Visual screen intelligence and on-demand screenshots",
            "settings_pane": "Privacy_ScreenCapture",
        },
        "system_audio": {
            "name": "System Audio Recording",
            "granted": True,
            "description": "Not required (DeskBot only captures screen displays, never system audio)",
            "settings_pane": None,
        },
    }
