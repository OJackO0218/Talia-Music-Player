"""
Cyberpunk 2077 HUD Controller for Talia Music Player, Visualizer, and Calibration.
Zero emojis, clean minimal typography, soft-contrast eye-friendly aesthetic, fully resizable.
"""

import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QCheckBox, QPushButton, QFileDialog, QComboBox,
    QListWidget, QListWidgetItem, QScrollArea, QFrame, QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon

from config import (
    user32, VK_F8, VK_F9, VK_F10, COLOR_THEMES, MIN_CHAR_SIZE, MAX_CHAR_SIZE,
    save_settings, PROJECT_ROOT, ICON_PATH
)
from audio_engine import CyberAudioEngine
from overlay import OverlayWindow


def create_section_header(title: str) -> QWidget:
    """Creates a refined Cyberpunk HUD section header with a soft crimson accent rule."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 8, 0, 4)
    layout.setSpacing(4)

    lbl = QLabel(title.upper())
    lbl.setStyleSheet("color: #dce3ed; font-weight: bold; font-size: 11px; letter-spacing: 1.5px;")
    layout.addWidget(lbl)

    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Plain)
    line.setStyleSheet("border: none; border-top: 1px solid #7a222e; max-height: 1px;")
    layout.addWidget(line)

    return container


class ControlPanel(QWidget):
    """The Cyberpunk HUD Controller with audio playback, tracklist, visualizer, and calibration."""

    def __init__(self, overlay: OverlayWindow, audio_engine: CyberAudioEngine):
        super().__init__()
        self.overlay = overlay
        self.overlay.panel = self
        self.audio_engine = audio_engine

        self.last_f8_state = False
        self.last_f9_state = False
        self.last_f10_state = False
        self.is_user_scrubbing = False

        self.setWindowTitle("TALIA // SYSTEM CONTROLLER")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        # Resizable window with sensible minimum bounds
        self.setMinimumSize(420, 560)
        self.resize(480, 780)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)

        # Softened, eye-friendly Cyberpunk slate palette (no harsh blinding neons)
        self.setStyleSheet("""
            QWidget {
                background-color: #0d0f15;
                color: #d1d9e6;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #0d0f15;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #2e3547;
                min-height: 24px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: #38d9d9;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QPushButton {
                background-color: #141722;
                border: 1px solid #2e3547;
                color: #d94452;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
                letter-spacing: 0.8px;
            }
            QPushButton:hover {
                background-color: #1c2230;
                border-color: #38d9d9;
                color: #38d9d9;
            }
            QPushButton:pressed {
                background-color: #24464c;
                color: #38d9d9;
                border-color: #38d9d9;
            }
            QPushButton#btnMoveTalia {
                background-color: #181318;
                color: #d94452;
                border: 1px solid #4d1f27;
                font-size: 11px;
                padding: 8px 12px;
                font-weight: bold;
                letter-spacing: 0.8px;
            }
            QPushButton#btnAudioMode {
                background-color: #181318;
                color: #d94452;
                border: 1px solid #4d1f27;
                font-size: 11px;
                padding: 8px 12px;
                font-weight: bold;
                letter-spacing: 0.8px;
            }
            QPushButton#btnPlayPause {
                background-color: #181318;
                color: #d94452;
                border: 1px solid #6b242e;
                font-size: 11px;
                padding: 7px 16px;
                font-weight: bold;
                letter-spacing: 0.8px;
            }
            QPushButton#btnPlayPause:hover {
                background-color: #5c1e26;
                color: #ffffff;
            }
            QPushButton#btnSaveSettings {
                background-color: #141f26;
                color: #38d9d9;
                border: 1px solid #285d66;
                font-weight: bold;
                padding: 7px;
                letter-spacing: 0.8px;
            }
            QPushButton#btnSaveSettings:hover {
                background-color: #1e3a42;
                border-color: #38d9d9;
                color: #ffffff;
            }
            QPushButton#btnExitApp {
                background-color: #181215;
                color: #d94452;
                border: 1px solid #4d1c23;
                font-size: 11px;
                padding: 7px;
                font-weight: bold;
                letter-spacing: 0.8px;
            }
            QPushButton#btnExitApp:hover {
                background-color: #8c2734;
                color: #ffffff;
                border-color: #b83344;
            }
            QComboBox {
                background-color: #141722;
                border: 1px solid #2e3547;
                color: #d94452;
                padding: 5px 10px;
                font-weight: bold;
                font-size: 11px;
            }
            QComboBox:hover {
                border-color: #38d9d9;
                color: #38d9d9;
            }
            QComboBox QAbstractItemView {
                background-color: #0f121a;
                border: 1px solid #38d9d9;
                color: #d1d9e6;
                selection-background-color: #1e3a42;
                selection-color: #38d9d9;
            }
            QListWidget {
                background-color: #0a0c11;
                border: 1px solid #242938;
                color: #cbd5e1;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 6px 10px;
                border-bottom: 1px solid #141722;
            }
            QListWidget::item:hover {
                background-color: #171d2b;
                color: #38d9d9;
            }
            QListWidget::item:selected {
                background-color: #1a2933;
                color: #38d9d9;
                font-weight: bold;
                border-left: 3px solid #38d9d9;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #141722;
                border: 1px solid #262c3d;
            }
            QSlider::sub-page:horizontal {
                background: #a82e3b;
            }
            QSlider::handle:horizontal {
                background: #c93646;
                border: 1px solid #dce3ed;
                width: 14px;
                margin-top: -6px;
                margin-bottom: -6px;
            }
            QSlider::handle:horizontal:hover {
                background: #38d9d9;
                border: 1px solid #ffffff;
            }
            QCheckBox {
                spacing: 8px;
                color: #b0bac9;
                font-size: 11px;
                font-weight: bold;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #2e3547;
                background: #141722;
            }
            QCheckBox::indicator:checked {
                background: #38d9d9;
                border: 1px solid #38d9d9;
            }
            QCheckBox::indicator:hover {
                border-color: #38d9d9;
            }
            QLabel {
                font-size: 11px;
            }
        """)

        self.init_ui()

        # Polling timer for global hotkeys (50ms)
        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.timeout.connect(self.check_hotkeys)
        self.hotkey_timer.start(50)

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
        content_layout.setContentsMargins(14, 12, 14, 14)
        content_layout.setSpacing(10)

        # --- PRIMARY TOGGLES ---
        self.btn_move_talia = QPushButton("MOVE TALIA: LOCKED")
        self.btn_move_talia.setObjectName("btnMoveTalia")
        self.btn_move_talia.clicked.connect(self.toggle_move_talia)
        content_layout.addWidget(self.btn_move_talia)

        self.btn_audio_mode = QPushButton("SOURCE: LOCAL PLAYER")
        self.btn_audio_mode.setObjectName("btnAudioMode")
        self.btn_audio_mode.clicked.connect(self.toggle_audio_mode)
        content_layout.addWidget(self.btn_audio_mode)

        # --- SECTION: PLAYBACK & VOLUME ---
        content_layout.addWidget(create_section_header("Playback & Volume"))

        # Track title banner
        self.lbl_track_title = QLabel("SYSTEM IDLE")
        self.lbl_track_title.setStyleSheet("color: #38d9d9; font-weight: bold; font-size: 12px; font-family: 'Consolas', monospace;")
        content_layout.addWidget(self.lbl_track_title)

        # Timeline seeker
        hbox_time = QHBoxLayout()
        self.lbl_time_cur = QLabel("00:00")
        self.lbl_time_cur.setStyleSheet("color: #8b9cb3; font-family: 'Consolas', monospace;")
        self.slider_seek = QSlider(Qt.Orientation.Horizontal)
        self.slider_seek.setRange(0, 1000)
        self.slider_seek.setValue(0)
        self.slider_seek.sliderPressed.connect(self.on_seek_pressed)
        self.slider_seek.sliderReleased.connect(self.on_seek_released)
        self.lbl_time_dur = QLabel("00:00")
        self.lbl_time_dur.setStyleSheet("color: #8b9cb3; font-family: 'Consolas', monospace;")

        hbox_time.addWidget(self.lbl_time_cur)
        hbox_time.addWidget(self.slider_seek)
        hbox_time.addWidget(self.lbl_time_dur)
        content_layout.addLayout(hbox_time)

        # Playback Transport Buttons
        hbox_controls = QHBoxLayout()
        btn_prev = QPushButton("PREV")
        btn_prev.clicked.connect(self.on_prev_clicked)
        hbox_controls.addWidget(btn_prev)

        self.btn_play_pause = QPushButton("PLAY")
        self.btn_play_pause.setObjectName("btnPlayPause")
        self.btn_play_pause.clicked.connect(self.on_play_pause_clicked)
        hbox_controls.addWidget(self.btn_play_pause)

        btn_next = QPushButton("NEXT")
        btn_next.clicked.connect(self.on_next_clicked)
        hbox_controls.addWidget(btn_next)

        self.btn_shuffle = QPushButton("SHUFFLE: OFF")
        self.btn_shuffle.clicked.connect(self.toggle_shuffle)
        hbox_controls.addWidget(self.btn_shuffle)
        content_layout.addLayout(hbox_controls)

        # Volume Slider
        hbox_vol = QHBoxLayout()
        lbl_vol_title = QLabel("VOLUME:")
        lbl_vol_title.setStyleSheet("color: #d94452; font-weight: bold;")
        hbox_vol.addWidget(lbl_vol_title)

        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(int(self.audio_engine.volume * 100))
        self.slider_vol.valueChanged.connect(self.on_volume_changed)
        hbox_vol.addWidget(self.slider_vol)

        self.lbl_vol_val = QLabel(f"{int(self.audio_engine.volume * 100)}%")
        self.lbl_vol_val.setFixedWidth(36)
        self.lbl_vol_val.setStyleSheet("color: #dce3ed; font-family: 'Consolas', monospace; font-weight: bold;")
        hbox_vol.addWidget(self.lbl_vol_val)
        content_layout.addLayout(hbox_vol)

        # --- SECTION: PLAYLIST & DIRECTORY ---
        content_layout.addWidget(create_section_header("Playlist & Directory"))

        self.lbl_folder_path = QLabel(f"{self.audio_engine.folder_path}")
        self.lbl_folder_path.setStyleSheet("color: #8b9cb3; font-size: 10px; font-family: 'Consolas', monospace;")
        content_layout.addWidget(self.lbl_folder_path)

        hbox_folder_btns = QHBoxLayout()
        btn_choose = QPushButton("LOAD FOLDER")
        btn_choose.clicked.connect(self.choose_music_folder)
        hbox_folder_btns.addWidget(btn_choose)

        btn_open_exp = QPushButton("EXPLORER")
        btn_open_exp.clicked.connect(self.open_music_folder_explorer)
        hbox_folder_btns.addWidget(btn_open_exp)

        btn_refresh = QPushButton("REFRESH")
        btn_refresh.clicked.connect(self.refresh_tracklist)
        hbox_folder_btns.addWidget(btn_refresh)
        content_layout.addLayout(hbox_folder_btns)

        self.list_tracks = QListWidget()
        self.list_tracks.setFixedHeight(120)
        self.list_tracks.itemDoubleClicked.connect(self.on_track_double_clicked)
        content_layout.addWidget(self.list_tracks)

        # --- SECTION: VISUALIZER CONFIGURATION ---
        content_layout.addWidget(create_section_header("Visualizer Configuration"))

        hbox_style = QHBoxLayout()
        lbl_vis_mode = QLabel("STYLE:")
        lbl_vis_mode.setStyleSheet("color: #d94452; font-weight: bold;")
        hbox_style.addWidget(lbl_vis_mode)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Cyber Bars", "Neon Wave", "Radial Core", "Dual Mirror"])
        self.combo_mode.currentTextChanged.connect(self.on_vis_mode_changed)
        hbox_style.addWidget(self.combo_mode)

        lbl_vis_theme = QLabel("PALETTE:")
        lbl_vis_theme.setStyleSheet("color: #d94452; font-weight: bold;")
        hbox_style.addWidget(lbl_vis_theme)

        self.combo_theme = QComboBox()
        self.combo_theme.addItems(list(COLOR_THEMES.keys()))
        self.combo_theme.currentTextChanged.connect(self.on_vis_theme_changed)
        hbox_style.addWidget(self.combo_theme)
        content_layout.addLayout(hbox_style)

        # --- SECTION: CALIBRATION & DISPLAY ---
        content_layout.addWidget(create_section_header("Calibration & Display"))

        # Eye sensitivity
        hbox_sens = QHBoxLayout()
        lbl_sens = QLabel("EYE SENSITIVITY:")
        lbl_sens.setStyleSheet("color: #d94452; font-weight: bold;")
        hbox_sens.addWidget(lbl_sens)

        self.slider_eye_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_eye_sens.setRange(20, 300)
        self.slider_eye_sens.setValue(100)
        self.slider_eye_sens.valueChanged.connect(self.on_eye_sens_changed)
        hbox_sens.addWidget(self.slider_eye_sens)

        self.lbl_sens_val = QLabel("1.0x")
        self.lbl_sens_val.setFixedWidth(36)
        self.lbl_sens_val.setStyleSheet("color: #dce3ed; font-family: 'Consolas', monospace; font-weight: bold;")
        hbox_sens.addWidget(self.lbl_sens_val)
        content_layout.addLayout(hbox_sens)

        # Character size
        hbox_sz = QHBoxLayout()
        lbl_sz = QLabel("CHARACTER SCALE:")
        lbl_sz.setStyleSheet("color: #d94452; font-weight: bold;")
        hbox_sz.addWidget(lbl_sz)

        self.slider_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_size.setRange(MIN_CHAR_SIZE, MAX_CHAR_SIZE)
        self.slider_size.setValue(self.overlay.width())
        self.slider_size.valueChanged.connect(self.on_size_change)
        hbox_sz.addWidget(self.slider_size)
        content_layout.addLayout(hbox_sz)

        # Character opacity
        hbox_op = QHBoxLayout()
        lbl_op = QLabel("OPACITY:")
        lbl_op.setStyleSheet("color: #d94452; font-weight: bold;")
        hbox_op.addWidget(lbl_op)

        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(20, 100)
        self.slider_opacity.setValue(100)
        self.slider_opacity.valueChanged.connect(self.on_opacity_change)
        hbox_op.addWidget(self.slider_opacity)
        content_layout.addLayout(hbox_op)

        # Feature Toggles
        hbox_toggles = QHBoxLayout()
        self.chk_scanlines = QCheckBox("CRT SCANLINES")
        self.chk_scanlines.setChecked(True)
        self.chk_scanlines.toggled.connect(self.on_scanlines_toggled)
        hbox_toggles.addWidget(self.chk_scanlines)

        self.chk_bass_pop = QCheckBox("BASS BEAT REACT")
        self.chk_bass_pop.setChecked(True)
        self.chk_bass_pop.toggled.connect(self.on_bass_pop_toggled)
        hbox_toggles.addWidget(self.chk_bass_pop)

        self.chk_widescreen = QCheckBox("16:9 BEZEL")
        self.chk_widescreen.setChecked(False)
        self.chk_widescreen.toggled.connect(self.on_widescreen_toggled)
        hbox_toggles.addWidget(self.chk_widescreen)
        content_layout.addLayout(hbox_toggles)

        # --- SECTION: SYSTEM ACTIONS ---
        content_layout.addWidget(create_section_header("System Actions"))

        hbox_actions = QHBoxLayout()
        self.btn_save_settings = QPushButton("SAVE CONFIG")
        self.btn_save_settings.setObjectName("btnSaveSettings")
        self.btn_save_settings.clicked.connect(self.save_settings_action)
        hbox_actions.addWidget(self.btn_save_settings)

        btn_reload = QPushButton("RELOAD ASSETS")
        btn_reload.clicked.connect(self.reload_art)
        hbox_actions.addWidget(btn_reload)
        content_layout.addLayout(hbox_actions)

        self.btn_exit_app = QPushButton("POWER OFF TALIA")
        self.btn_exit_app.setObjectName("btnExitApp")
        self.btn_exit_app.clicked.connect(self.overlay.close_application)
        content_layout.addWidget(self.btn_exit_app)

        scroll_area.setWidget(content_widget)
        root_layout.addWidget(scroll_area)

        # -------------------------------------------------------------
        # BOTTOM TELEMETRY & HOTKEY BAR (Anchored)
        # -------------------------------------------------------------
        bottom_bar = QWidget()
        bottom_bar.setStyleSheet("background-color: #10141e; border-top: 1px solid #2e3547; padding: 4px;")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(12, 6, 12, 6)

        lbl_f8 = QLabel("[ F8 ] MOVE TALIA")
        lbl_f8.setStyleSheet("color: #38d9d9; font-weight: bold; font-size: 10px; font-family: 'Consolas', monospace;")
        bottom_layout.addWidget(lbl_f8)

        bottom_layout.addStretch()

        lbl_f9 = QLabel("[ F9 ] HIDE / SHOW")
        lbl_f9.setStyleSheet("color: #8b9cb3; font-weight: bold; font-size: 10px; font-family: 'Consolas', monospace;")
        bottom_layout.addWidget(lbl_f9)

        bottom_layout.addStretch()

        lbl_f10 = QLabel("[ F10 ] SOURCE")
        lbl_f10.setStyleSheet("color: #d94452; font-weight: bold; font-size: 10px; font-family: 'Consolas', monospace;")
        bottom_layout.addWidget(lbl_f10)

        root_layout.addWidget(bottom_bar)

        self.populate_playlist_ui()

    def populate_playlist_ui(self):
        """Refreshes the tracklist widget items."""
        self.list_tracks.clear()
        self.lbl_folder_path.setText(f"{self.audio_engine.folder_path}")
        for i, path in enumerate(self.audio_engine.playlist):
            name = os.path.basename(path)
            item = QListWidgetItem(f"[{i+1:02d}] {name}")
            self.list_tracks.addItem(item)
        if 0 <= self.audio_engine.current_index < self.list_tracks.count():
            self.list_tracks.setCurrentRow(self.audio_engine.current_index)
            self.lbl_track_title.setText(f"{self.audio_engine.get_current_track_title()}")

    def toggle_audio_mode(self):
        """Toggles between Built-in Player and Desktop Audio WASAPI loopback."""
        new_mode = "desktop" if self.audio_engine.audio_mode == "player" else "player"
        self.set_audio_mode(new_mode)

    def set_audio_mode(self, mode: str):
        self.audio_engine.set_audio_mode(mode)
        self.update_audio_mode_ui()
        self.sync_play_state()

    def update_audio_mode_ui(self):
        if self.audio_engine.audio_mode == "desktop":
            self.btn_audio_mode.setText("SOURCE: DESKTOP AUDIO")
            self.btn_audio_mode.setStyleSheet("background-color: #1b3b44; color: #38d9d9; border: 1px solid #38d9d9; font-weight: bold;")
        else:
            self.btn_audio_mode.setText("SOURCE: LOCAL PLAYER")
            self.btn_audio_mode.setStyleSheet("background-color: #181318; color: #d94452; border: 1px solid #4d1f27; font-weight: bold;")

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
        if self.audio_engine.audio_mode == "desktop":
            self.btn_play_pause.setText("LIVE INPUT")
            self.btn_play_pause.setStyleSheet("background-color: #1b3b44; color: #38d9d9; border: 1px solid #38d9d9;")
            self.lbl_track_title.setText("DESKTOP AUDIO (LIVE LOOPBACK)")
            return

        if self.audio_engine.is_playing:
            self.btn_play_pause.setText("PAUSE")
            self.btn_play_pause.setStyleSheet("background-color: #1b3b44; color: #38d9d9; border: 1px solid #38d9d9;")
            self.lbl_track_title.setText(f"{self.audio_engine.get_current_track_title()}")
        else:
            self.btn_play_pause.setText("PLAY")
            self.btn_play_pause.setStyleSheet("background-color: #181318; color: #d94452; border: 1px solid #6b242e;")
            self.lbl_track_title.setText(f"{self.audio_engine.get_current_track_title()}")
        if 0 <= self.audio_engine.current_index < self.list_tracks.count():
            self.list_tracks.setCurrentRow(self.audio_engine.current_index)

    def on_next_clicked(self):
        self.audio_engine.next_track()
        self.sync_play_state()

    def on_prev_clicked(self):
        self.audio_engine.prev_track()
        self.sync_play_state()

    def toggle_shuffle(self):
        self.audio_engine.shuffle = not self.audio_engine.shuffle
        if self.audio_engine.shuffle:
            self.btn_shuffle.setText("SHUFFLE: ON")
            self.btn_shuffle.setStyleSheet("background-color: #1b3b44; color: #38d9d9; border: 1px solid #38d9d9;")
        else:
            self.btn_shuffle.setText("SHUFFLE: OFF")
            self.btn_shuffle.setStyleSheet("background-color: #141722; color: #8b9cb3; border: 1px solid #2e3547;")

    def on_track_double_clicked(self, item):
        row = self.list_tracks.row(item)
        self.audio_engine.play_index(row)
        self.sync_play_state()

    def sync_volume(self, vol: float):
        """Synchronizes the volume slider and label from external events (e.g. wheel scroll on Talia)."""
        val = int(round(vol * 100))
        self.slider_vol.blockSignals(True)
        self.slider_vol.setValue(val)
        self.lbl_vol_val.setText(f"{val}%")
        self.slider_vol.blockSignals(False)

    def on_volume_changed(self, val):
        vol = val / 100.0
        self.lbl_vol_val.setText(f"{val}%")
        self.overlay.set_volume(vol)

    def on_seek_pressed(self):
        self.is_user_scrubbing = True

    def on_seek_released(self):
        self.is_user_scrubbing = False
        duration = self.audio_engine.get_duration()
        if duration > 0:
            target_sec = (self.slider_seek.value() / 1000.0) * duration
            self.audio_engine.seek(target_sec)

    def update_timeline(self):
        if self.audio_engine.audio_mode == "desktop":
            self.lbl_time_cur.setText("LIVE")
            self.lbl_time_dur.setText("LOOP")
            self.slider_seek.setValue(0)
            return

        # Auto-advance to next track when song finishes
        if self.audio_engine.track_finished:
            self.audio_engine.track_finished = False
            self.audio_engine.next_track()
            self.sync_play_state()

        if self.is_user_scrubbing:
            return

        pos = self.audio_engine.get_position()
        dur = self.audio_engine.get_duration()

        m_pos, s_pos = int(pos // 60), int(pos % 60)
        m_dur, s_dur = int(dur // 60), int(dur % 60)

        self.lbl_time_cur.setText(f"{m_pos:02d}:{s_pos:02d}")
        self.lbl_time_dur.setText(f"{m_dur:02d}:{s_dur:02d}")

        if dur > 0:
            pct = int((pos / dur) * 1000)
            self.slider_seek.setValue(pct)
        else:
            self.slider_seek.setValue(0)

    def choose_music_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Music Folder / Playlist", self.audio_engine.folder_path
        )
        if folder:
            self.audio_engine.set_folder(folder)
            self.populate_playlist_ui()
            if self.audio_engine.playlist:
                self.audio_engine.load_file(self.audio_engine.playlist[0], auto_play=False)
                self.sync_play_state()

    def open_music_folder_explorer(self):
        if os.path.exists(self.audio_engine.folder_path):
            os.startfile(self.audio_engine.folder_path)

    def refresh_tracklist(self):
        self.audio_engine.refresh_playlist()
        self.populate_playlist_ui()

    def on_vis_mode_changed(self, mode):
        self.overlay.visualizer.mode = mode
        self.overlay.update()

    def on_vis_theme_changed(self, theme):
        self.overlay.visualizer.current_theme_name = theme
        self.overlay.update()

    def on_eye_sens_changed(self, val):
        self.overlay.eye_sensitivity = val / 100.0
        self.lbl_sens_val.setText(f"{val / 100.0:.1f}x")

    def on_size_change(self, val):
        self.overlay.resize(val, val)
        self.overlay.update()

    def on_opacity_change(self, val):
        self.overlay.opacity_val = val / 100.0
        self.overlay.update()

    def on_scanlines_toggled(self, checked):
        self.overlay.enable_scanlines = checked
        self.overlay.update()

    def on_bass_pop_toggled(self, checked):
        self.overlay.enable_bass_pop = checked
        self.overlay.update()

    def on_widescreen_toggled(self, checked):
        self.overlay.use_widescreen = checked
        self.overlay.load_assets()
        if checked:
            screen = self.screen().geometry()
            self.overlay.resize(screen.width(), screen.height())
            self.overlay.move(0, 0)
        else:
            size = self.slider_size.value()
            self.overlay.resize(size, size)
        self.overlay.update()

    def reload_art(self):
        self.overlay.load_assets()
        print("[STATUS] Reloaded fresh images from eye_parts/ folder!")

    def check_hotkeys(self):
        f8_down = bool(user32.GetAsyncKeyState(VK_F8) & 0x8000)
        if f8_down and not self.last_f8_state:
            self.toggle_move_talia()
        self.last_f8_state = f8_down

        f9_down = bool(user32.GetAsyncKeyState(VK_F9) & 0x8000)
        if f9_down and not self.last_f9_state:
            self.toggle_visibility()
        self.last_f9_state = f9_down

        f10_down = bool(user32.GetAsyncKeyState(VK_F10) & 0x8000)
        if f10_down and not self.last_f10_state:
            self.toggle_audio_mode()
        self.last_f10_state = f10_down

    def update_move_talia_ui(self):
        """Refreshes the Move Talia toggle button appearance to match current overlay state."""
        if self.overlay.move_talia_mode:
            self.btn_move_talia.setText("MOVE TALIA: ACTIVE")
            self.btn_move_talia.setStyleSheet("background-color: #1b3b44; color: #38d9d9; border: 1px solid #38d9d9; font-weight: bold;")
        else:
            self.btn_move_talia.setText("MOVE TALIA: LOCKED")
            self.btn_move_talia.setStyleSheet("background-color: #181318; color: #d94452; border: 1px solid #4d1f27; font-weight: bold;")

    def toggle_move_talia(self):
        new_state = not self.overlay.move_talia_mode
        self.overlay.set_move_talia_mode(new_state)
        self.update_move_talia_ui()

    def toggle_visibility(self):
        if self.overlay.isVisible():
            self.overlay.hide()
            print("[STATUS] Overlay hidden.")
        else:
            self.overlay.show()
            self.overlay.enforce_topmost()
            print("[STATUS] Overlay visible.")

    # ==========================================================
    # Settings Persistence
    # ==========================================================
    def get_current_settings_dict(self) -> dict:
        """Gathers all current configuration into a dictionary, protecting against shutdown/startup states."""
        # Use pre-shutdown coordinates if currently in a sinking shutdown sequence
        if getattr(self.overlay, "is_shutting_down", False) and hasattr(self.overlay, "shutdown_start_pos"):
            pos_x = int(self.overlay.shutdown_start_pos.x())
            pos_y = int(self.overlay.shutdown_start_pos.y())
        elif getattr(self.overlay, "is_starting_up", False) and hasattr(self.overlay, "target_startup_y"):
            pos_x = int(self.overlay.target_startup_x)
            pos_y = int(self.overlay.target_startup_y)
        else:
            pos_x = int(self.overlay.pos().x())
            pos_y = int(self.overlay.pos().y())

        # NEVER save 0.0 opacity from an animated shutdown fade! Use slider value (clamped 0.20 to 1.0)
        user_opacity = max(0.20, min(1.0, self.slider_opacity.value() / 100.0))

        return {
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
            "shuffle": bool(self.audio_engine.shuffle)
        }

    def apply_settings(self, cfg: dict):
        """Applies loaded settings to the overlay and controls with generous boundary safety."""
        # 1. Size
        size = int(cfg.get("char_size", self.overlay.width()))
        size = max(MIN_CHAR_SIZE, min(MAX_CHAR_SIZE, size))
        self.slider_size.setValue(size)
        self.overlay.resize(size, size)

        # 2. Position (ensure it is within visible screen bounds on laptop/desktop scaling)
        screen = QApplication.primaryScreen().geometry()
        pos_x = int(cfg.get("pos_x", -1))
        pos_y = int(cfg.get("pos_y", -1))

        # Accept any coordinate that places at least part of Talia on screen
        if (-size // 2 <= pos_x <= screen.width()) and (-size // 2 <= pos_y <= screen.height()):
            self.overlay.move(pos_x, pos_y)
        else:
            # Fallback to sensible visible bottom-right position
            def_x = max(20, screen.width() - size - 40)
            def_y = max(20, screen.height() - size - 80)
            self.overlay.move(def_x, def_y)

        # 3. Eye Sensitivity
        sens = cfg.get("eye_sensitivity", 1.0)
        self.slider_eye_sens.setValue(int(sens * 100))

        # 4. Opacity (GUARANTEE >= 0.20 so Talia can NEVER be invisible)
        raw_op = float(cfg.get("opacity", 1.0))
        if raw_op < 0.20:
            raw_op = 1.0
        self.slider_opacity.setValue(int(raw_op * 100))
        self.overlay.opacity_val = raw_op

        # 5. Features
        self.chk_scanlines.setChecked(cfg.get("scanlines", True))
        self.chk_bass_pop.setChecked(cfg.get("bass_pop", True))
        self.overlay.enable_bass_pop = cfg.get("bass_pop", True)
        self.chk_widescreen.setChecked(cfg.get("widescreen", False))

        # 6. Visualizer
        vis_mode = cfg.get("visualizer_mode", "Cyber Bars")
        if vis_mode in ["Cyber Bars", "Neon Wave", "Radial Core", "Dual Mirror"]:
            self.combo_mode.setCurrentText(vis_mode)

        palette = cfg.get("visualizer_palette", "Cyberpunk Neon")
        if palette in COLOR_THEMES:
            self.combo_theme.setCurrentText(palette)

        # 7. Volume
        vol = cfg.get("volume", 0.85)
        self.sync_volume(vol)
        self.overlay.set_volume(vol)

        # 8. Audio Mode
        audio_mode = cfg.get("audio_mode", "player")
        if audio_mode in ("player", "desktop"):
            self.set_audio_mode(audio_mode)

        # 9. Shuffle
        if cfg.get("shuffle", False) != self.audio_engine.shuffle:
            self.toggle_shuffle()

        self.overlay.update()

    def _reset_save_btn(self):
        self.btn_save_settings.setText("SAVE CONFIG")
        self.btn_save_settings.setStyleSheet("")

    def save_settings_action(self):
        """Triggered by the Save Settings button."""
        cfg = self.get_current_settings_dict()
        if save_settings(cfg):
            self.btn_save_settings.setText("CONFIG SAVED")
            self.btn_save_settings.setStyleSheet("background-color: #1b3b44; color: #38d9d9; border: 1px solid #38d9d9;")
            QTimer.singleShot(1500, self._reset_save_btn)

    def closeEvent(self, event):
        # Auto-save settings on close/hide
        cfg = self.get_current_settings_dict()
        save_settings(cfg)

        # Do NOT terminate overlay or stop timers - hide window cleanly!
        self.hide()
        event.ignore()
        print("[CONTROLLER] Controller window hidden. Click Talia 3x to reopen.")
