"""Tests for ★ Random Mix endless radio playlist, exclusions, auto-cleanup, and permanent save."""

import os
from unittest.mock import patch

import pytest

from audio_engine import CyberAudioEngine
from controller import ControlPanel
from lyrics_manager import LyricsManager
from lyrics_overlay import LyricsOverlayWindow
from overlay import OverlayWindow
from radio_mix import RADIO_PLAYLIST_NAME, RadioMixManager


@pytest.fixture(scope="module")
def radio_env(qapp):
    engine = CyberAudioEngine()
    l_mgr = LyricsManager()
    l_overlay = LyricsOverlayWindow(engine, l_mgr)
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, l_overlay)
    yield panel, engine
    panel.hide()
    l_overlay.hide()
    overlay.hide()


def test_random_mix_playlist_dropdown_and_bar_visibility(radio_env):
    panel, _ = radio_env
    idx = panel.combo_playlist.findText(RADIO_PLAYLIST_NAME)
    assert idx >= 0

    panel.on_playlist_selected(RADIO_PLAYLIST_NAME)
    assert panel.radio_mix_bar.isHidden() is False

    panel.on_playlist_selected("All Tracks")
    assert panel.radio_mix_bar.isHidden() is True


def test_exclusion_checklist_filtering(radio_env, tmp_path):
    panel, engine = radio_env
    lib_track = tmp_path / "Porter Robinson - Shelter.opus"
    lib_track.write_bytes(b"audio")
    engine.playlist = [str(lib_track)]

    mgr = RadioMixManager(panel, cache_dir=str(tmp_path / "radio_cache"))
    mgr.toggle_excluded_artist("Blocked Artist", True)

    assert mgr.is_candidate_excluded({"id": "1", "title": "Porter Robinson - Shelter (Official Audio)", "duration": 210})
    assert mgr.is_candidate_excluded({"id": "2", "title": "Cool Song (Nightcore)", "duration": 180})
    assert mgr.is_candidate_excluded({"id": "3", "title": "1 Hour Synthwave Mix", "duration": 3600})
    assert mgr.is_candidate_excluded({"id": "4", "title": "New Track", "uploader": "Blocked Artist", "duration": 200})

    # Clean unowned track passes
    assert not mgr.is_candidate_excluded(
        {"id": "5", "title": "Madeon - All My Friends", "uploader": "Madeon", "duration": 204}
    )


def test_cache_auto_cleanup_and_permanent_save(radio_env, tmp_path):
    panel, engine = radio_env
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    engine.folder_path = str(music_dir)
    engine.playlist = []

    cache_dir = tmp_path / "radio_cache"
    mgr = RadioMixManager(panel, cache_dir=str(cache_dir))

    # Create 4 cached tracks with staggered mtimes
    created = []
    for i in range(4):
        op = cache_dir / f"Artist {i} - Song {i}.opus"
        lrc = cache_dir / f"Artist {i} - Song {i}.lrc"
        op.write_bytes(b"opus")
        lrc.write_text("[00:01.00] Hello", encoding="utf-8")
        os.utime(op, (1000 + i * 10, 1000 + i * 10))
        created.append(str(op))

    # Protect newest 2; oldest 2 should be deleted with their .lrc
    mgr.cleanup_cache(max_keep=2)
    remaining = mgr.get_cached_tracks()
    assert len(remaining) == 2
    assert not os.path.exists(created[0])
    assert not os.path.exists(os.path.splitext(created[0])[0] + ".lrc")

    # Save newest track permanently into <music>/Downloaded Songs/
    target = remaining[0]
    ok, msg = mgr.save_track_permanently(target)
    assert ok is True, msg
    dest_op = music_dir / "Downloaded Songs" / os.path.basename(target)
    dest_lrc = music_dir / "Downloaded Songs" / (os.path.splitext(os.path.basename(target))[0] + ".lrc")
    assert dest_op.exists()
    assert dest_lrc.exists()
    assert not os.path.exists(target)
    assert str(dest_op) in engine.playlist


def test_play_triggers_random_mix_when_selected(radio_env):
    panel, engine = radio_env
    panel.on_playlist_selected(RADIO_PLAYLIST_NAME)
    engine.audio_mode = "local"
    engine.current_index = -1
    engine._active_file_path = ""

    with patch.object(panel.radio_mix, "request_next_track") as mock_req:
        panel.on_play_pause_clicked()
        mock_req.assert_called_once_with(auto_play=True)

    # Single-clicking Talia directly also triggers Random Mix playback
    with patch.object(panel.radio_mix, "request_next_track") as mock_req2:
        panel.overlay._trigger_single_click()
        mock_req2.assert_called_once_with(auto_play=True)
    panel.on_playlist_selected("All Tracks")


def test_two_song_retention_eviction_and_title_sync(radio_env, tmp_path):
    """Verify 5-song sliding window: 2 previous kept + current + 2 buffered next."""
    panel, engine = radio_env
    cache_dir = tmp_path / "radio_retention"
    cache_dir.mkdir()
    mgr = RadioMixManager(panel, cache_dir=str(cache_dir))

    def _make_cached(name: str) -> str:
        op = cache_dir / f"{name}.opus"
        lrc = cache_dir / f"{name}.lrc"
        op.write_bytes(b"opus")
        lrc.write_text("[00:01.00] line", encoding="utf-8")
        return str(op)

    song_a = _make_cached("Song A")
    song_b = _make_cached("Song B")
    song_c = _make_cached("Song C")
    song_d = _make_cached("Song D")
    next_1 = _make_cached("Next 1")
    mgr.prefetch_queue = [song_d, next_1]

    # A plays -> A kept
    mgr.record_played_radio_track(song_a)
    assert os.path.exists(song_a)

    # B plays -> A and B kept
    mgr.record_played_radio_track(song_b)
    assert os.path.exists(song_a) and os.path.exists(song_b)

    # C plays -> [A, B, C] (2 prev + cur) + [D, Next 1] (2 buffered) = 5 songs!
    mgr.record_played_radio_track(song_c)
    assert os.path.exists(song_a)
    assert os.path.exists(song_b)
    assert os.path.exists(song_c)
    assert len(mgr.get_cached_tracks()) == 5

    # Stepping Previous from C returns B cleanly
    assert mgr.get_previous_track(song_c) == song_b

    # D plays from prefetch_queue and Next 2 buffers -> A is immediately deleted, leaving [B, C, D, Next 1, Next 2] = 5 songs!
    next_2 = _make_cached("Next 2")
    mgr.prefetch_queue.append(next_2)
    mgr.record_played_radio_track(song_d)
    assert not os.path.exists(song_a)
    assert not os.path.exists(os.path.splitext(song_a)[0] + ".lrc")
    assert os.path.exists(song_b)
    assert os.path.exists(song_c)
    assert os.path.exists(song_d)
    assert len(mgr.get_cached_tracks()) == 5

    # Title sync reflects _active_file_path even when playlist index differs
    engine.playlist = [str(tmp_path / "Regular Song.opus")]
    engine.current_index = 0
    engine._active_file_path = song_d
    assert engine.get_current_track_title() == "Song D.opus"
    engine._active_file_path = ""


def test_two_ahead_prefetch_queue_advances_smoothly(radio_env, tmp_path):
    panel, _ = radio_env
    cache_dir = tmp_path / "radio_prefetch_2"
    cache_dir.mkdir()
    mgr = RadioMixManager(panel, cache_dir=str(cache_dir))

    n1 = cache_dir / "Buffered 1.opus"
    n2 = cache_dir / "Buffered 2.opus"
    n1.write_bytes(b"1")
    n2.write_bytes(b"2")
    mgr.prefetch_queue = [str(n1), str(n2)]

    emitted = []
    mgr.track_ready.connect(lambda p, ap: emitted.append((p, ap)))
    with patch.object(mgr, "prefetch_next") as mock_topup:
        mgr.request_next_track(auto_play=True)

    assert emitted == [(str(n1), True)]
    assert mgr.prefetch_queue == [str(n2)]
    mock_topup.assert_called_once()


def test_middle_click_talia_saves_current_radio_song(radio_env, tmp_path):
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent

    panel, engine = radio_env
    music_dir = tmp_path / "music_mid"
    music_dir.mkdir()
    engine.folder_path = str(music_dir)
    engine.playlist = []

    cache_dir = panel.radio_mix.cache_dir
    os.makedirs(cache_dir, exist_ok=True)
    cached_song = os.path.join(cache_dir, "Middle Click Test Song.opus")
    with open(cached_song, "wb") as fh:
        fh.write(b"opus")
    engine._active_file_path = cached_song

    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(50, 50),
        QPointF(50, 50),
        Qt.MouseButton.MiddleButton,
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(50, 50),
        QPointF(50, 50),
        Qt.MouseButton.MiddleButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    panel.overlay.mousePressEvent(press)
    panel.overlay.mouseReleaseEvent(release)

    saved_dest = music_dir / "Downloaded Songs" / "Middle Click Test Song.opus"
    assert saved_dest.exists()
    assert not os.path.exists(cached_song)
    assert panel.overlay.osd_symbol == "saved"
    assert panel.overlay.osd_timer > 0.0

    # Verify visual cue renders cleanly in paintEvent without error
    from PyQt6.QtGui import QImage
    img = QImage(panel.overlay.size(), QImage.Format.Format_ARGB32)
    panel.overlay.render(img)
    panel.overlay.osd_symbol = None
    panel.overlay.osd_timer = 0.0
    engine._active_file_path = ""


def test_random_mix_launch_restores_buffer_and_bar_visibility(qapp, tmp_path):
    """Launch with defer_populate=True + ★ Random Mix in settings shows bar & buffer immediately."""
    music_dir = tmp_path / "launch_music"
    music_dir.mkdir()
    reg = music_dir / "Regular Track.opus"
    reg.write_bytes(b"reg")

    engine = CyberAudioEngine()
    engine.set_folder(str(music_dir))
    l_overlay = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, l_overlay, defer_populate=True)

    # Seed 3 persisted cached songs on disk in a test cache dir
    cache_dir = tmp_path / "persisted_radio_cache"
    cache_dir.mkdir()
    panel.radio_mix.cache_dir = str(cache_dir)
    for i in range(3):
        p = cache_dir / f"Persisted {i}.opus"
        p.write_bytes(b"opus")

    panel.apply_settings({"current_playlist": RADIO_PLAYLIST_NAME})
    assert panel.current_playlist == RADIO_PLAYLIST_NAME
    assert panel.radio_mix_bar.isHidden() is False
    assert panel.list_tracks.count() == 3
    assert len(panel.radio_mix.get_cached_tracks()) == 3

    panel.hide()
    l_overlay.hide()
    overlay.hide()


def test_save_track_succeeds_even_when_source_file_is_locked(radio_env, tmp_path):
    """Simulates Windows WinError 32 lock on an actively playing file."""
    panel, engine = radio_env
    music_dir = tmp_path / "music_locked"
    music_dir.mkdir()
    engine.folder_path = str(music_dir)
    engine.playlist = []

    cache_dir = tmp_path / "radio_locked_cache"
    cache_dir.mkdir()
    mgr = RadioMixManager(panel, cache_dir=str(cache_dir))

    locked_song = cache_dir / "Locked Playing Song.opus"
    locked_lrc = cache_dir / "Locked Playing Song.lrc"
    locked_song.write_bytes(b"opus-bytes")
    locked_lrc.write_text("[00:01.00] Locked", encoding="utf-8")
    engine._active_file_path = str(locked_song)

    with patch.object(mgr, "_delete_audio_and_lrc", return_value=False):
        ok, msg = mgr.save_track_permanently(str(locked_song))

    assert ok is True, msg
    dest_op = music_dir / "Downloaded Songs" / "Locked Playing Song.opus"
    dest_lrc = music_dir / "Downloaded Songs" / "Locked Playing Song.lrc"
    assert dest_op.exists()
    assert dest_lrc.exists()
    assert engine._active_file_path == str(dest_op)
    # Hidden from cached list immediately, then flushed once unlocked
    assert str(locked_song) not in mgr.get_cached_tracks()
    mgr._flush_pending_deletes()
    assert not locked_song.exists()
    engine._active_file_path = ""
