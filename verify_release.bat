@echo off
setlocal
cd /d "%~dp0"
title AI Manga Studio - v0.8 Release Gate

set "MODE=%~1"

if /I "%MODE%"=="help" goto :usage
if not "%MODE%"=="" if /I not "%MODE%"=="preflight" if /I not "%MODE%"=="full" goto :usage_failed

echo ========================================
echo  AI Manga Studio v0.8 - Release Gate
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    goto :release_failed
)

npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js/npm not found.
    goto :release_failed
)

echo [1/3] Launcher and Windows entrypoint contracts...
python -m pytest -q tests/test_local_launchers.py
if errorlevel 1 goto :release_failed
echo [OK] Launcher contracts passed.
echo.

echo [2/3] H3 Unified code/runtime contracts...
python -m pytest -q tests/video/test_h3_unified.py tests/video/test_h3_unified_router.py tests/video/test_h3_unified_execution.py tests/video/test_h3_unified_formal.py tests/video/test_h3_unified_factory.py tests/video/test_h3_unified_formal_assets.py tests/video/test_h3_unified_provider_media_binding.py tests/video/test_h3_unified_live_gate.py --disable-warnings --maxfail=1
if errorlevel 1 goto :release_failed
echo [OK] H3 Unified contracts passed.
echo.

echo [3/3] Unified Studio frontend typecheck / tests / build...
if not exist "frontend\package.json" (
    echo [ERROR] frontend\package.json not found.
    goto :release_failed
)
pushd frontend
call npm run typecheck
if errorlevel 1 (
    popd
    goto :release_failed
)
call npm test -- --run
if errorlevel 1 (
    popd
    goto :release_failed
)
call npm run build
if errorlevel 1 (
    popd
    goto :release_failed
)
popd
echo [OK] Unified Studio frontend passed.
echo.

if "%MODE%"=="" goto :release_passed
if /I "%MODE%"=="preflight" goto :hardware_preflight
if /I "%MODE%"=="full" goto :hardware_full
goto :usage_failed

:hardware_preflight
echo [Hardware] H3 Unified preflight only...
call verify_h3.bat preflight
if errorlevel 1 goto :release_failed
goto :release_passed

:hardware_full
echo [Hardware] H3 Unified preflight + 5-second smoke generation...
call verify_h3.bat
if errorlevel 1 goto :release_failed
goto :release_passed

:release_passed
echo.
echo ========================================
echo  v0.8 Release Gate PASSED
echo ========================================
echo.
if "%MODE%"=="" echo  Scope: code gates only; no GPU generation was submitted.
if /I "%MODE%"=="preflight" echo  Scope: code gates + H3 hardware preflight; no generation submitted.
if /I "%MODE%"=="full" echo  Scope: code gates + H3 hardware preflight + 5-second smoke generation.
echo.
echo  Code only:       verify_release.bat
echo  + H3 preflight:  verify_release.bat preflight
echo  + H3 smoke:      verify_release.bat full
exit /b 0

:usage
echo.
echo  Usage:
echo    verify_release.bat
 echo      Run code release gates only. Safe default; no GPU generation.
echo.
echo    verify_release.bat preflight
 echo      Run code gates, then H3 hardware preflight only.
echo.
echo    verify_release.bat full
 echo      Run code gates, then H3 preflight and the 5-second real smoke generation.
exit /b 0

:usage_failed
echo [ERROR] Unknown mode: %MODE%
echo  Use: verify_release.bat ^| verify_release.bat preflight ^| verify_release.bat full
exit /b 2

:release_failed
echo.
echo ========================================
echo  [ERROR] v0.8 Release Gate FAILED
echo ========================================
echo  Fix the first failing gate above and run again.
exit /b 1
