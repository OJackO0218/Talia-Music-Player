"""Playlist, queue, and track context menu behaviour for the control panel."""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QListWidgetItem, QMenu


class PlaylistPanelMixin:
    """Playlist and queue UI mixed into ControlPanel."""

    def populate_playlist_ui(self):
        """Refreshes the tracklist widget items with search and subfolder display."""
        if hasattr(self, "lbl_folder_path") and self.lbl_folder_path:
            self.lbl_folder_path.setText(f"{self.audio_engine.folder_path}")
        if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "lbl_folder_path"):
            self.settings_dialog.lbl_folder_path.setText(f"{self.audio_engine.folder_path}")
        if hasattr(self, "combo_dl_folder"):
            self.refresh_dl_folders()
        search_txt = self.search_input.text() if hasattr(self, "search_input") else ""
        self.filter_tracks(search_txt)
        self.refresh_queue_ui()

    def filter_tracks(self, text: str = ""):
        query = (text or "").strip().lower()
        base_dir = self.audio_engine.folder_path
        self.list_tracks.clear()
        for i, path in enumerate(self.audio_engine.playlist):
            filename = os.path.basename(path)
            try:
                rel = os.path.relpath(path, base_dir)
                rel_dir = os.path.dirname(rel)
            except Exception:
                rel_dir = ""
            match = (not query) or (query in filename.lower()) or (query in rel_dir.lower())
            if not match:
                continue
            if rel_dir and rel_dir != ".":
                clean_dir = rel_dir.replace("\\", " / ")
                display_text = f"[{i+1:02d}] {filename}  ({clean_dir})"
            else:
                display_text = f"[{i+1:02d}] {filename}"
            item = QListWidgetItem(display_text)
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setData(Qt.ItemDataRole.UserRole + 1, path)
            self.list_tracks.addItem(item)
            if i == self.audio_engine.current_index:
                self.list_tracks.setCurrentItem(item)
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

    def show_track_context_menu(self, pos):
        item = self.list_tracks.itemAt(pos)
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole + 1)
        orig_idx = item.data(Qt.ItemDataRole.UserRole)
        if not path and orig_idx is not None and 0 <= orig_idx < len(self.audio_engine.playlist):
            path = self.audio_engine.playlist[orig_idx]
        if not path:
            return
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

        """)

        action_play = menu.addAction("Play Now")
        action_queue = menu.addAction("Add to Queue")
        action_play_next = menu.addAction("Play Next in Queue")
        menu.addSeparator()
        action_open = menu.addAction("Show in Explorer")
        selected = menu.exec(self.list_tracks.mapToGlobal(pos))
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
        elif selected == action_open:
            import subprocess

            subprocess.run(["explorer", f"/select,{path}"])

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

        """)

        action_play = menu.addAction("Play Now")
        action_remove = menu.addAction("Remove from Queue")
        action_clear = menu.addAction("Clear Entire Queue")
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
