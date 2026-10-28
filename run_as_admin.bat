@echo off
cd /d "%~dp0"
title Talia Cyberpunk Audio Visualizer (Admin Launcher)

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process cmd -ArgumentList '/c cd /d \"%~dp0\" && python \"Python Code\mouth_overlay_app.py\"' -Verb RunAs"
    exit /b
)

python "Python Code\mouth_overlay_app.py"
