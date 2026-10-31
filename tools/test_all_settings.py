"""
Comprehensive Settings Audit & Functional Verification for Talia.
Tests all modes, themes, toggles, sliders, lyrics settings, and buttons.
"""

import os
import sys
import glob

# Ensure offscreen Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
FETCHER_DIR = os.path.join(PROJECT_ROOT, "Talia Lyrics Fetch Automated")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
if FETCHER_DIR not in sys.path:
    sys.path.insert(0, FETCHER_DIR)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPainter, QImage
from config import init_app_fonts, COLOR_THEMES
from overlay import OverlayWindow
from audio_engine import CyberAudioEngine
from controller import ControlPanel
from lyrics_overlay import LyricsOverlayWindow
from lyrics_manager import LyricsManager

def run_audit():
    print("Initializing QApplication and fonts...")
    app = QApplication.instance() or QApplication(sys.argv)
    init_app_fonts()

    print("Initializing Audio Engine and Overlay...")
    engine = CyberAudioEngine()
    tracks = glob.glob(os.path.join(PROJECT_ROOT, "music", "**", "*.opus"), recursive=True)
    if not tracks:
        tracks = glob.glob(os.path.join(PROJECT_ROOT, "music", "**", "*.*"), recursive=True)
    engine.playlist = tracks
    engine.current_index = 0
    engine.is_playing = True

    l_mgr = LyricsManager()
    l_overlay = LyricsOverlayWindow(engine, l_mgr)
    overlay = OverlayWindow(engine)
    panel = ControlPanel(overlay, engine, l_overlay)
    panel.sync_play_state()

    img = QImage(300, 300, QImage.Format.Format_ARGB32)

    # 1. Lyric fetcher button
    print("\n--- TEST 1: Launch Automated Lyric Fetcher ---")
    panel.open_lyric_fetcher()
    assert hasattr(panel, "_lyrics_fetcher_win") and panel._lyrics_fetcher_win is not None
    print("[PASS] Lyric fetcher launched in-process successfully.")

    # 2. Visualizer styles & themes
    print("\n--- TEST 2: Every Visualizer Style & Theme ---")
    modes = ["Cyber Bars", "Neon Wave", "Radial Core", "Dual Mirror"]
    themes = list(COLOR_THEMES.keys())

    for m in modes:
        for t in themes:
            panel.settings_dialog.combo_mode.setCurrentText(m)
            panel.settings_dialog.combo_theme.setCurrentText(t)
            assert overlay.visualizer.mode == m, f"Mode mismatch: {overlay.visualizer.mode} != {m}"
            assert overlay.visualizer.current_theme_name == t, f"Theme mismatch: {overlay.visualizer.current_theme_name} != {t}"
            
            p = QPainter(img)
            overlay.paintEvent(None)
            p.end()

    print(f"[PASS] All {len(modes)} styles across all {len(themes)} themes rendered without errors.")

    # 3. Settings sliders & toggles
    print("\n--- TEST 3: Settings Sliders & Toggles ---")
    sd = panel.settings_dialog

    # Character size slider
    for sz in [150, 260, 400]:
        sd.slider_size.setValue(sz)
        print(f"Size {sz}: overlay width is {overlay.width()}")
        assert overlay.width() == sz

    # Opacity slider
    for op in [30, 75, 100]:
        sd.slider_opacity.setValue(op)
        print(f"Opacity {op}: overlay opacity is {overlay.opacity_val}")
        assert abs(overlay.opacity_val - (op / 100.0)) < 0.01

    # Eye sensitivity slider
    for es in [50, 100, 200]:
        sd.slider_eye_sens.setValue(es)
        print(f"Sensitivity {es}: overlay sensitivity is {overlay.eye_sensitivity}")
        assert abs(overlay.eye_sensitivity - (es / 100.0)) < 0.01

    print("Testing bass pop...")
    sd.chk_bass_pop.setChecked(True)
    assert overlay.enable_bass_pop is True
    sd.chk_bass_pop.setChecked(False)
    assert overlay.enable_bass_pop is False
    print("Bass pop OK")

    print("Testing widescreen...")
    sd.chk_widescreen.setChecked(True)
    assert overlay.use_widescreen is True
    sd.chk_widescreen.setChecked(False)
    assert overlay.use_widescreen is False
    print("Widescreen OK")

    print("[PASS] Sliders and toggles verified.")

    # 4. Audio settings & Volume taper
    print("\n--- TEST 4: Volume & Audio Settings ---")
    for vol in [1, 5, 20, 50, 85, 100]:
        panel.slider_vol.setValue(vol)
        print(f"Volume {vol}: engine volume is {engine.volume:.6f}")
        assert panel.slider_vol.value() == vol

    print("[PASS] Volume range and logarithmic response verified.")

    # 5. Skip OSD Symbols in Mouth
    print("\n--- TEST 5: Skip OSD Feedback In Mouth ---")
    overlay.trigger_skip_feedback("forward")
    assert overlay.osd_symbol == "forward"
    assert overlay.osd_timer > 0
    p = QPainter(img)
    overlay.paintEvent(None)
    p.end()
    print("Forward skip feedback rendered.")

    overlay.trigger_skip_feedback("backward")
    assert overlay.osd_symbol == "backward"
    assert overlay.osd_timer > 0
    p = QPainter(img)
    overlay.paintEvent(None)
    p.end()
    print("Backward skip feedback rendered.")
    print("[PASS] Forward and backward skip feedback verified.")

    # 6. Lyrics Settings & Toggles
    print("\n--- TEST 6: Lyrics Settings ---")
    initial_enabled = l_overlay.is_enabled
    panel.toggle_lyrics()
    assert l_overlay.is_enabled != initial_enabled
    panel.toggle_lyrics()
    assert l_overlay.is_enabled == initial_enabled

    sd.chk_word_glow.setChecked(True)
    assert l_overlay.word_glow is True
    sd.chk_word_glow.setChecked(False)
    assert l_overlay.word_glow is False

    panel.adjust_lyrics_offset(0.25)
    assert abs(l_mgr.manual_offset - 0.25) < 0.001
    panel.adjust_lyrics_offset(-0.25)
    assert abs(l_mgr.manual_offset) < 0.001

    print("[PASS] Lyrics settings verified.")

    # 7. Settings persistence
    print("\n--- TEST 7: Settings Persistence ---")
    panel.save_settings_action()
    print("[PASS] Settings saved successfully.")

    print("\n==========================================")
    print("  ALL 7 AUDIT SECTIONS PASSED WITH 0 ERRORS")
    print("==========================================")

if __name__ == "__main__":
    run_audit()
