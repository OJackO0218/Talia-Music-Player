# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for Talia.

Paths are resolved relative to this file (``SPECPATH``) so the project can be
built from any folder or drive without editing the spec.
"""

import os

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

PROJECT_ROOT = SPECPATH  # noqa: F821 - provided by PyInstaller
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
FETCHER_DIR = os.path.join(PROJECT_ROOT, "Talia Lyrics Fetch Automated")

datas = []
binaries = []
hiddenimports = [
    "audio_engine",
    "audio_feeder",
    "config",
    "controller",
    "download_panel",
    "guide_dialog",
    "logging_setup",
    "lyrics_manager",
    "lyrics_overlay",
    "overlay",
    "party_dialog",
    "party_sync",
    "playlist_panel",
    "settings_dialog",
    "song_downloader",
    "spotify_dialog",
    "spotify_sync",
    "ui_theme",
    "ui_widgets",
    "updater",
    "visualizer",
    "gui_fetcher",
    "fetch_lyrics",
    "PyQt6.QtMultimedia",
    "sounddevice",
    "soundfile",
    "soundcard",
    "numpy",
    "PIL",
    "yt_dlp",
    "static_ffmpeg",
    "syncedlyrics",
    "websockets",
    "discord_service",
    "pypresence",
]
datas += collect_data_files("sounddevice")
datas += collect_data_files("soundfile")
datas += collect_data_files("soundcard")
binaries += collect_dynamic_libs("sounddevice")
binaries += collect_dynamic_libs("soundfile")
for package in ("yt_dlp", "static_ffmpeg", "websockets", "pypresence"):
    collected = collect_all(package)
    datas += collected[0]
    binaries += collected[1]
    hiddenimports += collected[2]


a = Analysis(
    [os.path.join(SRC_DIR, "main.py")],
    pathex=[SRC_DIR, FETCHER_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "cv2",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineQuick",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuick3D",
        "PyQt6.QtPdf",
        "PyQt6.QtPdfWidgets",
        "PyQt6.QtSql",
        "PyQt6.QtTest",
        "PyQt6.QtSensors",
        "PyQt6.QtPositioning",
        "PyQt6.QtBluetooth",
        "PyQt6.QtNfc",
        "scipy",
        "pandas",
        "matplotlib",
        "tkinter",
        "setuptools",
        "pkg_resources",
        "werkzeug",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Talia",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=os.path.join(PROJECT_ROOT, "version_info.txt"),
    icon=[os.path.join(PROJECT_ROOT, "assets", "icons", "app_icon.ico")],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Talia",
)
