"""Home view featuring the central animated DeskBot face, state pill, and transcript card."""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.bridge import DeskBotBridge, get_ui_bridge
from ui.face_engine import DeskBotFaceWidget
from ui.theme import (
    COLOR_ACCENT_CYAN,
    COLOR_ACCENT_MINT,
    COLOR_BORDER,
    COLOR_SURFACE,
    COLOR_SURFACE_ELEVATED,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
)


class HomeView(QWidget):
    """Primary home screen centered around the animated face and real-time conversation."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.bridge: DeskBotBridge = get_ui_bridge()
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # 1. State Banner / Status Header
        status_bar = QHBoxLayout()
        status_bar.setSpacing(10)

        self.lbl_greeting = QLabel("DeskBot Assistant")
        self.lbl_greeting.setStyleSheet("font-size: 18px; font-weight: 700; color: #FFFFFF;")
        status_bar.addWidget(self.lbl_greeting)

        status_bar.addStretch()

        self.pill_state = QLabel("● IDLE")
        self.pill_state.setProperty("class", "StatusPill StatusPillReady")
        self.pill_state.setStyleSheet(
            "background-color: rgba(0, 230, 118, 0.12); color: #00E676; "
            "border: 1px solid rgba(0, 230, 118, 0.28); "
            "border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: 600;"
        )
        status_bar.addWidget(self.pill_state)

        layout.addLayout(status_bar)

        # 2. Central Face Stage Container (Sleek dark visor housing)
        face_frame = QFrame()
        face_frame.setObjectName("FaceStage")
        face_frame.setStyleSheet(
            "background-color: #06090F; border: 1px solid #141C2B; "
            "border-radius: 18px; padding: 6px;"
        )
        face_layout = QVBoxLayout(face_frame)
        face_layout.setContentsMargins(6, 6, 6, 6)

        self.face_widget = DeskBotFaceWidget()
        face_layout.addWidget(self.face_widget, alignment=Qt.AlignCenter)

        layout.addWidget(face_frame, stretch=3)

        # 3. Live Conversation & Activity Card (Clean stream, no textfield borders)
        transcript_card = QFrame()
        transcript_card.setProperty("class", "Card")
        transcript_card.setStyleSheet(
            "background-color: #111622; border: 1px solid #1A2436; "
            "border-radius: 14px; padding: 16px;"
        )
        t_layout = QVBoxLayout(transcript_card)
        t_layout.setContentsMargins(16, 14, 16, 14)
        t_layout.setSpacing(10)

        t_header = QHBoxLayout()
        lbl_t_title = QLabel("CONVERSATION & ACTIVITY")
        lbl_t_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748B; letter-spacing: 0.8px;")
        t_header.addWidget(lbl_t_title)
        t_header.addStretch()

        self.lbl_time = QLabel("Standing by")
        self.lbl_time.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_MUTED};")
        t_header.addWidget(self.lbl_time)
        t_layout.addLayout(t_header)

        # User Speech Row
        user_row = QHBoxLayout()
        user_row.setSpacing(10)
        lbl_user_tag = QLabel(" YOU ")
        lbl_user_tag.setStyleSheet(
            "background-color: rgba(0, 229, 255, 0.12); color: #00E5FF; "
            "font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 6px;"
        )
        self.lbl_user_text = QLabel('Say "Hey Jarvis" or tap Push-To-Talk')
        self.lbl_user_text.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_PRIMARY};")
        self.lbl_user_text.setWordWrap(True)
        user_row.addWidget(lbl_user_tag)
        user_row.addWidget(self.lbl_user_text, stretch=1)
        t_layout.addLayout(user_row)

        # Assistant Response Row
        bot_row = QHBoxLayout()
        bot_row.setSpacing(10)
        lbl_bot_tag = QLabel(" DESKBOT ")
        lbl_bot_tag.setStyleSheet(
            "background-color: rgba(0, 230, 118, 0.12); color: #00E676; "
            "font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 6px;"
        )
        self.lbl_bot_text = QLabel("Standing by.")
        self.lbl_bot_text.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY};")
        self.lbl_bot_text.setWordWrap(True)
        bot_row.addWidget(lbl_bot_tag)
        bot_row.addWidget(self.lbl_bot_text, stretch=1)
        t_layout.addLayout(bot_row)

        layout.addWidget(transcript_card, stretch=2)

        # 4. Quick Actions Control Bar (Clean typography, no generic emojis)
        actions_bar = QHBoxLayout()
        actions_bar.setSpacing(10)

        self.btn_ptt = QPushButton("●  Push-To-Talk")
        self.btn_ptt.setProperty("class", "PrimaryButton")
        self.btn_ptt.setStyleSheet(
            f"background-color: {COLOR_ACCENT_CYAN}; color: #05080E; "
            "font-weight: 700; font-size: 13px; padding: 10px 20px; border-radius: 8px; border: none;"
        )
        self.btn_ptt.setToolTip("Trigger voice listening without speaking the wake word")
        self.btn_ptt.clicked.connect(self._on_ptt_clicked)
        actions_bar.addWidget(self.btn_ptt)

        self.btn_screen = QPushButton("◈  Inspect Screen")
        self.btn_screen.setProperty("class", "SecondaryButton")
        self.btn_screen.setStyleSheet(
            "background-color: #161D2D; border: 1px solid #25334C; "
            "color: #FFFFFF; font-weight: 500; font-size: 13px; padding: 10px 16px; border-radius: 8px;"
        )
        self.btn_screen.setToolTip("Analyze code or UI currently visible on your monitor with vision AI")
        self.btn_screen.clicked.connect(self._on_screen_inspect_clicked)
        actions_bar.addWidget(self.btn_screen)

        self.btn_screenshot = QPushButton("◩  Capture Screen")
        self.btn_screenshot.setProperty("class", "SecondaryButton")
        self.btn_screenshot.setStyleSheet(
            "background-color: #161D2D; border: 1px solid #25334C; "
            "color: #FFFFFF; font-weight: 500; font-size: 13px; padding: 10px 16px; border-radius: 8px;"
        )
        self.btn_screenshot.setToolTip("Save a clean PNG screenshot directly to your Desktop")
        self.btn_screenshot.clicked.connect(self._on_screenshot_clicked)
        actions_bar.addWidget(self.btn_screenshot)

        actions_bar.addStretch()

        layout.addLayout(actions_bar)

    def _connect_signals(self) -> None:
        self.bridge.state_changed.connect(self._on_state_changed)
        self.bridge.transcript_received.connect(self._on_transcript_received)
        self.bridge.direct_answer_emitted.connect(self._on_bot_response)
        self.bridge.tool_executed.connect(self._on_tool_executed)
        self.bridge.speech_level.connect(self.face_widget.set_audio_level)

    def _on_state_changed(self, old_state: str, new_state: str, context: str) -> None:
        self.face_widget.set_assistant_state(new_state)

        # Update status pill text and color with subtle rgba styling
        clean_st = new_state.upper()
        if clean_st == "IDLE":
            self.pill_state.setText("● IDLE")
            self.pill_state.setStyleSheet(
                "background-color: rgba(0, 230, 118, 0.12); color: #00E676; "
                "border: 1px solid rgba(0, 230, 118, 0.28); "
                "border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: 600;"
            )
        elif clean_st in ("LISTENING", "WAKE"):
            self.pill_state.setText("● LISTENING")
            self.pill_state.setStyleSheet(
                "background-color: rgba(0, 229, 255, 0.12); color: #00E5FF; "
                "border: 1px solid rgba(0, 229, 255, 0.32); "
                "border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: 600;"
            )
        elif clean_st in ("THINKING", "SCREEN_ANALYSIS", "TRANSCRIBING"):
            self.pill_state.setText(f"● {clean_st}")
            self.pill_state.setStyleSheet(
                "background-color: rgba(124, 77, 255, 0.12); color: #B388FF; "
                "border: 1px solid rgba(124, 77, 255, 0.30); "
                "border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: 600;"
            )
        elif clean_st == "EXECUTING":
            self.pill_state.setText("● EXECUTING")
            self.pill_state.setStyleSheet(
                "background-color: rgba(0, 230, 118, 0.12); color: #00E676; "
                "border: 1px solid rgba(0, 230, 118, 0.28); "
                "border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: 600;"
            )
        elif clean_st in ("SPEAKING", "FOLLOW_UP", "SUCCESS"):
            self.pill_state.setText(f"● {clean_st}")
            self.pill_state.setStyleSheet(
                "background-color: rgba(0, 229, 255, 0.12); color: #00E5FF; "
                "border: 1px solid rgba(0, 229, 255, 0.32); "
                "border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: 600;"
            )
        elif clean_st == "ERROR":
            self.pill_state.setText("● ERROR")
            self.pill_state.setStyleSheet(
                "background-color: rgba(255, 61, 113, 0.12); color: #FF3D71; "
                "border: 1px solid rgba(255, 61, 113, 0.28); "
                "border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: 600;"
            )
        else:
            self.pill_state.setText(f"● {clean_st}")

    def _on_transcript_received(self, text: str) -> None:
        self.lbl_user_text.setText(f'"{text}"')
        self.lbl_time.setText(time.strftime("%H:%M:%S"))

    def _on_bot_response(self, text: str) -> None:
        self.lbl_bot_text.setText(text)
        self.lbl_time.setText(time.strftime("%H:%M:%S"))

    def _on_tool_executed(self, tool_name: str, success: bool, message: str) -> None:
        if message:
            self.lbl_bot_text.setText(f"[{tool_name}] {message}")

    def _on_ptt_clicked(self) -> None:
        """Trigger simulated or hardware touch push-to-talk."""
        self.bridge.notify_touch()

    def _on_screen_inspect_clicked(self) -> None:
        """Trigger vision screen inspection."""
        import threading
        def _run_vision():
            try:
                from command_executor import execute_intent
                self.bridge.notify_state_change("IDLE", "SCREEN_ANALYSIS", "Inspecting active screen...")
                res = execute_intent({"action": "screen_analysis", "query": "Explain what is on the screen"})
                self.bridge.notify_tool_result("screen_analysis", res.success, res.message)
                self.bridge.notify_state_change("SCREEN_ANALYSIS", "IDLE")
            except Exception as err:
                self.bridge.notify_state_change("SCREEN_ANALYSIS", "ERROR", str(err))

        threading.Thread(target=_run_vision, daemon=True).start()

    def _on_screenshot_clicked(self) -> None:
        """Trigger screenshot tool directly."""
        import threading
        def _run_screenshot():
            try:
                from command_executor import execute_intent
                res = execute_intent({"action": "screenshot"})
                self.bridge.notify_tool_result("screenshot", res.success, res.message)
            except Exception as err:
                self.bridge.notify_tool_result("screenshot", False, str(err))

        threading.Thread(target=_run_screenshot, daemon=True).start()
