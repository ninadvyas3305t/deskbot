"""DeskBot cross-platform platform layer exports."""

from .autostart import is_autostart_enabled, is_autostart_supported, set_autostart
from .config_manager import ConfigManager, get_config_manager
from .credentials import CredentialStore, get_credential_store
from .logger import open_log_file, setup_logging
from .paths import (
    get_app_data_dir,
    get_cache_dir,
    get_config_path,
    get_log_dir,
    get_log_file_path,
    get_model_cache_dir,
)
from .permissions import (
    check_microphone_permission,
    check_screen_recording_permission,
)

__all__ = [
    "get_app_data_dir",
    "get_config_path",
    "get_log_dir",
    "get_log_file_path",
    "get_model_cache_dir",
    "get_cache_dir",
    "ConfigManager",
    "get_config_manager",
    "CredentialStore",
    "get_credential_store",
    "is_autostart_supported",
    "is_autostart_enabled",
    "set_autostart",
    "check_microphone_permission",
    "check_screen_recording_permission",
    "setup_logging",
    "open_log_file",
]

