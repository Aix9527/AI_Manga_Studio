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
echo [1/5] Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1
echo [OK] pip is up to date

echo.
echo [2/5] Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [WARN] Some dependencies failed to install
) else (
    echo [OK] Python dependencies installed
)

echo.
echo [3/5] Installing optional dependencies...
pip install edge-tts Pillow >nul 2>&1
echo [OK] Optional dependencies done

echo.
echo [4/5] Installing frontend dependencies...
if exist "frontend\package.json" (
    pushd frontend
    call npm install --silent 2>nul
    if errorlevel 1 (
        echo [WARN] npm install failed. Is Node.js installed?
    ) else (
        echo [OK] Frontend dependencies installed
    )
    popd
) else (
    echo [SKIP] No frontend directory found
)

echo.
echo [5/5] Building frontend...
if exist "frontend\package.json" (
    pushd frontend
    call npm run build 2>nul
    if errorlevel 1 (
        echo [WARN] Build failed. Use "npm run dev" for dev mode.
    ) else (
        echo [OK] Frontend built
    )
    popd
) else (
    echo [SKIP] No frontend directory found
)

echo.
echo ========================================
echo  Setup complete!
echo.
echo  Usage:
echo    run.bat                        Start web UI
echo    run.bat generate -i novel.txt  Generate video
echo    run.bat diagnose               Check environment
echo ========================================

pause
exit /b 0