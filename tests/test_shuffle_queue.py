"""Tests for shuffle balancing and queue prioritisation."""

from audio_engine import CyberAudioEngine


def _make_engine(monkeypatch, playlist):
    engine = CyberAudioEngine()
    monkeypatch.setattr(engine, "_trigger_preload_next", lambda: None)
    engine.playlist = list(playlist)
    engine.current_index = 0
    return engine


def test_random_shuffle_covers_every_track_without_repeat(monkeypatch):
    playlist = [f"C:/music/Artist{i % 3} - Song{i}.opus" for i in range(12)]
    engine = _make_engine(monkeypatch, playlist)

    engine.shuffle = True
    order = engine._shuffle_order
    assert sorted(order) == list(range(len(playlist)))
    assert len(order) == len(playlist)


def test_disabling_shuffle_clears_history(monkeypatch):
    playlist = ["C:/music/A - 1.opus", "C:/music/B - 2.opus"]
    engine = _make_engine(monkeypatch, playlist)
    engine.shuffle = True
    engine.shuffle = False
    assert engine._shuffle_order == []
    assert engine._shuffle_pos == -1


def test_queue_has_priority_over_playlist_order(tmp_path, monkeypatch):
    first = tmp_path / "a.mp3"
    second = tmp_path / "b.mp3"
    first.write_bytes(b"")
    second.write_bytes(b"")
    engine = _make_engine(monkeypatch, [str(first)])
    assert engine.add_to_queue(str(second))

    loaded = []
    monkeypatch.setattr(
        engine,
        "load_file",
        lambda path, auto_play=True, blocking=False: loaded.append(path) or True,
    )

    engine.next_track()

    assert loaded == [str(second)]
    assert engine.queue == []
    # A queued file that is not in the playlist is appended so the UI stays consistent.
    assert str(second) in engine.playlist
    assert engine.current_index == engine.playlist.index(str(second))


def test_add_remove_clear_queue(tmp_path):
    engine = CyberAudioEngine()
    track = tmp_path / "track.mp3"
    track.write_bytes(b"")

    assert engine.add_to_queue(str(track))
    assert engine.queue == [str(track)]
    assert engine.remove_from_queue(0) == str(track)
    assert engine.queue == []
    assert engine.add_to_queue(str(track))
    engine.clear_queue()
    assert engine.queue == []


def test_shuffle_never_repeats_until_all_tracks_played(monkeypatch):
    playlist = [f"C:/music/Song{i}.mp3" for i in range(10)]
    engine = _make_engine(monkeypatch, playlist)
    engine.shuffle = True

    played_sequence = []
    monkeypatch.setattr(
        engine,
        "load_file",
        lambda path, auto_play=True, blocking=False: played_sequence.append(path) or True,
    )

    # Play initial track
    engine.play_index(0)
    assert played_sequence == [playlist[0]]

    # Step through 9 more tracks to complete the 10-track playlist cycle
    for _ in range(9):
        engine.next_track()

    # Every single track in the playlist must have been played exactly once!
    assert len(played_sequence) == 10
    assert len(set(played_sequence)) == 10
    assert set(played_sequence) == set(playlist)

    # Next track must start a new cycle and NOT repeat the last song immediately
    last_song = played_sequence[-1]
    engine.next_track()
    assert len(played_sequence) == 11
    assert played_sequence[-1] != last_song


def test_wide_reach_shuffle_starts_diversely(monkeypatch):
    playlist = [f"C:/music/Artist{i} - Song{i}.opus" for i in range(20)]
    engine = _make_engine(monkeypatch, playlist)

    # Rebuilding shuffle without a fixed starting index must produce diverse starting tracks
    starting_tracks = set()
    for _ in range(50):
        engine.rebuild_shuffle_order()
        starting_tracks.add(engine._shuffle_order[0])

    # Over 50 runs across 20 tracks, wide reach should hit at least 8 unique starting songs
    assert len(starting_tracks) >= 8


def test_shuffle_toggle_never_repeats_current_on_next(monkeypatch):
    playlist = [f"C:/music/Song{i}.mp3" for i in range(6)]
    engine = _make_engine(monkeypatch, playlist)
    played = []
    monkeypatch.setattr(
        engine,
        "load_file",
        lambda path, auto_play=True, blocking=False: played.append(path) or True,
    )

    # Play initial song
    engine.play_index(0)
    assert engine.current_index == 0

    # User turns shuffle off, then turns shuffle on
    engine.shuffle = False
    engine.shuffle = True

    # Pressing Next MUST NOT replay track 0!
    engine.next_track()
    assert engine.current_index != 0
    assert played[-1] != playlist[0]

    # Repeat toggle cycle with the new current song
    curr = engine.current_index
    engine.shuffle = False
    engine.shuffle = True
    engine.next_track()
    assert engine.current_index != curr
    assert played[-1] != playlist[curr]


def test_control_panel_play_next_track_respects_queue(tmp_path, monkeypatch, qapp):
    """Ensures ControlPanel.play_next_track consumes and plays queued songs before advancing playlist."""
    from controller import ControlPanel
    from lyrics_manager import LyricsManager
    from lyrics_overlay import LyricsOverlayWindow
    from overlay import OverlayWindow

    t1 = tmp_path / "song1.mp3"
    t2 = tmp_path / "song2.mp3"
    t_queued = tmp_path / "queued_song.mp3"
    for t in (t1, t2, t_queued):
        t.write_bytes(b"")

    engine = _make_engine(monkeypatch, [str(t1), str(t2)])
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    played = []
    monkeypatch.setattr(
        engine,
        "load_file",
        lambda path, auto_play=True, blocking=False: played.append(path) or True,
    )

    # Queue a song
    assert engine.add_to_queue(str(t_queued))
    assert engine.queue == [str(t_queued)]

    # Advance track via control panel hook
    assert panel.play_next_track() is True
    assert played == [str(t_queued)]
    assert engine.queue == []

    panel.hide()
    lyrics.hide()
    overlay.hide()



def test_queue_playlist_and_indicator_integration(tmp_path, monkeypatch, qapp):
    """Ensures Queue appears as a playlist, queue indicator displays and toggles, and tracks are removed when played."""
    from controller import ControlPanel
    from lyrics_manager import LyricsManager
    from lyrics_overlay import LyricsOverlayWindow
    from overlay import OverlayWindow

    t1 = tmp_path / "song1.mp3"
    t2 = tmp_path / "song2.mp3"
    t_queued = tmp_path / "queued_song.mp3"
    for t in (t1, t2, t_queued):
        t.write_bytes(b"")

    engine = _make_engine(monkeypatch, [str(t1), str(t2)])
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    played = []
    monkeypatch.setattr(
        engine,
        "load_file",
        lambda path, auto_play=True, blocking=False: played.append(path) or True,
    )

    # Queue playlist should be an option in dropdown
    items = [panel.combo_playlist.itemText(i) for i in range(panel.combo_playlist.count())]
    assert "Queue" in items

    # Initially empty queue: indicator hidden
    assert len(engine.queue) == 0
    assert panel.btn_queue_indicator.isHidden()

    # Add song to queue
    engine.add_to_queue(str(t_queued))
    panel.refresh_queue_ui()
    assert not panel.btn_queue_indicator.isHidden()
    assert "≡ 1" in panel.btn_queue_indicator.text()

    # Click indicator toggles to Queue playlist
    panel.btn_queue_indicator.click()
    assert panel.current_playlist == "Queue"
    assert panel.combo_playlist.currentText() == "Queue"
    assert panel.list_tracks.count() == 1
    assert panel.list_tracks.item(0).data(0x0100 + 1) == str(t_queued)

    # Click indicator again toggles back to All Tracks
    panel.btn_queue_indicator.click()
    assert panel.current_playlist == "All Tracks"
    assert panel.combo_playlist.currentText() == "All Tracks"

    # Switch back to Queue to test playback removal
    panel.on_playlist_selected("Queue")
    assert panel.list_tracks.count() == 1
    item = panel.list_tracks.item(0)
    panel.on_track_double_clicked(item)

    # Song was played and removed from queue
    assert played == [str(t_queued)]
    assert engine.queue == []
    assert panel.btn_queue_indicator.isHidden()
    assert panel.list_tracks.count() == 0

    panel.hide()
    lyrics.hide()
    overlay.hide()


def test_add_to_queue_does_not_open_blank_window(tmp_path, monkeypatch, qapp):
    """Ensures adding songs to queue does not instantiate or open any unparented top-level windows."""
    from controller import ControlPanel
    from lyrics_manager import LyricsManager
    from lyrics_overlay import LyricsOverlayWindow
    from overlay import OverlayWindow
    from PyQt6.QtWidgets import QApplication

    t1 = tmp_path / "song1.mp3"
    t1.write_bytes(b"")

    engine = _make_engine(monkeypatch, [str(t1)])
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    top_levels_before = set(QApplication.topLevelWidgets())

    # Trigger queue on the row widget directly
    row_widget = panel.list_tracks.itemWidget(panel.list_tracks.item(0))
    assert row_widget is not None
    row_widget._on_queue_clicked()

    top_levels_after = set(QApplication.topLevelWidgets())
    new_top_levels = [w for w in (top_levels_after - top_levels_before) if w.isVisible()]

    # Zero new visible top-level windows should have opened!
    assert len(new_top_levels) == 0
    assert str(t1) in engine.queue

    panel.hide()
    lyrics.hide()
    overlay.hide()

