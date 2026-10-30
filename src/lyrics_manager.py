"""
Lyrics Manager: Synchronized LRC lyrics parser, cache manager, and auto-fetcher.
Fetches high-accuracy timestamps from LRCLIB (Spotify/Musixmatch data source) and manages local .lrc files.
Includes full support for [offset: +/-ms] tags, manual micro-tuning, per-track persistence,
and automated audio-onset alignment.
"""

import os
import re
import json
import time
import urllib.request
import urllib.parse
import threading
from typing import List, Tuple, Optional, Dict

try:
    from config import load_settings, save_settings
except ImportError:
    def load_settings():
        return {}
    def save_settings(data):
        return True


class LyricsManager:
    """Manages synchronized line-by-line lyrics with offline cache, LRCLIB integration, and auto-sync offset."""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir or ""
        if self.cache_dir and not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir, exist_ok=True)
            except Exception:
                pass

        # Lyrics data: list of (timestamp_in_seconds, text_content)
        self.lines: List[Tuple[float, str]] = []
        self.current_track_path: str = ""
        self.current_title: str = ""
        self.is_loading: bool = False
        self.has_lyrics: bool = False
        self.lock = threading.Lock()

        # Offset management (in seconds)
        # Standard LRC [offset: +/-ms] tag: positive means lyrics play earlier
        self.file_offset: float = 0.0
        self.manual_offset: float = 0.0

        # Per-track saved offsets dictionary: { "filename": offset_in_seconds }
        self.track_offsets: Dict[str, float] = {}
        self._load_saved_offsets()

    def _load_saved_offsets(self):
        """Loads saved track offsets from settings.json."""
        try:
            cfg = load_settings()
            offsets = cfg.get("lyrics_offsets", {})
            if isinstance(offsets, dict):
                self.track_offsets = {k: float(v) for k, v in offsets.items()}
        except Exception as e:
            print(f"[LYRICS] Could not load saved offsets: {e}")
            self.track_offsets = {}

    def _save_current_track_offset(self):
        """Persists the current track's manual offset into settings.json."""
        if not self.current_track_path:
            return
        track_key = os.path.basename(self.current_track_path)
        with self.lock:
            if abs(self.manual_offset) > 0.01:
                self.track_offsets[track_key] = round(self.manual_offset, 2)
            else:
                self.track_offsets.pop(track_key, None)

        try:
            cfg = load_settings()
            cfg["lyrics_offsets"] = self.track_offsets
            save_settings(cfg)
        except Exception as e:
            print(f"[LYRICS] Failed to save track offset: {e}")

    def clean_title(self, filename: str) -> str:
        """Strips tags, file extensions, and common packaging noise to isolate song title."""
        stem = os.path.splitext(os.path.basename(filename))[0]
        # Remove tags like CPE-2, _Compressed_, 1080p, etc.
        stem = re.sub(r'[-_]?(CPE|Compressed|1080p|720p|Official|Remastered)[-_0-9]*', '', stem, flags=re.I)
        # Normalize dashes and underscores
        stem = stem.replace('_', ' ').replace('-', ' ')
        # Fix common punctuation/spelling like Who s -> Who's, Tommorow -> Tomorrow
        stem = re.sub(r'\bWho\s+s\b', "Who's", stem, flags=re.I)
        stem = re.sub(r'\bTommorow\b', "Tomorrow", stem, flags=re.I)
        # Collapse multiple whitespace
        stem = re.sub(r'\s+', ' ', stem).strip()
        return stem

    def parse_lrc(self, lrc_text: str) -> List[Tuple[float, str]]:
        """Parses standard LRC text into sorted [(timestamp_seconds, text), ...] list and extracts offset tag."""
        parsed: List[Tuple[float, str]] = []

        # Extract standard LRC [offset: +/-ms] tag if present
        # Note: positive offset means lyrics trigger earlier (+effective_time)
        offset_match = re.search(r'\[offset:\s*([+-]?\d+)\]', lrc_text, flags=re.I)
        if offset_match:
            try:
                ms_val = float(offset_match.group(1))
                self.file_offset = ms_val / 1000.0
            except Exception:
                self.file_offset = 0.0
        else:
            self.file_offset = 0.0

        # Matches [mm:ss.xx] or [mm:ss.xxx] or [mm:ss]
        pattern = re.compile(r'\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]')

        for line in lrc_text.splitlines():
            line = line.strip()
            if not line:
                continue
            matches = list(pattern.finditer(line))
            if not matches:
                continue

            # Strip all timestamp tags to extract the text content
            text = pattern.sub('', line).strip()
            for m in matches:
                mins = int(m.group(1))
                secs = int(m.group(2))
                ms_str = m.group(3)
                if ms_str:
                    ms = float("0." + ms_str)
                else:
                    ms = 0.0
                timestamp = mins * 60.0 + secs + ms
                parsed.append((timestamp, text))

        parsed.sort(key=lambda x: x[0])
        return parsed

    def load_track(self, track_path: str, title_hint: str = "", artist_hint: str = ""):
        """Loads synced lyrics for the given audio track. Priority: 1) local .lrc, 2) cache, 3) LRCLIB."""
        if not track_path:
            with self.lock:
                self.lines = []
                self.has_lyrics = False
                self.current_track_path = ""
                self.file_offset = 0.0
                self.manual_offset = 0.0
            return

        with self.lock:
            self.current_track_path = track_path
            self.current_title = title_hint or self.clean_title(track_path)
            self.lines = []
            self.has_lyrics = False
            self.is_loading = True
            self.file_offset = 0.0

            # Restore per-track saved offset
            track_key = os.path.basename(track_path)
            self.manual_offset = float(self.track_offsets.get(track_key, 0.0))

        # 1. Check local .lrc file right next to audio file
        local_lrc = os.path.splitext(track_path)[0] + ".lrc"
        if os.path.exists(local_lrc):
            try:
                with open(local_lrc, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                parsed = self.parse_lrc(content)
                if parsed:
                    with self.lock:
                        self.lines = parsed
                        self.has_lyrics = True
                        self.is_loading = False
                    return
            except Exception as e:
                print(f"[LYRICS] Error reading local LRC {local_lrc}: {e}")

        # 2. Check local lyrics cache directory
        cache_file = ""
        if self.cache_dir:
            safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', self.current_title) + ".lrc"
            cache_file = os.path.join(self.cache_dir, safe_name)
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    parsed = self.parse_lrc(content)
                    if parsed:
                        with self.lock:
                            self.lines = parsed
                            self.has_lyrics = True
                            self.is_loading = False
                        return
                except Exception as e:
                    print(f"[LYRICS] Error reading cached LRC {cache_file}: {e}")

        # 3. Fetch from LRCLIB asynchronously
        threading.Thread(
            target=self._fetch_remote_lyrics,
            args=(self.current_title, artist_hint, cache_file, track_path),
            daemon=True
        ).start()

    def _fetch_remote_lyrics(self, query_title: str, query_artist: str, cache_file: str, track_path: str):
        """Background worker that queries LRCLIB for Spotify/Musixmatch synced lyrics."""
        try:
            search_query = f"{query_title} {query_artist}".strip()
            url = f"https://lrclib.net/api/search?q={urllib.parse.quote(search_query)}"
            req = urllib.request.Request(url, headers={"User-Agent": "TaliaLyrics/1.0"})

            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            synced_content = None
            if isinstance(data, list):
                # Try to determine target audio duration from file
                target_dur = 0.0
                if track_path and os.path.exists(track_path):
                    try:
                        import soundfile as sf
                        info = sf.info(track_path)
                        target_dur = info.duration
                    except Exception:
                        pass

                best_item = None
                best_diff = float("inf")
                for item in data:
                    synced = item.get("syncedLyrics")
                    if not synced:
                        continue
                    cand_dur = float(item.get("duration") or 0.0)
                    if target_dur > 10.0 and cand_dur > 10.0:
                        diff = abs(cand_dur - target_dur)
                        if diff < best_diff:
                            best_diff = diff
                            best_item = item
                            if diff < 2.5:
                                break
                    elif best_item is None:
                        best_item = item

                if best_item and best_item.get("syncedLyrics"):
                    synced_content = best_item["syncedLyrics"]

            if synced_content:
                parsed = self.parse_lrc(synced_content)
                if parsed:
                    if cache_file:
                        try:
                            with open(cache_file, "w", encoding="utf-8") as f:
                                f.write(synced_content)
                        except Exception:
                            pass

                    with self.lock:
                        if self.current_track_path == track_path:
                            self.lines = parsed
                            self.has_lyrics = True
                            self.is_loading = False
                            print(f"[LYRICS] Synced lyrics loaded for '{query_title}' ({len(parsed)} lines)")
                            return

            print(f"[LYRICS] No synchronized lyrics found on LRCLIB for '{query_title}'")
        except Exception as e:
            print(f"[LYRICS] Online fetch failed for '{query_title}': {e}")
        finally:
            with self.lock:
                if self.current_track_path == track_path:
                    self.is_loading = False

    def get_total_offset(self) -> float:
        """Returns the active total offset applied to playback time in seconds."""
        with self.lock:
            return round(self.manual_offset + self.file_offset, 2)

    def adjust_offset(self, delta: float, persist: bool = True) -> float:
        """Shifts the manual offset by delta seconds (e.g. +0.25s or -0.25s) and saves."""
        with self.lock:
            self.manual_offset = round(self.manual_offset + delta, 2)
        if persist:
            self._save_current_track_offset()
        return self.get_total_offset()

    def set_offset(self, val: float, persist: bool = True) -> float:
        """Explicitly sets the manual offset in seconds and saves."""
        with self.lock:
            self.manual_offset = round(val, 2)
        if persist:
            self._save_current_track_offset()
        return self.get_total_offset()

    def reset_offset(self, persist: bool = True) -> float:
        """Resets the manual offset to 0.0s and saves."""
        with self.lock:
            self.manual_offset = 0.0
        if persist:
            self._save_current_track_offset()
        return self.get_total_offset()

    def auto_align_with_audio(self, audio_path: Optional[str] = None) -> Tuple[bool, float, str]:
        """
        Analyzes the audio file's initial energy onset and compares with the first lyric timestamp.
        If a significant discrepancy is detected, automatically applies the calculated offset.
        Returns (success, applied_offset, status_message).
        """
        target_path = audio_path or self.current_track_path
        if not target_path or not os.path.exists(target_path):
            return False, 0.0, "No audio file loaded"

        with self.lock:
            if not self.lines:
                return False, 0.0, "No lyrics loaded for track"
            # Find first non-empty lyric line timestamp
            first_lyric_ts = None
            for ts, text in self.lines:
                if len(text.strip()) > 1:
                    first_lyric_ts = ts
                    break

        if first_lyric_ts is None:
            return False, 0.0, "No valid lyric lines found"

        try:
            import soundfile as sf
            import numpy as np

            data, sr = sf.read(target_path)
            if len(data.shape) > 1:
                data = data.mean(axis=1)

            # Analyze first 35 seconds of audio in 50ms hops
            max_samples = int(min(len(data), sr * 35.0))
            hop = int(sr * 0.05)
            rms_list = []
            times = []

            for i in range(0, max_samples - hop, hop):
                chunk = data[i:i + hop]
                rms = np.sqrt(np.mean(chunk**2))
                rms_list.append(rms)
                times.append(i / float(sr))

            rms_arr = np.array(rms_list)
            if len(rms_arr) == 0:
                return False, 0.0, "Audio empty or unreadable"

            peak_rms = float(np.max(rms_arr))
            thresh = max(0.08, peak_rms * 0.28)

            detected_onset = 0.0
            for i in range(len(rms_arr) - 3):
                if rms_arr[i] >= thresh and rms_arr[i+1] >= thresh and rms_arr[i+2] >= thresh:
                    detected_onset = round(float(times[i]), 2)
                    break

            diff = round(detected_onset - first_lyric_ts, 2)
            # Only apply auto-sync if discrepancy is substantial (>= 1.5 seconds)
            if abs(diff) >= 1.5:
                needed_offset = round(first_lyric_ts - detected_onset, 2)
                self.set_offset(needed_offset, persist=True)
                return True, needed_offset, f"Auto-synced: {needed_offset:+.2f}s (onset: {detected_onset}s, lyric: {first_lyric_ts}s)"
            else:
                return False, 0.0, f"Already aligned within threshold (diff: {diff:+.2f}s)"

        except Exception as e:
            return False, 0.0, f"Auto-sync analysis error: {e}"

    def get_current_line_info(self, current_time: float) -> Tuple[int, str, float, float]:
        """
        Returns (line_index, text, time_since_line_start, line_duration).
        Takes into account total sync offset (file offset + manual offset).
        If before the first line or no lyrics, returns (-1, "", 0.0, 0.0).
        """
        with self.lock:
            if not self.lines:
                return -1, "", 0.0, 0.0

            # Apply sync offset: positive moves lyrics earlier
            effective_time = max(0.0, current_time + self.manual_offset + self.file_offset)

            # Find the active line index: largest timestamp <= effective_time
            idx = -1
            for i, (ts, text) in enumerate(self.lines):
                if ts <= effective_time:
                    idx = i
                else:
                    break

            if idx == -1:
                return -1, "", 0.0, 0.0

            ts, text = self.lines[idx]
            time_into_line = effective_time - ts

            # Calculate active duration to next line
            if idx + 1 < len(self.lines):
                next_ts = self.lines[idx + 1][0]
                gap = max(0.5, next_ts - ts)
                word_count = max(1, len(text.split()))
                est_dur = max(2.0, word_count * 0.42)
                singing_dur = min(gap * 0.85, est_dur)
                if gap > 5.5 and time_into_line > 4.5:
                    return -1, "", 0.0, 0.0
            else:
                word_count = max(1, len(text.split()))
                singing_dur = max(2.5, word_count * 0.45)

            return idx, text, time_into_line, singing_dur

    def get_current_line(self, current_time: float) -> Tuple[int, str, float]:
        """Backwards-compatible helper returning (line_index, text, time_into_line)."""
        idx, text, time_into, _ = self.get_current_line_info(current_time)
        return idx, text, time_into
