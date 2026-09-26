"""Unit tests for DeskBot state machine and event logging."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

COMPANION_DIR = Path(__file__).resolve().parent.parent
if str(COMPANION_DIR) not in sys.path:
    sys.path.insert(0, str(COMPANION_DIR))

from assistant.state_machine import AssistantState, AssistantStateMachine


class TestAssistantStateMachine(unittest.TestCase):
    def test_initial_state(self):
        sm = AssistantStateMachine(wake_word_name="Hey Jarvis")
        self.assertEqual(sm.state, AssistantState.IDLE)

    def test_state_flow_and_logging(self):
        sm = AssistantStateMachine(wake_word_name="Hey Jarvis")
        out = io.StringIO()

        with redirect_stdout(out):
            sm.transition_to(AssistantState.IDLE)
            sm.on_wake(0.95)
            sm.on_speech_start()
            sm.on_speech_end()
            sm.transition_to(AssistantState.TRANSCRIBING)
            sm.on_transcript("Open YouTube")
            sm.transition_to(AssistantState.THINKING)
            sm.on_ai_action("open_website")
            sm.transition_to(AssistantState.EXECUTING, context="Opening YouTube")
            sm.transition_to(AssistantState.IDLE)

        output = out.getvalue()
        self.assertIn("[IDLE] Listening for Hey Jarvis...", output)
        self.assertIn("[WAKE] Hey Jarvis detected (score: 0.95)", output)
        self.assertIn("[LISTENING] Listening for command...", output)
        self.assertIn("[SPEECH] User speech detected", output)
        self.assertIn("[SPEECH] End of speech", output)
        self.assertIn("[STT] Transcribing...", output)
        self.assertIn('[STT] Recognized: "Open YouTube"', output)
        self.assertIn("[AI] Action: open_website", output)
        self.assertIn("[EXECUTING] Opening YouTube", output)

    def test_touch_and_follow_up_logging(self):
        sm = AssistantStateMachine(wake_word_name="Hey Jarvis")
        out = io.StringIO()

        with redirect_stdout(out):
            sm.on_touch()
            sm.on_follow_up("Is that all?")
            sm.on_confirmation("I found notes.txt. Do you want me to delete it?")

        output = out.getvalue()
        self.assertIn("[TOUCH] Touch sensor triggered", output)
        self.assertIn('[FOLLOW_UP] Asking "Is that all?"', output)
        self.assertIn('[CONFIRMATION] Asking "I found notes.txt. Do you want me to delete it?"', output)


    def test_error_recovery(self):
        sm = AssistantStateMachine(wake_word_name="Hey Jarvis")
        out = io.StringIO()

        with redirect_stdout(out):
            sm.on_wake(0.85)
            sm.handle_error_and_recover("Nemotron API failed")

        output = out.getvalue()
        self.assertIn("[ERROR] Nemotron API failed", output)
        self.assertIn("[IDLE] Listening for Hey Jarvis...", output)
        self.assertEqual(sm.state, AssistantState.IDLE)

    def test_state_broadcaster(self):
        sm = AssistantStateMachine(wake_word_name="Hey Jarvis")
        broadcasted = []
        sm.set_state_broadcaster(lambda st: broadcasted.append(st))

        sm.transition_to(AssistantState.LISTENING)
        sm.transition_to(AssistantState.TRANSCRIBING)
        sm.transition_to(AssistantState.THINKING)
        sm.transition_to(AssistantState.EXECUTING)
        sm.transition_to(AssistantState.IDLE)

        self.assertEqual(
            broadcasted,
            [
                AssistantState.LISTENING,
                AssistantState.TRANSCRIBING,
                AssistantState.THINKING,
                AssistantState.EXECUTING,
                AssistantState.IDLE,
            ],
        )

    def test_on_tool_and_on_response_logging(self):
        sm = AssistantStateMachine(wake_word_name="Hey Jarvis")
        out = io.StringIO()

        with redirect_stdout(out):
            sm.on_tool("volume_up", True)
            sm.on_tool("close_app", False, "App not running")
            sm.on_response("It's 10:30 AM.")

        output = out.getvalue()
        self.assertIn("[TOOL] volume_up", output)
        self.assertIn("[TOOL] Success", output)
        self.assertIn("[TOOL] close_app", output)
        self.assertIn("[TOOL] Failed: App not running", output)
        self.assertIn("[RESPONSE] It's 10:30 AM.", output)

    def test_speaking_state_and_logging(self):
        sm = AssistantStateMachine(wake_word_name="Hey Jarvis")
        out = io.StringIO()
        broadcasted = []
        sm.set_state_broadcaster(lambda st: broadcasted.append(st))

        with redirect_stdout(out):
            sm.on_speaking("Opening Spotify.")

        output = out.getvalue()
        self.assertEqual(sm.state, AssistantState.SPEAKING)
        self.assertIn("[SPEAKING] Opening Spotify.", output)
        self.assertEqual(broadcasted, [AssistantState.SPEAKING])


if __name__ == "__main__":
    unittest.main()

