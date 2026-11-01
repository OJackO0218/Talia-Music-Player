"""Tests for the decoupled disk reader that feeds the audio callback."""

import time

import numpy as np
import soundfile as sf

from audio_feeder import AudioFeeder


def _drain(feeder, timeout=8.0):
    chunks = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        chunk = feeder.get_chunk()
        if chunk is not None:
            chunks.append(chunk)
            continue
        if feeder.exhausted:
            return np.concatenate(chunks)
        time.sleep(0.002)
    raise AssertionError("feeder did not finish in time")


def test_feeder_streams_entire_file(sample_wav):
    path, data, _sr = sample_wav
    with sf.SoundFile(path) as handle:
        feeder = AudioFeeder(handle, handle.frames, handle.channels, blocksize=256, max_chunks=4)
        feeder.start()
        result = _drain(feeder)
        feeder.stop()

    assert result.shape == data.shape
    np.testing.assert_allclose(result, data, atol=1e-6)


def test_feeder_uses_head_buffer_then_file(sample_wav):
    path, data, _sr = sample_wav
    head = data[:500].copy()
    with sf.SoundFile(path) as handle:
        feeder = AudioFeeder(
            handle,
            handle.frames,
            handle.channels,
            blocksize=256,
            max_chunks=4,
            head_buffer=head,
            head_frames=len(head),
        )
        feeder.start()
        result = _drain(feeder)
        feeder.stop()

    assert result.shape == data.shape
    np.testing.assert_allclose(result, data, atol=1e-6)


def test_feeder_resumes_head_buffer_at_start_frame(sample_wav):
    path, data, _sr = sample_wav
    head = data[:1000].copy()
    with sf.SoundFile(path) as handle:
        feeder = AudioFeeder(
            handle,
            handle.frames,
            handle.channels,
            blocksize=128,
            max_chunks=4,
            head_buffer=head,
            head_frames=len(head),
            start_frame=400,
        )
        feeder.start()
        result = _drain(feeder)
        feeder.stop()

    np.testing.assert_allclose(result, data[400:], atol=1e-6)


def test_feeder_seek_discards_stale_chunks(sample_wav):
    path, data, _sr = sample_wav
    with sf.SoundFile(path) as handle:
        feeder = AudioFeeder(handle, handle.frames, handle.channels, blocksize=256, max_chunks=4)
        feeder.start()
        time.sleep(0.01)
        feeder.seek(1000)
        result = _drain(feeder)
        feeder.stop()

    np.testing.assert_allclose(result[0], data[1000], atol=1e-6)
    assert result.shape[0] == len(data) - 1000


def test_feeder_stops_cleanly(sample_wav):
    path, _data, _sr = sample_wav
    with sf.SoundFile(path) as handle:
        feeder = AudioFeeder(handle, handle.frames, handle.channels)
        feeder.start()
        feeder.stop()
        assert feeder.exhausted is False
