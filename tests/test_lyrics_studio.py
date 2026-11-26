"""Tests for integrated LyricsStudioDialog and clean tabbed SettingsDialog."""

import os
from unittest.mock import patch

import pytest

from audio_engine import CyberAudioEngine
from controller import ControlPanel
from lyrics_manager import LyricsManager
from lyrics_overlay import LyricsOverlayWindow
from overlay import OverlayWindow


@pytest.fixture(scope="module")
def studio_env(qapp):
    engine = CyberAudioEngine()
    l_mgr = LyricsManager()
    l_overlay = LyricsOverlayWindow(engine, l_mgr)
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, l_overlay)
    yield panel, engine, l_mgr
    if getattr(panel, "_lyrics_fetcher_win", None) is not None:
        panel._lyrics_fetcher_win.hide()
    panel.hide()
    l_overlay.hide()
    overlay.hide()


def test_settings_dialog_has_clean_tabs_and_required_widgets(studio_env):
    panel, _, _ = studio_env
    sd = panel.settings_dialog
    assert sd.tabs.count() == 4
    for attr in (
        "lbl_folder_path",
        "btn_open_fetcher",
        "combo_font",
        "slider_lyric_size",
        "combo_lyric_color",
        "btn_pick_color",
        "chk_word_glow",
        "chk_dialogue_mode",
        "chk_subtitle_bg",
        "lbl_sync_offset",
        "combo_mode",
        "combo_theme",
        "btn_center_talia",
        "slider_pos_x",
        "slider_pos_y",
        "slider_eye_sens",
        "slider_size",
        "slider_opacity",
        "chk_bass_pop",
        "chk_head_bop",
        "chk_discord_rpc",
        "btn_eco",
        "btn_check_updates",
        "btn_save_settings",
        "btn_show_guide",
        "btn_exit_app",
    ):
        assert hasattr(sd, attr)


def test_lyrics_studio_calibration_workflow(studio_env, tmp_path):
    panel, engine, _ = studio_env
    mp3 = tmp_path / "Sample Track.mp3"
    mp3.write_bytes(b"fake-audio")
    lrc = tmp_path / "Sample Track.lrc"
    lrc.write_text("[00:10.00] First line\n[00:15.00] Second line\n", encoding="utf-8")

    engine.playlist = [str(mp3)]
    engine.current_index = 0

    panel.open_lyric_fetcher(str(mp3), select_calibrate_tab=True)
    studio = panel._lyrics_fetcher_win
    assert studio is not None
    assert studio.tabs.currentIndex() == 0
    assert studio.list_cal_lines.count() == 2

    # Snap first line to playback position 12.50s -> shifts all lines by +2.50s
    studio.list_cal_lines.setCurrentRow(0)
    with patch.object(engine, "get_position", return_value=12.5):
        studio._snap_all_to_selected()

    assert len(studio._parsed_entries) == 2
    assert abs(studio._parsed_entries[0]["time"] - 12.5) < 0.05
    assert abs(studio._parsed_entries[1]["time"] - 17.5) < 0.05
    assert studio._has_unsaved_changes is True

    # Stamp second line to 19.00s cleanly
    studio.list_cal_lines.setCurrentRow(1)
    with patch.object(engine, "get_position", return_value=19.0):
        studio._retime_selected_line_only()

    assert abs(studio._parsed_entries[1]["time"] - 19.0) < 0.05

    # Save back to disk and verify .bak backup was created
    studio._save_current_lrc()
    assert studio._has_unsaved_changes is False
    assert os.path.exists(str(lrc) + ".bak")
    saved_text = lrc.read_text(encoding="utf-8")
    assert "[00:12.50]" in saved_text and "First line" in saved_text
    assert "[00:19.00]" in saved_text and "Second line" in saved_text
    studio.hide()
