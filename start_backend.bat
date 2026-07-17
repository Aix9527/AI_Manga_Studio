@echo off
setlocal enabledelayedexpansion
title V6 Pipeline Backend

echo.
echo   ============================================
echo      AI Movie Studio V6 -- Pipeline Backend
echo   ============================================
echo.

:: ========== Workdir ==========
cd /d "%~dp0backend_v6"
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] Cannot enter backend_v6 directory.
    pause
    exit /b 1
)
echo   [OK] Working Directory: %cd%
echo.

:: ========== Python ==========
echo   Checking Python...
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] Python not found. Please install Python 3.10+.
    echo          Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "delims=" %%V in ('python --version 2^>^&1') do echo   [OK] Python: %%V
echo.

:: ========== Virtual Env ==========
if not exist "venv\" (
    echo   [INFO] Creating virtual environment...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo   [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
    echo   [OK] Virtual environment created.
)

call venv\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] Failed to activate venv.
    pause
    exit /b 1
)
echo   [OK] Venv activated: %VIRTUAL_ENV%
echo.

:: ========== Dependencies ==========
echo   Checking dependencies...
if not exist "requirements.txt" (
    echo   [WARN] requirements.txt missing, generating...
    (
        echo fastapi^>=0.104.0
        echo uvicorn[standard]^>=0.24.0
        echo pydantic^>=2.0.0
        echo aiohttp^>=3.9.0
        echo openai^>=1.0.0
        echo pillow^>=10.0.0
        echo sqlalchemy^>=2.0.0
        echo pydantic-settings^>=2.0.0
    ) > requirements.txt
    echo   [OK] requirements.txt generated.
)

echo   Installing / updating packages...
pip install -r requirements.txt -q
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] pip install failed. Check network or requirements.txt.
    pause
    exit /b 1
)
echo   [OK] Dependencies ready.
echo.

:: ========== Verify main.py ==========
echo   Verifying main.py...
python -c "from main import app; print('OK')" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] main.py import failed.
    echo          Debug: cd /d "%~dp0backend_v6" ^&^& python -c "from main import app"
    pause
    exit /b 1
)
echo   [OK] main.py import OK.
echo.

:: ========== Ollama ==========
echo   Checking Ollama (port 11434)...
curl -s --connect-timeout 3 http://localhost:11434/api/tags >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo   [OK] Ollama running (http://localhost:11434)
) else (
    powershell -Command "try { $r = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 3; exit 0 } catch { exit 1 }" >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        echo   [OK] Ollama running (http://localhost:11434)
    ) else (
        echo   [WARN] Ollama not available (port 11434 no response)
        echo          LLM Agent will run in fallback mode.
        echo          Start Ollama manually: ollama serve
    )
)
echo.

:: ========== ComfyUI ==========
echo   Checking ComfyUI (port 8188)...
curl -s --connect-timeout 3 http://localhost:8188/system_stats >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo   [OK] ComfyUI running (http://localhost:8188)
) else (
    powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8188/system_stats' -TimeoutSec 3 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        echo   [OK] ComfyUI running (http://localhost:8188)
    ) else (
        echo   [INFO] ComfyUI not available (port 8188 no response)
        echo           Image/video generation will use fallback mode.
    )
)
echo.

:: ========== Start uvicorn ==========
echo   ============================================
echo      Starting FastAPI Backend (port 8001)
echo   ============================================
echo.
echo   API Docs: http://localhost:8001/docs
echo   ReDoc:    http://localhost:8001/redoc
echo.
echo   Press Ctrl+C to stop
echo.

uvicorn main:app --host 0.0.0.0 --port 8001 --reload

pause
