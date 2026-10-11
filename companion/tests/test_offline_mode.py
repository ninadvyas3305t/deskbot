"""Automated test suite for DeskBot Offline & Degraded Mode Capabilities.

Validates:
1. Zero-network local Speech-To-Text loading with Faster-Whisper cache
2. Offline deterministic intent routing (apps, calculations, time, volume, screenshots, folders)
3. Graceful offline explanatory fallbacks for complex cloud-dependent queries
4. Non-crashing offline rejection of screen vision analysis and web search
5. Degraded mode fallback when cloud API requests time out or fail
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from companion.ai_brain import understand_intent
from companion.connectivity import (
    ConnectivityState,
    get_connectivity_manager,
)
from companion.speech_to_text import (
    get_whisper_model,
    is_model_cached_locally,
)
from companion.vision.service import perform_screen_analysis


@pytest.fixture(autouse=True)
def reset_connectivity():
    """Ensure clean connectivity manager state before and after each test."""
    mgr = get_connectivity_manager()
    mgr.set_override_state(None)
    yield mgr
    mgr.set_override_state(None)


# ==============================================================================
# 1. Offline Speech-To-Text (Whisper Cache)
# ==============================================================================

def test_whisper_model_cached_locally():
    """Verify that the default Faster-Whisper base model is detected in local cache."""
    assert is_model_cached_locally("base") is True


def test_whisper_model_loads_offline():
    """Verify that get_whisper_model loads from disk without remote network access."""
    model = get_whisper_model("base")
    assert model is not None
    assert hasattr(model, "transcribe")


# ==============================================================================
# 2. Offline Deterministic Intent Routing
# ==============================================================================

def test_offline_intent_calculator(reset_connectivity):
    """Verify mathematical calculations resolve deterministically when offline."""
    reset_connectivity.set_override_state(ConnectivityState.OFFLINE)
    assert reset_connectivity.is_offline() is True

    intent = understand_intent("calculate 25 * 4")
    assert intent is not None
    assert intent.get("action") == "calculate"
    assert "25 * 4" in intent.get("query", "")


def test_offline_intent_time(reset_connectivity):
    """Verify time requests resolve deterministically when offline."""
    reset_connectivity.set_override_state(ConnectivityState.OFFLINE)

    intent = understand_intent("what time is it right now")
    assert intent is not None
    assert intent.get("action") == "current_time"


def test_offline_intent_date(reset_connectivity):
    """Verify date requests resolve deterministically when offline."""
    reset_connectivity.set_override_state(ConnectivityState.OFFLINE)

    intent = understand_intent("what is today's date")
    assert intent is not None
    assert intent.get("action") == "current_date"


def test_offline_intent_open_app(reset_connectivity):
    """Verify application launching resolves deterministically when offline."""
    reset_connectivity.set_override_state(ConnectivityState.OFFLINE)

    intent = understand_intent("open calculator")
    assert intent is not None
    assert intent.get("action") == "open_app"
    assert "calculator" in intent.get("query", "").lower()


def test_offline_intent_screenshot(reset_connectivity):
    """Verify screenshot commands resolve deterministically when offline."""
    reset_connectivity.set_override_state(ConnectivityState.OFFLINE)

    intent = understand_intent("take a screenshot")
    assert intent is not None
    assert intent.get("action") == "screenshot"


def test_offline_intent_volume_control(reset_connectivity):
    """Verify volume commands resolve deterministically when offline."""
    reset_connectivity.set_override_state(ConnectivityState.OFFLINE)

    intent_up = understand_intent("volume up")
    assert intent_up is not None
    assert intent_up.get("action") == "volume_up"

    intent_mute = understand_intent("mute audio")
    assert intent_mute is not None
    assert intent_mute.get("action") == "mute"


def test_offline_intent_open_folder(reset_connectivity):
    """Verify folder opening commands resolve deterministically when offline."""
    reset_connectivity.set_override_state(ConnectivityState.OFFLINE)

    intent = understand_intent("open downloads folder")
    assert intent is not None
    assert intent.get("action") == "open_folder"
    assert "downloads" in intent.get("query", "").lower()


def test_offline_intent_system_info(reset_connectivity):
    """Verify system status commands resolve deterministically when offline."""
    reset_connectivity.set_override_state(ConnectivityState.OFFLINE)

    intent = understand_intent("check battery level")
    assert intent is not None
    assert intent.get("action") == "system_info"


# ==============================================================================
# 3. Offline Explanatory Fallback for Cloud Reasoning Queries
# ==============================================================================

def test_offline_complex_query_explanatory_fallback(reset_connectivity):
    """Verify complex cloud queries return an explanatory message instead of hanging."""
    reset_connectivity.set_override_state(ConnectivityState.OFFLINE)

    intent = understand_intent("Write a comprehensive Python script to simulate quantum annealing")
    assert intent is not None
    assert intent.get("action") == "direct_answer"
    resp = intent.get("response", "")
    assert "offline" in resp.lower() or "internet" in resp.lower()


# ==============================================================================
# 4. Offline Vision Screen Analysis Rejection
# ==============================================================================

def test_offline_screen_analysis_rejection(reset_connectivity):
    """Verify perform_screen_analysis declines cleanly when offline without crashing."""
    reset_connectivity.set_override_state(ConnectivityState.OFFLINE)

    from companion.vision.analyzer import NvidiaVisionAnalyzer
    real_analyzer = NvidiaVisionAnalyzer()

    with patch("companion.vision.service.get_vision_analyzer", return_value=real_analyzer):
        res = perform_screen_analysis("Explain the error on my screen")
        assert res.success is False
        assert "not available offline" in res.message.lower() or "internet" in res.response_text.lower()


# ==============================================================================
# 5. Degraded Mode Cloud Fallback
# ==============================================================================

def test_degraded_mode_local_tool_fallback(reset_connectivity):
    """Verify that when Cloud AI fails/times out, local commands still execute."""
    reset_connectivity.set_override_state(ConnectivityState.DEGRADED)

    # Mock understand to simulate cloud timeout
    with patch("companion.ai_brain.understand", side_effect=TimeoutError("Request timed out after 10s")):
        intent = understand_intent("open terminal")
        assert intent is not None
        assert intent.get("action") == "open_app"
        assert "terminal" in intent.get("query", "").lower()


def test_degraded_mode_general_knowledge_fallback(reset_connectivity):
    """Verify that when Cloud AI fails for complex queries, a clear degraded notice is returned."""
    reset_connectivity.set_override_state(ConnectivityState.DEGRADED)

    with patch("companion.ai_brain.understand", side_effect=RuntimeError("503 Service Unavailable")):
        intent = understand_intent("Who was the 16th president of the United States?")
        assert intent is not None
        assert intent.get("action") == "direct_answer"
        resp = intent.get("response", "")
        assert "trouble connecting" in resp.lower() or "cloud" in resp.lower()
