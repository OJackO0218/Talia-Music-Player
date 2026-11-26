"""Playlist, queue, and track context menu behaviour for the control panel."""

import logging
import os
import random
import re
import shutil
import subprocess
import sys
from typing import Optional, Tuple

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from config import portable_path, resolve_path

log = logging.getLogger("Talia.PlaylistPanel")


def extract_primary_artist(raw_artist: str) -> str:
    """
    Extracts primary artist name, ignoring featured credits and collaborations.
    Handles 'feat.', 'ft.', 'featuring', '&', 'x', and commas case-insensitively.
    Example: 'Eminem feat. Juice WRLD' -> 'Eminem'.
    """
    if not raw_artist:
        return ""
    # Strip any parenthetical / bracketed featured credits e.g. (feat. ...) or [ft. ...]
    cleaned = re.sub(
        r"(?i)\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring)\b[^\)\]]*[\)\]]",
        "",
        raw_artist,
    ).strip()
    # Match inline delimiters: feat., ft., featuring, &, x, or comma
    tokens = re.split(
        r"(?i)(?:\s+(?:feat\.?|ft\.?|featuring|&|x)\s+|\s*,\s*)",
        cleaned,
    )
    if tokens and tokens[0].strip():
        return tokens[0].strip()
    return cleaned or raw_artist.strip()



class TrackRowWidget(QFrame):
    """Sleek track item widget with index, title, play count, favorite button, and + Queue button."""

    def __init__(
        self,
        item: QListWidgetItem,
        list_widget: QListWidget,
        panel,
        index: int,
        orig_idx: int,
        filename: str,
        subfolder: str,
        path: str,
        is_current: bool = False,
        play_count: int = 0,
        is_fav: bool = False,
        is_checked: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.item = item
        self.list_widget = list_widget
        self.panel = panel
        self.index = index
        self.orig_idx = orig_idx
        self.path = path
        self.is_current = is_current
        self.play_count = play_count
        self.is_fav = is_fav

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("trackRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(8)

        # Batch Selection Checkbox (hidden by default unless in selection mode)
        self.chk_batch = QCheckBox()
        self.chk_batch.setChecked(is_checked)
        self.chk_batch.setToolTip("Select for batch delete / playlist actions")
        self.chk_batch.setStyleSheet("""
            QCheckBox::indicator {
                width: 13px;
                height: 13px;
                border: 1px solid #3f3f46;
                border-radius: 2px;
                background-color: #202024;
            }
            QCheckBox::indicator:checked {
                background-color: #5EF6FF;
                border-color: #5EF6FF;
            }
        """)
        self.chk_batch.toggled.connect(self._on_batch_toggled)
        is_selection_mode = is_checked or bool(getattr(self.panel, "is_batch_selection_mode", False))
        self.chk_batch.setVisible(is_selection_mode)
        layout.addWidget(self.chk_batch)

        # Track number (kept hidden to match 1:1 Figma Song_Buttons design)
        self.lbl_idx = QLabel(f"{index:02d}")
        self.lbl_idx.hide()

        # Song title & artist layout matching Figma Song_Buttons
        vbox = QVBoxLayout()
        vbox.setContentsMargins(2, 0, 0, 0)
        vbox.setSpacing(1)

        base_name = os.path.splitext(filename)[0]
        cleaned = re.sub(r"^\d{1,3}(?:[\.\-_]|\s+-)\s*", "", base_name).strip()
        artist_part = ""
        title_part = cleaned
        for sep in [" - ", " – ", " — "]:
            if sep in cleaned:
                parts = cleaned.split(sep, 1)
                artist_part = parts[0].strip()
                title_part = parts[1].strip()
                break
        if not artist_part and panel and hasattr(panel, "get_track_primary_artist"):
            artist_part = panel.get_track_primary_artist(path)
            if artist_part == "Unknown Artist":
                artist_part = ""
        if artist_part and (".." in artist_part or "/" in artist_part or "\\" in artist_part):
            artist_part = ""

        self.lbl_title = QLabel(title_part or cleaned or filename)
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lbl_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_title.setToolTip(path)
        vbox.addWidget(self.lbl_title)

        self.lbl_sub = QLabel(artist_part)
        self.lbl_sub.setFont(QFont("Segoe UI", 8))
        vbox.addWidget(self.lbl_sub)
        layout.addLayout(vbox, 1)

        # Right side: Play count badge and Favourite Heart (matching Figma layout)
        hbox_right = QHBoxLayout()
        hbox_right.setContentsMargins(0, 0, 0, 0)
        hbox_right.setSpacing(6)

        self.lbl_play_count = QLabel(f"{play_count}")
        self.lbl_play_count.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.lbl_play_count.setToolTip(f"Played {play_count} times")
        hbox_right.addWidget(self.lbl_play_count, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_fav = QPushButton("♥" if is_fav else "♡")
        self.btn_fav.setFont(QFont("Segoe UI Symbol", 11, QFont.Weight.Bold))
        self.btn_fav.setToolTip("Remove from favourites" if is_fav else "Add to favourites")
        self.btn_fav.setFixedSize(24, 24)
        self.btn_fav.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fav.clicked.connect(self._on_fav_clicked)
        hbox_right.addWidget(self.btn_fav, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(hbox_right)

        # + Queue Button (kept hidden to match 1:1 Figma design while retaining functionality)
        self.btn_q = QPushButton("+")
        self.btn_q.setFixedSize(22, 22)
        self.btn_q.clicked.connect(self._on_queue_clicked)
        self.btn_q.hide()

        self._update_row_appearance()

    def set_checkbox_visible(self, visible: bool):
        self.chk_batch.setVisible(visible)

    def _update_row_appearance(self):
        if self.is_current:
            # Active / Currently playing: Bright cyan background matching Figma Song_Buttons
            self.setStyleSheet("""
                QFrame#trackRow, QWidget#trackRow {
                    background-color: #00F5FF;
                    border: 1px solid #00F5FF;
                    border-radius: 2px;
                }
            """)
            self.lbl_idx.setStyleSheet("color: #000000; font-family: 'Share Tech Mono', 'Consolas', monospace; font-size: 11px; font-weight: bold;")
            self.lbl_title.setStyleSheet("color: #000000; font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 12px; text-transform: uppercase;")
            self.lbl_sub.setStyleSheet("color: #1a1a24; font-family: 'Rajdhani', sans-serif; font-size: 9px; font-weight: 600; text-transform: uppercase;")
            self.lbl_play_count.setStyleSheet("color: #000000; font-family: 'Share Tech Mono', 'Consolas', monospace; font-size: 11px; font-weight: bold;")
            if self.is_fav:
                self.btn_fav.setText("♥")
                self.btn_fav.setStyleSheet("QPushButton { background: transparent; color: #000000; border: none; font-size: 16px; font-weight: bold; }")
            else:
                self.btn_fav.setText("♡")
                self.btn_fav.setStyleSheet("QPushButton { background: transparent; color: #000000; border: none; font-size: 16px; font-weight: bold; }")
        else:
            # Normal state: Figma Song_Buttons (dark sleek row with subtle coral/dark border)
            self.setStyleSheet("""
                QFrame#trackRow, QWidget#trackRow {
                    background-color: rgba(28, 28, 38, 0.75);
                    border: 1px solid rgba(247, 80, 73, 45);
                    border-radius: 2px;
                }
                QFrame#trackRow:hover, QWidget#trackRow:hover {
                    background-color: rgba(247, 80, 73, 0.15);
                    border-color: rgba(247, 80, 73, 140);
                }
            """)
            self.lbl_idx.setStyleSheet("color: #747474; font-family: 'Share Tech Mono', 'Consolas', monospace; font-size: 11px;")
            self.lbl_title.setStyleSheet("color: #ff8a84; font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 12px; text-transform: uppercase;")
            self.lbl_sub.setStyleSheet("color: #8b8b9e; font-family: 'Rajdhani', sans-serif; font-size: 9px; font-weight: 600; text-transform: uppercase;")
            self.lbl_play_count.setStyleSheet("color: #00F5FF; font-family: 'Share Tech Mono', 'Consolas', monospace; font-size: 11px; font-weight: bold;")
            self._update_fav_style()

    def _update_fav_style(self):
        if self.is_fav:
            self.btn_fav.setText("♥")
            self.btn_fav.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #ff8a84;
                    border: none;
                    font-size: 15px;
                    font-weight: bold;
                    padding: 0px;
                }
                QPushButton:hover {
                    color: #ffffff;
                }
            """)
        else:
            self.btn_fav.setText("♡")
            self.btn_fav.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #a0a0b8;
                    border: none;
                    font-size: 15px;
                    padding: 0px;
                }
                QPushButton:hover {
                    color: #ff8a84;
                }
            """)

    def _on_fav_clicked(self):
        if self.panel and hasattr(self.panel, "toggle_favourite"):
            self.is_fav = self.panel.toggle_favourite(self.path)
            self._update_row_appearance()

    def _on_batch_toggled(self, checked: bool):
        if self.panel and hasattr(self.panel, "on_track_batch_toggled"):
            self.panel.on_track_batch_toggled(self.path, checked)

    def update_play_count(self, count: int):
        self.play_count = count
        self.lbl_play_count.setText(f"{count}")
        self._update_row_appearance()

    def set_current(self, is_cur: bool):
        self.is_current = is_cur
        self._update_row_appearance()

    def _on_queue_clicked(self):
        if self.panel and hasattr(self.panel, "audio_engine"):
            self.panel.audio_engine.add_to_queue(self.path)
            self.panel.refresh_queue_ui()
            if hasattr(self.panel, "save_settings"):
                self.panel.save_settings()
            # Tactile visual feedback
            self.btn_q.setText("✓")
            self.btn_q.setStyleSheet("""
                QPushButton {
                    background-color: #059669;
                    color: #ffffff;
                    border: 1px solid #10b981;
                    border-radius: 3px;
                    font-weight: bold;
                    font-size: 11px;
                }
            """)
            QTimer.singleShot(700, self._reset_queue_btn)

    def _reset_queue_btn(self):
        self.btn_q.setText("+")
        self.btn_q.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #a1a1aa;
                border: 1px solid #3f3f46;
                border-radius: 3px;
                font-weight: bold;
                font-size: 12px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #3b82f6;
                color: #ffffff;
                border-color: #60a5fa;
            }
        """)

    def enterEvent(self, event):
        try:
            from cyber_sfx import get_cyber_sfx
            get_cyber_sfx().play_hover()
        except Exception:
            pass
        super().enterEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.item and self.list_widget:
                self.list_widget.setCurrentItem(self.item)
            try:
                from cyber_sfx import get_cyber_sfx
                get_cyber_sfx().play_click()
            except Exception:
                pass
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            try:
                from cyber_sfx import get_cyber_sfx
                get_cyber_sfx().play_click()
            except Exception:
                pass
            if self.panel:
                if self.orig_idx >= 0:
                    self.panel.audio_engine.play_index(self.orig_idx)
                else:
                    self.panel.audio_engine.load_file(self.path, auto_play=True)
                self.panel.sync_play_state()
                self.panel.refresh_queue_ui()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        if self.panel and hasattr(self.panel, "show_track_context_menu_for_item"):
            self.panel.show_track_context_menu_for_item(self.item, event.globalPos())
            event.accept()
        else:
            super().contextMenuEvent(event)


def normalize_search_term(s: str) -> str:
    """Normalizes text for fuzzy search: lowercases and strips punctuation like ', -, =, _, ., etc."""
    if not s:
        return ""
    s = s.lower().replace("’", "'").replace("‘", "'").replace("`", "'")
    s = s.replace("'", "")
    s = re.sub(r"[-=_.,/\\|+:;!?~()\[\]{}\"]", " ", s)
    return " ".join(s.split())


class PlaylistPanelMixin:
    """Playlist and queue UI mixed into ControlPanel."""

    @staticmethod
    def extract_primary_artist(raw_artist: str) -> str:
        return extract_primary_artist(raw_artist)

    def get_track_primary_artist(self, path: str) -> str:
        """Extracts primary artist name from a track's filename or directory structure."""
        fn = os.path.splitext(os.path.basename(path))[0]
        cleaned = re.sub(r"^\d{1,3}(?:[\.\-_]|\s+-)\s*", "", fn).strip()
        raw_artist = ""
        for sep in [" - ", " – ", " — "]:
            if sep in cleaned:
                raw_artist = cleaned.split(sep)[0].strip()
                break
        if not raw_artist:
            try:
                base_dir = getattr(self.audio_engine, "folder_path", "")
                rel = os.path.relpath(path, base_dir) if base_dir else ""
                sub = os.path.dirname(rel)
                if sub and sub != ".":
                    raw_artist = os.path.basename(sub).strip()
            except Exception:
                pass
        if not raw_artist:
            raw_artist = "Unknown Artist"
        return extract_primary_artist(raw_artist)

    def get_music_subfolders(self) -> dict[str, list[str]]:
        """
        Scans active library tracks for subfolder groupings (e.g. Hamilton, Forza Pulse, Downloaded Songs).
        Returns a dictionary mapping subfolder name -> list of track paths.
        """
        base_dir = getattr(self.audio_engine, "folder_path", None)
        if not base_dir or not os.path.exists(base_dir):
            return {}
        subfolders: dict[str, list[str]] = {}
        for p in getattr(self.audio_engine, "playlist", []):
            try:
                rel = os.path.relpath(p, base_dir)
                parts = os.path.normpath(rel).split(os.sep)
                if len(parts) > 1 and parts[0] and parts[0] != ".":
                    folder_name = parts[0]
                    if folder_name not in subfolders:
                        subfolders[folder_name] = []
                    subfolders[folder_name].append(p)
            except Exception:
                continue
        return subfolders

    def populate_playlist_ui(self):
        """Refreshes the tracklist widget items with custom row widgets."""
        if hasattr(self, "lbl_folder_path") and self.lbl_folder_path:
            self.lbl_folder_path.setText(f"{self.audio_engine.folder_path}")
        if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "lbl_folder_path"):
            self.settings_dialog.lbl_folder_path.setText(f"{self.audio_engine.folder_path}")
        if hasattr(self, "refresh_folder_switcher"):
            self.refresh_folder_switcher()
        if hasattr(self, "combo_dl_folder"):
            self.refresh_dl_folders()
        if hasattr(self, "refresh_playlist_dropdown"):
            self.refresh_playlist_dropdown()

        base_dir = self.audio_engine.folder_path
        self.list_tracks.clear()
        cur_idx = self.audio_engine.current_index
        cur_path = self.audio_engine.playlist[cur_idx] if 0 <= cur_idx < len(self.audio_engine.playlist) else None

        # 1. Base tracks from active playlist (all tracks, favourites, folder playlists, or custom)
        cur_pl = getattr(self, "current_playlist", "All Tracks")
        if hasattr(self, "radio_mix_bar") and self.radio_mix_bar is not None:
            self.radio_mix_bar.setVisible(cur_pl == "★ Random Mix")
        subfolders = self.get_music_subfolders()
        if cur_pl in ("Favourites", "★ Favourites"):
            tracks = [p for p in self.audio_engine.playlist if self.is_favourite(p)]
        elif cur_pl == "★ Random Mix":
            tracks = (
                self.radio_mix.get_cached_tracks()
                if hasattr(self, "radio_mix") and self.radio_mix
                else []
            )
        elif cur_pl == "Queue":
            tracks = [p for p in getattr(self.audio_engine, "queue", []) if os.path.exists(p)]
        elif cur_pl in subfolders:
            tracks = list(subfolders[cur_pl])
        elif cur_pl != "All Tracks" and hasattr(self, "custom_playlists") and cur_pl in self.custom_playlists:
            tracks = [p for p in self.custom_playlists[cur_pl] if p in self.audio_engine.playlist or os.path.exists(p)]
        else:
            tracks = list(self.audio_engine.playlist)

        # 2. Sorting
        cur_sort = getattr(self, "current_sort", "Default")
        if cur_sort == "Time Added":
            def _get_time_added(p):
                try:
                    return os.path.getmtime(p)
                except Exception:
                    return 0.0
            tracks.sort(key=_get_time_added, reverse=True)
        elif cur_sort == "Alphabetical (A-Z)":
            tracks.sort(key=lambda p: os.path.basename(p).lower())
        elif cur_sort in ("Sort by artist", "Artist"):
            tracks.sort(key=lambda p: (self.get_track_primary_artist(p).lower(), os.path.basename(p).lower()))
        elif cur_sort == "Duration":
            tracks.sort(key=lambda p: self.get_track_duration(p))
        elif cur_sort == "Most Played":
            tracks.sort(key=lambda p: self.get_play_count(p), reverse=True)
        elif cur_sort == "Least Played":
            tracks.sort(key=lambda p: self.get_play_count(p))
        elif cur_sort == "Random":
            if not hasattr(self, "_random_sort_keys") or getattr(self, "_force_new_random_sort", False):
                self._random_sort_keys = {p: random.random() for p in tracks}
                self._force_new_random_sort = False
            tracks.sort(key=lambda p: self._random_sort_keys.get(p, 0.5))
        # "Default" keeps original order in tracks

        selected_batch = getattr(self, "selected_batch_tracks", set())
        playlist_index_map = {p: idx for idx, p in enumerate(self.audio_engine.playlist)}

        self.list_tracks.setUpdatesEnabled(False)
        try:
            for i, path in enumerate(tracks):
                filename = os.path.basename(path)
                try:
                    rel = os.path.relpath(path, base_dir)
                    rel_dir = os.path.dirname(rel)
                    sub_txt = rel_dir.replace("\\", " / ") if rel_dir and rel_dir != "." else ""
                except Exception:
                    sub_txt = ""

                orig_i = playlist_index_map.get(path, -1)
                is_cur = (path == cur_path)
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, orig_i)
                item.setData(Qt.ItemDataRole.UserRole + 1, path)
                item.setData(Qt.ItemDataRole.UserRole + 2, filename.lower())
                item.setData(Qt.ItemDataRole.UserRole + 3, sub_txt.lower())

                row_widget = TrackRowWidget(
                    item=item,
                    list_widget=self.list_tracks,
                    panel=self,
                    index=i + 1,
                    orig_idx=orig_i,
                    filename=filename,
                    subfolder=sub_txt,
                    path=path,
                    is_current=is_cur,
                    play_count=self.get_play_count(path),
                    is_fav=self.is_favourite(path),
                    is_checked=(path in selected_batch),
                )
                item.setSizeHint(QSize(200, 38))
                self.list_tracks.addItem(item)
                self.list_tracks.setItemWidget(item, row_widget)
                if is_cur:
                    self.list_tracks.setCurrentItem(item)
        finally:
            self.list_tracks.setUpdatesEnabled(True)

        search_txt = self.search_input.text() if hasattr(self, "search_input") else ""
        if search_txt:
            self.filter_tracks(search_txt)

        self.refresh_queue_ui()
        self._update_batch_delete_btn()

    def get_play_count(self, path: str) -> int:
        if not path:
            return 0
        counts = getattr(self, "play_counts", {})
        norm = os.path.normpath(path)
        port = portable_path(path)
        resolved = resolve_path(path)
        return int(
            counts.get(norm)
            or counts.get(port)
            or counts.get(path)
            or counts.get(resolved)
            or 0
        )

    def record_track_played(self, path: str) -> int:
        if not path:
            return 0
        norm = os.path.normpath(path)
        port = portable_path(path)
        if not hasattr(self, "play_counts") or not isinstance(self.play_counts, dict):
            self.play_counts = {}
        current = (
            self.play_counts.get(norm)
            or self.play_counts.get(port)
            or self.play_counts.get(path)
            or 0
        )
        new_count = current + 1
        self.play_counts[norm] = new_count
        self.play_counts[port] = new_count
        self.play_counts[path] = new_count
        for r in range(self.list_tracks.count()):
            it = self.list_tracks.item(r)
            if it and it.data(Qt.ItemDataRole.UserRole + 1) == path:
                w = self.list_tracks.itemWidget(it)
                if w and hasattr(w, "update_play_count"):
                    w.update_play_count(new_count)
                break
        if hasattr(self, "save_settings"):
            self.save_settings()
        return new_count

    def is_favourite(self, path: str) -> bool:
        norm = os.path.normpath(path)
        favs = getattr(self, "favourite_tracks", set())
        return norm in favs

    def toggle_favourite(self, path: str) -> bool:
        norm = os.path.normpath(path)
        if not hasattr(self, "favourite_tracks"):
            self.favourite_tracks = set()
        elif isinstance(self.favourite_tracks, list):
            self.favourite_tracks = set(self.favourite_tracks)

        if norm in self.favourite_tracks:
            self.favourite_tracks.remove(norm)
            res = False
        else:
            self.favourite_tracks.add(norm)
            res = True

        try:
            from cyber_sfx import get_cyber_sfx
            get_cyber_sfx().play_click()
        except Exception:
            pass

        if hasattr(self, "save_settings"):
            self.save_settings()

        cur_pl = getattr(self, "current_playlist", "All Tracks")
        if cur_pl in ("Favourites", "★ Favourites"):
            self.populate_playlist_ui()
        return res

    def get_track_duration(self, path: str) -> float:
        if not hasattr(self, "_duration_cache"):
            self._duration_cache = {}
        norm = os.path.normpath(path)
        if norm in self._duration_cache:
            return self._duration_cache[norm]
        dur = 0.0
        if os.path.exists(norm):
            try:
                import soundfile as sf
                info = sf.info(norm)
                dur = float(info.duration)
            except Exception:
                dur = 0.0
        self._duration_cache[norm] = dur
        return dur

    def on_track_batch_toggled(self, path: str, checked: bool):
        if not hasattr(self, "selected_batch_tracks"):
            self.selected_batch_tracks = set()
        if checked:
            self.selected_batch_tracks.add(path)
            self.is_batch_selection_mode = True
        else:
            self.selected_batch_tracks.discard(path)
            if not self.selected_batch_tracks:
                self.is_batch_selection_mode = False
                for r in range(self.list_tracks.count()):
                    it = self.list_tracks.item(r)
                    if it:
                        w = self.list_tracks.itemWidget(it)
                        if w and hasattr(w, "set_checkbox_visible"):
                            w.set_checkbox_visible(False)
        self._update_batch_delete_btn()

    def on_select_all_clicked(self):
        if not hasattr(self, "selected_batch_tracks"):
            self.selected_batch_tracks = set()
        visible_paths = []
        for r in range(self.list_tracks.count()):
            it = self.list_tracks.item(r)
            if it and not it.isHidden():
                p = it.data(Qt.ItemDataRole.UserRole + 1)
                if p:
                    visible_paths.append(p)
        if visible_paths and all(p in self.selected_batch_tracks for p in visible_paths):
            for p in visible_paths:
                self.selected_batch_tracks.discard(p)
            all_checked = False
            self.is_batch_selection_mode = False
        else:
            for p in visible_paths:
                self.selected_batch_tracks.add(p)
            all_checked = True
            self.is_batch_selection_mode = True

        for r in range(self.list_tracks.count()):
            it = self.list_tracks.item(r)
            if it:
                p = it.data(Qt.ItemDataRole.UserRole + 1)
                if p in visible_paths:
                    w = self.list_tracks.itemWidget(it)
                    if w and hasattr(w, "chk_batch"):
                        if hasattr(w, "set_checkbox_visible"):
                            w.set_checkbox_visible(all_checked)
                        w.chk_batch.blockSignals(True)
                        w.chk_batch.setChecked(all_checked)
                        w.chk_batch.blockSignals(False)
        self._update_batch_delete_btn()

    def _update_batch_delete_btn(self):
        if not hasattr(self, "btn_batch_delete"):
            return
        count = len(getattr(self, "selected_batch_tracks", set()))
        if count > 0:
            self.btn_batch_delete.setText(f"DELETE SELECTED ({count})")
        else:
            self.btn_batch_delete.setText("DELETE SELECTED")

    def batch_delete_selected(self):
        if not hasattr(self, "selected_batch_tracks"):
            self.selected_batch_tracks = set()
        targets = set(self.selected_batch_tracks)
        if not targets:
            for it in self.list_tracks.selectedItems():
                p = it.data(Qt.ItemDataRole.UserRole + 1)
                if p:
                    targets.add(p)
        if not targets:
            QMessageBox.information(self, "Batch Delete", "Please check songs to batch delete.")
            return

        reply = QMessageBox.question(
            self,
            "Batch Delete",
            f"Remove {len(targets)} selected song(s) from playlist and library?\n\n(Original audio files will remain safe on disk)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        cur_p = None
        if 0 <= self.audio_engine.current_index < len(self.audio_engine.playlist):
            cur_p = self.audio_engine.playlist[self.audio_engine.current_index]

        self.audio_engine.playlist = [p for p in self.audio_engine.playlist if p not in targets]
        if hasattr(self, "custom_playlists") and isinstance(self.custom_playlists, dict):
            for pl_k in self.custom_playlists:
                self.custom_playlists[pl_k] = [p for p in self.custom_playlists[pl_k] if p not in targets]
        if hasattr(self, "favourite_tracks"):
            self.favourite_tracks = {p for p in self.favourite_tracks if p not in targets}
        self.selected_batch_tracks.clear()

        if cur_p and cur_p in targets:
            if self.audio_engine.playlist:
                self.audio_engine.play_index(0)
            else:
                self.audio_engine.stop()
        else:
            if cur_p in self.audio_engine.playlist:
                self.audio_engine.current_index = self.audio_engine.playlist.index(cur_p)
            else:
                self.audio_engine.current_index = -1

        self.populate_playlist_ui()
        if hasattr(self, "save_settings"):
            self.save_settings()
        self._update_batch_delete_btn()
        log.info(f"[BATCH DELETE] Successfully removed {len(targets)} tracks.")

    def refresh_playlist_dropdown(self):
        if not hasattr(self, "combo_playlist"):
            return
        self.combo_playlist.blockSignals(True)
        cur = getattr(self, "current_playlist", "All Tracks")
        self.combo_playlist.clear()
        self.combo_playlist.addItem("All Tracks")
        self.combo_playlist.addItem("Queue")
        self.combo_playlist.addItem("★ Favourites")
        self.combo_playlist.addItem("★ Random Mix")

        # Automatically add subfolders in music as playlists
        subfolders = self.get_music_subfolders()
        for f_name in sorted(subfolders.keys()):
            self.combo_playlist.addItem(f_name)

        if hasattr(self, "custom_playlists") and isinstance(self.custom_playlists, dict):
            for name in sorted(self.custom_playlists.keys()):
                if name not in subfolders and name not in (
                    "All Tracks",
                    "Queue",
                    "★ Favourites",
                    "Favourites",
                    "★ Random Mix",
                ):
                    self.combo_playlist.addItem(name)
        idx = self.combo_playlist.findText(cur)
        if idx >= 0:
            self.combo_playlist.setCurrentIndex(idx)
        else:
            self.combo_playlist.setCurrentIndex(0)
            self.current_playlist = "All Tracks"
        self.combo_playlist.blockSignals(False)

    def on_playlist_selected(self, name: str):
        try:
            from cyber_sfx import get_cyber_sfx
            get_cyber_sfx().play_tab()
        except Exception:
            pass
        self.current_playlist = name
        self.populate_playlist_ui()
        if hasattr(self, "save_settings"):
            self.save_settings()

    def on_queue_indicator_clicked(self):
        try:
            from cyber_sfx import get_cyber_sfx
            get_cyber_sfx().play_tab()
        except Exception:
            pass
        if getattr(self, "current_playlist", "") == "Queue":
            if hasattr(self, "combo_playlist"):
                self.combo_playlist.setCurrentText("All Tracks")
            else:
                self.on_playlist_selected("All Tracks")
        else:
            if hasattr(self, "combo_playlist"):
                self.combo_playlist.setCurrentText("Queue")
            else:
                self.on_playlist_selected("Queue")

    def on_new_playlist_clicked(self):
        name, ok = QInputDialog.getText(self, "Create Playlist", "Enter new playlist name:")
        if ok and name and name.strip():
            try:
                from cyber_sfx import get_cyber_sfx
                get_cyber_sfx().play_add()
            except Exception:
                pass
            clean_name = name.strip()
            if not hasattr(self, "custom_playlists") or not isinstance(self.custom_playlists, dict):
                self.custom_playlists = {}
            if clean_name not in self.custom_playlists:
                self.custom_playlists[clean_name] = list(getattr(self, "selected_batch_tracks", []))
            self.current_playlist = clean_name
            self.refresh_playlist_dropdown()
            self.populate_playlist_ui()
            if hasattr(self, "save_settings"):
                self.save_settings()

    def group_songs_by_artist(self):
        """
        Prompts for an artist name, matches all library songs by their primary artist name
        (ignoring featured credits like feat., ft., featuring, &, x, commas), and displays them.
        """
        if not self.audio_engine.playlist:
            QMessageBox.information(self, "Group by Artist", "No songs found in the library to group.")
            return

        artist_input, ok = QInputDialog.getText(
            self,
            "Group by Artist",
            "Enter artist name to group songs:",
        )
        if not ok or not artist_input or not artist_input.strip():
            return

        target_raw = artist_input.strip()
        target_primary = extract_primary_artist(target_raw).lower()

        matching_tracks = []
        for path in self.audio_engine.playlist:
            song_primary = self.get_track_primary_artist(path).lower()
            if target_primary == song_primary or target_primary in song_primary:
                matching_tracks.append(path)

        if not matching_tracks:
            QMessageBox.information(
                self,
                "Group by Artist",
                f"No songs found matching artist '{target_raw}'.",
            )
            return

        if not hasattr(self, "custom_playlists") or not isinstance(self.custom_playlists, dict):
            self.custom_playlists = {}

        pl_key = f"Artist: {extract_primary_artist(target_raw)}"
        self.custom_playlists[pl_key] = matching_tracks
        self.current_playlist = pl_key
        self.refresh_playlist_dropdown()
        self.populate_playlist_ui()
        if hasattr(self, "save_settings"):
            self.save_settings()

        QMessageBox.information(
            self,
            "Group by Artist",
            f"Found and grouped {len(matching_tracks)} song(s) by {target_raw} into playlist '{pl_key}'!",
        )

    def delete_current_playlist(self):
        """Deletes the current custom playlist with a confirmation dialog."""
        cur_pl = getattr(self, "current_playlist", "All Tracks")
        subfolders = self.get_music_subfolders()
        if cur_pl in ("All Tracks", "Queue", "★ Favourites") or cur_pl in subfolders:
            QMessageBox.information(
                self,
                "Delete Playlist",
                f"Built-in playlist or music folder '{cur_pl}' cannot be deleted.",
            )
            return

        if not hasattr(self, "custom_playlists") or cur_pl not in self.custom_playlists:
            QMessageBox.information(
                self,
                "Delete Playlist",
                f"Playlist '{cur_pl}' not found.",
            )
            return

        if getattr(QMessageBox.question, "__module__", "") != "PyQt6.QtWidgets":
            reply = QMessageBox.question(
                self,
                "Delete Playlist",
                f"Are you sure you want to delete the playlist '{cur_pl}'?\n\n(Original songs will remain safe in your library.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            confirmed = (reply == QMessageBox.StandardButton.Yes)
        else:
            try:
                from ui_widgets import CyberDeletePlaylistDialog
                dlg = CyberDeletePlaylistDialog(cur_pl, self)
                confirmed = (dlg.exec() == QDialog.DialogCode.Accepted)
            except Exception:
                confirmed = False

        if confirmed:
            try:
                from cyber_sfx import get_cyber_sfx
                get_cyber_sfx().play_delete()
            except Exception:
                pass
            del self.custom_playlists[cur_pl]
            self.current_playlist = "All Tracks"
            self.refresh_playlist_dropdown()
            self.populate_playlist_ui()
            if hasattr(self, "save_settings"):
                self.save_settings()
            log.info(f"[PLAYLIST] Deleted custom playlist: '{cur_pl}'")

    def on_add_songs_to_playlist(self):
        """Allows user to select and add library songs into the current or selected playlist."""
        cur_pl = getattr(self, "current_playlist", "All Tracks")
        if cur_pl in ("All Tracks", "★ Favourites"):
            if not hasattr(self, "custom_playlists") or not self.custom_playlists:
                self.on_new_playlist_clicked()
                return
            items = list(sorted(self.custom_playlists.keys()))
            target_pl, ok = QInputDialog.getItem(
                self, "Add to Playlist", "Select destination playlist:", items, 0, False
            )
            if not ok or not target_pl:
                return
            cur_pl = target_pl

        existing = set(self.custom_playlists.get(cur_pl, []))
        available = [p for p in self.audio_engine.playlist if p not in existing]
        if not available:
            QMessageBox.information(
                self,
                "Add Songs to Playlist",
                f"All songs in your library are already in '{cur_pl}'.",
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Add Songs to '{cur_pl}'")
        dlg.resize(460, 420)
        dlg.setStyleSheet("""
            QDialog { background-color: #18181b; color: #f4f4f5; }
            QListWidget { background-color: #202024; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px; }
            QListWidget::item:selected { background-color: #0284c7; color: #ffffff; }
            QPushButton { background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px; padding: 6px 12px; }
            QPushButton:hover { background-color: #3b82f6; border-color: #3b82f6; }
        """)
        d_layout = QVBoxLayout(dlg)
        lbl = QLabel(f"Select songs to add to '{cur_pl}':")
        lbl.setStyleSheet("font-weight: bold; color: #38bdf8;")
        d_layout.addWidget(lbl)

        lw = QListWidget(dlg)
        lw.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for p in available:
            fn = os.path.basename(p)
            item = QListWidgetItem(fn)
            item.setData(Qt.ItemDataRole.UserRole, p)
            lw.addItem(item)
        d_layout.addWidget(lw)

        btn_box = QHBoxLayout()
        btn_sel_all = QPushButton("Select All")
        btn_sel_all.clicked.connect(lw.selectAll)
        btn_box.addWidget(btn_sel_all)

        btn_add = QPushButton("Add Selected")
        btn_add.setStyleSheet("background-color: #0284c7; font-weight: bold;")
        btn_box.addWidget(btn_add)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(dlg.reject)
        btn_box.addWidget(btn_cancel)
        d_layout.addLayout(btn_box)

        def do_add():
            sel_items = lw.selectedItems()
            if not sel_items:
                return
            to_add = [it.data(Qt.ItemDataRole.UserRole) for it in sel_items if it.data(Qt.ItemDataRole.UserRole)]
            if cur_pl not in self.custom_playlists:
                self.custom_playlists[cur_pl] = []
            for p in to_add:
                if p not in self.custom_playlists[cur_pl]:
                    self.custom_playlists[cur_pl].append(p)
            self.current_playlist = cur_pl
            self.refresh_playlist_dropdown()
            self.populate_playlist_ui()
            if hasattr(self, "save_settings"):
                self.save_settings()
            dlg.accept()
            QMessageBox.information(
                self,
                "Songs Added",
                f"Successfully added {len(to_add)} song(s) to '{cur_pl}'!",
            )

        btn_add.clicked.connect(do_add)
        dlg.exec()

    def on_sort_changed(self, sort_name: str):
        try:
            from cyber_sfx import get_cyber_sfx
            get_cyber_sfx().play_tab()
        except Exception:
            pass
        self.current_sort = sort_name
        if sort_name == "Random":
            self._force_new_random_sort = True
        self.populate_playlist_ui()
        if hasattr(self, "save_settings"):
            self.save_settings()

    def on_sort_activated(self, index: int):
        if hasattr(self, "combo_sort"):
            sort_name = self.combo_sort.itemText(index)
            if sort_name == "Random":
                self._force_new_random_sort = True
                self.populate_playlist_ui()

    def get_active_filtered_tracks(self) -> list[str]:
        """Returns the list of visible track paths in the currently active playlist/filter/sort."""
        tracks = []
        for r in range(self.list_tracks.count()):
            it = self.list_tracks.item(r)
            if it and not it.isHidden():
                p = it.data(Qt.ItemDataRole.UserRole + 1)
                if p:
                    tracks.append(p)
        if not tracks:
            return list(self.audio_engine.playlist)
        return tracks

    def filter_tracks(self, text: str = ""):
        raw_query = (text or "").strip()
        query_lower = raw_query.lower()
        norm_query = normalize_search_term(raw_query)
        query_tokens = norm_query.split() if norm_query else []

        matched = 0
        for i in range(self.list_tracks.count()):
            item = self.list_tracks.item(i)
            if not item:
                continue
            if not raw_query:
                item.setHidden(False)
                matched += 1
            else:
                fn = item.data(Qt.ItemDataRole.UserRole + 2) or ""
                sub = item.data(Qt.ItemDataRole.UserRole + 3) or ""
                # 1. Exact case-insensitive substring match
                match = (query_lower in fn) or (query_lower in sub)
                # 2. Punctuation-insensitive match (ignores ', -, =, etc., like 'Whats up' matching 'What\'s up')
                if not match and norm_query:
                    norm_fn = normalize_search_term(fn)
                    norm_sub = normalize_search_term(sub)
                    if (norm_query in norm_fn) or (norm_query in norm_sub):
                        match = True
                    elif len(query_tokens) > 1 and all(t in norm_fn or t in norm_sub for t in query_tokens):
                        match = True

                item.setHidden(not match)
                if match:
                    matched += 1

        if hasattr(self, "on_filter_results_changed"):
            self.on_filter_results_changed(raw_query, matched)

        if 0 <= self.audio_engine.current_index < len(self.audio_engine.playlist):
            self.lbl_track_title.setText(f"{self.audio_engine.get_current_track_title()}")

    def on_add_selected_to_queue(self):
        item = self.list_tracks.currentItem()
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole + 1)
        if not path:
            orig_idx = item.data(Qt.ItemDataRole.UserRole)
            if orig_idx is not None and 0 <= orig_idx < len(self.audio_engine.playlist):
                path = self.audio_engine.playlist[orig_idx]
        if path:
            self.audio_engine.add_to_queue(path)
            self.refresh_queue_ui()
            if hasattr(self, "save_settings"):
                self.save_settings()

    def toggle_queue_panel(self):
        if getattr(self, "current_playlist", "") == "Queue":
            self.current_playlist = "All Tracks"
        else:
            self.current_playlist = "Queue"
        if hasattr(self, "combo_playlist"):
            idx = self.combo_playlist.findText(self.current_playlist)
            if idx >= 0:
                self.combo_playlist.setCurrentIndex(idx)
        self.populate_playlist_ui()

    def on_queue_rows_moved(self, parent=None, start=0, end=0, destination=None, row=0):
        """Called when user drags and drops to reorder items inside the queue list widget."""
        new_queue = []
        base_dir = self.audio_engine.folder_path
        for r in range(self.list_queue.count()):
            it = self.list_queue.item(r)
            if it:
                p = it.toolTip()
                if p and os.path.exists(p):
                    clean_p = os.path.abspath(os.path.normpath(p))
                    new_queue.append(clean_p)
                    filename = os.path.basename(clean_p)
                    try:
                        rel = os.path.relpath(clean_p, base_dir)
                        rel_dir = os.path.dirname(rel)
                        if rel_dir and rel_dir != ".":
                            clean_dir = rel_dir.replace("\\", " / ")
                            sub_txt = f"  ({clean_dir})"
                        else:
                            sub_txt = ""
                    except Exception:
                        sub_txt = ""
                    it.setText(f"#{r+1:02d}  {filename}{sub_txt}")
        if new_queue:
            self.audio_engine.queue = new_queue
            if hasattr(self, "save_settings"):
                self.save_settings()

    def on_clear_queue_clicked(self):
        self.audio_engine.clear_queue()
        self.refresh_queue_ui()
        if hasattr(self, "save_settings"):
            self.save_settings()

    def refresh_queue_ui(self):
        count = len(getattr(self.audio_engine, "queue", []))
        if hasattr(self, "btn_queue_indicator") and self.btn_queue_indicator is not None:
            if count > 0:
                self.btn_queue_indicator.setText(f"≡ {count}")
                self.btn_queue_indicator.setToolTip(f"Queue: {count} track{'s' if count != 1 else ''} (Click to toggle)")
                self.btn_queue_indicator.show()
            else:
                self.btn_queue_indicator.hide()

        if hasattr(self, "btn_toggle_queue"):
            self.btn_toggle_queue.setText(f"Queue ({count})")
            if count > 0:
                self.btn_toggle_queue.setStyleSheet(
                    "background-color: #1e3a8a; color: #93c5fd; border: 1px solid #3b82f6; font-size: 10px; font-weight: 600; padding: 4px 10px; border-radius: 3px;"
                )
            else:
                self.btn_toggle_queue.setStyleSheet(
                    "background-color: #27272a; color: #a1a1aa; border: 1px solid #3f3f46; font-size: 10px; font-weight: 500; padding: 4px 10px; border-radius: 3px;"
                )
        if hasattr(self, "list_queue"):
            self.list_queue.clear()
            base_dir = self.audio_engine.folder_path
            for i, q_path in enumerate(getattr(self.audio_engine, "queue", [])):
                filename = os.path.basename(q_path)
                try:
                    rel = os.path.relpath(q_path, base_dir)
                    rel_dir = os.path.dirname(rel)
                    if rel_dir and rel_dir != ".":
                        clean_dir = rel_dir.replace("\\", " / ")
                        sub_txt = f"  ({clean_dir})"
                    else:
                        sub_txt = ""
                except Exception:
                    sub_txt = ""
                q_item = QListWidgetItem(f"#{i+1:02d}  {filename}{sub_txt}")
                q_item.setToolTip(q_path)
                self.list_queue.addItem(q_item)

        if getattr(self, "current_playlist", "") == "Queue":
            if not getattr(self, "_refreshing_queue_playlist", False):
                self._refreshing_queue_playlist = True
                try:
                    self.populate_playlist_ui()
                finally:
                    self._refreshing_queue_playlist = False

    def on_queue_item_double_clicked(self, item):
        row = self.list_queue.row(item)
        path = self.audio_engine.remove_from_queue(row)
        if path:
            if path in self.audio_engine.playlist:
                self.audio_engine.play_index(self.audio_engine.playlist.index(path))
            else:
                self.audio_engine.playlist.append(path)
                self.audio_engine.play_index(len(self.audio_engine.playlist) - 1)
                if hasattr(self, "populate_playlist_ui"):
                    self.populate_playlist_ui()
            self.sync_play_state()
            self.refresh_queue_ui()
            if hasattr(self, "save_settings"):
                self.save_settings()

    def show_track_context_menu_for_item(self, item, global_pos):
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole + 1)
        orig_idx = item.data(Qt.ItemDataRole.UserRole)
        if not path and orig_idx is not None and 0 <= orig_idx < len(self.audio_engine.playlist):
            path = self.audio_engine.playlist[orig_idx]
        if not path:
            return
        self._exec_track_menu(path, orig_idx, global_pos)

    def show_track_context_menu(self, pos):
        item = self.list_tracks.itemAt(pos)
        if not item:
            return
        self.show_track_context_menu_for_item(item, self.list_tracks.mapToGlobal(pos))

    def _exec_track_menu(self, path, orig_idx, global_pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #27272a;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                padding: 4px;
                border-radius: 6px;
            }
            QMenu::item {
                padding: 6px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #3b82f6;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #3f3f46;
                margin: 4px 8px;
            }
        """)

        action_play = menu.addAction("Play Now")
        action_save_radio = None
        if (
            hasattr(self, "radio_mix")
            and self.radio_mix
            and self.radio_mix.is_radio_cached_track(path)
        ):
            action_save_radio = menu.addAction("Save Permanently to Library")
        action_queue = menu.addAction("Add to Queue")
        action_play_next = menu.addAction("Play Next in Queue")
        action_party_queue = None
        if hasattr(self, "party_sync") and self.party_sync and self.party_sync.is_connected:
            action_party_queue = menu.addAction("Add to Party Queue")
        menu.addSeparator()

        # Add to Playlist Submenu
        menu_add_pl = menu.addMenu("Add to Playlist")
        if hasattr(self, "custom_playlists") and isinstance(self.custom_playlists, dict):
            for pl_name in sorted(self.custom_playlists.keys()):
                act = menu_add_pl.addAction(pl_name)
                act.setData(("add_to_existing", pl_name))
        menu_add_pl.addSeparator()
        act_new_pl = menu_add_pl.addAction("+ New Playlist...")
        act_new_pl.setData(("new_playlist", None))

        cur_pl = getattr(self, "current_playlist", "All Tracks")
        action_rem_from_pl = None
        if cur_pl not in ("All Tracks", "Queue", "★ Favourites") and hasattr(self, "custom_playlists") and cur_pl in self.custom_playlists:
            action_rem_from_pl = menu.addAction(f"Remove from '{cur_pl}'")
        action_rem_from_queue = None
        if cur_pl == "Queue":
            action_rem_from_queue = menu.addAction("Remove from Queue")

        menu.addSeparator()
        action_calibrate = menu.addAction("Calibrate this song lyric")
        action_move = menu.addAction("Move to Folder...")
        action_duplicate = menu.addAction("Duplicate to Folder...")
        action_open = menu.addAction("Show in Explorer")
        menu.addSeparator()
        is_fav = self.is_favourite(path)
        action_toggle_fav = menu.addAction("Remove from Favourites" if is_fav else "Add to Favourites")
        is_sel = path in getattr(self, "selected_batch_tracks", set())
        action_select = menu.addAction("Deselect Track" if is_sel else "Select Track")
        action_batch_del = menu.addAction("Batch Delete Selected Songs")
        menu.addSeparator()
        action_del_lyric = menu.addAction("Delete Lyric")
        action_del_song = menu.addAction("Remove Song and Lyric")

        selected = menu.exec(global_pos)
        if selected == action_select:
            if not hasattr(self, "selected_batch_tracks"):
                self.selected_batch_tracks = set()
            if path in self.selected_batch_tracks:
                self.selected_batch_tracks.discard(path)
            else:
                self.selected_batch_tracks.add(path)
            self.is_batch_selection_mode = bool(self.selected_batch_tracks)
            for r in range(self.list_tracks.count()):
                it = self.list_tracks.item(r)
                if it:
                    p = it.data(Qt.ItemDataRole.UserRole + 1)
                    w = self.list_tracks.itemWidget(it)
                    if w and hasattr(w, "chk_batch"):
                        if hasattr(w, "set_checkbox_visible"):
                            w.set_checkbox_visible(self.is_batch_selection_mode)
                        w.chk_batch.blockSignals(True)
                        w.chk_batch.setChecked(p in self.selected_batch_tracks)
                        w.chk_batch.blockSignals(False)
            self._update_batch_delete_btn()
        elif selected == action_play:
            if orig_idx is not None and orig_idx >= 0:
                self.audio_engine.play_index(orig_idx)
            else:
                self.audio_engine.load_file(path, auto_play=True)
            self.sync_play_state()
            self.refresh_queue_ui()
        elif action_save_radio is not None and selected == action_save_radio:
            if hasattr(self, "save_radio_track_permanently"):
                self.save_radio_track_permanently(path)
        elif selected == action_toggle_fav:
            self.toggle_favourite(path)
        elif selected == action_batch_del:
            self.batch_delete_selected()
        elif selected and selected.data():
            cmd, target_pl = selected.data()
            if cmd == "add_to_existing":
                targets = [path]
                for bp in getattr(self, "selected_batch_tracks", set()):
                    if bp not in targets:
                        targets.append(bp)
                pl_list = self.custom_playlists.setdefault(target_pl, [])
                added_count = 0
                for p_t in targets:
                    if p_t not in pl_list:
                        pl_list.append(p_t)
                        added_count += 1
                if hasattr(self, "save_settings"):
                    self.save_settings()
                self.populate_playlist_ui()
                log.info(f"[PLAYLIST] Added {added_count} tracks to '{target_pl}'")
            elif cmd == "new_playlist":
                name, ok = QInputDialog.getText(self, "Create Playlist", "Enter new playlist name:")
                if ok and name and name.strip():
                    clean_name = name.strip()
                    targets = [path]
                    for bp in getattr(self, "selected_batch_tracks", set()):
                        if bp not in targets:
                            targets.append(bp)
                    if not hasattr(self, "custom_playlists") or not isinstance(self.custom_playlists, dict):
                        self.custom_playlists = {}
                    self.custom_playlists[clean_name] = targets
                    self.current_playlist = clean_name
                    self.refresh_playlist_dropdown()
                    self.populate_playlist_ui()
                    if hasattr(self, "save_settings"):
                        self.save_settings()
        elif action_rem_from_pl and selected == action_rem_from_pl:
            if cur_pl in self.custom_playlists and path in self.custom_playlists[cur_pl]:
                self.custom_playlists[cur_pl].remove(path)
                self.populate_playlist_ui()
                if hasattr(self, "save_settings"):
                    self.save_settings()
        elif action_rem_from_queue and selected == action_rem_from_queue:
            targets = [path]
            for bp in getattr(self, "selected_batch_tracks", set()):
                if bp not in targets:
                    targets.append(bp)
            for p in targets:
                if hasattr(self.audio_engine, "queue") and p in self.audio_engine.queue:
                    self.audio_engine.queue.remove(p)
            self.refresh_queue_ui()
            if hasattr(self, "save_settings"):
                self.save_settings()
        elif selected == action_queue:
            targets = [path]
            for bp in getattr(self, "selected_batch_tracks", set()):
                if bp not in targets:
                    targets.append(bp)
            for p in targets:
                self.audio_engine.add_to_queue(p)
            self.refresh_queue_ui()
            if hasattr(self, "save_settings"):
                self.save_settings()
            try:
                from cyber_sfx import get_cyber_sfx
                get_cyber_sfx().play_click()
            except Exception:
                pass
        elif selected == action_play_next:
            targets = [path]
            for bp in getattr(self, "selected_batch_tracks", set()):
                if bp not in targets:
                    targets.append(bp)
            for p in reversed(targets):
                self.audio_engine.add_to_queue_next(p)
            self.refresh_queue_ui()
            if hasattr(self, "save_settings"):
                self.save_settings()
            try:
                from cyber_sfx import get_cyber_sfx
                get_cyber_sfx().play_click()
            except Exception:
                pass
        elif action_party_queue and selected == action_party_queue:
            from discord_service import parse_track_info
            raw_fn = os.path.basename(path)
            title, artist = parse_track_info(raw_fn)
            query = f"{artist} - {title}" if artist else title
            self.party_sync.add_to_party_queue(
                title=title,
                artist=artist,
                filename=raw_fn,
                yt_query=query,
            )
        elif selected == action_calibrate:
            self.calibrate_song_lyrics(path)
        elif selected == action_move:
            self.move_track_to_folder(path, orig_idx)
        elif selected == action_duplicate:
            self.duplicate_track_to_folder(path)
        elif selected == action_open:
            self.show_in_explorer(path)
        elif selected == action_del_lyric:
            self.delete_track_lyrics(path)
        elif selected == action_del_song:
            self.delete_track_and_lyrics(path, orig_idx)

    def move_track_to_folder(self, path: str, orig_idx: Optional[int] = None):
        """Prompts user for a destination folder, then moves the audio track and companion lyrics."""
        if not path or not os.path.exists(path):
            self._show_info_dialog("File Not Found", "The selected audio file does not exist on disk.")
            return

        dest_dir = QFileDialog.getExistingDirectory(
            self,
            "Move Track to Folder",
            os.path.dirname(path) or "",
        )
        if not dest_dir:
            return

        dest_dir = os.path.normpath(dest_dir)
        src_dir = os.path.normpath(os.path.dirname(path))
        if dest_dir.lower() == src_dir.lower():
            self._show_info_dialog("Same Directory", "Destination folder is identical to the current folder.")
            return

        file_name = os.path.basename(path)
        dest_audio_path = os.path.join(dest_dir, file_name)

        if os.path.exists(dest_audio_path):
            if not self._confirm_action(
                "Overwrite Existing File?",
                f"A file named '{file_name}' already exists in the destination folder.\nDo you want to overwrite it?",
                danger_text="Overwrite",
            ):
                return

        # Check if the track being moved is currently playing
        norm_target = os.path.normpath(path).lower()
        is_current = False
        cur_idx = self.audio_engine.current_index
        if 0 <= cur_idx < len(self.audio_engine.playlist):
            cur_path = self.audio_engine.playlist[cur_idx]
            if os.path.normpath(cur_path).lower() == norm_target:
                is_current = True

        if is_current:
            self.audio_engine._stop_for_playlist_change()
            self.sync_play_state()
            mgr = (
                getattr(self.audio_engine, "lyrics_manager", None)
                or getattr(self.lyrics_overlay, "lyrics_manager", None)
            )
            if mgr and hasattr(mgr, "clear_lyrics"):
                mgr.clear_lyrics()
            if hasattr(self, "lyrics_overlay") and self.lyrics_overlay:
                if hasattr(self.lyrics_overlay, "reset_lyrics_display"):
                    self.lyrics_overlay.reset_lyrics_display()
                else:
                    self.lyrics_overlay.update()

        if hasattr(self.audio_engine, "_invalidate_preload_cache"):
            self.audio_engine._invalidate_preload_cache()

        # Find companion lyrics (.lrc) before moving audio file
        local_lrc, cached_lrc = self.get_track_lyrics_paths(path)
        base_no_ext = os.path.splitext(file_name)[0]
        dest_lrc_path = os.path.join(dest_dir, f"{base_no_ext}.lrc")

        try:
            shutil.move(path, dest_audio_path)
        except PermissionError:
            self._show_info_dialog(
                "File In Use",
                f"Cannot move '{file_name}' because it is locked by another process.\nPlease stop playback or try again.",
            )
            return
        except Exception as exc:
            self._show_info_dialog("Move Error", f"Failed to move file: {exc}")
            return

        # Move or copy companion lyrics to match new track location
        if local_lrc and os.path.exists(local_lrc):
            try:
                shutil.move(local_lrc, dest_lrc_path)
            except Exception as exc:
                log.warning("Could not move companion lyric file: %s", exc)
        elif cached_lrc and os.path.exists(cached_lrc):
            try:
                shutil.copy2(cached_lrc, dest_lrc_path)
            except Exception as exc:
                log.warning("Could not copy cached lyric file: %s", exc)

        # Update queue references
        if hasattr(self.audio_engine, "queue"):
            self.audio_engine.queue = [
                dest_audio_path if os.path.normpath(q).lower() == norm_target else q
                for q in self.audio_engine.queue
            ]

        self.refresh_tracklist()
        self.refresh_queue_ui()
        log.info("[PLAYLIST] Moved track %s -> %s", path, dest_audio_path)

    def duplicate_track_to_folder(self, path: str):
        """Prompts user for a destination folder, then duplicates the audio track and companion lyrics."""
        if not path or not os.path.exists(path):
            self._show_info_dialog("File Not Found", "The selected audio file does not exist on disk.")
            return

        dest_dir = QFileDialog.getExistingDirectory(
            self,
            "Duplicate Track to Folder",
            os.path.dirname(path) or "",
        )
        if not dest_dir:
            return

        dest_dir = os.path.normpath(dest_dir)
        src_dir = os.path.normpath(os.path.dirname(path))
        file_name = os.path.basename(path)
        base_name, ext = os.path.splitext(file_name)

        if dest_dir.lower() == src_dir.lower():
            # Same folder duplication: generate unique non-conflicting filename
            counter = 1
            dest_name = f"{base_name} (Copy){ext}"
            while os.path.exists(os.path.join(dest_dir, dest_name)):
                counter += 1
                dest_name = f"{base_name} (Copy {counter}){ext}"
            dest_audio_path = os.path.join(dest_dir, dest_name)
            dest_lrc_name = f"{os.path.splitext(dest_name)[0]}.lrc"
        else:
            dest_audio_path = os.path.join(dest_dir, file_name)
            dest_lrc_name = f"{base_name}.lrc"
            if os.path.exists(dest_audio_path):
                if not self._confirm_action(
                    "Overwrite Existing File?",
                    f"A file named '{file_name}' already exists in destination folder.\nDo you want to overwrite it?",
                    danger_text="Overwrite",
                ):
                    return

        try:
            shutil.copy2(path, dest_audio_path)
        except Exception as exc:
            self._show_info_dialog("Duplicate Error", f"Failed to duplicate file: {exc}")
            return

        # Duplicate companion lyrics if present
        local_lrc, cached_lrc = self.get_track_lyrics_paths(path)
        dest_lrc_path = os.path.join(dest_dir, dest_lrc_name)
        if local_lrc and os.path.exists(local_lrc):
            try:
                shutil.copy2(local_lrc, dest_lrc_path)
            except Exception as exc:
                log.warning("Could not copy companion lyric file: %s", exc)
        elif cached_lrc and os.path.exists(cached_lrc):
            try:
                shutil.copy2(cached_lrc, dest_lrc_path)
            except Exception as exc:
                log.warning("Could not copy cached lyric file: %s", exc)

        self.refresh_tracklist()
        log.info("[PLAYLIST] Duplicated track %s -> %s", path, dest_audio_path)

    def calibrate_song_lyrics(self, path: str):
        """Opens the lyric calibration tool loaded directly with the selected song."""
        if hasattr(self, "open_lyric_fetcher"):
            self.open_lyric_fetcher(track_path=path, select_calibrate_tab=True)
        elif hasattr(self, "panel") and hasattr(self.panel, "open_lyric_fetcher"):
            self.panel.open_lyric_fetcher(track_path=path, select_calibrate_tab=True)

    def show_in_explorer(self, target_path: str):
        """Highlights the file in Windows Explorer, or opens containing folder on other OS."""
        if not target_path:
            return
        clean_path = os.path.normpath(os.path.abspath(target_path))
        if sys.platform == "win32":
            if os.path.isfile(clean_path):
                # Passing a raw string to subprocess.Popen bypasses subprocess.list2cmdline quoting
                # which otherwise quotes "/select,path" and causes Windows Explorer to open Documents.
                safe_path = clean_path.replace('"', "")
                subprocess.Popen(f'explorer /select,"{safe_path}"')
            elif os.path.isdir(clean_path):
                os.startfile(clean_path)
            elif os.path.exists(os.path.dirname(clean_path)):
                os.startfile(os.path.dirname(clean_path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", clean_path])
        else:
            folder = clean_path if os.path.isdir(clean_path) else os.path.dirname(clean_path)
            subprocess.Popen(["xdg-open", folder])

    def get_track_lyrics_paths(self, track_path: str) -> Tuple[Optional[str], Optional[str]]:
        """Returns (local_lrc_path, cached_lrc_path) for the given audio track."""
        if not track_path:
            return None, None
        local_lrc = os.path.splitext(track_path)[0] + ".lrc"
        local_found = local_lrc if os.path.exists(local_lrc) else None

        cached_found = None
        mgr = (
            getattr(self.audio_engine, "lyrics_manager", None)
            or getattr(self.lyrics_overlay, "lyrics_manager", None)
        )
        if mgr and getattr(mgr, "cache_dir", ""):
            title = mgr.clean_title(track_path)
            safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", title) + ".lrc"
            cp = os.path.join(mgr.cache_dir, safe_name)
            if os.path.exists(cp):
                cached_found = cp

        return local_found, cached_found

    def _confirm_action(self, title: str, message: str, danger_text: str = "Delete") -> bool:
        """Presents a styled cyberpunk confirmation dialog."""
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(message)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        yes_btn = box.button(QMessageBox.StandardButton.Yes)
        if yes_btn:
            yes_btn.setText(danger_text)
            yes_btn.setStyleSheet(
                "background-color: #ef4444; color: #ffffff; border: 1px solid #dc2626; "
                "padding: 6px 14px; border-radius: 4px; font-weight: bold;"
            )
        no_btn = box.button(QMessageBox.StandardButton.No)
        if no_btn:
            no_btn.setText("Cancel")
            no_btn.setStyleSheet(
                "background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; "
                "padding: 6px 14px; border-radius: 4px;"
            )
        box.setStyleSheet("""
            QMessageBox {
                background-color: #18181b;
                border: 1px solid #3f3f46;
                border-radius: 8px;
            }
            QLabel {
                color: #f4f4f5;
                font-size: 12px;
                padding: 6px;
            }
        """)
        return box.exec() == QMessageBox.StandardButton.Yes

    def _show_info_dialog(self, title: str, message: str):
        """Presents a styled info dialog."""
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(message)
        box.setIcon(QMessageBox.Icon.Information)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        ok_btn = box.button(QMessageBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setStyleSheet(
                "background-color: #3b82f6; color: #ffffff; border: 1px solid #2563eb; "
                "padding: 6px 14px; border-radius: 4px;"
            )
        box.setStyleSheet("""
            QMessageBox {
                background-color: #18181b;
                border: 1px solid #3f3f46;
                border-radius: 8px;
            }
            QLabel {
                color: #f4f4f5;
                font-size: 12px;
                padding: 6px;
            }
        """)
        box.exec()

    def delete_track_lyrics(self, path: str, confirm: bool = True):
        """Prompts for confirmation and deletes local and cached lyric files for the track."""
        if not path:
            return
        local_lrc, cached_lrc = self.get_track_lyrics_paths(path)
        if not local_lrc and not cached_lrc:
            self._show_info_dialog(
                "Delete Lyric",
                f"No lyric file (.lrc) found for:\n\n{os.path.basename(path)}",
            )
            return

        song_name = os.path.basename(path)
        if confirm and not self._confirm_action(
            "Delete Lyric",
            f"Are you sure you want to delete the lyric file for:\n\n{song_name}?",
            danger_text="Delete Lyric",
        ):
            return

        if local_lrc and os.path.exists(local_lrc):
            try:
                os.remove(local_lrc)
            except Exception as exc:
                log.error(f"[LYRICS] Failed to delete local lyric {local_lrc}: {exc}")

        if cached_lrc and os.path.exists(cached_lrc):
            try:
                os.remove(cached_lrc)
            except Exception as exc:
                log.error(f"[LYRICS] Failed to delete cached lyric {cached_lrc}: {exc}")

        # If this track is currently loaded in the lyrics manager, clear display
        mgr = (
            getattr(self.audio_engine, "lyrics_manager", None)
            or getattr(self.lyrics_overlay, "lyrics_manager", None)
        )
        if mgr:
            cur = getattr(mgr, "current_track_path", "")
            if cur and os.path.normpath(cur).lower() == os.path.normpath(path).lower():
                if hasattr(mgr, "clear_lyrics"):
                    mgr.clear_lyrics()
                if hasattr(self, "lyrics_overlay") and self.lyrics_overlay:
                    if hasattr(self.lyrics_overlay, "reset_lyrics_display"):
                        self.lyrics_overlay.reset_lyrics_display()
                    else:
                        self.lyrics_overlay.update()

        log.info(f"[LYRICS] Deleted lyric file(s) for {path}")

    def delete_track_and_lyrics(
        self, path: str, orig_idx: Optional[int] = None, confirm: bool = True
    ):
        """Prompts for confirmation and permanently deletes the song file and any lyric files."""
        if not path or not os.path.exists(path):
            self._show_info_dialog("Delete Song", "Song file does not exist on disk.")
            return

        song_name = os.path.basename(path)
        if confirm and not self._confirm_action(
            "Delete Song & Lyric",
            f"Are you sure you want to permanently delete this song and its lyrics?\n\n{song_name}\n\nThis cannot be undone.",
            danger_text="Delete Song & Lyric",
        ):
            return

        norm_target = os.path.normpath(path).lower()
        is_current = False
        cur_idx = self.audio_engine.current_index
        if 0 <= cur_idx < len(self.audio_engine.playlist):
            cur_path = self.audio_engine.playlist[cur_idx]
            if os.path.normpath(cur_path).lower() == norm_target:
                is_current = True

        was_playing = bool(self.audio_engine.is_playing)

        if is_current:
            self.audio_engine._stop_for_playlist_change()
            self.sync_play_state()
            mgr = (
                getattr(self.audio_engine, "lyrics_manager", None)
                or getattr(self.lyrics_overlay, "lyrics_manager", None)
            )
            if mgr and hasattr(mgr, "clear_lyrics"):
                mgr.clear_lyrics()
            if hasattr(self, "lyrics_overlay") and self.lyrics_overlay:
                if hasattr(self.lyrics_overlay, "reset_lyrics_display"):
                    self.lyrics_overlay.reset_lyrics_display()
                else:
                    self.lyrics_overlay.update()

        if hasattr(self.audio_engine, "_invalidate_preload_cache"):
            self.audio_engine._invalidate_preload_cache()

        self.audio_engine.queue = [
            q for q in self.audio_engine.queue if os.path.normpath(q).lower() != norm_target
        ]
        self.refresh_queue_ui()

        try:
            os.remove(path)
            log.info(f"[AUDIO] Deleted song file: {path}")
        except Exception as exc:
            log.error(f"[AUDIO] Failed to delete audio file {path}: {exc}")
            self._show_info_dialog("Error", f"Could not delete song file:\n\n{exc}")
            return

        local_lrc, cached_lrc = self.get_track_lyrics_paths(path)
        if local_lrc and os.path.exists(local_lrc):
            try:
                os.remove(local_lrc)
            except Exception as exc:
                log.error(f"[LYRICS] Failed to delete local lyric {local_lrc}: {exc}")
        if cached_lrc and os.path.exists(cached_lrc):
            try:
                os.remove(cached_lrc)
            except Exception as exc:
                log.error(f"[LYRICS] Failed to delete cached lyric {cached_lrc}: {exc}")

        self.refresh_tracklist()

        if is_current:
            if self.audio_engine.playlist:
                new_idx = min(
                    max(0, orig_idx if orig_idx is not None else 0),
                    len(self.audio_engine.playlist) - 1,
                )
                if was_playing:
                    self.audio_engine.play_index(new_idx)
                else:
                    self.audio_engine.current_index = new_idx
                    self.audio_engine.load_file(
                        self.audio_engine.playlist[new_idx], auto_play=False
                    )
                self.sync_play_state()
                self.refresh_queue_ui()
            else:
                self.audio_engine.current_index = -1
                if hasattr(self, "lbl_track_title") and self.lbl_track_title:
                    self.lbl_track_title.setText("No tracks in playlist")
                self.sync_play_state()

    def show_queue_context_menu(self, pos):
        item = self.list_queue.itemAt(pos)
        if not item:
            return
        row = self.list_queue.row(item)
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #27272a;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                padding: 4px;
                border-radius: 6px;
            }
            QMenu::item {
                padding: 6px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #3b82f6;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #3f3f46;
                margin: 4px 8px;
            }
        """)

        action_play = menu.addAction("Play Now")
        action_remove = menu.addAction("Remove from Queue")
        action_clear = menu.addAction("Clear Entire Queue")
        menu.addSeparator()
        action_calibrate = menu.addAction("Calibrate this song lyric")
        action_move = menu.addAction("Move to Folder...")
        action_duplicate = menu.addAction("Duplicate to Folder...")
        action_open = menu.addAction("Show in Explorer")
        selected = menu.exec(self.list_queue.mapToGlobal(pos))
        if selected == action_play:
            path = self.audio_engine.remove_from_queue(row)
            if path:
                if path in self.audio_engine.playlist:
                    self.audio_engine.play_index(self.audio_engine.playlist.index(path))
                else:
                    self.audio_engine.playlist.append(path)
                    self.audio_engine.play_index(len(self.audio_engine.playlist) - 1)
                    if hasattr(self, "populate_playlist_ui"):
                        self.populate_playlist_ui()
                self.sync_play_state()
                self.refresh_queue_ui()
                if hasattr(self, "save_settings"):
                    self.save_settings()
        elif selected == action_remove:
            self.audio_engine.remove_from_queue(row)
            self.refresh_queue_ui()
            if hasattr(self, "save_settings"):
                self.save_settings()
        elif selected == action_clear:
            self.audio_engine.clear_queue()
            self.refresh_queue_ui()
            if hasattr(self, "save_settings"):
                self.save_settings()
        elif selected == action_calibrate:
            if 0 <= row < len(self.audio_engine.queue):
                self.calibrate_song_lyrics(self.audio_engine.queue[row])
        elif selected == action_move:
            if 0 <= row < len(self.audio_engine.queue):
                self.move_track_to_folder(self.audio_engine.queue[row])
        elif selected == action_duplicate:
            if 0 <= row < len(self.audio_engine.queue):
                self.duplicate_track_to_folder(self.audio_engine.queue[row])
        elif selected == action_open:
            if 0 <= row < len(self.audio_engine.queue):
                self.show_in_explorer(self.audio_engine.queue[row])
