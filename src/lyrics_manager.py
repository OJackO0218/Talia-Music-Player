"""
Lyrics Manager: Synchronized LRC lyrics parser, cache manager, and auto-fetcher.
Fetches high-accuracy timestamps from LRCLIB (Spotify/Musixmatch data source) and manages local .lrc files.
"""

import os
import re
import json
import time
import urllib.request
import urllib.parse
import threading
from typing import List, Tuple, Optional


class LyricsManager:
    """Manages synchronized line-by-line lyrics with offline cache and LRCLIB integration."""

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
        """Parses standard LRC text into sorted [(timestamp_seconds, text), ...] list."""
        parsed: List[Tuple[float, str]] = []
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
            return

        with self.lock:
            self.current_track_path = track_path
            self.current_title = title_hint or self.clean_title(track_path)
            self.lines = []
            self.has_lyrics = False
            self.is_loading = True

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
            # Query by search API
            search_query = f"{query_title} {query_artist}".strip()
            url = f"https://lrclib.net/api/search?q={urllib.parse.quote(search_query)}"
            req = urllib.request.Request(url, headers={"User-Agent": "TaliaLyrics/1.0"})

            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            synced_content = None
            if isinstance(data, list):
                for item in data:
                    if item.get("syncedLyrics"):
                        synced_content = item["syncedLyrics"]
                        break

            if synced_content:
                parsed = self.parse_lrc(synced_content)
                if parsed:
                    # Save to cache
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

    def get_current_line_info(self, current_time: float) -> Tuple[int, str, float, float]:
        """
        Returns (line_index, text, time_since_line_start, line_duration).
        If before the first line or no lyrics, returns (-1, "", 0.0, 0.0).
        """
        with self.lock:
            if not self.lines:
                return -1, "", 0.0, 0.0

            # Find the active line index: largest timestamp <= current_time
            idx = -1
            for i, (ts, text) in enumerate(self.lines):
                if ts <= current_time:
                    idx = i
                else:
                    break

            if idx == -1:
                return -1, "", 0.0, 0.0

            ts, text = self.lines[idx]
            time_into_line = current_time - ts

            # Calculate active duration to next line
            if idx + 1 < len(self.lines):
                next_ts = self.lines[idx + 1][0]
                gap = max(0.5, next_ts - ts)
                # Vocal singing duration: typically 80% of gap or estimated by word count
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
