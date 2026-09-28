"""Tests for macOS permission verification, in-process screen capture, and stable app identity."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from companion.command_executor import REGISTRY, execute_intent
from companion.platform_layer.permissions import (
    check_microphone_permission,
    check_screen_recording_permission,
    get_permissions_summary,
    has_microphone_permission,
    has_screen_capture_permission,
    open_microphone_settings,
    open_screen_recording_settings,
    request_screen_capture_permission,
)
from companion.vision.screen_capture import (
    _capture_macos_in_process,
    capture_raw_screen,
    capture_screen,
)


def test_has_screen_capture_permission():
    """Verify has_screen_capture_permission returns a boolean without prompting."""
    result = has_screen_capture_permission()
    assert isinstance(result, bool)


def test_has_microphone_permission():
    """Verify has_microphone_permission returns a boolean without blocking."""
    result = has_microphone_permission()
    assert isinstance(result, bool)


def test_permissions_summary_structure():
    """Verify get_permissions_summary returns comprehensive dictionary."""
    summary = get_permissions_summary()
    assert "microphone" in summary
    assert "screen_recording" in summary
    assert "system_audio" in summary

    assert isinstance(summary["microphone"]["granted"], bool)
    assert isinstance(summary["screen_recording"]["granted"], bool)
    assert summary["system_audio"]["granted"] is True
    assert "Not required" in summary["system_audio"]["description"]


def test_legacy_permission_checks():
    """Verify backward compatibility of check_microphone_permission and check_screen_recording_permission."""
    has_mic, mic_msg = check_microphone_permission()
    assert isinstance(has_mic, bool)
    assert isinstance(mic_msg, str) and len(mic_msg) > 0

    has_scr, scr_msg = check_screen_recording_permission()
    assert isinstance(has_scr, bool)
    assert isinstance(scr_msg, str) and len(scr_msg) > 0


@patch("subprocess.Popen")
def test_open_settings_invocations(mock_popen):
    """Verify settings openers invoke the respective macOS/Windows preferences URL."""
    mock_popen.return_value = MagicMock()

    ok_scr = open_screen_recording_settings()
    assert ok_scr is True
    assert mock_popen.called

    mock_popen.reset_mock()
    ok_mic = open_microphone_settings()
    assert ok_mic is True
    assert mock_popen.called


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS in-process CoreGraphics capture test")
def test_capture_macos_in_process_no_subprocess():
    """Verify _capture_macos_in_process captures in-process without spawning any subprocesses."""
    with patch("subprocess.run") as mock_run, patch("subprocess.Popen") as mock_popen:
        img = _capture_macos_in_process()
        # Verify no helper binaries like /usr/sbin/screencapture were called
        mock_run.assert_not_called()
        mock_popen.assert_not_called()

        if has_screen_capture_permission():
            assert img is not None
            assert isinstance(img, Image.Image)
            assert img.width > 0
            assert img.height > 0
            assert img.mode in ("RGB", "RGBA")


def test_capture_screen_result():
    """Verify capture_screen produces an optimized ScreenCaptureResult."""
    if sys.platform == "darwin" and not has_screen_capture_permission():
        pytest.skip("Screen recording permission not granted on this machine.")

    res = capture_screen(max_dimension=512)
    assert res is not None
    assert max(res.width, res.height) <= 512
    assert len(res.base64_data) > 0
    assert res.data_uri.startswith("data:image/jpeg;base64,")


def test_screenshot_tool_execution(tmp_path, monkeypatch):
    """Verify screenshot tool saves directly to Desktop directory."""
    if sys.platform == "darwin" and not has_screen_capture_permission():
        pytest.skip("Screen recording permission not granted on this machine.")

    fake_desktop = tmp_path / "Desktop"
    fake_desktop.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    result = REGISTRY.execute("screenshot")
    assert result.success is True
    assert "saved to your desktop" in result.response_text.lower() or "desktop" in result.message.lower()

    # Verify screenshot file exists in fake Desktop directory
    saved_files = list(fake_desktop.glob("DeskBot_Screenshot_*.png"))
    assert len(saved_files) >= 1
    assert saved_files[0].stat().st_size > 0


@pytest.mark.skipif(sys.platform != "darwin", reason="Codesign designated requirement test")
def test_deskbot_app_designated_requirement():
    """Verify dist/DeskBot.app designated requirement is stable identifier and not pinned to cdhash."""
    import subprocess
    app_path = Path("dist/DeskBot.app")
    if not app_path.exists():
        pytest.skip("dist/DeskBot.app has not been built yet.")

    res = subprocess.run(
        ["codesign", "-d", "-r-", str(app_path)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    output = res.stdout + res.stderr
    assert 'identifier "com.deskbot.assistant"' in output
    assert "cdhash" not in output, f"Designated requirement must NOT be pinned to volatile cdhash: {output}"
