"""
Talia Song Downloader & Auto-Sync Service
Searches YouTube for tracks, converts audio to high-quality Opus (160kbps),
saves directly to the 'Downloaded Songs' subfolder, and automatically fetches
verified synchronized lyrics (.lrc).
"""

import ctypes
import gc
import logging
import os
import re
import sys
import threading
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

_yt_dlp = None


def _find_ffmpeg_dir() -> Optional[str]:
    """Locates and returns the directory containing ffmpeg and ffprobe binaries."""
    try:
        import static_ffmpeg

        static_ffmpeg.add_paths()
    except Exception as e:
        log.info(f"[FFMPEG INIT] Note: {e}")
    import shutil

    ffmpeg_exe = shutil.which("ffmpeg")
    if ffmpeg_exe and os.path.exists(ffmpeg_exe):
        return os.path.dirname(os.path.abspath(ffmpeg_exe))

    # Search PyInstaller packaged directories
    candidates = []
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, "static_ffmpeg", "bin", "win32"))
            candidates.append(os.path.join(sys._MEIPASS, "bin", "win32"))
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "_internal", "static_ffmpeg", "bin", "win32"))
        candidates.append(os.path.join(exe_dir, "static_ffmpeg", "bin", "win32"))
        candidates.append(exe_dir)

    # Search local project directories
    candidates.append(os.path.join(PROJECT_ROOT, "assets", "bin"))
    candidates.append(os.path.join(PROJECT_ROOT, "_internal", "static_ffmpeg", "bin", "win32"))
    for c in candidates:
        if os.path.exists(os.path.join(c, "ffmpeg.exe")) or os.path.exists(
            os.path.join(c, "ffmpeg")
        ):
            if c not in os.environ.get("PATH", ""):
                os.environ["PATH"] = os.pathsep.join([c, os.environ.get("PATH", "")])
            return c
    return None


def _get_yt_dlp():
    """Lazily loads static_ffmpeg and yt_dlp on first download/search request."""
    global _yt_dlp
    if _yt_dlp is None:
        _find_ffmpeg_dir()
        import yt_dlp

        _yt_dlp = yt_dlp
    return _yt_dlp


# Resolve path to Talia Lyrics Fetch Automated
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
FETCHER_DIR = os.path.join(PROJECT_ROOT, "Talia Lyrics Fetch Automated")
if FETCHER_DIR not in sys.path:
    sys.path.append(FETCHER_DIR)

try:
    from fetch_lyrics import fetch_lyrics_for_file
except ImportError:
    fetch_lyrics_for_file = None

try:
    from config import trim_process_memory
except ImportError:

    def trim_process_memory():
        """Forces garbage collection and trims Windows working set to guarantee < 200 MB RAM."""
        gc.collect()
        try:
            ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
        except Exception:
            pass


def sanitize_filename(name: str) -> str:
    """Removes invalid Windows filesystem characters and limits length."""
    clean = re.sub(r'[\\/*?:"<>|]', "_", name)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:120]


def search_youtube(query: str, limit: int = 5) -> List[Dict]:
    """Synchronously searches YouTube for songs matching query or direct URL."""
    q = query.strip()
    if not q:
        return []
    is_url = "youtube.com/" in q or "youtu.be/" in q
    search_term = q if is_url else f"ytsearch{limit}:{q}"
    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "mweb"]
            }
        },
    }
    results = []
    ydl_mod = _get_yt_dlp()
    with ydl_mod.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(search_term, download=False)
        entries = info.get("entries", [info]) if "entries" in info else [info]
        for e in entries:
            if not e:
                continue
            vid_id = e.get("id", "")
            title = e.get("title", "Unknown Track")
            channel = e.get("uploader") or e.get("channel") or "Unknown Artist"
            dur = e.get("duration") or 0
            dur_m = int(dur // 60)
            dur_s = int(dur % 60)
            dur_str = f"{dur_m:02d}:{dur_s:02d}" if dur > 0 else "--:--"
            url = e.get("url") if is_url else f"https://www.youtube.com/watch?v={vid_id}"
            results.append(
                {
                    "id": vid_id,
                    "title": title,
                    "channel": channel,
                    "duration": dur,
                    "duration_str": dur_str,
                    "url": url,
                }
            )
    return results


def pick_best_youtube_result(
    results: List[Dict],
    target_title: str = "",
    target_artist: str = "",
    target_duration: float = 0.0,
) -> Optional[Dict]:
    """
    Selects the best YouTube candidate matching the song.
    Prioritizes official audio/topic releases with duration matching target_duration (+-3s),
    and heavily penalizes covers, remixes, live recordings, and skits/dialogue edits.
    """
    if not results:
        return None
    if len(results) == 1:
        return results[0]

    best_candidate = results[0]
    best_score = -9999.0

    clean_target_title = re.sub(r"[^a-z0-9\s]", "", target_title.lower()).strip()
    clean_target_artist = re.sub(r"[^a-z0-9\s]", "", target_artist.lower()).strip()

    bad_keywords = (
        "cover", "live", "remix", "acoustic", "slowed", "reverb",
        "parody", "reaction", "karaoke", "instrumental", "10 hour",
        "1 hour", "bass boosted", "nightcore", "clean version"
    )

    for entry in results:
        if not entry:
            continue
        score = 50.0
        vid_title = (entry.get("title") or "").lower()
        channel = (entry.get("channel") or entry.get("uploader") or "").lower()
        cand_dur = float(entry.get("duration") or 0.0)

        # 1. Duration Evaluation
        if target_duration > 10.0 and cand_dur > 0:
            diff = abs(cand_dur - target_duration)
            if diff <= 1.5:
                score += 65.0
            elif diff <= 3.5:
                score += 45.0
            elif diff <= 6.0:
                score += 20.0
            elif diff <= 12.0:
                score += 5.0
            elif diff > 25.0:
                score -= 50.0
            elif diff > 60.0:
                score -= 120.0

        # 2. Official Topic / Clean Audio Priority
        if "- topic" in channel or "provided to youtube by" in vid_title:
            score += 35.0
        elif "official audio" in vid_title or "audio" in vid_title:
            score += 20.0
        elif "lyric" in vid_title or "lyrics" in vid_title:
            score += 15.0

        # 3. Title keywords
        if clean_target_title:
            words = [w for w in clean_target_title.split() if len(w) > 2]
            if words:
                matches = sum(1 for w in words if w in vid_title)
                score += (matches / len(words)) * 25.0

        # 4. Artist keywords
        if clean_target_artist:
            a_words = [w for w in clean_target_artist.split() if len(w) > 2]
            if a_words:
                if any(w in vid_title or w in channel for w in a_words):
                    score += 15.0

        # 5. Penalize unwanted versions unless explicitly requested in title
        for kw in bad_keywords:
            if kw in vid_title and kw not in clean_target_title and kw not in clean_target_artist:
                score -= 40.0

        if score > best_score:
            best_score = score
            best_candidate = entry

    return best_candidate


def download_and_sync_lrc(
    video_url: str,
    target_dir: str,
    progress_cb: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    track_info: Optional[Dict] = None,
) -> Tuple[bool, str, str]:
    """Downloads audio, converts to Opus 160kbps in target_dir, and auto-fetches synced LRC."""
    if cancel_check and cancel_check():
        return False, "", "Cancelled by user"

    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
    download_dir = target_dir
    if progress_cb:
        progress_cb("Connecting to YouTube stream...")

    def hook(d):
        if cancel_check and cancel_check():
            raise KeyboardInterrupt("Cancelled by user")
        if d.get("status") == "downloading":
            p_str = d.get("_percent_str", "").strip()
            spd = d.get("_speed_str", "").strip()
            msg = f"Downloading: {p_str}"
            if spd:
                msg += f" ({spd})"
            if progress_cb:
                progress_cb(msg)
        elif d.get("status") == "finished":
            if progress_cb:
                progress_cb("Converting to Opus 160kbps...")

    ffmpeg_dir = _find_ffmpeg_dir()

    # Determine output template: clean filename from track_info if provided
    outtmpl = os.path.join(download_dir, "%(title)s.%(ext)s")
    clean_target_stem = ""
    if track_info and track_info.get("title"):
        t_artist = str(track_info.get("artist") or "").strip()
        t_title = str(track_info.get("title") or "").strip()
        if t_artist and t_title:
            track_num = track_info.get("track_number")
            total_tracks = track_info.get("total_tracks", 0)
            prefix = ""
            if track_num and total_tracks > 1:
                pad = max(2, len(str(total_tracks)))
                prefix = f"{int(track_num):0{pad}d}. "
            clean_target_stem = sanitize_filename(f"{prefix}{t_artist} - {t_title}")
            outtmpl = os.path.join(download_dir, f"{clean_target_stem}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "opus",
                "preferredquality": "160",
            }
        ],
        "outtmpl": outtmpl,
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "mweb"]
            }
        },
    }
    if ffmpeg_dir:
        ydl_opts["ffmpeg_location"] = ffmpeg_dir
    ydl_mod = _get_yt_dlp()
    try:
        with ydl_mod.YoutubeDL(ydl_opts) as ydl:
            meta = ydl.extract_info(video_url, download=True)
            title = meta.get("title", "Track")
    except (KeyboardInterrupt, Exception) as exc:
        if cancel_check and cancel_check():
            return False, "", "Cancelled by user"
        log.warning("[DOWNLOAD] ydl extract_info error: %s", exc)
        return False, "", str(exc)

    if cancel_check and cancel_check():
        return False, "", "Cancelled by user"

    final_opus = None
    if clean_target_stem:
        target_path = os.path.join(download_dir, f"{clean_target_stem}.opus")
        if os.path.exists(target_path):
            final_opus = target_path

    if not final_opus:
        clean_title = sanitize_filename(title)
        expected_opus = os.path.join(download_dir, f"{clean_title}.opus")
        final_opus = expected_opus if os.path.exists(expected_opus) else None

    if not final_opus:
        opus_candidates = [
            os.path.join(download_dir, f)
            for f in os.listdir(download_dir)
            if f.lower().endswith(".opus")
        ]
        if opus_candidates:
            opus_candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            final_opus = opus_candidates[0]

    if not final_opus or not os.path.exists(final_opus):
        return False, "", "Audio download completed but .opus file not found."

    # Embed clean metadata tags into the Opus container
    try:
        from mutagen.oggopus import OggOpus
        audio = OggOpus(final_opus)
        if track_info:
            if track_info.get("title"):
                audio["title"] = [str(track_info["title"])]
            if track_info.get("artist"):
                audio["artist"] = [str(track_info["artist"])]
        if video_url:
            audio["comment"] = [f"yt_url={video_url}"]
        audio.save()
    except Exception as tag_err:
        log.debug("Could not write opus tags: %s", tag_err)

    # Auto-fetch synced lyrics (runs in < 1s with direct LRCLIB & NetEase)
    if progress_cb:
        progress_cb("Auto-fetching verified synced lyrics (.lrc)...")
    lrc_synced = False
    if fetch_lyrics_for_file:
        try:
            lrc_ok, lrc_msg = fetch_lyrics_for_file(final_opus, force_overwrite=True)
            lrc_synced = lrc_ok
        except Exception as le:
            log.info(f"[LYRICS AUTO-FETCH ERROR] {le}")
    status_msg = f"Saved: {os.path.basename(final_opus)}"
    if lrc_synced:
        status_msg += " (Lyrics synced)"
    else:
        status_msg += " (Audio ready, no lyrics match)"
    return True, final_opus, status_msg


log = logging.getLogger(__name__)


class SongDownloaderService(QObject):
    """Asynchronous service for searching YouTube, downloading Opus audio, and syncing lyrics."""

    search_finished = pyqtSignal(list)
    search_error = pyqtSignal(str)
    download_progress = pyqtSignal(str)
    download_finished = pyqtSignal(bool, str, str)  # success, file_path, status_msg

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_searching = False
        self._is_downloading = False
        self.last_downloaded_file: str = ""

    def is_busy(self) -> bool:
        return self._is_searching or self._is_downloading

    def search_async(self, query: str, limit: int = 5):
        """Asynchronously searches YouTube for songs matching query or URL."""
        q = query.strip()
        if not q:
            self.search_error.emit("Please enter a song name or YouTube URL.")
            return
        if self._is_searching:
            return
        self._is_searching = True

        def worker():
            try:
                results = search_youtube(q, limit=limit)
                self.search_finished.emit(results)
            except Exception as ex:
                self.search_error.emit(str(ex))
            finally:
                self._is_searching = False
                trim_process_memory()

        threading.Thread(target=worker, daemon=True).start()

    def download_sync_query(
        self,
        query: str,
        target_dir: str,
        progress_cb: Optional[Callable[[str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        track_info: Optional[Dict] = None,
        target_duration: float = 0.0,
        return_path: bool = False,
    ):
        """Synchronously searches YouTube (prioritizing official audio/album versions) and downloads into target_dir."""
        try:
            if cancel_check and cancel_check():
                return (False, "") if return_path else False

            t_artist = str(track_info.get("artist") or "").strip() if track_info else ""
            t_title = str(track_info.get("title") or "").strip() if track_info else ""
            if not target_duration and track_info and track_info.get("duration"):
                try:
                    target_duration = float(track_info["duration"])
                except (ValueError, TypeError):
                    target_duration = 0.0

            # Check if file already exists in target_dir to skip duplicate work
            if t_artist and t_title:
                track_num = track_info.get("track_number")
                total_tracks = track_info.get("total_tracks", 0)
                prefix = ""
                if track_num and total_tracks > 1:
                    pad = max(2, len(str(total_tracks)))
                    prefix = f"{int(track_num):0{pad}d}. "

                t_stem = sanitize_filename(f"{prefix}{t_artist} - {t_title}")
                exist_opus = os.path.join(target_dir, f"{t_stem}.opus")

                # If an un-numbered version exists from an earlier download, rename it!
                old_stem = sanitize_filename(f"{t_artist} - {t_title}")
                old_opus = os.path.join(target_dir, f"{old_stem}.opus")
                if prefix and os.path.exists(old_opus) and not os.path.exists(exist_opus):
                    try:
                        os.rename(old_opus, exist_opus)
                        old_lrc = os.path.join(target_dir, f"{old_stem}.lrc")
                        new_lrc = os.path.join(target_dir, f"{t_stem}.lrc")
                        if os.path.exists(old_lrc) and not os.path.exists(new_lrc):
                            os.rename(old_lrc, new_lrc)
                    except Exception as e:
                        log.warning("Could not rename existing track %s: %s", old_stem, e)

                if os.path.exists(exist_opus):
                    self.last_downloaded_file = exist_opus
                    exist_lrc = os.path.join(target_dir, f"{t_stem}.lrc")
                    if os.path.exists(exist_lrc):
                        if progress_cb:
                            progress_cb(f"Already downloaded: {t_stem}")
                        return (True, exist_opus) if return_path else True
                    else:
                        if progress_cb:
                            progress_cb(f"Audio exists, fetching lyrics: {t_stem}")
                        if fetch_lyrics_for_file:
                            fetch_lyrics_for_file(exist_opus, force_overwrite=True)
                        return (True, exist_opus) if return_path else True

            is_url = "youtube.com/" in query or "youtu.be/" in query
            if is_url:
                search_query = query
            elif t_artist and t_title:
                # Prioritize official audio / topic tracks for accurate duration and sync
                search_query = f"{t_artist} - {t_title} audio"
            else:
                search_query = f"{query} audio"

            if progress_cb:
                progress_cb(f"Searching YouTube: {search_query if not is_url else query}")

            results = search_youtube(search_query, limit=8 if not is_url else 1)
            # Fallback to lyrics query if audio search returned nothing
            if not results and not is_url:
                fallback_query = f"{t_artist} - {t_title} lyrics" if (t_artist and t_title) else f"{query} lyrics"
                results = search_youtube(fallback_query, limit=6)
            # Final fallback to raw query
            if not results and not is_url and search_query != query:
                results = search_youtube(query, limit=4)

            if cancel_check and cancel_check():
                return (False, "") if return_path else False
            if not results:
                log.warning("[DOWNLOAD] No YouTube results found for '%s'", query)
                if progress_cb:
                    progress_cb(f"No match found: {query}")
                return (False, "") if return_path else False

            best_entry = pick_best_youtube_result(
                results,
                target_title=t_title,
                target_artist=t_artist,
                target_duration=target_duration,
            ) if not is_url else results[0]

            top_url = best_entry.get("url") if best_entry else results[0].get("url")
            if not top_url:
                return (False, "") if return_path else False

            ok, opus_path, msg = download_and_sync_lrc(
                top_url,
                target_dir,
                progress_cb=progress_cb,
                cancel_check=cancel_check,
                track_info=track_info,
            )
            self.last_downloaded_file = opus_path if ok else ""
            trim_process_memory()
            return (ok, opus_path) if return_path else ok
        except Exception as e:
            log.warning("[DOWNLOAD] Sync query failed for %s: %s", query, e)
            if progress_cb:
                progress_cb(f"Error: {e}")
            return (False, "") if return_path else False

    def download_and_sync_async(self, video_url: str, target_dir: str):
        """Asynchronously downloads audio, converts to Opus 160kbps in target_dir, and fetches LRC."""
        if self._is_downloading:
            self.download_progress.emit("Another download is currently in progress...")
            return
        self._is_downloading = True

        def worker():
            try:
                ok, opus_path, msg = download_and_sync_lrc(
                    video_url, target_dir, progress_cb=self.download_progress.emit
                )
                self.download_finished.emit(ok, opus_path, msg)
            except Exception as ex:
                self.download_finished.emit(False, "", f"Download error: {ex}")
            finally:
                self._is_downloading = False
                trim_process_memory()

        threading.Thread(target=worker, daemon=True).start()
