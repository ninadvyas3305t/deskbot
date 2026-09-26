"""DeskBot Text-to-Speech (TTS) Package."""

from .base import BaseTTSEngine
from .factory import (
    MockTTSEngine,
    get_tts_engine,
    reset_tts_engine,
    set_tts_engine,
    speak,
    stop_speaking,
)
from .windows_sapi import WindowsSAPITTSEngine

__all__ = [
    "BaseTTSEngine",
    "WindowsSAPITTSEngine",
    "MockTTSEngine",
    "get_tts_engine",
    "set_tts_engine",
    "reset_tts_engine",
    "speak",
    "stop_speaking",
]
