"""Unit tests for new PC control tools, web search, info tools, and ToolResult."""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

COMPANION_DIR = Path(__file__).resolve().parent.parent
if str(COMPANION_DIR) not in sys.path:
    sys.path.insert(0, str(COMPANION_DIR))

import command_executor
from command_executor import ToolResult


class TestToolResult(unittest.TestCase):
    def test_tool_result_truth_value(self):
        res_ok = ToolResult(True, "OK", "Completed")
        res_fail = ToolResult(False, "Err", "Failed")

        self.assertTrue(bool(res_ok))
        self.assertFalse(bool(res_fail))
        self.assertEqual(res_ok.message, "OK")
        self.assertEqual(res_ok.response_text, "Completed")


class TestNewTools(unittest.TestCase):
    def test_registered_new_actions(self):
        new_actions = [
            "volume_up",
            "volume_down",
            "mute",
            "unmute",
            "screenshot",
            "close_app",
            "open_folder",
            "open_project_in_vscode",
            "web_search",
            "current_time",
            "current_date",
            "system_info",
            "weather",
        ]
        for act in new_actions:
            self.assertTrue(command_executor.REGISTRY.has_action(act), f"Missing action: {act}")

    @patch("ctypes.windll.user32.keybd_event")
    def test_volume_actions(self, mock_keybd):
        for act in ["volume_up", "volume_down", "mute", "unmute"]:
            res = command_executor.execute_intent({"action": act})
            self.assertTrue(res.success)
            self.assertTrue(bool(res))

    @patch("PIL.ImageGrab.grab")
    def test_screenshot_action(self, mock_grab):
        mock_img = MagicMock()
        mock_grab.return_value = mock_img

        res = command_executor.execute_intent({"action": "screenshot"})
        self.assertTrue(res.success)
        mock_img.save.assert_called()

    @patch("subprocess.run")
    def test_close_app_allowed(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        res = command_executor.execute_intent({"action": "close_app", "query": "Notepad"})
        self.assertTrue(res.success)
        self.assertIn("Notepad", res.response_text)

    def test_close_app_prohibited(self):
        res = command_executor.execute_intent({"action": "close_app", "query": "svchost.exe"})
        self.assertFalse(res.success)
        self.assertIn("prohibited", res.message.lower())

    @patch("subprocess.Popen")
    def test_open_folder(self, mock_popen):
        res = command_executor.execute_intent({"action": "open_folder", "query": "downloads"})
        self.assertTrue(res.success)
        mock_popen.assert_called()

    @patch("subprocess.Popen")
    def test_open_project_in_vscode(self, mock_popen):
        res = command_executor.execute_intent({"action": "open_project_in_vscode"})
        self.assertTrue(res.success)
        mock_popen.assert_called()

    @patch("tools.web_search.search_web")
    def test_web_search(self, mock_search):
        mock_search.return_value = [
            {"title": "Test Result", "url": "https://example.com", "snippet": "A test snippet."}
        ]
        res = command_executor.execute_intent({"action": "web_search", "query": "python"})
        self.assertTrue(res.success)
        self.assertIn("A test snippet.", res.response_text)

    @patch("tools.info_tools.get_current_time")
    def test_current_time(self, mock_time):
        mock_time.return_value = "02:30 PM"
        res = command_executor.execute_intent({"action": "current_time"})
        self.assertTrue(res.success)
        self.assertIn("02:30 PM", res.response_text)

    @patch("tools.info_tools.get_current_date")
    def test_current_date(self, mock_date):
        mock_date.return_value = "Thursday, September 24, 2026"
        res = command_executor.execute_intent({"action": "current_date"})
        self.assertTrue(res.success)
        self.assertIn("Thursday, September 24, 2026", res.response_text)

    @patch("tools.info_tools.get_system_info")
    def test_system_info(self, mock_info):
        mock_info.return_value = {
            "cpu_percent": 12.5,
            "ram_percent": 45.0,
            "battery_percent": 85,
        }
        res = command_executor.execute_intent({"action": "system_info"})
        self.assertTrue(res.success)
        self.assertIn("12.5%", res.response_text)
        self.assertIn("45.0%", res.response_text)

    @patch("tools.info_tools.get_weather")
    def test_weather(self, mock_weather):
        mock_weather.return_value = {
            "city": "Tokyo",
            "temperature_c": 19.5,
            "condition": "Clear sky",
        }
        res = command_executor.execute_intent({"action": "weather", "query": "Tokyo"})
        self.assertTrue(res.success)
        self.assertIn("Tokyo", res.response_text)
        self.assertIn("19.5", res.response_text)


if __name__ == "__main__":
    unittest.main()
