"""
Builds a lean, fast, standalone Windows distribution of Talia Visualizer.
Uses PyInstaller to bundle Python, PyQt6 (core only), OpenCV, and audio engines.
Outputs a clean portable folder: dist/Talia/ and a ready-to-upload ZIP: dist/Talia-Windows-x64.zip
"""

import os
import sys
import shutil
import zipfile
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
MAIN_PY = os.path.join(SRC_DIR, "main.py")
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
MUSIC_DIR = os.path.join(PROJECT_ROOT, "music")
ICON_ICO = os.path.join(ASSETS_DIR, "icons", "app_icon.ico")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")
APP_DIST = os.path.join(DIST_DIR, "Talia")
ZIP_OUTPUT = os.path.join(DIST_DIR, "Talia-Windows-x64.zip")

print("=======================================================")
print("  TALIA CYBERPUNK VISUALIZER - LEAN RELEASE BUILDER")
print("=======================================================")
print(f"[*] Project root: {PROJECT_ROOT}")

# 1. Clean previous build artifacts
if os.path.exists(DIST_DIR):
    shutil.rmtree(DIST_DIR, ignore_errors=True)
if os.path.exists(BUILD_DIR):
    shutil.rmtree(BUILD_DIR, ignore_errors=True)

# 2. Optimized PyInstaller command (excludes massive unused Qt/science modules)
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--onedir",
    "--uac-admin",
    "--name", "Talia",
    "--icon", ICON_ICO,
    "--paths", SRC_DIR,
    # Collect required audio backends
    "--collect-data", "sounddevice",
    "--collect-data", "soundfile",
    "--collect-data", "soundcard",
    "--collect-binaries", "sounddevice",
    "--collect-binaries", "soundfile",
    # Targeted imports
    "--hidden-import", "PyQt6.QtMultimedia",
    "--hidden-import", "sounddevice",
    "--hidden-import", "soundfile",
    "--hidden-import", "soundcard",
    "--hidden-import", "numpy",
    "--hidden-import", "PIL",
    # Exclude heavy unused modules to keep build fast (<60s) and lean
    "--exclude-module", "cv2",
    "--exclude-module", "PyQt6.QtWebEngineCore",
    "--exclude-module", "PyQt6.QtWebEngineWidgets",
    "--exclude-module", "PyQt6.QtWebEngineQuick",
    "--exclude-module", "PyQt6.QtQml",
    "--exclude-module", "PyQt6.QtQuick",
    "--exclude-module", "PyQt6.QtQuick3D",
    "--exclude-module", "PyQt6.QtPdf",
    "--exclude-module", "PyQt6.QtPdfWidgets",
    "--exclude-module", "PyQt6.QtSql",
    "--exclude-module", "PyQt6.QtTest",
    "--exclude-module", "PyQt6.QtSensors",
    "--exclude-module", "PyQt6.QtPositioning",
    "--exclude-module", "PyQt6.QtBluetooth",
    "--exclude-module", "PyQt6.QtNfc",
    "--exclude-module", "scipy",
    "--exclude-module", "pandas",
    "--exclude-module", "matplotlib",
    "--exclude-module", "tkinter",
    MAIN_PY
]

print(f"[*] Running PyInstaller command...")
res = subprocess.run(cmd, cwd=PROJECT_ROOT)
if res.returncode != 0:
    print(f"[X] PyInstaller build failed with exit code: {res.returncode}")
    sys.exit(res.returncode)

# 3. Copy assets and music into the dist/Talia folder
print("[*] Copying assets and music to portable distribution folder...")
dest_assets = os.path.join(APP_DIST, "assets")
dest_music = os.path.join(APP_DIST, "music")

if os.path.exists(ASSETS_DIR):
    shutil.copytree(ASSETS_DIR, dest_assets, dirs_exist_ok=True)
if os.path.exists(MUSIC_DIR):
    shutil.copytree(MUSIC_DIR, dest_music, dirs_exist_ok=True)

# Also create a quick launcher shortcut helper in the zip
readme_txt = """=======================================================
  TALIA CYBERPUNK MUSIC PLAYER & DESKTOP VISUALIZER
=======================================================

HOW TO RUN:
Double-click "Talia.exe" to start!
No installation, Python, or configuration required.

CONTROLS:
- 1 Click on Talia: Play / Pause.
- 2 Clicks on Talia: Skip to next song.
- 3 Clicks on Talia: Open Controller Settings Panel.
- Hold for 0.7s: Tactile punch unlocks Drag Mode (Move / Resize).
- Hold for 2s: Dramatic sinking power-down sequence and exit.
- Scroll Wheel on Talia:
  * In Live / Desktop Audio Mode ([F10]): Adjusts laptop master system volume directly!
  * In Built-in Player Mode: Adjusts Talia's music playback volume.
  * Eyes reflect saturation levels (0% grayscale mute to neon glow).
- [F8]: Toggle Move Talia mode (Click & Drag anywhere / Scroll wheel to resize).
- [F9]: Hide / Show Talia instantly.
- [F10]: Toggle Audio Source Mode (Desktop WASAPI Loopback vs Local Playlist).

Enjoy!
"""
with open(os.path.join(APP_DIST, "README.txt"), "w", encoding="utf-8") as f:
    f.write(readme_txt)

# 4. Create ZIP package
print(f"[*] Packaging standalone ZIP archive: {ZIP_OUTPUT}...")
with zipfile.ZipFile(ZIP_OUTPUT, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(APP_DIST):
        for file in files:
            full_path = os.path.join(root, file)
            arc_name = os.path.relpath(full_path, DIST_DIR)
            zf.write(full_path, arc_name)

zip_size_mb = os.path.getsize(ZIP_OUTPUT) / (1024 * 1024)
print(f"\n[+] SUCCESS! Created standalone release:")
print(f"    - Portable Folder : {APP_DIST}")
print(f"    - Standalone ZIP   : {ZIP_OUTPUT} ({zip_size_mb:.1f} MB)")
print("=======================================================")
