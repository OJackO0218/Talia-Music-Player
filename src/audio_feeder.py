"""Decoupled audio file reader for Talia.

The real-time audio callback must never touch the disk. This class reads chunks
from a SoundFile on a background thread and hands them to the callback through a
small bounded queue, so playback stays smooth even on slow storage.
"""

from __future__ import annotations

import logging
import queue
import threading

import numpy as np
import soundfile as sf

log = logging.getLogger(__name__)


class AudioFeeder:
    """Streams decoded chunks from a SoundFile to the audio callback via a queue."""

    def __init__(
        self,
        sound_file: sf.SoundFile,
        total_frames: int,
        channels: int,
        *,
        blocksize: int = 1024,
        max_chunks: int = 8,
        head_buffer: np.ndarray | None = None,
        head_frames: int = 0,
        start_frame: int = 0,
    ) -> None:
        self._sf = sound_file
        self.total_frames = max(0, int(total_frames))
        self.channels = int(channels)
        self.blocksize = int(blocksize)
        self._queue: queue.Queue[tuple[int, np.ndarray]] = queue.Queue(maxsize=max_chunks)
        self._stop_event = threading.Event()
        self._seek_lock = threading.Lock()
        self._pending_seek: int | None = None
        self._generation = 0
        self._thread: threading.Thread | None = None
        self._eof = self.total_frames == 0
        self._error: Exception | None = None
        self._head_buffer = head_buffer
        self._head_frames = (
            min(int(head_frames), self.total_frames) if head_buffer is not None else 0
        )
        self._head_pos = 0
        self._next_frame = max(0, min(int(start_frame), self.total_frames))
        if head_buffer is None or self._next_frame >= self._head_frames:
            self._head_buffer = None
            self._head_frames = 0
            self._head_pos = 0
        else:
            # Resume inside the cached head buffer instead of replaying from frame 0.
            self._head_pos = self._next_frame

    def start(self) -> None:
        """Starts the background reader thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="TaliaAudioFeeder", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        """Stops the reader thread. The SoundFile itself stays owned by the engine."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    def seek(self, frame: int) -> None:
        """Requests a seek; stale chunks from the old position are discarded."""
        with self._seek_lock:
            self._pending_seek = max(0, min(int(frame), self.total_frames))
            self._generation += 1

    def get_chunk(self) -> np.ndarray | None:
        """Non-blocking pop used by the audio callback. Returns None when starved."""
        while True:
            try:
                generation, chunk = self._queue.get_nowait()
            except queue.Empty:
                return None
            if generation == self._generation:
                return chunk

    @property
    def exhausted(self) -> bool:
        """True when the file has been fully read and the queue has drained.

        A pending seek means the old position's EOF must not be reported as the
        end of playback, otherwise seeking backwards could stop the track.
        """
        if self._pending_seek is not None:
            return False
        return self._eof and self._queue.empty()

    @property
    def error(self) -> Exception | None:
        return self._error

    def _run(self) -> None:
        try:
            if self._head_buffer is None:
                self._sf.seek(self._next_frame)
            while not self._stop_event.is_set():
                target = self._take_pending_seek()
                if target is not None:
                    self._apply_seek(target)
                    continue
                if self._eof:
                    self._stop_event.wait(0.01)
                    continue
                if self._queue.full():
                    self._stop_event.wait(0.004)
                    continue

                # Snapshot the position generation before reading. A seek that is
                # already pending must be applied first; a seek that arrives during
                # the disk read invalidates the chunk via the generation re-check.
                with self._seek_lock:
                    seek_pending = self._pending_seek is not None
                    generation = self._generation
                if seek_pending:
                    continue
                chunk = self._read_chunk()
                if chunk is None:
                    self._eof = True
                    continue
                with self._seek_lock:
                    stale = generation != self._generation
                if stale:
                    continue
                try:
                    self._queue.put((generation, chunk), timeout=0.05)
                except queue.Full:
                    # A seek happened between the fullness check and the put.
                    pass
        except Exception as exc:  # pragma: no cover - hardware/file dependent
            self._error = exc
            self._eof = True
            log.exception("Audio feeder failed: %s", exc)

    def _read_chunk(self) -> np.ndarray | None:
        if self._head_buffer is not None and self._head_pos < self._head_frames:
            start = self._head_pos
            end = min(self._head_frames, start + self.blocksize)
            chunk = self._head_buffer[start:end]
            self._head_pos = end
            if end >= self._head_frames:
                self._head_buffer = None
                if self.total_frames > self._head_frames:
                    self._sf.seek(self._head_frames)
                    self._next_frame = self._head_frames
                else:
                    self._eof = True
            return np.asarray(chunk, dtype=np.float32)
        remaining = self.total_frames - self._next_frame
        if remaining <= 0:
            return None
        frames = min(self.blocksize, remaining)
        data = self._sf.read(frames, dtype="float32")
        if len(data) == 0:
            return None
        self._next_frame += len(data)
        return data

    def _take_pending_seek(self) -> int | None:
        with self._seek_lock:
            target = self._pending_seek
            self._pending_seek = None
            return target

    def _apply_seek(self, frame: int) -> None:
        self._drain_queue()
        self._sf.seek(frame)
        self._next_frame = frame
        self._head_buffer = None
        self._head_frames = 0
        self._head_pos = 0
        self._eof = frame >= self.total_frames

    def _drain_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return
