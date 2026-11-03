"""Playlist, queue, and track context menu behaviour for the control panel."""

import logging
import os
import re
import shutil
import subprocess
import sys
from typing import Optional, Tuple

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger("Talia.PlaylistPanel")


class TrackRowWidget(QWidget):
    """Sleek track item widget with index, title, subfolder tag, and + Queue button."""

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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(6)

        # Track number (e.g. 01)
        self.lbl_idx = QLabel(f"{index:02d}")
        self.lbl_idx.setFixedWidth(22)
        if is_current:
            self.lbl_idx.setStyleSheet("color: #38bdf8; font-family: 'Consolas', monospace; font-size: 11px; font-weight: bold;")
        else:
            self.lbl_idx.setStyleSheet("color: #71717a; font-family: 'Consolas', monospace; font-size: 11px;")
        layout.addWidget(self.lbl_idx)

        # Song title & subfolder
        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(1)

        display_title = re.sub(r"^\d{1,3}(?:[\.\-_]|\s+-)\s*", "", filename).strip()
        self.lbl_title = QLabel(display_title or filename)
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        if is_current:
            self.lbl_title.setStyleSheet("color: #60a5fa; font-weight: bold; font-size: 11px;")
        else:
            self.lbl_title.setStyleSheet("color: #f4f4f5; font-size: 11px;")
        self.lbl_title.setToolTip(path)
        vbox.addWidget(self.lbl_title)

        if subfolder:
            lbl_sub = QLabel(subfolder)
            lbl_sub.setStyleSheet("color: #71717a; font-size: 9px;")
            vbox.addWidget(lbl_sub)

        layout.addLayout(vbox, 1)

        # + Queue Button
        self.btn_q = QPushButton("+")
        self.btn_q.setToolTip("Queue this song")
        self.btn_q.setFixedSize(22, 22)
        self.btn_q.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.btn_q.clicked.connect(self._on_queue_clicked)
        layout.addWidget(self.btn_q)

    def set_current(self, is_cur: bool):
        self.is_current = is_cur
        if is_cur:
            self.lbl_title.setStyleSheet("color: #60a5fa; font-weight: bold; font-size: 11px;")
            self.lbl_idx.setStyleSheet("color: #38bdf8; font-family: 'Consolas', monospace; font-size: 11px; font-weight: bold;")
        else:
            self.lbl_title.setStyleSheet("color: #f4f4f5; font-size: 11px;")
            self.lbl_idx.setStyleSheet("color: #71717a; font-family: 'Consolas', monospace; font-size: 11px;")

    def _on_queue_clicked(self):
        if self.panel and hasattr(self.panel, "audio_engine"):
            self.panel.audio_engine.add_to_queue(self.path)
            self.panel.refresh_queue_ui()
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

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.item and self.list_widget:
                self.list_widget.setCurrentItem(self.item)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.panel:
                self.panel.audio_engine.play_index(self.orig_idx)
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


class PlaylistPanelMixin:
    """Playlist and queue UI mixed into ControlPanel."""

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

        base_dir = self.audio_engine.folder_path
        self.list_tracks.clear()
        cur_idx = self.audio_engine.current_index

        for i, path in enumerate(self.audio_engine.playlist):
            filename = os.path.basename(path)
            try:
                rel = os.path.relpath(path, base_dir)
                rel_dir = os.path.dirname(rel)
                sub_txt = rel_dir.replace("\\", " / ") if rel_dir and rel_dir != "." else ""
            except Exception:
                sub_txt = ""

            is_cur = (i == cur_idx)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setData(Qt.ItemDataRole.UserRole + 1, path)
            item.setData(Qt.ItemDataRole.UserRole + 2, filename.lower())
            item.setData(Qt.ItemDataRole.UserRole + 3, sub_txt.lower())

            row_widget = TrackRowWidget(
                item=item,
                list_widget=self.list_tracks,
                panel=self,
                index=i + 1,
                orig_idx=i,
                filename=filename,
                subfolder=sub_txt,
                path=path,
                is_current=is_cur,
            )
            item.setSizeHint(QSize(200, 36))
            self.list_tracks.addItem(item)
            self.list_tracks.setItemWidget(item, row_widget)
            if is_cur:
                self.list_tracks.setCurrentItem(item)

        search_txt = self.search_input.text() if hasattr(self, "search_input") else ""
        if search_txt:
            self.filter_tracks(search_txt)

        self.refresh_queue_ui()

    def filter_tracks(self, text: str = ""):
        query = (text or "").strip().lower()
        for i in range(self.list_tracks.count()):
            item = self.list_tracks.item(i)
            if not item:
                continue
            if not query:
                item.setHidden(False)
            else:
                fn = item.data(Qt.ItemDataRole.UserRole + 2) or ""
                sub = item.data(Qt.ItemDataRole.UserRole + 3) or ""
                match = (query in fn) or (query in sub)
                item.setHidden(not match)

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
            self.queue_container.setVisible(True)

    def toggle_queue_panel(self):
        self.queue_container.setVisible(not self.queue_container.isVisible())

    def on_clear_queue_clicked(self):
        self.audio_engine.clear_queue()
        self.refresh_queue_ui()

    def refresh_queue_ui(self):
        if not hasattr(self, "btn_toggle_queue"):
            return
        count = len(self.audio_engine.queue)
        self.btn_toggle_queue.setText(f"Queue ({count})")
        if count > 0:
            self.btn_toggle_queue.setStyleSheet(
                "background-color: #1e3a8a; color: #93c5fd; border: 1px solid #3b82f6; font-size: 10px; font-weight: 600; padding: 4px 10px; border-radius: 3px;"
            )
        else:
            self.btn_toggle_queue.setStyleSheet(
                "background-color: #27272a; color: #a1a1aa; border: 1px solid #3f3f46; font-size: 10px; font-weight: 500; padding: 4px 10px; border-radius: 3px;"
            )
        self.list_queue.clear()
        base_dir = self.audio_engine.folder_path
        for i, q_path in enumerate(self.audio_engine.queue):
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

    def on_queue_item_double_clicked(self, item):
        row = self.list_queue.row(item)
        path = self.audio_engine.remove_from_queue(row)
        if path:
            if path in self.audio_engine.playlist:
                self.audio_engine.current_index = self.audio_engine.playlist.index(path)
            self.audio_engine.load_file(path, auto_play=True)
            self.sync_play_state()
            self.refresh_queue_ui()

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
        action_queue = menu.addAction("Add to Queue")
        action_play_next = menu.addAction("Play Next in Queue")
        menu.addSeparator()
        action_calibrate = menu.addAction("Calibrate this song lyric")
        action_move = menu.addAction("Move to Folder...")
        action_duplicate = menu.addAction("Duplicate to Folder...")
        action_open = menu.addAction("Show in Explorer")
        menu.addSeparator()
        action_del_lyric = menu.addAction("Delete Lyric")
        action_del_song = menu.addAction("Remove Song and Lyric")

        selected = menu.exec(global_pos)
        if selected == action_play:
            if orig_idx is not None:
                self.audio_engine.play_index(orig_idx)
            else:
                self.audio_engine.load_file(path, auto_play=True)
            self.sync_play_state()
            self.refresh_queue_ui()
        elif selected == action_queue:
            self.audio_engine.add_to_queue(path)
            self.refresh_queue_ui()
            self.queue_container.setVisible(True)
        elif selected == action_play_next:
            self.audio_engine.add_to_queue_next(path)
            self.refresh_queue_ui()
            self.queue_container.setVisible(True)
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
                    self.audio_engine.current_index = self.audio_engine.playlist.index(path)
                self.audio_engine.load_file(path, auto_play=True)
                self.sync_play_state()
                self.refresh_queue_ui()
        elif selected == action_remove:
            self.audio_engine.remove_from_queue(row)
            self.refresh_queue_ui()
        elif selected == action_clear:
            self.audio_engine.clear_queue()
            self.refresh_queue_ui()
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
