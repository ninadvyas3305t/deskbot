"""Bounded conversation context tracker for DeskBot multi-turn interactions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ConversationTurn:
    """Represents a single user-assistant interaction turn."""
    user_speech: str
    tool_name: str
    tool_query: Optional[str]
    tool_success: bool
    assistant_response: str
    timestamp: float = field(default_factory=time.time)

    def to_prompt_str(self) -> str:
        """Format turn concisely for LLM prompt context."""
        query_info = f" (query: '{self.tool_query}')" if self.tool_query else ""
        status = "Success" if self.tool_success else "Failed"
        return (
            f"User: \"{self.user_speech}\"\n"
            f"Assistant: executed {self.tool_name}{query_info} -> {status}. Response: \"{self.assistant_response}\""
        )


class ConversationContext:
    """Thread-safe bounded history of recent conversation turns."""

    def __init__(self, max_messages: int = 8, ttl_seconds: float = 90.0):
        self.max_messages = max_messages
        self.ttl_seconds = ttl_seconds
        self._turns: List[ConversationTurn] = []

    def add_turn(
        self,
        user_speech: str,
        tool_name: str,
        tool_query: Optional[str] = None,
        tool_success: bool = True,
        assistant_response: str = "",
    ) -> None:
        """Record an interaction turn and maintain bounds."""
        self._prune_expired()
        turn = ConversationTurn(
            user_speech=user_speech.strip(),
            tool_name=tool_name,
            tool_query=tool_query.strip() if tool_query else None,
            tool_success=tool_success,
            assistant_response=assistant_response.strip(),
        )
        self._turns.append(turn)

        if len(self._turns) > self.max_messages:
            self._turns = self._turns[-self.max_messages:]

    def _prune_expired(self) -> None:
        """Remove turns that are older than ttl_seconds."""
        now = time.time()
        self._turns = [t for t in self._turns if (now - t.timestamp) < self.ttl_seconds]

    def get_context_for_prompt(self) -> str:
        """Return formatted prompt context of recent interactions."""
        self._prune_expired()
        if not self._turns:
            return ""

        lines = ["Recent conversation context:"]
        for turn in self._turns:
            lines.append(turn.to_prompt_str())
        return "\n".join(lines)

    def get_last_turn(self) -> Optional[ConversationTurn]:
        """Get the most recent turn if available."""
        self._prune_expired()
        return self._turns[-1] if self._turns else None

    def clear(self) -> None:
        """Clear all conversation turns."""
        self._turns.clear()

    def __len__(self) -> int:
        self._prune_expired()
        return len(self._turns)
