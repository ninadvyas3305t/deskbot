"""Tests for DeskBot scalable animated face engine."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from companion.ui.face_engine import DeskBotFaceWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_face_widget_initialization(qapp):
    face = DeskBotFaceWidget()
    assert face.current_state == "IDLE"
    assert face.minimumWidth() >= 200
    assert face.minimumHeight() >= 100


def test_face_state_transitions(qapp):
    face = DeskBotFaceWidget()

    states = [
        "LISTENING",
        "TRANSCRIBING",
        "THINKING",
        "SCREEN_ANALYSIS",
        "EXECUTING",
        "SPEAKING",
        "ERROR",
        "SLEEPY",
        "IDLE",
    ]

    for st in states:
        face.set_assistant_state(st)
        assert face.current_state == st


def test_face_audio_level_reactivity(qapp):
    face = DeskBotFaceWidget()
    face.set_audio_level(0.75)
    assert face._audio_level == 0.75

    # Out of bounds clamping
    face.set_audio_level(1.5)
    assert face._audio_level == 1.0
    face.set_audio_level(-0.5)
    assert face._audio_level == 0.0


def test_face_widget_render_paint(qapp):
    face = DeskBotFaceWidget()
    face.resize(320, 180)

    # Render into an off-screen QImage buffer to verify paintEvent runs cleanly
    img = QImage(320, 180, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    face.render(img)

    assert img.width() == 320
    assert img.height() == 180


def test_mochi_happy_arc_and_thinking_asymmetry(qapp):
    face = DeskBotFaceWidget()

    # FOLLOW_UP triggers Mochi happy smiling crescents (^ ^)
    face.set_assistant_state("FOLLOW_UP")
    assert face.current_state == "FOLLOW_UP"
    assert face._tgt_left.is_arc is True
    assert face._tgt_right.is_arc is True

    # SUCCESS triggers Mochi happy smiling crescents
    face.set_assistant_state("SUCCESS")
    assert face.current_state == "SUCCESS"
    assert face._tgt_left.is_arc is True
    assert face._tgt_right.is_arc is True

    # Render smiling crescents off-screen
    img = QImage(320, 180, QImage.Format_ARGB32_Premultiplied)
    face.render(img)

    # THINKING triggers inquisitive asymmetric eye heights
    face.set_assistant_state("THINKING")
    assert face._tgt_left.is_arc is False
    assert face._tgt_left.height < face._tgt_right.height
    face.render(img)
