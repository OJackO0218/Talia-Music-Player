"""Level/XP curve and persistence regression tests.

Covers the "5 minutes to level 1" requirement, multi-level gains, the
settings.json round-trip, and the controller save path that previously
dropped level/exp/playtime_seconds on every song change or shutdown.
"""

from __future__ import annotations

import pytest
import types

from config import (
    LEVEL_1_EXP,
    apply_playtime_exp,
    get_exp_for_level,
    load_settings,
    save_settings,
)


def test_level_one_requires_five_minutes():
    assert LEVEL_1_EXP == 300
    assert get_exp_for_level(0) == 300

    # 299 seconds is not enough; the 300th second reaches level 1.
    level, exp, total, req, leveled_up = apply_playtime_exp(0, 0, 0, 299)
    assert (level, exp, total, req, leveled_up) == (0, 299, 299, 300, False)

    level, exp, total, req, leveled_up = apply_playtime_exp(0, 299, 299, 1)
    assert (level, exp, total, leveled_up) == (1, 0, 300, True)
    assert req == get_exp_for_level(1)


def test_curve_is_monotonic_and_reasonably_paced():
    reqs = [get_exp_for_level(level) for level in range(41)]

    assert reqs[0] == 300
    assert all(later > earlier for earlier, later in zip(reqs, reqs[1:]))

    # ~1.7 hours of playtime to reach level 10, ~8.5 hours to level 20.
    assert 5_000 <= sum(reqs[:10]) <= 7_000
    assert 25_000 <= sum(reqs[:20]) <= 35_000


def test_large_gain_can_level_multiple_times():
    need = sum(get_exp_for_level(i) for i in range(3))
    level, exp, total, req, leveled_up = apply_playtime_exp(0, 0, 0, need + 5)

    assert level == 3
    assert exp == 5
    assert total == need + 5
    assert req == get_exp_for_level(3)
    assert leveled_up is True


def test_xp_survives_settings_save_and_load(tmp_path):
    path = tmp_path / "settings.json"
    cfg = load_settings(str(path))
    cfg.update({"level": 7, "exp": 42, "playtime_seconds": 9_876})

    assert save_settings(cfg, str(path))

    loaded = load_settings(str(path))
    assert loaded["level"] == 7
    assert loaded["exp"] == 42
    assert loaded["playtime_seconds"] == 9_876


def test_level_display_formats_playtime():
    from controller import ControlPanel

    assert ControlPanel._format_level_playtime(0, 300) == "0/5m"
    assert ControlPanel._format_level_playtime(60, 300) == "1/5m"
    assert ControlPanel._format_level_playtime(299, 300) == "4/5m"
    # 345 s rounds up to a 6 minute requirement.
    assert ControlPanel._format_level_playtime(0, 345) == "0/6m"
    # At or past 60m: converts to hours and minutes (e.g. 1h 0m, 1h 1m).
    assert ControlPanel._format_level_playtime(3540, 4118) == "59m/1h 9m"
    assert ControlPanel._format_level_playtime(3600, 4118) == "1h 0m/1h 9m"
    assert ControlPanel._format_level_playtime(3660, 4118) == "1h 1m/1h 9m"
    assert ControlPanel._format_level_playtime(7200, 8700) == "2h 0m/2h 25m"


def test_controller_tick_reaches_level_one_after_five_minutes(qapp, monkeypatch):
    """Drives update_timeline for 300 ticks; level 1 must trigger a save."""
    import controller as controller_module
    from audio_engine import CyberAudioEngine
    from controller import ControlPanel
    from lyrics_manager import LyricsManager
    from lyrics_overlay import LyricsOverlayWindow
    from overlay import OverlayWindow

    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    try:
        panel.level = 0
        panel.exp = 0
        panel.playtime_seconds = 0
        panel._refresh_level_display()
        engine.is_playing = True
        engine.is_paused = False

        clock = {"now": 1_000.0}
        monkeypatch.setattr(controller_module.time, "time", lambda: clock["now"])
        saves = []
        monkeypatch.setattr(
            panel,
            "save_settings",
            lambda: saves.append(
                (panel.level, panel.exp, panel.playtime_seconds)
            ),
        )

        for _ in range(299):
            clock["now"] += 1.0
            panel.update_timeline()

        # 299 seconds is still level 0.
        assert panel.level == 0
        assert panel.exp == 299
        assert panel.playtime_seconds == 299

        clock["now"] += 1.0
        panel.update_timeline()

        assert panel.level == 1
        assert panel.exp == 0
        assert panel.playtime_seconds == 300
        assert saves == [(1, 0, 300)]
        assert panel.lbl_level_badge.text().startswith(
            '<span style="font-size:24px'
        )
    finally:
        panel.hide()
        lyrics.hide()
        overlay.hide()


def test_unrelated_settings_save_preserves_xp(tmp_path):
    """Overlay/download/guide saves must not reset progress."""
    path = tmp_path / "settings.json"
    cfg = load_settings(str(path))
    cfg.update({"level": 5, "exp": 77, "playtime_seconds": 4_321})
    assert save_settings(cfg, str(path))

    assert save_settings({"volume": 0.25}, str(path))

    loaded = load_settings(str(path))
    assert loaded["volume"] == 0.25
    assert loaded["level"] == 5
    assert loaded["exp"] == 77
    assert loaded["playtime_seconds"] == 4_321


def test_controller_save_dict_includes_xp_state():
    """Regression: get_current_settings_dict must not drop XP keys."""
    from controller import ControlPanel

    class _Point:
        def x(self):
            return 11

        def y(self):
            return 22

    class _Overlay:
        is_shutting_down = False
        is_starting_up = False
        eye_sensitivity = 1.25
        enable_bass_pop = True
        enable_head_bop = False
        visualizer = types.SimpleNamespace(
            mode="Neon Wave", current_theme_name="Cyberpunk Neon"
        )

        def pos(self):
            return _Point()

        def width(self):
            return 300

    class _Slider:
        def value(self):
            return 80

    class _Audio:
        volume = 0.4
        audio_mode = "player"
        folder_path = ""
        shuffle = False
        queue = []

    panel = types.SimpleNamespace(
        overlay=_Overlay(),
        slider_opacity=_Slider(),
        audio_engine=_Audio(),
        lyrics_overlay=None,
        eco_mode=False,
        show_startup_guide=True,
        level=6,
        exp=89,
        playtime_seconds=12_000,
    )

    cfg = ControlPanel.get_current_settings_dict(panel)
    assert cfg["level"] == 6
    assert cfg["exp"] == 89
    assert cfg["playtime_seconds"] == 12_000


@pytest.mark.gui
def test_level_continuous_cumulative_display_and_bar(qapp):
    from audio_engine import CyberAudioEngine
    from controller import ControlPanel
    from lyrics_manager import LyricsManager
    from lyrics_overlay import LyricsOverlayWindow
    from overlay import OverlayWindow

    engine = CyberAudioEngine()
    lyrics = LyricsOverlayWindow(engine, LyricsManager())
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, lyrics)

    # Level 0 starts at 0/5m
    panel.level = 0
    panel.exp = 0
    panel.playtime_seconds = 0
    panel._refresh_level_display()
    assert panel.lbl_exp_progress.text() == "0/5m"
    assert panel.exp_bar.value() == 0
    assert panel.exp_bar.maximum() == 300

    # Arriving at Level 1: 5m (300s), next level target is 11m (645s). Display is 5/11m
    panel.level = 1
    panel.exp = 0
    panel.playtime_seconds = 300
    panel._refresh_level_display()
    assert panel.lbl_exp_progress.text() == "5/11m"
    assert panel.exp_bar.value() == 300
    assert panel.exp_bar.maximum() == 645

    # Midway through Level 1 (e.g. 8m playtime): display is 8/11m
    panel.level = 1
    panel.exp = 180
    panel.playtime_seconds = 480
    panel._refresh_level_display()
    assert panel.lbl_exp_progress.text() == "8/11m"
    assert panel.exp_bar.value() == 480
    assert panel.exp_bar.maximum() == 645

    # At 60m playtime (Level 7, 3600s total, req = 4118s): display is 1h 0m/1h 9m
    panel.level = 7
    panel.exp = 3600 - 3320
    panel.playtime_seconds = 3600
    panel._refresh_level_display()
    assert panel.lbl_exp_progress.text() == "1h 0m/1h 9m"
    assert panel.exp_bar.value() == 3600
    assert panel.exp_bar.maximum() == 4118

    # At 61m playtime (Level 7, 3660s total, req = 4118s): display is 1h 1m/1h 9m
    panel.level = 7
    panel.exp = 3660 - 3320
    panel.playtime_seconds = 3660
    panel._refresh_level_display()
    assert panel.lbl_exp_progress.text() == "1h 1m/1h 9m"
    assert panel.exp_bar.value() == 3660
    assert panel.exp_bar.maximum() == 4118

    panel.hide()
    lyrics.hide()
    overlay.hide()
