"""Execute structured DeskBot AI intents on Windows via an extensible Action Registry."""

from __future__ import annotations

import ast
try:
    import config
except ImportError:
    from companion import config
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from typing import Any, Callable, Dict, Tuple
from urllib.parse import quote_plus

try:
    import winreg
except ImportError:
    winreg = None

logger = logging.getLogger(__name__)


from dataclasses import dataclass
from pathlib import Path


@dataclass
class ToolResult:
    """Standardized tool execution result."""
    success: bool
    message: str
    response_text: str = ""
    data: Any = None

    def __bool__(self) -> bool:
        """Allow backwards-compatible truth value testing (if result: ...)."""
        return self.success


class ActionRegistry:
    """Registry mapping intent action names to execution handlers."""

    def __init__(self):
        self._handlers: Dict[str, Callable[[Any], Any]] = {}
        self._descriptions: Dict[str, Callable[[Any], str]] = {}

    def register(self, action_name: str, description_fn: Callable[[Any], str] | None = None):
        """Decorator to register a handler for an action name."""
        def decorator(func: Callable[[Any], Any]):
            self._handlers[action_name] = func
            if description_fn:
                self._descriptions[action_name] = description_fn
            else:
                self._descriptions[action_name] = lambda q: f"Executing {action_name}"
            return func
        return decorator

    def has_action(self, action_name: str) -> bool:
        return action_name in self._handlers

    def describe(self, action_name: str, query: Any = None) -> str:
        desc_fn = self._descriptions.get(action_name)
        if desc_fn:
            try:
                return desc_fn(query)
            except Exception:
                pass
        return f"Executing {action_name}"

    def execute(self, action_name: str, query: Any = None) -> ToolResult:
        handler = self._handlers.get(action_name)
        if not handler:
            print(f"Unsupported AI action: {action_name}")
            return ToolResult(False, f"Unsupported action: {action_name}", "DeskBot does not know how to perform this command.")
        try:
            res = handler(query)
            if isinstance(res, ToolResult):
                return res

            desc = self.describe(action_name, query)
            if bool(res):
                return ToolResult(True, "Success", desc)
            else:
                return ToolResult(False, "Failed", f"Failed to execute {desc}.")
        except Exception as error:
            print(f"Action execution error ({action_name}): {error}", file=sys.stderr)
            return ToolResult(False, str(error), f"Error while executing {action_name}: {error}")


# Global registry instance
REGISTRY = ActionRegistry()


# --- Action Handlers ---

def open_youtube() -> bool:
    """Open YouTube."""
    webbrowser.open("https://www.youtube.com")
    return True


def search_youtube(query: str) -> bool:
    """Search YouTube for a query."""
    clean_query = (query or "").strip()
    if not clean_query:
        return open_youtube()
    url = "https://www.youtube.com/results?search_query=" + quote_plus(clean_query)
    webbrowser.open(url)
    return True


def find_first_youtube_video(query: str, timeout: float = 4.0) -> str | None:
    """Extract the video ID of the first video result for a YouTube query."""
    clean_query = query.strip()
    if not clean_query:
        return None

    search_url = f"https://www.youtube.com/results?search_query={quote_plus(clean_query)}"
    req = urllib.request.Request(
        search_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
    )

    # Robust cross-platform SSL context (handles macOS missing certs & Windows)
    ctx = None
    try:
        import ssl
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
    except Exception:
        ctx = None

    try:
        kwargs: Dict[str, Any] = {"timeout": timeout}
        if ctx is not None:
            kwargs["context"] = ctx
        with urllib.request.urlopen(req, **kwargs) as response:
            buffer = ""
            while True:
                chunk = response.read(32768)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="ignore")
                matches = re.findall(r"(?:watch\?v=|\"videoId\":\")([a-zA-Z0-9_-]{11})", buffer)
                if matches:
                    return matches[0]
                if len(buffer) > 65536:
                    buffer = buffer[-200:]
    except Exception as error:
        logger.debug("YouTube video ID extraction error: %s", error)

    return None


def play_youtube(query: str | None) -> bool:
    """Handle a YouTube play request: directly plays the first matching video."""
    clean_query = (query or "").strip()
    if not clean_query:
        return open_youtube()

    # Try resolving the first matching video ID to launch playback immediately
    video_id = find_first_youtube_video(clean_query)
    if video_id:
        direct_url = f"https://www.youtube.com/watch?v={video_id}"
        webbrowser.open(direct_url)
        return True

    # Fallback to search results page
    fallback_url = "https://www.youtube.com/results?search_query=" + quote_plus(clean_query)
    webbrowser.open(fallback_url)
    return True


def open_spotify() -> bool:
    """Open Spotify desktop client."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", "spotify:"], shell=False)
    else:
        subprocess.Popen(
            ["cmd", "/c", "start", "", "spotify:"],
            shell=False,
        )
    return True


def _bring_spotify_to_front() -> None:
    """Attempt to bring Spotify window to the foreground."""
    try:
        import ctypes
        import win32gui
        user32 = ctypes.windll.user32

        def enum_cb(hwnd, found):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                cls = win32gui.GetClassName(hwnd)
                if "Spotify" in title or cls == "Chrome_WidgetWin_0":
                    found.append(hwnd)

        hwnds: list[int] = []
        win32gui.EnumWindows(enum_cb, hwnds)
        if hwnds:
            user32.ShowWindow(hwnds[0], 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnds[0])
    except Exception as err:
        logger.debug("Could not bring Spotify to front: %s", err)


def _send_key(vk_code: int) -> None:
    """Send a keydown and keyup event for a given virtual key code."""
    import ctypes
    user32 = ctypes.windll.user32
    user32.keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(vk_code, 0, 2, 0)  # KEYEVENTF_KEYUP = 2


def _trigger_spotify_play() -> None:
    """Helper thread to play after Spotify loads search results."""
    try:
        if sys.platform == "darwin":
            time.sleep(1.8)
            try:
                subprocess.run(["osascript", "-e", 'tell application "Spotify" to play'], capture_output=True)
            except Exception:
                pass
            return

        # Give Spotify sufficient time to launch/focus and render network search results
        time.sleep(2.2)

        # 1. Bring Spotify to front and send keys via Windows Script Host COM if available
        try:
            import win32com.client
            wscript = win32com.client.Dispatch("WScript.Shell")
            if wscript.AppActivate("Spotify"):
                time.sleep(0.15)
                # Tab moves focus out of the search input box onto the Top Result card
                wscript.SendKeys("{TAB}")
                time.sleep(0.1)
                wscript.SendKeys("{ENTER}")
                time.sleep(0.5)
                wscript.SendKeys("{ENTER}")
                return
        except Exception as wscript_err:
            logger.debug("WScript Spotify trigger failed: %s", wscript_err)

        # 2. Fallback: Win32 API direct key simulation
        _bring_spotify_to_front()
        # Tab (0x09) moves focus from the search input field into the search results
        _send_key(0x09)  # VK_TAB
        time.sleep(0.1)
        # Enter (0x0D) triggers playback on the Top Result
        _send_key(0x0D)  # VK_RETURN
        time.sleep(0.5)
        _send_key(0x0D)  # VK_RETURN

    except Exception as err:
        logger.debug("Spotify auto-play trigger exception: %s", err)


def play_spotify(query: str | None) -> bool:
    """Handle a Spotify play/search request and trigger playback."""
    clean_query = (query or "").strip()
    if not clean_query:
        return open_spotify()

    encoded = quote_plus(clean_query)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", f"spotify:search:{encoded}"], shell=False)
        else:
            subprocess.Popen(
                ["cmd", "/c", "start", "", f"spotify:search:{encoded}"],
                shell=False,
            )
        # Launch background thread to press play on the top result
        threading.Thread(target=_trigger_spotify_play, daemon=True).start()
        return True
    except Exception as error:
        logger.warning("Could not launch Spotify protocol URI: %s", error)
        webbrowser.open(f"https://open.spotify.com/search/{encoded}")
        return True


def open_google() -> bool:
    """Open Google homepage."""
    webbrowser.open("https://www.google.com")
    return True


COMMON_APP_MAP: Dict[str, str] = {
    # System Utilities & Accessories
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "notepad": "notepad.exe",
    "notes": "notepad.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "snipping tool": "SnippingTool.exe",
    "snippingtool": "SnippingTool.exe",
    "snip": "ms-screenclip:",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "task monitor": "taskmgr.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "files": "explorer.exe",
    "my computer": "explorer.exe",
    "this pc": "explorer.exe",
    "control panel": "control.exe",
    "command prompt": "cmd.exe",
    "cmd": "cmd.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "wt": "wt.exe",
    "powershell": "powershell.exe",
    "registry editor": "regedit.exe",
    "regedit": "regedit.exe",
    "device manager": "devmgmt.msc",
    "disk cleanup": "cleanmgr.exe",
    "character map": "charmap.exe",
    "services": "services.msc",
    "event viewer": "eventvwr.msc",
    "resource monitor": "resmon.exe",

    # Windows Settings & UWP Apps
    "settings": "ms-settings:",
    "windows settings": "ms-settings:",
    "system settings": "ms-settings:",
    "clock": "ms-clock:",
    "alarms": "ms-clock:",
    "alarm": "ms-clock:",
    "timer": "ms-clock:",
    "stopwatch": "ms-clock:",
    "camera": "microsoft.windows.camera:",
    "photos": "ms-photos:",
    "photo viewer": "ms-photos:",
    "store": "ms-windows-store:",
    "microsoft store": "ms-windows-store:",
    "windows store": "ms-windows-store:",
    "weather": "bingweather:",
    "maps": "bingmaps:",
    "sticky notes": "shell:AppsFolder\\Microsoft.MicrosoftStickyNotes_8wekyb3d8bbwe!App",

    # Web Browsers
    "google chrome": "chrome.exe",
    "chrome": "chrome.exe",
    "chrome browser": "chrome.exe",
    "firefox": "firefox.exe",
    "mozilla firefox": "firefox.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "ms edge": "msedge.exe",
    "brave": "brave.exe",
    "opera": "opera.exe",

    # Development & Productivity
    "visual studio code": "code",
    "vs code": "code",
    "vscode": "code",
    "code": "code",
    "visual studio": "devenv.exe",
    "git bash": "git-bash.exe",

    # Office Suite
    "word": "winword.exe",
    "microsoft word": "winword.exe",
    "ms word": "winword.exe",
    "excel": "excel.exe",
    "microsoft excel": "excel.exe",
    "ms excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "microsoft powerpoint": "powerpnt.exe",
    "ppt": "powerpnt.exe",
    "outlook": "olk.exe",
    "microsoft outlook": "olk.exe",
    "teams": "msteams.exe",
    "microsoft teams": "msteams.exe",

    # Media & Third Party
    "spotify": "spotify:",
    "vlc": "vlc.exe",
    "vlc media player": "vlc.exe",
    "media player": "wmplayer.exe",
    "blender": "blender.exe",
    "steam": "steam.exe",
    "discord": "discord.exe",
    "slack": "slack.exe",
    "obs": "obs64.exe",
    "obs studio": "obs64.exe",
    "epic games": "EpicGamesLauncher.exe",
    "epic games launcher": "EpicGamesLauncher.exe",
    "7-zip": "7zFM.exe",
    "7zip": "7zFM.exe",
}

MACOS_APP_MAP: Dict[str, str] = {
    # System Utilities & Accessories
    "calculator": "Calculator",
    "calc": "Calculator",
    "notes": "Notes",
    "apple notes": "Notes",
    "notepad": "TextEdit",
    "textedit": "TextEdit",
    "terminal": "Terminal",
    "mac terminal": "Terminal",
    "activity monitor": "Activity Monitor",
    "task manager": "Activity Monitor",
    "taskmgr": "Activity Monitor",
    "task monitor": "Activity Monitor",
    "finder": "Finder",
    "files": "Finder",
    "file explorer": "Finder",
    "settings": "System Settings",
    "windows settings": "System Settings",
    "system settings": "System Settings",
    "system preferences": "System Settings",
    "preferences": "System Settings",
    "calendar": "Calendar",
    "reminders": "Reminders",
    "contacts": "Contacts",
    "mail": "Mail",
    "email": "Mail",
    "messages": "Messages",
    "imessage": "Messages",
    "facetime": "FaceTime",
    "maps": "Maps",
    "apple maps": "Maps",
    "photos": "Photos",
    "photo viewer": "Photos",
    "music": "Music",
    "apple music": "Music",
    "podcasts": "Podcasts",
    "tv": "TV",
    "apple tv": "TV",
    "books": "Books",
    "app store": "App Store",
    "store": "App Store",
    "keynote": "Keynote",
    "numbers": "Numbers",
    "pages": "Pages",
    "preview": "Preview",
    "pdf viewer": "Preview",
    "font book": "Font Book",
    "disk utility": "Disk Utility",
    "console": "Console",
    "clock": "Clock",
    "alarm": "Clock",
    "alarms": "Clock",
    "timer": "Clock",
    "stopwatch": "Clock",
    "weather": "Weather",
    "shortcuts": "Shortcuts",
    "camera": "Photo Booth",
    "photo booth": "Photo Booth",

    # Web Browsers
    "safari": "Safari",
    "google chrome": "Google Chrome",
    "chrome": "Google Chrome",
    "chrome browser": "Google Chrome",
    "firefox": "Firefox",
    "mozilla firefox": "Firefox",
    "brave": "Brave Browser",
    "brave browser": "Brave Browser",
    "edge": "Microsoft Edge",
    "microsoft edge": "Microsoft Edge",
    "ms edge": "Microsoft Edge",
    "arc": "Arc",
    "opera": "Opera",

    # Development & Productivity
    "visual studio code": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "xcode": "Xcode",
    "iterm": "iTerm",
    "iterm2": "iTerm",
    "warp": "Warp",
    "sublime": "Sublime Text",
    "sublime text": "Sublime Text",

    # Media & Communication
    "spotify": "Spotify",
    "vlc": "VLC",
    "vlc media player": "VLC",
    "slack": "Slack",
    "discord": "Discord",
    "zoom": "zoom.us",
    "teams": "Microsoft Teams",
    "microsoft teams": "Microsoft Teams",
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
    "notion": "Notion",
    "obs": "OBS",
    "obs studio": "OBS",
    "steam": "Steam",
    "chatgpt": "ChatGPT",
    "claude": "Claude",
    "github desktop": "GitHub Desktop",
}

_MACOS_APP_CACHE: Dict[str, str] | None = None
_MACOS_APP_CACHE_TIME: float = 0.0


def get_installed_macos_apps(refresh: bool = False) -> Dict[str, str]:
    """Scan macOS /Applications, /System/Applications, and ~/Applications for installed .app bundles."""
    global _MACOS_APP_CACHE, _MACOS_APP_CACHE_TIME
    now = time.time()
    if not refresh and _MACOS_APP_CACHE is not None and (now - _MACOS_APP_CACHE_TIME) < 60.0:
        return _MACOS_APP_CACHE

    dirs = [
        Path("/Applications"),
        Path("/System/Applications"),
        Path("/System/Applications/Utilities"),
        Path.home() / "Applications",
    ]
    apps: Dict[str, str] = {}
    for d in dirs:
        if d.is_dir():
            try:
                for entry in d.iterdir():
                    if entry.suffix == ".app":
                        name = entry.stem
                        apps[name.lower()] = name
            except Exception:
                pass

    _MACOS_APP_CACHE = apps
    _MACOS_APP_CACHE_TIME = now
    return apps


_SHORTCUT_CACHE: list[tuple[str, str]] | None = None
_SHORTCUT_CACHE_TIME: float = 0.0


def get_installed_shortcuts(refresh: bool = False) -> list[tuple[str, str]]:
    """Scan Start Menu and Desktop directories for .lnk shortcuts, with caching."""
    global _SHORTCUT_CACHE, _SHORTCUT_CACHE_TIME
    now = time.time()
    if not refresh and _SHORTCUT_CACHE is not None and (now - _SHORTCUT_CACHE_TIME) < 60.0:
        return _SHORTCUT_CACHE

    dirs = [
        os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%USERPROFILE%\Desktop"),
        os.path.expandvars(r"%PUBLIC%\Desktop"),
    ]
    shortcuts: list[tuple[str, str]] = []
    for directory in dirs:
        if os.path.exists(directory):
            for root, _, files in os.walk(directory):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        name = os.path.splitext(f)[0]
                        full_path = os.path.join(root, f)
                        shortcuts.append((name, full_path))

    _SHORTCUT_CACHE = shortcuts
    _SHORTCUT_CACHE_TIME = now
    return shortcuts


def find_best_shortcut(query: str, shortcuts: list[tuple[str, str]]) -> str | None:
    """Find the best matching shortcut path for a given app name."""
    clean_q = query.lower().strip()
    q_words = [w for w in re.split(r"[\s\-_]+", clean_q) if w]
    if not q_words:
        return None

    penalized_terms = {
        "uninstall",
        "help",
        "readme",
        "documentation",
        "manual",
        "website",
        "support",
        "license",
        "setup",
    }

    scored: list[tuple[int, str]] = []
    for name, path in shortcuts:
        nl = name.lower()
        n_words = [w for w in re.split(r"[\s\-_]+", nl) if w]

        penalty = 1000 if any(p in nl for p in penalized_terms) else 0

        # 1. Exact match
        if nl == clean_q:
            scored.append((0 + penalty, path))
            continue

        # 2. Substring matches
        if clean_q in nl:
            score = len(nl) - len(clean_q) + penalty
            scored.append((score, path))
            continue
        elif nl in clean_q:
            score = len(clean_q) - len(nl) + 50 + penalty
            scored.append((score, path))
            continue

        # 3. Word overlap
        common = set(q_words).intersection(set(n_words))
        if common:
            match_ratio = len(common) / max(len(q_words), 1)
            if match_ratio >= 0.5:
                score = int((1.0 - match_ratio) * 100) + len(nl) + penalty
                scored.append((score, path))

    if scored:
        scored.sort(key=lambda x: x[0])
        return scored[0][1]

    return None


_REGISTRY_APP_PATHS_CACHE: dict[str, str] | None = None


def get_registry_app_paths() -> dict[str, str]:
    """Retrieve executable registrations from Windows Registry App Paths."""
    global _REGISTRY_APP_PATHS_CACHE
    if _REGISTRY_APP_PATHS_CACHE is not None:
        return _REGISTRY_APP_PATHS_CACHE

    results: dict[str, str] = {}
    if winreg is None:
        _REGISTRY_APP_PATHS_CACHE = results
        return results

    for root_key in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root_key, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as key:
                count = winreg.QueryInfoKey(key)[0]
                for i in range(count):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            val, _ = winreg.QueryValueEx(subkey, "")
                            if val:
                                results[subkey_name.lower()] = val
                                base = os.path.splitext(subkey_name)[0].lower()
                                results[base] = val
                    except Exception:
                        pass
        except Exception:
            pass

    _REGISTRY_APP_PATHS_CACHE = results
    return results


def find_installed_app(app_name: str) -> str | None:
    """Resolve an application query to an executable, shortcut, or protocol URI."""
    clean = (app_name or "").strip()
    if not clean:
        return None

    # Remove conversational prefixes/suffixes
    clean = re.sub(r"^(?:the|a)\s+", "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r"\s+app(?:lication)?$", "", clean, flags=re.IGNORECASE).strip()
    clean_lower = clean.lower()

    # --- macOS Resolution ---
    if sys.platform == "darwin":
        # 1. Check known macOS alias map
        if clean_lower in MACOS_APP_MAP:
            return MACOS_APP_MAP[clean_lower]

        # 2. Check installed .app bundles across /Applications, /System/Applications, etc.
        apps = get_installed_macos_apps()
        if clean_lower in apps:
            return apps[clean_lower]

        # 3. Substring matching in installed applications
        for k, v in apps.items():
            if clean_lower in k or k in clean_lower:
                return v

        # 4. Check PATH via which
        try:
            which_res = subprocess.run(["which", clean_lower], capture_output=True, text=True)
            if which_res.returncode == 0 and which_res.stdout.strip():
                return which_res.stdout.strip()
        except OSError:
            pass

        return clean.title()

    # --- Windows Resolution ---
    # 1. Check known system/protocol alias map
    if clean_lower in COMMON_APP_MAP:
        return COMMON_APP_MAP[clean_lower]

    # 2. Check Start Menu and Desktop shortcuts
    shortcuts = get_installed_shortcuts()
    matched_shortcut = find_best_shortcut(clean_lower, shortcuts)
    if matched_shortcut:
        return matched_shortcut

    # 3. Check Windows Registry App Paths
    app_paths = get_registry_app_paths()
    if clean_lower in app_paths:
        return app_paths[clean_lower]
    if f"{clean_lower}.exe" in app_paths:
        return app_paths[f"{clean_lower}.exe"]

    # 4. Check %LOCALAPPDATA%\Microsoft\WindowsApps
    winapps_dir = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps")
    if os.path.exists(winapps_dir):
        candidate = os.path.join(winapps_dir, f"{clean_lower}.exe")
        if os.path.isfile(candidate):
            return candidate

    # 5. Check PATH via where.exe
    try:
        where_res = subprocess.run(
            ["where.exe", clean_lower],
            capture_output=True,
            text=True,
        )
        if where_res.returncode == 0:
            lines = where_res.stdout.strip().splitlines()
            if lines:
                return lines[0]
    except OSError:
        pass

    return None


def _launch_target(target: str) -> bool:
    """Launch a target (file, shortcut, URI, or command) non-blockingly."""
    # 0. macOS native launcher
    if sys.platform == "darwin":
        try:
            proc = subprocess.run(["open", "-a", target], capture_output=True, text=True)
            if proc.returncode == 0:
                return True
            proc2 = subprocess.run(["open", target], capture_output=True, text=True)
            return proc2.returncode == 0
        except Exception as err:
            logger.debug("macOS open failed for %r: %s", target, err)
            return False

    # 1. Native Windows ShellExecute
    if hasattr(os, "startfile"):
        try:
            os.startfile(target)
            return True
        except Exception as err:
            logger.debug("os.startfile failed for %r: %s", target, err)

    # 2. Command shell start
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", target],
            shell=False,
        )
        return True
    except Exception as err:
        logger.debug("cmd start failed for %r: %s", target, err)

    # 3. PowerShell Start-Process fallback
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f'Start-Process "{target}"'],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            return True
    except Exception as err:
        logger.debug("PowerShell Start-Process failed for %r: %s", target, err)

    return False


def launch_windows_app(app_name: str) -> bool:
    """Launch any application installed on the system (Windows or macOS)."""
    clean_name = (app_name or "").strip()
    if not clean_name:
        print("No application name was provided.")
        return False

    target = find_installed_app(clean_name)
    if not target:
        target = clean_name

    success = _launch_target(target)
    if success:
        logger.info("Successfully launched app %r (resolved target: %r)", clean_name, target)
        return True

    print(f"Could not find or launch installed app: {clean_name}")
    return False


launch_app = launch_windows_app


# --- Registration ---

@REGISTRY.register("open_app", description_fn=lambda q: f"Launching app: {q}")
def _handle_open_app(query: Any) -> ToolResult:
    clean_app = str(query or "").strip()
    if not clean_app:
        return ToolResult(False, "Missing app name", "Please specify which app you want to open.")
    ok = launch_app(clean_app)
    if ok:
        return ToolResult(True, f"Opened {clean_app}", f"Opening {clean_app}.")
    return ToolResult(False, f"Could not find or launch {clean_app}", f"I couldn't find or open {clean_app}.")


@REGISTRY.register("open_website", description_fn=lambda q: f"Opening website: {q}")
def _handle_open_website(query: Any) -> ToolResult:
    website = str(query or "").strip().lower()
    if not website:
        return ToolResult(False, "Missing website", "Please specify which website to open.")
    if website in {"youtube", "yt", "youtube.com", "www.youtube.com"}:
        ok = open_youtube()
        return ToolResult(ok, "Opened YouTube" if ok else "Failed to open YouTube", "Opening YouTube." if ok else "I couldn't open YouTube.")
    if website in {"google", "google.com", "www.google.com"}:
        ok = open_google()
        return ToolResult(ok, "Opened Google" if ok else "Failed to open Google", "Opening Google." if ok else "I couldn't open Google.")
    if website.startswith(("http://", "https://")):
        try:
            webbrowser.open(website)
            return ToolResult(True, f"Opened {website}", f"Opening {website}.")
        except Exception as err:
            return ToolResult(False, str(err), f"I couldn't open {website}.")
    if "." in website:
        try:
            webbrowser.open(f"https://{website}")
            return ToolResult(True, f"Opened https://{website}", f"Opening {website}.")
        except Exception as err:
            return ToolResult(False, str(err), f"I couldn't open {website}.")
    print(f"Unrecognized website address: {website}")
    return ToolResult(False, f"Unrecognized website: {website}", f"I couldn't recognize the website '{website}'.")


@REGISTRY.register("youtube_search", description_fn=lambda q: f"Searching YouTube for: {q}")
def _handle_youtube_search(query: Any) -> ToolResult:
    q_str = str(query or "").strip()
    ok = search_youtube(q_str)
    return ToolResult(ok, f"YouTube search: {q_str}" if ok else "Failed YouTube search", f"Searching YouTube for {q_str}." if ok else "Could not open YouTube search.")


@REGISTRY.register("youtube_play", description_fn=lambda q: f"Playing YouTube: {q or 'music'}")
def _handle_youtube_play(query: Any) -> ToolResult:
    q_str = str(query) if query else "music"
    ok = play_youtube(str(query) if query else None)
    return ToolResult(ok, f"Playing YouTube: {q_str}" if ok else "Failed YouTube play", f"Playing {q_str} on YouTube." if ok else "Could not play on YouTube.")


@REGISTRY.register("spotify_open", description_fn=lambda q: "Opening Spotify")
def _handle_spotify_open(query: Any = None) -> ToolResult:
    ok = open_spotify()
    return ToolResult(ok, "Opened Spotify" if ok else "Failed to open Spotify", "Opening Spotify." if ok else "I couldn't open Spotify.")


@REGISTRY.register("spotify_play", description_fn=lambda q: f"Playing on Spotify: {q or 'music'}")
def _handle_spotify_play(query: Any) -> ToolResult:
    q_str = str(query) if query else "music"
    ok = play_spotify(str(query) if query else None)
    return ToolResult(ok, f"Playing Spotify: {q_str}" if ok else "Failed Spotify play", f"Playing {q_str} on Spotify." if ok else "Could not play on Spotify.")


# --- Volume and Audio Controls ---
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF


def _adjust_volume_darwin(increase: bool, amount: int = 10) -> ToolResult:
    try:
        delta = amount if increase else -amount
        script = f"set volume output volume ((output volume of (get volume settings)) + {delta})"
        subprocess.run(["osascript", "-e", script], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        direction = "increased" if increase else "decreased"
        return ToolResult(True, f"Volume {direction} by {amount}%", f"Volume {direction}.")
    except Exception as err:
        return ToolResult(False, f"Volume error: {err}", "Failed to adjust volume.")


def _toggle_mute_darwin(mute: bool = True) -> ToolResult:
    try:
        val = "true" if mute else "false"
        script = f"set volume output muted {val}"
        subprocess.run(["osascript", "-e", script], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        action_word = "muted" if mute else "unmuted"
        return ToolResult(True, f"Master volume {action_word}", f"Audio {action_word}.")
    except Exception as err:
        return ToolResult(False, f"Mute toggle error: {err}", "Failed to toggle audio mute.")


def _adjust_volume_windows(increase: bool, amount: int = 10) -> ToolResult:
    steps = max(1, min(25, amount // 2))
    vk = VK_VOLUME_UP if increase else VK_VOLUME_DOWN
    try:
        import ctypes
        for _ in range(steps):
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
            time.sleep(0.015)
        direction = "increased" if increase else "decreased"
        return ToolResult(True, f"Volume {direction} by {steps * 2}%", f"Volume {direction}.")
    except Exception as err:
        return ToolResult(False, f"Volume error: {err}", "Failed to adjust volume.")


def _toggle_mute_windows(mute: bool = True) -> ToolResult:
    try:
        import ctypes
        ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
        action_word = "muted" if mute else "unmuted"
        return ToolResult(True, f"Master volume {action_word}", f"Audio {action_word}.")
    except Exception as err:
        return ToolResult(False, f"Mute toggle error: {err}", "Failed to toggle audio mute.")


def _adjust_volume(increase: bool, amount: int = 10) -> ToolResult:
    """Safely adjust master volume using native OS facilities."""
    if sys.platform == "darwin":
        return _adjust_volume_darwin(increase=increase, amount=amount)
    elif sys.platform == "win32":
        return _adjust_volume_windows(increase=increase, amount=amount)
    else:
        direction = "increased" if increase else "decreased"
        return ToolResult(True, f"Volume {direction} by {amount}%", f"Volume {direction}.")


def _toggle_mute(mute: bool = True) -> ToolResult:
    """Safely toggle master volume mute state."""
    if sys.platform == "darwin":
        return _toggle_mute_darwin(mute=mute)
    elif sys.platform == "win32":
        return _toggle_mute_windows(mute=mute)
    else:
        action_word = "muted" if mute else "unmuted"
        return ToolResult(True, f"Master volume {action_word}", f"Audio {action_word}.")


@REGISTRY.register("volume_up", description_fn=lambda q: f"Increasing volume: {q or '10%'}")
def _handle_volume_up(query: Any) -> ToolResult:
    amount = 10
    if query:
        match = re.search(r"\d+", str(query))
        if match:
            amount = int(match.group())
    return _adjust_volume(increase=True, amount=amount)


@REGISTRY.register("volume_down", description_fn=lambda q: f"Decreasing volume: {q or '10%'}")
def _handle_volume_down(query: Any) -> ToolResult:
    amount = 10
    if query:
        match = re.search(r"\d+", str(query))
        if match:
            amount = int(match.group())
    return _adjust_volume(increase=False, amount=amount)


@REGISTRY.register("mute", description_fn=lambda q: "Muting master volume")
def _handle_mute(query: Any) -> ToolResult:
    return _toggle_mute(mute=True)


@REGISTRY.register("unmute", description_fn=lambda q: "Unmuting master volume")
def _handle_unmute(query: Any) -> ToolResult:
    return _toggle_mute(mute=False)


@REGISTRY.register("screenshot", description_fn=lambda q: "Capturing screenshot")
def _handle_screenshot(query: Any) -> ToolResult:
    try:
        import datetime
        try:
            from platform_layer.permissions import has_screen_capture_permission, request_screen_capture_permission
            from vision.screen_capture import capture_raw_screen
        except (ImportError, ModuleNotFoundError):
            from companion.platform_layer.permissions import has_screen_capture_permission, request_screen_capture_permission
            from companion.vision.screen_capture import capture_raw_screen

        if sys.platform == "darwin" and not has_screen_capture_permission():
            # Trigger OS prompt once on explicit user screenshot action
            request_screen_capture_permission()
            return ToolResult(
                False,
                "Screen Recording permission is required.",
                "Screen Recording permission is required to capture screenshots. Please enable DeskBot in System Settings → Privacy & Security → Screen & System Audio Recording.",
            )

        desktop_dir = Path.home() / "Desktop"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        filename = f"DeskBot_Screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        target_path = desktop_dir / filename

        img = capture_raw_screen()
        if img is None:
            return ToolResult(
                False,
                "Could not capture screenshot. Screen recording permission may be required.",
                "I was unable to capture your screen. Please ensure Screen Recording permission is enabled under System Settings → Privacy & Security → Screen & System Audio Recording.",
            )

        img.save(str(target_path))

        return ToolResult(
            True,
            f"Saved to {target_path}",
            "Screenshot captured and saved to your Desktop.",
            data={"path": str(target_path)},
        )
    except Exception as err:
        logger.debug("Screenshot error: %s", err)
        return ToolResult(False, f"Screenshot error: {err}", "Could not capture a screenshot.")


PROHIBITED_PROCESSES = {
    "explorer.exe", "winlogon.exe", "csrss.exe", "smss.exe", "svchost.exe",
    "services.exe", "lsass.exe", "dwm.exe", "system", "idle"
}
MACOS_PROHIBITED_APPS = {
    "finder", "dock", "systemuiserver", "windowserver", "loginwindow", "launchd", "kernel_task"
}


@REGISTRY.register("close_app", description_fn=lambda q: f"Closing application: {q}")
def _handle_close_app(query: Any) -> ToolResult:
    clean_name = str(query or "").strip().lower()
    if not clean_name:
        return ToolResult(False, "Missing app name", "Please specify which application to close.")

    # Guard critical system processes on both platforms
    clean_base = clean_name[:-4] if clean_name.endswith(".exe") else clean_name
    clean_exe = f"{clean_base}.exe"
    if (
        clean_name in PROHIBITED_PROCESSES
        or clean_exe in PROHIBITED_PROCESSES
        or clean_base in MACOS_PROHIBITED_APPS
        or clean_name in MACOS_PROHIBITED_APPS
    ):
        return ToolResult(False, f"Closing {clean_name} is prohibited for system safety.", "Cannot close protected system process.")

    if sys.platform == "darwin":
        app_title = MACOS_APP_MAP.get(clean_name, clean_name.title())
        try:
            res = subprocess.run(["osascript", "-e", f'tell application "{app_title}" to quit'], capture_output=True, text=True)
            if res.returncode == 0:
                return ToolResult(True, f"Closed {app_title}", f"Closed {clean_name.title()}.")
            res_pkill = subprocess.run(["pkill", "-f", clean_name], capture_output=True, text=True)
            if res_pkill.returncode == 0:
                return ToolResult(True, f"Closed {app_title}", f"Closed {clean_name.title()}.")
            return ToolResult(False, f"{app_title} was not running", f"{clean_name.title()} is not currently open.")
        except Exception as err:
            return ToolResult(False, str(err), f"Error closing {clean_name.title()}: {err}")

    exe_target = COMMON_APP_MAP.get(clean_name, clean_name)
    if not exe_target.lower().endswith(".exe"):
        exe_target += ".exe"

    try:
        res = subprocess.run(
            ["taskkill", "/IM", exe_target, "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return ToolResult(True, f"Closed {exe_target}", f"Closed {clean_name.title()}.")
        elif res.returncode == 128:
            return ToolResult(False, f"{exe_target} was not running", f"{clean_name.title()} is not currently open.")
        else:
            return ToolResult(False, res.stderr.strip() or "Taskkill failed", f"Could not close {clean_name.title()}.")
    except Exception as err:
        return ToolResult(False, str(err), f"Error closing {clean_name.title()}: {err}")


SAFE_FOLDERS: Dict[str, Path] = {
    "downloads": Path.home() / "Downloads",
    "documents": Path.home() / "Documents",
    "pictures": Path.home() / "Pictures",
    "screenshots": Path.home() / "Pictures" / "Screenshots",
    "screenshot": Path.home() / "Pictures" / "Screenshots",
    "desktop": Path.home() / "Desktop",
    "videos": Path.home() / "Videos",
    "music": Path.home() / "Music",
    "projects": Path.home() / "Projects",
    "deskbot": config.WORKSPACE_ROOT,
}


def _extract_path_arg(query: Any) -> str:
    """Helper to extract path/target argument from string or dict."""
    if isinstance(query, dict):
        if "arguments" in query and isinstance(query["arguments"], dict):
            return str(query["arguments"].get("path") or query["arguments"].get("query") or "")
        return str(query.get("path") or query.get("query") or query.get("file") or query.get("folder") or "")
    return str(query or "").strip()


@REGISTRY.register("open_file_explorer", description_fn=lambda q: "Opening File Explorer")
def _handle_open_file_explorer(query: Any = None) -> ToolResult:
    from tools.file_tools import open_file_explorer
    return open_file_explorer()


@REGISTRY.register("open_folder", description_fn=lambda q: f"Opening folder: {_extract_path_arg(q) or 'Explorer'}")
def _handle_open_folder(query: Any) -> ToolResult:
    from tools.file_tools import open_folder
    target = _extract_path_arg(query)
    return open_folder(target)


@REGISTRY.register("create_file", description_fn=lambda q: f"Creating file: {_extract_path_arg(q)}")
def _handle_create_file(query: Any) -> ToolResult:
    from tools.file_tools import create_file
    target = _extract_path_arg(query)
    content = ""
    if isinstance(query, dict):
        content = str(query.get("content", ""))
    return create_file(target, content=content)


@REGISTRY.register("create_folder", description_fn=lambda q: f"Creating folder: {_extract_path_arg(q)}")
def _handle_create_folder(query: Any) -> ToolResult:
    from tools.file_tools import create_folder
    target = _extract_path_arg(query)
    return create_folder(target)


@REGISTRY.register("open_file", description_fn=lambda q: f"Opening file: {_extract_path_arg(q)}")
def _handle_open_file(query: Any) -> ToolResult:
    from tools.file_tools import open_file
    target = _extract_path_arg(query)
    return open_file(target)


@REGISTRY.register("open_in_vscode", description_fn=lambda q: f"Opening in VS Code: {_extract_path_arg(q) or 'DeskBot project'}")
def _handle_open_in_vscode(query: Any = None) -> ToolResult:
    from tools.file_tools import open_in_vscode
    target = _extract_path_arg(query)
    return open_in_vscode(target)


@REGISTRY.register("open_project_in_vscode", description_fn=lambda q: "Opening DeskBot project in VS Code")
def _handle_open_project_in_vscode(query: Any = None) -> ToolResult:
    from tools.file_tools import open_in_vscode
    target = _extract_path_arg(query) or "deskbot"
    return open_in_vscode(target)


@REGISTRY.register("delete_file", description_fn=lambda q: f"Deleting file: {_extract_path_arg(q)}")
def _handle_delete_file(query: Any) -> ToolResult:
    from tools.file_tools import delete_file
    target = _extract_path_arg(query)
    return delete_file(target)


@REGISTRY.register("delete_folder", description_fn=lambda q: f"Deleting folder: {_extract_path_arg(q)}")
def _handle_delete_folder(query: Any) -> ToolResult:
    from tools.file_tools import delete_folder
    target = _extract_path_arg(query)
    return delete_folder(target)



@REGISTRY.register("web_search", description_fn=lambda q: f"Searching web for: {q}")
def _handle_web_search(query: Any) -> ToolResult:
    from tools.web_search import search_web
    clean_q = str(query or "").strip()
    if not clean_q:
        return ToolResult(False, "Missing search query", "Please specify what you would like to search for.", data=[])
    results = search_web(clean_q, max_results=4)
    if not results:
        return ToolResult(False, f"No results for {clean_q}", f"I couldn't find any web results for '{clean_q}'.", data=[])
    top_snippet = results[0]["snippet"]
    return ToolResult(True, f"Found {len(results)} results", f"Here is what I found for '{clean_q}': {top_snippet}", data=results)


@REGISTRY.register("clarification", description_fn=lambda q: "Clarification needed")
def _handle_clarification(query: Any) -> ToolResult:
    text = str(query or "").strip() or "Could you please clarify what you would like me to do?"
    return ToolResult(True, "Clarification needed", text)


@REGISTRY.register("current_time", description_fn=lambda q: "Checking current time")
def _handle_current_time(query: Any = None) -> ToolResult:
    from tools.info_tools import get_current_time
    t = get_current_time()
    return ToolResult(True, f"Time: {t}", f"It's {t}.")


@REGISTRY.register("current_date", description_fn=lambda q: "Checking current date")
def _handle_current_date(query: Any = None) -> ToolResult:
    from tools.info_tools import get_current_date
    d = get_current_date()
    return ToolResult(True, f"Date: {d}", f"Today is {d}.")


@REGISTRY.register("system_info", description_fn=lambda q: "Checking system metrics")
def _handle_system_info(query: Any = None) -> ToolResult:
    from tools.info_tools import get_system_info
    info = get_system_info()
    cpu = info.get("cpu_percent", "N/A")
    ram = info.get("ram_percent", "N/A")
    battery = info.get("battery_percent")
    b_text = f", battery is at {battery}%" if battery is not None else ""
    resp = f"CPU usage is {cpu}%, RAM is at {ram}%{b_text}."
    return ToolResult(True, str(info), resp, data=info)


@REGISTRY.register("weather", description_fn=lambda q: f"Checking weather: {q or 'local'}")
def _handle_weather(query: Any = None) -> ToolResult:
    try:
        from tools.info_tools import get_weather
    except ImportError:
        from companion.tools.info_tools import get_weather
    res = get_weather(str(query) if query else None)
    if "error" in res:
        if res.get("need_city"):
            return ToolResult(True, "City required", "Which city should I check?", data=res)
        return ToolResult(False, res["error"], f"Could not retrieve weather: {res['error']}")
    city = res["city"]
    temp = res["temperature_c"]
    cond = res["condition"]
    return ToolResult(True, f"{city}: {temp}°C {cond}", f"The weather in {city} is {temp}°C with {cond.lower()}.", data=res)


@REGISTRY.register("direct_answer", description_fn=lambda q: "Direct answer")
def _handle_direct_answer(query: Any) -> ToolResult:
    text = str(query or "").strip()
    return ToolResult(True, "Direct answer", text)


@REGISTRY.register("calculate", description_fn=lambda q: f"Calculating: {q}")
def _handle_calculate(query: Any) -> ToolResult:
    try:
        from tools.calculator import evaluate_math
    except ImportError:
        from companion.tools.calculator import evaluate_math
    expr = str(query or "").strip()
    if re.search(r"\b(?:is|equals)\s+[0-9\-.]+\.?$", expr, re.IGNORECASE):
        return ToolResult(True, expr, expr, data={"result": expr})
    res = evaluate_math(expr)
    if res:
        return ToolResult(True, res, res, data={"result": res})
    return ToolResult(False, f"Could not calculate {expr}.", f"Could not calculate {expr}.")


@REGISTRY.register("enter_developer_mode", description_fn=lambda q: "Entering Developer Mode")
def _handle_enter_developer_mode(query: Any = None) -> ToolResult:
    from tools.developer_tools import set_developer_mode
    return set_developer_mode(True)


@REGISTRY.register("exit_developer_mode", description_fn=lambda q: "Exiting Developer Mode")
def _handle_exit_developer_mode(query: Any = None) -> ToolResult:
    from tools.developer_tools import set_developer_mode
    return set_developer_mode(False)


@REGISTRY.register("developer_mode_status", description_fn=lambda q: "Checking Developer Mode status")
def _handle_developer_mode_status(query: Any = None) -> ToolResult:
    from tools.developer_tools import is_developer_mode
    active = is_developer_mode()
    spoken = f"Developer mode is currently {'on' if active else 'off'}."
    return ToolResult(True, f"Developer mode: {active}", spoken, data={"developer_mode": active})


@REGISTRY.register("get_active_window", description_fn=lambda q: "Detecting active window")
def _handle_get_active_window(query: Any = None) -> ToolResult:
    from tools.developer_tools import get_active_window
    return get_active_window()


@REGISTRY.register("get_current_file", description_fn=lambda q: "Identifying current file")
def _handle_get_current_file(query: Any = None) -> ToolResult:
    from tools.developer_tools import get_current_file
    return get_current_file()


@REGISTRY.register("get_current_workspace", description_fn=lambda q: "Checking current workspace")
def _handle_get_current_workspace(query: Any = None) -> ToolResult:
    from tools.developer_tools import get_current_workspace
    return get_current_workspace()


@REGISTRY.register("list_workspace_files", description_fn=lambda q: f"Listing files: {q or 'all'}")
def _handle_list_workspace_files(query: Any = None) -> ToolResult:
    from tools.developer_tools import list_workspace_files
    ext = str(query) if query else ""
    return list_workspace_files(ext)


@REGISTRY.register("search_workspace", description_fn=lambda q: f"Searching workspace for: {q}")
def _handle_search_workspace(query: Any = None) -> ToolResult:
    from tools.developer_tools import search_workspace
    return search_workspace(str(query or ""))


@REGISTRY.register("read_active_file", description_fn=lambda q: f"Reading file: {q or 'active'}")
def _handle_read_active_file(query: Any = None) -> ToolResult:
    from tools.developer_tools import read_active_file
    return read_active_file(str(query or ""))


@REGISTRY.register("analyze_code", description_fn=lambda q: f"Analyzing code: {q or 'active'}")
def _handle_analyze_code(query: Any = None) -> ToolResult:
    from tools.developer_tools import analyze_code
    return analyze_code(str(query or ""))


@REGISTRY.register("run_tests", description_fn=lambda q: f"Running unit tests: {q or 'all'}")
def _handle_run_tests(query: Any = None) -> ToolResult:
    from tools.developer_tools import run_tests
    return run_tests(str(query or ""))


@REGISTRY.register("propose_patch", description_fn=lambda q: "Proposing code patch")
def _handle_propose_patch(query: Any = None) -> ToolResult:
    from tools.developer_tools import propose_patch
    if isinstance(query, dict):
        return propose_patch(
            query.get("file", ""),
            query.get("old_code", ""),
            query.get("new_code", ""),
        )
    return ToolResult(False, "Missing patch parameters", "Could not propose patch without code details.")


@REGISTRY.register("capture_screen_context", description_fn=lambda q: "Capturing screen context")
def _handle_capture_screen_context(query: Any = None) -> ToolResult:
    from tools.developer_tools import capture_screen_context
    return capture_screen_context()


@REGISTRY.register("apply_patch", description_fn=lambda q: f"Applying code patch: {q or 'staged'}")
def _handle_apply_patch(query: Any = None) -> ToolResult:
    from tools.developer_tools import apply_patch
    return apply_patch(str(query or ""))


@REGISTRY.register("rollback_patch", description_fn=lambda q: f"Rolling back patch: {q or 'last'}")
def _handle_rollback_patch(query: Any = None) -> ToolResult:
    from tools.developer_tools import rollback_patch
    return rollback_patch(str(query or ""))


@REGISTRY.register("screen_analysis", description_fn=lambda q: f"Analyzing screen: {q or 'visual inspection'}")
def _handle_screen_analysis(query: Any = None) -> ToolResult:
    from vision.service import perform_screen_analysis
    clean_q = str(query or "").strip()
    return perform_screen_analysis(user_query=clean_q)


@REGISTRY.register("unknown", description_fn=lambda q: "Unknown command")

def _handle_unknown(query: Any) -> ToolResult:
    print("DeskBot does not know how to perform this command.")
    return ToolResult(False, "Unknown command", "DeskBot does not know how to perform this command.")


def get_action_description(intent: dict) -> str:
    """Get user-friendly string description of an intent."""
    action = intent.get("action", "unknown")
    query = intent.get("response") if "response" in intent else intent.get("query")
    if not query and "question" in intent:
        query = intent.get("question")
    return REGISTRY.describe(action, query)


def execute_intent(intent: dict) -> ToolResult:
    """Execute an intent returned by the AI brain and return ToolResult."""
    if not isinstance(intent, dict):
        print(f"Invalid intent format: expected dict, got {type(intent)}")
        return ToolResult(False, "Invalid intent format", "Invalid intent received.")

    action = intent.get("action")
    query = intent.get("response") if "response" in intent else intent.get("query")
    if not query and "question" in intent:
        query = intent.get("question")

    if not action:
        print("Intent missing 'action' field.")
        return ToolResult(False, "Missing action", "Command missing action.")

    return REGISTRY.execute(action, query)



def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python command_executor.py '<json intent>'")
        return 1

    raw_intent = " ".join(sys.argv[1:])

    try:
        intent = json.loads(raw_intent)
    except json.JSONDecodeError:
        try:
            intent = ast.literal_eval(raw_intent)
        except Exception as error:
            print(f"Invalid AI JSON: {error}", file=sys.stderr)
            return 1

    if not isinstance(intent, dict):
        print("AI response must be a JSON object.", file=sys.stderr)
        return 1

    success = execute_intent(intent)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())