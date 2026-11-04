"""
Talia Party Sync UI Dialog.

Provides a cyberpunk-themed modal interface for hosting or joining
synchronized music listening sessions with friends, including transfer of host
privileges and a shared room queue where everyone can add tracks and the host
(or track author) can manage entries.
"""

import os
import re
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from discord_service import parse_track_info
from party_sync import DEFAULT_RELAY_URL, generate_room_code, get_local_lan_ip
from ui_theme import SHARED_PANEL_STYLE
from ui_widgets import DraggableClampedDialogMixin, create_section_header


class TrackPickerDialog(DraggableClampedDialogMixin, QDialog):
    """Searchable dialog for picking a track from the local library to queue."""

    def __init__(self, playlist: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Track from Library to Party Queue")
        self.resize(420, 480)
        self.setStyleSheet(SHARED_PANEL_STYLE)
        self.playlist = list(playlist)
        self.selected_path: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        lbl = QLabel("Select a track from your library:")
        lbl.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")
        layout.addWidget(lbl)

        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText("Filter songs...")
        self.edit_filter.textChanged.connect(self._filter_tracks)
        layout.addWidget(self.edit_filter)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            "QListWidget { background-color: #121215; border: 1px solid #27272a; border-radius: 4px; padding: 4px; color: #f4f4f5; }"
            "QListWidget::item { padding: 6px; border-radius: 4px; }"
            "QListWidget::item:selected { background-color: #2563eb; color: #ffffff; }"
        )
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget, 1)

        self._populate(self.playlist)

        hbox_btns = QHBoxLayout()
        hbox_btns.addStretch(1)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        hbox_btns.addWidget(btn_cancel)

        self.btn_add = QPushButton("Add to Queue")
        self.btn_add.setStyleSheet(
            "background-color: #059669; color: #ffffff; font-weight: bold; padding: 6px 14px; border-radius: 4px;"
        )
        self.btn_add.clicked.connect(self._on_add_clicked)
        hbox_btns.addWidget(self.btn_add)
        layout.addLayout(hbox_btns)

    def _populate(self, paths: list[str]):
        self.list_widget.clear()
        for p in paths:
            fn = os.path.basename(p)
            title, artist = parse_track_info(fn)
            display = f"{title} - {artist}" if artist != "Talia Music Player" else title
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.list_widget.addItem(item)

    def _filter_tracks(self, text: str):
        query = text.strip().lower()
        if not query:
            self._populate(self.playlist)
            return
        filtered = [
            p for p in self.playlist if query in os.path.basename(p).lower()
        ]
        self._populate(filtered)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        self.selected_path = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def _on_add_clicked(self):
        curr = self.list_widget.currentItem()
        if curr:
            self.selected_path = curr.data(Qt.ItemDataRole.UserRole)
            self.accept()


class PartySyncDialog(DraggableClampedDialogMixin, QDialog):
    """Sleek cyberpunk dialog to host or join real-time listening parties with queue & host transfer."""

    def __init__(self, panel, parent=None):
        super().__init__(parent or panel)
        self.panel = panel
        self.sync_service = panel.party_sync

        self.setWindowTitle("Listen Together - Party Sync")
        self.setMinimumSize(480, 580)
        self.resize(520, 640)
        self.setWindowFlags(Qt.WindowType.Dialog)
        self.setStyleSheet(SHARED_PANEL_STYLE)

        self._generated_code = generate_room_code()
        self.members: list[str] = []
        self.init_ui()
        self._wire_signals()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # Title and header
        lbl_title = QLabel("LISTEN TOGETHER")
        lbl_title.setStyleSheet(
            "color: #38bdf8; font-family: 'Rajdhani', sans-serif; font-size: 18px; font-weight: bold; letter-spacing: 1px;"
        )
        main_layout.addWidget(lbl_title)

        lbl_desc = QLabel("Synchronize playback, lyrics, and shared song queue with friends in real-time.")
        lbl_desc.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        lbl_desc.setWordWrap(True)
        main_layout.addWidget(lbl_desc)

        # Main stacked pages: 0 = Connection Setup, 1 = Active Session
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)

        # --- PAGE 0: CONNECTION SETUP ---
        page_setup = QWidget()
        setup_layout = QVBoxLayout(page_setup)
        setup_layout.setContentsMargins(0, 4, 0, 0)
        setup_layout.setSpacing(10)

        # User Name row
        hbox_user = QHBoxLayout()
        lbl_name = QLabel("Nickname:")
        lbl_name.setStyleSheet("color: #f4f4f5; font-weight: 600; min-width: 70px;")
        hbox_user.addWidget(lbl_name)
        self.edit_user_name = QLineEdit("Listener")
        self.edit_user_name.setPlaceholderText("Enter your display name")
        hbox_user.addWidget(self.edit_user_name)
        setup_layout.addLayout(hbox_user)

        # Relay URL row
        hbox_relay = QHBoxLayout()
        lbl_relay = QLabel("Relay URL:")
        lbl_relay.setStyleSheet("color: #a1a1aa; font-weight: 600; min-width: 70px;")
        hbox_relay.addWidget(lbl_relay)
        self.edit_relay_url = QLineEdit(DEFAULT_RELAY_URL)
        self.edit_relay_url.setPlaceholderText("wss://soft-mongoose-6754.ojacko0218.deno.net")
        hbox_relay.addWidget(self.edit_relay_url)
        setup_layout.addLayout(hbox_relay)

        setup_layout.addWidget(create_section_header("Host a Room"))

        # Room code display row
        hbox_code = QHBoxLayout()
        self.lbl_room_code = QLabel(self._generated_code)
        self.lbl_room_code.setStyleSheet(
            "background-color: #18181b; color: #f472b6; font-family: 'Consolas', monospace; "
            "font-size: 20px; font-weight: bold; padding: 6px 16px; border: 1px solid #e879f9; border-radius: 6px; letter-spacing: 4px;"
        )
        self.lbl_room_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hbox_code.addWidget(self.lbl_room_code, 1)

        btn_regen = QPushButton("Refresh")
        btn_regen.setToolTip("Generate a fresh 5-character room code")
        btn_regen.clicked.connect(self._on_regenerate_code)
        hbox_code.addWidget(btn_regen)

        btn_copy = QPushButton("Copy")
        btn_copy.setToolTip("Copy room code to clipboard")
        btn_copy.clicked.connect(self._on_copy_code)
        hbox_code.addWidget(btn_copy)
        setup_layout.addLayout(hbox_code)

        self.chk_guest_control = QCheckBox("Allow listeners to control playback (Shared DJ)")
        self.chk_guest_control.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        setup_layout.addWidget(self.chk_guest_control)

        self.btn_host = QPushButton("Start Hosting Session")
        self.btn_host.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; font-weight: bold; padding: 8px; border-radius: 4px;"
        )
        self.btn_host.clicked.connect(self._on_host_clicked)
        setup_layout.addWidget(self.btn_host)

        setup_layout.addWidget(create_section_header("Join a Friend's Room"))

        # Join Input row
        hbox_join = QHBoxLayout()
        self.edit_join_code = QLineEdit()
        self.edit_join_code.setPlaceholderText("Enter 5-character Code (e.g. CYBER)")
        self.edit_join_code.setMaxLength(128)
        self.edit_join_code.setStyleSheet("font-family: 'Consolas', monospace; font-size: 13px; font-weight: bold; text-transform: uppercase;")
        hbox_join.addWidget(self.edit_join_code, 1)

        self.btn_join = QPushButton("Join Party")
        self.btn_join.setStyleSheet(
            "background-color: #059669; color: #ffffff; font-weight: bold; padding: 7px 16px; border-radius: 4px;"
        )
        self.btn_join.clicked.connect(self._on_join_clicked)
        hbox_join.addWidget(self.btn_join)
        setup_layout.addLayout(hbox_join)

        self.lbl_join_error = QLabel("")
        self.lbl_join_error.setStyleSheet("color: #f87171; font-size: 11px; font-weight: bold; padding: 2px 0;")
        self.lbl_join_error.setVisible(False)
        self.lbl_join_error.setWordWrap(True)
        setup_layout.addWidget(self.lbl_join_error)

        self.edit_join_code.textChanged.connect(lambda: self.lbl_join_error.setVisible(False))

        setup_layout.addStretch(1)
        self.stack.addWidget(page_setup)

        # --- PAGE 1: ACTIVE SESSION ---
        page_active = QWidget()
        active_layout = QVBoxLayout(page_active)
        active_layout.setContentsMargins(0, 4, 0, 0)
        active_layout.setSpacing(10)

        # Active Session Header Card
        card = QFrame()
        card.setStyleSheet("background-color: #18181b; border: 1px solid #3f3f46; border-radius: 6px; padding: 10px;")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(6)

        # Header row: Connected Code + Copy Code Button
        hbox_card_top = QHBoxLayout()
        self.lbl_active_status = QLabel("Connected: NEON7")
        self.lbl_active_status.setStyleSheet("color: #4ade80; font-size: 14px; font-weight: bold;")
        hbox_card_top.addWidget(self.lbl_active_status, 1)

        self.btn_copy_invite = QPushButton("Copy Code")
        self.btn_copy_invite.setStyleSheet(
            "padding: 4px 12px; font-size: 11px; font-weight: 600; background-color: #27272a; border: 1px solid #3f3f46; border-radius: 4px; color: #f4f4f5;"
        )
        self.btn_copy_invite.clicked.connect(self._on_copy_invite_clicked)
        hbox_card_top.addWidget(self.btn_copy_invite)
        card_layout.addLayout(hbox_card_top)

        self.lbl_active_role = QLabel("Role: Host (Broadcasting playback)")
        self.lbl_active_role.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        card_layout.addWidget(self.lbl_active_role)

        self.lbl_members_count = QLabel("Listeners in party: 1")
        self.lbl_members_count.setStyleSheet("color: #e4e4e7; font-size: 12px; font-weight: 600;")
        card_layout.addWidget(self.lbl_members_count)

        # Host Transfer row (prominently visible to Host)
        self.frame_transfer = QFrame()
        self.frame_transfer.setFixedHeight(44)
        self.frame_transfer.setStyleSheet(
            "background-color: #121215; border: 1px solid #27272a; border-radius: 6px; padding: 3px 8px;"
        )
        transfer_layout = QHBoxLayout(self.frame_transfer)
        transfer_layout.setContentsMargins(6, 2, 6, 2)
        transfer_layout.setSpacing(8)

        lbl_transfer = QLabel("Transfer Host:")
        lbl_transfer.setStyleSheet("color: #c084fc; font-size: 11px; font-weight: 700;")
        transfer_layout.addWidget(lbl_transfer)

        self.combo_members = QComboBox()
        self.combo_members.setFixedHeight(26)
        self.combo_members.setStyleSheet(
            "background-color: #18181b; color: #71717a; border: 1px dashed #3f3f46; border-radius: 4px; padding: 2px 8px; font-size: 11px;"
        )
        self.combo_members.addItem("Waiting for friends to join...")
        self.combo_members.setEnabled(False)
        transfer_layout.addWidget(self.combo_members, 1)

        self.btn_transfer = QPushButton("Make Host")
        self.btn_transfer.setFixedHeight(26)
        self.btn_transfer.setEnabled(False)
        self.btn_transfer.setStyleSheet(
            "background-color: #27272a; color: #71717a; border: 1px solid #3f3f46; padding: 3px 10px; border-radius: 4px; font-size: 11px;"
        )
        self.btn_transfer.clicked.connect(self._on_transfer_clicked)
        transfer_layout.addWidget(self.btn_transfer)
        self.frame_transfer.setVisible(True)
        card_layout.addWidget(self.frame_transfer)

        active_layout.addWidget(card)

        # --- SHARED ROOM QUEUE CARD ---
        card_queue = QFrame()
        card_queue.setStyleSheet("background-color: #18181b; border: 1px solid #3f3f46; border-radius: 6px; padding: 10px;")
        queue_card_layout = QVBoxLayout(card_queue)
        queue_card_layout.setSpacing(8)

        hbox_queue_hdr = QHBoxLayout()
        self.lbl_queue_header = QLabel("ROOM QUEUE (0)")
        self.lbl_queue_header.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px; letter-spacing: 0.5px;")
        hbox_queue_hdr.addWidget(self.lbl_queue_header, 1)

        self.btn_clear_queue = QPushButton("Clear")
        self.btn_clear_queue.setStyleSheet(
            "padding: 2px 8px; font-size: 10px; background-color: #27272a; border: 1px solid #3f3f46; border-radius: 3px; color: #fca5a5;"
        )
        self.btn_clear_queue.clicked.connect(self._on_clear_queue_clicked)
        self.btn_clear_queue.setVisible(False)
        hbox_queue_hdr.addWidget(self.btn_clear_queue)
        queue_card_layout.addLayout(hbox_queue_hdr)

        # Queue Add Input Row
        hbox_add_q = QHBoxLayout()
        hbox_add_q.setSpacing(6)
        self.edit_queue_input = QLineEdit()
        self.edit_queue_input.setPlaceholderText("Enter song name, artist, or YouTube URL...")
        self.edit_queue_input.returnPressed.connect(self._on_add_queue_clicked)
        hbox_add_q.addWidget(self.edit_queue_input, 1)

        self.btn_add_queue = QPushButton("+ Add")
        self.btn_add_queue.setStyleSheet(
            "background-color: #0284c7; color: #ffffff; font-weight: bold; padding: 5px 12px; border-radius: 4px; font-size: 11px;"
        )
        self.btn_add_queue.clicked.connect(self._on_add_queue_clicked)
        hbox_add_q.addWidget(self.btn_add_queue)

        self.btn_queue_library = QPushButton("+ My Library")
        self.btn_queue_library.setStyleSheet(
            "background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; font-weight: 600; padding: 5px 10px; border-radius: 4px; font-size: 11px;"
        )
        self.btn_queue_library.clicked.connect(self._on_add_from_library_clicked)
        hbox_add_q.addWidget(self.btn_queue_library)
        queue_card_layout.addLayout(hbox_add_q)

        # Scrollable Queue List
        self.queue_scroll = QScrollArea()
        self.queue_scroll.setWidgetResizable(True)
        self.queue_scroll.setFixedHeight(140)
        self.queue_scroll.setStyleSheet(
            "QScrollArea { background-color: #121215; border: 1px solid #27272a; border-radius: 4px; }"
            "QWidget { background-color: #121215; }"
        )
        self.queue_container = QWidget()
        self.queue_list_layout = QVBoxLayout(self.queue_container)
        self.queue_list_layout.setContentsMargins(6, 6, 6, 6)
        self.queue_list_layout.setSpacing(4)
        self.queue_scroll.setWidget(self.queue_container)
        queue_card_layout.addWidget(self.queue_scroll)

        active_layout.addWidget(card_queue)

        # Event log
        active_layout.addWidget(create_section_header("Party Feed"))
        self.lbl_feed = QLabel("Session active. Play any track to synchronize.")
        self.lbl_feed.setStyleSheet(
            "background-color: #121215; color: #a1a1aa; font-size: 11px; padding: 8px; border: 1px solid #27272a; border-radius: 4px;"
        )
        self.lbl_feed.setWordWrap(True)
        active_layout.addWidget(self.lbl_feed, 1)

        # Leave session button
        self.btn_leave = QPushButton("Leave Party Session")
        self.btn_leave.setStyleSheet(
            "background-color: #dc2626; color: #ffffff; font-weight: bold; padding: 8px; border-radius: 4px;"
        )
        self.btn_leave.clicked.connect(self._on_leave_clicked)
        active_layout.addWidget(self.btn_leave)

        self.stack.addWidget(page_active)

        # Bottom status label
        self.lbl_status = QLabel("Ready to connect.")
        self.lbl_status.setStyleSheet("color: #71717a; font-size: 10px; font-style: italic;")
        main_layout.addWidget(self.lbl_status)

    def _wire_signals(self):
        """Connects PartySyncService events to UI updates."""
        self.sync_service.connected.connect(self._on_connected)
        self.sync_service.disconnected.connect(self._on_disconnected)
        self.sync_service.peer_joined.connect(self._on_peer_joined)
        self.sync_service.peer_left.connect(self._on_peer_left)
        self.sync_service.host_transferred.connect(self._on_host_transferred)
        self.sync_service.queue_updated.connect(self._on_queue_updated)
        self.sync_service.status_message.connect(self._set_status)
        self.sync_service.error_occurred.connect(self._set_error)

    # -------------------------------------------------------------------------
    # UI Event Handlers
    # -------------------------------------------------------------------------

    def _on_regenerate_code(self):
        self._generated_code = generate_room_code()
        self.lbl_room_code.setText(self._generated_code)

    def _on_copy_code(self):
        code = self.lbl_room_code.text()
        QApplication.clipboard().setText(code)
        self.lbl_status.setText(f"Copied '{code}' to clipboard!")

    def _on_host_clicked(self):
        code = self.lbl_room_code.text().strip().upper()
        name = self.edit_user_name.text().strip() or "Host"
        relay = self.edit_relay_url.text().strip() or DEFAULT_RELAY_URL
        self.sync_service.allow_guest_control = self.chk_guest_control.isChecked()
        self.sync_service.host_session(code, name, relay)

    def _on_copy_invite_clicked(self):
        code = self.sync_service.room_code
        self.lbl_status.setText(f"Copied '{code}' to clipboard.")
        QApplication.clipboard().setText(code)

    def _on_join_clicked(self):
        raw_text = self.edit_join_code.text().strip()
        if not raw_text:
            self.lbl_status.setText("Please enter a room code first.")
            return
        name = self.edit_user_name.text().strip() or "Listener"
        relay = self.edit_relay_url.text().strip() or DEFAULT_RELAY_URL
        code = raw_text

        # Smart parsing for invite format (e.g. "ROOM5@192.168.1.50:8765")
        if "@" in raw_text:
            parts = raw_text.split("@", 1)
            code = parts[0].strip()
            remote = parts[1].strip()
            if not remote.startswith("ws://") and not remote.startswith("wss://"):
                remote = f"ws://{remote}"
            relay = remote
            self.edit_relay_url.setText(relay)

        code = code.upper()
        self.sync_service.join_session(code, name, relay)

    def _on_leave_clicked(self):
        self.sync_service.disconnect_session()

    def _on_connected(self, room_code: str, is_host: bool, members: list):
        relay_url = self.edit_relay_url.text().strip().lower()
        is_lan = "127.0.0.1" in relay_url or "localhost" in relay_url
        if is_host:
            role_str = "Role: Host (LAN Mode)" if is_lan else "Role: Host (Cloud Relay)"
        else:
            role_str = "Role: Listener (Synced with party)"

        self.lbl_active_status.setText(f"Connected: {room_code}")
        self.lbl_active_role.setText(role_str)
        self.lbl_members_count.setText(f"Listeners in party: {len(members)}")
        self.btn_copy_invite.setVisible(is_host)
        self.btn_clear_queue.setVisible(is_host)

        self.members = list(members)
        self._update_transfer_ui()
        self._on_queue_updated(self.sync_service.party_queue)
        self.lbl_feed.setText(f"Connected to room {room_code}. Members: {', '.join(members)}")
        self.stack.setCurrentIndex(1)
        if self.panel and hasattr(self.panel, "update_party_hud"):
            self.panel.update_party_hud(True, room_code, is_host)

    def _on_disconnected(self, reason: str):
        self.lbl_status.setText(reason)
        self.stack.setCurrentIndex(0)
        if self.panel and hasattr(self.panel, "update_party_hud"):
            self.panel.update_party_hud(False, "", False)

    def _update_transfer_ui(self):
        is_host = self.sync_service.is_host
        current_user = self.sync_service.user_name
        other_members = [m for m in self.members if m != current_user]
        self.combo_members.blockSignals(True)
        self.combo_members.clear()
        if other_members:
            self.combo_members.addItems(other_members)
            self.combo_members.setEnabled(True)
            self.combo_members.setStyleSheet(
                "background-color: #18181b; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px; padding: 2px 8px; font-size: 11px;"
            )
            self.btn_transfer.setEnabled(True)
            self.btn_transfer.setStyleSheet(
                "background-color: #7c3aed; color: #ffffff; font-weight: bold; padding: 3px 10px; border-radius: 4px; font-size: 11px;"
            )
            self.btn_transfer.setToolTip("Transfer host control to selected member")
        else:
            self.combo_members.addItem("Waiting for friends to join...")
            self.combo_members.setEnabled(False)
            self.combo_members.setStyleSheet(
                "background-color: #18181b; color: #71717a; border: 1px dashed #3f3f46; border-radius: 4px; padding: 2px 8px; font-size: 11px;"
            )
            self.btn_transfer.setEnabled(False)
            self.btn_transfer.setStyleSheet(
                "background-color: #27272a; color: #71717a; border: 1px solid #3f3f46; padding: 3px 10px; border-radius: 4px; font-size: 11px;"
            )
            self.btn_transfer.setToolTip("Wait for friends to join your party before transferring host privileges")
        self.combo_members.blockSignals(False)

        # Always visible to Host so the control is prominent and immediately discoverable!
        self.frame_transfer.setVisible(is_host)
        self.btn_clear_queue.setVisible(is_host)

    def _on_transfer_clicked(self):
        target = self.combo_members.currentText().strip()
        if not target:
            return
        self.sync_service.transfer_host(target)
        self.lbl_feed.setText(f"Transferring host role to {target}...")

    def _on_host_transferred(self, new_host: str, old_host: str):
        is_host = self.sync_service.is_host
        relay_url = self.edit_relay_url.text().strip().lower()
        is_lan = "127.0.0.1" in relay_url or "localhost" in relay_url
        if is_host:
            self.lbl_active_role.setText("Role: Host (LAN Mode)" if is_lan else "Role: Host (Cloud Relay)")
            self.btn_copy_invite.setVisible(True)
        else:
            self.lbl_active_role.setText(f"Role: Listener (Host: {new_host})")
            self.btn_copy_invite.setVisible(False)

        self._update_transfer_ui()
        self._on_queue_updated(self.sync_service.party_queue)
        self.lbl_feed.setText(f"Host privileges transferred from {old_host} to {new_host}.")
        if self.panel and hasattr(self.panel, "update_party_hud"):
            self.panel.update_party_hud(True, self.sync_service.room_code, is_host)

    def _on_peer_joined(self, name: str, count: int):
        if name not in self.members:
            self.members.append(name)
        self.lbl_members_count.setText(f"Listeners in party: {count}")
        self.lbl_feed.setText(f"{name} joined the room ({count} listening)")
        self._update_transfer_ui()

    def _on_peer_left(self, name: str, count: int):
        if name in self.members:
            self.members.remove(name)
        self.lbl_members_count.setText(f"Listeners in party: {count}")
        self._update_transfer_ui()
        if not self.sync_service.is_host and (count <= 1 or name == self.sync_service.host_name):
            self.lbl_feed.setText(f"{name} (Host) left the party. Room closed.")
            self.lbl_status.setText("Host left the session. Room closed.")
            self.sync_service.disconnect_session()
        else:
            self.lbl_feed.setText(f"{name} left the room.")

    # -------------------------------------------------------------------------
    # Shared Room Queue UI
    # -------------------------------------------------------------------------

    def _on_add_queue_clicked(self):
        text = self.edit_queue_input.text().strip()
        if not text:
            return
        title, artist = parse_track_info(text)

        # Match against local playlist / library to attach exact filename & artist if already on disk
        matched_fn = ""
        if self.panel and hasattr(self.panel, "find_matching_party_track"):
            matched_idx = self.panel.find_matching_party_track({"title": title, "artist": artist, "yt_query": text})
            if matched_idx >= 0 and matched_idx < len(self.panel.audio_engine.playlist):
                matched_path = self.panel.audio_engine.playlist[matched_idx]
                matched_fn = os.path.basename(matched_path)
                c_title, c_artist = parse_track_info(matched_fn)
                if not artist and c_artist:
                    artist = c_artist
                if c_title:
                    title = c_title

        if not matched_fn:
            playlist = getattr(self.panel.audio_engine, "playlist", []) if self.panel else []
            norm_text = re.sub(r"[^a-z0-9]", "", text.lower())
            norm_title = re.sub(r"[^a-z0-9]", "", title.lower())
            for track_path in playlist:
                fn = os.path.basename(track_path)
                c_title, c_artist = parse_track_info(fn)
                norm_fn = re.sub(r"[^a-z0-9]", "", fn.lower())
                norm_ct = re.sub(r"[^a-z0-9]", "", c_title.lower())
                if norm_text == norm_fn or norm_text == norm_ct or (norm_title and norm_title == norm_ct):
                    matched_fn = fn
                    if not artist and c_artist:
                        artist = c_artist
                    break

        query = text
        if artist and " - " not in text:
            query = f"{artist} - {title}"

        self.sync_service.add_to_party_queue(
            title=title,
            artist=artist,
            filename=matched_fn,
            yt_query=query,
        )
        self.edit_queue_input.clear()
        self.lbl_feed.setText(f"Added '{title}' to Party Queue.")

    def _on_add_from_library_clicked(self):
        playlist = getattr(self.panel.audio_engine, "playlist", []) if self.panel else []
        if not playlist:
            self.lbl_feed.setText("Your local playlist is empty.")
            return
        dlg = TrackPickerDialog(playlist, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_path:
            fn = os.path.basename(dlg.selected_path)
            title, artist = parse_track_info(fn)
            query = f"{artist} - {title}" if artist else title
            self.sync_service.add_to_party_queue(
                title=title,
                artist=artist,
                filename=fn,
                yt_query=query,
            )
            self.lbl_feed.setText(f"Added '{title}' to Party Queue.")

    def _on_clear_queue_clicked(self):
        self.sync_service.clear_party_queue()
        self.lbl_feed.setText("Cleared Party Queue.")

    def _on_queue_updated(self, queue: list):
        """Renders the shared party queue entries with strictly enforced permissions."""
        self.lbl_queue_header.setText(f"ROOM QUEUE ({len(queue)})")

        # Clear existing layout
        while self.queue_list_layout.count():
            child = self.queue_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not queue:
            lbl_empty = QLabel("Queue is empty. Anyone in the room can add songs to play next!")
            lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_empty.setStyleSheet("color: #71717a; font-style: italic; font-size: 11px; padding: 12px 0;")
            self.queue_list_layout.addWidget(lbl_empty)
            return

        is_host = self.sync_service.is_host
        current_user = self.sync_service.user_name

        for idx, item in enumerate(queue):
            row = QFrame()
            row.setStyleSheet(
                "QFrame { background-color: #18181b; border: 1px solid #27272a; border-radius: 4px; padding: 3px 6px; }"
                "QFrame:hover { border-color: #3f3f46; }"
            )
            h_layout = QHBoxLayout(row)
            h_layout.setContentsMargins(4, 2, 4, 2)
            h_layout.setSpacing(6)

            # Index badge
            lbl_num = QLabel(f"#{idx + 1}")
            lbl_num.setStyleSheet("color: #71717a; font-family: 'Consolas', monospace; font-size: 10px; font-weight: bold;")
            h_layout.addWidget(lbl_num)

            # Track Title & Artist
            t_title = item.get("title", "Unknown Title")
            t_artist = item.get("artist", "")
            disp = f"<b>{t_title}</b>"
            if t_artist and t_artist != "Talia Music Player":
                disp += f" - <span style='color:#a1a1aa;'>{t_artist}</span>"
            lbl_info = QLabel(disp)
            lbl_info.setStyleSheet("color: #f4f4f5; font-size: 11px;")
            h_layout.addWidget(lbl_info, 1)

            # 'Added by' badge
            added_by = item.get("added_by", "")
            is_own = (added_by == current_user)
            tag_color = "#38bdf8" if is_own else "#a1a1aa"
            tag_text = "You" if is_own else added_by
            lbl_by = QLabel(f"[by {tag_text}]")
            lbl_by.setStyleSheet(f"color: {tag_color}; font-size: 10px; font-weight: 600;")
            h_layout.addWidget(lbl_by)

            # Remove permission: Host can remove any song; member can remove ONLY their own
            if is_host or is_own:
                item_id = item.get("id")
                btn_del = QPushButton("✕")
                btn_del.setFixedSize(20, 20)
                btn_del.setToolTip("Remove from room queue" if is_host else "Remove your song")
                btn_del.setStyleSheet(
                    "QPushButton { background-color: #27272a; color: #ef4444; border: 1px solid #3f3f46; border-radius: 3px; font-size: 10px; font-weight: bold; padding: 0; }"
                    "QPushButton:hover { background-color: #ef4444; color: #ffffff; border-color: #dc2626; }"
                )
                btn_del.clicked.connect(lambda _, q_id=item_id: self.sync_service.remove_from_party_queue(q_id))
                h_layout.addWidget(btn_del)

            self.queue_list_layout.addWidget(row)

        self.queue_list_layout.addStretch(1)

    def _set_status(self, text: str):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 10px;")

    def _set_error(self, text: str):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet("color: #f87171; font-size: 11px; font-weight: bold;")
        if hasattr(self, "lbl_join_error"):
            self.lbl_join_error.setText(text)
            self.lbl_join_error.setVisible(True)
        lowered = text.lower()
        if self.stack.currentIndex() != 0 and (
            "not exist" in lowered
            or "offline" in lowered
            or "room closed" in lowered
            or "host has left" in lowered
            or "closed" in lowered
        ):
            self.stack.setCurrentIndex(0)
            if self.panel and hasattr(self.panel, "update_party_hud"):
                self.panel.update_party_hud(False, "", False)
