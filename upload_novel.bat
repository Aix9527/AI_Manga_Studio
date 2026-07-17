@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Novel Upload

echo ============================================
echo   Upload Novel to AI Movie Studio V6
echo ============================================
echo.

if "%~1"=="" (
    echo Usage: upload_novel.bat "D:\path\novel.txt"
    echo.
    set /p "FILE_PATH=Enter file path: "
) else (
    set "FILE_PATH=%~1"
)

if not exist "!FILE_PATH!" (
    echo [ERROR] File not found: !FILE_PATH!
    pause
    exit /b 1
)

for %%F in ("!FILE_PATH!") do set "TITLE=%%~nF"

echo Uploading: !TITLE!
echo File: !FILE_PATH!
echo.

python -c "import requests, json, os, sys; fp=r'!FILE_PATH!'; f=open(fp,'r',encoding='utf-8'); c=f.read(); f.close(); t=os.path.splitext(os.path.basename(fp))[0]; r=requests.post('http://localhost:8001/api/v6/novels',json={'raw_text':c,'title':t}); print(f'Status: {r.status_code}'); d=r.json(); print(f'Novel ID: {d[\"novel\"][\"id\"]}'); print(f'Words: {d[\"novel\"][\"word_count\"]}')"

echo.
echo ============================================
echo List: http://localhost:8001/api/v6/novels
echo ============================================
pause
