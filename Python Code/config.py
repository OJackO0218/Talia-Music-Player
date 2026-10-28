"""
Configuration, Constants, Settings Storage, and Win32 Bindings for Talia Cyberpunk Visualizer.
"""

import os
import json
import ctypes
from PyQt6.QtGui import QColor

# ==========================================================
# Paths & Directories (Resolves project root dynamically)
# ==========================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(CURRENT_DIR).lower() in ("python code", "code", "src"):
    PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
else:
    PROJECT_ROOT = CURRENT_DIR

BASE_DIR = PROJECT_ROOT
EYE_PARTS_DIR = os.path.join(PROJECT_ROOT, "eye_parts")
DEFAULT_MUSIC_DIR = os.path.join(PROJECT_ROOT, "music")
SETTINGS_FILE = os.path.join(PROJECT_ROOT, "settings.json")
PNGS_DIR = os.path.join(PROJECT_ROOT, "PNGs")
SOUNDS_DIR = os.path.join(PROJECT_ROOT, "sounds")

SUPPORTED_AUDIO_EXTS = ('.mp3', '.wav', '.flac', '.ogg', '.m4a', '.opus')

# ==========================================================
# Window & Sizing Constants
# ==========================================================
CANVAS_BASE_SIZE = 591
DEFAULT_OVERLAY_SIZE = 850
MIN_CHAR_SIZE = 150
MAX_CHAR_SIZE = 3840

# Mouth bounding box coordinates in the 591x591 sprite space:
MOUTH_BOX_X = 143
MOUTH_BOX_Y = 228
MOUTH_BOX_W = 300
MOUTH_BOX_H = 217

# Eye socket origins in the 591x591 sprite space:
DEFAULT_ORIGIN_LX = 148
DEFAULT_ORIGIN_LY = 85
DEFAULT_ORIGIN_RX = 403
DEFAULT_ORIGIN_RY = 106

# ==========================================================
# Persistent Settings Management
# ==========================================================
DEFAULT_SETTINGS = {
    "pos_x": -1,
    "pos_y": -1,
    "char_size": 850,
    "eye_sensitivity": 1.0,
    "opacity": 1.0,
    "scanlines": True,
    "widescreen": False,
    "visualizer_mode": "Cyber Bars",
    "visualizer_palette": "Cyberpunk Neon",
    "volume": 0.85,
    "music_folder": DEFAULT_MUSIC_DIR,
    "shuffle": False,
    "bass_pop": True,
    "audio_mode": "player"  # "player" = Built-in Playlist, "desktop" = Desktop Audio (osu!, Spotify, Games)
}


def load_settings() -> dict:
    """Loads saved settings from settings.json or returns defaults."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                settings = DEFAULT_SETTINGS.copy()
                settings.update(data)
                return settings
        except Exception as e:
            print(f"[SETTINGS] Failed to read {SETTINGS_FILE}: {e}")
    return DEFAULT_SETTINGS.copy()


def save_settings(data: dict) -> bool:
    """Saves settings dictionary to settings.json."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print("[SETTINGS] Saved all layout & settings to settings.json successfully!")
        return True
    except Exception as e:
        print(f"[SETTINGS] Failed to save {SETTINGS_FILE}: {e}")
        return False


# ==========================================================
# Win32 API Bindings & Constants
# ==========================================================
user32 = ctypes.windll.user32

try:
    GetWindowLong = user32.GetWindowLongPtrW
    SetWindowLong = user32.SetWindowLongPtrW
except AttributeError:
    GetWindowLong = user32.GetWindowLongW
    SetWindowLong = user32.SetWindowLongW

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008

HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_FRAMECHANGED = 0x0020

VK_F8 = 0x77   # F8: Toggle Move Talia mode
VK_F9 = 0x78   # F9: Toggle Show/Hide overlay
VK_F10 = 0x79  # F10: Toggle Audio Source Mode (Desktop vs Player)

VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1

# ==========================================================
# Cyberpunk Visualizer Color Palettes
# ==========================================================
COLOR_THEMES = {
    "Cyberpunk Neon": {
        "bg": QColor(8, 8, 18, 245),
        "grid": QColor(0, 240, 255, 25),
        "bar_bottom": QColor(0, 240, 255),      # Neon Cyan
        "bar_mid": QColor(255, 0, 128),         # Neon Magenta
        "bar_top": QColor(255, 230, 0),          # Cyber Yellow
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
        "bar_bottom": QColor(128, 0, 255),      # Deep Violet
        "bar_mid": QColor(255, 0, 100),         # Hot Pink
        "bar_top": QColor(255, 160, 0),         # Sunburst Orange
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
    }
}
