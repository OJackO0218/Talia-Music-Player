"""
Tests for rapid spam clicking and switching between Listen Together (PartySyncDialog)
and Spotify Sync (SpotifySyncDialog) to verify zero bugged state or unopenable dialogs.
"""

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from audio_engine import CyberAudioEngine
from lyrics_overlay import LyricsManager, LyricsOverlayWindow
from overlay import OverlayWindow
from controller import ControlPanel


def test_rapid_toggle_party_dialog(qapp):
    """Verifies that clicking party sync button repeatedly cleanly toggles on/off without getting stuck."""
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)
    panel.show()
    qapp.processEvents()

    # Toggle 20 times rapidly
    for i in range(20):
        panel.open_party_dialog()
        qapp.processEvents()
        expected = (i % 2 == 0)
        assert panel.party_dialog.isVisible() == expected

    # Ensure hidden
    panel.party_dialog.hide()
    panel.spotify_dialog.hide()
    panel.close()
    overlay.close()


def test_rapid_alternating_switch_party_and_spotify(qapp):
    """Verifies that spamming between Spotify and Party sync buttons never corrupts dialog state."""
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)
    panel.show()
    qapp.processEvents()

    for _ in range(50):
        panel.open_party_dialog()
        qapp.processEvents()
        assert panel.party_dialog.isVisible() is True
        assert panel.spotify_dialog.isVisible() is False

        panel.open_spotify_dialog()
        qapp.processEvents()
        assert panel.party_dialog.isVisible() is False
        assert panel.spotify_dialog.isVisible() is True

    # After 50 alternating switches, test opening party dialog again
    panel.open_party_dialog()
    qapp.processEvents()
    assert panel.party_dialog.isVisible() is True
    assert panel.spotify_dialog.isVisible() is False

    # Close party dialog
    panel.open_party_dialog()
    qapp.processEvents()
    assert panel.party_dialog.isVisible() is False

    # Reopen party dialog cleanly
    panel.open_party_dialog()
    qapp.processEvents()
    assert panel.party_dialog.isVisible() is True

    panel.party_dialog.hide()
    panel.spotify_dialog.hide()
    panel.close()
    overlay.close()


def test_minimized_dialog_recovery(qapp):
    """Verifies that if a dialog is minimized, opening it un-minimizes and displays properly."""
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)
    panel.show()
    qapp.processEvents()

    # Show then minimize party dialog
    panel.open_party_dialog()
    qapp.processEvents()
    panel.party_dialog.showMinimized()
    qapp.processEvents()

    # Close/hide and reopen
    panel.party_dialog.hide()
    qapp.processEvents()
    panel.open_party_dialog()
    qapp.processEvents()

    assert panel.party_dialog.isVisible() is True
    assert panel.party_dialog.isMinimized() is False

    panel.party_dialog.hide()
    panel.spotify_dialog.hide()
    panel.close()
    overlay.close()


def test_dialog_close_event_safe_hiding(qapp):
    """Verifies that closeEvent and reject on both dialogs safely hide instead of destroying."""
    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)
    panel.show()
    qapp.processEvents()

    # Party dialog close()
    panel.party_dialog.show()
    qapp.processEvents()
    assert panel.party_dialog.isVisible() is True
    panel.party_dialog.close()
    qapp.processEvents()
    assert panel.party_dialog.isVisible() is False

    # Party dialog reject()
    panel.party_dialog.show()
    qapp.processEvents()
    panel.party_dialog.reject()
    qapp.processEvents()
    assert panel.party_dialog.isVisible() is False

    # Spotify dialog close()
    panel.spotify_dialog.show()
    qapp.processEvents()
    assert panel.spotify_dialog.isVisible() is True
    panel.spotify_dialog.close()
    qapp.processEvents()
    assert panel.spotify_dialog.isVisible() is False

    # Spotify dialog reject()
    panel.spotify_dialog.show()
    qapp.processEvents()
    panel.spotify_dialog.reject()
    qapp.processEvents()
    assert panel.spotify_dialog.isVisible() is False

    panel.close()
    overlay.close()
