@echo off
title V6 Dashboard

echo.
echo   ============================================
echo      AI Movie Studio V6 -- Dashboard Frontend
echo   ============================================
echo.

:: ========== Workdir ==========
cd /d "%~dp0frontend_v6"
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] Cannot enter frontend_v6 directory.
    pause
    exit /b 1
)
echo   [OK] Working Directory: %cd%
echo.

:: ========== Node.js ==========
echo   Checking Node.js...
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] Node.js not found. Please install Node.js 18+.
    echo          Download: https://nodejs.org/
    pause
    exit /b 1
)
for /f "delims=" %%V in ('node -v 2^>nul') do echo   [OK] Node.js: %%V

where npm >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] npm not found.
    pause
    exit /b 1
)
for /f "delims=" %%V in ('npm -v 2^>nul') do echo   [OK] npm: %%V
echo.

:: ========== Install Dependencies ==========
if not exist "node_modules\" (
    echo   [INFO] Installing dependencies...
    echo.
    call npm install
    if %ERRORLEVEL% neq 0 (
        echo.
        echo   [ERROR] npm install failed. Check network and package.json.
        pause
        exit /b 1
    )
    echo.
    echo   [OK] Dependencies installed.
) else (
    echo   [OK] node_modules exists, skipping install.
)
echo.

:: ========== Start Vite ==========
echo   ============================================
echo      Starting Vite Dev Server (port 5174)
echo   ============================================
echo.
echo   URL: http://localhost:5174
echo   Press Ctrl+C to stop
echo.

start "" http://localhost:5174 2>nul

call npm run dev

pause
