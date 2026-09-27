"""Structured rotating logging with secret redaction and log viewer launcher."""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
import subprocess
import sys
from pathlib import Path

from .paths import get_log_dir, get_log_file_path

API_KEY_REGEX = re.compile(r"\b(?:nvapi-|sk-)[a-zA-Z0-9_\-]{20,}\b", re.IGNORECASE)


class RedactingFilter(logging.Filter):
    """Filter that strips API keys and sensitive tokens before writing to logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = API_KEY_REGEX.sub("[REDACTED_API_KEY]", record.msg)
        if record.args:
            clean_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    clean_args.append(API_KEY_REGEX.sub("[REDACTED_API_KEY]", arg))
                else:
                    clean_args.append(arg)
            record.args = tuple(clean_args)
        return True


def setup_logging(debug: bool = False, to_console: bool = True) -> logging.Logger:
    """Initialize structured rotating file logging in platform AppData and console output."""
    log_dir = get_log_dir()
    log_file = get_log_file_path()

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Clear existing handlers to prevent duplicates
    root_logger.handlers.clear()

    redactor = RedactingFilter()

    # 1. Rotating File Handler (5 MB per file, keep 3 backups)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_file),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(redactor)
        file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        root_logger.addHandler(file_handler)
    except Exception as err:
        print(f"Warning: Could not set up rotating file log: {err}", file=sys.stderr)

    # 2. Console Handler (Standard Output)
    if to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = logging.Formatter("%(message)s")
        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(redactor)
        console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        root_logger.addHandler(console_handler)

    deskbot_logger = logging.getLogger("deskbot")
    deskbot_logger.info("DeskBot logging initialized. Log file: %s", log_file)
    return deskbot_logger


def open_log_file() -> bool:
    """Open the main log file in the operating system's default text viewer."""
    log_file = get_log_file_path()
    if not log_file.exists():
        log_file.write_text("DeskBot log file created.\n", encoding="utf-8")

    try:
        if sys.platform == "win32":
            os.startfile(str(log_file))
            return True
        elif sys.platform == "darwin":
            subprocess.run(["open", str(log_file)], check=False)
            return True
        else:
            subprocess.run(["xdg-open", str(log_file)], check=False)
            return True
    except Exception as err:
        logging.getLogger("deskbot").error("Could not open log viewer: %s", err)
        return False
