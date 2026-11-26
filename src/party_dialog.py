"""
Talia Party Sync UI Dialog.

Provides a cyberpunk-themed modal interface for hosting or joining
synchronized music listening sessions with friends, including transfer of host
privileges and a shared room queue where everyone can add tracks and the host
(or track author) can manage entries.
"""

import html
import os
import re
from typing import Optional

from PyQt6.QtCore import Qt
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
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from discord_service import parse_track_info
from party_sync import DEFAULT_RELAY_URL, generate_room_code, get_local_lan_ip
from ui_theme import CYBER_DIALOG_CONTROLS_QSS
from ui_widgets import (
    CyberCardContainer,
    CyberChamferButton,
    CyberLineEdit,
    DraggableClampedDialogMixin,
    DraggableHeaderWidget,
)


class TrackPickerDialog(DraggableClampedDialogMixin, QDialog):
    """Searchable cyberpunk dialog for picking a track from the local library to queue."""

    def __init__(self, playlist: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Track from Library to Party Queue")
        self.resize(430, 500)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.playlist = list(playlist)
        self.selected_path: Optional[str] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = CyberCardContainer(self)
        card.setObjectName("trackPickerCard")
        card.setStyleSheet(
            "QFrame#trackPickerCard { border: none; background: transparent; }"
            + CYBER_DIALOG_CONTROLS_QSS
        )
        root.addWidget(card)

        shell = QVBoxLayout(card)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        header = DraggableHeaderWidget(self)
        header.setFixedHeight(40)
        hbox_hdr = QHBoxLayout(header)
        hbox_hdr.setContentsMargins(14, 2, 12, 2)
        lbl_hdr = QLabel("LIBRARY TRACK PICKER", header)
        lbl_hdr.setStyleSheet(
            "color: #FFFFFF; font-family: 'Rajdhani', sans-serif; font-size: 14px; font-weight: bold; letter-spacing: 1.4px; background: transparent;"
        )
        hbox_hdr.addWidget(lbl_hdr, 1)
        btn_x = CyberChamferButton("✕", variant="exit", parent=header)
        btn_x.setFixedSize(24, 24)
        btn_x.clicked.connect(self.reject)
        hbox_hdr.addWidget(btn_x)
        shell.addWidget(header)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 6, 16, 12)
        layout.setSpacing(8)
        shell.addLayout(layout, 1)

        hbox_sub = QHBoxLayout()
        lbl = QLabel("SELECT TRACK TO QUEUE")
        lbl.setStyleSheet("color: #5EF6FF; font-family: 'Rajdhani', sans-serif; font-weight: 800; font-size: 11px; letter-spacing: 1px;")
        hbox_sub.addWidget(lbl, 1)
        self.lbl_count = QLabel(f"{len(self.playlist)} tracks")
        self.lbl_count.setStyleSheet("color: #a1a1aa; font-family: 'Consolas', monospace; font-size: 10px;")
        hbox_sub.addWidget(self.lbl_count)
        layout.addLayout(hbox_sub)

        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText("Filter by song title or artist...")
        self.edit_filter.textChanged.connect(self._filter_tracks)
        layout.addWidget(self.edit_filter)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            "QListWidget { background-color: #08090F; border: 1px solid rgba(247, 80, 73, 85); border-radius: 3px; padding: 4px; color: #f4f4f5; font-size: 11px; }"
            "QListWidget::item { padding: 6px; border-radius: 2px; border-bottom: 1px solid #161722; }"
            "QListWidget::item:hover { background-color: #161826; }"
            "QListWidget::item:selected { background-color: rgba(247, 80, 73, 180); color: #0e0e17; font-weight: bold; }"
        )
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget, 1)

        self._populate(self.playlist)

        hbox_btns = QHBoxLayout()
        hbox_btns.addStretch(1)

        btn_cancel = CyberChamferButton("CANCEL", variant="action_neutral")
        btn_cancel.setFixedSize(84, 28)
        btn_cancel.clicked.connect(self.reject)
        hbox_btns.addWidget(btn_cancel)

        self.btn_add = CyberChamferButton("ADD TO QUEUE", variant="action_green")
        self.btn_add.setFixedSize(124, 28)
        self.btn_add.clicked.connect(self._on_add_clicked)
        hbox_btns.addWidget(self.btn_add)
        layout.addLayout(hbox_btns)

    def _populate(self, paths: list[str]):
        self.list_widget.clear()
        if hasattr(self, "lbl_count"):
            self.lbl_count.setText(f"{len(paths)} tracks")
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
        self.setFixedSize(430, 490)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self._custom_positioned = False

        self._generated_code = generate_room_code()
        self.members: list[str] = []
        self.init_ui()
        self._wire_signals()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Card container with authentic Cyberpunk dark background & red chamfered border matching ControlPanel
        self.card_container = CyberCardContainer(self)
        self.card_container.setObjectName("partyDialogCard")
        self.card_container.setStyleSheet(
            "QFrame#partyDialogCard { border: none; background: transparent; }"
            + CYBER_DIALOG_CONTROLS_QSS
        )
        root_layout.addWidget(self.card_container)

        container_layout = QVBoxLayout(self.card_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 1. Top Header Bar (spans full card width over red header banner hug)
        header_widget = DraggableHeaderWidget(self)
        header_widget.setFixedHeight(42)
        hbox_header = QHBoxLayout(header_widget)
        hbox_header.setContentsMargins(14, 2, 12, 2)
        hbox_header.setSpacing(8)

        lbl_title = QLabel("LISTEN TOGETHER", header_widget)
        lbl_title.setStyleSheet(
            "color: #FFFFFF; font-family: 'Rajdhani', sans-serif; font-size: 15px; font-weight: bold; letter-spacing: 1.5px; background: transparent;"
        )
        hbox_header.addWidget(lbl_title)

        self.lbl_header_pill = QLabel("OFFLINE", header_widget)
        self.lbl_header_pill.setStyleSheet(
            "background-color: #12121a; color: #71717a; border: 1px solid #3f3f46; border-radius: 2px; padding: 2px 7px; font-size: 9px; font-weight: bold; font-family: 'Share Tech Mono', 'Consolas', monospace;"
        )
        hbox_header.addWidget(self.lbl_header_pill)

        hbox_header.addStretch(1)

        self.btn_close = CyberChamferButton("✕", variant="exit", parent=header_widget)
        self.btn_close.setFixedSize(26, 26)
        self.btn_close.setToolTip("Close")
        self.btn_close.clicked.connect(self.hide)
        hbox_header.addWidget(self.btn_close)

        container_layout.addWidget(header_widget)

        # 2. Main Middle Body (content matching ControlPanel margins & styling)
        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(14, 6, 16, 10)
        body_layout.setSpacing(6)

        # Main stacked pages: 0 = Connection Setup / Lobby, 1 = Active Session
        self.stack = QStackedWidget(body_widget)
        body_layout.addWidget(self.stack, 1)

        # =========================================================================
        # --- PAGE 0: DISCONNECTED LOBBY (HOST & JOIN SEGMENTED TABS) ---
        # =========================================================================
        page_setup = QWidget()
        setup_layout = QVBoxLayout(page_setup)
        setup_layout.setContentsMargins(0, 0, 0, 0)
        setup_layout.setSpacing(6)

        # Sleek 2-segment chamfered switcher: [ HOST LOBBY ] | [ JOIN A ROOM ]
        tab_bar_layout = QHBoxLayout()
        tab_bar_layout.setContentsMargins(0, 0, 0, 0)
        tab_bar_layout.setSpacing(6)

        self.btn_tab_host = CyberChamferButton("HOST LOBBY", variant="tab_cyan")
        self.btn_tab_host.setFixedHeight(26)
        self.btn_tab_host.clicked.connect(lambda: self._switch_lobby_tab("host"))
        tab_bar_layout.addWidget(self.btn_tab_host, 1)

        self.btn_tab_join = CyberChamferButton("JOIN A ROOM", variant="tab_idle")
        self.btn_tab_join.setFixedHeight(26)
        self.btn_tab_join.clicked.connect(lambda: self._switch_lobby_tab("join"))
        tab_bar_layout.addWidget(self.btn_tab_join, 1)

        setup_layout.addLayout(tab_bar_layout)

        # Sub-stack for Host vs Join view inside lobby
        self.lobby_stack = QStackedWidget()
        setup_layout.addWidget(self.lobby_stack, 1)

        # --- SUB-PAGE 0: HOST LOBBY ---
        sub_host = QWidget()
        sub_host_layout = QVBoxLayout(sub_host)
        sub_host_layout.setContentsMargins(0, 2, 0, 0)
        sub_host_layout.setSpacing(6)

        # Card 1: Host Configuration Card
        card_host_cfg = QFrame()
        card_host_cfg.setStyleSheet(
            "QFrame { background-color: #0B0B13; border: 1px solid rgba(247, 80, 73, 85); border-radius: 3px; }"
        )
        cfg_layout = QVBoxLayout(card_host_cfg)
        cfg_layout.setSpacing(6)
        cfg_layout.setContentsMargins(8, 7, 8, 7)

        hbox_hname = QHBoxLayout()
        lbl_hname = QLabel("HOST DJ NAME:")
        lbl_hname.setStyleSheet("color: #5EF6FF; font-family: 'Rajdhani', sans-serif; font-weight: 800; font-size: 10px; letter-spacing: 0.8px; min-width: 82px; border: none; background: transparent;")
        hbox_hname.addWidget(lbl_hname)
        self.edit_user_name = QLineEdit("Listener")
        self.edit_user_name.setPlaceholderText("Enter display name")
        hbox_hname.addWidget(self.edit_user_name, 1)
        cfg_layout.addLayout(hbox_hname)

        hbox_net = QHBoxLayout()
        lbl_net = QLabel("NET MODE:")
        lbl_net.setStyleSheet("color: #5EF6FF; font-family: 'Rajdhani', sans-serif; font-weight: 800; font-size: 10px; letter-spacing: 0.8px; min-width: 82px; border: none; background: transparent;")
        hbox_net.addWidget(lbl_net)
        self.combo_net_mode = QComboBox()
        self.combo_net_mode.addItem("Online Cloud Relay (Internet)")
        self.combo_net_mode.addItem("Local Wi-Fi / LAN (Zero Latency)")
        self.combo_net_mode.currentIndexChanged.connect(self._on_net_mode_changed)
        hbox_net.addWidget(self.combo_net_mode, 1)
        cfg_layout.addLayout(hbox_net)

        # Hidden/Advanced relay URL for test compatibility
        self.edit_relay_url = QLineEdit(DEFAULT_RELAY_URL)
        self.edit_relay_url.hide()
        cfg_layout.addWidget(self.edit_relay_url)

        sub_host_layout.addWidget(card_host_cfg)

        # Card 2: Room Code HUD Card
        card_code = QFrame()
        card_code.setStyleSheet(
            "QFrame { background-color: #0B0B13; border: 1px solid rgba(247, 80, 73, 85); border-radius: 3px; }"
        )
        code_card_layout = QVBoxLayout(card_code)
        code_card_layout.setSpacing(6)
        code_card_layout.setContentsMargins(8, 7, 8, 7)

        hbox_code = QHBoxLayout()
        hbox_code.setSpacing(6)
        self.lbl_room_code = QLabel(self._generated_code)
        self.lbl_room_code.setStyleSheet(
            "background-color: #050509; color: #ff8a84; font-family: 'Share Tech Mono', 'Consolas', monospace; "
            "font-size: 20px; font-weight: bold; padding: 3px 12px; border: 1px solid #F75049; border-radius: 2px; letter-spacing: 4px;"
        )
        self.lbl_room_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hbox_code.addWidget(self.lbl_room_code, 1)

        btn_regen = CyberChamferButton("REFRESH", variant="action_neutral")
        btn_regen.setFixedSize(72, 30)
        btn_regen.setToolTip("Generate a fresh 5-character room code")
        btn_regen.clicked.connect(self._on_regenerate_code)
        hbox_code.addWidget(btn_regen)

        btn_copy = CyberChamferButton("COPY", variant="action_cyan")
        btn_copy.setFixedSize(64, 30)
        btn_copy.setToolTip("Copy room code or LAN invite to clipboard")
        btn_copy.clicked.connect(self._on_copy_code)
        hbox_code.addWidget(btn_copy)
        code_card_layout.addLayout(hbox_code)

        self.chk_guest_control = QCheckBox("Shared DJ Mode (Allow listeners to control playback)")
        code_card_layout.addWidget(self.chk_guest_control)
        sub_host_layout.addWidget(card_code)

        # Primary Start Hosting Button
        self.btn_host = CyberChamferButton("START HOSTING SESSION", variant="action_cyan")
        self.btn_host.setFixedHeight(34)
        self.btn_host.clicked.connect(self._on_host_clicked)
        sub_host_layout.addWidget(self.btn_host)

        # Card 3: Cyber Telemetry & Info Box
        card_info = QFrame()
        card_info.setStyleSheet(
            "QFrame { background-color: #08090F; border: 1px solid rgba(94, 246, 255, 55); border-radius: 3px; }"
        )
        info_layout = QVBoxLayout(card_info)
        info_layout.setSpacing(3)
        info_layout.setContentsMargins(8, 6, 8, 6)

        lbl_info_hdr = QLabel("REAL-TIME MULTIPLAYER AUDIO HUD")
        lbl_info_hdr.setStyleSheet("color: #5EF6FF; font-family: 'Rajdhani', sans-serif; font-size: 10px; font-weight: 800; letter-spacing: 0.9px; border: none; background: transparent;")
        info_layout.addWidget(lbl_info_hdr)

        for info_txt in (
            "• Clock Sync: Audio position aligns automatically across all listeners.",
            "• Auto Cache: Missing tracks download cleanly in Opus + lyrics.",
            "• Shared Queue: Listeners can queue upcoming tracks to play next.",
        ):
            lbl_i = QLabel(info_txt)
            lbl_i.setStyleSheet("color: #a1a1aa; font-size: 10px; border: none; background: transparent;")
            lbl_i.setWordWrap(True)
            info_layout.addWidget(lbl_i)

        sub_host_layout.addWidget(card_info)
        self.lobby_stack.addWidget(sub_host)

        # --- SUB-PAGE 1: JOIN PARTY ---
        sub_join = QWidget()
        sub_join_layout = QVBoxLayout(sub_join)
        sub_join_layout.setContentsMargins(0, 2, 0, 0)
        sub_join_layout.setSpacing(6)

        # Card 1: Join Credentials Card
        card_join_cfg = QFrame()
        card_join_cfg.setStyleSheet(
            "QFrame { background-color: #0B0B13; border: 1px solid rgba(247, 80, 73, 85); border-radius: 3px; }"
        )
        jcfg_layout = QVBoxLayout(card_join_cfg)
        jcfg_layout.setSpacing(6)
        jcfg_layout.setContentsMargins(8, 7, 8, 7)

        hbox_jname = QHBoxLayout()
        lbl_jname = QLabel("YOUR NAME:")
        lbl_jname.setStyleSheet("color: #5EF6FF; font-family: 'Rajdhani', sans-serif; font-weight: 800; font-size: 10px; letter-spacing: 0.8px; min-width: 86px; border: none; background: transparent;")
        hbox_jname.addWidget(lbl_jname)
        self.edit_user_name_join = QLineEdit("Listener")
        self.edit_user_name_join.setPlaceholderText("Enter display name")
        self.edit_user_name_join.textChanged.connect(lambda t: self.edit_user_name.setText(t))
        hbox_jname.addWidget(self.edit_user_name_join, 1)
        jcfg_layout.addLayout(hbox_jname)

        hbox_jcode = QHBoxLayout()
        hbox_jcode.setSpacing(5)
        lbl_jcode = QLabel("CODE / IP:")
        lbl_jcode.setStyleSheet("color: #5EF6FF; font-family: 'Rajdhani', sans-serif; font-weight: 800; font-size: 10px; letter-spacing: 0.8px; min-width: 86px; border: none; background: transparent;")
        hbox_jcode.addWidget(lbl_jcode)

        self.edit_join_code = CyberLineEdit("Code (NEON7) or ROOM@IP:8765", monospace=True)
        self.edit_join_code.setMaxLength(128)
        self.edit_join_code.returnPressed.connect(self._on_join_clicked)
        hbox_jcode.addWidget(self.edit_join_code, 1)

        btn_paste_code = CyberChamferButton("PASTE", variant="action_neutral")
        btn_paste_code.setFixedSize(56, 26)
        btn_paste_code.clicked.connect(self._on_paste_join_code)
        hbox_jcode.addWidget(btn_paste_code)
        jcfg_layout.addLayout(hbox_jcode)

        sub_join_layout.addWidget(card_join_cfg)

        # Primary Join Party Button
        self.btn_join = CyberChamferButton("JOIN PARTY SESSION", variant="action_green")
        self.btn_join.setFixedHeight(34)
        self.btn_join.clicked.connect(self._on_join_clicked)
        sub_join_layout.addWidget(self.btn_join)

        self.lbl_join_error = QLabel("")
        self.lbl_join_error.setStyleSheet("color: #f87171; font-size: 11px; font-weight: bold; padding: 2px 4px;")
        self.lbl_join_error.setVisible(False)
        self.lbl_join_error.setWordWrap(True)
        sub_join_layout.addWidget(self.lbl_join_error)
        self.edit_join_code.textChanged.connect(lambda: self.lbl_join_error.setVisible(False))

        # Card 2: How to Connect Guide
        card_guide = QFrame()
        card_guide.setStyleSheet(
            "QFrame { background-color: #08090F; border: 1px solid rgba(74, 222, 128, 65); border-radius: 3px; }"
        )
        guide_layout = QVBoxLayout(card_guide)
        guide_layout.setSpacing(3)
        guide_layout.setContentsMargins(8, 6, 8, 6)

        lbl_guide_hdr = QLabel("HOW TO CONNECT WITH FRIENDS")
        lbl_guide_hdr.setStyleSheet("color: #4ade80; font-family: 'Rajdhani', sans-serif; font-size: 10px; font-weight: 800; letter-spacing: 0.9px; border: none; background: transparent;")
        guide_layout.addWidget(lbl_guide_hdr)

        for guide_txt in (
            "1. Cloud Mode: Enter your host friend's 5-character Room Code.",
            "2. Wi-Fi / LAN: Paste host's CODE@192.168.x.x:8765 invite string.",
            "3. Playback, seeks, and lyrics lock together in real time.",
            "4. Everyone in the room can queue songs from YouTube or library.",
        ):
            lbl_g = QLabel(guide_txt)
            lbl_g.setStyleSheet("color: #a1a1aa; font-size: 10px; border: none; background: transparent;")
            lbl_g.setWordWrap(True)
            guide_layout.addWidget(lbl_g)

        sub_join_layout.addWidget(card_guide)
        self.lobby_stack.addWidget(sub_join)

        # Initialize tab styling
        self._switch_lobby_tab("host")

        self.stack.addWidget(page_setup)

        # =========================================================================
        # --- PAGE 1: ACTIVE SESSION HUB (WHEN CONNECTED) ---
        # =========================================================================
        page_active = QWidget()
        active_layout = QVBoxLayout(page_active)
        active_layout.setContentsMargins(0, 0, 0, 0)
        active_layout.setSpacing(6)

        # Active Session Header Card
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: #0B0B13; border: 1px solid rgba(247, 80, 73, 85); border-radius: 3px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(4)
        card_layout.setContentsMargins(8, 6, 8, 6)

        # Header row: Connected Code + Copy Invite Button
        hbox_card_top = QHBoxLayout()
        self.lbl_active_status = QLabel("Connected: NEON7")
        self.lbl_active_status.setStyleSheet("color: #4ade80; font-family: 'Rajdhani', sans-serif; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        hbox_card_top.addWidget(self.lbl_active_status, 1)

        self.btn_copy_invite = CyberChamferButton("COPY INVITE", variant="action_cyan")
        self.btn_copy_invite.setFixedSize(90, 24)
        self.btn_copy_invite.clicked.connect(self._on_copy_invite_clicked)
        hbox_card_top.addWidget(self.btn_copy_invite)
        card_layout.addLayout(hbox_card_top)

        hbox_role_info = QHBoxLayout()
        self.lbl_active_role = QLabel("Role: Host (Broadcasting playback)")
        self.lbl_active_role.setStyleSheet("color: #a1a1aa; font-size: 10px; border: none; background: transparent;")
        hbox_role_info.addWidget(self.lbl_active_role, 1)

        self.lbl_members_count = QLabel("Listeners in party: 1")
        self.lbl_members_count.setStyleSheet("color: #5EF6FF; font-family: 'Rajdhani', sans-serif; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        hbox_role_info.addWidget(self.lbl_members_count)
        card_layout.addLayout(hbox_role_info)

        # Host Transfer row (prominently visible to Host)
        self.frame_transfer = QFrame()
        self.frame_transfer.setFixedHeight(32)
        self.frame_transfer.setStyleSheet(
            "QFrame { background-color: #08090F; border: 1px solid rgba(168, 85, 247, 85); border-radius: 2px; }"
        )
        transfer_layout = QHBoxLayout(self.frame_transfer)
        transfer_layout.setContentsMargins(6, 3, 6, 3)
        transfer_layout.setSpacing(6)

        lbl_transfer = QLabel("TRANSFER HOST:")
        lbl_transfer.setStyleSheet("color: #c084fc; font-family: 'Rajdhani', sans-serif; font-size: 10px; font-weight: 800; border: none; background: transparent;")
        transfer_layout.addWidget(lbl_transfer)

        self.combo_members = QComboBox()
        self.combo_members.setFixedHeight(22)
        self.combo_members.addItem("Waiting for friends to join...")
        self.combo_members.setEnabled(False)
        transfer_layout.addWidget(self.combo_members, 1)

        self.btn_transfer = CyberChamferButton("MAKE HOST", variant="action_purple")
        self.btn_transfer.setFixedSize(82, 22)
        self.btn_transfer.setEnabled(False)
        self.btn_transfer.clicked.connect(self._on_transfer_clicked)
        transfer_layout.addWidget(self.btn_transfer)
        self.frame_transfer.setVisible(True)
        card_layout.addWidget(self.frame_transfer)

        active_layout.addWidget(card)

        # --- SHARED ROOM QUEUE CARD (EXPANDABLE) ---
        card_queue = QFrame()
        card_queue.setStyleSheet(
            "QFrame { background-color: #0B0B13; border: 1px solid rgba(247, 80, 73, 85); border-radius: 3px; }"
        )
        queue_card_layout = QVBoxLayout(card_queue)
        queue_card_layout.setSpacing(5)
        queue_card_layout.setContentsMargins(8, 6, 8, 6)

        hbox_queue_hdr = QHBoxLayout()
        self.lbl_queue_header = QLabel("ROOM QUEUE (0)")
        self.lbl_queue_header.setStyleSheet("color: #5EF6FF; font-family: 'Rajdhani', sans-serif; font-weight: 800; font-size: 12px; letter-spacing: 0.8px; border: none; background: transparent;")
        hbox_queue_hdr.addWidget(self.lbl_queue_header, 1)

        self.btn_clear_queue = CyberChamferButton("CLEAR", variant="action_red")
        self.btn_clear_queue.setFixedSize(56, 22)
        self.btn_clear_queue.clicked.connect(self._on_clear_queue_clicked)
        self.btn_clear_queue.setVisible(False)
        hbox_queue_hdr.addWidget(self.btn_clear_queue)
        queue_card_layout.addLayout(hbox_queue_hdr)

        # Queue Add Input Row
        hbox_add_q = QHBoxLayout()
        hbox_add_q.setSpacing(5)
        self.edit_queue_input = QLineEdit()
        self.edit_queue_input.setFixedHeight(26)
        self.edit_queue_input.setPlaceholderText("Song name, artist, or YouTube URL...")
        self.edit_queue_input.returnPressed.connect(self._on_add_queue_clicked)
        hbox_add_q.addWidget(self.edit_queue_input, 1)

        self.btn_add_queue = CyberChamferButton("+ ADD", variant="action_cyan")
        self.btn_add_queue.setFixedSize(58, 26)
        self.btn_add_queue.clicked.connect(self._on_add_queue_clicked)
        hbox_add_q.addWidget(self.btn_add_queue)

        self.btn_queue_library = CyberChamferButton("+ LIBRARY", variant="action_neutral")
        self.btn_queue_library.setFixedSize(76, 26)
        self.btn_queue_library.clicked.connect(self._on_add_from_library_clicked)
        hbox_add_q.addWidget(self.btn_queue_library)
        queue_card_layout.addLayout(hbox_add_q)

        # Scrollable Queue List
        self.queue_scroll = QScrollArea()
        self.queue_scroll.setWidgetResizable(True)
        self.queue_scroll.setMinimumHeight(100)
        self.queue_container = QWidget()
        self.queue_container.setStyleSheet("background: transparent;")
        self.queue_list_layout = QVBoxLayout(self.queue_container)
        self.queue_list_layout.setContentsMargins(4, 4, 4, 4)
        self.queue_list_layout.setSpacing(3)
        self.queue_scroll.setWidget(self.queue_container)
        queue_card_layout.addWidget(self.queue_scroll, 1)

        active_layout.addWidget(card_queue, 1)

        # Event log
        self.lbl_feed = QLabel("Session active. Play any track to synchronize.")
        self.lbl_feed.setStyleSheet(
            "background-color: #08090F; color: #a1a1aa; font-size: 10px; padding: 5px 8px; border: 1px solid rgba(247, 80, 73, 70); border-radius: 2px;"
        )
        self.lbl_feed.setWordWrap(True)
        active_layout.addWidget(self.lbl_feed)

        # Leave session button
        self.btn_leave = CyberChamferButton("LEAVE PARTY SESSION", variant="action_red")
        self.btn_leave.setFixedHeight(28)
        self.btn_leave.clicked.connect(self._on_leave_clicked)
        active_layout.addWidget(self.btn_leave)

        self.stack.addWidget(page_active)

        # Bottom status label
        self.lbl_status = QLabel("Ready to connect.")
        self.lbl_status.setStyleSheet("color: #a1a1aa; font-size: 10px;")
        body_layout.addWidget(self.lbl_status)

        container_layout.addWidget(body_widget, 1)

    def _switch_lobby_tab(self, mode: str):
        """Switches between Host Lobby and Join Party views inside the disconnected state."""
        if mode == "host":
            self.lobby_stack.setCurrentIndex(0)
            self.btn_tab_host.set_variant("tab_cyan")
            self.btn_tab_join.set_variant("tab_idle")
        else:
            self.lobby_stack.setCurrentIndex(1)
            self.btn_tab_join.set_variant("tab_green")
            self.btn_tab_host.set_variant("tab_idle")

    def _on_net_mode_changed(self, idx: int):
        """Updates connection parameters when switching between Cloud Relay and LAN."""
        if idx == 1:
            lan_ip = get_local_lan_ip()
            self.edit_relay_url.setText(f"ws://{lan_ip}:8765")
            self.lbl_status.setText(f"Local LAN Mode active ({lan_ip}:8765)")
        else:
            self.edit_relay_url.setText(DEFAULT_RELAY_URL)
            self.lbl_status.setText("Cloud Relay Mode active")

    def _on_paste_join_code(self):
        """Pastes text from clipboard into join code input."""
        clip = QApplication.clipboard().text().strip()
        if clip:
            self.edit_join_code.setText(clip)

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

    def _format_invite_string(self, code: str) -> str:
        if hasattr(self, "combo_net_mode") and self.combo_net_mode.currentIndex() == 1:
            return f"{code}@{get_local_lan_ip()}:8765"
        return code

    def _on_copy_code(self):
        invite = self._format_invite_string(self.lbl_room_code.text())
        QApplication.clipboard().setText(invite)
        self.lbl_status.setText(f"Copied '{invite}' to clipboard!")

    def _on_host_clicked(self):
        if hasattr(self, "combo_net_mode") and self.combo_net_mode.currentIndex() == 1:
            lan_ip = get_local_lan_ip()
            relay = f"ws://{lan_ip}:8765"
            self.edit_relay_url.setText(relay)
        else:
            relay = self.edit_relay_url.text().strip() or DEFAULT_RELAY_URL

        code = self.lbl_room_code.text().strip().upper()
        name = self.edit_user_name.text().strip() or "Host"
        self.btn_host.setEnabled(False)
        self.btn_host.setText("Starting Session...")
        if hasattr(self, "lbl_header_pill"):
            self.lbl_header_pill.setText("CONNECTING...")
            self.lbl_header_pill.setStyleSheet(
                "color: #fbbf24; border: 1px solid #f59e0b; background-color: #451a03; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;"
            )
        self.lbl_status.setText(f"Starting host session for room {code}...")
        self.sync_service.allow_guest_control = self.chk_guest_control.isChecked()
        self.sync_service.host_session(code, name, relay)

    def _on_copy_invite_clicked(self):
        invite = self._format_invite_string(self.sync_service.room_code)
        self.lbl_status.setText(f"Copied '{invite}' to clipboard.")
        QApplication.clipboard().setText(invite)

    def _on_join_clicked(self):
        raw_text = self.edit_join_code.text().strip()
        if not raw_text:
            if hasattr(self, "lbl_join_error"):
                self.lbl_join_error.setText("Please enter a room code or host IP.")
                self.lbl_join_error.setVisible(True)
            self.lbl_status.setText("Please enter a room code first.")
            return

        if hasattr(self, "lbl_join_error"):
            self.lbl_join_error.setVisible(False)

        name = self.edit_user_name.text().strip() or "Listener"
        relay = self.edit_relay_url.text().strip() or DEFAULT_RELAY_URL
        code = raw_text

        # Smart parsing for invite format (e.g. "ROOM5@192.168.1.50:8765", "localhost:8765", or direct IP)
        is_direct_addr = (
            raw_text.startswith(("ws://", "wss://", "localhost"))
            or any(raw_text.startswith(prefix) for prefix in ("192.", "10.", "172.", "127."))
        )
        if "@" in raw_text:
            parts = raw_text.split("@", 1)
            code = parts[0].strip()
            remote = parts[1].strip()
            if not remote.startswith(("ws://", "wss://")):
                if ":" not in remote:
                    remote = f"{remote}:8765"
                remote = f"ws://{remote}"
            relay = remote
            self.edit_relay_url.setText(relay)
        elif is_direct_addr:
            remote = raw_text
            if not remote.startswith(("ws://", "wss://")):
                if ":" not in remote:
                    remote = f"{remote}:8765"
                remote = f"ws://{remote}"
            relay = remote
            self.edit_relay_url.setText(relay)
            code = "LAN"

        code = code.upper()
        self.btn_join.setEnabled(False)
        self.btn_join.setText("Connecting...")
        if hasattr(self, "lbl_header_pill"):
            self.lbl_header_pill.setText("CONNECTING...")
            self.lbl_header_pill.setStyleSheet(
                "color: #fbbf24; border: 1px solid #f59e0b; background-color: #451a03; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;"
            )
        self.lbl_status.setText(f"Connecting to party {code}...")
        self.sync_service.join_session(code, name, relay)

    def _on_leave_clicked(self):
        self.sync_service.disconnect_session()

    def _on_connected(self, room_code: str, is_host: bool, members: list):
        self.btn_host.setEnabled(True)
        self.btn_host.setText("START HOSTING SESSION")
        self.btn_join.setEnabled(True)
        self.btn_join.setText("JOIN PARTY SESSION")

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

        if hasattr(self, "lbl_header_pill"):
            self.lbl_header_pill.setText(f"HOST: {room_code}" if is_host else f"PARTY: {room_code}")
            self.lbl_header_pill.setStyleSheet(
                "color: #4ade80; border: 1px solid #22c55e; background-color: #052e16; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;"
            )

        self.members = list(members)
        self._update_transfer_ui()
        self._on_queue_updated(self.sync_service.party_queue)
        self.lbl_feed.setText(f"Connected to room {room_code}. Members: {', '.join(members)}")
        self.stack.setCurrentIndex(1)
        if self.panel and hasattr(self.panel, "update_party_hud"):
            self.panel.update_party_hud(True, room_code, is_host)

    def _on_disconnected(self, reason: str):
        self.btn_host.setEnabled(True)
        self.btn_host.setText("START HOSTING SESSION")
        self.btn_join.setEnabled(True)
        self.btn_join.setText("JOIN PARTY SESSION")
        if hasattr(self, "lbl_header_pill"):
            self.lbl_header_pill.setText("OFFLINE")
            self.lbl_header_pill.setStyleSheet(
                "color: #71717a; border: 1px solid #27272f; background-color: #121218; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;"
            )
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
            self.btn_transfer.setEnabled(True)
            self.btn_transfer.set_variant("action_purple")
            self.btn_transfer.setToolTip("Transfer host control to selected member")
        else:
            self.combo_members.addItem("Waiting for friends to join...")
            self.combo_members.setEnabled(False)
            self.btn_transfer.setEnabled(False)
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
                if not title and c_title:
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
            row.setFixedHeight(32)
            row.setStyleSheet(
                "QFrame { background-color: #161622; border: 1px solid #27272f; border-radius: 4px; padding: 2px 6px; }"
                "QFrame:hover { border-color: #5EF6FF; }"
            )
            h_layout = QHBoxLayout(row)
            h_layout.setContentsMargins(6, 2, 6, 2)
            h_layout.setSpacing(6)

            # Index badge
            lbl_num = QLabel(f"#{idx + 1}")
            lbl_num.setStyleSheet("color: #71717a; font-family: 'Consolas', monospace; font-size: 10px; font-weight: bold; background: transparent;")
            h_layout.addWidget(lbl_num)

            # Track Title & Artist (escaped against HTML injection)
            t_title = html.escape(str(item.get("title", "Unknown Title")))
            t_artist = html.escape(str(item.get("artist", "")))
            disp = f"<b>{t_title}</b>"
            if t_artist and t_artist != "Talia Music Player":
                disp += f" - <span style='color:#a1a1aa;'>{t_artist}</span>"
            lbl_info = QLabel(disp)
            lbl_info.setStyleSheet("color: #f4f4f5; font-size: 11px; background: transparent; border: none;")
            lbl_info.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            h_layout.addWidget(lbl_info, 1)

            # 'Added by' badge
            added_by = str(item.get("added_by", ""))
            is_own = (added_by == current_user)
            tag_color = "#5EF6FF" if is_own else "#a1a1aa"
            tag_text = "You" if is_own else html.escape(added_by)
            lbl_by = QLabel(f"[by {tag_text}]")
            lbl_by.setStyleSheet(f"color: {tag_color}; font-size: 10px; font-weight: 600; background: transparent; border: none;")
            h_layout.addWidget(lbl_by)

            # Remove permission: Host can remove any song; member can remove ONLY their own
            if is_host or is_own:
                item_id = item.get("id")
                btn_del = CyberChamferButton("✕", variant="delete_playlist")
                btn_del.setFixedSize(20, 20)
                btn_del.setToolTip("Remove from room queue" if is_host else "Remove your song")
                btn_del.clicked.connect(lambda _, q_id=item_id: self.sync_service.remove_from_party_queue(q_id))
                h_layout.addWidget(btn_del)

            self.queue_list_layout.addWidget(row)

        self.queue_list_layout.addStretch(1)

    def _set_status(self, text: str):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 10px;")

    def _set_error(self, text: str):
        self.btn_host.setEnabled(True)
        self.btn_host.setText("START HOSTING SESSION")
        self.btn_join.setEnabled(True)
        self.btn_join.setText("JOIN PARTY SESSION")
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet("color: #f87171; font-size: 11px; font-weight: bold;")
        if hasattr(self, "lbl_join_error"):
            self.lbl_join_error.setText(text)
            self.lbl_join_error.setVisible(True)
        if hasattr(self, "lbl_header_pill") and self.stack.currentIndex() == 0:
            self.lbl_header_pill.setText("OFFLINE")
            self.lbl_header_pill.setStyleSheet(
                "color: #71717a; border: 1px solid #27272f; background-color: #121218; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;"
            )
        lowered = text.lower()
        if self.stack.currentIndex() != 0 and (
            "not exist" in lowered
            or "offline" in lowered
            or "room closed" in lowered
            or "host has left" in lowered
            or "closed" in lowered
        ):
            self.stack.setCurrentIndex(0)
            if hasattr(self, "lbl_header_pill"):
                self.lbl_header_pill.setText("OFFLINE")
                self.lbl_header_pill.setStyleSheet(
                    "color: #71717a; border: 1px solid #27272f; background-color: #121218; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 6px;"
                )
            if self.panel and hasattr(self.panel, "update_party_hud"):
                self.panel.update_party_hud(False, "", False)

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def reject(self):
        self.hide()
