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
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import DEFAULT_MUSIC_DIR, PROJECT_ROOT
from ui_theme import SHARED_PANEL_STYLE
from ui_widgets import create_section_header

log = logging.getLogger("SpotifyDialog")


class DownloadBridge(QObject):
    """Thread-safe Qt signal bridge between background download worker and main GUI thread."""

    track_started = pyqtSignal(int, int, str, int)   # idx, total, query, pct
    live_progress = pyqtSignal(int, int, str)         # idx, total, msg
    track_completed = pyqtSignal(int, bool)           # item_idx, is_success
    batch_finished = pyqtSignal(int, int, str, bool)  # success, failed, target_dir, was_stopped


class SpotifySyncDialog(QDialog):
    """Cyberpunk modal dialog for importing playlists from Spotify with zero developer keys."""

    def __init__(self, panel, parent=None):
        super().__init__(parent or panel)
        self.panel = panel
        self.spotify_service = panel.spotify_service

        self.setWindowTitle("Spotify Sync - Import Playlists")
        self.resize(560, 640)
        self.setWindowFlags(Qt.WindowType.Dialog)
        self.setStyleSheet(SHARED_PANEL_STYLE)

        self._active_playlist_data: Optional[dict] = None
        self._track_checkboxes: list[tuple[QCheckBox, dict, str]] = []  # (checkbox, track_dict, orig_label)
        self._is_batch_downloading = False
        self._stop_download_flag = False

        # Thread-safe Signal Bridge
        self.bridge = DownloadBridge()
        self.bridge.track_started.connect(self._on_track_started)
        self.bridge.live_progress.connect(self._on_live_progress)
        self.bridge.track_completed.connect(self._on_track_completed)
        self.bridge.batch_finished.connect(self._on_batch_complete)

        self.init_ui()
        self._wire_signals()
        self._populate_saved_playlists()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(10)

        # Header title
        lbl_title = QLabel("SPOTIFY PLAYLIST SYNC")
        lbl_title.setStyleSheet(
            "color: #10b981; font-family: 'Rajdhani', sans-serif; font-size: 18px; font-weight: bold; letter-spacing: 1px;"
        )
        main_layout.addWidget(lbl_title)

        lbl_desc = QLabel("Import songs from Spotify into Talia. No developer keys or account logins required.")
        lbl_desc.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        lbl_desc.setWordWrap(True)
        main_layout.addWidget(lbl_desc)

        # Tabs: 0 = Link Import (Zero Setup), 1 = Saved & Curated Playlists
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3f3f46; background-color: #18181b; border-radius: 6px; }
            QTabBar::tab { background: #27272a; color: #a1a1aa; padding: 6px 14px; font-size: 11px; font-weight: 600; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
            QTabBar::tab:selected { background: #10b981; color: #ffffff; }
        """)

        # --- TAB 1: PASTE URL (ZERO SETUP) ---
        tab_url = QWidget()
        url_layout = QVBoxLayout(tab_url)
        url_layout.setContentsMargins(12, 10, 12, 10)
        url_layout.setSpacing(8)

        lbl_url_inst = QLabel("Paste any Spotify Playlist, Album, or Track link:")
        lbl_url_inst.setStyleSheet("color: #f4f4f5; font-size: 11px; font-weight: 600;")
        url_layout.addWidget(lbl_url_inst)

        hbox_input = QHBoxLayout()
        self.edit_url = QLineEdit()
        self.edit_url.setPlaceholderText("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M...")
        hbox_input.addWidget(self.edit_url, 1)

        self.btn_fetch_url = QPushButton("Fetch Songs")
        self.btn_fetch_url.setStyleSheet(
            "background-color: #059669; color: #ffffff; font-weight: bold; padding: 6px 14px; border-radius: 4px;"
        )
        self.btn_fetch_url.clicked.connect(self._on_fetch_url_clicked)
        hbox_input.addWidget(self.btn_fetch_url)
        url_layout.addLayout(hbox_input)
        self.tabs.addTab(tab_url, "Paste Spotify Link")

        # --- TAB 2: SAVED & CURATED PLAYLISTS ---
        tab_saved = QWidget()
        saved_layout = QVBoxLayout(tab_saved)
        saved_layout.setContentsMargins(12, 10, 12, 10)
        saved_layout.setSpacing(8)

        lbl_saved_inst = QLabel("Choose from curated playlists or your saved personal links:")
        lbl_saved_inst.setStyleSheet("color: #f4f4f5; font-size: 11px; font-weight: 600;")
        saved_layout.addWidget(lbl_saved_inst)

        hbox_combo = QHBoxLayout()
        self.combo_saved_playlists = QComboBox()
        self.combo_saved_playlists.setStyleSheet(
            "background-color: #27272a; color: #f4f4f5; padding: 4px 8px; border: 1px solid #3f3f46; border-radius: 4px; font-size: 11px;"
        )
        hbox_combo.addWidget(self.combo_saved_playlists, 1)

        btn_load_saved = QPushButton("Load Selected")
        btn_load_saved.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; font-weight: bold; padding: 5px 12px; border-radius: 4px; font-size: 11px;"
        )
        btn_load_saved.clicked.connect(self._on_load_saved_clicked)
        hbox_combo.addWidget(btn_load_saved)
        saved_layout.addLayout(hbox_combo)

        # Add custom playlist section
        hbox_add = QHBoxLayout()
        self.edit_custom_name = QLineEdit()
        self.edit_custom_name.setPlaceholderText("Playlist Name (e.g. My Favorites)")
        self.edit_custom_name.setStyleSheet("font-size: 10px; max-width: 140px;")
        hbox_add.addWidget(self.edit_custom_name)

        self.edit_custom_url = QLineEdit()
        self.edit_custom_url.setPlaceholderText("Paste Spotify Playlist URL to save")
        self.edit_custom_url.setStyleSheet("font-size: 10px;")
        hbox_add.addWidget(self.edit_custom_url, 1)

        btn_save_link = QPushButton("Save Link")
        btn_save_link.setStyleSheet("padding: 4px 8px; font-size: 10px;")
        btn_save_link.clicked.connect(self._on_save_custom_playlist)
        hbox_add.addWidget(btn_save_link)
        saved_layout.addLayout(hbox_add)

        self.tabs.addTab(tab_saved, "Saved & Curated Playlists")
        main_layout.addWidget(self.tabs)

        # --- PLAYLIST PREVIEW & TRACK SELECTION ---
        main_layout.addWidget(create_section_header("Tracks in Playlist"))

        # Playlist Info summary
        self.lbl_playlist_meta = QLabel("No playlist loaded yet.")
        self.lbl_playlist_meta.setStyleSheet("color: #a1a1aa; font-size: 11px; font-weight: 600;")
        main_layout.addWidget(self.lbl_playlist_meta)

        # Selection toggles
        hbox_toggles = QHBoxLayout()
        btn_sel_all = QPushButton("Select All")
        btn_sel_all.setStyleSheet("padding: 3px 8px; font-size: 10px;")
        btn_sel_all.clicked.connect(self._select_all_tracks)
        hbox_toggles.addWidget(btn_sel_all)

        btn_desel_all = QPushButton("Deselect All")
        btn_desel_all.setStyleSheet("padding: 3px 8px; font-size: 10px;")
        btn_desel_all.clicked.connect(self._deselect_all_tracks)
        hbox_toggles.addWidget(btn_desel_all)
        hbox_toggles.addStretch(1)

        self.lbl_sel_count = QLabel("0 selected")
        self.lbl_sel_count.setStyleSheet("color: #10b981; font-size: 11px; font-weight: bold;")
        hbox_toggles.addWidget(self.lbl_sel_count)
        main_layout.addLayout(hbox_toggles)

        # Scrollable track checkboxes container
        self.scroll_tracks = QScrollArea()
        self.scroll_tracks.setWidgetResizable(True)
        self.scroll_tracks.setStyleSheet(
            "background-color: #121215; border: 1px solid #27272a; border-radius: 4px;"
        )
        self.track_list_widget = QWidget()
        self.track_list_layout = QVBoxLayout(self.track_list_widget)
        self.track_list_layout.setContentsMargins(8, 8, 8, 8)
        self.track_list_layout.setSpacing(4)
        self.track_list_layout.addStretch(1)
        self.scroll_tracks.setWidget(self.track_list_widget)
        main_layout.addWidget(self.scroll_tracks, 1)

        # --- DESTINATION & DOWNLOAD BAR ---
        hbox_dest = QHBoxLayout()
        lbl_dest = QLabel("Save to:")
        lbl_dest.setStyleSheet("color: #a1a1aa; font-size: 11px; font-weight: 600;")
        hbox_dest.addWidget(lbl_dest)

        self.edit_dest_folder = QLineEdit(DEFAULT_MUSIC_DIR)
        self.edit_dest_folder.setStyleSheet("font-size: 11px;")
        hbox_dest.addWidget(self.edit_dest_folder, 1)

        btn_browse = QPushButton("Browse...")
        btn_browse.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        btn_browse.clicked.connect(self._on_browse_dest)
        hbox_dest.addWidget(btn_browse)
        main_layout.addLayout(hbox_dest)

        # Download progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #3f3f46; border-radius: 4px; background: #18181b; height: 18px; text-align: center; color: #f4f4f5; font-size: 10px; font-weight: bold; }
            QProgressBar::chunk { background-color: #10b981; border-radius: 3px; }
        """)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # Status & Action Buttons
        hbox_actions = QHBoxLayout()
        self.lbl_status = QLabel("Ready to import.")
        self.lbl_status.setStyleSheet("color: #71717a; font-size: 10px; font-style: italic;")
        self.lbl_status.setWordWrap(True)
        hbox_actions.addWidget(self.lbl_status, 1)

        self.btn_download_selected = QPushButton("Download Selected Tracks")
        self.btn_download_selected.setEnabled(False)
        self.btn_download_selected.setStyleSheet(
            "background-color: #059669; color: #ffffff; font-weight: bold; padding: 8px 18px; border-radius: 4px;"
        )
        self.btn_download_selected.clicked.connect(self._on_download_toggle_clicked)
        hbox_actions.addWidget(self.btn_download_selected)
        main_layout.addLayout(hbox_actions)

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
            return
        self.lbl_status.setText("Fetching playlist tracks from Spotify...")
        self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 10px;")
        self.btn_fetch_url.setEnabled(False)
        threading.Thread(target=self._async_fetch_url, args=(url,), daemon=True).start()

    def _async_fetch_url(self, url: str):
        self.spotify_service.fetch_playlist_by_url(url)
        self.btn_fetch_url.setEnabled(True)

    def _on_playlist_loaded(self, data: dict):
        self._active_playlist_data = data
        title = data.get("title", "Playlist")
        owner = data.get("owner", "")
        tracks = data.get("tracks", [])

        meta_str = f"\"{title}\" ({len(tracks)} tracks)"
        if owner:
            meta_str += f" - by {owner}"
        self.lbl_playlist_meta.setText(meta_str)

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

        # Populate tracks
        for t in tracks:
            label_txt = f"{t['artist']} - {t['title']}  ({t.get('duration_str', '')})"
            chk = QCheckBox(label_txt)
            chk.setChecked(True)
            chk.setStyleSheet("color: #f4f4f5; font-size: 11px;")
            chk.toggled.connect(self._update_selected_count)
            self._track_checkboxes.append((chk, t, label_txt))
            # Insert before final stretch
            self.track_list_layout.insertWidget(self.track_list_layout.count() - 1, chk)

        self._update_selected_count()
        self.btn_download_selected.setEnabled(len(tracks) > 0)
        self.lbl_status.setText(f"Found {len(tracks)} songs! Ready to download.")
        self.lbl_status.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 600;")

    def _on_fetch_error(self, err: str):
        self.lbl_status.setText(err)
        self.lbl_status.setStyleSheet("color: #f87171; font-size: 10px;")

    def _select_all_tracks(self):
        for chk, _, _ in self._track_checkboxes:
            chk.setChecked(True)

    def _deselect_all_tracks(self):
        for chk, _, _ in self._track_checkboxes:
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
            self.lbl_status.setStyleSheet("color: #fb923c; font-size: 11px;")
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
        self.btn_download_selected.setStyleSheet(
            "background-color: #dc2626; color: #ffffff; font-weight: bold; padding: 8px 18px; border-radius: 4px;"
        )
        self.btn_download_selected.setEnabled(True)

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"Starting download (0/{len(selected_items)})...")

        self.lbl_status.setText(f"Starting download of {len(selected_items)} tracks...")
        self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 11px;")

        threading.Thread(
            target=self._batch_download_worker,
            args=(selected_items, target_dir),
            daemon=True,
        ).start()

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

            # Polite pacing between downloads to avoid YouTube burst bot rate limits
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
        self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 11px;")

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
                chk.setStyleSheet("color: #4ade80; font-size: 11px;")
            else:
                chk.setText(f"[Skipped] {orig_lbl}")
                chk.setStyleSheet("color: #71717a; font-size: 11px;")

    def _on_batch_complete(self, success: int, failed: int, target_dir: str, was_stopped: bool):
        self._is_batch_downloading = False
        self._stop_download_flag = False

        self.btn_download_selected.setText("Download Selected Tracks")
        self.btn_download_selected.setStyleSheet(
            "background-color: #059669; color: #ffffff; font-weight: bold; padding: 8px 18px; border-radius: 4px;"
        )
        self.btn_download_selected.setEnabled(True)
        self._update_selected_count()

        if was_stopped:
            self.progress_bar.setFormat("Download Stopped")
            msg = f"Download stopped. {success} tracks saved."
            self.lbl_status.setText(msg)
            self.lbl_status.setStyleSheet("color: #fb923c; font-weight: bold; font-size: 11px;")
        else:
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("Complete! (100%)")
            msg = f"Completed! {success} downloaded successfully."
            if failed > 0:
                msg += f" ({failed} skipped or failed)"
            self.lbl_status.setText(msg)
            self.lbl_status.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 11px;")

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
