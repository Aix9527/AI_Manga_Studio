@echo off
setlocal
cd /d "%~dp0"
title AI Manga Studio - H3 Unified Verification

set "EVIDENCE=storage\live\h3_unified_live_gate.json"

echo ========================================
echo  AI Manga Studio - H3 Unified Verify
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    goto :verify_failed
)

if /I "%~1"=="help" goto :usage
if /I not "%~1"=="" if /I not "%~1"=="preflight" (
    echo [ERROR] Unknown mode: %~1
    goto :usage_failed
)

echo [Gate A] Preflight GPU / FFmpeg / ComfyUI / Unified nodes...
python tools\h3_unified_live_gate.py --evidence "%EVIDENCE%"
if errorlevel 1 goto :verify_failed

echo [OK] Gate A passed.
echo      Evidence: %EVIDENCE%
echo.

if /I "%~1"=="preflight" goto :verify_passed

echo [Gate B] Running 5s T2VA smoke generation...
python tools\h3_unified_live_gate.py --submit --mode T2VA --duration 5 --resolution 480p --aspect-ratio 9:16 --steps 12 --evidence "%EVIDENCE%"
if errorlevel 1 goto :verify_failed

echo [OK] Gate B passed.
echo      Evidence: %EVIDENCE%
goto :verify_passed

:verify_passed
echo.
echo ========================================
echo  H3 Unified verification PASSED
echo  Evidence: storage\live\h3_unified_live_gate.json
echo ========================================
echo.
echo  Full verification:  verify_h3.bat
echo  Preflight only:     verify_h3.bat preflight
exit /b 0

:usage
echo.
echo  Usage:
echo    verify_h3.bat
 echo      Run Gate A, then submit the 5-second Gate B smoke generation.
echo.
echo    verify_h3.bat preflight
 echo      Run Gate A only. No generation is submitted.
exit /b 0

:usage_failed
echo.
echo  Usage:
echo    verify_h3.bat
 echo    verify_h3.bat preflight
exit /b 2

:verify_failed
echo.
echo ========================================
echo  [ERROR] H3 Unified verification FAILED
echo  Evidence: storage\live\h3_unified_live_gate.json
echo ========================================
echo  Fix the reported Gate failure and run again.
exit /b 1
