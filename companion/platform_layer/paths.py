"""Cross-platform directory and file path management for DeskBot."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "DeskBot"


def get_app_data_dir() -> Path:
    """Return the platform-standard application data directory for DeskBot.

    - Windows: %LOCALAPPDATA%\\DeskBot (e.g. C:\\Users\\<user>\\AppData\\Local\\DeskBot)
    - macOS: ~/Library/Application Support/DeskBot
    - Linux: ~/.config/deskbot
    """
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA")
        if base:
            path = Path(base) / APP_NAME
        else:
            path = Path.home() / "AppData" / "Local" / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = os.getenv("XDG_CONFIG_HOME")
        if base:
            path = Path(base) / APP_NAME.lower()
        else:
            path = Path.home() / ".config" / APP_NAME.lower()

    path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path() -> Path:
    """Return path to persistent user configuration JSON file."""
    return get_app_data_dir() / "config.json"


def get_log_dir() -> Path:
    """Return directory for rotating application log files."""
    log_dir = get_app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_file_path() -> Path:
    """Return path to main rotating log file."""
    return get_log_dir() / "deskbot.log"


def get_model_cache_dir() -> Path:
    """Return directory for persistent cached AI models (Faster-Whisper, etc.)."""
    model_dir = get_app_data_dir() / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    return model_dir


def get_cache_dir() -> Path:
    """Return directory for general application caches."""
    cache_dir = get_app_data_dir() / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir
