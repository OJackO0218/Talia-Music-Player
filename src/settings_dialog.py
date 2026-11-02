"""Advanced settings dialog for Talia."""

import os
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from config import (
    COLOR_THEMES,
    ICON_PATH,
    MAX_CHAR_SIZE,
    MIN_CHAR_SIZE,
    trim_process_memory,
)
from ui_theme import SHARED_PANEL_STYLE
from ui_widgets import NoScrollComboBox, create_section_header

if TYPE_CHECKING:
    from controller import ControlPanel


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
        self.btn_lyrics.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: bold; font-size: 11px; padding: 7px 8px;"
        )
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
        self.lbl_lyric_disclaimer = QLabel(
            "Note: Some songs may not have available or synchronized lyrics."
        )
        self.lbl_lyric_disclaimer.setStyleSheet(
            "color: #71717a; font-size: 10px; font-style: italic; margin-top: 2px; margin-bottom: 4px;"
        )
        self.lbl_lyric_disclaimer.setWordWrap(True)
        content_layout.addWidget(self.lbl_lyric_disclaimer)

        # Lyrics Size slider row
        hbox_size = QHBoxLayout()
        lbl_size_title = QLabel("Size:")
        lbl_size_title.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        hbox_size.addWidget(lbl_size_title)
        self.slider_lyric_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_lyric_size.setRange(14, 60)
        init_size = 25
        if self.panel and getattr(self.panel, "lyrics_overlay", None):
            init_size = getattr(self.panel.lyrics_overlay, "base_font_size", 25)
        self.slider_lyric_size.setValue(init_size)
        self.slider_lyric_size.valueChanged.connect(self.panel.on_lyric_size_changed)
        hbox_size.addWidget(self.slider_lyric_size)
        self.lbl_lyric_size_val = QLabel(f"{init_size} pt")
        self.lbl_lyric_size_val.setFixedWidth(42)
        self.lbl_lyric_size_val.setStyleSheet(
            "color: #f4f4f5; font-family: 'Consolas', monospace; font-weight: 600;"
        )
        hbox_size.addWidget(self.lbl_lyric_size_val)
        content_layout.addLayout(hbox_size)

        # Font dropdown row
        hbox_font = QHBoxLayout()
        lbl_font_title = QLabel("Font:")
        lbl_font_title.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        hbox_font.addWidget(lbl_font_title)
        self.combo_font = NoScrollComboBox()
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
        self.combo_lyric_color = NoScrollComboBox()
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
        self.combo_mode = NoScrollComboBox()
        self.combo_mode.addItems(["Cyber Bars", "Neon Wave", "Radial Core", "Dual Mirror"])
        self.combo_mode.currentTextChanged.connect(self.panel.on_vis_mode_changed)
        hbox_style.addWidget(self.combo_mode)
        lbl_vis_theme = QLabel("Palette:")
        lbl_vis_theme.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        hbox_style.addWidget(lbl_vis_theme)
        self.combo_theme = NoScrollComboBox()
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
        self.lbl_sens_val.setStyleSheet(
            "color: #f4f4f5; font-family: 'Consolas', monospace; font-weight: 600;"
        )
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
        self.chk_bass_pop = QCheckBox("Bass Reaction")
        self.chk_bass_pop.setChecked(True)
        self.chk_bass_pop.toggled.connect(self.panel.on_bass_pop_toggled)
        hbox_toggles.addWidget(self.chk_bass_pop)
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
        active = (
            getattr(self.panel.lyrics_overlay, "custom_font_family", None)
            if self.panel.lyrics_overlay
            else None
        )
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
