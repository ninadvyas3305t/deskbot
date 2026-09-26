"""Unit tests for Command Executor Action Registry, AI Brain intent validation, and STT validation."""

import json
import unittest
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

COMPANION_DIR = Path(__file__).resolve().parent.parent
if str(COMPANION_DIR) not in sys.path:
    sys.path.insert(0, str(COMPANION_DIR))

import ai_brain
import command_executor
from speech_to_text import validate_audio


class TestActionRegistry(unittest.TestCase):
    def test_registered_actions(self):
        self.assertTrue(command_executor.REGISTRY.has_action("open_app"))
        self.assertTrue(command_executor.REGISTRY.has_action("open_website"))
        self.assertTrue(command_executor.REGISTRY.has_action("youtube_search"))
        self.assertTrue(command_executor.REGISTRY.has_action("youtube_play"))
        self.assertTrue(command_executor.REGISTRY.has_action("spotify_open"))
        self.assertTrue(command_executor.REGISTRY.has_action("unknown"))

    @patch("webbrowser.open")
    def test_open_youtube(self, mock_web):
        intent = {"action": "open_website", "query": "youtube.com"}
        desc = command_executor.get_action_description(intent)
        self.assertIn("youtube.com", desc)
        success = command_executor.execute_intent(intent)
        self.assertTrue(success)
        mock_web.assert_called_with("https://www.youtube.com")

    @patch("subprocess.Popen")
    def test_open_spotify(self, mock_popen):
        intent = {"action": "spotify_open"}
        desc = command_executor.get_action_description(intent)
        self.assertEqual(desc, "Opening Spotify")
        success = command_executor.execute_intent(intent)
        self.assertTrue(success)
        mock_popen.assert_called()

    @patch("command_executor._launch_target")
    def test_launch_notepad(self, mock_launch):
        mock_launch.return_value = True
        intent = {"action": "open_app", "query": "Notepad"}
        desc = command_executor.get_action_description(intent)
        self.assertIn("Notepad", desc)
        success = command_executor.execute_intent(intent)
        self.assertTrue(success)
        expected = "TextEdit" if sys.platform == "darwin" else "notepad.exe"
        mock_launch.assert_called_with(expected)

    @patch("command_executor._launch_target")
    def test_launch_calculator(self, mock_launch):
        mock_launch.return_value = True
        intent = {"action": "open_app", "query": "Calculator"}
        success = command_executor.execute_intent(intent)
        self.assertTrue(success)
        expected = "Calculator" if sys.platform == "darwin" else "calc.exe"
        mock_launch.assert_called_with(expected)

    def test_unknown_action(self):
        intent = {"action": "unknown"}
        success = command_executor.execute_intent(intent)
        self.assertFalse(success)

    @patch("command_executor.find_first_youtube_video")
    @patch("webbrowser.open")
    def test_play_youtube_direct(self, mock_web, mock_find):
        mock_find.return_value = "fJ9rUzIMcZQ"
        intent = {"action": "youtube_play", "query": "Bohemian Rhapsody"}
        success = command_executor.execute_intent(intent)
        self.assertTrue(success)
        mock_find.assert_called_with("Bohemian Rhapsody")
        mock_web.assert_called_with("https://www.youtube.com/watch?v=fJ9rUzIMcZQ")

    @patch("command_executor.find_first_youtube_video")
    @patch("webbrowser.open")
    def test_play_youtube_fallback(self, mock_web, mock_find):
        mock_find.return_value = None
        intent = {"action": "youtube_play", "query": "Uncommon Song 12345"}
        success = command_executor.execute_intent(intent)
        self.assertTrue(success)
        mock_web.assert_called_with("https://www.youtube.com/results?search_query=Uncommon+Song+12345")

    @patch("webbrowser.open")
    def test_play_youtube_empty(self, mock_web):
        intent = {"action": "youtube_play", "query": None}
        success = command_executor.execute_intent(intent)
        self.assertTrue(success)
        mock_web.assert_called_with("https://www.youtube.com")

    @patch("subprocess.Popen")
    def test_play_spotify_query(self, mock_popen):
        intent = {"action": "spotify_play", "query": "Starboy"}
        desc = command_executor.get_action_description(intent)
        self.assertIn("Starboy", desc)
        success = command_executor.execute_intent(intent)
        self.assertTrue(success)
        mock_popen.assert_called()

    @patch("subprocess.Popen")
    def test_play_spotify_empty(self, mock_popen):
        intent = {"action": "spotify_play", "query": None}
        desc = command_executor.get_action_description(intent)
        self.assertEqual(desc, "Playing on Spotify: music")
        success = command_executor.execute_intent(intent)
        self.assertTrue(success)
        mock_popen.assert_called()

    def test_invalid_intent_dict(self):
        self.assertFalse(command_executor.execute_intent(None))
        self.assertFalse(command_executor.execute_intent({}))


class TestAIBrainValidation(unittest.TestCase):
    def test_validate_intent_success(self):
        valid, msg = ai_brain.validate_intent({"action": "open_app", "query": "Notepad"})
        self.assertTrue(valid)

        valid, msg = ai_brain.validate_intent({"action": "spotify_open"})
        self.assertTrue(valid)

        valid, msg = ai_brain.validate_intent({"action": "spotify_play", "query": "Starboy"})
        self.assertTrue(valid)

        for act in [
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
        ]:
            valid, msg = ai_brain.validate_intent({"action": act})
            self.assertTrue(valid, f"Failed for action: {act}")

    def test_validate_intent_failures(self):
        # Non-dict
        valid, _ = ai_brain.validate_intent("not a dict")
        self.assertFalse(valid)

        # Missing action
        valid, _ = ai_brain.validate_intent({"query": "Notepad"})
        self.assertFalse(valid)

        # Unsupported action
        valid, _ = ai_brain.validate_intent({"action": "launch_missile"})
        self.assertFalse(valid)

    @patch("ai_brain.understand")
    def test_understand_intent_mock_valid(self, mock_understand):
        mock_understand.return_value = json.dumps({"action": "open_app", "query": "Notepad"})
        intent = ai_brain.understand_intent("Open Notepad")
        self.assertEqual(intent, {"action": "open_app", "query": "Notepad"})

    @patch("ai_brain.understand")
    def test_understand_intent_mock_malformed(self, mock_understand):
        mock_understand.return_value = "Not valid JSON {"
        intent = ai_brain.understand_intent("blabla unparseable xyz")
        self.assertIsNone(intent)

    @patch("ai_brain.create_client")
    def test_understand_context_history(self, mock_create):
        ai_brain.reset_history()
        mock_resp1 = MagicMock(choices=[MagicMock(message=MagicMock(content='{"action": "youtube_play", "query": "Bohemian Rhapsody"}'))])
        mock_resp2 = MagicMock(choices=[MagicMock(message=MagicMock(content='{"action": "spotify_play", "query": "Bohemian Rhapsody"}'))])
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [mock_resp1, mock_resp2]
        mock_create.return_value = mock_client

        ai_brain.understand("play Bohemian Rhapsody")
        ai_brain.understand("play it on Spotify")

        # Second call to completions.create must have messages with history
        call_args = mock_client.chat.completions.create.call_args_list
        self.assertEqual(len(call_args), 2)
        second_call_messages = call_args[1].kwargs["messages"]
        # System prompt + turn 1 user + turn 1 assistant + turn 2 user = 4 messages
        self.assertEqual(len(second_call_messages), 4)
        self.assertEqual(second_call_messages[1]["content"], "play Bohemian Rhapsody")
        self.assertEqual(second_call_messages[3]["content"], "play it on Spotify")

    @patch("ai_brain.create_client")
    def test_understand_context_prompt_passed(self, mock_create):
        mock_resp = MagicMock(choices=[MagicMock(message=MagicMock(content='{"action": "weather", "query": "London"}'))])
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        mock_create.return_value = mock_client

        ai_brain.understand("what about London", context_prompt="Recent conversation context: User said weather in Tokyo")
        messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        self.assertTrue(any("Recent conversation context:" in m["content"] for m in messages))

    def test_extract_json_intent_reasoning_fallback(self):
        raw_reasoning = (
            'The user wants to play "Loser" by "Team Impala". This is a specific song request. '
            'Since no platform mentioned, maybe we should use youtube_play.'
        )
        intent = ai_brain.extract_json_intent(raw_reasoning, "Play loser by team Impala.")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.get("action"), "youtube_play")
        self.assertIn("loser by team impala", intent.get("query", "").lower())

    def test_extract_json_intent_doubled_brace(self):
        raw_malformed = '{"{"action": "spotify_play", "query": "Loser by Tame Impala"}'
        intent = ai_brain.extract_json_intent(raw_malformed, "Just play the song on Spotify.")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.get("action"), "spotify_play")
        self.assertEqual(intent.get("query"), "Loser by Tame Impala")

    def test_extract_json_intent_nested_notepad(self):
        # Exact malformed response from user's session
        raw_malformed = '{"action":{"action": "open_app", "query": "Notepad"}'
        intent = ai_brain.extract_json_intent(raw_malformed, "Open Notepad")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.get("action"), "open_app")
        self.assertEqual(intent.get("query"), "Notepad")

    def test_extract_json_intent_natural_app_phrasing(self):
        intents = [
            ("hey jarvis open calculator", "open_app", "Calculator"),
            ("please open paint", "open_app", "Paint"),
            ("launch epic games", "open_app", "Epic Games"),
            ("start blender", "open_app", "Blender"),
            ("run task manager", "open_app", "Task Manager"),
            ("volume up", "volume_up", None),
            ("turn it down", "volume_down", None),
            ("mute", "mute", None),
            ("unmute", "unmute", None),
            ("take a screenshot", "screenshot", None),
            ("close spotify", "close_app", "Spotify"),
            ("open downloads folder", "open_folder", "downloads"),
            ("open project in vscode", "open_project_in_vscode", None),
            ("what time is it", "current_time", None),
            ("what's today's date", "current_date", None),
            ("cpu usage", "system_info", None),
            ("what's the weather in Paris", "weather", "Paris"),
            ("search the web for quantum computing", "web_search", "quantum computing"),
        ]
        for phrase, expected_action, expected_query in intents:
            result = ai_brain.extract_json_intent("", phrase)
            self.assertIsNotNone(result, f"Failed for {phrase}")
            self.assertEqual(result.get("action"), expected_action, f"Wrong action for {phrase}")
            if expected_query is not None:
                self.assertEqual(result.get("query"), expected_query, f"Wrong query for {phrase}")


class TestAppResolution(unittest.TestCase):
    def test_find_common_system_apps(self):
        if sys.platform == "darwin":
            self.assertEqual(command_executor.find_installed_app("calculator"), "Calculator")
            self.assertEqual(command_executor.find_installed_app("the calculator app"), "Calculator")
            self.assertEqual(command_executor.find_installed_app("settings"), "System Settings")
            self.assertEqual(command_executor.find_installed_app("file explorer"), "Finder")
            self.assertEqual(command_executor.find_installed_app("terminal"), "Terminal")
        else:
            self.assertEqual(command_executor.find_installed_app("calculator"), "calc.exe")
            self.assertEqual(command_executor.find_installed_app("the calculator app"), "calc.exe")
            self.assertEqual(command_executor.find_installed_app("paint"), "mspaint.exe")
            self.assertEqual(command_executor.find_installed_app("task manager"), "taskmgr.exe")
            self.assertEqual(command_executor.find_installed_app("settings"), "ms-settings:")
            self.assertEqual(command_executor.find_installed_app("file explorer"), "explorer.exe")
            self.assertEqual(command_executor.find_installed_app("terminal"), "wt.exe")

    def test_find_best_shortcut(self):
        shortcuts = [
            ("7-Zip Help", r"C:\Start\7-Zip Help.lnk"),
            ("7-Zip File Manager", r"C:\Start\7-Zip File Manager.lnk"),
            ("Epic Games Launcher", r"C:\Start\Epic Games Launcher.lnk"),
            ("Adobe Premiere Pro 2021", r"C:\Start\Adobe Premiere Pro 2021.lnk"),
            ("Uninstall App", r"C:\Start\Uninstall App.lnk"),
        ]
        # 7-Zip should pick File Manager over Help
        match_7z = command_executor.find_best_shortcut("7-zip", shortcuts)
        self.assertEqual(match_7z, r"C:\Start\7-Zip File Manager.lnk")

        # Epic Games
        match_epic = command_executor.find_best_shortcut("epic games", shortcuts)
        self.assertEqual(match_epic, r"C:\Start\Epic Games Launcher.lnk")

        # Premiere
        match_prem = command_executor.find_best_shortcut("premiere pro", shortcuts)
        self.assertEqual(match_prem, r"C:\Start\Adobe Premiere Pro 2021.lnk")


class TestAudioValidation(unittest.TestCase):
    def test_valid_audio_file(self):
        last_command = COMPANION_DIR / "last_command.wav"
        if last_command.is_file():
            # Should not raise exception
            validate_audio(last_command)

    def test_missing_audio_file(self):
        missing = COMPANION_DIR / "non_existent.wav"
        with self.assertRaises(FileNotFoundError):
            validate_audio(missing)


class TestWhisperCaching(unittest.TestCase):
    def test_whisper_caching(self):
        import speech_to_text
        mock_model = MagicMock()
        with patch.dict(speech_to_text._MODEL_CACHE, {"test_model": mock_model}, clear=False):
            model = speech_to_text.get_whisper_model("test_model")
            self.assertIs(model, mock_model)


class TestYouTubeAndSpotifyHelpers(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_chunked_youtube_search(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [
            b'<html><head></head><body><div href="/watch?v=dQw4w9WgXcQ">Rick</div>',
            b"",
        ]
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        vid = command_executor.find_first_youtube_video("never gonna give you up")
        self.assertEqual(vid, "dQw4w9WgXcQ")

    @patch("command_executor._send_key")
    @patch("command_executor._bring_spotify_to_front")
    @patch("time.sleep")
    def test_spotify_trigger_keys(self, mock_sleep, mock_bring, mock_send):
        with patch("sys.platform", "win32"):
            command_executor._trigger_spotify_play()
            sent_keys = [call.args[0] for call in mock_send.call_args_list]
            self.assertIn(0x09, sent_keys)
            self.assertIn(0x0D, sent_keys)
            self.assertNotIn(0xB3, sent_keys)


class TestDirectAnswerAndMathRouting(unittest.TestCase):
    def test_direct_answer_registration_and_execution(self):
        self.assertTrue(command_executor.REGISTRY.has_action("direct_answer"))
        self.assertTrue(command_executor.REGISTRY.has_action("calculate"))

        res = command_executor.execute_intent({
            "action": "direct_answer",
            "response": "The square root of 64 is 8.",
        })
        self.assertTrue(res.success)
        self.assertEqual(res.response_text, "The square root of 64 is 8.")

    def test_calculate_execution(self):
        res = command_executor.execute_intent({
            "action": "calculate",
            "query": "What is the square root of 64?",
        })
        self.assertTrue(res.success)
        self.assertEqual(res.response_text, "The square root of 64 is 8.")

    def test_math_heuristic_routing(self):
        intent = ai_brain.extract_json_intent("", "What is the square root of 64?")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.get("action"), "direct_answer")
        self.assertEqual(intent.get("response"), "The square root of 64 is 8.")

        intent2 = ai_brain.extract_json_intent("", "What is 25 times 16?")
        self.assertIsNotNone(intent2)
        self.assertEqual(intent2.get("action"), "direct_answer")
        self.assertEqual(intent2.get("response"), "25 multiplied by 16 is 400.")


if __name__ == "__main__":
    unittest.main()

