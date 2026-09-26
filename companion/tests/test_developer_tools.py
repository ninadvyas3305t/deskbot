"""Unit tests for developer tools (file reading, AST code analysis, test runner, screen capture, patches, workspace)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

COMPANION_DIR = Path(__file__).resolve().parent.parent
if str(COMPANION_DIR) not in sys.path:
    sys.path.insert(0, str(COMPANION_DIR))

import command_executor
from command_executor import ToolResult
import config
from tools import developer_tools


class TestDeveloperTools(unittest.TestCase):
    """Comprehensive test suite for developer mode and computer assistance capabilities."""

    def setUp(self):
        # Reset developer mode state and pending patches before each test
        developer_tools._DEVELOPER_MODE_ACTIVE = False
        developer_tools._PENDING_PATCHES.clear()

    def tearDown(self):
        developer_tools._DEVELOPER_MODE_ACTIVE = False
        developer_tools._PENDING_PATCHES.clear()

    def test_registered_developer_actions(self):
        """Verify all developer mode actions are registered in command_executor."""
        actions = [
            "enter_developer_mode",
            "exit_developer_mode",
            "developer_mode_status",
            "get_active_window",
            "get_current_file",
            "get_current_workspace",
            "read_active_file",
            "list_workspace_files",
            "search_workspace",
            "analyze_code",
            "propose_patch",
            "apply_patch",
            "rollback_patch",
            "run_tests",
            "capture_screen_context",
        ]
        for act in actions:
            self.assertTrue(command_executor.REGISTRY.has_action(act), f"Missing action: {act}")

    def test_developer_mode_toggle(self):
        """Test enabling, checking, and disabling developer mode."""
        self.assertFalse(developer_tools.is_developer_mode())

        # Enable
        res = developer_tools.set_developer_mode(True)
        self.assertTrue(res.success)
        self.assertTrue(developer_tools.is_developer_mode())
        self.assertIn("active", res.response_text.lower())

        # Via command_executor status
        status_res = command_executor.execute_intent({"action": "developer_mode_status"})
        self.assertTrue(status_res.success)
        self.assertTrue(status_res.data["developer_mode"])

        # Disable
        off_res = developer_tools.set_developer_mode(False)
        self.assertTrue(off_res.success)
        self.assertFalse(developer_tools.is_developer_mode())
        self.assertIn("off", off_res.response_text.lower())

    def test_get_active_window_macos(self):
        """Test active window detection on macOS with mock osascript."""
        app_mock = MagicMock(returncode=0, stdout="/Applications/Visual Studio Code.app:\n")
        title_mock = MagicMock(returncode=0, stdout="main.cpp — deskbot\n")

        with patch("sys.platform", "darwin"), patch("subprocess.run", side_effect=[app_mock, title_mock]):
            res = developer_tools.get_active_window()
            self.assertTrue(res.success)
            self.assertEqual(res.data["application"], "Visual Studio Code")
            self.assertEqual(res.data["title"], "main.cpp — deskbot")
            self.assertIn("Visual Studio Code", res.response_text)

    def test_get_active_window_win32(self):
        """Test active window detection on Windows with mock win32 libraries."""
        mock_win32gui = MagicMock()
        mock_win32gui.GetForegroundWindow.return_value = 9999
        mock_win32gui.GetWindowText.return_value = "calculator.py — deskbot - Visual Studio Code"

        mock_win32process = MagicMock()
        mock_win32process.GetWindowThreadProcessId.return_value = (100, 200)

        mock_psutil = MagicMock()
        mock_proc = MagicMock()
        mock_proc.name.return_value = "code.exe"
        mock_psutil.Process.return_value = mock_proc

        with patch("sys.platform", "win32"), \
             patch.dict("sys.modules", {
                 "win32gui": mock_win32gui,
                 "win32process": mock_win32process,
                 "psutil": mock_psutil,
             }):
            res = developer_tools.get_active_window()
            self.assertTrue(res.success)
            self.assertEqual(res.data["application"], "Visual Studio Code")
            self.assertIn("calculator.py", res.data["title"])

    def test_get_current_file_detected(self):
        """Test extracting active code file from VS Code window title."""
        mock_win = ToolResult(
            True,
            "Active app",
            "In Code",
            data={
                "application": "Visual Studio Code",
                "title": "● calculator.py — deskbot — Visual Studio Code",
            },
        )
        with patch.object(developer_tools, "get_active_window", return_value=mock_win):
            res = developer_tools.get_current_file()
            self.assertTrue(res.success)
            self.assertEqual(res.data["filename"], "calculator.py")
            self.assertTrue(Path(res.data["filepath"]).is_file())

    def test_get_current_file_not_found(self):
        """Test when current window is not editing a recognizable file."""
        mock_win = ToolResult(
            True,
            "Active app",
            "In Chrome",
            data={"application": "Google Chrome", "title": "Google Search - Chrome"},
        )
        with patch.object(developer_tools, "get_active_window", return_value=mock_win):
            res = developer_tools.get_current_file()
            self.assertFalse(res.success)
            self.assertIn("No active code file", res.message)

    def test_get_current_workspace(self):
        """Test workspace boundary inspection."""
        res = developer_tools.get_current_workspace()
        self.assertTrue(res.success)
        self.assertEqual(res.data["workspace_root"], str(config.WORKSPACE_ROOT))
        self.assertTrue(res.data["exists"])

    def test_list_workspace_files(self):
        """Test workspace file indexing and ignored directory filtering."""
        res = developer_tools.list_workspace_files()
        self.assertTrue(res.success)
        files = res.data["files"]
        self.assertGreater(len(files), 0)
        # Ensure hidden/build directories are excluded
        for f in files:
            self.assertFalse(f.startswith(".git/"))
            self.assertFalse(f.startswith(".venv/"))
            self.assertFalse(f.startswith("__pycache__/"))

    def test_list_workspace_files_with_extension(self):
        """Test filtering workspace files by extension."""
        res = developer_tools.list_workspace_files(extension=".py")
        self.assertTrue(res.success)
        files = res.data["files"]
        self.assertGreater(len(files), 0)
        for f in files:
            self.assertTrue(f.endswith(".py"))

    def test_search_workspace_found(self):
        """Test searching for an existing token in the codebase."""
        res = developer_tools.search_workspace("evaluate_math")
        self.assertTrue(res.success)
        self.assertGreater(len(res.data["matches"]), 0)
        matched_files = [m["file"] for m in res.data["matches"]]
        self.assertTrue(any("calculator.py" in f for f in matched_files))

    def test_search_workspace_empty_query(self):
        """Test searching with an empty query."""
        res = developer_tools.search_workspace("")
        self.assertFalse(res.success)
        self.assertIn("Missing search query", res.message)

    def test_search_workspace_not_found(self):
        """Test searching for a non-existent token."""
        query = "".join(["non", "existent", "token", "xyz_998877"])
        res = developer_tools.search_workspace(query)
        self.assertTrue(res.success)
        self.assertEqual(len(res.data["matches"]), 0)

    def test_read_active_file_success(self):
        """Test reading an existing project file."""
        res = developer_tools.read_active_file("calculator.py")
        self.assertTrue(res.success)
        self.assertIn("calculator.py", res.message)
        self.assertIn("content", res.data)
        self.assertGreater(res.data["total_lines"], 0)

    def test_read_active_file_missing(self):
        """Test reading a non-existent file."""
        res = developer_tools.read_active_file("nonexistent_random_file_9876.py")
        self.assertFalse(res.success)
        self.assertIn("not found", res.message.lower())

    def test_read_active_file_forbidden(self):
        """Test reading a sensitive system file is blocked."""
        res = developer_tools.read_active_file("C:/Windows/System32/drivers/etc/hosts")
        self.assertFalse(res.success)

    def test_analyze_code_python(self):
        """Test AST analysis on a Python module."""
        res = developer_tools.analyze_code("calculator.py")
        self.assertTrue(res.success)
        self.assertIn("calculator.py", res.message)
        self.assertIn("evaluate_math", res.data["functions"])
        self.assertGreater(res.data["line_count"], 50)

    def test_analyze_code_syntax_error(self):
        """Test AST analysis reporting syntax errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = Path(tmpdir) / "broken.py"
            bad_file.write_text("def broken_syntax(:\n    pass\n", encoding="utf-8")
            res = developer_tools.analyze_code(str(bad_file))
            self.assertFalse(res.success)
            self.assertIn("SyntaxError", res.message)

    def test_analyze_code_non_python(self):
        """Test analyzing a non-python file skips AST analysis gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            text_file = Path(tmpdir) / "notes.txt"
            text_file.write_text("Hello world notes", encoding="utf-8")
            res = developer_tools.analyze_code(str(text_file))
            self.assertTrue(res.success)
            self.assertIn("skipping AST", res.response_text)

    def test_patch_lifecycle_and_rollback(self):
        """Test complete patch workflow: propose -> stage -> apply -> backup -> rollback."""
        # Create a test file within a temporary directory
        with tempfile.TemporaryDirectory(dir=config.WORKSPACE_ROOT) as tmpdir:
            target = Path(tmpdir) / "sample_service.py"
            original_code = "def get_greeting():\n    return 'hello world'\n"
            target.write_text(original_code, encoding="utf-8")

            # 1. Propose patch
            prop_res = developer_tools.propose_patch(
                str(target),
                "return 'hello world'",
                "return 'hello developer'",
            )
            self.assertTrue(prop_res.success)
            self.assertTrue(prop_res.data["confirmation_required"])
            patch_id = prop_res.data["patch_id"]
            self.assertIn("-return 'hello world'", prop_res.data["diff"])
            self.assertIn("+return 'hello developer'", prop_res.data["diff"])

            # 2. Apply patch
            apply_res = developer_tools.apply_patch(patch_id)
            self.assertTrue(apply_res.success)
            self.assertEqual(target.read_text(encoding="utf-8"), "def get_greeting():\n    return 'hello developer'\n")

            # Check that backup file was created
            backup_file = target.with_suffix(".py.backup")
            self.assertTrue(backup_file.exists())
            self.assertEqual(backup_file.read_text(encoding="utf-8"), original_code)

            # 3. Rollback patch
            rb_res = developer_tools.rollback_patch(str(target))
            self.assertTrue(rb_res.success)
            self.assertEqual(target.read_text(encoding="utf-8"), original_code)
            self.assertFalse(backup_file.exists())

    def test_propose_patch_target_not_found(self):
        """Test proposing a patch where old code doesn't match content."""
        with tempfile.TemporaryDirectory(dir=config.WORKSPACE_ROOT) as tmpdir:
            target = Path(tmpdir) / "module.py"
            target.write_text("value = 42\n", encoding="utf-8")

            res = developer_tools.propose_patch(str(target), "value = 100", "value = 200")
            self.assertFalse(res.success)
            self.assertIn("not found in file", res.message.lower())

    def test_apply_patch_syntax_error_protection(self):
        """Test applying a patch that causes a Python syntax error is rejected."""
        with tempfile.TemporaryDirectory(dir=config.WORKSPACE_ROOT) as tmpdir:
            target = Path(tmpdir) / "safe_module.py"
            target.write_text("def run():\n    return True\n", encoding="utf-8")

            prop_res = developer_tools.propose_patch(
                str(target),
                "return True",
                "return True (broken_syntax",
            )
            self.assertTrue(prop_res.success)
            patch_id = prop_res.data["patch_id"]

            apply_res = developer_tools.apply_patch(patch_id)
            self.assertFalse(apply_res.success)
            self.assertIn("syntax error", apply_res.message.lower())
            # Ensure target file was NOT corrupted
            self.assertEqual(target.read_text(encoding="utf-8"), "def run():\n    return True\n")

    def test_apply_patch_conflict_detected(self):
        """Test patch conflict when file is modified between proposal and application."""
        with tempfile.TemporaryDirectory(dir=config.WORKSPACE_ROOT) as tmpdir:
            target = Path(tmpdir) / "conflict_module.py"
            target.write_text("x = 1\n", encoding="utf-8")

            prop_res = developer_tools.propose_patch(str(target), "x = 1", "x = 2")
            self.assertTrue(prop_res.success)
            patch_id = prop_res.data["patch_id"]

            # File is modified externally before apply
            target.write_text("x = 999\n", encoding="utf-8")

            apply_res = developer_tools.apply_patch(patch_id)
            self.assertFalse(apply_res.success)
            self.assertIn("PATCH_CONFLICT", apply_res.message)

    def test_rollback_no_backup(self):
        """Test rollback failure when no backup file exists."""
        with tempfile.TemporaryDirectory(dir=config.WORKSPACE_ROOT) as tmpdir:
            target = Path(tmpdir) / "lonely.py"
            target.write_text("data = 1\n", encoding="utf-8")

            res = developer_tools.rollback_patch(str(target))
            self.assertFalse(res.success)
            self.assertIn("no backup found", res.message.lower())

    @patch("subprocess.run")
    def test_run_tests_success(self, mock_run):
        """Test run_tests when test suite passes."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Ran 10 tests in 0.1s\n\nOK\n")
        res = developer_tools.run_tests()
        self.assertTrue(res.success)
        self.assertIn("passed successfully", res.response_text)
        mock_run.assert_called()

    @patch("subprocess.run")
    def test_run_tests_failure(self, mock_run):
        """Test run_tests when test suite fails."""
        mock_run.return_value = MagicMock(returncode=1, stdout="FAILED (failures=1)\n")
        res = developer_tools.run_tests()
        self.assertFalse(res.success)
        self.assertIn("failures", res.response_text)

    @patch("PIL.ImageGrab.grab")
    def test_capture_screen_context(self, mock_grab):
        """Test screen capture tool creates image file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_img = MagicMock()
            mock_grab.return_value = mock_img
            res = developer_tools.capture_screen_context(save_dir=Path(tmpdir))
            self.assertTrue(res.success)
            mock_grab.assert_called_once()
            mock_img.save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
