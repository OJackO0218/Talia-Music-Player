from party_dialog import PartySyncDialog
from party_sync import PartySyncService
from spotify_dialog import SpotifySyncDialog
from spotify_sync import SpotifySyncService
from discord_service import DiscordRpcService, parse_track_info
from typing import Optional
"""Main controller panel for Talia playback, appearance, and configuration."""

import logging
import os
import random
import re
import subprocess
import sys
import threading
import time

log = logging.getLogger("ControlPanel")

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon
from PyQt6.QtMultimedia import QMediaDevices
from PyQt6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from audio_engine import CyberAudioEngine
from config import (
    COLOR_THEMES,
    DEFAULT_MUSIC_DIR,
    FONTS_DIR,
    ICON_PATH,
    MAX_CHAR_SIZE,
    MIN_CHAR_SIZE,
    PNGS_DIR,
    PROJECT_ROOT,
    SUPPORTED_AUDIO_EXTS,
    VK_CONTROL,
    VK_F7,
    VK_F8,
    VK_F9,
    VK_F10,
    VK_F11,
    VK_OEM_4,
    VK_OEM_6,
    save_settings,
    trim_process_memory,
    user32,
)
from download_panel import DownloadPanelMixin
from guide_dialog import GuideDialog
from overlay import OverlayWindow
from playlist_panel import PlaylistPanelMixin
from settings_dialog import SettingsDialog
from song_downloader import SongDownloaderService
from ui_theme import SHARED_PANEL_STYLE
from ui_widgets import (
    CyberScrollingTrackLabel,
    NoScrollComboBox,
    create_section_header,
)

log = logging.getLogger(__name__)


class ControlPanel(PlaylistPanelMixin, DownloadPanelMixin, QWidget):
    """Clean, modern controller for Talia Music Player, Visualizer, and Settings."""

    def __init__(self, overlay: OverlayWindow, audio_engine: CyberAudioEngine, lyrics_overlay=None):
        super().__init__()
        self.overlay = overlay
        self.overlay.panel = self
        self.audio_engine = audio_engine
        self.lyrics_overlay = lyrics_overlay
        if self.lyrics_overlay:
            self.lyrics_overlay.panel = self
        self.lyric_presets = {
            "Electric Blue": "#00ffff",
            "Cyberpunk Blue": "#64f0f8",
            "Electric Cyan": "#00ffff",
            "Pure White": "#ffffff",
            "Soft Cyan": "#38bdf8",
            "Soft Pink": "#f472b6",
            "Soft Purple": "#c084fc",
            "Soft Yellow": "#fde047",
            "Mint Green": "#4ade80",
        }
        self.last_f7_state = False
        self.last_bracket_left_state = False
        self.last_bracket_right_state = False
        self.last_f8_state = False
        self.last_f9_state = False
        self.last_f10_state = False
        self.last_f11_state = False
        self.is_user_scrubbing = False
        self.setWindowTitle("Talia Player")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        # Stylized minimal player window
        self.setMinimumSize(420, 540)
        self.resize(460, 640)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setStyleSheet(SHARED_PANEL_STYLE)
        self.init_ui()

        # Dedicated Full Settings & Customization Dialog
        self.settings_dialog = SettingsDialog(self)

        # Direct attribute proxies for seamless backwards compatibility
        self.slider_size = self.settings_dialog.slider_size
        self.slider_opacity = self.settings_dialog.slider_opacity
        self.slider_eye_sens = self.settings_dialog.slider_eye_sens
        self.lbl_sens_val = self.settings_dialog.lbl_sens_val
        self.chk_scanlines = None
        self.chk_bass_pop = self.settings_dialog.chk_bass_pop
        self.chk_head_bop = getattr(self.settings_dialog, 'chk_head_bop', None)
        self.combo_mode = self.settings_dialog.combo_mode
        self.combo_theme = self.settings_dialog.combo_theme
        self.combo_lyric_color = self.settings_dialog.combo_lyric_color
        self.combo_font = self.settings_dialog.combo_font
        self.slider_lyric_size = self.settings_dialog.slider_lyric_size
        self.lbl_lyric_size_val = self.settings_dialog.lbl_lyric_size_val
        self.btn_pick_color = self.settings_dialog.btn_pick_color
        self.chk_word_glow = self.settings_dialog.chk_word_glow
        self.chk_dialogue_mode = getattr(self.settings_dialog, "chk_dialogue_mode", None)
        self.lbl_sync_offset = self.settings_dialog.lbl_sync_offset
        self.btn_save_settings = self.settings_dialog.btn_save_settings
        self.lbl_folder_path = self.settings_dialog.lbl_folder_path

        # Song Downloader & Auto-Sync Service (YouTube search -> Opus 160k -> Synced LRC)
        self.downloader = SongDownloaderService(self)
        self.downloader.search_finished.connect(self._on_search_finished)
        self.downloader.search_error.connect(self._on_search_error)
        self.downloader.download_progress.connect(self._on_download_progress)
        self.downloader.download_finished.connect(self._on_download_finished)

        # Real-time Party Sync Service (Listen Together)
        self.party_sync = PartySyncService(self)
        self.party_dialog = PartySyncDialog(self)
        self.party_sync.track_received.connect(self._on_party_track_received)
        self.party_sync.play_received.connect(self._on_party_play_received)
        self.party_sync.pause_received.connect(self._on_party_pause_received)
        self.party_sync.seek_received.connect(self._on_party_seek_received)
        self.party_sync.heartbeat_received.connect(self._on_party_heartbeat_received)
        self.party_sync.track_auto_downloaded.connect(self._on_party_track_downloaded)
        self.party_sync.peer_joined.connect(self._on_party_peer_joined)
        self.party_sync.connected.connect(self._on_party_connected)
        self.party_sync.disconnected.connect(self._on_party_disconnected)
        self.party_sync.host_transferred.connect(self._on_party_host_transferred)
        self.party_sync.queue_updated.connect(self._on_party_queue_updated)
        self.party_sync.prefetch_completed.connect(self._on_prefetch_completed)
        self._is_handling_party_event = False
        self._last_party_heartbeat = 0.0
        self._prefetching_track_id: Optional[str] = None
        self._waiting_for_download_to_play: bool = False
        self.audio_engine.play_next_hook = self.play_next_track

        # Spotify Playlist Sync & Import Service
        self.spotify_service = SpotifySyncService(self)
        self.spotify_dialog = SpotifySyncDialog(self)

        # Discord Rich Presence Service
        self._discord_rpc_enabled = True
        self.discord_service = DiscordRpcService(enabled=self._discord_rpc_enabled)
        self._last_discord_update = 0.0

        # Polling timer for global hotkeys (50ms)
        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.timeout.connect(self.check_hotkeys)
        self.hotkey_timer.start(50)

        # Eco Mode & Download Destination state
        self.eco_mode = False
        self.saved_dl_folder = ""

        # Timeline & auto-advance timer (always active in background for reliable track progression)
        self.timeline_timer = QTimer(self)
        self.timeline_timer.timeout.connect(self.update_timeline)
        self.timeline_timer.start(500 if getattr(self, "eco_mode", False) else 200)

        # Real-time audio output device monitoring (headset plug/unplug)
        self._last_stream_drop_check = 0.0
        try:
            self.media_devices = QMediaDevices(self)
            self._device_change_timer = QTimer(self)
            self._device_change_timer.setSingleShot(True)
            self._device_change_timer.setInterval(350)
            self._device_change_timer.timeout.connect(self._do_audio_device_recovery)
            self.media_devices.audioOutputsChanged.connect(self._on_audio_device_changed)
        except Exception as exc:
            log.warning("Could not initialize QMediaDevices monitor: %s", exc)

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # -------------------------------------------------------------
        # PINNED PLAYBACK HEADER (Always visible even when scrolled)
        # -------------------------------------------------------------
        pinned_header = QWidget()
        pinned_header.setObjectName("pinnedPlaybackHeader")
        pinned_layout = QVBoxLayout(pinned_header)
        pinned_layout.setContentsMargins(12, 10, 12, 6)
        pinned_layout.setSpacing(8)

        # --- PRIMARY TOGGLES (Settings, Move, Mode, Lyrics, Eco) ---
        hbox_top_toggles = QHBoxLayout()
        hbox_top_toggles.setSpacing(4)
        self.btn_open_settings = QPushButton("Settings")
        self.btn_open_settings.setObjectName("btnOpenSettings")
        self.btn_open_settings.setToolTip("Open Full Settings & Customization")
        self.btn_open_settings.setStyleSheet(
            "background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; font-weight: 600; font-size: 11px; padding: 5px 8px;"
        )
        self.btn_open_settings.clicked.connect(self.open_settings_window)
        hbox_top_toggles.addWidget(self.btn_open_settings)
        self.btn_move_talia = QPushButton("Lock Window")
        self.btn_move_talia.setObjectName("btnMoveTalia")
        self.btn_move_talia.clicked.connect(self.toggle_move_talia)
        # Note: Move mode is now controlled exclusively via X/Y sliders & Center Talia in Settings
        self.btn_audio_mode = QPushButton("Player Mode")
        self.btn_audio_mode.setObjectName("btnAudioMode")
        self.btn_audio_mode.clicked.connect(self.toggle_audio_mode)
        hbox_top_toggles.addWidget(self.btn_audio_mode)
        self.btn_lyrics = QPushButton("Lyrics: On")
        self.btn_lyrics.setObjectName("btnLyrics")
        self.btn_lyrics.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: bold; font-size: 11px; padding: 5px 8px;"
        )
        self.btn_lyrics.clicked.connect(self.toggle_lyrics)
        hbox_top_toggles.addWidget(self.btn_lyrics)
        self.btn_eco = QPushButton("Eco Mode: Off")
        self.btn_eco.setObjectName("btnEco")
        self.btn_eco.setToolTip("Toggle Eco Mode (< 1% CPU) [F11]")
        self.btn_eco.clicked.connect(self.toggle_eco_mode)
        hbox_top_toggles.addWidget(self.btn_eco)
        pinned_layout.addLayout(hbox_top_toggles)

        # --- SYNC & PARTY BUTTONS (Listen Together & Spotify Sync) ---
        hbox_sync_tools = QHBoxLayout()
        hbox_sync_tools.setSpacing(6)

        self.btn_party_sync = QPushButton("Listen Together")
        self.btn_party_sync.setObjectName("btnPartySync")
        self.btn_party_sync.setToolTip("Listen together with friends in real-time with synchronized lyrics and playback")
        self.btn_party_sync.setStyleSheet(
            "background-color: #1e1b4b; color: #a78bfa; border: 1px solid #7c3aed; font-weight: bold; font-size: 11px; padding: 5px 10px; border-radius: 4px;"
        )
        self.btn_party_sync.clicked.connect(self.open_party_dialog)
        hbox_sync_tools.addWidget(self.btn_party_sync, 1)

        self.btn_spotify_sync = QPushButton("Spotify Sync")
        self.btn_spotify_sync.setObjectName("btnSpotifySync")
        self.btn_spotify_sync.setToolTip("Import and auto-download Spotify playlists with synchronized lyrics")
        self.btn_spotify_sync.setStyleSheet(
            "background-color: #064e3b; color: #6ee7b7; border: 1px solid #059669; font-weight: bold; font-size: 11px; padding: 5px 10px; border-radius: 4px;"
        )
        self.btn_spotify_sync.clicked.connect(self.open_spotify_dialog)
        hbox_sync_tools.addWidget(self.btn_spotify_sync, 1)

        pinned_layout.addLayout(hbox_sync_tools)

        # --- SECTION: PLAYBACK & VOLUME ---
        pinned_layout.addWidget(create_section_header("Playback & Volume"))

        # Track title banner (Cyberpunk Rajdhani marquee)
        self.lbl_track_title = CyberScrollingTrackLabel()
        pinned_layout.addWidget(self.lbl_track_title)

        # Timeline seeker
        hbox_time = QHBoxLayout()
        hbox_time.setSpacing(6)
        self.lbl_time_cur = QLabel("00:00")
        self.lbl_time_cur.setStyleSheet(
            "color: #a1a1aa; font-family: 'Consolas', monospace; font-size: 11px;"
        )
        self.slider_seek = QSlider(Qt.Orientation.Horizontal)
        self.slider_seek.setRange(0, 1000)
        self.slider_seek.setValue(0)
        self.slider_seek.sliderPressed.connect(self.on_seek_pressed)
        self.slider_seek.sliderReleased.connect(self.on_seek_released)
        self.slider_seek.sliderMoved.connect(self.on_seek_moved)
        self.lbl_time_dur = QLabel("00:00")
        self.lbl_time_dur.setStyleSheet(
            "color: #a1a1aa; font-family: 'Consolas', monospace; font-size: 11px;"
        )
        hbox_time.addWidget(self.lbl_time_cur)
        hbox_time.addWidget(self.slider_seek)
        hbox_time.addWidget(self.lbl_time_dur)
        pinned_layout.addLayout(hbox_time)

        # Playback Transport Buttons (Clean Symbols: Shuffle, Rewind, Play/Pause, Next)
        hbox_controls = QHBoxLayout()
        hbox_controls.setSpacing(8)
        hbox_controls.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_shuffle = QPushButton("⇄")
        self.btn_shuffle.setFont(QFont("Segoe UI Symbol", 12, QFont.Weight.Bold))
        self.btn_shuffle.setToolTip("Shuffle: Disabled")
        self.btn_shuffle.setFixedSize(38, 30)
        self.btn_shuffle.setStyleSheet(
            "background-color: #27272a; color: #71717a; border: 1px solid #3f3f46; border-radius: 4px;"
        )
        self.btn_shuffle.clicked.connect(self.toggle_shuffle)
        hbox_controls.addWidget(self.btn_shuffle)

        self.btn_prev = QPushButton("⏮")
        self.btn_prev.setFont(QFont("Segoe UI Symbol", 12, QFont.Weight.Bold))
        self.btn_prev.setToolTip("Previous Track [Rewind]")
        self.btn_prev.setFixedSize(46, 30)
        self.btn_prev.setStyleSheet(
            "background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px;"
        )
        self.btn_prev.clicked.connect(self.on_prev_clicked)
        hbox_controls.addWidget(self.btn_prev)

        self.btn_play_pause = QPushButton("▶")
        self.btn_play_pause.setFont(QFont("Segoe UI Symbol", 13, QFont.Weight.Bold))
        self.btn_play_pause.setObjectName("btnPlayPause")
        self.btn_play_pause.setToolTip("Play / Pause [Space]")
        self.btn_play_pause.setFixedSize(56, 30)
        self.btn_play_pause.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; border-radius: 4px;"
        )
        self.btn_play_pause.clicked.connect(self.on_play_pause_clicked)
        hbox_controls.addWidget(self.btn_play_pause)

        self.btn_next = QPushButton("⏭")
        self.btn_next.setFont(QFont("Segoe UI Symbol", 12, QFont.Weight.Bold))
        self.btn_next.setToolTip("Next Track [Next]")
        self.btn_next.setFixedSize(46, 30)
        self.btn_next.setStyleSheet(
            "background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px;"
        )
        self.btn_next.clicked.connect(self.on_next_clicked)
        hbox_controls.addWidget(self.btn_next)

        pinned_layout.addLayout(hbox_controls)

        # Small Volume Slider
        hbox_vol = QHBoxLayout()
        hbox_vol.setSpacing(8)
        lbl_vol_title = QLabel("Vol:")
        lbl_vol_title.setStyleSheet("color: #a1a1aa; font-weight: 600; font-size: 11px;")
        hbox_vol.addWidget(lbl_vol_title)
        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(int(self.audio_engine.volume * 100))
        self.slider_vol.valueChanged.connect(self.on_volume_changed)
        hbox_vol.addWidget(self.slider_vol)
        self.lbl_vol_val = QLabel(f"{int(self.audio_engine.volume * 100)}%")
        self.lbl_vol_val.setFixedWidth(40)
        self.lbl_vol_val.setStyleSheet(
            "color: #f4f4f5; font-family: 'Consolas', monospace; font-weight: 600; font-size: 11px;"
        )
        hbox_vol.addWidget(self.lbl_vol_val)
        pinned_layout.addLayout(hbox_vol)

        # Divider separating pinned playback area from scrollable playlist
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background-color: #27272a; max-height: 1px;")
        pinned_layout.addWidget(divider)

        root_layout.addWidget(pinned_header)

        # -------------------------------------------------------------
        # SCROLLABLE CONTENT BODY (Song Selection, Download Songs)
        # -------------------------------------------------------------
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(12, 6, 12, 12)
        content_layout.setSpacing(8)

        # --- SECTION: SONG SELECTION ---
        content_layout.addWidget(create_section_header("Song Selection"))

        # Folder Quick-Switcher (Clean 1-line dropdown + browse button)
        hbox_folder = QHBoxLayout()
        hbox_folder.setSpacing(6)
        lbl_folder_icon = QLabel("Folder:")
        lbl_folder_icon.setStyleSheet("color: #a1a1aa; font-weight: 600; font-size: 11px;")
        hbox_folder.addWidget(lbl_folder_icon)

        self.combo_active_folder = NoScrollComboBox()
        self.combo_active_folder.setStyleSheet("""
            QComboBox {
                background-color: #202024;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: 500;
            }
            QComboBox:hover {
                border-color: #3b82f6;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox QAbstractItemView {
                background-color: #1f1f23;
                color: #f4f4f5;
                selection-background-color: #3b82f6;
                border: 1px solid #3f3f46;
                padding: 4px;
            }
        """)
        self.combo_active_folder.activated.connect(self.on_active_folder_selected)
        hbox_folder.addWidget(self.combo_active_folder, 1)

        self.btn_browse_folder = QPushButton("...")
        self.btn_browse_folder.setToolTip("Browse and choose a custom music folder")
        self.btn_browse_folder.setFixedWidth(34)
        self.btn_browse_folder.setStyleSheet(
            "background-color: #27272a; color: #a1a1aa; border: 1px solid #3f3f46; font-weight: bold; border-radius: 4px;"
        )
        self.btn_browse_folder.clicked.connect(self.choose_music_folder)
        hbox_folder.addWidget(self.btn_browse_folder)
        content_layout.addLayout(hbox_folder)

        # Search Bar with live filter and clear button
        hbox_search = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search songs...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #202024;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
        """)
        self.search_input.textChanged.connect(self.filter_tracks)
        hbox_search.addWidget(self.search_input)

        self.btn_clear_search = QPushButton("✕")
        self.btn_clear_search.setFixedWidth(28)
        self.btn_clear_search.setStyleSheet(
            "background-color: #27272a; color: #a1a1aa; border: 1px solid #3f3f46; font-weight: bold; border-radius: 4px;"
        )
        self.btn_clear_search.clicked.connect(lambda: self.search_input.clear())
        hbox_search.addWidget(self.btn_clear_search)
        content_layout.addLayout(hbox_search)

        # Track List (Wider & Taller, each row includes tactile + queue button)
        self.list_tracks = QListWidget()
        self.list_tracks.setMinimumHeight(180)
        self.list_tracks.setFixedHeight(210)
        self.list_tracks.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_tracks.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_tracks.customContextMenuRequested.connect(self.show_track_context_menu)
        self.list_tracks.itemDoubleClicked.connect(self.on_track_double_clicked)
        self.list_tracks.setStyleSheet("""
            QListWidget {
                background-color: #18181b;
                border: 1px solid #2d2d35;
                border-radius: 4px;
                padding: 2px;
            }
            QListWidget::item {
                border-radius: 3px;
                padding: 1px;
            }
            QListWidget::item:selected {
                background-color: #27272a;
            }
            QListWidget::item:hover {
                background-color: #222227;
            }
        """)
        content_layout.addWidget(self.list_tracks)

        # Queue Status & Toggle Actions
        hbox_track_actions = QHBoxLayout()
        hbox_track_actions.setSpacing(6)
        self.btn_toggle_queue = QPushButton("Queue (0)")
        self.btn_toggle_queue.setStyleSheet(
            "background-color: #27272a; color: #a1a1aa; border: 1px solid #3f3f46; font-size: 10px; font-weight: 500; padding: 4px 10px; border-radius: 3px;"
        )
        self.btn_toggle_queue.clicked.connect(self.toggle_queue_panel)
        hbox_track_actions.addWidget(self.btn_toggle_queue)

        self.btn_clear_queue = QPushButton("Clear Queue")
        self.btn_clear_queue.setStyleSheet(
            "background-color: #27272a; color: #f87171; border: 1px solid #3f3f46; font-size: 10px; padding: 4px 10px; border-radius: 3px;"
        )
        self.btn_clear_queue.clicked.connect(self.on_clear_queue_clicked)
        hbox_track_actions.addWidget(self.btn_clear_queue)
        hbox_track_actions.addStretch()
        content_layout.addLayout(hbox_track_actions)

        # Collapsible Upcoming Queue Container
        self.queue_container = QWidget()
        queue_layout = QVBoxLayout(self.queue_container)
        queue_layout.setContentsMargins(0, 4, 0, 4)
        queue_layout.setSpacing(4)
        lbl_queue_hdr = QLabel("Upcoming Queue:")
        lbl_queue_hdr.setStyleSheet("color: #a1a1aa; font-weight: 600; font-size: 10px;")
        queue_layout.addWidget(lbl_queue_hdr)
        self.list_queue = QListWidget()
        self.list_queue.setFixedHeight(85)
        self.list_queue.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_queue.customContextMenuRequested.connect(self.show_queue_context_menu)
        self.list_queue.itemDoubleClicked.connect(self.on_queue_item_double_clicked)
        queue_layout.addWidget(self.list_queue)
        self.queue_container.setVisible(False)
        content_layout.addWidget(self.queue_container)

        # --- SECTION: SONG SEARCH & AUTO-DOWNLOAD ---
        content_layout.addWidget(create_section_header("Download Songs"))

        # Download Destination Folder Dropdown Row
        hbox_dl_folder = QHBoxLayout()
        hbox_dl_folder.setSpacing(6)
        lbl_dl_folder = QLabel("Save to:")
        lbl_dl_folder.setStyleSheet("color: #a1a1aa; font-size: 11px; font-weight: 500;")
        hbox_dl_folder.addWidget(lbl_dl_folder)
        self.combo_dl_folder = NoScrollComboBox()

        self.combo_dl_folder.setStyleSheet("""

            QComboBox {

                background-color: #202024;

                border: 1px solid #3f3f46;

                border-radius: 4px;

                color: #f4f4f5;

                padding: 4px 8px;

                font-size: 11px;

            }

            QComboBox:hover {

                border-color: #52525b;

            }

            QComboBox QAbstractItemView {

                background-color: #18181b;

                color: #f4f4f5;

                border: 1px solid #3f3f46;

                selection-background-color: #3b82f6;

                selection-color: #ffffff;

            }

        """)

        self.combo_dl_folder.currentIndexChanged.connect(self.on_dl_folder_changed)
        hbox_dl_folder.addWidget(self.combo_dl_folder, 1)
        content_layout.addLayout(hbox_dl_folder)

        # Search Input row
        hbox_dl_search = QHBoxLayout()
        hbox_dl_search.setSpacing(6)
        self.edit_dl_search = QLineEdit()
        self.edit_dl_search.setPlaceholderText(
            "Search YouTube (e.g. Hate Me Ellie Goulding) or paste URL..."
        )

        self.edit_dl_search.setStyleSheet("""

            QLineEdit {

                background-color: #202024;

                color: #f4f4f5;

                border: 1px solid #3f3f46;

                border-radius: 4px;

                padding: 5px 8px;

                font-size: 11px;

            }

            QLineEdit:focus {

                border-color: #3b82f6;

            }

        """)

        self.edit_dl_search.returnPressed.connect(self.on_dl_search_clicked)
        hbox_dl_search.addWidget(self.edit_dl_search)
        self.btn_dl_search = QPushButton("Search")
        self.btn_dl_search.setStyleSheet(
            "background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: 500; font-size: 11px; padding: 5px 12px;"
        )
        self.btn_dl_search.clicked.connect(self.on_dl_search_clicked)
        hbox_dl_search.addWidget(self.btn_dl_search)
        content_layout.addLayout(hbox_dl_search)

        # Download Tip Label
        self.lbl_dl_tip = QLabel(
            "Tip: For best lyric sync, download Lyric Videos or Audio Tracks instead of Official MVs (music videos often have extra intros/breaks that desync lyrics)."
        )
        self.lbl_dl_tip.setStyleSheet(
            "color: #71717a; font-size: 10px; font-style: italic; margin-top: 1px;"
        )
        self.lbl_dl_tip.setWordWrap(True)
        content_layout.addWidget(self.lbl_dl_tip)

        # Search Results List (Collapsible / Dynamic)
        self.list_dl_results = QListWidget()
        self.list_dl_results.setFixedHeight(95)

        self.list_dl_results.setStyleSheet("""

            QListWidget {

                background-color: #202024;

                border: 1px solid #3f3f46;

                border-radius: 4px;

                color: #f4f4f5;

                font-size: 11px;

                padding: 2px;

            }

            QListWidget::item {

                padding: 4px 6px;

                border-bottom: 1px solid #27272a;

            }

            QListWidget::item:selected {

                background-color: #3b82f6;

                color: #ffffff;

            }

        """)

        self.list_dl_results.itemDoubleClicked.connect(self.on_dl_item_double_clicked)
        self.list_dl_results.itemSelectionChanged.connect(self.on_dl_selection_changed)
        self.list_dl_results.setVisible(False)
        content_layout.addWidget(self.list_dl_results)

        # Download Action Button
        self.btn_dl_action = QPushButton("+ Add to Library")
        self.btn_dl_action.setStyleSheet(
            "background-color: #166534; color: #4ade80; border: 1px solid #22c55e; font-size: 11px; font-weight: 600; padding: 6px 10px; border-radius: 4px;"
        )
        self.btn_dl_action.clicked.connect(self.on_dl_download_clicked)
        self.btn_dl_action.setVisible(False)
        content_layout.addWidget(self.btn_dl_action)

        # Real-time Status / Progress Log
        self.lbl_dl_status = QLabel("")
        self.lbl_dl_status.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        self.lbl_dl_status.setWordWrap(True)
        self.lbl_dl_status.setVisible(False)
        content_layout.addWidget(self.lbl_dl_status)
        scroll_area.setWidget(content_widget)
        root_layout.addWidget(scroll_area, 1)

        # -------------------------------------------------------------

        # BOTTOM SHORTCUT BAR (Clean and subtle)

        # -------------------------------------------------------------
        bottom_bar = QWidget()
        bottom_bar.setStyleSheet(
            "background-color: #18181b; border-top: 1px solid #27272a; padding: 4px;"
        )
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(12, 6, 12, 6)
        shortcuts = [
            ("F7", "Lyrics"),
            ("F8", "Move"),
            ("F9", "Toggle"),
            ("F10", "Source"),
            ("F11", "Eco"),
        ]
        for i, (key, desc) in enumerate(shortcuts):
            lbl = QLabel(
                f"<span style='color: #a1a1aa; font-weight: 600;'>{key}:</span> <span style='color: #71717a;'>{desc}</span>"
            )
            lbl.setStyleSheet("font-size: 10px; font-family: 'Segoe UI', Arial, sans-serif;")
            bottom_layout.addWidget(lbl)
            if i < len(shortcuts) - 1:
                sep = QLabel("•")
                sep.setStyleSheet("color: #3f3f46; font-size: 10px;")
                bottom_layout.addWidget(sep)
        root_layout.addWidget(bottom_bar)
        self.populate_playlist_ui()

    def toggle_audio_mode(self):
        """Toggles between Built-in Player and Desktop Audio loopback."""
        new_mode = "desktop" if self.audio_engine.audio_mode == "player" else "player"
        self.set_audio_mode(new_mode)

    def set_audio_mode(self, mode: str):
        self.audio_engine.set_audio_mode(mode)
        self.update_audio_mode_ui()
        self.sync_play_state()

    def update_audio_mode_ui(self):
        is_desktop = self.audio_engine.audio_mode == "desktop"
        txt = "Desktop Audio" if is_desktop else "Player Mode"
        style = (
            "background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: 500;"
            if is_desktop
            else ""
        )
        if hasattr(self, "btn_audio_mode"):
            self.btn_audio_mode.setText(txt)
            self.btn_audio_mode.setStyleSheet(style)
        if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "btn_audio_mode"):
            self.settings_dialog.btn_audio_mode.setText(txt)
            self.settings_dialog.btn_audio_mode.setStyleSheet(style)

    def on_play_pause_clicked(self):
        if self.audio_engine.audio_mode == "desktop":
            self.audio_engine.toggle_play_pause()
            return
        if not self.audio_engine.playlist:
            return
        if self.audio_engine.current_index < 0:
            if getattr(self.audio_engine, "_shuffle", False) and getattr(self.audio_engine, "_shuffle_order", []):
                start_idx = self.audio_engine._shuffle_order[0]
            else:
                start_idx = random.randint(0, len(self.audio_engine.playlist) - 1)
            self.audio_engine.play_index(start_idx)
        else:
            self.audio_engine.toggle_play_pause()
        self.sync_play_state()

    def sync_play_state(self):
        self.update_sync_offset_display()
        if self.audio_engine.audio_mode == "desktop":
            self.btn_play_pause.setText("Live Audio")
            self.btn_play_pause.setStyleSheet(
                "background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6;"
            )
            self.lbl_track_title.setText("Desktop Audio")
            return
        if self.audio_engine.is_playing:
            self.btn_play_pause.setText("Pause")
            self.btn_play_pause.setStyleSheet(
                "background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6;"
            )
            self.lbl_track_title.setText(f"{self.audio_engine.get_current_track_title()}")
        else:
            self.btn_play_pause.setText("Play")
            self.btn_play_pause.setStyleSheet("")
            self.lbl_track_title.setText(f"{self.audio_engine.get_current_track_title()}")

        # Update Discord Rich Presence
        if hasattr(self, "discord_service") and self.discord_service:
            raw_title = self.audio_engine.get_current_track_title()
            is_playing = self.audio_engine.is_playing and self.audio_engine.audio_mode != "desktop"
            pos = self.audio_engine.get_position()
            dur = self.audio_engine.get_duration()
            self.discord_service.update_playback(raw_title, is_playing, pos, dur)

        # Broadcast playback state to Listen Together party
        if hasattr(self, "party_sync") and self.party_sync.is_connected:
            if not getattr(self, "_is_handling_party_event", False):
                if self.party_sync.is_host or self.party_sync.allow_guest_control:
                    curr_idx = self.audio_engine.current_index
                    last_idx = getattr(self, "_last_broadcast_party_idx", -999)
                    last_playing = getattr(self, "_last_broadcast_party_playing", None)
                    is_p = self.audio_engine.is_playing and self.audio_engine.audio_mode != "desktop"
                    cur_pos = self.audio_engine.get_position()

                    if curr_idx != last_idx:
                        self._last_broadcast_party_idx = curr_idx
                        self._last_broadcast_party_playing = is_p
                        self._broadcast_party_track()
                    elif is_p != last_playing:
                        self._last_broadcast_party_playing = is_p
                        if is_p:
                            self.party_sync.broadcast_play(cur_pos)
                        else:
                            self.party_sync.broadcast_pause(cur_pos)

        for r in range(self.list_tracks.count()):
            it = self.list_tracks.item(r)
            if it.data(Qt.ItemDataRole.UserRole) == self.audio_engine.current_index:
                self.list_tracks.setCurrentRow(r)
                break

    def refresh_queue_ui(self):
        """Refreshes the room queue display in PartySyncDialog if open."""
        if hasattr(self, "party_dialog") and self.party_dialog and hasattr(self.party_dialog, "_on_queue_updated"):
            if hasattr(self, "party_sync") and self.party_sync:
                self.party_dialog._on_queue_updated(self.party_sync.party_queue)

    def _on_party_queue_updated(self, queue: list):
        """Called whenever the room queue updates. Automatically checks and prefetches the next song."""
        self.refresh_queue_ui()
        self._check_and_prefetch_next_in_queue()

    def _check_and_prefetch_next_in_queue(self):
        """
        Inspects the immediate next track in the Party Queue (index 0).
        If not yet present in the local playlist/library, pre-downloads it
        in the background ahead of time so transitions are seamless and instant.
        Only prefetches the immediate next song (party_queue[0]), never later items.
        """
        if not hasattr(self, "party_sync") or not self.party_sync.is_connected:
            return
        if not self.party_sync.party_queue:
            return

        next_item = self.party_sync.party_queue[0]
        item_id = next_item.get("id")

        if getattr(self, "_prefetching_track_id", None) == item_id:
            return

        matched_idx = self.find_matching_party_track(next_item)
        if matched_idx >= 0:
            return

        self._prefetching_track_id = item_id
        log.info("[PARTY QUEUE] Pre-downloading next queued track ahead of time: %s", next_item.get("title"))

        threading.Thread(
            target=self._run_prefetch_next_track,
            args=(next_item,),
            daemon=True,
            name="PartyQueuePrefetcher",
        ).start()

    def _run_prefetch_next_track(self, track_data: dict):
        cur_folder = getattr(self.audio_engine, 'folder_path', None)
        if cur_folder and os.path.isdir(cur_folder):
            target_dir = os.path.join(cur_folder, "Downloaded Songs")
        else:
            target_dir = os.path.join(DEFAULT_MUSIC_DIR, "Downloaded Songs")
        os.makedirs(target_dir, exist_ok=True)

        query = track_data.get("yt_query")
        if not query:
            a = track_data.get("artist", "").strip()
            t = track_data.get("title", "").strip()
            if a.lower() in ("talia music player", "talia player", "unknown artist", "unknown"):
                a = ""
            query = f"{a} - {t}" if a else t
        query = re.sub(r"(?i)\btalia\s+(?:music\s+)?player\s*[-:]?\s*", "", query).strip()

        target_dur = float(track_data.get("duration", 0.0))
        ok = False
        final_path = ""
        if hasattr(self, "downloader") and self.downloader:
            ok, final_path = self.downloader.download_sync_query(
                query,
                target_dir,
                track_info=track_data,
                target_duration=target_dur,
                return_path=True,
            )
        self.party_sync.prefetch_completed.emit(bool(ok), final_path or "", track_data)

    def _on_prefetch_completed(self, ok: bool, file_path: str, track_data: dict):
        item_id = track_data.get("id")
        if getattr(self, "_prefetching_track_id", None) == item_id:
            self._prefetching_track_id = None

        if ok and file_path and os.path.exists(file_path):
            norm_target = os.path.normcase(os.path.abspath(file_path))
            target_idx = -1
            for idx, p in enumerate(self.audio_engine.playlist):
                if os.path.normcase(os.path.abspath(p)) == norm_target:
                    target_idx = idx
                    break
            if target_idx == -1:
                self.audio_engine.playlist.append(file_path)
                target_idx = len(self.audio_engine.playlist) - 1
                self.populate_playlist_ui()
            log.info("[PARTY QUEUE] Pre-download ready for '%s' at index %d", track_data.get("title"), target_idx)

            if hasattr(self, "party_sync") and self.party_sync.party_queue:
                for q_item in self.party_sync.party_queue:
                    if q_item.get("id") == item_id or q_item == track_data:
                        q_item["local_path"] = file_path
                        q_item["filename"] = os.path.basename(file_path)

            waiting = getattr(self, "_waiting_for_download_to_play", False)
            downloading_track = getattr(self, "_party_downloading_track", None)
            is_matching_waiting = waiting and (
                downloading_track is None
                or downloading_track == track_data
                or (item_id and downloading_track.get("id") == item_id)
                or (downloading_track.get("title") and downloading_track.get("title") == track_data.get("title"))
            )

            if is_matching_waiting:
                self._waiting_for_download_to_play = False
                self._party_downloading_track = None
                matched_idx = target_idx if 0 <= target_idx < len(self.audio_engine.playlist) else self.find_matching_party_track(track_data)
                if matched_idx >= 0:
                    is_host = hasattr(self, "party_sync") and self.party_sync.is_host
                    self._is_handling_party_event = True
                    try:
                        self.audio_engine.play_index(matched_idx)
                        if is_host:
                            self.audio_engine.play()
                        else:
                            seek_pos = getattr(self, "_last_known_host_pos", 0.0)
                            if seek_pos > 0:
                                self.audio_engine.seek(seek_pos)
                            if getattr(self, "_last_known_host_playing", True):
                                self.audio_engine.play()
                            else:
                                self.audio_engine.pause()
                        self.sync_play_state()
                    finally:
                        self._is_handling_party_event = False

                    if is_host:
                        self._broadcast_party_track()
                        self._check_and_prefetch_next_in_queue()
                else:
                    log.warning("[PARTY QUEUE] Downloaded track ready but could not determine index in playlist.")
        else:
            log.warning("[PARTY QUEUE] Pre-download failed for '%s'", track_data.get("title"))
            waiting = getattr(self, "_waiting_for_download_to_play", False)
            downloading_track = getattr(self, "_party_downloading_track", None)
            is_matching_waiting = waiting and (
                downloading_track is None
                or downloading_track == track_data
                or (item_id and downloading_track.get("id") == item_id)
            )
            if is_matching_waiting:
                self._waiting_for_download_to_play = False
                self._party_downloading_track = None
                if hasattr(self, "lbl_track_title") and self.lbl_track_title:
                    self.lbl_track_title.setText(f"[PARTY] Could not fetch '{track_data.get('title')}'")
                if hasattr(self, "party_sync") and self.party_sync.is_host:
                    QTimer.singleShot(1500, lambda: self.play_next_track(crossfade=False, force_skip=True))

    def play_next_track(self, crossfade: bool = False, force_skip: bool = False) -> bool:
        """
        Advances to the next track.
        If in an active Party Sync room as Host and tracks are queued in the party queue,
        pops and plays the next party track for all room members!
        Otherwise, plays the next track from the local playlist.
        """
        if hasattr(self, "party_sync") and self.party_sync.is_connected:
            # Guests must NEVER advance local playlists; they follow host broadcasts
            if not self.party_sync.is_host:
                log.info("[PARTY SYNC] Guest ignoring local play_next_track; following host.")
                return False

            if force_skip:
                self._waiting_for_download_to_play = False
                self._party_downloading_track = None
                self._prefetching_track_id = None

            # If host is already waiting on a queued download, ignore duplicate trigger calls (unless force_skip)
            if not force_skip and (getattr(self, "_waiting_for_download_to_play", False) or getattr(self, "_party_downloading_track", None)):
                log.info("[PARTY SYNC] Party track download already in progress; holding advance.")
                return False

            if self.party_sync.party_queue:
                next_item = self.party_sync.pop_next_party_track()
                if next_item:
                    matched_idx = self.find_matching_party_track(next_item)
                    if matched_idx >= 0:
                        self._waiting_for_download_to_play = False
                        self._party_downloading_track = None
                        self.audio_engine.play_index(matched_idx, crossfade=crossfade)
                        self.sync_play_state()
                        self.refresh_queue_ui()
                        self._broadcast_party_track()
                        # Inspect and prefetch the NEW next song in line!
                        self._check_and_prefetch_next_in_queue()
                        return True
                    else:
                        is_mid_prefetch = (getattr(self, "_prefetching_track_id", None) == next_item.get("id"))
                        log.info("[PARTY QUEUE] Host waiting on queued track: %s (prefetching=%s)", next_item.get("title"), is_mid_prefetch)
                        self.audio_engine.pause()
                        self._party_downloading_track = next_item
                        self._waiting_for_download_to_play = True

                        title = next_item.get("title", "Unknown Track")
                        if hasattr(self, "lbl_track_title") and self.lbl_track_title:
                            self.lbl_track_title.setText(f"[PARTY] Downloading '{title}'...")
                            self.lbl_track_title.full_text = f"[PARTY] Downloading '{title}'..."
                        if self.overlay:
                            self.overlay.update()

                        # Inform room of the track being prepared
                        self.party_sync.broadcast_track(
                            title=next_item.get("title", ""),
                            artist=next_item.get("artist", ""),
                            filename=next_item.get("filename", ""),
                            yt_query=next_item.get("yt_query", ""),
                            duration=float(next_item.get("duration", 0.0)),
                            timestamp=0.0,
                            is_playing=False,
                        )

                        if not is_mid_prefetch:
                            self._prefetching_track_id = next_item.get("id")
                            threading.Thread(
                                target=self._run_prefetch_next_track,
                                args=(next_item,),
                                daemon=True,
                                name="PartyQueuePrefetcher",
                            ).start()
                        return True

        self.audio_engine.next_track(crossfade=crossfade)
        self.sync_play_state()
        if hasattr(self, "party_sync") and self.party_sync.is_connected and self.party_sync.is_host:
            self._broadcast_party_track()
        self.refresh_queue_ui()
        return True

    def on_next_clicked(self):
        self.play_next_track(crossfade=False, force_skip=True)
        if hasattr(self, "lbl_track_title"):
            self.lbl_track_title.trigger_symbol("forward")
        if self.overlay:
            self.overlay.trigger_skip_feedback("forward")

    def on_prev_clicked(self):
        self._waiting_for_download_to_play = False
        self._party_downloading_track = None
        self.audio_engine.prev_track()
        self.sync_play_state()
        if hasattr(self, "party_sync") and self.party_sync.is_connected and self.party_sync.is_host:
            self._broadcast_party_track()
        self.refresh_queue_ui()
        if hasattr(self, "lbl_track_title"):
            self.lbl_track_title.trigger_symbol("backward")
        if self.overlay:
            self.overlay.trigger_skip_feedback("backward")

    def toggle_shuffle(self):
        self.audio_engine.shuffle = not self.audio_engine.shuffle
        self.update_shuffle_ui()
        self.save_settings()

    def update_shuffle_ui(self):
        if not hasattr(self, "btn_shuffle"):
            return
        if self.audio_engine.shuffle:
            self.btn_shuffle.setText("⇄")
            self.btn_shuffle.setToolTip("Shuffle: Enabled")
            self.btn_shuffle.setStyleSheet(
                "background-color: #1e3a8a; color: #60a5fa; border: 1px solid #3b82f6; border-radius: 4px; font-weight: bold; font-size: 13px;"
            )
        else:
            self.btn_shuffle.setText("⇄")
            self.btn_shuffle.setToolTip("Shuffle: Disabled")
            self.btn_shuffle.setStyleSheet(
                "background-color: #27272a; color: #71717a; border: 1px solid #3f3f46; border-radius: 4px; font-size: 13px;"
            )

    def on_track_double_clicked(self, item):
        self._waiting_for_download_to_play = False
        self._party_downloading_track = None
        orig_idx = item.data(Qt.ItemDataRole.UserRole)
        if orig_idx is not None and 0 <= orig_idx < len(self.audio_engine.playlist):
            self.audio_engine.play_index(orig_idx)
        else:
            row = self.list_tracks.row(item)
            self.audio_engine.play_index(row)
        self.sync_play_state()
        if hasattr(self, "party_sync") and self.party_sync.is_connected and self.party_sync.is_host:
            self._broadcast_party_track()
        self.refresh_queue_ui()

    def sync_volume(self, vol: float):
        """Synchronizes the volume slider and label from external events."""
        val = int(vol * 100)
        self.slider_vol.blockSignals(True)
        self.slider_vol.setValue(val)
        self.slider_vol.blockSignals(False)
        self.lbl_vol_val.setText(f"{val}%")

    def on_volume_changed(self, value):
        vol = value / 100.0
        self.audio_engine.set_volume(vol)
        self.overlay.set_volume(vol)
        self.lbl_vol_val.setText(f"{value}%")

    def on_seek_pressed(self):
        self.is_user_scrubbing = True

    def on_seek_moved(self, value):
        dur = self.audio_engine.get_duration()
        if dur > 0:
            target_sec = (value / 1000.0) * dur
            self.lbl_time_cur.setText(f"{int(target_sec // 60):02d}:{int(target_sec % 60):02d}")

    def on_seek_released(self):
        self.is_user_scrubbing = False
        val = self.slider_seek.value()
        dur = self.audio_engine.get_duration()
        if dur > 0:
            target_sec = (val / 1000.0) * dur
            self.audio_engine.seek(target_sec)
        else:
            target_sec = 0.0
            self.audio_engine.seek(0.0)
        if hasattr(self, "discord_service") and self.discord_service:
            raw_title = self.audio_engine.get_current_track_title()
            is_playing = self.audio_engine.is_playing and self.audio_engine.audio_mode != "desktop"
            self.discord_service.update_playback(raw_title, is_playing, target_sec, dur)

        if hasattr(self, "party_sync") and self.party_sync.is_connected:
            if not getattr(self, "_is_handling_party_event", False):
                if self.party_sync.is_host or self.party_sync.allow_guest_control:
                    self.party_sync.broadcast_seek(target_sec)

    def update_timeline(self):
        if self.is_user_scrubbing:
            return
        pos = self.audio_engine.get_position()
        dur = self.audio_engine.get_duration()
        if self.isVisible():
            if self.audio_engine.audio_mode == "desktop":
                self.lbl_time_cur.setText("LIVE")
                self.lbl_time_dur.setText("LOOP")
                self.slider_seek.setValue(1000)
            else:
                if dur > 0:
                    pct = int((pos / dur) * 1000)
                    self.slider_seek.setValue(pct)
                else:
                    self.slider_seek.setValue(0)
                m_pos, s_pos = int(pos // 60), int(pos % 60)
                m_dur, s_dur = int(dur // 60), int(dur % 60)
                self.lbl_time_cur.setText(f"{m_pos:02d}:{s_pos:02d}")
                self.lbl_time_dur.setText(f"{m_dur:02d}:{s_dur:02d}")

        # Periodic party heartbeat (every 3s for host)
        if hasattr(self, "party_sync") and self.party_sync.is_connected and self.party_sync.is_host:
            now = time.time()
            if now - getattr(self, "_last_party_heartbeat", 0.0) >= 3.0:
                self._last_party_heartbeat = now
                self.party_sync.broadcast_heartbeat(pos, self.audio_engine.is_playing)

        # Periodic Discord Rich Presence timeline update (every 4s while playing)
        if hasattr(self, "discord_service") and self.discord_service and self.discord_service.enabled:
            now = time.time()
            if now - getattr(self, "_last_discord_update", 0.0) >= 4.0:
                self._last_discord_update = now
                raw_title = self.audio_engine.get_current_track_title()
                is_playing = self.audio_engine.is_playing and self.audio_engine.audio_mode != "desktop"
                self.discord_service.update_playback(raw_title, is_playing, pos, dur)

        # Check if stream dropped unexpectedly (e.g. headset unplugged mid-playback)
        if (
            self.audio_engine.is_playing
            and self.audio_engine.audio_mode != "desktop"
            and not self.audio_engine.track_finished
            and self.audio_engine.stream is not None
            and not getattr(self.audio_engine.stream, "active", False)
        ):
            now = time.time()
            if now - getattr(self, "_last_stream_drop_check", 0.0) >= 1.5:
                self._last_stream_drop_check = now
                log.warning("[AUDIO] Output stream dropped unexpectedly. Re-routing audio to default device...")
                self.audio_engine.handle_device_changed(resume_playback=True)

        # Auto-advance / 2-second DJ crossfade when song approaches end or finishes
        if self.audio_engine.audio_mode != "desktop":
            is_finished = self.audio_engine.track_finished or (
                dur > 0 and pos >= dur - 0.08 and (self.audio_engine.is_playing or pos > 0.5)
            )
            crossfade_dur = getattr(self.audio_engine, "_crossfade_duration", 2.0)
            if (
                dur > (crossfade_dur * 2.0)
                and pos >= (dur - crossfade_dur)
                and not getattr(self.audio_engine, "_in_crossfade", False)
                and self.audio_engine.is_playing
                and (len(self.audio_engine.playlist) > 1 or (hasattr(self, "party_sync") and self.party_sync.is_connected and self.party_sync.party_queue))
            ):
                self.play_next_track(crossfade=True)
            elif is_finished:
                self.audio_engine.track_finished = False
                self.play_next_track(crossfade=False)

    def _on_audio_device_changed(self):
        log.info("[AUDIO] Audio outputs change detected. Scheduling device recovery in 350ms...")
        if hasattr(self, "_device_change_timer"):
            self._device_change_timer.start(350)

    def _do_audio_device_recovery(self):
        log.info("[AUDIO] Performing audio device recovery...")
        if hasattr(self, "audio_engine"):
            self.audio_engine.handle_device_changed()

    def choose_music_folder(self):
        cur = self.audio_engine.folder_path or DEFAULT_MUSIC_DIR
        folder = QFileDialog.getExistingDirectory(
            self, "Select Music Folder", cur
        )
        if folder and os.path.exists(folder):
            self.audio_engine.set_folder(folder)
            self.refresh_tracklist()
            self.refresh_folder_switcher()
            if hasattr(self, "lbl_folder_path") and self.lbl_folder_path:
                self.lbl_folder_path.setText(f"{folder}")
            if hasattr(self, "settings_dialog") and hasattr(
                self.settings_dialog, "lbl_folder_path"
            ):
                self.settings_dialog.lbl_folder_path.setText(f"{folder}")
            self.save_settings()

    def open_music_folder_explorer(self):
        folder = self.audio_engine.folder_path
        if folder and os.path.exists(folder):
            if sys.platform == "win32":
                os.startfile(os.path.normpath(folder))
            else:
                                subprocess.run(["xdg-open", os.path.normpath(folder)])

    def refresh_tracklist(self):
        self.audio_engine.refresh_playlist()
        self.populate_playlist_ui()
        if hasattr(self, "lbl_folder_path") and self.lbl_folder_path:
            self.lbl_folder_path.setText(f"{self.audio_engine.folder_path}")
        if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "lbl_folder_path"):
            self.settings_dialog.lbl_folder_path.setText(f"{self.audio_engine.folder_path}")

    def refresh_playlist(self):
        """Alias for playlist refresh called by downloaders, party sync, and dialogs."""
        self.refresh_tracklist()

    def on_vis_mode_changed(self, mode: str):
        self.overlay.visualizer.set_mode(mode)
        self.overlay._was_rendering = True
        self.overlay.update()

    def on_vis_theme_changed(self, theme_name: str):
        self.overlay.visualizer.set_theme(theme_name)
        self.overlay._was_rendering = True
        self.overlay.update()

    def on_eye_sens_changed(self, val):
        self.overlay.eye_sensitivity = val / 100.0
        self.lbl_sens_val.setText(f"{val / 100.0:.1f}x")

    def on_scanlines_toggled(self, checked):
        self.overlay.enable_scanlines = checked
        self.overlay._was_rendering = True
        self.overlay.update()


    def on_head_bop_toggled(self, checked: bool):
        self.overlay.enable_head_bop = bool(checked)
        self.overlay._was_rendering = True
        self.overlay.update()
        self.save_settings()

    def on_bass_pop_toggled(self, checked):
        self.overlay.enable_bass_pop = checked
        self.overlay._was_rendering = True
        self.overlay.update()

    def on_discord_rpc_toggled(self, checked: bool):
        self._discord_rpc_enabled = bool(checked)
        if hasattr(self, "discord_service") and self.discord_service:
            self.discord_service.set_enabled(bool(checked))
            if checked:
                raw_title = self.audio_engine.get_current_track_title()
                is_playing = self.audio_engine.is_playing and self.audio_engine.audio_mode != "desktop"
                pos = self.audio_engine.get_position()
                dur = self.audio_engine.get_duration()
                self.discord_service.update_playback(raw_title, is_playing, pos, dur)
        self.save_settings()

    def on_widescreen_toggled(self, checked):
        self.overlay.use_widescreen = checked
        if hasattr(self.overlay.visualizer, "use_widescreen"):
            self.overlay.visualizer.use_widescreen = checked
        self.on_size_change()

    def on_opacity_change(self, val=None):
        if val is None:
            val = self.slider_opacity.value()
        self.overlay.opacity_val = val / 100.0
        self.overlay._was_rendering = True
        self.overlay.update()

    def on_size_change(self, val=None):
        if self.overlay.use_widescreen:
            h = self.slider_size.value()
            w = int(h * (16.0 / 9.0))
            self.overlay.resize(w, h)
        else:
            size = self.slider_size.value()
            self.overlay.resize(size, size)
        self.overlay._was_rendering = True
        self.overlay.update()

    def reload_art(self):
        self.overlay.load_assets()
        log.info("[STATUS] Reloaded fresh images from assets/eye_parts/ folder!")

    def check_hotkeys(self):
        """Monitors global hotkeys without polling lag."""

        # F7: Toggle Lyrics Overlay
        f7_down = bool(user32.GetAsyncKeyState(VK_F7) & 0x8000)
        if f7_down and not self.last_f7_state:
            self.toggle_lyrics()
        self.last_f7_state = f7_down

        # Ctrl+[ and Ctrl+]: Manual lyric offset adjustments
        ctrl_down = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
        bracket_l = bool(user32.GetAsyncKeyState(VK_OEM_4) & 0x8000)
        if ctrl_down and bracket_l and not self.last_bracket_left_state:
            self.adjust_lyrics_offset(-0.25)
        self.last_bracket_left_state = bracket_l
        bracket_r = bool(user32.GetAsyncKeyState(VK_OEM_6) & 0x8000)
        if ctrl_down and bracket_r and not self.last_bracket_right_state:
            self.adjust_lyrics_offset(0.25)
        self.last_bracket_right_state = bracket_r

        # F8: Toggle Move Talia mode
        f8_down = bool(user32.GetAsyncKeyState(VK_F8) & 0x8000)
        if f8_down and not self.last_f8_state:
            self.toggle_move_talia()
        self.last_f8_state = f8_down

        # F9: Toggle Show/Hide overlay
        f9_down = bool(user32.GetAsyncKeyState(VK_F9) & 0x8000)
        if f9_down and not self.last_f9_state:
            self.toggle_visibility()
        self.last_f9_state = f9_down

        # F10: Toggle Audio Source Mode (Desktop vs Player)
        f10_down = bool(user32.GetAsyncKeyState(VK_F10) & 0x8000)
        if f10_down and not self.last_f10_state:
            self.toggle_audio_mode()
        self.last_f10_state = f10_down

        # F11: Toggle Eco Mode (< 1% CPU)
        f11_down = bool(user32.GetAsyncKeyState(VK_F11) & 0x8000)
        if f11_down and not self.last_f11_state:
            self.toggle_eco_mode()
        self.last_f11_state = f11_down

    def toggle_eco_mode(self):
        """Toggles Eco Mode (< 1% CPU target) and persists preference."""
        self.set_eco_mode(not self.eco_mode)
        if not getattr(self, "is_loading_settings", False):
            try:
                cfg = self.get_current_settings_dict()
                save_settings(cfg)
            except Exception:
                pass

    def set_eco_mode(self, enabled: bool):
        """Applies Eco Mode settings across audio engine, character overlay, lyrics, and controller."""
        self.eco_mode = enabled
        if hasattr(self.audio_engine, "set_eco_mode"):
            self.audio_engine.set_eco_mode(enabled)
        if hasattr(self.overlay, "set_eco_mode"):
            self.overlay.set_eco_mode(enabled)
        if self.lyrics_overlay and hasattr(self.lyrics_overlay, "set_eco_mode"):
            self.lyrics_overlay.set_eco_mode(enabled)
        if enabled:
            self.hotkey_timer.setInterval(120)
            self.timeline_timer.setInterval(500)
            if hasattr(self, "btn_eco"):
                self.btn_eco.setText("Eco Mode: On")
                self.btn_eco.setStyleSheet(
                    "background-color: #166534; color: #4ade80; border: 1px solid #22c55e; font-weight: 500; font-size: 11px; padding: 7px 8px;"
                )
            if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "btn_eco"):
                self.settings_dialog.btn_eco.setText("Eco Mode: On")
                self.settings_dialog.btn_eco.setStyleSheet(
                    "background-color: #166534; color: #4ade80; border: 1px solid #22c55e; font-weight: 500; font-size: 11px; padding: 7px 8px;"
                )
            log.info("[STATUS] Eco Mode enabled (< 1% CPU).")
        else:
            self.hotkey_timer.setInterval(50)
            self.timeline_timer.setInterval(200)
            if hasattr(self, "btn_eco"):
                self.btn_eco.setText("Eco Mode: Off")
                self.btn_eco.setStyleSheet("")
            if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "btn_eco"):
                self.settings_dialog.btn_eco.setText("Eco Mode: Off")
                self.settings_dialog.btn_eco.setStyleSheet("")
            log.info("[STATUS] Eco Mode disabled (Standard).")

    def toggle_lyrics(self):
        if not self.lyrics_overlay:
            return
        self.lyrics_overlay.is_enabled = not self.lyrics_overlay.is_enabled
        if self.lyrics_overlay.is_enabled:
            self.lyrics_overlay.show()
            self.lyrics_overlay.enforce_topmost()
            log.info("[STATUS] Lyrics Overlay enabled.")
        else:
            self.lyrics_overlay.hide()
            log.info("[STATUS] Lyrics Overlay disabled.")
        self.update_lyrics_ui()

    def update_lyrics_ui(self):
        if not hasattr(self, "btn_lyrics") or not self.lyrics_overlay:
            return
        txt = "Lyrics: On" if self.lyrics_overlay.is_enabled else "Lyrics: Off"
        style = (
            "background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: 500; font-size: 11px; padding: 7px 8px;"
            if self.lyrics_overlay.is_enabled
            else ""
        )
        if hasattr(self, "btn_lyrics"):
            self.btn_lyrics.setText(txt)
            self.btn_lyrics.setStyleSheet(style)
        if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "btn_lyrics"):
            self.settings_dialog.btn_lyrics.setText(txt)
            self.settings_dialog.btn_lyrics.setStyleSheet(style)

    def update_move_talia_ui(self):
        """Refreshes the Move Talia toggle button appearance to match current overlay state."""
        txt = "Unlock Window" if self.overlay.move_talia_mode else "Lock Window"
        style = (
            "background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: 500;"
            if self.overlay.move_talia_mode
            else ""
        )
        if hasattr(self, "btn_move_talia"):
            self.btn_move_talia.setText(txt)
            self.btn_move_talia.setStyleSheet(style)
        if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "btn_move_talia"):
            self.settings_dialog.btn_move_talia.setText(txt)
            self.settings_dialog.btn_move_talia.setStyleSheet(style)

    def adjust_lyrics_offset(self, delta: float):
        if (
            self.lyrics_overlay
            and hasattr(self.lyrics_overlay, "lyrics_manager")
            and self.lyrics_overlay.lyrics_manager
        ):
            new_val = self.lyrics_overlay.lyrics_manager.adjust_offset(delta)
            self.update_sync_offset_display(new_val)
            log.info(f"[LYRICS] Manual sync offset adjusted: {new_val:+.2f}s")

    def reset_lyrics_offset(self):
        if (
            self.lyrics_overlay
            and hasattr(self.lyrics_overlay, "lyrics_manager")
            and self.lyrics_overlay.lyrics_manager
        ):
            new_val = self.lyrics_overlay.lyrics_manager.reset_offset()
            self.update_sync_offset_display(new_val)
            log.info("[LYRICS] Manual sync offset reset to 0.0s")

    def auto_sync_lyrics(self):
        if (
            self.lyrics_overlay
            and hasattr(self.lyrics_overlay, "lyrics_manager")
            and self.lyrics_overlay.lyrics_manager
        ):
            success, val, msg = self.lyrics_overlay.lyrics_manager.auto_align_with_audio()
            self.update_sync_offset_display()
            log.info(f"[LYRICS AUTO-SYNC] {msg}")

    def update_sync_offset_display(self, val=None):
        if (
            hasattr(self, "lbl_sync_offset")
            and self.lyrics_overlay
            and hasattr(self.lyrics_overlay, "lyrics_manager")
            and self.lyrics_overlay.lyrics_manager
        ):
            offset = (
                val if val is not None else self.lyrics_overlay.lyrics_manager.get_total_offset()
            )
            self.lbl_sync_offset.setText(f"{offset:+.2f}s")

    def on_lyric_size_changed(self, val: int):
        val = max(14, min(60, int(val)))
        if hasattr(self, "lbl_lyric_size_val"):
            self.lbl_lyric_size_val.setText(f"{val} pt")
        if self.lyrics_overlay:
            self.lyrics_overlay.set_font_size(val, keep_center=True)
        if not getattr(self, "is_loading_settings", False):
            try:
                cfg = self.get_current_settings_dict()
                cfg["lyrics_font_size"] = val
                save_settings(cfg)
            except Exception:
                pass

    def sync_lyric_size(self, val: int):
        val = max(14, min(60, int(val)))
        if hasattr(self, "slider_lyric_size"):
            self.slider_lyric_size.blockSignals(True)
            self.slider_lyric_size.setValue(val)
            self.slider_lyric_size.blockSignals(False)
        if hasattr(self, "lbl_lyric_size_val"):
            self.lbl_lyric_size_val.setText(f"{val} pt")
        if not getattr(self, "is_loading_settings", False):
            try:
                cfg = self.get_current_settings_dict()
                cfg["lyrics_font_size"] = val
                save_settings(cfg)
            except Exception:
                pass

    def on_word_glow_toggled(self, checked: bool):
        if self.lyrics_overlay:
            self.lyrics_overlay.word_glow = checked
            self.lyrics_overlay._cached_layout_key = None
            self.lyrics_overlay.update()
        if not getattr(self, "is_loading_settings", False):
            try:
                cfg = self.get_current_settings_dict()
                save_settings(cfg)
            except Exception:
                pass

    def on_dialogue_mode_toggled(self, checked: bool):
        if self.lyrics_overlay:
            self.lyrics_overlay.dialogue_mode = checked
            self.lyrics_overlay._cached_layout_key = None
            self.lyrics_overlay.update()
        if not getattr(self, "is_loading_settings", False):
            try:
                cfg = self.get_current_settings_dict()
                save_settings(cfg)
            except Exception:
                pass

    def on_lyric_preset_changed(self, text: str):
        if getattr(self, "is_loading_settings", False):
            return
        if hasattr(self, "lyric_presets") and text in self.lyric_presets:
            hex_code = self.lyric_presets[text]
            if self.lyrics_overlay:
                self.lyrics_overlay.set_color(hex_code)
            self._update_color_btn_style(hex_code)
            try:
                cfg = self.get_current_settings_dict()
                cfg["lyrics_color"] = hex_code
                save_settings(cfg)
            except Exception:
                pass

    def choose_custom_lyric_color(self):
        try:
            curr_hex = (
                getattr(self.lyrics_overlay, "color_hex", "#ffffff")
                if self.lyrics_overlay
                else "#ffffff"
            )
            options = QColorDialog.ColorDialogOption.DontUseNativeDialog
            color = QColorDialog.getColor(QColor(curr_hex), self, "Choose Lyrics Color", options)
            if color.isValid():
                hex_code = color.name()
                if self.lyrics_overlay:
                    self.lyrics_overlay.set_color(hex_code)
                matched_preset = None
                for name, code_str in self.lyric_presets.items():
                    if code_str.lower() == hex_code.lower():
                        matched_preset = name
                        break
                if matched_preset:
                    self.combo_lyric_color.setCurrentText(matched_preset)
                else:
                    self.combo_lyric_color.setCurrentText("Custom...")
                self._update_color_btn_style(hex_code)

                # Auto save chosen color
                cfg = self.get_current_settings_dict()
                cfg["lyrics_color"] = hex_code
                save_settings(cfg)
        except Exception as e:
            log.info(f"[ERROR] choose_custom_lyric_color: {e}")

    def _update_color_btn_style(self, hex_code: str):
        if hasattr(self, "btn_pick_color"):
            self.btn_pick_color.setStyleSheet(
                f"background-color: #27272a; color: {hex_code}; border: 1px solid {hex_code}; font-weight: 500;"
            )

    def open_settings_window(self):
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.show()
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()

    def on_font_changed(self, text: str):
        if getattr(self, "is_loading_settings", False):
            return
        if not text or "Default" in text:
            if self.lyrics_overlay:
                self.lyrics_overlay.set_custom_font(None)
        else:
            if self.lyrics_overlay:
                self.lyrics_overlay.set_custom_font(text)
        try:
            cfg = self.get_current_settings_dict()
            cfg["lyrics_font"] = text
            save_settings(cfg)
        except Exception as e:
            log.info(f"[ERROR] Auto-saving lyrics font: {e}")

    def open_fonts_folder(self):
        os.makedirs(FONTS_DIR, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(os.path.normpath(FONTS_DIR))
        else:
                        subprocess.run(["xdg-open", os.path.normpath(FONTS_DIR)])

    def open_lyric_fetcher(self, track_path: Optional[str] = None, select_calibrate_tab: bool = False):
        # Open automated lyric fetcher GUI
        if not isinstance(track_path, str):
            track_path = None
        try:
            fetcher_dir = os.path.join(PROJECT_ROOT, "Talia Lyrics Fetch Automated")
            if fetcher_dir not in sys.path:
                sys.path.insert(0, fetcher_dir)
            from gui_fetcher import LyricsFetcherWindow

            if not hasattr(self, "_lyrics_fetcher_win") or self._lyrics_fetcher_win is None:
                self._lyrics_fetcher_win = LyricsFetcherWindow()
                self._lyrics_fetcher_win.lyrics_saved.connect(self._on_lyrics_saved_externally)

            # Auto-select the target track (or currently playing track) in the calibrator tab for instant editing
            curr_track = track_path
            if not curr_track:
                if hasattr(
                    self.audio_engine, "playlist"
                ) and 0 <= self.audio_engine.current_index < len(self.audio_engine.playlist):
                    curr_track = self.audio_engine.playlist[self.audio_engine.current_index]
            if (
                curr_track
                and os.path.exists(curr_track)
                and hasattr(self._lyrics_fetcher_win, "edit_cal_file")
            ):
                self._lyrics_fetcher_win.edit_cal_file.setText(os.path.normpath(curr_track))
                self._lyrics_fetcher_win._load_cal_track(os.path.normpath(curr_track))

            if select_calibrate_tab and hasattr(self._lyrics_fetcher_win, "tabs"):
                self._lyrics_fetcher_win.tabs.setCurrentIndex(2)

            self._lyrics_fetcher_win.show()
            self._lyrics_fetcher_win.raise_()
            self._lyrics_fetcher_win.activateWindow()
            log.info(f"[ACTION] Opened Lyrics Fetcher Window (target track: {curr_track}).")
        except Exception as e:
            log.info(f"[ERROR] In-process lyric fetcher launch failed: {e}")
            try:
                folder = os.path.join(PROJECT_ROOT, "Talia Lyrics Fetch Automated")
                if os.path.exists(folder):
                    os.startfile(folder)
            except Exception as e2:
                log.info(f"[ERROR] Fallback lyric fetcher launch failed: {e2}")

    def _on_lyrics_saved_externally(self, lrc_path: str):
        """Auto-refreshes lyrics immediately when saved from Lyrics Fetcher without changing tracks."""
        log.info(f"[ACTION] Lyrics saved externally: {lrc_path}. Auto-refreshing lyrics...")
        if hasattr(self.audio_engine, "lyrics_manager") and self.audio_engine.lyrics_manager:
            self.audio_engine.lyrics_manager.reload_current_track()
        if hasattr(self, "lyrics_overlay") and self.lyrics_overlay:
            self.lyrics_overlay.update()

    def reload_custom_fonts(self):
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.populate_fonts()
        active = self.combo_font.currentText() if hasattr(self, "combo_font") else ""
        if self.lyrics_overlay:
            if not active or "Default" in active:
                self.lyrics_overlay.set_custom_font(None)
            else:
                self.lyrics_overlay.set_custom_font(active)
            self.lyrics_overlay.update()
        log.info(f"[FONTS] Reloaded lyric fonts. Active: {active or 'Default'}")

    def show_guide_dialog(self):
        cfg = self.get_current_settings_dict()
        self.guide_dialog = GuideDialog(self, cfg)
        self.guide_dialog.show()
        self.guide_dialog.raise_()
        self.guide_dialog.activateWindow()

    def toggle_move_talia(self):
        new_state = not self.overlay.move_talia_mode
        self.overlay.set_move_talia_mode(new_state)
        if self.lyrics_overlay:
            self.lyrics_overlay.set_move_mode(new_state)
        self.update_move_talia_ui()

    def toggle_visibility(self):
        if self.overlay.isVisible():
            self.overlay.hide()
            if self.lyrics_overlay:
                self.lyrics_overlay.hide()
            log.info("[STATUS] Overlay and lyrics hidden.")
        else:
            self.overlay.show()
            self.overlay.enforce_topmost()
            if self.lyrics_overlay and self.lyrics_overlay.is_enabled:
                self.lyrics_overlay.show()
                self.lyrics_overlay.enforce_topmost()
            log.info("[STATUS] Overlay and lyrics visible.")

    # ==========================================================

    # Settings Persistence

    # ==========================================================

    def get_current_settings_dict(self) -> dict:
        """Gathers all current configuration into a dictionary."""
        if getattr(self.overlay, "is_shutting_down", False) and hasattr(
            self.overlay, "shutdown_start_pos"
        ):
            pos_x = int(self.overlay.shutdown_start_pos.x())
            pos_y = int(self.overlay.shutdown_start_pos.y())
        elif getattr(self.overlay, "is_starting_up", False) and hasattr(
            self.overlay, "target_startup_y"
        ):
            pos_x = int(self.overlay.target_startup_x)
            pos_y = int(self.overlay.target_startup_y)
        else:
            pos_x = int(self.overlay.pos().x())
            pos_y = int(self.overlay.pos().y())
        user_opacity = max(0.20, min(1.0, self.slider_opacity.value() / 100.0))
        settings_dict = {
            "pos_x": pos_x,
            "pos_y": pos_y,
            "char_size": max(MIN_CHAR_SIZE, int(self.overlay.width())),
            "eye_sensitivity": round(float(self.overlay.eye_sensitivity), 2),
            "opacity": round(float(user_opacity), 2),
            "bass_pop": bool(self.overlay.enable_bass_pop),
            "visualizer_mode": str(self.overlay.visualizer.mode),
            "visualizer_palette": str(self.overlay.visualizer.current_theme_name),
            "volume": round(float(self.audio_engine.volume), 2),
            "audio_mode": str(self.audio_engine.audio_mode),
            "music_folder": str(self.audio_engine.folder_path),
            "shuffle": bool(self.audio_engine.shuffle),
            "eco_mode": bool(self.eco_mode),
            "show_startup_guide": bool(getattr(self, "show_startup_guide", True)),
        }
        if self.lyrics_overlay:
            settings_dict["lyrics_x"] = int(self.lyrics_overlay.pos().x())
            settings_dict["lyrics_y"] = int(self.lyrics_overlay.pos().y())
            settings_dict["lyrics_font_size"] = int(
                getattr(self.lyrics_overlay, "base_font_size", 18)
            )
            settings_dict["show_lyrics"] = bool(self.lyrics_overlay.is_enabled)
            settings_dict["lyrics_color"] = str(
                getattr(self.lyrics_overlay, "color_hex", "#00ffff")
            )
            settings_dict["lyrics_word_glow"] = bool(
                getattr(self.lyrics_overlay, "word_glow", True)
            )
            settings_dict["lyrics_dialogue_mode"] = bool(
                getattr(self.lyrics_overlay, "dialogue_mode", True)
            )
            font_val = (
                self.combo_font.currentText()
                if hasattr(self, "combo_font")
                else "Default (Segoe UI / Inter)"
            )
            settings_dict["lyrics_font"] = font_val
        settings_dict["head_bop"] = bool(
            self.settings_dialog.chk_head_bop.isChecked()
            if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "chk_head_bop")
            else getattr(self.overlay, "enable_head_bop", False)
        )
        settings_dict["download_folder"] = str(getattr(self, "saved_dl_folder", ""))
        settings_dict["discord_rpc"] = bool(
            self.settings_dialog.chk_discord_rpc.isChecked()
            if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "chk_discord_rpc")
            else getattr(self, "_discord_rpc_enabled", True)
        )
        settings_dict["queue"] = list(getattr(self.audio_engine, "queue", []))
        return settings_dict

    def apply_settings(self, cfg: dict):
        # Apply settings to overlay and controls
        self.is_loading_settings = True
        self.show_startup_guide = bool(cfg.get("show_startup_guide", True))

        # Size
        size = int(cfg.get("char_size", 300))
        size = max(MIN_CHAR_SIZE, min(MAX_CHAR_SIZE, size))
        self.slider_size.setValue(size)
        self.overlay.resize(size, size)

        # Position
        screen = QApplication.primaryScreen().geometry()
        pos_x = int(cfg.get("pos_x", -1))
        pos_y = int(cfg.get("pos_y", -1))
        if (-size // 2 <= pos_x <= screen.width()) and (-size // 2 <= pos_y <= screen.height()):
            self.overlay.move(pos_x, pos_y)
        else:
            def_x = max(20, screen.width() - size - 40)
            def_y = max(20, screen.height() - size - 80)
            self.overlay.move(def_x, def_y)

        # Eye Sensitivity
        sens = cfg.get("eye_sensitivity", 1.68)
        self.slider_eye_sens.setValue(int(sens * 100))

        # Opacity
        raw_op = float(cfg.get("opacity", 1.0))
        if raw_op < 0.20:
            raw_op = 1.0
        self.slider_opacity.setValue(int(raw_op * 100))
        self.overlay.opacity_val = raw_op

        # Features
        self.overlay.enable_scanlines = False
        self.chk_bass_pop.setChecked(cfg.get("bass_pop", True))
        discord_on = bool(cfg.get("discord_rpc", True))
        self._discord_rpc_enabled = discord_on
        if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "chk_discord_rpc"):
            self.settings_dialog.chk_discord_rpc.setChecked(discord_on)
        if hasattr(self, "discord_service") and self.discord_service:
            self.discord_service.set_enabled(discord_on)
        self.overlay.enable_bass_pop = cfg.get("bass_pop", True)

        # Visualizer
        vis_mode = cfg.get("visualizer_mode", "Neon Wave")
        if vis_mode in ["Cyber Bars", "Neon Wave", "Radial Core", "Dual Mirror"]:
            self.combo_mode.setCurrentText(vis_mode)
        palette = cfg.get("visualizer_palette", "Cyberpunk Neon")
        if palette in COLOR_THEMES:
            self.combo_theme.setCurrentText(palette)

        # Volume
        vol = cfg.get("volume", 0.49)
        self.sync_volume(vol)
        self.overlay.set_volume(vol)

        # Audio Mode
        audio_mode = cfg.get("audio_mode", "player")
        if audio_mode in ("player", "desktop"):
            self.set_audio_mode(audio_mode)

        # Shuffle
        self.audio_engine.shuffle = bool(cfg.get("shuffle", False))
        self.update_shuffle_ui()

        # Lyrics Overlay Position & Visibility
        if self.lyrics_overlay:
            font_size = int(cfg.get("lyrics_font_size", 18))
            font_size = max(14, min(60, font_size))
            self.lyrics_overlay.set_font_size(font_size, keep_center=False)
            lx = int(cfg.get("lyrics_x", -1))
            ly = int(cfg.get("lyrics_y", -1))
            if 0 <= lx < screen.width() and 0 <= ly < screen.height():
                clamped_x = max(10, min(lx, screen.width() - self.lyrics_overlay.width() - 10))
                self.lyrics_overlay.move(clamped_x, ly)
            if hasattr(self, "slider_lyric_size"):
                self.slider_lyric_size.blockSignals(True)
                self.slider_lyric_size.setValue(font_size)
                self.slider_lyric_size.blockSignals(False)
            if hasattr(self, "lbl_lyric_size_val"):
                self.lbl_lyric_size_val.setText(f"{font_size} pt")

            show_lyrics = bool(cfg.get("show_lyrics", True))
            self.lyrics_overlay.is_enabled = show_lyrics
            if show_lyrics:
                self.lyrics_overlay.show()
                self.lyrics_overlay.enforce_topmost()
            else:
                self.lyrics_overlay.hide()
            self.update_lyrics_ui()
            lyric_color = cfg.get("lyrics_color", "#00ffff")
            self.lyrics_overlay.set_color(lyric_color)
            if hasattr(self, "combo_lyric_color"):
                matched = None
                for name, code_str in self.lyric_presets.items():
                    if code_str.lower() == lyric_color.lower():
                        matched = name
                        break
                self.combo_lyric_color.blockSignals(True)
                if matched:
                    self.combo_lyric_color.setCurrentText(matched)
                else:
                    self.combo_lyric_color.setCurrentText("Custom...")
                self.combo_lyric_color.blockSignals(False)
                self._update_color_btn_style(lyric_color)
            word_glow = bool(cfg.get("lyrics_word_glow", True))
            self.lyrics_overlay.word_glow = word_glow
            if hasattr(self, "chk_word_glow"):
                self.chk_word_glow.blockSignals(True)
                self.chk_word_glow.setChecked(word_glow)
                self.chk_word_glow.blockSignals(False)

            dialogue_mode = bool(cfg.get("lyrics_dialogue_mode", True))
            self.lyrics_overlay.dialogue_mode = dialogue_mode
            if getattr(self, "chk_dialogue_mode", None):
                self.chk_dialogue_mode.blockSignals(True)
                self.chk_dialogue_mode.setChecked(dialogue_mode)
                self.chk_dialogue_mode.blockSignals(False)

            # Lyrics Font
            lyrics_font = cfg.get("lyrics_font", "Rajdhani")
            if hasattr(self, "settings_dialog"):
                self.settings_dialog.populate_fonts()
                if hasattr(self, "combo_font"):
                    idx = self.combo_font.findText(lyrics_font)
                    if idx >= 0:
                        self.combo_font.blockSignals(True)
                        self.combo_font.setCurrentIndex(idx)
                        self.combo_font.blockSignals(False)
                    if "Default" in lyrics_font:
                        self.lyrics_overlay.set_custom_font(None)
                    else:
                        self.lyrics_overlay.set_custom_font(lyrics_font)
        eco = bool(cfg.get("eco_mode", False))
        self.set_eco_mode(eco)

        # Download Destination Folder
        self.saved_dl_folder = str(cfg.get("download_folder", ""))
        self.refresh_dl_folders()

        # Restore Saved Queue
        saved_q = cfg.get("queue", [])
        if isinstance(saved_q, list):
            valid_queue = [
                os.path.normpath(p) for p in saved_q
                if isinstance(p, str) and os.path.exists(p)
            ]
            self.audio_engine.queue = valid_queue
            if hasattr(self, "refresh_queue_ui"):
                self.refresh_queue_ui()

        self.overlay.update()
        self.is_loading_settings = False

    def _reset_save_btn(self):
        self.btn_save_settings.setText("Save Settings")
        self.btn_save_settings.setStyleSheet("")

    def save_settings(self):
        """Saves current settings to disk."""
        cfg = self.get_current_settings_dict()
        return save_settings(cfg)

    def save_settings_action(self):
        """Triggered by the Save Settings button."""
        cfg = self.get_current_settings_dict()
        if save_settings(cfg):
            self.btn_save_settings.setText("Settings Saved")
            self.btn_save_settings.setStyleSheet(
                "background-color: #166534; color: #4ade80; border: 1px solid #22c55e;"
            )
            QTimer.singleShot(1500, self._reset_save_btn)

    def showEvent(self, event):
        super().showEvent(event)
        # Ensure window header is never stuck off-screen
        screen = QApplication.primaryScreen().availableGeometry()
        if self.y() < screen.top() + 30:
            self.move(self.x(), screen.top() + 40)
        if self.x() < screen.left():
            self.move(screen.left() + 20, self.y())
        if hasattr(self, "timeline_timer"):
            interval = 500 if getattr(self, "eco_mode", False) else 200
            self.timeline_timer.setInterval(interval)
            self.update_timeline()
        if (
            self.overlay
            and hasattr(self.overlay, "sound_menu_open")
            and self.overlay.sound_menu_open.isLoaded()
        ):
            self.overlay.sound_menu_open.play()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "_drag_pos", None) is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            screen = QApplication.primaryScreen().availableGeometry()
            clamped_y = max(screen.top() + 10, min(new_pos.y(), screen.bottom() - 60))
            clamped_x = max(screen.left() - self.width() + 60, min(new_pos.x(), screen.right() - 60))
            self.move(clamped_x, clamped_y)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, "timeline_timer"):
            self.timeline_timer.setInterval(600)
        if (
            self.overlay
            and hasattr(self.overlay, "sound_menu_close")
            and self.overlay.sound_menu_close.isLoaded()
        ):
            self.overlay.sound_menu_close.play()
        trim_process_memory()

    def closeEvent(self, event):
        cfg = self.get_current_settings_dict()
        save_settings(cfg)
        if hasattr(self, "settings_dialog") and self.settings_dialog.isVisible():
            self.settings_dialog.hide()
        self.hide()
        if (
            self.overlay
            and hasattr(self.overlay, "sound_menu_close")
            and self.overlay.sound_menu_close.isLoaded()
        ):
            self.overlay.sound_menu_close.play()
        trim_process_memory()
        event.ignore()

    # -------------------------------------------------------------

    # SONG SEARCH & AUTO-DOWNLOAD SLOTS

    # -------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Party Sync (Listen Together) & Spotify Integration Handlers
    # -------------------------------------------------------------------------

    def open_party_dialog(self):
        if hasattr(self, "party_dialog"):
            self.party_dialog.show()
            self.party_dialog.raise_()
            self.party_dialog.activateWindow()

    def open_spotify_dialog(self):
        if hasattr(self, "spotify_dialog"):
            self.spotify_dialog.show()
            self.spotify_dialog.raise_()
            self.spotify_dialog.activateWindow()

    def update_party_hud(self, is_connected: bool, room_code: str, is_host: bool):
        if hasattr(self, "btn_party_sync"):
            if is_connected:
                role = "HOST" if is_host else "PARTY"
                self.btn_party_sync.setText(f"{role}: {room_code}")
                self.btn_party_sync.setStyleSheet(
                    "background-color: #581c87; color: #f0abfc; border: 1px solid #c084fc; font-weight: bold; font-size: 11px; padding: 5px 10px; border-radius: 4px;"
                )
            else:
                self.btn_party_sync.setText("Listen Together")
                self.btn_party_sync.setStyleSheet(
                    "background-color: #1e1b4b; color: #a78bfa; border: 1px solid #7c3aed; font-weight: bold; font-size: 11px; padding: 5px 10px; border-radius: 4px;"
                )


    def _on_party_connected(self, room_code: str, is_host: bool, members: list):
        if is_host:
            self._broadcast_party_track()

    def _on_party_disconnected(self, reason: str = ""):
        self._waiting_for_download_to_play = False
        self._party_downloading_track = None
        self._prefetching_track_id = None
        self.update_party_hud(False, "", False)
        self.refresh_queue_ui()

    def _on_party_peer_joined(self, name: str, count: int):
        if hasattr(self, "party_sync") and self.party_sync.is_host:
            self._broadcast_party_track()

    def _on_party_host_transferred(self, new_host: str, old_host: str):
        if hasattr(self, "party_sync"):
            self.update_party_hud(self.party_sync.is_connected, self.party_sync.room_code, self.party_sync.is_host)
            if self.party_sync.is_host:
                self._broadcast_party_track()

    def _broadcast_party_track(self):
        if not hasattr(self, "party_sync") or not self.party_sync.is_connected:
            return
        if getattr(self, "_is_handling_party_event", False):
            return
        if not self.party_sync.is_host and not self.party_sync.allow_guest_control:
            return
        try:
            if 0 <= self.audio_engine.current_index < len(self.audio_engine.playlist):
                path = self.audio_engine.playlist[self.audio_engine.current_index]
                fname = os.path.basename(path)
                raw_title = self.audio_engine.get_current_track_title()
                title, artist = parse_track_info(raw_title)
                dur = self.audio_engine.get_duration()
                pos = self.audio_engine.get_position()
                is_playing = self.audio_engine.is_playing and self.audio_engine.audio_mode != "desktop"

                # Check if this track contains an embedded YouTube URL or ID
                yt_query = ""
                try:
                    if path.lower().endswith(".opus"):
                        from mutagen.oggopus import OggOpus
                        audio = OggOpus(path)
                        for c in audio.get("comment", []):
                            if c.startswith("yt_url="):
                                yt_query = c.split("yt_url=", 1)[1].strip()
                                break
                except Exception:
                    pass

                log.info("[PARTY SYNC] Broadcasting track: '%s' by '%s' (pos=%.2f, dur=%.2f, playing=%s, yt=%s)", title, artist, pos, dur, is_playing, yt_query)
                self.party_sync.broadcast_track(
                    title=title,
                    artist=artist,
                    filename=fname,
                    duration=dur,
                    timestamp=pos,
                    is_playing=is_playing,
                    yt_query=yt_query,
                )
        except Exception as exc:
            log.exception("[PARTY SYNC] Failed to broadcast track: %s", exc)

    def find_matching_party_track(self, data: dict) -> int:
        """
        Locates the best matching track in the local playlist or music folders.
        Prevents false-positive substring collisions and supports normalized title/artist matching,
        token set overlap (bag-of-words agnostic to word order), and recursive subfolder scanning.
        """
        local_path = (data.get("local_path") or "").strip()
        if local_path and os.path.exists(local_path):
            norm_target = os.path.normcase(os.path.abspath(local_path))
            for i, p in enumerate(self.audio_engine.playlist):
                if os.path.normcase(os.path.abspath(p)) == norm_target:
                    return i
            self.audio_engine.playlist.append(local_path)
            self.populate_playlist_ui()
            return len(self.audio_engine.playlist) - 1

        target_fn = (data.get("filename") or "").strip().lower()
        target_title = (data.get("title") or "").strip().lower()
        target_artist = (data.get("artist") or "").strip().lower()
        if target_artist in ("talia music player", "talia player", "unknown artist", "unknown"):
            target_artist = ""
        yt_query = (data.get("yt_query") or "").strip().lower()
        yt_query = re.sub(r"(?i)\btalia\s+(?:music\s+)?player\s*[-:]?\s*", "", yt_query).strip()

        noise_words = {
            "official", "video", "audio", "lyrics", "remix", "feat", "ft",
            "music", "talia", "player", "hd", "4k", "hq", "mv", "original",
            "mix", "version", "full"
        }

        def tokenize(s: str) -> set[str]:
            return {
                w for w in re.findall(r"[a-z0-9]+", s.lower())
                if (len(w) >= 2 or w.isdigit()) and w not in noise_words
            }

        def clean_stem(fn: str) -> str:
            stem = os.path.splitext(fn)[0].lower()
            return re.sub(r"^\d{1,3}(?:[\.\-_]|\s+-)\s*", "", stem).strip()

        target_stem = clean_stem(target_fn) if target_fn else ""
        norm_target_title = re.sub(r"[^a-z0-9]", "", target_title)
        norm_target_artist = re.sub(r"[^a-z0-9]", "", target_artist)
        norm_yt_query = re.sub(r"[^a-z0-9]", "", yt_query)

        query_tokens = tokenize(f"{target_title} {target_artist} {yt_query}")
        title_tokens = tokenize(target_title)
        artist_tokens = tokenize(target_artist)
        core_query_tokens = title_tokens | artist_tokens

        def score_candidate(fn: str, full_path: str = "") -> int:
            fn_lower = fn.lower()
            c_stem = clean_stem(fn)
            norm_c_stem = re.sub(r"[^a-z0-9]", "", c_stem)
            cand_tokens = tokenize(c_stem)

            # Exact filename or stem match
            if target_fn and (fn_lower == target_fn or c_stem == target_stem):
                return 1200

            # Exact query matches filename or stem without punctuation
            if norm_yt_query and (norm_yt_query == norm_c_stem or norm_yt_query == re.sub(r"[^a-z0-9]", "", fn_lower)):
                return 1000

            c_title, c_artist = parse_track_info(fn)
            c_title_clean = c_title.lower().strip()
            c_artist_clean = c_artist.lower().strip()
            if c_artist_clean in ("talia music player", "talia player", "unknown artist", "unknown"):
                c_artist_clean = ""
            norm_c_title = re.sub(r"[^a-z0-9]", "", c_title_clean)
            norm_c_artist = re.sub(r"[^a-z0-9]", "", c_artist_clean)
            cand_t_tokens = tokenize(c_title_clean)
            cand_a_tokens = tokenize(c_artist_clean)
            cand_core_tokens = cand_t_tokens | cand_a_tokens

            score = 0

            # Normalized query matches candidate title exactly
            if norm_yt_query and norm_c_title and norm_yt_query == norm_c_title:
                score = max(score, 950)

            # Bag-of-words / token overlap matching (order agnostic)
            if query_tokens and cand_tokens:
                if query_tokens == cand_tokens:
                    score = max(score, 900)
                elif core_query_tokens and core_query_tokens.issubset(cand_tokens) and len(core_query_tokens) >= 2:
                    score = max(score, 850 + len(core_query_tokens) * 10)
                elif cand_core_tokens and cand_core_tokens.issubset(query_tokens) and len(cand_core_tokens) >= 2:
                    score = max(score, 820 + len(cand_core_tokens) * 10)
                elif query_tokens.issubset(cand_tokens) and len(query_tokens) >= 2:
                    score = max(score, 800 + len(query_tokens) * 10)
                elif cand_tokens.issubset(query_tokens) and len(cand_tokens) >= 2:
                    score = max(score, 780 + len(cand_tokens) * 10)
                else:
                    common = query_tokens & cand_tokens
                    if len(common) >= 2:
                        ratio = len(common) / max(len(query_tokens), len(cand_tokens))
                        if ratio >= 0.5:
                            score = max(score, 300 + int(ratio * 500))

            # Title + Artist matching
            if norm_target_title and norm_c_title:
                if norm_target_title == norm_c_title:
                    title_score = 650
                    if norm_target_artist and norm_c_artist:
                        if norm_target_artist == norm_c_artist:
                            title_score += 350
                        elif norm_target_artist in norm_c_artist or norm_c_artist in norm_target_artist:
                            title_score += 250
                    elif not norm_target_artist:
                        title_score += 150
                    score = max(score, title_score)
                elif len(norm_target_title) >= 5 and len(norm_c_title) >= 5 and (norm_target_title in norm_c_title or norm_c_title in norm_target_title):
                    if norm_target_artist and norm_c_artist and (norm_target_artist in norm_c_artist or norm_c_artist in norm_target_artist):
                        score = max(score, 450)
                    elif not norm_target_artist and (norm_target_title in norm_c_title):
                        score = max(score, 350)

            # Substring match on stem
            if norm_yt_query and len(norm_yt_query) >= 4 and norm_yt_query in norm_c_stem:
                score = max(score, 400)
            elif norm_target_title and len(norm_target_title) >= 4 and norm_target_title in norm_c_stem:
                score = max(score, 350)

            return score

        # 1. Search active playlist in audio_engine
        best_idx = -1
        best_score = 0

        for i, track_path in enumerate(self.audio_engine.playlist):
            fn = os.path.basename(track_path)
            s = score_candidate(fn, track_path)
            if s > best_score:
                best_score = s
                best_idx = i
                if s >= 1000:
                    break

        if best_idx >= 0 and best_score >= 250:
            return best_idx

        # 2. Check if the song already exists on disk in music directories (recursive os.walk)
        candidate_dirs = [
            os.path.join(DEFAULT_MUSIC_DIR, "Downloaded Songs"),
            DEFAULT_MUSIC_DIR,
        ]
        cur_folder = getattr(self.audio_engine, "folder_path", None)
        if cur_folder and cur_folder not in candidate_dirs and os.path.exists(cur_folder):
            candidate_dirs.append(cur_folder)

        best_disk_file = None
        best_disk_score = 0

        for c_dir in candidate_dirs:
            if not os.path.exists(c_dir):
                continue
            for root, dirs, files in os.walk(c_dir):
                for fname in files:
                    if not fname.lower().endswith(SUPPORTED_AUDIO_EXTS):
                        continue
                    full_p = os.path.join(root, fname)
                    s = score_candidate(fname, full_p)
                    if s > best_disk_score:
                        best_disk_score = s
                        best_disk_file = full_p
                        if s >= 1000:
                            break
                if best_disk_score >= 1000:
                    break
            if best_disk_score >= 1000:
                break

        if best_disk_file and best_disk_score >= 250:
            norm_cand = os.path.normcase(os.path.abspath(best_disk_file))
            for i, p in enumerate(self.audio_engine.playlist):
                if os.path.normcase(os.path.abspath(p)) == norm_cand:
                    return i
            self.audio_engine.playlist.append(best_disk_file)
            self.populate_playlist_ui()
            return len(self.audio_engine.playlist) - 1

        return -1

    def _on_party_track_received(self, data: dict):
        if hasattr(self, "party_sync") and self.party_sync.is_host and not self.party_sync.allow_guest_control:
            return
        target_title = (data.get("title") or "").strip()
        target_artist = (data.get("artist") or "").strip()
        if target_artist.lower() in ("talia music player", "talia player", "unknown artist", "unknown"):
            target_artist = ""
        target_time = float(data.get("timestamp", 0.0))
        target_playing = bool(data.get("is_playing", True))

        matched_idx = self.find_matching_party_track(data)
        if matched_idx >= 0:
            self._party_downloading_track = None
            self._waiting_for_download_to_play = False
            self._is_handling_party_event = True
            try:
                self.audio_engine.play_index(matched_idx)
                if target_time > 0:
                    self.audio_engine.seek(target_time)
                if not target_playing:
                    self.audio_engine.pause()
                else:
                    self.audio_engine.play()
                self.sync_play_state()
            finally:
                self._is_handling_party_event = False
        else:
            # Pause playback immediately so guest doesn't fall through to next local playlist track!
            self.audio_engine.pause()
            self._party_downloading_track = data
            self._waiting_for_download_to_play = True
            self._last_known_host_pos = target_time
            self._last_known_host_playing = target_playing

            query = data.get("yt_query")
            if not query:
                query = f"{target_artist} - {target_title}" if target_artist else target_title
            query = re.sub(r"(?i)\btalia\s+(?:music\s+)?player\s*[-:]?\s*", "", query).strip()

            dur = float(data.get("duration", 0.0))
            log.info("[PARTY SYNC] Track not in local library. Auto-downloading: %s (duration=%.1f)", query, dur)
            display_title = data.get("title") or query
            if hasattr(self, "lbl_track_title") and self.lbl_track_title:
                self.lbl_track_title.setText(f"[PARTY] Downloading '{display_title}'...")
                self.lbl_track_title.full_text = f"[PARTY] Downloading '{display_title}'..."
            if self.overlay:
                self.overlay.update()

            threading.Thread(
                target=self._auto_download_party_track,
                args=(data, target_time, target_playing),
                daemon=True,
            ).start()

    def _auto_download_party_track(self, track_data: dict, target_time: float, target_playing: bool):
        cur_folder = getattr(self.audio_engine, 'folder_path', None)
        if cur_folder and os.path.isdir(cur_folder):
            target_dir = os.path.join(cur_folder, "Downloaded Songs")
        else:
            target_dir = os.path.join(DEFAULT_MUSIC_DIR, "Downloaded Songs")
        os.makedirs(target_dir, exist_ok=True)

        query = track_data.get("yt_query")
        if not query:
            a = track_data.get("artist", "").strip()
            t = track_data.get("title", "").strip()
            if a.lower() in ("talia music player", "talia player", "unknown artist", "unknown"):
                a = ""
            query = f"{a} - {t}" if a else t
        query = re.sub(r"(?i)\btalia\s+(?:music\s+)?player\s*[-:]?\s*", "", query).strip()

        target_dur = float(track_data.get("duration", 0.0))
        ok = False
        final_path = ""
        if hasattr(self, "downloader") and self.downloader:
            ok, final_path = self.downloader.download_sync_query(
                query,
                target_dir,
                track_info=track_data,
                target_duration=target_dur,
                return_path=True,
            )
        if ok and final_path and os.path.exists(final_path):
            self.party_sync.track_auto_downloaded.emit(target_dir, target_time, target_playing, final_path)
        else:
            log.warning("[PARTY QUEUE] Download failed for: %s", query)
            self._party_downloading_track = None
            self._waiting_for_download_to_play = False
            title = track_data.get("title") or query
            if hasattr(self, "lbl_track_title") and self.lbl_track_title:
                self.lbl_track_title.setText(f"[PARTY] Could not fetch '{title}'")
            if hasattr(self, "party_sync") and self.party_sync.is_host:
                QTimer.singleShot(1500, lambda: self.play_next_track(crossfade=False, force_skip=True))

    def _on_party_track_downloaded(self, target_dir: str, target_time: float, target_playing: bool, file_path: str = ""):
        self._party_downloading_track = None
        self._waiting_for_download_to_play = False
        cur_folder = getattr(self.audio_engine, 'folder_path', None)
        if not cur_folder or not os.path.exists(cur_folder):
            self.audio_engine.set_folder(target_dir)

        self.refresh_tracklist()

        target_idx = -1
        if file_path and os.path.exists(file_path):
            norm_target = os.path.normcase(os.path.abspath(file_path))
            for idx, p in enumerate(self.audio_engine.playlist):
                if os.path.normcase(os.path.abspath(p)) == norm_target:
                    target_idx = idx
                    break

            if target_idx == -1:
                self.audio_engine.playlist.append(file_path)
                target_idx = len(self.audio_engine.playlist) - 1
                self.populate_playlist_ui()
        elif self.audio_engine.playlist:
            target_idx = len(self.audio_engine.playlist) - 1

        if 0 <= target_idx < len(self.audio_engine.playlist):
            is_host = hasattr(self, "party_sync") and self.party_sync.is_host
            self._is_handling_party_event = True
            try:
                self.audio_engine.play_index(target_idx)
                if not is_host:
                    seek_pos = getattr(self, "_last_known_host_pos", target_time)
                    if seek_pos > 0:
                        self.audio_engine.seek(seek_pos)
                    should_play = getattr(self, "_last_known_host_playing", target_playing)
                    if should_play:
                        self.audio_engine.play()
                    else:
                        self.audio_engine.pause()
                else:
                    self.audio_engine.play()
                self.sync_play_state()
            finally:
                self._is_handling_party_event = False

            if is_host:
                self._broadcast_party_track()
                self._check_and_prefetch_next_in_queue()

    def _on_party_play_received(self, ts: float):
        if hasattr(self, "party_sync") and self.party_sync.is_host and not self.party_sync.allow_guest_control:
            return
        self._is_handling_party_event = True
        try:
            curr_pos = self.audio_engine.get_position()
            if abs(curr_pos - ts) > 0.35:
                self.audio_engine.seek(ts)
            if not self.audio_engine.is_playing:
                self.audio_engine.play()
                self.sync_play_state()
        finally:
            self._is_handling_party_event = False

    def _on_party_pause_received(self, ts: float):
        if hasattr(self, "party_sync") and self.party_sync.is_host and not self.party_sync.allow_guest_control:
            return
        self._is_handling_party_event = True
        try:
            if self.audio_engine.is_playing:
                self.audio_engine.pause()
                self.sync_play_state()
            curr_pos = self.audio_engine.get_position()
            if abs(curr_pos - ts) > 0.35:
                self.audio_engine.seek(ts)
        finally:
            self._is_handling_party_event = False

    def _on_party_seek_received(self, ts: float):
        if hasattr(self, "party_sync") and self.party_sync.is_host and not self.party_sync.allow_guest_control:
            return
        self._is_handling_party_event = True
        try:
            self.audio_engine.seek(ts)
            self.update_timeline()
        finally:
            self._is_handling_party_event = False

    def _on_party_heartbeat_received(self, ts: float, is_playing: bool):
        if hasattr(self, "party_sync") and self.party_sync.is_host:
            return
        self._last_known_host_pos = ts
        self._last_known_host_playing = is_playing
        if getattr(self, "_party_downloading_track", None):
            return
        curr_pos = self.audio_engine.get_position()
        drift = abs(curr_pos - ts)
        if drift > 0.40:
            log.info("[PARTY SYNC] Clock drift: %.2fs -> snapping seek", drift)
            self._is_handling_party_event = True
            try:
                self.audio_engine.seek(ts)
            finally:
                self._is_handling_party_event = False

    def refresh_folder_switcher(self):
        if getattr(self, "combo_active_folder", None) is None:
            return
        self.combo_active_folder.blockSignals(True)
        self.combo_active_folder.clear()

        cur = os.path.abspath(self.audio_engine.folder_path) if self.audio_engine.folder_path else ""
        root_dir = os.path.abspath(DEFAULT_MUSIC_DIR)

        # 1. All Music root
        self.combo_active_folder.addItem("All Music", root_dir)

        # 2. Subfolders of DEFAULT_MUSIC_DIR
        if os.path.exists(root_dir):
            for entry in sorted(os.listdir(root_dir)):
                full_p = os.path.abspath(os.path.join(root_dir, entry))
                if os.path.isdir(full_p):
                    self.combo_active_folder.addItem(f"{entry}", full_p)

        # 3. Custom external folder if active
        found = False
        for idx in range(self.combo_active_folder.count()):
            p = self.combo_active_folder.itemData(idx)
            if p and os.path.abspath(p) == cur:
                self.combo_active_folder.setCurrentIndex(idx)
                found = True
                break

        if not found and cur and os.path.exists(cur):
            display_name = os.path.basename(cur) or cur
            self.combo_active_folder.insertItem(1, f"{display_name} (Custom)", cur)
            self.combo_active_folder.setCurrentIndex(1)

        # 4. Browse option at bottom
        self.combo_active_folder.addItem("+ Browse Folder...", "__browse__")
        self.combo_active_folder.blockSignals(False)

    def on_active_folder_selected(self, index: int):
        target = self.combo_active_folder.itemData(index)
        if target == "__browse__":
            self.choose_music_folder()
            self.refresh_folder_switcher()
            return
        if target and target != "__browse__" and os.path.exists(target):
            cur = os.path.abspath(self.audio_engine.folder_path) if self.audio_engine.folder_path else ""
            if cur != os.path.abspath(target):
                self.audio_engine.set_folder(target)
                self.refresh_tracklist()
                if hasattr(self, "lbl_folder_path") and self.lbl_folder_path:
                    self.lbl_folder_path.setText(f"{target}")
                if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "lbl_folder_path"):
                    self.settings_dialog.lbl_folder_path.setText(f"{target}")
                self.save_settings()
