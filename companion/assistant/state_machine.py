"""Explicit state machine and standardized logger for DeskBot."""

from __future__ import annotations

import enum
import sys
from typing import Callable, Optional


class AssistantState(str, enum.Enum):
    """Lifecycle states of the DeskBot voice assistant."""
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    EXECUTING = "EXECUTING"
    SPEAKING = "SPEAKING"
    FOLLOW_UP = "FOLLOW_UP"
    ERROR = "ERROR"


class AssistantStateMachine:
    """Manages state transitions, terminal output, and error containment for DeskBot."""

    def __init__(self, wake_word_name: str = "Hey Jarvis", debug: bool = False):
        self.state: AssistantState = AssistantState.IDLE
        self.wake_word_name = wake_word_name
        self.debug = debug
        self._on_transition_callback: Optional[Callable[[AssistantState, AssistantState], None]] = None
        self._broadcaster: Optional[Callable[[AssistantState], None]] = None

    @property
    def current_state(self) -> AssistantState:
        """Alias property for backwards compatibility and clarity."""
        return self.state

    def set_state_broadcaster(self, broadcaster: Callable[[AssistantState], None]) -> None:
        """Register a callback for hardware state sync (e.g. ESP32 OLED face)."""
        self._broadcaster = broadcaster

    def log(self, tag: str, message: str) -> None:
        """Standardized console logging format."""
        print(f"[{tag}] {message}", flush=True)

    def log_debug(self, message: str) -> None:
        if self.debug:
            print(f"[DEBUG] {message}", file=sys.stderr, flush=True)

    def transition_to(self, new_state: AssistantState, context: Optional[str] = None) -> None:
        """Transition to a new state, sync with hardware broadcaster, and emit standard output."""
        old_state = self.state
        self.state = new_state

        if new_state == AssistantState.IDLE:
            self.log("IDLE", f"Listening for {self.wake_word_name}...")
        elif new_state == AssistantState.LISTENING:
            self.log("LISTENING", "Listening for command...")
        elif new_state == AssistantState.TRANSCRIBING:
            self.log("STT", "Transcribing...")
        elif new_state == AssistantState.THINKING:
            self.log("THINKING", context or "Processing with AI / fast intent...")
        elif new_state == AssistantState.EXECUTING:
            self.log("EXECUTING", context or "Executing command...")
        elif new_state == AssistantState.SPEAKING:
            self.log("SPEAKING", context or "Speaking...")
        elif new_state == AssistantState.FOLLOW_UP:
            self.log("FOLLOW_UP", context or 'Asking "Is that all?"')
        elif new_state == AssistantState.ERROR:
            err_msg = context or "An unexpected error occurred."
            self.log("ERROR", err_msg)

        if self._broadcaster:
            try:
                self._broadcaster(new_state)
            except Exception as b_err:
                self.log_debug(f"State broadcaster error: {b_err}")

        if self._on_transition_callback:
            try:
                self._on_transition_callback(old_state, new_state)
            except Exception as cb_err:
                self.log_debug(f"Transition callback error: {cb_err}")

    def on_wake(self, confidence: float | None = None) -> None:
        """Handle wake-word detection event."""
        if confidence is not None:
            self.log("WAKE", f"{self.wake_word_name} detected (score: {confidence:.2f})")
        else:
            self.log("WAKE", f"{self.wake_word_name} detected")
        self.transition_to(AssistantState.LISTENING)

    def on_touch(self) -> None:
        """Handle manual touch sensor activation event."""
        self.log("TOUCH", "Touch sensor triggered")
        self.transition_to(AssistantState.LISTENING)

    def on_follow_up(self, prompt: str = "Is that all?") -> None:
        """Log follow-up prompt and transition to FOLLOW_UP state."""
        self.transition_to(AssistantState.FOLLOW_UP, context=f'Asking "{prompt}"')

    def on_confirmation(self, prompt: str) -> None:
        """Log confirmation prompt and transition to FOLLOW_UP state."""
        self.state = AssistantState.FOLLOW_UP
        self.log("CONFIRMATION", f'Asking "{prompt}"')
        if self._broadcaster:
            try:
                self._broadcaster(AssistantState.FOLLOW_UP)
            except Exception as b_err:
                self.log_debug(f"State broadcaster error: {b_err}")

    def on_speech_start(self) -> None:
        """Handle speech detection event."""
        self.log("SPEECH", "User speech detected")

    def on_speech_end(self) -> None:
        """Handle end-of-speech detection event."""
        self.log("SPEECH", "End of speech")

    def on_transcript(self, text: str) -> None:
        """Log speech-to-text result."""
        self.log("STT", f'Recognized: "{text}"')

    def on_ai_action(self, action: str) -> None:
        """Log AI routing decision."""
        self.log("AI", f"Action: {action}")

    def on_direct_answer(self, text: str) -> None:
        """Log direct answer response."""
        self.log("ANSWER", text)

    def on_tool(self, tool_name: str, success: bool, reason: str = "") -> None:
        """Log tool execution result."""
        self.log("TOOL", tool_name)

        if success:
            self.log("TOOL", "Success")
        else:
            msg = f"Failed: {reason}" if reason else "Failed"
            self.log("TOOL", msg)

    def on_response(self, text: str) -> None:
        """Log final response text."""
        self.log("RESPONSE", text)

    def on_speaking(self, text: str) -> None:
        """Log and transition to SPEAKING state with spoken text context."""
        self.transition_to(AssistantState.SPEAKING, context=text)

    def handle_error_and_recover(self, error_message: str) -> None:
        """Record an error, clean up, and return safely to IDLE."""
        self.transition_to(AssistantState.ERROR, context=error_message)
        self.transition_to(AssistantState.IDLE)

