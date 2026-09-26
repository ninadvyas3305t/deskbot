"""Unit tests for developer tools (file reading, AST code analysis, test runner, screen capture)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import developer_tools


class TestDeveloperTools(unittest.TestCase):
    """Test suite for developer capabilities."""

    def test_read_active_file_success(self):
        res = developer_tools.read_active_file("calculator.py")
        self.assertTrue(res.success)
        self.assertIn("calculator.py", res.message)
        self.assertIn("content", res.data)
        self.assertGreater(res.data["total_lines"], 0)

    def test_read_active_file_missing(self):
        res = developer_tools.read_active_file("nonexistent_random_file_9876.py")
        self.assertFalse(res.success)
        self.assertIn("not found", res.message.lower())

    def test_read_active_file_forbidden(self):
        res = developer_tools.read_active_file("C:/Windows/System32/drivers/etc/hosts")
        self.assertFalse(res.success)

    def test_analyze_code_python(self):
        res = developer_tools.analyze_code("calculator.py")
        self.assertTrue(res.success)
        self.assertIn("calculator.py", res.message)
        self.assertIn("evaluate_math", res.data["functions"])
        self.assertGreater(res.data["line_count"], 50)

    def test_analyze_code_syntax_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = Path(tmpdir) / "broken.py"
            bad_file.write_text("def broken_syntax(:\n    pass\n", encoding="utf-8")
            res = developer_tools.analyze_code(str(bad_file))
            self.assertFalse(res.success)
            self.assertIn("SyntaxError", res.message)

    @patch("subprocess.run")
    def test_run_tests_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Ran 10 tests in 0.1s\n\nOK\n")
        res = developer_tools.run_tests()
        self.assertTrue(res.success)
        self.assertIn("passed successfully", res.response_text)
        mock_run.assert_called()

    @patch("subprocess.run")
    def test_run_tests_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="FAILED (failures=1)\n")
        res = developer_tools.run_tests()
        self.assertFalse(res.success)
        self.assertIn("failures", res.response_text)

    @patch("PIL.ImageGrab.grab")
    def test_capture_screen_context(self, mock_grab):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_img = MagicMock()
            mock_grab.return_value = mock_img
            res = developer_tools.capture_screen_context(save_dir=Path(tmpdir))
            self.assertTrue(res.success)
            mock_grab.assert_called_once()
            mock_img.save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
