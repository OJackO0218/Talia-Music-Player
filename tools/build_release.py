"""
Builds a lean, fast, standalone Windows distribution of Talia Visualizer.
Uses PyInstaller to bundle Python, PyQt6 (core only), OpenCV, and audio engines.
Outputs a clean portable folder and a ready-to-upload ZIP: dist/Talia-Windows-x64.zip
Uses a staging directory to prevent PermissionError when an existing Talia.exe instance is running.
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
STAGE_DIR = os.path.join(PROJECT_ROOT, "build_stage")
APP_STAGE = os.path.join(STAGE_DIR, "Talia")
APP_DIST = os.path.join(DIST_DIR, "Talia")
ZIP_OUTPUT = os.path.join(DIST_DIR, "Talia-Windows-x64.zip")

print("=======================================================")
print("  TALIA CYBERPUNK VISUALIZER - LEAN RELEASE BUILDER")
print("=======================================================")
print(f"[*] Project root: {PROJECT_ROOT}")

# 1. Clean previous build staging
if os.path.exists(STAGE_DIR):
    shutil.rmtree(STAGE_DIR, ignore_errors=True)
os.makedirs(DIST_DIR, exist_ok=True)

# 2. Optimized PyInstaller command (excludes massive unused Qt/science modules)
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--onedir",
    "--uac-admin",
    "--name", "Talia",
    "--distpath", STAGE_DIR,
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

print(f"[*] Running PyInstaller command into staging area...")
res = subprocess.run(cmd, cwd=PROJECT_ROOT)
if res.returncode != 0:
    print(f"[X] PyInstaller build failed with exit code: {res.returncode}")
    sys.exit(res.returncode)

# 3. Copy assets and music into the staging folder
print("[*] Copying assets and music to release folder...")
dest_assets = os.path.join(APP_STAGE, "assets")
dest_music = os.path.join(APP_STAGE, "music")

if os.path.exists(ASSETS_DIR):
    shutil.copytree(ASSETS_DIR, dest_assets, dirs_exist_ok=True)
    # Also provide direct root fallbacks for eye_parts, icons, sounds for 100% path safety
    for sub in ["eye_parts", "icons", "sounds"]:
        sub_src = os.path.join(ASSETS_DIR, sub)
        sub_dest = os.path.join(APP_STAGE, sub)
        if os.path.exists(sub_src):
            shutil.copytree(sub_src, sub_dest, dirs_exist_ok=True)
if os.path.exists(MUSIC_DIR):
    shutil.copytree(MUSIC_DIR, dest_music, dirs_exist_ok=True)

readme_txt = """=======================================================
  TALIA CYBERPUNK MUSIC PLAYER & DESKTOP VISUALIZER
=======================================================

HOW TO RUN:
Double-click "Talia.exe" to start!
No installation, Python, or configuration required.

CONTROLS:
- 1 Click on Talia: Play / Pause.
- 2 Clicks on Talia: Double tap right side to skip, double tap left side to rewind.
- 3 Clicks on Talia: Open Controller Settings Panel.
- Hold until SFX plays (0.7s): Initiates Move Mode (Drag Talia and lyrics, scroll to resize).
- Hold for 2s: Sinking power-down sequence and exit.
- Scroll Wheel on Talia: Adjusts volume (or scales Talia when Move Mode is active).
- [F7]: Toggle Synced Lyrics Overlay on / off.
- [F8]: Toggle Move Mode (reposition Talia and lyrics).
- [F9]: Hide / Show Talia and lyrics.
- [F10]: Switch Desktop Audio Mode vs Local Player.

Enjoy!
"""
with open(os.path.join(APP_STAGE, "README.txt"), "w", encoding="utf-8") as f:
    f.write(readme_txt)

# 4. Create ZIP package
print(f"[*] Packaging standalone ZIP archive: {ZIP_OUTPUT}...")
with zipfile.ZipFile(ZIP_OUTPUT, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(APP_STAGE):
        for file in files:
            full_path = os.path.join(root, file)
            arc_name = os.path.relpath(full_path, STAGE_DIR)
            zf.write(full_path, arc_name)

zip_size_mb = os.path.getsize(ZIP_OUTPUT) / (1024 * 1024)

# 5. Try updating dist/Talia if not locked
try:
    if os.path.exists(APP_DIST):
        shutil.rmtree(APP_DIST)
    shutil.copytree(APP_STAGE, APP_DIST)
    print(f"[+] Updated portable folder: {APP_DIST}")
except Exception as e:
    print(f"[*] Note: dist/Talia is currently in use ({e}).")
    print(f"[*] Standalone ZIP package is updated: {ZIP_OUTPUT}")

# Clean stage
shutil.rmtree(STAGE_DIR, ignore_errors=True)

print(f"\n[+] SUCCESS! Created standalone release:")
print(f"    - Standalone ZIP   : {ZIP_OUTPUT} ({zip_size_mb:.1f} MB)")
print("=======================================================")
