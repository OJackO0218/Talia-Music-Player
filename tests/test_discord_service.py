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
