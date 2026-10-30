@echo off
title Talia - Automated Lyrics Fetcher
cd /d "%~dp0"
python gui_fetcher.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [!] An error occurred running the GUI.
    pause
)
