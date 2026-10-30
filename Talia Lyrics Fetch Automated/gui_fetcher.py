"""
Talia Lyrics Fetch Automated - Cyberpunk GUI (v2.0 Idiot-Proof Edition)
Visual desktop utility for batch lyrics downloading, auto-tagging, and continuous folder monitoring.
Matches Talia's Cyberpunk 2077 HUD palette and design system.
"""

import os
import sys
import time
import shutil
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QProgressBar, QTextEdit, QCheckBox, QFrame,
    QTabWidget, QSplitter, QSlider, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import QFont, QIcon, QColor
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from fetch_lyrics import (
    get_default_music_dir, scan_and_fetch_folder, fetch_synced_lyrics,
    fetch_lyrics_for_file, SUPPORTED_AUDIO_EXTS, detect_vocal_entry,
    search_all_lrc_candidates, smart_auto_calibrate_lrc, restore_lrc_backup,
    shift_lrc_timestamps, extract_metadata
)


class BatchFetchWorker(QThread):
    progress = pyqtSignal(int, int, str, bool, str)
    finished = pyqtSignal(dict)

    def __init__(self, folder_path: str, force_overwrite: bool):
        super().__init__()
        self.folder_path = folder_path
        self.force_overwrite = force_overwrite
        self.is_cancelled = False

    def run(self):
        def cb(cur, total, path, success, msg):
            if not self.is_cancelled:
                self.progress.emit(cur, total, path, success, msg)

        stats = scan_and_fetch_folder(
            self.folder_path,
            force_overwrite=self.force_overwrite,
            progress_callback=cb
        )
        self.finished.emit(stats)

    def cancel(self):
        self.is_cancelled = True


class LyricsFetcherWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TALIA // AUTOMATED LYRICS FETCHER")
        self.resize(760, 660)
        self.setMinimumSize(600, 520)

        self.worker: BatchFetchWorker = None
        self.watcher_timer = QTimer(self)
        self.watcher_timer.timeout.connect(self._on_watcher_tick)
        self.known_songs = set()

        # Dedicated Media Player for audio preview & tap-to-sync
        self.cal_player = QMediaPlayer(self)
        self.cal_audio_output = QAudioOutput(self)
        self.cal_player.setAudioOutput(self.cal_audio_output)
        self.cal_player.positionChanged.connect(self._on_player_pos_changed)
        self.cal_player.durationChanged.connect(self._on_player_dur_changed)

        self._apply_styling()
        self._init_ui()

    def _apply_styling(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #0b0d13;
                color: #d1d9e6;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLineEdit {
                background-color: #12151f;
                border: 1px solid #23293a;
                border-radius: 3px;
                padding: 7px 10px;
                color: #e2e8f0;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #e879f9;
            }
            QPushButton {
                background-color: #181d2c;
                border: 1px solid #2e3852;
                border-radius: 3px;
                padding: 8px 14px;
                font-weight: bold;
                font-size: 11px;
                color: #cbd5e1;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background-color: #232a3f;
                border: 1px solid #38d9d9;
                color: #38d9d9;
            }
            QPushButton:pressed {
                background-color: #0e121c;
            }
            QProgressBar {
                background-color: #12151f;
                border: 1px solid #23293a;
                border-radius: 3px;
                text-align: center;
                color: #ffffff;
                font-size: 10px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9333ea, stop:1 #38d9d9);
                border-radius: 2px;
            }
            QTextEdit {
                background-color: #08090d;
                border: 1px solid #1c2130;
                border-radius: 3px;
                color: #a5b4fc;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                padding: 6px;
            }
            QCheckBox {
                color: #94a3b8;
                font-size: 11px;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                background-color: #12151f;
                border: 1px solid #2e3852;
                border-radius: 2px;
            }
            QCheckBox::indicator:checked {
                background-color: #9333ea;
                border: 1px solid #e879f9;
            }
            QTabWidget::pane {
                border: 1px solid #1e2435;
                background: #0d0f17;
            }
            QTabBar::tab {
                background: #12151f;
                border: 1px solid #1e2435;
                padding: 8px 18px;
                color: #64748b;
                font-weight: bold;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: #1b1f2e;
                color: #e879f9;
                border-bottom: 2px solid #e879f9;
            }
        """)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header
        header_layout = QHBoxLayout()
        title_lbl = QLabel("TALIA // AUTOMATED LYRICS FETCHER (v2.0)")
        title_lbl.setStyleSheet("color: #e879f9; font-size: 14px; font-weight: bold; letter-spacing: 1.5px;")
        header_layout.addWidget(title_lbl)

        header_layout.addStretch()
        self.lbl_watcher_status = QLabel("WATCHER: IDLE")
        self.lbl_watcher_status.setStyleSheet("color: #64748b; font-size: 10px; font-weight: bold;")
        header_layout.addWidget(self.lbl_watcher_status)
        main_layout.addLayout(header_layout)

        # Tabs: Batch Folder Processing vs Single Track Lookup
        tabs = QTabWidget()
        tabs.addTab(self._create_batch_tab(), "BATCH FOLDER SYNC")
        tabs.addTab(self._create_lookup_tab(), "SINGLE SONG SEARCH")
        tabs.addTab(self._create_calibrator_tab(), "SYNC CALIBRATOR")
        main_layout.addWidget(tabs)

    def _create_batch_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        # Folder Picker
        lbl_folder = QLabel("MUSIC LIBRARY FOLDER:")
        lbl_folder.setStyleSheet("color: #38d9d9; font-weight: bold; font-size: 10px; letter-spacing: 1px;")
        layout.addWidget(lbl_folder)

        hbox_folder = QHBoxLayout()
        self.edit_folder = QLineEdit(get_default_music_dir())
        hbox_folder.addWidget(self.edit_folder)

        btn_browse = QPushButton("BROWSE")
        btn_browse.clicked.connect(self._browse_folder)
        hbox_folder.addWidget(btn_browse)
        layout.addLayout(hbox_folder)

        # Options & Watcher
        hbox_opts = QHBoxLayout()
        self.chk_force = QCheckBox("Force Re-fetch Existing (Creates .bak backup)")
        hbox_opts.addWidget(self.chk_force)

        self.chk_watch = QCheckBox("Auto-Watch Folder (Auto-downloads when songs are added)")
        self.chk_watch.toggled.connect(self._toggle_watcher)
        hbox_opts.addWidget(self.chk_watch)
        hbox_opts.addStretch()
        layout.addLayout(hbox_opts)

        # Action Buttons
        hbox_actions = QHBoxLayout()
        self.btn_start = QPushButton("FETCH ALL MISSING LYRICS")
        self.btn_start.setStyleSheet("background-color: #2b1138; color: #e879f9; border: 1px solid #9333ea; font-size: 12px; padding: 10px;")
        self.btn_start.clicked.connect(self._start_batch_fetch)
        hbox_actions.addWidget(self.btn_start)

        btn_restore_bak = QPushButton("RESTORE .BAK BACKUPS")
        btn_restore_bak.clicked.connect(self._restore_backups)
        hbox_actions.addWidget(btn_restore_bak)

        self.btn_clear_log = QPushButton("CLEAR LOG")
        self.btn_clear_log.clicked.connect(lambda: self.log_text.clear())
        hbox_actions.addWidget(self.btn_clear_log)
        layout.addLayout(hbox_actions)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(16)
        layout.addWidget(self.progress_bar)

        # Terminal Log
        lbl_log = QLabel("ACTIVITY TERMINAL:")
        lbl_log.setStyleSheet("color: #64748b; font-weight: bold; font-size: 10px; letter-spacing: 1px;")
        layout.addWidget(lbl_log)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        return tab

    def _create_lookup_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        layout.addWidget(QLabel("SEARCH SYNCHRONIZED LYRICS ONLINE:"))

        hbox_fields = QHBoxLayout()
        self.edit_search_title = QLineEdit()
        self.edit_search_title.setPlaceholderText("Song Title (e.g. BANG BANG BANG)...")
        hbox_fields.addWidget(self.edit_search_title)

        self.edit_search_artist = QLineEdit()
        self.edit_search_artist.setPlaceholderText("Artist (e.g. bbpanzu)...")
        hbox_fields.addWidget(self.edit_search_artist)

        btn_search = QPushButton("SEARCH")
        btn_search.setStyleSheet("background-color: #1b3b44; color: #38d9d9; border: 1px solid #38d9d9;")
        btn_search.clicked.connect(self._lookup_single_song)
        hbox_fields.addWidget(btn_search)
        layout.addLayout(hbox_fields)

        self.txt_preview = QTextEdit()
        self.txt_preview.setPlaceholderText("Synchronized LRC results will appear here...")
        layout.addWidget(self.txt_preview)

        hbox_save = QHBoxLayout()
        hbox_save.addStretch()
        btn_save_preview = QPushButton("SAVE PREVIEW TO FILE (.LRC)")
        btn_save_preview.clicked.connect(self._save_preview_lrc)
        hbox_save.addWidget(btn_save_preview)
        layout.addLayout(hbox_save)

        return tab


    def _create_calibrator_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header description
        desc = QLabel("Interactive Audio Player, Tap-to-Sync, Multi-Candidate Search, and Vocal Formant Calibrator.")
        desc.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(desc)

        # 1. File Selector Row
        hbox_file = QHBoxLayout()
        self.edit_cal_file = QLineEdit()
        self.edit_cal_file.setPlaceholderText("Select audio track to calibrate...")
        hbox_file.addWidget(self.edit_cal_file)

        btn_browse_cal = QPushButton("BROWSE FILE")
        btn_browse_cal.clicked.connect(self._browse_cal_file)
        hbox_file.addWidget(btn_browse_cal)

        btn_smart_cal = QPushButton("SMART AUTO-CALIBRATE")
        btn_smart_cal.setStyleSheet("background-color: #2b1138; color: #e879f9; border: 1px solid #c084fc; font-weight: bold; padding: 6px 12px;")
        btn_smart_cal.setToolTip("Analyzes human vocal frequencies (350-2800 Hz) and safely shifts only if genuinely delayed")
        btn_smart_cal.clicked.connect(self._auto_calibrate_active_file)
        hbox_file.addWidget(btn_smart_cal)
        layout.addLayout(hbox_file)

        # 2. Interactive Audio Player & Tap-to-Sync Row
        player_frame = QFrame()
        player_frame.setStyleSheet("background-color: #0e111a; border: 1px solid #23293a; border-radius: 4px; padding: 8px;")
        vbox_player = QVBoxLayout(player_frame)
        vbox_player.setContentsMargins(6, 6, 6, 6)
        vbox_player.setSpacing(6)

        hbox_player_ctrls = QHBoxLayout()
        self.btn_play_pause = QPushButton("PLAY")
        self.btn_play_pause.setStyleSheet("background-color: #1b3b44; color: #38d9d9; border: 1px solid #38d9d9; font-weight: bold; min-width: 70px;")
        self.btn_play_pause.clicked.connect(self._toggle_audio_playback)
        hbox_player_ctrls.addWidget(self.btn_play_pause)

        btn_stop = QPushButton("STOP")
        btn_stop.setStyleSheet("background-color: #181d2c; color: #cbd5e1; border: 1px solid #2e3852;")
        btn_stop.clicked.connect(self._stop_audio_playback)
        hbox_player_ctrls.addWidget(btn_stop)

        self.slider_pos = QSlider(Qt.Orientation.Horizontal)
        self.slider_pos.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #23293a; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #e879f9; border-radius: 2px; }
            QSlider::handle:horizontal { background: #38d9d9; width: 12px; margin: -4px 0; border-radius: 6px; }
        """)
        self.slider_pos.sliderMoved.connect(self._on_slider_moved)
        hbox_player_ctrls.addWidget(self.slider_pos)

        self.lbl_time = QLabel("00:00.00 / 00:00.00")
        self.lbl_time.setStyleSheet("color: #94a3b8; font-family: 'Consolas', monospace; font-size: 11px; min-width: 120px;")
        hbox_player_ctrls.addWidget(self.lbl_time)

        # Big TAP TO SYNC button
        self.btn_tap_sync = QPushButton("TAP TO SYNC (SPACEBAR)")
        self.btn_tap_sync.setStyleSheet("background-color: #2b1138; color: #ffe600; border: 2px solid #ffe600; font-weight: bold; padding: 6px 14px; font-size: 11px;")
        self.btn_tap_sync.setToolTip("Play the song. As soon as the first word is sung, click this or hit Spacebar to lock the sync!")
        self.btn_tap_sync.clicked.connect(self._tap_to_sync)
        hbox_player_ctrls.addWidget(self.btn_tap_sync)

        vbox_player.addLayout(hbox_player_ctrls)
        layout.addWidget(player_frame)

        # 3. Telemetry Display Box
        telemetry_frame = QFrame()
        telemetry_frame.setStyleSheet("background-color: #12151f; border: 1px solid #23293a; border-radius: 4px; padding: 6px;")
        hbox_tele = QHBoxLayout(telemetry_frame)

        self.lbl_cal_onset = QLabel("VOCAL ENTRY: --")
        self.lbl_cal_onset.setStyleSheet("color: #38d9d9; font-weight: bold; font-family: 'Consolas', monospace;")
        hbox_tele.addWidget(self.lbl_cal_onset)

        self.lbl_cal_lyric = QLabel("FIRST LYRIC: --")
        self.lbl_cal_lyric.setStyleSheet("color: #e879f9; font-weight: bold; font-family: 'Consolas', monospace;")
        hbox_tele.addWidget(self.lbl_cal_lyric)

        self.lbl_cal_diff = QLabel("DISCREPANCY: --")
        self.lbl_cal_diff.setStyleSheet("color: #ffe600; font-weight: bold; font-family: 'Consolas', monospace;")
        hbox_tele.addWidget(self.lbl_cal_diff)

        self.lbl_cal_status = QLabel("STATUS: IDLE")
        self.lbl_cal_status.setStyleSheet("color: #94a3b8; font-weight: bold; font-family: 'Consolas', monospace;")
        hbox_tele.addWidget(self.lbl_cal_status)
        layout.addWidget(telemetry_frame)

        # 4. High-Precision Lyrics & Calibration Action Row
        hbox_cands = QHBoxLayout()
        btn_fetch_verified = QPushButton("FETCH VERIFIED LRC")
        btn_fetch_verified.setStyleSheet("background-color: #1b3b44; color: #38d9d9; border: 1px solid #38d9d9; font-weight: bold; padding: 5px 12px;")
        btn_fetch_verified.setToolTip("Fetches verified synced lyrics with strict duration proximity (+/-2.0s) to prevent desync")
        btn_fetch_verified.clicked.connect(self._fetch_verified_lrc)
        hbox_cands.addWidget(btn_fetch_verified)

        btn_auto_cal = QPushButton("AUTO CALIBRATE (VOCALS)")
        btn_auto_cal.setStyleSheet("background-color: #142838; color: #00f0ff; border: 1px solid #00f0ff; font-weight: bold; padding: 5px 12px;")
        btn_auto_cal.setToolTip("Aligns timestamps automatically based on singing frequency formant detection")
        btn_auto_cal.clicked.connect(self._auto_calibrate_active_file)
        hbox_cands.addWidget(btn_auto_cal)

        self.btn_tap_sync = QPushButton("TAP TO SYNC [SPACE]")
        self.btn_tap_sync.setStyleSheet("background-color: #2b1138; color: #e879f9; border: 1px solid #c084fc; font-weight: bold; padding: 5px 12px;")
        self.btn_tap_sync.setToolTip("Press Space or click when you hear the first vocal to sync the entire song")
        self.btn_tap_sync.clicked.connect(self._tap_to_sync)
        hbox_cands.addWidget(self.btn_tap_sync)

        layout.addLayout(hbox_cands)

        # 5. Quick Offset Tuning Buttons + Direct Offset Input
        hbox_shifts = QHBoxLayout()
        for delta in [-1.0, -0.5, -0.1, 0.1, 0.5, 1.0]:
            sign = "+" if delta > 0 else ""
            btn = QPushButton(f"{sign}{delta}s")
            btn.setStyleSheet("background-color: #181d2c; color: #cbd5e1; border: 1px solid #2e3852; padding: 4px 8px;")
            btn.clicked.connect(lambda _, d=delta: self._shift_active_lrc(d))
            hbox_shifts.addWidget(btn)

        lbl_manual_shift = QLabel("SHIFT:")
        lbl_manual_shift.setStyleSheet("color: #94a3b8; font-size: 11px;")
        hbox_shifts.addWidget(lbl_manual_shift)

        self.edit_manual_shift = QLineEdit()
        self.edit_manual_shift.setPlaceholderText("+/-sec (e.g. -11.5)")
        self.edit_manual_shift.setMaximumWidth(110)
        hbox_shifts.addWidget(self.edit_manual_shift)

        btn_apply_shift = QPushButton("APPLY")
        btn_apply_shift.setStyleSheet("background-color: #1e1528; color: #c084fc; border: 1px solid #4a3b60; font-weight: bold; padding: 4px 8px;")
        btn_apply_shift.clicked.connect(self._apply_manual_shift_input)
        hbox_shifts.addWidget(btn_apply_shift)

        layout.addLayout(hbox_shifts)

        # 6. Preview area
        self.txt_cal_preview = QTextEdit()
        self.txt_cal_preview.setPlaceholderText("LRC file content will be previewed here...")
        layout.addWidget(self.txt_cal_preview)

        # 7. Action Bar: Restore Backup & Save
        hbox_save = QHBoxLayout()
        btn_restore_bak = QPushButton("RESTORE FROM BACKUP (.BAK)")
        btn_restore_bak.setStyleSheet("background-color: #2b141d; color: #ff2a85; border: 1px solid #ff2a85; font-weight: bold;")
        btn_restore_bak.setToolTip("Reverts this track's lyrics back to the untouched original .lrc.bak")
        btn_restore_bak.clicked.connect(self._restore_active_backup)
        hbox_save.addWidget(btn_restore_bak)

        hbox_save.addStretch()

        btn_save = QPushButton("SAVE CURRENT PREVIEW TO .LRC")
        btn_save.setStyleSheet("background-color: #122822; color: #00ff66; border: 1px solid #00ff66; font-weight: bold; padding: 6px 14px;")
        btn_save.clicked.connect(self._save_cal_preview)
        hbox_save.addWidget(btn_save)
        layout.addLayout(hbox_save)

        return tab

    def _browse_cal_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Audio File", self.edit_folder.text(), "Audio Files (*.mp3 *.opus *.flac *.ogg *.m4a *.wav)")
        if f:
            self.edit_cal_file.setText(os.path.normpath(f))
            self._load_cal_track(os.path.normpath(f))

    def _load_cal_track(self, audio_path: str):
        if not os.path.exists(audio_path):
            return

        self._stop_audio_playback()
        self.cal_player.setSource(QUrl.fromLocalFile(audio_path))

        # Detect vocal entry
        entry, peak, method = detect_vocal_entry(audio_path)
        self.lbl_cal_onset.setText(f"VOCAL ENTRY: {entry:.2f}s" if entry > 0 else "VOCAL ENTRY: N/A")

        lrc_path = os.path.splitext(audio_path)[0] + ".lrc"
        if os.path.exists(lrc_path):
            with open(lrc_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            self.txt_cal_preview.setText(content)

            import re
            pattern = re.compile(r'\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]')
            first_ts = None
            for line in content.splitlines():
                m = pattern.search(line)
                if m:
                    text = pattern.sub('', line).strip()
                    if len(text) >= 2 and not text.startswith(('by:', 'ar:', 'ti:', 'al:')):
                        mins = int(m.group(1))
                        secs = int(m.group(2))
                        ms = float("0." + m.group(3)) if m.group(3) else 0.0
                        first_ts = mins * 60.0 + secs + ms
                        break

            if first_ts is not None:
                self.lbl_cal_lyric.setText(f"FIRST LYRIC: {first_ts:.2f}s")
                if entry > 0:
                    diff = round(entry - first_ts, 2)
                    self.lbl_cal_diff.setText(f"DISCREPANCY: {diff:+.2f}s")
                    if abs(diff) < 1.0:
                        self.lbl_cal_status.setText("STATUS: IN SYNC")
                        self.lbl_cal_status.setStyleSheet("color: #00ff66; font-weight: bold;")
                    else:
                        self.lbl_cal_status.setText("STATUS: DESYNC DETECTED")
                        self.lbl_cal_status.setStyleSheet("color: #ffe600; font-weight: bold;")
                else:
                    self.lbl_cal_diff.setText("DISCREPANCY: --")
                    self.lbl_cal_status.setText("STATUS: VOCAL UNMASKED")
            else:
                self.lbl_cal_lyric.setText("FIRST LYRIC: N/A")
                self.lbl_cal_diff.setText("DISCREPANCY: N/A")
        else:
            self.txt_cal_preview.setText("// No companion .lrc file found for this track.\n// Click 'FETCH VERIFIED LRC' above to download exact synced lyrics.")
            self.lbl_cal_lyric.setText("FIRST LYRIC: MISSING")
            self.lbl_cal_diff.setText("DISCREPANCY: MISSING")
            self.lbl_cal_status.setText("STATUS: NO LRC")

    def _toggle_audio_playback(self):
        if self.cal_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.cal_player.pause()
            self.btn_play_pause.setText("PLAY")
            self.btn_play_pause.setStyleSheet("background-color: #1b3b44; color: #38d9d9; border: 1px solid #38d9d9; font-weight: bold;")
        else:
            self.cal_player.play()
            self.btn_play_pause.setText("PAUSE")
            self.btn_play_pause.setStyleSheet("background-color: #2b1138; color: #e879f9; border: 1px solid #c084fc; font-weight: bold;")

    def _stop_audio_playback(self):
        self.cal_player.stop()
        self.btn_play_pause.setText("PLAY")
        self.btn_play_pause.setStyleSheet("background-color: #1b3b44; color: #38d9d9; border: 1px solid #38d9d9; font-weight: bold;")

    def _on_player_pos_changed(self, pos_ms: int):
        if not self.slider_pos.isSliderDown():
            self.slider_pos.setValue(pos_ms)
        dur_ms = self.cal_player.duration()
        pos_s = pos_ms / 1000.0
        dur_s = dur_ms / 1000.0 if dur_ms > 0 else 0.0
        self.lbl_time.setText(f"{int(pos_s//60):02d}:{pos_s%60:05.2f} / {int(dur_s//60):02d}:{dur_s%60:05.2f}")

    def _on_player_dur_changed(self, dur_ms: int):
        self.slider_pos.setRange(0, dur_ms)

    def _on_slider_moved(self, pos_ms: int):
        self.cal_player.setPosition(pos_ms)

    def _tap_to_sync(self):
        pos_ms = self.cal_player.position()
        t_tapped = pos_ms / 1000.0
        if t_tapped <= 0.0:
            return

        text = self.txt_cal_preview.toPlainText()
        if not text or text.startswith("//"):
            return

        import re
        pattern = re.compile(r'\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]')
        first_ts = None
        for line in text.splitlines():
            m = pattern.search(line)
            if m:
                t_str = pattern.sub('', line).strip()
                if len(t_str) >= 2 and not t_str.startswith(('by:', 'ar:', 'ti:', 'al:')):
                    mins = int(m.group(1))
                    secs = int(m.group(2))
                    ms = float("0." + m.group(3)) if m.group(3) else 0.0
                    first_ts = mins * 60.0 + secs + ms
                    break

        if first_ts is None:
            return

        diff = round(t_tapped - first_ts, 2)
        shifted = shift_lrc_timestamps(text, diff)
        self.txt_cal_preview.setText(shifted)

        self.lbl_cal_diff.setText(f"TAPPED SHIFT: {diff:+.2f}s")
        self.lbl_cal_status.setText(f"STATUS: TAPPED AT {t_tapped:.2f}s")
        self.lbl_cal_status.setStyleSheet("color: #ffe600; font-weight: bold;")

    def keyPressEvent(self, event):
        # Spacebar triggers Tap-to-Sync if in calibrator tab
        if event.key() == Qt.Key.Key_Space:
            if hasattr(self, "btn_tap_sync") and self.cal_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self._tap_to_sync()
                event.accept()
                return
        super().keyPressEvent(event)

    def _fetch_verified_lrc(self):
        audio_path = self.edit_cal_file.text().strip()
        if not os.path.exists(audio_path):
            self.lbl_cal_status.setText("STATUS: NO FILE LOADED")
            return

        meta = extract_metadata(audio_path)
        title = meta.get("title") or ""
        artist = meta.get("artist") or ""
        duration = meta.get("duration") or 0.0

        self.lbl_cal_status.setText("STATUS: QUERYING VERIFIED LYRICS...")
        self.lbl_cal_status.setStyleSheet("color: #38d9d9; font-weight: bold;")
        QApplication.processEvents()

        lrc_text = fetch_synced_lyrics(title, artist, duration)
        if lrc_text:
            self.txt_cal_preview.setText(lrc_text)
            self.lbl_cal_status.setText("STATUS: VERIFIED LRC LOADED (EXACT DURATION)")
            self.lbl_cal_status.setStyleSheet("color: #00ff66; font-weight: bold;")
            entry, peak, method = detect_vocal_entry(audio_path)
            import re
            pattern = re.compile(r'\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]')
            first_ts = None
            for line in lrc_text.splitlines():
                m = pattern.search(line)
                if m:
                    text = pattern.sub('', line).strip()
                    if len(text) >= 2 and not text.startswith(('by:', 'ar:', 'ti:', 'al:')):
                        mins = int(m.group(1))
                        secs = int(m.group(2))
                        ms = float("0." + m.group(3)) if m.group(3) else 0.0
                        first_ts = mins * 60.0 + secs + ms
                        break
            if first_ts is not None:
                self.lbl_cal_lyric.setText(f"FIRST LYRIC: {first_ts:.2f}s")
                if entry > 0:
                    diff = round(entry - first_ts, 2)
                    self.lbl_cal_diff.setText(f"DISCREPANCY: {diff:+.2f}s")
        else:
            self.lbl_cal_status.setText("STATUS: NO VERIFIED MATCH (PREVENTED MISMATCH)")
            self.lbl_cal_status.setStyleSheet("color: #ff2a85; font-weight: bold;")

    def _shift_active_lrc(self, delta: float):
        text = self.txt_cal_preview.toPlainText()
        if not text or text.startswith("//"):
            return
        shifted = shift_lrc_timestamps(text, delta)
        self.txt_cal_preview.setText(shifted)
        self.lbl_cal_status.setText(f"STATUS: SHIFTED {delta:+.2f}s")
        self.lbl_cal_status.setStyleSheet("color: #c084fc; font-weight: bold;")

    def _apply_manual_shift_input(self):
        val_str = self.edit_manual_shift.text().strip()
        try:
            delta = float(val_str)
            self._shift_active_lrc(delta)
        except ValueError:
            pass

    def _auto_calibrate_active_file(self):
        audio_path = self.edit_cal_file.text().strip()
        if not os.path.exists(audio_path):
            return
        success, offset, msg = smart_auto_calibrate_lrc(audio_path)
        self._load_cal_track(audio_path)
        if success:
            self.lbl_cal_status.setText(f"STATUS: AUTO-CALIBRATED ({offset:+.2f}s)")
            self.lbl_cal_status.setStyleSheet("color: #00ff66; font-weight: bold;")
        else:
            self.lbl_cal_status.setText(f"STATUS: {msg}")
            self.lbl_cal_status.setStyleSheet("color: #ffe600; font-weight: bold;")

    def _restore_active_backup(self):
        audio_path = self.edit_cal_file.text().strip()
        if not audio_path:
            return
        success, msg = restore_lrc_backup(audio_path)
        if success:
            self._load_cal_track(audio_path)
            self.lbl_cal_status.setText("STATUS: BACKUP RESTORED")
            self.lbl_cal_status.setStyleSheet("color: #00ff66; font-weight: bold;")
        else:
            self.lbl_cal_status.setText(f"STATUS: {msg}")
            self.lbl_cal_status.setStyleSheet("color: #ff2a85; font-weight: bold;")

    def _save_cal_preview(self):
        audio_path = self.edit_cal_file.text().strip()
        if not audio_path:
            return
        lrc_path = os.path.splitext(audio_path)[0] + ".lrc"
        text = self.txt_cal_preview.toPlainText()
        if not text or text.startswith("//"):
            return
        try:
            # Create backup if file exists
            if os.path.exists(lrc_path):
                import shutil
                shutil.copy2(lrc_path, lrc_path + ".bak")

            with open(lrc_path, "w", encoding="utf-8") as f:
                f.write(text)
            self._load_cal_track(audio_path)
            self.lbl_cal_status.setText("STATUS: SAVED (BACKUP CREATED)")
            self.lbl_cal_status.setStyleSheet("color: #00ff66; font-weight: bold;")
        except Exception as e:
            self.lbl_cal_status.setText(f"STATUS: SAVE ERROR: {e}")
            self.lbl_cal_status.setStyleSheet("color: #ff2a85; font-weight: bold;")

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Music Library Folder", self.edit_folder.text())
        if folder:
            self.edit_folder.setText(os.path.normpath(folder))

    def _log(self, text: str):
        self.log_text.append(f"[{time.strftime('%H:%M:%S')}] {text}")

    def _start_batch_fetch(self):
        folder = self.edit_folder.text().strip()
        if not os.path.exists(folder):
            self._log(f"ERROR: Folder does not exist: {folder}")
            return

        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.btn_start.setText("FETCH ALL MISSING LYRICS")
            self._log("Process stopped by user.")
            return

        self.btn_start.setText("STOP FETCHING")
        self.progress_bar.setValue(0)
        self._log(f"Starting batch lyrics scan on: {folder}")

        self.worker = BatchFetchWorker(folder, self.chk_force.isChecked())
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_progress(self, cur: int, total: int, path: str, success: bool, msg: str):
        if total > 0:
            pct = int((cur / total) * 100)
            self.progress_bar.setValue(pct)

        status_tag = "OK" if success else "FAIL"
        fname = os.path.basename(path)
        self._log(f"[{status_tag}] {fname} -> {msg}")

    def _on_worker_finished(self, stats: dict):
        self.btn_start.setText("FETCH ALL MISSING LYRICS")
        self.progress_bar.setValue(100)
        self._log("=" * 50)
        self._log(f"BATCH FINISHED: Scanned {stats['total']} | Fetched {stats['fetched']} | Skipped {stats['skipped']} | Failed {stats['failed']}")
        self._log("=" * 50)

    def _restore_backups(self):
        folder = self.edit_folder.text().strip()
        if not os.path.exists(folder):
            return

        count = 0
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(".lrc.bak"):
                    bak_path = os.path.join(root, f)
                    orig_lrc = bak_path[:-4]  # Remove .bak
                    try:
                        shutil.copy2(bak_path, orig_lrc)
                        count += 1
                        self._log(f"[RESTORED] {os.path.basename(orig_lrc)} from backup")
                    except Exception as e:
                        self._log(f"[ERROR] Restoring {f}: {e}")
        if count == 0:
            self._log("No .lrc.bak backups found in library.")
        else:
            self._log(f"Successfully restored {count} lyric backup(s).")

    def _toggle_watcher(self, enabled: bool):
        if enabled:
            folder = self.edit_folder.text().strip()
            if not os.path.exists(folder):
                self._log(f"Cannot watch non-existent folder: {folder}")
                self.chk_watch.setChecked(False)
                return

            self.watcher_timer.start(3500)
            self.lbl_watcher_status.setText("WATCHER: ACTIVE (MONITORING)")
            self.lbl_watcher_status.setStyleSheet("color: #38d9d9; font-size: 10px; font-weight: bold;")
            self._log(f"Live folder watcher enabled on: {folder}")
        else:
            self.watcher_timer.stop()
            self.lbl_watcher_status.setText("WATCHER: IDLE")
            self.lbl_watcher_status.setStyleSheet("color: #64748b; font-size: 10px; font-weight: bold;")
            self._log("Live folder watcher stopped.")

    def _on_watcher_tick(self):
        folder = self.edit_folder.text().strip()
        if not os.path.exists(folder):
            return

        for root, _, filenames in os.walk(folder):
            for f in sorted(filenames):
                if f.lower().endswith(SUPPORTED_AUDIO_EXTS):
                    audio_full = os.path.normpath(os.path.join(root, f))
                    lrc_full = os.path.splitext(audio_full)[0] + ".lrc"

                    if not os.path.exists(lrc_full) and audio_full not in self.known_songs:
                        self.known_songs.add(audio_full)
                        self._log(f"[WATCHER] New audio detected: {f} -> Fetching lyrics...")
                        success, msg = fetch_lyrics_for_file(audio_full, force_overwrite=False)
                        tag = "OK" if success else "FAIL"
                        self._log(f"[WATCHER {tag}] {f} -> {msg}")

    def _lookup_single_song(self):
        title = self.edit_search_title.text().strip()
        artist = self.edit_search_artist.text().strip()
        if not title:
            self.txt_preview.setText("Please enter at least a song title.")
            return

        self.txt_preview.setText(f"Searching lyrics for '{title}' by '{artist}'...")
        QApplication.processEvents()

        lrc = fetch_synced_lyrics(title, artist)
        if lrc:
            self.txt_preview.setText(lrc)
        else:
            self.txt_preview.setText("No synchronized lyrics found for this song.")

    def _save_preview_lrc(self):
        content = self.txt_preview.toPlainText().strip()
        if not content or content.startswith("Searching") or content.startswith("No synchronized"):
            return

        save_path, _ = QFileDialog.getSaveFileName(self, "Save Synchronized Lyrics", "lyrics.lrc", "LRC Files (*.lrc)")
        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(content)
                self._log(f"Saved custom LRC to: {save_path}")
            except Exception as e:
                self._log(f"Failed to save custom LRC: {e}")


def main():
    app = QApplication(sys.argv)
    win = LyricsFetcherWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
