"""YouTube search and download UI behaviour for the control panel."""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog, QListWidgetItem

from config import PROJECT_ROOT, save_settings


class DownloadPanelMixin:
    """Download UI mixed into ControlPanel."""

    def on_dl_search_clicked(self):
        query = self.edit_dl_search.text().strip()
        if not query:
            return
        self.lbl_dl_status.setText("Searching YouTube...")
        self.lbl_dl_status.setStyleSheet("color: #3b82f6; font-size: 11px;")
        self.lbl_dl_status.setVisible(True)
        self.btn_dl_search.setEnabled(False)
        self.btn_dl_search.setText("Searching...")
        self.downloader.search_async(query, limit=5)

    def _on_search_finished(self, results):
        self.btn_dl_search.setEnabled(True)
        self.btn_dl_search.setText("Search")
        self.list_dl_results.clear()
        if not results:
            self.lbl_dl_status.setText(
                "No search results found. Try a different title or paste a YouTube URL."
            )
            self.lbl_dl_status.setStyleSheet("color: #f87171; font-size: 11px;")
            self.list_dl_results.setVisible(False)
            self.btn_dl_action.setVisible(False)
            return
        for r in results:
            title = r.get("title", "Unknown")
            channel = r.get("channel", "Unknown")
            dur_str = r.get("duration_str", "--:--")
            item = QListWidgetItem(f"[{dur_str}] {title} • {channel}")
            item.setData(Qt.ItemDataRole.UserRole, r)
            self.list_dl_results.addItem(item)
        self.list_dl_results.setVisible(True)
        self.list_dl_results.setCurrentRow(0)
        self.btn_dl_action.setVisible(True)
        self.lbl_dl_status.setText(
            f"Found {len(results)} matches. Double-click to add or select & click below."
        )
        self.lbl_dl_status.setStyleSheet("color: #a1a1aa; font-size: 11px;")

    def _on_search_error(self, err_msg):
        self.btn_dl_search.setEnabled(True)
        self.btn_dl_search.setText("Search")
        self.lbl_dl_status.setText(f"Search error: {err_msg}")
        self.lbl_dl_status.setStyleSheet("color: #f87171; font-size: 11px;")
        self.lbl_dl_status.setVisible(True)

    def on_dl_selection_changed(self):
        has_sel = len(self.list_dl_results.selectedItems()) > 0
        self.btn_dl_action.setEnabled(has_sel)

    def on_dl_item_double_clicked(self, item):
        self.on_dl_download_clicked()

    def on_dl_folder_changed(self, index: int):
        if not hasattr(self, "combo_dl_folder"):
            return
        data = self.combo_dl_folder.itemData(index)
        if data == "__BROWSE__":
            current_base = self.audio_engine.folder_path or PROJECT_ROOT
            chosen = QFileDialog.getExistingDirectory(
                self, "Select Destination Folder for Downloads", current_base
            )
            if chosen and os.path.isdir(chosen):
                self.saved_dl_folder = os.path.normpath(chosen)
                self.refresh_dl_folders()
                if not getattr(self, "is_loading_settings", False):
                    cfg = self.get_current_settings_dict()
                    save_settings(cfg)
            else:
                self.refresh_dl_folders()
        elif data:
            self.saved_dl_folder = str(data)
            if not getattr(self, "is_loading_settings", False):
                cfg = self.get_current_settings_dict()
                save_settings(cfg)

    def refresh_dl_folders(self):
        """Populates the download destination folder dropdown with standard and custom locations."""
        if not hasattr(self, "combo_dl_folder"):
            return
        current_selected = getattr(self, "saved_dl_folder", "")
        self.combo_dl_folder.blockSignals(True)
        self.combo_dl_folder.clear()
        music_dir = self.audio_engine.folder_path
        if not music_dir or not os.path.exists(music_dir):
            music_dir = os.path.join(PROJECT_ROOT, "music")
        os.makedirs(music_dir, exist_ok=True)
        default_sub = os.path.normpath(os.path.join(music_dir, "Downloaded Songs"))
        os.makedirs(default_sub, exist_ok=True)

        # 1. Default Downloaded Songs
        self.combo_dl_folder.addItem("📁 Downloaded Songs", default_sub)

        # 2. Main Library Root
        root_name = os.path.basename(os.path.normpath(music_dir)) or "Music"
        self.combo_dl_folder.addItem(f"📁 Library Root ({root_name})", os.path.normpath(music_dir))

        # 3. Existing subfolders in music_dir
        try:
            for item in sorted(os.listdir(music_dir), key=lambda s: s.lower()):
                full_p = os.path.normpath(os.path.join(music_dir, item))
                if os.path.isdir(full_p) and full_p != default_sub:
                    self.combo_dl_folder.addItem(f"📁 {item}", full_p)
        except Exception:
            pass

        # 4. Custom directory if outside music_dir
        if current_selected and os.path.exists(current_selected):
            norm_custom = os.path.normpath(current_selected)
            found = False
            for idx in range(self.combo_dl_folder.count()):
                if os.path.normpath(str(self.combo_dl_folder.itemData(idx))) == norm_custom:
                    found = True
                    break
            if not found:
                custom_name = os.path.basename(norm_custom) or norm_custom
                self.combo_dl_folder.addItem(f"📁 Custom: {custom_name}", norm_custom)

        # 5. Browse option
        self.combo_dl_folder.addItem("➕ Browse Custom Folder...", "__BROWSE__")

        # Select target
        target = (
            os.path.normpath(current_selected)
            if (current_selected and os.path.exists(current_selected))
            else default_sub
        )
        for idx in range(self.combo_dl_folder.count()):
            if os.path.normpath(str(self.combo_dl_folder.itemData(idx))) == target:
                self.combo_dl_folder.setCurrentIndex(idx)
                break
        self.combo_dl_folder.blockSignals(False)

    def on_dl_download_clicked(self):
        items = self.list_dl_results.selectedItems()
        if not items:
            return
        data = items[0].data(Qt.ItemDataRole.UserRole)
        if not data or not data.get("url"):
            return
        url = data.get("url")
        title = data.get("title", "Track")
        target_dir = None
        if hasattr(self, "combo_dl_folder"):
            selected_path = self.combo_dl_folder.currentData()
            if selected_path and selected_path != "__BROWSE__" and os.path.isdir(selected_path):
                target_dir = selected_path
        if not target_dir:
            music_dir = self.audio_engine.folder_path or os.path.join(PROJECT_ROOT, "music")
            target_dir = os.path.join(music_dir, "Downloaded Songs")
        os.makedirs(target_dir, exist_ok=True)
        self.btn_dl_action.setEnabled(False)
        self.btn_dl_search.setEnabled(False)
        folder_label = os.path.basename(target_dir) or "Music"
        self.lbl_dl_status.setText(f"Downloading '{title}' to {folder_label}...")
        self.lbl_dl_status.setStyleSheet("color: #3b82f6; font-size: 11px;")
        self.lbl_dl_status.setVisible(True)
        self.downloader.download_and_sync_async(url, target_dir)

    def _on_download_progress(self, msg):
        self.lbl_dl_status.setText(msg)
        self.lbl_dl_status.setStyleSheet("color: #3b82f6; font-size: 11px;")

    def _on_download_finished(self, success, opus_path, status_msg):
        self.btn_dl_action.setEnabled(True)
        self.btn_dl_search.setEnabled(True)
        if success:
            self.lbl_dl_status.setText(f"✓ {status_msg}")
            self.lbl_dl_status.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: 500;")

            # Automatically refresh playlist to include the new track
            self.audio_engine.refresh_playlist()
            self.refresh_tracklist()
            self.refresh_dl_folders()

            # Highlight the newly downloaded track in list_tracks
            if opus_path and os.path.exists(opus_path):
                norm_opus = os.path.normpath(opus_path)
                existing = [os.path.normpath(p) for p in self.audio_engine.playlist]
                if norm_opus not in existing:
                    self.audio_engine.playlist.append(norm_opus)
                    self.populate_playlist_ui()
                for r in range(self.list_tracks.count()):
                    it = self.list_tracks.item(r)
                    orig_idx = it.data(Qt.ItemDataRole.UserRole)
                    if 0 <= orig_idx < len(self.audio_engine.playlist):
                        if os.path.normpath(self.audio_engine.playlist[orig_idx]) == norm_opus:
                            self.list_tracks.setCurrentRow(r)
                            break
        else:
            self.lbl_dl_status.setText(f"✗ {status_msg}")
            self.lbl_dl_status.setStyleSheet("color: #f87171; font-size: 11px;")
