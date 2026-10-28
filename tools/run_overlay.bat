@echo off
cd /d "%~dp0\.."
title Talia Cyberpunk Audio Visualizer
python "src\main.py"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred.
    pause
)
