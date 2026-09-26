"""Abstract Base Class for DeskBot Text-To-Speech (TTS) Engines."""

from __future__ import annotations

import abc
from typing import List, Optional


class BaseTTSEngine(abc.ABC):
    """Abstract interface for local and modular TTS engines."""

    @abc.abstractmethod
    def speak(self, text: str, block: bool = True) -> bool:
        """Speak the given text.

        Args:
            text: The plain text to speak.
            block: If True, waits until speech completes. If False, returns immediately.

        Returns:
            bool: True if speech was initiated or completed successfully, False otherwise.
        """
        pass

    @abc.abstractmethod
    def stop(self) -> None:
        """Interrupt and cancel any currently active speech immediately."""
        pass

    @abc.abstractmethod
    def is_speaking(self) -> bool:
        """Check whether the TTS engine is currently outputting audio."""
        pass

    @abc.abstractmethod
    def get_voices(self) -> List[str]:
        """Return a list of available voice names."""
        pass

    @abc.abstractmethod
    def set_voice(self, voice_name_or_index: str | int) -> bool:
        """Select active voice by name or index."""
        pass

    @abc.abstractmethod
    def set_rate(self, rate: int) -> None:
        """Set speech rate (speed)."""
        pass

    @abc.abstractmethod
    def set_volume(self, volume: int) -> None:
        """Set speech volume (0 to 100)."""
        pass
