"""
Controls and Shortcuts Guide Dialog for Talia.
Provides clear instructions on startup with a 'Never show again' preference.
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QFrame, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from config import ICON_PATH, save_settings, load_settings


class GuideDialog(QDialog):
    """Clean, modern dialog explaining Talia's controls and shortcuts."""

    def __init__(self, parent=None, config: dict = None):
        super().__init__(parent)
        self.config = config or {}

        self.setWindowTitle("Controls & Shortcuts")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.setMinimumSize(540, 560)
        self.resize(580, 620)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.setStyleSheet("""
            QDialog {
                background-color: #18181b;
                color: #f4f4f5;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #f4f4f5;
                font-size: 13px;
                line-height: 1.5;
            }
            QCheckBox {
                color: #a1a1aa;
                font-size: 12px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #3f3f46;
                background: #202024;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background: #3b82f6;
                border-color: #3b82f6;
            }
            QPushButton#btnClose {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #3b82f6;
                font-size: 12px;
                font-weight: 500;
                padding: 8px 24px;
                border-radius: 4px;
            }
            QPushButton#btnClose:hover {
                background-color: #1d4ed8;
            }
        """)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header Title
        title_lbl = QLabel("Controls & Shortcuts")
        title_lbl.setStyleSheet("color: #f4f4f5; font-size: 16px; font-weight: 600;")
        layout.addWidget(title_lbl)

        # Subtle separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("border: none; border-top: 1px solid #27272a;")
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
            ("Press 'P' or click Talia once to play/pause", [
                "Single tap on keyboard or mascot toggles audio playback immediately."
            ]),
            ("Double-press 'P' or double-click Talia on the right to skip song", [
                "Two quick taps of 'P' or a double-click on the right side of Talia advances to the next track.",
                "Double-click on the left side of Talia backtracks to the previous song."
            ]),
            ("Hold Talia to enter Move Mode", [
                "Scroll mouse wheel to resize Talia",
                "Drag to reposition anywhere on your desktop",
                "Hold again to lock in place"
            ]),
            ("Click Talia 3 times to open Controller", [
                "Opens the control panel where you can browse library files, search and download songs, adjust lyrics, and customize visuals."
            ]),
            ("Hold Talia for 2 seconds to close the app", []),
        ]

        for main_text, sub_items in guide_items:
            item_box = QWidget()
            item_layout = QVBoxLayout(item_box)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(4)

            main_lbl = QLabel(f"• <b>{main_text}</b>")
            main_lbl.setWordWrap(True)
            main_lbl.setStyleSheet("color: #f4f4f5; font-size: 13px;")
            item_layout.addWidget(main_lbl)

            for sub in sub_items:
                sub_lbl = QLabel(f"   <span style='color: #3b82f6;'>›</span> <span style='color: #a1a1aa;'>{sub}</span>")
                sub_lbl.setWordWrap(True)
                sub_lbl.setStyleSheet("font-size: 12px; margin-left: 12px;")
                item_layout.addWidget(sub_lbl)

            content_layout.addWidget(item_box)

        # Note block regarding Modes & Lyrics
        note_frame = QFrame()
        note_frame.setStyleSheet("background-color: #202024; border: 1px solid #3f3f46; border-radius: 4px; padding: 10px;")
        note_layout = QVBoxLayout(note_frame)
        note_layout.setContentsMargins(12, 10, 12, 10)
        note_layout.setSpacing(8)

        note_txt = QLabel(
            "<b>Playback Modes:</b><br>"
            "• <b>Player Mode:</b> Plays your local music files with synchronized desktop lyrics.<br>"
            "• <b>Desktop Audio:</b> Connects to system audio (browser, Spotify, games) for live reactive visuals.<br><br>"
            "<b>Eco Mode (< 1% CPU):</b><br>"
            "Press <b>F11</b> or toggle Eco Mode in the controller to minimize CPU usage while keeping responsive music playback.<br><br>"
            "<i>Note: Some songs may not have available or synchronized lyrics.</i>"
        )
        note_txt.setWordWrap(True)
        note_txt.setStyleSheet("color: #d4d4d8; font-size: 12px; line-height: 1.4;")
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

        btn_close = QPushButton("Close")
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
