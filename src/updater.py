"""
Talia Auto-Updater Service.

Checks GitHub Releases for new Talia distributions, downloads update packages,
and stages an atomic Windows file replacement via detached runner script to bypass
OS binary file locks.
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal

log = logging.getLogger("TaliaUpdater")

REPO_API_URL = "https://api.github.com/repos/OJackO0218/Talia-Music-Player/releases/latest"


def parse_semver(ver_str: str) -> tuple[int, ...]:
    """Extracts numeric semver components from version tag (e.g. 'v2.3.1' -> (2, 3, 1))."""
    cleaned = re.sub(r"^[^\d]*", "", str(ver_str).strip())
    nums = re.findall(r"\d+", cleaned)
    return tuple(int(n) for n in nums) if nums else (0, 0, 0)


def check_for_updates(current_version: str, timeout: float = 5.0) -> dict:
    """
    Checks the GitHub API for the latest release.
    Returns dictionary with update details, version comparison, and download URL.
    """
    result = {
        "has_update": False,
        "latest_version": current_version,
        "download_url": "",
        "asset_name": "",
        "release_notes": "",
        "error": "",
    }
    try:
        req = urllib.request.Request(
            REPO_API_URL,
            headers={
                "User-Agent": f"Talia-Music-Player/{current_version}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                result["error"] = f"GitHub API returned HTTP {response.status}"
                return result
            data = json.loads(response.read().decode("utf-8"))

        tag = data.get("tag_name", "").strip()
        result["latest_version"] = tag.lstrip("vV")
        result["release_notes"] = data.get("body", "")

        curr_semver = parse_semver(current_version)
        latest_semver = parse_semver(tag)

        # Look for release assets (.zip)
        assets = data.get("assets", [])
        zip_asset = None
        for a in assets:
            aname = a.get("name", "").lower()
            if aname.endswith(".zip"):
                # Prioritize windows x64 zip
                if "windows" in aname:
                    zip_asset = a
                    break
                if not zip_asset:
                    zip_asset = a

        if zip_asset:
            result["download_url"] = zip_asset.get("browser_download_url", "")
            result["asset_name"] = zip_asset.get("name", "")

        if latest_semver > curr_semver and result["download_url"]:
            result["has_update"] = True

    except Exception as exc:
        log.warning("[UPDATER] Failed to check for updates: %s", exc)
        result["error"] = str(exc)

    return result


def download_update_zip(
    download_url: str,
    dest_dir: str,
    progress_cb: Optional[Callable[[int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> tuple[bool, str, str]:
    """
    Streams the release zip to dest_dir with progress tracking.
    Returns (success, zip_path, error_msg).
    """
    os.makedirs(dest_dir, exist_ok=True)
    zip_path = os.path.join(dest_dir, "talia_latest_update.zip")
    if os.path.exists(zip_path):
        try:
            os.remove(zip_path)
        except Exception:
            pass

    try:
        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": "Talia-AutoUpdater/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15.0) as response:
            total_bytes = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            start_time = time.time()
            chunk_size = 64 * 1024

            with open(zip_path, "wb") as f_out:
                while True:
                    if cancel_check and cancel_check():
                        return False, "", "Download cancelled by user."
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f_out.write(chunk)
                    downloaded += len(chunk)

                    elapsed = time.time() - start_time
                    speed_str = ""
                    if elapsed > 0.3:
                        speed_mb = (downloaded / (1024 * 1024)) / elapsed
                        speed_str = f"{speed_mb:.1f} MB/s"

                    percent = int((downloaded / total_bytes) * 100) if total_bytes > 0 else 0
                    if progress_cb:
                        progress_cb(percent, speed_str)

        return True, zip_path, ""
    except Exception as exc:
        log.warning("[UPDATER] Download error: %s", exc)
        return False, "", str(exc)


def create_updater_batch_script(zip_path: str, target_dir: str, pid: int) -> str:
    """Generates the Windows detached updater script."""
    script_dir = os.path.dirname(zip_path)
    bat_path = os.path.join(script_dir, "apply_update.bat")

    is_frozen = getattr(sys, "frozen", False)
    exe_name = os.path.basename(sys.executable) if is_frozen else "Talia.exe"

    bat_content = f"""@echo off
setlocal enabledelayedexpansion
title Talia Music Player Auto-Updater
color 0b

echo.
echo =======================================================
echo          TALIA MUSIC PLAYER AUTO-UPDATER
echo =======================================================
echo.

set "PID={pid}"
set "ZIP_PATH={zip_path}"
set "TARGET_DIR={target_dir}"
set "EXE_NAME={exe_name}"
set "EXTRACT_DIR=%TEMP%\\talia_update_extracted"

echo [*] Waiting for previous Talia instance (PID %PID%) to close...
set /a WAIT_COUNT=0
:wait_loop
timeout /t 1 /nobreak >nul
tasklist /fi "PID eq %PID%" 2>nul | findstr /i "%PID%" >nul
if not errorlevel 1 (
    set /a WAIT_COUNT+=1
    if !WAIT_COUNT! geq 4 (
        echo [*] Releasing lingering process locks...
        taskkill /f /pid %PID% >nul 2>&1
        goto proceed
    )
    goto wait_loop
)
:proceed

echo [*] File locks released.
timeout /t 1 /nobreak >nul

:: 2. Clean previous temp extraction directory if any
echo [*] Preparing extraction workspace...
if exist "!EXTRACT_DIR!" rmdir /s /q "!EXTRACT_DIR!" 2>nul
mkdir "!EXTRACT_DIR!" 2>nul

:: 3. Extract the update zip archive via PowerShell built-in Expand-Archive
echo [*] Extracting update files...
powershell -NoProfile -Command "Expand-Archive -LiteralPath '!ZIP_PATH!' -DestinationPath '!EXTRACT_DIR!' -Force"

:: Check if archive extracted into a nested 'Talia' folder
set "SRC_DIR=!EXTRACT_DIR!"
if exist "!EXTRACT_DIR!\\Talia\\%EXE_NAME%" set "SRC_DIR=!EXTRACT_DIR!\\Talia"
if exist "!EXTRACT_DIR!\\Talia\\Talia.exe" set "SRC_DIR=!EXTRACT_DIR!\\Talia"

:: 4. Copy updated binary and asset files in place, safely preserving user music and settings
echo [*] Applying update to !TARGET_DIR!...
robocopy "!SRC_DIR!" "!TARGET_DIR!" /E /XD "!TARGET_DIR!\\music" "!TARGET_DIR!\\assets\\lyrics_cache" /XF "!TARGET_DIR!\\settings.json" /R:2 /W:1 >nul

:: 5. Cleanup temporary extraction folder
echo [*] Cleaning up temporary files...
rmdir /s /q "!EXTRACT_DIR!" 2>nul
del /f /q "!ZIP_PATH!" 2>nul

:: 6. Relaunch updated Talia executable
echo [*] Update complete! Relaunching Talia...
if exist "!TARGET_DIR!\\%EXE_NAME%" (
    start "" "!TARGET_DIR!\\%EXE_NAME%"
) else if exist "!TARGET_DIR!\\Talia.exe" (
    start "" "!TARGET_DIR!\\Talia.exe"
)

:: 7. Self-delete the batch runner
(goto) 2>nul & del "%~f0"
exit /b 0
"""
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    return bat_path


def launch_updater_and_exit(zip_path: str, target_dir: str):
    """Spawns the detached updater batch script and exits Talia process cleanly."""
    bat_script = create_updater_batch_script(zip_path, target_dir, os.getpid())
    log.info("[UPDATER] Spawning detached update runner: %s", bat_script)

    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_CONSOLE = 0x00000010

    subprocess.Popen(
        ["cmd.exe", "/c", bat_script],
        creationflags=CREATE_NEW_CONSOLE | DETACHED_PROCESS,
        close_fds=True,
    )
    # Clean exit
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app:
        app.quit()
    # Force immediate OS-level termination so background threads release file locks
    os._exit(0)


class UpdateCheckWorker(QThread):
    """Background worker for querying GitHub releases without freezing UI."""

    check_finished = pyqtSignal(dict)

    def __init__(self, current_version: str, parent=None):
        super().__init__(parent)
        self.current_version = current_version

    def run(self):
        info = check_for_updates(self.current_version)
        self.check_finished.emit(info)


class UpdateDownloadWorker(QThread):
    """Background worker for streaming update zip with progress updates."""

    progress = pyqtSignal(int, str)  # percent, speed_str
    download_finished = pyqtSignal(bool, str, str)  # success, zip_path, error_msg

    def __init__(self, download_url: str, parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        dest_dir = os.path.join(tempfile.gettempdir(), "talia_update")
        ok, zip_p, err = download_update_zip(
            self.download_url,
            dest_dir,
            progress_cb=self.progress.emit,
            cancel_check=lambda: self._cancelled,
        )
        self.download_finished.emit(ok, zip_p, err)
