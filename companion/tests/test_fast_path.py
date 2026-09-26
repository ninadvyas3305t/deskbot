"""Test verification for fast-path intent matching and zero-delay execution."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import ai_brain
import command_executor


class TestFastPathLatency(unittest.TestCase):
    def test_fast_intent_match_time(self):
        intent = ai_brain.fast_intent_match("what time is it")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "current_time")
        res = command_executor.execute_intent(intent)
        self.assertTrue(res.success)
        self.assertIn("M", res.response_text)

    def test_fast_intent_match_date(self):
        intent = ai_brain.fast_intent_match("what is today's date")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "current_date")
        res = command_executor.execute_intent(intent)
        self.assertTrue(res.success)
        self.assertIn("202", res.response_text)

    def test_fast_intent_match_math(self):
        intent = ai_brain.fast_intent_match("what is 25 times 16")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "direct_answer")
        self.assertIn("400", intent["response"])

    def test_fast_intent_match_delete(self):
        intent = ai_brain.fast_intent_match("delete notes.txt on my Desktop")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "delete_file")
        self.assertEqual(intent["query"], "notes.txt on my Desktop")

    def test_fast_intent_match_open_app(self):
        intent = ai_brain.fast_intent_match("open notepad")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "open_app")
        self.assertEqual(intent["query"], "Notepad")

    def test_fast_intent_match_developer_mode(self):
        intent = ai_brain.fast_intent_match("enter developer mode")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "enter_developer_mode")

        intent_exit = ai_brain.fast_intent_match("exit developer mode")
        self.assertIsNotNone(intent_exit)
        self.assertEqual(intent_exit["action"], "exit_developer_mode")

    def test_fast_intent_match_developer_queries(self):
        intent_file = ai_brain.fast_intent_match("what file am i working on")
        self.assertIsNotNone(intent_file)
        self.assertEqual(intent_file["action"], "get_current_file")

        intent_win = ai_brain.fast_intent_match("what window is active")
        self.assertIsNotNone(intent_win)
        self.assertEqual(intent_win["action"], "get_active_window")

        intent_search = ai_brain.fast_intent_match("search workspace for evaluate_math")
        self.assertIsNotNone(intent_search)
        self.assertEqual(intent_search["action"], "search_workspace")
        self.assertEqual(intent_search["query"], "evaluate_math")

        intent_tests = ai_brain.fast_intent_match("run the unit tests")
        self.assertIsNotNone(intent_tests)
        self.assertEqual(intent_tests["action"], "run_tests")


if __name__ == "__main__":
    unittest.main()
