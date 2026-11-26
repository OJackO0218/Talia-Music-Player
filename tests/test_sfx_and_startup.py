"""Tests for Talia SFX volume scaling and fast startup optimizations."""

import sys
import wave

import pytest

from audio_engine import CyberAudioEngine
from config import init_app_fonts
from controller import ControlPanel
from cyber_sfx import (
    BASE_CYBER_SFX_VOLUME,
    CyberSfxManager,
    compute_sfx_volume_multiplier,
    set_cyber_sfx_talia_volume,
)
from lyrics_manager import LyricsManager
from lyrics_overlay import LyricsOverlayWindow
from overlay import OverlayWindow


def _write_silent_wav(path, frames: int = 4410, rate: int = 44100) -> str:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * frames)
    return str(path)


def test_sfx_multiplier_curve_matches_volume_tiers():
    quiet = compute_sfx_volume_multiplier(0.0)
    half = compute_sfx_volume_multiplier(0.5)
    full = compute_sfx_volume_multiplier(1.0)

    assert 0.10 <= quiet <= 0.25
    assert 0.65 <= half < 0.90
    assert 1.15 <= full <= 1.50
    assert quiet < compute_sfx_volume_multiplier(0.25) < half < compute_sfx_volume_multiplier(0.75) < full
    assert compute_sfx_volume_multiplier(-0.5) == quiet
    assert compute_sfx_volume_multiplier(1.8) == full


@pytest.mark.gui
def test_overlay_and_cyber_sfx_scale_with_talia_volume(qapp):
    prev_instance = CyberSfxManager._instance
    CyberSfxManager._instance = None
    try:
        # Setting volume before CyberSfxManager instantiation applies when created later
        set_cyber_sfx_talia_volume(0.0)
        sfx = CyberSfxManager.instance()
        assert sfx.volume == pytest.approx(
            BASE_CYBER_SFX_VOLUME * compute_sfx_volume_multiplier(0.0), abs=1e-4
        )

        engine = CyberAudioEngine()
        lyrics = LyricsOverlayWindow(engine, LyricsManager())
        overlay = OverlayWindow(engine, initial_volume=0.5)
        panel = ControlPanel(overlay, engine, lyrics, defer_populate=True)

        try:
            # 0% volume -> quiet SFX
            overlay.set_volume(0.0)
            assert overlay.sound_pop.volume() == pytest.approx(
                0.24 * compute_sfx_volume_multiplier(0.0), abs=1e-3
            )
            assert overlay.sound_btn.volume() == pytest.approx(
                0.20 * compute_sfx_volume_multiplier(0.0), abs=1e-3
            )
            assert sfx.volume == pytest.approx(
                BASE_CYBER_SFX_VOLUME * compute_sfx_volume_multiplier(0.0), abs=1e-3
            )

            # 50% volume -> normal, still a little quiet
            panel.slider_vol.setValue(50)
            assert overlay.sound_pop.volume() == pytest.approx(
                0.24 * compute_sfx_volume_multiplier(0.5), abs=1e-3
            )
            assert overlay.sound_skip_next.volume() < 0.30
            assert sfx.volume < BASE_CYBER_SFX_VOLUME

            # 100% volume -> normal, a little louder
            panel.slider_vol.setValue(100)
            assert overlay.sound_pop.volume() > 0.24
            assert overlay.sound_pop.volume() == pytest.approx(
                0.24 * compute_sfx_volume_multiplier(1.0), abs=1e-3
            )
            assert overlay.sound_skip_next.volume() > 0.30
            assert sfx.volume > BASE_CYBER_SFX_VOLUME
        finally:
            panel.hide()
            lyrics.hide()
            overlay.hide()
            for timer_attr in ("timeline_timer", "hotkey_timer"):
                if hasattr(panel, timer_attr):
                    getattr(panel, timer_attr).stop()
            for timer_attr in ("anim_timer", "topmost_timer"):
                if hasattr(overlay, timer_attr):
                    getattr(overlay, timer_attr).stop()
            panel.deleteLater()
            lyrics.deleteLater()
            overlay.deleteLater()
            sfx.deleteLater()
    finally:
        CyberSfxManager._instance = prev_instance
        set_cyber_sfx_talia_volume(0.49)


def test_lazy_imports_and_deferred_paused_stream(tmp_path):
    # Importing song_downloader should not force syncedlyrics at launch
    if "syncedlyrics" not in sys.modules:
        import song_downloader  # noqa: F401

        assert "syncedlyrics" not in sys.modules

    wav = _write_silent_wav(tmp_path / "sample.wav")
    engine = CyberAudioEngine()
    try:
        assert engine.load_file(wav, auto_play=False, blocking=False) is True
        # Paused startup track loads feeder & metadata without blocking on OutputStream
        assert engine.active_sf is not None
        assert engine.stream is None
        assert engine.is_paused is True
    finally:
        engine.shutdown()


@pytest.mark.gui
def test_init_app_fonts_is_idempotent(qapp):
    first = init_app_fonts(force=True)
    second = init_app_fonts()
    assert isinstance(first, list)
    assert second == []
