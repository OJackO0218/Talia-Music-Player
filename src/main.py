"""
Main entry point for Talia Cyberpunk Audio Visualizer.
"""

import os
import sys
import ctypes

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from config import DEFAULT_MUSIC_DIR, PROJECT_ROOT, load_settings, ICON_PATH, LYRICS_CACHE_DIR
from audio_engine import CyberAudioEngine
from lyrics_manager import LyricsManager
from lyrics_overlay import LyricsOverlayWindow
from overlay import OverlayWindow
from controller import ControlPanel

# Explicit AppUserModelID so Windows treats Talia as its own taskbar entity
APP_ID = "Athar.Talia.CyberpunkVisualizer.1.0"
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
except Exception:
    pass


def main():
    # 0. Automatically elevate and run as Administrator if not already elevated
    if "--no-admin" not in sys.argv:
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_admin = False

        if not is_admin:
            if getattr(sys, "frozen", False):
                args = " ".join([f'"{a}"' for a in sys.argv[1:]])
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
            else:
                python_exe = sys.executable
                script = os.path.abspath(__file__)
                ctypes.windll.shell32.ShellExecuteW(None, "runas", python_exe, f'"{script}"', None, 1)
            sys.exit(0)

    # Ensure only 1 instance of Talia runs at a time (prevents orphaned background instances)
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "AtharTaliaCyberpunkVisualizerMutex")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        print("[!] Another instance of Talia is already running! Exiting duplicate process...")
        sys.exit(0)

    print("[1/4] Starting Talia Cyberpunk Visualizer...")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Set application icon for Windows taskbar & alt-tab
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    # Load persistent settings from settings.json
    saved_cfg = load_settings()

    # Initialize audio playback engine and lyrics manager
    music_folder = saved_cfg.get("music_folder", DEFAULT_MUSIC_DIR)
    if not music_folder or not os.path.exists(music_folder):
        music_folder = DEFAULT_MUSIC_DIR
    lyrics_manager = LyricsManager(LYRICS_CACHE_DIR)
    audio_engine = CyberAudioEngine()
    audio_engine.set_lyrics_manager(lyrics_manager)
    audio_engine.set_folder(music_folder)

    # Initialize transparent Live2D character overlay & synced lyrics overlay
    print("[2/4] Loading Talia character rig & visualizer surface...")
    overlay = OverlayWindow(audio_engine)
    lyrics_overlay = LyricsOverlayWindow(audio_engine, lyrics_manager)
    overlay.lyrics_overlay = lyrics_overlay

    # Initialize controller panel and apply saved layout/settings
    # Note: Controller panel starts closed/hidden as requested; open with 3 clicks on Talia!
    print("[3/4] Initializing Controller Panel & restoring saved settings...")
    panel = ControlPanel(overlay, audio_engine, lyrics_overlay)
    panel.apply_settings(saved_cfg)

    # Load first track into engine in paused state (no autoplay)
    if audio_engine.playlist:
        audio_engine.current_index = 0
        audio_engine.load_file(audio_engine.playlist[0], auto_play=False, blocking=True)
        panel.sync_play_state()

    # Show overlays (Talia + Synced Lyrics)
    overlay.show()
    overlay.trigger_startup_entrance()
    if lyrics_overlay.is_enabled:
        lyrics_overlay.show()
        lyrics_overlay.enforce_topmost()

    # Show startup controls & shortcuts guide if enabled
    if saved_cfg.get("show_startup_guide", True):
        panel.show_guide_dialog()

    print("[4/4] Talia is ready!")
    print("\n=======================================================")
    print("  TALIA CYBERPUNK AUDIO VISUALIZER")
    print("  - Click Talia 1x to Play / Pause.")
    print("  - Click Talia 2x on Right to Skip / Left to Rewind.")
    print("  - Click Talia 3x to Open / Show Controller Window.")
    print("  - Close Controller with [X] anytime (reopen with 3 clicks).")
    print("  - Hold Talia for 0.7s & release to toggle Move Mode (Talia & Lyrics).")
    print("  - Hold Talia for 2s to Power Down & Exit.")
    print("  - Scroll wheel on Talia to adjust volume (or resize in Move Mode).")
    print("  - Press [F7] to toggle Synced Lyrics Overlay.")
    print("  - Press [F8] to toggle Move Mode.")
    print("  - Press [F10] to switch Desktop Mode vs Local Player.")
    print("  - Press [F11] to toggle Eco Mode (< 1% CPU).")
    print("=======================================================\n")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
