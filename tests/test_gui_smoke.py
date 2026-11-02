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


@pytest.mark.gui
def test_lyrics_font_sizing_and_wheel(qapp):
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QWheelEvent
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    assert panel.settings_dialog.slider_lyric_size.value() == 25
    assert panel.settings_dialog.slider_lyric_size.minimum() == 14
    assert panel.settings_dialog.slider_lyric_size.maximum() == 60

    # Test slider change
    panel.settings_dialog.slider_lyric_size.setValue(32)
    assert lyrics.base_font_size == 32
    assert "32 pt" in panel.lbl_lyric_size_val.text()

    # Test set_font_size directly
    lyrics.set_font_size(40)
    assert lyrics.base_font_size == 40

    # Test wheel event in move mode
    lyrics.set_move_mode(True)
    assert lyrics.move_mode is True

    # Wheel up (+120 delta)
    wheel_up = QWheelEvent(
        QPointF(50, 50),
        QPointF(50, 50),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    lyrics.wheelEvent(wheel_up)
    assert lyrics.base_font_size == 42
    assert panel.slider_lyric_size.value() == 42

    # Wheel down (-120 delta)
    wheel_down = QWheelEvent(
        QPointF(50, 50),
        QPointF(50, 50),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    lyrics.wheelEvent(wheel_down)
    assert lyrics.base_font_size == 40
    assert panel.slider_lyric_size.value() == 40

    lyrics.set_move_mode(False)
    panel.settings_dialog.hide()
    panel.hide()
    lyrics.hide()
    overlay.hide()
