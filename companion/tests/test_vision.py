"""Automated test suite for DeskBot Visual Screen Intelligence and Code Understanding."""

from __future__ import annotations

import base64
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

COMPANION_DIR = Path(__file__).resolve().parent.parent
if str(COMPANION_DIR) not in sys.path:
    sys.path.insert(0, str(COMPANION_DIR))

from PIL import Image

import config
from ai_brain import fast_intent_match

from assistant.context import ConversationContext
from command_executor import REGISTRY, ToolResult, execute_intent
from vision.analyzer import (
    MockVisionAnalyzer,
    NvidiaVisionAnalyzer,
    VisionAnalysis,
    _clean_tts_text,
    _parse_vision_response,
)
from vision.screen_capture import (
    ScreenCaptureResult,
    capture_screen,
    optimize_image_for_vision,
)
from vision.service import (
    clear_vision_cache,
    get_last_vision_result,
    is_vision_cache_valid,
    perform_screen_analysis,
    set_vision_analyzer,
)


class TestScreenCaptureAndOptimization(unittest.TestCase):
    """Test image optimization, scaling, format conversions, and capture abstraction."""

    def test_optimize_large_image_scaling(self):
        # Create a large 4K test image (3840 x 2160)
        img = Image.new("RGB", (3840, 2160), color=(30, 30, 30))
        optimized, b64_str = optimize_image_for_vision(img, max_dimension=1920, quality=85)

        self.assertEqual(optimized.width, 1920)
        self.assertEqual(optimized.height, 1080)
        self.assertGreater(len(b64_str), 100)

        # Verify decoded bytes form valid JPEG
        decoded = base64.b64decode(b64_str)
        reopened = Image.open(io.BytesIO(decoded))
        self.assertEqual(reopened.size, (1920, 1080))
        self.assertEqual(reopened.format, "JPEG")

    def test_optimize_rgba_image(self):
        # Create an RGBA image with transparency
        img = Image.new("RGBA", (800, 600), color=(255, 0, 0, 128))
        optimized, b64_str = optimize_image_for_vision(img, max_dimension=1920, quality=88)

        self.assertEqual(optimized.mode, "RGB")
        self.assertEqual(optimized.size, (800, 600))
        self.assertTrue(len(b64_str) > 0)

    def test_screen_capture_result_data_uri(self):
        img = Image.new("RGB", (200, 200), color=(0, 255, 0))
        res = ScreenCaptureResult(
            image=img,
            width=200,
            height=200,
            base64_data="dummy_base64",
            format="jpeg",
            timestamp=123.456,
        )
        self.assertEqual(res.data_uri, "data:image/jpeg;base64,dummy_base64")

    @patch("vision.screen_capture.ImageGrab")
    def test_capture_screen_with_pillow(self, mock_image_grab):
        mock_img = Image.new("RGB", (1920, 1080), color=(10, 20, 30))
        mock_image_grab.grab.return_value = mock_img

        result = capture_screen(max_dimension=1920, quality=88)
        self.assertIsInstance(result, ScreenCaptureResult)
        self.assertEqual(result.width, 1920)
        self.assertEqual(result.height, 1080)
        self.assertTrue(result.data_uri.startswith("data:image/jpeg;base64,"))


class TestVisionAnalyzerParsing(unittest.TestCase):
    """Test JSON response parsing, markdown stripping, and spoken TTS formatting."""

    def test_parse_clean_json(self):
        payload = """{
            "content_type": "code",
            "language": "python",
            "readability": "clear",
            "summary": "A quicksort function in Python.",
            "code_details": "quicksort partition and recursion",
            "visible_issues": "none",
            "uncertainties": "none",
            "spoken_response": "You have a Python implementation of the quicksort algorithm on your screen."
        }"""
        analysis = _parse_vision_response(payload)
        self.assertEqual(analysis.content_type, "code")
        self.assertEqual(analysis.language, "python")
        self.assertEqual(analysis.readability, "clear")
        self.assertIn("quicksort", analysis.spoken_response)

    def test_parse_markdown_wrapped_json(self):
        payload = """```json
{
    "content_type": "terminal_error",
    "language": "python",
    "readability": "clear",
    "summary": "ModuleNotFoundError in terminal.",
    "code_details": "Traceback showing No module named 'requests'",
    "visible_issues": "ModuleNotFoundError: No module named requests",
    "uncertainties": "none",
    "spoken_response": "Your terminal is showing a ModuleNotFoundError because the requests library is not installed."
}
```"""
        analysis = _parse_vision_response(payload)
        self.assertEqual(analysis.content_type, "terminal_error")
        self.assertEqual(analysis.language, "python")
        self.assertIn("ModuleNotFoundError", analysis.visible_issues)
        self.assertIn("requests library is not installed", analysis.spoken_response)

    def test_clean_tts_text(self):
        raw = "Here is **bold text**, *italic text*, `# Header` and `code_sample()`."
        cleaned = _clean_tts_text(raw)
        self.assertNotIn("**", cleaned)
        self.assertNotIn("`", cleaned)
        self.assertEqual(cleaned, "Here is bold text, italic text, Header and code_sample().")

    def test_parse_fallback_unstructured_text(self):
        raw = "This is a C++ video tutorial showing how to use std::vector with push_back."
        analysis = _parse_vision_response(raw)
        self.assertEqual(analysis.content_type, "video_tutorial")
        self.assertEqual(analysis.language, "c++")
        self.assertIn("std::vector", analysis.spoken_response)



class TestVisionServiceAndCaching(unittest.TestCase):
    """Test perform_screen_analysis coordination, caching, and follow-up reuse."""

    def setUp(self):
        clear_vision_cache()
        self.mock_analyzer = MockVisionAnalyzer(
            predefined_response=VisionAnalysis(
                content_type="video_tutorial",
                language="javascript",
                readability="clear",
                summary="React useEffect tutorial video.",
                code_details="Explaining dependency array in useEffect hook.",
                visible_issues="none",
                uncertainties="bottom of editor truncated",
                spoken_response="The presenter in the video is explaining how to manage dependencies in a React useEffect hook.",
            )
        )
        set_vision_analyzer(self.mock_analyzer)

    def tearDown(self):
        clear_vision_cache()

    @patch("vision.service.capture_screen")
    def test_perform_screen_analysis_success(self, mock_capture):
        dummy_img = Image.new("RGB", (640, 480))
        mock_capture.return_value = ScreenCaptureResult(
            image=dummy_img,
            width=640,
            height=480,
            base64_data="dummy_b64",
            format="jpeg",
            timestamp=100.0,
        )

        result = perform_screen_analysis(user_query="What is the guy in the video coding?")
        self.assertTrue(result.success)
        self.assertIn("React useEffect", result.response_text)
        self.assertIn("video_tutorial", result.data["content_type"])
        self.assertEqual(result.data["language"], "javascript")

        # Verify caching
        cached = get_last_vision_result()
        self.assertIsNotNone(cached)
        self.assertEqual(cached.language, "javascript")
        self.assertTrue(is_vision_cache_valid(ttl_seconds=60.0))

    @patch("vision.service.capture_screen")
    def test_perform_screen_analysis_cache_reuse(self, mock_capture):
        dummy_img = Image.new("RGB", (640, 480))
        mock_capture.return_value = ScreenCaptureResult(
            image=dummy_img,
            width=640,
            height=480,
            base64_data="dummy_b64",
            format="jpeg",
            timestamp=100.0,
        )

        # Initial analysis
        perform_screen_analysis(user_query="What is on my screen?")
        self.assertEqual(mock_capture.call_count, 1)

        # Follow-up analysis with cache enabled
        cached_result = perform_screen_analysis(
            user_query="Explain it more simply",
            use_cache_if_recent=True,
            cache_ttl=30.0,
        )
        self.assertTrue(cached_result.success)
        # Should NOT capture screen again
        self.assertEqual(mock_capture.call_count, 1)


class TestIntentRoutingForScreen(unittest.TestCase):
    """Test natural language intent routing for visual screen intelligence."""

    def test_direct_screen_queries(self):
        queries = [
            "what is on my screen",
            "what's on my screen",
            "what is visible on my screen",
            "look at my screen",
            "inspect my screen",
            "examine my screen",
            "what do you see on my screen",
            "can you read what's on my screen",
            "what am i looking at",
        ]
        for q in queries:
            intent = fast_intent_match(q)
            self.assertIsNotNone(intent, f"Failed to match: {q}")
            self.assertEqual(intent.get("action"), "screen_analysis", f"Wrong action for: {q}")

    def test_visible_code_queries(self):
        queries = [
            "explain this code",
            "explain the code on my screen",
            "what does this code do",
            "what is this code doing",
            "what code is this",
            "what is this code",
            "what does this function do",
            "explain this function",
        ]
        for q in queries:
            intent = fast_intent_match(q)
            self.assertIsNotNone(intent, f"Failed to match: {q}")
            self.assertEqual(intent.get("action"), "screen_analysis", f"Wrong action for: {q}")

    def test_video_tutorial_queries(self):
        queries = [
            "what is the guy in the video coding",
            "what is the person in the video coding",
            "what is the instructor coding",
            "what is being coded in this video",
            "explain the video code",
        ]
        for q in queries:
            intent = fast_intent_match(q)
            self.assertIsNotNone(intent, f"Failed to match: {q}")
            self.assertEqual(intent.get("action"), "screen_analysis", f"Wrong action for: {q}")

    def test_visible_error_and_debugging_queries(self):
        queries = [
            "what is wrong with this code",
            "what's wrong with this code",
            "why is this code failing",
            "why is this failing",
            "what is this error",
            "what error is on my screen",
            "debug this code",
        ]
        for q in queries:
            intent = fast_intent_match(q)
            self.assertIsNotNone(intent, f"Failed to match: {q}")
            self.assertEqual(intent.get("action"), "screen_analysis", f"Wrong action for: {q}")

    def test_language_detection_queries(self):
        queries = [
            "what programming language is this",
            "what language is this code",
            "what language is this",
        ]
        for q in queries:
            intent = fast_intent_match(q)
            self.assertIsNotNone(intent, f"Failed to match: {q}")
            self.assertEqual(intent.get("action"), "screen_analysis", f"Wrong action for: {q}")

    def test_active_window_vs_screen_differentiation(self):
        # Window-specific queries should trigger get_active_window
        win_intent = fast_intent_match("what window is active")
        self.assertIsNotNone(win_intent)
        self.assertEqual(win_intent.get("action"), "get_active_window")

        app_intent = fast_intent_match("what app is open")
        self.assertIsNotNone(app_intent)
        self.assertEqual(app_intent.get("action"), "get_active_window")

        # Developer mode file tools remain distinct
        file_intent = fast_intent_match("explain the active file")
        self.assertIsNotNone(file_intent)
        self.assertEqual(file_intent.get("action"), "read_active_file")


class TestActionRegistryAndExecution(unittest.TestCase):
    """Test action registry execution of screen_analysis."""

    def setUp(self):
        clear_vision_cache()
        self.mock_analyzer = MockVisionAnalyzer(
            predefined_response=VisionAnalysis(
                content_type="code",
                language="python",
                readability="clear",
                summary="A Flask web app definition.",
                code_details="app = Flask(__name__) with a @app.route('/') index handler",
                visible_issues="none",
                uncertainties="none",
                spoken_response="On your screen is a minimal Flask application with a single home route.",
            )
        )
        set_vision_analyzer(self.mock_analyzer)

    def tearDown(self):
        clear_vision_cache()

    def test_registry_has_screen_analysis(self):
        self.assertTrue(REGISTRY.has_action("screen_analysis"))

    @patch("vision.service.capture_screen")
    def test_execute_intent_screen_analysis(self, mock_capture):
        dummy_img = Image.new("RGB", (800, 600))
        mock_capture.return_value = ScreenCaptureResult(
            image=dummy_img,
            width=800,
            height=600,
            base64_data="dummy_b64",
            format="jpeg",
            timestamp=100.0,
        )

        intent = {"action": "screen_analysis", "query": "What is this code?"}
        result = execute_intent(intent)
        self.assertTrue(result.success)
        self.assertIn("Flask", result.response_text)
        self.assertEqual(result.data["language"], "python")


class TestConversationContextIntegration(unittest.TestCase):
    """Test multi-turn context tracking with screen analysis."""

    def test_multi_turn_with_screen_context(self):
        ctx = ConversationContext(max_messages=4, ttl_seconds=60.0)

        # Record screen analysis turn
        ctx.add_turn(
            user_speech="What is on my screen?",
            tool_name="screen_analysis",
            tool_query="What is on my screen?",
            tool_success=True,
            assistant_response="You have an asynchronous Python script using asyncio to scrape web endpoints.",
        )

        prompt_str = ctx.get_context_for_prompt()
        self.assertIn("What is on my screen?", prompt_str)
        self.assertIn("screen_analysis", prompt_str)
        self.assertIn("asyncio", prompt_str)


if __name__ == "__main__":
    unittest.main()
