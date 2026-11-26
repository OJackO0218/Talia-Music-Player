"""
Unit tests for Discord Rich Presence Service.
Verifies payload parsing, track name extraction, and graceful failure handling.
"""

from discord_service import DiscordRpcService, parse_track_info


def test_parse_track_info():
    assert parse_track_info("Colicchie - Worth It.opus") == ("Worth It", "Colicchie")
    assert parse_track_info("Juice WRLD - Lucid Dreams.mp3") == ("Lucid Dreams", "Juice WRLD")
    assert parse_track_info("SoloTrack.flac") == ("SoloTrack", "")
    assert parse_track_info("") == ("Unknown Track", "")
    # Sequential Spotify playlist numbering formats
    assert parse_track_info("01. Lin-Manuel Miranda - Alexander Hamilton.opus") == ("Alexander Hamilton", "Lin-Manuel Miranda")
    assert parse_track_info("02 - Lin-Manuel Miranda - Aaron Burr, Sir.opus") == ("Aaron Burr, Sir", "Lin-Manuel Miranda")
    assert parse_track_info("100. Artist - Song.opus") == ("Song", "Artist")


def test_discord_service_lifecycle_without_discord():
    """Ensures DiscordRpcService initializes and updates without errors even if Discord is not connected."""
    service = DiscordRpcService(enabled=False)
    assert service.enabled is False

    # Enable and push updates
    service.set_enabled(True)
    assert service.enabled is True

    service.update_playback("Test Artist - Test Song.opus", True, 10.0, 180.0)
    service.update_playback("Test Artist - Test Song.opus", False, 15.0, 180.0)

    # Disable cleanly
    service.set_enabled(False)
    service.stop()


def test_discord_payload_uses_current_app_version():
    """Ensures Discord RPC payload text stays synchronized with config.APP_VERSION."""
    from config import APP_VERSION

    service = DiscordRpcService(enabled=False)
    payload_idle = service._build_payload("", False, None, None)
    assert payload_idle["large_text"] == f"Talia Music Player v{APP_VERSION}"

    payload_playing = service._build_payload("Artist - Song.opus", True, 0, 180)
    assert payload_playing["large_text"] == f"Talia Music Player v{APP_VERSION}"
    assert f"v{APP_VERSION}" in payload_playing["small_text"]
    assert payload_playing["buttons"][0]["label"] == f"Talia v{APP_VERSION} on GitHub"

    payload_radio = service._build_payload("Artist - Song.opus", True, 0, 180, mode_hint="Random Mix")
    assert payload_radio["small_text"] == "Random Mix • Playing"

    payload_desktop = service._build_payload("Desktop Audio", True, 0, 0, mode_hint="Desktop Audio")
    assert payload_desktop["details"] == "Desktop Audio Loopback"
    assert f"v{APP_VERSION}" in payload_desktop["small_text"]
