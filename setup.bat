@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo  AI Manga Studio v0.8 - Setup
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+
    echo         https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python found

echo.
echo [1/4] Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1
if errorlevel 1 (
    echo [WARN] pip upgrade failed; continuing with the installed pip version
) else (
    echo [OK] pip is up to date
)

echo.
echo [2/4] Installing Python dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 goto :setup_failed
echo [OK] Python dependencies installed

echo.
echo [3/4] Installing frontend dependencies...
if not exist "frontend\package.json" (
    echo [ERROR] frontend\package.json not found
    goto :setup_failed
)
pushd frontend
npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js/npm not found. Install Node.js 20+
    popd
    goto :setup_failed
)
if exist "package-lock.json" (
    call npm ci
) else (
    echo [WARN] package-lock.json not found; falling back to npm install
    call npm install
)
if errorlevel 1 (
    echo [ERROR] Frontend dependency installation failed
    popd
    goto :setup_failed
)
echo [OK] Frontend dependencies installed

echo.
echo [4/4] Building frontend...
call npm run build
if errorlevel 1 (
    echo [ERROR] Frontend build failed
    popd
    goto :setup_failed
)
popd
echo [OK] Frontend built

echo.
echo ========================================
echo  Setup complete!
echo.
echo  Usage:
echo    run.bat
echo      Start local Web UI
echo.
echo    python -m backend.cli diagnose
echo      Check the local runtime environment
echo.
echo    python -m backend.cli generate -i novel.txt -o output.mp4
echo      Run the legacy CLI generation path
echo.
echo    python tools\h3_unified_live_gate.py
echo      Preflight RTX / ComfyUI / H3 Unified without submitting generation
echo ========================================

pause
exit /b 0

:setup_failed
echo.
echo ========================================
echo  [ERROR] Setup failed.
echo  Fix the error above, then run setup.bat again.
echo ========================================
pause
exit /b 1
