"""
Talia Lyrics Fetch Automated - Cyberpunk Interface & Calibrator
Modern dark Cyberpunk UI matching Talia's main control panel with batch sync,
non-blocking candidate search, library track switcher, vocal onset calibration,
and live synchronized playback preview.
"""

import os
import re
import shutil
import sys
import time
from typing import Optional

from PyQt6.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_BASE_DIR = (
    os.path.dirname(sys.executable)
    if getattr(sys, "frozen", False)
    else os.path.dirname(_THIS_DIR)
)
_SRC_DIR = os.path.join(_APP_BASE_DIR, "src")
for _p in (_THIS_DIR, _SRC_DIR):
    if _p and os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from fetch_lyrics import (  # noqa: E402
    SUPPORTED_AUDIO_EXTS,
    detect_vocal_entry,
    extract_metadata,
    fetch_lyrics_for_file,
    fetch_synced_lyrics,
    get_default_music_dir,
    restore_lrc_backup,
    search_all_lrc_candidates,
    shift_lrc_timestamps,
    smart_auto_calibrate_lrc,
)

try:
    from ui_widgets import CyberChamferButton, NoScrollComboBox
except Exception:
    CyberChamferButton = None
    NoScrollComboBox = QComboBox

_LRC_TS_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]")


def _parse_lrc_entries(lrc_text: str) -> list[tuple[float, str]]:
    """Parses LRC content into sorted (timestamp_sec, lyric_text) tuples."""
    entries: list[tuple[float, str]] = []
    for line in lrc_text.splitlines():
        matches = list(_LRC_TS_RE.finditer(line))
        if not matches:
            continue
        text = _LRC_TS_RE.sub("", line).strip()
        if len(text) < 1 or text.startswith(("by:", "ar:", "ti:", "al:", "offset:")):
            continue
        for m in matches:
            mins = int(m.group(1))
            secs = int(m.group(2))
            ms = float("0." + m.group(3)) if m.group(3) else 0.0
            entries.append((mins * 60.0 + secs + ms, text))
    entries.sort(key=lambda x: x[0])
    return entries


def _first_lrc_timestamp(lrc_text: str) -> Optional[float]:
    """Returns the first meaningful lyric timestamp in seconds, or None."""
    entries = _parse_lrc_entries(lrc_text)
    for ts, txt in entries:
        if len(txt) >= 2:
            return ts
    return None


def _make_cyber_btn(text: str, variant: str = "action_neutral", parent: Optional[QWidget] = None):
    """Creates a CyberChamferButton matching the main menu panel when available."""
    if CyberChamferButton is not None:
        return CyberChamferButton(text, variant=variant, parent=parent)
    btn = QPushButton(text, parent)
    if variant in ("action_cyan", "action_green"):
        btn.setObjectName("btnPrimary")
    return btn


class BatchFetchWorker(QThread):
    progress = pyqtSignal(int, int, str, bool, str)
    finished = pyqtSignal(dict)

    def __init__(self, folder: str, force: bool = False):
        super().__init__()
        self.folder = folder
        self.force = force
        self.is_cancelled = False

    def run(self):
        stats = {"total": 0, "fetched": 0, "skipped": 0, "failed": 0}
        audio_files = []
        for root, _, filenames in os.walk(self.folder):
            for f in sorted(filenames):
                if f.lower().endswith(SUPPORTED_AUDIO_EXTS):
                    audio_files.append(os.path.normpath(os.path.join(root, f)))

        stats["total"] = len(audio_files)

        for i, path in enumerate(audio_files):
            if self.is_cancelled:
                break
            success, msg = fetch_lyrics_for_file(path, force_overwrite=self.force)
            if success:
                if "already exists" in msg:
                    stats["skipped"] += 1
                else:
                    stats["fetched"] += 1
            else:
                stats["failed"] += 1

            self.progress.emit(i + 1, stats["total"], path, success, msg)
            time.sleep(0.05)

        self.finished.emit(stats)

    def cancel(self):
        self.is_cancelled = True


class CandidateSearchWorker(QThread):
    """Non-blocking online candidate lookup worker."""

    results_ready = pyqtSignal(list, str)  # candidates, fallback_lrc

    def __init__(self, title: str, artist: str = "", duration: float = 0.0, allow_fallback: bool = True):
        super().__init__()
        self.title = title
        self.artist = artist
        self.duration = duration
        self.allow_fallback = allow_fallback

    def run(self):
        cands = search_all_lrc_candidates(self.title, self.artist, self.duration)
        fallback = ""
        if not cands and self.allow_fallback:
            fallback = fetch_synced_lyrics(self.title, self.artist, self.duration) or ""
        self.results_ready.emit(cands, fallback)


class LyricsFetcherWindow(QWidget):
    lyrics_saved = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Talia Lyrics Fetcher & Calibrator")
        self.resize(800, 700)
        self.setMinimumSize(640, 560)

        self.worker: Optional[BatchFetchWorker] = None
        self._search_worker: Optional[CandidateSearchWorker] = None
        self._cal_fetch_worker: Optional[CandidateSearchWorker] = None
        self._search_candidates: list[dict] = []
        self._cal_candidates: list[dict] = []
        self._parsed_cal_entries: list[tuple[float, str]] = []

        self.watcher_timer = QTimer(self)
        self.watcher_timer.timeout.connect(self._on_watcher_tick)
        self.known_songs: set[str] = set()

        # Dedicated Media Player for audio preview & tap-to-sync
        self.cal_player = QMediaPlayer(self)
        self.cal_audio_output = QAudioOutput(self)
        self.cal_player.setAudioOutput(self.cal_audio_output)
        self.cal_player.positionChanged.connect(self._on_player_pos_changed)
        self.cal_player.durationChanged.connect(self._on_player_dur_changed)

        self._apply_styling()
        self._init_ui()
        self._populate_cal_track_list()

    def _apply_styling(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #0A0B10;
                color: #f4f4f5;
                font-family: 'Rajdhani', 'Segoe UI', Arial, sans-serif;
            }
            QLineEdit, QComboBox {
                background-color: #050508;
                color: #ff8a84;
                border: 1px solid rgba(247, 80, 73, 95);
                border-radius: 2px;
                padding: 5px 8px;
                font-size: 11px;
                font-weight: 600;
                selection-background-color: #F75049;
                selection-color: #0e0e17;
            }
            QLineEdit:focus, QComboBox:focus {
                background-color: rgba(247, 80, 73, 24);
                border: 1px solid #5EF6FF;
                color: #f4f4f5;
            }
            QComboBox::drop-down {
                border: none;
                width: 16px;
            }
            QComboBox QAbstractItemView {
                background-color: #14151f;
                color: #ff8a84;
                border: 1px solid #F75049;
                selection-background-color: #F75049;
                selection-color: #0e0e17;
                padding: 4px;
            }
            QPushButton {
                background-color: #141520;
                border: 1px solid rgba(247, 80, 73, 95);
                border-radius: 2px;
                padding: 6px 12px;
                font-weight: 600;
                font-size: 11px;
                color: #f4f4f5;
            }
            QPushButton:hover {
                border-color: #5EF6FF;
                color: #ffffff;
            }
            QPushButton#btnPrimary {
                background-color: #0c1624;
                border: 1px solid #5EF6FF;
                color: #5EF6FF;
                font-weight: 700;
            }
            QProgressBar {
                background-color: #06060b;
                border: 1px solid rgba(247, 80, 73, 120);
                border-radius: 2px;
                text-align: center;
                color: #ffffff;
                font-family: 'Consolas', monospace;
                font-size: 10px;
                font-weight: 700;
            }
            QProgressBar::chunk {
                background: #5EF6FF;
            }
            QTextEdit {
                background-color: #08090F;
                border: 1px solid rgba(247, 80, 73, 85);
                border-radius: 3px;
                color: #e4e4e7;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                padding: 8px;
            }
            QTextEdit:focus {
                border-color: #5EF6FF;
            }
            QCheckBox {
                color: #d4d4d8;
                font-size: 11px;
                font-weight: 600;
                spacing: 7px;
            }
            QCheckBox::indicator {
                width: 13px;
                height: 13px;
                background-color: #08080e;
                border: 1px solid rgba(247, 80, 73, 140);
                border-radius: 2px;
            }
            QCheckBox::indicator:checked {
                background-color: #F75049;
                border-color: #ff8a84;
            }
            QTabWidget::pane {
                border: 1px solid rgba(247, 80, 73, 110);
                background: #0D0E16;
                border-radius: 3px;
            }
            QTabBar::tab {
                background: #10111A;
                border: 1px solid rgba(247, 80, 73, 75);
                padding: 7px 18px;
                color: #a1a1aa;
                font-weight: 700;
                font-size: 11px;
                letter-spacing: 0.8px;
            }
            QTabBar::tab:selected {
                background: #161826;
                color: #5EF6FF;
                border-bottom: 2px solid #5EF6FF;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: rgba(247, 80, 73, 80);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #F75049;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ff8a84;
                border: 1px solid #ffffff;
                width: 10px;
                height: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 1px;
            }
            QSlider::handle:horizontal:hover {
                background: #5EF6FF;
            }
        """)

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Cyberpunk Top Header Banner
        banner = QFrame()
        banner.setFixedHeight(44)
        banner.setStyleSheet(
            "QFrame { background-color: #F75049; border-bottom: 2px solid #5EF6FF; }"
        )
        header_layout = QHBoxLayout(banner)
        header_layout.setContentsMargins(16, 4, 16, 4)

        vbox_title = QVBoxLayout()
        vbox_title.setSpacing(0)
        title_lbl = QLabel("TALIA LYRIC FETCHER & CALIBRATOR")
        title_lbl.setStyleSheet(
            "color: #0E0E17; font-family: 'Rajdhani', sans-serif; font-size: 16px; font-weight: 800; letter-spacing: 1.5px; background: transparent;"
        )
        vbox_title.addWidget(title_lbl)

        disclaimer_lbl = QLabel("Batch LRCLIB sync, multi-candidate lookup, vocal onset align & live tap-to-sync")
        disclaimer_lbl.setStyleSheet("color: #28080a; font-size: 10px; font-weight: 600; background: transparent;")
        vbox_title.addWidget(disclaimer_lbl)
        header_layout.addLayout(vbox_title)

        header_layout.addStretch()
        self.lbl_watcher_status = QLabel("WATCHER: IDLE")
        self.lbl_watcher_status.setStyleSheet(
            "background-color: #0E0E17; color: #a1a1aa; border: 1px solid #3f3f46; border-radius: 2px; padding: 3px 8px; font-family: 'Share Tech Mono', 'Consolas', monospace; font-size: 10px; font-weight: 700;"
        )
        header_layout.addWidget(self.lbl_watcher_status)
        root_layout.addWidget(banner)

        body = QWidget()
        main_layout = QVBoxLayout(body)
        main_layout.setContentsMargins(14, 12, 14, 14)
        main_layout.setSpacing(10)

        # Tabs: Library Sync, Search, Calibrate
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_batch_tab(), "LIBRARY SYNC")
        self.tabs.addTab(self._create_lookup_tab(), "ONLINE SEARCH")
        self.tabs.addTab(self._create_calibrator_tab(), "CALIBRATE")
        main_layout.addWidget(self.tabs)
        root_layout.addWidget(body, 1)

    def _create_batch_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        lbl_folder = QLabel("MUSIC LIBRARY FOLDER:")
        lbl_folder.setStyleSheet("color: #5EF6FF; font-weight: 800; font-size: 11px; letter-spacing: 1px;")
        layout.addWidget(lbl_folder)

        hbox_folder = QHBoxLayout()
        hbox_folder.setSpacing(6)
        self.edit_folder = QLineEdit(get_default_music_dir())
        hbox_folder.addWidget(self.edit_folder)

        btn_browse = _make_cyber_btn("BROWSE...", "action_neutral")
        btn_browse.setFixedSize(92, 28)
        btn_browse.clicked.connect(self._browse_folder)
        hbox_folder.addWidget(btn_browse)
        layout.addLayout(hbox_folder)

        hbox_opts = QHBoxLayout()
        self.chk_force = QCheckBox("Force re-fetch existing (creates .bak backup)")
        hbox_opts.addWidget(self.chk_force)

        self.chk_watch = QCheckBox("Auto-watch folder for new tracks")
        self.chk_watch.toggled.connect(self._toggle_watcher)
        hbox_opts.addWidget(self.chk_watch)
        hbox_opts.addStretch()
        layout.addLayout(hbox_opts)

        hbox_actions = QHBoxLayout()
        hbox_actions.setSpacing(8)
        self.btn_start = _make_cyber_btn("FETCH MISSING LYRICS", "action_green")
        self.btn_start.setFixedHeight(30)
        self.btn_start.clicked.connect(self._start_batch_fetch)
        hbox_actions.addWidget(self.btn_start, 2)

        btn_restore_bak = _make_cyber_btn("RESTORE BACKUPS", "action_neutral")
        btn_restore_bak.setFixedHeight(30)
        btn_restore_bak.clicked.connect(self._restore_backups)
        hbox_actions.addWidget(btn_restore_bak, 1)

        self.btn_clear_log = _make_cyber_btn("CLEAR LOG", "action_red")
        self.btn_clear_log.setFixedSize(94, 30)
        self.btn_clear_log.clicked.connect(lambda: self.log_text.clear())
        hbox_actions.addWidget(self.btn_clear_log)
        layout.addLayout(hbox_actions)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(16)
        layout.addWidget(self.progress_bar)

        lbl_log = QLabel("ACTIVITY LOG:")
        lbl_log.setStyleSheet("color: #5EF6FF; font-weight: 800; font-size: 11px; letter-spacing: 1px;")
        layout.addWidget(lbl_log)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        return tab

    def _create_lookup_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(8)

        lbl_head = QLabel("SEARCH SYNCHRONIZED LYRICS (LRCLIB CANDIDATES):")
        lbl_head.setStyleSheet("color: #5EF6FF; font-weight: 800; font-size: 11px; letter-spacing: 1px;")
        layout.addWidget(lbl_head)

        hbox_fields = QHBoxLayout()
        hbox_fields.setSpacing(6)
        self.edit_search_title = QLineEdit()
        self.edit_search_title.setPlaceholderText("Song Title (e.g. Stay At Your House)...")
        self.edit_search_title.returnPressed.connect(self._lookup_single_song)
        hbox_fields.addWidget(self.edit_search_title, 2)

        self.edit_search_artist = QLineEdit()
        self.edit_search_artist.setPlaceholderText("Artist (optional)...")
        self.edit_search_artist.returnPressed.connect(self._lookup_single_song)
        hbox_fields.addWidget(self.edit_search_artist, 1)

        self.btn_search = _make_cyber_btn("SEARCH", "action_cyan")
        self.btn_search.setFixedSize(92, 28)
        self.btn_search.clicked.connect(self._lookup_single_song)
        hbox_fields.addWidget(self.btn_search)
        layout.addLayout(hbox_fields)

        # Candidate selector row
        hbox_cand = QHBoxLayout()
        hbox_cand.setSpacing(6)
        lbl_cand = QLabel("VERSION:")
        lbl_cand.setStyleSheet("color: #a1a1aa; font-weight: 700; font-size: 10px;")
        hbox_cand.addWidget(lbl_cand)

        self.combo_search_candidates = NoScrollComboBox()
        self.combo_search_candidates.addItem("Run a search to inspect available versions...")
        self.combo_search_candidates.currentIndexChanged.connect(self._on_search_candidate_selected)
        hbox_cand.addWidget(self.combo_search_candidates, 1)

        self.lbl_search_status = QLabel("Ready")
        self.lbl_search_status.setStyleSheet("color: #a1a1aa; font-family: 'Consolas', monospace; font-size: 10px;")
        hbox_cand.addWidget(self.lbl_search_status)
        layout.addLayout(hbox_cand)

        self.txt_preview = QTextEdit()
        self.txt_preview.setPlaceholderText("Synchronized lyrics preview will appear here...")
        layout.addWidget(self.txt_preview, 1)

        hbox_save = QHBoxLayout()
        hbox_save.setSpacing(8)
        btn_apply_cal = _make_cyber_btn("SEND TO CALIBRATOR", "action_purple")
        btn_apply_cal.setFixedHeight(28)
        btn_apply_cal.setToolTip("Load this lyric text directly into the Calibrate tab for preview or saving")
        btn_apply_cal.clicked.connect(self._send_search_to_calibrator)
        hbox_save.addWidget(btn_apply_cal)

        hbox_save.addStretch()

        btn_save_preview = _make_cyber_btn("SAVE LYRICS (.LRC)", "action_green")
        btn_save_preview.setFixedSize(148, 28)
        btn_save_preview.clicked.connect(self._save_preview_lrc)
        hbox_save.addWidget(btn_save_preview)
        layout.addLayout(hbox_save)

        return tab

    def _create_calibrator_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Quick Library Track Picker Row
        hbox_lib = QHBoxLayout()
        hbox_lib.setSpacing(6)
        lbl_lib = QLabel("LIBRARY TRACK:")
        lbl_lib.setStyleSheet("color: #5EF6FF; font-weight: 800; font-size: 10px; letter-spacing: 0.8px;")
        hbox_lib.addWidget(lbl_lib)

        self.combo_cal_tracks = NoScrollComboBox()
        self.combo_cal_tracks.currentIndexChanged.connect(self._on_cal_combo_selected)
        hbox_lib.addWidget(self.combo_cal_tracks, 1)

        btn_reload_list = _make_cyber_btn("REFRESH", "action_neutral")
        btn_reload_list.setFixedSize(76, 26)
        btn_reload_list.clicked.connect(self._populate_cal_track_list)
        hbox_lib.addWidget(btn_reload_list)
        layout.addLayout(hbox_lib)

        # File Selector Row
        hbox_file = QHBoxLayout()
        hbox_file.setSpacing(6)
        self.edit_cal_file = QLineEdit()
        self.edit_cal_file.setPlaceholderText("Select audio track to calibrate...")
        hbox_file.addWidget(self.edit_cal_file)

        btn_browse_cal = _make_cyber_btn("BROWSE FILE", "action_neutral")
        btn_browse_cal.setFixedSize(104, 28)
        btn_browse_cal.clicked.connect(self._browse_cal_file)
        hbox_file.addWidget(btn_browse_cal)
        layout.addLayout(hbox_file)

        # Interactive Audio Player, Live Active Lyric & Tap-to-Sync
        player_frame = QFrame()
        player_frame.setStyleSheet(
            "QFrame { background-color: #08090F; border: 1px solid rgba(247, 80, 73, 85); border-radius: 3px; }"
        )
        vbox_player = QVBoxLayout(player_frame)
        vbox_player.setContentsMargins(8, 7, 8, 7)
        vbox_player.setSpacing(5)

        hbox_player_ctrls = QHBoxLayout()
        hbox_player_ctrls.setSpacing(5)
        self.btn_play_pause = _make_cyber_btn("PLAY", "action_cyan")
        self.btn_play_pause.setFixedSize(64, 26)
        self.btn_play_pause.clicked.connect(self._toggle_audio_playback)
        hbox_player_ctrls.addWidget(self.btn_play_pause)

        btn_stop = _make_cyber_btn("STOP", "action_neutral")
        btn_stop.setFixedSize(56, 26)
        btn_stop.clicked.connect(self._stop_audio_playback)
        hbox_player_ctrls.addWidget(btn_stop)

        btn_rew = _make_cyber_btn("-5s", "action_neutral")
        btn_rew.setFixedSize(38, 26)
        btn_rew.clicked.connect(lambda: self._jump_audio_ms(-5000))
        hbox_player_ctrls.addWidget(btn_rew)

        btn_fwd = _make_cyber_btn("+5s", "action_neutral")
        btn_fwd.setFixedSize(38, 26)
        btn_fwd.clicked.connect(lambda: self._jump_audio_ms(5000))
        hbox_player_ctrls.addWidget(btn_fwd)

        self.slider_pos = QSlider(Qt.Orientation.Horizontal)
        self.slider_pos.sliderMoved.connect(self._on_slider_moved)
        hbox_player_ctrls.addWidget(self.slider_pos, 1)

        self.lbl_time = QLabel("00:00.00 / 00:00.00")
        self.lbl_time.setStyleSheet(
            "color: #5EF6FF; font-family: 'Consolas', monospace; font-size: 11px; min-width: 122px; border: none; background: transparent;"
        )
        hbox_player_ctrls.addWidget(self.lbl_time)

        self.btn_tap_sync = _make_cyber_btn("TAP SYNC [SPACE]", "action_purple")
        self.btn_tap_sync.setFixedSize(124, 26)
        self.btn_tap_sync.setToolTip("Play the song and press Spacebar right when the first vocal enters.")
        self.btn_tap_sync.clicked.connect(self._tap_to_sync)
        hbox_player_ctrls.addWidget(self.btn_tap_sync)

        vbox_player.addLayout(hbox_player_ctrls)

        self.lbl_live_lyric = QLabel("Now singing: (press Play to preview live subtitle sync)")
        self.lbl_live_lyric.setStyleSheet(
            "color: #ff8a84; font-family: 'Rajdhani', sans-serif; font-size: 12px; font-weight: 700; border: none; background: transparent;"
        )
        vbox_player.addWidget(self.lbl_live_lyric)

        layout.addWidget(player_frame)

        # Telemetry Display Box
        telemetry_frame = QFrame()
        telemetry_frame.setStyleSheet(
            "QFrame { background-color: #08090F; border: 1px solid rgba(94, 246, 255, 65); border-radius: 3px; }"
        )
        hbox_tele = QHBoxLayout(telemetry_frame)
        hbox_tele.setContentsMargins(8, 5, 8, 5)

        self.lbl_cal_onset = QLabel("Vocal entry: --")
        self.lbl_cal_onset.setStyleSheet("color: #f4f4f5; font-family: 'Share Tech Mono', 'Consolas', monospace; font-size: 11px; border: none; background: transparent;")
        hbox_tele.addWidget(self.lbl_cal_onset)

        self.lbl_cal_lyric = QLabel("First lyric: --")
        self.lbl_cal_lyric.setStyleSheet("color: #f4f4f5; font-family: 'Share Tech Mono', 'Consolas', monospace; font-size: 11px; border: none; background: transparent;")
        hbox_tele.addWidget(self.lbl_cal_lyric)

        self.lbl_cal_diff = QLabel("Offset: --")
        self.lbl_cal_diff.setStyleSheet("color: #f4f4f5; font-family: 'Share Tech Mono', 'Consolas', monospace; font-size: 11px; border: none; background: transparent;")
        hbox_tele.addWidget(self.lbl_cal_diff)

        self.lbl_cal_status = QLabel("Status: Ready")
        self.lbl_cal_status.setStyleSheet("color: #5EF6FF; font-family: 'Share Tech Mono', 'Consolas', monospace; font-size: 11px; border: none; background: transparent;")
        hbox_tele.addWidget(self.lbl_cal_status)
        layout.addWidget(telemetry_frame)

        # Lyrics Fetch, Candidates & Vocal Auto-Calibrate Row
        hbox_cands = QHBoxLayout()
        hbox_cands.setSpacing(6)
        self.btn_fetch_verified = _make_cyber_btn("FETCH VERIFIED (.LRC)", "action_cyan")
        self.btn_fetch_verified.setFixedSize(156, 28)
        self.btn_fetch_verified.setToolTip("Searches duration-scored candidates asynchronously")
        self.btn_fetch_verified.clicked.connect(self._fetch_verified_lrc)
        hbox_cands.addWidget(self.btn_fetch_verified)

        self.combo_cal_candidates = NoScrollComboBox()
        self.combo_cal_candidates.addItem("Online candidates will appear here...")
        self.combo_cal_candidates.currentIndexChanged.connect(self._on_cal_candidate_selected)
        hbox_cands.addWidget(self.combo_cal_candidates, 1)

        btn_auto_cal = _make_cyber_btn("AUTO-CALIBRATE", "action_purple")
        btn_auto_cal.setFixedSize(124, 28)
        btn_auto_cal.setToolTip("Align LRC timestamps using bandpass vocal onset detection")
        btn_auto_cal.clicked.connect(self._auto_calibrate_active_file)
        hbox_cands.addWidget(btn_auto_cal)
        layout.addLayout(hbox_cands)

        # Quick Offset Tuning Buttons + Direct Offset Input
        hbox_shifts = QHBoxLayout()
        hbox_shifts.setSpacing(4)
        for delta in (-1.0, -0.5, -0.1, 0.1, 0.5, 1.0):
            sign = "+" if delta > 0 else ""
            btn = _make_cyber_btn(f"{sign}{delta}s", "action_neutral")
            btn.setFixedSize(50, 26)
            btn.clicked.connect(lambda _, d=delta: self._shift_active_lrc(d))
            hbox_shifts.addWidget(btn)

        lbl_manual_shift = QLabel("SHIFT:")
        lbl_manual_shift.setStyleSheet("color: #a1a1aa; font-weight: 700; font-size: 10px;")
        hbox_shifts.addWidget(lbl_manual_shift)

        self.edit_manual_shift = QLineEdit()
        self.edit_manual_shift.setPlaceholderText("+/-sec (e.g. -0.5)")
        self.edit_manual_shift.setMaximumWidth(110)
        self.edit_manual_shift.returnPressed.connect(self._apply_manual_shift_input)
        hbox_shifts.addWidget(self.edit_manual_shift)

        btn_apply_shift = _make_cyber_btn("APPLY", "action_cyan")
        btn_apply_shift.setFixedSize(62, 26)
        btn_apply_shift.clicked.connect(self._apply_manual_shift_input)
        hbox_shifts.addWidget(btn_apply_shift)

        layout.addLayout(hbox_shifts)

        # Preview area
        self.txt_cal_preview = QTextEdit()
        self.txt_cal_preview.setPlaceholderText("Lyrics content preview...")
        self.txt_cal_preview.textChanged.connect(self._refresh_parsed_cal_entries)
        layout.addWidget(self.txt_cal_preview, 1)

        # Action Bar: Restore Backup & Save
        hbox_save = QHBoxLayout()
        btn_restore_bak = _make_cyber_btn("RESTORE BACKUP (.BAK)", "action_neutral")
        btn_restore_bak.setFixedSize(166, 28)
        btn_restore_bak.setToolTip("Reverts lyrics back to original .bak")
        btn_restore_bak.clicked.connect(self._restore_active_backup)
        hbox_save.addWidget(btn_restore_bak)

        hbox_save.addStretch()

        btn_save = _make_cyber_btn("SAVE LYRICS (.LRC)", "action_green")
        btn_save.setFixedSize(148, 28)
        btn_save.clicked.connect(self._save_cal_preview)
        hbox_save.addWidget(btn_save)
        layout.addLayout(hbox_save)

        return tab

    def _populate_cal_track_list(self):
        if not hasattr(self, "combo_cal_tracks"):
            return
        self.combo_cal_tracks.blockSignals(True)
        self.combo_cal_tracks.clear()
        folder = self.edit_folder.text().strip() if hasattr(self, "edit_folder") else get_default_music_dir()
        items: list[tuple[str, str]] = []
        if folder and os.path.isdir(folder):
            for root, _, files in os.walk(folder):
                for f in sorted(files):
                    if f.lower().endswith(SUPPORTED_AUDIO_EXTS):
                        full = os.path.normpath(os.path.join(root, f))
                        has_lrc = os.path.exists(os.path.splitext(full)[0] + ".lrc")
                        tag = "[LRC]" if has_lrc else "[MISSING]"
                        items.append((f"{tag} {f}", full))
        self.combo_cal_tracks.addItem("Select a library track...", "")
        for label, full in items[:400]:
            self.combo_cal_tracks.addItem(label, full)
        self.combo_cal_tracks.blockSignals(False)

    def _on_cal_combo_selected(self, idx: int):
        path = self.combo_cal_tracks.itemData(idx)
        if path and os.path.exists(path):
            self.edit_cal_file.setText(path)
            self._load_cal_track(path)

    def _browse_cal_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio File",
            self.edit_folder.text(),
            "Audio Files (*.mp3 *.opus *.flac *.ogg *.m4a *.wav)",
        )
        if f:
            norm = os.path.normpath(f)
            self.edit_cal_file.setText(norm)
            self._load_cal_track(norm)

    def _refresh_parsed_cal_entries(self):
        self._parsed_cal_entries = _parse_lrc_entries(self.txt_cal_preview.toPlainText())

    def _load_cal_track(self, audio_path: str):
        if not os.path.exists(audio_path):
            return

        self._stop_audio_playback()
        self.cal_player.setSource(QUrl.fromLocalFile(audio_path))
        self.lbl_live_lyric.setText("Now singing: (press Play to preview live subtitle sync)")

        entry, _peak, _method = detect_vocal_entry(audio_path)
        self.lbl_cal_onset.setText(f"Vocal entry: {entry:.2f}s" if entry > 0 else "Vocal entry: N/A")

        lrc_path = os.path.splitext(audio_path)[0] + ".lrc"
        if not os.path.exists(lrc_path):
            base_name = os.path.splitext(os.path.basename(audio_path))[0]
            cache_dir = os.path.join(_APP_BASE_DIR, "assets", "lyrics_cache")
            candidate = os.path.join(cache_dir, base_name + ".lrc")
            if os.path.exists(candidate):
                lrc_path = candidate

        if os.path.exists(lrc_path):
            with open(lrc_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            self.txt_cal_preview.setText(content)
            first_ts = _first_lrc_timestamp(content)

            if first_ts is not None:
                self.lbl_cal_lyric.setText(f"First lyric: {first_ts:.2f}s")
                if entry > 0:
                    diff = round(entry - first_ts, 2)
                    self.lbl_cal_diff.setText(f"Offset: {diff:+.2f}s")
                    if abs(diff) < 1.0:
                        self.lbl_cal_status.setText("Status: In Sync")
                        self.lbl_cal_status.setStyleSheet("color: #4ade80; font-family: 'Consolas', monospace; font-size: 11px;")
                    else:
                        self.lbl_cal_status.setText("Status: Desync Detected")
                        self.lbl_cal_status.setStyleSheet("color: #fde047; font-family: 'Consolas', monospace; font-size: 11px;")
                else:
                    self.lbl_cal_diff.setText("Offset: --")
                    self.lbl_cal_status.setText("Status: Vocal unmasked")
                    self.lbl_cal_status.setStyleSheet("color: #5EF6FF; font-family: 'Consolas', monospace; font-size: 11px;")
            else:
                self.lbl_cal_lyric.setText("First lyric: N/A")
                self.lbl_cal_diff.setText("Offset: N/A")
        else:
            self.txt_cal_preview.setText(
                "No companion .lrc file found for this track.\n"
                "Click 'FETCH VERIFIED (.LRC)' above to search online synced candidates."
            )
            self.lbl_cal_lyric.setText("First lyric: Missing")
            self.lbl_cal_diff.setText("Offset: Missing")
            self.lbl_cal_status.setText("Status: No LRC")
            self.lbl_cal_status.setStyleSheet("color: #f87171; font-family: 'Consolas', monospace; font-size: 11px;")

    def _toggle_audio_playback(self):
        if self.cal_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.cal_player.pause()
            self.btn_play_pause.setText("PLAY")
        else:
            self.cal_player.play()
            self.btn_play_pause.setText("PAUSE")

    def _stop_audio_playback(self):
        self.cal_player.stop()
        self.btn_play_pause.setText("PLAY")

    def _jump_audio_ms(self, delta_ms: int):
        dur = max(0, self.cal_player.duration())
        pos = self.cal_player.position()
        target = max(0, min(dur if dur > 0 else pos + abs(delta_ms), pos + delta_ms))
        self.cal_player.setPosition(target)

    def _on_player_pos_changed(self, pos_ms: int):
        if not self.slider_pos.isSliderDown():
            self.slider_pos.setValue(pos_ms)
        dur_ms = self.cal_player.duration()
        pos_s = pos_ms / 1000.0
        dur_s = dur_ms / 1000.0 if dur_ms > 0 else 0.0
        self.lbl_time.setText(f"{int(pos_s // 60):02d}:{pos_s % 60:05.2f} / {int(dur_s // 60):02d}:{dur_s % 60:05.2f}")

        if self._parsed_cal_entries:
            active_line = ""
            for ts, txt in self._parsed_cal_entries:
                if ts <= pos_s:
                    active_line = txt
                else:
                    break
            if active_line:
                self.lbl_live_lyric.setText(f"Now singing: {active_line}")

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
        if not text or text.startswith("//") or text.startswith("No companion"):
            return

        first_ts = _first_lrc_timestamp(text)
        if first_ts is None:
            return

        diff = round(t_tapped - first_ts, 2)
        shifted = shift_lrc_timestamps(text, diff)
        self.txt_cal_preview.setText(shifted)

        self.lbl_cal_diff.setText(f"Offset: {diff:+.2f}s")
        self.lbl_cal_status.setText(f"Status: Tapped at {t_tapped:.2f}s")
        self.lbl_cal_status.setStyleSheet("color: #4ade80; font-family: 'Consolas', monospace; font-size: 11px;")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            if hasattr(self, "btn_tap_sync") and self.cal_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self._tap_to_sync()
                event.accept()
                return
        super().keyPressEvent(event)

    def _fetch_verified_lrc(self):
        audio_path = self.edit_cal_file.text().strip()
        if not os.path.exists(audio_path):
            self.lbl_cal_status.setText("Status: No file loaded")
            return
        if self._cal_fetch_worker and self._cal_fetch_worker.isRunning():
            return

        meta = extract_metadata(audio_path)
        title = meta.get("title") or ""
        artist = meta.get("artist") or ""
        duration = meta.get("duration") or 0.0

        self.btn_fetch_verified.setEnabled(False)
        self.lbl_cal_status.setText("Status: Searching candidates...")
        self.lbl_cal_status.setStyleSheet("color: #5EF6FF; font-family: 'Consolas', monospace; font-size: 11px;")

        self._cal_fetch_worker = CandidateSearchWorker(title, artist, duration, allow_fallback=True)
        self._cal_fetch_worker.results_ready.connect(
            lambda cands, fb, ap=audio_path: self._on_cal_candidates_ready(ap, cands, fb)
        )
        self._cal_fetch_worker.start()

    def _on_cal_candidates_ready(self, audio_path: str, candidates: list, fallback_lrc: str):
        self.btn_fetch_verified.setEnabled(True)
        self._cal_candidates = list(candidates)
        self.combo_cal_candidates.blockSignals(True)
        self.combo_cal_candidates.clear()

        if candidates:
            for c in candidates:
                tag = "MATCH" if c.get("is_match") else f"{c.get('duration_diff', 0):.1f}s diff"
                dur = c.get("duration", 0.0)
                dur_str = f"{int(dur // 60):02d}:{int(dur % 60):02d}" if dur > 0 else "--:--"
                label = f"[{tag}] {c.get('track')} - {c.get('artist')} ({dur_str}, {c.get('line_count')} lines)"
                self.combo_cal_candidates.addItem(label)
            self.combo_cal_candidates.blockSignals(False)
            self._apply_cal_lrc_text(audio_path, candidates[0].get("synced", ""), f"{len(candidates)} candidates found")
        elif fallback_lrc:
            self.combo_cal_candidates.addItem("Provider fallback match")
            self.combo_cal_candidates.blockSignals(False)
            self._apply_cal_lrc_text(audio_path, fallback_lrc, "Verified fallback loaded")
        else:
            self.combo_cal_candidates.addItem("No synced candidates found")
            self.combo_cal_candidates.blockSignals(False)
            self.lbl_cal_status.setText("Status: No verified match found")
            self.lbl_cal_status.setStyleSheet("color: #f87171; font-family: 'Consolas', monospace; font-size: 11px;")

    def _on_cal_candidate_selected(self, idx: int):
        if 0 <= idx < len(self._cal_candidates):
            audio_path = self.edit_cal_file.text().strip()
            self._apply_cal_lrc_text(
                audio_path,
                self._cal_candidates[idx].get("synced", ""),
                f"Candidate #{idx + 1} loaded",
            )

    def _apply_cal_lrc_text(self, audio_path: str, lrc_text: str, status_msg: str):
        self.txt_cal_preview.setText(lrc_text)
        self.lbl_cal_status.setText(f"Status: {status_msg}")
        self.lbl_cal_status.setStyleSheet("color: #4ade80; font-family: 'Consolas', monospace; font-size: 11px;")
        entry, _, _ = detect_vocal_entry(audio_path) if audio_path and os.path.exists(audio_path) else (0.0, 0.0, "")
        first_ts = _first_lrc_timestamp(lrc_text)
        if first_ts is not None:
            self.lbl_cal_lyric.setText(f"First lyric: {first_ts:.2f}s")
            if entry > 0:
                diff = round(entry - first_ts, 2)
                self.lbl_cal_diff.setText(f"Offset: {diff:+.2f}s")

    def _shift_active_lrc(self, delta: float):
        text = self.txt_cal_preview.toPlainText()
        if not text or text.startswith("//") or text.startswith("No companion"):
            return
        shifted = shift_lrc_timestamps(text, delta)
        self.txt_cal_preview.setText(shifted)
        self.lbl_cal_status.setText(f"Status: Shifted {delta:+.2f}s")
        self.lbl_cal_status.setStyleSheet("color: #5EF6FF; font-family: 'Consolas', monospace; font-size: 11px;")

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
            self.lbl_cal_status.setText(f"Status: Auto-calibrated ({offset:+.2f}s)")
            self.lbl_cal_status.setStyleSheet("color: #4ade80; font-family: 'Consolas', monospace; font-size: 11px;")
            lrc_path = os.path.splitext(audio_path)[0] + ".lrc"
            if os.path.exists(lrc_path):
                self.lyrics_saved.emit(os.path.normpath(lrc_path))
        else:
            self.lbl_cal_status.setText(f"Status: {msg}")
            self.lbl_cal_status.setStyleSheet("color: #fde047; font-family: 'Consolas', monospace; font-size: 11px;")

    def _restore_active_backup(self):
        audio_path = self.edit_cal_file.text().strip()
        if not audio_path:
            return
        success, msg = restore_lrc_backup(audio_path)
        if success:
            self._load_cal_track(audio_path)
            self.lbl_cal_status.setText("Status: Backup restored")
            self.lbl_cal_status.setStyleSheet("color: #4ade80; font-family: 'Consolas', monospace; font-size: 11px;")
            lrc_path = os.path.splitext(audio_path)[0] + ".lrc"
            if os.path.exists(lrc_path):
                self.lyrics_saved.emit(os.path.normpath(lrc_path))
        else:
            self.lbl_cal_status.setText(f"Status: {msg}")
            self.lbl_cal_status.setStyleSheet("color: #f87171; font-family: 'Consolas', monospace; font-size: 11px;")

    def _save_cal_preview(self):
        audio_path = self.edit_cal_file.text().strip()
        if not audio_path:
            return
        lrc_path = os.path.splitext(audio_path)[0] + ".lrc"
        text = self.txt_cal_preview.toPlainText()
        if not text or text.startswith("//") or text.startswith("No companion"):
            return
        try:
            if os.path.exists(lrc_path):
                shutil.copy2(lrc_path, lrc_path + ".bak")

            with open(lrc_path, "w", encoding="utf-8") as f:
                f.write(text)
            self._load_cal_track(audio_path)
            self._populate_cal_track_list()
            self.lbl_cal_status.setText("Status: Saved (backup created)")
            self.lbl_cal_status.setStyleSheet("color: #4ade80; font-family: 'Consolas', monospace; font-size: 11px;")
            self.lyrics_saved.emit(os.path.normpath(lrc_path))
        except Exception as e:
            self.lbl_cal_status.setText(f"Status: Save error: {e}")
            self.lbl_cal_status.setStyleSheet("color: #f87171; font-family: 'Consolas', monospace; font-size: 11px;")

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Music Library Folder", self.edit_folder.text())
        if folder:
            self.edit_folder.setText(os.path.normpath(folder))
            self._populate_cal_track_list()

    def _log(self, text: str):
        self.log_text.append(f"[{time.strftime('%H:%M:%S')}] {text}")

    def _start_batch_fetch(self):
        folder = self.edit_folder.text().strip()
        if not os.path.exists(folder):
            self._log(f"ERROR: Folder does not exist: {folder}")
            return

        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.btn_start.setText("FETCH MISSING LYRICS")
            if hasattr(self.btn_start, "set_variant"):
                self.btn_start.set_variant("action_green")
            self._log("Process stopped by user.")
            return

        self.btn_start.setText("STOP FETCHING")
        if hasattr(self.btn_start, "set_variant"):
            self.btn_start.set_variant("action_red")
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
        self.btn_start.setText("FETCH MISSING LYRICS")
        if hasattr(self.btn_start, "set_variant"):
            self.btn_start.set_variant("action_green")
        self.progress_bar.setValue(100)
        self._populate_cal_track_list()
        self._log("-" * 45)
        self._log(f"Finished: Total {stats['total']} | Fetched {stats['fetched']} | Skipped {stats['skipped']} | Failed {stats['failed']}")
        self._log("-" * 45)

    def _restore_backups(self):
        folder = self.edit_folder.text().strip()
        if not os.path.exists(folder):
            return

        count = 0
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(".lrc.bak"):
                    bak_path = os.path.join(root, f)
                    orig_lrc = bak_path[:-4]
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
            self.lbl_watcher_status.setText("WATCHER: ACTIVE")
            self.lbl_watcher_status.setStyleSheet(
                "background-color: #052e16; color: #4ade80; border: 1px solid #22c55e; border-radius: 2px; padding: 3px 8px; font-family: 'Consolas', monospace; font-size: 10px; font-weight: 700;"
            )
            self._log(f"Live folder watcher enabled on: {folder}")
        else:
            self.watcher_timer.stop()
            self.lbl_watcher_status.setText("WATCHER: IDLE")
            self.lbl_watcher_status.setStyleSheet(
                "background-color: #0E0E17; color: #a1a1aa; border: 1px solid #3f3f46; border-radius: 2px; padding: 3px 8px; font-family: 'Consolas', monospace; font-size: 10px; font-weight: 700;"
            )
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
        if self._search_worker and self._search_worker.isRunning():
            return

        self.btn_search.setEnabled(False)
        self.lbl_search_status.setText("Searching...")
        self.txt_preview.setText(f"Searching lyrics for '{title}' by '{artist}'...")

        self._search_worker = CandidateSearchWorker(title, artist, 0.0, allow_fallback=True)
        self._search_worker.results_ready.connect(self._on_search_results_ready)
        self._search_worker.start()

    def _on_search_results_ready(self, candidates: list, fallback_lrc: str):
        self.btn_search.setEnabled(True)
        self._search_candidates = list(candidates)
        self.combo_search_candidates.blockSignals(True)
        self.combo_search_candidates.clear()

        if candidates:
            for c in candidates:
                dur = c.get("duration", 0.0)
                dur_str = f"{int(dur // 60):02d}:{int(dur % 60):02d}" if dur > 0 else "--:--"
                album = f" | {c.get('album')}" if c.get("album") else ""
                label = f"{c.get('track')} - {c.get('artist')}{album} ({dur_str}, {c.get('line_count')} lines)"
                self.combo_search_candidates.addItem(label)
            self.combo_search_candidates.blockSignals(False)
            self.lbl_search_status.setText(f"{len(candidates)} versions found")
            self.txt_preview.setText(candidates[0].get("synced", ""))
        elif fallback_lrc:
            self.combo_search_candidates.addItem("Provider match")
            self.combo_search_candidates.blockSignals(False)
            self.lbl_search_status.setText("1 match found")
            self.txt_preview.setText(fallback_lrc)
        else:
            self.combo_search_candidates.addItem("No candidates found")
            self.combo_search_candidates.blockSignals(False)
            self.lbl_search_status.setText("0 matches")
            self.txt_preview.setText("No synchronized lyrics found for this song.")

    def _on_search_candidate_selected(self, idx: int):
        if 0 <= idx < len(self._search_candidates):
            self.txt_preview.setText(self._search_candidates[idx].get("synced", ""))

    def _send_search_to_calibrator(self):
        content = self.txt_preview.toPlainText().strip()
        if not content or content.startswith(("Searching", "No synchronized")):
            return
        self.txt_cal_preview.setText(content)
        self.tabs.setCurrentIndex(2)
        self.lbl_cal_status.setText("Status: Loaded from search preview")

    def _save_preview_lrc(self):
        content = self.txt_preview.toPlainText().strip()
        if not content or content.startswith(("Searching", "No synchronized")):
            return

        save_path, _ = QFileDialog.getSaveFileName(self, "Save Synchronized Lyrics", "lyrics.lrc", "LRC Files (*.lrc)")
        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(content)
                self._log(f"Saved custom LRC to: {save_path}")
                self.lyrics_saved.emit(os.path.normpath(save_path))
            except Exception as e:
                self._log(f"Failed to save custom LRC: {e}")


def main():
    app = QApplication(sys.argv)
    win = LyricsFetcherWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
