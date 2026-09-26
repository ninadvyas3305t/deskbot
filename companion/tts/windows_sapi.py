"""Native Windows SAPI5 TTS Engine Implementation for DeskBot."""

from __future__ import annotations

import logging
import threading
from typing import List, Optional

from .base import BaseTTSEngine

logger = logging.getLogger(__name__)

# SAPI SpeechVoiceSpeakFlags constants
SVSF_DEFAULT = 0
SVSF_ASYNC = 1
SVSF_PURGE_BEFORE_SPEAK = 2


class WindowsSAPITTSEngine(BaseTTSEngine):
    """Local, offline Windows TTS engine using native Windows SAPI.SpVoice.

    Outputs audio directly through the default Windows audio output device.
    """

    def __init__(self, voice_name_or_index: Optional[str | int] = None, rate: int = 1, volume: int = 100):
        self._lock = threading.Lock()
        self._voice = None
        self._is_initialized = False
        self._rate = rate
        self._volume = max(0, min(100, volume))
        self._preferred_voice = voice_name_or_index
        self._init_voice()

    def _init_voice(self) -> bool:
        """Initialize COM and SAPI SpVoice instance."""
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            self._voice = win32com.client.Dispatch("SAPI.SpVoice")
            self._voice.Rate = self._rate
            self._voice.Volume = self._volume

            if self._preferred_voice is not None:
                self.set_voice(self._preferred_voice)

            self._is_initialized = True
            logger.info("Windows SAPI5 TTS Engine initialized successfully.")
            return True
        except Exception as err:
            logger.error("Failed to initialize Windows SAPI.SpVoice: %s", err)
            self._voice = None
            self._is_initialized = False
            return False

    def speak(self, text: str, block: bool = True) -> bool:
        """Speak plain text through default Windows audio output device."""
        if not text or not text.strip():
            return False

        with self._lock:
            if not self._is_initialized or self._voice is None:
                if not self._init_voice():
                    logger.warning("TTS speak called but engine failed to initialize.")
                    return False

            clean_text = text.strip()
            flags = SVSF_DEFAULT if block else SVSF_ASYNC

            try:
                import pythoncom
                pythoncom.CoInitialize()
                # Purge any previous audio before speaking to ensure immediate response
                res = self._voice.Speak(clean_text, flags)
                return True
            except Exception as err:
                logger.error("TTS speak error: %s", err)
                return False

    def stop(self) -> None:
        """Interrupt and cancel any active speech playback."""
        with self._lock:
            if self._voice is None:
                return
            try:
                import pythoncom
                pythoncom.CoInitialize()
                # Flag 2 (SVSFPurgeBeforeSpeak) with empty text cancels all active output
                self._voice.Speak("", SVSF_PURGE_BEFORE_SPEAK)
            except Exception as err:
                logger.debug("TTS stop error: %s", err)

    def is_speaking(self) -> bool:
        """Check if SAPI.SpVoice is currently rendering audio."""
        if self._voice is None:
            return False
        try:
            # RunningState: 1 = Done/Idle, 2 = Speaking
            return getattr(self._voice.Status, "RunningState", 1) == 2
        except Exception:
            return False

    def get_voices(self) -> List[str]:
        """Return list of installed SAPI voice descriptions."""
        if self._voice is None:
            return []
        try:
            voices = self._voice.GetVoices()
            return [voices.Item(i).GetDescription() for i in range(voices.Count)]
        except Exception as err:
            logger.debug("Failed to retrieve voices: %s", err)
            return []

    def set_voice(self, voice_name_or_index: str | int) -> bool:
        """Select voice by substring name (e.g. 'Zira', 'David') or integer index."""
        if self._voice is None:
            return False
        try:
            voices = self._voice.GetVoices()
            if isinstance(voice_name_or_index, int):
                if 0 <= voice_name_or_index < voices.Count:
                    self._voice.Voice = voices.Item(voice_name_or_index)
                    return True
                return False

            target = str(voice_name_or_index).lower()
            for i in range(voices.Count):
                desc = voices.Item(i).GetDescription().lower()
                if target in desc:
                    self._voice.Voice = voices.Item(i)
                    return True
            return False
        except Exception as err:
            logger.debug("Failed to set voice '%s': %s", voice_name_or_index, err)
            return False

    def set_rate(self, rate: int) -> None:
        """Set speech rate between -10 (slowest) and +10 (fastest). Default is 1."""
        self._rate = max(-10, min(10, rate))
        if self._voice:
            try:
                self._voice.Rate = self._rate
            except Exception as err:
                logger.debug("Failed to set rate: %s", err)

    def set_volume(self, volume: int) -> None:
        """Set volume between 0 and 100."""
        self._volume = max(0, min(100, volume))
        if self._voice:
            try:
                self._voice.Volume = self._volume
            except Exception as err:
                logger.debug("Failed to set volume: %s", err)
