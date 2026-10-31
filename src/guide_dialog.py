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
            ("Click & Mouse Controls", [
                "1 Click: Play / Pause with white tactile flash.",
                "2 Clicks: Double-tap right side to skip track, left side to rewind (shows symbols in mouth).",
                "3 Clicks: Open Minimal Player (playback, queue, search downloader, and settings).",
                "Scroll Wheel: Adjust volume smoothly (whisper-quiet logarithmic curve down to 1%).",
                "Right-Click Drag: Quickly drag Talia anywhere without entering Move Mode."
            ]),
            ("Move Mode & Resizing", [
                "Hold Talia for 0.7s until SFX plays to toggle Move Mode (or press F8).",
                "In Move Mode: Drag Talia and lyrics freely; scroll mouse wheel to resize scale.",
                "Hold Talia again or press F8 to lock positions."
            ]),
            ("Power Down & Exit", [
                "Hold Talia for 2 seconds to initiate power-down and close the app."
            ]),
            ("Global Keyboard Shortcuts", [
                "F7 : Toggle Synced Lyrics Overlay on / off",
                "F8 : Toggle Move Mode (reposition Talia & lyrics)",
                "F9 : Hide / Show Talia and lyrics overlay",
                "F10: Switch Local Player Mode vs Desktop Audio Mode",
                "F11: Toggle Eco Mode (< 1% CPU, 30 FPS)",
                "Ctrl+[ / Ctrl+] : Nudge lyric sync offset by -0.25s / +0.25s in real time"
            ]),
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
            "<b>Playback Modes & Features:</b><br>"
            "• <b>Player Mode:</b> Plays your local audio files (.opus, .mp3, .flac) with continuous title marquee in mouth and synced lyrics.<br>"
            "• <b>Desktop Audio:</b> Connects to PC audio output (browser, Spotify, games, osu!) for live reactive visuals.<br>"
            "• <b>Automated Lyrics Fetcher:</b> Open Settings &gt; Lyrics and click <i>'Launch Automated Lyric Fetcher'</i> to batch download synced lyrics.<br><br>"
            "<i>Tip: You can re-open this guide anytime from the Settings dialog under 'Controls Guide'.</i>"
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
