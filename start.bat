@echo off
chcp 65001 >nul
title AI Manga Studio V4 - 一键启动

echo ============================================
echo   AI Manga Studio V4 - 启动中...
echo ============================================
echo.

:: 1. 检测并启动 ComfyUI
echo [1/3] 检测 ComfyUI...
netstat -an | findstr ":8188" >nul
if %errorlevel% equ 0 (
    echo   ComfyUI 已在运行 (端口 8188)
) else (
    echo   正在启动 ComfyUI...
    start "ComfyUI" cmd /c "cd /d D:\ComfyUI_new && D:\ComfyUI_new\venv\Scripts\python.exe main.py --listen 0.0.0.0"
    echo   等待 ComfyUI 就绪（15秒）...
    timeout /t 15 /nobreak >nul
)

:: 2. 启动 FastAPI 后端
echo [2/3] 启动 FastAPI 后端 (端口 8000)...
start "Backend V4" /D "%~dp0backend_v4" cmd /k "uvicorn main:app --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul

:: 3. 启动 Vue3 前端（优先 V4，失败降级 V3.5）
echo [3/3] 启动前端...
where npm >nul 2>&1
if %errorlevel% equ 0 (
    echo   启动 V4 前端 (端口 5173)...
    start "Frontend V4" /D "%~dp0frontend_v4" cmd /k "npm run dev"
    timeout /t 4 /nobreak >nul
    set "FRONTEND_URL=http://localhost:5173"
    set "FRONTEND_LABEL=V4 界面"
) else (
    echo   npm 不可用，降级为 V3.5 界面
    set "FRONTEND_URL=http://localhost:5173"
    set "FRONTEND_LABEL=V3.5 console.html"
)

:: 4. 打开浏览器
echo.
echo 正在打开浏览器 %FRONTEND_URL% (%FRONTEND_LABEL%) ...
start %FRONTEND_URL%

echo.
echo ============================================
echo   所有服务已启动！
echo   前端 (%FRONTEND_LABEL%):  %FRONTEND_URL%
echo   后端:  http://localhost:8000
echo   API文档: http://localhost:8000/docs
echo   ComfyUI: http://localhost:8188
echo ============================================
echo.
echo 按任意键关闭此窗口（不会停止各服务）...
pause >nul
