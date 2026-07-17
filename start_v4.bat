@echo off
chcp 65001 >nul
title AI Manga Studio V4 - 瀵兼紨绾х绾?echo ============================================
echo   AI Manga Studio V4 - 瀵兼紨绾х绾垮惎鍔ㄥ櫒
echo ============================================
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.10+ first.
    pause
    exit /b 1
)

echo [OK] Python found
python --version
echo.

:: Check ComfyUI
echo [1/2] Checking ComfyUI...
powershell -Command "try {$r=Invoke-RestMethod 'http://localhost:8188/system_stats' -TimeoutSec 2;exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] ComfyUI running on :8188
) else (
    echo   [WARN] ComfyUI not running
    echo   Image/video generation requires ComfyUI.
    echo.
    set /p "START_CUI=  Start ComfyUI now? [Y/n]: "
    if /i not "!START_CUI!"=="n" (
        if exist "D:\\ComfyUI\main.py" (
            echo   Starting ComfyUI...
            start "ComfyUI" cmd /c "cd /d D:\\ComfyUI && D:\\ComfyUI\venv\Scripts\python.exe main.py --listen 127.0.0.1"
            echo   Waiting for ComfyUI to be ready (max 30s)...
            set /a WAIT=0
            :wait_cui
            timeout /t 2 /nobreak >nul
            set /a WAIT+=2
            powershell -Command "try {$r=Invoke-RestMethod 'http://localhost:8188/system_stats' -TimeoutSec 2;exit 0}catch{exit 1}" >nul 2>&1
            if %errorlevel% equ 0 goto :cui_ready
            if !WAIT! lss 30 goto :wait_cui
            :cui_ready
            echo   [OK] ComfyUI ready
        ) else (
            echo   [SKIP] D:\\ComfyUI not found. Skipping.
        )
    )
)

echo.
echo [2/2] Checking backend modules...
python -c "
import sys; sys.path.insert(0, '.')
from backend.cinema_video_prompt_builder import CinemaVideoPromptBuilder
from backend.enhanced_image_prompt_builder import EnhancedImagePromptBuilder
from backend.shot_table_generator import ShotTableGenerator
from backend.vfx_generator import VFXGenerator
from backend.i2v_generator import I2VGenerator
from backend.orchestrator_v4 import OrchestratorV4
print('  [OK] All V4 modules loaded')
" 2>nul
if %errorlevel% neq 0 (
    echo   [FAIL] Some V4 modules failed to load
    echo   Run: pip install -r requirements.txt
    echo   Then try again.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   V4 瀵兼紨绾х绾?灏辩华!
echo ============================================
echo.
echo   浣跨敤鏂瑰紡:
echo   1. 鍛戒护琛? python scripts\run_v4_pipeline.py novel.txt
echo   2. Web鐣岄潰: 鍚姩 backend_v11 鍚庣 + 鍓嶇
echo   3. 娴嬭瘯:   python scripts\test_v4_full.py
echo.
echo   鏈嶅姟鍦板潃:
echo     ComfyUI:  http://localhost:8188
echo     API鏂囨。:  http://localhost:8800/docs (backend_v11)
echo ============================================
echo.
pause
