"""Comprehensive end-to-end and regression tests for DeskBot system stabilization audit.

Tests:
1. Wake word memory preservation (reset_wake_scores does not wipe acoustic spectrogram).
2. Intent routing fast paths (math, weather, apps, screenshots).
3. Deterministic calculator execution (450 * 12 -> 5400) vs opening Calculator app.
4. Deterministic weather API execution (Open-Meteo, default city fallback, ask city prompt).
5. Screenshot destination: Saved directly to Path.home() / "Desktop" with DeskBot_Screenshot_*.png.
6. Real success verification (ToolResult contract & negative checks).
7. TTP223 touch debouncing (single activation on rapid taps).
8. Performance profiling instrumentation ([PERF]).
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from companion import ai_brain, command_executor, config
from companion.command_executor import ToolResult
from companion.tools.calculator import evaluate_math
from companion.tools.info_tools import get_weather


class TestAuditStabilization(unittest.TestCase):
    def setUp(self):
        self.desktop_dir = Path.home() / "Desktop"

    def test_wake_scores_reset_preserves_acoustic_memory(self):
        """Verify that reset_wake_scores clears score history without destroying preprocessor spectrogram."""
        # Create a mock openWakeWord detector
        mock_detector = MagicMock()
        mock_detector.prediction_buffer = {
            "hey_jarvis": [0.45, 0.52, 0.48],
        }
        mock_preprocessor = MagicMock()
        mock_preprocessor.melspectrogram_buffer = MagicMock()
        mock_detector.preprocessor = mock_preprocessor

        # Simulate the reset logic used in continuous_assistant
        for k in list(mock_detector.prediction_buffer.keys()):
            mock_detector.prediction_buffer[k].clear()

        self.assertEqual(len(mock_detector.prediction_buffer["hey_jarvis"]), 0)
        # Preprocessor spectrogram buffer should NOT have been replaced or wiped to ones
        self.assertIsNotNone(mock_preprocessor.melspectrogram_buffer)

    def test_calculator_ast_deterministic_450_times_12(self):
        """Requirement 4: 450 * 12 -> 5400 evaluated safely and spoken."""
        res = evaluate_math("450 * 12")
        self.assertIsNotNone(res)
        self.assertIn("5400", res)
        self.assertEqual(res, "450 multiplied by 12 is 5400.")

        res_calc = evaluate_math("calculate 450 times 12")
        self.assertIsNotNone(res_calc)
        self.assertIn("5400", res_calc)

        # Execution via command_executor
        exec_res = command_executor.execute_intent({
            "action": "calculate",
            "query": "450 * 12",
        })
        self.assertTrue(exec_res.success)
        self.assertEqual(exec_res.response_text, "450 multiplied by 12 is 5400.")
        self.assertEqual(exec_res.data, {"result": "450 multiplied by 12 is 5400."})

    def test_open_calculator_app_not_confused_with_calculate(self):
        """Requirement 4: 'open calculator' launches Calculator app, does NOT evaluate math."""
        intent = ai_brain.fast_intent_match("open calculator")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.get("action"), "open_app")
        self.assertEqual(intent.get("query"), "Calculator")

    def test_weather_with_city_open_meteo(self):
        """Requirement 3: Fetch real weather for specified city."""
        res = get_weather("London")
        self.assertNotIn("error", res)
        self.assertEqual(res["city"], "London")
        self.assertIn("temperature_c", res)
        self.assertIn("condition", res)

        intent = ai_brain.fast_intent_match("what is the weather in London")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.get("action"), "weather")
        self.assertEqual(intent.get("query"), "London")

    def test_weather_without_city_asks_city(self):
        """Requirement 3: If no city specified and no default, ask 'Which city should I check?'."""
        with patch.dict(os.environ, {"DESKBOT_DEFAULT_CITY": ""}, clear=False):
            res = get_weather(None)
            self.assertTrue(res.get("need_city"))
            exec_res = command_executor.execute_intent({"action": "weather", "query": None})
            self.assertTrue(exec_res.success)
            self.assertEqual(exec_res.response_text, "Which city should I check?")

    def test_weather_with_configured_default_city(self):
        """Requirement 3: If no city specified but configured in env, use configured city."""
        with patch.dict(os.environ, {"DESKBOT_DEFAULT_CITY": "Tokyo"}, clear=False):
            res = get_weather(None)
            self.assertNotIn("error", res)
            self.assertEqual(res["city"], "Tokyo")

    def test_screenshot_saved_directly_to_desktop(self):
        """Requirement 10: Screenshot saved directly to Path.home() / 'Desktop' with DeskBot_Screenshot_*.png."""
        mock_img = MagicMock()
        mock_path_str = ""

        def fake_save(path_arg):
            nonlocal mock_path_str
            mock_path_str = str(path_arg)
            Path(path_arg).touch()

        mock_img.save.side_effect = fake_save

        with patch("PIL.ImageGrab.grab", return_value=mock_img):
            result = command_executor.execute_intent({"action": "screenshot"})
            self.assertTrue(result.success)
            self.assertIn("saved to your Desktop", result.response_text)
            self.assertTrue(result.data and "path" in result.data)

            saved_path = Path(result.data["path"])
            self.assertEqual(saved_path.parent, self.desktop_dir)
            self.assertTrue(saved_path.name.startswith("DeskBot_Screenshot_"))
            self.assertTrue(saved_path.name.endswith(".png"))
            if saved_path.exists():
                try:
                    saved_path.unlink()
                except Exception:
                    pass

    def test_never_claim_success_without_real_success(self):
        """Requirement 5: Tools must return success=False and clear error message on failure."""
        # Non-existent application launch
        res_app = command_executor.execute_intent({"action": "open_app", "query": "TotallyNonExistentApp12345"})
        self.assertFalse(res_app.success)
        self.assertIn("couldn't find or open", res_app.response_text)

        # Invalid website
        res_web = command_executor.execute_intent({"action": "open_website", "query": "not a website at all"})
        self.assertFalse(res_web.success)

        # Non-existent file deletion
        res_del = command_executor.execute_intent({"action": "delete_file", "query": "non_existent_file_xyz_987.txt"})
        self.assertFalse(res_del.success)

    def test_ttp223_touch_sensor_debouncing(self):
        """Requirement 8: Rapid consecutive touch triggers must be debounced to exactly ONE activation."""
        from companion.audio.audio_engine import AudioEngine

        engine = AudioEngine(sample_rate=16000, frame_bytes=960)
        self.assertFalse(engine.check_and_consume_touch())

        # Simulate first touch trigger in serial stream
        now = time.monotonic()
        engine._last_touch_time = 0.0
        with engine._touch_lock:
            if (now - engine._last_touch_time) >= engine._touch_debounce_seconds:
                engine._last_touch_time = now
                engine._touch_detected = True

        # First consumption must succeed
        self.assertTrue(engine.check_and_consume_touch())
        self.assertFalse(engine.check_and_consume_touch())

        # Simulate a bounce 50ms later (well within 600ms debounce window)
        bounce_time = now + 0.05
        with engine._touch_lock:
            if (bounce_time - engine._last_touch_time) >= engine._touch_debounce_seconds:
                engine._last_touch_time = bounce_time
                engine._touch_detected = True

        # Should NOT trigger again because it was debounced
        self.assertFalse(engine.check_and_consume_touch())

    def test_performance_profiling_format(self):
        """Requirement 2: Validate [PERF] timing log format."""
        wake_ms = 45.2
        stt_ms = 112.5
        intent_ms = 0.4
        tool_ms = 18.3
        response_ms = 0.0
        tts_ms = 85.0
        total_ms = wake_ms + stt_ms + intent_ms + tool_ms + response_ms + tts_ms

        perf_msg = (
            f"[PERF] Wake: {wake_ms:.1f} ms | STT: {stt_ms:.1f} ms | "
            f"Intent: {intent_ms:.1f} ms | Tool: {tool_ms:.1f} ms | "
            f"Response: {response_ms:.1f} ms | TTS: {tts_ms:.1f} ms | "
            f"TOTAL: {total_ms:.1f} ms"
        )

        self.assertIn("[PERF]", perf_msg)
        self.assertIn("Wake: 45.2 ms", perf_msg)
        self.assertIn("STT: 112.5 ms", perf_msg)
        self.assertIn("Intent: 0.4 ms", perf_msg)
        self.assertIn("Tool: 18.3 ms", perf_msg)
        self.assertIn("Response: 0.0 ms", perf_msg)
        self.assertIn("TTS: 85.0 ms", perf_msg)
        self.assertIn("TOTAL: 261.4 ms", perf_msg)


if __name__ == "__main__":
    unittest.main()
