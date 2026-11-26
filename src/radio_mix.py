"""Lightweight Endless Random Mix engine for Talia.

Discovers unowned tracks matching the user's favourites/play history via
yt-dlp flat YouTube Mix / search metadata, respects user-configurable
exclusion checklists, buffers at most one track ahead in assets/radio_cache,
auto-cleans older temp files, and supports one-click permanent saving.
"""

import logging
import os
import random
import re
import shutil
import threading
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

from config import DEFAULT_MUSIC_DIR, PROJECT_ROOT, SUPPORTED_AUDIO_EXTS, trim_process_memory
from song_downloader import _get_yt_dlp, download_and_sync_lrc

if TYPE_CHECKING:
    from controller import ControlPanel

log = logging.getLogger("Talia.RadioMix")

RADIO_PLAYLIST_NAME = "★ Random Mix"
RADIO_CACHE_DIR = os.path.join(PROJECT_ROOT, "assets", "radio_cache")
MAX_PREFETCH_AHEAD = 2
MAX_PLAYED_HISTORY = 3  # Current song + 2 previous songs kept on disk
MAX_RADIO_CACHE = MAX_PREFETCH_AHEAD + MAX_PLAYED_HISTORY  # 5 total songs available
MAX_HISTORY_IDS = 200

DEFAULT_EXCLUSIONS: Dict[str, Tuple[str, bool]] = {
    "library_dupes": ("Songs Already in Library", True),
    "nightcore_sped": ("Nightcore / Sped Up / Slowed", True),
    "covers_remixes": ("Covers / Remixes / Karaoke", False),
    "live_concerts": ("Live / Concert Recordings", False),
    "long_mixes": ("Long Mixes (> 6 min)", True),
}

_CATEGORY_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "nightcore_sped": (
        "nightcore",
        "sped up",
        "speed up",
        "slowed",
        "reverb",
        "8d audio",
        "daycore",
    ),
    "covers_remixes": (
        "cover",
        "remix",
        "bootleg",
        "karaoke",
        "instrumental",
        "piano version",
        "acoustic version",
    ),
    "live_concerts": (
        "live at",
        "live performance",
        "concert",
        "world tour",
        "fancam",
        "tiny desk",
    ),
    "long_mixes": (
        "1 hour",
        "full album",
        "megamix",
        "mashup mix",
        "playlist mix",
        "compilation",
    ),
}

_NOISE_RE = re.compile(
    r"\([^)]*(?:official|audio|video|lyric|lyrics|mv|hd|4k)[^)]*\)"
    r"|\[[^\]]*(?:official|audio|video|lyric|lyrics|mv|hd|4k)[^\]]*\]",
    flags=re.I,
)


def _normalize_title_key(text: str) -> str:
    """Normalize track title/filename for fuzzy library duplicate matching."""
    cleaned = os.path.splitext(os.path.basename(text or ""))[0]
    cleaned = _NOISE_RE.sub("", cleaned)
    cleaned = re.sub(r"^\d{1,3}(?:[\.\-_]|\s+-)\s*", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned.lower()).strip()
    return cleaned


class RadioMixManager(QObject):
    """Manages endless taste-based discovery, 1-ahead buffering, and cache cleanup."""

    status_changed = pyqtSignal(str)
    track_ready = pyqtSignal(str, bool)  # (local_path, auto_play)
    prefetch_ready = pyqtSignal(str)
    track_saved_permanently = pyqtSignal(str)

    def __init__(self, panel: "ControlPanel", cache_dir: str = RADIO_CACHE_DIR):
        super().__init__(panel)
        self.panel = panel
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

        self.exclusions: Dict[str, bool] = {
            k: default_val for k, (_lbl, default_val) in DEFAULT_EXCLUSIONS.items()
        }
        self.excluded_artists: List[str] = []
        self.recent_artists: List[str] = []
        self.seen_video_ids: List[str] = []

        self.prefetch_queue: List[str] = []
        self.played_history: List[str] = []
        self._pending_deletes: List[str] = []
        self.last_seed_label: str = "Library Taste"
        self._busy_lock = threading.Lock()
        self._is_fetching: bool = False
        self._pending_autoplay: bool = False

    @property
    def prefetched_path(self) -> Optional[str]:
        return self.prefetch_queue[0] if self.prefetch_queue else None

    @prefetched_path.setter
    def prefetched_path(self, value: Optional[str]):
        if value is None:
            self.prefetch_queue.clear()
        else:
            if value not in self.prefetch_queue:
                self.prefetch_queue.insert(0, value)
                self.prefetch_queue = self.prefetch_queue[:MAX_PREFETCH_AHEAD]

    # -----------------------------------------------------------------
    # PERSISTENCE HELPERS
    # -----------------------------------------------------------------
    def export_state(self) -> dict:
        return {
            "radio_exclusions": dict(self.exclusions),
            "radio_excluded_artists": list(self.excluded_artists),
        }

    def load_state(self, cfg: dict):
        saved_exc = cfg.get("radio_exclusions")
        if isinstance(saved_exc, dict):
            for k in self.exclusions:
                if k in saved_exc:
                    self.exclusions[k] = bool(saved_exc[k])
        saved_art = cfg.get("radio_excluded_artists")
        if isinstance(saved_art, list):
            self.excluded_artists = [str(a).strip() for a in saved_art if str(a).strip()]

    def toggle_exclusion(self, key: str, enabled: bool):
        if key in self.exclusions:
            self.exclusions[key] = bool(enabled)
            # Clear stale prefetched tracks if user changed filter rules
            self.prefetch_queue = [
                p for p in self.prefetch_queue if self.is_track_currently_playing(p)
            ]

    def toggle_excluded_artist(self, artist: str, exclude: bool):
        clean = (artist or "").strip()
        if not clean:
            return
        lower_map = {a.lower(): a for a in self.excluded_artists}
        if exclude:
            if clean.lower() not in lower_map:
                self.excluded_artists.append(clean)
        else:
            existing = lower_map.get(clean.lower())
            if existing:
                self.excluded_artists.remove(existing)
        self.prefetch_queue = [
            p for p in self.prefetch_queue if self.is_track_currently_playing(p)
        ]

    def is_artist_excluded(self, artist: str) -> bool:
        low = (artist or "").strip().lower()
        return any(a.lower() == low for a in self.excluded_artists)

    def _remember_artist(self, artist: str):
        clean = (artist or "").strip()
        if not clean or clean.lower() in ("unknown", "various artists"):
            return
        self.recent_artists = [a for a in self.recent_artists if a.lower() != clean.lower()]
        self.recent_artists.insert(0, clean)
        self.recent_artists = self.recent_artists[:8]

    # -----------------------------------------------------------------
    # CACHE LISTING, CLEANUP & PERMANENT SAVE
    # -----------------------------------------------------------------
    def _flush_pending_deletes(self):
        """Retry deleting any previously locked cache files once playback moves on."""
        remaining: List[str] = []
        for p in self._pending_deletes:
            if not self._delete_audio_and_lrc(p):
                remaining.append(p)
        self._pending_deletes = remaining

    def restore_from_cache(self):
        """Adopt persisted files in assets/radio_cache on app startup into the 5-song window."""
        self._flush_pending_deletes()
        if not os.path.isdir(self.cache_dir):
            return
        files = []
        for fn in os.listdir(self.cache_dir):
            if fn.lower().endswith(SUPPORTED_AUDIO_EXTS):
                files.append(os.path.join(self.cache_dir, fn))
        files.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0.0)

        # Keep at most MAX_RADIO_CACHE (5) newest files on launch
        while len(files) > MAX_RADIO_CACHE:
            stale = files.pop(0)
            self._delete_audio_and_lrc(stale)

        if not files:
            self.played_history.clear()
            self.prefetch_queue.clear()
            self.status_changed.emit("Press Play to start Radio")
            return

        # Newest up to 2 act as buffered upcoming songs; remaining older (up to 3) form played_history
        split = max(0, len(files) - MAX_PREFETCH_AHEAD)
        if split == 0 and len(files) > 1:
            split = 1
        self.played_history = files[:split][-MAX_PLAYED_HISTORY:]
        self.prefetch_queue = files[split:][-MAX_PREFETCH_AHEAD:]
        self.status_changed.emit(
            f"Seed: {self.last_seed_label} · {len(self.prefetch_queue)}/{MAX_PREFETCH_AHEAD} queued"
        )

    def get_cached_tracks(self) -> List[str]:
        """Return cached radio tracks ordered chronologically: [prev2, prev1, current, next1, next2]."""
        self._flush_pending_deletes()
        if not os.path.isdir(self.cache_dir):
            return []
        pending_norm = {os.path.normcase(os.path.abspath(p)) for p in self._pending_deletes}
        ordered: List[str] = []
        seen_norm: set[str] = set()

        for p in list(self.played_history) + list(self.prefetch_queue):
            if p and os.path.exists(p):
                norm_p = os.path.normcase(os.path.abspath(p))
                if norm_p not in pending_norm and norm_p not in seen_norm:
                    seen_norm.add(norm_p)
                    ordered.append(p)

        extras: List[str] = []
        for fn in os.listdir(self.cache_dir):
            if fn.lower().endswith(SUPPORTED_AUDIO_EXTS):
                full = os.path.join(self.cache_dir, fn)
                norm_f = os.path.normcase(os.path.abspath(full))
                if norm_f not in pending_norm and norm_f not in seen_norm:
                    seen_norm.add(norm_f)
                    extras.append(full)
        extras.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0.0)
        return ordered + extras

    def is_radio_cached_track(self, path: Optional[str]) -> bool:
        if not path:
            return False
        try:
            norm_p = os.path.normcase(os.path.abspath(path))
            norm_dir = os.path.normcase(os.path.abspath(self.cache_dir))
            return norm_p.startswith(norm_dir + os.sep)
        except Exception:
            return False

    def is_track_currently_playing(self, path: Optional[str]) -> bool:
        if not path or not self.panel or not getattr(self.panel, "audio_engine", None):
            return False
        engine = self.panel.audio_engine
        target_norm = os.path.normcase(os.path.abspath(path))
        active_p = getattr(engine, "_active_file_path", "")
        if active_p and os.path.normcase(os.path.abspath(active_p)) == target_norm:
            return True
        idx = getattr(engine, "current_index", -1)
        pl = getattr(engine, "playlist", []) or []
        if 0 <= idx < len(pl):
            return os.path.normcase(os.path.abspath(pl[idx])) == target_norm
        return False

    def record_played_radio_track(self, path: str):
        """Keep current song + 2 previous songs; delete older songs once surpassed.

        With 2 buffered next tracks, up to 5 tracks stay available in ★ Random Mix:
        [prev 2, prev 1, current playing, buffered next 1, buffered next 2].
        """
        if not path or not self.is_radio_cached_track(path):
            return
        norm_new = os.path.normcase(os.path.abspath(path))
        self.prefetch_queue = [
            p
            for p in self.prefetch_queue
            if os.path.normcase(os.path.abspath(p)) != norm_new and os.path.exists(p)
        ]
        self.played_history = [
            p
            for p in self.played_history
            if os.path.normcase(os.path.abspath(p)) != norm_new and os.path.exists(p)
        ]
        self.played_history.append(path)

        while len(self.played_history) > MAX_PLAYED_HISTORY:
            evicted = self.played_history.pop(0)
            evicted_norm = os.path.normcase(os.path.abspath(evicted))
            if any(
                os.path.normcase(os.path.abspath(q)) == evicted_norm
                for q in self.prefetch_queue
            ):
                continue
            if not self._delete_audio_and_lrc(evicted):
                self._pending_deletes.append(evicted)

    def get_previous_track(self, current_path: Optional[str]) -> Optional[str]:
        """Step back through the kept played_history without triggering eviction."""
        existing = [p for p in self.played_history if os.path.exists(p)]
        if not existing:
            return None
        if current_path:
            norm_cur = os.path.normcase(os.path.abspath(current_path))
            for i, p in enumerate(existing):
                if os.path.normcase(os.path.abspath(p)) == norm_cur:
                    return existing[i - 1] if i > 0 else existing[0]
        return existing[-2] if len(existing) >= 2 else existing[-1]

    def cleanup_cache(self, max_keep: int = MAX_RADIO_CACHE):
        """Remove oldest temp tracks beyond max_keep, protecting 2 prev + current + 2 next."""
        self._flush_pending_deletes()
        cached = self.get_cached_tracks()
        if len(cached) <= max_keep:
            return
        protected = set()
        for q in self.prefetch_queue[:MAX_PREFETCH_AHEAD]:
            protected.add(os.path.normcase(os.path.abspath(q)))
        for p in self.played_history[-MAX_PLAYED_HISTORY:]:
            protected.add(os.path.normcase(os.path.abspath(p)))
        engine = getattr(self.panel, "audio_engine", None)
        if engine and 0 <= engine.current_index < len(engine.playlist):
            protected.add(os.path.normcase(os.path.abspath(engine.playlist[engine.current_index])))
        active_p = getattr(engine, "_active_file_path", "") if engine else ""
        if active_p:
            protected.add(os.path.normcase(os.path.abspath(active_p)))

        for stale in cached[:-max_keep]:
            norm_stale = os.path.normcase(os.path.abspath(stale))
            if norm_stale in protected:
                continue
            if not self._delete_audio_and_lrc(stale):
                self._pending_deletes.append(stale)

    @staticmethod
    def _delete_audio_and_lrc(audio_path: str) -> bool:
        """Delete audio and matching .lrc/.bak files. Returns True if all gone."""
        base = os.path.splitext(audio_path)[0]
        all_removed = True
        for target in (audio_path, base + ".lrc", base + ".lrc.bak"):
            if os.path.exists(target):
                try:
                    os.remove(target)
                except OSError:
                    all_removed = False
        return all_removed

    def save_track_permanently(self, cache_path: str) -> Tuple[bool, str]:
        """Copy/move a cached radio track + .lrc into <music_folder>/Downloaded Songs/.

        Uses copy-then-delete so saving never fails with WinError 32 while the
        audio file is open for live playback in SoundFile.
        """
        if not cache_path or not os.path.exists(cache_path):
            return False, "No cached radio track to save."
        if not self.is_radio_cached_track(cache_path):
            return False, "Track is already in your permanent library."

        music_root = (
            getattr(self.panel.audio_engine, "folder_path", "")
            if self.panel and getattr(self.panel, "audio_engine", None)
            else ""
        ) or DEFAULT_MUSIC_DIR
        target_dir = os.path.join(music_root, "Downloaded Songs")
        os.makedirs(target_dir, exist_ok=True)

        filename = os.path.basename(cache_path)
        stem, ext = os.path.splitext(filename)
        dest_audio = os.path.join(target_dir, filename)
        counter = 1
        while os.path.exists(dest_audio):
            dest_audio = os.path.join(target_dir, f"{stem} ({counter}){ext}")
            counter += 1

        try:
            shutil.copy2(cache_path, dest_audio)
            src_lrc = os.path.splitext(cache_path)[0] + ".lrc"
            if os.path.exists(src_lrc):
                dest_lrc = os.path.splitext(dest_audio)[0] + ".lrc"
                shutil.copy2(src_lrc, dest_lrc)
        except Exception as exc:
            return False, f"Failed to save track: {exc}"

        if not self._delete_audio_and_lrc(cache_path):
            self._pending_deletes.append(cache_path)

        # Keep audio_engine pointing cleanly at the saved file if it was active
        engine = getattr(self.panel, "audio_engine", None)
        if engine:
            norm_old = os.path.normcase(os.path.abspath(cache_path))
            active_p = getattr(engine, "_active_file_path", "")
            if active_p and os.path.normcase(os.path.abspath(active_p)) == norm_old:
                engine._active_file_path = dest_audio
            replaced = False
            for i, p in enumerate(engine.playlist):
                if os.path.normcase(os.path.abspath(p)) == norm_old:
                    engine.playlist[i] = dest_audio
                    replaced = True
                    break
            if not replaced:
                engine.playlist.append(dest_audio)

        norm_saved = os.path.normcase(os.path.abspath(cache_path))
        self.prefetch_queue = [
            p for p in self.prefetch_queue if os.path.normcase(os.path.abspath(p)) != norm_saved
        ]
        self.played_history = [
            p for p in self.played_history if os.path.normcase(os.path.abspath(p)) != norm_saved
        ]

        self.track_saved_permanently.emit(dest_audio)
        return True, f"Saved to {os.path.basename(target_dir)}/{os.path.basename(dest_audio)}"

    # -----------------------------------------------------------------
    # TASTE SEED & EXCLUSION FILTERING
    # -----------------------------------------------------------------
    def _build_library_title_set(self) -> set[str]:
        titles: set[str] = set()
        engine = getattr(self.panel, "audio_engine", None)
        if engine:
            for p in getattr(engine, "playlist", []) or []:
                if self.is_radio_cached_track(p):
                    continue
                key = _normalize_title_key(p)
                if key:
                    titles.add(key)
        for p in list(self.played_history) + list(self.prefetch_queue):
            key = _normalize_title_key(p)
            if key:
                titles.add(key)
        return titles

    def _pick_seed_query(self) -> Tuple[str, str]:
        """Return (search_query, human_label) from favourites, play counts, or library."""
        favs = [p for p in getattr(self.panel, "favourite_tracks", set()) if os.path.exists(p)]
        candidates: List[str] = []
        if favs:
            candidates = favs
        else:
            counts: Dict[str, int] = getattr(self.panel, "play_counts", {}) or {}
            ranked = sorted(
                [(p, c) for p, c in counts.items() if c > 0 and os.path.exists(p)],
                key=lambda x: x[1],
                reverse=True,
            )[:10]
            if ranked:
                candidates = [p for p, _ in ranked]
            elif self.panel and getattr(self.panel, "audio_engine", None):
                lib = [
                    p
                    for p in (self.panel.audio_engine.playlist or [])
                    if not self.is_radio_cached_track(p)
                ]
                if lib:
                    candidates = lib

        if not candidates:
            return "indie pop electronic chill music", "General Mix"

        chosen = random.choice(candidates)
        raw_stem = os.path.splitext(os.path.basename(chosen))[0]
        clean_seed = re.sub(r"^\d{1,3}(?:[\.\-_]|\s+-)\s*", "", raw_stem).strip()
        # Extract artist for label if "Artist - Title" format
        label = clean_seed.split(" - ")[0].strip() if " - " in clean_seed else clean_seed[:28]
        return clean_seed, (label or "Library Taste")

    def is_candidate_excluded(self, entry: dict, library_keys: Optional[set[str]] = None) -> bool:
        """Check whether a flat yt-dlp entry violates any active exclusion rule."""
        vid = str(entry.get("id") or "")
        if vid and vid in self.seen_video_ids:
            return True

        title = str(entry.get("title") or "")
        uploader = str(entry.get("uploader") or entry.get("channel") or "")
        combined = f"{title} {uploader}".lower()
        duration = float(entry.get("duration") or 0.0)

        if duration > 0 and duration < 45:
            return True
        if self.exclusions.get("long_mixes", True):
            if duration > 360:
                return True

        for exc_key, keywords in _CATEGORY_KEYWORDS.items():
            if self.exclusions.get(exc_key, False):
                if any(kw in combined for kw in keywords):
                    return True

        for artist in self.excluded_artists:
            if artist.lower() in combined:
                return True

        if self.exclusions.get("library_dupes", True):
            norm_cand = _normalize_title_key(title)
            if library_keys is None:
                library_keys = self._build_library_title_set()
            if norm_cand and any(
                norm_cand == lib_k or (len(norm_cand) > 6 and norm_cand in lib_k) or (len(lib_k) > 6 and lib_k in norm_cand)
                for lib_k in library_keys
            ):
                return True

        return False

    def _discover_candidate(self) -> Optional[dict]:
        """Find one fresh YouTube track matching taste & exclusions (flat metadata only)."""
        yt_dlp = _get_yt_dlp()
        seed_query, seed_label = self._pick_seed_query()
        self.last_seed_label = seed_label
        library_keys = self._build_library_title_set()

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "ignoreerrors": True,
            "playlistend": 20,
        }

        pool: List[dict] = []
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 1. Resolve seed to a video ID and fetch YouTube's lightweight Mix (RD<id>)
            seed_info = ydl.extract_info(f"ytsearch3:{seed_query} audio", download=False)
            seed_entries = (seed_info or {}).get("entries") or []
            seed_id = next((e.get("id") for e in seed_entries if e and e.get("id")), None)
            if seed_id:
                mix_url = f"https://www.youtube.com/watch?v={seed_id}&list=RD{seed_id}"
                mix_info = ydl.extract_info(mix_url, download=False)
                for e in (mix_info or {}).get("entries") or []:
                    if e and e.get("id") and e.get("id") != seed_id:
                        pool.append(e)

            # 2. Fallback: broader search around seed if Mix returned nothing usable
            valid = [e for e in pool if not self.is_candidate_excluded(e, library_keys)]
            if not valid:
                artist_hint = seed_query.split(" - ")[0].strip()
                fb_info = ydl.extract_info(
                    f"ytsearch12:{artist_hint} similar songs music", download=False
                )
                for e in (fb_info or {}).get("entries") or []:
                    if e and e.get("id") and not self.is_candidate_excluded(e, library_keys):
                        valid.append(e)
            pool = valid

        if not pool:
            return None
        chosen = random.choice(pool[:12])
        vid = str(chosen.get("id") or "")
        if vid:
            self.seen_video_ids.append(vid)
            self.seen_video_ids = self.seen_video_ids[-MAX_HISTORY_IDS:]
        return chosen

    # -----------------------------------------------------------------
    # ASYNC DOWNLOAD & 2-AHEAD PREFETCH
    # -----------------------------------------------------------------
    def _prune_prefetch_queue(self):
        self.prefetch_queue = [p for p in self.prefetch_queue if p and os.path.exists(p)]

    def request_next_track(self, auto_play: bool = True):
        """Play next buffered track immediately if ready, and top up 2-ahead buffer."""
        self._prune_prefetch_queue()
        if auto_play and self.prefetch_queue:
            ready_path = self.prefetch_queue.pop(0)
            self.track_ready.emit(ready_path, True)
            self.prefetch_next()
            return

        with self._busy_lock:
            if self._is_fetching:
                if auto_play:
                    self._pending_autoplay = True
                return
            self._is_fetching = True
            self._pending_autoplay = auto_play

        self.status_changed.emit(f"Discovering track (seed: {self.last_seed_label})...")
        threading.Thread(
            target=self._fetch_worker,
            daemon=True,
            name="RadioMixFetcher",
        ).start()

    def prefetch_next(self):
        """Pre-buffer upcoming tracks sequentially until 2 next tracks are ready."""
        self._prune_prefetch_queue()
        if len(self.prefetch_queue) >= MAX_PREFETCH_AHEAD:
            return
        self.request_next_track(auto_play=False)

    def _fetch_worker(self):
        saved_path = ""
        try:
            cand = self._discover_candidate()
            if not cand:
                self.status_changed.emit("No fresh unexcluded tracks found. Try relaxing filters.")
                return

            vid = str(cand.get("id") or "")
            url = f"https://www.youtube.com/watch?v={vid}"
            title = str(cand.get("title") or "Unknown Track")
            uploader = str(cand.get("uploader") or cand.get("channel") or "").replace(" - Topic", "").strip()
            if uploader:
                self._remember_artist(uploader)

            self.status_changed.emit(f"Buffering: {title[:34]}...")
            ok, audio_path, _err = download_and_sync_lrc(
                url,
                self.cache_dir,
                track_info={"title": title, "artist": uploader} if " - " not in title else None,
            )
            if ok and audio_path and os.path.exists(audio_path):
                saved_path = audio_path
                self.cleanup_cache()
        except Exception as exc:
            log.warning(f"[RADIO MIX] Fetch worker failed: {exc}")
            self.status_changed.emit("Radio fetch failed — retrying on next skip.")
        finally:
            with self._busy_lock:
                autoplay = self._pending_autoplay
                self._is_fetching = False
                self._pending_autoplay = False

            if saved_path:
                if autoplay:
                    self.status_changed.emit(f"Seed: {self.last_seed_label}")
                    self.track_ready.emit(saved_path, True)
                    self.prefetch_next()
                else:
                    self.prefetch_queue.append(saved_path)
                    queued_n = len(self.prefetch_queue)
                    self.status_changed.emit(
                        f"Seed: {self.last_seed_label} · {queued_n}/{MAX_PREFETCH_AHEAD} queued"
                    )
                    self.prefetch_ready.emit(saved_path)
                    if queued_n < MAX_PREFETCH_AHEAD:
                        self.prefetch_next()
            trim_process_memory()
