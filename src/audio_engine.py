"""
High-performance audio streaming engine with vectorized FFT spectral analysis.
"""

import os
import random
import threading
import ctypes
import sounddevice as sd
import soundfile as sf
import numpy as np

from config import (
    SUPPORTED_AUDIO_EXTS, user32, trim_process_memory,
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
        self.effective_gain = float(self.volume ** 2.2)

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
        self._shuffle = False
        self._shuffle_order = []
        self._shuffle_pos = -1
        self.track_finished = False
        self.queue = []

        # Zero-freeze Stream Reuse & Predictive Preloader
        self._audio_lock = threading.Lock()
        self._preload_cache = {}

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @shuffle.setter
    def shuffle(self, enabled: bool):
        self._shuffle = bool(enabled)
        if self._shuffle:
            self.rebuild_shuffle_order(starting_index=self.current_index)
            self._trigger_preload_next()
        else:
            self._shuffle_order.clear()
            self._shuffle_pos = -1
            self._trigger_preload_next()

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
            print(f"[DESKTOP AUDIO ERROR] {e}")
        finally:
            ctypes.windll.ole32.CoUninitialize()

    def set_lyrics_manager(self, mgr):
        self.lyrics_manager = mgr

    def set_folder(self, folder_path: str):
        """Sets the active playlist directory and refreshes tracks."""
        self.folder_path = folder_path
        self._preload_cache.clear()
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

    def _extract_cluster_key(self, path: str) -> str:
        """Extracts artist or folder cluster key for Spotify-style balanced shuffling."""
        if not path:
            return "unknown"
        fname = os.path.splitext(os.path.basename(path))[0]
        if " - " in fname:
            part = fname.split(" - ")[0].strip().lower()
            import re
            part = re.sub(r'^\d+[\.\s_-]+', '', part).strip()
            return part or "unknown"
        parent = os.path.basename(os.path.dirname(path)).strip().lower()
        return parent or "unknown"

    def rebuild_shuffle_order(self, starting_index: int = -1):
        """
        Builds a balanced Spotify-style shuffle order using distributed dithering.
        Spreads songs by the same artist/folder evenly across the timeline with jitter,
        preventing back-to-back clusters while keeping natural variety.
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

        # 1. Group track indices by artist/folder
        clusters = {}
        for idx, path in enumerate(self.playlist):
            key = self._extract_cluster_key(path)
            if key not in clusters:
                clusters[key] = []
            clusters[key].append(idx)

        # 2. Distribute each cluster across [0.0, 1.0) timeline with dither jitter
        items = []
        for key, indices in clusters.items():
            k = len(indices)
            shuffled = list(indices)
            random.shuffle(shuffled)
            step = 1.0 / k
            offset = random.uniform(0.0, step)
            for i, track_idx in enumerate(shuffled):
                base_pos = (i * step) + offset
                jitter = random.uniform(-0.15 * step, 0.15 * step)
                pos = (base_pos + jitter) % 1.0
                items.append((pos, track_idx, key))

        # Sort all tracks by timeline position
        items.sort(key=lambda x: x[0])
        order = [x[1] for x in items]
        keys = [x[2] for x in items]

        # 3. Anti-consecutive collision pass (prevent same artist playing consecutively)
        for i in range(len(order) - 1):
            if keys[i] == keys[i + 1]:
                for j in range(i + 2, min(i + 8, len(order))):
                    if keys[j] != keys[i]:
                        order[i + 1], order[j] = order[j], order[i + 1]
                        keys[i + 1], keys[j] = keys[j], keys[i + 1]
                        break

        # 4. If starting_index specified, place it at the beginning of the order
        if 0 <= starting_index < n and starting_index in order:
            idx_in_order = order.index(starting_index)
            order.pop(idx_in_order)
            order.insert(0, starting_index)

        self._shuffle_order = order
        self._shuffle_pos = 0

    def refresh_playlist(self):
        """Recursively scans the folder and all subfolders (Foobar2000 structure) for supported audio files."""
        if not self.folder_path or not os.path.exists(self.folder_path):
            self.playlist = []
            self._shuffle_order.clear()
            self._shuffle_pos = -1
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

        if self._shuffle:
            self.rebuild_shuffle_order(starting_index=self.current_index)

    def play_index(self, idx: int) -> bool:
        """Loads and plays the track at the specified index."""
        if not self.playlist or idx < 0 or idx >= len(self.playlist):
            return False
        self.current_index = idx
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
            trim_process_memory(force_gc=False)
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
            if self._shuffle:
                if not self._shuffle_order or len(self._shuffle_order) != len(self.playlist):
                    self.rebuild_shuffle_order(starting_index=self.current_index)
                next_pos = (self._shuffle_pos + 1) % len(self._shuffle_order)
                next_track_path = self.playlist[self._shuffle_order[next_pos]]
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
                stereo = np.empty((len(audio), 2), dtype=np.float32)
                stereo[:, 0] = audio
                stereo[:, 1] = audio
                audio = stereo
            # Cache strictly 1 track maximum
            self._preload_cache.clear()
            self._preload_cache[path] = (audio, sr, info.frames, audio.shape[1])
        except Exception:
            pass

    def play(self):
        self.is_playing = True
        self.is_paused = False
        if self.stream is not None:
            if not self.stream.active:
                try:
                    self.stream.start()
                except Exception as e:
                    print(f"[AUDIO ERROR] stream.start() failed: {e}")

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
        if self._shuffle:
            if not self._shuffle_order or len(self._shuffle_order) != len(self.playlist):
                self.rebuild_shuffle_order(starting_index=self.current_index)

            self._shuffle_pos += 1
            if self._shuffle_pos >= len(self._shuffle_order):
                last_idx = self._shuffle_order[-1] if self._shuffle_order else -1
                self.rebuild_shuffle_order()
                if len(self._shuffle_order) > 1 and self._shuffle_order[0] == last_idx:
                    self._shuffle_order[0], self._shuffle_order[1] = self._shuffle_order[1], self._shuffle_order[0]
                self._shuffle_pos = 0

            idx = self._shuffle_order[self._shuffle_pos]
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
        if self.sr > 0 and self.active_sf is not None:
            with self._audio_lock:
                target_frame = int(seconds * self.sr)
                target_frame = max(0, min(target_frame, self.total_frames))
                try:
                    self.active_sf.seek(target_frame)
                    self.current_frame = target_frame
                    self.head_buffer = None
                    self.track_finished = False
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
        # Set volume from 0.0 to 1.0
        self.volume = max(0.0, min(float(vol), 1.0))
        # Logarithmic perceptual curve for quiet volume down to -88 dB
        self.effective_gain = float(self.volume ** 2.2) if self.volume > 0.0 else 0.0

    def get_current_track_title(self) -> str:
        if self.audio_mode == "desktop":
            return "Desktop Audio"
        if 0 <= self.current_index < len(self.playlist):
            return os.path.basename(self.playlist[self.current_index])
        return "No Track Loaded"

    def is_track_finished(self) -> bool:
        return bool(self.track_finished)

    def _audio_callback(self, outdata, frames, time_info, status):
        # Audio streaming callback
        if not self.is_playing or self.active_sf is None:
            outdata.fill(0)
            return

        gain = self.effective_gain
        with self._audio_lock:
            if self.active_sf is None:
                outdata.fill(0)
                return

            if self.head_buffer is not None and self.current_frame < self.head_frames:
                avail = min(frames, self.head_frames - self.current_frame)
                slice_data = self.head_buffer[self.current_frame : self.current_frame + avail]
                if avail < frames:
                    outdata[:avail] = slice_data * gain
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
                            outdata[avail:avail+l, 0] = rem_data * gain
                            outdata[avail:avail+l, 1] = rem_data * gain
                        else:
                            outdata[avail:avail+l] = rem_data * gain
                    if l < rem:
                        outdata[avail+l:] = 0
                        self.track_finished = True
                        self.is_playing = False
                    self.current_frame += l
                    self.head_buffer = None
                else:
                    outdata[:] = slice_data * gain
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
                            outdata[:l, 0] = data * gain
                            outdata[:l, 1] = data * gain
                        else:
                            outdata[:l] = data * gain
                    outdata[l:] = 0
                    self.current_frame = self.total_frames
                    self.track_finished = True
                    self.is_playing = False
                else:
                    if len(data.shape) == 1:
                        outdata[:, 0] = data * gain
                        outdata[:, 1] = data * gain
                    else:
                        outdata[:] = data * gain
                    self.current_frame += frames

        # Mono buffer for visualizer FFT
        n = min(1024, frames)
        norm_factor = max(gain, 0.05) if gain > 0 else 1.0
        self.latest_buffer[:n] = outdata[:n, 0] / norm_factor

    def update_spectrum(self):
        # FFT spectral analysis and bass beat energy
        if getattr(self, "eco_mode", False):
            self._eco_frame_counter = getattr(self, "_eco_frame_counter", 0) + 1
            if self._eco_frame_counter % 3 != 0 and getattr(self, "_cached_eco_spectrum", None) is not None:
                return self._cached_eco_spectrum

        buf = self.latest_buffer
        buf_peak = max(float(buf.max()), -float(buf.min()))
        is_idle = (self.audio_mode == "player" and not self.is_playing) or buf_peak < 0.001
        if is_idle:
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
            res = (self.smoothed_bars, self.peak_bars, self.beat_energy)
            if getattr(self, "eco_mode", False):
                self._cached_eco_spectrum = res
            return res

        # 1. Apply Hanning window and Real FFT
        np.multiply(buf, self.hanning_window, out=self._windowed_buffer)
        fft = np.abs(np.fft.rfft(self._windowed_buffer))

        # 2. Bass energy (20Hz - 250Hz)
        bass_mag = float(np.mean(fft[1:8]))
        target_beat = min(1.0, bass_mag / 28.0)
        self.beat_energy = max(target_beat, self.beat_energy * 0.82)

        # 3. Logarithmic band grouping
        self.raw_bars.fill(0)
        for i in range(self.num_bars):
            start = self.indices[i]
            end = max(start + 1, self.indices[i + 1])
            self.raw_bars[i] = np.mean(fft[start:end])

        # Apply high-frequency boost and normalization
        np.clip((self.raw_bars * self.boost_weights) / 38.0, 0.0, 1.0, out=self.raw_bars)

        # 4. Attack and release smoothing
        rising = self.raw_bars > self.smoothed_bars
        diff = self.raw_bars - self.smoothed_bars
        self.smoothed_bars = np.where(
            rising,
            self.smoothed_bars + diff * 0.65,
            self.smoothed_bars + diff * 0.16
        )

        # 5. Peak hold with decay
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
        # Sampled oscilloscope points
        buf = self.latest_buffer
        if len(buf) < sample_count:
            return np.zeros(sample_count, dtype=np.float32)
        step = len(buf) // sample_count
        return np.clip(buf[::step][:sample_count] * 1.25, -1.0, 1.0)
