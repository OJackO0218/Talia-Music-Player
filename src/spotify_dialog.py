"""
Talia Spotify Sync & Playlist Import Dialog.

Allows users to import public Spotify playlists, albums, and tracks via direct URL
or select from curated and saved personal playlists with zero API keys required.
Tracks are downloaded with Opus audio and verified synchronized LRC lyrics.
"""

import logging
import os
import re
import threading
from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config import DEFAULT_MUSIC_DIR, SUPPORTED_AUDIO_EXTS
from ui_theme import CYBER_DIALOG_CONTROLS_QSS
from ui_widgets import (
    CyberCardContainer,
    CyberChamferButton,
    CyberLineEdit,
    DraggableClampedDialogMixin,
    DraggableHeaderWidget,
)

log = logging.getLogger("SpotifyDialog")


class DownloadBridge(QObject):
    """Thread-safe Qt signal bridge between background download worker and main GUI thread."""

    fetch_finished = pyqtSignal()                     # emitted when URL fetch completes
    track_started = pyqtSignal(int, int, str, int)    # idx, total, query, pct
    live_progress = pyqtSignal(int, int, str)         # idx, total, msg
    track_completed = pyqtSignal(int, bool)           # item_idx, is_success
    batch_finished = pyqtSignal(int, int, str, bool)  # success, failed, target_dir, was_stopped


class SpotifySyncDialog(DraggableClampedDialogMixin, QDialog):
    """Cyberpunk modal dialog for importing playlists from Spotify with zero developer keys."""

    def __init__(self, panel, parent=None):
        super().__init__(parent or panel)
        self.panel = panel
        self.spotify_service = panel.spotify_service

        self.setWindowTitle("Spotify Sync - Import Playlists")
        self.setFixedSize(450, 500)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self._custom_positioned = False

        self._active_playlist_data: Optional[dict] = None
        self._track_checkboxes: list[tuple[QCheckBox, dict, str]] = []  # (checkbox, track_dict, orig_label)
        self._is_batch_downloading = False
        self._stop_download_flag = False

        # Thread-safe Signal Bridge
        self.bridge = DownloadBridge()
        self.bridge.fetch_finished.connect(self._on_fetch_finished)
        self.bridge.track_started.connect(self._on_track_started)
        self.bridge.live_progress.connect(self._on_live_progress)
        self.bridge.track_completed.connect(self._on_track_completed)
        self.bridge.batch_finished.connect(self._on_batch_complete)

        self.init_ui()
        self._wire_signals()
        self._populate_saved_playlists()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Card container with authentic Cyberpunk dark background & red chamfered border matching ControlPanel
        self.card_container = CyberCardContainer(self)
        self.card_container.setObjectName("spotifyDialogCard")
        self.card_container.setStyleSheet(
            "QFrame#spotifyDialogCard { border: none; background: transparent; }"
            + CYBER_DIALOG_CONTROLS_QSS
        )
        root_layout.addWidget(self.card_container)

        container_layout = QVBoxLayout(self.card_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 1. Top Header Bar (spans full card width over red header banner)
        header_widget = DraggableHeaderWidget(self)
        header_widget.setFixedHeight(40)
        hbox_header = QHBoxLayout(header_widget)
        hbox_header.setContentsMargins(12, 2, 12, 2)
        hbox_header.setSpacing(8)

        lbl_title = QLabel("SPOTIFY PLAYLIST SYNC", header_widget)
        lbl_title.setStyleSheet(
            "color: #FFFFFF; font-family: 'Rajdhani', sans-serif; font-size: 15px; font-weight: bold; letter-spacing: 1.5px; background: transparent;"
        )
        hbox_header.addWidget(lbl_title)

        self.lbl_header_pill = QLabel("READY", header_widget)
        self.lbl_header_pill.setStyleSheet(
            "color: #4ade80; border: 1px solid #22c55e; background-color: #052e16; font-family: 'Share Tech Mono', 'Consolas', monospace; font-size: 9px; font-weight: bold; border-radius: 2px; padding: 2px 6px;"
        )
        hbox_header.addWidget(self.lbl_header_pill)

        hbox_header.addStretch(1)

        self.btn_close = CyberChamferButton("X", variant="exit", parent=header_widget)
        self.btn_close.setFixedSize(26, 26)
        self.btn_close.setToolTip("Close")
        self.btn_close.clicked.connect(self.hide)
        hbox_header.addWidget(self.btn_close)

        container_layout.addWidget(header_widget)

        # 2. Main Middle Body (dense layout matching ControlPanel margins & spacing)
        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(14, 6, 16, 12)
        body_layout.setSpacing(6)

        # Segmented Mode Switcher with Chamfered Tabs
        tab_bar_layout = QHBoxLayout()
        tab_bar_layout.setContentsMargins(0, 0, 0, 0)
        tab_bar_layout.setSpacing(6)

        self.btn_tab_link = CyberChamferButton("PASTE SPOTIFY LINK", variant="tab_cyan")
        self.btn_tab_link.setFixedHeight(26)
        self.btn_tab_link.clicked.connect(lambda: self._switch_input_tab("link"))
        tab_bar_layout.addWidget(self.btn_tab_link, 1)

        self.btn_tab_saved = CyberChamferButton("SAVED & CURATED", variant="tab_idle")
        self.btn_tab_saved.setFixedHeight(26)
        self.btn_tab_saved.clicked.connect(lambda: self._switch_input_tab("saved"))
        tab_bar_layout.addWidget(self.btn_tab_saved, 1)

        body_layout.addLayout(tab_bar_layout)

        # Mode Stack (Dense Card)
        self.input_stack = QStackedWidget()
        self.input_stack.setFixedHeight(76)

        # --- VIEW 0: PASTE URL ---
        view_url = QFrame()
        view_url.setStyleSheet(
            "QFrame { background-color: #0B0B13; border: 1px solid rgba(247, 80, 73, 85); border-radius: 3px; }"
        )
        url_layout = QVBoxLayout(view_url)
        url_layout.setContentsMargins(8, 6, 8, 6)
        url_layout.setSpacing(4)

        hbox_input = QHBoxLayout()
        hbox_input.setSpacing(5)

        self.edit_url = CyberLineEdit("Paste Spotify playlist, album, or track URL...", monospace=True)
        self.edit_url.setFixedHeight(26)
        self.edit_url.returnPressed.connect(self._on_fetch_url_clicked)
        hbox_input.addWidget(self.edit_url, 1)

        btn_paste = CyberChamferButton("PASTE", variant="action_neutral")
        btn_paste.setFixedSize(58, 26)
        btn_paste.setToolTip("Paste Spotify URL from clipboard and auto-fetch")
        btn_paste.clicked.connect(self._on_paste_url_clicked)
        hbox_input.addWidget(btn_paste)

        self.btn_fetch_url = CyberChamferButton("Fetch Songs", variant="action_green")
        self.btn_fetch_url.setFixedSize(96, 26)
        self.btn_fetch_url.clicked.connect(self._on_fetch_url_clicked)
        hbox_input.addWidget(self.btn_fetch_url)
        url_layout.addLayout(hbox_input)

        lbl_url_inst = QLabel("Accepts public playlists, albums, and tracks. Includes Opus audio + LRC lyrics.")
        lbl_url_inst.setStyleSheet("color: #71717a; font-size: 10px; background: transparent; border: none;")
        url_layout.addWidget(lbl_url_inst)

        self.input_stack.addWidget(view_url)

        # --- VIEW 1: SAVED & CURATED PLAYLISTS ---
        view_saved = QFrame()
        view_saved.setStyleSheet(
            "QFrame { background-color: #0B0B13; border: 1px solid rgba(247, 80, 73, 85); border-radius: 3px; }"
        )
        saved_layout = QVBoxLayout(view_saved)
        saved_layout.setContentsMargins(8, 6, 8, 6)
        saved_layout.setSpacing(5)

        hbox_combo = QHBoxLayout()
        hbox_combo.setSpacing(5)
        self.combo_saved_playlists = QComboBox()
        self.combo_saved_playlists.setFixedHeight(26)
        hbox_combo.addWidget(self.combo_saved_playlists, 1)

        btn_load_saved = CyberChamferButton("LOAD SELECTED", variant="action_cyan")
        btn_load_saved.setFixedSize(102, 26)
        btn_load_saved.clicked.connect(self._on_load_saved_clicked)
        hbox_combo.addWidget(btn_load_saved)

        self.btn_delete_saved = CyberChamferButton("✕", variant="delete_playlist")
        self.btn_delete_saved.setFixedSize(26, 26)
        self.btn_delete_saved.setToolTip("Delete selected custom bookmark")
        self.btn_delete_saved.clicked.connect(self._on_delete_saved_clicked)
        hbox_combo.addWidget(self.btn_delete_saved)
        saved_layout.addLayout(hbox_combo)

        # Save custom bookmark row
        hbox_add = QHBoxLayout()
        hbox_add.setSpacing(5)
        self.edit_custom_name = QLineEdit()
        self.edit_custom_name.setPlaceholderText("Bookmark Name...")
        self.edit_custom_name.setFixedHeight(24)
        self.edit_custom_name.setMaximumWidth(120)
        hbox_add.addWidget(self.edit_custom_name)

        self.edit_custom_url = QLineEdit()
        self.edit_custom_url.setPlaceholderText("Spotify Playlist URL...")
        self.edit_custom_url.setFixedHeight(24)
        hbox_add.addWidget(self.edit_custom_url, 1)

        btn_save_link = CyberChamferButton("+ SAVE", variant="action_cyan")
        btn_save_link.setFixedSize(64, 24)
        btn_save_link.clicked.connect(self._on_save_custom_playlist)
        hbox_add.addWidget(btn_save_link)
        saved_layout.addLayout(hbox_add)

        self.input_stack.addWidget(view_saved)
        body_layout.addWidget(self.input_stack)

        # Legacy compatibility alias
        self.tabs = self.input_stack

        # Default tab state
        self._switch_input_tab("link")

        # --- PLAYLIST METADATA, FILTER & CONTROLS HUD CARD ---
        self.card_meta = QFrame()
        self.card_meta.setStyleSheet(
            "QFrame { background-color: #0B0B13; border: 1px solid rgba(247, 80, 73, 85); border-radius: 3px; }"
        )
        meta_card_layout = QVBoxLayout(self.card_meta)
        meta_card_layout.setContentsMargins(8, 5, 8, 5)
        meta_card_layout.setSpacing(4)

        # Row 1: Playlist Title + Live Track Filter
        hbox_meta_top = QHBoxLayout()
        hbox_meta_top.setSpacing(6)
        self.lbl_playlist_meta = QLabel("No playlist loaded yet.", self.card_meta)
        self.lbl_playlist_meta.setStyleSheet(
            "color: #a1a1aa; font-family: 'Rajdhani', sans-serif; font-size: 11px; font-weight: bold; background: transparent; border: none;"
        )
        hbox_meta_top.addWidget(self.lbl_playlist_meta, 1)

        self.edit_track_filter = QLineEdit()
        self.edit_track_filter.setPlaceholderText("Filter tracks...")
        self.edit_track_filter.setFixedHeight(22)
        self.edit_track_filter.setMaximumWidth(145)
        self.edit_track_filter.textChanged.connect(self._filter_loaded_tracks)
        hbox_meta_top.addWidget(self.edit_track_filter)
        meta_card_layout.addLayout(hbox_meta_top)

        # Row 2: Chamfered Select / Deselect / Only New & Count Badge
        hbox_meta_bottom = QHBoxLayout()
        hbox_meta_bottom.setSpacing(5)

        btn_sel_all = CyberChamferButton("SELECT ALL", variant="action_neutral")
        btn_sel_all.setFixedSize(78, 22)
        btn_sel_all.clicked.connect(self._select_all_tracks)
        hbox_meta_bottom.addWidget(btn_sel_all)

        btn_desel_all = CyberChamferButton("DESELECT", variant="action_neutral")
        btn_desel_all.setFixedSize(72, 22)
        btn_desel_all.clicked.connect(self._deselect_all_tracks)
        hbox_meta_bottom.addWidget(btn_desel_all)

        btn_sel_missing = CyberChamferButton("ONLY NEW", variant="action_cyan")
        btn_sel_missing.setFixedSize(74, 22)
        btn_sel_missing.setToolTip("Select only tracks not already downloaded in the target folder")
        btn_sel_missing.clicked.connect(self._select_missing_only)
        hbox_meta_bottom.addWidget(btn_sel_missing)

        hbox_meta_bottom.addStretch(1)

        self.lbl_sel_count = QLabel("0 selected", self.card_meta)
        self.lbl_sel_count.setStyleSheet(
            "color: #4ade80; font-family: 'Rajdhani', sans-serif; font-size: 11px; font-weight: bold; background: transparent; border: none;"
        )
        hbox_meta_bottom.addWidget(self.lbl_sel_count)

        meta_card_layout.addLayout(hbox_meta_bottom)
        body_layout.addWidget(self.card_meta)

        # --- SCROLLABLE TRACK SELECTION LIST (FILLS ALL AVAILABLE VERTICAL SPACE) ---
        self.scroll_tracks = QScrollArea(body_widget)
        self.scroll_tracks.setWidgetResizable(True)
        self.track_list_widget = QWidget()
        self.track_list_widget.setStyleSheet("background: transparent;")
        self.track_list_layout = QVBoxLayout(self.track_list_widget)
        self.track_list_layout.setContentsMargins(4, 4, 4, 4)
        self.track_list_layout.setSpacing(3)

        self.lbl_placeholder = QLabel("Paste a Spotify link above and click Fetch Songs to preview tracks.")
        self.lbl_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_placeholder.setStyleSheet("color: #71717a; font-style: italic; font-size: 11px; padding: 30px 0;")
        self.track_list_layout.addWidget(self.lbl_placeholder)

        self.track_list_layout.addStretch(1)
        self.scroll_tracks.setWidget(self.track_list_widget)
        body_layout.addWidget(self.scroll_tracks, 1)

        # --- DESTINATION & DOWNLOAD BAR ---
        hbox_dest = QHBoxLayout()
        hbox_dest.setSpacing(5)
        lbl_dest = QLabel("SAVE TO:")
        lbl_dest.setStyleSheet("color: #5EF6FF; font-family: 'Rajdhani', sans-serif; font-size: 10px; font-weight: 800; letter-spacing: 0.8px;")
        hbox_dest.addWidget(lbl_dest)

        self.edit_dest_folder = QLineEdit(DEFAULT_MUSIC_DIR)
        self.edit_dest_folder.setFixedHeight(24)
        hbox_dest.addWidget(self.edit_dest_folder, 1)

        btn_browse = CyberChamferButton("BROWSE", variant="action_neutral")
        btn_browse.setFixedSize(68, 24)
        btn_browse.clicked.connect(self._on_browse_dest)
        hbox_dest.addWidget(btn_browse)
        body_layout.addLayout(hbox_dest)

        # Download progress bar
        self.progress_bar = QProgressBar(body_widget)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setVisible(False)
        body_layout.addWidget(self.progress_bar)

        # Status & Action Buttons (reserve 52px on right for protocol badge)
        hbox_actions = QHBoxLayout()
        hbox_actions.setContentsMargins(0, 0, 52, 0)
        hbox_actions.setSpacing(8)

        self.lbl_status = QLabel("Ready to import.", body_widget)
        self.lbl_status.setStyleSheet("color: #a1a1aa; font-size: 10px; background: transparent;")
        self.lbl_status.setWordWrap(True)
        hbox_actions.addWidget(self.lbl_status, 1)

        self.btn_download_selected = CyberChamferButton("Download Selected Tracks", variant="action_green")
        self.btn_download_selected.setFixedSize(206, 28)
        self.btn_download_selected.setEnabled(False)
        self.btn_download_selected.clicked.connect(self._on_download_toggle_clicked)
        hbox_actions.addWidget(self.btn_download_selected)
        body_layout.addLayout(hbox_actions)

        container_layout.addWidget(body_widget, 1)

    def _switch_input_tab(self, mode: str):
        """Switches between direct Spotify link pasting and curated playlists."""
        if mode == "link":
            self.input_stack.setCurrentIndex(0)
            self.btn_tab_link.set_variant("tab_cyan")
            self.btn_tab_saved.set_variant("tab_idle")
        else:
            self.input_stack.setCurrentIndex(1)
            self.btn_tab_saved.set_variant("tab_purple")
            self.btn_tab_link.set_variant("tab_idle")

    def _on_paste_url_clicked(self):
        """Pastes text from clipboard into URL input and auto-triggers fetch if URL present."""
        clip = QApplication.clipboard().text().strip()
        if clip:
            self.edit_url.setText(clip)
            if "spotify.com" in clip.lower():
                self._on_fetch_url_clicked()

    def _wire_signals(self):
        """Connects service signals to dialog UI updates."""
        self.spotify_service.playlist_loaded.connect(self._on_playlist_loaded)
        self.spotify_service.saved_playlists_updated.connect(self._populate_saved_playlists)
        self.spotify_service.fetch_error.connect(self._on_fetch_error)

    # -------------------------------------------------------------------------
    # Saved Playlists Management
    # -------------------------------------------------------------------------

    def _populate_saved_playlists(self, playlist_list: Optional[list] = None):
        items = playlist_list if playlist_list is not None else self.spotify_service.get_saved_playlists()
        self.combo_saved_playlists.clear()
        for p in items:
            cat = p.get("category", "Playlists")
            name = p.get("name", "Playlist")
            label = f"[{cat}] {name}"
            self.combo_saved_playlists.addItem(label, p.get("url"))

    def _on_load_saved_clicked(self):
        url = self.combo_saved_playlists.currentData()
        if not url:
            self.lbl_status.setText("Please select a playlist from the dropdown.")
            return
        self.edit_url.setText(url)
        self._switch_input_tab("link")
        self._on_fetch_url_clicked()

    def _on_save_custom_playlist(self):
        name = self.edit_custom_name.text().strip()
        url = self.edit_custom_url.text().strip()
        if not name or not url:
            self.lbl_status.setText("Please enter both a playlist name and Spotify URL.")
            return
        ok = self.spotify_service.save_custom_playlist(name, url)
        if ok:
            self.edit_custom_name.clear()
            self.edit_custom_url.clear()
            self.lbl_status.setText(f"Saved '{name}' to your playlist library!")
            self._populate_saved_playlists()

    # -------------------------------------------------------------------------
    # UI Actions & Callbacks
    # -------------------------------------------------------------------------

    def _on_fetch_url_clicked(self):
        url = self.edit_url.text().strip()
        if not url:
            self.lbl_status.setText("Please paste a Spotify URL first.")
            self.lbl_status.setStyleSheet("color: #f87171; font-size: 10px;")
            return
        self.lbl_status.setText("Fetching playlist tracks from Spotify...")
        self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 10px;")
        self.btn_fetch_url.setEnabled(False)
        self.btn_fetch_url.setText("Fetching...")
        if hasattr(self, "lbl_header_pill"):
            self.lbl_header_pill.setText("FETCHING")
            self.lbl_header_pill.setStyleSheet(
                "color: #fbbf24; border: 1px solid #f59e0b; background-color: #451a03; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;"
            )
        threading.Thread(target=self._async_fetch_url, args=(url,), daemon=True).start()

    def _async_fetch_url(self, url: str):
        try:
            self.spotify_service.fetch_playlist_by_url(url)
        finally:
            try:
                self.bridge.fetch_finished.emit()
            except (RuntimeError, AttributeError):
                pass

    def _on_fetch_finished(self):
        self.btn_fetch_url.setEnabled(True)
        self.btn_fetch_url.setText("Fetch Songs")

    def _on_delete_saved_clicked(self):
        url = self.combo_saved_playlists.currentData()
        if not url:
            return
        if self.spotify_service.delete_saved_playlist(url):
            self.lbl_status.setText("Removed custom playlist bookmark.")
            self._populate_saved_playlists()

    def _is_track_on_disk(self, target_dir: str, artist: str, title: str) -> bool:
        if not target_dir or not os.path.isdir(target_dir):
            return False
        needle_title = re.sub(r"[^a-z0-9]", "", title.lower())
        needle_pair = re.sub(r"[^a-z0-9]", "", f"{artist}{title}".lower())
        try:
            for fn in os.listdir(target_dir):
                if fn.lower().endswith(SUPPORTED_AUDIO_EXTS):
                    norm_fn = re.sub(r"[^a-z0-9]", "", os.path.splitext(fn)[0].lower())
                    if needle_pair and needle_pair in norm_fn:
                        return True
                    if needle_title and len(needle_title) >= 4 and needle_title in norm_fn:
                        return True
        except Exception:
            pass
        return False

    def _filter_loaded_tracks(self, text: str):
        q = text.strip().lower()
        for chk, t, orig_lbl in self._track_checkboxes:
            if not q:
                chk.setVisible(True)
            else:
                hay = f"{t.get('artist', '')} {t.get('title', '')} {orig_lbl}".lower()
                chk.setVisible(q in hay)

    def _select_missing_only(self):
        target_dir = self.edit_dest_folder.text().strip() or DEFAULT_MUSIC_DIR
        for chk, t, _ in self._track_checkboxes:
            on_disk = self._is_track_on_disk(target_dir, t.get("artist", ""), t.get("title", ""))
            chk.setChecked(not on_disk)

    def _on_playlist_loaded(self, data: dict):
        self._active_playlist_data = data
        title = data.get("title", "Playlist")
        owner = data.get("owner", "")
        tracks = data.get("tracks", [])

        meta_str = f"\"{title}\" ({len(tracks)} tracks)"
        if owner:
            meta_str += f" - by {owner}"
        self.lbl_playlist_meta.setText(meta_str)
        self.lbl_playlist_meta.setStyleSheet("color: #5EF6FF; font-size: 11px; font-weight: bold;")

        if hasattr(self, "lbl_header_pill"):
            self.lbl_header_pill.setText(f"{len(tracks)} TRACKS")
            self.lbl_header_pill.setStyleSheet(
                "color: #4ade80; border: 1px solid #22c55e; background-color: #052e16; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;"
            )

        # Set suggested subfolder in music/
        safe_name = re.sub(r'[\\/*?:"<>|]', "", title).strip() or "Spotify Playlist"
        suggested_dir = os.path.join(DEFAULT_MUSIC_DIR, safe_name)
        self.edit_dest_folder.setText(suggested_dir)

        # Clear old track items
        self._track_checkboxes.clear()
        while self.track_list_layout.count() > 1:
            child = self.track_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Remove placeholder if present
        if hasattr(self, "lbl_placeholder") and self.lbl_placeholder:
            self.lbl_placeholder.setVisible(False)

        # Populate tracks with high-density styled rows
        if hasattr(self, "edit_track_filter"):
            self.edit_track_filter.clear()
        on_disk_count = 0
        for t in tracks:
            track_no = t.get("track_number", 0)
            prefix = f"{track_no:02d}. " if track_no else ""
            on_disk = self._is_track_on_disk(suggested_dir, t.get("artist", ""), t.get("title", ""))
            if on_disk:
                on_disk_count += 1
            disk_tag = "  [On Disk]" if on_disk else ""
            label_txt = f"{prefix}{t['artist']} - {t['title']}  ({t.get('duration_str', '')}){disk_tag}"
            chk = QCheckBox(label_txt)
            chk.setChecked(True)
            border_c = "#22c55e" if on_disk else "#27272f"
            chk.setStyleSheet(
                f"QCheckBox {{ color: #f4f4f5; font-size: 11px; padding: 3px 6px; background-color: #10111a; border: 1px solid {border_c}; border-radius: 3px; }}"
                "QCheckBox:hover { border-color: #5EF6FF; background-color: #161826; }"
                "QCheckBox::indicator { width: 13px; height: 13px; border-radius: 2px; border: 1px solid rgba(247, 80, 73, 140); background: #08080e; }"
                "QCheckBox::indicator:checked { background: #20E070; border-color: #4ade80; }"
            )
            chk.toggled.connect(self._update_selected_count)
            self._track_checkboxes.append((chk, t, label_txt))
            # Insert before final stretch
            self.track_list_layout.insertWidget(self.track_list_layout.count() - 1, chk)

        self._update_selected_count()
        self.btn_download_selected.setEnabled(len(tracks) > 0)
        extra = f" ({on_disk_count} already on disk)" if on_disk_count else ""
        self.lbl_status.setText(f"Found {len(tracks)} songs{extra}! Ready to download.")
        self.lbl_status.setStyleSheet("color: #4ade80; font-size: 10px; font-weight: 600;")

    def _on_fetch_error(self, err: str):
        self.lbl_status.setText(err)
        self.lbl_status.setStyleSheet("color: #f87171; font-size: 10px;")
        if hasattr(self, "lbl_header_pill"):
            self.lbl_header_pill.setText("ERROR")
            self.lbl_header_pill.setStyleSheet(
                "color: #f87171; border: 1px solid #ef4444; background-color: #450a0a; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;"
            )

    def _select_all_tracks(self):
        for chk, _, _ in self._track_checkboxes:
            if not chk.isHidden():
                chk.setChecked(True)

    def _deselect_all_tracks(self):
        for chk, _, _ in self._track_checkboxes:
            if not chk.isHidden():
                chk.setChecked(False)

    def _update_selected_count(self):
        sel_count = sum(1 for chk, _, _ in self._track_checkboxes if chk.isChecked())
        self.lbl_sel_count.setText(f"{sel_count} selected")
        if not self._is_batch_downloading:
            self.btn_download_selected.setEnabled(sel_count > 0)
            self.btn_download_selected.setText(f"Download Selected Tracks ({sel_count} Songs)")

    def _on_browse_dest(self):
        chosen = QFileDialog.getExistingDirectory(self, "Select Download Destination Folder", self.edit_dest_folder.text())
        if chosen:
            self.edit_dest_folder.setText(chosen)

    # -------------------------------------------------------------------------
    # Batch Downloader Execution & Live Progress
    # -------------------------------------------------------------------------

    def _on_download_toggle_clicked(self):
        if self._is_batch_downloading:
            # User clicked Stop Download
            self._stop_download_flag = True
            self.lbl_status.setText("Stopping download...")
            self.lbl_status.setStyleSheet("color: #fb923c; font-size: 10px;")
            self.btn_download_selected.setEnabled(False)
            return

        selected_items = [
            (idx, chk, t, lbl)
            for idx, (chk, t, lbl) in enumerate(self._track_checkboxes)
            if chk.isChecked()
        ]
        if not selected_items:
            self.lbl_status.setText("Please select at least one song to download.")
            return

        target_dir = self.edit_dest_folder.text().strip() or DEFAULT_MUSIC_DIR
        os.makedirs(target_dir, exist_ok=True)

        self._is_batch_downloading = True
        self._stop_download_flag = False

        # Switch button to Red Cancel state
        self.btn_download_selected.setText("Stop Download")
        self.btn_download_selected.set_variant("action_red")
        self.btn_download_selected.setEnabled(True)

        if hasattr(self, "lbl_header_pill"):
            self.lbl_header_pill.setText("DOWNLOADING")
            self.lbl_header_pill.setStyleSheet(
                "color: #38bdf8; border: 1px solid #0284c7; background-color: #082f49; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;"
            )

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"Starting download (0/{len(selected_items)})...")

        self.lbl_status.setText(f"Starting download of {len(selected_items)} tracks...")
        self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 10px;")

        self._worker_thread = threading.Thread(
            target=self._batch_download_worker,
            args=(selected_items, target_dir),
            daemon=True,
        )
        self._worker_thread.start()

    def _batch_download_worker(self, items: list[tuple], target_dir: str):
        total = len(items)
        success = 0
        failed = 0

        downloader = getattr(self.panel, "downloader", None)

        for step_num, (item_idx, chk, t, orig_lbl) in enumerate(items, start=1):
            if self._stop_download_flag:
                break

            query = t["query"]
            pct = int(((step_num - 1) / max(1, total)) * 100)

            # Signal UI that track has started
            try:
                self.bridge.track_started.emit(step_num, total, query, pct)
            except (RuntimeError, AttributeError):
                break

            def _live_cb(msg: str, s=step_num):
                try:
                    self.bridge.live_progress.emit(s, total, msg)
                except (RuntimeError, AttributeError):
                    pass

            dl_ok = False
            try:
                if downloader:
                    dl_ok = downloader.download_sync_query(
                        query,
                        target_dir,
                        progress_cb=_live_cb,
                        cancel_check=lambda: self._stop_download_flag,
                        track_info=t,
                    )
                else:
                    log.warning("No downloader instance found on panel.")
            except Exception as e:
                log.warning("Failed to download track %s: %s", query, e)

            if dl_ok:
                success += 1
            else:
                failed += 1

            try:
                self.bridge.track_completed.emit(item_idx, dl_ok)
            except (RuntimeError, AttributeError):
                break

            # Polite pacing between downloads to avoid burst rate limits
            if step_num < total and not self._stop_download_flag:
                import time
                time.sleep(0.8)

        # Batch finished notification via thread-safe signal
        try:
            self.bridge.batch_finished.emit(success, failed, target_dir, self._stop_download_flag)
        except (RuntimeError, AttributeError):
            pass

    # -------------------------------------------------------------------------
    # Thread-Safe Signal Slots (Executed on Main Qt GUI Thread)
    # -------------------------------------------------------------------------

    def _on_track_started(self, step_num: int, total: int, query: str, pct: int):
        self.progress_bar.setValue(pct)
        self.progress_bar.setFormat(f"Downloading track {step_num}/{total} ({pct}%)")
        self.lbl_status.setText(f"[{step_num}/{total}] Searching: {query}...")
        self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 10px;")

    def _on_live_progress(self, step_num: int, total: int, msg: str):
        self.lbl_status.setText(f"[{step_num}/{total}] {msg}")
        pct_match = re.search(r"(\d+(?:\.\d+)?)%", msg)
        if pct_match:
            sub_pct = float(pct_match.group(1))
            overall_pct = int(((step_num - 1) / total + (sub_pct / 100.0) / total) * 100)
            self.progress_bar.setValue(min(99, max(0, overall_pct)))
            self.progress_bar.setFormat(f"Track {step_num}/{total} - {msg}")

    def _on_track_completed(self, item_idx: int, is_success: bool):
        if 0 <= item_idx < len(self._track_checkboxes):
            chk, _, orig_lbl = self._track_checkboxes[item_idx]
            if is_success:
                chk.setText(f"[Saved] {orig_lbl}")
                chk.setStyleSheet(
                    "QCheckBox { color: #4ade80; font-size: 11px; padding: 3px 6px; background-color: #052e16; border: 1px solid #22c55e; border-radius: 4px; }"
                )
            else:
                chk.setText(f"[Skipped] {orig_lbl}")
                chk.setStyleSheet(
                    "QCheckBox { color: #71717a; font-size: 11px; padding: 3px 6px; background-color: #18181b; border: 1px solid #27272a; border-radius: 4px; }"
                )

    def _on_batch_complete(self, success: int, failed: int, target_dir: str, was_stopped: bool):
        self._is_batch_downloading = False
        self._stop_download_flag = False

        self.btn_download_selected.setText("Download Selected Tracks")
        self.btn_download_selected.set_variant("action_green")
        self.btn_download_selected.setEnabled(True)
        self._update_selected_count()

        if was_stopped:
            self.progress_bar.setFormat("Download Stopped")
            msg = f"Download stopped. {success} tracks saved."
            self.lbl_status.setText(msg)
            self.lbl_status.setStyleSheet("color: #fb923c; font-weight: bold; font-size: 10px;")
            if hasattr(self, "lbl_header_pill"):
                self.lbl_header_pill.setText("STOPPED")
                self.lbl_header_pill.setStyleSheet(
                    "color: #fb923c; border: 1px solid #f97316; background-color: #431407; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;"
                )
        else:
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("Complete! (100%)")
            msg = f"Completed! {success} downloaded successfully."
            if failed > 0:
                msg += f" ({failed} skipped or failed)"
            self.lbl_status.setText(msg)
            self.lbl_status.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 10px;")
            if hasattr(self, "lbl_header_pill"):
                self.lbl_header_pill.setText("SYNCED")
                self.lbl_header_pill.setStyleSheet(
                    "color: #4ade80; border: 1px solid #22c55e; background-color: #052e16; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;"
                )

        # Write/Update playlist.m3u8 in sequential Spotify playlist order
        if success > 0:
            try:
                from song_downloader import sanitize_filename
                m3u_path = os.path.join(target_dir, "playlist.m3u8")
                lines = ["#EXTM3U\n"]
                for chk, t, _ in self._track_checkboxes:
                    t_artist = str(t.get("artist") or "").strip()
                    t_title = str(t.get("title") or "").strip()
                    track_num = t.get("track_number")
                    total_tracks = t.get("total_tracks", 0)
                    prefix = ""
                    if track_num and total_tracks > 1:
                        pad = max(2, len(str(total_tracks)))
                        prefix = f"{int(track_num):0{pad}d}. "
                    stem = sanitize_filename(f"{prefix}{t_artist} - {t_title}")
                    opus_name = f"{stem}.opus"
                    if not os.path.exists(os.path.join(target_dir, opus_name)):
                        old_name = f"{sanitize_filename(f'{t_artist} - {t_title}')}.opus"
                        if os.path.exists(os.path.join(target_dir, old_name)):
                            opus_name = old_name
                        else:
                            continue
                    dur_s = int(t.get("duration_ms", 0) / 1000)
                    lines.append(f"#EXTINF:{dur_s},{t_artist} - {t_title}\n{opus_name}\n")
                with open(m3u_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
            except Exception as exc:
                log.warning("Could not write playlist.m3u8: %s", exc)

        # Automatically refresh Talia's player playlist and switch to target folder
        if success > 0 and self.panel and hasattr(self.panel, "refresh_playlist"):
            try:
                if hasattr(self.panel, "audio_engine") and self.panel.audio_engine:
                    if self.panel.audio_engine.folder_path != target_dir:
                        if hasattr(self.panel.audio_engine, 'switch_folder'):
                            self.panel.audio_engine.switch_folder(target_dir)
                        elif hasattr(self.panel.audio_engine, 'set_folder'):
                            self.panel.audio_engine.set_folder(target_dir)
                self.panel.refresh_playlist()
                if hasattr(self.panel, "populate_playlist_ui"):
                    self.panel.populate_playlist_ui()
            except Exception as e:
                log.warning("Could not auto-refresh playlist: %s", e)

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def reject(self):
        self.hide()
