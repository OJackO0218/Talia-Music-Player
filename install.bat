@echo off
setlocal EnableDelayedExpansion
title Talia Music Player & Cyberpunk Visualizer Installer
echo ========================================================
echo    TALIA MUSIC PLAYER - 1-CLICK EASY INSTALLER
echo ========================================================
echo.

:: 1. Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python was not found on your system.
    echo [*] Automatically installing official Python 3.11 for you (1-click setup)...
    echo.
    
    winget --version >nul 2>&1
    if not errorlevel 1 (
        echo [*] Installing Python via Windows Package Manager (winget)...
        winget install --id Python.Python.3.11 -e --silent --accept-package-agreements --accept-source-agreements
    ) else (
        echo [*] Downloading official Python 3.11 installer...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe', '$env:TEMP\python_installer.exe')"
        echo [*] Installing Python silently...
        "%TEMP%\python_installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
        del "%TEMP%\python_installer.exe" >nul 2>&1
    )
    
    :: Refresh PATH for current command prompt
    for /f "tokens=*" %%a in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')"') do set "PATH=%%a"
    
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [!] Please restart your computer or command prompt to finish Python setup.
        pause
        exit /b 1
    )
)

echo [*] Python detected:
python --version
echo.

:: 2. Upgrade pip and install dependencies
echo [*] Installing required audio and graphics libraries...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [!] Retrying dependency install with --user...
    python -m pip install -r requirements.txt --user --quiet
)

:: 3. Run setup to build native launcher and desktop shortcuts
echo.
echo [*] Setting up Talia Desktop App, custom app icon, and native launcher...
python tools\setup_windows_app.py

echo.
echo ========================================================
echo    INSTALLATION COMPLETE!
echo.
echo    You can now launch Talia anytime via:
echo    - Desktop shortcut: "Talia Visualizer"
echo    - Windows Start Menu: Search for "Talia"
echo    - Direct file: Double-click "Talia.exe"
echo ========================================================
echo.

:: 4. Ask to launch now
set /p LAUNCH="Would you like to launch Talia now? (Y/n): "
if /i not "%LAUNCH%"=="n" (
    start "" "Talia.exe"
)
