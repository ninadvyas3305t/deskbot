"""Design system tokens and QSS styles for DeskBot 2.0 futuristic desktop application."""

from __future__ import annotations

# Color Palette Tokens
COLOR_BG_DARK = "#090C10"          # Deep space / canvas background
COLOR_SURFACE = "#111622"          # Base surface / navigation sidebar
COLOR_SURFACE_ELEVATED = "#161D2D" # Cards and floating panels
COLOR_SURFACE_HOVER = "#1D263B"    # Interactive hover
COLOR_BORDER = "#212C42"           # Subtle structural outline
COLOR_BORDER_FOCUS = "#00E5FF"     # Cyber cyan active outline

COLOR_TEXT_PRIMARY = "#FFFFFF"     # Crisp white
COLOR_TEXT_SECONDARY = "#8B9BB4"   # Cool slate
COLOR_TEXT_MUTED = "#55657E"       # Subtle label
COLOR_TEXT_DISABLED = "#3E4A5E"    # Disabled state

COLOR_ACCENT_CYAN = "#00E5FF"      # Cyber Cyan (Primary active)
COLOR_ACCENT_CYAN_DIM = "rgba(0, 229, 255, 0.12)" # 12% opacity cyan tint
COLOR_ACCENT_VIOLET = "#7C4DFF"    # Electric Violet (AI / Thinking)
COLOR_ACCENT_MINT = "#00E676"      # Neon Mint (Success / Executing)
COLOR_ACCENT_AMBER = "#FFB300"     # Amber (Warning / Follow-up)
COLOR_ACCENT_CORAL = "#FF3D71"     # Neon Coral (Error / Alert)
COLOR_VISOR_BG = "#070A0F"         # Deep Mochi visor black
COLOR_VISOR_BORDER = "#141D2C"     # Sleek visor border


def hex_to_rgba(hex_code: str, alpha: float = 0.15) -> str:
    """Convert a hex color (#RRGGBB) to rgba(r, g, b, alpha) for safe Qt QSS usage."""
    h = hex_code.lstrip("#")
    if len(h) >= 6:
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        return f"rgba({r}, {g}, {b}, {alpha:.2f})"
    return hex_code


APPLICATION_STYLESHEET = f"""
QMainWindow {{
    background-color: {COLOR_BG_DARK};
}}

QWidget#MainContent {{
    background-color: {COLOR_BG_DARK};
}}

/* Sidebar Navigation */
QFrame#Sidebar {{
    background-color: {COLOR_SURFACE};
    border-right: 1px solid {COLOR_BORDER};
}}

QPushButton.NavButton {{
    background-color: transparent;
    border: none;
    border-radius: 8px;
    color: {COLOR_TEXT_SECONDARY};
    font-size: 13px;
    font-weight: 500;
    padding: 10px 14px;
    text-align: left;
}}

QPushButton.NavButton:hover {{
    background-color: {COLOR_SURFACE_HOVER};
    color: {COLOR_TEXT_PRIMARY};
}}

QPushButton.NavButton:checked {{
    background-color: {COLOR_ACCENT_CYAN_DIM};
    border-left: 3px solid {COLOR_ACCENT_CYAN};
    color: {COLOR_ACCENT_CYAN};
    font-weight: 600;
}}

/* Header Bar */
QFrame#HeaderBar {{
    background-color: {COLOR_SURFACE};
    border-bottom: 1px solid {COLOR_BORDER};
}}

/* Generic Cards and Panels */
QFrame.Card {{
    background-color: {COLOR_SURFACE_ELEVATED};
    border: 1px solid {COLOR_BORDER};
    border-radius: 12px;
    padding: 16px;
}}

QFrame.Card:hover {{
    border: 1px solid #2B3954;
}}

/* Labels */
QLabel {{
    color: {COLOR_TEXT_PRIMARY};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}}

QLabel.Heading1 {{
    font-size: 20px;
    font-weight: 700;
    color: {COLOR_TEXT_PRIMARY};
}}

QLabel.Heading2 {{
    font-size: 15px;
    font-weight: 600;
    color: {COLOR_TEXT_PRIMARY};
}}

QLabel.Subheading {{
    font-size: 13px;
    font-weight: 400;
    color: {COLOR_TEXT_SECONDARY};
}}

QLabel.Caption {{
    font-size: 11px;
    font-weight: 400;
    color: {COLOR_TEXT_MUTED};
}}

/* Status Pills */
QLabel.StatusPill {{
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}

QLabel.StatusPillReady {{
    background-color: rgba(0, 230, 118, 0.12);
    color: {COLOR_ACCENT_MINT};
    border: 1px solid rgba(0, 230, 118, 0.28);
}}

QLabel.StatusPillListening {{
    background-color: rgba(0, 229, 255, 0.12);
    color: {COLOR_ACCENT_CYAN};
    border: 1px solid rgba(0, 229, 255, 0.32);
}}

QLabel.StatusPillWaiting {{
    background-color: rgba(255, 179, 0, 0.12);
    color: {COLOR_ACCENT_AMBER};
    border: 1px solid rgba(255, 179, 0, 0.28);
}}

QLabel.StatusPillError {{
    background-color: rgba(255, 61, 113, 0.12);
    color: {COLOR_ACCENT_CORAL};
    border: 1px solid rgba(255, 61, 113, 0.28);
}}

/* Push Buttons */
QPushButton.PrimaryButton {{
    background-color: {COLOR_ACCENT_CYAN};
    border: none;
    border-radius: 8px;
    color: #05080E;
    font-size: 13px;
    font-weight: 600;
    padding: 8px 18px;
}}

QPushButton.PrimaryButton:hover {{
    background-color: #33EBFF;
}}

QPushButton.PrimaryButton:pressed {{
    background-color: #00B4D8;
}}

QPushButton.SecondaryButton {{
    background-color: {COLOR_SURFACE_HOVER};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    color: {COLOR_TEXT_PRIMARY};
    font-size: 13px;
    font-weight: 500;
    padding: 8px 16px;
}}

QPushButton.SecondaryButton:hover {{
    background-color: #26324A;
    border-color: #354766;
}}

QPushButton.SecondaryButton:pressed {{
    background-color: #1A2233;
}}

QPushButton.IconButton {{
    background-color: transparent;
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    color: {COLOR_TEXT_SECONDARY};
    padding: 6px;
}}

QPushButton.IconButton:hover {{
    background-color: {COLOR_SURFACE_HOVER};
    color: {COLOR_TEXT_PRIMARY};
}}

/* Line Edits */
QLineEdit {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    color: {COLOR_TEXT_PRIMARY};
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: {COLOR_ACCENT_CYAN};
    selection-color: #000000;
}}

QLineEdit:focus {{
    border: 1px solid {COLOR_ACCENT_CYAN};
}}

/* ScrollBars */
QScrollBar:vertical {{
    background: {COLOR_SURFACE};
    width: 8px;
    margin: 0;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background: #25334A;
    min-height: 24px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLOR_ACCENT_CYAN};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* CheckBoxes */
QCheckBox {{
    color: {COLOR_TEXT_PRIMARY};
    font-size: 13px;
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid {COLOR_BORDER};
    background-color: {COLOR_SURFACE};
}}

QCheckBox::indicator:hover {{
    border-color: {COLOR_ACCENT_CYAN};
}}

QCheckBox::indicator:checked {{
    background-color: {COLOR_ACCENT_CYAN};
    border-color: {COLOR_ACCENT_CYAN};
    image: url("resources/check.png");
}}

/* Sliders */
QSlider::groove:horizontal {{
    height: 4px;
    background: {COLOR_BORDER};
    border-radius: 2px;
}}

QSlider::sub-page:horizontal {{
    background: {COLOR_ACCENT_CYAN};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {COLOR_TEXT_PRIMARY};
    width: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}}

QSlider::handle:horizontal:hover {{
    background: {COLOR_ACCENT_CYAN};
}}

/* ComboBox */
QComboBox {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    color: {COLOR_TEXT_PRIMARY};
    padding: 6px 12px;
    font-size: 13px;
}}

QComboBox:focus {{
    border-color: {COLOR_ACCENT_CYAN};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox QAbstractItemView {{
    background-color: {COLOR_SURFACE_ELEVATED};
    border: 1px solid {COLOR_BORDER};
    selection-background-color: {COLOR_ACCENT_CYAN_DIM};
    selection-color: {COLOR_ACCENT_CYAN};
    color: {COLOR_TEXT_PRIMARY};
    outline: none;
}}
"""
