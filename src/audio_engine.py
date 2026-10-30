"""
High-performance audio streaming engine with vectorized FFT spectral analysis.
"""

import os
import random
import threading
import ctypes
import sounddevice as sd
import soundfile as sf
import soundcard as sc
import numpy as np

from config import (
    SUPPORTED_AUDIO_EXTS, user32,
    VK_MEDIA_PLAY_PAUSE, VK_MEDIA_NEXT_TRACK, VK_MEDIA_PREV_TRACK
)


class CyberAudioEngine:
    """Streams audio via sounddevice and calculates real-time FFT spectrum & waveform data."""

    def __init__(self, num_bars: int = 28):
        self.stream = None
        self.data = None
        self.active_sf = None
        self.head_buffer = None
        self.head_frames = 0
        self.sr = 44100
        self.channels = 2
        self.current_frame = 0
        self.total_frames = 0
        self.is_playing = False
        self.is_paused = False
        self.volume = 0.85

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
        # Logarithmic grouping indices for 513 FFT bins (0 - 22.05 kHz)
        self.indices = np.logspace(np.log10(1), np.log10(512), num_bars + 1).astype(int)
        # High-frequency pink noise compensation curve
        self.boost_weights = (1.0 + (np.arange(num_bars, dtype=np.float32) / float(num_bars)) * 2.2).astype(np.float32)
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
        self.shuffle = False
        self.track_finished = False
        self.queue = []

        # Zero-freeze Stream Reuse & Predictive Preloader
        self._audio_lock = threading.Lock()
        self._preload_cache = {}
        self._next_shuffle_idx = None

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
            print("[AUDIO SOURCE] Switched to DESKTOP AUDIO (Listening to osu!, Spotify, Games).")
        else:
            self._stop_desktop_capture()
            print("[AUDIO SOURCE] Switched to BUILT-IN MUSIC PLAYER.")

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
            print(f"[DESKTOP AUDIO ERROR] {e}")
        finally:
            ctypes.windll.ole32.CoUninitialize()

    def set_lyrics_manager(self, mgr):
        self.lyrics_manager = mgr

    def set_folder(self, folder_path: str):
        """Sets the active playlist directory and refreshes tracks."""
        self.folder_path = folder_path
        self._preload_cache.clear()
        self._next_shuffle_idx = None
        self.refresh_playlist()

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

    def refresh_playlist(self):
        """Recursively scans the folder and all subfolders (Foobar2000 structure) for supported audio files."""
        if not self.folder_path or not os.path.exists(self.folder_path):
            self.playlist = []
            return

        current_track = self.playlist[self.current_index] if (0 <= self.current_index < len(self.playlist)) else None

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
        elif self.playlist:
            if self.current_index < 0 or self.current_index >= len(self.playlist):
                self.current_index = 0
        else:
            self.current_index = -1

    def play_index(self, idx: int) -> bool:
        """Loads and plays the track at the specified index."""
        if not self.playlist or idx < 0 or idx >= len(self.playlist):
            return False
        self.current_index = idx
        path = self.playlist[idx]
        return self.load_file(path, auto_play=True)

    def load_file(self, file_path: str, auto_play: bool = True, blocking: bool = False) -> bool:
        """Loads audio with 15s head instant switch and block-streaming to guarantee < 200 MB RAM."""
        try:
            with self._audio_lock:
                if self.active_sf is not None:
                    try:
                        self.active_sf.close()
                    except Exception:
                        pass
                    self.active_sf = None

                # 1. Check preload cache (strictly 1 track, 15s head buffer)
                cached = self._preload_cache.pop(file_path, None)
                if cached is not None:
                    head_data, sr, total_frames, channels = cached
                    self.head_buffer = head_data
                    self.head_frames = len(head_data)
                else:
                    self.head_buffer = None
                    self.head_frames = 0

                new_sf = sf.SoundFile(file_path, 'r')
                self.active_sf = new_sf
                self.sr = new_sf.samplerate
                self.channels = new_sf.channels
                self.total_frames = new_sf.frames
                self.current_frame = 0
                self.data = True  # Signal that track is loaded
                self.track_finished = False

            needs_new_stream = (
                self.stream is None or
                self.stream.samplerate != self.sr or
                self.stream.channels != self.channels
            )

            if needs_new_stream:
                if self.stream is not None:
                    try:
                        self.stream.stop()
                        self.stream.close()
                    except Exception:
                        pass
                    self.stream = None

                self.stream = sd.OutputStream(
                    samplerate=self.sr,
                    channels=self.channels,
                    callback=self._audio_callback,
                    blocksize=1024
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
            import gc
            gc.collect()
            return True
        except Exception as e:
            print(f"[AUDIO ERROR] Could not open {file_path}: {e}")
            return False

    def _trigger_preload_next(self):
        """Asynchronously pre-decodes the first 15s of the upcoming track in a background thread."""
        if not self.playlist:
            return
        next_track_path = None
        if self.queue:
            next_track_path = self.queue[0]
        elif len(self.playlist) > 1:
            if self.shuffle:
                if self._next_shuffle_idx is None or self._next_shuffle_idx == self.current_index:
                    candidates = [i for i in range(len(self.playlist)) if i != self.current_index]
                    self._next_shuffle_idx = random.choice(candidates) if candidates else 0
                next_track_path = self.playlist[self._next_shuffle_idx]
            else:
                next_track_path = self.playlist[(self.current_index + 1) % len(self.playlist)]

        if next_track_path and next_track_path not in self._preload_cache:
            threading.Thread(target=self._preload_worker, args=(next_track_path,), daemon=True).start()

    def _preload_worker(self, path: str):
        """Background worker that pre-decodes ONLY the first 15 seconds (max ~5.5 MB RAM)."""
        if not path or not os.path.exists(path) or path in self._preload_cache:
            return
        try:
            info = sf.info(path)
            sr = info.samplerate
            frames_to_read = min(info.frames, int(sr * 15.0))
            audio, _ = sf.read(path, frames=frames_to_read, dtype='float32')
            if len(audio.shape) == 1:
                audio = np.column_stack((audio, audio))
            # Cache strictly 1 track maximum
            self._preload_cache.clear()
            self._preload_cache[path] = (audio, sr, info.frames, audio.shape[1])
        except Exception:
            pass

    def play(self):
        if self.stream and not self.stream.active:
            self.is_playing = True
            self.is_paused = False
            self.stream.start()

    def pause(self):
        if self.stream and self.stream.active:
            self.is_playing = False
            self.is_paused = True
            self.stream.stop()

    def shutdown(self):
        """Immediately aborts audio stream and releases hardware audio handles."""
        self.is_playing = False
        self.is_paused = False
        self._preload_cache.clear()
        self.head_buffer = None
        self._stop_desktop_capture()
        with self._audio_lock:
            if self.active_sf is not None:
                try:
                    self.active_sf.close()
                except Exception:
                    pass
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
            print("[DESKTOP AUDIO] Sent Play/Pause command to system.")
            return

        if self.stream is None:
            if self.playlist:
                idx = max(0, self.current_index)
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
            print("[DESKTOP AUDIO] Sent Next Track command to system.")
            return

        if not self.playlist and not self.queue:
            return

        # 1. Spotify Queue Priority: If queue has items, play next in queue!
        if self.queue:
            next_path = self.queue.pop(0)
            if next_path in self.playlist:
                self.current_index = self.playlist.index(next_path)
            self.load_file(next_path, auto_play=True)
            return

        # 2. Normal sequential / shuffle playback
        if not self.playlist:
            return
        if self.shuffle:
            if self._next_shuffle_idx is not None and 0 <= self._next_shuffle_idx < len(self.playlist):
                idx = self._next_shuffle_idx
                self._next_shuffle_idx = None
            else:
                candidates = [i for i in range(len(self.playlist)) if i != self.current_index]
                idx = random.choice(candidates) if candidates else 0
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
            idx = (self.current_index - 1) % len(self.playlist)
            self.play_index(idx)

    def seek(self, seconds: float):
        if self.sr > 0 and self.active_sf is not None:
            with self._audio_lock:
                target_frame = int(seconds * self.sr)
                target_frame = max(0, min(target_frame, self.total_frames))
                try:
                    self.active_sf.seek(target_frame)
                    self.current_frame = target_frame
                    self.head_buffer = None
                except Exception as e:
                    print(f"[AUDIO ERROR] Seek failed: {e}")

    def get_position(self) -> float:
        if self.sr > 0:
            return self.current_frame / float(self.sr)
        return 0.0

    def get_duration(self) -> float:
        if self.sr > 0 and self.total_frames > 0:
            return self.total_frames / float(self.sr)
        return 0.0

    def set_volume(self, vol: float):
        self.volume = max(0.0, min(float(vol), 1.0))

    def get_current_track_title(self) -> str:
        if self.audio_mode == "desktop":
            return "Desktop Audio"
        if 0 <= self.current_index < len(self.playlist):
            return os.path.basename(self.playlist[self.current_index])
        return "No Track Loaded"

    def is_track_finished(self) -> bool:
        """Returns True if track playback has reached the end."""
        return bool(self.track_finished)

    def _audio_callback(self, outdata, frames, time_info, status):
        """High-priority audio streaming thread callback with zero-memory block streaming."""
        if not self.is_playing or self.active_sf is None:
            outdata.fill(0)
            return

        with self._audio_lock:
            if self.active_sf is None:
                outdata.fill(0)
                return

            # If head buffer is available and current_frame < head_frames, read from head
            if self.head_buffer is not None and self.current_frame < self.head_frames:
                avail = min(frames, self.head_frames - self.current_frame)
                slice_data = self.head_buffer[self.current_frame : self.current_frame + avail]
                if avail < frames:
                    outdata[:avail] = slice_data * self.volume
                    self.current_frame += avail
                    try:
                        self.active_sf.seek(self.current_frame)
                    except Exception:
                        pass
                    rem = frames - avail
                    try:
                        rem_data = self.active_sf.read(rem, dtype='float32')
                    except Exception:
                        rem_data = np.zeros((0, self.channels), dtype=np.float32)
                    l = len(rem_data)
                    if l > 0:
                        if len(rem_data.shape) == 1:
                            outdata[avail:avail+l, 0] = rem_data * self.volume
                            outdata[avail:avail+l, 1] = rem_data * self.volume
                        else:
                            outdata[avail:avail+l] = rem_data * self.volume
                    if l < rem:
                        outdata[avail+l:] = 0
                        self.track_finished = True
                        self.is_playing = False
                    self.current_frame += l
                    self.head_buffer = None
                else:
                    outdata[:] = slice_data * self.volume
                    self.current_frame += frames
            else:
                try:
                    data = self.active_sf.read(frames, dtype='float32')
                except Exception:
                    data = np.zeros((0, self.channels), dtype=np.float32)
                l = len(data)
                if l < frames:
                    if l > 0:
                        if len(data.shape) == 1:
                            outdata[:l, 0] = data * self.volume
                            outdata[:l, 1] = data * self.volume
                        else:
                            outdata[:l] = data * self.volume
                    outdata[l:] = 0
                    self.current_frame = self.total_frames
                    self.track_finished = True
                    self.is_playing = False
                else:
                    if len(data.shape) == 1:
                        outdata[:, 0] = data * self.volume
                        outdata[:, 1] = data * self.volume
                    else:
                        outdata[:] = data * self.volume
                    self.current_frame += frames

        # Extract mono buffer for FFT visualizer (zero-allocation single channel slice)
        n = min(1024, frames)
        self.latest_buffer[:n] = outdata[:n, 0]

    def update_spectrum(self):
        """Vectorized FFT spectral analysis and bass beat energy computation (zero-allocation)."""
        if getattr(self, "eco_mode", False):
            self._eco_frame_counter = getattr(self, "_eco_frame_counter", 0) + 1
            if self._eco_frame_counter % 3 != 0 and getattr(self, "_cached_eco_spectrum", None) is not None:
                return self._cached_eco_spectrum

        buf = self.latest_buffer
        is_idle = (self.audio_mode == "player" and not self.is_playing) or np.max(np.abs(buf)) < 0.001
        if is_idle:
            if self.beat_energy > 0.002 or np.max(self.smoothed_bars) > 0.002:
                # Fast exponential decay towards zero
                self.smoothed_bars *= 0.82
                self.peak_bars *= 0.88
                self.beat_energy *= 0.80
            else:
                self.smoothed_bars.fill(0)
                self.peak_bars.fill(0)
                self.beat_energy = 0.0
            res = (self.smoothed_bars, self.peak_bars, self.beat_energy)
            if getattr(self, "eco_mode", False):
                self._cached_eco_spectrum = res
            return res

        # 1. Apply pre-computed Hanning window & Real FFT
        windowed = buf * self.hanning_window
        fft = np.abs(np.fft.rfft(windowed))

        # 2. Bass & kick drum energy (20Hz - 250Hz)
        bass_mag = float(np.mean(fft[1:8]))
        target_beat = min(1.0, bass_mag / 20.0)
        self.beat_energy = max(target_beat, self.beat_energy * 0.82)

        # 3. Logarithmic band grouping (reusing preallocated buffer, 0 bytes allocated)
        self.raw_bars.fill(0)
        for i in range(self.num_bars):
            start = self.indices[i]
            end = max(start + 1, self.indices[i + 1])
            self.raw_bars[i] = np.mean(fft[start:end])

        # Apply high-frequency boost and normalize to [0.0, 1.0] in-place
        np.clip((self.raw_bars * self.boost_weights) / 28.0, 0.0, 1.0, out=self.raw_bars)

        # 4. Vectorized attack & release smoothing
        rising = self.raw_bars > self.smoothed_bars
        self.smoothed_bars = np.where(
            rising,
            self.smoothed_bars + (self.raw_bars - self.smoothed_bars) * 0.65,  # Fast attack
            self.smoothed_bars + (self.raw_bars - self.smoothed_bars) * 0.16   # Smooth release
        )

        # 5. Vectorized peak hold with gravity acceleration
        new_peaks = self.smoothed_bars >= self.peak_bars
        self.peak_bars = np.where(
            new_peaks,
            self.smoothed_bars,
            np.maximum(0.0, self.peak_bars - self.peak_decay)
        )
        self.peak_decay = np.where(new_peaks, 0.005, self.peak_decay + 0.008)

        res = (self.smoothed_bars, self.peak_bars, self.beat_energy)
        if getattr(self, "eco_mode", False):
            self._cached_eco_spectrum = res
        return res

    def get_waveform(self, sample_count: int = 80) -> np.ndarray:
        """Returns sampled oscilloscope points [-1.0, 1.0]."""
        buf = self.latest_buffer
        if len(buf) < sample_count:
            return np.zeros(sample_count, dtype=np.float32)
        step = len(buf) // sample_count
        return np.clip(buf[::step][:sample_count] * 1.8, -1.0, 1.0)
