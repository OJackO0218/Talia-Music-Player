"""
Talia Cyberpunk UI Theme Engine.

Centralizes color tokens, palette definitions, and shared Qt stylesheets
to eliminate scattered inline CSS and ensure consistent visual hierarchy.
"""

# ==========================================================
# Cyberpunk Design Tokens (Colors & Accents)
# ==========================================================
COLOR_BG_ROOT = "#09090b"
COLOR_BG_PANEL = "#18181b"
COLOR_BG_CARD = "#202024"
COLOR_BG_HOVER = "#27272a"
COLOR_BG_ACTIVE = "#2e2e33"

COLOR_BORDER_SUBTLE = "#27272a"
COLOR_BORDER_DEFAULT = "#3f3f46"
COLOR_BORDER_BRIGHT = "#52525b"

COLOR_TEXT_PRIMARY = "#f4f4f5"
COLOR_TEXT_SECONDARY = "#d4d4d8"
COLOR_TEXT_MUTED = "#a1a1aa"
COLOR_TEXT_FAINT = "#71717a"

# Accent Colors
COLOR_ACCENT_CYAN = "#00ffff"
COLOR_ACCENT_ELECTRIC = "#5EF6FF"
COLOR_ACCENT_CYAN_BORDER = "#06b6d4"
COLOR_ACCENT_CORAL = "#F75049"
COLOR_ACCENT_CORAL_SOFT = "#ff8a84"
COLOR_ACCENT_BLUE = "#2563eb"
COLOR_ACCENT_BLUE_BORDER = "#3b82f6"
COLOR_ACCENT_PURPLE = "#7c3aed"
COLOR_ACCENT_PURPLE_BG = "#1e1b4b"
COLOR_ACCENT_PURPLE_TEXT = "#a78bfa"
COLOR_ACCENT_PINK = "#f472b6"
COLOR_ACCENT_GREEN = "#059669"
COLOR_ACCENT_GREEN_TEXT = "#4ade80"
COLOR_ACCENT_DANGER = "#991b1b"
COLOR_ACCENT_DANGER_BG = "#450a0a"
COLOR_ACCENT_DANGER_TEXT = "#fca5a5"

# ==========================================================
# Button Variant Style Generator
# ==========================================================
BUTTON_VARIANTS = {
    "default": f"""
        QPushButton {{
            background-color: {COLOR_BG_HOVER};
            border: 1px solid {COLOR_BORDER_DEFAULT};
            color: {COLOR_TEXT_PRIMARY};
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: 500;
            font-size: 11px;
        }}
        QPushButton:hover {{
            background-color: {COLOR_BORDER_DEFAULT};
            border-color: {COLOR_BORDER_BRIGHT};
            color: #ffffff;
        }}
        QPushButton:pressed {{
            background-color: {COLOR_BG_CARD};
        }}
        QPushButton:disabled {{
            background-color: {COLOR_BG_CARD};
            border-color: {COLOR_BORDER_SUBTLE};
            color: {COLOR_TEXT_FAINT};
        }}
    """,
    "primary": f"""
        QPushButton {{
            background-color: {COLOR_ACCENT_BLUE};
            border: 1px solid {COLOR_ACCENT_BLUE_BORDER};
            color: #ffffff;
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: bold;
            font-size: 11px;
        }}
        QPushButton:hover {{
            background-color: #1d4ed8;
            border-color: #60a5fa;
            color: #ffffff;
        }}
        QPushButton:pressed {{
            background-color: #1e40af;
        }}
        QPushButton:disabled {{
            background-color: #1e3a5f;
            border-color: #1d4ed8;
            color: #93c5fd;
        }}
    """,
    "purple": f"""
        QPushButton {{
            background-color: {COLOR_ACCENT_PURPLE_BG};
            border: 1px solid {COLOR_ACCENT_PURPLE};
            color: {COLOR_ACCENT_PURPLE_TEXT};
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: bold;
            font-size: 11px;
        }}
        QPushButton:hover {{
            background-color: #2e1065;
            border-color: #a855f7;
            color: #ffffff;
        }}
        QPushButton:pressed {{
            background-color: #1e1b4b;
        }}
    """,
    "cyan": f"""
        QPushButton {{
            background-color: #083344;
            border: 1px solid {COLOR_ACCENT_CYAN_BORDER};
            color: {COLOR_ACCENT_CYAN};
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: bold;
            font-size: 11px;
        }}
        QPushButton:hover {{
            background-color: #0e7490;
            border-color: {COLOR_ACCENT_CYAN};
            color: #ffffff;
        }}
        QPushButton:pressed {{
            background-color: #083344;
        }}
    """,
    "success": f"""
        QPushButton {{
            background-color: {COLOR_ACCENT_GREEN};
            border: 1px solid #10b981;
            color: #ffffff;
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: bold;
            font-size: 11px;
        }}
        QPushButton:hover {{
            background-color: #047857;
            border-color: #34d399;
        }}
        QPushButton:pressed {{
            background-color: #065f46;
        }}
    """,
    "danger": f"""
        QPushButton {{
            background-color: {COLOR_ACCENT_DANGER_BG};
            border: 1px solid {COLOR_ACCENT_DANGER};
            color: {COLOR_ACCENT_DANGER_TEXT};
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: bold;
            font-size: 11px;
        }}
        QPushButton:hover {{
            background-color: #7f1d1d;
            border-color: #b91c1c;
            color: #ffffff;
        }}
        QPushButton:pressed {{
            background-color: #450a0a;
        }}
    """,
}

# ==========================================================
# Card Container Style (Clean Slate Utility UI)
# ==========================================================
CARD_STYLE = """
    QFrame#cyberCard {
        background-color: #1b1b21;
        border: 1px solid #2a2a33;
        border-radius: 10px;
    }
"""

# Shared Cyberpunk Inner Widget Styling matching ControlPanel
CYBER_DIALOG_CONTROLS_QSS = """
    QLineEdit, QComboBox {
        background-color: #050508;
        color: #ff8a84;
        border: 1px solid rgba(247, 80, 73, 95);
        border-radius: 2px;
        padding: 4px 8px;
        font-family: 'Rajdhani', 'Segoe UI', sans-serif;
        font-size: 11px;
        font-weight: 600;
        selection-background-color: #F75049;
        selection-color: #0e0e17;
    }
    QLineEdit:hover, QComboBox:hover {
        border-color: #F75049;
    }
    QLineEdit:focus, QComboBox:focus {
        background-color: rgba(247, 80, 73, 24);
        border: 1px solid #5EF6FF;
        color: #f4f4f5;
    }
    QComboBox::drop-down {
        border: none;
        width: 16px;
    }
    QComboBox QAbstractItemView {
        background-color: #14151f;
        color: #ff8a84;
        border: 1px solid #F75049;
        selection-background-color: #F75049;
        selection-color: #0e0e17;
        padding: 4px;
    }
    QCheckBox {
        color: #d4d4d8;
        font-family: 'Rajdhani', 'Segoe UI', sans-serif;
        font-size: 11px;
        font-weight: 600;
        spacing: 7px;
    }
    QCheckBox::indicator {
        width: 13px;
        height: 13px;
        border: 1px solid rgba(247, 80, 73, 140);
        border-radius: 2px;
        background: #08080e;
    }
    QCheckBox::indicator:hover {
        border-color: #5EF6FF;
    }
    QCheckBox::indicator:checked {
        background: #F75049;
        border-color: #ff8a84;
    }
    QScrollArea {
        border: 1px solid rgba(247, 80, 73, 80);
        background-color: #09090F;
        border-radius: 3px;
    }
    QScrollBar:vertical {
        border: none;
        background: #0b0b12;
        width: 6px;
        margin: 0;
    }
    QScrollBar::handle:vertical {
        background: rgba(247, 80, 73, 140);
        min-height: 20px;
        border-radius: 2px;
    }
    QScrollBar::handle:vertical:hover {
        background: #5EF6FF;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }
    QProgressBar {
        border: 1px solid rgba(247, 80, 73, 120);
        border-radius: 2px;
        background: #06060b;
        text-align: center;
        color: #f4f4f5;
        font-family: 'Rajdhani', 'Consolas', monospace;
        font-size: 10px;
        font-weight: bold;
    }
    QProgressBar::chunk {
        background-color: #5EF6FF;
    }
"""

CYBER_SETTINGS_QSS = f"""
    QDialog {{
        background-color: #0A0B10;
        color: #f4f4f5;
        font-family: 'Rajdhani', 'Segoe UI', sans-serif;
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QWidget#settingsContent {{
        background-color: #0A0B10;
    }}
    QLabel {{
        font-family: 'Rajdhani', 'Segoe UI', sans-serif;
        font-size: 11px;
        background: transparent;
    }}
    QSlider::groove:horizontal {{
        height: 4px;
        background: rgba(247, 80, 73, 75);
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: #F75049;
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: #ff8a84;
        border: 1px solid #ffffff;
        width: 8px;
        height: 14px;
        margin-top: -5px;
        margin-bottom: -5px;
        border-radius: 1px;
    }}
    QSlider::handle:horizontal:hover {{
        background: #5EF6FF;
        border-color: #ffffff;
    }}
    {CYBER_DIALOG_CONTROLS_QSS}
"""

CLEAN_UTILITY_QSS = """
    QDialog {
        background-color: #121216;
        color: #f4f4f5;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 12px;
    }
    QWidget#cleanContent {
        background-color: #121216;
    }
    QScrollArea {
        border: none;
        background-color: transparent;
    }
    QLabel {
        color: #e4e4e7;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 12px;
        background: transparent;
    }
    QTabWidget::pane {
        border: none;
        background-color: #121216;
        margin-top: 2px;
    }
    QTabBar {
        background: #17171c;
        border-bottom: 1px solid #272730;
    }
    QTabBar::tab {
        background: transparent;
        color: #9ca3af;
        border: none;
        border-bottom: 2px solid transparent;
        padding: 9px 14px;
        margin-right: 4px;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 12px;
        font-weight: 600;
    }
    QTabBar::tab:hover {
        color: #f4f4f5;
        background: rgba(255, 255, 255, 0.03);
    }
    QTabBar::tab:selected {
        color: #ffffff;
        border-bottom: 2px solid #3b82f6;
        background: rgba(59, 130, 246, 0.08);
    }
    QLineEdit, QPlainTextEdit, QComboBox {
        background-color: #16161b;
        color: #f4f4f5;
        border: 1px solid #2e2e38;
        border-radius: 6px;
        padding: 6px 10px;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 12px;
        selection-background-color: #2563eb;
        selection-color: #ffffff;
    }
    QLineEdit:hover, QPlainTextEdit:hover, QComboBox:hover {
        border-color: #3f3f4d;
    }
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
        border-color: #3b82f6;
        background-color: #181820;
    }
    QComboBox::drop-down {
        border: none;
        width: 20px;
    }
    QComboBox QAbstractItemView {
        background-color: #1b1b22;
        color: #f4f4f5;
        border: 1px solid #3f3f4d;
        selection-background-color: #2563eb;
        selection-color: #ffffff;
        padding: 4px;
    }
    QPushButton {
        background-color: #24242c;
        color: #e4e4e7;
        border: 1px solid #32323d;
        border-radius: 6px;
        padding: 6px 12px;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 12px;
        font-weight: 600;
    }
    QPushButton:hover {
        background-color: #2d2d37;
        border-color: #464655;
        color: #ffffff;
    }
    QPushButton:pressed {
        background-color: #1f1f27;
    }
    QPushButton:disabled {
        background-color: #19191f;
        color: #6b7280;
        border-color: #25252e;
    }
    QPushButton[role="primary"] {
        background-color: #2563eb;
        color: #ffffff;
        border: 1px solid #3b82f6;
    }
    QPushButton[role="primary"]:hover {
        background-color: #1d4ed8;
        border-color: #60a5fa;
    }
    QPushButton[role="success"] {
        background-color: #065f46;
        color: #ecfdf5;
        border: 1px solid #10b981;
    }
    QPushButton[role="success"]:hover {
        background-color: #047857;
    }
    QPushButton[role="danger"] {
        background-color: #3b181c;
        color: #fca5a5;
        border: 1px solid #7f1d1d;
    }
    QPushButton[role="danger"]:hover {
        background-color: #7f1d1d;
        color: #ffffff;
    }
    QCheckBox {
        color: #e4e4e7;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 12px;
        spacing: 8px;
    }
    QCheckBox::indicator {
        width: 15px;
        height: 15px;
        border: 1px solid #424250;
        border-radius: 4px;
        background: #16161b;
    }
    QCheckBox::indicator:hover {
        border-color: #3b82f6;
    }
    QCheckBox::indicator:checked {
        background: #2563eb;
        border-color: #3b82f6;
    }
    QSlider::groove:horizontal {
        height: 4px;
        background: #2b2b35;
        border-radius: 2px;
    }
    QSlider::sub-page:horizontal {
        background: #3b82f6;
        border-radius: 2px;
    }
    QSlider::handle:horizontal {
        background: #f4f4f5;
        border: 2px solid #3b82f6;
        width: 12px;
        height: 12px;
        margin-top: -5px;
        margin-bottom: -5px;
        border-radius: 7px;
    }
    QSlider::handle:horizontal:hover {
        background: #ffffff;
        border-color: #60a5fa;
    }
    QListWidget {
        background-color: #16161b;
        color: #e4e4e7;
        border: 1px solid #2a2a33;
        border-radius: 8px;
        padding: 4px;
        outline: none;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 12px;
    }
    QListWidget::item {
        padding: 7px 10px;
        border-radius: 5px;
        margin: 1px 0;
    }
    QListWidget::item:hover {
        background-color: #202028;
    }
    QListWidget::item:selected {
        background-color: rgba(37, 99, 235, 0.28);
        color: #ffffff;
        border: 1px solid rgba(59, 130, 246, 0.55);
    }
    QProgressBar {
        border: 1px solid #2b2b35;
        border-radius: 5px;
        background: #16161b;
        text-align: center;
        color: #e4e4e7;
        font-size: 11px;
    }
    QProgressBar::chunk {
        background-color: #3b82f6;
        border-radius: 4px;
    }
    QScrollBar:vertical {
        border: none;
        background: transparent;
        width: 7px;
        margin: 2px 0;
    }
    QScrollBar::handle:vertical {
        background: #353542;
        min-height: 24px;
        border-radius: 3px;
    }
    QScrollBar::handle:vertical:hover {
        background: #4d4d5e;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }
"""

# ==========================================================
# Global Master Panel Stylesheet
# ==========================================================
SHARED_PANEL_STYLE = f"""
    QWidget {{
        background-color: {COLOR_BG_PANEL};
        color: {COLOR_TEXT_PRIMARY};
        font-family: 'Segoe UI', Arial, sans-serif;
    }}
    QScrollArea {{
        border: none;
        background-color: transparent;
    }}
    QScrollBar:vertical {{
        border: none;
        background: {COLOR_BG_PANEL};
        width: 6px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {COLOR_BORDER_DEFAULT};
        min-height: 24px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {COLOR_BORDER_BRIGHT};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QComboBox {{
        background-color: {COLOR_BG_CARD};
        border: 1px solid {COLOR_BORDER_DEFAULT};
        border-radius: 4px;
        color: {COLOR_TEXT_PRIMARY};
        padding: 5px 10px;
        font-size: 11px;
    }}
    QComboBox:hover {{
        border-color: {COLOR_ACCENT_BLUE_BORDER};
    }}
    QComboBox QAbstractItemView {{
        background-color: {COLOR_BG_CARD};
        border: 1px solid {COLOR_BORDER_DEFAULT};
        color: {COLOR_TEXT_PRIMARY};
        selection-background-color: {COLOR_ACCENT_BLUE_BORDER};
        selection-color: #ffffff;
    }}
    QListWidget {{
        background-color: {COLOR_BG_CARD};
        border: 1px solid {COLOR_BORDER_DEFAULT};
        border-radius: 4px;
        color: #e4e4e7;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 11px;
        padding: 4px;
    }}
    QListWidget::item {{
        padding: 5px 8px;
        border-radius: 3px;
        border-bottom: 1px solid {COLOR_BORDER_SUBTLE};
    }}
    QListWidget::item:hover {{
        background-color: {COLOR_BG_HOVER};
        color: #ffffff;
    }}
    QListWidget::item:selected {{
        background-color: #2e3547;
        color: #ffffff;
        border-left: 3px solid {COLOR_ACCENT_BLUE_BORDER};
    }}
    QSlider::groove:horizontal {{
        height: 4px;
        background: {COLOR_BORDER_DEFAULT};
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {COLOR_ACCENT_BLUE_BORDER};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: #ffffff;
        border: 1px solid #71717a;
        width: 14px;
        height: 14px;
        margin-top: -5px;
        margin-bottom: -5px;
        border-radius: 7px;
    }}
    QSlider::handle:horizontal:hover {{
        background: #ffffff;
        border: 1px solid {COLOR_ACCENT_BLUE_BORDER};
    }}
    QCheckBox {{
        spacing: 8px;
        color: {COLOR_TEXT_SECONDARY};
        font-size: 11px;
    }}
    QCheckBox::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {COLOR_BORDER_DEFAULT};
        border-radius: 3px;
        background: {COLOR_BG_CARD};
    }}
    QCheckBox::indicator:checked {{
        background: {COLOR_ACCENT_BLUE_BORDER};
        border: 1px solid {COLOR_ACCENT_BLUE_BORDER};
    }}
    QCheckBox::indicator:hover {{
        border-color: {COLOR_ACCENT_BLUE_BORDER};
    }}
    QLineEdit {{
        background-color: {COLOR_BG_CARD};
        border: 1px solid {COLOR_BORDER_DEFAULT};
        border-radius: 4px;
        color: {COLOR_TEXT_PRIMARY};
        padding: 6px 10px;
        font-size: 11px;
    }}
    QLineEdit:focus {{
        border: 1px solid {COLOR_ACCENT_BLUE_BORDER};
    }}
    QLabel {{
        font-size: 11px;
    }}
"""
