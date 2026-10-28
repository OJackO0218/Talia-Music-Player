@echo off
cd /d "%~dp0"
title Talia Cyberpunk Audio Visualizer
python "Python Code\mouth_overlay_app.py"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred.
    pause
)
