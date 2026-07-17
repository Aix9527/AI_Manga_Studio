@echo off
title V6 All Services Launcher

echo.
echo   ============================================
echo      AI Movie Studio V6 -- One-Click Launch
echo   ============================================
echo.

set "PROJECT_ROOT=%~dp0"
set "BACKEND_SCRIPT=%PROJECT_ROOT%start_backend.bat"
set "FRONTEND_SCRIPT=%PROJECT_ROOT%start_frontend.bat"

:: ========== Pre-checks ==========
echo   [INFO] Environment check...
echo.

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] Python not installed.
)
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] Node.js not installed.
)
where npm >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] npm not installed.
)

if not exist "%BACKEND_SCRIPT%" (
    echo   [ERROR] start_backend.bat not found
)
if not exist "%FRONTEND_SCRIPT%" (
    echo   [ERROR] start_frontend.bat not found
)
echo.

:: ========== Start Backend ==========
echo   ============================================
echo      Phase 1/2: Starting Backend (port 8001)
echo   ============================================
echo.
echo   Launching backend in new window...

start "V6 Pipeline Backend" "%BACKEND_SCRIPT%"

:: ========== Wait for Backend ==========
echo   Waiting for backend (max 90s)...
set /a "WAIT_COUNT=0"
:wait_backend
timeout /t 1 >nul 2>nul
set /a "WAIT_COUNT+=1"

:: Progress dot every 5 seconds
set /a "DOT=%WAIT_COUNT% %% 5"
if !DOT! equ 0 echo   .

powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8001/docs' -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue; if ($r.StatusCode -eq 200) { exit 0 } } catch { exit 1 }" >nul 2>nul
if %ERRORLEVEL% equ 0 goto backend_ready

if %WAIT_COUNT% lss 90 goto wait_backend

echo   [WARN] Backend not ready within 90s. Continuing...
echo          The backend window may be installing dependencies.
goto start_frontend

:backend_ready
echo   [OK] Backend ready (http://localhost:8001/docs)
echo.

:: ========== Start Frontend ==========
:start_frontend
echo   ============================================
echo      Phase 2/2: Starting Frontend (port 5174)
echo   ============================================
echo.

start "V6 Dashboard" "%FRONTEND_SCRIPT%"

echo   Waiting for frontend (max 60s)...
set /a "WAIT_COUNT=0"
:wait_frontend
timeout /t 1 >nul 2>nul
set /a "WAIT_COUNT+=1"

set /a "DOT=%WAIT_COUNT% %% 5"
if !DOT! equ 0 echo   .

powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:5174' -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue; if ($r.StatusCode -eq 200) { exit 0 } } catch { exit 1 }" >nul 2>nul
if %ERRORLEVEL% equ 0 goto frontend_ready

if %WAIT_COUNT% lss 60 goto wait_frontend

echo   [WARN] Frontend not ready within 60s. It may be installing npm packages.
goto show_panel

:frontend_ready
echo   [OK] Frontend ready (http://localhost:5174)
echo.

:: ========== Status Panel ==========
:show_panel
echo.
echo   ============================================
echo              Service Status Panel
echo   ============================================
echo.
echo   Service                 Port   Status
echo   ----------------------------------------

powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8001/docs' -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue; if ($r.StatusCode -eq 200) { Write-Host '  Backend Pipeline       8001   READY   http://localhost:8001/docs' } else { Write-Host '  Backend Pipeline       8001   OFFLINE' } } catch { Write-Host '  Backend Pipeline       8001   OFFLINE' }"
if %ERRORLEVEL% neq 0 echo   Backend Pipeline       8001   OFFLINE

powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:5174' -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue; if ($r.StatusCode -eq 200) { Write-Host '  Frontend Dashboard     5174   READY   http://localhost:5174' } else { Write-Host '  Frontend Dashboard     5174   OFFLINE' } } catch { Write-Host '  Frontend Dashboard     5174   OFFLINE' }"
if %ERRORLEVEL% neq 0 echo   Frontend Dashboard     5174   OFFLINE

echo.
echo   [INFO] Press any key to close this launcher.
echo          Service windows will keep running.
echo.
pause
