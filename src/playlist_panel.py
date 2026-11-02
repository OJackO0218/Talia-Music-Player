"""Playlist, queue, and track context menu behaviour for the control panel."""

import os

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QSizePolicy,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


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

        self.lbl_title = QLabel(filename)
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
        """)

        action_play = menu.addAction("Play Now")
        action_queue = menu.addAction("Add to Queue")
        action_play_next = menu.addAction("Play Next in Queue")
        menu.addSeparator()
        action_open = menu.addAction("Show in Explorer")
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
