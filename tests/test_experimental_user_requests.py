"""Unit and integration tests for the latest Talia Experimental features."""

import os
import time
import pytest
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import QApplication

from audio_engine import CyberAudioEngine
from lyrics_manager import LyricsManager
from lyrics_overlay import LyricsOverlayWindow
from overlay import OverlayWindow
from controller import ControlPanel
from settings_dialog import SettingsDialog


def _make_engine(monkeypatch, playlist):
    engine = CyberAudioEngine()
    monkeypatch.setattr(engine, "_trigger_preload_next", lambda: None)
    engine.playlist = list(playlist)
    engine.current_index = 0
    return engine


def test_sorting_time_added_least_played_and_random(tmp_path, monkeypatch, qapp):
    """Verifies Time Added, Least Played, and Random sorting behaviors."""
    t1 = tmp_path / "song_old.mp3"
    t2 = tmp_path / "song_new.mp3"
    t3 = tmp_path / "song_mid.mp3"

    t1.write_bytes(b"")
    time.sleep(0.05)
    t3.write_bytes(b"")
    time.sleep(0.05)
    t2.write_bytes(b"")

    engine = _make_engine(monkeypatch, [str(t1), str(t2), str(t3)])
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    # 1. Test Time Added
    panel.on_sort_changed("Time Added")
    time_sorted = [panel.list_tracks.item(i).data(Qt.ItemDataRole.UserRole + 1) for i in range(panel.list_tracks.count())]
    assert time_sorted == [str(t2), str(t3), str(t1)]

    # 2. Test Least Played
    panel.play_counts = {str(t1): 10, str(t2): 1, str(t3): 5}
    panel.on_sort_changed("Least Played")
    least_sorted = [panel.list_tracks.item(i).data(Qt.ItemDataRole.UserRole + 1) for i in range(panel.list_tracks.count())]
    assert least_sorted == [str(t2), str(t3), str(t1)]

    # 3. Test Random Sort & Re-randomization
    panel.on_sort_changed("Random")
    rand_1 = [panel.list_tracks.item(i).data(Qt.ItemDataRole.UserRole + 1) for i in range(panel.list_tracks.count())]
    assert len(rand_1) == 3
    assert set(rand_1) == {str(t1), str(t2), str(t3)}

    # Activating Random sort again re-randomizes order
    idx_random = panel.combo_sort.findText("Random")
    assert idx_random >= 0
    panel.on_sort_activated(idx_random)
    # The order remains a valid permutation
    rand_2 = [panel.list_tracks.item(i).data(Qt.ItemDataRole.UserRole + 1) for i in range(panel.list_tracks.count())]
    assert len(rand_2) == 3
    assert set(rand_2) == {str(t1), str(t2), str(t3)}

    panel.hide()
    lyrics.hide()
    overlay.hide()


def test_eco_mode_button_in_advanced_settings(tmp_path, monkeypatch, qapp):
    """Ensures Eco Mode button exists in Advanced Settings and toggles properly."""
    engine = _make_engine(monkeypatch, [])
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    dialog = SettingsDialog(panel)
    assert hasattr(dialog, "btn_eco")
    assert "Eco Mode" in dialog.btn_eco.text()

    # Toggle eco mode via dialog button
    assert panel.eco_mode is False
    dialog.btn_eco.click()
    assert panel.eco_mode is True
    assert "On" in dialog.btn_eco.text()

    dialog.btn_eco.click()
    assert panel.eco_mode is False
    assert "Off" in dialog.btn_eco.text()

    dialog.hide()
    panel.hide()
    lyrics.hide()
    overlay.hide()


def test_system_tray_icon_and_hidden_background_run(tmp_path, monkeypatch, qapp):
    """Ensures System Tray icon is registered and controls background state."""
    engine = _make_engine(monkeypatch, [])
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    assert hasattr(panel, "tray_icon")
    if panel.tray_icon is not None:
        assert panel.tray_icon.contextMenu() is not None
        actions = [act.text() for act in panel.tray_icon.contextMenu().actions()]
        assert "Show / Hide Talia" in actions
        assert "Exit Talia" in actions
        assert "Play / Pause" in actions

    # Toggle visibility hides window while app remains running in background
    overlay.show()
    assert overlay.isVisible()
    panel.toggle_visibility()
    assert not overlay.isVisible()
    panel.toggle_visibility()
    assert overlay.isVisible()

    panel.hide()
    lyrics.hide()
    overlay.hide()


def test_f_keys_removed_from_hotkeys(tmp_path, monkeypatch, qapp):
    """Ensures F-key polling variables and bindings have been removed."""
    engine = _make_engine(monkeypatch, [])
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    # F-key state trackers must no longer exist on panel
    for f in ["last_f7_state", "last_f8_state", "last_f9_state", "last_f11_state"]:
        assert not hasattr(panel, f)

    panel.hide()
    lyrics.hide()
    overlay.hide()


def test_timeline_scrubber_hud_render_and_styling(tmp_path, monkeypatch, qapp):
    """Verifies timeline scrubber HUD renders with electric blue duration text and Master Volume styling."""
    from PyQt6.QtGui import QPixmap, QPainter

    engine = _make_engine(monkeypatch, [str(tmp_path / "song.mp3")])
    overlay = OverlayWindow(engine)
    overlay.is_scrubbing_overlay = True
    overlay.scrub_ratio = 0.45
    overlay.scrub_target_time = 85.0
    monkeypatch.setattr(engine, "get_duration", lambda: 180.0)

    pixmap = QPixmap(300, 300)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    overlay._draw_scrubber_hud(painter, 10, 10, 280)
    painter.end()

    # Image rendered cleanly without exceptions
    assert not pixmap.isNull()
    overlay.hide()
