"""
Configuration, Constants, Settings Storage, and Win32 Bindings for Talia Cyberpunk Visualizer.
"""

import ctypes
import json
import logging
import os
import sys
import tempfile
from ctypes import wintypes

from PyQt6.QtGui import QColor

log = logging.getLogger(__name__)


# ==========================================================
# Paths & Directories (Resolves project root dynamically)
# ==========================================================
if getattr(sys, "frozen", False):
    PROJECT_ROOT = os.path.dirname(os.path.abspath(sys.executable))
    CURRENT_DIR = PROJECT_ROOT
else:
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(CURRENT_DIR).lower() in ("python code", "code", "src"):
        PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
    else:
        PROJECT_ROOT = CURRENT_DIR

BASE_DIR = PROJECT_ROOT
EYE_PARTS_DIR = (
    os.path.join(PROJECT_ROOT, "assets", "eye_parts")
    if os.path.exists(os.path.join(PROJECT_ROOT, "assets", "eye_parts"))
    else os.path.join(PROJECT_ROOT, "eye_parts")
)
DEFAULT_MUSIC_DIR = os.path.join(PROJECT_ROOT, "music")
SETTINGS_FILE = os.path.join(PROJECT_ROOT, "settings.json")
PNGS_DIR = (
    os.path.join(PROJECT_ROOT, "assets", "icons")
    if os.path.exists(os.path.join(PROJECT_ROOT, "assets", "icons"))
    else os.path.join(PROJECT_ROOT, "PNGs")
)
SOUNDS_DIR = (
    os.path.join(PROJECT_ROOT, "assets", "sounds")
    if os.path.exists(os.path.join(PROJECT_ROOT, "assets", "sounds"))
    else os.path.join(PROJECT_ROOT, "sounds")
)
LYRICS_CACHE_DIR = os.path.join(PROJECT_ROOT, "assets", "lyrics_cache")
os.makedirs(LYRICS_CACHE_DIR, exist_ok=True)
FONTS_DIR = os.path.join(PROJECT_ROOT, "assets", "fonts")
os.makedirs(FONTS_DIR, exist_ok=True)
ICON_PATH = (
    os.path.join(PROJECT_ROOT, "assets", "icons", "app_icon.ico")
    if os.path.exists(os.path.join(PROJECT_ROOT, "assets", "icons", "app_icon.ico"))
    else os.path.join(PROJECT_ROOT, "app_icon.ico")
)

SUPPORTED_AUDIO_EXTS = (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".opus")

# ==========================================================
# Window & Sizing Constants
# ==========================================================
CANVAS_BASE_SIZE = 591
DEFAULT_OVERLAY_SIZE = 300
MIN_CHAR_SIZE = 150
MAX_CHAR_SIZE = 3840

# Mouth bounding box coordinates in the 591x591 sprite space (covers transparent cavity with generous safety margin):
MOUTH_BOX_X = 135
MOUTH_BOX_Y = 220
MOUTH_BOX_W = 320
MOUTH_BOX_H = 232

# Eye socket origins in the 591x591 sprite space:
DEFAULT_ORIGIN_LX = 148
DEFAULT_ORIGIN_LY = 85
DEFAULT_ORIGIN_RX = 403
DEFAULT_ORIGIN_RY = 106

# Persistent settings defaults
DEFAULT_SETTINGS = {
    "pos_x": 1347,
    "pos_y": 630,
    "char_size": 200,
    "eye_sensitivity": 1.68,
    "opacity": 1.0,
    "bass_pop": True,
    "visualizer_mode": "Neon Wave",
    "visualizer_palette": "Cyberpunk Neon",
    "volume": 0.49,
    "music_folder": "",
    "shuffle": False,
    "lyrics_enabled": True,
    "lyrics_color": "#00ffff",
    "lyrics_word_glow": True,
    "lyrics_dialogue_mode": True,
    "show_subtitle_bg": True,
    "lyrics_font": "Rajdhani",
    "lyrics_font_size": 18,
    "lyrics_offsets": {},
    "show_startup_guide": True,
    "eco_mode": False,
    "audio_mode": "player",
    "lyrics_x": 427,
    "lyrics_y": 727,
    "show_lyrics": True,
    "download_folder": "",
    "discord_rpc": True,
    "queue": [],
    "play_counts": {},
    "favourite_tracks": [],
    "custom_playlists": {},
    "current_playlist": "All Tracks",
    "current_sort": "Default",
    "playtime_seconds": 0,
    "level": 0,
    "exp": 0,
}


SETTINGS_VERSION = 2
APP_VERSION = "2.6.0"


def portable_path(path: str) -> str:
    """Stores paths inside the project as relative paths so the folder stays movable."""
    if not path:
        return path
    try:
        relative = os.path.relpath(os.path.abspath(path), PROJECT_ROOT)
    except (OSError, ValueError):
        return path
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        return path
    return relative.replace(os.sep, "/")


def resolve_path(path: str) -> str:
    """Resolves a relative settings path against the project root."""
    if not path:
        return path
    expanded = os.path.expanduser(path)
    if os.path.isabs(expanded):
        return os.path.normpath(expanded)
    return os.path.normpath(os.path.join(PROJECT_ROOT, expanded))


def load_settings(path: str | None = None) -> dict:
    """Loads settings, merges defaults, and resolves portable paths."""
    settings_path = path or SETTINGS_FILE
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                settings.update(data)
        except (OSError, json.JSONDecodeError) as exc:
            log.error("[SETTINGS] Failed to read %s: %s", settings_path, exc)
    for key in ("music_folder", "download_folder"):
        if settings.get(key):
            settings[key] = resolve_path(settings[key])
    if isinstance(settings.get("queue"), list):
        settings["queue"] = [
            resolve_path(p) for p in settings["queue"]
            if isinstance(p, str) and p.strip()
        ]
    else:
        settings["queue"] = []
    if not isinstance(settings.get("lyrics_offsets"), dict):
        settings["lyrics_offsets"] = {}
    if not isinstance(settings.get("play_counts"), dict):
        settings["play_counts"] = {}
    else:
        resolved_counts = {}
        for p, count in settings["play_counts"].items():
            if isinstance(p, str):
                c = int(count)
                resolved_counts[p] = c
                resolved_p = resolve_path(p)
                resolved_counts[resolved_p] = c
                resolved_counts[os.path.normpath(resolved_p)] = c
                resolved_counts[portable_path(p)] = c
        settings["play_counts"] = resolved_counts
    if not isinstance(settings.get("favourite_tracks"), list):
        settings["favourite_tracks"] = []
    else:
        settings["favourite_tracks"] = [
            resolve_path(p) for p in settings["favourite_tracks"]
            if isinstance(p, str) and p.strip()
        ]
    if not isinstance(settings.get("custom_playlists"), dict):
        settings["custom_playlists"] = {}
    else:
        resolved_pl = {}
        for pl_name, p_list in settings["custom_playlists"].items():
            if isinstance(p_list, list):
                resolved_pl[pl_name] = [
                    resolve_path(p) for p in p_list if isinstance(p, str) and p.strip()
                ]
        settings["custom_playlists"] = resolved_pl
    if not isinstance(settings.get("current_playlist"), str):
        settings["current_playlist"] = "All Tracks"
    if not isinstance(settings.get("current_sort"), str):
        settings["current_sort"] = "Default"
    try:
        val = int(settings.get("lyrics_font_size", 18))
        settings["lyrics_font_size"] = max(14, min(60, val))
    except (TypeError, ValueError):
        settings["lyrics_font_size"] = 18
    settings["_version"] = SETTINGS_VERSION
    return settings


def save_settings(data: dict, path: str | None = None) -> bool:
    """Atomically saves settings, converting project paths to portable relative paths."""
    settings_path = path or SETTINGS_FILE
    payload = dict(data)
    payload["_version"] = SETTINGS_VERSION

    # Preserve level/XP when an unrelated component saves a settings dict that
    # was loaded earlier (overlay position, download folder, guide, etc.).
    # Without this, those write-backs silently reset all progress.
    xp_keys = ("level", "exp", "playtime_seconds")
    if any(key not in payload for key in xp_keys):
        try:
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if isinstance(existing, dict):
                    for key in xp_keys:
                        payload.setdefault(key, existing.get(key, 0))
        except (OSError, json.JSONDecodeError):
            pass
    for key in xp_keys:
        payload.setdefault(key, DEFAULT_SETTINGS.get(key, 0))
    for key in ("music_folder", "download_folder"):
        if payload.get(key):
            payload[key] = portable_path(payload[key])
    if isinstance(payload.get("queue"), list):
        payload["queue"] = [
            portable_path(p) for p in payload["queue"]
            if isinstance(p, str) and p.strip()
        ]
    if isinstance(payload.get("favourite_tracks"), list):
        payload["favourite_tracks"] = [
            portable_path(p) for p in payload["favourite_tracks"]
            if isinstance(p, str) and p.strip()
        ]
    if isinstance(payload.get("custom_playlists"), dict):
        portable_pl = {}
        for pl_name, p_list in payload["custom_playlists"].items():
            if isinstance(p_list, list):
                portable_pl[pl_name] = [
                    portable_path(p) for p in p_list if isinstance(p, str) and p.strip()
                ]
        payload["custom_playlists"] = portable_pl
    if isinstance(payload.get("play_counts"), dict):
        portable_counts = {}
        for p, count in payload["play_counts"].items():
            if isinstance(p, str):
                port_key = portable_path(p)
                portable_counts[port_key] = max(portable_counts.get(port_key, 0), int(count))
        payload["play_counts"] = portable_counts
    directory = os.path.dirname(os.path.abspath(settings_path)) or "."
    tmp_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".talia-settings-", suffix=".tmp", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, settings_path)
        tmp_path = None
        log.debug("[SETTINGS] Saved all layout & settings to %s", settings_path)
        return True
    except Exception as exc:
        log.error("[SETTINGS] Failed to save %s: %s", settings_path, exc)
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def trim_process_memory(force_gc: bool = False):
    """Releases physical RAM working set back to Windows without causing periodic GC stalls."""
    if force_gc:
        import gc

        gc.collect()
    try:
        ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
    except Exception:
        pass


_fonts_initialized = False


def init_app_fonts(force: bool = False):
    """Pre-registers all bundled fonts in assets/fonts/ (including Rajdhani) with QFontDatabase."""
    global _fonts_initialized
    if _fonts_initialized and not force:
        return []
    from PyQt6.QtGui import QFontDatabase

    registered = []
    if os.path.exists(FONTS_DIR):
        for f in os.listdir(FONTS_DIR):
            if f.lower().endswith((".ttf", ".otf", ".woff", ".woff2")):
                p = os.path.join(FONTS_DIR, f)
                fid = QFontDatabase.addApplicationFont(p)
                if fid != -1:
                    registered.extend(QFontDatabase.applicationFontFamilies(fid))
    _fonts_initialized = True
    return registered


# ==========================================================
# Win32 API Bindings & Constants
# ==========================================================
user32 = ctypes.windll.user32

try:
    GetWindowLong = user32.GetWindowLongPtrW
    SetWindowLong = user32.SetWindowLongPtrW
    GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
    GetWindowLong.restype = ctypes.c_ssize_t
    SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    SetWindowLong.restype = ctypes.c_ssize_t
except AttributeError:
    GetWindowLong = user32.GetWindowLongW
    SetWindowLong = user32.SetWindowLongW
    GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
    GetWindowLong.restype = ctypes.c_long
    SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    SetWindowLong.restype = ctypes.c_long

user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL

user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008

HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_FRAMECHANGED = 0x0020

VK_CONTROL = 0x11
VK_OEM_4 = 0xDB  # '[' key (Lyrics Sync Offset -0.25s)
VK_OEM_6 = 0xDD  # ']' key (Lyrics Sync Offset +0.25s)

VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF

# ==========================================================
# Cyberpunk Visualizer Color Palettes
# ==========================================================
COLOR_THEMES = {
    "Cyberpunk Neon": {
        "bg": QColor(8, 8, 18, 245),
        "grid": QColor(0, 240, 255, 25),
        "bar_bottom": QColor(0, 240, 255),  # Neon Cyan
        "bar_mid": QColor(255, 0, 128),  # Neon Magenta
        "bar_top": QColor(255, 230, 0),  # Cyber Yellow
        "peak": QColor(255, 255, 255),
        "wave": QColor(0, 240, 255),
        "wave_glow": QColor(255, 0, 128, 90),
    },
    "Matrix Terminal": {
        "bg": QColor(4, 14, 6, 245),
        "grid": QColor(0, 255, 100, 25),
        "bar_bottom": QColor(0, 180, 50),
        "bar_mid": QColor(0, 255, 100),
        "bar_top": QColor(180, 255, 120),
        "peak": QColor(240, 255, 240),
        "wave": QColor(0, 255, 100),
        "wave_glow": QColor(0, 255, 120, 90),
    },
    "Synthwave Sunset": {
        "bg": QColor(18, 6, 26, 245),
        "grid": QColor(255, 110, 0, 30),
        "bar_bottom": QColor(128, 0, 255),  # Deep Violet
        "bar_mid": QColor(255, 0, 100),  # Hot Pink
        "bar_top": QColor(255, 160, 0),  # Sunburst Orange
        "peak": QColor(255, 240, 200),
        "wave": QColor(255, 50, 130),
        "wave_glow": QColor(255, 130, 0, 90),
    },
    "Arctic Glitch": {
        "bg": QColor(6, 12, 22, 245),
        "grid": QColor(120, 200, 255, 25),
        "bar_bottom": QColor(0, 150, 255),
        "bar_mid": QColor(140, 100, 255),
        "bar_top": QColor(220, 245, 255),
        "peak": QColor(255, 255, 255),
        "wave": QColor(100, 220, 255),
        "wave_glow": QColor(160, 100, 255, 90),
    },
}


# Level pacing: 1 EXP per second of active playback.
# Level 0 -> 1 needs 300 EXP (5 minutes); each later level costs 15% more.
EXP_PER_SECOND = 1
LEVEL_1_EXP = 300
LEVEL_EXP_GROWTH = 1.15


def get_exp_for_level(level: int) -> int:
    """Calculates the EXP needed to advance from `level` to `level + 1`.

    Level 0 -> 1 requires 300 EXP (5 minutes at 1 EXP/sec). Each subsequent
    level costs 15% more than the previous one: 300 * (1.15 ** level).
    Cumulative playtime is roughly 1.7 h to level 10 and 8.5 h to level 20.
    """
    level = max(0, int(level))
    return int(round(LEVEL_1_EXP * (LEVEL_EXP_GROWTH**level)))


def get_cumulative_exp_for_level(level: int) -> int:
    """Calculates the cumulative EXP (in seconds) required to reach `level + 1`.

    Level 0 -> 300s (5m) to reach Level 1.
    Level 1 -> 300s + 345s = 645s (11m) to reach Level 2.
    """
    level = max(0, int(level))
    return sum(get_exp_for_level(i) for i in range(level + 1))


def apply_playtime_exp(
    level: int, exp: int, playtime_seconds: int, seconds: int = 1
) -> tuple[int, int, int, int, bool]:
    """Advances XP in memory without touching settings.json.

    Args:
        level: Current level.
        exp: EXP accumulated toward the next level.
        playtime_seconds: Total lifetime playtime in seconds.
        seconds: Seconds of playback to add (1 second = 1 EXP).

    Returns:
        (new_level, new_exp, new_playtime_seconds, exp_needed_for_next, leveled_up)
    """
    seconds = max(0, int(seconds))
    level = max(0, int(level))
    exp = max(0, int(exp)) + seconds
    playtime_seconds = max(0, int(playtime_seconds)) + seconds

    leveled_up = False
    while exp >= get_exp_for_level(level):
        exp -= get_exp_for_level(level)
        level += 1
        leveled_up = True

    return level, exp, playtime_seconds, get_exp_for_level(level), leveled_up


def add_playtime_exp(seconds: int = 1) -> tuple[int, int, int, bool]:
    """Disk-backed XP helper (kept for scripts/tests).

    The live UI uses :func:`apply_playtime_exp` and batches saves so it does not
    rewrite settings.json every second.

    Returns:
        (current_level, current_exp, max_exp_for_level, did_level_up)
    """
    settings = load_settings()
    level, exp, playtime_seconds, req, leveled_up = apply_playtime_exp(
        settings.get("level", 0),
        settings.get("exp", 0),
        settings.get("playtime_seconds", 0),
        seconds,
    )
    settings["playtime_seconds"] = playtime_seconds
    settings["level"] = level
    settings["exp"] = exp
    save_settings(settings)
    return level, exp, req, leveled_up

