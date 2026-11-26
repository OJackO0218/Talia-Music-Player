"""Tests for Subtitle Shadow Box, Hold-to-Drag Move Mode, Sinking Shutdown, and Playback Controls."""

import time
import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QImage, QPainter

from audio_engine import CyberAudioEngine
from controller import ControlPanel
from lyrics_manager import LyricsManager
from lyrics_overlay import LyricsOverlayWindow
from overlay import BUTTON_STRIP_H, OverlayWindow
from settings_dialog import SettingsDialog


@pytest.mark.gui
def test_subtitle_shadow_box(qapp):
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())

    # Default is now True (On)
    assert lyrics.show_subtitle_bg is True
    assert lyrics.subtitle_bg_opacity == 0.40

    lyrics.set_subtitle_bg_enabled(False)
    assert lyrics.show_subtitle_bg is False

    lyrics.set_subtitle_bg_enabled(True)
    assert lyrics.show_subtitle_bg is True
    lyrics.set_subtitle_bg_opacity(0.65)
    assert lyrics.subtitle_bg_opacity == 0.65

    # Drawing with background box enabled should not raise any exceptions
    image = QImage(500, 150, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        lyrics._draw_full_line(painter, "Night City Cyberpunk Lyrics Line", 1.0)
    finally:
        painter.end()

    lyrics.hide()


@pytest.mark.gui
def test_transport_buttons_inside_box(qapp):
    from config import MOUTH_BOX_X, MOUTH_BOX_Y, MOUTH_BOX_W, MOUTH_BOX_H
    engine = CyberAudioEngine()
    overlay = OverlayWindow(engine)

    # 1. Transport buttons cleanly removed from Talia box
    assert hasattr(overlay, "transport_bar")
    assert overlay.transport_bar is None
    assert overlay.btn_pet_prev is None
    assert overlay.btn_pet_play is None
    assert overlay.btn_pet_next is None
    assert BUTTON_STRIP_H == 0

    # 2. Mouth bounding box enlarged to seal hole to desktop while staying within Talia
    assert MOUTH_BOX_X <= 138
    assert MOUTH_BOX_Y <= 222
    assert MOUTH_BOX_X + MOUTH_BOX_W >= 450
    assert MOUTH_BOX_Y + MOUTH_BOX_H >= 450
    # Must remain strictly within Talia's 591x591 bounds (not bigger than Talia)
    assert MOUTH_BOX_X >= 0
    assert MOUTH_BOX_Y >= 0
    assert MOUTH_BOX_X + MOUTH_BOX_W <= 591
    assert MOUTH_BOX_Y + MOUTH_BOX_H <= 591

    overlay.hide()


@pytest.mark.gui
def test_hold_to_move_mode_toggle_and_shutdown(qapp):
    engine = CyberAudioEngine()
    overlay = OverlayWindow(engine)

    # 1. From Locked mode: hold 0.7s toggles Move Mode ON
    assert overlay.move_talia_mode is False
    overlay.press_pos = QPoint(100, 100)
    overlay.press_time = time.time() - 0.75
    overlay.press_was_in_move_mode = False
    overlay.is_holding = True
    overlay.has_dragged = False
    overlay.has_dragged_window = False
    overlay.drag_ready_triggered = False

    overlay._on_hold_tick()
    assert overlay.move_talia_mode is True
    assert overlay.drag_ready_triggered is True
    assert overlay.is_dragging is True

    # 2. From Move Mode: hold 0.7s toggles Move Mode OFF (Locks Talia back!)
    overlay.press_pos = QPoint(100, 100)
    overlay.press_time = time.time() - 0.75
    overlay.press_was_in_move_mode = True
    overlay.is_holding = True
    overlay.has_dragged = False
    overlay.has_dragged_window = False
    overlay.drag_ready_triggered = False

    overlay._on_hold_tick()
    assert overlay.move_talia_mode is False
    assert overlay.is_dragging is False

    # 3. From Locked Mode: hold 2.0s without moving mouse triggers sinking shutdown
    overlay.press_pos = QPoint(100, 100)
    overlay.press_time = time.time() - 2.1
    overlay.press_was_in_move_mode = False
    overlay.is_holding = True
    overlay.has_dragged = False
    overlay.has_dragged_window = False
    overlay.drag_ready_triggered = False
    overlay.is_shutting_down = False

    overlay._on_hold_tick()
    assert overlay.is_shutting_down is True

    overlay.hide()


@pytest.mark.gui
def test_popup_scrubber_on_drag(qapp):
    engine = CyberAudioEngine()
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine)

    seek_called_with = []
    engine.seek = lambda s: seek_called_with.append(s)
    engine.get_duration = lambda: 200.0

    overlay.move_talia_mode = False
    overlay.press_pos = QPoint(100, 100)
    overlay.press_time = time.time()
    overlay.press_was_in_move_mode = False
    overlay.is_holding = True
    overlay.drag_ready_triggered = False

    class DummyMoveEvent:
        def globalPosition(self):
            class Pt:
                def toPoint(self):
                    return QPoint(150, 102)
            return Pt()
        def position(self):
            class PtF:
                def x(self):
                    return 180.0
                def y(self):
                    return 102.0
            return PtF()
        def buttons(self):
            return Qt.MouseButton.LeftButton
        def accept(self):
            pass

    overlay.mouseMoveEvent(DummyMoveEvent())
    assert overlay.is_scrubbing_overlay is True
    assert overlay.scrub_ratio > 0.0
    assert overlay.scrub_target_time > 0.0

    # HUD drawing smoke test
    img = QImage(300, 300, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    try:
        overlay._draw_scrubber_hud(p, 16, 16, 268)
    finally:
        p.end()

    # Release mouse to seek
    class DummyReleaseEvent:
        def button(self):
            return Qt.MouseButton.LeftButton
        def accept(self):
            pass

    overlay.mouseReleaseEvent(DummyReleaseEvent())
    assert overlay.is_scrubbing_overlay is False
    assert len(seek_called_with) == 1
    assert seek_called_with[0] > 0.0

    panel.hide()
    overlay.hide()


@pytest.mark.gui
def test_song_played_counter(qapp):
    engine = CyberAudioEngine()
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine)

    track1 = "C:/music/Song1.mp3"
    track2 = "C:/music/Song2.mp3"

    assert panel.get_play_count(track1) == 0
    assert panel.get_play_count(track2) == 0

    c1 = panel.record_track_played(track1)
    assert c1 == 1
    assert panel.get_play_count(track1) == 1

    c2 = panel.record_track_played(track1)
    assert c2 == 2
    assert panel.get_play_count(track1) == 2
    assert panel.get_play_count(track2) == 0

    # Ensure single increment per play via hook
    panel.audio_engine.playlist = [track1, track2]
    old_c = panel.get_play_count(track1)
    panel.audio_engine.track_started_hook(track1)
    assert panel.get_play_count(track1) == old_c + 1

    cfg = panel.get_current_settings_dict()
    assert "play_counts" in cfg

    panel.hide()
    overlay.hide()


@pytest.mark.gui
def test_favourite_playlist_and_symbol(qapp):
    engine = CyberAudioEngine()
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine)

    track1 = "C:/music/Cyber1.mp3"
    assert panel.is_favourite(track1) is False

    res1 = panel.toggle_favourite(track1)
    assert res1 is True
    assert panel.is_favourite(track1) is True

    res2 = panel.toggle_favourite(track1)
    assert res2 is False
    assert panel.is_favourite(track1) is False

    # Turn back on
    panel.toggle_favourite(track1)
    cfg = panel.get_current_settings_dict()
    assert "favourite_tracks" in cfg

    panel.hide()
    overlay.hide()


@pytest.mark.gui
def test_sort_and_filtered_navigation(qapp):
    engine = CyberAudioEngine()
    engine.load_file = lambda p, **kwargs: True
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine)

    t_z = "C:/music/Z_track.mp3"
    t_a = "C:/music/A_track.mp3"
    t_m = "C:/music/M_track.mp3"
    engine.playlist = [t_z, t_a, t_m]
    engine.current_index = 0
    panel.populate_playlist_ui()

    # 1. Default order: Z -> A -> M
    active = panel.get_active_filtered_tracks()
    assert active == [t_z, t_a, t_m]

    # Advance next in default order
    panel.play_next_track()
    assert engine.current_index == 1  # t_a

    # 2. Alphabetical Sort: A -> M -> Z
    panel.on_sort_changed("Alphabetical (A-Z)")
    active_alpha = panel.get_active_filtered_tracks()
    assert active_alpha == [t_a, t_m, t_z]

    # Current is t_a, next should be t_m!
    panel.play_next_track()
    assert engine.current_index == 2  # t_m is index 2 in engine.playlist

    # Next from t_m should be t_z!
    panel.play_next_track()
    assert engine.current_index == 0  # t_z is index 0 in engine.playlist

    # Previous from t_z should go back to t_m!
    panel.on_prev_clicked()
    assert engine.current_index == 2  # t_m

    # 3. Most Played Sort:
    # Give t_z 10 plays, t_m 50 plays, t_a 2 plays
    panel.play_counts = {t_z: 10, t_m: 50, t_a: 2}
    panel.on_sort_changed("Most Played")
    active_plays = panel.get_active_filtered_tracks()
    assert active_plays == [t_m, t_z, t_a]

    # Next from t_m should be t_z!
    engine.current_index = 2  # t_m
    panel.play_next_track()
    assert engine.current_index == 0  # t_z

    panel.hide()
    overlay.hide()


@pytest.mark.gui
def test_batch_delete(qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    engine = CyberAudioEngine()
    engine.load_file = lambda p, **kwargs: True
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine)

    t1 = "C:/music/Track1.mp3"
    t2 = "C:/music/Track2.mp3"
    t3 = "C:/music/Track3.mp3"
    engine.playlist = [t1, t2, t3]
    engine.current_index = 0
    panel.populate_playlist_ui()

    # Select Track2 for batch deletion
    panel.on_track_batch_toggled(t2, True)
    assert t2 in panel.selected_batch_tracks

    # Mock user confirming deletion
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    panel.batch_delete_selected()
    assert t2 not in engine.playlist
    assert engine.playlist == [t1, t3]
    assert len(panel.selected_batch_tracks) == 0

    panel.hide()
    overlay.hide()


@pytest.mark.gui
def test_playlist_maker_and_group_by_artist(qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox, QInputDialog
    from playlist_panel import extract_primary_artist

    # Test primary artist extraction ignoring featured credits
    assert extract_primary_artist("Eminem") == "Eminem"
    assert extract_primary_artist("Eminem feat. Juice WRLD") == "Eminem"
    assert extract_primary_artist("Eminem ft. Rihanna") == "Eminem"
    assert extract_primary_artist("Eminem featuring 50 Cent") == "Eminem"
    assert extract_primary_artist("David Guetta & Bebe Rexha") == "David Guetta"
    assert extract_primary_artist("Marshmello x Khalid") == "Marshmello"
    assert extract_primary_artist("Drake, 21 Savage") == "Drake"

    engine = CyberAudioEngine()
    engine.load_file = lambda p, **kwargs: True
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine)

    t1 = "C:/music/Cyberpunk - City Night.mp3"
    t2 = "C:/music/Cyberpunk feat. Johnny - Rebel Path.mp3"
    t3 = "C:/music/01. Samurai - Chippin In.mp3"
    engine.playlist = [t1, t2, t3]
    engine.current_index = 0
    panel.populate_playlist_ui()

    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    # Mock user entering "Cyberpunk" in the input prompt
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Cyberpunk", True))
    panel.group_songs_by_artist()

    assert "Artist: Cyberpunk" in panel.custom_playlists
    # Both "Cyberpunk" and "Cyberpunk feat. Johnny" count as Cyberpunk!
    assert len(panel.custom_playlists["Artist: Cyberpunk"]) == 2
    assert t1 in panel.custom_playlists["Artist: Cyberpunk"]
    assert t2 in panel.custom_playlists["Artist: Cyberpunk"]

    # Select the Cyberpunk artist playlist
    panel.on_playlist_selected("Artist: Cyberpunk")
    active = panel.get_active_filtered_tracks()
    assert active == [t1, t2]

    # Advance next within this playlist
    panel.play_next_track()
    assert engine.current_index == 1  # t2

    panel.hide()
    overlay.hide()


@pytest.mark.gui
def test_playlist_add_and_delete(qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox, QInputDialog

    engine = CyberAudioEngine()
    engine.load_file = lambda p, **kwargs: True
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine)

    t1 = "C:/music/Song1.mp3"
    t2 = "C:/music/Song2.mp3"
    t3 = "C:/music/Song3.mp3"
    engine.playlist = [t1, t2, t3]
    engine.current_index = 0
    panel.populate_playlist_ui()

    # 1. Create playlist
    panel.custom_playlists["Roadtrip"] = [t1]
    panel.current_playlist = "Roadtrip"

    # Add song to playlist
    panel.custom_playlists["Roadtrip"].append(t2)
    assert len(panel.custom_playlists["Roadtrip"]) == 2
    assert t2 in panel.custom_playlists["Roadtrip"]

    # 2. Cannot delete default playlists
    info_shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: info_shown.append(args))
    panel.current_playlist = "All Tracks"
    panel.delete_current_playlist()
    assert len(info_shown) > 0
    assert "All Tracks" in panel.current_playlist

    # 3. Delete custom playlist with confirmation
    panel.current_playlist = "Roadtrip"
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    panel.delete_current_playlist()

    assert "Roadtrip" not in panel.custom_playlists
    assert panel.current_playlist == "All Tracks"

    panel.hide()
    overlay.hide()


@pytest.mark.gui
def test_sort_by_artist(qapp):
    engine = CyberAudioEngine()
    engine.load_file = lambda p, **kwargs: True
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine)

    s_samurai = "C:/music/Samurai - Never Fade Away.mp3"
    s_eminem_feat = "C:/music/Eminem feat. Juice WRLD - Godzilla.mp3"
    s_eminem_solo = "C:/music/Eminem - Without Me.mp3"
    s_cyber = "C:/music/Cyberpunk - City Night.mp3"

    engine.playlist = [s_samurai, s_eminem_feat, s_cyber, s_eminem_solo]
    panel.on_sort_changed("Sort by artist")

    # In Sort by artist, primary artists should be: Cyberpunk -> Eminem -> Samurai
    active = panel.get_active_filtered_tracks()
    assert active[0] == s_cyber
    # Both Eminem tracks group together in alphabetical order
    assert active[1:3] == [s_eminem_feat, s_eminem_solo] or active[1:3] == [s_eminem_solo, s_eminem_feat]
    assert active[3] == s_samurai

    panel.hide()
    overlay.hide()


@pytest.mark.gui
def test_subtitles_draggable_and_hover_dim(qapp):
    from PyQt6.QtGui import QCursor
    from PyQt6.QtCore import QPoint

    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    lyrics.resize(800, 150)
    lyrics.move(100, 100)
    lyrics.show()

    # Default hover dim is 1.0 (full brightness)
    assert lyrics.hover_dim == 1.0
    assert lyrics.is_hovered is False

    # Set displayed text and render to compute subtitle_rect
    lyrics.displayed_text = "City of Dreams"
    lyrics.line_opacity = 1.0
    lyrics.paintEvent(None)
    assert not lyrics.subtitle_rect.isEmpty()

    # Outside the subtitle box: hover_dim remains 1.0
    QCursor.setPos(QPoint(0, 0))
    lyrics.update_hover_state()
    assert lyrics.is_hovered is False
    assert lyrics.hover_dim == 1.0

    # Inside the subtitle box: dims by 60% -> opacity is 40% (0.40)
    inside_pt = lyrics.mapToGlobal(lyrics.subtitle_rect.center().toPoint())
    QCursor.setPos(inside_pt)
    lyrics.update_hover_state()
    assert lyrics.is_hovered is True
    assert lyrics.hover_dim == 0.40

    # Simulate leave (leaveEvent)
    class DummyLeaveEvent:
        pass

    lyrics.leaveEvent(DummyLeaveEvent())
    assert lyrics.is_hovered is False
    assert lyrics.hover_dim == 1.0

    # Subtitles are draggable anytime when clicking the subtitle box
    assert lyrics.move_mode is False
    class DummyMousePressEvent:
        def button(self):
            return Qt.MouseButton.LeftButton
        def globalPosition(self):
            class Pt:
                def toPoint(self):
                    return inside_pt
            return Pt()
        def accept(self):
            pass

    lyrics.mousePressEvent(DummyMousePressEvent())
    assert lyrics.is_dragging is True

    class DummyMouseMoveEvent:
        def buttons(self):
            return Qt.MouseButton.LeftButton
        def globalPosition(self):
            class Pt:
                def toPoint(self):
                    return QPoint(220, 230)
            return Pt()
        def accept(self):
            pass

    lyrics.mouseMoveEvent(DummyMouseMoveEvent())

    class DummyMouseReleaseEvent:
        def accept(self):
            pass

    lyrics.mouseReleaseEvent(DummyMouseReleaseEvent())
    assert lyrics.is_dragging is False

    lyrics.hide()


@pytest.mark.gui
def test_slide_out_panel_and_screen_edge_logic(qapp):
    engine = CyberAudioEngine()
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine)

    # Controls Bar exists and is transparent
    assert hasattr(panel, "controls_bar")
    assert panel.controls_bar is not None
    assert hasattr(panel.controls_bar, "btn_prev")
    assert hasattr(panel.controls_bar, "btn_play")
    assert hasattr(panel.controls_bar, "btn_next")
    assert hasattr(panel.controls_bar, "btn_shuffle")

    # Geometry calculation test
    overlay.setGeometry(500, 400, 250, 250)
    p_start, p_target, c_start, c_target = panel.calculate_slide_geometries()

    # Panel target width and height are respected
    assert p_target.width() in (360, 380)
    assert p_target.height() == 460
    # Controls target sits below Talia by default
    assert c_target.y() >= overlay.geometry().bottom()

    # Test screen edge awareness: position Talia near left edge
    overlay.setGeometry(10, 400, 250, 250)
    _, p_target_left, _, _ = panel.calculate_slide_geometries()
    # When left side is blocked, panel slides to the RIGHT!
    assert p_target_left.left() >= overlay.geometry().right()

    panel.hide()
    panel.controls_bar.hide()
    overlay.hide()
    if hasattr(panel, "timeline_timer"):
        panel.timeline_timer.stop()
    if hasattr(panel, "hotkey_timer"):
        panel.hotkey_timer.stop()
    panel.deleteLater()
    overlay.deleteLater()


@pytest.mark.gui
def test_settings_dialog_and_controller_subtitle_bg(qapp):
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    assert hasattr(panel.settings_dialog, "chk_subtitle_bg")
    # Subtitle shadow is default ON
    assert panel.settings_dialog.chk_subtitle_bg.isChecked() is True

    panel.on_subtitle_bg_toggled(False)
    assert lyrics.show_subtitle_bg is False

    cfg = panel.get_current_settings_dict()
    assert cfg.get("show_subtitle_bg") is False

    cfg["show_subtitle_bg"] = True
    panel.apply_settings(cfg)
    assert lyrics.show_subtitle_bg is True
    assert panel.settings_dialog.chk_subtitle_bg.isChecked() is True

    panel.hide()
    lyrics.hide()
    overlay.hide()
    if hasattr(panel, "timeline_timer"):
        panel.timeline_timer.stop()
    if hasattr(panel, "hotkey_timer"):
        panel.hotkey_timer.stop()
    panel.deleteLater()
    lyrics.deleteLater()
    overlay.deleteLater()
