"""Developer Mode & Computer Assistance Tools for DeskBot.

Provides controlled, safe inspection and assistance for developer workflows:
- Phase 1: get_active_window, capture_screen_context, developer mode state.
- Phase 2: get_current_file, get_current_workspace, read_active_file.
- Phase 3: list_workspace_files, search_workspace.
- Phase 4: AST analyze_code, error inspection.
- Phase 5/6: Controlled patching (propose_patch, apply_patch, rollback_patch).
- Phase 7: run_tests test runner.

Strictly enforces workspace boundaries: no arbitrary shell or filesystem access.
"""

from __future__ import annotations

import ast
import difflib
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config
from command_executor import ToolResult
from tools.file_tools import find_file_in_workspace, is_path_safe

logger = logging.getLogger(__name__)

# Global Developer Mode state toggle
_DEVELOPER_MODE_ACTIVE = False

# In-memory storage for proposed patches awaiting user confirmation
_PENDING_PATCHES: Dict[str, Dict[str, Any]] = {}


def is_developer_mode() -> bool:
    """Return whether DeskBot Developer Mode is currently active."""
    return _DEVELOPER_MODE_ACTIVE


def set_developer_mode(enabled: bool) -> ToolResult:
    """Activate or deactivate DeskBot Developer Mode."""
    global _DEVELOPER_MODE_ACTIVE
    _DEVELOPER_MODE_ACTIVE = enabled
    status = "activated" if enabled else "deactivated"
    spoken = (
        "Developer Mode is now active. I'm ready to assist with your code and screen."
        if enabled
        else "Developer Mode is now off."
    )
    return ToolResult(True, f"Developer Mode {status}", spoken, data={"developer_mode": enabled})


# --- Phase 1: Screen & Active Window Awareness ---

def get_active_window() -> ToolResult:
    """Detect the currently active foreground window and application.

    Deterministic cross-platform implementation (Windows via Win32, macOS via System Events).
    """
    app_info: Dict[str, str] = {
        "application": "Unknown",
        "title": "Unknown",
        "process": "unknown",
    }

    if sys.platform == "win32":
        try:
            import win32gui
            import win32process
            import psutil

            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                title = win32gui.GetWindowText(hwnd) or ""
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc_name = psutil.Process(pid).name() if pid else "unknown"

                app_name = proc_name
                if "code" in proc_name.lower():
                    app_name = "Visual Studio Code"
                elif "chrome" in proc_name.lower():
                    app_name = "Google Chrome"
                elif "explorer" in proc_name.lower():
                    app_name = "File Explorer"
                elif "terminal" in proc_name.lower() or "cmd" in proc_name.lower() or "powershell" in proc_name.lower():
                    app_name = "Terminal"

                app_info = {
                    "application": app_name,
                    "title": title,
                    "process": proc_name,
                }
        except Exception as err:
            logger.debug("Win32 get_active_window error: %s", err)

    elif sys.platform == "darwin":
        try:
            # 1. Fast, permission-free frontmost application path
            cmd = ["osascript", "-e", "return (path to frontmost application as text)"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0)
            if proc.returncode == 0 and proc.stdout.strip():
                raw = proc.stdout.strip().rstrip(":")
                raw_name = re.split(r"[:/]", raw)[-1]
                if raw_name.endswith(".app"):
                    raw_name = raw_name[:-4]

                app_info["application"] = raw_name
                app_info["process"] = f"{raw_name}.app"
                app_info["title"] = raw_name

            # 2. Window title inspection if available
            title_cmd = [
                "osascript",
                "-e",
                'tell application "System Events" to set t to name of front window of (first application process whose frontmost is true)',
                "-e",
                "return t",
            ]
            t_proc = subprocess.run(title_cmd, capture_output=True, text=True, timeout=1.5)
            if t_proc.returncode == 0 and t_proc.stdout.strip():
                app_info["title"] = t_proc.stdout.strip()
        except Exception as err:
            logger.debug("macOS get_active_window error: %s", err)

    spoken = f"You are currently in {app_info['application']}."
    if app_info["title"] and app_info["title"] != app_info["application"]:
        spoken += f" Window: {app_info['title']}."

    return ToolResult(True, f"Active app: {app_info['application']}", spoken, data=app_info)


def capture_screen_context(save_dir: Optional[Path] = None) -> ToolResult:
    """Capture a screenshot to disk on-demand for visual analysis (never continuous)."""
    try:
        from PIL import ImageGrab
    except ImportError:
        return ToolResult(False, "Pillow is not installed", "Screen capture is currently unavailable.")

    output_dir = save_dir or (config.WORKSPACE_ROOT / "screenshots")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"capture_{int(time.time())}.png"
        filepath = output_dir / filename

        screenshot = ImageGrab.grab()
        screenshot.save(str(filepath))

        return ToolResult(
            True,
            f"Screen captured to {filepath}",
            "I've captured your screen for analysis.",
            data={"filepath": str(filepath), "timestamp": time.time()},
        )
    except Exception as err:
        logger.error("Screen capture failed: %s", err)
        return ToolResult(False, str(err), "Could not capture the screen.")


# --- Phase 2: VS Code & Current File Awareness ---

def get_current_file() -> ToolResult:
    """Identify the currently active/edited file from VS Code or active window metadata."""
    win_res = get_active_window()
    title = (win_res.data.get("title") or "") if win_res.data else ""

    # Parse filename from common VS Code title patterns:
    # "main.cpp — deskbot — Visual Studio Code"
    # "● continuous_assistant.py — deskbot"
    # "ai_brain.py - Visual Studio Code"
    candidate_filename = ""
    clean_title = re.sub(r"^[●*]\s*", "", title).strip()

    # Split by em-dash or hyphen
    parts = re.split(r"\s+[—–-]\s+", clean_title)
    if parts:
        first = parts[0].strip()
        # Does it look like a filename? (has extension like .py, .cpp, .h, .md, .json)
        if re.search(r"\.[a-zA-Z0-9_]+$", first):
            candidate_filename = first

    resolved: Optional[Path] = None
    if candidate_filename:
        resolved = find_file_in_workspace(candidate_filename)

    if resolved and resolved.is_file():
        rel_path = resolved.relative_to(config.WORKSPACE_ROOT)
        data = {
            "filename": resolved.name,
            "filepath": str(resolved),
            "relative_path": str(rel_path),
            "workspace": str(config.WORKSPACE_ROOT),
        }
        return ToolResult(
            True,
            f"Active file: {rel_path}",
            f"You are currently working on {resolved.name}.",
            data=data,
        )

    return ToolResult(
        False,
        "No active code file detected",
        f"I can see you're in {win_res.data.get('application', 'an application')}, but couldn't identify the active code file.",
        data={"title": title},
    )


def get_current_workspace() -> ToolResult:
    """Return the bounded workspace root for the current project."""
    ws = config.WORKSPACE_ROOT
    name = ws.name
    data = {
        "workspace_root": str(ws),
        "name": name,
        "exists": ws.exists(),
    }
    return ToolResult(
        True,
        f"Workspace: {name}",
        f"The current project workspace is {name}.",
        data=data,
    )


def read_active_file(target: str = "", max_lines: int = 200) -> ToolResult:
    """Safely read lines from a code file within the workspace (prefers actual file over OCR)."""
    clean_target = (target or "").strip()

    # If no target specified, attempt resolving the currently active file from VS Code
    if not clean_target:
        cur = get_current_file()
        if cur.success and cur.data and "filepath" in cur.data:
            clean_target = cur.data["filepath"]
        else:
            return ToolResult(False, "Missing target filename", "Please specify which file you want to read.")

    resolved: Optional[Path] = None
    direct = Path(clean_target)
    if direct.is_absolute() and direct.exists() and is_path_safe(direct):
        resolved = direct
    else:
        resolved = find_file_in_workspace(clean_target)

    if not resolved or not resolved.exists() or not resolved.is_file():
        return ToolResult(False, f"File not found: {clean_target}", f"I couldn't locate '{clean_target}' in the project.")

    if not is_path_safe(resolved):
        return ToolResult(False, "Path forbidden", "Reading system files is not allowed.")

    try:
        # Enforce 1MB safety size cap
        if resolved.stat().st_size > 1024 * 1024:
            return ToolResult(False, "File too large", f"'{resolved.name}' is too large to read into context.")

        content = resolved.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        truncated = len(lines) > max_lines
        preview_lines = lines[:max_lines]

        summary = f"Read {len(preview_lines)} lines from {resolved.name}"
        if truncated:
            summary += f" (truncated from {len(lines)} total lines)"

        return ToolResult(
            True,
            summary,
            f"Here is {resolved.name}. It has {len(lines)} lines.",
            data={
                "filepath": str(resolved),
                "filename": resolved.name,
                "total_lines": len(lines),
                "content": "\n".join(preview_lines),
            },
        )
    except Exception as err:
        logger.error("Failed to read file '%s': %s", resolved, err)
        return ToolResult(False, str(err), f"Could not read {resolved.name}.")


# --- Phase 3: Workspace Intelligence ---

IGNORED_DIRECTORIES = {
    ".git", ".venv", "venv", "__pycache__", ".pio", ".vscode", "node_modules", "build", "dist"
}


def list_workspace_files(extension: str = "") -> ToolResult:
    """List safe project files within the bounded workspace root."""
    root = config.WORKSPACE_ROOT
    if not root.exists():
        return ToolResult(False, "Workspace root not found", "Could not locate the project workspace.")

    ext_filter = extension.lower().strip()
    if ext_filter and not ext_filter.startswith("."):
        ext_filter = f".{ext_filter}"

    found_files: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Exclude hidden and build directories
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRECTORIES and not d.startswith(".")]

        for fn in filenames:
            if fn.startswith("."):
                continue
            if ext_filter and not fn.lower().endswith(ext_filter):
                continue
            rel = Path(dirpath, fn).relative_to(root)
            found_files.append(str(rel))

    found_files.sort()
    count = len(found_files)
    sample = found_files[:10]
    spoken = f"Found {count} files in the workspace."
    if count > 0:
        spoken += f" Including {', '.join(Path(f).name for f in sample[:3])}."

    return ToolResult(
        True,
        f"Found {count} workspace files",
        spoken,
        data={"total_files": count, "files": found_files},
    )


def search_workspace(query: str, max_results: int = 15) -> ToolResult:
    """Search for symbols, function names, or text across the project workspace."""
    clean_query = (query or "").strip()
    if not clean_query:
        return ToolResult(False, "Missing search query", "What would you like me to search for in the codebase?")

    root = config.WORKSPACE_ROOT
    matches: List[Dict[str, Any]] = []

    pattern = re.compile(re.escape(clean_query), re.IGNORECASE)

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRECTORIES and not d.startswith(".")]

        for fn in filenames:
            if fn.startswith(".") or fn.endswith((".pyc", ".png", ".jpg", ".bin", ".wav", ".elf")):
                continue
            file_path = Path(dirpath, fn)
            try:
                if file_path.stat().st_size > 512 * 1024:
                    continue
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for line_idx, line in enumerate(content.splitlines(), start=1):
                    if pattern.search(line):
                        rel = str(file_path.relative_to(root))
                        matches.append({
                            "file": rel,
                            "line": line_idx,
                            "content": line.strip()[:100],
                        })
                        if len(matches) >= max_results:
                            break
            except Exception:
                pass
        if len(matches) >= max_results:
            break

    if not matches:
        return ToolResult(
            True,
            f"No matches for '{clean_query}'",
            f"I couldn't find any occurrences of '{clean_query}' in the project.",
            data={"query": clean_query, "matches": []},
        )

    matched_files = list(dict.fromkeys(m["file"] for m in matches))
    files_spoken = ", ".join(Path(f).name for f in matched_files[:3])
    spoken = f"I found {len(matches)} occurrences of '{clean_query}' in {len(matched_files)} files, including {files_spoken}."

    return ToolResult(
        True,
        f"Found {len(matches)} matches",
        spoken,
        data={"query": clean_query, "matches": matches, "files": matched_files},
    )


# --- Phase 4 & 5: Code Understanding & AST Analysis ---

def analyze_code(target: str = "") -> ToolResult:
    """Perform AST analysis on a Python file to report classes, functions, and syntax."""
    clean_target = (target or "").strip()
    if not clean_target:
        cur = get_current_file()
        if cur.success and cur.data and "filepath" in cur.data:
            clean_target = cur.data["filepath"]
        else:
            return ToolResult(False, "Missing filename", "Please specify which file you want to analyze.")

    resolved = find_file_in_workspace(clean_target)
    if not resolved:
        direct = Path(clean_target)
        if direct.exists() and is_path_safe(direct):
            resolved = direct

    if not resolved or not resolved.exists() or not resolved.is_file():
        return ToolResult(False, f"File not found: {clean_target}", f"Could not find '{clean_target}'.")

    if not resolved.name.endswith(".py"):
        return ToolResult(
            True,
            f"Non-python file {resolved.name}",
            f"'{resolved.name}' is not a Python source file, skipping AST analysis.",
        )

    try:
        source = resolved.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(resolved))

        classes: List[str] = []
        functions: List[str] = []
        imports: List[str] = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    imports.append(f"{mod}.{alias.name}")

        line_count = len(source.splitlines())
        analysis_data = {
            "file": resolved.name,
            "line_count": line_count,
            "classes": classes,
            "functions": functions,
            "imports": imports,
        }

        spoken = f"{resolved.name} has {line_count} lines, {len(classes)} classes, and {len(functions)} functions."
        return ToolResult(True, f"Analyzed {resolved.name}", spoken, data=analysis_data)
    except SyntaxError as syn_err:
        return ToolResult(
            False,
            f"SyntaxError in {resolved.name}: {syn_err.msg} at line {syn_err.lineno}",
            f"Syntax error found in {resolved.name} on line {syn_err.lineno}: {syn_err.msg}.",
        )
    except Exception as err:
        logger.error("Failed to analyze code '%s': %s", resolved, err)
        return ToolResult(False, str(err), f"Could not analyze {resolved.name}.")


# --- Phase 6 & 7: Controlled Patching & Verification ---

def propose_patch(file_spec: str, old_code: str, new_code: str) -> ToolResult:
    """Propose a code modification and stage it for explicit user confirmation.

    Never modifies files without user approval.
    """
    clean_target = (file_spec or "").strip()
    if not clean_target:
        cur = get_current_file()
        if cur.success and cur.data and "filepath" in cur.data:
            clean_target = cur.data["filepath"]
        else:
            return ToolResult(False, "Missing file target", "Which file should I propose changes to?")

    resolved = find_file_in_workspace(clean_target)
    if not resolved:
        direct = Path(clean_target)
        if direct.exists() and is_path_safe(direct):
            resolved = direct

    if not resolved or not resolved.exists() or not resolved.is_file():
        return ToolResult(False, f"File not found: {clean_target}", f"I couldn't find '{clean_target}' in the project.")

    if not is_path_safe(resolved):
        return ToolResult(False, "Path forbidden", "Modifying system files is strictly prohibited.")

    content = resolved.read_text(encoding="utf-8", errors="replace")
    if old_code not in content:
        return ToolResult(
            False,
            "Target code chunk not found in file",
            f"I couldn't locate the exact original code inside {resolved.name}. The file may have changed.",
        )

    # Generate unified diff
    diff_lines = list(difflib.unified_diff(
        old_code.splitlines(keepends=True),
        new_code.splitlines(keepends=True),
        fromfile=f"a/{resolved.name}",
        tofile=f"b/{resolved.name}",
    ))
    diff_text = "".join(diff_lines)

    patch_id = f"patch_{int(time.time())}"
    _PENDING_PATCHES[patch_id] = {
        "file_path": str(resolved),
        "old_code": old_code,
        "new_code": new_code,
        "diff": diff_text,
    }

    spoken = (
        f"I've prepared a patch for {resolved.name}. "
        "Should I apply this change?"
    )

    return ToolResult(
        True,
        f"Patch {patch_id} staged for {resolved.name}",
        spoken,
        data={
            "confirmation_required": True,
            "action": "apply_patch",
            "patch_id": patch_id,
            "file": resolved.name,
            "diff": diff_text,
        },
    )


def apply_patch(patch_id: str = "") -> ToolResult:
    """Apply a confirmed staged patch after creating a safe reversible backup."""
    global _PENDING_PATCHES

    # If no patch_id given, take the most recent staged patch
    if not patch_id:
        if not _PENDING_PATCHES:
            return ToolResult(False, "No pending patch", "There are no pending code changes to apply.")
        patch_id = list(_PENDING_PATCHES.keys())[-1]

    patch_entry = _PENDING_PATCHES.pop(patch_id, None)
    if not patch_entry:
        return ToolResult(False, f"Unknown patch: {patch_id}", "The requested patch could not be found.")

    target_path = Path(patch_entry["file_path"])
    if not target_path.exists() or not is_path_safe(target_path):
        return ToolResult(False, "File unavailable or forbidden", "Target file is no longer accessible.")

    # 1. Create reversible backup
    backup_path = target_path.with_suffix(target_path.suffix + ".backup")
    try:
        current_content = target_path.read_text(encoding="utf-8")
        backup_path.write_text(current_content, encoding="utf-8")
    except Exception as b_err:
        return ToolResult(False, f"Backup creation failed: {b_err}", "Could not create safety backup before editing.")

    # 2. Check for patch conflict (ensure old_code is still present)
    if patch_entry["old_code"] not in current_content:
        return ToolResult(
            False,
            "PATCH_CONFLICT: Original content modified",
            f"The contents of {target_path.name} changed since the patch was created. Aborted.",
        )

    # 3. Apply single replacement
    new_content = current_content.replace(patch_entry["old_code"], patch_entry["new_code"], 1)

    # 4. If python, verify syntax before writing
    if target_path.suffix.lower() == ".py":
        try:
            ast.parse(new_content, filename=str(target_path))
        except SyntaxError as syn:
            return ToolResult(
                False,
                f"Patch resulted in syntax error: {syn.msg}",
                f"Patch aborted: applying this change causes a syntax error on line {syn.lineno}.",
            )

    try:
        target_path.write_text(new_content, encoding="utf-8")
        return ToolResult(
            True,
            f"Successfully patched {target_path.name}",
            f"I have updated {target_path.name}. A backup was saved in case we need to roll back.",
            data={"file": str(target_path), "backup": str(backup_path)},
        )
    except Exception as write_err:
        # Rollback immediately
        try:
            target_path.write_text(current_content, encoding="utf-8")
        except Exception:
            pass
        return ToolResult(False, str(write_err), f"Failed to write patch to {target_path.name}.")


def rollback_patch(file_spec: str = "") -> ToolResult:
    """Roll back the last change made to a file using its .backup copy."""
    clean_target = (file_spec or "").strip()
    if not clean_target:
        cur = get_current_file()
        if cur.success and cur.data and "filepath" in cur.data:
            clean_target = cur.data["filepath"]
        else:
            return ToolResult(False, "Missing file target", "Which file should I roll back?")

    resolved = find_file_in_workspace(clean_target)
    if not resolved:
        direct = Path(clean_target)
        if direct.exists() and is_path_safe(direct):
            resolved = direct

    if not resolved:
        return ToolResult(False, f"File not found: {clean_target}", f"Could not find '{clean_target}'.")

    backup_path = resolved.with_suffix(resolved.suffix + ".backup")
    if not backup_path.exists():
        return ToolResult(
            False,
            f"No backup found for {resolved.name}",
            f"I don't have a recent backup for {resolved.name} to restore.",
        )

    try:
        backup_content = backup_path.read_text(encoding="utf-8")
        resolved.write_text(backup_content, encoding="utf-8")
        backup_path.unlink(missing_ok=True)
        return ToolResult(
            True,
            f"Rolled back {resolved.name}",
            f"I've restored {resolved.name} from its previous backup.",
        )
    except Exception as err:
        return ToolResult(False, str(err), f"Could not roll back {resolved.name}: {err}.")


# --- Phase 7: Test Runner ---

def run_tests(test_target: str = "") -> ToolResult:
    """Run project test suite deterministically using python -m unittest."""
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "companion/tests", "-v"]
    if test_target and test_target.strip():
        clean_t = test_target.strip()
        if clean_t.endswith(".py"):
            clean_t = clean_t[:-3]
        clean_t = clean_t.replace("/", ".").replace("\\", ".")
        if clean_t.startswith("tests."):
            clean_t = f"companion.{clean_t}"
        elif not clean_t.startswith("companion.tests.") and not clean_t.startswith("companion."):
            clean_t = f"companion.tests.{clean_t}"
        cmd = [sys.executable, "-m", "unittest", clean_t, "-v"]

    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(config.WORKSPACE_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
        )
        duration = round(time.perf_counter() - start, 2)
        output = proc.stdout or ""

        success = proc.returncode == 0
        if success:
            return ToolResult(
                True,
                f"Tests passed in {duration}s",
                f"All tests passed successfully in {duration} seconds.",
                data={"output": output, "duration": duration, "returncode": proc.returncode},
            )
        else:
            return ToolResult(
                False,
                f"Tests failed in {duration}s",
                f"Tests finished with failures in {duration} seconds.",
                data={"output": output, "duration": duration, "returncode": proc.returncode},
            )
    except subprocess.TimeoutExpired:
        return ToolResult(False, "Test run timed out after 60 seconds", "Test suite execution timed out.")
    except Exception as err:
        logger.error("Test execution failed: %s", err)
        return ToolResult(False, str(err), "Could not execute the test suite.")
