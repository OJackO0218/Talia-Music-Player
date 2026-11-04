"""
Main entry point for Talia Cyberpunk Audio Visualizer.
"""

# ruff: noqa: E402  (Qt imports must follow environment/path setup)

import ctypes
import logging
import os
import random
import sys

# Prevent OpenMP / BLAS from spawning multi-threaded thread pools for micro-FFT ops
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from audio_engine import CyberAudioEngine
from config import (
    DEFAULT_MUSIC_DIR,
    ICON_PATH,
    LYRICS_CACHE_DIR,
    PROJECT_ROOT,
    init_app_fonts,
    load_settings,
    save_settings,
    trim_process_memory,
)
from controller import ControlPanel
from logging_setup import setup_logging
from lyrics_manager import LyricsManager
from lyrics_overlay import LyricsOverlayWindow
from overlay import OverlayWindow
from updater import cleanup_updater_leftovers

log = logging.getLogger(__name__)

# Explicit AppUserModelID so Windows treats Talia as its own taskbar entity
APP_ID = "Athar.Talia.CyberpunkVisualizer.1.0"
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
except Exception:
    log.debug("Could not set AppUserModelID", exc_info=True)


def _log_uncaught_exception(exc_type, exc_value, exc_tb):
    """Make GUI crashes visible in talia.log instead of vanishing silently."""
    log.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def main():
    setup_logging()
    cleanup_updater_leftovers(PROJECT_ROOT)
    sys.excepthook = _log_uncaught_exception
    # Elevate to Administrator only if explicitly requested via --admin flag
    if "--admin" in sys.argv:
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_admin = False
        if not is_admin:
            if getattr(sys, "frozen", False):
                args = " ".join([f'"{a}"' for a in sys.argv[1:] if a != "--admin"])
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
            else:
                python_exe = sys.executable
                script = os.path.abspath(__file__)
                args = " ".join([f'"{a}"' for a in sys.argv[1:] if a != "--admin"])
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", python_exe, f'"{script}" {args}', None, 1
                )
            sys.exit(0)

    # Ensure only 1 instance of Talia runs at a time (pass --multi to allow multiple instances for testing)
    if "--multi" not in sys.argv:
        mutex = ctypes.windll.kernel32.CreateMutexW(  # noqa: F841 (handle must outlive app)
            None, False, "AtharTaliaCyberpunkVisualizerMutex"
        )
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            log.warning(
                "[!] Another instance of Talia is already running! Exiting duplicate process..."
            )
            sys.exit(0)
    log.info("[1/4] Starting Talia Cyberpunk Visualizer...")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    init_app_fonts()

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
    log.info("[2/4] Loading Talia character rig & visualizer surface...")
    overlay = OverlayWindow(audio_engine)
    lyrics_overlay = LyricsOverlayWindow(audio_engine, lyrics_manager)
    overlay.lyrics_overlay = lyrics_overlay

    # Initialize controller panel and apply saved layout/settings
    # Note: Controller panel starts closed/hidden as requested; open with 3 clicks on Talia!
    log.info("[3/4] Initializing Controller Panel & restoring saved settings...")
    panel = ControlPanel(overlay, audio_engine, lyrics_overlay)
    panel.apply_settings(saved_cfg)

    # Load initial track into engine in paused state (random selection on launch)
    if audio_engine.playlist:
        start_idx = random.randint(0, len(audio_engine.playlist) - 1)
        audio_engine.current_index = start_idx
        audio_engine.load_file(audio_engine.playlist[start_idx], auto_play=False, blocking=True)
        if audio_engine.shuffle:
            audio_engine.rebuild_shuffle_order(starting_index=start_idx)
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

    def _save_state_on_exit():
        try:
            cfg = panel.get_current_settings_dict()
            save_settings(cfg)
            log.info("[SETTINGS] Persisted application state and queue on exit.")
        except Exception as exc:
            log.debug("Could not save settings on exit: %s", exc)

    app.aboutToQuit.connect(_save_state_on_exit)

    trim_process_memory()
    log.info("[4/4] Talia is ready!")
    log.info("\n=======================================================")
    log.info("  TALIA CYBERPUNK AUDIO VISUALIZER")
    log.info("  - Click Talia 1x to Play / Pause.")
    log.info("  - Click Talia 2x on Right to Skip / Left to Rewind.")
    log.info("  - Click Talia 3x to Open / Show Controller Window.")
    log.info("  - Close Controller with [X] anytime (reopen with 3 clicks).")
    log.info("  - Hold Talia for 0.7s & release to toggle Move Mode (Talia & Lyrics).")
    log.info("  - Hold Talia for 2s to Power Down & Exit.")
    log.info("  - Scroll wheel on Talia to adjust volume (or resize in Move Mode).")
    log.info("  - Press [F7] to toggle Synced Lyrics Overlay.")
    log.info("  - Press [F8] to toggle Move Mode.")
    log.info("  - Press [F10] to switch Desktop Mode vs Local Player.")
    log.info("  - Press [F11] to toggle Eco Mode (< 1% CPU).")
    log.info("=======================================================\n")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
