"""Tests for playlist scanning and the folder-switch regression."""

from audio_engine import CyberAudioEngine


def _touch(path):
    path.write_bytes(b"")
    return str(path)


def test_refresh_playlist_scans_subfolders(tmp_path):
    album = tmp_path / "Album"
    album.mkdir()
    _touch(tmp_path / "root.mp3")
    _touch(album / "nested.opus")
    _touch(tmp_path / "ignore.txt")

    engine = CyberAudioEngine()
    engine.folder_path = str(tmp_path)
    engine.refresh_playlist()

    assert len(engine.playlist) == 2
    assert engine.current_index == 0


def test_switching_folders_stops_the_old_track(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _touch(first / "old.mp3")
    _touch(second / "new.mp3")

    engine = CyberAudioEngine()
    engine.folder_path = str(first)
    engine.refresh_playlist()
    engine.current_index = 0
    engine.is_playing = True
    engine.is_paused = False

    engine.folder_path = str(second)
    engine.refresh_playlist()

    assert engine.playlist[0].endswith("new.mp3")
    assert engine.current_index == 0
    assert engine.is_playing is False
    assert engine.is_paused is True
    assert engine.track_finished is False


def test_missing_folder_clears_playlist(tmp_path):
    engine = CyberAudioEngine()
    engine.folder_path = str(tmp_path / "does-not-exist")
    engine.refresh_playlist()
    assert engine.playlist == []
    assert engine.current_index == -1
