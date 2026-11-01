@echo off
setlocal
title Talia Test Suite
cd /d "%~dp0"

echo ========================================================
echo    TALIA - LINT, FORMAT CHECK, AND TEST SUITE
echo ========================================================
echo.

python -m pip show pytest >nul 2>&1
if errorlevel 1 (
    echo [*] Installing development dependencies...
    python -m pip install -r requirements-dev.txt --quiet
)

set "QT_QPA_PLATFORM=offscreen"
set "PYTHONPATH=%CD%\src;%CD%\Talia Lyrics Fetch Automated"

echo [1/3] Ruff...
python -m ruff check src tests tools
if errorlevel 1 goto :failed
echo.

echo [2/3] Black format check...
python -m black --check src tests tools
if errorlevel 1 (
    echo [i] Run "python -m black src tests tools" to format the code.
    goto :failed
)
echo.

echo [3/3] Pytest...
python -m pytest tests -q
if errorlevel 1 goto :failed

echo.
echo ========================================================
echo    ALL CHECKS PASSED
echo ========================================================
pause
exit /b 0

:failed
echo.
echo ========================================================
echo    CHECKS FAILED - see output above
echo ========================================================
pause
exit /b 1
