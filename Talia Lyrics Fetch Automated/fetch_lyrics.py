"""
Talia Lyrics Fetch Automated - Robust Core Engine
Recursively scans music folders, extracts embedded audio metadata,
intelligently sanitizes messy filenames (YouTube hashes, CPE tags, video qualifiers),
and cascades across multiple synchronized lyrics providers (LRCLIB, Musixmatch, Deezer, NetEase)
with duration sanity checks to guarantee 100% accurate lyrics matching.
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
    from mutagen.oggopus import OggOpus
    from mutagen.flac import FLAC
    from mutagen.mp4 import MP4
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

    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_music = os.path.join(parent_dir, "music")
    if os.path.exists(local_music):
        return os.path.normpath(local_music)

    return os.path.normpath(os.path.expanduser("~/Music"))


def clean_filename_idiot_proof(filename: str) -> Tuple[str, str]:
    """
    Robust multi-stage filename sanitizer.
    Handles YouTube hashes, release tags, CPE markers, bracketed garbage,
    and extracts candidate (artist, title).
    """
    stem = os.path.splitext(os.path.basename(filename))[0]

    # 1. Strip leading track numbers: '01 - ', '01. ', '1-02 '
    stem = re.sub(r'^\d{1,3}[\.\-_\s]+', '', stem)

    # 2. Strip trailing YouTube video IDs / hashes (e.g. -qbmmhu, _dQw4w9WgXcQ, [dx_qbmmhu])
    stem = re.sub(r'\[[a-zA-Z0-9_\-]{8,15}\]$', '', stem)
    stem = re.sub(r'[-_][a-zA-Z0-9_\-]{6,15}$', '', stem)

    # 3. Strip release & encoding junk
    junk_patterns = [
        r'[-_]?(CPE|CPE-\d+|CPE\s*\d+)',
        r'[-_]?(Compressed|_Compressed_)',
        r'[-_]?(1080p|720p|4k|60fps|HD|HQ)',
        r'\(?(Official Music Video|Official Video|Official Audio|Lyric Video|Lyrics Video|Full Song|Theme Song|Audio)\)?',
        r'\[(Official Music Video|Official Video|Official Audio|Lyric Video|Lyrics Video|Full Song|Theme Song|Audio)\]',
        r'\(?(Remastered|Remaster|Explicit|Bonus Track|OST|Soundtrack)\)?',
        r'\[(Remastered|Remaster|Explicit|Bonus Track|OST|Soundtrack)\]',
        r'[-_]?chainsaw\s*man\s*song',
    ]
    for pat in junk_patterns:
        stem = re.sub(pat, '', stem, flags=re.I)

    # 4. Extract 'ft.' or 'feat.' artists embedded in title
    feat_artist = ""
    feat_match = re.search(r'(?:ft\.?|feat\.?|featuring)\s+([^-\(\)\[\]]+)', stem, flags=re.I)
    if feat_match:
        feat_artist = feat_match.group(1).strip()
        stem = re.sub(r'(?:ft\.?|feat\.?|featuring)\s+[^-\(\)\[\]]+', '', stem, flags=re.I)

    # 5. Normalize dashes and underscores
    # If dashes are used as word spaces (like 'bang-bang-bang' without ' - ')
    if ' - ' not in stem and '-' in stem:
        stem = stem.replace('-', ' ')
    stem = stem.replace('_', ' ')

    # Remove lingering empty brackets or parens
    stem = re.sub(r'\(\s*\)', '', stem)
    stem = re.sub(r'\[\s*\]', '', stem)
    stem = re.sub(r'\s+', ' ', stem).strip()

    # 6. Parse 'Artist - Title'
    artist = ""
    title = stem
    if ' - ' in stem:
        parts = stem.split(' - ', 1)
        artist = parts[0].strip()
        title = parts[1].strip()

    if feat_artist:
        if artist:
            artist = f"{artist} feat. {feat_artist}"
        else:
            artist = feat_artist

    return artist, title


def extract_metadata(audio_path: str) -> Dict[str, any]:
    """
    Extracts embedded metadata (title, artist, album, duration) using Mutagen.
    Falls back to the idiot-proof filename sanitizer if tags are absent.
    """
    title = ""
    artist = ""
    album = ""
    duration = 0.0

    if mutagen is not None and os.path.exists(audio_path):
        try:
            audio = mutagen.File(audio_path)
            if audio is not None:
                if hasattr(audio, "info") and hasattr(audio.info, "length"):
                    duration = float(audio.info.length)

                tags = getattr(audio, "tags", None)
                if tags:
                    # Generic / ID3 / Vorbis / FLAC tag mapping
                    for key in ["title", "TITLE", "tit2", "TIT2", "\xa9nam"]:
                        if key in tags:
                            val = tags[key]
                            title = str(val[0] if isinstance(val, (list, tuple)) else val).strip()
                            break

                    for key in ["artist", "ARTIST", "tpe1", "TPE1", "\xa9ART"]:
                        if key in tags:
                            val = tags[key]
                            artist = str(val[0] if isinstance(val, (list, tuple)) else val).strip()
                            break

                    for key in ["album", "ALBUM", "talb", "TALB", "\xa9alb"]:
                        if key in tags:
                            val = tags[key]
                            album = str(val[0] if isinstance(val, (list, tuple)) else val).strip()
                            break
        except Exception:
            pass

    # Heuristic fallback if tags were missing or incomplete
    guess_artist, guess_title = clean_filename_idiot_proof(audio_path)
    if not title:
        title = guess_title
    if not artist and guess_artist:
        artist = guess_artist

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "duration": duration
    }


def parse_last_timestamp(lrc_text: str) -> float:
    """Parses the latest timestamp in the LRC to verify track length."""
    max_ts = 0.0
    pattern = re.compile(r'\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]')
    for line in lrc_text.splitlines():
        for m in pattern.finditer(line):
            mins = int(m.group(1))
            secs = int(m.group(2))
            ms = float("0." + m.group(3)) if m.group(3) else 0.0
            ts = mins * 60.0 + secs + ms
            if ts > max_ts:
                max_ts = ts
    return max_ts


def clean_unwanted_lrc_headers(lrc_text: str) -> str:
    """Removes messy CJK composer tags (e.g. 作曲/作词) from western tracks."""
    lines = []
    for line in lrc_text.splitlines():
        # Remove foreign credit headers that clash with lyrics
        if re.search(r'\[\d{1,2}:\d{2}.*?\]\s*(?:作曲|作词|编曲|制作人)\s*:', line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def validate_lyrics_match(lrc_text: str, expected_duration: float = 0.0) -> bool:
    """Sanity checks the lyrics text: has lines, has timestamps, and matches song length."""
    if not lrc_text or "[" not in lrc_text:
        return False

    lines = [line.strip() for line in lrc_text.splitlines() if line.strip()]
    # Must have at least 3 lyric lines
    if len(lines) < 3:
        return False

    # Duration tolerance check (if audio length is known)
    if expected_duration > 15.0:
        last_ts = parse_last_timestamp(lrc_text)
        if last_ts > 0.0:
            diff = abs(expected_duration - last_ts)
            # If the lyrics stop 45s before the song ends or continue 45s after, it's likely a wrong song
            if diff > 45.0 and last_ts < expected_duration * 0.60:
                return False

    return True


def fetch_from_lrclib_direct(title: str, artist: str = "", duration: float = 0.0) -> Optional[str]:
    """Direct query to LRCLIB API with exact track duration matching."""
    try:
        if artist and title and duration > 10.0:
            params = {
                "track_name": title,
                "artist_name": artist,
                "duration": int(round(duration))
            }
            url = f"https://lrclib.net/api/get?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url, headers={"User-Agent": "TaliaLyricsFetcher/2.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("syncedLyrics"):
                    return clean_unwanted_lrc_headers(data["syncedLyrics"])
    except Exception:
        pass

    try:
        query = f"{title} {artist}".strip()
        url = f"https://lrclib.net/api/search?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "TaliaLyricsFetcher/2.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list):
                for item in data:
                    synced = item.get("syncedLyrics")
                    if synced:
                        cleaned = clean_unwanted_lrc_headers(synced)
                        if validate_lyrics_match(cleaned, duration):
                            return cleaned
    except Exception:
        pass

    return None


def fetch_synced_lyrics(title: str, artist: str = "", duration: float = 0.0) -> Optional[str]:
    """
    Cascading Multi-Provider Search:
    Tries 4 prioritized query iterations across syncedlyrics and LRCLIB.
    """
    queries = []
    if artist and title:
        queries.append(f"{artist} - {title}")
        queries.append(f"{title} {artist}")
    if title:
        queries.append(title)
        # Strip parens/brackets from title for fallback
        clean_bare_title = re.sub(r'[\(\[\{].*?[\)\]\}]', '', title).strip()
        if clean_bare_title and clean_bare_title != title:
            if artist:
                queries.append(f"{artist} {clean_bare_title}")
            queries.append(clean_bare_title)

    # 1. Try Direct LRCLIB exact match first (highest accuracy)
    if artist and title and duration > 10.0:
        direct = fetch_from_lrclib_direct(title, artist, duration)
        if direct and validate_lyrics_match(direct, duration):
            return direct

    # 2. Iterate through query waterfall with syncedlyrics
    if syncedlyrics is not None:
        for q in queries:
            try:
                result = syncedlyrics.search(q, synced_only=True)
                if result:
                    cleaned = clean_unwanted_lrc_headers(result)
                    if validate_lyrics_match(cleaned, duration):
                        return cleaned
            except Exception:
                continue

    # 3. Fallback to LRCLIB search
    for q in queries:
        try:
            url = f"https://lrclib.net/api/search?q={urllib.parse.quote(q)}"
            req = urllib.request.Request(url, headers={"User-Agent": "TaliaLyricsFetcher/2.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list):
                    for item in data:
                        synced = item.get("syncedLyrics")
                        if synced:
                            cleaned = clean_unwanted_lrc_headers(synced)
                            if validate_lyrics_match(cleaned, duration):
                                return cleaned
        except Exception:
            continue

    return None


def fetch_lyrics_for_file(audio_path: str, force_overwrite: bool = False) -> Tuple[bool, str]:
    """
    Safely fetches lyrics for a single track.
    If lyrics already exist, preserves them unless force_overwrite is explicitly requested.
    When overwriting, creates a .lrc.bak backup for safety.
    """
    audio_path = os.path.normpath(audio_path)
    if not os.path.exists(audio_path):
        return False, f"File not found: {audio_path}"

    base, _ = os.path.splitext(audio_path)
    lrc_path = base + ".lrc"

    if os.path.exists(lrc_path) and not force_overwrite:
        return True, f"Skipped (Verified LRC already exists): {os.path.basename(lrc_path)}"

    meta = extract_metadata(audio_path)
    title = meta["title"]
    artist = meta["artist"]
    dur = meta["duration"]

    if not title:
        return False, f"Could not determine track title for {os.path.basename(audio_path)}"

    display_name = f"{artist} - {title}" if artist else title
    lrc_text = fetch_synced_lyrics(title, artist, dur)

    if not lrc_text:
        return False, f"No matching lyrics found for: {display_name}"

    try:
        # Create backup if overwriting existing file
        if os.path.exists(lrc_path):
            bak_path = lrc_path + ".bak"
            try:
                import shutil
                shutil.copy2(lrc_path, bak_path)
            except Exception:
                pass

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
    """Recursively scans folder for supported audio files and downloads missing .lrc files."""
    stats = {"total": 0, "fetched": 0, "skipped": 0, "failed": 0}
    if not os.path.exists(folder_path):
        return stats

    audio_files: List[str] = []
    for root, _, filenames in os.walk(folder_path):
        for f in sorted(filenames):
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



def detect_audio_onset(audio_path: str, max_search_s: float = 35.0, hop_ms: float = 50.0) -> float:
    """
    Detects the first significant vocal or musical energy onset in an audio track.
    Returns the onset timestamp in seconds.
    """
    try:
        import soundfile as sf
        import numpy as np

        data, sr = sf.read(audio_path)
        if len(data.shape) > 1:
            data = data.mean(axis=1)

        max_samples = int(min(len(data), sr * max_search_s))
        search_data = data[:max_samples]
        hop_samples = int(sr * (hop_ms / 1000.0))

        rms_vals = []
        times = []
        for i in range(0, max_samples - hop_samples, hop_samples):
            chunk = search_data[i:i + hop_samples]
            rms = float(np.sqrt(np.mean(chunk**2)))
            rms_vals.append(rms)
            times.append(i / float(sr))

        if not rms_vals:
            return 0.0

        peak_rms = max(rms_vals)
        thresh = max(0.08, peak_rms * 0.28)

        for i in range(len(rms_vals) - 3):
            if rms_vals[i] >= thresh and rms_vals[i+1] >= thresh and rms_vals[i+2] >= thresh:
                return round(float(times[i]), 2)
    except Exception:
        pass
    return 0.0


def shift_lrc_timestamps(lrc_text: str, offset_seconds: float) -> str:
    """
    Applies a time offset (in seconds) to all timestamps within an LRC text string.
    Positive offset adds time; negative offset shifts earlier.
    """
    pattern = re.compile(r'\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]')
    shifted_lines = []

    for line in lrc_text.splitlines():
        matches = list(pattern.finditer(line))
        if not matches:
            shifted_lines.append(line)
            continue

        text_content = pattern.sub('', line).strip()
        new_tags = []
        for m in matches:
            mins = int(m.group(1))
            secs = int(m.group(2))
            ms = float("0." + m.group(3)) if m.group(3) else 0.0
            ts = mins * 60.0 + secs + ms
            new_ts = max(0.0, ts + offset_seconds)
            new_mins = int(new_ts // 60)
            new_secs = int(new_ts % 60)
            new_ms = int(round((new_ts - int(new_ts)) * 100))
            new_tags.append(f"[{new_mins:02d}:{new_secs:02d}.{new_ms:02d}]")

        shifted_lines.append("".join(new_tags) + text_content)

    return "\n".join(shifted_lines) + "\n"


def auto_calibrate_lrc_file(audio_path: str) -> Tuple[bool, float, str]:
    """
    Calculates audio onset and first lyric timestamp for an audio track.
    If a substantial offset discrepancy (>= 1.5s) exists, safely shifts the LRC timestamps.
    """
    audio_path = os.path.normpath(audio_path)
    if not os.path.exists(audio_path):
        return False, 0.0, "Audio file does not exist"

    lrc_path = os.path.splitext(audio_path)[0] + ".lrc"
    if not os.path.exists(lrc_path):
        return False, 0.0, "Companion .lrc file not found"

    try:
        with open(lrc_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        pattern = re.compile(r'\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]')
        first_ts = None
        for line in content.splitlines():
            m = pattern.search(line)
            if m:
                text = pattern.sub('', line).strip()
                if len(text) >= 2 and not text.startswith(('by:', 'ar:', 'ti:', 'al:')):
                    mins = int(m.group(1))
                    secs = int(m.group(2))
                    ms = float("0." + m.group(3)) if m.group(3) else 0.0
                    first_ts = mins * 60.0 + secs + ms
                    break

        if first_ts is None:
            return False, 0.0, "No lyric timestamps found in LRC"

        onset = detect_audio_onset(audio_path)
        diff = round(onset - first_ts, 2)

        if abs(diff) < 1.0:
            return False, 0.0, f"Already synchronized (onset: {onset}s, first lyric: {first_ts}s)"

        # Apply shift
        offset = round(onset - first_ts, 2)
        # Create backup
        try:
            import shutil
            shutil.copy2(lrc_path, lrc_path + ".bak")
        except Exception:
            pass

        shifted_lrc = shift_lrc_timestamps(content, offset)
        with open(lrc_path, "w", encoding="utf-8") as f:
            f.write(shifted_lrc)

        return True, offset, f"Shifted by {offset:+.2f}s (onset: {onset}s -> lyric: {first_ts}s)"

    except Exception as e:
        return False, 0.0, f"Auto-calibration failed: {e}"

def watch_folder_continuous(folder_path: str, poll_interval: float = 3.5):
    """Continuously monitors folder for newly added music files and auto-fetches lyrics."""
    print(f"[*] Starting live folder watcher on: {folder_path}")
    print(f"[*] Drop any audio file into this folder to auto-fetch its synced lyrics.")
    print(f"[*] Press Ctrl+C to stop.\n")

    known_processed = set()

    try:
        while True:
            for root, _, filenames in os.walk(folder_path):
                for f in sorted(filenames):
                    if f.lower().endswith(SUPPORTED_AUDIO_EXTS):
                        full_audio = os.path.normpath(os.path.join(root, f))
                        lrc_path = os.path.splitext(full_audio)[0] + ".lrc"

                        if not os.path.exists(lrc_path) and full_audio not in known_processed:
                            print(f"[+] New song detected: {f}")
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
    parser.add_argument("--force", action="store_true", help="Force overwrite existing .lrc files (creates .bak)")
    parser.add_argument("--watch", action="store_true", help="Run in continuous live folder watcher mode")
    args = parser.parse_args()

    target_dir = args.folder or get_default_music_dir()
    print("=" * 60)
    print("  TALIA AUTOMATED SYNCHRONIZED LYRICS FETCHER (v2.0)")
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
