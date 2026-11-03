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


@pytest.mark.gui
def test_cyberpunk_dialogue_subtitles_and_expanded_width(qapp, monkeypatch):
    """Verifies Cyberpunk 2077 dialogue subtitle mode and 20% expanded box width."""
    engine = CyberAudioEngine()
    engine.playlist = [r"C:\Music\Rosa Walton - I Really Want to Stay At Your House.flac"]
    engine.current_index = 0
    engine.is_playing = True

    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    # 1. Verify 20% expanded box width
    lyrics.set_font_size(25)
    # 25 * 28 = 700px (previously was 25 * 23 = 575px, 700 / 575 = +21.7%)
    assert lyrics.width() >= 690, f"Expected expanded width >= 690, got {lyrics.width()}"

    # 2. Verify dialogue mode default and artist extraction
    assert lyrics.dialogue_mode is True
    artist = lyrics.get_current_artist()
    assert artist == "Rosa Walton", f"Expected 'Rosa Walton', got '{artist}'"

    # 3. Verify render execution with dialogue speaker
    lyrics.displayed_text = "I couldn't wait for you to come clear the cupboards"
    lyrics.line_opacity = 1.0
    lyrics.line_progress = 0.5

    image = QImage(lyrics.width(), lyrics.height(), QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        lyrics._draw_full_line(painter, lyrics.displayed_text, 1.0)
    finally:
        painter.end()

    # 4. Verify dialogue toggle
    panel.on_dialogue_mode_toggled(False)
    assert lyrics.dialogue_mode is False
    panel.on_dialogue_mode_toggled(True)
    assert lyrics.dialogue_mode is True

    panel.settings_dialog.hide()
    panel.hide()
    lyrics.hide()
    overlay.hide()


def test_cyberpunk_blue_preset_and_box_width(qapp):
    from audio_engine import CyberAudioEngine
    from controller import ControlPanel
    from lyrics_manager import LyricsManager
    from lyrics_overlay import LyricsOverlayWindow
    from overlay import OverlayWindow

    engine = CyberAudioEngine()
    mgr = LyricsManager()
    lyrics = LyricsOverlayWindow(engine, mgr)
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    # 1. Preset verification
    assert "Cyberpunk Blue" in panel.lyric_presets
    assert panel.lyric_presets["Cyberpunk Blue"] == "#64f0f8"
    assert "Electric Cyan" in panel.lyric_presets
    assert "Soft Blue" not in panel.lyric_presets

    # 2. Lyric box dimensions (+40% expansion verification)
    lyrics.base_font_size = 25
    lyrics._update_window_dimensions(keep_center=False)
    # 25 * 51.0 = 1275 px width (bounded by screen width - 40, minimum 917)
    screen = lyrics.screen()
    expected_w = min((screen.geometry().width() - 40) if screen else 1880, max(917, int(25 * 51.0)))
    assert lyrics.width() >= 760  # bounded by offscreen screen width (800 - 40)
    assert lyrics.width() == expected_w

    panel.hide()
    lyrics.hide()
    overlay.hide()
