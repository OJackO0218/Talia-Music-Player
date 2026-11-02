"""
Builds a lean, standalone Windows distribution of Talia Visualizer.

The build is driven by ``Talia.spec`` (portable, no absolute paths), then assets
and (optionally) music are copied next to the executable. Outputs a portable
folder and ``dist/Talia-Windows-x64.zip``.

Music is *not* bundled by default because most tracks are copyrighted. Pass
``--with-music`` for a private build that includes your local library.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
MAIN_PY = os.path.join(SRC_DIR, "main.py")
SPEC_FILE = os.path.join(PROJECT_ROOT, "Talia.spec")
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
MUSIC_DIR = os.path.join(PROJECT_ROOT, "music")
FETCHER_DIR = os.path.join(PROJECT_ROOT, "Talia Lyrics Fetch Automated")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
STAGE_DIR = os.path.join(PROJECT_ROOT, "build_stage")
APP_STAGE = os.path.join(STAGE_DIR, "Talia")
APP_DIST = os.path.join(DIST_DIR, "Talia")
ZIP_OUTPUT = os.path.join(DIST_DIR, "Talia-Windows-x64.zip")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Build a standalone Talia release.")
    parser.add_argument(
        "--with-music",
        action="store_true",
        help="Bundle the local music/ library (only for private, non-redistributed builds).",
    )
    return parser.parse_args(argv)


def build_executable() -> None:
    """Runs PyInstaller through the shared, portable spec file."""
    print("[*] Running PyInstaller from Talia.spec ...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        STAGE_DIR,
        SPEC_FILE,
    ]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"[X] PyInstaller build failed with exit code: {result.returncode}")
        sys.exit(result.returncode)


def copy_assets() -> None:
    print("[*] Copying assets to release folder...")
    dest_assets = os.path.join(APP_STAGE, "assets")
    if os.path.exists(ASSETS_DIR):
        shutil.copytree(ASSETS_DIR, dest_assets, dirs_exist_ok=True)
        # Direct root fallbacks keep legacy asset lookups working.
        for sub in ("eye_parts", "icons", "sounds", "fonts"):
            sub_src = os.path.join(ASSETS_DIR, sub)
            sub_dest = os.path.join(APP_STAGE, sub)
            if os.path.exists(sub_src):
                shutil.copytree(sub_src, sub_dest, dirs_exist_ok=True)


def copy_music(with_music: bool) -> None:
    """Ships an empty library by default; copyrighted audio is opt-in."""
    dest_music = os.path.join(APP_STAGE, "music")
    os.makedirs(os.path.join(dest_music, "Downloaded Songs"), exist_ok=True)
    if not with_music:
        print("[i] Music not bundled (pass --with-music for a private build).")
        return

    print("[!] Bundling local music. Do not redistribute this build.")
    if not os.path.exists(MUSIC_DIR):
        return
    for entry in os.listdir(MUSIC_DIR):
        if entry == "Downloaded Songs":
            continue
        source = os.path.join(MUSIC_DIR, entry)
        target = os.path.join(dest_music, entry)
        if os.path.isdir(source):
            shutil.copytree(source, target, dirs_exist_ok=True)
        elif os.path.isfile(source):
            shutil.copy2(source, target)


def copy_fetcher() -> None:
    dest_fetcher = os.path.join(APP_STAGE, "Talia Lyrics Fetch Automated")
    if os.path.exists(FETCHER_DIR):
        shutil.copytree(
            FETCHER_DIR,
            dest_fetcher,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )


def bundle_ffmpeg() -> None:
    """Guarantees ffmpeg.exe/ffprobe.exe exist in the packaged app."""
    target_bin = os.path.join(APP_STAGE, "_internal", "static_ffmpeg", "bin", "win32")
    os.makedirs(target_bin, exist_ok=True)
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin or not os.path.exists(ffmpeg_bin):
        print("[i] ffmpeg not found on PATH; static_ffmpeg will resolve it at runtime.")
        return
    bin_dir = os.path.dirname(os.path.abspath(ffmpeg_bin))
    for name in ("ffmpeg.exe", "ffprobe.exe", "installed.crumb"):
        source = os.path.join(bin_dir, name)
        target = os.path.join(target_bin, name)
        if os.path.exists(source) and not os.path.exists(target):
            print(f"[+] Bundling {name}")
            shutil.copy2(source, target)


def write_release_settings() -> None:
    settings = {
        "pos_x": 1028,
        "pos_y": 358,
        "char_size": 300,
        "eye_sensitivity": 1.68,
        "opacity": 1.0,
        "bass_pop": True,
        "visualizer_mode": "Neon Wave",
        "visualizer_palette": "Cyberpunk Neon",
        "volume": 0.49,
        "audio_mode": "player",
        "music_folder": "music",
        "shuffle": False,
        "eco_mode": False,
        "show_startup_guide": True,
        "lyrics_x": 218,
        "lyrics_y": 664,
        "show_lyrics": True,
        "lyrics_color": "#f472b6",
        "lyrics_word_glow": True,
        "lyrics_font": "Rajdhani",
        "download_folder": "",
        "discord_rpc": True,
        "_version": 2,
    }
    with open(os.path.join(APP_STAGE, "settings.json"), "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=4)


def write_readme() -> None:
    readme = """=======================================================
  TALIA CYBERPUNK MUSIC PLAYER & DESKTOP VISUALIZER
=======================================================

HOW TO RUN:
1. Extract the ZIP archive (Click "Extract all" in Windows Explorer).
2. Open the extracted folder and double-click "Talia.exe" to start!
   (Note: Do not run directly inside the unextracted zip, extract first!)
No installation, Python, or configuration required.

ADD YOUR MUSIC:
Copy your audio files into the "music" folder (subfolders are supported),
then use Settings -> Music Folder -> Re-scan in the app.

CONTROLS:
- 1 Click on Talia: Play / Pause.
- 2 Clicks on Talia: Double tap right side to skip, double tap left side to rewind.
- 3 Clicks on Talia: Open Minimal Player Window (Playback, Library, Song Search & Settings).
- Hold until SFX plays (0.7s): Initiates Move Mode (Drag Talia and lyrics, scroll to resize).
- Hold for 2s: Sinking power-down sequence and exit.
- Scroll Wheel on Talia: Adjusts volume (or scales Talia when Move Mode is active).
- [F7]: Toggle Synced Lyrics Overlay on / off.
- [F8]: Toggle Move Mode (reposition Talia and lyrics).
- [F9]: Hide / Show Talia and lyrics.
- [F10]: Switch Desktop Audio Mode vs Local Player.
- [F11]: Toggle Eco Mode (30 FPS, ultra-low CPU).

Enjoy!
"""
    with open(os.path.join(APP_STAGE, "README.txt"), "w", encoding="utf-8") as handle:
        handle.write(readme)


def zip_release() -> None:
    print(f"[*] Packaging standalone ZIP archive: {ZIP_OUTPUT} ...")
    with zipfile.ZipFile(ZIP_OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, _dirs, files in os.walk(APP_STAGE):
            for name in files:
                full_path = os.path.join(root, name)
                archive.write(full_path, os.path.relpath(full_path, STAGE_DIR))
    size_mb = os.path.getsize(ZIP_OUTPUT) / (1024 * 1024)
    print(f"[+] Created {ZIP_OUTPUT} ({size_mb:.1f} MB)")


def main(argv=None) -> None:
    args = parse_args(argv)
    print("=======================================================")
    print("  TALIA CYBERPUNK VISUALIZER - LEAN RELEASE BUILDER")
    print("=======================================================")
    print(f"[*] Project root: {PROJECT_ROOT}")

    if not os.path.exists(MAIN_PY) or not os.path.exists(SPEC_FILE):
        print("[X] src/main.py or Talia.spec is missing.")
        sys.exit(1)

    print("[*] Ensuring static_ffmpeg binaries are fetched before packaging...")
    try:
        import static_ffmpeg

        static_ffmpeg.add_paths()
    except Exception as exc:
        print(f"[!] Warning fetching static_ffmpeg: {exc}")

    if os.path.exists(STAGE_DIR):
        shutil.rmtree(STAGE_DIR, ignore_errors=True)
    os.makedirs(DIST_DIR, exist_ok=True)

    build_executable()
    copy_assets()
    copy_music(args.with_music)
    copy_fetcher()
    bundle_ffmpeg()
    write_release_settings()
    write_readme()
    zip_release()

    try:
        if os.path.exists(APP_DIST):
            shutil.rmtree(APP_DIST)
        shutil.copytree(APP_STAGE, APP_DIST)
        print(f"[+] Updated portable folder: {APP_DIST}")
    except OSError as exc:
        print(f"[*] Note: dist/Talia is currently in use ({exc}).")
        print(f"[*] Standalone ZIP package is up to date: {ZIP_OUTPUT}")

    shutil.rmtree(STAGE_DIR, ignore_errors=True)
    print("\n[+] SUCCESS! Standalone release created.")
    print("=======================================================")


if __name__ == "__main__":
    main()
