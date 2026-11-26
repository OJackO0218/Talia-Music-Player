"""Integrated in-app Lyrics & Calibration Studio for Talia.

Directly wired to Talia's live audio_engine and lyrics_overlay so users can
search synced lyrics, calibrate timing visually with clicks or Spacebar,
auto-align vocals, and batch-sync their music folder without leaving Talia.
"""

import os
import re
import shutil
import sys
import time
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import ICON_PATH, PROJECT_ROOT, trim_process_memory
from ui_theme import CLEAN_UTILITY_QSS
from ui_widgets import CyberCard, DraggableClampedDialogMixin, NoScrollComboBox

if TYPE_CHECKING:
    from controller import ControlPanel

_FETCHER_DIR = os.path.join(PROJECT_ROOT, "Talia Lyrics Fetch Automated")
if _FETCHER_DIR not in sys.path and os.path.isdir(_FETCHER_DIR):
    sys.path.insert(0, _FETCHER_DIR)

from fetch_lyrics import (  # noqa: E402
    SUPPORTED_AUDIO_EXTS,
    detect_vocal_entry,
    extract_metadata,
    fetch_lyrics_for_file,
    fetch_synced_lyrics,
    restore_lrc_backup,
    search_all_lrc_candidates,
    shift_lrc_timestamps,
)

_LRC_TS_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]")
_OFFSET_TAG_RE = re.compile(r"^\[offset:.*?\]\r?\n?", flags=re.I | re.M)


def _fmt_mmss(seconds: float) -> str:
    sec = max(0.0, float(seconds))
    m = int(sec // 60)
    s = int(sec % 60)
    return f"{m:02d}:{s:02d}"


def _fmt_lrc_ts(seconds: float) -> str:
    sec = max(0.0, float(seconds))
    m = int(sec // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100.0))
    if cs >= 100:
        s += 1
        cs = 0
    if s >= 60:
        m += 1
        s -= 60
    return f"[{m:02d}:{s:02d}.{cs:02d}]"


def _parse_lrc_lines(lrc_text: str) -> list[dict]:
    """Parse LRC lines preserving raw line index for targeted single-line re-timing."""
    entries: list[dict] = []
    raw_lines = lrc_text.splitlines()
    for line_idx, raw in enumerate(raw_lines):
        matches = list(_LRC_TS_RE.finditer(raw))
        if not matches:
            continue
        text = _LRC_TS_RE.sub("", raw).strip()
        if not text or text.lower().startswith(("by:", "ar:", "ti:", "al:", "offset:", "re:", "ve:")):
            continue
        first_m = matches[0]
        mins = int(first_m.group(1))
        secs = int(first_m.group(2))
        ms = float("0." + first_m.group(3)) if first_m.group(3) else 0.0
        entries.append(
            {
                "time": mins * 60.0 + secs + ms,
                "text": text,
                "line_idx": line_idx,
            }
        )
    entries.sort(key=lambda item: item["time"])
    return entries


def _clean_btn(text: str, role: str = "default", height: int = 30, tooltip: str = "") -> QPushButton:
    btn = QPushButton(text)
    if role != "default":
        btn.setProperty("role", role)
    if height > 0:
        btn.setFixedHeight(height)
    if tooltip:
        btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


class CandidateSearchWorker(QThread):
    """Non-blocking LRCLIB / multi-provider search worker."""

    results_ready = pyqtSignal(list, str)

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


class VocalDetectWorker(QThread):
    """Background worker for vocal onset auto-alignment."""

    detected = pyqtSignal(float)  # vocal timestamp or -1.0

    def __init__(self, audio_path: str):
        super().__init__()
        self.audio_path = audio_path

    def run(self):
        try:
            pos = detect_vocal_entry(self.audio_path)
            self.detected.emit(float(pos) if pos is not None else -1.0)
        except Exception:
            self.detected.emit(-1.0)


class BatchFetchWorker(QThread):
    """Background folder scanner for missing .lrc files."""

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
            for fname in sorted(filenames):
                if fname.lower().endswith(SUPPORTED_AUDIO_EXTS):
                    audio_files.append(os.path.normpath(os.path.join(root, fname)))

        stats["total"] = len(audio_files)
        for idx, path in enumerate(audio_files):
            if self.is_cancelled:
                break
            ok, msg = fetch_lyrics_for_file(path, force_overwrite=self.force)
            if ok:
                if "already exists" in msg:
                    stats["skipped"] += 1
                else:
                    stats["fetched"] += 1
            else:
                stats["failed"] += 1
            self.progress.emit(idx + 1, stats["total"], path, ok, msg)
            time.sleep(0.03)

        self.finished.emit(stats)

    def cancel(self):
        self.is_cancelled = True


class LyricsStudioDialog(DraggableClampedDialogMixin, QDialog):
    """Unified in-app Lyrics Search, Visual Timing Calibrator, and Folder Auto-Sync Studio."""

    lyrics_saved = pyqtSignal(str)

    def __init__(self, panel: "ControlPanel"):
        super().__init__()
        self.panel = panel
        self.setWindowTitle("Lyrics & Calibration Studio")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumSize(760, 620)
        self.resize(800, 680)
        self.setStyleSheet(CLEAN_UTILITY_QSS)

        self._current_track_path: str = ""
        self._lrc_text_buffer: str = ""
        self._parsed_entries: list[dict] = []
        self._has_unsaved_changes: bool = False
        self._is_scrubbing: bool = False
        self._last_active_idx: int = -1
        self._search_candidates: list[dict] = []

        self._search_worker: Optional[CandidateSearchWorker] = None
        self._cal_search_worker: Optional[CandidateSearchWorker] = None
        self._vocal_worker: Optional[VocalDetectWorker] = None
        self._batch_worker: Optional[BatchFetchWorker] = None

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(100)
        self._sync_timer.timeout.connect(self._on_playback_tick)

        self._init_ui()
        self.refresh_track_list()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Clean Header Bar
        header = QFrame()
        header.setStyleSheet("QFrame { background-color: #17171c; border-bottom: 1px solid #272730; }")
        hbox_hdr = QHBoxLayout(header)
        hbox_hdr.setContentsMargins(18, 12, 16, 12)
        hbox_hdr.setSpacing(10)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        lbl_title = QLabel("Lyrics & Calibration Studio")
        lbl_title.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: 700;")
        title_col.addWidget(lbl_title)

        lbl_sub = QLabel(
            "Directly synced with Talia's playback. Double-click any line to hear it, or press Space to align."
        )
        lbl_sub.setStyleSheet("color: #8e8ea0; font-size: 11px;")
        title_col.addWidget(lbl_sub)
        hbox_hdr.addLayout(title_col, 1)

        self.lbl_dirty_badge = QLabel("Saved")
        self.lbl_dirty_badge.setStyleSheet(
            "background-color: #1d2722; color: #6ee7b7; border: 1px solid #284b3a; "
            "border-radius: 5px; padding: 3px 9px; font-size: 11px; font-weight: 600;"
        )
        hbox_hdr.addWidget(self.lbl_dirty_badge)

        root.addWidget(header)

        # Tabs (0 = Calibrate, 1 = Search Online, 2 = Auto-Sync Folder)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.tab_calibrate = QWidget()
        self.tab_search = QWidget()
        self.tab_sync = QWidget()

        self._build_calibrate_tab()
        self._build_search_tab()
        self._build_sync_tab()

        self.tabs.addTab(self.tab_calibrate, "Calibrate Timing")
        self.tabs.addTab(self.tab_search, "Search Online")
        self.tabs.addTab(self.tab_sync, "Folder Auto-Sync")
        root.addWidget(self.tabs, 1)

        # Spacebar shortcut to align selected line cleanly when Calibrate tab is open
        self._shortcut_space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._shortcut_space.activated.connect(self._on_space_align_shortcut)

    # -----------------------------------------------------------------
    # TAB 0: INTERACTIVE CALIBRATOR (Directly Bound to AudioEngine)
    # -----------------------------------------------------------------
    def _build_calibrate_tab(self):
        layout = QVBoxLayout(self.tab_calibrate)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        # Track Selection Card
        track_card = CyberCard("Track Selection")
        track_card.layout_content.setContentsMargins(12, 10, 12, 12)
        track_card.layout_content.setSpacing(8)

        hbox_trk = QHBoxLayout()
        hbox_trk.setSpacing(8)
        self.combo_tracks = NoScrollComboBox()
        self.combo_tracks.currentIndexChanged.connect(self._on_combo_track_selected)
        hbox_trk.addWidget(self.combo_tracks, 1)

        btn_playing = _clean_btn(
            "Sync Playing",
            height=29,
            tooltip="Load whichever song Talia is currently playing",
        )
        btn_playing.clicked.connect(self.load_currently_playing)
        hbox_trk.addWidget(btn_playing)

        btn_browse = _clean_btn("Browse File...", height=29)
        btn_browse.clicked.connect(self._browse_cal_audio)
        hbox_trk.addWidget(btn_browse)

        btn_quick_fetch = _clean_btn(
            "Fetch Online",
            role="primary",
            height=29,
            tooltip="Search online lyrics for this song and load into Calibrate",
        )
        btn_quick_fetch.clicked.connect(self._quick_fetch_for_cal_track)
        hbox_trk.addWidget(btn_quick_fetch)
        track_card.layout_content.addLayout(hbox_trk)

        # Keep hidden-compatible path line edit synced for callers/scripts
        self.edit_cal_file = QLineEdit()
        self.edit_cal_file.setReadOnly(True)
        self.edit_cal_file.setPlaceholderText("No audio file loaded...")
        self.edit_cal_file.setStyleSheet("color: #9ca3af; font-family: 'Consolas', monospace; font-size: 11px;")
        track_card.layout_content.addWidget(self.edit_cal_file)

        layout.addWidget(track_card)

        # Live Playback Card (Controlled via Talia's AudioEngine)
        player_card = CyberCard("Live Playback")
        player_card.layout_content.setContentsMargins(12, 10, 12, 12)
        player_card.layout_content.setSpacing(8)

        hbox_ctrl = QHBoxLayout()
        hbox_ctrl.setSpacing(6)
        self.btn_cal_play = _clean_btn("Play", role="primary", height=29)
        self.btn_cal_play.setFixedWidth(78)
        self.btn_cal_play.clicked.connect(self._toggle_playback)
        hbox_ctrl.addWidget(self.btn_cal_play)

        btn_restart = _clean_btn("Restart", height=29, tooltip="Jump back to 00:00")
        btn_restart.clicked.connect(lambda: self._seek_absolute(0.0))
        hbox_ctrl.addWidget(btn_restart)

        btn_back5 = _clean_btn("-5s", height=29)
        btn_back5.clicked.connect(lambda: self._seek_relative(-5.0))
        hbox_ctrl.addWidget(btn_back5)

        btn_fwd5 = _clean_btn("+5s", height=29)
        btn_fwd5.clicked.connect(lambda: self._seek_relative(5.0))
        hbox_ctrl.addWidget(btn_fwd5)

        self.slider_cal_pos = QSlider(Qt.Orientation.Horizontal)
        self.slider_cal_pos.setRange(0, 1000)
        self.slider_cal_pos.sliderPressed.connect(lambda: setattr(self, "_is_scrubbing", True))
        self.slider_cal_pos.sliderReleased.connect(self._on_scrub_released)
        hbox_ctrl.addWidget(self.slider_cal_pos, 1)

        self.lbl_cal_time = QLabel("00:00 / 00:00")
        self.lbl_cal_time.setStyleSheet(
            "color: #d4d4d8; font-family: 'Consolas', monospace; font-size: 11px; min-width: 92px;"
        )
        self.lbl_cal_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hbox_ctrl.addWidget(self.lbl_cal_time)
        player_card.layout_content.addLayout(hbox_ctrl)

        self.lbl_active_lyric_preview = QLabel("Active line: —")
        self.lbl_active_lyric_preview.setStyleSheet(
            "background-color: #15151a; color: #93c5fd; border: 1px solid #282834; "
            "border-radius: 6px; padding: 6px 10px; font-size: 12px; font-weight: 600;"
        )
        player_card.layout_content.addWidget(self.lbl_active_lyric_preview)
        layout.addWidget(player_card)

        # Calibration Toolbar + Interactive Timeline / Raw Editor
        cal_card = CyberCard("Lyric Timeline & Alignment")
        cal_card.layout_content.setContentsMargins(12, 10, 12, 12)
        cal_card.layout_content.setSpacing(8)

        hbox_align = QHBoxLayout()
        hbox_align.setSpacing(6)

        self.btn_snap_all = _clean_btn(
            "Align All Here [Space]",
            role="primary",
            height=30,
            tooltip="Move ALL lyric timestamps so the selected line lands at the exact current playback time",
        )
        self.btn_snap_all.clicked.connect(self._snap_all_to_selected)
        hbox_align.addWidget(self.btn_snap_all)

        self.btn_stamp_single = _clean_btn(
            "Stamp This Line",
            height=30,
            tooltip="Set ONLY the selected line's timestamp to the current time and move to the next line",
        )
        self.btn_stamp_single.clicked.connect(self._retime_selected_line_only)
        hbox_align.addWidget(self.btn_stamp_single)

        self.btn_auto_vocal = _clean_btn(
            "Auto-Align Vocals",
            height=30,
            tooltip="Analyze audio vocal onset and align the first lyric line automatically",
        )
        self.btn_auto_vocal.clicked.connect(self._auto_align_vocals)
        hbox_align.addWidget(self.btn_auto_vocal)

        hbox_align.addStretch(1)

        self.btn_toggle_raw = _clean_btn("Raw .LRC", height=30)
        self.btn_toggle_raw.setCheckable(True)
        self.btn_toggle_raw.toggled.connect(self._on_toggle_raw_view)
        hbox_align.addWidget(self.btn_toggle_raw)
        cal_card.layout_content.addLayout(hbox_align)

        # Fine Shift Nudge Row + Tip
        hbox_nudge = QHBoxLayout()
        hbox_nudge.setSpacing(6)
        lbl_nudge = QLabel("Shift whole file:")
        lbl_nudge.setStyleSheet("color: #9ca3af; font-size: 11px;")
        hbox_nudge.addWidget(lbl_nudge)

        for delta, txt in [(-0.5, "-0.5s"), (-0.1, "-0.1s"), (0.1, "+0.1s"), (0.5, "+0.5s")]:
            b = _clean_btn(txt, height=26)
            b.clicked.connect(lambda _chk=False, d=delta: self._shift_buffer(d))
            hbox_nudge.addWidget(b)

        hbox_nudge.addStretch(1)
        self.lbl_cal_status = QLabel("Select a line and press Space when you hear it sung.")
        self.lbl_cal_status.setStyleSheet("color: #9ca3af; font-size: 11px;")
        hbox_nudge.addWidget(self.lbl_cal_status)
        cal_card.layout_content.addLayout(hbox_nudge)

        # Stacked View: Page 0 = Visual Timeline List, Page 1 = Raw LRC Editor
        self.stack_editor = QStackedWidget()

        self.list_cal_lines = QListWidget()
        self.list_cal_lines.setAlternatingRowColors(False)
        self.list_cal_lines.itemDoubleClicked.connect(self._on_line_double_clicked)
        self.stack_editor.addWidget(self.list_cal_lines)

        self.edit_raw_lrc = QPlainTextEdit()
        self.edit_raw_lrc.setPlaceholderText("[00:12.40] Paste or edit raw .lrc timestamps and text here...")
        self.edit_raw_lrc.setFont(QFont("Consolas", 10))
        self.edit_raw_lrc.textChanged.connect(self._on_raw_text_edited)
        self.stack_editor.addWidget(self.edit_raw_lrc)

        cal_card.layout_content.addWidget(self.stack_editor, 1)

        # Save / Backup Actions Row
        hbox_save = QHBoxLayout()
        hbox_save.setSpacing(8)
        self.btn_restore_bak = _clean_btn(
            "Restore Backup (.bak)",
            height=30,
            tooltip="Revert .lrc file back to the automatic .bak backup created before edits",
        )
        self.btn_restore_bak.clicked.connect(self._restore_current_backup)
        hbox_save.addWidget(self.btn_restore_bak)

        hbox_save.addStretch(1)

        self.btn_save_lrc = _clean_btn("Save & Reload Lyrics", role="success", height=30)
        self.btn_save_lrc.clicked.connect(self._save_current_lrc)
        hbox_save.addWidget(self.btn_save_lrc)
        cal_card.layout_content.addLayout(hbox_save)

        layout.addWidget(cal_card, 1)

    # -----------------------------------------------------------------
    # TAB 1: SEARCH ONLINE
    # -----------------------------------------------------------------
    def _build_search_tab(self):
        layout = QVBoxLayout(self.tab_search)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        search_card = CyberCard("Search Synced Lyrics Database")
        search_card.layout_content.setContentsMargins(12, 10, 12, 12)
        search_card.layout_content.setSpacing(8)

        hbox_inputs = QHBoxLayout()
        hbox_inputs.setSpacing(8)

        self.edit_search_title = QLineEdit()
        self.edit_search_title.setPlaceholderText("Song title...")
        self.edit_search_title.returnPressed.connect(self._start_online_search)
        hbox_inputs.addWidget(self.edit_search_title, 2)

        self.edit_search_artist = QLineEdit()
        self.edit_search_artist.setPlaceholderText("Artist (optional)...")
        self.edit_search_artist.returnPressed.connect(self._start_online_search)
        hbox_inputs.addWidget(self.edit_search_artist, 2)

        self.btn_search_online = _clean_btn("Search", role="primary", height=30)
        self.btn_search_online.clicked.connect(self._start_online_search)
        hbox_inputs.addWidget(self.btn_search_online)
        search_card.layout_content.addLayout(hbox_inputs)

        self.lbl_search_status = QLabel("Enter a song title or load a track to auto-fill metadata.")
        self.lbl_search_status.setStyleSheet("color: #9ca3af; font-size: 11px;")
        search_card.layout_content.addWidget(self.lbl_search_status)
        layout.addWidget(search_card)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_box = QWidget()
        left_lay = QVBoxLayout(left_box)
        left_lay.setContentsMargins(0, 0, 4, 0)
        left_lay.setSpacing(6)
        lbl_cands = QLabel("Matching Releases")
        lbl_cands.setStyleSheet("color: #d4d4d8; font-weight: 600;")
        left_lay.addWidget(lbl_cands)

        self.list_search_results = QListWidget()
        self.list_search_results.currentRowChanged.connect(self._on_search_candidate_selected)
        left_lay.addWidget(self.list_search_results, 1)
        splitter.addWidget(left_box)

        right_box = QWidget()
        right_lay = QVBoxLayout(right_box)
        right_lay.setContentsMargins(4, 0, 0, 0)
        right_lay.setSpacing(6)
        lbl_prev = QLabel("Lyrics Preview")
        lbl_prev.setStyleSheet("color: #d4d4d8; font-weight: 600;")
        right_lay.addWidget(lbl_prev)

        self.edit_search_preview = QPlainTextEdit()
        self.edit_search_preview.setReadOnly(True)
        self.edit_search_preview.setFont(QFont("Consolas", 10))
        self.edit_search_preview.setPlaceholderText("Select a match on the left to preview its synced lines...")
        right_lay.addWidget(self.edit_search_preview, 1)
        splitter.addWidget(right_box)
        splitter.setSizes([310, 400])

        layout.addWidget(splitter, 1)

        hbox_use = QHBoxLayout()
        hbox_use.setSpacing(8)
        hbox_use.addStretch(1)
        self.btn_use_in_cal = _clean_btn("Load into Calibrate Tab", height=32)
        self.btn_use_in_cal.setEnabled(False)
        self.btn_use_in_cal.clicked.connect(lambda: self._apply_search_result(save_now=False))
        hbox_use.addWidget(self.btn_use_in_cal)

        self.btn_save_search_result = _clean_btn("Save Directly to Current Track", role="success", height=32)
        self.btn_save_search_result.setEnabled(False)
        self.btn_save_search_result.clicked.connect(lambda: self._apply_search_result(save_now=True))
        hbox_use.addWidget(self.btn_save_search_result)
        layout.addLayout(hbox_use)

    # -----------------------------------------------------------------
    # TAB 2: FOLDER AUTO-SYNC
    # -----------------------------------------------------------------
    def _build_sync_tab(self):
        layout = QVBoxLayout(self.tab_sync)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        folder_card = CyberCard("Library Batch Lyrics Sync")
        folder_card.layout_content.setContentsMargins(12, 10, 12, 12)
        folder_card.layout_content.setSpacing(8)

        hbox_dir = QHBoxLayout()
        hbox_dir.setSpacing(8)
        default_dir = ""
        if self.panel and getattr(self.panel, "audio_engine", None):
            default_dir = getattr(self.panel.audio_engine, "folder_path", "") or ""
        self.edit_sync_folder = QLineEdit(default_dir)
        hbox_dir.addWidget(self.edit_sync_folder, 1)

        btn_dir = _clean_btn("Browse...", height=29)
        btn_dir.clicked.connect(self._browse_sync_folder)
        hbox_dir.addWidget(btn_dir)
        folder_card.layout_content.addLayout(hbox_dir)

        self.chk_sync_overwrite = QCheckBox("Overwrite existing .lrc files (re-download everything)")
        folder_card.layout_content.addWidget(self.chk_sync_overwrite)

        hbox_sync_btns = QHBoxLayout()
        hbox_sync_btns.setSpacing(8)
        self.btn_start_sync = _clean_btn("Download Missing Lyrics", role="primary", height=30)
        self.btn_start_sync.clicked.connect(self._start_batch_sync)
        hbox_sync_btns.addWidget(self.btn_start_sync)

        self.btn_stop_sync = _clean_btn("Stop", role="danger", height=30)
        self.btn_stop_sync.setEnabled(False)
        self.btn_stop_sync.clicked.connect(self._stop_batch_sync)
        hbox_sync_btns.addWidget(self.btn_stop_sync)

        btn_restore_all = _clean_btn("Restore All .bak Backups", height=30)
        btn_restore_all.clicked.connect(self._restore_all_backups)
        hbox_sync_btns.addWidget(btn_restore_all)
        hbox_sync_btns.addStretch(1)
        folder_card.layout_content.addLayout(hbox_sync_btns)

        self.progress_sync = QProgressBar()
        self.progress_sync.setRange(0, 100)
        self.progress_sync.setValue(0)
        self.progress_sync.setFixedHeight(16)
        folder_card.layout_content.addWidget(self.progress_sync)
        layout.addWidget(folder_card)

        self.txt_sync_log = QPlainTextEdit()
        self.txt_sync_log.setReadOnly(True)
        self.txt_sync_log.setFont(QFont("Consolas", 9))
        self.txt_sync_log.setPlaceholderText("Batch download log will appear here...")
        layout.addWidget(self.txt_sync_log, 1)

    # -----------------------------------------------------------------
    # LIFECYCLE & ENGINE SYNCHRONIZATION
    # -----------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_track_list()
        if not self._current_track_path:
            self.load_currently_playing()
        self._sync_timer.start()
        self._on_playback_tick()

    def hideEvent(self, event):
        self._sync_timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._sync_timer.stop()
        self.hide()
        trim_process_memory()
        event.ignore()

    def refresh_track_list(self):
        playlist = []
        if self.panel and getattr(self.panel, "audio_engine", None):
            playlist = list(getattr(self.panel.audio_engine, "playlist", []) or [])

        self.combo_tracks.blockSignals(True)
        current_norm = os.path.normpath(self._current_track_path) if self._current_track_path else ""
        self.combo_tracks.clear()
        selected_idx = -1
        for i, path in enumerate(playlist):
            norm = os.path.normpath(path)
            has_lrc = os.path.exists(os.path.splitext(norm)[0] + ".lrc")
            marker = "[LRC] " if has_lrc else "[No LRC] "
            self.combo_tracks.addItem(f"{marker}{os.path.basename(norm)}", norm)
            if current_norm and norm == current_norm:
                selected_idx = i
        if selected_idx >= 0:
            self.combo_tracks.setCurrentIndex(selected_idx)
        self.combo_tracks.blockSignals(False)

    def load_currently_playing(self):
        engine = getattr(self.panel, "audio_engine", None)
        if not engine:
            return
        playlist = getattr(engine, "playlist", []) or []
        idx = getattr(engine, "current_index", -1)
        if 0 <= idx < len(playlist):
            self._load_cal_track(os.path.normpath(playlist[idx]))

    def _on_combo_track_selected(self, idx: int):
        if idx < 0:
            return
        path = self.combo_tracks.itemData(idx)
        if path and os.path.exists(path):
            self._load_cal_track(path)

    def _browse_cal_audio(self):
        start_dir = (
            self.panel.audio_engine.folder_path
            if self.panel and getattr(self.panel, "audio_engine", None)
            else PROJECT_ROOT
        )
        exts = " ".join(f"*{e}" for e in SUPPORTED_AUDIO_EXTS)
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Audio Track", start_dir, f"Audio Files ({exts})"
        )
        if path:
            self._load_cal_track(os.path.normpath(path))

    def _load_cal_track(self, track_path: str):
        """Public-compatible loader called by controller/tests/UI."""
        norm = os.path.normpath(track_path)
        self._current_track_path = norm
        self.edit_cal_file.setText(norm)

        # Keep combo selection synced if present
        self.combo_tracks.blockSignals(True)
        for i in range(self.combo_tracks.count()):
            if os.path.normpath(str(self.combo_tracks.itemData(i) or "")) == norm:
                self.combo_tracks.setCurrentIndex(i)
                break
        self.combo_tracks.blockSignals(False)

        # Auto-fill Search tab metadata cleanly
        try:
            meta = extract_metadata(norm)
            self.edit_search_title.setText(meta.get("title", "") or "")
            self.edit_search_artist.setText(meta.get("artist", "") or "")
        except Exception:
            stem = os.path.splitext(os.path.basename(norm))[0]
            self.edit_search_title.setText(stem)
            self.edit_search_artist.clear()

        lrc_path = os.path.splitext(norm)[0] + ".lrc"
        if os.path.exists(lrc_path):
            try:
                with open(lrc_path, "r", encoding="utf-8") as fh:
                    self._set_lrc_buffer(fh.read(), dirty=False)
                self.lbl_cal_status.setText(f"Loaded {os.path.basename(lrc_path)}")
            except Exception as exc:
                self._set_lrc_buffer("", dirty=False)
                self.lbl_cal_status.setText(f"Could not read .lrc: {exc}")
        else:
            self._set_lrc_buffer("", dirty=False)
            self.lbl_cal_status.setText("No .lrc file yet. Click 'Fetch Online' to download one.")

        bak_exists = os.path.exists(lrc_path + ".bak")
        self.btn_restore_bak.setEnabled(bak_exists)

    def _set_lrc_buffer(self, text: str, dirty: bool = True):
        self._lrc_text_buffer = text
        self._has_unsaved_changes = dirty
        self._update_dirty_badge()

        self.edit_raw_lrc.blockSignals(True)
        self.edit_raw_lrc.setPlainText(text)
        self.edit_raw_lrc.blockSignals(False)

        self._rebuild_timeline_list()

    def _update_dirty_badge(self):
        if self._has_unsaved_changes:
            self.lbl_dirty_badge.setText("Unsaved Changes")
            self.lbl_dirty_badge.setStyleSheet(
                "background-color: #2f2516; color: #fbbf24; border: 1px solid #6b4e16; "
                "border-radius: 5px; padding: 3px 9px; font-size: 11px; font-weight: 600;"
            )
        else:
            self.lbl_dirty_badge.setText("Saved")
            self.lbl_dirty_badge.setStyleSheet(
                "background-color: #1d2722; color: #6ee7b7; border: 1px solid #284b3a; "
                "border-radius: 5px; padding: 3px 9px; font-size: 11px; font-weight: 600;"
            )

    def _rebuild_timeline_list(self):
        prev_row = self.list_cal_lines.currentRow()
        self._parsed_entries = _parse_lrc_lines(self._lrc_text_buffer)
        self.list_cal_lines.blockSignals(True)
        self.list_cal_lines.clear()
        for entry in self._parsed_entries:
            ts_str = _fmt_lrc_ts(entry["time"])
            item = QListWidgetItem(f"{ts_str}   {entry['text']}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.list_cal_lines.addItem(item)
        if 0 <= prev_row < self.list_cal_lines.count():
            self.list_cal_lines.setCurrentRow(prev_row)
        elif self.list_cal_lines.count() > 0:
            self.list_cal_lines.setCurrentRow(0)
        self.list_cal_lines.blockSignals(False)
        self._last_active_idx = -1

    # -----------------------------------------------------------------
    # LIVE ENGINE PLAYBACK BINDINGS
    # -----------------------------------------------------------------
    def _ensure_track_loaded_in_engine(self) -> tuple[bool, bool]:
        """Ensure `_current_track_path` is active in `audio_engine`. Returns (ok, started_playing)."""
        engine = getattr(self.panel, "audio_engine", None)
        if not engine or not self._current_track_path:
            return False, False
        playlist = getattr(engine, "playlist", []) or []
        idx = getattr(engine, "current_index", -1)
        curr_path = os.path.normpath(playlist[idx]) if 0 <= idx < len(playlist) else ""
        if curr_path != os.path.normpath(self._current_track_path):
            norm_target = os.path.normpath(self._current_track_path)
            found_idx = -1
            for i, p in enumerate(playlist):
                if os.path.normpath(p) == norm_target:
                    found_idx = i
                    break
            if found_idx < 0:
                playlist.append(norm_target)
                engine.playlist = playlist
                found_idx = len(playlist) - 1
            engine.play_index(found_idx)
            if self.panel and hasattr(self.panel, "sync_play_state"):
                self.panel.sync_play_state()
            return True, True
        return True, False

    def _toggle_playback(self):
        engine = getattr(self.panel, "audio_engine", None)
        if not engine:
            return
        ok, started_new = self._ensure_track_loaded_in_engine()
        if not ok:
            return
        if not started_new:
            engine.toggle_play_pause()
            if self.panel and hasattr(self.panel, "sync_play_state"):
                self.panel.sync_play_state()
        self._on_playback_tick()

    def _seek_absolute(self, target_sec: float):
        engine = getattr(self.panel, "audio_engine", None)
        if not engine:
            return
        ok, _ = self._ensure_track_loaded_in_engine()
        if not ok:
            return
        dur = max(0.0, float(engine.get_duration() or 0.0))
        clamped = max(0.0, min(target_sec, dur if dur > 0 else target_sec))
        engine.seek(clamped)
        self._on_playback_tick()

    def _seek_relative(self, delta_sec: float):
        engine = getattr(self.panel, "audio_engine", None)
        if not engine:
            return
        curr = float(engine.get_position() or 0.0)
        self._seek_absolute(curr + delta_sec)

    def _on_scrub_released(self):
        self._is_scrubbing = False
        engine = getattr(self.panel, "audio_engine", None)
        if not engine:
            return
        dur = max(0.0, float(engine.get_duration() or 0.0))
        if dur > 0:
            target = (self.slider_cal_pos.value() / 1000.0) * dur
            self._seek_absolute(target)

    def _on_playback_tick(self):
        engine = getattr(self.panel, "audio_engine", None)
        if not engine:
            return
        is_playing = bool(getattr(engine, "is_playing", False))
        self.btn_cal_play.setText("Pause" if is_playing else "Play")

        pos = float(engine.get_position() or 0.0)
        dur = float(engine.get_duration() or 0.0)
        self.lbl_cal_time.setText(f"{_fmt_mmss(pos)} / {_fmt_mmss(dur)}")

        if not self._is_scrubbing and dur > 0:
            slider_val = int(max(0, min(1000, round((pos / dur) * 1000.0))))
            self.slider_cal_pos.blockSignals(True)
            self.slider_cal_pos.setValue(slider_val)
            self.slider_cal_pos.blockSignals(False)

        # Highlight active lyric line matching current engine position
        active_idx = -1
        for i, entry in enumerate(self._parsed_entries):
            if entry["time"] <= pos:
                active_idx = i
            else:
                break

        if active_idx != self._last_active_idx:
            if 0 <= self._last_active_idx < self.list_cal_lines.count():
                prev_item = self.list_cal_lines.item(self._last_active_idx)
                prev_item.setForeground(QColor("#e4e4e7"))
                font = prev_item.font()
                font.setBold(False)
                prev_item.setFont(font)

            self._last_active_idx = active_idx
            if 0 <= active_idx < self.list_cal_lines.count():
                cur_item = self.list_cal_lines.item(active_idx)
                cur_item.setForeground(QColor("#60a5fa"))
                font = cur_item.font()
                font.setBold(True)
                cur_item.setFont(font)
                if self.tabs.currentIndex() == 0 and not self.list_cal_lines.underMouse():
                    self.list_cal_lines.scrollToItem(
                        cur_item, QListWidget.ScrollHint.EnsureVisible
                    )
                self.lbl_active_lyric_preview.setText(
                    f"Now ({_fmt_mmss(pos)}): {self._parsed_entries[active_idx]['text']}"
                )
            else:
                self.lbl_active_lyric_preview.setText(f"Now ({_fmt_mmss(pos)}): —")

    # -----------------------------------------------------------------
    # CALIBRATION ACTIONS (Visual Timeline & Nudges)
    # -----------------------------------------------------------------
    def _on_line_double_clicked(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        # Seek slightly before the lyric so the user hears the lead-in beat clearly
        self._seek_absolute(max(0.0, float(data["time"]) - 1.5))

    def _on_space_align_shortcut(self):
        if self.tabs.currentIndex() == 0 and self.stack_editor.currentIndex() == 0:
            self._snap_all_to_selected()

    def _snap_all_to_selected(self):
        row = self.list_cal_lines.currentRow()
        if row < 0 or row >= len(self._parsed_entries):
            self.lbl_cal_status.setText("Select a lyric line first before aligning.")
            return
        engine = getattr(self.panel, "audio_engine", None)
        if not engine:
            return
        curr_pos = float(engine.get_position() or 0.0)
        line_time = float(self._parsed_entries[row]["time"])
        delta = curr_pos - line_time
        self._shift_buffer(delta)
        self.lbl_cal_status.setText(
            f"Aligned line #{row + 1} to {_fmt_mmss(curr_pos)} (shifted all lyrics {delta:+.2f}s)."
        )

    def _retime_selected_line_only(self):
        row = self.list_cal_lines.currentRow()
        if row < 0 or row >= len(self._parsed_entries):
            self.lbl_cal_status.setText("Select a lyric line to re-time.")
            return
        engine = getattr(self.panel, "audio_engine", None)
        if not engine:
            return
        curr_pos = float(engine.get_position() or 0.0)
        entry = self._parsed_entries[row]
        raw_lines = self._lrc_text_buffer.splitlines()
        line_idx = entry["line_idx"]
        if 0 <= line_idx < len(raw_lines):
            clean_text = _LRC_TS_RE.sub("", raw_lines[line_idx]).strip()
            raw_lines[line_idx] = f"{_fmt_lrc_ts(curr_pos)} {clean_text}"
            self._set_lrc_buffer("\n".join(raw_lines), dirty=True)
            next_row = min(row + 1, self.list_cal_lines.count() - 1)
            self.list_cal_lines.setCurrentRow(next_row)
            self.list_cal_lines.scrollToItem(self.list_cal_lines.item(next_row))
            self.lbl_cal_status.setText(f"Stamped line #{row + 1} at {_fmt_mmss(curr_pos)}.")

    def _shift_buffer(self, delta_sec: float):
        if not self._lrc_text_buffer.strip():
            self.lbl_cal_status.setText("No lyrics loaded to shift.")
            return
        # Bake out any stale [offset:] tag and apply exact delta to timestamps
        cleaned = _OFFSET_TAG_RE.sub("", self._lrc_text_buffer)
        shifted = shift_lrc_timestamps(cleaned, delta_sec)
        self._set_lrc_buffer(shifted, dirty=True)
        self.lbl_cal_status.setText(f"Shifted all timestamps by {delta_sec:+.2f}s (unsaved).")

    def _auto_align_vocals(self):
        if not self._current_track_path or not os.path.exists(self._current_track_path):
            self.lbl_cal_status.setText("Load a valid audio track first.")
            return
        if not self._parsed_entries:
            self.lbl_cal_status.setText("Load or fetch .lrc lyrics before auto-aligning.")
            return
        self.btn_auto_vocal.setEnabled(False)
        self.lbl_cal_status.setText("Analyzing audio for vocal entry...")
        self._vocal_worker = VocalDetectWorker(self._current_track_path)
        self._vocal_worker.detected.connect(self._on_vocal_entry_detected)
        self._vocal_worker.start()

    def _on_vocal_entry_detected(self, vocal_sec: float):
        self.btn_auto_vocal.setEnabled(True)
        if vocal_sec < 0:
            self.lbl_cal_status.setText("Could not detect clear vocal entry automatically.")
            return
        first_ts = self._parsed_entries[0]["time"] if self._parsed_entries else 0.0
        delta = vocal_sec - first_ts
        self._shift_buffer(delta)
        self.lbl_cal_status.setText(
            f"Detected vocals at {vocal_sec:.2f}s — shifted all lines by {delta:+.2f}s."
        )

    def _on_toggle_raw_view(self, show_raw: bool):
        self.stack_editor.setCurrentIndex(1 if show_raw else 0)
        if not show_raw:
            self._rebuild_timeline_list()

    def _on_raw_text_edited(self):
        self._lrc_text_buffer = self.edit_raw_lrc.toPlainText()
        if not self._has_unsaved_changes:
            self._has_unsaved_changes = True
            self._update_dirty_badge()

    def _save_current_lrc(self):
        if not self._current_track_path:
            self.lbl_cal_status.setText("No target audio track selected.")
            return
        content = self._lrc_text_buffer.strip()
        if not content:
            self.lbl_cal_status.setText("Cannot save empty lyrics.")
            return

        lrc_path = os.path.splitext(self._current_track_path)[0] + ".lrc"
        bak_path = lrc_path + ".bak"
        try:
            if os.path.exists(lrc_path) and not os.path.exists(bak_path):
                shutil.copy2(lrc_path, bak_path)
            with open(lrc_path, "w", encoding="utf-8") as fh:
                fh.write(content + "\n")
        except Exception as exc:
            self.lbl_cal_status.setText(f"Failed to write file: {exc}")
            return

        self._has_unsaved_changes = False
        self._update_dirty_badge()
        self.btn_restore_bak.setEnabled(os.path.exists(bak_path))

        # Reset per-track manual offset when permanently saving baked timestamps
        if self.panel and getattr(self.panel, "lyrics_overlay", None):
            mgr = self.panel.lyrics_overlay.lyrics_manager
            if abs(getattr(mgr, "manual_offset", 0.0)) > 0.005:
                mgr.reset_offset()
            self.panel._on_lyrics_saved_externally(lrc_path)

        self.lyrics_saved.emit(lrc_path)
        self.refresh_track_list()
        self.lbl_cal_status.setText(f"Saved {os.path.basename(lrc_path)} and reloaded desktop subtitles.")

    def _restore_current_backup(self):
        if not self._current_track_path:
            return
        ok, msg = restore_lrc_backup(self._current_track_path)
        self.lbl_cal_status.setText(msg)
        if ok:
            self._load_cal_track(self._current_track_path)
            lrc_path = os.path.splitext(self._current_track_path)[0] + ".lrc"
            if self.panel:
                self.panel._on_lyrics_saved_externally(lrc_path)
            self.lyrics_saved.emit(lrc_path)

    # -----------------------------------------------------------------
    # ONLINE CANDIDATE SEARCH ACTIONS
    # -----------------------------------------------------------------
    def _quick_fetch_for_cal_track(self):
        self.tabs.setCurrentIndex(1)
        self._start_online_search()

    def _start_online_search(self):
        title = self.edit_search_title.text().strip()
        artist = self.edit_search_artist.text().strip()
        if not title:
            self.lbl_search_status.setText("Enter a song title first.")
            return

        dur = 0.0
        engine = getattr(self.panel, "audio_engine", None)
        if engine and self._current_track_path:
            dur = float(engine.get_duration() or 0.0)

        self.btn_search_online.setEnabled(False)
        self.btn_use_in_cal.setEnabled(False)
        self.btn_save_search_result.setEnabled(False)
        self.list_search_results.clear()
        self.edit_search_preview.clear()
        self._search_candidates = []
        self.lbl_search_status.setText("Searching LRCLIB & synced providers...")

        self._search_worker = CandidateSearchWorker(title, artist, dur, allow_fallback=True)
        self._search_worker.results_ready.connect(self._on_online_search_finished)
        self._search_worker.start()

    def _on_online_search_finished(self, cands: list, fallback_lrc: str):
        self.btn_search_online.setEnabled(True)
        self._search_candidates = list(cands or [])

        if not self._search_candidates and fallback_lrc:
            self._search_candidates = [
                {
                    "trackName": self.edit_search_title.text().strip(),
                    "artistName": self.edit_search_artist.text().strip() or "Provider Match",
                    "albumName": "SyncedLyrics Fallback",
                    "duration": 0,
                    "syncedLyrics": fallback_lrc,
                }
            ]

        if not self._search_candidates:
            self.lbl_search_status.setText("No synced lyrics found for this query.")
            return

        for cand in self._search_candidates:
            track = cand.get("trackName") or cand.get("name") or "Unknown Track"
            artist = cand.get("artistName") or "Unknown Artist"
            album = cand.get("albumName") or ""
            dur_s = cand.get("duration") or 0
            dur_label = _fmt_mmss(dur_s) if dur_s else "--:--"
            album_part = f" · {album}" if album else ""
            self.list_search_results.addItem(f"{track} — {artist}{album_part} ({dur_label})")

        self.lbl_search_status.setText(f"Found {len(self._search_candidates)} synced candidate(s).")
        self.list_search_results.setCurrentRow(0)

    def _on_search_candidate_selected(self, row: int):
        if 0 <= row < len(self._search_candidates):
            lrc = self._search_candidates[row].get("syncedLyrics") or ""
            self.edit_search_preview.setPlainText(lrc)
            self.btn_use_in_cal.setEnabled(bool(lrc.strip()))
            self.btn_save_search_result.setEnabled(
                bool(lrc.strip()) and bool(self._current_track_path)
            )
        else:
            self.edit_search_preview.clear()
            self.btn_use_in_cal.setEnabled(False)
            self.btn_save_search_result.setEnabled(False)

    def _apply_search_result(self, save_now: bool):
        lrc = self.edit_search_preview.toPlainText().strip()
        if not lrc:
            return
        self._set_lrc_buffer(lrc, dirty=not save_now)
        self.tabs.setCurrentIndex(0)
        if save_now:
            self._save_current_lrc()
        else:
            self.lbl_cal_status.setText("Loaded candidate into Calibrate tab — preview and click Save when ready.")

    # -----------------------------------------------------------------
    # FOLDER AUTO-SYNC ACTIONS
    # -----------------------------------------------------------------
    def _browse_sync_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Music Folder", self.edit_sync_folder.text() or PROJECT_ROOT
        )
        if folder:
            self.edit_sync_folder.setText(os.path.normpath(folder))

    def _start_batch_sync(self):
        folder = self.edit_sync_folder.text().strip()
        if not folder or not os.path.isdir(folder):
            self.txt_sync_log.appendPlainText("Select a valid music folder first.")
            return
        self.txt_sync_log.clear()
        self.progress_sync.setValue(0)
        self.btn_start_sync.setEnabled(False)
        self.btn_stop_sync.setEnabled(True)

        self._batch_worker = BatchFetchWorker(folder, force=self.chk_sync_overwrite.isChecked())
        self._batch_worker.progress.connect(self._on_batch_progress)
        self._batch_worker.finished.connect(self._on_batch_finished)
        self._batch_worker.start()

    def _stop_batch_sync(self):
        if self._batch_worker:
            self._batch_worker.cancel()
        self.btn_stop_sync.setEnabled(False)

    def _on_batch_progress(self, curr: int, total: int, path: str, ok: bool, msg: str):
        pct = int(round((curr / max(1, total)) * 100))
        self.progress_sync.setValue(pct)
        tag = "OK" if ok else "MISS"
        self.txt_sync_log.appendPlainText(f"[{tag}] {os.path.basename(path)} — {msg}")
        if ok and "already exists" not in msg:
            lrc_path = os.path.splitext(path)[0] + ".lrc"
            if self.panel:
                self.panel._on_lyrics_saved_externally(lrc_path)
            self.lyrics_saved.emit(lrc_path)

    def _on_batch_finished(self, stats: dict):
        self.btn_start_sync.setEnabled(True)
        self.btn_stop_sync.setEnabled(False)
        self.refresh_track_list()
        self.txt_sync_log.appendPlainText(
            f"Completed — Total: {stats.get('total', 0)}, Downloaded: {stats.get('fetched', 0)}, "
            f"Skipped: {stats.get('skipped', 0)}, Missing: {stats.get('failed', 0)}"
        )

    def _restore_all_backups(self):
        folder = self.edit_sync_folder.text().strip()
        if not folder or not os.path.isdir(folder):
            return
        restored = 0
        for root, _, filenames in os.walk(folder):
            for fname in filenames:
                if fname.lower().endswith(SUPPORTED_AUDIO_EXTS):
                    ok, _msg = restore_lrc_backup(os.path.join(root, fname))
                    if ok:
                        restored += 1
        self.txt_sync_log.appendPlainText(f"Restored {restored} backup .lrc file(s).")
        if self._current_track_path:
            self._load_cal_track(self._current_track_path)
        self.refresh_track_list()
