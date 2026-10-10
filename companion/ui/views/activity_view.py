"""Activity inspector view displaying chronological voice, AI, and tool execution history."""

from __future__ import annotations

import time
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.bridge import DeskBotBridge, get_ui_bridge
from ui.theme import (
    COLOR_ACCENT_AMBER,
    COLOR_ACCENT_CORAL,
    COLOR_ACCENT_CYAN,
    COLOR_ACCENT_MINT,
    COLOR_ACCENT_VIOLET,
    COLOR_BORDER,
    COLOR_SURFACE,
    COLOR_SURFACE_ELEVATED,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    hex_to_rgba,
)


class ActivityItemWidget(QFrame):
    """Render a single event card in the activity timeline."""

    def __init__(self, event: dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {COLOR_SURFACE_ELEVATED}; border: 1px solid {COLOR_BORDER}; "
            "border-radius: 8px; padding: 10px;"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # Time
        ts = event.get("timestamp", time.time())
        time_str = time.strftime("%H:%M:%S", time.localtime(ts))
        lbl_time = QLabel(time_str)
        lbl_time.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_MUTED}; min-width: 55px;")
        layout.addWidget(lbl_time)

        # Category Badge
        cat = event.get("category", "INFO")
        lbl_badge = QLabel(f" {cat} ")
        badge_style = self._get_badge_style(cat)
        lbl_badge.setStyleSheet(badge_style)
        layout.addWidget(lbl_badge)

        # Content (Title & Details)
        content_box = QVBoxLayout()
        content_box.setSpacing(2)

        title = QLabel(event.get("title", ""))
        title.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {COLOR_TEXT_PRIMARY};")
        title.setWordWrap(True)
        content_box.addWidget(title)

        details = event.get("details", "")
        if details:
            # Redact common secrets if present
            redacted = self._redact(details)
            lbl_details = QLabel(redacted)
            lbl_details.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_SECONDARY};")
            lbl_details.setWordWrap(True)
            content_box.addWidget(lbl_details)

        layout.addLayout(content_box, stretch=1)

    def _get_badge_style(self, category: str) -> str:
        color = COLOR_ACCENT_CYAN
        if category in ("WAKE", "STT"):
            color = COLOR_ACCENT_CYAN
        elif category in ("AI", "THINKING"):
            color = COLOR_ACCENT_VIOLET
        elif category in ("TOOL", "SUCCESS", "ANSWER"):
            color = COLOR_ACCENT_MINT
        elif category in ("DEVICE", "NETWORK", "WARNING"):
            color = COLOR_ACCENT_AMBER
        elif category in ("ERROR", "FAIL"):
            color = COLOR_ACCENT_CORAL

        bg_col = hex_to_rgba(color, 0.12)
        border_col = hex_to_rgba(color, 0.35)
        return (
            f"background-color: {bg_col}; color: {color}; border: 1px solid {border_col}; "
            "border-radius: 4px; font-size: 10px; font-weight: 700; padding: 2px 6px;"
        )

    def _redact(self, text: str) -> str:
        if "nvapi-" in text:
            import re
            return re.sub(r"nvapi-[A-Za-z0-9_-]+", "nvapi-••••••••", text)
        return text


class ActivityView(QWidget):
    """Chronological event feed with search filter and clear controls."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.bridge: DeskBotBridge = get_ui_bridge()
        self._events: List[dict] = []
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # Header
        top_row = QHBoxLayout()
        v_titles = QVBoxLayout()
        v_titles.setSpacing(4)
        lbl_title = QLabel("Activity Timeline")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        lbl_desc = QLabel("Real-time chronological log of speech detection, AI reasoning, and tool executions.")
        lbl_desc.setStyleSheet(f"font-size: 13px; color: {COLOR_TEXT_SECONDARY};")
        v_titles.addWidget(lbl_title)
        v_titles.addWidget(lbl_desc)
        top_row.addLayout(v_titles, stretch=1)

        self.btn_clear = QPushButton("⌫ Clear History")
        self.btn_clear.setStyleSheet(
            f"background-color: {COLOR_SURFACE}; border: 1px solid {COLOR_BORDER}; "
            "color: #FFFFFF; font-weight: 500; font-size: 12px; padding: 8px 14px; border-radius: 6px;"
        )
        self.btn_clear.clicked.connect(self._clear_history)
        top_row.addWidget(self.btn_clear)
        main_layout.addLayout(top_row)

        # Search / Filter Row
        filter_row = QHBoxLayout()
        self.entry_filter = QLineEdit()
        self.entry_filter.setPlaceholderText("Filter events (e.g. WAKE, STT, open_app, error)...")
        self.entry_filter.textChanged.connect(self._rebuild_list)
        filter_row.addWidget(self.entry_filter)
        main_layout.addLayout(filter_row)

        # Scrollable events timeline
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("background: transparent;")

        self.feed_container = QWidget()
        self.feed_layout = QVBoxLayout(self.feed_container)
        self.feed_layout.setContentsMargins(0, 0, 0, 0)
        self.feed_layout.setSpacing(8)
        self.feed_layout.addStretch()

        self.scroll.setWidget(self.feed_container)
        main_layout.addWidget(self.scroll, stretch=1)

    def _connect_signals(self) -> None:
        self.bridge.activity_logged.connect(self._on_activity_logged)

    def _on_activity_logged(self, event: dict) -> None:
        self._events.insert(0, event)  # newest first
        if len(self._events) > 200:
            self._events.pop()
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        # Clear layout items
        while self.feed_layout.count() > 1:
            item = self.feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        filter_text = self.entry_filter.text().strip().lower()
        count = 0
        for ev in self._events:
            title = ev.get("title", "").lower()
            cat = ev.get("category", "").lower()
            details = ev.get("details", "").lower()

            if filter_text and filter_text not in title and filter_text not in cat and filter_text not in details:
                continue

            item_widget = ActivityItemWidget(ev)
            self.feed_layout.insertWidget(count, item_widget)
            count += 1

    def _clear_history(self) -> None:
        self._events.clear()
        self._rebuild_list()
