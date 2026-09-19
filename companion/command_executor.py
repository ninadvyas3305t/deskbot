"""Execute structured DeskBot AI intents on Windows."""

from __future__ import annotations

import json
import subprocess
import sys
import webbrowser
from urllib.parse import quote_plus


def open_youtube() -> bool:
    """Open YouTube."""
    print("Action: Opening YouTube")
    webbrowser.open("https://www.youtube.com")
    return True


def search_youtube(query: str) -> bool:
    """Search YouTube for a query."""
    query = query.strip()

    if not query:
        return open_youtube()

    print(f"Action: Searching YouTube for: {query}")

    url = (
        "https://www.youtube.com/results?search_query="
        + quote_plus(query)
    )

    webbrowser.open(url)
    return True


def play_youtube(query: str | None) -> bool:
    """Handle a YouTube play request."""

    if not query:
        print("Action: Opening YouTube for music")
        return open_youtube()

    print(f"Action: Playing/searching YouTube for: {query}")

    url = (
        "https://www.youtube.com/results?search_query="
        + quote_plus(query)
    )

    webbrowser.open(url)
    return True


def open_spotify() -> bool:
    """Open Spotify."""
    print("Action: Opening Spotify")

    subprocess.Popen(
        ["cmd", "/c", "start", "", "spotify:"],
        shell=False,
    )

    return True


def launch_windows_app(app_name: str) -> bool:
    """Launch a Windows application using app names or PATH executables."""

    app_name = app_name.strip()

    if not app_name:
        print("No application name was provided.")
        return False

    print(f"Action: Launching Windows app: {app_name}")

    # Friendly-name aliases for common applications.
    aliases = {
        "visual studio code": "code",
        "vs code": "code",
        "vscode": "code",
        "google chrome": "chrome",
        "chrome browser": "chrome",
    }

    lookup_name = aliases.get(
        app_name.lower(),
        app_name,
    )

    # First try the application directly through Windows.
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f'Start-Process "{lookup_name}"',
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print(f"Successfully launched: {app_name}")
        return True

    # If that fails, look for an executable on PATH.
    try:
        result = subprocess.run(
            ["where.exe", lookup_name],
            capture_output=True,
            text=True,
        )

        executable = result.stdout.strip().splitlines()

        if executable:
            subprocess.Popen(executable[0])
            print(f"Successfully launched: {app_name}")
            return True

    except OSError:
        pass

    print(f"Could not find installed app: {app_name}")
    return False

def open_google() -> bool:
    """Open Google."""
    print("Action: Opening Google")
    webbrowser.open("https://www.google.com")
    return True


def execute_intent(intent: dict) -> bool:
    """Execute an intent returned by the AI brain."""

    action = intent.get("action")
    query = intent.get("query")

    print(f"AI action: {action}")
    print(f"AI query: {query}")

    if action == "open_app":
        return launch_windows_app(str(query or ""))

    elif action == "open_website":
        website = str(query or "").lower()

        if website in {"youtube", "yt"}:
            return open_youtube()

        if website == "google":
            return open_google()

    elif action == "youtube_search":
        return search_youtube(str(query or ""))

    elif action == "youtube_play":
        return play_youtube(
            str(query) if query else None
        )

    elif action == "spotify_open":
        return open_spotify()

    elif action == "unknown":
        print("DeskBot does not know how to perform this command.")
        return False

    print(f"Unsupported AI action: {action}")
    return False


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python command_executor.py '<json intent>'")
        return 1

    raw_intent = " ".join(sys.argv[1:])

    try:
        intent = json.loads(raw_intent)
    except json.JSONDecodeError as error:
        print(f"Invalid AI JSON: {error}", file=sys.stderr)
        return 1

    if not isinstance(intent, dict):
        print("AI response must be a JSON object.", file=sys.stderr)
        return 1

    success = execute_intent(intent)

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())