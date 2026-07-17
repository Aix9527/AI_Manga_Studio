@echo off
chcp 65001 >nul
title AI Manga Studio Pipeline

:: ============================================================
:: AI Manga Studio - Pipeline Runner
:: Usage: run.bat "novel.txt"
::        or drag-and-drop a .txt file onto run.bat
:: ============================================================

setlocal enabledelayedexpansion
set "NOVEL_PATH=%~1"

if "%NOVEL_PATH%"=="" (
    echo.
    echo   ╔════════════════════════════════════════════╗
    echo   ║  AI Manga Studio - Pipeline Runner         ║
    echo   ╠════════════════════════════════════════════╣
    echo   ║  Usage:                                    ║
    echo   ║    run.bat "novel.txt"                     ║
    echo   ║    or drag .txt file onto run.bat          ║
    echo   ║                                            ║
    echo   ║  For interactive menu, use: 一键启动.bat    ║
    echo   ╚════════════════════════════════════════════╝
    echo.
    pause
    exit /b 1
)

if not exist "!NOVEL_PATH!" (
    echo   [ERROR] File not found: !NOVEL_PATH!
    pause
    exit /b 1
)

echo.
echo   ══════════════════════════════════════════════
echo   Pipeline: %~nx1 -> AI Manga Video
echo   ══════════════════════════════════════════════
echo.

:: Check Python
where python >nul 2>&1
if !errorlevel! neq 0 (
    echo   [ERROR] Python not found!
    pause
    exit /b 1
)

:: Check ComfyUI
powershell -Command "try {$null=Invoke-RestMethod 'http://localhost:8188/system_stats' -TimeoutSec 3;exit 0}catch{exit 1}" >nul 2>&1
if !errorlevel! neq 0 (
    echo   [WARNING] ComfyUI not running on :8188
    echo   Image/video generation will fail.
    echo   Start ComfyUI first: python run.py --comfyui
    echo.
)

:: Run pipeline
python -u "%~dp0pipeline.py" "!NOVEL_PATH!" 2>&1

echo.
echo   ══════════════════════════════════════════════
echo   Done! Output in: output\
echo   ══════════════════════════════════════════════
pause
endlocal
