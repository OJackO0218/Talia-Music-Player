@echo off
setlocal
title Talia Music Player & Cyberpunk Visualizer Installer
echo ========================================================
echo    TALIA MUSIC PLAYER - 1-CLICK EASY INSTALLER
echo ========================================================
echo.

:: 1. Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python was not found on your system!
    echo     Please install Python 3.10+ from https://www.python.org/downloads/
    echo     Make sure to check "Add python.exe to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo [*] Python detected:
python --version
echo.

:: 2. Upgrade pip and install dependencies
echo [*] Installing required Python libraries...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [!] Standard install encountered an issue, retrying with --user...
    python -m pip install -r requirements.txt --user
)

:: 3. Run setup to build native launcher and desktop shortcuts
echo.
echo [*] Setting up Talia Desktop App, custom app icon, and native launcher...
python setup_windows_app.py

echo.
echo ========================================================
echo    INSTALLATION COMPLETE!
echo.
echo    You can now launch Talia anytime via:
echo    - Desktop shortcut: "Talia Visualizer"
echo    - Windows Start Menu: Search for "Talia"
echo    - Direct file: Double-click "Talia.exe" or "run_overlay.bat"
echo ========================================================
echo.
pause
