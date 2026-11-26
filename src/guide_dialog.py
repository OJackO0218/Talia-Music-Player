"""
Controls and Shortcuts Guide Dialog for Talia.
Provides clear instructions on startup with a 'Never show again' preference.
"""

import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import ICON_PATH, load_settings, save_settings
from ui_widgets import DraggableClampedDialogMixin

log = logging.getLogger(__name__)


class GuideDialog(DraggableClampedDialogMixin, QDialog):
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
            (
                "Click & Mouse Controls",
                [
                    "1 Click: Play / Pause (starts ★ Random Mix when selected).",
                    "2 Clicks: Double-tap right side to skip track, left side to rewind (shows symbols in mouth).",
                    "3 Clicks: Open / close Player Control Panel (library, queue, Random Mix, and tools).",
                    "Middle-Click: Save currently playing ★ Random Mix song permanently to Downloaded Songs.",
                    "Middle / Right-Click Drag: Quickly reposition Talia anywhere on screen.",
                    "Scroll Wheel: Adjust volume smoothly (logarithmic curve down to 1%).",
                ],
            ),
            (
                "Move Mode & Resizing",
                [
                    "Hold Talia for 0.7s until SFX plays to toggle Move Mode.",
                    "In Move Mode: Drag Talia and lyrics freely; scroll mouse wheel to resize scale.",
                    "Hold Talia again or click to lock positions.",
                ],
            ),
            (
                "Power Down & Exit",
                ["Hold Talia for 2 seconds to initiate power-down and close the app."],
            ),
            (
                "Controls & Shortcuts",
                [
                    "System Tray: Left-click tray icon in hidden icons to show/hide Talia.",
                    "System Tray: Right-click tray icon for playback controls, panel & exit.",
                    "Ctrl+[ / Ctrl+] : Nudge lyric sync offset by -0.25s / +0.25s in real time.",
                ],
            ),
            (
                "Credits & Attribution",
                [
                    "Original Character Artwork: Dreamoon-Q (@dreamoon131 on X / Twitter)",
                    "Live2D Slicing, Rigging, Expressions & Animations: Modified by JackO",
                ],
            ),
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
                sub_lbl = QLabel(
                    f"   <span style='color: #3b82f6;'>›</span> <span style='color: #a1a1aa;'>{sub}</span>"
                )
                sub_lbl.setWordWrap(True)
                sub_lbl.setStyleSheet("font-size: 12px; margin-left: 12px;")
                item_layout.addWidget(sub_lbl)
            content_layout.addWidget(item_box)

        # Note block regarding Modes & Lyrics
        note_frame = QFrame()
        note_frame.setStyleSheet(
            "background-color: #202024; border: 1px solid #3f3f46; border-radius: 4px; padding: 10px;"
        )
        note_layout = QVBoxLayout(note_frame)
        note_layout.setContentsMargins(12, 10, 12, 10)
        note_layout.setSpacing(8)
        note_txt = QLabel(
            "<b>What's New in v2.6:</b><br>"
            "• <b>★ Random Mix:</b> Endless taste-based track discovery with Exclusion Checklist (<i>EXCLUDE</i>), 5-song sliding buffer, and Middle-Click to save.<br>"
            "• <b>Lyrics & Calibration Studio:</b> Integrated visual timeline + <i>[Space]</i> beat alignment inside Settings &gt; Lyrics &amp; Fonts.<br>"
            "• <b>Listen Together &amp; Spotify Sync:</b> Shared party rooms and direct playlist importing.<br><br>"
            "<i>Tip: Re-open this guide anytime from Settings &gt; Updates &amp; App &gt; Controls &amp; Hotkeys Guide.</i>"
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
            log.info(f"[GUIDE] Error saving preference: {e}")

    def on_close(self):
        self.save_guide_preference()
        self.accept()

    def closeEvent(self, event):
        self.save_guide_preference()
        super().closeEvent(event)

    def reject(self):
        self.save_guide_preference()
        super().reject()
