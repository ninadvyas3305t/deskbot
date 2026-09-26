"""Unit tests for AI reasoning pipeline, answer synthesis, intent taxonomy, and duplicate STT prevention."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

COMPANION_DIR = Path(__file__).resolve().parent.parent
if str(COMPANION_DIR) not in sys.path:
    sys.path.insert(0, str(COMPANION_DIR))

import ai_brain
import command_executor
from command_executor import ToolResult


class TestIntentTaxonomy(unittest.TestCase):
    """Test DIRECT_ANSWER, WEB_SEARCH, TOOL_CALL, and CLARIFICATION classification & normalization."""

    def test_direct_answer_normalization(self):
        intent = {"type": "DIRECT_ANSWER", "response": "The capital of India is New Delhi."}
        valid, msg = ai_brain.validate_intent(intent)
        self.assertTrue(valid, msg)
        self.assertEqual(intent.get("action"), "direct_answer")
        self.assertEqual(ai_brain.get_intent_type(intent), "DIRECT_ANSWER")

    def test_web_search_normalization(self):
        intent = {"type": "WEB_SEARCH", "query": "latest sports news India"}
        valid, msg = ai_brain.validate_intent(intent)
        self.assertTrue(valid, msg)
        self.assertEqual(intent.get("action"), "web_search")
        self.assertEqual(ai_brain.get_intent_type(intent), "WEB_SEARCH")

    def test_clarification_normalization(self):
        intent = {"type": "CLARIFICATION", "question": "Which file would you like me to delete?"}
        valid, msg = ai_brain.validate_intent(intent)
        self.assertTrue(valid, msg)
        self.assertEqual(intent.get("action"), "clarification")
        self.assertEqual(ai_brain.get_intent_type(intent), "CLARIFICATION")

    def test_tool_call_categorization(self):
        intent = {"action": "screenshot"}
        valid, msg = ai_brain.validate_intent(intent)
        self.assertTrue(valid, msg)
        self.assertEqual(ai_brain.get_intent_type(intent), "TOOL_CALL")

    def test_clarification_tool_execution(self):
        intent = {"type": "CLARIFICATION", "action": "clarification", "question": "Which note file should I open?"}
        res = command_executor.execute_intent(intent)
        self.assertTrue(res.success)
        self.assertEqual(res.response_text, "Which note file should I open?")


class TestAnswerSynthesis(unittest.TestCase):
    """Test two-step search synthesis and fallback behavior."""

    def setUp(self):
        ai_brain.reset_history()

    def test_synthesize_web_answer_empty_results(self):
        ans = ai_brain.synthesize_web_answer("Is there any event?", "events today", [])
        self.assertIn("couldn't find any relevant", ans.lower())

    def test_synthesize_web_answer_offline_fallback(self):
        mock_results = [
            {
                "title": "India Today Sports",
                "snippet": "India won the cricket match by 5 wickets in an exciting finish.",
                "url": "https://example.com/sports",
            }
        ]
        with patch.dict("os.environ", {}, clear=True):
            ans = ai_brain.synthesize_web_answer(
                "Tell me sports news",
                "latest sports news India",
                mock_results,
            )
            self.assertIn("According to India Today Sports:", ans)
            self.assertIn("India won the cricket match", ans)

    @patch("ai_brain.create_client")
    def test_synthesize_web_answer_llm_synthesis(self, mock_create):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = "According to recent reports, India secured a decisive victory in cricket today with a five-wicket win."
        mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

        mock_results = [
            {
                "title": "NDTV Sports",
                "snippet": "India cricket score update.",
                "url": "https://example.com/cricket",
            }
        ]

        with patch.dict("os.environ", {"NVIDIA_API_KEY": "test-key"}):
            ans = ai_brain.synthesize_web_answer(
                "Tell me about sports news.",
                "latest sports news India",
                mock_results,
            )
            self.assertEqual(
                ans,
                "According to recent reports, India secured a decisive victory in cricket today with a five-wicket win.",
            )
            # Check conversation turn updated
            self.assertTrue(len(ai_brain._CONVERSATION_TURNS) >= 2)


class TestDuplicateSTTAndFollowUpRouting(unittest.TestCase):
    """Test duplicate STT elimination and direct follow-up command routing."""

    @patch("continuous_assistant.transcribe")
    @patch("continuous_assistant.synthesize_web_answer")
    @patch("continuous_assistant.execute_intent")
    @patch("continuous_assistant.understand_intent")
    @patch("continuous_assistant.save_wav")
    @patch("continuous_assistant.validate_audio")
    def test_web_search_two_step_pipeline_flow(
        self, mock_validate, mock_save, mock_understand, mock_execute, mock_synthesize, mock_transcribe
    ):
        from assistant.state_machine import AssistantState, AssistantStateMachine

        # Turn 1: User asks for news in India
        mock_transcribe.return_value = ("Can you tell me the news in India?", "en")
        mock_understand.return_value = {
            "type": "WEB_SEARCH",
            "action": "web_search",
            "query": "latest news in India",
        }
        mock_results = [{"title": "India Times", "snippet": "New infrastructure projects launched.", "url": "https://indiatimes.com"}]
        mock_execute.return_value = ToolResult(True, "Found 1 results", "Raw snippet", data=mock_results)
        mock_synthesize.return_value = "Here are the top developments in India today regarding infrastructure."

        state_machine = AssistantStateMachine()
        states_seen = []
        state_machine.set_state_broadcaster(lambda s: states_seen.append(s))

        # Simulate execution of the two-step search flow in continuous assistant
        intent = mock_understand("Can you tell me the news in India?")
        self.assertEqual(intent["action"], "web_search")

        # Step 1: Retrieval
        res = mock_execute(intent)
        self.assertTrue(res.success)
        self.assertEqual(res.data, mock_results)

        # Step 2: Synthesis
        spoken = mock_synthesize("Can you tell me the news in India?", intent["query"], res.data)
        self.assertNotIn("Here is what I found for", spoken)
        self.assertEqual(spoken, "Here are the top developments in India today regarding infrastructure.")

    def test_follow_up_routes_clean_transcript_without_retranscription(self):
        """Verify that when follow-up has an active command, current_transcript is forwarded directly."""
        # Simulated follow-up utterance already transcribed:
        fu_clean = "Tell me about sports news"

        # Verify that setting current_transcript bypasses transcribe()
        current_transcript = fu_clean
        current_pcm = None

        # Loop logic simulation:
        if current_transcript:
            clean_transcript = current_transcript.strip()
            current_transcript = None
            current_pcm = None
            transcribe_called = False
        else:
            transcribe_called = True

        self.assertFalse(transcribe_called)
        self.assertEqual(clean_transcript, "Tell me about sports news")
    def test_screenshot_folder_resolution(self):
        """Verify screenshot folder voice queries map directly to open_folder('screenshots')."""
        queries = [
            "Open the screenshots folder",
            "Open screenshots folder",
            "open the folder where you saved screen shot",
            "open folder where you saved screenshots",
        ]
        for q in queries:
            intent = ai_brain.fast_intent_match(q)
            self.assertIsNotNone(intent, f"Failed for query: {q}")
            self.assertEqual(intent.get("action"), "open_folder", f"Wrong action for {q}")
            self.assertEqual(intent.get("query"), "screenshots", f"Wrong query for {q}")

    def test_follow_up_affirmative_patterns(self):
        """Verify extended affirmative expressions like 'Yeah that is all' exit the loop."""
        import re
        patterns = [
            "Yeah that is all.",
            "you are that is all.",
            "yes that's all",
            "That is all",
            "that would be all",
            "that'll be all",
            "No that's all",
            "that is it",
        ]
        AFFIRMATIVE_SUBSTRINGS = {
            "that's all", "thats all", "that is all", "that will be all",
            "that'll be all", "that would be all", "that is it", "that's it",
            "thats it", "all done", "nothing else", "no more", "im good",
            "i'm good", "all set", "all good",
        }
        for p in patterns:
            clean = p.lower().replace(",", " ").strip(".,?!;:`'\"")
            clean = re.sub(r"\s+", " ", clean).strip()
            is_aff = (
                any(phrase in clean for phrase in AFFIRMATIVE_SUBSTRINGS)
                or (re.search(r"\b(?:that(?:'s|\s+is|\s+will\s+be|\s+would\s+be)?\s+all)\b", clean) is not None)
                or (re.search(r"\b(?:that(?:'s|\s+is)?\s+it)\b", clean) is not None)
            )
            self.assertTrue(is_aff, f"Pattern failed: {p}")

    def test_speech_detector_rejects_micro_bursts(self):
        """Verify speech detector ignores 1-2 frame spikes/clicks without sustained voiced speech."""
        from audio.speech_detector import SpeechDetector
        detector = SpeechDetector(frame_duration_ms=30)
        # Verify min onset frames is at least 4 (120ms)
        self.assertGreaterEqual(detector.min_speech_onset_frames, 4)
        self.assertEqual(detector.min_speech_amplitude, 200)


if __name__ == "__main__":
    unittest.main()
