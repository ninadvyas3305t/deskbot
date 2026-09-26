"""Unit tests for DeskBot conversation context tracker."""

import time
import unittest
from pathlib import Path
import sys

COMPANION_DIR = Path(__file__).resolve().parent.parent
if str(COMPANION_DIR) not in sys.path:
    sys.path.insert(0, str(COMPANION_DIR))

from assistant.context import ConversationContext, ConversationTurn


class TestConversationContext(unittest.TestCase):
    def test_add_and_retrieve_turn(self):
        ctx = ConversationContext(max_messages=4, ttl_seconds=10.0)
        ctx.add_turn(
            user_speech="Open Spotify",
            tool_name="spotify_open",
            tool_query=None,
            tool_success=True,
            assistant_response="Opening Spotify",
        )
        self.assertEqual(len(ctx), 1)
        last = ctx.get_last_turn()
        self.assertIsNotNone(last)
        self.assertEqual(last.user_speech, "Open Spotify")
        self.assertEqual(last.tool_name, "spotify_open")
        self.assertTrue(last.tool_success)

    def test_prompt_formatting(self):
        ctx = ConversationContext(max_messages=4, ttl_seconds=10.0)
        ctx.add_turn(
            user_speech="Play Starboy on Spotify",
            tool_name="spotify_play",
            tool_query="Starboy",
            tool_success=True,
            assistant_response="Playing Starboy on Spotify",
        )
        prompt_str = ctx.get_context_for_prompt()
        self.assertIn("Recent conversation context:", prompt_str)
        self.assertIn('User: "Play Starboy on Spotify"', prompt_str)
        self.assertIn("Assistant: executed spotify_play (query: 'Starboy') -> Success", prompt_str)

    def test_max_messages_pruning(self):
        ctx = ConversationContext(max_messages=2, ttl_seconds=10.0)
        ctx.add_turn("Turn 1", "tool_1")
        ctx.add_turn("Turn 2", "tool_2")
        ctx.add_turn("Turn 3", "tool_3")

        self.assertEqual(len(ctx), 2)
        turns = ctx._turns
        self.assertEqual(turns[0].user_speech, "Turn 2")
        self.assertEqual(turns[1].user_speech, "Turn 3")

    def test_ttl_expiration(self):
        ctx = ConversationContext(max_messages=5, ttl_seconds=0.1)
        ctx.add_turn("Old turn", "tool_old")
        self.assertEqual(len(ctx), 1)
        time.sleep(0.15)
        self.assertEqual(len(ctx), 0)
        self.assertEqual(ctx.get_context_for_prompt(), "")

    def test_clear_context(self):
        ctx = ConversationContext(max_messages=5, ttl_seconds=10.0)
        ctx.add_turn("Turn 1", "tool_1")
        self.assertEqual(len(ctx), 1)
        ctx.clear()
        self.assertEqual(len(ctx), 0)


if __name__ == "__main__":
    unittest.main()
