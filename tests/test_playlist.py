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


def test_lyrics_manager_clear_lyrics():
    from lyrics_manager import LyricsManager
    mgr = LyricsManager()
    mgr.lines = [(1.0, "Test"), (2.0, "Line")]
    mgr.has_lyrics = True
    mgr.current_track_path = "C:/fake/track.mp3"
    mgr.current_lrc_path = "C:/fake/track.lrc"
    mgr.manual_offset = 1.5
    mgr.file_offset = -0.5

    mgr.clear_lyrics()
    assert mgr.lines == []
    assert mgr.has_lyrics is False
    assert mgr.current_track_path == ""
    assert mgr.current_lrc_path == ""
    assert mgr.manual_offset == 0.0
    assert mgr.file_offset == 0.0


def test_lyrics_overlay_reset_display(qapp):
    from audio_engine import CyberAudioEngine
    from lyrics_manager import LyricsManager
    from lyrics_overlay import LyricsOverlayWindow
    engine = CyberAudioEngine()
    mgr = LyricsManager()
    overlay = LyricsOverlayWindow(engine, mgr)
    overlay.displayed_text = "Singing words"
    overlay.current_line_idx = 3
    overlay.line_opacity = 1.0

    overlay.reset_lyrics_display()
    assert overlay.displayed_text == ""
    assert overlay.current_line_idx == -1
    assert overlay.line_opacity == 0.0
    overlay.hide()


def test_delete_track_lyrics(tmp_path, qapp):
    from audio_engine import CyberAudioEngine
    from controller import ControlPanel
    from lyrics_manager import LyricsManager
    from lyrics_overlay import LyricsOverlayWindow
    from overlay import OverlayWindow

    song_file = tmp_path / "test_track.mp3"
    song_file.write_bytes(b"dummy audio")
    lrc_file = tmp_path / "test_track.lrc"
    lrc_file.write_text("[00:01.00] Test lyric line", encoding="utf-8")

    engine = CyberAudioEngine()
    mgr = LyricsManager()
    lyrics = LyricsOverlayWindow(engine, mgr)
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    local_lrc, cached_lrc = panel.get_track_lyrics_paths(str(song_file))
    assert local_lrc == str(lrc_file)

    # Delete lyric only
    panel.delete_track_lyrics(str(song_file), confirm=False)
    assert not lrc_file.exists()
    assert song_file.exists()

    panel.hide()
    lyrics.hide()
    overlay.hide()


def test_delete_track_and_lyrics(tmp_path, qapp):
    from audio_engine import CyberAudioEngine
    from controller import ControlPanel
    from lyrics_manager import LyricsManager
    from lyrics_overlay import LyricsOverlayWindow
    from overlay import OverlayWindow

    song_file1 = tmp_path / "track1.mp3"
    song_file1.write_bytes(b"dummy audio 1")
    lrc_file1 = tmp_path / "track1.lrc"
    lrc_file1.write_text("[00:01.00] Lyric 1", encoding="utf-8")

    song_file2 = tmp_path / "track2.mp3"
    song_file2.write_bytes(b"dummy audio 2")

    engine = CyberAudioEngine()
    engine.folder_path = str(tmp_path)
    engine.refresh_playlist()

    mgr = LyricsManager()
    lyrics = LyricsOverlayWindow(engine, mgr)
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)
    panel.refresh_tracklist()

    assert len(engine.playlist) == 2

    # Delete song 1 and its lyrics
    panel.delete_track_and_lyrics(str(song_file1), orig_idx=0, confirm=False)

    assert not song_file1.exists()
    assert not lrc_file1.exists()
    assert song_file2.exists()
    assert len(engine.playlist) == 1
    assert engine.playlist[0] == str(song_file2)

    panel.hide()
    lyrics.hide()
    overlay.hide()


def test_show_in_explorer_command(tmp_path, monkeypatch):
    import subprocess
    from playlist_panel import PlaylistPanelMixin
    mixin = PlaylistPanelMixin()
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd: calls.append(cmd))

    test_file = tmp_path / "Track 01.mp3"
    test_file.write_bytes(b"")
    mixin.show_in_explorer(str(test_file))
    assert len(calls) == 1
    assert calls[0].startswith("explorer /select,")
    assert str(test_file) in calls[0]

