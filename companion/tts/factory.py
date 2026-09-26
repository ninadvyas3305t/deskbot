"""TTS Factory and convenience module functions for DeskBot."""

from __future__ import annotations

import logging
from typing import List, Optional

import sys

from .base import BaseTTSEngine
from .macos_say import MacOSSayTTSEngine
from .windows_sapi import WindowsSAPITTSEngine

logger = logging.getLogger(__name__)


class MockTTSEngine(BaseTTSEngine):
    """Test engine that captures speech in memory without emitting physical audio."""

    def __init__(self):
        self.spoken_texts: List[str] = []
        self._is_speaking: bool = False
        self._rate: int = 1
        self._volume: int = 100
        self._active_voice: str = "MockVoice"

    def speak(self, text: str, block: bool = True) -> bool:
        if not text or not text.strip():
            return False
        self.spoken_texts.append(text.strip())
        return True

    def stop(self) -> None:
        self._is_speaking = False

    def is_speaking(self) -> bool:
        return self._is_speaking

    def get_voices(self) -> List[str]:
        return ["MockVoice"]

    def set_voice(self, voice_name_or_index: str | int) -> bool:
        self._active_voice = str(voice_name_or_index)
        return True

    def set_rate(self, rate: int) -> None:
        self._rate = rate

    def set_volume(self, volume: int) -> None:
        self._volume = volume


_GLOBAL_TTS_ENGINE: Optional[BaseTTSEngine] = None


def get_tts_engine(engine_type: Optional[str] = None, voice: Optional[str] = None, rate: int = 1, volume: int = 100) -> BaseTTSEngine:
    """Retrieve or initialize the singleton TTS engine."""
    global _GLOBAL_TTS_ENGINE

    if _GLOBAL_TTS_ENGINE is not None:
        return _GLOBAL_TTS_ENGINE

    if engine_type == "mock":
        _GLOBAL_TTS_ENGINE = MockTTSEngine()
        return _GLOBAL_TTS_ENGINE

    if engine_type == "say" or (engine_type is None and sys.platform == "darwin"):
        try:
            _GLOBAL_TTS_ENGINE = MacOSSayTTSEngine(voice_name_or_index=voice, rate=rate, volume=volume)
            return _GLOBAL_TTS_ENGINE
        except Exception as err:
            logger.warning("Could not initialize macOS Say TTS engine: %s", err)

    try:
        if sys.platform == "win32" or engine_type == "sapi5":
            _GLOBAL_TTS_ENGINE = WindowsSAPITTSEngine(voice_name_or_index=voice, rate=rate, volume=volume)
        elif sys.platform == "darwin":
            _GLOBAL_TTS_ENGINE = MacOSSayTTSEngine(voice_name_or_index=voice, rate=rate, volume=volume)
        else:
            _GLOBAL_TTS_ENGINE = MockTTSEngine()
    except Exception as err:
        logger.warning("Could not initialize native TTS engine, falling back to MockTTSEngine: %s", err)
        _GLOBAL_TTS_ENGINE = MockTTSEngine()

    return _GLOBAL_TTS_ENGINE


def set_tts_engine(engine: BaseTTSEngine) -> None:
    """Override global TTS engine (useful for unit tests or switching engines)."""
    global _GLOBAL_TTS_ENGINE
    _GLOBAL_TTS_ENGINE = engine


def reset_tts_engine() -> None:
    """Reset the global TTS engine singleton."""
    global _GLOBAL_TTS_ENGINE
    if _GLOBAL_TTS_ENGINE:
        try:
            _GLOBAL_TTS_ENGINE.stop()
        except Exception:
            pass
    _GLOBAL_TTS_ENGINE = None


def speak(text: str, block: bool = True) -> bool:
    """Convenience module function to speak text using the active Windows TTS engine."""
    engine = get_tts_engine()
    return engine.speak(text, block=block)


def stop_speaking() -> None:
    """Convenience module function to interrupt any active speech."""
    if _GLOBAL_TTS_ENGINE:
        _GLOBAL_TTS_ENGINE.stop()
