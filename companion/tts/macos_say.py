"""Native macOS TTS Engine Implementation for DeskBot using system 'say'."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
from typing import List, Optional

from .base import BaseTTSEngine

logger = logging.getLogger(__name__)


class MacOSSayTTSEngine(BaseTTSEngine):
    """Local, offline macOS TTS engine using the native /usr/bin/say utility."""

    def __init__(self, voice_name_or_index: Optional[str | int] = None, rate: int = 1, volume: int = 100):
        self._lock = threading.RLock()
        self._rate = rate  # Base rate -10 to 10 mapped to words per minute (e.g. 175-225 wpm)
        self._volume = max(0, min(100, volume))
        self._active_voice: Optional[str] = None
        self._current_proc: Optional[subprocess.Popen] = None
        self._say_path = shutil.which("say") or "/usr/bin/say"

        if voice_name_or_index is not None:
            self.set_voice(voice_name_or_index)

    def _rate_to_wpm(self, rate: int) -> int:
        """Convert rate (-10 to +10) to words per minute (100 to 300, default ~185)."""
        clamped = max(-10, min(10, rate))
        return 185 + (clamped * 10)

    def speak(self, text: str, block: bool = True) -> bool:
        """Speak plain text using macOS say command."""
        if not text or not text.strip():
            return False

        clean_text = text.strip()
        cmd = [self._say_path]
        if self._active_voice:
            cmd.extend(["-v", self._active_voice])

        wpm = self._rate_to_wpm(self._rate)
        cmd.extend(["-r", str(wpm)])
        cmd.append(clean_text)

        with self._lock:
            # Stop any currently speaking process
            self.stop()

            try:
                if block:
                    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True
                else:
                    self._current_proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return True
            except Exception as err:
                logger.error("macOS say TTS speak error: %s", err)
                return False

    def stop(self) -> None:
        """Interrupt and cancel any active speech playback."""
        with self._lock:
            if self._current_proc and self._current_proc.poll() is None:
                try:
                    self._current_proc.terminate()
                    self._current_proc.wait(timeout=0.5)
                except Exception:
                    try:
                        self._current_proc.kill()
                    except Exception:
                        pass
                finally:
                    self._current_proc = None

    def is_speaking(self) -> bool:
        """Check if say subprocess is currently outputting audio."""
        with self._lock:
            if self._current_proc is None:
                return False
            return self._current_proc.poll() is None

    def get_voices(self) -> List[str]:
        """Return list of installed macOS voices."""
        try:
            res = subprocess.run(
                [self._say_path, "-v", "?"],
                capture_output=True,
                text=True,
                check=True,
            )
            voices = []
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                # Line format: "Name       locale    # Description"
                match = re.match(r"^([A-Za-z0-9_\-\s]+?)\s+[a-z]{2}_[A-Z]{2}", line)
                if match:
                    voices.append(match.group(1).strip())
                else:
                    parts = line.split()
                    if parts:
                        voices.append(parts[0])
            return voices if voices else ["default"]
        except Exception as err:
            logger.debug("Failed to retrieve macOS voices: %s", err)
            return ["default"]

    def set_voice(self, voice_name_or_index: str | int) -> bool:
        """Select voice by name substring or integer index."""
        voices = self.get_voices()
        if not voices:
            return False

        if isinstance(voice_name_or_index, int):
            if 0 <= voice_name_or_index < len(voices):
                self._active_voice = voices[voice_name_or_index]
                return True
            return False

        target = str(voice_name_or_index).lower()
        for v in voices:
            if target in v.lower():
                self._active_voice = v
                return True

        self._active_voice = str(voice_name_or_index)
        return True

    def set_rate(self, rate: int) -> None:
        """Set speech rate between -10 and +10."""
        self._rate = max(-10, min(10, rate))

    def set_volume(self, volume: int) -> None:
        """Set volume between 0 and 100."""
        self._volume = max(0, min(100, volume))
