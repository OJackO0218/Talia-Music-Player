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
