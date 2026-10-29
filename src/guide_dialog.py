"""
Controls and Shortcuts Guide Dialog for Talia.
Provides clear instructions on startup with a 'Never show again' preference.
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QFrame, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QFont

from config import ICON_PATH, save_settings, load_settings


class GuideDialog(QDialog):
    """Clean, high-contrast modal dialog explaining Talia's controls and shortcuts."""

    def __init__(self, parent=None, config: dict = None):
        super().__init__(parent)
        self.config = config or {}

        self.setWindowTitle("TALIA // CONTROLS & SHORTCUTS")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.setMinimumSize(540, 560)
        self.resize(580, 620)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.setStyleSheet("""
            QDialog {
                background-color: #0b0d13;
                color: #d1d9e6;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #d1d9e6;
                font-size: 13px;
                line-height: 1.5;
            }
            QCheckBox {
                color: #8b9cb3;
                font-size: 12px;
                font-weight: 500;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #38d9d9;
                background: #141722;
                border-radius: 2px;
            }
            QCheckBox::indicator:checked {
                background: #38d9d9;
            }
            QPushButton#btnClose {
                background-color: #141f26;
                color: #38d9d9;
                border: 1px solid #285d66;
                font-size: 12px;
                font-weight: bold;
                padding: 10px 24px;
                letter-spacing: 1px;
                border-radius: 3px;
            }
            QPushButton#btnClose:hover {
                background-color: #1e3a42;
                border-color: #38d9d9;
                color: #ffffff;
            }
        """)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header Title
        title_lbl = QLabel("CONTROLS & SHORTCUTS")
        title_lbl.setStyleSheet("color: #38d9d9; font-size: 16px; font-weight: bold; letter-spacing: 1.5px;")
        layout.addWidget(title_lbl)

        # Subtle separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("border: none; border-top: 1px solid #242938;")
        layout.addWidget(line)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(4, 4, 12, 4)
        content_layout.setSpacing(14)

        guide_items = [
            ("Hold until an sfx plays to initiate move mode", [
                "Scroll up and down to scale Talia",
                "Move around Talia to desired position",
                "Hold until an sfx plays to bring back to Default mode"
            ]),
            ("Press Talia once to play/pause", []),
            ("Press Talia twice on the right to skip song and twice on the left to backtrack to the song before", []),
            ("Press Talia thrice to open settings", [
                "Load folder first to play actual songs when in local music player mode (load the music -> Cyberpunk Edgerunners folder that's already included in the download to play CPE songs)"
            ]),
            ("Hold Talia for 2 seconds to close", []),
        ]

        for main_text, sub_items in guide_items:
            item_box = QWidget()
            item_layout = QVBoxLayout(item_box)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(4)

            main_lbl = QLabel(f"• <b>{main_text}</b>")
            main_lbl.setWordWrap(True)
            main_lbl.setStyleSheet("color: #e2e8f0; font-size: 13px;")
            item_layout.addWidget(main_lbl)

            for sub in sub_items:
                sub_lbl = QLabel(f"   <span style='color: #38d9d9;'>›</span> <span style='color: #94a3b8;'>{sub}</span>")
                sub_lbl.setWordWrap(True)
                sub_lbl.setStyleSheet("font-size: 12px; margin-left: 12px;")
                item_layout.addWidget(sub_lbl)

            content_layout.addWidget(item_box)

        # Note block regarding Desktop Mode vs Local Player
        note_frame = QFrame()
        note_frame.setStyleSheet("background-color: #121622; border: 1px solid #232a3d; border-radius: 4px; padding: 8px;")
        note_layout = QVBoxLayout(note_frame)
        note_layout.setContentsMargins(12, 10, 12, 10)

        note_txt = QLabel(
            "<b>Mode Switch:</b><br>"
            "Switch Talia to <b>Desktop Mode</b> (press <b>F10</b> or use the controller) to make her a global play/pause, skip, and volume control for desktop apps, games, or browser audio.<br><br>"
            "Switch Talia to <b>Local Music Player</b> mode to play music files directly from your computer with synchronized lyrics."
        )
        note_txt.setWordWrap(True)
        note_txt.setStyleSheet("color: #cbd5e1; font-size: 12px; line-height: 1.4;")
        note_layout.addWidget(note_txt)
        content_layout.addWidget(note_frame)

        content_layout.addStretch()
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

        # Bottom Bar: Checkbox and Close button
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(12)

        self.chk_never_show = QCheckBox("Never show this again")
        self.chk_never_show.setChecked(not self.config.get("show_startup_guide", True))
        self.chk_never_show.toggled.connect(self.on_checkbox_toggled)
        bottom_layout.addWidget(self.chk_never_show)

        bottom_layout.addStretch()

        btn_close = QPushButton("GOT IT")
        btn_close.setObjectName("btnClose")
        btn_close.clicked.connect(self.on_close)
        bottom_layout.addWidget(btn_close)

        layout.addLayout(bottom_layout)

    def on_checkbox_toggled(self, checked: bool):
        self.save_guide_preference()

    def save_guide_preference(self):
        show_guide = not self.chk_never_show.isChecked()
        self.config["show_startup_guide"] = show_guide
        if self.parent() and hasattr(self.parent(), "show_startup_guide"):
            self.parent().show_startup_guide = show_guide
        try:
            current_disk = load_settings()
            current_disk["show_startup_guide"] = show_guide
            save_settings(current_disk)
        except Exception as e:
            print(f"[GUIDE] Error saving preference: {e}")

    def on_close(self):
        self.save_guide_preference()
        self.accept()

    def closeEvent(self, event):
        self.save_guide_preference()
        super().closeEvent(event)

    def reject(self):
        self.save_guide_preference()
        super().reject()
