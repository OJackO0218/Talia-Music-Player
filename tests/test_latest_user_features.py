"""Tests for Timeline Scrubber HUD, Menu Panel Styling, Compact Controls,
Pet Transport Buttons Visibility, Subfolder Playlists, Search & YouTube Download Merge,
and Removal of Desktop Audio Mode.
"""

import os
import inspect
import pytest
from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication, QMessageBox

from audio_engine import CyberAudioEngine
from config import PROJECT_ROOT
from controller import ControlPanel
from lyrics_manager import LyricsManager
from lyrics_overlay import LyricsOverlayWindow
from overlay import OverlayWindow


@pytest.mark.gui
def test_timeline_slider_no_seek_text(qapp):
    engine = CyberAudioEngine()
    overlay = OverlayWindow(engine)

    # 1. Verify code has removed 'KIROSHI TIMELINE SEEK'
    src = inspect.getsource(overlay._draw_scrubber_hud)
    assert "KIROSHI TIMELINE SEEK" not in src
    assert "time_str" in src

    # 2. Test HUD painting during scrub
    overlay.is_scrubbing_overlay = True
    overlay.scrub_ratio = 0.45
    overlay.scrub_target_time = 75.0
    img = QImage(300, 300, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    try:
        overlay._draw_scrubber_hud(p, 10, 10, 200)
    finally:
        p.end()

    overlay.is_scrubbing_overlay = False
    overlay.hide()
    overlay.deleteLater()


@pytest.mark.gui
def test_menu_panel_styling_and_compact_controls(qapp):
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    # 1. Red outline on menu panel card
    card_ss = panel.card_container.styleSheet()
    assert "rgba(255, 0, 60" in card_ss or "#ff003c" in card_ss

    # 2. Red MENU branding
    found_menu = False
    for child in panel.card_container.children():
        if hasattr(child, "text") and child.text() == "MENU":
            found_menu = True
            assert "#ff003c" in child.styleSheet()
            break
    assert found_menu, "MENU title not found in card_container!"

    # 3. Compact 28x28 controls bar buttons with crisp 24x24 icons
    cb = panel.controls_bar
    for btn in (cb.btn_prev, cb.btn_play, cb.btn_next, cb.btn_shuffle):
        assert btn.width() <= 30
        assert btn.height() <= 30
        assert btn.text() == ""  # Zero text, sprite/symbol only

    # 4. sync_play_state does not overwrite button text or set solid background
    panel.sync_play_state()
    assert cb.btn_play.text() == ""
    assert "background-color: transparent" in cb.btn_play.styleSheet()

    panel.update_shuffle_ui()
    assert cb.btn_shuffle.text() == ""
    assert "background-color: transparent" in cb.btn_shuffle.styleSheet()

    panel.hide()
    cb.hide()
    lyrics.hide()
    overlay.hide()
    if hasattr(panel, "timeline_timer"):
        panel.timeline_timer.stop()
    if hasattr(panel, "hotkey_timer"):
        panel.hotkey_timer.stop()
    panel.deleteLater()
    lyrics.deleteLater()
    overlay.deleteLater()


@pytest.mark.gui
def test_talia_transport_buttons_ux(qapp):
    from config import MOUTH_BOX_X, MOUTH_BOX_Y, MOUTH_BOX_W, MOUTH_BOX_H
    engine = CyberAudioEngine()
    overlay = OverlayWindow(engine)
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    panel = ControlPanel(overlay, engine, lyrics)

    # 1. Transport buttons cleanly removed from Talia box
    assert overlay.transport_bar is None
    assert overlay.btn_pet_play is None
    assert overlay.btn_pet_prev is None
    assert overlay.btn_pet_next is None

    # 2. Playback controls remain intact and fully functional in the slide-out menu panel
    cb = panel.controls_bar
    assert hasattr(cb, "btn_play")
    assert hasattr(cb, "btn_prev")
    assert hasattr(cb, "btn_next")
    assert hasattr(cb, "btn_shuffle")

    # Initial state (paused): play icon
    engine.is_playing = False
    panel.sync_play_state()
    assert not cb.btn_play.icon().isNull()

    # Playing state: toggles to pause icon without recursion
    engine.is_playing = True
    panel.sync_play_state()
    assert not cb.btn_play.icon().isNull()

    # 3. Mouth cavity background is enlarged and covers transparent opening without holes
    assert MOUTH_BOX_X <= 138
    assert MOUTH_BOX_Y <= 220
    assert MOUTH_BOX_X + MOUTH_BOX_W >= 450
    assert MOUTH_BOX_Y + MOUTH_BOX_H >= 450
    assert MOUTH_BOX_X + MOUTH_BOX_W <= 591
    assert MOUTH_BOX_Y + MOUTH_BOX_H <= 591

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


@pytest.mark.gui
def test_music_folders_as_playlists(qapp, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    engine = CyberAudioEngine()
    base_music = os.path.join(PROJECT_ROOT, "music")
    engine.folder_path = base_music
    engine.playlist = [
        os.path.join(base_music, "Hamilton (Original Broadway Cast Recording)", "01 Alexander Hamilton.opus"),
        os.path.join(base_music, "Hamilton (Original Broadway Cast Recording)", "02 Aaron Burr.opus"),
        os.path.join(base_music, "Forza Horizon 4", "Deadly Valentine.opus"),
        os.path.join(base_music, "Downloaded Songs", "Eminem - Venom.opus"),
        os.path.join(base_music, "RootSong.opus"),
    ]

    overlay = OverlayWindow(engine)
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    panel = ControlPanel(overlay, engine, lyrics)

    # 1. get_music_subfolders automatically identifies all subfolders
    subfolders = panel.get_music_subfolders()
    assert "Hamilton (Original Broadway Cast Recording)" in subfolders
    assert "Forza Horizon 4" in subfolders
    assert "Downloaded Songs" in subfolders
    assert len(subfolders["Hamilton (Original Broadway Cast Recording)"]) == 2

    # 2. combo_playlist automatically includes folder names
    panel.refresh_playlist_dropdown()
    items = [panel.combo_playlist.itemText(i) for i in range(panel.combo_playlist.count())]
    assert "Hamilton (Original Broadway Cast Recording)" in items
    assert "Forza Horizon 4" in items
    assert "Downloaded Songs" in items

    # 3. Selecting folder playlist displays only songs from that folder
    panel.on_playlist_selected("Hamilton (Original Broadway Cast Recording)")
    assert panel.list_tracks.count() == 2

    # 4. Cannot delete folder playlist
    panel.delete_current_playlist()
    items_after = [panel.combo_playlist.itemText(i) for i in range(panel.combo_playlist.count())]
    assert "Hamilton (Original Broadway Cast Recording)" in items_after

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


@pytest.mark.gui
def test_search_and_youtube_download_merge(qapp):
    engine = CyberAudioEngine()
    base_music = os.path.join(PROJECT_ROOT, "music")
    engine.folder_path = base_music
    engine.playlist = [
        os.path.join(base_music, "Hamilton", "01 Alexander Hamilton.opus"),
    ]

    overlay = OverlayWindow(engine)
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    panel = ControlPanel(overlay, engine, lyrics)
    panel.show()

    assert hasattr(panel, "yt_download_card")
    assert panel.yt_download_card.isHidden() is True

    # 1. Search for existing track -> matches, download card remains hidden
    panel.search_input.setText("Hamilton")
    assert panel.yt_download_card.isHidden() is True

    # 2. Search for non-existing track -> 0 matches, download card is shown
    panel.search_input.setText("Coldplay - Yellow")
    assert panel.yt_download_card.isVisible() is True
    assert "Coldplay - Yellow" in panel.lbl_yt_prompt.text()
    assert "Download" in panel.btn_yt_download.text()

    # 3. Clearing search hides download card
    panel.search_input.clear()
    assert panel.yt_download_card.isHidden() is True

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


def test_desktop_audio_mode_removed():
    engine = CyberAudioEngine()
    assert engine.audio_mode == "player"

    # Switching to desktop is a no-op; stays player
    engine.set_audio_mode("desktop")
    assert engine.audio_mode == "player"
    assert engine.get_current_track_title() == "No Track Loaded"

    # Verify VK_F10 removed from config
    import config
    assert not hasattr(config, "VK_F10")


@pytest.mark.gui
def test_v250_menu_and_volume_slider(qapp):
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    # 1. Dim cyberpunk blue background on TaliaControlsBar
    cb = panel.controls_bar
    cb_style = cb.styleSheet()
    assert "rgba(6, 20, 36" in cb_style or "rgba(0, 240, 255" in cb_style

    # 2. Spotify playlist sync and listen together buttons in header beside MENU
    assert hasattr(panel, "btn_spotify_sync")
    assert panel.btn_spotify_sync is not None
    assert "Spotify" in panel.btn_spotify_sync.text()
    assert hasattr(panel, "btn_party_sync")
    assert panel.btn_party_sync is not None
    assert "Together" in panel.btn_party_sync.text()

    # 3. + Add button removed from playlist bar, + New kept (+ icon matching Figma)
    assert hasattr(panel, "btn_new_playlist")
    assert panel.btn_new_playlist.text() in ("+ New", "+")
    assert getattr(panel, "btn_add_to_playlist", None) is None

    # 4. Vertical volume slider on left side of menu panel & sync with Talia
    assert hasattr(panel, "slider_vol")
    assert panel.slider_vol.orientation() == Qt.Orientation.Vertical
    assert panel.slider_vol.value() == int(engine.volume * 100)

    # Talia scroll / volume change syncs volume slider
    overlay.set_volume(0.42)
    assert panel.slider_vol.value() == 42
    assert panel.lbl_vol_val.text() == "42%"

    # Moving slider updates audio engine and overlay volume
    panel.slider_vol.setValue(75)
    assert abs(engine.volume - 0.75) < 0.02
    assert abs(overlay.current_volume - 0.75) < 0.02

    # 5. Persistent download status badge on bottom-right of menu panel
    assert hasattr(panel, "download_status_badge")
    panel.show()
    panel.show_download_status("Downloading 'Cyber Song'...", is_done=False)
    assert not panel.download_status_badge.isHidden()
    assert "Cyber Song" in panel.lbl_download_badge_text.text()

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


def test_punctuation_insensitive_song_search():
    from playlist_panel import normalize_search_term

    # Ignore apostrophes, dashes, equals, dots, underscores
    fn = "4 Non Blondes - What's Up.mp3"
    norm_fn = normalize_search_term(fn)

    # Various queries with and without punctuation
    for q in ["Whats up", "What's up", "whats-up", "whats = up", "WHAT'S UP", "whats_up", "whats . up"]:
        norm_q = normalize_search_term(q)
        assert norm_q in norm_fn or all(t in norm_fn for t in norm_q.split()), f"Failed to match query {q!r}"


def test_app_version_is_2_6_0():
    from config import APP_VERSION, PROJECT_ROOT
    assert APP_VERSION == "2.6.0"

    vinfo_p = os.path.join(PROJECT_ROOT, "version_info.txt")
    if os.path.exists(vinfo_p):
        with open(vinfo_p, encoding="utf-8") as f:
            v_txt = f.read()
        assert "2, 6, 0, 0" in v_txt
        assert "2.6.0.0" in v_txt

    pyproj_p = os.path.join(PROJECT_ROOT, "pyproject.toml")
    if os.path.exists(pyproj_p):
        with open(pyproj_p, encoding="utf-8") as f:
            toml_txt = f.read()
        assert 'version = "2.6.0"' in toml_txt


@pytest.mark.gui
def test_controls_bar_permanent_box_and_shuffle_colors(qapp):
    from PIL import Image

    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    cb = panel.controls_bar
    cb.setFixedSize(136, 34)
    cb.show()

    # 1. Permanent rectangular background box surrounding all 4 buttons
    pix = cb.grab()
    img = pix.toImage()
    # Check margin/background pixel (dim cyberpunk blue, alpha ~230)
    bg_px = img.pixelColor(4, 4)
    assert bg_px.alpha() > 200
    assert bg_px.red() in range(4, 10)
    assert bg_px.green() in range(16, 25)
    assert bg_px.blue() in range(30, 42)

    # 2. Shuffle OFF: icon is red (shuffle_active.png)
    engine.shuffle = False
    cb.sync_state()
    off_icon_path = os.path.join(PROJECT_ROOT, "assets", "user_sprites", "shuffle_active.png")
    assert os.path.exists(off_icon_path)
    im_off = Image.open(off_icon_path)
    red_pixels = [px for px in im_off.getdata() if px[3] > 0 and px[0] > 140 and px[2] < 50]
    assert len(red_pixels) > 200, "shuffle_active.png must have predominantly red pixels for OFF state"

    # 3. Shuffle ON: icon is blue (shuffle_button.png)
    engine.shuffle = True
    cb.sync_state()
    on_icon_path = os.path.join(PROJECT_ROOT, "assets", "user_sprites", "shuffle_button.png")
    assert os.path.exists(on_icon_path)
    im_on = Image.open(on_icon_path)
    blue_pixels = [px for px in im_on.getdata() if px[3] > 0 and px[0] < 50 and px[2] > 200]
    assert len(blue_pixels) > 200, "shuffle_button.png must have predominantly cyan/blue pixels for ON state"

    # 4. Clicking the shuffle button toggles shuffle state properly
    engine.shuffle = False
    cb.sync_state()
    assert engine.shuffle is False
    cb.btn_shuffle.click()
    assert engine.shuffle is True
    cb.btn_shuffle.click()
    assert engine.shuffle is False

    cb.hide()
    panel.hide()
    lyrics.hide()
    overlay.hide()
    if hasattr(panel, "timeline_timer"):
        panel.timeline_timer.stop()
    if hasattr(panel, "hotkey_timer"):
        panel.hotkey_timer.stop()
    cb.deleteLater()
    panel.deleteLater()
    lyrics.deleteLater()
    overlay.deleteLater()


@pytest.mark.gui
def test_lyrics_default_full_brightness_and_precise_hover(qapp):
    from PyQt6.QtGui import QCursor
    from PyQt6.QtCore import QPoint

    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    lyrics.resize(1000, 150)
    lyrics.move(100, 100)
    lyrics.show()

    # 1. When lyrics first show up: default brightness is 1.0 (never dimmed)
    lyrics.displayed_text = "Never Fade Away"
    lyrics.line_opacity = 1.0
    lyrics.pop_progress = 1.0
    assert lyrics.hover_dim == 1.0
    assert lyrics.is_hovered is False

    # Force a paintEvent to construct subtitle_rect
    img = QImage(lyrics.size(), QImage.Format.Format_ARGB32)
    p = QPainter(img)
    try:
        lyrics.paintEvent(None)
    finally:
        p.end()

    assert not lyrics.subtitle_rect.isEmpty()
    sub_rect = lyrics.subtitle_rect

    # 2. When cursor is at (0, 0) global (outside the subtitle box), hover_dim remains 1.0
    QCursor.setPos(QPoint(0, 0))
    lyrics.update_hover_state()
    assert lyrics.hover_dim == 1.0
    assert lyrics.is_hovered is False

    # 3. When cursor enters inside the subtitle_rect, hover_dim reduces to 0.40 (60% dimming)
    inside_pt_local = sub_rect.center().toPoint()
    inside_pt_global = lyrics.mapToGlobal(inside_pt_local)
    QCursor.setPos(inside_pt_global)
    lyrics.update_hover_state()
    assert lyrics.is_hovered is True
    assert lyrics.hover_dim == 0.40

    # 4. When cursor moves away back to (0, 0), full brightness is restored
    QCursor.setPos(QPoint(0, 0))
    lyrics.update_hover_state()
    assert lyrics.is_hovered is False
    assert lyrics.hover_dim == 1.0

    lyrics.hide()
    lyrics.deleteLater()





