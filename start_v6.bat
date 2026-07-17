@echo off
chcp 65001 >nul
title AI Movie Studio V6 Enterprise
echo ============================================
echo   AI Movie Studio V6 Enterprise Launcher
echo ============================================
echo.

cd /d "%~dp0"

:: 1. ComfyUI
set COMFY_DIR=D:\ComfyUI_new
if exist "%COMFY_DIR%" (
    echo [1/3] ComfyUI 节点检测到，启动中...
    start "ComfyUI" cmd /c "cd /d %COMFY_DIR% && python main.py --port 8188"
) else (
    echo [1/3] ComfyUI 未找到 (D:\ComfyUI_new)，跳过。
)

:: 2. Backend
echo [2/3] 启动后端 backend_v6...
start "Backend V6" cmd /c "cd /d backend_v6 && python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload"

:: 3. Frontend
echo [3/3] 启动前端 frontend_v6...
start "Frontend V6" cmd /c "cd /d frontend_v6 && npm run dev"

:: 等待后端就绪
echo 等待后端就绪...
timeout /t 8 /nobreak >nul

:: 打开浏览器
start http://localhost:5174

echo.
echo ============================================
echo   全部服务已启动:
echo   - Backend:  http://localhost:8001
echo   - Frontend: http://localhost:5174
echo   - API Docs: http://localhost:8001/docs
echo ============================================
pause
