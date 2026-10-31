import os
import sys
import subprocess
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QCheckBox, QPushButton, QFileDialog, QComboBox,
    QListWidget, QListWidgetItem, QScrollArea, QFrame, QApplication, QColorDialog,
    QLineEdit, QMenu, QTextEdit, QPlainTextEdit, QDialog
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QPointF, QSize
from PyQt6.QtGui import QIcon, QColor, QAction, QFont, QFontMetrics, QPainter, QPixmap

from config import (
    user32, VK_F7, VK_F8, VK_F9, VK_F10, VK_F11, VK_CONTROL, VK_OEM_4, VK_OEM_6, COLOR_THEMES, MIN_CHAR_SIZE, MAX_CHAR_SIZE,
    save_settings, PROJECT_ROOT, ICON_PATH, FONTS_DIR, PNGS_DIR, trim_process_memory
)
from audio_engine import CyberAudioEngine
from overlay import OverlayWindow
from guide_dialog import GuideDialog
from song_downloader import SongDownloaderService

SHARED_PANEL_STYLE = """
    QWidget {
        background-color: #18181b;
        color: #f4f4f5;
        font-family: 'Segoe UI', Arial, sans-serif;
    }
    QScrollArea {
        border: none;
        background-color: transparent;
    }
    QScrollBar:vertical {
        border: none;
        background: #18181b;
        width: 6px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #3f3f46;
        min-height: 24px;
        border-radius: 3px;
    }
    QScrollBar::handle:vertical:hover {
        background: #52525b;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QPushButton {
        background-color: #27272a;
        border: 1px solid #3f3f46;
        color: #f4f4f5;
        border-radius: 4px;
        padding: 6px 12px;
        font-weight: 500;
        font-size: 11px;
    }
    QPushButton:hover {
        background-color: #3f3f46;
        border-color: #52525b;
        color: #ffffff;
    }
    QPushButton:pressed {
        background-color: #202024;
    }
    QPushButton:disabled {
        background-color: #202024;
        border-color: #27272a;
        color: #52525b;
    }
    QPushButton#btnPrimary {
        background-color: #2563eb;
        border: 1px solid #3b82f6;
        color: #ffffff;
    }
    QPushButton#btnPrimary:hover {
        background-color: #1d4ed8;
    }
    QPushButton#btnExitApp {
        background-color: #27272a;
        color: #f87171;
        border: 1px solid #451a1a;
        border-radius: 4px;
        padding: 7px;
        font-size: 11px;
        font-weight: 500;
    }
    QPushButton#btnExitApp:hover {
        background-color: #7f1d1d;
        color: #ffffff;
        border-color: #b91c1c;
    }
    QComboBox {
        background-color: #202024;
        border: 1px solid #3f3f46;
        border-radius: 4px;
        color: #f4f4f5;
        padding: 5px 10px;
        font-size: 11px;
    }
    QComboBox:hover {
        border-color: #3b82f6;
    }
    QComboBox QAbstractItemView {
        background-color: #202024;
        border: 1px solid #3f3f46;
        color: #f4f4f5;
        selection-background-color: #3b82f6;
        selection-color: #ffffff;
    }
    QListWidget {
        background-color: #202024;
        border: 1px solid #3f3f46;
        border-radius: 4px;
        color: #e4e4e7;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 11px;
        padding: 4px;
    }
    QListWidget::item {
        padding: 5px 8px;
        border-radius: 3px;
        border-bottom: 1px solid #27272a;
    }
    QListWidget::item:hover {
        background-color: #27272a;
        color: #ffffff;
    }
    QListWidget::item:selected {
        background-color: #2e3547;
        color: #ffffff;
        border-left: 3px solid #3b82f6;
    }
    QSlider::groove:horizontal {
        height: 4px;
        background: #3f3f46;
        border-radius: 2px;
    }
    QSlider::sub-page:horizontal {
        background: #3b82f6;
        border-radius: 2px;
    }
    QSlider::handle:horizontal {
        background: #ffffff;
        border: 1px solid #71717a;
        width: 14px;
        height: 14px;
        margin-top: -5px;
        margin-bottom: -5px;
        border-radius: 7px;
    }
    QSlider::handle:horizontal:hover {
        background: #ffffff;
        border: 1px solid #3b82f6;
    }
    QCheckBox {
        spacing: 8px;
        color: #d4d4d8;
        font-size: 11px;
    }
    QCheckBox::indicator {
        width: 14px;
        height: 14px;
        border: 1px solid #3f3f46;
        border-radius: 3px;
        background: #202024;
    }
    QCheckBox::indicator:checked {
        background: #3b82f6;
        border: 1px solid #3b82f6;
    }
    QCheckBox::indicator:hover {
        border-color: #3b82f6;
    }
    QLabel {
        font-size: 11px;
    }
"""


def create_section_header(title: str) -> QWidget:
    """Creates a clean, minimal section header with a subtle separator."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 10, 0, 4)
    layout.setSpacing(4)

    lbl = QLabel(title)
    lbl.setStyleSheet("color: #a1a1aa; font-weight: 600; font-size: 11px;")
    layout.addWidget(lbl)

    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Plain)
    line.setStyleSheet("border: none; border-top: 1px solid #27272a; max-height: 1px;")
    layout.addWidget(line)

    return container


class SettingsDialog(QDialog):
    """Clean, dedicated settings dialog for advanced lyrics, visualizer, and character configuration."""

    def __init__(self, panel: "ControlPanel"):
        super().__init__()
        self.panel = panel
        self.setWindowTitle("Talia Settings")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumSize(460, 560)
        self.resize(480, 740)
        self.setStyleSheet(SHARED_PANEL_STYLE)
        self.init_ui()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(14, 14, 14, 14)
        content_layout.setSpacing(10)

        # --- SECTION: MODES & WINDOW STATE ---
        content_layout.addWidget(create_section_header("Playback Modes"))

        hbox_modes = QHBoxLayout()
        hbox_modes.setSpacing(6)

        self.btn_move_talia = QPushButton("Lock Window")
        self.btn_move_talia.clicked.connect(self.panel.toggle_move_talia)
        hbox_modes.addWidget(self.btn_move_talia)

        self.btn_audio_mode = QPushButton("Player Mode")
        self.btn_audio_mode.clicked.connect(self.panel.toggle_audio_mode)
        hbox_modes.addWidget(self.btn_audio_mode)

        self.btn_lyrics = QPushButton("Lyrics: On")
        self.btn_lyrics.setStyleSheet("background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: bold; font-size: 11px; padding: 7px 8px;")
        self.btn_lyrics.clicked.connect(self.panel.toggle_lyrics)
        hbox_modes.addWidget(self.btn_lyrics)

        self.btn_eco = QPushButton("Eco Mode: Off")
        self.btn_eco.setToolTip("Toggle Eco Mode (< 1% CPU) [F11]")
        self.btn_eco.clicked.connect(self.panel.toggle_eco_mode)
        hbox_modes.addWidget(self.btn_eco)

        content_layout.addLayout(hbox_modes)

        # --- SECTION: MUSIC FOLDER & LIBRARY ---
        content_layout.addWidget(create_section_header("Music Folder"))

        self.lbl_folder_path = QLabel(f"{self.panel.audio_engine.folder_path}")
        self.lbl_folder_path.setStyleSheet("color: #71717a; font-size: 10px;")
        self.lbl_folder_path.setWordWrap(True)
        content_layout.addWidget(self.lbl_folder_path)

        hbox_folder_btns = QHBoxLayout()
        btn_choose = QPushButton("Change Folder")
        btn_choose.clicked.connect(self.panel.choose_music_folder)
        hbox_folder_btns.addWidget(btn_choose)

        btn_open_exp = QPushButton("Open in Explorer")
        btn_open_exp.clicked.connect(self.panel.open_music_folder_explorer)
        hbox_folder_btns.addWidget(btn_open_exp)

        btn_refresh = QPushButton("Refresh Library")
        btn_refresh.clicked.connect(self.panel.refresh_tracklist)
        hbox_folder_btns.addWidget(btn_refresh)
        content_layout.addLayout(hbox_folder_btns)

        # --- SECTION: LYRICS ---
        content_layout.addWidget(create_section_header("Lyrics"))

        # Launch automated lyrics fetcher tool
        self.btn_open_fetcher = QPushButton("Launch Automated Lyric Fetcher")
        self.btn_open_fetcher.setToolTip("Open the automated lyrics fetcher and calibration tool")
        self.btn_open_fetcher.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 600;
                font-size: 11px;
                margin-top: 2px;
                margin-bottom: 4px;
            }
            QPushButton:hover {
                background-color: #0284c7;
                color: #ffffff;
            }
        """)
        self.btn_open_fetcher.clicked.connect(self.panel.open_lyric_fetcher)
        content_layout.addWidget(self.btn_open_fetcher)

        self.lbl_lyric_disclaimer = QLabel("Note: Some songs may not have available or synchronized lyrics.")
        self.lbl_lyric_disclaimer.setStyleSheet("color: #71717a; font-size: 10px; font-style: italic; margin-top: 2px; margin-bottom: 4px;")
        self.lbl_lyric_disclaimer.setWordWrap(True)
        content_layout.addWidget(self.lbl_lyric_disclaimer)

        # Font dropdown row
        hbox_font = QHBoxLayout()
        lbl_font_title = QLabel("Font:")
        lbl_font_title.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        hbox_font.addWidget(lbl_font_title)

        self.combo_font = QComboBox()
        self.combo_font.currentTextChanged.connect(self.panel.on_font_changed)
        hbox_font.addWidget(self.combo_font, 1)

        self.btn_open_fonts = QPushButton("Open Folder")
        self.btn_open_fonts.setToolTip("Open assets/fonts/ folder to add .ttf/.otf fonts")
        self.btn_open_fonts.clicked.connect(self.panel.open_fonts_folder)
        hbox_font.addWidget(self.btn_open_fonts)

        self.btn_reload_fonts = QPushButton("Reload")
        self.btn_reload_fonts.setToolTip("Re-scan fonts folder")
        self.btn_reload_fonts.clicked.connect(self.panel.reload_custom_fonts)
        hbox_font.addWidget(self.btn_reload_fonts)
        content_layout.addLayout(hbox_font)

        # Color row
        hbox_lyric_color = QHBoxLayout()
        lbl_lyric_col = QLabel("Color:")
        lbl_lyric_col.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        hbox_lyric_color.addWidget(lbl_lyric_col)

        self.combo_lyric_color = QComboBox()
        for name in self.panel.lyric_presets.keys():
            self.combo_lyric_color.addItem(name)
        self.combo_lyric_color.addItem("Custom...")
        self.combo_lyric_color.currentTextChanged.connect(self.panel.on_lyric_preset_changed)
        hbox_lyric_color.addWidget(self.combo_lyric_color, 1)

        self.btn_pick_color = QPushButton("Custom Color")
        self.btn_pick_color.clicked.connect(self.panel.choose_custom_lyric_color)
        hbox_lyric_color.addWidget(self.btn_pick_color)
        content_layout.addLayout(hbox_lyric_color)

        self.chk_word_glow = QCheckBox("Word highlight animation")
        self.chk_word_glow.setChecked(True)
        self.chk_word_glow.toggled.connect(self.panel.on_word_glow_toggled)
        content_layout.addWidget(self.chk_word_glow)

        # Sync offset controls
        hbox_sync = QHBoxLayout()
        lbl_sync_title = QLabel("Sync:")
        lbl_sync_title.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        hbox_sync.addWidget(lbl_sync_title)

        btn_minus_half = QPushButton("-0.5s")
        btn_minus_half.setToolTip("Shift lyrics 0.5s earlier (Hotkeys: Ctrl+[ / Ctrl+])")
        btn_minus_half.clicked.connect(lambda: self.panel.adjust_lyrics_offset(-0.5))
        hbox_sync.addWidget(btn_minus_half)

        btn_minus_tenth = QPushButton("-0.1s")
        btn_minus_tenth.clicked.connect(lambda: self.panel.adjust_lyrics_offset(-0.1))
        hbox_sync.addWidget(btn_minus_tenth)

        self.lbl_sync_offset = QLabel("+0.00s")
        self.lbl_sync_offset.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sync_offset.setStyleSheet("color: #f4f4f5; font-weight: 600; min-width: 50px;")
        hbox_sync.addWidget(self.lbl_sync_offset)

        btn_plus_tenth = QPushButton("+0.1s")
        btn_plus_tenth.clicked.connect(lambda: self.panel.adjust_lyrics_offset(0.1))
        hbox_sync.addWidget(btn_plus_tenth)

        btn_plus_half = QPushButton("+0.5s")
        btn_plus_half.clicked.connect(lambda: self.panel.adjust_lyrics_offset(0.5))
        hbox_sync.addWidget(btn_plus_half)

        btn_sync_reset = QPushButton("Reset")
        btn_sync_reset.clicked.connect(self.panel.reset_lyrics_offset)
        hbox_sync.addWidget(btn_sync_reset)

        btn_auto_sync = QPushButton("Auto-Sync")
        btn_auto_sync.setToolTip("Automatically align audio start with lyrics timestamp")
        btn_auto_sync.clicked.connect(self.panel.auto_sync_lyrics)
        hbox_sync.addWidget(btn_auto_sync)
        content_layout.addLayout(hbox_sync)

        # --- SECTION: VISUALIZER CONFIGURATION ---
        content_layout.addWidget(create_section_header("Visualizer"))

        hbox_style = QHBoxLayout()
        lbl_vis_mode = QLabel("Style:")
        lbl_vis_mode.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        hbox_style.addWidget(lbl_vis_mode)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Cyber Bars", "Neon Wave", "Radial Core", "Dual Mirror"])
        self.combo_mode.currentTextChanged.connect(self.panel.on_vis_mode_changed)
        hbox_style.addWidget(self.combo_mode)

        lbl_vis_theme = QLabel("Palette:")
        lbl_vis_theme.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        hbox_style.addWidget(lbl_vis_theme)

        self.combo_theme = QComboBox()
        self.combo_theme.addItems(list(COLOR_THEMES.keys()))
        self.combo_theme.currentTextChanged.connect(self.panel.on_vis_theme_changed)
        hbox_style.addWidget(self.combo_theme)
        content_layout.addLayout(hbox_style)

        # --- SECTION: CHARACTER & DISPLAY ---
        content_layout.addWidget(create_section_header("Character"))

        # Eye sensitivity
        hbox_sens = QHBoxLayout()
        lbl_sens = QLabel("Eye Sensitivity:")
        lbl_sens.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        hbox_sens.addWidget(lbl_sens)

        self.slider_eye_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_eye_sens.setRange(20, 300)
        self.slider_eye_sens.setValue(100)
        self.slider_eye_sens.valueChanged.connect(self.panel.on_eye_sens_changed)
        hbox_sens.addWidget(self.slider_eye_sens)

        self.lbl_sens_val = QLabel("1.0x")
        self.lbl_sens_val.setFixedWidth(36)
        self.lbl_sens_val.setStyleSheet("color: #f4f4f5; font-family: 'Consolas', monospace; font-weight: 600;")
        hbox_sens.addWidget(self.lbl_sens_val)
        content_layout.addLayout(hbox_sens)

        # Character size
        hbox_sz = QHBoxLayout()
        lbl_sz = QLabel("Character Scale:")
        lbl_sz.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        hbox_sz.addWidget(lbl_sz)

        self.slider_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_size.setRange(MIN_CHAR_SIZE, MAX_CHAR_SIZE)
        self.slider_size.setValue(self.panel.overlay.width())
        self.slider_size.valueChanged.connect(self.panel.on_size_change)
        hbox_sz.addWidget(self.slider_size)
        content_layout.addLayout(hbox_sz)

        # Character opacity
        hbox_op = QHBoxLayout()
        lbl_op = QLabel("Opacity:")
        lbl_op.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        hbox_op.addWidget(lbl_op)

        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(20, 100)
        self.slider_opacity.setValue(100)
        self.slider_opacity.valueChanged.connect(self.panel.on_opacity_change)
        hbox_op.addWidget(self.slider_opacity)
        content_layout.addLayout(hbox_op)

        # Feature Toggles
        hbox_toggles = QHBoxLayout()
        self.chk_scanlines = QCheckBox("Scanlines")
        self.chk_scanlines.setChecked(True)
        self.chk_scanlines.toggled.connect(self.panel.on_scanlines_toggled)
        hbox_toggles.addWidget(self.chk_scanlines)

        self.chk_bass_pop = QCheckBox("Bass Reaction")
        self.chk_bass_pop.setChecked(True)
        self.chk_bass_pop.toggled.connect(self.panel.on_bass_pop_toggled)
        hbox_toggles.addWidget(self.chk_bass_pop)

        self.chk_widescreen = QCheckBox("Widescreen")
        self.chk_widescreen.setChecked(False)
        self.chk_widescreen.toggled.connect(self.panel.on_widescreen_toggled)
        hbox_toggles.addWidget(self.chk_widescreen)
        content_layout.addLayout(hbox_toggles)

        # --- SECTION: SETTINGS & ACTIONS ---
        content_layout.addWidget(create_section_header("Actions"))

        hbox_actions = QHBoxLayout()
        self.btn_save_settings = QPushButton("Save Settings")
        self.btn_save_settings.setObjectName("btnSaveSettings")
        self.btn_save_settings.clicked.connect(self.panel.save_settings_action)
        hbox_actions.addWidget(self.btn_save_settings)

        self.btn_show_guide = QPushButton("Controls Guide")
        self.btn_show_guide.clicked.connect(self.panel.show_guide_dialog)
        hbox_actions.addWidget(self.btn_show_guide)

        btn_reload = QPushButton("Reload Assets")
        btn_reload.clicked.connect(self.panel.reload_art)
        hbox_actions.addWidget(btn_reload)
        content_layout.addLayout(hbox_actions)

        self.btn_exit_app = QPushButton("Exit Talia")
        self.btn_exit_app.setObjectName("btnExitApp")
        self.btn_exit_app.clicked.connect(self.panel.overlay.close_application)
        content_layout.addWidget(self.btn_exit_app)

        scroll_area.setWidget(content_widget)
        root_layout.addWidget(scroll_area)

        self.populate_fonts()

    def populate_fonts(self):
        self.combo_font.blockSignals(True)
        curr = self.combo_font.currentText()
        self.combo_font.clear()

        available = ["Default (Segoe UI / Inter)"]
        if self.panel.lyrics_overlay and hasattr(self.panel.lyrics_overlay, "get_available_fonts"):
            available = self.panel.lyrics_overlay.get_available_fonts()

        for name in available:
            self.combo_font.addItem(name)

        active = getattr(self.panel.lyrics_overlay, "custom_font_family", None) if self.panel.lyrics_overlay else None
        if active and active in available:
            self.combo_font.setCurrentText(active)
        elif curr and curr in available:
            self.combo_font.setCurrentText(curr)
        else:
            self.combo_font.setCurrentIndex(0)
        self.combo_font.blockSignals(False)

    def closeEvent(self, event):
        self.hide()
        trim_process_memory()
        event.ignore()


class CyberScrollingTrackLabel(QWidget):
    # Track title marquee label in Rajdhani font
    def __init__(self, parent=None):
        super().__init__(parent)
        self.full_text = "No track loaded"
        self.scroll_x = 0.0
        self.scroll_speed = 36.0
        self.is_scrolling = False
        self.symbol_mode = None
        self.symbol_timer = 0.0

        # Load skip symbols
        self.icon_forward = QPixmap(os.path.join(PNGS_DIR, "icon_forward.png"))
        self.icon_backward = QPixmap(os.path.join(PNGS_DIR, "icon_backward.png"))

        self.setFixedHeight(26)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.setInterval(33)

        self.font = QFont("Rajdhani", 12, QFont.Weight.Bold)
        self.font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.5)

    def text(self) -> str:
        return self.full_text

    def setText(self, text: str):
        cleaned = text.strip() if text else "No track loaded"
        if cleaned != self.full_text:
            self.full_text = cleaned
            self.scroll_x = 0.0
            self._check_scroll_needed()
            self.update()

    def trigger_symbol(self, direction: str):
        # Display forward/backward symbol for 2.2 seconds
        self.symbol_mode = direction
        self.symbol_timer = 2.2
        if not self.timer.isActive() and self.isVisible():
            self.timer.start(33)
        self.update()

    def _check_scroll_needed(self):
        if self.full_text != "No track loaded" and self.isVisible():
            self.is_scrolling = True
            if not self.timer.isActive():
                self.timer.start(33)
        else:
            self.is_scrolling = False
            self.scroll_x = 0.0
            if self.symbol_timer <= 0.0:
                self.timer.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._check_scroll_needed()

    def showEvent(self, event):
        super().showEvent(event)
        self._check_scroll_needed()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.timer.stop()

    def _on_tick(self):
        dt = 0.033
        needs_update = False

        if self.symbol_timer > 0.0:
            self.symbol_timer -= dt
            if self.symbol_timer <= 0.0:
                self.symbol_mode = None
                self.symbol_timer = 0.0
            needs_update = True

        if self.is_scrolling and self.full_text != "No track loaded":
            self.scroll_x += self.scroll_speed * dt
            needs_update = True
        elif self.symbol_timer <= 0.0:
            self.timer.stop()

        if needs_update:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        metrics = QFontMetrics(self.font)
        baseline = (self.height() + metrics.ascent() - metrics.descent()) / 2.0

        x_start = 2
        if self.symbol_mode:
            icon = self.icon_forward if self.symbol_mode == "forward" else self.icon_backward
            if not icon.isNull():
                icon_h = min(16, self.height() - 6)
                icon_w = int(icon.width() * (icon_h / float(icon.height())))
                iy = int((self.height() - icon_h) / 2.0)
                painter.drawPixmap(x_start, iy, icon_w, icon_h, icon)
                x_start += icon_w + 8

        painter.setFont(self.font)
        painter.setPen(QColor("#f4f4f5"))

        avail_w = max(10, self.width() - x_start)
        painter.setClipRect(x_start, 0, avail_w, self.height())

        text_w = metrics.horizontalAdvance(self.full_text)
        if self.is_scrolling and self.full_text != "No track loaded":
            gap = 48
            span = text_w + gap
            curr_x = x_start - (self.scroll_x % span)
            painter.drawText(QPointF(curr_x, baseline), self.full_text)
            painter.drawText(QPointF(curr_x + span, baseline), self.full_text)
        else:
            painter.drawText(QPointF(x_start, baseline), self.full_text)


class ControlPanel(QWidget):
    """Clean, modern controller for Talia Music Player, Visualizer, and Settings."""

    def __init__(self, overlay: OverlayWindow, audio_engine: CyberAudioEngine, lyrics_overlay=None):
        super().__init__()
        self.overlay = overlay
        self.overlay.panel = self
        self.audio_engine = audio_engine
        self.lyrics_overlay = lyrics_overlay
        if self.lyrics_overlay:
            self.lyrics_overlay.panel = self

        self.lyric_presets = {
            "Pure White": "#ffffff",
            "Soft Blue": "#60a5fa",
            "Soft Cyan": "#38bdf8",
            "Soft Pink": "#f472b6",
            "Soft Purple": "#c084fc",
            "Soft Yellow": "#fde047",
            "Mint Green": "#4ade80",
        }

        self.last_f7_state = False
        self.last_bracket_left_state = False
        self.last_bracket_right_state = False
        self.last_f8_state = False
        self.last_f9_state = False
        self.last_f10_state = False
        self.last_f11_state = False
        self.is_user_scrubbing = False

        self.setWindowTitle("Talia Player")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        # Stylized minimal player window
        self.setMinimumSize(360, 480)
        self.resize(380, 560)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(SHARED_PANEL_STYLE)

        self.init_ui()

        # Dedicated Full Settings & Customization Dialog
        self.settings_dialog = SettingsDialog(self)

        # Direct attribute proxies for seamless backwards compatibility
        self.slider_size = self.settings_dialog.slider_size
        self.slider_opacity = self.settings_dialog.slider_opacity
        self.slider_eye_sens = self.settings_dialog.slider_eye_sens
        self.lbl_sens_val = self.settings_dialog.lbl_sens_val
        self.chk_scanlines = self.settings_dialog.chk_scanlines
        self.chk_bass_pop = self.settings_dialog.chk_bass_pop
        self.chk_widescreen = self.settings_dialog.chk_widescreen
        self.combo_mode = self.settings_dialog.combo_mode
        self.combo_theme = self.settings_dialog.combo_theme
        self.combo_lyric_color = self.settings_dialog.combo_lyric_color
        self.combo_font = self.settings_dialog.combo_font
        self.btn_pick_color = self.settings_dialog.btn_pick_color
        self.chk_word_glow = self.settings_dialog.chk_word_glow
        self.lbl_sync_offset = self.settings_dialog.lbl_sync_offset
        self.btn_save_settings = self.settings_dialog.btn_save_settings
        self.lbl_folder_path = self.settings_dialog.lbl_folder_path

        # Song Downloader & Auto-Sync Service (YouTube search -> Opus 160k -> Synced LRC)
        self.downloader = SongDownloaderService(self)
        self.downloader.search_finished.connect(self._on_search_finished)
        self.downloader.search_error.connect(self._on_search_error)
        self.downloader.download_progress.connect(self._on_download_progress)
        self.downloader.download_finished.connect(self._on_download_finished)

        # Polling timer for global hotkeys (50ms)
        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.timeout.connect(self.check_hotkeys)
        self.hotkey_timer.start(50)

        # Eco Mode & Download Destination state
        self.eco_mode = False
        self.saved_dl_folder = ""

        # Timeline & auto-advance timer (200ms)
        self.timeline_timer = QTimer(self)
        self.timeline_timer.timeout.connect(self.update_timeline)
        self.timeline_timer.start(200)

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # -------------------------------------------------------------
        # SCROLLABLE CONTENT BODY (Resizable)
        # -------------------------------------------------------------
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(12, 10, 12, 12)
        content_layout.setSpacing(8)

        # --- PRIMARY TOGGLES (Settings, Move, Mode, Lyrics, Eco) ---
        hbox_top_toggles = QHBoxLayout()
        hbox_top_toggles.setSpacing(4)

        self.btn_open_settings = QPushButton("⚙ Settings")
        self.btn_open_settings.setObjectName("btnOpenSettings")
        self.btn_open_settings.setToolTip("Open Full Settings & Customization")
        self.btn_open_settings.setStyleSheet(
            "background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; font-weight: 600; font-size: 11px; padding: 5px 8px;"
        )
        self.btn_open_settings.clicked.connect(self.open_settings_window)
        hbox_top_toggles.addWidget(self.btn_open_settings)

        self.btn_move_talia = QPushButton("Lock Window")
        self.btn_move_talia.setObjectName("btnMoveTalia")
        self.btn_move_talia.clicked.connect(self.toggle_move_talia)
        hbox_top_toggles.addWidget(self.btn_move_talia)

        self.btn_audio_mode = QPushButton("Player Mode")
        self.btn_audio_mode.setObjectName("btnAudioMode")
        self.btn_audio_mode.clicked.connect(self.toggle_audio_mode)
        hbox_top_toggles.addWidget(self.btn_audio_mode)

        self.btn_lyrics = QPushButton("Lyrics: On")
        self.btn_lyrics.setObjectName("btnLyrics")
        self.btn_lyrics.setStyleSheet("background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: bold; font-size: 11px; padding: 5px 8px;")
        self.btn_lyrics.clicked.connect(self.toggle_lyrics)
        hbox_top_toggles.addWidget(self.btn_lyrics)

        self.btn_eco = QPushButton("Eco Mode: Off")
        self.btn_eco.setObjectName("btnEco")
        self.btn_eco.setToolTip("Toggle Eco Mode (< 1% CPU) [F11]")
        self.btn_eco.clicked.connect(self.toggle_eco_mode)
        hbox_top_toggles.addWidget(self.btn_eco)

        content_layout.addLayout(hbox_top_toggles)

        # --- SECTION: PLAYBACK & VOLUME ---
        content_layout.addWidget(create_section_header("Playback & Volume"))

        # Track title banner (Cyberpunk Rajdhani marquee)
        self.lbl_track_title = CyberScrollingTrackLabel()
        content_layout.addWidget(self.lbl_track_title)

        # Timeline seeker
        hbox_time = QHBoxLayout()
        hbox_time.setSpacing(6)
        self.lbl_time_cur = QLabel("00:00")
        self.lbl_time_cur.setStyleSheet("color: #a1a1aa; font-family: 'Consolas', monospace; font-size: 11px;")
        self.slider_seek = QSlider(Qt.Orientation.Horizontal)
        self.slider_seek.setRange(0, 1000)
        self.slider_seek.setValue(0)
        self.slider_seek.sliderPressed.connect(self.on_seek_pressed)
        self.slider_seek.sliderReleased.connect(self.on_seek_released)
        self.slider_seek.sliderMoved.connect(self.on_seek_moved)
        self.lbl_time_dur = QLabel("00:00")
        self.lbl_time_dur.setStyleSheet("color: #a1a1aa; font-family: 'Consolas', monospace; font-size: 11px;")

        hbox_time.addWidget(self.lbl_time_cur)
        hbox_time.addWidget(self.slider_seek)
        hbox_time.addWidget(self.lbl_time_dur)
        content_layout.addLayout(hbox_time)

        # Playback Transport Buttons (Basic: Rewind, Play/Pause, Next + Shuffle)
        hbox_controls = QHBoxLayout()
        hbox_controls.setSpacing(6)
        btn_prev = QPushButton(" Rewind")
        icon_bw_path = os.path.join(PNGS_DIR, "icon_backward.png")
        if os.path.exists(icon_bw_path):
            btn_prev.setIcon(QIcon(icon_bw_path))
            btn_prev.setIconSize(QSize(13, 13))
        btn_prev.setFont(QFont("Rajdhani", 10, QFont.Weight.Bold))
        btn_prev.clicked.connect(self.on_prev_clicked)
        hbox_controls.addWidget(btn_prev)

        self.btn_play_pause = QPushButton("Play")
        self.btn_play_pause.setFont(QFont("Rajdhani", 10, QFont.Weight.Bold))
        self.btn_play_pause.setObjectName("btnPlayPause")
        self.btn_play_pause.setStyleSheet("background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: bold;")
        self.btn_play_pause.clicked.connect(self.on_play_pause_clicked)
        hbox_controls.addWidget(self.btn_play_pause)

        btn_next = QPushButton(" Next")
        icon_fw_path = os.path.join(PNGS_DIR, "icon_forward.png")
        if os.path.exists(icon_fw_path):
            btn_next.setIcon(QIcon(icon_fw_path))
            btn_next.setIconSize(QSize(13, 13))
        btn_next.setFont(QFont("Rajdhani", 10, QFont.Weight.Bold))
        btn_next.clicked.connect(self.on_next_clicked)
        hbox_controls.addWidget(btn_next)

        self.btn_shuffle = QPushButton("Shuffle: Off")
        self.btn_shuffle.setFont(QFont("Rajdhani", 10, QFont.Weight.Bold))
        self.btn_shuffle.clicked.connect(self.toggle_shuffle)
        hbox_controls.addWidget(self.btn_shuffle)
        content_layout.addLayout(hbox_controls)

        # Small Volume Slider
        hbox_vol = QHBoxLayout()
        hbox_vol.setSpacing(8)
        lbl_vol_title = QLabel("Vol:")
        lbl_vol_title.setStyleSheet("color: #a1a1aa; font-weight: 600; font-size: 11px;")
        hbox_vol.addWidget(lbl_vol_title)

        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(int(self.audio_engine.volume * 100))
        self.slider_vol.valueChanged.connect(self.on_volume_changed)
        hbox_vol.addWidget(self.slider_vol)

        self.lbl_vol_val = QLabel(f"{int(self.audio_engine.volume * 100)}%")
        self.lbl_vol_val.setFixedWidth(40)
        self.lbl_vol_val.setStyleSheet("color: #f4f4f5; font-family: 'Consolas', monospace; font-weight: 600; font-size: 11px;")
        hbox_vol.addWidget(self.lbl_vol_val)
        content_layout.addLayout(hbox_vol)

        # --- SECTION: SONG SELECTION ---
        content_layout.addWidget(create_section_header("Song Selection"))

        # Search Bar with live filter and clear button
        hbox_search = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search songs...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #202024;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
        """)
        self.search_input.textChanged.connect(self.filter_tracks)
        hbox_search.addWidget(self.search_input)

        self.btn_clear_search = QPushButton("✕")
        self.btn_clear_search.setFixedWidth(28)
        self.btn_clear_search.setStyleSheet("background-color: #27272a; color: #a1a1aa; border: 1px solid #3f3f46; font-weight: bold;")
        self.btn_clear_search.clicked.connect(lambda: self.search_input.clear())
        hbox_search.addWidget(self.btn_clear_search)
        content_layout.addLayout(hbox_search)

        self.btn_clear_search = QPushButton("✕")
        self.btn_clear_search.setFixedWidth(28)
        self.btn_clear_search.setStyleSheet("background-color: #27272a; color: #a1a1aa; border: 1px solid #3f3f46; font-weight: bold;")
        self.btn_clear_search.clicked.connect(lambda: self.search_input.clear())
        hbox_search.addWidget(self.btn_clear_search)
        content_layout.addLayout(hbox_search)

        self.list_tracks = QListWidget()
        self.list_tracks.setFixedHeight(120)
        self.list_tracks.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_tracks.customContextMenuRequested.connect(self.show_track_context_menu)
        self.list_tracks.itemDoubleClicked.connect(self.on_track_double_clicked)
        content_layout.addWidget(self.list_tracks)

        # Track & Queue Action Buttons
        hbox_track_actions = QHBoxLayout()
        self.btn_add_to_queue = QPushButton("+ Queue")
        self.btn_add_to_queue.setStyleSheet("background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; font-size: 10px; font-weight: 500; padding: 4px 8px;")
        self.btn_add_to_queue.clicked.connect(self.on_add_selected_to_queue)
        hbox_track_actions.addWidget(self.btn_add_to_queue)

        self.btn_toggle_queue = QPushButton("Queue (0)")
        self.btn_toggle_queue.setStyleSheet("background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; font-size: 10px; font-weight: 500; padding: 4px 8px;")
        self.btn_toggle_queue.clicked.connect(self.toggle_queue_panel)
        hbox_track_actions.addWidget(self.btn_toggle_queue)

        self.btn_clear_queue = QPushButton("Clear Queue")
        self.btn_clear_queue.setStyleSheet("background-color: #27272a; color: #f87171; border: 1px solid #3f3f46; font-size: 10px; padding: 4px 8px;")
        self.btn_clear_queue.clicked.connect(self.on_clear_queue_clicked)
        hbox_track_actions.addWidget(self.btn_clear_queue)
        content_layout.addLayout(hbox_track_actions)

        # Collapsible Upcoming Queue Container
        self.queue_container = QWidget()
        queue_layout = QVBoxLayout(self.queue_container)
        queue_layout.setContentsMargins(0, 4, 0, 4)
        queue_layout.setSpacing(4)

        lbl_queue_hdr = QLabel("Upcoming Queue:")
        lbl_queue_hdr.setStyleSheet("color: #a1a1aa; font-weight: 600; font-size: 10px;")
        queue_layout.addWidget(lbl_queue_hdr)

        self.list_queue = QListWidget()
        self.list_queue.setFixedHeight(85)
        self.list_queue.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_queue.customContextMenuRequested.connect(self.show_queue_context_menu)
        self.list_queue.itemDoubleClicked.connect(self.on_queue_item_double_clicked)
        queue_layout.addWidget(self.list_queue)
        self.queue_container.setVisible(False)
        content_layout.addWidget(self.queue_container)

        # --- SECTION: SONG SEARCH & AUTO-DOWNLOAD ---
        content_layout.addWidget(create_section_header("Download Songs"))

        # Download Destination Folder Dropdown Row
        hbox_dl_folder = QHBoxLayout()
        hbox_dl_folder.setSpacing(6)
        lbl_dl_folder = QLabel("Save to:")
        lbl_dl_folder.setStyleSheet("color: #a1a1aa; font-size: 11px; font-weight: 500;")
        hbox_dl_folder.addWidget(lbl_dl_folder)

        self.combo_dl_folder = QComboBox()
        self.combo_dl_folder.setStyleSheet("""
            QComboBox {
                background-color: #202024;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                color: #f4f4f5;
                padding: 4px 8px;
                font-size: 11px;
            }
            QComboBox:hover {
                border-color: #52525b;
            }
            QComboBox QAbstractItemView {
                background-color: #18181b;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                selection-background-color: #3b82f6;
                selection-color: #ffffff;
            }
        """)
        self.combo_dl_folder.currentIndexChanged.connect(self.on_dl_folder_changed)
        hbox_dl_folder.addWidget(self.combo_dl_folder, 1)
        content_layout.addLayout(hbox_dl_folder)

        # Search Input row
        hbox_dl_search = QHBoxLayout()
        hbox_dl_search.setSpacing(6)
        self.edit_dl_search = QLineEdit()
        self.edit_dl_search.setPlaceholderText("Search YouTube (e.g. Hate Me Ellie Goulding) or paste URL...")
        self.edit_dl_search.setStyleSheet("""
            QLineEdit {
                background-color: #202024;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
        """)
        self.edit_dl_search.returnPressed.connect(self.on_dl_search_clicked)
        hbox_dl_search.addWidget(self.edit_dl_search)

        self.btn_dl_search = QPushButton("Search")
        self.btn_dl_search.setStyleSheet("background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: 500; font-size: 11px; padding: 5px 12px;")
        self.btn_dl_search.clicked.connect(self.on_dl_search_clicked)
        hbox_dl_search.addWidget(self.btn_dl_search)
        content_layout.addLayout(hbox_dl_search)

        # Search Results List (Collapsible / Dynamic)
        self.list_dl_results = QListWidget()
        self.list_dl_results.setFixedHeight(95)
        self.list_dl_results.setStyleSheet("""
            QListWidget {
                background-color: #202024;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                color: #f4f4f5;
                font-size: 11px;
                padding: 2px;
            }
            QListWidget::item {
                padding: 4px 6px;
                border-bottom: 1px solid #27272a;
            }
            QListWidget::item:selected {
                background-color: #3b82f6;
                color: #ffffff;
            }
        """)
        self.list_dl_results.itemDoubleClicked.connect(self.on_dl_item_double_clicked)
        self.list_dl_results.itemSelectionChanged.connect(self.on_dl_selection_changed)
        self.list_dl_results.setVisible(False)
        content_layout.addWidget(self.list_dl_results)

        # Download Action Button
        self.btn_dl_action = QPushButton("+ Add to Library")
        self.btn_dl_action.setStyleSheet("background-color: #166534; color: #4ade80; border: 1px solid #22c55e; font-size: 11px; font-weight: 600; padding: 6px 10px; border-radius: 4px;")
        self.btn_dl_action.clicked.connect(self.on_dl_download_clicked)
        self.btn_dl_action.setVisible(False)
        content_layout.addWidget(self.btn_dl_action)

        # Real-time Status / Progress Log
        self.lbl_dl_status = QLabel("")
        self.lbl_dl_status.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        self.lbl_dl_status.setWordWrap(True)
        self.lbl_dl_status.setVisible(False)
        content_layout.addWidget(self.lbl_dl_status)

        scroll_area.setWidget(content_widget)
        root_layout.addWidget(scroll_area)

        # -------------------------------------------------------------
        # BOTTOM SHORTCUT BAR (Clean and subtle)
        # -------------------------------------------------------------
        bottom_bar = QWidget()
        bottom_bar.setStyleSheet("background-color: #18181b; border-top: 1px solid #27272a; padding: 4px;")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(12, 6, 12, 6)

        shortcuts = [
            ("F7", "Lyrics"),
            ("F8", "Move"),
            ("F9", "Toggle"),
            ("F10", "Source"),
            ("F11", "Eco"),
        ]
        for i, (key, desc) in enumerate(shortcuts):
            lbl = QLabel(f"<span style='color: #a1a1aa; font-weight: 600;'>{key}:</span> <span style='color: #71717a;'>{desc}</span>")
            lbl.setStyleSheet("font-size: 10px; font-family: 'Segoe UI', Arial, sans-serif;")
            bottom_layout.addWidget(lbl)
            if i < len(shortcuts) - 1:
                sep = QLabel("•")
                sep.setStyleSheet("color: #3f3f46; font-size: 10px;")
                bottom_layout.addWidget(sep)

        root_layout.addWidget(bottom_bar)

        self.populate_playlist_ui()

    def populate_playlist_ui(self):
        """Refreshes the tracklist widget items with search and subfolder display."""
        if hasattr(self, "lbl_folder_path") and self.lbl_folder_path:
            self.lbl_folder_path.setText(f"{self.audio_engine.folder_path}")
        if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "lbl_folder_path"):
            self.settings_dialog.lbl_folder_path.setText(f"{self.audio_engine.folder_path}")
        if hasattr(self, "combo_dl_folder"):
            self.refresh_dl_folders()
        search_txt = self.search_input.text() if hasattr(self, "search_input") else ""
        self.filter_tracks(search_txt)
        self.refresh_queue_ui()

    def filter_tracks(self, text: str = ""):
        query = (text or "").strip().lower()
        base_dir = self.audio_engine.folder_path

        self.list_tracks.clear()
        for i, path in enumerate(self.audio_engine.playlist):
            filename = os.path.basename(path)
            try:
                rel = os.path.relpath(path, base_dir)
                rel_dir = os.path.dirname(rel)
            except Exception:
                rel_dir = ""

            match = (not query) or (query in filename.lower()) or (query in rel_dir.lower())
            if not match:
                continue

            if rel_dir and rel_dir != ".":
                clean_dir = rel_dir.replace("\\", " / ")
                display_text = f"[{i+1:02d}] {filename}  ({clean_dir})"
            else:
                display_text = f"[{i+1:02d}] {filename}"

            item = QListWidgetItem(display_text)
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setData(Qt.ItemDataRole.UserRole + 1, path)
            self.list_tracks.addItem(item)

            if i == self.audio_engine.current_index:
                self.list_tracks.setCurrentItem(item)

        if 0 <= self.audio_engine.current_index < len(self.audio_engine.playlist):
            self.lbl_track_title.setText(f"{self.audio_engine.get_current_track_title()}")

    def on_add_selected_to_queue(self):
        item = self.list_tracks.currentItem()
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole + 1)
        if not path:
            orig_idx = item.data(Qt.ItemDataRole.UserRole)
            if orig_idx is not None and 0 <= orig_idx < len(self.audio_engine.playlist):
                path = self.audio_engine.playlist[orig_idx]
        if path:
            self.audio_engine.add_to_queue(path)
            self.refresh_queue_ui()
            self.queue_container.setVisible(True)

    def toggle_queue_panel(self):
        self.queue_container.setVisible(not self.queue_container.isVisible())

    def on_clear_queue_clicked(self):
        self.audio_engine.clear_queue()
        self.refresh_queue_ui()

    def refresh_queue_ui(self):
        if not hasattr(self, "btn_toggle_queue"):
            return
        count = len(self.audio_engine.queue)
        self.btn_toggle_queue.setText(f"Queue ({count})")
        self.list_queue.clear()
        base_dir = self.audio_engine.folder_path
        for i, q_path in enumerate(self.audio_engine.queue):
            filename = os.path.basename(q_path)
            try:
                rel = os.path.relpath(q_path, base_dir)
                rel_dir = os.path.dirname(rel)
                if rel_dir and rel_dir != ".":
                    clean_dir = rel_dir.replace("\\", " / ")
                    sub_txt = f"  ({clean_dir})"
                else:
                    sub_txt = ""
            except Exception:
                sub_txt = ""
            q_item = QListWidgetItem(f"#{i+1:02d}  {filename}{sub_txt}")
            q_item.setToolTip(q_path)
            self.list_queue.addItem(q_item)

    def on_queue_item_double_clicked(self, item):
        row = self.list_queue.row(item)
        path = self.audio_engine.remove_from_queue(row)
        if path:
            if path in self.audio_engine.playlist:
                self.audio_engine.current_index = self.audio_engine.playlist.index(path)
            self.audio_engine.load_file(path, auto_play=True)
            self.sync_play_state()
            self.refresh_queue_ui()

    def show_track_context_menu(self, pos):
        item = self.list_tracks.itemAt(pos)
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole + 1)
        orig_idx = item.data(Qt.ItemDataRole.UserRole)
        if not path and orig_idx is not None and 0 <= orig_idx < len(self.audio_engine.playlist):
            path = self.audio_engine.playlist[orig_idx]
        if not path:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #27272a;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                padding: 4px;
                border-radius: 6px;
            }
            QMenu::item {
                padding: 6px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #3b82f6;
                color: #ffffff;
            }
        """)
        action_play = menu.addAction("Play Now")
        action_queue = menu.addAction("Add to Queue")
        action_play_next = menu.addAction("Play Next in Queue")
        menu.addSeparator()
        action_open = menu.addAction("Show in Explorer")

        selected = menu.exec(self.list_tracks.mapToGlobal(pos))
        if selected == action_play:
            if orig_idx is not None:
                self.audio_engine.play_index(orig_idx)
            else:
                self.audio_engine.load_file(path, auto_play=True)
            self.sync_play_state()
            self.refresh_queue_ui()
        elif selected == action_queue:
            self.audio_engine.add_to_queue(path)
            self.refresh_queue_ui()
            self.queue_container.setVisible(True)
        elif selected == action_play_next:
            self.audio_engine.add_to_queue_next(path)
            self.refresh_queue_ui()
            self.queue_container.setVisible(True)
        elif selected == action_open:
            import subprocess
            subprocess.run(["explorer", f"/select,{path}"])

    def show_queue_context_menu(self, pos):
        item = self.list_queue.itemAt(pos)
        if not item:
            return
        row = self.list_queue.row(item)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #27272a;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                padding: 4px;
                border-radius: 6px;
            }
            QMenu::item {
                padding: 6px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #3b82f6;
                color: #ffffff;
            }
        """)
        action_play = menu.addAction("Play Now")
        action_remove = menu.addAction("Remove from Queue")
        action_clear = menu.addAction("Clear Entire Queue")

        selected = menu.exec(self.list_queue.mapToGlobal(pos))
        if selected == action_play:
            path = self.audio_engine.remove_from_queue(row)
            if path:
                if path in self.audio_engine.playlist:
                    self.audio_engine.current_index = self.audio_engine.playlist.index(path)
                self.audio_engine.load_file(path, auto_play=True)
                self.sync_play_state()
                self.refresh_queue_ui()
        elif selected == action_remove:
            self.audio_engine.remove_from_queue(row)
            self.refresh_queue_ui()
        elif selected == action_clear:
            self.audio_engine.clear_queue()
            self.refresh_queue_ui()

    def toggle_audio_mode(self):
        """Toggles between Built-in Player and Desktop Audio loopback."""
        new_mode = "desktop" if self.audio_engine.audio_mode == "player" else "player"
        self.set_audio_mode(new_mode)

    def set_audio_mode(self, mode: str):
        self.audio_engine.set_audio_mode(mode)
        self.update_audio_mode_ui()
        self.sync_play_state()

    def update_audio_mode_ui(self):
        is_desktop = (self.audio_engine.audio_mode == "desktop")
        txt = "Desktop Audio" if is_desktop else "Player Mode"
        style = "background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: 500;" if is_desktop else ""
        if hasattr(self, "btn_audio_mode"):
            self.btn_audio_mode.setText(txt)
            self.btn_audio_mode.setStyleSheet(style)
        if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "btn_audio_mode"):
            self.settings_dialog.btn_audio_mode.setText(txt)
            self.settings_dialog.btn_audio_mode.setStyleSheet(style)

    def on_play_pause_clicked(self):
        if self.audio_engine.audio_mode == "desktop":
            self.audio_engine.toggle_play_pause()
            return
        if not self.audio_engine.playlist:
            return
        if self.audio_engine.current_index < 0:
            self.audio_engine.play_index(0)
        else:
            self.audio_engine.toggle_play_pause()
        self.sync_play_state()

    def sync_play_state(self):
        self.update_sync_offset_display()
        if self.audio_engine.audio_mode == "desktop":
            self.btn_play_pause.setText("Live Audio")
            self.btn_play_pause.setStyleSheet("background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6;")
            self.lbl_track_title.setText("Desktop Audio")
            return

        if self.audio_engine.is_playing:
            self.btn_play_pause.setText("Pause")
            self.btn_play_pause.setStyleSheet("background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6;")
            self.lbl_track_title.setText(f"{self.audio_engine.get_current_track_title()}")
        else:
            self.btn_play_pause.setText("Play")
            self.btn_play_pause.setStyleSheet("")
            self.lbl_track_title.setText(f"{self.audio_engine.get_current_track_title()}")

        for r in range(self.list_tracks.count()):
            it = self.list_tracks.item(r)
            if it.data(Qt.ItemDataRole.UserRole) == self.audio_engine.current_index:
                self.list_tracks.setCurrentRow(r)
                break

    def on_next_clicked(self):
        self.audio_engine.next_track()
        self.sync_play_state()
        self.refresh_queue_ui()
        if hasattr(self, "lbl_track_title"):
            self.lbl_track_title.trigger_symbol("forward")
        if self.overlay:
            self.overlay.trigger_skip_feedback("forward")

    def on_prev_clicked(self):
        self.audio_engine.prev_track()
        self.sync_play_state()
        self.refresh_queue_ui()
        if hasattr(self, "lbl_track_title"):
            self.lbl_track_title.trigger_symbol("backward")
        if self.overlay:
            self.overlay.trigger_skip_feedback("backward")

    def toggle_shuffle(self):
        self.audio_engine.shuffle = not self.audio_engine.shuffle
        if self.audio_engine.shuffle:
            self.btn_shuffle.setText("Shuffle: On")
            self.btn_shuffle.setStyleSheet("background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6;")
        else:
            self.btn_shuffle.setText("Shuffle: Off")
            self.btn_shuffle.setStyleSheet("")

    def on_track_double_clicked(self, item):
        orig_idx = item.data(Qt.ItemDataRole.UserRole)
        if orig_idx is not None and 0 <= orig_idx < len(self.audio_engine.playlist):
            self.audio_engine.play_index(orig_idx)
        else:
            row = self.list_tracks.row(item)
            self.audio_engine.play_index(row)
        self.sync_play_state()
        self.refresh_queue_ui()

    def sync_volume(self, vol: float):
        """Synchronizes the volume slider and label from external events."""
        val = int(vol * 100)
        self.slider_vol.blockSignals(True)
        self.slider_vol.setValue(val)
        self.slider_vol.blockSignals(False)
        self.lbl_vol_val.setText(f"{val}%")

    def on_volume_changed(self, value):
        vol = value / 100.0
        self.audio_engine.set_volume(vol)
        self.overlay.set_volume(vol)
        self.lbl_vol_val.setText(f"{value}%")

    def on_seek_pressed(self):
        self.is_user_scrubbing = True

    def on_seek_moved(self, value):
        dur = self.audio_engine.get_duration()
        if dur > 0:
            target_sec = (value / 1000.0) * dur
            self.lbl_time_cur.setText(f"{int(target_sec // 60):02d}:{int(target_sec % 60):02d}")

    def on_seek_released(self):
        self.is_user_scrubbing = False
        val = self.slider_seek.value()
        dur = self.audio_engine.get_duration()
        if dur > 0:
            target_sec = (val / 1000.0) * dur
            self.audio_engine.seek(target_sec)
        else:
            self.audio_engine.seek(0.0)

    def update_timeline(self):
        if self.is_user_scrubbing:
            return

        pos = self.audio_engine.get_position()
        dur = self.audio_engine.get_duration()

        if self.isVisible():
            if self.audio_engine.audio_mode == "desktop":
                self.lbl_time_cur.setText("LIVE")
                self.lbl_time_dur.setText("LOOP")
                self.slider_seek.setValue(1000)
            else:
                if dur > 0:
                    pct = int((pos / dur) * 1000)
                    self.slider_seek.setValue(pct)
                else:
                    self.slider_seek.setValue(0)

                m_pos, s_pos = int(pos // 60), int(pos % 60)
                m_dur, s_dur = int(dur // 60), int(dur % 60)
                self.lbl_time_cur.setText(f"{m_pos:02d}:{s_pos:02d}")
                self.lbl_time_dur.setText(f"{m_dur:02d}:{s_dur:02d}")

        # Auto-advance to next track when song finishes
        if self.audio_engine.audio_mode != "desktop":
            is_finished = self.audio_engine.track_finished or (dur > 0 and pos >= dur - 0.08)
            if is_finished:
                self.audio_engine.track_finished = False
                self.audio_engine.next_track()
                self.sync_play_state()
                self.refresh_queue_ui()

    def choose_music_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Music Folder", self.audio_engine.folder_path)
        if folder:
            self.audio_engine.set_music_folder(folder)
            self.populate_playlist_ui()
            if hasattr(self, "lbl_folder_path") and self.lbl_folder_path:
                self.lbl_folder_path.setText(f"{folder}")
            if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "lbl_folder_path"):
                self.settings_dialog.lbl_folder_path.setText(f"{folder}")
            cfg = self.get_current_settings_dict()
            save_settings(cfg)

    def open_music_folder_explorer(self):
        folder = self.audio_engine.folder_path
        if folder and os.path.exists(folder):
            import subprocess
            subprocess.run(["explorer", os.path.normpath(folder)])

    def refresh_tracklist(self):
        self.audio_engine.refresh_playlist()
        self.populate_playlist_ui()
        if hasattr(self, "lbl_folder_path") and self.lbl_folder_path:
            self.lbl_folder_path.setText(f"{self.audio_engine.folder_path}")
        if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "lbl_folder_path"):
            self.settings_dialog.lbl_folder_path.setText(f"{self.audio_engine.folder_path}")

    def on_vis_mode_changed(self, mode: str):
        self.overlay.visualizer.set_mode(mode)
        self.overlay._was_rendering = True
        self.overlay.update()

    def on_vis_theme_changed(self, theme_name: str):
        self.overlay.visualizer.set_theme(theme_name)
        self.overlay._was_rendering = True
        self.overlay.update()

    def on_eye_sens_changed(self, val):
        self.overlay.eye_sensitivity = val / 100.0
        self.lbl_sens_val.setText(f"{val / 100.0:.1f}x")

    def on_scanlines_toggled(self, checked):
        self.overlay.enable_scanlines = checked
        self.overlay._was_rendering = True
        self.overlay.update()

    def on_bass_pop_toggled(self, checked):
        self.overlay.enable_bass_pop = checked
        self.overlay._was_rendering = True
        self.overlay.update()

    def on_widescreen_toggled(self, checked):
        self.overlay.use_widescreen = checked
        if hasattr(self.overlay.visualizer, "use_widescreen"):
            self.overlay.visualizer.use_widescreen = checked
        self.on_size_change()

    def on_opacity_change(self, val=None):
        if val is None:
            val = self.slider_opacity.value()
        self.overlay.opacity_val = val / 100.0
        self.overlay._was_rendering = True
        self.overlay.update()

    def on_size_change(self, val=None):
        if self.overlay.use_widescreen:
            h = self.slider_size.value()
            w = int(h * (16.0 / 9.0))
            self.overlay.resize(w, h)
        else:
            size = self.slider_size.value()
            self.overlay.resize(size, size)
        self.overlay._was_rendering = True
        self.overlay.update()

    def reload_art(self):
        self.overlay.load_assets()
        print("[STATUS] Reloaded fresh images from assets/eye_parts/ folder!")

    def check_hotkeys(self):
        """Monitors global hotkeys without polling lag."""
        # F7: Toggle Lyrics Overlay
        f7_down = bool(user32.GetAsyncKeyState(VK_F7) & 0x8000)
        if f7_down and not self.last_f7_state:
            self.toggle_lyrics()
        self.last_f7_state = f7_down

        # Ctrl+[ and Ctrl+]: Manual lyric offset adjustments
        ctrl_down = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
        bracket_l = bool(user32.GetAsyncKeyState(VK_OEM_4) & 0x8000)
        if ctrl_down and bracket_l and not self.last_bracket_left_state:
            self.adjust_lyrics_offset(-0.25)
        self.last_bracket_left_state = bracket_l

        bracket_r = bool(user32.GetAsyncKeyState(VK_OEM_6) & 0x8000)
        if ctrl_down and bracket_r and not self.last_bracket_right_state:
            self.adjust_lyrics_offset(0.25)
        self.last_bracket_right_state = bracket_r

        # F8: Toggle Move Talia mode
        f8_down = bool(user32.GetAsyncKeyState(VK_F8) & 0x8000)
        if f8_down and not self.last_f8_state:
            self.toggle_move_talia()
        self.last_f8_state = f8_down

        # F9: Toggle Show/Hide overlay
        f9_down = bool(user32.GetAsyncKeyState(VK_F9) & 0x8000)
        if f9_down and not self.last_f9_state:
            self.toggle_visibility()
        self.last_f9_state = f9_down

        # F10: Toggle Audio Source Mode (Desktop vs Player)
        f10_down = bool(user32.GetAsyncKeyState(VK_F10) & 0x8000)
        if f10_down and not self.last_f10_state:
            self.toggle_audio_mode()
        self.last_f10_state = f10_down

        # F11: Toggle Eco Mode (< 1% CPU)
        f11_down = bool(user32.GetAsyncKeyState(VK_F11) & 0x8000)
        if f11_down and not self.last_f11_state:
            self.toggle_eco_mode()
        self.last_f11_state = f11_down

    def toggle_eco_mode(self):
        """Toggles Eco Mode (< 1% CPU target) and persists preference."""
        self.set_eco_mode(not self.eco_mode)
        if not getattr(self, "is_loading_settings", False):
            try:
                cfg = self.get_current_settings_dict()
                save_settings(cfg)
            except Exception:
                pass

    def set_eco_mode(self, enabled: bool):
        """Applies Eco Mode settings across audio engine, character overlay, lyrics, and controller."""
        self.eco_mode = enabled
        if hasattr(self.audio_engine, "set_eco_mode"):
            self.audio_engine.set_eco_mode(enabled)
        if hasattr(self.overlay, "set_eco_mode"):
            self.overlay.set_eco_mode(enabled)
        if self.lyrics_overlay and hasattr(self.lyrics_overlay, "set_eco_mode"):
            self.lyrics_overlay.set_eco_mode(enabled)

        if enabled:
            self.hotkey_timer.setInterval(60)
            self.timeline_timer.setInterval(500)
            if hasattr(self, "btn_eco"):
                self.btn_eco.setText("Eco Mode: On")
                self.btn_eco.setStyleSheet("background-color: #166534; color: #4ade80; border: 1px solid #22c55e; font-weight: 500; font-size: 11px; padding: 7px 8px;")
            if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "btn_eco"):
                self.settings_dialog.btn_eco.setText("Eco Mode: On")
                self.settings_dialog.btn_eco.setStyleSheet("background-color: #166534; color: #4ade80; border: 1px solid #22c55e; font-weight: 500; font-size: 11px; padding: 7px 8px;")
            print("[STATUS] Eco Mode enabled (< 1% CPU).")
        else:
            self.hotkey_timer.setInterval(50)
            self.timeline_timer.setInterval(200)
            if hasattr(self, "btn_eco"):
                self.btn_eco.setText("Eco Mode: Off")
                self.btn_eco.setStyleSheet("")
            if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "btn_eco"):
                self.settings_dialog.btn_eco.setText("Eco Mode: Off")
                self.settings_dialog.btn_eco.setStyleSheet("")
            print("[STATUS] Eco Mode disabled (Standard).")

    def toggle_lyrics(self):
        if not self.lyrics_overlay:
            return
        self.lyrics_overlay.is_enabled = not self.lyrics_overlay.is_enabled
        if self.lyrics_overlay.is_enabled:
            self.lyrics_overlay.show()
            self.lyrics_overlay.enforce_topmost()
            print("[STATUS] Lyrics Overlay enabled.")
        else:
            self.lyrics_overlay.hide()
            print("[STATUS] Lyrics Overlay disabled.")
        self.update_lyrics_ui()

    def update_lyrics_ui(self):
        if not hasattr(self, "btn_lyrics") or not self.lyrics_overlay:
            return
        txt = "Lyrics: On" if self.lyrics_overlay.is_enabled else "Lyrics: Off"
        style = "background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: 500; font-size: 11px; padding: 7px 8px;" if self.lyrics_overlay.is_enabled else ""
        if hasattr(self, "btn_lyrics"):
            self.btn_lyrics.setText(txt)
            self.btn_lyrics.setStyleSheet(style)
        if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "btn_lyrics"):
            self.settings_dialog.btn_lyrics.setText(txt)
            self.settings_dialog.btn_lyrics.setStyleSheet(style)

    def update_move_talia_ui(self):
        """Refreshes the Move Talia toggle button appearance to match current overlay state."""
        txt = "Unlock Window" if self.overlay.move_talia_mode else "Lock Window"
        style = "background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: 500;" if self.overlay.move_talia_mode else ""
        if hasattr(self, "btn_move_talia"):
            self.btn_move_talia.setText(txt)
            self.btn_move_talia.setStyleSheet(style)
        if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "btn_move_talia"):
            self.settings_dialog.btn_move_talia.setText(txt)
            self.settings_dialog.btn_move_talia.setStyleSheet(style)

    def adjust_lyrics_offset(self, delta: float):
        if self.lyrics_overlay and hasattr(self.lyrics_overlay, "lyrics_manager") and self.lyrics_overlay.lyrics_manager:
            new_val = self.lyrics_overlay.lyrics_manager.adjust_offset(delta)
            self.update_sync_offset_display(new_val)
            print(f"[LYRICS] Manual sync offset adjusted: {new_val:+.2f}s")

    def reset_lyrics_offset(self):
        if self.lyrics_overlay and hasattr(self.lyrics_overlay, "lyrics_manager") and self.lyrics_overlay.lyrics_manager:
            new_val = self.lyrics_overlay.lyrics_manager.reset_offset()
            self.update_sync_offset_display(new_val)
            print("[LYRICS] Manual sync offset reset to 0.0s")

    def auto_sync_lyrics(self):
        if self.lyrics_overlay and hasattr(self.lyrics_overlay, "lyrics_manager") and self.lyrics_overlay.lyrics_manager:
            success, val, msg = self.lyrics_overlay.lyrics_manager.auto_align_with_audio()
            self.update_sync_offset_display()
            print(f"[LYRICS AUTO-SYNC] {msg}")

    def update_sync_offset_display(self, val=None):
        if hasattr(self, "lbl_sync_offset") and self.lyrics_overlay and hasattr(self.lyrics_overlay, "lyrics_manager") and self.lyrics_overlay.lyrics_manager:
            offset = val if val is not None else self.lyrics_overlay.lyrics_manager.get_total_offset()
            self.lbl_sync_offset.setText(f"{offset:+.2f}s")

    def on_word_glow_toggled(self, checked: bool):
        if self.lyrics_overlay:
            self.lyrics_overlay.word_glow = checked
            self.lyrics_overlay.update()
        if not getattr(self, "is_loading_settings", False):
            try:
                cfg = self.get_current_settings_dict()
                save_settings(cfg)
            except Exception:
                pass

    def on_lyric_preset_changed(self, text: str):
        if getattr(self, "is_loading_settings", False):
            return
        if hasattr(self, "lyric_presets") and text in self.lyric_presets:
            hex_code = self.lyric_presets[text]
            if self.lyrics_overlay:
                self.lyrics_overlay.set_color(hex_code)
            self._update_color_btn_style(hex_code)
            try:
                cfg = self.get_current_settings_dict()
                cfg["lyrics_color"] = hex_code
                save_settings(cfg)
            except Exception:
                pass

    def choose_custom_lyric_color(self):
        try:
            curr_hex = getattr(self.lyrics_overlay, "color_hex", "#ffffff") if self.lyrics_overlay else "#ffffff"
            options = QColorDialog.ColorDialogOption.DontUseNativeDialog
            color = QColorDialog.getColor(QColor(curr_hex), self, "Choose Lyrics Color", options)
            if color.isValid():
                hex_code = color.name()
                if self.lyrics_overlay:
                    self.lyrics_overlay.set_color(hex_code)
                matched_preset = None
                for name, code_str in self.lyric_presets.items():
                    if code_str.lower() == hex_code.lower():
                        matched_preset = name
                        break
                if matched_preset:
                    self.combo_lyric_color.setCurrentText(matched_preset)
                else:
                    self.combo_lyric_color.setCurrentText("Custom...")
                self._update_color_btn_style(hex_code)
                # Auto save chosen color
                cfg = self.get_current_settings_dict()
                cfg["lyrics_color"] = hex_code
                save_settings(cfg)
        except Exception as e:
            print(f"[ERROR] choose_custom_lyric_color: {e}")

    def _update_color_btn_style(self, hex_code: str):
        if hasattr(self, "btn_pick_color"):
            self.btn_pick_color.setStyleSheet(
                f"background-color: #27272a; color: {hex_code}; border: 1px solid {hex_code}; font-weight: 500;"
            )

    def open_settings_window(self):
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.show()
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()

    def on_font_changed(self, text: str):
        if getattr(self, "is_loading_settings", False):
            return
        if not text or "Default" in text:
            if self.lyrics_overlay:
                self.lyrics_overlay.set_custom_font(None)
        else:
            if self.lyrics_overlay:
                self.lyrics_overlay.set_custom_font(text)
        try:
            cfg = self.get_current_settings_dict()
            cfg["lyrics_font"] = text
            save_settings(cfg)
        except Exception as e:
            print(f"[ERROR] Auto-saving lyrics font: {e}")

    def open_fonts_folder(self):
        os.makedirs(FONTS_DIR, exist_ok=True)
        subprocess.run(["explorer", os.path.normpath(FONTS_DIR)])

    def open_lyric_fetcher(self):
        # Open automated lyric fetcher GUI
        try:
            fetcher_dir = os.path.join(PROJECT_ROOT, "Talia Lyrics Fetch Automated")
            if fetcher_dir not in sys.path:
                sys.path.insert(0, fetcher_dir)
            from gui_fetcher import LyricsFetcherWindow
            if not hasattr(self, "_lyrics_fetcher_win") or self._lyrics_fetcher_win is None:
                self._lyrics_fetcher_win = LyricsFetcherWindow()
            self._lyrics_fetcher_win.show()
            self._lyrics_fetcher_win.raise_()
            self._lyrics_fetcher_win.activateWindow()
            print("[ACTION] Opened Lyrics Fetcher Window.")
        except Exception as e:
            print(f"[ERROR] In-process lyric fetcher launch failed: {e}")
            try:
                bat_path = os.path.join(PROJECT_ROOT, "Talia Lyrics Fetch Automated", "run_fetcher.bat")
                if os.path.exists(bat_path):
                    subprocess.Popen(["cmd.exe", "/c", bat_path], cwd=os.path.dirname(bat_path))
                else:
                    folder = os.path.join(PROJECT_ROOT, "Talia Lyrics Fetch Automated")
                    if os.path.exists(folder):
                        os.startfile(folder)
            except Exception as e2:
                print(f"[ERROR] Fallback lyric fetcher launch failed: {e2}")

    def reload_custom_fonts(self):
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.populate_fonts()
        active = self.combo_font.currentText() if hasattr(self, "combo_font") else ""
        if self.lyrics_overlay:
            if not active or "Default" in active:
                self.lyrics_overlay.set_custom_font(None)
            else:
                self.lyrics_overlay.set_custom_font(active)
            self.lyrics_overlay.update()
        print(f"[FONTS] Reloaded lyric fonts. Active: {active or 'Default'}")

    def show_guide_dialog(self):
        cfg = self.get_current_settings_dict()
        self.guide_dialog = GuideDialog(self, cfg)
        self.guide_dialog.show()
        self.guide_dialog.raise_()
        self.guide_dialog.activateWindow()

    def toggle_move_talia(self):
        new_state = not self.overlay.move_talia_mode
        self.overlay.set_move_talia_mode(new_state)
        if self.lyrics_overlay:
            self.lyrics_overlay.set_move_mode(new_state)
        self.update_move_talia_ui()

    def toggle_visibility(self):
        if self.overlay.isVisible():
            self.overlay.hide()
            if self.lyrics_overlay:
                self.lyrics_overlay.hide()
            print("[STATUS] Overlay and lyrics hidden.")
        else:
            self.overlay.show()
            self.overlay.enforce_topmost()
            if self.lyrics_overlay and self.lyrics_overlay.is_enabled:
                self.lyrics_overlay.show()
                self.lyrics_overlay.enforce_topmost()
            print("[STATUS] Overlay and lyrics visible.")

    # ==========================================================
    # Settings Persistence
    # ==========================================================
    def get_current_settings_dict(self) -> dict:
        """Gathers all current configuration into a dictionary."""
        if getattr(self.overlay, "is_shutting_down", False) and hasattr(self.overlay, "shutdown_start_pos"):
            pos_x = int(self.overlay.shutdown_start_pos.x())
            pos_y = int(self.overlay.shutdown_start_pos.y())
        elif getattr(self.overlay, "is_starting_up", False) and hasattr(self.overlay, "target_startup_y"):
            pos_x = int(self.overlay.target_startup_x)
            pos_y = int(self.overlay.target_startup_y)
        else:
            pos_x = int(self.overlay.pos().x())
            pos_y = int(self.overlay.pos().y())

        user_opacity = max(0.20, min(1.0, self.slider_opacity.value() / 100.0))

        settings_dict = {
            "pos_x": pos_x,
            "pos_y": pos_y,
            "char_size": max(MIN_CHAR_SIZE, int(self.overlay.width())),
            "eye_sensitivity": round(float(self.overlay.eye_sensitivity), 2),
            "opacity": round(float(user_opacity), 2),
            "scanlines": bool(self.overlay.enable_scanlines),
            "bass_pop": bool(self.overlay.enable_bass_pop),
            "widescreen": bool(self.overlay.use_widescreen),
            "visualizer_mode": str(self.overlay.visualizer.mode),
            "visualizer_palette": str(self.overlay.visualizer.current_theme_name),
            "volume": round(float(self.audio_engine.volume), 2),
            "audio_mode": str(self.audio_engine.audio_mode),
            "music_folder": str(self.audio_engine.folder_path),
            "shuffle": bool(self.audio_engine.shuffle),
            "eco_mode": bool(self.eco_mode),
            "show_startup_guide": bool(getattr(self, "show_startup_guide", True))
        }
        if self.lyrics_overlay:
            settings_dict["lyrics_x"] = int(self.lyrics_overlay.pos().x())
            settings_dict["lyrics_y"] = int(self.lyrics_overlay.pos().y())
            settings_dict["show_lyrics"] = bool(self.lyrics_overlay.is_enabled)
            settings_dict["lyrics_color"] = str(getattr(self.lyrics_overlay, "color_hex", "#ffffff"))
            settings_dict["lyrics_word_glow"] = bool(getattr(self.lyrics_overlay, "word_glow", True))
            font_val = self.combo_font.currentText() if hasattr(self, "combo_font") else "Default (Segoe UI / Inter)"
            settings_dict["lyrics_font"] = font_val
        settings_dict["download_folder"] = str(getattr(self, "saved_dl_folder", ""))
        return settings_dict

    def apply_settings(self, cfg: dict):
        # Apply settings to overlay and controls
        self.is_loading_settings = True
        self.show_startup_guide = bool(cfg.get("show_startup_guide", False))

        # Size
        size = int(cfg.get("char_size", 300))
        size = max(MIN_CHAR_SIZE, min(MAX_CHAR_SIZE, size))
        self.slider_size.setValue(size)
        self.overlay.resize(size, size)

        # Position
        screen = QApplication.primaryScreen().geometry()
        pos_x = int(cfg.get("pos_x", -1))
        pos_y = int(cfg.get("pos_y", -1))

        if (-size // 2 <= pos_x <= screen.width()) and (-size // 2 <= pos_y <= screen.height()):
            self.overlay.move(pos_x, pos_y)
        else:
            def_x = max(20, screen.width() - size - 40)
            def_y = max(20, screen.height() - size - 80)
            self.overlay.move(def_x, def_y)

        # Eye Sensitivity
        sens = cfg.get("eye_sensitivity", 1.68)
        self.slider_eye_sens.setValue(int(sens * 100))

        # Opacity
        raw_op = float(cfg.get("opacity", 1.0))
        if raw_op < 0.20:
            raw_op = 1.0
        self.slider_opacity.setValue(int(raw_op * 100))
        self.overlay.opacity_val = raw_op

        # Features
        self.chk_scanlines.setChecked(cfg.get("scanlines", False))
        self.chk_bass_pop.setChecked(cfg.get("bass_pop", False))
        self.overlay.enable_bass_pop = cfg.get("bass_pop", False)
        self.chk_widescreen.setChecked(cfg.get("widescreen", False))

        # Visualizer
        vis_mode = cfg.get("visualizer_mode", "Neon Wave")
        if vis_mode in ["Cyber Bars", "Neon Wave", "Radial Core", "Dual Mirror"]:
            self.combo_mode.setCurrentText(vis_mode)

        palette = cfg.get("visualizer_palette", "Cyberpunk Neon")
        if palette in COLOR_THEMES:
            self.combo_theme.setCurrentText(palette)

        # Volume
        vol = cfg.get("volume", 0.49)
        self.sync_volume(vol)
        self.overlay.set_volume(vol)

        # Audio Mode
        audio_mode = cfg.get("audio_mode", "player")
        if audio_mode in ("player", "desktop"):
            self.set_audio_mode(audio_mode)

        # Shuffle
        if cfg.get("shuffle", False) != self.audio_engine.shuffle:
            self.toggle_shuffle()

        # Lyrics Overlay Position & Visibility
        if self.lyrics_overlay:
            lx = int(cfg.get("lyrics_x", -1))
            ly = int(cfg.get("lyrics_y", -1))
            if 0 <= lx < screen.width() and 0 <= ly < screen.height():
                self.lyrics_overlay.move(lx, ly)
            show_lyrics = bool(cfg.get("show_lyrics", True))
            self.lyrics_overlay.is_enabled = show_lyrics
            if show_lyrics:
                self.lyrics_overlay.show()
                self.lyrics_overlay.enforce_topmost()
            else:
                self.lyrics_overlay.hide()
            self.update_lyrics_ui()

            lyric_color = cfg.get("lyrics_color", "#f472b6")
            self.lyrics_overlay.set_color(lyric_color)
            if hasattr(self, "combo_lyric_color"):
                matched = None
                for name, code_str in self.lyric_presets.items():
                    if code_str.lower() == lyric_color.lower():
                        matched = name
                        break
                self.combo_lyric_color.blockSignals(True)
                if matched:
                    self.combo_lyric_color.setCurrentText(matched)
                else:
                    self.combo_lyric_color.setCurrentText("Custom...")
                self.combo_lyric_color.blockSignals(False)
                self._update_color_btn_style(lyric_color)

            word_glow = bool(cfg.get("lyrics_word_glow", True))
            self.lyrics_overlay.word_glow = word_glow
            if hasattr(self, "chk_word_glow"):
                self.chk_word_glow.blockSignals(True)
                self.chk_word_glow.setChecked(word_glow)
                self.chk_word_glow.blockSignals(False)

            # Lyrics Font
            lyrics_font = cfg.get("lyrics_font", "Rajdhani")
            if hasattr(self, "settings_dialog"):
                self.settings_dialog.populate_fonts()
                if hasattr(self, "combo_font"):
                    idx = self.combo_font.findText(lyrics_font)
                    if idx >= 0:
                        self.combo_font.blockSignals(True)
                        self.combo_font.setCurrentIndex(idx)
                        self.combo_font.blockSignals(False)
                    if "Default" in lyrics_font:
                        self.lyrics_overlay.set_custom_font(None)
                    else:
                        self.lyrics_overlay.set_custom_font(lyrics_font)

        eco = bool(cfg.get("eco_mode", False))
        self.set_eco_mode(eco)

        # Download Destination Folder
        self.saved_dl_folder = str(cfg.get("download_folder", ""))
        self.refresh_dl_folders()

        self.overlay.update()
        self.is_loading_settings = False

    def _reset_save_btn(self):
        self.btn_save_settings.setText("Save Settings")
        self.btn_save_settings.setStyleSheet("")

    def save_settings_action(self):
        """Triggered by the Save Settings button."""
        cfg = self.get_current_settings_dict()
        if save_settings(cfg):
            self.btn_save_settings.setText("Settings Saved")
            self.btn_save_settings.setStyleSheet("background-color: #166534; color: #4ade80; border: 1px solid #22c55e;")
            QTimer.singleShot(1500, self._reset_save_btn)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "timeline_timer"):
            self.timeline_timer.setInterval(200)
            self.update_timeline()
        if self.overlay and hasattr(self.overlay, "sound_menu_open") and self.overlay.sound_menu_open.isLoaded():
            self.overlay.sound_menu_open.play()

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, "timeline_timer"):
            self.timeline_timer.setInterval(600)
        if self.overlay and hasattr(self.overlay, "sound_menu_close") and self.overlay.sound_menu_close.isLoaded():
            self.overlay.sound_menu_close.play()
        trim_process_memory()

    def closeEvent(self, event):
        cfg = self.get_current_settings_dict()
        save_settings(cfg)
        if hasattr(self, "settings_dialog") and self.settings_dialog.isVisible():
            self.settings_dialog.hide()
        self.hide()
        if self.overlay and hasattr(self.overlay, "sound_menu_close") and self.overlay.sound_menu_close.isLoaded():
            self.overlay.sound_menu_close.play()
        trim_process_memory()
        event.ignore()

    # -------------------------------------------------------------
    # SONG SEARCH & AUTO-DOWNLOAD SLOTS
    # -------------------------------------------------------------
    def on_dl_search_clicked(self):
        query = self.edit_dl_search.text().strip()
        if not query:
            return
        self.lbl_dl_status.setText("Searching YouTube...")
        self.lbl_dl_status.setStyleSheet("color: #3b82f6; font-size: 11px;")
        self.lbl_dl_status.setVisible(True)
        self.btn_dl_search.setEnabled(False)
        self.btn_dl_search.setText("Searching...")
        self.downloader.search_async(query, limit=5)

    def _on_search_finished(self, results):
        self.btn_dl_search.setEnabled(True)
        self.btn_dl_search.setText("Search")
        self.list_dl_results.clear()
        if not results:
            self.lbl_dl_status.setText("No search results found. Try a different title or paste a YouTube URL.")
            self.lbl_dl_status.setStyleSheet("color: #f87171; font-size: 11px;")
            self.list_dl_results.setVisible(False)
            self.btn_dl_action.setVisible(False)
            return

        for r in results:
            title = r.get("title", "Unknown")
            channel = r.get("channel", "Unknown")
            dur_str = r.get("duration_str", "--:--")
            item = QListWidgetItem(f"[{dur_str}] {title} • {channel}")
            item.setData(Qt.ItemDataRole.UserRole, r)
            self.list_dl_results.addItem(item)

        self.list_dl_results.setVisible(True)
        self.list_dl_results.setCurrentRow(0)
        self.btn_dl_action.setVisible(True)
        self.lbl_dl_status.setText(f"Found {len(results)} matches. Double-click to add or select & click below.")
        self.lbl_dl_status.setStyleSheet("color: #a1a1aa; font-size: 11px;")

    def _on_search_error(self, err_msg):
        self.btn_dl_search.setEnabled(True)
        self.btn_dl_search.setText("Search")
        self.lbl_dl_status.setText(f"Search error: {err_msg}")
        self.lbl_dl_status.setStyleSheet("color: #f87171; font-size: 11px;")
        self.lbl_dl_status.setVisible(True)

    def on_dl_selection_changed(self):
        has_sel = len(self.list_dl_results.selectedItems()) > 0
        self.btn_dl_action.setEnabled(has_sel)

    def on_dl_item_double_clicked(self, item):
        self.on_dl_download_clicked()

    def on_dl_folder_changed(self, index: int):
        if not hasattr(self, "combo_dl_folder"):
            return
        data = self.combo_dl_folder.itemData(index)
        if data == "__BROWSE__":
            current_base = self.audio_engine.folder_path or PROJECT_ROOT
            chosen = QFileDialog.getExistingDirectory(
                self,
                "Select Destination Folder for Downloads",
                current_base
            )
            if chosen and os.path.isdir(chosen):
                self.saved_dl_folder = os.path.normpath(chosen)
                self.refresh_dl_folders()
                if not getattr(self, "is_loading_settings", False):
                    cfg = self.get_current_settings_dict()
                    save_settings(cfg)
            else:
                self.refresh_dl_folders()
        elif data:
            self.saved_dl_folder = str(data)
            if not getattr(self, "is_loading_settings", False):
                cfg = self.get_current_settings_dict()
                save_settings(cfg)

    def refresh_dl_folders(self):
        """Populates the download destination folder dropdown with standard and custom locations."""
        if not hasattr(self, "combo_dl_folder"):
            return

        current_selected = getattr(self, "saved_dl_folder", "")
        self.combo_dl_folder.blockSignals(True)
        self.combo_dl_folder.clear()

        music_dir = self.audio_engine.folder_path
        if not music_dir or not os.path.exists(music_dir):
            music_dir = os.path.join(PROJECT_ROOT, "music")
        os.makedirs(music_dir, exist_ok=True)

        default_sub = os.path.normpath(os.path.join(music_dir, "Downloaded Songs"))
        os.makedirs(default_sub, exist_ok=True)

        # 1. Default Downloaded Songs
        self.combo_dl_folder.addItem("📁 Downloaded Songs", default_sub)

        # 2. Main Library Root
        root_name = os.path.basename(os.path.normpath(music_dir)) or "Music"
        self.combo_dl_folder.addItem(f"📁 Library Root ({root_name})", os.path.normpath(music_dir))

        # 3. Existing subfolders in music_dir
        try:
            for item in sorted(os.listdir(music_dir), key=lambda s: s.lower()):
                full_p = os.path.normpath(os.path.join(music_dir, item))
                if os.path.isdir(full_p) and full_p != default_sub:
                    self.combo_dl_folder.addItem(f"📁 {item}", full_p)
        except Exception:
            pass

        # 4. Custom directory if outside music_dir
        if current_selected and os.path.exists(current_selected):
            norm_custom = os.path.normpath(current_selected)
            found = False
            for idx in range(self.combo_dl_folder.count()):
                if os.path.normpath(str(self.combo_dl_folder.itemData(idx))) == norm_custom:
                    found = True
                    break
            if not found:
                custom_name = os.path.basename(norm_custom) or norm_custom
                self.combo_dl_folder.addItem(f"📁 Custom: {custom_name}", norm_custom)

        # 5. Browse option
        self.combo_dl_folder.addItem("➕ Browse Custom Folder...", "__BROWSE__")

        # Select target
        target = os.path.normpath(current_selected) if (current_selected and os.path.exists(current_selected)) else default_sub
        for idx in range(self.combo_dl_folder.count()):
            if os.path.normpath(str(self.combo_dl_folder.itemData(idx))) == target:
                self.combo_dl_folder.setCurrentIndex(idx)
                break

        self.combo_dl_folder.blockSignals(False)

    def on_dl_download_clicked(self):
        items = self.list_dl_results.selectedItems()
        if not items:
            return
        data = items[0].data(Qt.ItemDataRole.UserRole)
        if not data or not data.get("url"):
            return

        url = data.get("url")
        title = data.get("title", "Track")

        target_dir = None
        if hasattr(self, "combo_dl_folder"):
            selected_path = self.combo_dl_folder.currentData()
            if selected_path and selected_path != "__BROWSE__" and os.path.isdir(selected_path):
                target_dir = selected_path

        if not target_dir:
            music_dir = self.audio_engine.folder_path or os.path.join(PROJECT_ROOT, "music")
            target_dir = os.path.join(music_dir, "Downloaded Songs")

        os.makedirs(target_dir, exist_ok=True)

        self.btn_dl_action.setEnabled(False)
        self.btn_dl_search.setEnabled(False)
        folder_label = os.path.basename(target_dir) or "Music"
        self.lbl_dl_status.setText(f"Downloading '{title}' to {folder_label}...")
        self.lbl_dl_status.setStyleSheet("color: #3b82f6; font-size: 11px;")
        self.lbl_dl_status.setVisible(True)

        self.downloader.download_and_sync_async(url, target_dir)

    def _on_download_progress(self, msg):
        self.lbl_dl_status.setText(msg)
        self.lbl_dl_status.setStyleSheet("color: #3b82f6; font-size: 11px;")

    def _on_download_finished(self, success, opus_path, status_msg):
        self.btn_dl_action.setEnabled(True)
        self.btn_dl_search.setEnabled(True)
        if success:
            self.lbl_dl_status.setText(f"✓ {status_msg}")
            self.lbl_dl_status.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 500;")

            # Automatically refresh playlist to include the new track
            self.audio_engine.refresh_playlist()
            self.refresh_tracklist()
            self.refresh_dl_folders()

            # Highlight the newly downloaded track in list_tracks
            if opus_path and os.path.exists(opus_path):
                norm_opus = os.path.normpath(opus_path)
                existing = [os.path.normpath(p) for p in self.audio_engine.playlist]
                if norm_opus not in existing:
                    self.audio_engine.playlist.append(norm_opus)
                    self.populate_playlist_ui()
                for r in range(self.list_tracks.count()):
                    it = self.list_tracks.item(r)
                    orig_idx = it.data(Qt.ItemDataRole.UserRole)
                    if 0 <= orig_idx < len(self.audio_engine.playlist):
                        if os.path.normpath(self.audio_engine.playlist[orig_idx]) == norm_opus:
                            self.list_tracks.setCurrentRow(r)
                            break
        else:
            self.lbl_dl_status.setText(f"✗ {status_msg}")
            self.lbl_dl_status.setStyleSheet("color: #f87171; font-size: 11px;")
