"""Tests for shuffle balancing and queue prioritisation."""

from audio_engine import CyberAudioEngine


def _make_engine(monkeypatch, playlist):
    engine = CyberAudioEngine()
    monkeypatch.setattr(engine, "_trigger_preload_next", lambda: None)
    engine.playlist = list(playlist)
    engine.current_index = 0
    return engine


def test_balanced_shuffle_covers_every_track(monkeypatch):
    playlist = [f"C:/music/Artist{i % 3} - Song{i}.opus" for i in range(12)]
    engine = _make_engine(monkeypatch, playlist)

    engine.shuffle = True
    order = engine._shuffle_order
    assert sorted(order) == list(range(len(playlist)))

    keys = [engine._extract_cluster_key(playlist[i]) for i in order]
    for left, right in zip(keys, keys[1:]):
        if left == right:
            # Only acceptable when one artist dominates the playlist.
            assert keys.count(left) > len(keys) / 2


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
