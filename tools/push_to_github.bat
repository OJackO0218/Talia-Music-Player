@echo off
setlocal
title Push Talia Music Player to GitHub
echo ========================================================
echo    PUSHING TALIA MUSIC PLAYER TO GITHUB
echo ========================================================
echo.
cd /d "%~dp0\.."
echo [*] Pushing to https://github.com/OJackO0218/Talia-Music-Player.git...
echo [*] (If a browser window appears, click 'Sign in with your browser' to authorize Git)
echo.
git push -u origin main
if %ERRORLEVEL% equ 0 (
    echo.
    echo ========================================================
    echo    [+] SUCCESS! Repository pushed to GitHub!
    echo    https://github.com/OJackO0218/Talia-Music-Player
    echo ========================================================
) else (
    echo.
    echo [!] Push could not be completed.
)
echo.
pause
