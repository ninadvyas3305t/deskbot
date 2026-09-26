"""Unit tests for safe file operations, workspace search, and VS Code launching."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import ai_brain
import command_executor
from tools import file_tools


class TestFileTools(unittest.TestCase):
    """Test suite for deterministic file tools and path safety."""

    def test_path_safety_allowed(self):
        desktop = Path.home() / "Desktop" / "test.txt"
        self.assertTrue(file_tools.is_path_safe(desktop))
        projects = Path.home() / "Projects" / "deskbot" / "main.py"
        self.assertTrue(file_tools.is_path_safe(projects))

    def test_path_safety_forbidden(self):
        win_dir = Path("C:/Windows/System32/calc.exe")
        self.assertFalse(file_tools.is_path_safe(win_dir))
        prog_dir = Path("C:/Program Files/Common Files")
        self.assertFalse(file_tools.is_path_safe(prog_dir))
        root_dir = Path("C:/")
        self.assertFalse(file_tools.is_path_safe(root_dir))

    def test_parse_location_spec(self):
        target, loc = file_tools.parse_location_spec("notes.txt on my Desktop")
        self.assertEqual(target, "notes.txt")
        self.assertEqual(loc, "desktop")

        target, loc = file_tools.parse_location_spec("a folder called Test inside Documents")
        self.assertEqual(target, "Test")
        self.assertEqual(loc, "documents")

        target, loc = file_tools.parse_location_spec("simple_file.py")
        self.assertEqual(target, "simple_file.py")
        self.assertIsNone(loc)

    def test_find_file_in_workspace(self):
        # main.py and ai_brain.py exist in workspace
        p = file_tools.find_file_in_workspace("main.py")
        self.assertIsNotNone(p)
        self.assertTrue(p.exists())
        self.assertEqual(p.name.lower(), "main.py")

        p2 = file_tools.find_file_in_workspace("ai_brain.py")
        self.assertIsNotNone(p2)
        self.assertTrue(p2.exists())
        self.assertEqual(p2.name.lower(), "ai_brain.py")

        missing = file_tools.find_file_in_workspace("completely_nonexistent_file_12345.xyz")
        self.assertIsNone(missing)

    def test_create_file_and_duplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "sample.txt"
            res = file_tools.create_file(str(test_file), content="Hello DeskBot")
            self.assertTrue(res.success)
            self.assertTrue(test_file.exists())
            self.assertEqual(test_file.read_text(encoding="utf-8"), "Hello DeskBot")

            # Duplicate check
            res_dup = file_tools.create_file(str(test_file))
            self.assertTrue(res_dup.success)
            self.assertIn("already exists", res_dup.response_text)

    def test_create_folder_and_duplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_folder = Path(tmpdir) / "SubDir" / "Target"
            res = file_tools.create_folder(str(test_folder))
            self.assertTrue(res.success)
            self.assertTrue(test_folder.is_dir())

            # Duplicate check
            res_dup = file_tools.create_folder(str(test_folder))
            self.assertTrue(res_dup.success)
            self.assertIn("already exists", res_dup.response_text)

    @patch("subprocess.Popen")
    def test_open_file_explorer(self, mock_popen):
        res = file_tools.open_file_explorer()
        self.assertTrue(res.success)
        mock_popen.assert_called_with(["explorer.exe"], shell=False)

    @patch("subprocess.Popen")
    def test_open_in_vscode(self, mock_popen):
        # Open workspace
        res = file_tools.open_in_vscode("deskbot")
        self.assertTrue(res.success)
        mock_popen.assert_called()

        # Open specific file
        res_file = file_tools.open_in_vscode("main.py")
        self.assertTrue(res_file.success)
        mock_popen.assert_called()


class TestFileHeuristicsAndDestructiveGuards(unittest.TestCase):
    """Test AI intent extraction for file operations and destructive commands."""

    def test_heuristic_open_file_explorer(self):
        intent = ai_brain.extract_json_intent("", "open file explorer")
        self.assertEqual(intent["action"], "open_file_explorer")

        intent2 = ai_brain.extract_json_intent("", "open explorer")
        self.assertEqual(intent2["action"], "open_file_explorer")

    def test_heuristic_create_file(self):
        intent = ai_brain.extract_json_intent("", "create a file called notes.txt on my Desktop")
        self.assertEqual(intent["action"], "create_file")
        self.assertEqual(intent["query"], "notes.txt on my Desktop")

        intent2 = ai_brain.extract_json_intent("", "make a new file todo.txt")
        self.assertEqual(intent2["action"], "create_file")
        self.assertEqual(intent2["query"], "todo.txt")

    def test_heuristic_create_folder(self):
        intent = ai_brain.extract_json_intent("", "create a folder called Test on Desktop")
        self.assertEqual(intent["action"], "create_folder")
        self.assertEqual(intent["query"], "Test on Desktop")

    def test_heuristic_open_in_vscode(self):
        intent = ai_brain.extract_json_intent("", "open main.py in vs code")
        self.assertEqual(intent["action"], "open_in_vscode")
        self.assertEqual(intent["query"], "main.py")

        intent_code_file = ai_brain.extract_json_intent("", "open main.py")
        self.assertEqual(intent_code_file["action"], "open_in_vscode")
        self.assertEqual(intent_code_file["query"], "main.py")

        intent_project = ai_brain.extract_json_intent("", "open deskbot in vs code")
        self.assertEqual(intent_project["action"], "open_project_in_vscode")

    def test_heuristic_open_file(self):
        intent = ai_brain.extract_json_intent("", "open file notes.txt")
        self.assertEqual(intent["action"], "open_file")
        self.assertEqual(intent["query"], "notes.txt")

        intent_doc = ai_brain.extract_json_intent("", "open notes.txt")
        self.assertEqual(intent_doc["action"], "open_file")
        self.assertEqual(intent_doc["query"], "notes.txt")

    def test_delete_file_and_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "notes.txt"
            test_file.write_text("temporary content", encoding="utf-8")
            self.assertTrue(test_file.exists())

            # Delete file
            res = file_tools.delete_file(str(test_file))
            self.assertTrue(res.success)
            self.assertFalse(test_file.exists())
            self.assertIn("Deleted", res.response_text)

            # Deleting missing file
            res_missing = file_tools.delete_file(str(test_file))
            self.assertFalse(res_missing.success)
            self.assertIn("couldn't find", res_missing.response_text)

    def test_delete_folder_and_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "TestFolder"
            test_dir.mkdir(parents=True, exist_ok=True)
            self.assertTrue(test_dir.exists())

            res = file_tools.delete_folder(str(test_dir))
            self.assertTrue(res.success)
            self.assertFalse(test_dir.exists())

    def test_is_safe_to_delete_protection(self):
        self.assertFalse(file_tools.is_safe_to_delete(Path("C:/Windows")))
        self.assertFalse(file_tools.is_safe_to_delete(Path("C:/")))
        self.assertFalse(file_tools.is_safe_to_delete(Path.home()))
        for std_dir in file_tools.STANDARD_DIRECTORIES.values():
            self.assertFalse(file_tools.is_safe_to_delete(std_dir))

    def test_heuristic_delete(self):
        intent = ai_brain.extract_json_intent("", "delete notes.txt on my Desktop")
        self.assertEqual(intent["action"], "delete_file")
        self.assertEqual(intent["query"], "notes.txt on my Desktop")

        intent2 = ai_brain.extract_json_intent("", "delete notes.txt")
        self.assertEqual(intent2["action"], "delete_file")
        self.assertEqual(intent2["query"], "notes.txt")

        intent3 = ai_brain.extract_json_intent("", "delete folder Test on my Desktop")
        self.assertEqual(intent3["action"], "delete_folder")
        self.assertEqual(intent3["query"], "Test on my Desktop")

    def test_fast_intent_match_speed_and_fallthrough(self):
        # Fast path returns instant intent for deterministic tools
        time_intent = ai_brain.fast_intent_match("what time is it")
        self.assertIsNotNone(time_intent)
        self.assertEqual(time_intent["action"], "current_time")

        shot_intent = ai_brain.fast_intent_match("take a screenshot")
        self.assertIsNotNone(shot_intent)
        self.assertEqual(shot_intent["action"], "screenshot")

        del_intent = ai_brain.fast_intent_match("delete notes.txt on my Desktop")
        self.assertIsNotNone(del_intent)
        self.assertEqual(del_intent["action"], "delete_file")

        # Open-ended questions fall through to cloud LLM (returns None from fast path)
        general_query = ai_brain.fast_intent_match("what is a neural network?")
        self.assertIsNone(general_query)

        conv_query = ai_brain.fast_intent_match("why is the sky blue?")
        self.assertIsNone(conv_query)

    def test_normalize_spoken_filename(self):
        self.assertEqual(file_tools.normalize_spoken_filename("document dot txt"), "document.txt")
        self.assertEqual(file_tools.normalize_spoken_filename("notes dot txt"), "notes.txt")
        self.assertEqual(file_tools.normalize_spoken_filename("main dot py"), "main.py")
        self.assertEqual(file_tools.normalize_spoken_filename("test dot py"), "test.py")
        self.assertEqual(file_tools.normalize_spoken_filename("notes.txt."), "notes.txt")
        self.assertEqual(file_tools.normalize_spoken_filename("notes.txt?"), "notes.txt")
        self.assertEqual(file_tools.normalize_spoken_filename("notes .txt"), "notes.txt")

    def test_fuzzy_filename_resolution_delete_confirmation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            test_file = tmp_path / "notes.txt"
            test_file.write_text("Hello DeskBot", encoding="utf-8")

            with patch.dict(file_tools.STANDARD_DIRECTORIES, {"desktop": tmp_path}):
                # User says "delete nodes.txt" (STT mistranscription)
                res = file_tools.delete_file("nodes.txt")
                self.assertTrue(res.success)
                self.assertIsNotNone(res.data)
                self.assertTrue(res.data.get("confirmation_required"))
                self.assertEqual(res.data.get("action"), "delete_file")
                self.assertIn("notes.txt", res.response_text)
                self.assertIn("Do you want me to delete it?", res.response_text)

                # Crucial safety requirement: File MUST NOT be deleted yet!
                self.assertTrue(test_file.exists())

                # Once user confirms "Yes", execute_pending_deletion is called:
                del_res = file_tools.execute_pending_deletion(res.data["target_path"])
                self.assertTrue(del_res.success)
                self.assertFalse(test_file.exists())
                self.assertIn("Deleted notes.txt", del_res.response_text)

    @patch("os.startfile")
    def test_fuzzy_filename_resolution_open_file(self, mock_startfile):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            test_file = tmp_path / "notes.txt"
            test_file.write_text("Test", encoding="utf-8")

            with patch.dict(file_tools.STANDARD_DIRECTORIES, {"desktop": tmp_path}):
                # User says "open nodes.txt"
                res = file_tools.open_file("nodes.txt")
                self.assertTrue(res.success)
                self.assertIn("Opening notes.txt", res.response_text)
                mock_startfile.assert_called_with(str(test_file))

    @patch("subprocess.Popen")
    def test_fuzzy_filename_resolution_open_in_vscode(self, mock_popen):
        # User says "open mane.py in vs code" (STT for main.py)
        res = file_tools.open_in_vscode("mane.py")
        self.assertTrue(res.success)
        self.assertIn("Opening main.py in VS Code", res.response_text)
        mock_popen.assert_called()

    def test_multiple_candidates_clarification(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "notes_one.txt").write_text("1", encoding="utf-8")
            (tmp_path / "notes_two.txt").write_text("2", encoding="utf-8")

            with patch.dict(file_tools.STANDARD_DIRECTORIES, {"desktop": tmp_path}):
                res = file_tools.delete_file("notes.txt")
                self.assertFalse(res.success)
                self.assertIn("multiple files", res.response_text.lower())
                self.assertIn("which one", res.response_text.lower())

    def test_fast_intent_spoken_extensions_and_conversational_prefix(self):
        intent = ai_brain.fast_intent_match("delete notes dot txt.")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "delete_file")
        self.assertEqual(intent["query"], "notes.txt")

        intent_vscode = ai_brain.fast_intent_match("open main dot py")
        self.assertIsNotNone(intent_vscode)
        self.assertEqual(intent_vscode["action"], "open_in_vscode")
        self.assertEqual(intent_vscode["query"], "main.py")

        intent_prefix = ai_brain.fast_intent_match("No, open my project")
        self.assertIsNotNone(intent_prefix)
        self.assertEqual(intent_prefix["action"], "open_project_in_vscode")

    def test_location_first_parsing_and_creation(self):
        target, loc = file_tools.parse_location_spec("on my desktop named notes.txt")
        self.assertEqual(target, "notes.txt")
        self.assertEqual(loc, "desktop")

        target2, loc2 = file_tools.parse_location_spec("on my desktop called notes.txt")
        self.assertEqual(target2, "notes.txt")
        self.assertEqual(loc2, "desktop")

        target3, loc3 = file_tools.parse_location_spec("in downloads called report.pdf")
        self.assertEqual(target3, "report.pdf")
        self.assertEqual(loc3, "downloads")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch.dict(file_tools.STANDARD_DIRECTORIES, {"desktop": tmp_path}):
                res = file_tools.create_file("on my desktop named notes.txt", content="deskbot notes")
                self.assertTrue(res.success)
                self.assertTrue((tmp_path / "notes.txt").exists())
                self.assertIn("Created notes.txt on your Desktop", res.response_text)

    def test_anaphora_contextual_deletion(self):
        # Simulate previous turn where DeskBot created a file
        ai_brain._CONVERSATION_TURNS.clear()
        ai_brain._CONVERSATION_TURNS.append({
            "role": "assistant",
            "content": "Created notes.txt on your Desktop."
        })

        intent1 = ai_brain.fast_intent_match("delete the file that you just created.")
        self.assertIsNotNone(intent1)
        self.assertEqual(intent1["action"], "delete_file")
        self.assertEqual(intent1["query"], "notes.txt")

        intent2 = ai_brain.fast_intent_match("delete that file")
        self.assertIsNotNone(intent2)
        self.assertEqual(intent2["action"], "delete_file")
        self.assertEqual(intent2["query"], "notes.txt")

        intent3 = ai_brain.fast_intent_match("delete it")
        self.assertIsNotNone(intent3)
        self.assertEqual(intent3["action"], "delete_file")
        self.assertEqual(intent3["query"], "notes.txt")


if __name__ == "__main__":
    unittest.main()
