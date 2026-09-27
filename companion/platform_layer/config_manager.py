"""Persistent configuration management storing user settings in platform AppData."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, Optional

from .paths import get_config_path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: Dict[str, Any] = {
    "wake_word": "hey_jarvis",
    "wake_threshold": 0.48,
    "mic_gain": 1.2,
    "stt_model": "base",
    "tts_enabled": True,
    "tts_engine": "auto",
    "tts_voice": None,
    "tts_rate": 1,
    "tts_volume": 100,
    "developer_mode": False,
    "autostart": False,
    "vision_model": "meta/llama-3.2-11b-vision-instruct",
    "vision_max_dimension": 1024,
    "vision_jpeg_quality": 85,
    "serial_port": "auto",
    "baud_rate": 921600,
    "debug": False,
    "first_run_completed": False,
}


class ConfigManager:
    """Thread-safe persistent configuration manager."""

    def __init__(self, config_path: Optional[str] = None):
        self._path = config_path or get_config_path()
        self._lock = threading.Lock()
        self._config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self.load()

    def load(self) -> Dict[str, Any]:
        """Load configuration from disk, falling back to defaults for missing keys."""
        with self._lock:
            try:
                import os
                if os.path.exists(self._path):
                    with open(self._path, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                    if isinstance(saved, dict):
                        # Merge saved onto defaults to ensure newly added keys exist
                        merged = dict(DEFAULT_CONFIG)
                        merged.update(saved)
                        self._config = merged
            except Exception as err:
                logger.warning("Could not read configuration from %s: %s", self._path, err)
            return dict(self._config)

    def save(self) -> bool:
        """Persist current configuration to disk."""
        with self._lock:
            try:
                with open(self._path, "w", encoding="utf-8") as f:
                    json.dump(self._config, f, indent=2)
                return True
            except Exception as err:
                logger.error("Failed to save configuration to %s: %s", self._path, err)
                return False

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if default is not None:
                return self._config.get(key, default)
            return self._config.get(key, DEFAULT_CONFIG.get(key))

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        with self._lock:
            self._config[key] = value
        if auto_save:
            self.save()

    def update(self, updates: Dict[str, Any], auto_save: bool = True) -> None:
        with self._lock:
            self._config.update(updates)
        if auto_save:
            self.save()

    def as_dict(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._config)


_GLOBAL_CONFIG_MANAGER: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Singleton getter for the global configuration manager."""
    global _GLOBAL_CONFIG_MANAGER
    if _GLOBAL_CONFIG_MANAGER is None:
        _GLOBAL_CONFIG_MANAGER = ConfigManager()
    return _GLOBAL_CONFIG_MANAGER
