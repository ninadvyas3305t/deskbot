# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for DeskBot (macOS Application Bundle .app)."""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

PROJECT_ROOT = Path(SPECPATH).parent.resolve()
COMPANION_DIR = PROJECT_ROOT / "companion"
RESOURCES_DIR = PROJECT_ROOT / "resources"

# 1. Collect model files, certificates, and runtime assets
datas = [
    (str(COMPANION_DIR), "companion"),
]
datas += collect_data_files("openwakeword")
datas += collect_data_files("certifi")
datas += collect_data_files("faster_whisper")

# Include icon files
if (RESOURCES_DIR / "deskbot.icns").is_file():
    datas.append((str(RESOURCES_DIR / "deskbot.icns"), "resources"))
if (RESOURCES_DIR / "deskbot.png").is_file():
    datas.append((str(RESOURCES_DIR / "deskbot.png"), "resources"))

# 2. Collect dynamic binaries (ctranslate2, onnxruntime, etc.)
binaries = []
binaries += collect_dynamic_libs("ctranslate2")
try:
    binaries += collect_dynamic_libs("onnxruntime")
except Exception:
    pass

# 3. Hidden imports
hiddenimports = [
    "keyring.backends",
    "keyring.backends.macOS",
    "pystray._darwin",
    "faster_whisper",
    "ctranslate2",
    "tokenizers",
    "openwakeword",
    "webrtcvad",
    "PIL._imaging",
    "PIL.ImageGrab",
    "PIL.ImageTk",
    "certifi",
    "requests",
    "urllib3",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "connectivity",
    "companion.connectivity",
    "assistant.local_llm",
    "companion.assistant.local_llm",
    "ui.edge_overlay",
    "companion.ui.edge_overlay",
    "vision.analyzer",
    "vision.screen_capture",
    "vision.service",
    "companion.vision.analyzer",
    "companion.vision.screen_capture",
    "companion.vision.service",
    "ui.views.activity_view",
    "ui.views.devices_view",
    "ui.views.home_view",
    "ui.views.settings_view",
    "companion.ui.views.activity_view",
    "companion.ui.views.devices_view",
    "companion.ui.views.home_view",
    "companion.ui.views.settings_view",
    "tools.calculator",
    "tools.developer_tools",
    "tools.file_tools",
    "tools.info_tools",
    "tools.web_search",
    "companion.tools.calculator",
    "companion.tools.developer_tools",
    "companion.tools.file_tools",
    "companion.tools.info_tools",
    "companion.tools.web_search",
    "tts.macos_say",
    "companion.tts.macos_say",
]
hiddenimports += collect_submodules("faster_whisper")
hiddenimports += collect_submodules("ctranslate2")
hiddenimports += collect_submodules("openwakeword")

a = Analysis(
    [str(COMPANION_DIR / "app.py")],
    pathex=[str(PROJECT_ROOT), str(COMPANION_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(PROJECT_ROOT / "build" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "notebook"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DeskBot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=str(PROJECT_ROOT / "build" / "deskbot.entitlements"),
    icon=str(RESOURCES_DIR / "deskbot.icns") if (RESOURCES_DIR / "deskbot.icns").is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DeskBot",
)

app = BUNDLE(
    coll,
    name="DeskBot.app",
    icon=str(RESOURCES_DIR / "deskbot.icns") if (RESOURCES_DIR / "deskbot.icns").is_file() else None,
    bundle_identifier="com.deskbot.assistant",
    info_plist={
        "CFBundleDisplayName": "DeskBot",
        "CFBundleName": "DeskBot",
        "CFBundleIdentifier": "com.deskbot.assistant",
        "CFBundleVersion": "2.0.0",
        "CFBundleShortVersionString": "2.0.0",
        "NSHighResolutionCapable": True,
        "LSUIElement": False,  # Allow windowed dialogs (Setup, Settings, About) to focus cleanly
        "NSMicrophoneUsageDescription": "DeskBot requires microphone access for wake-word detection and voice commands.",
        "NSScreenCaptureUsageDescription": "DeskBot requires screen recording permissions for visual screen understanding and code analysis.",
    },
)
