@echo off
cd /d D:\AI_Manga_Studio
title AI_Manga_Studio_V7

set PYTHON=F:\Python312\python.exe
if not exist "%PYTHON%" set PYTHON=D:\AI_Manga_Studio\backend_v6\venv\Scripts\python.exe
if not exist "%PYTHON%" (
    echo Python not found.
    pause
    exit /b 1
)

echo ================================================
echo   AI Manga Studio V7
echo ================================================

set NOVEL=%1
if "%NOVEL%"=="" (
    for /f "delims=" %%f in ('dir /b /od novels\*.txt 2^>nul') do set NOVEL=novels\%%f
    if "%NOVEL%"=="" (
        echo No .txt files in novels\ folder.
        echo Drag a .txt file onto run_v7.bat.
        pause
        exit /b 1
    )
    echo Auto: %NOVEL%
)

echo.
echo [*] Checking backend...
powershell -Command "try {$r=Invoke-RestMethod 'http://localhost:8001/health' -TimeoutSec 2 -ErrorAction Stop;exit 0}catch{exit 1}" >nul 2>&1
if errorlevel 1 (
    echo [*] Starting backend...
    start "BackendV6" /MIN cmd /c "cd /d D:\AI_Manga_Studio\backend_v6 && %PYTHON% -m uvicorn main:app --host 0.0.0.0 --port 8001"
    timeout /t 6 /nobreak >nul
)

echo [*] Running pipeline...
echo.
%PYTHON% D:\AI_Manga_Studio\pipeline_v7.py "%NOVEL%" --style "er ci yuan" --engine "ltx_2.3"

echo.
echo ================================================
echo   Done.
echo ================================================
pause
