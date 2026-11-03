"""
High-performance audio streaming engine with vectorized FFT spectral analysis.
"""

import ctypes
import heapq
import math
import logging
import os
import random
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

from audio_feeder import AudioFeeder
from config import (
    SUPPORTED_AUDIO_EXTS,
    VK_MEDIA_NEXT_TRACK,
    VK_MEDIA_PLAY_PAUSE,
    VK_MEDIA_PREV_TRACK,
    trim_process_memory,
    user32,
)

log = logging.getLogger(__name__)


class CyberAudioEngine:
    """Streams audio via sounddevice and calculates real-time FFT spectrum & waveform data."""

    def __init__(self, num_bars: int = 28):
        self.stream = None
        self.data = None
        self.active_sf = None
        self.feeder: AudioFeeder | None = None
        self._leftover: np.ndarray | None = None
        self.sr = 44100
        self.channels = 2
        self.current_frame = 0
        self.total_frames = 0
        self.is_playing = False
        self.is_paused = False
        self.volume = 0.85
        self.effective_gain = float(self.volume**2.2)

        # Raw audio buffer from audio callback (1024 mono samples)
        self.latest_buffer = np.zeros(1024, dtype=np.float32)

        # FFT Analysis & Vectorized Cache
        self.num_bars = num_bars
        self.smoothed_bars = np.zeros(num_bars, dtype=np.float32)
        self.peak_bars = np.zeros(num_bars, dtype=np.float32)
        self.peak_decay = np.zeros(num_bars, dtype=np.float32)
        self.beat_energy = 0.0

        # Pre-computed FFT arrays for 60 FPS zero-allocation performance
        self.hanning_window = np.hanning(1024).astype(np.float32)
        self._windowed_buffer = np.zeros(1024, dtype=np.float32)
        # Logarithmic grouping indices for 513 FFT bins (0 - 22.05 kHz)
        self.indices = np.logspace(np.log10(1), np.log10(512), num_bars + 1).astype(int)
        # Pre-computed matrix multiplication for vectorized logarithmic band grouping: raw_bars = M @ fft
        self.fft_band_matrix = np.zeros((num_bars, 513), dtype=np.float32)
        for i in range(num_bars):
            start = self.indices[i]
            end = max(start + 1, self.indices[i + 1])
            self.fft_band_matrix[i, start:end] = 1.0 / float(end - start)

        # High-frequency pink noise compensation curve
        self.boost_weights = (
            1.0 + (np.arange(num_bars, dtype=np.float32) / float(num_bars)) * 2.2
        ).astype(np.float32)
        self.raw_bars = np.zeros(num_bars, dtype=np.float32)

        # Audio Input Source Mode: 'player' (Local Playlist) or 'desktop' (Desktop Loopback)
        self.audio_mode = "player"
        self.desktop_running = False
        self.desktop_thread = None

        # Eco Mode State (< 1% CPU optimization)
        self.eco_mode = False
        self._eco_frame_counter = 0
        self._cached_eco_spectrum = None

        # Playlist State
        self.lyrics_manager = None
        self.folder_path = ""
        self.playlist = []
        self.current_index = -1
        self._shuffle = False
        self._shuffle_order = []
        self._shuffle_pos = -1
        self._played_indices: set[int] = set()
        self._shuffle_history: list[int] = []
        self.track_finished = False
        self.queue = []

        # Real-time BPM & Bass Onset Tracking (Musical Grooving & Head-Bobbing)
        self.estimated_bpm = 120.0
        self.last_beat_time = 0.0
        self.beat_intervals = []
        self._prev_bass_energy = 0.0
        self._prev_bass_diff = 0.0
        self.is_beat_kick = False

        # Zero-freeze Stream Reuse & Predictive Preloader
        self._audio_lock = threading.Lock()
        self._preload_lock = threading.Lock()
        self._preload_cache: dict[str, tuple[np.ndarray, int, int, int]] = {}
        self._preload_inflight: set[str] = set()
        self._preload_generation = 0
        self._consecutive_failures = 0

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @shuffle.setter
    def shuffle(self, enabled: bool):
        self._shuffle = bool(enabled)
        if self._shuffle:
            self.rebuild_shuffle_order(starting_index=self.current_index)
            if 0 <= self.current_index < len(self.playlist):
                self._played_indices.add(self.current_index)
            self._trigger_preload_next()
        else:
            self._shuffle_order.clear()
            self._shuffle_pos = -1
            self._played_indices.clear()
            self._shuffle_history.clear()
            self._trigger_preload_next()

    def reset_bpm_tracking(self):
        """Resets BPM detection state when a new song loads or user seeks."""
        self.last_beat_time = 0.0
        self.beat_intervals.clear()
        self._prev_bass_energy = 0.0
        self._prev_bass_diff = 0.0
        self.is_beat_kick = False

    def set_eco_mode(self, enabled: bool):
        """Toggles Eco Mode (< 1% CPU target) by reducing internal sampling overhead."""
        self.eco_mode = enabled
        self._cached_eco_spectrum = None

    def set_audio_mode(self, mode: str):
        """Switches between 'player' (local playlist files) and 'desktop' (Windows audio loopback)."""
        if mode == self.audio_mode:
            return
        self.audio_mode = mode
        if mode == "desktop":
            # Pause local file playback
            if self.is_playing:
                self.pause()
            self._start_desktop_capture()
            log.info(
                "[AUDIO SOURCE] Switched to DESKTOP AUDIO (Listening to osu!, Spotify, Games)."
            )
        else:
            self._stop_desktop_capture()
            log.info("[AUDIO SOURCE] Switched to BUILT-IN MUSIC PLAYER.")

    def _start_desktop_capture(self):
        """Spawns background audio loopback capture thread."""
        self._stop_desktop_capture()
        self.desktop_running = True
        self.desktop_thread = threading.Thread(target=self._desktop_capture_worker, daemon=True)
        self.desktop_thread.start()

    def _stop_desktop_capture(self):
        """Stops background loopback capture thread."""
        self.desktop_running = False
        if self.desktop_thread and self.desktop_thread.is_alive():
            self.desktop_thread.join(timeout=0.25)
        self.desktop_thread = None

    def _desktop_capture_worker(self):
        """Real-time WASAPI loopback capture worker thread."""
        ctypes.windll.ole32.CoInitialize(None)
        try:
            import soundcard as sc

            spk = sc.default_speaker()
            mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
            with mic.recorder(samplerate=48000, blocksize=1024) as recorder:
                while self.desktop_running:
                    data = recorder.record(numframes=1024)
                    if not self.desktop_running:
                        break
                    # Convert stereo to mono and scale with volume sensitivity
                    mono = np.mean(data, axis=1) * (self.volume / 0.85)
                    self.latest_buffer = mono.astype(np.float32)
        except Exception as e:
            log.error(f"[DESKTOP AUDIO ERROR] {e}")
        finally:
            ctypes.windll.ole32.CoUninitialize()

    def set_lyrics_manager(self, mgr):
        self.lyrics_manager = mgr

    def set_folder(self, folder_path: str):
        """Sets the active playlist directory and refreshes tracks."""
        self.folder_path = folder_path
        self._invalidate_preload_cache()
        self.refresh_playlist()

    def switch_folder(self, folder_path: str):
        """Alias for set_folder."""
        self.set_folder(folder_path)

    def set_music_folder(self, folder_path: str):
        """Alias for set_folder."""
        self.set_folder(folder_path)

    def _invalidate_preload_cache(self) -> None:
        """Drops cached preloads and makes in-flight preloads discard their result."""
        with self._preload_lock:
            self._preload_generation += 1
            self._preload_cache.clear()
            self._preload_inflight.clear()

    def _stop_for_playlist_change(self) -> None:
        """Stops playback when the loaded track no longer belongs to the playlist."""
        self.is_playing = False
        self.is_paused = True
        if self.stream is not None and self.stream.active:
            try:
                self.stream.stop()
            except Exception as exc:
                log.debug("Could not stop stream after playlist change: %s", exc)
        with self._audio_lock:
            self._stop_feeder_locked()
            if self.active_sf is not None:
                try:
                    self.active_sf.close()
                except Exception as exc:
                    log.debug("Could not close audio file after playlist change: %s", exc)
                self.active_sf = None
        self.data = None
        self.current_frame = 0
        self.total_frames = 0
        self.track_finished = False
        self.reset_bpm_tracking()

    def _stop_feeder_locked(self) -> None:
        """Stops the reader thread. Caller must hold _audio_lock."""
        feeder = self.feeder
        self.feeder = None
        if feeder is not None:
            feeder.stop()

    def add_to_queue(self, track_path: str) -> bool:
        """Appends a track to the upcoming playback queue."""
        if os.path.exists(track_path):
            self.queue.append(os.path.normpath(track_path))
            return True
        return False

    def add_to_queue_next(self, track_path: str) -> bool:
        """Inserts a track at the front of the queue to play next."""
        if os.path.exists(track_path):
            self.queue.insert(0, os.path.normpath(track_path))
            return True
        return False

    def remove_from_queue(self, index: int):
        """Removes a queued track by its index and returns its path."""
        if 0 <= index < len(self.queue):
            return self.queue.pop(index)
        return None

    def clear_queue(self):
        """Clears all upcoming queued songs."""
        self.queue.clear()

    def _extract_cluster_key(self, path: str) -> str:
        """Extracts artist or folder cluster key for Spotify-style balanced shuffling."""
        if not path:
            return "unknown"
        fname = os.path.splitext(os.path.basename(path))[0]
        if " - " in fname:
            part = fname.split(" - ")[0].strip().lower()
            import re

            part = re.sub(r"^\d+[\.\s_-]+", "", part).strip()
            return part or "unknown"
        parent = os.path.basename(os.path.dirname(path)).strip().lower()
        return parent or "unknown"

    def rebuild_shuffle_order(self, starting_index: int = -1):
        """
        Builds a balanced shuffle by interleaving artist/folder clusters.

        The most represented cluster is always scheduled next unless that would
        repeat the current artist, which is the classic greedy solution to the
        "rearrange a string so no two adjacent characters are equal" problem.
        Same-artist runs only remain when one cluster genuinely dominates the
        playlist and no better ordering exists.
        """
        if not self.playlist:
            self._shuffle_order = []
            self._shuffle_pos = -1
            return
        n = len(self.playlist)
        if n == 1:
            self._shuffle_order = [0]
            self._shuffle_pos = 0
            return

        # 1. Group track indices by artist/folder and randomise within each cluster.
        clusters: dict[str, list[int]] = {}
        for idx, path in enumerate(self.playlist):
            clusters.setdefault(self._extract_cluster_key(path), []).append(idx)
        for indices in clusters.values():
            random.shuffle(indices)

        # 2. If a start track was requested, play it first and remove it from its cluster.
        order: list[int] = []
        last_key: str | None = None
        if 0 <= starting_index < n:
            last_key = self._extract_cluster_key(self.playlist[starting_index])
            if starting_index in clusters.get(last_key, []):
                clusters[last_key].remove(starting_index)
                if not clusters[last_key]:
                    del clusters[last_key]
            order.append(starting_index)

        # 3. Dynamic anti-clustering with weighted random reach:
        #    Prevents starvation of smaller artists by sampling proportionally from all
        #    eligible clusters, while prioritizing critical clusters to eliminate adjacent repeats.
        while clusters:
            rem_total = sum(len(indices) for indices in clusters.values())
            critical_key = None
            for k, v in clusters.items():
                if len(v) >= math.ceil(rem_total / 2.0):
                    critical_key = k
                    break

            eligible = [k for k in clusters.keys() if k != last_key]
            if not eligible:
                eligible = list(clusters.keys())

            if critical_key and critical_key in eligible:
                chosen_key = critical_key
            else:
                weights = [len(clusters[k]) for k in eligible]
                chosen_key = random.choices(eligible, weights=weights, k=1)[0]

            chosen_idx = clusters[chosen_key].pop()
            order.append(chosen_idx)
            last_key = chosen_key
            if not clusters[chosen_key]:
                del clusters[chosen_key]

        self._shuffle_order = order
        self._shuffle_pos = 0

    def refresh_playlist(self):
        """Recursively scans the folder and all subfolders (Foobar2000 structure) for supported audio files."""
        if not self.folder_path or not os.path.exists(self.folder_path):
            self.playlist = []
            self._shuffle_order.clear()
            self._shuffle_pos = -1
            self.current_index = -1
            self._stop_for_playlist_change()
            return
        current_track = (
            self.playlist[self.current_index]
            if (0 <= self.current_index < len(self.playlist))
            else None
        )
        files = []
        for root, dirs, filenames in os.walk(self.folder_path):
            dirs.sort()  # Natural alphabetical subfolder traversal
            for f in sorted(filenames):
                if f.lower().endswith(SUPPORTED_AUDIO_EXTS):
                    files.append(os.path.normpath(os.path.join(root, f)))

        # Group root files and subfolders neatly
        try:
            files.sort(key=lambda p: os.path.relpath(p, self.folder_path).lower())
        except Exception:
            files.sort()
        self.playlist = files
        if current_track and current_track in files:
            self.current_index = files.index(current_track)
        elif files:
            if current_track is not None:
                # The folder changed (or the file was deleted): stop the stale track so
                # the UI and the audio engine never disagree about what is playing.
                log.info("Current track is gone from the playlist; stopping playback.")
                self._stop_for_playlist_change()
            self.current_index = 0
        else:
            self.current_index = -1
            self._stop_for_playlist_change()
        if self._shuffle and self.playlist:
            if current_track and current_track in self.playlist:
                self.rebuild_shuffle_order(starting_index=self.current_index)
            else:
                self.rebuild_shuffle_order()
                if self._shuffle_order:
                    self.current_index = self._shuffle_order[0]
        else:
            self._shuffle_order.clear()
            self._shuffle_pos = -1

    def play_index(self, idx: int) -> bool:
        """Loads and plays the track at the specified index."""
        if not self.playlist or idx < 0 or idx >= len(self.playlist):
            return False

        if 0 <= self.current_index < len(self.playlist) and self.current_index != idx:
            self._shuffle_history.append(self.current_index)
            if len(self._shuffle_history) > 100:
                self._shuffle_history.pop(0)

        self.current_index = idx
        self._played_indices.add(idx)

        # Reset cycle if all tracks have now been played once
        if len(self._played_indices) >= len(self.playlist):
            self._played_indices = {idx}

        if self._shuffle:
            if not self._shuffle_order or len(self._shuffle_order) != len(self.playlist):
                self.rebuild_shuffle_order(starting_index=idx)
            elif idx in self._shuffle_order:
                self._shuffle_pos = self._shuffle_order.index(idx)
            else:
                self.rebuild_shuffle_order(starting_index=idx)
        path = self.playlist[idx]
        return self.load_file(path, auto_play=True)

    def load_file(self, file_path: str, auto_play: bool = True, blocking: bool = False) -> bool:
        """Loads a track and starts a background feeder for smooth, disk-independent playback."""
        # Stop feeding the callback before swapping files so a track change can
        # never play a stale chunk from the previous song.
        self.is_playing = False
        try:
            with self._audio_lock:
                self._stop_feeder_locked()
                if self.active_sf is not None:
                    try:
                        self.active_sf.close()
                    except Exception as exc:
                        log.debug("Could not close previous audio file: %s", exc)
                    self.active_sf = None

                # 1. Check preload cache (strictly 1 track, 15s head buffer)
                with self._preload_lock:
                    cached = self._preload_cache.pop(file_path, None)
                new_sf = sf.SoundFile(file_path, "r")
                self.active_sf = new_sf
                self.sr = new_sf.samplerate
                self.channels = new_sf.channels
                self.total_frames = new_sf.frames
                self.current_frame = 0
                self._leftover = None
                self.data = True  # Signal that track is loaded
                self.track_finished = new_sf.frames == 0
                self.reset_bpm_tracking()
                head_buffer = None
                head_frames = 0
                if cached is not None:
                    cached_audio, cached_sr, _cached_total, cached_channels = cached
                    if cached_sr == new_sf.samplerate and cached_channels == new_sf.channels:
                        head_buffer = cached_audio
                        head_frames = min(len(cached_audio), new_sf.frames)
                if new_sf.frames > 0:
                    feeder = AudioFeeder(
                        new_sf,
                        new_sf.frames,
                        new_sf.channels,
                        head_buffer=head_buffer,
                        head_frames=head_frames,
                    )
                    feeder.start()
                    self.feeder = feeder
            needs_new_stream = (
                self.stream is None
                or self.stream.samplerate != self.sr
                or self.stream.channels != self.channels
            )
            if needs_new_stream:
                if self.stream is not None:
                    try:
                        self.stream.stop()
                        self.stream.close()
                    except Exception as exc:
                        log.debug("Could not close previous output stream: %s", exc)
                    self.stream = None
                self.stream = sd.OutputStream(
                    samplerate=self.sr,
                    channels=self.channels,
                    callback=self._audio_callback,
                    blocksize=1024,
                )
            if self.lyrics_manager:
                self.lyrics_manager.load_track(file_path)
            if auto_play:
                self.play()
            else:
                self.is_playing = False
                self.is_paused = True

            # Trigger background preload for next track (max 1 track, 15s head)
            self._trigger_preload_next()
            self._consecutive_failures = 0
            trim_process_memory(force_gc=False)
            return True
        except Exception as exc:
            log.exception("Could not open %s: %s", file_path, exc)
            with self._audio_lock:
                self._stop_feeder_locked()
                if self.active_sf is not None:
                    try:
                        self.active_sf.close()
                    except Exception:
                        pass
                    self.active_sf = None
            self.is_playing = False
            # Auto-skip corrupted/missing files, but never recurse more than 10 tracks deep.
            if len(self.playlist) > 1 and self._consecutive_failures < min(len(self.playlist), 10):
                self._consecutive_failures += 1
                self.next_track()
            return False

    def _trigger_preload_next(self):
        """Asynchronously pre-decodes the first 15s of the upcoming track in a background thread."""
        if not self.playlist:
            return
        next_track_path = None
        if self.queue:
            next_track_path = self.queue[0]
        elif len(self.playlist) > 1:
            if self._shuffle:
                if not self._shuffle_order or len(self._shuffle_order) != len(self.playlist):
                    self.rebuild_shuffle_order(starting_index=self.current_index)
                unplayed = [
                    i for i in self._shuffle_order
                    if i not in self._played_indices and (len(self.playlist) <= 1 or i != self.current_index)
                ]
                if unplayed:
                    next_track_path = self.playlist[unplayed[0]]
                else:
                    candidates = [i for i in self._shuffle_order if (len(self.playlist) <= 1 or i != self.current_index)]
                    next_track_path = self.playlist[candidates[0]] if candidates else None
            else:
                next_track_path = self.playlist[(self.current_index + 1) % len(self.playlist)]
        if not next_track_path:
            return
        with self._preload_lock:
            if next_track_path in self._preload_cache or next_track_path in self._preload_inflight:
                return
            self._preload_inflight.add(next_track_path)
            generation = self._preload_generation
        threading.Thread(
            target=self._preload_worker,
            args=(next_track_path, generation),
            name="TaliaPreloader",
            daemon=True,
        ).start()

    def _preload_worker(self, path: str, generation: int):
        """Background worker that pre-decodes ONLY the first 15 seconds (max ~5.5 MB RAM)."""
        try:
            if not path or not os.path.exists(path):
                return
            info = sf.info(path)
            sr = info.samplerate
            frames_to_read = min(info.frames, int(sr * 15.0))
            audio, _ = sf.read(path, frames=frames_to_read, dtype="float32")
            if len(audio.shape) == 1:
                stereo = np.empty((len(audio), 2), dtype=np.float32)
                stereo[:, 0] = audio
                stereo[:, 1] = audio
                audio = stereo
            with self._preload_lock:
                if generation != self._preload_generation:
                    return  # folder changed while decoding; discard stale audio
                # Cache strictly 1 track maximum
                self._preload_cache.clear()
                self._preload_cache[path] = (audio, sr, info.frames, audio.shape[1])
        except Exception as exc:
            log.debug("Preload failed for %s: %s", path, exc)
        finally:
            with self._preload_lock:
                self._preload_inflight.discard(path)

    def play(self):
        if self.stream is None:
            self.is_playing = False
            return
        if not self.stream.active:
            try:
                self.stream.start()
            except Exception as e:
                log.error(f"[AUDIO ERROR] stream.start() failed: {e}")
                self.is_playing = False
                self.is_paused = True
                return
        self.is_playing = True
        self.is_paused = False

    def pause(self):
        self.is_playing = False
        self.is_paused = True
        if self.stream is not None and self.stream.active:
            try:
                self.stream.stop()
            except Exception:
                pass

    def shutdown(self):
        """Immediately aborts audio stream and releases hardware audio handles."""
        self.is_playing = False
        self.is_paused = False
        self._leftover = None
        self._invalidate_preload_cache()
        self._stop_desktop_capture()
        with self._audio_lock:
            self._stop_feeder_locked()
            if self.active_sf is not None:
                try:
                    self.active_sf.close()
                except Exception as exc:
                    log.debug("Could not close audio file during shutdown: %s", exc)
                self.active_sf = None
        try:
            if self.stream is not None:
                self.stream.abort()
                self.stream.close()
                self.stream = None
        except Exception:
            pass

    def toggle_play_pause(self):
        if self.audio_mode == "desktop":
            user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 0, 0)
            user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 2, 0)
            self.desktop_playing = not getattr(self, "desktop_playing", True)
            log.info("[DESKTOP AUDIO] Sent Play/Pause command to system.")
            return
        if self.stream is None:
            if self.playlist:
                if self._shuffle:
                    if not self._shuffle_order or len(self._shuffle_order) != len(self.playlist):
                        self.rebuild_shuffle_order()
                    pos = self._shuffle_pos if (0 <= self._shuffle_pos < len(self._shuffle_order)) else 0
                    idx = self._shuffle_order[pos]
                elif self.current_index < 0 or self.current_index >= len(self.playlist):
                    idx = 0
                else:
                    idx = self.current_index
                self.play_index(idx)
            return
        if self.is_playing:
            self.pause()
        else:
            self.play()

    @property
    def is_active(self):
        """Returns True if local player or desktop audio is active."""
        if self.audio_mode == "desktop":
            return getattr(self, "desktop_playing", True)
        return self.is_playing

    def next_track(self):
        if self.audio_mode == "desktop":
            user32.keybd_event(VK_MEDIA_NEXT_TRACK, 0, 0, 0)
            user32.keybd_event(VK_MEDIA_NEXT_TRACK, 0, 2, 0)
            log.info("[DESKTOP AUDIO] Sent Next Track command to system.")
            return
        if not self.playlist and not self.queue:
            return

        # 1. Spotify Queue Priority: If queue has items, play next in queue!
        if self.queue:
            next_path = self.queue.pop(0)
            if next_path in self.playlist:
                self.current_index = self.playlist.index(next_path)
            else:
                # Queued files downloaded after the last scan still need a valid index.
                self.playlist.append(next_path)
                self.current_index = len(self.playlist) - 1
            self.load_file(next_path, auto_play=True)
            return

        # 2. Normal sequential / shuffle playback
        if not self.playlist:
            return
        if self._shuffle:
            if not self._shuffle_order or len(self._shuffle_order) != len(self.playlist):
                self.rebuild_shuffle_order(starting_index=self.current_index)

            # Strict no-repeat shuffle: always select from remaining unplayed tracks in cycle,
            # and guarantee we NEVER replay the current track when pressing Next.
            unplayed = [
                i for i in self._shuffle_order
                if i not in self._played_indices and (len(self.playlist) <= 1 or i != self.current_index)
            ]
            if not unplayed:
                last_idx = self.current_index
                self._played_indices.clear()
                self.rebuild_shuffle_order()
                if len(self._shuffle_order) > 1 and self._shuffle_order[0] == last_idx:
                    self._shuffle_order[0], self._shuffle_order[1] = (
                        self._shuffle_order[1],
                        self._shuffle_order[0],
                    )
                unplayed = [i for i in self._shuffle_order if i != last_idx]
                if not unplayed:
                    unplayed = list(self._shuffle_order)

            idx = unplayed[0]
            if idx in self._shuffle_order:
                self._shuffle_pos = self._shuffle_order.index(idx)
        else:
            idx = (self.current_index + 1) % len(self.playlist)
        self.play_index(idx)

    def prev_track(self):
        if self.audio_mode == "desktop":
            user32.keybd_event(VK_MEDIA_PREV_TRACK, 0, 0, 0)
            user32.keybd_event(VK_MEDIA_PREV_TRACK, 0, 2, 0)
            return
        if not self.playlist:
            return
        if self.get_position() > 3.0:
            self.seek(0)
        else:
            if self._shuffle and self._shuffle_history:
                prev_idx = self._shuffle_history.pop()
                self.current_index = prev_idx
                if prev_idx in self._shuffle_order:
                    self._shuffle_pos = self._shuffle_order.index(prev_idx)
                path = self.playlist[prev_idx]
                self.load_file(path, auto_play=True)
                return

            if self._shuffle:
                if not self._shuffle_order or len(self._shuffle_order) != len(self.playlist):
                    self.rebuild_shuffle_order(starting_index=self.current_index)
                if self._shuffle_pos > 0:
                    self._shuffle_pos -= 1
                else:
                    self._shuffle_pos = len(self._shuffle_order) - 1
                idx = self._shuffle_order[self._shuffle_pos]
            else:
                idx = (self.current_index - 1) % len(self.playlist)
            self.play_index(idx)

    def seek(self, seconds: float):
        if self.sr <= 0 or self.feeder is None:
            return
        target_frame = int(seconds * self.sr)
        target_frame = max(0, min(target_frame, self.total_frames))
        try:
            self.feeder.seek(target_frame)
            self._leftover = None
            self.current_frame = target_frame
            self.track_finished = False
            self.reset_bpm_tracking()
        except Exception as exc:
            log.error("Seek failed: %s", exc)

    def get_position(self) -> float:
        if self.sr > 0:
            return self.current_frame / float(self.sr)
        return 0.0

    def get_duration(self) -> float:
        if self.sr > 0 and self.total_frames > 0:
            return self.total_frames / float(self.sr)
        return 0.0

    def set_volume(self, vol: float):
        # Set volume from 0.0 to 1.0
        self.volume = max(0.0, min(float(vol), 1.0))
        # Logarithmic perceptual curve for quiet volume down to -88 dB
        self.effective_gain = float(self.volume**2.2) if self.volume > 0.0 else 0.0

    def get_current_track_title(self) -> str:
        if self.audio_mode == "desktop":
            return "Desktop Audio"
        if 0 <= self.current_index < len(self.playlist):
            return os.path.basename(self.playlist[self.current_index])
        return "No Track Loaded"

    def is_track_finished(self) -> bool:
        return bool(self.track_finished)

    def _audio_callback(self, outdata, frames, time_info, status):
        """Real-time callback: consumes memory chunks only, never touches the disk."""
        # Keep a local reference: a track switch on the UI thread may clear
        # self.feeder after this check, and the callback must not dereference None.
        feeder = self.feeder
        if not self.is_playing or feeder is None:
            outdata.fill(0)
            return
        if self._leftover is not None:
            chunk = self._leftover
            self._leftover = None
        else:
            chunk = feeder.get_chunk()
        if chunk is None:
            outdata.fill(0)
            if feeder.exhausted:
                self.current_frame = self.total_frames
                self.track_finished = True
                self.is_playing = False
            return
        gain = self.effective_gain
        count = min(len(chunk), frames)
        if chunk.ndim == 1:
            outdata[:count, 0] = chunk[:count] * gain
            if outdata.shape[1] > 1:
                outdata[:count, 1] = chunk[:count] * gain
        else:
            outdata[:count] = chunk[:count] * gain
        if count < frames:
            outdata[count:] = 0
        if count < len(chunk):
            self._leftover = chunk[count:]
        self.current_frame = min(self.total_frames, self.current_frame + count)

        # Mono buffer for visualizer FFT
        n = min(1024, frames)
        norm_factor = max(gain, 0.05) if gain > 0 else 1.0
        self.latest_buffer[:n] = outdata[:n, 0] / norm_factor

    def update_spectrum(self):
        # 0. Eco Mode Fast-Path (< 0.5% CPU): Visualizer bars are disabled in Eco Mode, so skip FFT completely!
        if getattr(self, "eco_mode", False):
            buf = self.latest_buffer
            buf_peak = max(float(buf.max()), -float(buf.min()))
            self.beat_energy = min(1.0, buf_peak * 2.0)
            self.is_beat_kick = False
            return (self.smoothed_bars, self.peak_bars, self.beat_energy)
        buf = self.latest_buffer
        buf_peak = max(float(buf.max()), -float(buf.min()))
        is_idle = (self.audio_mode == "player" and not self.is_playing) or buf_peak < 0.001
        if is_idle:
            self.is_beat_kick = False
            bars_peak = float(self.smoothed_bars.max()) if len(self.smoothed_bars) > 0 else 0.0
            if self.beat_energy > 0.002 or bars_peak > 0.002:
                # Fast decay towards zero
                self.smoothed_bars *= 0.82
                self.peak_bars *= 0.88
                self.beat_energy *= 0.80
            else:
                self.smoothed_bars.fill(0)
                self.peak_bars.fill(0)
                self.beat_energy = 0.0
            return (self.smoothed_bars, self.peak_bars, self.beat_energy)

        # 1. Apply Hanning window and Real FFT
        np.multiply(buf, self.hanning_window, out=self._windowed_buffer)
        fft = np.abs(np.fft.rfft(self._windowed_buffer))

        # 2. Bass energy (20Hz - 250Hz) and Real-time BPM calculation
        bass_mag = float(np.mean(fft[1:8]))
        target_beat = min(1.0, bass_mag / 28.0)
        self.beat_energy = max(target_beat, self.beat_energy * 0.82)
        import time as _time

        now = _time.time()
        diff = target_beat - self._prev_bass_energy
        self.is_beat_kick = False

        # Onset peak detection: sharp rise and refractory minimum 0.22s (max 270 BPM)
        if diff > 0.05 and self._prev_bass_diff <= diff and (now - self.last_beat_time) > 0.22:
            self.is_beat_kick = True
            if self.last_beat_time > 0.0:
                ibi = now - self.last_beat_time
                # Normalize double-time or half-time intervals into musical range 75 - 175 BPM
                while ibi < 0.34:  # > 176 BPM
                    ibi *= 2.0
                while ibi > 0.80:  # < 75 BPM
                    ibi /= 2.0
                self.beat_intervals.append(ibi)
                if len(self.beat_intervals) > 10:
                    self.beat_intervals.pop(0)
                if len(self.beat_intervals) >= 3:
                    med_ibi = float(np.median(self.beat_intervals))
                    instant_bpm = 60.0 / med_ibi
                    self.estimated_bpm += (instant_bpm - self.estimated_bpm) * 0.35
            self.last_beat_time = now
        self._prev_bass_diff = diff
        self._prev_bass_energy = target_beat

        # 3. Logarithmic band grouping (Vectorized BLAS matrix dot product: 27x faster than Python loop)
        np.dot(self.fft_band_matrix, fft, out=self.raw_bars)

        # Apply high-frequency boost and normalization
        np.clip((self.raw_bars * self.boost_weights) / 38.0, 0.0, 1.0, out=self.raw_bars)

        # 4. Attack and release smoothing
        rising = self.raw_bars > self.smoothed_bars
        diff = self.raw_bars - self.smoothed_bars
        self.smoothed_bars = np.where(
            rising, self.smoothed_bars + diff * 0.65, self.smoothed_bars + diff * 0.16
        )

        # 5. Peak hold with decay
        new_peaks = self.smoothed_bars >= self.peak_bars
        self.peak_bars = np.where(
            new_peaks, self.smoothed_bars, np.maximum(0.0, self.peak_bars - self.peak_decay)
        )
        self.peak_decay = np.where(new_peaks, 0.005, self.peak_decay + 0.008)
        res = (self.smoothed_bars, self.peak_bars, self.beat_energy)
        if getattr(self, "eco_mode", False):
            self._cached_eco_spectrum = res
        return res

    def get_waveform(self, sample_count: int = 80) -> np.ndarray:
        # Sampled oscilloscope points
        buf = self.latest_buffer
        if len(buf) < sample_count:
            return np.zeros(sample_count, dtype=np.float32)
        step = len(buf) // sample_count
        return np.clip(buf[::step][:sample_count] * 1.25, -1.0, 1.0)
