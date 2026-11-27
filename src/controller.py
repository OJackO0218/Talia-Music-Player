"""Main controller panel for Talia playback, appearance, and configuration."""

import logging
import os
import random
import re
import subprocess
import sys
import threading
import time
import weakref
from typing import Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QCursor, QIcon, QPainter, QPen, QPixmap
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
    QMenu,
    QProgressBar,
    QPushButton,
    QSlider,
    QSystemTrayIcon,
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
    PROJECT_ROOT,
    SUPPORTED_AUDIO_EXTS,
    VK_CONTROL,
    VK_OEM_4,
    VK_OEM_6,
    apply_playtime_exp,
    get_cumulative_exp_for_level,
    load_settings,
    save_settings,
    trim_process_memory,
    user32,
)
from discord_service import DiscordRpcService, parse_track_info
from download_panel import DownloadPanelMixin
from guide_dialog import GuideDialog
from overlay import OverlayWindow
from party_sync import PartySyncService
from playlist_panel import PlaylistPanelMixin
from settings_dialog import SettingsDialog
from song_downloader import SongDownloaderService
from spotify_sync import SpotifySyncService
from ui_widgets import (
    CyberButton,
    CyberCardContainer,
    CyberChamferButton,
    CyberScrollingTrackLabel,
    CyberVerticalVolumeSlider,
    NoScrollComboBox,
)

log = logging.getLogger("ControlPanel")

USER_SPRITES_DIR = os.path.join(PROJECT_ROOT, "assets", "user_sprites")


class OutsideClickFilter(QObject):
    """Detects clicks outside the sliding panel and controls bar to auto-close."""

    def __init__(self, panel, controls_bar, overlay, parent=None):
        super().__init__(parent)
        self._panel_ref = weakref.ref(panel)
        self._controls_ref = weakref.ref(controls_bar)
        self._overlay_ref = weakref.ref(overlay)

    @property
    def panel(self):
        return self._panel_ref()

    @property
    def controls_bar(self):
        return self._controls_ref()

    @property
    def overlay(self):
        return self._overlay_ref()

    def eventFilter(self, obj, event):
        panel = self.panel
        controls_bar = self.controls_bar
        overlay = self.overlay
        if panel is None or controls_bar is None or overlay is None:
            return False
        if event.type() == QEvent.Type.MouseButtonPress:
            try:
                is_vis = panel.isVisible()
            except RuntimeError:
                return False
            if is_vis and not getattr(panel, "is_animating", False):
                pos = event.globalPosition().toPoint()
                # Don't auto-close if settings dialog or another modal / popup is open
                if hasattr(self.panel, "settings_dialog") and self.panel.settings_dialog.isVisible():
                    return False
                party_dlg = getattr(self.panel, "_party_dialog", None)
                if party_dlg is not None and party_dlg.isVisible():
                    return False
                spotify_dlg = getattr(self.panel, "_spotify_dialog", None)
                if spotify_dlg is not None and spotify_dlg.isVisible():
                    return False
                if (
                    hasattr(self.panel, "_lyrics_fetcher_win")
                    and self.panel._lyrics_fetcher_win is not None
                    and self.panel._lyrics_fetcher_win.isVisible()
                ):
                    return False
                if QApplication.activePopupWidget() or QApplication.activeModalWidget():
                    return False

                in_panel = self.panel.frameGeometry().contains(pos)
                in_ctrl = self.controls_bar.isVisible() and self.controls_bar.frameGeometry().contains(pos)
                in_overlay = self.overlay.frameGeometry().contains(pos)
                if not (in_panel or in_ctrl or in_overlay):
                    self.panel.close_slide_panel()
        return False


class TaliaControlsBar(QWidget):
    """
    Floating playback controls bar that pops out below (or above) Talia.
    - Transparent background (zero black box).
    - 4 buttons: Previous, Play/Pause, Next, Shuffle.
    - Nearest-neighbor crisp scaling (FastTransformation, no blurriness).
    """

    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self.panel = panel
        self.audio_engine = panel.audio_engine

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("taliaControlsBar")
        self.setStyleSheet("""
            QWidget#taliaControlsBar {
                background-color: rgba(6, 20, 36, 220);
                border: 1px solid rgba(0, 240, 255, 95);
                border-radius: 6px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(4)

        btn_style = """
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 45);
                border-radius: 5px;
            }
            QPushButton:pressed {
                background-color: rgba(0, 240, 255, 90);
                border-radius: 5px;
            }
        """

        self.btn_prev = QPushButton(self)
        self.btn_prev.setFixedSize(28, 28)
        self.btn_prev.setStyleSheet(btn_style)
        self.btn_prev.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_prev.setToolTip("Previous Track")
        self.btn_prev.clicked.connect(self._on_prev_clicked)

        self.btn_play = QPushButton(self)
        self.btn_play.setFixedSize(28, 28)
        self.btn_play.setStyleSheet(btn_style)
        self.btn_play.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_play.setToolTip("Play / Pause")
        self.btn_play.clicked.connect(self._on_play_clicked)

        self.btn_next = QPushButton(self)
        self.btn_next.setFixedSize(28, 28)
        self.btn_next.setStyleSheet(btn_style)
        self.btn_next.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_next.setToolTip("Next Track")
        self.btn_next.clicked.connect(self._on_next_clicked)

        self.btn_shuffle = QPushButton(self)
        self.btn_shuffle.setFixedSize(28, 28)
        self.btn_shuffle.setStyleSheet(btn_style)
        self.btn_shuffle.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_shuffle.setToolTip("Toggle Shuffle")
        self.btn_shuffle.clicked.connect(self._on_shuffle_clicked)

        layout.addWidget(self.btn_prev)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.btn_shuffle)

        self._load_icons()
        self.sync_state()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(6, 20, 36, 230))
        painter.setPen(QPen(QColor(0, 240, 255, 120), 1.2))
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.drawRoundedRect(rect, 6, 6)

    def _load_crisp_icon(self, filename: str, target_size: int = 24) -> QIcon:
        """Loads sprite with nearest-neighbor scaling (FastTransformation) for crisp pixel art."""
        p = os.path.join(USER_SPRITES_DIR, filename)
        if not os.path.exists(p):
            return QIcon()
        pix = QPixmap(p)
        if pix.isNull():
            return QIcon()
        scaled = pix.scaled(
            target_size,
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        return QIcon(scaled)

    def _load_icons(self):
        self.icon_prev = self._load_crisp_icon("previous_button.png", 24)
        self.icon_play = self._load_crisp_icon("play_button.png", 24)
        self.icon_pause = self._load_crisp_icon("pause_button.png", 24)
        self.icon_next = self._load_crisp_icon("next_button.png", 24)
        self.icon_shuffle_on = self._load_crisp_icon("shuffle_button.png", 24)   # Blue when ON
        self.icon_shuffle_off = self._load_crisp_icon("shuffle_active.png", 24)  # Red when OFF
        self.icon_shuffle = self.icon_shuffle_off
        self.icon_shuffle_active = self.icon_shuffle_on

        self.btn_prev.setIcon(self.icon_prev)
        self.btn_prev.setIconSize(QSize(24, 24))
        self.btn_next.setIcon(self.icon_next)
        self.btn_next.setIconSize(QSize(24, 24))

    def sync_state(self):
        """Synchronizes play/pause and shuffle button icons without setting any text."""
        is_playing = getattr(self.audio_engine, "is_playing", False)
        if is_playing:
            self.btn_play.setIcon(self.icon_pause)
        else:
            self.btn_play.setIcon(self.icon_play)
        self.btn_play.setIconSize(QSize(24, 24))
        self.btn_play.setText("")

        is_shuffle = getattr(self.audio_engine, "shuffle", False)
        if is_shuffle:
            self.btn_shuffle.setIcon(self.icon_shuffle_on)
        else:
            self.btn_shuffle.setIcon(self.icon_shuffle_off)
        self.btn_shuffle.setIconSize(QSize(24, 24))
        self.btn_shuffle.setText("")

    def _on_prev_clicked(self):
        if hasattr(self.panel, "on_prev_clicked"):
            self.panel.on_prev_clicked()
        else:
            self.audio_engine.prev_track()
        self.sync_state()

    def _on_play_clicked(self):
        if hasattr(self.panel, "toggle_play_pause"):
            self.panel.toggle_play_pause()
        else:
            self.audio_engine.toggle_play_pause()
        self.sync_state()

    def _on_next_clicked(self):
        if hasattr(self.panel, "on_next_clicked"):
            self.panel.on_next_clicked()
        else:
            self.audio_engine.next_track()
        self.sync_state()

    def _on_shuffle_clicked(self):
        if hasattr(self.panel, "toggle_shuffle"):
            self.panel.toggle_shuffle()
        else:
            self.audio_engine.shuffle = not getattr(self.audio_engine, "shuffle", False)
            self.sync_state()
            if hasattr(self.panel, "save_settings"):
                self.panel.save_settings()





class ControlPanel(PlaylistPanelMixin, DownloadPanelMixin, QWidget):
    """Clean, modern controller for Talia Music Player, Visualizer, and Settings."""

    yt_search_progress = pyqtSignal(str)
    yt_search_done = pyqtSignal(bool, str, str)

    def __init__(
        self,
        overlay: OverlayWindow,
        audio_engine: CyberAudioEngine,
        lyrics_overlay=None,
        defer_populate: bool = False,
        initial_settings: dict | None = None,
    ):
        super().__init__()
        self._defer_initial_populate = defer_populate
        self.yt_search_progress.connect(self._on_yt_search_progress_safe)
        self.yt_search_done.connect(self._on_yt_search_download_done)
        self.overlay = overlay
        self.overlay.panel = self
        self.audio_engine = audio_engine
        self.audio_engine.track_started_hook = self.record_track_played
        self.lyrics_overlay = lyrics_overlay

        # Pre-register bundled Cyberpunk and mono fonts (no-op if already initialized)
        from config import init_app_fonts
        init_app_fonts()

        # Persistent level / XP state. Held in memory while Talia runs and
        # written back through every save path (song change, settings, close).
        cfg = initial_settings if isinstance(initial_settings, dict) else load_settings()
        self.level = max(0, int(cfg.get("level", 0)))
        self.exp = max(0, int(cfg.get("exp", 0)))
        self.playtime_seconds = max(0, int(cfg.get("playtime_seconds", 0)))
        self._last_exp_save = time.time()
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
        self.last_bracket_left_state = False
        self.last_bracket_right_state = False
        self.is_user_scrubbing = False
        self.setWindowTitle("Talia Player")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        # Slide-out Settings Panel configuration
        self.setFixedSize(380, 460)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("taliaSlidePanel")

        self.play_counts = {}
        self.favourite_tracks = set()
        self.custom_playlists = {}
        self.selected_batch_tracks = set()
        self.current_playlist = "All Tracks"
        self.current_sort = "Default"
        self._duration_cache = {}

        self.is_animating = False
        self.controls_bar = TaliaControlsBar(self)

        from radio_mix import RadioMixManager

        self.radio_mix = RadioMixManager(self)
        self.radio_mix.status_changed.connect(self._on_radio_status_changed)
        self.radio_mix.track_ready.connect(self._on_radio_track_ready)
        self.radio_mix.prefetch_ready.connect(self._on_radio_prefetch_ready)
        self.radio_mix.track_saved_permanently.connect(self._on_radio_saved_permanently)

        self.init_ui()

        # Outside click listener to smoothly auto-close on desktop clicks (single filter per QApplication)
        qapp = QApplication.instance()
        if qapp is not None:
            prev_flt = getattr(qapp, "_talia_outside_filter", None)
            if prev_flt is not None:
                try:
                    qapp.removeEventFilter(prev_flt)
                except Exception:
                    pass
            self.outside_click_filter = OutsideClickFilter(
                self, self.controls_bar, self.overlay, parent=qapp
            )
            qapp._talia_outside_filter = self.outside_click_filter
            qapp.installEventFilter(self.outside_click_filter)
        else:
            self.outside_click_filter = OutsideClickFilter(self, self.controls_bar, self.overlay)

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
        self.chk_subtitle_bg = getattr(self.settings_dialog, "chk_subtitle_bg", None)
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
        self._party_dialog = None
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
        self._spotify_dialog = None

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

        self._init_tray_icon()

    @property
    def party_dialog(self):
        """Lazily construct Listen Together dialog on first access."""
        if self._party_dialog is None:
            from party_dialog import PartySyncDialog

            self._party_dialog = PartySyncDialog(self)
        return self._party_dialog

    @property
    def spotify_dialog(self):
        """Lazily construct Spotify Sync dialog on first access."""
        if self._spotify_dialog is None:
            from spotify_dialog import SpotifySyncDialog

            self._spotify_dialog = SpotifySyncDialog(self)
        return self._spotify_dialog

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Card container with stylish Cyberpunk dark background & single chamfer border (Figma node 2215:411)
        self.card_container = CyberCardContainer(self)
        self.card_container.setObjectName("slidePanelCard")
        self.card_container.setStyleSheet("QFrame#slidePanelCard { border: none; background: transparent; color: #ff003c; }")

        lbl_menu_anchor = QLabel("MENU", self.card_container)
        lbl_menu_anchor.setStyleSheet("color: #ff003c;")
        lbl_menu_anchor.hide()

        container_layout = QVBoxLayout(self.card_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 1. Top Header Bar (spans full card width over red header_geometry4 banner)
        header_widget = QWidget()
        header_widget.setFixedHeight(42)
        hbox_header = QHBoxLayout(header_widget)
        hbox_header.setContentsMargins(12, 2, 12, 2)
        hbox_header.setSpacing(6)

        # 1a. Level / XP block:
        #     Level number + "LEVEL" label, 110x2 XP bar, and playtime readout.
        level_widget = QWidget()
        level_widget.setFixedSize(220, 36)

        self.lbl_level_badge = QLabel(level_widget)
        self.lbl_level_badge.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_level_badge.setStyleSheet(
            "color: #5EF6FF; background: transparent;"
        )
        self.lbl_level_badge.setGeometry(0, 0, 100, 30)
        self.lbl_level_badge.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom
        )

        self.exp_bar = QProgressBar(level_widget)
        self.exp_bar.setGeometry(0, 29, 110, 2)
        self.exp_bar.setTextVisible(False)
        self.exp_bar.setStyleSheet(
            "QProgressBar { background-color: #000000; border: none; }"
            "QProgressBar::chunk { background-color: #5EF6FF; }"
        )

        self.lbl_exp_progress = QLabel(level_widget)
        self.lbl_exp_progress.setStyleSheet(
            "color: #5EF6FF; font-size: 11px;"
            "font-family: 'Share Tech Mono', 'Consolas', monospace;"
        )
        self.lbl_exp_progress.setGeometry(114, 18, 106, 17)
        self.lbl_exp_progress.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom
        )

        hbox_header.addWidget(level_widget)
        self._refresh_level_display()

        hbox_header.addStretch()

        # 1c. Action Buttons with Chamfered Corners matching Figma (26x26)
        # Order: [Party 👥] -> [Spotify Sync] -> [Settings ⚙] -> [Close ✕]
        self.btn_party_sync = CyberChamferButton("Listen Together", variant="party")
        self.btn_party_sync.setFixedSize(26, 26)
        self.btn_party_sync.setToolTip("Listen Together (Real-time Party Sync)")
        self.btn_party_sync.clicked.connect(self.open_party_dialog)
        hbox_header.addWidget(self.btn_party_sync)

        self.btn_spotify_sync = CyberChamferButton("Spotify", variant="spotify")
        self.btn_spotify_sync.setFixedSize(26, 26)
        self.btn_spotify_sync.setToolTip("Spotify Playlist Sync")
        self.btn_spotify_sync.clicked.connect(self.open_spotify_dialog)
        hbox_header.addWidget(self.btn_spotify_sync)

        self.btn_open_settings = CyberChamferButton("⚙", variant="settings")
        self.btn_open_settings.setObjectName("btnOpenSettings")
        self.btn_open_settings.setFixedSize(26, 26)
        self.btn_open_settings.setToolTip("Advanced Settings")
        self.btn_open_settings.clicked.connect(self.open_settings_window)
        hbox_header.addWidget(self.btn_open_settings)

        self.btn_close = CyberChamferButton("✕", variant="exit")
        self.btn_close.setFixedSize(26, 26)
        self.btn_close.setToolTip("Close Panel")
        self.btn_close.clicked.connect(self.close_slide_panel)
        hbox_header.addWidget(self.btn_close)

        container_layout.addWidget(header_widget)

        # 2. Main Middle Body (Volume strip on left, Content on right)
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(14, 0, 16, 6)
        body_layout.setSpacing(6)

        # Left side vertical volume slider (Figma Demo frame rotated volume slider spanning full flank)
        init_vol = int(getattr(self.audio_engine, "volume", 1.0) * 100)
        self.slider_vol = CyberVerticalVolumeSlider(self)
        self.slider_vol.setValue(init_vol)
        self.slider_vol.valueChanged.connect(self.on_volume_changed)
        body_layout.addWidget(self.slider_vol)

        # Hidden label kept for backwards compatibility with tests checking lbl_vol_val
        self.lbl_vol_val = QLabel(f"{init_vol}%", self)
        self.lbl_vol_val.hide()

        # Right side main content layout (with top breathing room below header banner)
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(0, 8, 0, 0)
        card_layout.setSpacing(6)
        body_layout.addLayout(card_layout, 1)

        container_layout.addWidget(body_widget, 1)

        # 2a. Playlist row: PLAYLIST: [ All Tracks v ] [+] [A] [X]
        hbox_playlist = QHBoxLayout()
        hbox_playlist.setSpacing(6)

        lbl_pl_icon = QLabel("PLAYLIST:")
        lbl_pl_icon.setStyleSheet("color: #5EF6FF; font-family: 'Rajdhani', sans-serif; font-weight: 800; font-size: 11px; letter-spacing: 1px;")
        hbox_playlist.addWidget(lbl_pl_icon)

        self.combo_playlist = NoScrollComboBox()
        self.combo_playlist.addItem("All Tracks")
        self.combo_playlist.addItem("Queue")
        self.combo_playlist.addItem("★ Favourites")
        self.combo_playlist.addItem("★ Random Mix")
        self.combo_playlist.setStyleSheet("""
            QComboBox {
                background-color: #050505;
                color: #ff8a84;
                border: 1px solid rgba(247, 80, 73, 77);
                border-radius: 2px;
                padding: 3px 6px;
                font-family: 'Rajdhani', sans-serif;
                font-size: 11px;
                font-weight: 600;
            }
            QComboBox:hover, QComboBox:focus {
                border-color: #F75049;
                background-color: rgba(247, 80, 73, 26);
            }
            QComboBox::drop-down {
                border: none;
                width: 16px;
            }
            QComboBox QAbstractItemView {
                background-color: #222325;
                color: #ff8a84;
                selection-background-color: #F75049;
                selection-color: #0e0e17;
                border: 1px solid rgba(247, 80, 73, 77);
                padding: 4px;
            }
        """)
        self.combo_playlist.currentTextChanged.connect(self.on_playlist_selected)
        hbox_playlist.addWidget(self.combo_playlist, 1)

        self.btn_queue_indicator = QPushButton("≡ 0")
        self.btn_queue_indicator.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_queue_indicator.setFixedHeight(26)
        self.btn_queue_indicator.setStyleSheet("""
            QPushButton {
                background-color: rgba(94, 246, 255, 0.12);
                color: #5EF6FF;
                border: 1px solid #5EF6FF;
                border-radius: 2px;
                font-family: 'Rajdhani', sans-serif;
                font-size: 11px;
                font-weight: 800;
                padding: 2px 7px;
            }
            QPushButton:hover {
                background-color: #5EF6FF;
                color: #050505;
                border: 1px solid #5EF6FF;
            }
        """)
        self.btn_queue_indicator.clicked.connect(self.on_queue_indicator_clicked)
        self.btn_queue_indicator.hide()
        hbox_playlist.addWidget(self.btn_queue_indicator)

        self.btn_new_playlist = CyberChamferButton("+", variant="new_playlist")
        self.btn_new_playlist.setFixedSize(26, 26)
        self.btn_new_playlist.setToolTip("Create a new playlist")
        self.btn_new_playlist.clicked.connect(self.on_new_playlist_clicked)
        hbox_playlist.addWidget(self.btn_new_playlist)

        self.btn_group_artist = CyberChamferButton("A", variant="action_cyan")
        self.btn_group_artist.setFixedSize(26, 26)
        self.btn_group_artist.setToolTip("Group songs by primary artist")
        self.btn_group_artist.clicked.connect(self.group_songs_by_artist)
        self.btn_group_artist.hide()

        self.btn_add_to_playlist = None

        self.btn_delete_playlist = CyberChamferButton("✕", variant="delete_playlist")
        self.btn_delete_playlist.setFixedSize(26, 26)
        self.btn_delete_playlist.setToolTip("Delete current custom playlist")
        self.btn_delete_playlist.clicked.connect(self.delete_current_playlist)
        hbox_playlist.addWidget(self.btn_delete_playlist)

        card_layout.addLayout(hbox_playlist)

        # 2b. Compact Random Mix Bar (shown only when ★ Random Mix is active)
        self.radio_mix_bar = QFrame()
        self.radio_mix_bar.setStyleSheet(
            "QFrame { background-color: rgba(14, 16, 26, 200); border: 1px solid rgba(94, 246, 255, 85); border-radius: 3px; }"
        )
        hbox_radio = QHBoxLayout(self.radio_mix_bar)
        hbox_radio.setContentsMargins(6, 4, 6, 4)
        hbox_radio.setSpacing(6)

        self.btn_radio_exclude = CyberChamferButton("EXCLUDE ▾", variant="action_neutral")
        self.btn_radio_exclude.setFixedHeight(24)
        self.btn_radio_exclude.setToolTip("Choose what types or artists to exclude from Random Mix")
        self.btn_radio_exclude.clicked.connect(self._show_radio_exclude_menu)
        hbox_radio.addWidget(self.btn_radio_exclude)

        self.btn_radio_save = CyberChamferButton("SAVE TRACK", variant="action_green")
        self.btn_radio_save.setFixedHeight(24)
        self.btn_radio_save.setToolTip("Move the current Random Mix song permanently into Downloaded Songs")
        self.btn_radio_save.clicked.connect(lambda: self.save_radio_track_permanently())
        hbox_radio.addWidget(self.btn_radio_save)

        self.lbl_radio_status = QLabel("Press Play to start Radio")
        self.lbl_radio_status.setStyleSheet(
            "color: #5EF6FF; font-family: 'Rajdhani', sans-serif; font-size: 11px; font-weight: 600; background: transparent; border: none;"
        )
        hbox_radio.addWidget(self.lbl_radio_status, 1)

        self.radio_mix_bar.hide()
        card_layout.addWidget(self.radio_mix_bar)

        # 3. Search Bar + Clear + Sort Selector
        hbox_search = QHBoxLayout()
        hbox_search.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search songs...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #050505;
                color: #ff8a84;
                border: 1px solid rgba(247, 80, 73, 77);
                border-radius: 2px;
                padding: 4px 8px;
                font-family: 'Rajdhani', sans-serif;
                font-size: 11px;
                selection-background-color: #F75049;
                selection-color: #0e0e17;
            }
            QLineEdit:focus {
                background-color: rgba(247, 80, 73, 26);
                border: 1px solid #F75049;
                color: #ff8a84;
            }
        """)
        self.search_input.textChanged.connect(self.filter_tracks)
        hbox_search.addWidget(self.search_input, 1)

        self.btn_clear_search = CyberChamferButton("✕", variant="exit")
        self.btn_clear_search.setFixedSize(24, 24)
        self.btn_clear_search.clicked.connect(lambda: self.search_input.clear())
        self.btn_clear_search.hide()

        lbl_sort = QLabel("SORT:")
        lbl_sort.setStyleSheet("color: #5EF6FF; font-family: 'Rajdhani', sans-serif; font-weight: 800; font-size: 10px; letter-spacing: 1px;")
        hbox_search.addWidget(lbl_sort)

        self.combo_sort = NoScrollComboBox()
        self.combo_sort.addItems([
            "Default",
            "Time Added",
            "Alphabetical (A-Z)",
            "Sort by artist",
            "Duration",
            "Most Played",
            "Least Played",
            "Random",
        ])
        self.combo_sort.setStyleSheet("""
            QComboBox {
                background-color: #050505;
                color: #ff8a84;
                border: 1px solid rgba(247, 80, 73, 77);
                border-radius: 2px;
                padding: 3px 6px;
                font-family: 'Rajdhani', sans-serif;
                font-size: 10px;
                font-weight: 600;
            }
            QComboBox:hover, QComboBox:focus {
                border-color: #F75049;
                background-color: rgba(247, 80, 73, 26);
            }
            QComboBox::drop-down {
                border: none;
                width: 14px;
            }
            QComboBox QAbstractItemView {
                background-color: #222325;
                color: #ff8a84;
                selection-background-color: #F75049;
                selection-color: #0e0e17;
                border: 1px solid rgba(247, 80, 73, 77);
                padding: 4px;
            }
        """)
        self.combo_sort.currentTextChanged.connect(self.on_sort_changed)
        self.combo_sort.activated.connect(self.on_sort_activated)
        hbox_search.addWidget(self.combo_sort)

        card_layout.addLayout(hbox_search)
        self.search_input.returnPressed.connect(self.on_search_return_pressed)

        # YouTube Download Banner / Prompt (merged with search)
        self.yt_download_card = QFrame()
        self.yt_download_card.setObjectName("ytDownloadCard")
        self.yt_download_card.setStyleSheet("""
            QFrame#ytDownloadCard {
                background-color: rgba(30, 20, 24, 240);
                border: 1px solid rgba(255, 0, 60, 160);
                border-radius: 6px;
                padding: 4px;
            }
        """)
        yt_card_layout = QVBoxLayout(self.yt_download_card)
        yt_card_layout.setContentsMargins(8, 6, 8, 6)
        yt_card_layout.setSpacing(4)

        self.lbl_yt_prompt = QLabel("No song detected.")
        self.lbl_yt_prompt.setStyleSheet("color: #fca5a5; font-size: 11px; font-weight: 500;")
        self.lbl_yt_prompt.setWordWrap(True)
        yt_card_layout.addWidget(self.lbl_yt_prompt)

        self.btn_yt_download = QPushButton("Download from YouTube")
        self.btn_yt_download.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_yt_download.setStyleSheet("""
            QPushButton {
                background-color: #ff003c;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                border: none;
                border-radius: 4px;
                padding: 5px 8px;
            }
            QPushButton:hover {
                background-color: #e10034;
            }
            QPushButton:pressed {
                background-color: #b30029;
            }
        """)
        self.btn_yt_download.clicked.connect(self.on_yt_prompt_download_clicked)
        yt_card_layout.addWidget(self.btn_yt_download)

        self.yt_download_card.hide()
        card_layout.addWidget(self.yt_download_card)

        # 4. Playlist selection: Track List (ListWidget)
        self.list_tracks = QListWidget()
        self.list_tracks.setSpacing(5)
        self.list_tracks.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_tracks.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_tracks.customContextMenuRequested.connect(self.show_track_context_menu)
        self.list_tracks.itemClicked.connect(self.on_track_clicked)
        self.list_tracks.currentItemChanged.connect(self._on_track_selection_changed)
        self.list_tracks.itemDoubleClicked.connect(self.on_track_double_clicked)
        self.list_tracks.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QListWidget::item {
                background-color: transparent;
                border: none;
                padding: 1px 0px;
            }
            QListWidget::item:selected {
                background-color: transparent;
            }
            QListWidget::item:hover {
                background-color: transparent;
            }
        """)
        card_layout.addWidget(self.list_tracks, 1)

        # 5. Batch actions & summary row
        hbox_batch = QHBoxLayout()
        hbox_batch.setSpacing(6)

        # Bottom batch actions bar (Figma node 2215:411 Buttons/Web)
        bottom_widget = QWidget()
        bottom_widget.setFixedHeight(30)
        hbox_batch = QHBoxLayout(bottom_widget)
        hbox_batch.setContentsMargins(42, 0, 78, 6)
        hbox_batch.setSpacing(8)

        btn_cyber_action_style = """
            QPushButton {
                background-color: rgba(14, 24, 38, 0.85);
                color: #5EF6FF;
                border: 1px solid #5EF6FF;
                border-radius: 2px;
                font-size: 9px;
                font-weight: bold;
                letter-spacing: 1px;
                padding: 2px 7px;
                text-transform: uppercase;
            }
            QPushButton:hover {
                background-color: rgba(94, 246, 255, 0.25);
                color: #ffffff;
                border-color: #ffffff;
            }
            QPushButton:pressed {
                background-color: rgba(94, 246, 255, 0.45);
            }
        """

        btn_cyber_delete_style = """
            QPushButton {
                background-color: rgba(28, 12, 16, 0.85);
                color: #f87171;
                border: 1px solid #ef4444;
                border-radius: 2px;
                font-size: 9px;
                font-weight: bold;
                letter-spacing: 1px;
                padding: 2px 7px;
                text-transform: uppercase;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.35);
                color: #ffffff;
                border-color: #ffffff;
            }
            QPushButton:pressed {
                background-color: rgba(239, 68, 68, 0.60);
            }
        """

        self.btn_select_all = CyberChamferButton("SELECT ALL", variant="action_cyan")
        self.btn_select_all.setFixedHeight(24)
        self.btn_select_all.setToolTip("Toggle select all visible tracks")
        self.btn_select_all.clicked.connect(self.on_select_all_clicked)
        hbox_batch.addWidget(self.btn_select_all)

        self.btn_batch_delete = CyberChamferButton("DELETE SELECTED", variant="action_cyan")
        self.btn_batch_delete.setFixedHeight(24)
        self.btn_batch_delete.setToolTip("Remove selected songs from playlist")
        self.btn_batch_delete.clicked.connect(self.batch_delete_selected)
        hbox_batch.addWidget(self.btn_batch_delete)

        hbox_batch.addStretch()

        self.lbl_track_summary = QLabel("")
        self.lbl_track_summary.setStyleSheet("color: #a1a1aa; font-size: 10px; font-family: monospace;")
        hbox_batch.addWidget(self.lbl_track_summary)

        container_layout.addWidget(bottom_widget)
        root_layout.addWidget(self.card_container)

        # Wire transport button references to controls bar
        self.btn_play_pause = self.controls_bar.btn_play
        self.btn_prev = self.controls_bar.btn_prev
        self.btn_next = self.controls_bar.btn_next
        self.btn_shuffle = self.controls_bar.btn_shuffle

        # Persistent floating download status badge on bottom-right of menu panel
        self.download_status_badge = QFrame(self)
        self.download_status_badge.setObjectName("downloadStatusBadge")
        self.download_status_badge.setStyleSheet("""
            QFrame#downloadStatusBadge {
                background-color: rgba(10, 16, 30, 0.96);
                border: 1px solid #00f0ff;
                border-radius: 6px;
            }
        """)
        badge_layout = QHBoxLayout(self.download_status_badge)
        badge_layout.setContentsMargins(8, 4, 8, 4)
        badge_layout.setSpacing(6)

        self.lbl_download_badge_icon = QLabel("⬇")
        self.lbl_download_badge_icon.setStyleSheet("color: #00f0ff; font-size: 11px; font-weight: bold;")
        badge_layout.addWidget(self.lbl_download_badge_icon)

        self.lbl_download_badge_text = QLabel("Downloading...")
        self.lbl_download_badge_text.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 500;")
        badge_layout.addWidget(self.lbl_download_badge_text)

        self.download_status_badge.hide()

        # Compatibility proxies for background services
        self.lbl_track_title = CyberScrollingTrackLabel()
        self.slider_seek = QSlider(Qt.Orientation.Horizontal)
        self.lbl_time_cur = QLabel("00:00")
        self.lbl_time_dur = QLabel("00:00")
        self.btn_lyrics = CyberButton("Lyrics: On", variant="primary")
        self.btn_eco = QPushButton("Eco Mode: Off")
        self.btn_audio_mode = QPushButton("Player Mode")
        self.btn_move_talia = QPushButton("Lock Window")
        self.queue_container = QWidget(self)
        self.queue_container.hide()
        self.list_queue = QListWidget()
        self.btn_toggle_queue = QPushButton("Queue (0)")
        self.btn_clear_queue = QPushButton("Clear Queue")
        self.combo_active_folder = NoScrollComboBox()
        self.btn_browse_folder = QPushButton("...")
        self.combo_dl_folder = NoScrollComboBox()
        self.edit_dl_search = QLineEdit()
        self.btn_dl_search = QPushButton("Search")
        self.list_dl_results = QListWidget()
        self.lbl_dl_status = QLabel("")
        self.progress_dl = QSlider(Qt.Orientation.Horizontal)

        if not getattr(self, "_defer_initial_populate", False):
            self.populate_playlist_ui()

    def calculate_slide_geometries(self):
        """
        Calculates screen-edge aware coordinates for sliding panel and popped-out controls.
        - Default: panel slides left out of Talia, controls sit below Talia.
        - If left blocked: slides right.
        - If bottom blocked: controls sit above Talia.
        - If both left and right blocked: panel falls back to above/below.
        - Never lets any part go off-screen.
        """
        talia_geo = self.overlay.geometry()
        screen = QApplication.screenAt(talia_geo.center()) or QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        panel_w = self.width() if self.width() > 50 else 380
        panel_h = self.height() if self.height() > 50 else 460
        ctrl_w = 136
        ctrl_h = 34

        # 1. Controls Bar Placement (Below Talia default; Above if bottom blocked)
        space_below = avail.bottom() - talia_geo.bottom()
        space_above = talia_geo.top() - avail.top()

        if space_below >= ctrl_h + 6:
            ctrl_end_y = talia_geo.bottom() + 4
            ctrl_start_y = talia_geo.bottom() - 10
        elif space_above >= ctrl_h + 6:
            ctrl_end_y = talia_geo.top() - ctrl_h - 4
            ctrl_start_y = talia_geo.top() + 10
        else:
            ctrl_end_y = max(avail.top(), min(avail.bottom() - ctrl_h, talia_geo.bottom() + 4))
            ctrl_start_y = ctrl_end_y

        ctrl_end_x = max(avail.left(), min(avail.right() - ctrl_w, talia_geo.center().x() - ctrl_w // 2))
        ctrl_start_x = ctrl_end_x

        ctrl_target = QRect(ctrl_end_x, ctrl_end_y, ctrl_w, ctrl_h)
        ctrl_start = QRect(ctrl_start_x, ctrl_start_y, ctrl_w, ctrl_h)

        # 2. Settings Panel Placement (Left default; Right if left blocked; Above/Below fallback)
        space_left = talia_geo.left() - avail.left()
        space_right = avail.right() - talia_geo.right()

        panel_target_y = max(avail.top() + 4, min(avail.bottom() - panel_h - 4, talia_geo.top()))

        if space_left >= panel_w + 6:
            # Slides LEFT (Default)
            panel_end_x = talia_geo.left() - panel_w - 6
            panel_start_x = talia_geo.left() - 20
            panel_end_y = panel_target_y
            panel_start_y = panel_target_y
        elif space_right >= panel_w + 6:
            # Slides RIGHT
            panel_end_x = talia_geo.right() + 6
            panel_start_x = talia_geo.right() - panel_w + 20
            panel_end_y = panel_target_y
            panel_start_y = panel_target_y
        else:
            # Both Left and Right blocked: Fallback to Above / Below
            panel_end_x = max(avail.left() + 4, min(avail.right() - panel_w - 4, talia_geo.center().x() - panel_w // 2))
            panel_start_x = panel_end_x
            if space_above >= panel_h + ctrl_h + 10:
                panel_end_y = talia_geo.top() - panel_h - 6
                panel_start_y = talia_geo.top() - 20
            else:
                panel_end_y = min(avail.bottom() - panel_h, ctrl_end_y + ctrl_h + 6)
                panel_start_y = ctrl_end_y

        # Clamping guarantees: Never go off-screen
        panel_end_x = max(avail.left(), min(avail.right() - panel_w, panel_end_x))
        panel_end_y = max(avail.top(), min(avail.bottom() - panel_h, panel_end_y))

        panel_target = QRect(panel_end_x, panel_end_y, panel_w, panel_h)
        panel_start = QRect(panel_start_x, panel_start_y, panel_w, panel_h)

        return panel_start, panel_target, ctrl_start, ctrl_target

    def open_slide_panel(self):
        """Smoothly slides the settings panel out of Talia and pops out playback controls."""
        if self.isVisible() or getattr(self, "is_animating", False):
            return

        try:
            from cyber_sfx import get_cyber_sfx
            get_cyber_sfx().play_open()
        except Exception:
            pass

        if getattr(self, "_defer_initial_populate", False):
            self._defer_initial_populate = False
            self.populate_playlist_ui()

        panel_start, panel_target, ctrl_start, ctrl_target = self.calculate_slide_geometries()

        self.setGeometry(panel_start)
        self.show()
        self.raise_()

        self.controls_bar.setGeometry(ctrl_start)
        self.controls_bar.show()
        self.controls_bar.raise_()
        self.controls_bar.sync_state()
        if hasattr(self.overlay, "update_transport_state"):
            self.overlay.update_transport_state()

        self.is_animating = True

        self.panel_anim = QPropertyAnimation(self, b"geometry")
        self.panel_anim.setDuration(250)
        self.panel_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.panel_anim.setStartValue(panel_start)
        self.panel_anim.setEndValue(panel_target)

        self.ctrl_anim = QPropertyAnimation(self.controls_bar, b"geometry")
        self.ctrl_anim.setDuration(250)
        self.ctrl_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.ctrl_anim.setStartValue(ctrl_start)
        self.ctrl_anim.setEndValue(ctrl_target)

        def _on_open_done():
            self.is_animating = False

        self.panel_anim.finished.connect(_on_open_done)
        self.panel_anim.start()
        self.ctrl_anim.start()

    def close_slide_panel(self):
        """Smoothly slides the settings panel and controls back into Talia and hides them."""
        if not self.isVisible() or getattr(self, "is_animating", False):
            return

        try:
            from cyber_sfx import get_cyber_sfx
            get_cyber_sfx().play_close()
        except Exception:
            pass

        panel_start, _, ctrl_start, _ = self.calculate_slide_geometries()

        self.is_animating = True

        self.panel_anim = QPropertyAnimation(self, b"geometry")
        self.panel_anim.setDuration(220)
        self.panel_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.panel_anim.setStartValue(self.geometry())
        self.panel_anim.setEndValue(panel_start)

        self.ctrl_anim = QPropertyAnimation(self.controls_bar, b"geometry")
        self.ctrl_anim.setDuration(220)
        self.ctrl_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.ctrl_anim.setStartValue(self.controls_bar.geometry())
        self.ctrl_anim.setEndValue(ctrl_start)

        def _on_close_done():
            self.hide()
            self.controls_bar.hide()
            if getattr(self, "_party_dialog", None) is not None and self._party_dialog.isVisible():
                self._party_dialog.hide()
            if getattr(self, "_spotify_dialog", None) is not None and self._spotify_dialog.isVisible():
                self._spotify_dialog.hide()
            self.is_animating = False
            if hasattr(self.overlay, "update_transport_state"):
                self.overlay.update_transport_state()

        self.panel_anim.finished.connect(_on_close_done)
        self.panel_anim.start()
        self.ctrl_anim.start()

    def toggle_slide_panel(self):
        """Toggles the slide-out panel and controls."""
        if self.isVisible():
            self.close_slide_panel()
        else:
            self.open_slide_panel()

    def toggle_minigame(self):
        """Toggles the Mania 4K minigame overlay."""
        if hasattr(self, "osu_overlay") and self.osu_overlay:
            self.osu_overlay.toggle_game()
        elif hasattr(self, "minigame_overlay") and self.minigame_overlay:
            self.minigame_overlay.toggle_game()

    def toggle_osu_minigame(self):
        """Backwards compatibility alias for toggle_minigame."""
        self.toggle_minigame()

    def update_sliding_panel_position(self):
        """Keeps panel and controls locked with Talia when Talia is moved."""
        if self.isVisible() and not getattr(self, "is_animating", False):
            _, panel_target, _, ctrl_target = self.calculate_slide_geometries()
            self.setGeometry(panel_target)
            self.controls_bar.setGeometry(ctrl_target)

    def open_settings_window(self):
        """Opens dedicated Settings Dialog."""
        if hasattr(self, "settings_dialog"):
            try:
                from cyber_sfx import get_cyber_sfx
                get_cyber_sfx().play_open()
            except Exception:
                pass
            self.settings_dialog.show()
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()

    def open_advanced_settings(self):
        self.open_settings_window()

    def toggle_play_pause(self):
        self.on_play_pause_clicked()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_download_badge_position()

    def _update_download_badge_position(self):
        if hasattr(self, "download_status_badge") and self.download_status_badge:
            self.download_status_badge.adjustSize()
            bw = self.download_status_badge.width()
            bh = self.download_status_badge.height()
            self.download_status_badge.move(self.width() - bw - 14, self.height() - bh - 14)
            self.download_status_badge.raise_()

    def show_download_status(self, text: str, is_done: bool = False, is_error: bool = False):
        """Displays persistent download status badge on bottom-right of menu panel (always on top)."""
        if not hasattr(self, "download_status_badge"):
            return
        self.lbl_download_badge_text.setText(text)
        if is_error:
            self.lbl_download_badge_icon.setText("✕")
            self.lbl_download_badge_icon.setStyleSheet("color: #f87171; font-size: 11px; font-weight: bold;")
            self.lbl_download_badge_text.setStyleSheet("color: #f87171; font-size: 11px;")
        elif is_done:
            self.lbl_download_badge_icon.setText("✓")
            self.lbl_download_badge_icon.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
            self.lbl_download_badge_text.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
            QTimer.singleShot(4000, self.download_status_badge.hide)
        else:
            self.lbl_download_badge_icon.setText("⬇")
            self.lbl_download_badge_icon.setStyleSheet("color: #00f0ff; font-size: 11px; font-weight: bold;")
            self.lbl_download_badge_text.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 500;")
        self.download_status_badge.show()
        self.download_status_badge.raise_()
        self._update_download_badge_position()

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
        if (
            getattr(self, "current_playlist", "") == "★ Random Mix"
            and hasattr(self, "radio_mix")
            and self.radio_mix
        ):
            cur_path = getattr(self.audio_engine, "_active_file_path", "") or None
            if not cur_path:
                cur_idx = self.audio_engine.current_index
                cur_path = (
                    self.audio_engine.playlist[cur_idx]
                    if 0 <= cur_idx < len(self.audio_engine.playlist)
                    else None
                )
            if not self.radio_mix.is_radio_cached_track(cur_path):
                self.radio_mix.request_next_track(auto_play=True)
                return
            self.audio_engine.toggle_play_pause()
            self.sync_play_state()
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
        if hasattr(self, "controls_bar") and self.controls_bar:
            self.controls_bar.sync_state()
        if hasattr(self.overlay, "update_transport_state"):
            self.overlay.update_transport_state()

        self.lbl_track_title.setText(f"{self.audio_engine.get_current_track_title()}")

        # Update Discord Rich Presence
        self._push_discord_playback(
            self.audio_engine.get_position(),
            self.audio_engine.get_duration(),
        )

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

        cur_idx = self.audio_engine.current_index
        active_p = getattr(self.audio_engine, "_active_file_path", "")
        cur_path = (
            active_p
            if active_p
            else (
                self.audio_engine.playlist[cur_idx]
                if 0 <= cur_idx < len(self.audio_engine.playlist)
                else ""
            )
        )
        cur_norm = os.path.normcase(os.path.abspath(cur_path)) if cur_path else ""
        for r in range(self.list_tracks.count()):
            it = self.list_tracks.item(r)
            if not it:
                continue
            row_path = it.data(Qt.ItemDataRole.UserRole + 1) or ""
            orig_i = it.data(Qt.ItemDataRole.UserRole)
            if cur_norm and row_path:
                is_cur = os.path.normcase(os.path.abspath(row_path)) == cur_norm
            else:
                is_cur = (orig_i == cur_idx and orig_i >= 0)
            w = self.list_tracks.itemWidget(it)
            if w and hasattr(w, "set_current"):
                w.set_current(is_cur)
            if is_cur:
                self.list_tracks.setCurrentRow(r)

    def refresh_queue_ui(self):
        """Refreshes both local player queue UI and Party Sync room queue UI."""
        PlaylistPanelMixin.refresh_queue_ui(self)
        party_dlg = getattr(self, "_party_dialog", None)
        if party_dlg is not None and hasattr(party_dlg, "_on_queue_updated"):
            if hasattr(self, "party_sync") and self.party_sync:
                party_dlg._on_queue_updated(self.party_sync.party_queue)

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

        # 1. Local Queue Priority: If songs are queued, play the next in queue!
        while getattr(self.audio_engine, "queue", None):
            next_p = self.audio_engine.queue.pop(0)
            if not os.path.exists(next_p):
                continue
            if next_p in self.audio_engine.playlist:
                new_idx = self.audio_engine.playlist.index(next_p)
                self.audio_engine.play_index(new_idx, crossfade=crossfade)
            else:
                self.audio_engine.load_file(next_p, auto_play=True)
            self.sync_play_state()
            self.refresh_queue_ui()
            if hasattr(self, "save_settings"):
                self.save_settings()
            if hasattr(self, "party_sync") and self.party_sync.is_connected and self.party_sync.is_host:
                self._broadcast_party_track()
            return True

        if (
            getattr(self, "current_playlist", "") == "★ Random Mix"
            and hasattr(self, "radio_mix")
            and self.radio_mix
        ):
            self.radio_mix.request_next_track(auto_play=True)
            return True

        active_tracks = self.get_active_filtered_tracks()
        if not active_tracks:
            return False

        cur_idx = self.audio_engine.current_index
        cur_p = self.audio_engine.playlist[cur_idx] if 0 <= cur_idx < len(self.audio_engine.playlist) else None

        if self.audio_engine.shuffle:
            played_paths = {
                self.audio_engine.playlist[i]
                for i in getattr(self.audio_engine, "_played_indices", set())
                if 0 <= i < len(self.audio_engine.playlist)
            }
            unplayed = [
                p for p in active_tracks
                if p not in played_paths and (len(active_tracks) <= 1 or p != cur_p)
            ]
            if not unplayed:
                self.audio_engine._played_indices.clear()
                unplayed = [p for p in active_tracks if p != cur_p] or active_tracks
            next_p = random.choice(unplayed)
            if next_p in self.audio_engine.playlist:
                self.audio_engine._played_indices.add(self.audio_engine.playlist.index(next_p))
        else:
            if cur_p in active_tracks:
                pos = active_tracks.index(cur_p)
                next_p = active_tracks[(pos + 1) % len(active_tracks)]
            else:
                next_p = active_tracks[0]

        if next_p in self.audio_engine.playlist:
            new_idx = self.audio_engine.playlist.index(next_p)
            self.audio_engine.play_index(new_idx, crossfade=crossfade)
        else:
            self.audio_engine.load_file(next_p, auto_play=True)
        self.sync_play_state()
        if hasattr(self, "party_sync") and self.party_sync.is_connected and self.party_sync.is_host:
            self._broadcast_party_track()
        self.refresh_queue_ui()
        if hasattr(self, "save_settings"):
            self.save_settings()
        return True

    def on_next_clicked(self):
        self.play_next_track(crossfade=False, force_skip=True)
        if hasattr(self, "lbl_track_title"):
            self.lbl_track_title.trigger_symbol("forward")
        if self.overlay:
            self.overlay.trigger_skip_feedback("forward")

    # -------------------------------------------------------------
    # RANDOM MIX (ENDLESS RADIO) HANDLERS
    # -------------------------------------------------------------
    def _on_radio_status_changed(self, msg: str):
        if hasattr(self, "lbl_radio_status") and self.lbl_radio_status:
            self.lbl_radio_status.setText(msg)

    def _on_radio_track_ready(self, path: str, auto_play: bool):
        if not path or not os.path.exists(path):
            return
        if auto_play:
            self.radio_mix.record_played_radio_track(path)
            self.audio_engine.load_file(path, auto_play=True)
            self.sync_play_state()
            if hasattr(self, "party_sync") and self.party_sync.is_connected and self.party_sync.is_host:
                self._broadcast_party_track()
        if getattr(self, "current_playlist", "") == "★ Random Mix":
            self.populate_playlist_ui()

    def _on_radio_prefetch_ready(self, _path: str):
        if getattr(self, "current_playlist", "") == "★ Random Mix":
            self.populate_playlist_ui()

    def _on_radio_saved_permanently(self, new_path: str):
        if hasattr(self, "lbl_radio_status") and self.lbl_radio_status:
            self.lbl_radio_status.setText(f"Saved: {os.path.basename(new_path)}")
        if (
            getattr(self, "current_playlist", "") == "★ Random Mix"
            and hasattr(self, "list_tracks")
            and hasattr(self, "radio_mix")
            and self.radio_mix
        ):
            for r in range(self.list_tracks.count()):
                it = self.list_tracks.item(r)
                p_row = it.data(Qt.ItemDataRole.UserRole + 1) if it else ""
                if p_row and self.radio_mix.is_track_saved(p_row):
                    w = self.list_tracks.itemWidget(it)
                    if w is not None and hasattr(w, "set_saved"):
                        w.set_saved(True)
        elif hasattr(self, "populate_playlist_ui"):
            self.populate_playlist_ui()
        if hasattr(self, "save_settings"):
            self.save_settings()

    def save_radio_track_permanently(self, target_path: Optional[str] = None):
        if not hasattr(self, "radio_mix") or not self.radio_mix:
            return
        candidate = target_path
        if not candidate:
            cur_p = getattr(self.audio_engine, "_active_file_path", "")
            if cur_p and self.radio_mix.is_radio_cached_track(cur_p):
                candidate = cur_p
        if not candidate:
            cur_idx = self.audio_engine.current_index
            if 0 <= cur_idx < len(self.audio_engine.playlist):
                cur_p = self.audio_engine.playlist[cur_idx]
                if self.radio_mix.is_radio_cached_track(cur_p):
                    candidate = cur_p
        if not candidate and hasattr(self, "list_tracks"):
            it = self.list_tracks.currentItem()
            if it:
                p = it.data(Qt.ItemDataRole.UserRole + 1)
                if p and self.radio_mix.is_radio_cached_track(p):
                    candidate = p
        if not candidate:
            cached = self.radio_mix.get_cached_tracks()
            candidate = cached[0] if cached else None
        if not candidate:
            self._on_radio_status_changed("No cached Random Mix song to save.")
            return
        ok, msg = self.radio_mix.save_track_permanently(candidate)
        self._on_radio_status_changed(msg)
        if ok:
            self.sync_play_state()
            if self.overlay:
                self.overlay._trigger_click_feedback(
                    color=QColor(74, 222, 128), rot_degrees=2.2, alpha=0.72
                )
                self.overlay.osd_symbol = "saved"
                self.overlay.osd_title = f"Saved: {os.path.basename(candidate)}"
                self.overlay.osd_timer = 1.8
                self.overlay.update()

    def _show_radio_exclude_menu(self):
        from PyQt6.QtWidgets import QInputDialog
        from radio_mix import DEFAULT_EXCLUSIONS

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #14151e;
                color: #f4f4f5;
                border: 1px solid #5EF6FF;
                padding: 4px;
                border-radius: 3px;
            }
            QMenu::item {
                padding: 5px 14px;
            }
            QMenu::item:selected {
                background-color: rgba(247, 80, 73, 180);
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(247, 80, 73, 95);
                margin: 4px 8px;
            }
        """)

        for key, (label, _default) in DEFAULT_EXCLUSIONS.items():
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.radio_mix.exclusions.get(key, False))
            act.toggled.connect(
                lambda checked, k=key: (
                    self.radio_mix.toggle_exclusion(k, checked),
                    self.save_settings() if hasattr(self, "save_settings") else None,
                )
            )

        menu.addSeparator()
        artist_pool = list(
            dict.fromkeys(self.radio_mix.excluded_artists + self.radio_mix.recent_artists)
        )
        if artist_pool:
            sub_art = menu.addMenu("Exclude Artists")
            for artist in artist_pool[:12]:
                act_a = sub_art.addAction(artist)
                act_a.setCheckable(True)
                act_a.setChecked(self.radio_mix.is_artist_excluded(artist))
                act_a.toggled.connect(
                    lambda checked, a=artist: (
                        self.radio_mix.toggle_excluded_artist(a, checked),
                        self.save_settings() if hasattr(self, "save_settings") else None,
                    )
                )

        act_add_kw = menu.addAction("+ Add Artist / Keyword to Exclude...")
        act_clear_hist = menu.addAction("Reset Heard Track History")

        chosen = menu.exec(
            self.btn_radio_exclude.mapToGlobal(self.btn_radio_exclude.rect().bottomLeft())
        )
        if chosen == act_add_kw:
            kw, ok = QInputDialog.getText(
                self,
                "Exclude from Random Mix",
                "Artist name or keyword to exclude:",
            )
            if ok and kw.strip():
                self.radio_mix.toggle_excluded_artist(kw.strip(), True)
                self._on_radio_status_changed(f"Excluded: {kw.strip()}")
                if hasattr(self, "save_settings"):
                    self.save_settings()
        elif chosen == act_clear_hist:
            self.radio_mix.seen_video_ids.clear()
            self._on_radio_status_changed("Radio history cleared.")

    def on_prev_clicked(self):
        self._waiting_for_download_to_play = False
        self._party_downloading_track = None

        if (
            getattr(self, "current_playlist", "") == "★ Random Mix"
            and hasattr(self, "radio_mix")
            and self.radio_mix
        ):
            cur_p = getattr(self.audio_engine, "_active_file_path", "") or None
            prev_p = self.radio_mix.get_previous_track(cur_p)
            if prev_p and os.path.exists(prev_p):
                self.audio_engine.load_file(prev_p, auto_play=True)
                self.sync_play_state()
                self.populate_playlist_ui()
                return True
            self.radio_mix.request_next_track(auto_play=True)
            return True

        active_tracks = self.get_active_filtered_tracks()
        if not active_tracks:
            return

        cur_idx = self.audio_engine.current_index
        cur_p = self.audio_engine.playlist[cur_idx] if 0 <= cur_idx < len(self.audio_engine.playlist) else None

        if cur_p in active_tracks:
            pos = active_tracks.index(cur_p)
            prev_p = active_tracks[(pos - 1) % len(active_tracks)]
        else:
            prev_p = active_tracks[-1]

        if prev_p in self.audio_engine.playlist:
            new_idx = self.audio_engine.playlist.index(prev_p)
            self.audio_engine.play_index(new_idx)
        else:
            self.audio_engine.load_file(prev_p, auto_play=True)
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
        if hasattr(self, "controls_bar") and self.controls_bar:
            self.controls_bar.sync_state()

    def _on_track_selection_changed(self, current, previous):
        if current and current != previous:
            try:
                from cyber_sfx import get_cyber_sfx
                get_cyber_sfx().play_click()
            except Exception:
                pass

    def on_track_clicked(self, item):
        try:
            from cyber_sfx import get_cyber_sfx
            get_cyber_sfx().play_click()
        except Exception:
            pass

    def on_track_double_clicked(self, item):
        try:
            from cyber_sfx import get_cyber_sfx
            get_cyber_sfx().play_click()
        except Exception:
            pass
        self._waiting_for_download_to_play = False
        self._party_downloading_track = None
        orig_idx = item.data(Qt.ItemDataRole.UserRole)
        path = item.data(Qt.ItemDataRole.UserRole + 1)
        if path and hasattr(self.audio_engine, "queue") and path in self.audio_engine.queue:
            self.audio_engine.queue.remove(path)
            if hasattr(self, "save_settings"):
                self.save_settings()
        in_radio = (
            path
            and hasattr(self, "radio_mix")
            and self.radio_mix
            and (
                getattr(self, "current_playlist", "") == "★ Random Mix"
                or self.radio_mix.is_radio_cached_track(path)
            )
        )
        if in_radio and path and os.path.exists(path):
            self.radio_mix.select_radio_track(path)
            self.audio_engine.load_file(path, auto_play=True)
            if getattr(self, "current_playlist", "") == "★ Random Mix":
                self.populate_playlist_ui()
        elif orig_idx is not None and 0 <= orig_idx < len(self.audio_engine.playlist):
            self.audio_engine.play_index(orig_idx)
        elif path and os.path.exists(path):
            if path in self.audio_engine.playlist:
                self.audio_engine.play_index(self.audio_engine.playlist.index(path))
            else:
                self.audio_engine.load_file(path, auto_play=True)
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

    @staticmethod
    def _format_time_component(minutes: int) -> str:
        """Formats minute duration, switching to 'Xh Ym' past 60m."""
        if minutes < 60:
            return f"{minutes}m"
        h = minutes // 60
        m = minutes % 60
        return f"{h}h {m}m"

    @classmethod
    def _format_level_playtime(cls, exp: int, req: int) -> str:
        """Formats XP progress.
        Under 60m: 1/10m, 5/11m.
        At or past 60m: converts to hours and minutes (e.g. 1h 0m/1h 9m).
        """
        current_min = max(0, int(exp)) // 60
        total_min = max(1, (max(1, int(req)) + 59) // 60)
        if total_min < 60 and current_min < 60:
            return f"{current_min}/{total_min}m"
        return f"{cls._format_time_component(current_min)}/{cls._format_time_component(total_min)}"

    def _refresh_level_display(self):
        """Updates the header level display, XP bar, and playtime readout."""
        cum_req = get_cumulative_exp_for_level(self.level)
        base_exp = get_cumulative_exp_for_level(self.level - 1) if self.level > 0 else 0
        current_exp = max(getattr(self, "playtime_seconds", 0), base_exp + getattr(self, "exp", 0))
        if hasattr(self, "lbl_level_badge"):
            self.lbl_level_badge.setText(
                f"<span style=\"font-size:24px; font-family:'Share Tech Mono';\">{self.level}</span>"
                "<span style=\"font-size:10px; font-family:'Rajdhani'; font-weight:700;\">&nbsp;LEVEL</span>"
            )
        if hasattr(self, "lbl_exp_progress"):
            self.lbl_exp_progress.setText(self._format_level_playtime(current_exp, cum_req))
        if hasattr(self, "exp_bar"):
            self.exp_bar.setRange(0, max(1, cum_req))
            self.exp_bar.setValue(max(0, min(int(current_exp), cum_req)))

    def _push_discord_playback(self, pos: float, dur: float):
        """Send playback metadata and active mode context cleanly to Discord RPC."""
        if not (hasattr(self, "discord_service") and self.discord_service and self.discord_service.enabled):
            return
        if self.audio_engine.audio_mode == "desktop":
            self.discord_service.update_playback(
                "Desktop Audio",
                bool(self.audio_engine.is_playing),
                0.0,
                0.0,
                mode_hint="Desktop Audio",
            )
            return
        raw_title = self.audio_engine.get_current_track_title()
        is_playing = bool(self.audio_engine.is_playing and not self.audio_engine.is_paused)
        mode_hint = ""
        if hasattr(self, "party_sync") and self.party_sync.is_connected:
            mode_hint = f"Party {self.party_sync.room_code}" if self.party_sync.room_code else "Listen Together"
        elif getattr(self, "current_playlist", "") == "★ Random Mix":
            mode_hint = "Random Mix"
        self.discord_service.update_playback(raw_title, is_playing, pos, dur, mode_hint=mode_hint)

    def update_timeline(self):
        if self.is_user_scrubbing:
            return
        panel_visible = self.isVisible()
        audio_active = bool(self.audio_engine.is_playing and not self.audio_engine.is_paused)
        party_connected = bool(
            hasattr(self, "party_sync") and self.party_sync.is_connected and self.party_sync.is_host
        )
        if not panel_visible and not audio_active and not party_connected:
            return

        pos = self.audio_engine.get_position()
        dur = self.audio_engine.get_duration()
        if panel_visible:
            if self.audio_engine.audio_mode == "desktop":
                self.lbl_time_cur.setText("LIVE")
                self.lbl_time_dur.setText("LOOP")
                self.slider_seek.setValue(1000)
            else:
                if dur > 0:
                    self.slider_seek.setValue(int((pos / dur) * 1000))
                else:
                    self.slider_seek.setValue(0)
                m_pos, s_pos = int(pos // 60), int(pos % 60)
                m_dur, s_dur = int(dur // 60), int(dur % 60)
                self.lbl_time_cur.setText(f"{m_pos:02d}:{s_pos:02d}")
                self.lbl_time_dur.setText(f"{m_dur:02d}:{s_dur:02d}")

        # Active Playtime & EXP progression tracking (every 1s while actively playing)
        if audio_active:
            now = time.time()
            if now - getattr(self, "_last_exp_tick", 0.0) >= 1.0:
                self._last_exp_tick = now
                lvl, exp, total, _req, leveled_up = apply_playtime_exp(
                    self.level, self.exp, self.playtime_seconds, 1
                )
                self.level, self.exp, self.playtime_seconds = lvl, exp, total
                if panel_visible or leveled_up:
                    self._refresh_level_display()
                if leveled_up:
                    try:
                        from cyber_sfx import get_cyber_sfx
                        get_cyber_sfx().play_level_up()
                    except Exception:
                        pass
                if leveled_up or now - getattr(self, "_last_exp_save", now) >= 60.0:
                    self._last_exp_save = now
                    self.save_settings()

        if party_connected:
            now = time.time()
            if now - getattr(self, "_last_party_heartbeat", 0.0) >= 3.0:
                self._last_party_heartbeat = now
                self.party_sync.broadcast_heartbeat(pos, self.audio_engine.is_playing)

        if (
            audio_active
            and hasattr(self, "discord_service")
            and self.discord_service
            and self.discord_service.enabled
        ):
            now = time.time()
            if now - getattr(self, "_last_discord_update", 0.0) >= 4.0:
                self._last_discord_update = now
                self._push_discord_playback(pos, dur)

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
                and (
                    len(self.audio_engine.playlist) > 1
                    or bool(getattr(self.audio_engine, "queue", None))
                    or (hasattr(self, "party_sync") and self.party_sync.is_connected and self.party_sync.party_queue)
                    or (
                        getattr(self, "current_playlist", "") == "★ Random Mix"
                        and hasattr(self, "radio_mix")
                        and self.radio_mix
                        and bool(self.radio_mix.prefetch_queue or self.radio_mix.get_next_played_track(getattr(self.audio_engine, "_active_file_path", "")))
                    )
                )
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
        """Monitors Ctrl+[ / Ctrl+] lyric offset hotkeys with minimal Win32 calls."""
        if not (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000):
            self.last_bracket_left_state = False
            self.last_bracket_right_state = False
            return
        bracket_l = bool(user32.GetAsyncKeyState(VK_OEM_4) & 0x8000)
        if bracket_l and not self.last_bracket_left_state:
            self.adjust_lyrics_offset(-0.25)
        self.last_bracket_left_state = bracket_l
        bracket_r = bool(user32.GetAsyncKeyState(VK_OEM_6) & 0x8000)
        if bracket_r and not self.last_bracket_right_state:
            self.adjust_lyrics_offset(0.25)
        self.last_bracket_right_state = bracket_r

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
                eco_btn = self.settings_dialog.btn_eco
                eco_btn.setText("Eco Mode: On")
                eco_btn.setProperty("role", "success")
                if eco_btn.style():
                    eco_btn.style().unpolish(eco_btn)
                    eco_btn.style().polish(eco_btn)
            log.info("[STATUS] Eco Mode enabled (< 1% CPU).")
        else:
            self.hotkey_timer.setInterval(50)
            self.timeline_timer.setInterval(200)
            if hasattr(self, "btn_eco"):
                self.btn_eco.setText("Eco Mode: Off")
                self.btn_eco.setStyleSheet("")
            if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "btn_eco"):
                eco_btn = self.settings_dialog.btn_eco
                eco_btn.setText("Eco Mode: Off")
                eco_btn.setProperty("role", None)
                if eco_btn.style():
                    eco_btn.style().unpolish(eco_btn)
                    eco_btn.style().polish(eco_btn)
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

    def on_subtitle_bg_toggled(self, checked: bool):
        if self.lyrics_overlay:
            self.lyrics_overlay.set_subtitle_bg_enabled(checked)
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
            if hasattr(self.btn_pick_color, "set_custom_tint"):
                self.btn_pick_color.set_custom_tint(hex_code)
            else:
                self.btn_pick_color.setStyleSheet(
                    f"background-color: #27272a; color: {hex_code}; border: 1px solid {hex_code}; font-weight: 500;"
                )

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
        """Open the integrated in-app Lyrics & Calibration Studio."""
        if not isinstance(track_path, str):
            track_path = None
        try:
            from lyrics_studio_dialog import LyricsStudioDialog

            if not hasattr(self, "_lyrics_fetcher_win") or self._lyrics_fetcher_win is None:
                self._lyrics_fetcher_win = LyricsStudioDialog(self)
                self._lyrics_fetcher_win.lyrics_saved.connect(self._on_lyrics_saved_externally)
            elif hasattr(self._lyrics_fetcher_win, "refresh_track_list"):
                self._lyrics_fetcher_win.refresh_track_list()

            # Auto-select the target track (or currently playing track) for instant calibration
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
                self._lyrics_fetcher_win.tabs.setCurrentIndex(0)

            self._lyrics_fetcher_win.show()
            self._lyrics_fetcher_win.raise_()
            self._lyrics_fetcher_win.activateWindow()
            log.info(f"[ACTION] Opened Lyrics & Calibration Studio (target track: {curr_track}).")
        except Exception as e:
            log.info(f"[ERROR] In-process lyrics studio launch failed: {e}")

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

    def _init_tray_icon(self):
        """Initializes system tray icon in Windows notification area (hidden icons)."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = None
            return

        icon = QIcon(ICON_PATH) if os.path.exists(ICON_PATH) else self.windowIcon()
        self.tray_icon = QSystemTrayIcon(icon, self)
        from config import APP_VERSION
        self.tray_icon.setToolTip(f"Talia v{APP_VERSION} - Cyberpunk Music Player")

        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu {
                background-color: #121215;
                color: #f4f4f5;
                border: 1px solid #F75049;
                padding: 4px;
                font-family: 'Rajdhani', sans-serif;
                font-weight: 600;
                font-size: 12px;
            }
            QMenu::item {
                padding: 5px 20px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: #F75049;
                color: #0e0e17;
            }
            QMenu::separator {
                height: 1px;
                background-color: #3f3f46;
                margin: 4px 8px;
            }
        """)

        act_toggle = tray_menu.addAction("Show / Hide Talia")
        act_toggle.triggered.connect(self.toggle_visibility)

        act_panel = tray_menu.addAction("Playlist & Controls")
        act_panel.triggered.connect(self.toggle_slide_panel)

        tray_menu.addSeparator()

        act_play = tray_menu.addAction("Play / Pause")
        act_play.triggered.connect(self.on_play_pause_clicked)

        act_next = tray_menu.addAction("Next Track")
        act_next.triggered.connect(self.on_next_clicked)

        act_prev = tray_menu.addAction("Previous Track")
        act_prev.triggered.connect(self.on_prev_clicked)

        tray_menu.addSeparator()

        act_party = tray_menu.addAction("Listen Together (Party Sync)")
        act_party.triggered.connect(self.open_party_dialog)

        act_spotify = tray_menu.addAction("Spotify Playlist Sync")
        act_spotify.triggered.connect(self.open_spotify_dialog)

        act_settings = tray_menu.addAction("Advanced Settings")
        act_settings.triggered.connect(self.open_settings_window)

        tray_menu.addSeparator()

        act_exit = tray_menu.addAction("Exit Talia")
        act_exit.triggered.connect(self.exit_application)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_icon_activated)
        self.tray_icon.show()

    def _on_tray_icon_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.toggle_visibility()

    def exit_application(self):
        try:
            self.save_settings_action()
        except Exception:
            pass
        if self.overlay:
            self.overlay.close_application()
        else:
            QApplication.quit()

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
            "level": max(0, int(getattr(self, "level", 0))),
            "exp": max(0, int(getattr(self, "exp", 0))),
            "playtime_seconds": max(0, int(getattr(self, "playtime_seconds", 0))),
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
            settings_dict["show_subtitle_bg"] = bool(
                getattr(self.lyrics_overlay, "show_subtitle_bg", False)
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
        settings_dict["play_counts"] = dict(getattr(self, "play_counts", {}))
        settings_dict["favourite_tracks"] = list(getattr(self, "favourite_tracks", []))
        settings_dict["custom_playlists"] = dict(getattr(self, "custom_playlists", {}))
        settings_dict["current_playlist"] = str(getattr(self, "current_playlist", "All Tracks"))
        settings_dict["current_sort"] = str(getattr(self, "current_sort", "Default"))
        if hasattr(self, "radio_mix") and self.radio_mix:
            settings_dict.update(self.radio_mix.export_state())
        return settings_dict

    def apply_settings(self, cfg: dict):
        # Apply settings to overlay and controls
        self.is_loading_settings = True
        self.show_startup_guide = bool(cfg.get("show_startup_guide", True))

        # Level / XP state (never reset when a song changes or settings reload)
        self.level = max(0, int(cfg.get("level", self.level)))
        self.exp = max(0, int(cfg.get("exp", self.exp)))
        self.playtime_seconds = max(
            0, int(cfg.get("playtime_seconds", self.playtime_seconds))
        )
        self._refresh_level_display()

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
        head_bop_on = bool(cfg.get("head_bop", False))
        self.overlay.enable_head_bop = head_bop_on
        if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "chk_head_bop"):
            self.settings_dialog.chk_head_bop.blockSignals(True)
            self.settings_dialog.chk_head_bop.setChecked(head_bop_on)
            self.settings_dialog.chk_head_bop.blockSignals(False)
        discord_on = bool(cfg.get("discord_rpc", True))
        self._discord_rpc_enabled = discord_on
        if hasattr(self, "settings_dialog") and hasattr(self.settings_dialog, "chk_discord_rpc"):
            self.settings_dialog.chk_discord_rpc.blockSignals(True)
            self.settings_dialog.chk_discord_rpc.setChecked(discord_on)
            self.settings_dialog.chk_discord_rpc.blockSignals(False)
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

            subtitle_bg = bool(cfg.get("show_subtitle_bg", True))
            self.lyrics_overlay.set_subtitle_bg_enabled(subtitle_bg)
            chk_sub = getattr(self, "chk_subtitle_bg", None) or (
                getattr(self.settings_dialog, "chk_subtitle_bg", None)
                if hasattr(self, "settings_dialog")
                else None
            )
            if chk_sub:
                chk_sub.blockSignals(True)
                chk_sub.setChecked(subtitle_bg)
                chk_sub.blockSignals(False)

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

        # Play counts, favourites, playlists, and sort
        self.play_counts = dict(cfg.get("play_counts", {}))
        self.favourite_tracks = set(cfg.get("favourite_tracks", []))
        self.custom_playlists = dict(cfg.get("custom_playlists", {}))
        self.current_playlist = str(cfg.get("current_playlist", "All Tracks"))
        self.current_sort = str(cfg.get("current_sort", "Default"))
        if hasattr(self, "radio_mix") and self.radio_mix:
            self.radio_mix.load_state(cfg)
            self.radio_mix.restore_from_cache()
        if hasattr(self, "radio_mix_bar") and self.radio_mix_bar is not None:
            self.radio_mix_bar.setVisible(self.current_playlist == "★ Random Mix")
        if hasattr(self, "refresh_playlist_dropdown"):
            self.refresh_playlist_dropdown()
        if hasattr(self, "combo_sort"):
            idx_s = self.combo_sort.findText(self.current_sort)
            if idx_s >= 0:
                self.combo_sort.blockSignals(True)
                self.combo_sort.setCurrentIndex(idx_s)
                self.combo_sort.blockSignals(False)

        if self.current_playlist == "★ Random Mix" or not getattr(self, "_defer_initial_populate", False):
            self._defer_initial_populate = False
            self.populate_playlist_ui()

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
        if getattr(self, "_defer_initial_populate", False):
            self._defer_initial_populate = False
            self.populate_playlist_ui()
        self._update_download_badge_position()
        if hasattr(self, "download_status_badge") and self.download_status_badge.isVisible():
            self.download_status_badge.raise_()
        if hasattr(self, "controls_bar") and not self.controls_bar.isVisible():
            _, _, _, ctrl_target = self.calculate_slide_geometries()
            self.controls_bar.setGeometry(ctrl_target)
            self.controls_bar.show()
            self.controls_bar.raise_()
            self.controls_bar.sync_state()
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
        if hasattr(self, "controls_bar") and self.controls_bar.isVisible():
            self.controls_bar.hide()
        if hasattr(self, "timeline_timer"):
            self.timeline_timer.setInterval(900)
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
        if getattr(self, "_party_dialog", None) is not None and self._party_dialog.isVisible():
            self._party_dialog.hide()
        if getattr(self, "_spotify_dialog", None) is not None and self._spotify_dialog.isVisible():
            self._spotify_dialog.hide()
        if (
            hasattr(self, "_lyrics_fetcher_win")
            and self._lyrics_fetcher_win is not None
            and self._lyrics_fetcher_win.isVisible()
        ):
            self._lyrics_fetcher_win.hide()
        self.hide()
        if (
            self.overlay
            and hasattr(self.overlay, "sound_menu_close")
            and self.overlay.sound_menu_close.isLoaded()
        ):
            self.overlay.sound_menu_close.play()
        trim_process_memory()
        event.ignore()

    def _position_popup_dialog(self, dlg: QWidget):
        """Positions popup dialog adjacent to the slide-out control panel or centered."""
        try:
            screen_obj = self.screen() if hasattr(self, "screen") and self.screen() else (
                QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
            )
            screen = screen_obj.availableGeometry() if screen_obj else QRect(0, 0, 1920, 1080)
            dlg_w = dlg.width()
            dlg_h = dlg.height()

            if self.isVisible() and not getattr(self, "is_animating", False):
                panel_geo = self.geometry()
                margin = 10
                target_x = panel_geo.left() - dlg_w - margin
                if target_x < screen.left() + 10:
                    target_x = panel_geo.right() + margin
                    if target_x + dlg_w > screen.right() - 10:
                        target_x = screen.left() + max(10, (screen.width() - dlg_w) // 2)

                target_y = max(screen.top() + 10, min(panel_geo.top(), screen.bottom() - dlg_h - 10))
                dlg._custom_positioned = True
                dlg.move(target_x, target_y)
            else:
                dlg._custom_positioned = False
                if hasattr(dlg, "center_and_clamp_on_screen"):
                    dlg.center_and_clamp_on_screen()
        except Exception as exc:
            log.warning("Could not position popup dialog: %s", exc)

    def _toggle_tool_dialog(self, dialog, sibling):
        """Uniform open/close/hide toggle for Party Sync and Spotify Sync popups."""
        if dialog.isVisible():
            try:
                from cyber_sfx import get_cyber_sfx
                get_cyber_sfx().play_close()
            except Exception:
                pass
            dialog.hide()
            return
        if sibling is not None and sibling.isVisible():
            sibling.hide()
        try:
            from cyber_sfx import get_cyber_sfx
            get_cyber_sfx().play_open()
        except Exception:
            pass
        self._position_popup_dialog(dialog)
        if dialog.isMinimized():
            dialog.showNormal()
        else:
            dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def open_party_dialog(self):
        self._toggle_tool_dialog(self.party_dialog, getattr(self, "_spotify_dialog", None))

    def open_spotify_dialog(self):
        self._toggle_tool_dialog(self.spotify_dialog, getattr(self, "_party_dialog", None))

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

        STOP_WORDS = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "in", "on", "at", "to",
            "for", "from", "of", "by", "with", "and", "or", "my", "your", "his", "her", "our",
            "their", "its", "i", "me", "we", "us", "you", "he", "him", "she", "it", "they", "them",
            "where", "what", "when", "why", "how", "who", "all", "this", "that", "so", "no", "not"
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

            # Mandatory Title Verification:
            # If the candidate has an identifiable title, it MUST match the query's title.
            # Matching the artist alone must NEVER match a different song by the same artist!
            has_title_cand = bool(norm_c_title or cand_t_tokens)
            if has_title_cand:
                # Content tokens (keywords minus grammatical stopwords)
                tt_content = {w for w in title_tokens if w not in STOP_WORDS}
                ct_content = {w for w in cand_t_tokens if w not in STOP_WORDS}
                q_content = {w for w in query_tokens if w not in STOP_WORDS}

                # If both titles contain meaningful content keywords, they MUST share at least one keyword!
                # E.g. 'where is my husband' (keyword: husband) must never match 'where is my mind' (keyword: mind)
                if tt_content and ct_content and not (tt_content & ct_content):
                    return 0
                if ct_content and q_content and not (ct_content & q_content):
                    return 0

                exact_t = bool(norm_target_title and norm_c_title and norm_target_title == norm_c_title)
                exact_yq = bool(norm_yt_query and norm_c_title and (norm_yt_query == norm_c_title or (len(norm_c_title) >= 5 and norm_c_title in norm_yt_query)))
                sub_t = bool(norm_target_title and norm_c_title and len(norm_target_title) >= 5 and len(norm_c_title) >= 5 and (norm_target_title in norm_c_title or norm_c_title in norm_target_title))
                token_t_equal = bool(title_tokens and cand_t_tokens and title_tokens == cand_t_tokens)
                token_t_subset = bool(cand_t_tokens and (cand_t_tokens.issubset(title_tokens) or cand_t_tokens.issubset(query_tokens)))
                token_t_ratio = False
                if title_tokens and cand_t_tokens:
                    comm_t = title_tokens & cand_t_tokens
                    token_t_ratio = (len(comm_t) / max(len(title_tokens), len(cand_t_tokens))) >= 0.65

                if not (exact_t or exact_yq or sub_t or token_t_equal or token_t_subset or token_t_ratio):
                    return 0

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

    def on_filter_results_changed(self, query: str, matched: int):
        """Called by PlaylistPanelMixin.filter_tracks when search results change."""
        if not hasattr(self, "yt_download_card"):
            return
        if query and matched == 0:
            raw_q = self.search_input.text().strip()
            self.lbl_yt_prompt.setText(f"No local song detected matching '{raw_q}'.")
            self.lbl_yt_prompt.setStyleSheet("color: #fca5a5; font-size: 11px; font-weight: 500;")
            self.btn_yt_download.setText(f"Download '{raw_q}' from YouTube")
            self.btn_yt_download.setEnabled(True)
            self.yt_download_card.show()
        else:
            if not getattr(self, "_is_downloading_yt_search", False):
                self.yt_download_card.hide()

    def on_search_return_pressed(self):
        """Pressing Enter in search bar: plays first visible match, or downloads from YouTube if none."""
        query = self.search_input.text().strip()
        if not query:
            return
        first_visible = None
        for i in range(self.list_tracks.count()):
            item = self.list_tracks.item(i)
            if item and not item.isHidden():
                first_visible = item
                break
        if first_visible:
            self.on_track_double_clicked(first_visible)
        else:
            self.on_yt_prompt_download_clicked()

    def _on_yt_search_progress_safe(self, msg: str):
        """Thread-safe UI updater for YouTube search download progress."""
        if hasattr(self, "lbl_yt_prompt"):
            self.lbl_yt_prompt.setText(msg)
        if hasattr(self, "show_download_status"):
            self.show_download_status(msg)

    def on_yt_prompt_download_clicked(self):
        """Downloads the searched song directly from YouTube into Downloaded Songs folder."""
        query = self.search_input.text().strip()
        if not query:
            return
        music_dir = self.audio_engine.folder_path or os.path.join(PROJECT_ROOT, "music")
        target_dir = os.path.join(music_dir, "Downloaded Songs")
        os.makedirs(target_dir, exist_ok=True)

        self._is_downloading_yt_search = True
        self.lbl_yt_prompt.setText(f"Searching and downloading '{query}' from YouTube...")
        self.lbl_yt_prompt.setStyleSheet("color: #38bdf8; font-size: 11px;")
        self.btn_yt_download.setEnabled(False)
        self.btn_yt_download.setText("Downloading...")
        self.show_download_status(f"Downloading '{query}'...")

        def _on_progress(msg: str):
            self.yt_search_progress.emit(msg)

        def _worker():
            ok = False
            final_p = ""
            try:
                if hasattr(self, "downloader") and self.downloader:
                    ok, final_p = self.downloader.download_sync_query(
                        query,
                        target_dir,
                        progress_cb=_on_progress,
                        return_path=True,
                    )
            except Exception as e:
                log.warning("[DOWNLOAD] Error during yt search download: %s", e)
            finally:
                self.yt_search_done.emit(ok, final_p, query)

        threading.Thread(target=_worker, daemon=True, name="YtSearchWorker").start()

    def _on_yt_search_download_done(self, ok: bool, file_path: str, query: str):
        self._is_downloading_yt_search = False
        if ok and file_path and os.path.exists(file_path):
            fn = os.path.basename(file_path)
            self.lbl_yt_prompt.setText(f"Downloaded '{fn}' to Downloaded Songs folder!")
            self.lbl_yt_prompt.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
            self.btn_yt_download.setText("Downloaded!")
            self.btn_yt_download.setEnabled(False)
            self.show_download_status(f"Downloaded: {fn}", is_done=True)

            # Clear search input so user sees the newly downloaded song in track list immediately
            self.search_input.blockSignals(True)
            self.search_input.clear()
            self.search_input.blockSignals(False)

            self.audio_engine.refresh_playlist()
            self.refresh_tracklist()
            self.populate_playlist_ui()

            norm = os.path.normpath(file_path)
            for r in range(self.list_tracks.count()):
                it = self.list_tracks.item(r)
                if it and os.path.normpath(it.data(Qt.ItemDataRole.UserRole + 1) or "") == norm:
                    self.list_tracks.setCurrentRow(r)
                    self.list_tracks.scrollToItem(it)
                    break

            # Auto-hide the download prompt card after 3.5s so the UI returns to normal
            QTimer.singleShot(3500, lambda: self.yt_download_card.hide() if not getattr(self, "_is_downloading_yt_search", False) else None)
        else:
            self.lbl_yt_prompt.setText(f"Could not download '{query}' from YouTube.")
            self.lbl_yt_prompt.setStyleSheet("color: #f87171; font-size: 11px;")
            self.btn_yt_download.setEnabled(True)
            self.btn_yt_download.setText("Retry Download")
            self.show_download_status(f"Could not download '{query}'", is_error=True)
