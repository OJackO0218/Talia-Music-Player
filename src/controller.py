"""
Cyberpunk Controller UI for Talia Music Player, Visualizers, and Layout Configuration.
"""

import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QCheckBox, QPushButton, QGroupBox, QFileDialog,
    QComboBox, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon

from config import (
    user32, VK_F8, VK_F9, VK_F10, COLOR_THEMES, MIN_CHAR_SIZE, MAX_CHAR_SIZE,
    save_settings, load_settings, PROJECT_ROOT, ICON_PATH
)
from audio_engine import CyberAudioEngine
from overlay import OverlayWindow


class ControlPanel(QWidget):
    """The Controller UI with audio playback, tracklist, visualizer themes, and layout persistence."""

    def __init__(self, overlay: OverlayWindow, audio_engine: CyberAudioEngine):
        super().__init__()
        self.overlay = overlay
        self.overlay.panel = self
        self.audio_engine = audio_engine

        self.last_f8_state = False
        self.last_f9_state = False
        self.last_f10_state = False
        self.is_user_scrubbing = False

        self.setWindowTitle("Talia Cyberpunk Music Controller")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setFixedSize(460, 890)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QWidget {
                background-color: #0b0e14;
                color: #e6edf3;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QGroupBox {
                border: 1px solid #1f2937;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: #00f0ff;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QPushButton {
                background-color: #161b22;
                border: 1px solid #30363d;
                color: #c9d1d9;
                padding: 6px 12px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #21262d;
                border-color: #00f0ff;
                color: #00f0ff;
            }
            QPushButton#btnMoveTalia {
                background-color: #238636;
                color: #ffffff;
                border: 1px solid #2ea043;
                font-size: 12px;
                padding: 8px;
            }
            QPushButton#btnAudioMode {
                background-color: #161b22;
                color: #00f0ff;
                border: 1px solid #30363d;
                font-size: 11px;
                padding: 7px;
                font-weight: bold;
            }
            QPushButton#btnAudioMode:hover {
                border-color: #00f0ff;
                background-color: #1f2937;
            }
            QPushButton#btnPlayPause {
                background-color: #ff0055;
                color: #ffffff;
                border: 1px solid #ff3377;
                font-size: 13px;
                padding: 7px 16px;
            }
            QPushButton#btnPlayPause:hover {
                background-color: #e6004c;
            }
            QPushButton#btnSaveSettings {
                background-color: #1f6feb;
                color: #ffffff;
                border: 1px solid #388bfd;
            }
            QPushButton#btnSaveSettings:hover {
                background-color: #388bfd;
            }
            QComboBox {
                background-color: #161b22;
                border: 1px solid #30363d;
                color: #00f0ff;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
            QComboBox QAbstractItemView {
                background-color: #161b22;
                color: #e6edf3;
                selection-background-color: #00f0ff;
                selection-color: #000000;
            }
            QListWidget {
                background-color: #0e121a;
                border: 1px solid #1f2937;
                border-radius: 4px;
                color: #c9d1d9;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #161b22;
            }
            QListWidget::item:hover {
                background-color: #161b22;
                color: #00f0ff;
            }
            QListWidget::item:selected {
                background-color: #1a2736;
                color: #00f0ff;
                font-weight: bold;
                border-left: 3px solid #00f0ff;
            }
            QSlider::groove:horizontal {
                height: 5px;
                background: #1f2937;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #00f0ff;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 12px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 6px;
            }
            QCheckBox {
                spacing: 8px;
                font-size: 11px;
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
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # 1. Move Talia Mode Button
        self.btn_move_talia = QPushButton("🔒 MOVE TALIA: OFF (Click Talia to Play/Skip)")
        self.btn_move_talia.setObjectName("btnMoveTalia")
        self.btn_move_talia.clicked.connect(self.toggle_move_talia)
        layout.addWidget(self.btn_move_talia)

        # Audio Source Mode Toggle Button
        self.btn_audio_mode = QPushButton("🎵 AUDIO SOURCE: BUILT-IN MUSIC PLAYER (Click to switch)")
        self.btn_audio_mode.setObjectName("btnAudioMode")
        self.btn_audio_mode.clicked.connect(self.toggle_audio_mode)
        layout.addWidget(self.btn_audio_mode)

        lbl_hint = QLabel("💡 Hotkeys: [F8] Move Talia | [F9] Hide/Show Talia | [F10] Switch Desktop/Player")
        lbl_hint.setStyleSheet("color: #8b949e; font-size: 10px;")
        layout.addWidget(lbl_hint)

        # ==========================================================
        # 2. Cyberpunk Music Player Section
        # ==========================================================
        grp_player = QGroupBox("Cyberpunk Music Player")
        vbox_player = QVBoxLayout()
        vbox_player.setSpacing(5)

        # Track title banner
        self.lbl_track_title = QLabel("🎵 Ready")
        self.lbl_track_title.setStyleSheet("color: #00f0ff; font-weight: bold; font-size: 12px;")
        vbox_player.addWidget(self.lbl_track_title)

        # Time elapsed & Duration
        hbox_time = QHBoxLayout()
        self.lbl_time_cur = QLabel("00:00")
        self.lbl_time_cur.setStyleSheet("color: #8b949e; font-family: monospace;")
        self.slider_seek = QSlider(Qt.Orientation.Horizontal)
        self.slider_seek.setRange(0, 1000)
        self.slider_seek.setValue(0)
        self.slider_seek.sliderPressed.connect(self.on_seek_pressed)
        self.slider_seek.sliderReleased.connect(self.on_seek_released)
        self.lbl_time_dur = QLabel("00:00")
        self.lbl_time_dur.setStyleSheet("color: #8b949e; font-family: monospace;")

        hbox_time.addWidget(self.lbl_time_cur)
        hbox_time.addWidget(self.slider_seek)
        hbox_time.addWidget(self.lbl_time_dur)
        vbox_player.addLayout(hbox_time)

        # Playback Transport Buttons
        hbox_controls = QHBoxLayout()
        btn_prev = QPushButton("⏮ Prev")
        btn_prev.clicked.connect(self.on_prev_clicked)
        hbox_controls.addWidget(btn_prev)

        self.btn_play_pause = QPushButton("▶ Play")
        self.btn_play_pause.setObjectName("btnPlayPause")
        self.btn_play_pause.clicked.connect(self.on_play_pause_clicked)
        hbox_controls.addWidget(self.btn_play_pause)

        btn_next = QPushButton("Next ⏭")
        btn_next.clicked.connect(self.on_next_clicked)
        hbox_controls.addWidget(btn_next)

        self.btn_shuffle = QPushButton("🔀 Shuffle: OFF")
        self.btn_shuffle.clicked.connect(self.toggle_shuffle)
        hbox_controls.addWidget(self.btn_shuffle)
        vbox_player.addLayout(hbox_controls)

        # Volume Slider
        hbox_vol = QHBoxLayout()
        hbox_vol.addWidget(QLabel("Volume:"))
        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(int(self.audio_engine.volume * 100))
        self.slider_vol.valueChanged.connect(self.on_volume_changed)
        hbox_vol.addWidget(self.slider_vol)
        self.lbl_vol_val = QLabel(f"{int(self.audio_engine.volume * 100)}%")
        self.lbl_vol_val.setFixedWidth(32)
        hbox_vol.addWidget(self.lbl_vol_val)
        vbox_player.addLayout(hbox_vol)

        # Visualizer Style & Theme Selectors
        hbox_style = QHBoxLayout()
        hbox_style.addWidget(QLabel("Visualizer:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Cyber Bars", "Neon Wave", "Radial Core", "Dual Mirror"])
        self.combo_mode.currentTextChanged.connect(self.on_vis_mode_changed)
        hbox_style.addWidget(self.combo_mode)

        hbox_style.addWidget(QLabel("Palette:"))
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(list(COLOR_THEMES.keys()))
        self.combo_theme.currentTextChanged.connect(self.on_vis_theme_changed)
        hbox_style.addWidget(self.combo_theme)
        vbox_player.addLayout(hbox_style)

        grp_player.setLayout(vbox_player)
        layout.addWidget(grp_player)

        # ==========================================================
        # 3. Folder & Playlist Management Section
        # ==========================================================
        grp_playlist = QGroupBox("Playlist & Music Folder")
        vbox_pl = QVBoxLayout()
        vbox_pl.setSpacing(5)

        # Folder Path Display
        self.lbl_folder_path = QLabel(f"📂 {self.audio_engine.folder_path}")
        self.lbl_folder_path.setStyleSheet("color: #8b949e; font-size: 10px;")
        vbox_pl.addWidget(self.lbl_folder_path)

        # Folder Actions
        hbox_folder_btns = QHBoxLayout()
        btn_choose = QPushButton("📁 Choose Folder")
        btn_choose.clicked.connect(self.choose_music_folder)
        hbox_folder_btns.addWidget(btn_choose)

        btn_open_exp = QPushButton("📂 Open in Explorer")
        btn_open_exp.clicked.connect(self.open_music_folder_explorer)
        hbox_folder_btns.addWidget(btn_open_exp)

        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self.refresh_tracklist)
        hbox_folder_btns.addWidget(btn_refresh)
        vbox_pl.addLayout(hbox_folder_btns)

        # Tracklist ListWidget
        self.list_tracks = QListWidget()
        self.list_tracks.setFixedHeight(110)
        self.list_tracks.itemDoubleClicked.connect(self.on_track_double_clicked)
        vbox_pl.addWidget(self.list_tracks)

        grp_playlist.setLayout(vbox_pl)
        layout.addWidget(grp_playlist)

        # ==========================================================
        # 4. Interactive Eye Tracking Settings
        # ==========================================================
        grp_eyes = QGroupBox("Interactive Eye-Tracking")
        vbox_eyes = QVBoxLayout()

        hbox_sens = QHBoxLayout()
        hbox_sens.addWidget(QLabel("Eye Sensitivity:"))
        self.slider_eye_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_eye_sens.setRange(20, 300)
        self.slider_eye_sens.setValue(100)
        self.slider_eye_sens.valueChanged.connect(self.on_eye_sens_changed)
        hbox_sens.addWidget(self.slider_eye_sens)

        self.lbl_sens_val = QLabel("1.0x")
        self.lbl_sens_val.setFixedWidth(36)
        hbox_sens.addWidget(self.lbl_sens_val)

        vbox_eyes.addLayout(hbox_sens)
        grp_eyes.setLayout(vbox_eyes)
        layout.addWidget(grp_eyes)

        # ==========================================================
        # 5. Display, Aesthetics & Settings Saving
        # ==========================================================
        grp_display = QGroupBox("Display & Settings")
        vbox_disp = QVBoxLayout()
        vbox_disp.setSpacing(5)

        # Size slider (150px to 3840px)
        hbox_sz = QHBoxLayout()
        hbox_sz.addWidget(QLabel("Character Size:"))
        self.slider_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_size.setRange(MIN_CHAR_SIZE, MAX_CHAR_SIZE)
        self.slider_size.setValue(self.overlay.width())
        self.slider_size.valueChanged.connect(self.on_size_change)
        hbox_sz.addWidget(self.slider_size)
        vbox_disp.addLayout(hbox_sz)

        # Opacity slider
        hbox_op = QHBoxLayout()
        hbox_op.addWidget(QLabel("Character Opacity:"))
        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(20, 100)
        self.slider_opacity.setValue(100)
        self.slider_opacity.valueChanged.connect(self.on_opacity_change)
        hbox_op.addWidget(self.slider_opacity)
        vbox_disp.addLayout(hbox_op)

        # Scanlines, Bass Beat Pop & Widescreen
        hbox_toggles = QHBoxLayout()
        self.chk_scanlines = QCheckBox("CRT Scanlines")
        self.chk_scanlines.setChecked(True)
        self.chk_scanlines.toggled.connect(self.on_scanlines_toggled)
        hbox_toggles.addWidget(self.chk_scanlines)

        self.chk_bass_pop = QCheckBox("🎵 Bass Beat Pop")
        self.chk_bass_pop.setChecked(True)
        self.chk_bass_pop.toggled.connect(self.on_bass_pop_toggled)
        hbox_toggles.addWidget(self.chk_bass_pop)

        self.chk_widescreen = QCheckBox("16:9 Bezel")
        self.chk_widescreen.setChecked(False)
        self.chk_widescreen.toggled.connect(self.on_widescreen_toggled)
        hbox_toggles.addWidget(self.chk_widescreen)
        vbox_disp.addLayout(hbox_toggles)

        # Actions: Save Settings & Reload Art
        hbox_actions = QHBoxLayout()
        self.btn_save_settings = QPushButton("💾 Save Settings & Position")
        self.btn_save_settings.setObjectName("btnSaveSettings")
        self.btn_save_settings.clicked.connect(self.save_settings_action)
        hbox_actions.addWidget(self.btn_save_settings)

        btn_reload = QPushButton("🔄 Reload Art Files")
        btn_reload.clicked.connect(self.reload_art)
        hbox_actions.addWidget(btn_reload)
        vbox_disp.addLayout(hbox_actions)

        # Power Off / Exit Talia button
        self.btn_exit_app = QPushButton("🛑 Power Off & Exit Talia")
        self.btn_exit_app.setStyleSheet("""
            QPushButton {
                background-color: #2a1118;
                color: #ff4d6d;
                border: 1px solid #ff4d6d;
                font-size: 11px;
                padding: 6px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #ff0055;
                color: #ffffff;
            }
        """)
        self.btn_exit_app.clicked.connect(self.overlay.close_application)
        vbox_disp.addWidget(self.btn_exit_app)

        grp_display.setLayout(vbox_disp)
        layout.addWidget(grp_display)

        self.setLayout(layout)
        self.populate_playlist_ui()

    def populate_playlist_ui(self):
        """Refreshes the tracklist widget items."""
        self.list_tracks.clear()
        self.lbl_folder_path.setText(f"📂 {self.audio_engine.folder_path}")
        for i, path in enumerate(self.audio_engine.playlist):
            name = os.path.basename(path)
            item = QListWidgetItem(f"{i+1:02d}. {name}")
            self.list_tracks.addItem(item)
        if 0 <= self.audio_engine.current_index < self.list_tracks.count():
            self.list_tracks.setCurrentRow(self.audio_engine.current_index)
            self.lbl_track_title.setText(f"🎵 {self.audio_engine.get_current_track_title()}")

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
            self.btn_audio_mode.setText("🎧 AUDIO SOURCE: DESKTOP AUDIO (Listening to osu!, Spotify...)")
            self.btn_audio_mode.setStyleSheet("background-color: #7928ca; color: #ffffff; border: 1px solid #ff007f; font-size: 11px; padding: 7px; font-weight: bold;")
        else:
            self.btn_audio_mode.setText("🎵 AUDIO SOURCE: BUILT-IN MUSIC PLAYER (Click to switch)")
            self.btn_audio_mode.setStyleSheet("background-color: #161b22; color: #00f0ff; border: 1px solid #30363d; font-size: 11px; padding: 7px; font-weight: bold;")

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
            self.btn_play_pause.setText("🎧 Live Loop")
            self.btn_play_pause.setStyleSheet("background-color: #7928ca; border-color: #ff007f; color: white;")
            self.lbl_track_title.setText("🎧 Desktop Audio (osu!, Spotify, Games)")
            return

        if self.audio_engine.is_playing:
            self.btn_play_pause.setText("⏸ Pause")
            self.btn_play_pause.setStyleSheet("background-color: #238636; border-color: #2ea043; color: white;")
            self.lbl_track_title.setText(f"🎵 Playing: {self.audio_engine.get_current_track_title()}")
        else:
            self.btn_play_pause.setText("▶ Play")
            self.btn_play_pause.setStyleSheet("background-color: #ff0055; border-color: #ff3377; color: white;")
            self.lbl_track_title.setText(f"⏸ Paused: {self.audio_engine.get_current_track_title()}")
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
            self.btn_shuffle.setText("🔀 Shuffle: ON")
            self.btn_shuffle.setStyleSheet("color: #00f0ff; border-color: #00f0ff;")
        else:
            self.btn_shuffle.setText("🔀 Shuffle: OFF")
            self.btn_shuffle.setStyleSheet("")

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
            self.btn_move_talia.setText("🖐️ MOVE TALIA: ON (Drag to Reposition)")
            self.btn_move_talia.setStyleSheet("background-color: #00f0ff; color: #0b0e14; border: 1px solid #38d9a9; font-size: 12px; padding: 8px; font-weight: bold;")
        else:
            self.btn_move_talia.setText("🔒 MOVE TALIA: OFF (Click Talia to Play/Skip)")
            self.btn_move_talia.setStyleSheet("background-color: #238636; color: #ffffff; border: 1px solid #2ea043; font-size: 12px; padding: 8px; font-weight: bold;")

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
        """Gathers all current configuration into a dictionary."""
        return {
            "pos_x": int(self.overlay.pos().x()),
            "pos_y": int(self.overlay.pos().y()),
            "char_size": int(self.overlay.width()),
            "eye_sensitivity": round(float(self.overlay.eye_sensitivity), 2),
            "opacity": round(float(self.overlay.opacity_val), 2),
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
        """Applies loaded settings to the overlay and controls."""
        # 1. Position and Size
        size = cfg.get("char_size", self.overlay.width())
        self.slider_size.setValue(size)
        self.overlay.resize(size, size)

        pos_x = cfg.get("pos_x", -1)
        pos_y = cfg.get("pos_y", -1)
        if pos_x >= 0 and pos_y >= 0:
            self.overlay.move(pos_x, pos_y)

        # 2. Eye Sensitivity
        sens = cfg.get("eye_sensitivity", 1.0)
        self.slider_eye_sens.setValue(int(sens * 100))

        # 3. Opacity
        opacity = cfg.get("opacity", 1.0)
        self.slider_opacity.setValue(int(opacity * 100))

        # 4. Scanlines, Bass Beat Pop & Widescreen
        self.chk_scanlines.setChecked(cfg.get("scanlines", True))
        self.chk_bass_pop.setChecked(cfg.get("bass_pop", True))
        self.overlay.enable_bass_pop = cfg.get("bass_pop", True)
        self.chk_widescreen.setChecked(cfg.get("widescreen", False))

        # 5. Visualizer Mode & Palette
        vis_mode = cfg.get("visualizer_mode", "Cyber Bars")
        if vis_mode in ["Cyber Bars", "Neon Wave", "Radial Core", "Dual Mirror"]:
            self.combo_mode.setCurrentText(vis_mode)

        palette = cfg.get("visualizer_palette", "Cyberpunk Neon")
        if palette in COLOR_THEMES:
            self.combo_theme.setCurrentText(palette)

        # 6. Volume
        vol = cfg.get("volume", 0.85)
        self.sync_volume(vol)
        self.overlay.set_volume(vol)

        # 7. Audio Mode
        audio_mode = cfg.get("audio_mode", "player")
        if audio_mode in ("player", "desktop"):
            self.set_audio_mode(audio_mode)

        # 8. Shuffle
        if cfg.get("shuffle", False) != self.audio_engine.shuffle:
            self.toggle_shuffle()

        self.overlay.update()

    def save_settings_action(self):
        """Triggered by the Save Settings button."""
        cfg = self.get_current_settings_dict()
        if save_settings(cfg):
            self.btn_save_settings.setText("✅ Settings Saved!")
            QTimer.singleShot(1500, lambda: self.btn_save_settings.setText("💾 Save Settings & Position"))

    def closeEvent(self, event):
        # Auto-save settings on close/hide
        cfg = self.get_current_settings_dict()
        save_settings(cfg)

        # Do NOT terminate overlay or stop timers - hide window cleanly!
        self.hide()
        event.ignore()
        print("[CONTROLLER] Controller window closed/hidden. Click Talia 3x to reopen.")
