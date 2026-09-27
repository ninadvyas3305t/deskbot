"""Cross-platform System Tray (Windows) and Menu Bar (macOS) integration."""

from __future__ import annotations

import logging
import sys
import threading
from typing import Callable, Optional

import pystray
from PIL import Image

try:
    from assistant.lifecycle import AppLifecycleState, get_lifecycle_manager
    from platform.autostart import is_autostart_enabled, is_autostart_supported, set_autostart
    from platform.config_manager import get_config_manager
    from platform.logger import open_log_file
except (ImportError, ModuleNotFoundError):
    from companion.assistant.lifecycle import AppLifecycleState, get_lifecycle_manager
    from companion.platform.autostart import is_autostart_enabled, is_autostart_supported, set_autostart
    from companion.platform.config_manager import get_config_manager
    from companion.platform.logger import open_log_file

from .about_dialog import show_about_dialog
from .icon import create_tray_icon_image
from .settings_dialog import show_settings_dialog

logger = logging.getLogger(__name__)


class DeskBotTray:
    """Manages the background System Tray / Menu Bar icon and context menu."""

    def __init__(
        self,
        on_quit_callback: Optional[Callable[[], None]] = None,
        on_reconnect_callback: Optional[Callable[[], None]] = None,
    ):
        self.on_quit_callback = on_quit_callback
        self.on_reconnect_callback = on_reconnect_callback
        self.config_mgr = get_config_manager()
        self.lifecycle_mgr = get_lifecycle_manager()

        self._status_text = "DeskBot: Initializing..."
        self._current_mood = "ready"
        self._icon: Optional[pystray.Icon] = None
        self._lock = threading.Lock()

        # Listen to lifecycle state changes to update tooltip and icon
        self.lifecycle_mgr.add_listener(self._on_lifecycle_change)

    def _on_lifecycle_change(self, state: AppLifecycleState, details: str = "") -> None:
        self._status_text = self.lifecycle_mgr.get_status_description()
        if state == AppLifecycleState.WAITING_FOR_DEVICE or state == AppLifecycleState.DISCONNECTED:
            self._current_mood = "disconnected"
        elif state == AppLifecycleState.READY or state == AppLifecycleState.RUNNING:
            self._current_mood = "ready"
        else:
            self._current_mood = "thinking"

        if self._icon:
            try:
                self._icon.title = self._status_text
                self._icon.icon = create_tray_icon_image(self._current_mood)
            except Exception:
                pass

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(lambda text: self._status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings...", self._action_open_settings),
            pystray.MenuItem("Developer Mode", self._action_toggle_dev_mode, checked=lambda item: bool(self.config_mgr.get("developer_mode", False))),
            pystray.MenuItem("Reconnect Device", self._action_reconnect),
            pystray.MenuItem("View Logs...", self._action_view_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Start with System",
                self._action_toggle_autostart,
                checked=lambda item: is_autostart_enabled(),
                visible=lambda item: is_autostart_supported(),
            ),
            pystray.MenuItem("About DeskBot", self._action_about),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit DeskBot", self._action_quit),
        )

    def _action_open_settings(self, icon=None, item=None) -> None:
        threading.Thread(target=show_settings_dialog, daemon=True).start()

    def _action_toggle_dev_mode(self, icon=None, item=None) -> None:
        current = bool(self.config_mgr.get("developer_mode", False))
        new_val = not current
        self.config_mgr.set("developer_mode", new_val)
        try:
            from tools.developer_tools import set_developer_mode
            set_developer_mode(new_val)
        except Exception:
            pass
        logger.info("[APP] Developer Mode toggled to: %s", new_val)

    def _action_reconnect(self, icon=None, item=None) -> None:
        logger.info("[DEVICE] Manual hardware reconnect requested from tray")
        if self.on_reconnect_callback:
            threading.Thread(target=self.on_reconnect_callback, daemon=True).start()

    def _action_view_logs(self, icon=None, item=None) -> None:
        open_log_file()

    def _action_toggle_autostart(self, icon=None, item=None) -> None:
        new_state = not is_autostart_enabled()
        set_autostart(new_state)

    def _action_about(self, icon=None, item=None) -> None:
        threading.Thread(target=show_about_dialog, daemon=True).start()

    def _action_quit(self, icon=None, item=None) -> None:
        logger.info("[APP] Quit requested from System Tray")
        self.stop()
        if self.on_quit_callback:
            try:
                self.on_quit_callback()
            except Exception:
                pass
        sys.exit(0)

    def start(self) -> None:
        """Start the system tray icon in detached non-blocking background thread."""
        img = create_tray_icon_image("ready")
        self._icon = pystray.Icon(
            name="DeskBot",
            icon=img,
            title="DeskBot: Initializing...",
            menu=self._build_menu(),
        )
        self._icon.run_detached()
        logger.info("[APP] System Tray / Menu Bar icon started")

    def stop(self) -> None:
        """Stop and remove the system tray icon."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
