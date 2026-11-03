"""Regression tests for the real-time callback's memory-only data path."""

import numpy as np

from audio_engine import CyberAudioEngine


class FakeFeeder:
    """Stand-in for AudioFeeder so the callback can be tested without a device."""

    def __init__(self, chunks=(), exhausted=False):
        self._chunks = list(chunks)
        self._exhausted = exhausted

    def get_chunk(self):
        if self._chunks:
            return self._chunks.pop(0)
        return None

    @property
    def exhausted(self):
        return self._exhausted


def _engine_with(feeder):
    engine = CyberAudioEngine()
    engine.feeder = feeder
    engine.is_playing = True
    engine.total_frames = 100_000
    engine.current_frame = 0
    engine.set_volume(1.0)
    return engine


def test_callback_uses_leftover_when_chunk_is_shorter_than_buffer():
    chunk = np.ones((1500, 2), dtype=np.float32)
    engine = _engine_with(FakeFeeder([chunk]))

    first = np.zeros((1024, 2), dtype=np.float32)
    engine._audio_callback(first, 1024, None, None)
    np.testing.assert_allclose(first, 1.0)
    assert engine._leftover.shape == (476, 2)
    assert engine.current_frame == 1024

    second = np.zeros((1024, 2), dtype=np.float32)
    engine._audio_callback(second, 1024, None, None)
    np.testing.assert_allclose(second[:476], 1.0)
    np.testing.assert_allclose(second[476:], 0.0)
    assert engine._leftover is None
    assert engine.current_frame == 1500


def test_callback_duplicates_mono_chunks_to_stereo():
    chunk = np.full((256,), 0.5, dtype=np.float32)
    engine = _engine_with(FakeFeeder([chunk]))

    out = np.zeros((256, 2), dtype=np.float32)
    engine._audio_callback(out, 256, None, None)

    np.testing.assert_allclose(out[:, 0], 0.5)
    np.testing.assert_allclose(out[:, 1], 0.5)


def test_callback_marks_finished_only_after_feeder_is_exhausted():
    engine = _engine_with(FakeFeeder([], exhausted=False))
    out = np.zeros((256, 2), dtype=np.float32)

    engine._audio_callback(out, 256, None, None)
    assert not engine.track_finished
    assert engine.is_playing

    engine.feeder._exhausted = True
    engine._audio_callback(out, 256, None, None)
    assert engine.track_finished
    assert not engine.is_playing
    assert engine.current_frame == engine.total_frames


def test_callback_survives_feeder_cleared_mid_call():
    """A track switch on the UI thread may clear engine.feeder while we read."""

    class VanishingFeeder(FakeFeeder):
        def __init__(self, engine, chunk):
            super().__init__([chunk])
            self.engine = engine

        def get_chunk(self):
            self.engine.feeder = None
            return super().get_chunk()

    engine = CyberAudioEngine()
    engine.is_playing = True
    engine.total_frames = 100_000
    engine.set_volume(1.0)
    engine.feeder = VanishingFeeder(engine, np.ones((256, 2), dtype=np.float32))

    out = np.zeros((256, 2), dtype=np.float32)
    engine._audio_callback(out, 256, None, None)

    np.testing.assert_allclose(out, 1.0)
    assert engine.current_frame == 256


def test_callback_is_silent_when_not_playing():
    engine = _engine_with(FakeFeeder([np.ones((256, 2), dtype=np.float32)]))
    engine.is_playing = False
    out = np.ones((256, 2), dtype=np.float32)

    engine._audio_callback(out, 256, None, None)

    np.testing.assert_allclose(out, 0.0)


def test_callback_dj_overlap_crossfade():
    """Verifies simultaneous mixing of fading out track and incoming track with equal power curve."""
    engine = _engine_with(FakeFeeder([np.ones((1024, 2), dtype=np.float32)]))
    engine.sr = 44100
    engine.set_volume(1.0)
    fade_len = int(4.0 * 44100)

    # Incoming Song B
    engine._fade_in_total = fade_len
    engine._fade_in_remaining = fade_len

    # Outgoing Song A
    engine._fading_out_feeder = FakeFeeder([np.ones((1024, 2), dtype=np.float32)])
    engine._fading_out_total = fade_len
    engine._fading_out_remaining = fade_len

    out = np.zeros((1024, 2), dtype=np.float32)
    engine._audio_callback(out, 1024, None, None)

    # Start of crossfade: Song A is at ~1.0, Song B is near 0.0, total sum is ~1.0
    assert out[0, 0] > 0.98
    assert out[0, 0] <= 1.02

    # Midpoint test (2.0s in): both tracks are at equal power ~0.7071
    engine.feeder = FakeFeeder([np.ones((1024, 2), dtype=np.float32)])
    engine._fading_out_feeder = FakeFeeder([np.ones((1024, 2), dtype=np.float32)])
    engine._fade_in_remaining = fade_len // 2
    engine._fading_out_remaining = fade_len // 2

    out_mid = np.zeros((1024, 2), dtype=np.float32)
    engine._audio_callback(out_mid, 1024, None, None)

    # Midpoint acoustic power sum: (0.7071)^2 + (0.7071)^2 ≈ 1.0
    # Linear amplitude sum: 0.7071 + 0.7071 ≈ 1.414
    np.testing.assert_allclose(out_mid[0, 0], np.sqrt(2.0), rtol=0.02)
