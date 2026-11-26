"""Clean, modern Settings dialog for Talia configuration."""

import os
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import (
    APP_VERSION,
    COLOR_THEMES,
    ICON_PATH,
    MAX_CHAR_SIZE,
    MIN_CHAR_SIZE,
    PROJECT_ROOT,
    trim_process_memory,
)
from ui_theme import CLEAN_UTILITY_QSS
from ui_widgets import (
    CyberCard,
    DraggableClampedDialogMixin,
    NoScrollComboBox,
)
from updater import (
    UpdateCheckWorker,
    UpdateDownloadWorker,
    launch_updater_and_exit,
)

if TYPE_CHECKING:
    from controller import ControlPanel


def create_card_frame(title: str):
    """Creates a clean grouped card container for settings sections."""
    card = CyberCard(title)
    card.layout_content.setContentsMargins(12, 10, 12, 12)
    card.layout_content.setSpacing(8)
    return card, card.layout_content


def _make_clean_btn(text: str, role: str = "default", height: int = 30, tooltip: str = "") -> QPushButton:
    """Create a clean rounded push button with semantic role styling."""
    btn = QPushButton(text)
    if role != "default":
        btn.setProperty("role", role)
    if height > 0:
        btn.setFixedHeight(height)
    if tooltip:
        btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def _set_btn_role(btn: QPushButton, role: str):
    """Update a QPushButton's dynamic [role=...] property cleanly."""
    if role == "default":
        btn.setProperty("role", None)
    else:
        btn.setProperty("role", role)
    style = btn.style()
    if style:
        style.unpolish(btn)
        style.polish(btn)
    btn.update()


def _make_tab_scroll_page():
    """Return (scroll_area, content_layout) for a scrollable settings tab."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    content = QWidget()
    content.setObjectName("cleanContent")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(14, 10, 14, 12)
    layout.setSpacing(10)
    scroll.setWidget(content)
    return scroll, layout


def _add_slider_row(
    parent_layout: QVBoxLayout,
    label_text: str,
    slider: QSlider,
    value_label: QLabel,
    label_width: int = 92,
    val_width: int = 56,
):
    """Build a crisp horizontal row: fixed label, expanding slider, right-aligned readout."""
    row = QHBoxLayout()
    row.setSpacing(10)

    lbl = QLabel(label_text)
    lbl.setStyleSheet("color: #a1a1aa; font-weight: 600;")
    lbl.setFixedWidth(label_width)
    row.addWidget(lbl)

    row.addWidget(slider, 1)

    value_label.setFixedWidth(val_width)
    value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    value_label.setStyleSheet(
        "color: #f4f4f5; font-family: 'Consolas', monospace; font-size: 11px; font-weight: 600;"
    )
    row.addWidget(value_label)
    parent_layout.addLayout(row)


class SettingsDialog(DraggableClampedDialogMixin, QDialog):
    """Clean, intuitive tabbed settings dialog for music library, character, lyrics, and updates."""

    def __init__(self, panel: "ControlPanel"):
        super().__init__()
        self.panel = panel
        self.panel.settings_dialog = self
        self.setWindowTitle("Talia Settings")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumSize(540, 580)
        self.resize(580, 690)
        self.setStyleSheet(CLEAN_UTILITY_QSS)
        self.init_ui()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Clean Slate Header Bar
        header = QFrame()
        header.setStyleSheet(
            "QFrame { background-color: #17171c; border-bottom: 1px solid #272730; }"
        )
        hbox_header = QHBoxLayout(header)
        hbox_header.setContentsMargins(18, 12, 16, 12)
        hbox_header.setSpacing(10)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        lbl_title = QLabel("Settings")
        lbl_title.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: 700;")
        title_col.addWidget(lbl_title)

        lbl_subtitle = QLabel("Configure library folders, character behavior, subtitles, and updates.")
        lbl_subtitle.setStyleSheet("color: #8e8ea0; font-size: 11px;")
        title_col.addWidget(lbl_subtitle)
        hbox_header.addLayout(title_col, 1)

        lbl_ver_badge = QLabel(f"v{APP_VERSION}")
        lbl_ver_badge.setStyleSheet(
            "background-color: #202028; color: #9ca3af; border: 1px solid #2e2e38; "
            "border-radius: 5px; padding: 3px 8px; font-family: 'Consolas', monospace; font-size: 11px;"
        )
        hbox_header.addWidget(lbl_ver_badge)

        root_layout.addWidget(header)

        # Main Tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        tab_general, layout_general = _make_tab_scroll_page()
        tab_lyrics, layout_lyrics_tab = _make_tab_scroll_page()
        tab_visualizer, layout_vis_tab = _make_tab_scroll_page()
        tab_system, layout_sys_tab = _make_tab_scroll_page()

        self.tabs.addTab(tab_general, "General")
        self.tabs.addTab(tab_lyrics, "Lyrics && Fonts")
        self.tabs.addTab(tab_visualizer, "Visualizer")
        self.tabs.addTab(tab_system, "Updates && App")
        root_layout.addWidget(self.tabs, 1)

        # =============================================================
        # TAB 1: GENERAL (Music Library + Character + Behavior)
        # =============================================================
        card_music, layout_music = create_card_frame("Music Library")

        self.lbl_folder_path = QLabel(f"{self.panel.audio_engine.folder_path}")
        self.lbl_folder_path.setStyleSheet(
            "background-color: #15151a; color: #d4d4d8; border: 1px solid #2a2a33; "
            "border-radius: 6px; padding: 8px 10px; font-size: 11px; font-family: 'Consolas', monospace;"
        )
        self.lbl_folder_path.setWordWrap(True)
        layout_music.addWidget(self.lbl_folder_path)

        hbox_folder_btns = QHBoxLayout()
        hbox_folder_btns.setSpacing(8)
        btn_choose = _make_clean_btn("Change Folder...", role="primary")
        btn_choose.clicked.connect(self.panel.choose_music_folder)
        hbox_folder_btns.addWidget(btn_choose)

        btn_open_exp = _make_clean_btn("Open in Explorer")
        btn_open_exp.clicked.connect(self.panel.open_music_folder_explorer)
        hbox_folder_btns.addWidget(btn_open_exp)

        btn_refresh = _make_clean_btn("Refresh Library")
        btn_refresh.clicked.connect(self.panel.refresh_tracklist)
        hbox_folder_btns.addWidget(btn_refresh)
        layout_music.addLayout(hbox_folder_btns)
        layout_general.addWidget(card_music)

        # Character Position & Appearance
        card_char, layout_char = create_card_frame("Character Position & Display")

        self.slider_pos_x = QSlider(Qt.Orientation.Horizontal)
        self.slider_pos_x.valueChanged.connect(self._on_pos_x_changed)
        self.slider_pos_x.sliderReleased.connect(self._on_pos_slider_released)
        self.lbl_pos_x_val = QLabel("0 px")
        _add_slider_row(layout_char, "Horizontal X", self.slider_pos_x, self.lbl_pos_x_val)

        self.slider_pos_y = QSlider(Qt.Orientation.Horizontal)
        self.slider_pos_y.valueChanged.connect(self._on_pos_y_changed)
        self.slider_pos_y.sliderReleased.connect(self._on_pos_slider_released)
        self.lbl_pos_y_val = QLabel("0 px")
        _add_slider_row(layout_char, "Vertical Y", self.slider_pos_y, self.lbl_pos_y_val)

        self.slider_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_size.setRange(MIN_CHAR_SIZE, MAX_CHAR_SIZE)
        self.slider_size.setValue(self.panel.overlay.width())
        self.slider_size.valueChanged.connect(self.panel.on_size_change)
        self.lbl_size_val = QLabel(f"{self.panel.overlay.width()} px")
        _add_slider_row(layout_char, "Scale", self.slider_size, self.lbl_size_val)

        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(20, 100)
        self.slider_opacity.setValue(100)
        self.slider_opacity.valueChanged.connect(self.panel.on_opacity_change)
        self.lbl_op_val = QLabel("100%")
        _add_slider_row(layout_char, "Opacity", self.slider_opacity, self.lbl_op_val)

        self.slider_eye_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_eye_sens.setRange(20, 300)
        self.slider_eye_sens.setValue(100)
        self.slider_eye_sens.valueChanged.connect(self.panel.on_eye_sens_changed)
        self.lbl_sens_val = QLabel("1.0x")
        _add_slider_row(layout_char, "Eye Tracking", self.slider_eye_sens, self.lbl_sens_val)

        self.btn_center_talia = _make_clean_btn(
            "Center Character on Screen",
            tooltip="Move Talia back to the center of your primary monitor",
        )
        self.btn_center_talia.clicked.connect(self.center_talia_on_screen)
        layout_char.addWidget(self.btn_center_talia)
        layout_general.addWidget(card_char)

        # Behavior & Performance
        card_behavior, layout_behavior = create_card_frame("Behavior & Performance")

        hbox_toggles = QHBoxLayout()
        hbox_toggles.setSpacing(14)
        self.chk_bass_pop = QCheckBox("Bass Reaction")
        self.chk_bass_pop.setChecked(True)
        self.chk_bass_pop.toggled.connect(self.panel.on_bass_pop_toggled)
        hbox_toggles.addWidget(self.chk_bass_pop)

        self.chk_head_bop = QCheckBox("Head Bop")
        self.chk_head_bop.setChecked(False)
        self.chk_head_bop.setToolTip("Rhythmic head bobbing animation synchronized to music BPM")
        self.chk_head_bop.toggled.connect(self.panel.on_head_bop_toggled)
        hbox_toggles.addWidget(self.chk_head_bop)

        self.chk_discord_rpc = QCheckBox("Discord Presence")
        self.chk_discord_rpc.setChecked(True)
        self.chk_discord_rpc.toggled.connect(self.panel.on_discord_rpc_toggled)
        hbox_toggles.addWidget(self.chk_discord_rpc)
        hbox_toggles.addStretch(1)
        layout_behavior.addLayout(hbox_toggles)

        is_eco = getattr(self.panel, "eco_mode", False)
        self.btn_eco = _make_clean_btn(
            "Eco Mode: On" if is_eco else "Eco Mode: Off",
            role="success" if is_eco else "default",
            tooltip="Lower animation frame rate to reduce CPU/GPU usage",
        )
        self.btn_eco.clicked.connect(self.panel.toggle_eco_mode)
        layout_behavior.addWidget(self.btn_eco)

        layout_general.addWidget(card_behavior)
        layout_general.addStretch(1)

        # =============================================================
        # TAB 2: LYRICS & FONTS
        # =============================================================
        card_studio, layout_studio = create_card_frame("Lyrics & Calibration Studio")
        lbl_studio_desc = QLabel(
            "Search online synced lyrics, calibrate lines live against playback, or auto-sync your music folder."
        )
        lbl_studio_desc.setStyleSheet("color: #9ca3af; font-size: 11px;")
        lbl_studio_desc.setWordWrap(True)
        layout_studio.addWidget(lbl_studio_desc)

        self.btn_open_fetcher = _make_clean_btn(
            "Open Lyrics & Calibration Studio",
            role="primary",
            height=34,
            tooltip="Open the integrated lyrics search, live timing calibrator, and library sync studio",
        )
        self.btn_open_fetcher.clicked.connect(self.panel.open_lyric_fetcher)
        layout_studio.addWidget(self.btn_open_fetcher)
        layout_lyrics_tab.addWidget(card_studio)

        # Subtitle Timing Offset Card
        card_timing, layout_timing = create_card_frame("Quick Subtitle Timing Offset")
        lbl_timing_hint = QLabel(
            "Nudge lyrics earlier or later for the current song (Ctrl+[ / Ctrl+]). Use Lyrics Studio to save permanently."
        )
        lbl_timing_hint.setStyleSheet("color: #9ca3af; font-size: 11px;")
        lbl_timing_hint.setWordWrap(True)
        layout_timing.addWidget(lbl_timing_hint)

        hbox_sync = QHBoxLayout()
        hbox_sync.setSpacing(6)
        for delta, txt in [(-0.5, "-0.5s"), (-0.1, "-0.1s")]:
            b = _make_clean_btn(txt, height=28)
            b.clicked.connect(lambda _chk=False, d=delta: self.panel.adjust_lyrics_offset(d))
            hbox_sync.addWidget(b)

        self.lbl_sync_offset = QLabel("+0.00s")
        self.lbl_sync_offset.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sync_offset.setMinimumWidth(62)
        self.lbl_sync_offset.setStyleSheet(
            "background-color: #15151a; color: #93c5fd; border: 1px solid #2a2a34; "
            "border-radius: 6px; padding: 4px 6px; font-family: 'Consolas', monospace; font-size: 11px; font-weight: 700;"
        )
        hbox_sync.addWidget(self.lbl_sync_offset)

        for delta, txt in [(0.1, "+0.1s"), (0.5, "+0.5s")]:
            b = _make_clean_btn(txt, height=28)
            b.clicked.connect(lambda _chk=False, d=delta: self.panel.adjust_lyrics_offset(d))
            hbox_sync.addWidget(b)

        btn_sync_reset = _make_clean_btn("Reset", height=28)
        btn_sync_reset.clicked.connect(self.panel.reset_lyrics_offset)
        hbox_sync.addWidget(btn_sync_reset)

        btn_auto_sync = _make_clean_btn(
            "Auto-Align",
            role="primary",
            height=28,
            tooltip="Automatically estimate vocal entry and shift lyric timing",
        )
        btn_auto_sync.clicked.connect(self.panel.auto_sync_lyrics)
        hbox_sync.addWidget(btn_auto_sync)
        layout_timing.addLayout(hbox_sync)
        layout_lyrics_tab.addWidget(card_timing)

        # Typography & Style Card
        card_font, layout_font = create_card_frame("Font & Appearance")

        hbox_font = QHBoxLayout()
        hbox_font.setSpacing(8)
        lbl_font_title = QLabel("Font")
        lbl_font_title.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        lbl_font_title.setFixedWidth(52)
        hbox_font.addWidget(lbl_font_title)

        self.combo_font = NoScrollComboBox()
        self.combo_font.currentTextChanged.connect(self.panel.on_font_changed)
        hbox_font.addWidget(self.combo_font, 1)

        self.btn_open_fonts = _make_clean_btn(
            "Folder", height=28, tooltip="Open assets/fonts/ folder to add .ttf/.otf fonts"
        )
        self.btn_open_fonts.clicked.connect(self.panel.open_fonts_folder)
        hbox_font.addWidget(self.btn_open_fonts)

        self.btn_reload_fonts = _make_clean_btn("Reload", height=28, tooltip="Re-scan fonts folder")
        self.btn_reload_fonts.clicked.connect(self.panel.reload_custom_fonts)
        hbox_font.addWidget(self.btn_reload_fonts)
        layout_font.addLayout(hbox_font)

        self.slider_lyric_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_lyric_size.setRange(14, 60)
        init_size = 18
        if self.panel and getattr(self.panel, "lyrics_overlay", None):
            init_size = getattr(self.panel.lyrics_overlay, "base_font_size", 18)
        self.slider_lyric_size.setValue(init_size)
        self.slider_lyric_size.valueChanged.connect(self.panel.on_lyric_size_changed)
        self.lbl_lyric_size_val = QLabel(f"{init_size} pt")
        _add_slider_row(layout_font, "Font Size", self.slider_lyric_size, self.lbl_lyric_size_val, label_width=64, val_width=48)

        hbox_lyric_color = QHBoxLayout()
        hbox_lyric_color.setSpacing(8)
        lbl_lyric_col = QLabel("Color")
        lbl_lyric_col.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        lbl_lyric_col.setFixedWidth(52)
        hbox_lyric_color.addWidget(lbl_lyric_col)

        self.combo_lyric_color = NoScrollComboBox()
        for name in self.panel.lyric_presets.keys():
            self.combo_lyric_color.addItem(name)
        self.combo_lyric_color.addItem("Custom...")
        self.combo_lyric_color.currentTextChanged.connect(self.panel.on_lyric_preset_changed)
        hbox_lyric_color.addWidget(self.combo_lyric_color, 1)

        self.btn_pick_color = _make_clean_btn("Custom Color...", height=28)
        self.btn_pick_color.clicked.connect(self.panel.choose_custom_lyric_color)
        hbox_lyric_color.addWidget(self.btn_pick_color)
        layout_font.addLayout(hbox_lyric_color)

        self.chk_word_glow = QCheckBox("Word highlight glow animation")
        self.chk_word_glow.setChecked(True)
        self.chk_word_glow.toggled.connect(self.panel.on_word_glow_toggled)
        layout_font.addWidget(self.chk_word_glow)

        self.chk_dialogue_mode = QCheckBox("Dialogue Subtitle Style (Show Artist Speaker Label)")
        self.chk_dialogue_mode.setChecked(True)
        self.chk_dialogue_mode.setToolTip(
            "Displays the detected song artist on the left as the subtitle speaker"
        )
        self.chk_dialogue_mode.toggled.connect(self.panel.on_dialogue_mode_toggled)
        layout_font.addWidget(self.chk_dialogue_mode)

        self.chk_subtitle_bg = QCheckBox("Subtitle Shadow Box Background")
        init_bg = (
            getattr(self.panel.lyrics_overlay, "show_subtitle_bg", True)
            if self.panel and getattr(self.panel, "lyrics_overlay", None)
            else True
        )
        self.chk_subtitle_bg.setChecked(init_bg)
        self.chk_subtitle_bg.setToolTip("Renders a subtle dark shadow box behind subtitles")
        self.chk_subtitle_bg.toggled.connect(self.panel.on_subtitle_bg_toggled)
        layout_font.addWidget(self.chk_subtitle_bg)

        layout_lyrics_tab.addWidget(card_font)
        layout_lyrics_tab.addStretch(1)

        # =============================================================
        # TAB 3: VISUALIZER
        # =============================================================
        card_vis, layout_vis = create_card_frame("Audio Visualizer")

        lbl_vis_hint = QLabel(
            "Choose the waveform geometry and accent palette rendered behind Talia while music plays."
        )
        lbl_vis_hint.setStyleSheet("color: #9ca3af; font-size: 11px;")
        lbl_vis_hint.setWordWrap(True)
        layout_vis.addWidget(lbl_vis_hint)

        hbox_vis_mode = QHBoxLayout()
        hbox_vis_mode.setSpacing(10)
        lbl_vis_mode = QLabel("Visualizer Style")
        lbl_vis_mode.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        lbl_vis_mode.setFixedWidth(112)
        hbox_vis_mode.addWidget(lbl_vis_mode)

        self.combo_mode = NoScrollComboBox()
        self.combo_mode.addItems(["Cyber Bars", "Neon Wave", "Radial Core", "Dual Mirror"])
        self.combo_mode.currentTextChanged.connect(self.panel.on_vis_mode_changed)
        hbox_vis_mode.addWidget(self.combo_mode, 1)
        layout_vis.addLayout(hbox_vis_mode)

        hbox_vis_theme = QHBoxLayout()
        hbox_vis_theme.setSpacing(10)
        lbl_vis_theme = QLabel("Color Palette")
        lbl_vis_theme.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        lbl_vis_theme.setFixedWidth(112)
        hbox_vis_theme.addWidget(lbl_vis_theme)

        self.combo_theme = NoScrollComboBox()
        self.combo_theme.addItems(list(COLOR_THEMES.keys()))
        self.combo_theme.currentTextChanged.connect(self.panel.on_vis_theme_changed)
        hbox_vis_theme.addWidget(self.combo_theme, 1)
        layout_vis.addLayout(hbox_vis_theme)

        layout_vis_tab.addWidget(card_vis)
        layout_vis_tab.addStretch(1)

        # =============================================================
        # TAB 4: UPDATES & APP
        # =============================================================
        card_updates, layout_updates = create_card_frame("Application Updates")

        hbox_ver = QHBoxLayout()
        self.lbl_curr_ver = QLabel(f"Installed Version: v{APP_VERSION}")
        self.lbl_curr_ver.setStyleSheet("color: #f4f4f5; font-weight: 600; font-size: 12px;")
        hbox_ver.addWidget(self.lbl_curr_ver, 1)

        self.btn_check_updates = _make_clean_btn("Check for Updates", height=30)
        self.btn_check_updates.clicked.connect(self._on_check_updates_clicked)
        hbox_ver.addWidget(self.btn_check_updates)
        layout_updates.addLayout(hbox_ver)

        self.lbl_update_status = QLabel("Ready to check GitHub releases for updates.")
        self.lbl_update_status.setStyleSheet("color: #9ca3af; font-size: 11px;")
        self.lbl_update_status.setWordWrap(True)
        layout_updates.addWidget(self.lbl_update_status)

        self.progress_update = QProgressBar()
        self.progress_update.setRange(0, 100)
        self.progress_update.setValue(0)
        self.progress_update.setFixedHeight(14)
        self.progress_update.setVisible(False)
        layout_updates.addWidget(self.progress_update)

        self.btn_install_update = _make_clean_btn("Download & Install Update", role="success", height=32)
        self.btn_install_update.clicked.connect(self._on_install_update_clicked)
        self.btn_install_update.setVisible(False)
        layout_updates.addWidget(self.btn_install_update)
        layout_sys_tab.addWidget(card_updates)

        card_actions, layout_actions = create_card_frame("System & Shortcuts")

        hbox_act_btns = QHBoxLayout()
        hbox_act_btns.setSpacing(8)
        self.btn_show_guide = _make_clean_btn("Controls & Hotkeys Guide", height=30)
        self.btn_show_guide.clicked.connect(self.panel.show_guide_dialog)
        hbox_act_btns.addWidget(self.btn_show_guide, 1)

        btn_reload = _make_clean_btn("Reload Sprites & Assets", height=30)
        btn_reload.clicked.connect(self.panel.reload_art)
        hbox_act_btns.addWidget(btn_reload, 1)
        layout_actions.addLayout(hbox_act_btns)

        self.btn_exit_app = _make_clean_btn("Exit Talia", role="danger", height=32)
        self.btn_exit_app.setObjectName("btnExitApp")
        self.btn_exit_app.clicked.connect(self.panel.overlay.close_application)
        layout_actions.addWidget(self.btn_exit_app)

        layout_sys_tab.addWidget(card_actions)
        layout_sys_tab.addStretch(1)

        # Persistent Footer Bar
        footer = QFrame()
        footer.setStyleSheet(
            "QFrame { background-color: #17171c; border-top: 1px solid #272730; }"
        )
        hbox_footer = QHBoxLayout(footer)
        hbox_footer.setContentsMargins(16, 10, 16, 10)
        hbox_footer.setSpacing(8)

        lbl_auto_hint = QLabel("Most changes preview live on desktop.")
        lbl_auto_hint.setStyleSheet("color: #71717a; font-size: 11px;")
        hbox_footer.addWidget(lbl_auto_hint, 1)

        btn_close_footer = _make_clean_btn("Close", height=30)
        btn_close_footer.clicked.connect(self.hide)
        hbox_footer.addWidget(btn_close_footer)

        self.btn_save_settings = _make_clean_btn("Save Settings", role="primary", height=30)
        self.btn_save_settings.setObjectName("btnSaveSettings")
        self.btn_save_settings.clicked.connect(self.panel.save_settings_action)
        hbox_footer.addWidget(self.btn_save_settings)

        root_layout.addWidget(footer)

        self.populate_fonts()
        self.sync_position_sliders()

    def showEvent(self, event):
        super().showEvent(event)
        self.sync_position_sliders()
        if self.panel and self.panel.overlay:
            self.lbl_size_val.setText(f"{self.panel.overlay.width()} px")
            self.lbl_op_val.setText(
                f"{int(round(getattr(self.panel.overlay, 'opacity_val', 1.0) * 100))}%"
            )
            self.lbl_sens_val.setText(f"{getattr(self.panel.overlay, 'eye_sensitivity', 1.0):.1f}x")
            is_eco = bool(getattr(self.panel, "eco_mode", False))
            self.btn_eco.setText("Eco Mode: On" if is_eco else "Eco Mode: Off")
            _set_btn_role(self.btn_eco, "success" if is_eco else "default")
        if self.panel and getattr(self.panel, "lyrics_overlay", None) and hasattr(self, "chk_subtitle_bg"):
            self.chk_subtitle_bg.blockSignals(True)
            self.chk_subtitle_bg.setChecked(
                getattr(self.panel.lyrics_overlay, "show_subtitle_bg", False)
            )
            self.chk_subtitle_bg.blockSignals(False)

    def sync_position_sliders(self):
        if not hasattr(self, "slider_pos_x") or not hasattr(self, "slider_pos_y"):
            return
        primary_screen = QApplication.primaryScreen()
        if not primary_screen:
            return
        geom = primary_screen.availableGeometry()
        curr_x = self.panel.overlay.x() if self.panel and self.panel.overlay else 0
        curr_y = self.panel.overlay.y() if self.panel and self.panel.overlay else 0

        max_x = max(curr_x + 100, geom.right() - 50)
        max_y = max(curr_y + 100, geom.bottom() - 50)
        min_x = min(curr_x, geom.left())
        min_y = min(curr_y, geom.top())

        self.slider_pos_x.blockSignals(True)
        self.slider_pos_y.blockSignals(True)
        self.slider_pos_x.setRange(min_x, max_x)
        self.slider_pos_y.setRange(min_y, max_y)
        self.slider_pos_x.setValue(curr_x)
        self.slider_pos_y.setValue(curr_y)
        self.lbl_pos_x_val.setText(f"{curr_x} px")
        self.lbl_pos_y_val.setText(f"{curr_y} px")
        self.slider_pos_x.blockSignals(False)
        self.slider_pos_y.blockSignals(False)

    def _on_pos_x_changed(self, val: int):
        self.lbl_pos_x_val.setText(f"{val} px")
        if self.panel and self.panel.overlay:
            self.panel.overlay.move(val, self.panel.overlay.y())

    def _on_pos_y_changed(self, val: int):
        self.lbl_pos_y_val.setText(f"{val} px")
        if self.panel and self.panel.overlay:
            self.panel.overlay.move(self.panel.overlay.x(), val)

    def _on_pos_slider_released(self):
        if self.panel:
            try:
                self.panel.save_settings()
            except Exception:
                pass

    def center_talia_on_screen(self):
        primary_screen = QApplication.primaryScreen()
        if not primary_screen or not self.panel or not self.panel.overlay:
            return
        geom = primary_screen.availableGeometry()
        ow = self.panel.overlay.width()
        oh = self.panel.overlay.height()
        cx = geom.left() + max(0, (geom.width() - ow) // 2)
        cy = geom.top() + max(0, (geom.height() - oh) // 2)
        self.panel.overlay.move(cx, cy)
        self.sync_position_sliders()
        try:
            self.panel.save_settings()
        except Exception:
            pass

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

    def _on_check_updates_clicked(self):
        self.btn_check_updates.setEnabled(False)
        self.lbl_update_status.setText("Checking GitHub for the latest release...")
        self.lbl_update_status.setStyleSheet("color: #60a5fa; font-size: 11px;")
        self._update_worker = UpdateCheckWorker(APP_VERSION, self)
        self._update_worker.check_finished.connect(self._on_update_check_finished)
        self._update_worker.start()

    def _on_update_check_finished(self, info: dict):
        self.btn_check_updates.setEnabled(True)
        if info.get("has_update"):
            ver = info.get("latest_version")
            self._pending_update_url = info.get("download_url")
            self.lbl_update_status.setText(
                f"New version v{ver} available! Click below to update seamlessly."
            )
            self.lbl_update_status.setStyleSheet(
                "color: #4ade80; font-weight: bold; font-size: 11px;"
            )
            self.btn_install_update.setText(f"Update Now to v{ver}")
            self.btn_install_update.setVisible(True)
        elif info.get("error"):
            self.lbl_update_status.setText(f"Could not reach GitHub: {info['error']}")
            self.lbl_update_status.setStyleSheet("color: #f87171; font-size: 11px;")
            self.btn_install_update.setVisible(False)
        else:
            self.lbl_update_status.setText(f"Talia is up to date (v{APP_VERSION}).")
            self.lbl_update_status.setStyleSheet("color: #60a5fa; font-size: 11px;")
            self.btn_install_update.setVisible(False)

    def _on_install_update_clicked(self):
        url = getattr(self, "_pending_update_url", None)
        if not url:
            return
        self.btn_install_update.setEnabled(False)
        self.btn_check_updates.setEnabled(False)
        self.progress_update.setValue(0)
        self.progress_update.setVisible(True)
        self.lbl_update_status.setText("Connecting and downloading update package...")
        self.lbl_update_status.setStyleSheet("color: #60a5fa; font-size: 11px;")

        self._dl_worker = UpdateDownloadWorker(url, target_dir=PROJECT_ROOT, parent=self)
        self._dl_worker.progress.connect(self._on_update_progress)
        self._dl_worker.download_finished.connect(self._on_update_download_finished)
        self._dl_worker.start()

    def _on_update_progress(self, percent: int, speed: str):
        self.progress_update.setValue(percent)
        spd_str = f" ({speed})" if speed else ""
        self.lbl_update_status.setText(f"Downloading update: {percent}%{spd_str}...")

    def _on_update_download_finished(self, ok: bool, zip_path: str, err: str):
        if ok and zip_path and os.path.exists(zip_path):
            self.progress_update.setValue(100)
            self.lbl_update_status.setText(
                "Update package downloaded. Talia is restarting to apply update..."
            )
            self.lbl_update_status.setStyleSheet(
                "color: #4ade80; font-weight: bold; font-size: 11px;"
            )
            QTimer.singleShot(1000, lambda: launch_updater_and_exit(zip_path, PROJECT_ROOT))
        else:
            self.btn_install_update.setEnabled(True)
            self.btn_check_updates.setEnabled(True)
            self.lbl_update_status.setText(f"Update download failed: {err}")
            self.lbl_update_status.setStyleSheet("color: #f87171; font-size: 11px;")

    def closeEvent(self, event):
        self.hide()
        trim_process_memory()
        event.ignore()
