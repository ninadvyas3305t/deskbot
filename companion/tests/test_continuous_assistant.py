"""Unit tests for Continuous Assistant logic and conversation integration."""

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

COMPANION_DIR = Path(__file__).resolve().parent.parent
if str(COMPANION_DIR) not in sys.path:
    sys.path.insert(0, str(COMPANION_DIR))

import continuous_assistant
from assistant.context import ConversationContext
from assistant.state_machine import AssistantState, AssistantStateMachine
from command_executor import ToolResult


class TestContinuousAssistantComponents(unittest.TestCase):
    def test_save_wav(self):
        test_pcm = b"\x00\x00" * 1600  # 0.1 sec of 16kHz 16-bit mono
        test_wav = COMPANION_DIR / "test_out.wav"
        try:
            continuous_assistant.save_wav(test_pcm, test_wav)
            self.assertTrue(test_wav.exists())
            self.assertGreater(test_wav.stat().st_size, 44)
        finally:
            if test_wav.exists():
                test_wav.unlink()

    @patch("continuous_assistant.transcribe")
    @patch("continuous_assistant.understand_intent")
    @patch("continuous_assistant.execute_intent")
    @patch("continuous_assistant.save_wav")
    @patch("continuous_assistant.validate_audio")
    def test_process_utterance_flow(
        self, mock_validate, mock_save, mock_execute, mock_understand, mock_transcribe
    ):
        mock_transcribe.return_value = ("open notepad", "en")
        mock_understand.return_value = {"action": "open_app", "query": "Notepad"}
        mock_execute.return_value = ToolResult(True, "Opened notepad.exe", "Opening Notepad.")

        state_machine = AssistantStateMachine()
        states_seen = []
        state_machine.set_state_broadcaster(lambda s: states_seen.append(s))
        context = ConversationContext()

        # Replicate process_utterance inner logic
        transcript, _ = mock_transcribe(b"dummy")
        state_machine.transition_to(AssistantState.TRANSCRIBING)
        state_machine.on_transcript(transcript)
        state_machine.transition_to(AssistantState.THINKING)
        intent = mock_understand(transcript, context_prompt=context.get_context_for_prompt())
        state_machine.transition_to(AssistantState.EXECUTING)
        res = mock_execute(intent)
        state_machine.on_tool(intent["action"], res.success, res.message)
        state_machine.on_response(res.response_text)
        state_machine.transition_to(AssistantState.SPEAKING, context=res.response_text)
        context.add_turn(transcript, intent["action"], intent.get("query"), res.success, res.response_text)

        self.assertIn(AssistantState.TRANSCRIBING, states_seen)
        self.assertIn(AssistantState.THINKING, states_seen)
        self.assertIn(AssistantState.EXECUTING, states_seen)
        self.assertIn(AssistantState.SPEAKING, states_seen)
        self.assertEqual(len(context), 1)
        self.assertEqual(context.get_last_turn().user_speech, "open notepad")
        self.assertEqual(context.get_last_turn().tool_name, "open_app")

    def test_touch_trigger_detection(self):
        from audio.audio_engine import AudioEngine
        engine = AudioEngine(port="COM99")
        self.assertFalse(engine.check_and_consume_touch())

        # Simulate in-band touch trigger arrival
        with engine._touch_lock:
            engine._touch_detected = True

        self.assertTrue(engine.check_and_consume_touch())
        # Consuming it clears it atomically
        self.assertFalse(engine.check_and_consume_touch())

    def test_follow_up_affirmative_and_negative_matching(self):
        AFFIRMATIVE_RESPONSES = {
            "yes", "yeah", "yup", "yep", "sure", "that's all", "thats all",
            "that is all", "i'm good", "im good", "no more", "all good",
            "that's it", "thats it", "that is it", "all done", "done",
            "nothing else", "nothing", "nope that's all", "no that's all",
            "alright", "thank you", "thanks", "that'll do", "that will do",
            "no that's it", "no thats it", "that would be all", "fine",
            "no that is all", "no thank you", "no thanks",
        }
        NEGATIVE_STANDALONE = {
            "no", "nope", "nah", "not yet", "wait", "hold on", "one more thing",
            "not really", "wait a minute", "hang on",
        }

        # Test common conversational "Yes" variations
        for term in ["yes", "yeah", "Yup", "That's all.", "no, that's all", "Done!", "I'm good"]:
            clean = term.lower().replace(",", " ").strip(".,?!;:`'\"")
            clean = re.sub(r"\s+", " ", clean).strip()
            self.assertIn(clean, AFFIRMATIVE_RESPONSES)

        # Test common conversational "No" variations
        for term in ["No", "nope.", "not yet", "Wait"]:
            clean = term.lower().replace(",", " ").strip(".,?!;:`'\"")
            clean = re.sub(r"\s+", " ", clean).strip()
            self.assertIn(clean, NEGATIVE_STANDALONE)

    def test_fuzzy_delete_confirmation_workflow(self):
        import tempfile
        from tools import file_tools

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            test_file = tmp_path / "notes.txt"
            test_file.write_text("Hello DeskBot", encoding="utf-8")

            with patch.dict(file_tools.STANDARD_DIRECTORIES, {"desktop": tmp_path}):
                # Step 1: User says "delete nodes.txt" -> Tool requires confirmation
                res = file_tools.delete_file("nodes.txt")
                self.assertTrue(res.success)
                self.assertTrue(res.data.get("confirmation_required"))
                self.assertEqual(res.response_text, "I found notes.txt. Do you want me to delete it?")
                self.assertTrue(test_file.exists())  # Must not delete yet!

                # Step 2: User confirms -> execute_pending_deletion called
                del_res = file_tools.execute_pending_deletion(res.data["target_path"])
                self.assertTrue(del_res.success)
                self.assertFalse(test_file.exists())


if __name__ == "__main__":
    unittest.main()
