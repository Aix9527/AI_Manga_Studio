@echo off
cd /d "%~dp0"
title AI Manga Studio

echo.
echo ========================================
echo    AI Manga Studio - Launcher v0.8.0
echo ========================================
echo.

REM ========== Find Python ==========
echo [1/4] Checking Python...
python --version >nul 2>&1
if %errorlevel% equ 0 goto :python_ok

REM Try common Python installation locations
if exist "C:\Python313\python.exe" ( set "PATH=C:\Python313;C:\Python313\Scripts;%PATH%" & goto :python_ok )
if exist "C:\Python312\python.exe" ( set "PATH=C:\Python312;C:\Python312\Scripts;%PATH%" & goto :python_ok )
if exist "C:\Python311\python.exe" ( set "PATH=C:\Python311;C:\Python311\Scripts;%PATH%" & goto :python_ok )
if exist "C:\Python310\python.exe" ( set "PATH=C:\Python310;C:\Python310\Scripts;%PATH%" & goto :python_ok )
if exist "F:\Python313\python.exe" ( set "PATH=F:\Python313;F:\Python313\Scripts;%PATH%" & goto :python_ok )
if exist "F:\Python312\python.exe" ( set "PATH=F:\Python312;F:\Python312\Scripts;%PATH%" & goto :python_ok )
if exist "C:\Program Files\Python313\python.exe" ( set "PATH=C:\Program Files\Python313;C:\Program Files\Python313\Scripts;%PATH%" & goto :python_ok )
if exist "C:\Program Files\Python312\python.exe" ( set "PATH=C:\Program Files\Python312;C:\Program Files\Python312\Scripts;%PATH%" & goto :python_ok )
if exist "C:\Program Files\Python311\python.exe" ( set "PATH=C:\Program Files\Python311;C:\Program Files\Python311\Scripts;%PATH%" & goto :python_ok )
if exist "C:\Program Files\Python310\python.exe" ( set "PATH=C:\Program Files\Python310;C:\Program Files\Python310\Scripts;%PATH%" & goto :python_ok )

REM Try TRAE bundled Python
if exist "%APPDATA%\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\python.exe" ( set "PATH=%APPDATA%\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python;%APPDATA%\TRAE SOLO CN\ModularData\ai-agent\vm\tools\bin;%PATH%" & goto :python_ok )

echo.
echo [ERROR] Python not found!
echo   Tried: system PATH, C:\Python*, F:\Python*, Program Files
echo   Please install Python 3.10+ from https://www.python.org/
echo.
echo   Or run this script from within TRAE environment.
echo.
pause
exit /b 1

:python_ok
for /f "delims=" %%v in ('python --version 2^>^&1') do echo   OK - %%v

REM ========== Find Node.js ==========
echo [2/4] Checking Node.js...
node --version >nul 2>&1
if %errorlevel% equ 0 goto :node_ok

REM Try common Node.js locations
if exist "C:\Program Files\nodejs\node.exe" ( set "PATH=C:\Program Files\nodejs;%PATH%" & goto :node_ok )
if exist "C:\Program Files (x86)\nodejs\node.exe" ( set "PATH=C:\Program Files (x86)\nodejs;%PATH%" & goto :node_ok )
if exist "C:\nodejs\node.exe" ( set "PATH=C:\nodejs;%PATH%" & goto :node_ok )

REM Try TRAE bundled Node
if exist "%APPDATA%\TRAE SOLO CN\ModularData\ai-agent\vm\tools\node\node.exe" ( set "PATH=%APPDATA%\TRAE SOLO CN\ModularData\ai-agent\vm\tools\node;%PATH%" & goto :node_ok )

echo   [WARN] Node.js not found - frontend will not start
echo   Install from https://nodejs.org/
goto :node_skip

:node_ok
for /f "delims=" %%v in ('node --version 2^>^&1') do echo   OK - %%v

:node_skip

REM ========== Check Python dependencies ==========
echo [3/4] Checking Python dependencies...
python -c "import fastapi" >nul 2>&1
if %errorlevel% equ 0 goto :deps_ok

echo   Installing dependencies...
if not exist "requirements.txt" goto :no_reqs
pip install -r requirements.txt -q
if %errorlevel% neq 0 echo   [WARN] Some dependencies may have failed to install
goto :deps_ok

:no_reqs
echo   [WARN] requirements.txt not found

:deps_ok
echo   Dependencies checked

REM ========== Private local capability handoff ==========
REM The value is only inherited by the backend and local UI processes. It is
REM never echoed, put in browser storage, or requested over HTTP.
for /f "delims=" %%c in ('python -c "import secrets; print(secrets.token_urlsafe(32))"') do set "AI_MANGA_NOVEL_VIDEO_CAPABILITY=%%c"
for /f "delims=" %%s in ('python -c "import secrets; print(secrets.token_urlsafe(48))"') do set "AI_MANGA_NOVEL_PROXY_SECRET=%%s"

REM ========== Start services ==========
echo [4/4] Starting services...
echo.

REM --- ComfyUI (optional) ---
set COMFYUI_DIR=D:\ComfyUI
set COMFYUI_STARTED=0
if not exist "%COMFYUI_DIR%\main.py" goto :comfyui_skip
if not exist "%COMFYUI_DIR%\.venv\Scripts\python.exe" goto :comfyui_novenv

echo   Starting ComfyUI on port 8188...
start "ComfyUI" /D "%COMFYUI_DIR%" cmd /k .venv\Scripts\python.exe main.py --novram
set COMFYUI_STARTED=1
echo   Waiting for ComfyUI to initialize...
timeout /t 10 /nobreak >nul
goto :comfyui_done

:comfyui_novenv
echo   ComfyUI found but venv missing, skipping
goto :comfyui_done

:comfyui_skip
echo   ComfyUI not found at D:\ComfyUI - using placeholder mode

:comfyui_done

REM --- Backend ---
echo   Starting backend on port 8000...
start "Backend" /D "%~dp0" cmd /k python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
echo   Waiting for backend to start...
timeout /t 3 /nobreak >nul

REM --- Frontend ---
if exist "frontend\dist\index.html" goto :frontend_dist
if exist "frontend\package.json" goto :frontend_dev
goto :frontend_none

:frontend_dist
echo   Frontend: serving built dist from backend
set FRONTEND_URL=http://localhost:8000
goto :frontend_done

:frontend_dev
echo   Starting frontend dev server on port 5173...
pushd frontend
if not exist "node_modules" (
    echo   Installing frontend dependencies...
    call npm install --silent
)
popd
start "Frontend" /D "%~dp0frontend" cmd /k npm run dev -- --host 127.0.0.1
set FRONTEND_URL=http://localhost:5173
goto :frontend_done

:frontend_none
echo   [WARN] No frontend project found
set FRONTEND_URL=http://localhost:8000/docs

:frontend_done

echo.
echo ========================================
echo   Services started!
echo.
echo   Web UI:    %FRONTEND_URL%
echo   API Docs:  http://localhost:8000/docs
if "%COMFYUI_STARTED%"=="1" (
    echo   ComfyUI:    http://localhost:8188
) else (
    echo   ComfyUI:    not started
)
echo.
echo   Close THIS window to stop all services.
echo ========================================
echo.

REM Open browser
start "" "%FRONTEND_URL%"

echo Waiting for services... Press any key to stop.
pause >nul

echo.
echo Stopping services...
taskkill /FI "WINDOWTITLE eq ComfyUI" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Backend" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Frontend*" /T /F >nul 2>&1
del /q "storage\runtime\novel-video-capability" >nul 2>&1
echo All services stopped.
echo.
pause
