"""Modular developer mode capabilities and stubs for future DeskBot developer features.

Includes:
- capture_screen_context: Screenshot capture for multimodal analysis.
- read_active_file: Safely read file content within project workspace.
- run_tests: Subprocess runner for project unit tests with summary report.
- analyze_code: Basic AST structural analysis (functions, classes, imports, syntax).
"""

from __future__ import annotations

import ast
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from command_executor import ToolResult
from tools.file_tools import find_file_in_workspace, is_path_safe

logger = logging.getLogger(__name__)


def capture_screen_context(save_dir: Optional[Path] = None) -> ToolResult:
    """Capture a screenshot to disk for developer analysis or vision models."""
    try:
        from PIL import ImageGrab
    except ImportError:
        return ToolResult(
            False,
            "Pillow is not installed",
            "Screen capture is currently unavailable.",
        )

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


def read_active_file(target: str, max_lines: int = 200) -> ToolResult:
    """Safely read lines from a code file within the workspace."""
    clean_target = (target or "").strip()
    if not clean_target:
        return ToolResult(False, "Missing target filename", "Please specify which file you want to read.")

    resolved: Optional[Path] = None
    direct = Path(clean_target)
    if direct.is_absolute() and direct.exists() and is_path_safe(direct):
        resolved = direct
    else:
        resolved = find_file_in_workspace(clean_target)

    if not resolved or not resolved.exists() or not resolved.is_file():
        return ToolResult(
            False,
            f"File not found: {clean_target}",
            f"I couldn't locate '{clean_target}' in the project.",
        )

    if not is_path_safe(resolved):
        return ToolResult(False, "Path forbidden", "Reading system files is not allowed.")

    try:
        # Prevent reading overly massive binary/data files (>1MB)
        if resolved.stat().st_size > 1024 * 1024:
            return ToolResult(
                False,
                "File too large",
                f"'{resolved.name}' is too large to read into context.",
            )

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
                "total_lines": len(lines),
                "content": "\n".join(preview_lines),
            },
        )
    except Exception as err:
        logger.error("Failed to read file '%s': %s", resolved, err)
        return ToolResult(False, str(err), f"Could not read {resolved.name}.")


def run_tests(test_target: str = "") -> ToolResult:
    """Run project test suite deterministically using python -m unittest."""
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "companion/tests", "-v"]
    if test_target and test_target.strip():
        clean_t = test_target.strip()
        # If specific test module given
        if clean_t.endswith(".py"):
            clean_t = clean_t[:-3]
        clean_t = clean_t.replace("/", ".").replace("\\", ".")
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


def analyze_code(target: str) -> ToolResult:
    """Perform AST analysis on a Python file to report classes, functions, and syntax."""
    clean_target = (target or "").strip()
    if not clean_target:
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

        spoken = (
            f"{resolved.name} has {line_count} lines, "
            f"{len(classes)} classes, and {len(functions)} functions."
        )
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
