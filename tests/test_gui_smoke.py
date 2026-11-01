"""Headless GUI smoke tests (Qt offscreen)."""

import pytest
from PyQt6.QtGui import QImage, QPainter

from audio_engine import CyberAudioEngine
from controller import ControlPanel
from download_panel import DownloadPanelMixin
from lyrics_manager import LyricsManager
from lyrics_overlay import LyricsOverlayWindow
from overlay import OverlayWindow
from playlist_panel import PlaylistPanelMixin
from settings_dialog import SettingsDialog


@pytest.mark.gui
def test_window_stack_constructs(qapp):
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    assert isinstance(panel, PlaylistPanelMixin)
    assert isinstance(panel, DownloadPanelMixin)
    assert isinstance(panel.settings_dialog, SettingsDialog)
    assert hasattr(panel, "populate_playlist_ui")
    assert hasattr(panel, "on_dl_search_clicked")

    panel.hide()
    lyrics.hide()
    overlay.hide()


@pytest.mark.gui
def test_full_line_lyrics_render_does_not_raise(qapp):
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    image = QImage(400, 120, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        lyrics._draw_full_line(painter, "Cyberpunk test line", 1.0)
    finally:
        painter.end()
    lyrics.hide()


@pytest.mark.gui
def test_settings_dialog_exposes_all_sections(qapp):
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)
    dialog = SettingsDialog(panel)

    assert dialog.combo_mode.count() == 4
    assert dialog.combo_theme.count() == 4
    dialog.hide()
    panel.hide()
    lyrics.hide()
    overlay.hide()
