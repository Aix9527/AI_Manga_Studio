@echo off
chcp 65001 >nul
title AI Manga Studio - 一键启动

:: ============================================================
:: AI Manga Studio - One-Click Launcher
:: Usage: Double-click this file, or drag a .txt novel onto it
:: ============================================================

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

:: ============================================================
:: Parse drag-and-drop or argument
:: ============================================================
set "NOVEL_PATH=%~1"

:: ============================================================
:: Welcome screen
:: ============================================================
echo.
echo   ╔══════════════════════════════════════════════════════╗
echo   ║      AI Manga Studio Pro - 一键启动                   ║
echo   ║      小说 -> AI漫剧，全自动！                         ║
echo   ╚══════════════════════════════════════════════════════╝
echo.

:: If novel was passed (drag-and-drop), go directly to pipeline
if not "%NOVEL_PATH%"=="" (
    if exist "%NOVEL_PATH%" (
        echo   检测到小说: %~nx1
        echo.
        goto :run_pipeline
    )
)

:: ============================================================
:: Menu
:: ============================================================
:menu
echo   ╔══════════════════════════════════════╗
echo   ║       请选择模式:                     ║
echo   ╠══════════════════════════════════════╣
echo   ║  [1] 小说 -> AI漫剧 (一键生成)        ║
echo   ║  [2] 启动Web服务 (后台+前端)          ║
echo   ║  [3] 全部启动 (Web + 流水线)          ║
echo   ║  [4] 仅启动 ComfyUI                   ║
echo   ║  [5] 环境检查                          ║
echo   ║  [q] 退出                              ║
echo   ╚══════════════════════════════════════╝
echo.
set /p "CHOICE=  请选择 [1-5/q]: "

if "%CHOICE%"=="q" goto :end
if "%CHOICE%"=="Q" goto :end
if "%CHOICE%"=="1" goto :select_novel
if "%CHOICE%"=="2" goto :web_services
if "%CHOICE%"=="3" goto :select_novel_all
if "%CHOICE%"=="4" goto :start_comfyui
if "%CHOICE%"=="5" goto :env_check
goto :menu

:: ============================================================
:: Novel selection
:: ============================================================
:select_novel
echo.
echo   --- 选择小说 ---
echo.

:: Check novels/ directory
set "NOVEL_INDEX=0"
if exist "novels\*.txt" (
    for %%f in (novels\*.txt) do (
        set /a NOVEL_INDEX+=1
        echo   [!NOVEL_INDEX!] %%~nxf
        set "NOVEL_!NOVEL_INDEX!=%%f"
    )
)

:: Check root level novels
for %%f in (novel*.txt) do (
    if exist "%%f" (
        set /a NOVEL_INDEX+=1
        echo   [!NOVEL_INDEX!] %%~nxf
        set "NOVEL_!NOVEL_INDEX!=%%~dp0%%f"
    )
)

if !NOVEL_INDEX!==0 (
    echo   没有找到小说文件。
    set /p "NOVEL_PATH=  请输入小说路径: "
    if "!NOVEL_PATH!"=="" goto :menu
) else (
    echo.
    set /p "NOVEL_SEL=  选择编号 (或输入路径): "
    if "!NOVEL_SEL!"=="" goto :menu
    echo !NOVEL_SEL! | findstr /r "^[0-9]*$" >nul
    if !errorlevel!==0 (
        if !NOVEL_SEL! gtr 0 if !NOVEL_SEL! leq !NOVEL_INDEX! (
            call set "NOVEL_PATH=%%NOVEL_!NOVEL_SEL!%%"
        )
    ) else (
        set "NOVEL_PATH=!NOVEL_SEL!"
    )
)

if not exist "!NOVEL_PATH!" (
    echo   文件不存在: !NOVEL_PATH!
    pause
    goto :menu
)

goto :run_pipeline

:select_novel_all
echo.
set "NOVEL_SEL="
set "NOVEL_INDEX=0"
if exist "novels\*.txt" (
    for %%f in (novels\*.txt) do (
        set /a NOVEL_INDEX+=1
        echo   [!NOVEL_INDEX!] %%~nxf
        set "NOVEL_!NOVEL_INDEX!=%%f"
    )
)
for %%f in (novel*.txt) do (
    if exist "%%f" (
        set /a NOVEL_INDEX+=1
        echo   [!NOVEL_INDEX!] %%~nxf
        set "NOVEL_!NOVEL_INDEX!=%%~dp0%%f"
    )
)
if !NOVEL_INDEX!==0 (
    set /p "NOVEL_PATH=  请输入小说路径: "
) else (
    set /p "NOVEL_SEL=  选择编号 (或输入路径): "
    if not "!NOVEL_SEL!"=="" (
        echo !NOVEL_SEL! | findstr /r "^[0-9]*$" >nul
        if !errorlevel!==0 (
            if !NOVEL_SEL! gtr 0 if !NOVEL_SEL! leq !NOVEL_INDEX! (
                call set "NOVEL_PATH=%%NOVEL_!NOVEL_SEL!%%"
            )
        ) else (
            set "NOVEL_PATH=!NOVEL_SEL!"
        )
    )
)
if "!NOVEL_PATH!"=="" goto :menu
if not exist "!NOVEL_PATH!" (
    echo   文件不存在: !NOVEL_PATH!
    pause
    goto :menu
)

:: First start web, then pipeline
call :start_comfyui_check
call :start_backend_check
call :start_frontend_check
call :wait_services
goto :run_pipeline

:: ============================================================
:: Run Pipeline
:: ============================================================
:run_pipeline
echo.
echo   ══════════════════════════════════════════════
echo   Pipeline: !NOVEL_PATH! -> AI漫剧
echo   ══════════════════════════════════════════════
echo.

:: Check ComfyUI
powershell -Command "try {$null=Invoke-RestMethod 'http://localhost:8188/system_stats' -TimeoutSec 3;exit 0}catch{exit 1}" >nul 2>&1
if !errorlevel! neq 0 (
    echo   [WARNING] ComfyUI not running on :8188
    echo   图片/视频生成将无法工作。
    echo.
    set /p "START_CUI=  是否启动ComfyUI? [Y/n]: "
    if /i not "!START_CUI!"=="n" (
        call :start_comfyui_check
        echo   等待ComfyUI就绪... (最多90秒)
        set /a WAIT=0
        :wait_cui
        timeout /t 1 >nul
        set /a WAIT+=1
        powershell -Command "try {$null=Invoke-RestMethod 'http://localhost:8188/system_stats' -TimeoutSec 3;exit 0}catch{exit 1}" >nul 2>&1
        if !errorlevel!==0 goto :cui_ready
        if !WAIT! lss 90 goto :wait_cui
        :cui_ready
    )
)

:: Check backend
powershell -Command "try {$null=Invoke-RestMethod 'http://localhost:8800/health' -TimeoutSec 3;exit 0}catch{exit 1}" >nul 2>&1
if !errorlevel! neq 0 (
    echo   [INFO] Backend not running. Pipeline will use direct mode.
)

echo.
echo   Launching pipeline...
python -u "%~dp0pipeline.py" "!NOVEL_PATH!" 2>&1

echo.
echo   ══════════════════════════════════════════════
echo   Pipeline 完成!
echo   输出目录: output\
echo   ══════════════════════════════════════════════
pause
goto :end

:: ============================================================
:: Web Services
:: ============================================================
:web_services
echo.
echo   Starting Web Services...
call :start_comfyui_check
call :start_backend_check
call :start_frontend_check
call :wait_services

echo.
echo   ══════════════════════════════════════════════
echo   All Services Running!
echo   前端:   http://localhost:3000
echo   后端:   http://localhost:8800
echo   API文档: http://localhost:8800/docs
echo   ══════════════════════════════════════════════
echo.
echo   按任意键关闭此窗口 (服务将继续运行)
pause >nul
goto :end

:: ============================================================
:: ComfyUI
:: ============================================================
:start_comfyui
echo.
echo   Starting ComfyUI...
call :start_comfyui_check
echo   ComfyUI started. 按任意键退出此窗口。
pause >nul
goto :end

:start_comfyui_check
powershell -Command "try {$null=Invoke-RestMethod 'http://localhost:8188/system_stats' -TimeoutSec 3;exit 0}catch{exit 1}" >nul 2>&1
if !errorlevel!==0 (
    echo   [OK] ComfyUI already running
    goto :eof
)
if exist "comfyui\main.py" (
    echo   [START] ComfyUI on :8188
    start "ComfyUI" cmd /c "cd /d %PROJECT_ROOT%comfyui && python main.py --listen 127.0.0.1 --port 8188"
) else (
    echo   [SKIP] ComfyUI not installed
)
goto :eof

:: ============================================================
:: Backend
:: ============================================================
:start_backend_check
powershell -Command "try {$null=Invoke-RestMethod 'http://localhost:8800/health' -TimeoutSec 3;exit 0}catch{exit 1}" >nul 2>&1
if !errorlevel!==0 (
    echo   [OK] Backend already running
    goto :eof
)
echo   [START] Backend on :8800
start "Backend V1" cmd /c "cd /d %PROJECT_ROOT% && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8800 --log-level info"
goto :eof

:: ============================================================
:: Frontend
:: ============================================================
:start_frontend_check
powershell -Command "try {$null=Invoke-RestMethod 'http://localhost:3000' -TimeoutSec 3;exit 0}catch{exit 1}" >nul 2>&1
if !errorlevel!==0 (
    echo   [OK] Frontend already running
    goto :eof
)

where npm >nul 2>&1
if !errorlevel! neq 0 (
    echo   [SKIP] npm not found (frontend won't start)
    goto :eof
)

if not exist "frontend\node_modules" (
    echo   [INSTALL] npm dependencies...
    cd frontend
    call npm install
    cd ..
)

echo   [START] Frontend on :3000
start "Frontend" cmd /c "cd /d %PROJECT_ROOT%frontend && npm start"
goto :eof

:: ============================================================
:: Wait for services
:: ============================================================
:wait_services
echo.
echo   Waiting for services to be ready...
set /a WAIT_COUNT=0
:wait_loop
timeout /t 1 >nul
set /a WAIT_COUNT+=1

set /a DOT=WAIT_COUNT %% 5
if !DOT!==0 echo   .

powershell -Command "try {$r=Invoke-WebRequest 'http://localhost:8800/health' -TimeoutSec 3 -UseBasicParsing -ErrorAction SilentlyContinue;if($r.StatusCode -eq 200){exit 0}}catch{exit 1}" >nul 2>&1
if !errorlevel!==0 (
    echo   [OK] Backend ready
    goto :wait_frontend
)
if !WAIT_COUNT! lss 30 goto :wait_loop

:wait_frontend
powershell -Command "try {$r=Invoke-WebRequest 'http://localhost:3000' -TimeoutSec 3 -UseBasicParsing -ErrorAction SilentlyContinue;if($r.StatusCode -eq 200){exit 0}}catch{exit 1}" >nul 2>&1
if !errorlevel!==0 (
    echo   [OK] Frontend ready
    goto :eof
)
if !WAIT_COUNT! lss 60 (
    timeout /t 1 >nul
    set /a WAIT_COUNT+=1
    goto :wait_frontend
)
echo   [WARN] Frontend not ready (may still be building)
goto :eof

:: ============================================================
:: Environment Check
:: ============================================================
:env_check
echo.
echo   --- Environment Check ---

where python >nul 2>&1
if !errorlevel!==0 (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo   [OK] %%i
) else (
    echo   [FAIL] Python not found
)

where node >nul 2>&1
if !errorlevel!==0 (
    for /f "tokens=*" %%i in ('node --version 2^>^&1') do echo   [OK] Node.js %%i
) else (
    echo   [WARN] Node.js not found
)

where npm >nul 2>&1
if !errorlevel!==0 (
    for /f "tokens=*" %%i in ('npm --version 2^>^&1') do echo   [OK] npm %%i
) else (
    echo   [WARN] npm not found
)

if exist "comfyui\main.py" (
    echo   [OK] ComfyUI installed
) else (
    echo   [WARN] ComfyUI not installed
)

if exist "backend\main.py" (
    echo   [OK] Backend code found
) else (
    echo   [FAIL] Backend code missing
)

if exist "frontend\package.json" (
    echo   [OK] Frontend code found
) else (
    echo   [WARN] Frontend code missing
)

echo.
pause
goto :menu

:: ============================================================
:: End
:: ============================================================
:end
endlocal
