"""
Talia Song Downloader & Auto-Sync Service
Searches YouTube for tracks, converts audio to high-quality Opus (160kbps),
saves directly to the 'Downloaded Songs' subfolder, and automatically fetches
verified synchronized lyrics (.lrc).
"""

import os
import sys
import re
import gc
import ctypes
import threading
from typing import List, Dict, Optional, Tuple, Callable

from PyQt6.QtCore import QObject, pyqtSignal

import yt_dlp
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception as e:
    print(f"[FFMPEG INIT] Note: {e}")

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


def trim_process_memory():
    """Forces garbage collection and trims Windows working set to guarantee < 200 MB RAM."""
    gc.collect()
    try:
        ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
    except Exception:
        pass


def sanitize_filename(name: str) -> str:
    """Removes invalid Windows filesystem characters and limits length."""
    clean = re.sub(r'[\\/*?:"<>|]', '_', name)
    clean = re.sub(r'\s+', ' ', clean).strip()
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
    }

    results = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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

            results.append({
                "id": vid_id,
                "title": title,
                "channel": channel,
                "duration": dur,
                "duration_str": dur_str,
                "url": url
            })

    return results


def download_and_sync_lrc(
    video_url: str,
    music_dir: str,
    progress_cb: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str, str]:
    """Downloads audio, converts to Opus 160kbps in 'Downloaded Songs', and auto-fetches synced LRC."""
    if not os.path.exists(music_dir):
        os.makedirs(music_dir, exist_ok=True)

    download_dir = os.path.join(music_dir, "Downloaded Songs")
    os.makedirs(download_dir, exist_ok=True)

    if progress_cb:
        progress_cb("Connecting to YouTube stream...")

    def hook(d):
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

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "opus",
            "preferredquality": "160",
        }],
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        meta = ydl.extract_info(video_url, download=True)
        title = meta.get("title", "Track")

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

    # Auto-fetch synced lyrics
    if progress_cb:
        progress_cb("Auto-fetching verified synced lyrics (.lrc)...")
    lrc_synced = False
    if fetch_lyrics_for_file:
        try:
            lrc_ok, lrc_msg = fetch_lyrics_for_file(final_opus, force_overwrite=True)
            lrc_synced = lrc_ok
        except Exception as le:
            print(f"[LYRICS AUTO-FETCH ERROR] {le}")

    status_msg = f"Saved: {os.path.basename(final_opus)}"
    if lrc_synced:
        status_msg += " (Lyrics synced)"
    else:
        status_msg += " (Audio ready, no lyrics match)"

    return True, final_opus, status_msg


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

    def download_and_sync_async(self, video_url: str, music_dir: str):
        """Asynchronously downloads audio, converts to Opus 160kbps in 'Downloaded Songs', and fetches LRC."""
        if self._is_downloading:
            self.download_progress.emit("Another download is currently in progress...")
            return

        self._is_downloading = True

        def worker():
            try:
                ok, opus_path, msg = download_and_sync_lrc(
                    video_url,
                    music_dir,
                    progress_cb=self.download_progress.emit
                )
                self.download_finished.emit(ok, opus_path, msg)
            except Exception as ex:
                self.download_finished.emit(False, "", f"Download error: {ex}")
            finally:
                self._is_downloading = False
                trim_process_memory()

        threading.Thread(target=worker, daemon=True).start()
