"""
Talia Lyrics Fetch Automated - Core Engine
Recursively scans music folders, extracts embedded audio metadata,
and automatically fetches synchronized lyrics (.lrc) from Spotify/Musixmatch/LRCLIB databases.
"""

import os
import re
import sys
import time
import json
import urllib.request
import urllib.parse
from typing import Optional, Tuple, Dict, List

try:
    import mutagen
    from mutagen.easyid3 import EasyID3
except ImportError:
    mutagen = None

try:
    import syncedlyrics
except ImportError:
    syncedlyrics = None

SUPPORTED_AUDIO_EXTS = (
    ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wav", ".wma", ".aac", ".aiff"
)

SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json"
)


def get_default_music_dir() -> str:
    """Retrieves the active music directory configured in Talia's settings.json."""
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                folder = cfg.get("music_folder", "")
                if folder and os.path.exists(folder):
                    return os.path.normpath(folder)
        except Exception:
            pass

    # Fallback to local 'music' directory inside Talia project
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_music = os.path.join(parent_dir, "music")
    if os.path.exists(local_music):
        return os.path.normpath(local_music)

    return os.path.normpath(os.path.expanduser("~/Music"))


def clean_title_heuristics(filename: str) -> Tuple[str, str]:
    """
    Cleans messy filenames (YouTube packaging, release tags, bitrates)
    and extracts candidate (artist, title).
    """
    stem = os.path.splitext(os.path.basename(filename))[0]

    # Remove common video / audio release noise tags
    stem = re.sub(
        r'[-_]?(CPE|Compressed|1080p|720p|4k|Official Video|Official Audio|Lyric Video|Remastered|HD|HQ)[-_0-9]*',
        '', stem, flags=re.I
    )
    # Remove bracketed and parenthesized garbage like [Official Music Video], (Audio), etc.
    stem = re.sub(r'\[.*?\]', '', stem)
    stem = re.sub(r'\((Official|Music Video|Audio|Lyric|HD|4K|Remastered|Explicit).*?\)', '', stem, flags=re.I)

    # Normalize dashes and underscores
    stem = stem.replace('_', ' ').strip()
    stem = re.sub(r'\s+', ' ', stem)

    # Check for "Artist - Title" pattern
    if ' - ' in stem:
        parts = stem.split(' - ', 1)
        artist = parts[0].strip()
        title = parts[1].strip()
        return artist, title

    return "", stem


def extract_metadata(audio_path: str) -> Dict[str, str]:
    """
    Extracts embedded audio metadata (title, artist, album, duration) using Mutagen.
    Falls back to intelligent filename parsing if tags are missing.
    """
    title = ""
    artist = ""
    album = ""
    duration = 0.0

    if mutagen is not None:
        try:
            audio = mutagen.File(audio_path)
            if audio is not None:
                if hasattr(audio, "info") and hasattr(audio.info, "length"):
                    duration = float(audio.info.length)

                tags = getattr(audio, "tags", None)
                if tags:
                    # Generic / Vorbis / FLAC tag mapping
                    for key in ["title", "TITLE", "tit2", "TIT2"]:
                        if key in tags:
                            val = tags[key]
                            title = str(val[0] if isinstance(val, (list, tuple)) else val).strip()
                            break

                    for key in ["artist", "ARTIST", "tpe1", "TPE1"]:
                        if key in tags:
                            val = tags[key]
                            artist = str(val[0] if isinstance(val, (list, tuple)) else val).strip()
                            break

                    for key in ["album", "ALBUM", "talb", "TALB"]:
                        if key in tags:
                            val = tags[key]
                            album = str(val[0] if isinstance(val, (list, tuple)) else val).strip()
                            break
        except Exception:
            pass

    # Fallback to filename heuristics if tags were missing
    if not title:
        guess_artist, guess_title = clean_title_heuristics(audio_path)
        title = guess_title
        if not artist and guess_artist:
            artist = guess_artist

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "duration": duration
    }


def fetch_from_lrclib_direct(title: str, artist: str = "", duration: float = 0.0) -> Optional[str]:
    """Queries LRCLIB directly for synchronized lyrics."""
    try:
        # Method A: exact match if duration and artist are known
        if artist and title and duration > 10.0:
            params = {
                "track_name": title,
                "artist_name": artist,
                "duration": int(round(duration))
            }
            url = f"https://lrclib.net/api/get?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url, headers={"User-Agent": "TaliaLyricsFetcher/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("syncedLyrics"):
                    return data["syncedLyrics"]
    except Exception:
        pass

    try:
        # Method B: Search endpoint
        query = f"{title} {artist}".strip()
        url = f"https://lrclib.net/api/search?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "TaliaLyricsFetcher/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list):
                for item in data:
                    if item.get("syncedLyrics"):
                        return item["syncedLyrics"]
    except Exception:
        pass

    return None


def fetch_synced_lyrics(title: str, artist: str = "", duration: float = 0.0) -> Optional[str]:
    """
    Multi-provider synchronized lyrics retrieval:
    1. syncedlyrics library (LRCLIB, Musixmatch, Deezer, NetEase)
    2. Direct LRCLIB API fallback
    """
    search_term = f"{title} {artist}".strip() if artist else title
    if not search_term:
        return None

    # Provider 1: syncedlyrics
    if syncedlyrics is not None:
        try:
            lrc_content = syncedlyrics.search(search_term, synced_only=True)
            if lrc_content and "[" in lrc_content:
                return lrc_content
        except Exception:
            pass

    # Provider 2: Direct LRCLIB API
    direct_lrc = fetch_from_lrclib_direct(title, artist, duration)
    if direct_lrc and "[" in direct_lrc:
        return direct_lrc

    return None


def fetch_lyrics_for_file(audio_path: str, force_overwrite: bool = False) -> Tuple[bool, str]:
    """
    Fetches synchronized lyrics for a single audio file and saves the .lrc file next to it.
    Returns (success: bool, status_message: str).
    """
    audio_path = os.path.normpath(audio_path)
    if not os.path.exists(audio_path):
        return False, f"File not found: {audio_path}"

    base, _ = os.path.splitext(audio_path)
    lrc_path = base + ".lrc"

    if os.path.exists(lrc_path) and not force_overwrite:
        return True, f"Skipped (LRC already exists): {os.path.basename(lrc_path)}"

    meta = extract_metadata(audio_path)
    title = meta["title"]
    artist = meta["artist"]
    dur = meta["duration"]

    if not title:
        return False, f"Could not determine track title for {os.path.basename(audio_path)}"

    display_name = f"{artist} - {title}" if artist else title
    lrc_text = fetch_synced_lyrics(title, artist, dur)

    if not lrc_text:
        return False, f"No synchronized lyrics found for: {display_name}"

    try:
        with open(lrc_path, "w", encoding="utf-8") as f:
            f.write(lrc_text)
        return True, f"Saved lyrics: {os.path.basename(lrc_path)}"
    except Exception as e:
        return False, f"Failed to save {lrc_path}: {e}"


def scan_and_fetch_folder(
    folder_path: str,
    force_overwrite: bool = False,
    progress_callback=None
) -> Dict[str, int]:
    """
    Recursively scans the folder for all supported audio files and downloads missing .lrc files.
    """
    stats = {"total": 0, "fetched": 0, "skipped": 0, "failed": 0}
    if not os.path.exists(folder_path):
        return stats

    audio_files: List[str] = []
    for root, _, filenames in os.walk(folder_path):
        for f in filenames:
            if f.lower().endswith(SUPPORTED_AUDIO_EXTS):
                audio_files.append(os.path.normpath(os.path.join(root, f)))

    stats["total"] = len(audio_files)

    for idx, audio_path in enumerate(audio_files):
        success, msg = fetch_lyrics_for_file(audio_path, force_overwrite)
        if "Skipped" in msg:
            stats["skipped"] += 1
        elif success:
            stats["fetched"] += 1
        else:
            stats["failed"] += 1

        if progress_callback:
            progress_callback(idx + 1, stats["total"], audio_path, success, msg)

    return stats


def watch_folder_continuous(folder_path: str, poll_interval: float = 4.0):
    """
    Live folder watcher: continuously polls folder for new songs without .lrc files
    and automatically downloads lyrics as soon as you drop music into the folder.
    """
    print(f"[*] Starting live folder watcher on: {folder_path}")
    print(f"[*] Drop any audio file into this folder to auto-fetch its synced lyrics.")
    print(f"[*] Press Ctrl+C to stop.")

    known_processed = set()

    try:
        while True:
            for root, _, filenames in os.walk(folder_path):
                for f in filenames:
                    if f.lower().endswith(SUPPORTED_AUDIO_EXTS):
                        full_audio = os.path.normpath(os.path.join(root, f))
                        lrc_path = os.path.splitext(full_audio)[0] + ".lrc"

                        if not os.path.exists(lrc_path) and full_audio not in known_processed:
                            print(f"\n[+] New song detected: {f}")
                            success, msg = fetch_lyrics_for_file(full_audio, force_overwrite=False)
                            print(f"    -> {msg}")
                            known_processed.add(full_audio)

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("\n[*] Live folder watcher stopped.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Talia Automated Synchronized Lyrics Fetcher")
    parser.add_argument("--folder", type=str, default="", help="Music folder path to scan")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing .lrc files")
    parser.add_argument("--watch", action="store_true", help="Run in continuous live folder watcher mode")
    args = parser.parse_args()

    target_dir = args.folder or get_default_music_dir()
    print("=" * 60)
    print("  TALIA AUTOMATED SYNCHRONIZED LYRICS FETCHER")
    print(f"  Target Folder: {target_dir}")
    print("=" * 60)

    if not os.path.exists(target_dir):
        print(f"[ERROR] Music folder does not exist: {target_dir}")
        sys.exit(1)

    if args.watch:
        watch_folder_continuous(target_dir)
    else:
        def on_prog(cur, total, path, success, msg):
            status = "[OK]" if success else "[--]"
            print(f"[{cur}/{total}] {status} {os.path.basename(path)} -> {msg}")

        results = scan_and_fetch_folder(target_dir, args.force, on_prog)
        print("\n" + "=" * 60)
        print(f"  SUMMARY:")
        print(f"  - Total Audio Files Scanned: {results['total']}")
        print(f"  - Successfully Fetched     : {results['fetched']}")
        print(f"  - Already Had Lyrics       : {results['skipped']}")
        print(f"  - Not Found / Failed       : {results['failed']}")
        print("=" * 60)
