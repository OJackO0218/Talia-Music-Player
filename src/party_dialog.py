"""
Talia Party Sync UI Dialog.

Provides a cyberpunk-themed modal interface for hosting or joining
synchronized music listening sessions with friends.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import re
from party_sync import DEFAULT_RELAY_URL, generate_room_code, get_local_lan_ip
from ui_theme import SHARED_PANEL_STYLE
from ui_widgets import create_section_header


class PartySyncDialog(QDialog):
    """Sleek cyberpunk dialog to host or join real-time listening parties."""

    def __init__(self, panel, parent=None):
        super().__init__(parent or panel)
        self.panel = panel
        self.sync_service = panel.party_sync

        self.setWindowTitle("Listen Together - Party Sync")
        self.setFixedSize(480, 520)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(SHARED_PANEL_STYLE)

        self._generated_code = generate_room_code()
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

        lbl_desc = QLabel("Synchronize tracks, karaoke lyrics, and Talia reactions with friends in real-time.")
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
        self.edit_relay_url.setPlaceholderText("ws://127.0.0.1:8765")
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
        self.edit_join_code.setMaxLength(8)
        self.edit_join_code.setStyleSheet("font-family: 'Consolas', monospace; font-size: 13px; font-weight: bold; text-transform: uppercase;")
        hbox_join.addWidget(self.edit_join_code, 1)

        self.btn_join = QPushButton("Join Party")
        self.btn_join.setStyleSheet(
            "background-color: #059669; color: #ffffff; font-weight: bold; padding: 7px 16px; border-radius: 4px;"
        )
        self.btn_join.clicked.connect(self._on_join_clicked)
        hbox_join.addWidget(self.btn_join)
        setup_layout.addLayout(hbox_join)

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

        self.lbl_active_status = QLabel("Connected: NEON7")
        self.lbl_active_status.setStyleSheet("color: #4ade80; font-size: 14px; font-weight: bold;")
        card_layout.addWidget(self.lbl_active_status)

        self.lbl_active_role = QLabel("Role: Host (Broadcasting playback)")
        self.lbl_active_role.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        card_layout.addWidget(self.lbl_active_role)

        self.lbl_members_count = QLabel("Listeners in party: 1")
        self.lbl_members_count.setStyleSheet("color: #e4e4e7; font-size: 12px; font-weight: 600;")
        card_layout.addWidget(self.lbl_members_count)

        self.lbl_share_info = QLabel("Share with friends:")
        self.lbl_share_info.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 500;")
        self.lbl_share_info.setWordWrap(True)
        card_layout.addWidget(self.lbl_share_info)

        self.btn_copy_invite = QPushButton("Copy Room Invite for Friends")
        self.btn_copy_invite.setStyleSheet(
            "padding: 5px 10px; font-size: 11px; background-color: #27272a; border: 1px solid #3f3f46; border-radius: 4px; color: #f4f4f5;"
        )
        self.btn_copy_invite.clicked.connect(self._on_copy_invite_clicked)
        card_layout.addWidget(self.btn_copy_invite)

        active_layout.addWidget(card)

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
        self.sync_service.status_message.connect(self._set_status)
        self.sync_service.error_occurred.connect(self._set_error)
        self.sync_service.tunnel_ready.connect(self._on_tunnel_ready)

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
        pub_tunnel = getattr(self.sync_service, "public_tunnel_url", "")
        if pub_tunnel:
            invite_str = f"{code}@{pub_tunnel}"
            self.lbl_status.setText("Copied Worldwide Invite! Send this to your friend.")
        else:
            lan_ip = get_local_lan_ip()
            invite_str = f"{code}@{lan_ip}:8765"
            self.lbl_status.setText(f"Copied invite '{invite_str}'! Friends can paste this directly into Join.")
        QApplication.clipboard().setText(invite_str)

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


    def _on_tunnel_ready(self, pub_url: str):
        if self.sync_service.is_host:
            code = self.sync_service.room_code
            invite_str = f"{code}@{pub_url}"
            self.lbl_share_info.setText(f"Worldwide Invite:\n{invite_str}")
            self.lbl_status.setText("Internet tunnel active! Friends worldwide can join.")

    def _on_connected(self, room_code: str, is_host: bool, members: list):
        role_str = "Host (Broadcasting playback)" if is_host else "Listener (Synced with party)"
        self.lbl_active_status.setText(f"Connected: {room_code}")
        self.lbl_active_role.setText(f"Role: {role_str}")
        self.lbl_members_count.setText(f"Listeners in party: {len(members)}")
        lan_ip = get_local_lan_ip()
        if is_host:
            if getattr(self.sync_service, "public_tunnel_url", ""):
                self.lbl_share_info.setText(f"Worldwide Invite:\n{room_code}@{self.sync_service.public_tunnel_url}")
            else:
                self.lbl_share_info.setText(f"Starting worldwide internet tunnel... (or LAN: {room_code}@{lan_ip}:8765)")
            self.lbl_share_info.setVisible(True)
            self.btn_copy_invite.setVisible(True)
        else:
            self.lbl_share_info.setVisible(False)
            self.btn_copy_invite.setVisible(False)
        self.lbl_feed.setText(f"Connected to room {room_code}. Members: {', '.join(members)}")
        self.stack.setCurrentIndex(1)
        if self.panel and hasattr(self.panel, "update_party_hud"):
            self.panel.update_party_hud(True, room_code, is_host)

    def _on_disconnected(self, reason: str):
        self.lbl_status.setText(reason)
        self.stack.setCurrentIndex(0)
        if self.panel and hasattr(self.panel, "update_party_hud"):
            self.panel.update_party_hud(False, "", False)

    def _on_peer_joined(self, name: str, count: int):
        self.lbl_members_count.setText(f"Listeners in party: {count}")
        self.lbl_feed.setText(f"{name} joined the room ({count} listening)")

    def _on_peer_left(self, name: str, count: int):
        self.lbl_members_count.setText(f"Listeners in party: {count}")
        self.lbl_feed.setText(f"{name} left the room.")


    def _set_status(self, text: str):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 10px;")

    def _set_error(self, text: str):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet("color: #f87171; font-size: 10px;")
