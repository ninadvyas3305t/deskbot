"""DeskBot cross-platform GUI and System Tray package."""

from .about_dialog import show_about_dialog
from .icon import create_tray_icon_image
from .settings_dialog import SettingsDialog, show_settings_dialog
from .setup_wizard import SetupWizard, maybe_run_first_time_setup
from .tray import DeskBotTray

__all__ = [
    "DeskBotTray",
    "SetupWizard",
    "maybe_run_first_time_setup",
    "SettingsDialog",
    "show_settings_dialog",
    "show_about_dialog",
    "create_tray_icon_image",
]
