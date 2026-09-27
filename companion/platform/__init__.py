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

# Transparent fallback to Python's standard library platform module
# in case this package is imported as top-level 'platform' via sys.path.
import sysconfig
import importlib.util

_stdlib_platform = None

def __getattr__(name: str):
    global _stdlib_platform
    if _stdlib_platform is None:
        try:
            stdlib_dir = sysconfig.get_path("stdlib")
            spec = importlib.util.spec_from_file_location("_stdlib_platform", f"{stdlib_dir}/platform.py")
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                _stdlib_platform = mod
        except Exception:
            pass
    if _stdlib_platform is not None and hasattr(_stdlib_platform, name):
        return getattr(_stdlib_platform, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

