"""Advanced settings dialog for Talia."""

import os
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
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
from updater import (
    UpdateCheckWorker,
    UpdateDownloadWorker,
    launch_updater_and_exit,
)
from ui_theme import SHARED_PANEL_STYLE
from ui_widgets import NoScrollComboBox, create_section_header

if TYPE_CHECKING:
    from controller import ControlPanel


def create_card_frame(title: str):
    """Creates a neat, modern grouped card container for settings."""
    frame = QFrame()
    frame.setStyleSheet("""
        QFrame {
            background-color: #1a1a1f;
            border: 1px solid #292932;
            border-radius: 6px;
        }
    """)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(8)
    layout.addWidget(create_section_header(title))
    return frame, layout


class SettingsDialog(QDialog):
    """Clean, dedicated settings dialog for advanced lyrics, visualizer, and character configuration."""

    def __init__(self, panel: "ControlPanel"):
        super().__init__()
        self.panel = panel
        self.setWindowTitle("Talia Settings")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumSize(480, 580)
        self.resize(500, 720)
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
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(14, 14, 14, 14)
        content_layout.setSpacing(10)

        # -------------------------------------------------------------
        # CARD 1: MUSIC LIBRARY
        # -------------------------------------------------------------
        card_music, layout_music = create_card_frame("Music Library")

        self.lbl_folder_path = QLabel(f"{self.panel.audio_engine.folder_path}")
        self.lbl_folder_path.setStyleSheet(
            "background-color: #121215; color: #a1a1aa; border: 1px solid #27272f; border-radius: 4px; padding: 6px 8px; font-size: 10px; font-family: 'Consolas', monospace;"
        )
        self.lbl_folder_path.setWordWrap(True)
        layout_music.addWidget(self.lbl_folder_path)

        hbox_folder_btns = QHBoxLayout()
        hbox_folder_btns.setSpacing(6)
        btn_choose = QPushButton("Change Folder")
        btn_choose.clicked.connect(self.panel.choose_music_folder)
        hbox_folder_btns.addWidget(btn_choose)

        btn_open_exp = QPushButton("Open in Explorer")
        btn_open_exp.clicked.connect(self.panel.open_music_folder_explorer)
        hbox_folder_btns.addWidget(btn_open_exp)

        btn_refresh = QPushButton("Refresh Library")
        btn_refresh.clicked.connect(self.panel.refresh_tracklist)
        hbox_folder_btns.addWidget(btn_refresh)
        layout_music.addLayout(hbox_folder_btns)

        content_layout.addWidget(card_music)

        # -------------------------------------------------------------
        # CARD 2: LYRICS CONFIGURATION & TIMINGS
        # -------------------------------------------------------------
        card_lyrics, layout_lyrics = create_card_frame("Lyrics Configuration")

        self.btn_open_fetcher = QPushButton("Launch Automated Lyric Fetcher")
        self.btn_open_fetcher.setToolTip("Open the automated lyrics fetcher and calibration tool")
        self.btn_open_fetcher.setStyleSheet("""
            QPushButton {
                background-color: #0c4a6e;
                color: #7dd3fc;
                border: 1px solid #0284c7;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #0284c7;
                color: #ffffff;
            }
        """)
        self.btn_open_fetcher.clicked.connect(self.panel.open_lyric_fetcher)
        layout_lyrics.addWidget(self.btn_open_fetcher)

        # Font row
        hbox_font = QHBoxLayout()
        hbox_font.setSpacing(6)
        lbl_font_title = QLabel("Font:")
        lbl_font_title.setStyleSheet("color: #a1a1aa; font-weight: 600; min-width: 45px;")
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
        layout_lyrics.addLayout(hbox_font)

        # Lyrics Size slider row
        hbox_size = QHBoxLayout()
        hbox_size.setSpacing(6)
        lbl_size_title = QLabel("Size:")
        lbl_size_title.setStyleSheet("color: #a1a1aa; font-weight: 600; min-width: 45px;")
        hbox_size.addWidget(lbl_size_title)

        self.slider_lyric_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_lyric_size.setRange(14, 60)
        init_size = 18
        if self.panel and getattr(self.panel, "lyrics_overlay", None):
            init_size = getattr(self.panel.lyrics_overlay, "base_font_size", 18)
        self.slider_lyric_size.setValue(init_size)
        self.slider_lyric_size.valueChanged.connect(self.panel.on_lyric_size_changed)
        hbox_size.addWidget(self.slider_lyric_size)

        self.lbl_lyric_size_val = QLabel(f"{init_size} pt")
        self.lbl_lyric_size_val.setFixedWidth(44)
        self.lbl_lyric_size_val.setStyleSheet(
            "color: #f4f4f5; font-family: 'Consolas', monospace; font-weight: 600; font-size: 11px;"
        )
        hbox_size.addWidget(self.lbl_lyric_size_val)
        layout_lyrics.addLayout(hbox_size)

        # Color row
        hbox_lyric_color = QHBoxLayout()
        hbox_lyric_color.setSpacing(6)
        lbl_lyric_col = QLabel("Color:")
        lbl_lyric_col.setStyleSheet("color: #a1a1aa; font-weight: 600; min-width: 45px;")
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
        layout_lyrics.addLayout(hbox_lyric_color)

        self.chk_word_glow = QCheckBox("Word highlight glow animation")
        self.chk_word_glow.setChecked(True)
        self.chk_word_glow.toggled.connect(self.panel.on_word_glow_toggled)
        layout_lyrics.addWidget(self.chk_word_glow)

        self.chk_dialogue_mode = QCheckBox("Cyberpunk Dialogue Subtitles (Show Artist in Red)")
        self.chk_dialogue_mode.setChecked(True)
        self.chk_dialogue_mode.setToolTip("Displays the detected song artist on the left in Cyberpunk 2077 red as the dialogue speaker")
        self.chk_dialogue_mode.toggled.connect(self.panel.on_dialogue_mode_toggled)
        layout_lyrics.addWidget(self.chk_dialogue_mode)

        # Sync offset controls
        hbox_sync = QHBoxLayout()
        hbox_sync.setSpacing(4)
        lbl_sync_title = QLabel("Sync:")
        lbl_sync_title.setStyleSheet("color: #a1a1aa; font-weight: 600; min-width: 45px;")
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
        self.lbl_sync_offset.setStyleSheet(
            "color: #f4f4f5; font-weight: 600; min-width: 52px; font-family: 'Consolas', monospace; font-size: 11px;"
        )
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
        layout_lyrics.addLayout(hbox_sync)

        content_layout.addWidget(card_lyrics)

        # -------------------------------------------------------------
        # CARD 3: VISUALIZER & PALETTE
        # -------------------------------------------------------------
        card_vis, layout_vis = create_card_frame("Visualizer & Palette")

        hbox_style = QHBoxLayout()
        hbox_style.setSpacing(8)

        lbl_vis_mode = QLabel("Style:")
        lbl_vis_mode.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        hbox_style.addWidget(lbl_vis_mode)

        self.combo_mode = NoScrollComboBox()
        self.combo_mode.addItems(["Cyber Bars", "Neon Wave", "Radial Core", "Dual Mirror"])
        self.combo_mode.currentTextChanged.connect(self.panel.on_vis_mode_changed)
        hbox_style.addWidget(self.combo_mode, 1)

        lbl_vis_theme = QLabel("Palette:")
        lbl_vis_theme.setStyleSheet("color: #a1a1aa; font-weight: 600;")
        hbox_style.addWidget(lbl_vis_theme)

        self.combo_theme = NoScrollComboBox()
        self.combo_theme.addItems(list(COLOR_THEMES.keys()))
        self.combo_theme.currentTextChanged.connect(self.panel.on_vis_theme_changed)
        hbox_style.addWidget(self.combo_theme, 1)

        layout_vis.addLayout(hbox_style)
        content_layout.addWidget(card_vis)

        # -------------------------------------------------------------
        # CARD 4: CHARACTER & DISPLAY
        # -------------------------------------------------------------
        card_char, layout_char = create_card_frame("Character & Display")

        # Eye sensitivity
        hbox_sens = QHBoxLayout()
        hbox_sens.setSpacing(6)
        lbl_sens = QLabel("Sensitivity:")
        lbl_sens.setStyleSheet("color: #a1a1aa; font-weight: 600; min-width: 75px;")
        hbox_sens.addWidget(lbl_sens)

        self.slider_eye_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_eye_sens.setRange(20, 300)
        self.slider_eye_sens.setValue(100)
        self.slider_eye_sens.valueChanged.connect(self.panel.on_eye_sens_changed)
        hbox_sens.addWidget(self.slider_eye_sens)

        self.lbl_sens_val = QLabel("1.0x")
        self.lbl_sens_val.setFixedWidth(40)
        self.lbl_sens_val.setStyleSheet(
            "color: #f4f4f5; font-family: 'Consolas', monospace; font-weight: 600; font-size: 11px;"
        )
        hbox_sens.addWidget(self.lbl_sens_val)
        layout_char.addLayout(hbox_sens)

        # Character scale
        hbox_sz = QHBoxLayout()
        hbox_sz.setSpacing(6)
        lbl_sz = QLabel("Scale:")
        lbl_sz.setStyleSheet("color: #a1a1aa; font-weight: 600; min-width: 75px;")
        hbox_sz.addWidget(lbl_sz)

        self.slider_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_size.setRange(MIN_CHAR_SIZE, MAX_CHAR_SIZE)
        self.slider_size.setValue(self.panel.overlay.width())
        self.slider_size.valueChanged.connect(self.panel.on_size_change)
        hbox_sz.addWidget(self.slider_size)

        self.lbl_size_val = QLabel(f"{self.panel.overlay.width()} px")
        self.lbl_size_val.setFixedWidth(50)
        self.lbl_size_val.setStyleSheet(
            "color: #f4f4f5; font-family: 'Consolas', monospace; font-weight: 600; font-size: 11px;"
        )
        hbox_sz.addWidget(self.lbl_size_val)
        layout_char.addLayout(hbox_sz)

        # Character opacity
        hbox_op = QHBoxLayout()
        hbox_op.setSpacing(6)
        lbl_op = QLabel("Opacity:")
        lbl_op.setStyleSheet("color: #a1a1aa; font-weight: 600; min-width: 75px;")
        hbox_op.addWidget(lbl_op)

        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(20, 100)
        self.slider_opacity.setValue(100)
        self.slider_opacity.valueChanged.connect(self.panel.on_opacity_change)
        hbox_op.addWidget(self.slider_opacity)

        self.lbl_op_val = QLabel("100%")
        self.lbl_op_val.setFixedWidth(40)
        self.lbl_op_val.setStyleSheet(
            "color: #f4f4f5; font-family: 'Consolas', monospace; font-weight: 600; font-size: 11px;"
        )
        hbox_op.addWidget(self.lbl_op_val)
        layout_char.addLayout(hbox_op)

        # Checkboxes
        hbox_toggles = QHBoxLayout()
        hbox_toggles.setSpacing(12)
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
        layout_char.addLayout(hbox_toggles)

        content_layout.addWidget(card_char)

        # -------------------------------------------------------------
        # CARD 5: APPLICATION UPDATES
        # -------------------------------------------------------------
        card_updates, layout_updates = create_card_frame("Application Updates")

        hbox_ver = QHBoxLayout()
        self.lbl_curr_ver = QLabel(f"Installed Version: v{APP_VERSION}")
        self.lbl_curr_ver.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 12px;")
        hbox_ver.addWidget(self.lbl_curr_ver, 1)

        self.btn_check_updates = QPushButton("Check for Updates")
        self.btn_check_updates.setStyleSheet(
            "background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px; font-weight: 600; padding: 4px 12px; font-size: 11px;"
        )
        self.btn_check_updates.clicked.connect(self._on_check_updates_clicked)
        hbox_ver.addWidget(self.btn_check_updates)
        layout_updates.addLayout(hbox_ver)

        self.lbl_update_status = QLabel("Ready to check GitHub for updates.")
        self.lbl_update_status.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        self.lbl_update_status.setWordWrap(True)
        layout_updates.addWidget(self.lbl_update_status)

        self.progress_update = QProgressBar()
        self.progress_update.setRange(0, 100)
        self.progress_update.setValue(0)
        self.progress_update.setFixedHeight(12)
        self.progress_update.setStyleSheet("""
            QProgressBar {
                background-color: #121215;
                border: 1px solid #27272a;
                border-radius: 4px;
                text-align: center;
                color: transparent;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 3px;
            }
        """)
        self.progress_update.setVisible(False)
        layout_updates.addWidget(self.progress_update)

        self.btn_install_update = QPushButton("Download & Install Update")
        self.btn_install_update.setStyleSheet(
            "background-color: #059669; color: #ffffff; font-weight: bold; padding: 7px; border-radius: 4px; font-size: 12px;"
        )
        self.btn_install_update.clicked.connect(self._on_install_update_clicked)
        self.btn_install_update.setVisible(False)
        layout_updates.addWidget(self.btn_install_update)

        content_layout.addWidget(card_updates)

        # -------------------------------------------------------------
        # CARD 6: ACTIONS & SYSTEM
        # -------------------------------------------------------------
        card_actions, layout_actions = create_card_frame("Actions")

        hbox_act_btns = QHBoxLayout()
        hbox_act_btns.setSpacing(6)

        self.btn_save_settings = QPushButton("Save Settings")
        self.btn_save_settings.setObjectName("btnSaveSettings")
        self.btn_save_settings.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: bold;"
        )
        self.btn_save_settings.clicked.connect(self.panel.save_settings_action)
        hbox_act_btns.addWidget(self.btn_save_settings)

        self.btn_show_guide = QPushButton("Controls Guide")
        self.btn_show_guide.clicked.connect(self.panel.show_guide_dialog)
        hbox_act_btns.addWidget(self.btn_show_guide)

        btn_reload = QPushButton("Reload Assets")
        btn_reload.clicked.connect(self.panel.reload_art)
        hbox_act_btns.addWidget(btn_reload)

        layout_actions.addLayout(hbox_act_btns)

        self.btn_exit_app = QPushButton("Exit Talia")
        self.btn_exit_app.setObjectName("btnExitApp")
        self.btn_exit_app.setStyleSheet(
            "background-color: #450a0a; color: #fca5a5; border: 1px solid #991b1b; font-weight: bold; margin-top: 4px;"
        )
        self.btn_exit_app.clicked.connect(self.panel.overlay.close_application)
        layout_actions.addWidget(self.btn_exit_app)

        content_layout.addWidget(card_actions)

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

    def _on_check_updates_clicked(self):
        self.btn_check_updates.setEnabled(False)
        self.lbl_update_status.setText("Checking GitHub for the latest release...")
        self.lbl_update_status.setStyleSheet("color: #38bdf8; font-size: 11px;")
        self._update_worker = UpdateCheckWorker(APP_VERSION, self)
        self._update_worker.check_finished.connect(self._on_update_check_finished)
        self._update_worker.start()

    def _on_update_check_finished(self, info: dict):
        self.btn_check_updates.setEnabled(True)
        if info.get("has_update"):
            ver = info.get("latest_version")
            self._pending_update_url = info.get("download_url")
            self.lbl_update_status.setText(f"New version v{ver} available! Click below to update seamlessly.")
            self.lbl_update_status.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 11px;")
            self.btn_install_update.setText(f"Update Now to v{ver}")
            self.btn_install_update.setVisible(True)
        elif info.get("error"):
            self.lbl_update_status.setText(f"Could not reach GitHub: {info['error']}")
            self.lbl_update_status.setStyleSheet("color: #f87171; font-size: 11px;")
            self.btn_install_update.setVisible(False)
        else:
            self.lbl_update_status.setText(f"Talia is up to date (v{APP_VERSION}).")
            self.lbl_update_status.setStyleSheet("color: #38bdf8; font-size: 11px;")
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
        self.lbl_update_status.setStyleSheet("color: #38bdf8; font-size: 11px;")

        self._dl_worker = UpdateDownloadWorker(url, self)
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
            self.lbl_update_status.setText("Update package downloaded. Talia is restarting to apply update...")
            self.lbl_update_status.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 11px;")
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
