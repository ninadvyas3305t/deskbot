"""Unit tests for DeskBot Windows TTS abstraction and factory."""

from __future__ import annotations

import unittest
from companion.tts.base import BaseTTSEngine
from companion.tts.factory import (
    MockTTSEngine,
    get_tts_engine,
    reset_tts_engine,
    set_tts_engine,
    speak,
    stop_speaking,
)
from companion.tts.windows_sapi import WindowsSAPITTSEngine


class TestTTSAbstraction(unittest.TestCase):
    """Test BaseTTSEngine, MockTTSEngine, and Factory behaviors."""

    def setUp(self):
        reset_tts_engine()

    def tearDown(self):
        reset_tts_engine()

    def test_mock_tts_engine_lifecycle(self):
        engine = MockTTSEngine()
        self.assertIsInstance(engine, BaseTTSEngine)
        self.assertEqual(engine.spoken_texts, [])
        self.assertFalse(engine.is_speaking())

        # Speak valid text
        res = engine.speak("Hello DeskBot")
        self.assertTrue(res)
        self.assertEqual(engine.spoken_texts, ["Hello DeskBot"])

        # Speak empty / whitespace text returns False
        self.assertFalse(engine.speak(""))
        self.assertFalse(engine.speak("   "))
        self.assertEqual(len(engine.spoken_texts), 1)

        # Stop
        engine.stop()
        self.assertFalse(engine.is_speaking())

        # Voices
        self.assertEqual(engine.get_voices(), ["MockVoice"])
        self.assertTrue(engine.set_voice("CustomVoice"))
        self.assertEqual(engine._active_voice, "CustomVoice")

    def test_factory_singleton_and_override(self):
        mock_engine = MockTTSEngine()
        set_tts_engine(mock_engine)

        retrieved = get_tts_engine()
        self.assertIs(retrieved, mock_engine)

        # Speak via module convenience function
        ok = speak("Opening Spotify")
        self.assertTrue(ok)
        self.assertEqual(mock_engine.spoken_texts, ["Opening Spotify"])

        # Stop via module convenience function
        stop_speaking()
        self.assertFalse(mock_engine.is_speaking())

    def test_windows_sapi_initialization_and_voices(self):
        """Test Windows SAPI engine on Windows environment."""
        engine = WindowsSAPITTSEngine(rate=1, volume=100)
        self.assertIsInstance(engine, BaseTTSEngine)

        voices = engine.get_voices()
        self.assertIsInstance(voices, list)
        # On Windows there should be at least 1 voice installed (David or Zira)
        self.assertGreaterEqual(len(voices), 1)

        # Voice selection
        if len(voices) > 0:
            self.assertTrue(engine.set_voice(0))

        # Safe rate and volume
        engine.set_rate(2)
        engine.set_volume(80)

        # Invalid speak input must not crash
        self.assertFalse(engine.speak(""))
        self.assertFalse(engine.speak("   "))

        # Stop when idle must not crash
        engine.stop()

    def test_windows_sapi_safe_execution(self):
        """Test that SAPI speak executes without error and can be interrupted."""
        engine = WindowsSAPITTSEngine(rate=2, volume=50)
        # Non-blocking speak
        res = engine.speak("Testing DeskBot TTS", block=False)
        self.assertTrue(res)

        # Immediately interrupt/stop
        engine.stop()
        self.assertFalse(engine.is_speaking())


if __name__ == "__main__":
    unittest.main()
