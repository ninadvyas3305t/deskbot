"""Unit tests for Whisper anti-hallucination, repetition filtering, and AI brain API key handling."""

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from companion.speech_to_text import is_hallucination, transcribe
from companion.ai_brain import understand_intent


class TestSTTHallucinationFilter(unittest.TestCase):
    """Test Whisper anti-hallucination heuristic filter."""

    def test_repetition_loops_detected(self):
        """Autoregressive repetition loops must be detected and rejected."""
        loop1 = "I'm sorry, I'm sorry, I'm sorry, I'm sorry, I'm sorry"
        loop2 = "thank you, thank you, thank you, thank you"
        loop3 = "open YouTube open YouTube open YouTube"
        self.assertTrue(is_hallucination(loop1))
        self.assertTrue(is_hallucination(loop2))
        self.assertTrue(is_hallucination(loop3))

    def test_vocabulary_collapse_detected(self):
        """Token repetition with few distinct words must be rejected."""
        collapse = "sorry sorry sorry sorry"
        self.assertTrue(is_hallucination(collapse))

    def test_silence_hallucinations_detected(self):
        """Common Whisper training set artifacts on silent/low-energy frames must be rejected."""
        self.assertTrue(is_hallucination("I'm sorry."))
        self.assertTrue(is_hallucination("im sorry"))
        self.assertTrue(is_hallucination("Thank you for watching!"))
        self.assertTrue(is_hallucination("Subtitles by Amara.org"))
        self.assertTrue(is_hallucination("Subtitles by the Amara.org community"))
        self.assertTrue(is_hallucination("Please subscribe"))
        self.assertTrue(is_hallucination("[music]"))
        self.assertTrue(is_hallucination("(applause)"))
        self.assertTrue(is_hallucination(""))
        self.assertTrue(is_hallucination("   "))

    def test_filler_words_detected(self):
        """Single or pairs of noise filler words must be rejected as hallucinations."""
        self.assertTrue(is_hallucination("and"))
        self.assertTrue(is_hallucination("and,"))
        self.assertTrue(is_hallucination("and."))
        self.assertTrue(is_hallucination("so"))
        self.assertTrue(is_hallucination("the"))
        self.assertTrue(is_hallucination("um uh"))
        self.assertTrue(is_hallucination("YouTube, mute, mute."))
        self.assertTrue(is_hallucination("mute, mute"))

    def test_legitimate_commands_accepted(self):
        """Normal voice commands must NOT be classified as hallucinations."""
        valid_commands = [
            "Open YouTube",
            "Play Bohemian Rhapsody",
            "Delete notes.txt on my desktop",
            "What time is it?",
            "Take a screenshot",
            "Create a file named notes.txt on desktop",
            "Open main.py in VS Code",
            "Turn up the volume",
            "Mute sound",
            "yes",
            "no",
            "that's all",
        ]
        for cmd in valid_commands:
            self.assertFalse(is_hallucination(cmd), f"False positive on valid command: {cmd}")

    def test_transcribe_passes_anti_repetition_flags(self):
        """Verify transcribe passes repetition_penalty and no_repeat_ngram_size to Faster-Whisper."""
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "Open YouTube"
        mock_segment.compression_ratio = 1.0
        mock_segment.no_speech_prob = 0.05
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_model.transcribe.return_value = ([mock_segment], mock_info)

        dummy_path = Path("dummy.wav")
        transcript, lang = transcribe(dummy_path, model_name=mock_model)

        self.assertEqual(transcript, "Open YouTube")
        self.assertEqual(lang, "en")

        call_kwargs = mock_model.transcribe.call_args.kwargs
        self.assertEqual(call_kwargs.get("repetition_penalty"), 1.2)
        self.assertEqual(call_kwargs.get("no_repeat_ngram_size"), 3)
        self.assertEqual(call_kwargs.get("temperature"), 0)

    def test_transcribe_scrubs_hallucinations(self):
        """If model returns an autoregressive repetition loop, transcribe returns empty string."""
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "I'm sorry, I'm sorry, I'm sorry, I'm sorry"
        mock_segment.compression_ratio = 3.5
        mock_segment.no_speech_prob = 0.8
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_model.transcribe.return_value = ([mock_segment], mock_info)

        dummy_path = Path("dummy.wav")
        transcript, lang = transcribe(dummy_path, model_name=mock_model)

        self.assertEqual(transcript, "")
        self.assertEqual(lang, "en")


class TestAIBrainAPIKeyHandling(unittest.TestCase):
    """Test AI brain handling when NVIDIA_API_KEY is not set."""

    def test_missing_api_key_returns_graceful_response(self):
        """Unrecognized intent with missing NVIDIA_API_KEY should return a direct_answer informing the user."""
        with patch.dict(os.environ, {}, clear=True):
            if "NVIDIA_API_KEY" in os.environ:
                del os.environ["NVIDIA_API_KEY"]
            result = understand_intent("What is the meaning of quantum superposition?")
            self.assertIsNotNone(result)
            self.assertEqual(result.get("action"), "direct_answer")
            self.assertIn("NVIDIA API key is not set", result.get("response", ""))


if __name__ == "__main__":
    unittest.main()
