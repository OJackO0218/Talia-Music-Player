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
    QTabWidget, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon, QColor

from fetch_lyrics import (
    get_default_music_dir, scan_and_fetch_folder, fetch_synced_lyrics,
    fetch_lyrics_for_file, SUPPORTED_AUDIO_EXTS
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
