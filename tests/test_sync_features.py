"""
Tests for Party Sync (Listen Together) and Spotify Sync & Playlist Import.
"""

import time
import pytest
from PyQt6.QtCore import QCoreApplication

from party_sync import PartySyncService, generate_room_code
from spotify_sync import SpotifySyncService
from party_dialog import PartySyncDialog
from spotify_dialog import SpotifySyncDialog
from audio_engine import CyberAudioEngine
from lyrics_manager import LyricsManager
from lyrics_overlay import LyricsOverlayWindow
from overlay import OverlayWindow
from controller import ControlPanel


def test_room_code_generation():
    code = generate_room_code()
    assert len(code) == 5
    assert code.isupper()
    assert code.isalnum()


def test_spotify_extract_playlist_id():
    svc = SpotifySyncService()
    # Standard web link
    url1 = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abcd1234"
    assert svc.extract_playlist_id(url1) == "37i9dQZF1DXcBWIGoYBM5M"

    # Album web link
    url2 = "https://open.spotify.com/album/4LH4d3cOWNNXdsqFd4B7f4"
    assert svc.extract_playlist_id(url2) == "4LH4d3cOWNNXdsqFd4B7f4"

    # Raw 22-char ID
    assert svc.extract_playlist_id("37i9dQZF1DXcBWIGoYBM5M") == "37i9dQZF1DXcBWIGoYBM5M"

    # Invalid string
    assert svc.extract_playlist_id("not-a-spotify-url") is None


def test_spotify_time_formatting():
    assert SpotifySyncService._format_ms(0) == "--:--"
    assert SpotifySyncService._format_ms(185000) == "03:05"
    assert SpotifySyncService._format_ms(65000) == "01:05"


@pytest.mark.gui
def test_party_and_spotify_dialogs_construct(qapp):
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    assert hasattr(panel, "party_sync")
    assert hasattr(panel, "party_dialog")
    assert hasattr(panel, "spotify_service")
    assert hasattr(panel, "spotify_dialog")

    assert isinstance(panel.party_dialog, PartySyncDialog)
    assert isinstance(panel.spotify_dialog, SpotifySyncDialog)

    # Test HUD badge update
    panel.update_party_hud(True, "NEON7", True)
    assert "HOST: NEON7" in panel.btn_party_sync.text()

    panel.update_party_hud(False, "", False)
    assert "Listen Together" in panel.btn_party_sync.text()

    panel.party_dialog.hide()
    panel.spotify_dialog.hide()
    panel.hide()
    lyrics.hide()
    overlay.hide()


def test_party_sync_local_exchange():
    """Starts local party server and verifies message delivery between Host and Guest."""
    host_svc = PartySyncService()
    _app = QCoreApplication.instance() or QCoreApplication([])
    guest_svc = PartySyncService()

    host_connected = []
    guest_connected = []
    received_tracks = []
    received_plays = []
    received_pauses = []
    received_seeks = []

    host_svc.connected.connect(lambda code, is_h, mem: host_connected.append(code))
    guest_svc.connected.connect(lambda code, is_h, mem: guest_connected.append(code))
    guest_svc.track_received.connect(lambda d: received_tracks.append(d))
    guest_svc.play_received.connect(lambda ts: received_plays.append(ts))
    guest_svc.pause_received.connect(lambda ts: received_pauses.append(ts))
    guest_svc.seek_received.connect(lambda ts: received_seeks.append(ts))

    # Start local server on test port 9876
    test_port = 9876
    host_svc.host_local_server(port=test_port, room_code="SYNC1", user_name="Alice")

    # Give server a moment to spin up
    for _ in range(50):
        QCoreApplication.processEvents()
        if host_connected:
            break
        time.sleep(0.05)

    assert len(host_connected) == 1
    assert host_connected[0] == "SYNC1"

    # Guest joins local server
    guest_svc.join_session("SYNC1", user_name="Bob", relay_url=f"ws://127.0.0.1:{test_port}")

    for _ in range(50):
        QCoreApplication.processEvents()
        if guest_connected:
            break
        time.sleep(0.05)

    assert len(guest_connected) == 1

    # Host broadcasts track change
    host_svc.broadcast_track(
        title="Language",
        artist="Porter Robinson",
        filename="Porter Robinson - Language.opus",
        duration=210.0,
        timestamp=10.5,
        is_playing=True,
    )

    # Host broadcasts play, pause, seek, reaction
    host_svc.broadcast_play(15.2)
    host_svc.broadcast_pause(15.2)
    host_svc.broadcast_seek(45.0)

    for _ in range(25):
        QCoreApplication.processEvents()
        if received_tracks and received_plays and received_pauses and received_seeks:
            break
        time.sleep(0.05)

    assert len(received_tracks) >= 1
    assert received_tracks[0]["title"] == "Language"
    assert received_tracks[0]["artist"] == "Porter Robinson"

    assert len(received_plays) >= 1
    assert received_plays[0] == 15.2

    assert len(received_pauses) >= 1
    assert received_pauses[0] == 15.2

    assert len(received_seeks) >= 1
    assert received_seeks[0] == 45.0


    # Cleanup
    host_svc.disconnect_session()
    guest_svc.disconnect_session()
    for _ in range(10):
        QCoreApplication.processEvents()
        time.sleep(0.05)

def test_party_host_session_auto_starts_embedded():
    """Verifies that calling host_session() automatically starts the local relay and connects."""
    svc = PartySyncService()
    connected_events = []
    svc.connected.connect(lambda code, is_h, mem: connected_events.append((code, is_h, mem)))

    # Call host_session directly with no external relay running
    svc.host_session(room_code="AUTO1", user_name="HostAlice", relay_url="")

    for _ in range(25):
        QCoreApplication.processEvents()
        if connected_events:
            break
        time.sleep(0.05)

    assert len(connected_events) == 1
    code, is_h, mem = connected_events[0]
    assert code == "AUTO1"
    assert is_h is True
    assert "HostAlice" in mem
    assert svc.is_connected is True

    svc.disconnect_session()
    for _ in range(10):
        QCoreApplication.processEvents()
        time.sleep(0.05)


def test_spotify_saved_playlists_management():
    """Verifies saving, retrieving, and deleting personal Spotify playlists."""
    svc = SpotifySyncService()
    initial_count = len(svc.get_saved_playlists())
    assert initial_count >= 1

    test_url = "https://open.spotify.com/playlist/test123456789012345678"
    svc.save_custom_playlist("My Test Party", test_url)

    saved = svc.get_saved_playlists()
    assert len(saved) == initial_count + 1
    assert any(p["name"] == "My Test Party" and p["url"] == test_url for p in saved)

    # Delete
    deleted = svc.delete_saved_playlist(test_url)
    assert deleted is True
    assert len(svc.get_saved_playlists()) == initial_count


def test_spotify_dialog_batch_download_ui_states(qapp):
    """Verifies that starting batch download updates button to Stop Download and shows progress."""
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)
    dlg = panel.spotify_dialog
    dlg.show()

    # Simulate loaded tracks
    dlg._on_playlist_loaded({
        "title": "Neon Dreams",
        "owner": "Tester",
        "tracks": [
            {"title": "Track 1", "artist": "Artist 1", "duration_str": "3:00", "query": "Artist 1 - Track 1"},
            {"title": "Track 2", "artist": "Artist 2", "duration_str": "3:30", "query": "Artist 2 - Track 2"},
        ]
    })

    assert dlg.btn_download_selected.isEnabled() is True
    assert "Download Selected Tracks (2 Songs)" in dlg.btn_download_selected.text()
    assert dlg.progress_bar.isVisible() is False

    # Start download
    dlg._on_download_toggle_clicked()
    assert dlg._is_batch_downloading is True
    assert "Stop Download" in dlg.btn_download_selected.text()
    assert dlg.progress_bar.isVisible() is True

    # User cancels download
    dlg._on_download_toggle_clicked()
    assert dlg._stop_download_flag is True

    if hasattr(dlg, "_worker_thread") and dlg._worker_thread:
        dlg._worker_thread.join(timeout=1.0)

    # Cleanup
    dlg.hide()
    panel.hide()
    lyrics.hide()
    overlay.hide()


def test_party_sync_host_transfer_and_auto_close():
    """Tests host transfer and auto-closure on host departure between PartySyncService instances."""
    host_svc = PartySyncService()
    _app = QCoreApplication.instance() or QCoreApplication([])
    guest_svc = PartySyncService()

    host_connected = []
    guest_connected = []
    transferred_events = []
    guest_errors = []

    host_svc.connected.connect(lambda code, is_h, mem: host_connected.append(code))
    guest_svc.connected.connect(lambda code, is_h, mem: guest_connected.append(code))
    guest_svc.host_transferred.connect(lambda new_h, old_h: transferred_events.append((new_h, old_h)))
    guest_svc.error_occurred.connect(lambda err: guest_errors.append(err))

    test_port = 9888
    host_svc.host_local_server(port=test_port, room_code="TRANS1", user_name="Alice")

    for _ in range(50):
        QCoreApplication.processEvents()
        if host_connected:
            break
        time.sleep(0.05)

    assert len(host_connected) == 1
    assert host_svc.is_host is True

    guest_svc.join_session("TRANS1", user_name="Bob", relay_url=f"ws://127.0.0.1:{test_port}")

    for _ in range(50):
        QCoreApplication.processEvents()
        if guest_connected:
            break
        time.sleep(0.05)

    assert len(guest_connected) == 1
    assert guest_svc.is_host is False

    # 1. Host transfers role to Bob
    host_svc.transfer_host("Bob")

    for _ in range(30):
        QCoreApplication.processEvents()
        if transferred_events:
            break
        time.sleep(0.05)

    assert len(transferred_events) == 1
    assert transferred_events[0] == ("Bob", "Alice")
    assert guest_svc.is_host is True
    assert host_svc.is_host is False

    # Cleanup
    host_svc.disconnect_session()
    guest_svc.disconnect_session()


def test_party_sync_reject_phantom_room():
    """Verifies that joining a non-existent room without a host is rejected."""
    _app = QCoreApplication.instance() or QCoreApplication([])
    guest_svc = PartySyncService()
    connected_list = []
    error_list = []

    guest_svc.connected.connect(lambda code, is_h, mem: connected_list.append(code))
    guest_svc.error_occurred.connect(lambda err: error_list.append(err))

    # Join random room with no host online
    guest_svc.join_session("NO_HOST_ROOM_XYZ", user_name="Bob", relay_url="wss://soft-mongoose-6754.ojacko0218.deno.net")

    for _ in range(120):
        QCoreApplication.processEvents()
        if error_list:
            break
        time.sleep(0.05)

    guest_svc.disconnect_session()
    assert len(connected_list) == 0
    assert len(error_list) >= 1
    assert "does not exist or host is offline" in error_list[0]


def test_pick_best_youtube_result():
    from song_downloader import pick_best_youtube_result
    candidates = [
        {
            "id": "vid_bad_cov",
            "title": "Alexander Hamilton (Cover by John)",
            "channel": "John Music",
            "duration": 220,
            "url": "https://youtube.com/watch?v=cov",
        },
        {
            "id": "vid_mv",
            "title": "Alexander Hamilton (Official Music Video)",
            "channel": "Atlantic Records",
            "duration": 315,  # Has 80s dialogue skit
            "url": "https://youtube.com/watch?v=mv",
        },
        {
            "id": "vid_topic",
            "title": "Alexander Hamilton",
            "channel": "Lin-Manuel Miranda - Topic",
            "duration": 236,  # Exact album duration!
            "url": "https://youtube.com/watch?v=exact",
        },
    ]

    best = pick_best_youtube_result(
        candidates,
        target_title="Alexander Hamilton",
        target_artist="Lin-Manuel Miranda",
        target_duration=236.0,
    )
    assert best is not None
    assert best["id"] == "vid_topic"
    assert best["url"] == "https://youtube.com/watch?v=exact"


@pytest.mark.gui
def test_find_matching_party_track(qapp, tmp_path):
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    # Setup playlist with various tracks
    t1 = str(tmp_path / "01. Zara Larsson - Symphony.mp3")
    t2 = str(tmp_path / "05. Lin-Manuel Miranda - Alexander Hamilton.mp3")
    t3 = str(tmp_path / "99. YOASOBI - Idol.mp3")
    for t in (t1, t2, t3):
        with open(t, "w") as f:
            f.write("audio")

    engine.playlist = [t1, t2, t3]

    # Host sends opus filename with track numbering from spotify
    host_data = {
        "title": "Alexander Hamilton",
        "artist": "Lin-Manuel Miranda",
        "filename": "01. Lin-Manuel Miranda - Alexander Hamilton.opus",
        "duration": 236.4,
    }
    idx = panel.find_matching_party_track(host_data)
    assert idx == 1  # Matches t2 despite prefix differences and extension differences

    # Test that substring false positives are rejected
    false_data = {
        "title": "Sym",  # Substring of Symphony
        "artist": "Another Artist",
        "filename": "Another Artist - Sym.opus",
    }
    idx_false = panel.find_matching_party_track(false_data)
    assert idx_false == -1

    panel.hide()
    lyrics.hide()
    overlay.hide()


@pytest.mark.gui
def test_party_track_downloaded_exact_playback(qapp, tmp_path):
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    # Guest has existing tracks: Track A, Track Z
    track_a = str(tmp_path / "A_Track.mp3")
    track_z = str(tmp_path / "Z_Track.mp3")
    track_hamilton = str(tmp_path / "Hamilton.mp3")
    for t in (track_a, track_z, track_hamilton):
        with open(t, "w") as f:
            f.write("dummy")

    engine.playlist = [track_a, track_hamilton, track_z]
    engine.folder_path = str(tmp_path)

    played_indices = []
    engine.play_index = lambda idx, *args, **kwargs: played_indices.append(idx)

    # When track_hamilton is downloaded, it must play index 1 (Hamilton), NOT index 2 (Z_Track / len - 1)!
    panel._on_party_track_downloaded(str(tmp_path), target_time=15.0, target_playing=True, file_path=track_hamilton)

    assert len(played_indices) == 1
    assert played_indices[0] == 1  # Played Hamilton, NOT Z_Track!

    panel.hide()
    lyrics.hide()
    overlay.hide()



def test_updater_semver_parsing():
    from updater import parse_semver

    assert parse_semver("v2.4.0") == (2, 4, 0)
    assert parse_semver("2.3.1") == (2, 3, 1)
    assert parse_semver("v1.0.0-beta") == (1, 0, 0)
    assert parse_semver("2.4.0") > parse_semver("2.3.1")
    assert parse_semver("2.3.1") == parse_semver("v2.3.1")


def test_party_shared_queue_permissions():
    """Verifies that everyone can add to party queue, but non-hosts can only remove their own tracks."""
    svc = PartySyncService()
    svc.is_connected = True
    svc.is_host = False
    svc.user_name = "Alice"

    # Alice adds a song
    svc.add_to_party_queue(title="Song A", artist="Artist A", filename="songA.mp3")
    assert len(svc.party_queue) == 1
    alice_item_id = svc.party_queue[0]["id"]
    assert svc.party_queue[0]["added_by"] == "Alice"

    # Bob's song is added via sync
    bob_item = {
        "id": "item_bob_123",
        "title": "Song B",
        "artist": "Artist B",
        "filename": "songB.mp3",
        "added_by": "Bob",
    }
    svc.party_queue.append(bob_item)
    assert len(svc.party_queue) == 2

    # Alice tries to remove Bob's song -> should fail!
    assert svc.remove_from_party_queue("item_bob_123") is False
    assert len(svc.party_queue) == 2

    # Alice removes her own song -> should succeed!
    assert svc.remove_from_party_queue(alice_item_id) is True
    assert len(svc.party_queue) == 1
    assert svc.party_queue[0]["id"] == "item_bob_123"

    # Host can remove Bob's song
    svc.is_host = True
    assert svc.remove_from_party_queue("item_bob_123") is True
    assert len(svc.party_queue) == 0


def test_audio_engine_device_recovery():
    """Tests that audio engine can recreate its stream and handle device reset safely."""
    engine = CyberAudioEngine()
    engine.sr = 44100
    engine.channels = 2

    # Recreate stream with device re-init
    res = engine.recreate_stream(force_reinit_device=True)
    assert res is True
    assert engine.stream is not None

    # Handle device changed
    res2 = engine.handle_device_changed(resume_playback=False)
    assert res2 is True


@pytest.mark.gui
def test_controller_queue_persistence(qapp, tmp_path):
    """Tests that ControlPanel restores queue from settings and saves queue back."""
    import os

    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    # Create dummy track files
    track1 = str(tmp_path / "track1.mp3")
    track2 = str(tmp_path / "track2.mp3")
    with open(track1, "w") as f:
        f.write("t1")
    with open(track2, "w") as f:
        f.write("t2")

    cfg = {
        "queue": [track1, track2, "non_existent.mp3"],
    }
    panel.apply_settings(cfg)

    # Valid existing tracks are restored, non-existent filtered
    assert len(engine.queue) == 2
    assert engine.queue[0] == os.path.normpath(track1)
    assert engine.queue[1] == os.path.normpath(track2)

    # Settings dict includes the restored queue
    saved = panel.get_current_settings_dict()
    assert "queue" in saved
    assert len(saved["queue"]) == 2

    panel.hide()
    lyrics.hide()
    overlay.hide()


@pytest.mark.gui
def test_settings_talia_center_and_sliders(qapp):
    """Tests Center Talia button and X/Y position sliders in Settings."""
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)
    settings = panel.settings_dialog

    assert hasattr(settings, "btn_center_talia")
    assert hasattr(settings, "slider_pos_x")
    assert hasattr(settings, "slider_pos_y")

    # Center Talia
    settings.center_talia_on_screen()
    screen = qapp.primaryScreen().availableGeometry()
    expected_cx = screen.left() + (screen.width() - overlay.width()) // 2
    expected_cy = screen.top() + (screen.height() - overlay.height()) // 2
    assert overlay.x() == expected_cx
    assert overlay.y() == expected_cy

    # Move sliders
    settings.slider_pos_x.setValue(screen.left() + 150)
    assert overlay.x() == screen.left() + 150
    settings.slider_pos_y.setValue(screen.top() + 200)
    assert overlay.y() == screen.top() + 200

    panel.hide()
    lyrics.hide()
    overlay.hide()
    settings.hide()


@pytest.mark.gui
def test_dialog_screen_clamping_and_transfer_host(qapp):
    """Tests screen clamping mixin and Transfer Host visibility in PartySyncDialog."""
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    party_dlg = PartySyncDialog(panel)
    party_dlg.sync_service.is_host = True
    party_dlg.sync_service.room_code = "TEST01"
    party_dlg._update_transfer_ui()

    # Transfer host UI frame must remain visible for host even when alone
    assert not party_dlg.frame_transfer.isHidden()

    # Center and clamp on screen
    party_dlg.center_and_clamp_on_screen()
    screen = qapp.primaryScreen().availableGeometry()
    assert party_dlg.y() >= screen.top() + 30
    assert party_dlg.x() >= screen.left()

    panel.hide()
    lyrics.hide()
    overlay.hide()
    party_dlg.hide()


def test_audio_engine_play_next_hook():
    """Tests that play_next_hook intercepts next_track calls."""
    engine = CyberAudioEngine()
    hook_called = False

    def custom_hook(*args, **kwargs):
        nonlocal hook_called
        hook_called = True
        return True

    engine.play_next_hook = custom_hook
    engine.next_track()
    assert hook_called is True


@pytest.mark.gui
def test_party_queue_song_title_matching_and_no_talia_prefix(qapp, tmp_path):
    """Tests that queuing just a song name matches a local file and never injects Talia Music Player."""
    engine = CyberAudioEngine()
    track_file = str(tmp_path / "Queen - Bohemian Rhapsody.mp3")
    with open(track_file, "w") as f:
        f.write("dummy audio")
    engine.playlist = [track_file]
    engine.current_index = 0

    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    # Simulate room connection
    panel.party_sync.is_connected = True
    panel.party_sync.is_host = True

    # Queue just the song title
    item = panel.party_sync.add_to_party_queue(title="Bohemian Rhapsody")
    assert "talia music player" not in item.get("artist", "").lower()
    assert "talia music player" not in item.get("yt_query", "").lower()
    assert item.get("title") == "Bohemian Rhapsody"

    # Must match local "Queen - Bohemian Rhapsody.mp3"
    idx = panel.find_matching_party_track(item)
    assert idx == 0

    panel.hide()
    lyrics.hide()
    overlay.hide()


@pytest.mark.gui
def test_party_guest_does_not_advance_local_playlist(qapp, tmp_path):
    """Tests that a party guest never auto-advances their local playlist."""
    engine = CyberAudioEngine()
    track1 = str(tmp_path / "Song1.mp3")
    track2 = str(tmp_path / "Song2.mp3")
    with open(track1, "w") as f:
        f.write("1")
    with open(track2, "w") as f:
        f.write("2")
    engine.playlist = [track1, track2]
    engine.current_index = 0

    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    # Connected as GUEST
    panel.party_sync.is_connected = True
    panel.party_sync.is_host = False

    result = panel.play_next_track()
    assert result is False
    assert engine.current_index == 0  # Did not advance

    panel.hide()
    lyrics.hide()
    overlay.hide()


@pytest.mark.gui
def test_party_downloading_holds_advance(qapp, tmp_path):
    """Tests that play_next_track holds when a party track is being downloaded."""
    engine = CyberAudioEngine()
    track1 = str(tmp_path / "Song1.mp3")
    with open(track1, "w") as f:
        f.write("1")
    engine.playlist = [track1]
    engine.current_index = 0

    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    panel.party_sync.is_connected = True
    panel.party_sync.is_host = True
    panel._party_downloading_track = {"title": "Pending Song"}

    result = panel.play_next_track()
    assert result is False

    panel.hide()
    lyrics.hide()
    overlay.hide()


@pytest.mark.gui
def test_party_queue_prefetches_only_first_track(qapp, tmp_path):
    """Tests that Talia only pre-downloads the immediate next song in queue (index 0), not subsequent ones."""
    engine = CyberAudioEngine()
    current_track = str(tmp_path / "CurrentSong.mp3")
    with open(current_track, "w") as f:
        f.write("audio")
    engine.playlist = [current_track]
    engine.current_index = 0

    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    panel.party_sync.is_connected = True
    panel.party_sync.is_host = True

    prefetched = []
    def fake_run_prefetch(track_data):
        prefetched.append(track_data.get("id"))

    panel._run_prefetch_next_track = fake_run_prefetch

    # Add 3 songs to party queue
    item1 = panel.party_sync.add_to_party_queue(title="Song1")
    item2 = panel.party_sync.add_to_party_queue(title="Song2")
    item3 = panel.party_sync.add_to_party_queue(title="Song3")

    assert len(panel.party_sync.party_queue) == 3

    # Trigger prefetch check
    panel._check_and_prefetch_next_in_queue()

    # ONLY item1 (index 0) must be prefetched! Item 2 and 3 must NOT be prefetched!
    assert len(prefetched) == 1
    assert prefetched[0] == item1.get("id")

    # When prefetch completes, file is added to playlist without interrupting playback
    dummy_file = str(tmp_path / "Downloaded_Song1.opus")
    with open(dummy_file, "w") as f:
        f.write("downloaded")
    panel._on_prefetch_completed(True, dummy_file, item1)

    assert dummy_file in panel.audio_engine.playlist
    assert panel.audio_engine.current_index == 0  # Still on current track!

    panel.hide()
    lyrics.hide()
    overlay.hide()



