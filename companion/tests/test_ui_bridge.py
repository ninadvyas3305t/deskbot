"""Tests for DeskBotBridge signal routing and state synchronization."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication

from companion.assistant.state_machine import AssistantState, AssistantStateMachine
from companion.ui.bridge import DeskBotBridge, get_ui_bridge


@pytest.fixture(scope="session")
def qapp():
    """Ensure QApplication instance exists for Qt signals."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def test_bridge_singleton(qapp):
    b1 = get_ui_bridge()
    b2 = get_ui_bridge()
    assert b1 is b2
    assert isinstance(b1, DeskBotBridge)


def test_bridge_state_change_signal(qapp):
    bridge = DeskBotBridge()
    received = []

    def on_change(old_s, new_s, ctx):
        received.append((old_s, new_s, ctx))

    bridge.state_changed.connect(on_change)
    bridge.notify_state_change("IDLE", "LISTENING", "User said wake word")

    assert len(received) == 1
    assert received[0] == ("IDLE", "LISTENING", "User said wake word")
    assert bridge.current_state == "LISTENING"


def test_bridge_transcript_and_intent_signals(qapp):
    bridge = DeskBotBridge()
    transcripts = []
    intents = []

    bridge.transcript_received.connect(transcripts.append)
    bridge.ai_intent_resolved.connect(lambda a, q: intents.append((a, q)))

    bridge.notify_transcript("Open Calculator")
    bridge.notify_ai_intent("open_app", "Calculator")

    assert transcripts == ["Open Calculator"]
    assert intents == [("open_app", "Calculator")]


def test_bridge_device_status(qapp):
    bridge = DeskBotBridge()
    statuses = []

    bridge.device_status_changed.connect(lambda conn, port, desc: statuses.append((conn, port, desc)))
    bridge.notify_device_status(True, "/dev/cu.usbmodem123", "ESP32-S3")

    assert len(statuses) == 1
    assert statuses[0] == (True, "/dev/cu.usbmodem123", "ESP32-S3")
    assert bridge.is_device_connected is True


def test_state_machine_bridge_integration(qapp):
    sm = AssistantStateMachine(wake_word_name="Hey Jarvis")
    bridge = get_ui_bridge()

    states = []
    bridge.state_changed.connect(lambda old, new, ctx: states.append(new))

    sm.on_wake(0.85)
    sm.on_transcript("Hello DeskBot")
    sm.on_ai_action("direct_answer")
    sm.transition_to(AssistantState.IDLE)

    assert "LISTENING" in states
    assert "IDLE" in states
