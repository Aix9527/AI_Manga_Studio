@echo off
setlocal enabledelayedexpansion
echo.
echo ============================================================
echo   AI Manga Studio - Pipeline Launcher v3
echo ============================================================
echo.
if "%~1"=="" (
    set /p "NOVEL_PATH=  Novel file path: "
) else (
    set "NOVEL_PATH=%~1"
    echo   Novel path: !NOVEL_PATH!
)
if not exist "!NOVEL_PATH!" (
    echo.
    echo   [ERROR] File not found: !NOVEL_PATH!
    pause
    exit /b 1
)
for %%F in ("!NOVEL_PATH!") do set "TITLE=%%~nF"
echo   Novel: !TITLE!
echo.
echo ------------------------------------------------------------
echo   Style ^& Aspect Ratio
echo ------------------------------------------------------------
set "IMG_STYLE=二次元"
set "ASPECT_RATIO=16:9 横屏 (1280x720)"
set "IMG_WIDTH=1280"
set "IMG_HEIGHT=720"

echo.
echo   1. Visual Style
echo      [1] 二次元 (default)
echo      [2] 古风写实
echo      [3] 现代写实
echo      [4] 赛博朋克
echo      [5] 水墨国风
echo      [6] 3D卡通
echo      [7] 3D电影写实
echo      [8] 3D古装玄幻
set /p "CHOICE=      Select [1-8, Enter=default]: "
if "!CHOICE!"=="2" set "IMG_STYLE=古风写实"
if "!CHOICE!"=="3" set "IMG_STYLE=现代写实"
if "!CHOICE!"=="4" set "IMG_STYLE=赛博朋克"
if "!CHOICE!"=="5" set "IMG_STYLE=水墨国风"
if "!CHOICE!"=="6" set "IMG_STYLE=3D卡通"
if "!CHOICE!"=="7" set "IMG_STYLE=3D电影写实"
if "!CHOICE!"=="8" set "IMG_STYLE=3D古装玄幻"
echo      -^> Style: !IMG_STYLE!

echo.
echo   2. Aspect Ratio
echo      [1] 16:9 横屏 (1280x720) (default)
echo      [2] 9:16 竖屏 (720x1280)
echo      [3] 4:3 标准 (1024x768)
echo      [4] 21:9 宽银幕 (1536x640)
echo      [5] 16:9 FHD (1920x1080)
echo      [6] 9:16 FHD (1080x1920)
set /p "CHOICE=      Select [1-6, Enter=default]: "
if "!CHOICE!"=="2" (
    set "ASPECT_RATIO=9:16 竖屏 (720x1280)"
    set "IMG_WIDTH=720"
    set "IMG_HEIGHT=1280"
)
if "!CHOICE!"=="3" (
    set "ASPECT_RATIO=4:3 标准 (1024x768)"
    set "IMG_WIDTH=1024"
    set "IMG_HEIGHT=768"
)
if "!CHOICE!"=="4" (
    set "ASPECT_RATIO=21:9 宽银幕 (1536x640)"
    set "IMG_WIDTH=1536"
    set "IMG_HEIGHT=640"
)
if "!CHOICE!"=="5" (
    set "ASPECT_RATIO=16:9 FHD (1920x1080)"
    set "IMG_WIDTH=1920"
    set "IMG_HEIGHT=1080"
)
if "!CHOICE!"=="6" (
    set "ASPECT_RATIO=9:16 FHD (1080x1920)"
    set "IMG_WIDTH=1080"
    set "IMG_HEIGHT=1920"
)
echo      -^> Aspect: !ASPECT_RATIO! (!IMG_WIDTH!x!IMG_HEIGHT!)

echo.
echo ------------------------------------------------------------
echo   Image Generation Parameters
echo ------------------------------------------------------------
set "IMG_MODEL=sd_xl_base_1.0"
set "IMG_STEPS=25"
set "IMG_CFG=7.5"
set "IMG_SAMPLER=euler_ancestral"

echo.
echo   1. Model
echo      [1] sd_xl_base_1.0 (default)
echo      [2] sd_xl_turbo
echo      [3] juggernautXL_v9
echo      [4] realvisxlV40
echo      [5] dreamshaperXL
set /p "CHOICE=      Select [1-5, Enter=default]: "
if "!CHOICE!"=="2" set "IMG_MODEL=sd_xl_turbo"
if "!CHOICE!"=="3" set "IMG_MODEL=juggernautXL_v9"
if "!CHOICE!"=="4" set "IMG_MODEL=realvisxlV40"
if "!CHOICE!"=="5" set "IMG_MODEL=dreamshaperXL"
echo      -^> Model: !IMG_MODEL!

echo.
echo   2. Sampling steps [15-50] (default 25)
set /p "IMG_STEPS_IN=      Steps: "
if not "!IMG_STEPS_IN!"=="" set "IMG_STEPS=!IMG_STEPS_IN!"
echo      -^> Steps: !IMG_STEPS!

echo.
echo   3. CFG scale [3.0-12.0] (default 7.5)
set /p "IMG_CFG_IN=      CFG: "
if not "!IMG_CFG_IN!"=="" set "IMG_CFG=!IMG_CFG_IN!"
echo      -^> CFG: !IMG_CFG!

echo.
echo   4. Sampler
echo      [1] euler_ancestral (default)
echo      [2] euler
echo      [3] dpmpp_2m
echo      [4] dpmpp_sde
echo      [5] lcm
set /p "CHOICE=      Select [1-5, Enter=default]: "
if "!CHOICE!"=="2" set "IMG_SAMPLER=euler"
if "!CHOICE!"=="3" set "IMG_SAMPLER=dpmpp_2m"
if "!CHOICE!"=="4" set "IMG_SAMPLER=dpmpp_sde"
if "!CHOICE!"=="5" set "IMG_SAMPLER=lcm"
echo      -^> Sampler: !IMG_SAMPLER!

echo.
echo ------------------------------------------------------------
echo   Video Generation Parameters
echo ------------------------------------------------------------
set "VID_FRAMES=16"
set "VID_FPS=8"
set "VID_DENOISE=0.85"
set "VID_MOTION=mm_sdxl_v10_beta.ckpt"

echo   1. Frames per shot (default 16)
set /p "VID_FRAMES_IN=      Frames: "
if not "!VID_FRAMES_IN!"=="" set "VID_FRAMES=!VID_FRAMES_IN!"
echo      -^> Frames: !VID_FRAMES!

echo.
echo   2. FPS (default 8)
set /p "VID_FPS_IN=      FPS: "
if not "!VID_FPS_IN!"=="" set "VID_FPS=!VID_FPS_IN!"
echo      -^> FPS: !VID_FPS!

echo.
echo   3. Denoise strength [0.5-1.0] (default 0.85)
set /p "VID_DENOISE_IN=      Denoise: "
if not "!VID_DENOISE_IN!"=="" set "VID_DENOISE=!VID_DENOISE_IN!"
echo      -^> Denoise: !VID_DENOISE!

echo.
echo   4. Motion module (default mm_sdxl_v10_beta.ckpt)
set /p "VID_MOTION_IN=      Motion module: "
if not "!VID_MOTION_IN!"=="" set "VID_MOTION=!VID_MOTION_IN!"
echo      -^> Motion: !VID_MOTION!

echo.
echo ------------------------------------------------------------
echo   Character ^& Audio Settings
echo ------------------------------------------------------------
set "SKIP_CHAR="
set "CHAR_STYLE=二次元"
set "CHAR_RES=768x1024"
set "TTS_ENABLED=true"
set "SUBS_ENABLED=true"
set "BGM_ENABLED=false"

echo.
echo   1. Generate character sheets?
echo      [1] Yes (default) - extracts characters, generates 6-view sheets
echo      [2] No (skip, use existing reference images)
set /p "CHOICE=      Select [1-2, Enter=default]: "
if "!CHOICE!"=="2" set "SKIP_CHAR=--skip-characters"
echo      -^> Generate: !SKIP_CHAR!

echo.
echo   2. Character image resolution
echo      [1] 竖屏角色卡 (768x1024) (default)
echo      [2] 正方形角色卡 (1024x1024)
echo      [3] 横屏角色卡 (1024x768)
echo      [4] 横屏 FHD (1920x1080)
echo      [5] 竖屏 FHD (1080x1920)
set /p "CHOICE=      Select [1-5, Enter=default]: "
if "!CHOICE!"=="2" set "CHAR_RES=1024x1024"
if "!CHOICE!"=="3" set "CHAR_RES=1024x768"
if "!CHOICE!"=="4" set "CHAR_RES=1920x1080"
if "!CHOICE!"=="5" set "CHAR_RES=1080x1920"
echo      -^> Char res: !CHAR_RES!

echo.
echo   3. TTS voiceover (Chinese)?
echo      [1] Yes (default)
echo      [2] No
set /p "CHOICE=      Select [1-2, Enter=default]: "
if "!CHOICE!"=="2" set "TTS_ENABLED=false"
echo      -^> TTS: !TTS_ENABLED!

echo.
echo   4. Generate subtitles (SRT)?
echo      [1] Yes (default)
echo      [2] No
set /p "CHOICE=      Select [1-2, Enter=default]: "
if "!CHOICE!"=="2" set "SUBS_ENABLED=false"
echo      -^> Subtitles: !SUBS_ENABLED!

echo.
echo   5. Background music?
echo      [1] No (default)
echo      [2] Yes (epic orchestral)
set /p "CHOICE=      Select [1-2, Enter=default]: "
if "!CHOICE!"=="2" set "BGM_ENABLED=true"
echo      -^> BGM: !BGM_ENABLED!

echo.
echo ============================================================
echo   Configuration Summary
echo ============================================================
echo.
echo   Style ^& Format:
echo     Style       : !IMG_STYLE!
echo     Aspect Ratio: !ASPECT_RATIO!
echo.
echo   Image Generation:
echo     Model      : !IMG_MODEL!
echo     Steps      : !IMG_STEPS!
echo     CFG Scale  : !IMG_CFG!
echo     Sampler    : !IMG_SAMPLER!
echo     Resolution : !IMG_WIDTH!x!IMG_HEIGHT!
echo.
echo   Video Generation:
echo     Frames      : !VID_FRAMES!
echo     FPS         : !VID_FPS!
echo     Denoise     : !VID_DENOISE!
echo     Motion Mod. : !VID_MOTION!
echo.
echo   Character ^& Audio:
echo     Char Sheet  : !SKIP_CHAR!
echo     Char Res    : !CHAR_RES!
echo     TTS         : !TTS_ENABLED!
echo     Subtitles   : !SUBS_ENABLED!
echo     BGM         : !BGM_ENABLED!
echo.
echo   Novel: !TITLE!
echo.

set /p "CONFIRM=  Proceed with these settings? [Y/n]: "
if /i "!CONFIRM!"=="n" (
    echo   Cancelled by user.
    pause
    exit /b 0
)

set "CONFIG_DIR=%~dp0temp"
if not exist "!CONFIG_DIR!" mkdir "!CONFIG_DIR!"
set "CONFIG_PATH=!CONFIG_DIR!\pipeline_config.json"

python -c "import json,os;d={'image':{'model':os.environ['IMG_MODEL'],'steps':int(os.environ['IMG_STEPS']),'cfg':float(os.environ['IMG_CFG']),'sampler':os.environ['IMG_SAMPLER'],'width':int(os.environ['IMG_WIDTH']),'height':int(os.environ['IMG_HEIGHT']),'style':os.environ['IMG_STYLE'],'aspect_ratio':os.environ['ASPECT_RATIO']},'video':{'frames':int(os.environ['VID_FRAMES']),'fps':int(os.environ['VID_FPS']),'denoise':float(os.environ['VID_DENOISE']),'motion_module':os.environ['VID_MOTION']},'character':{'style':os.environ['CHAR_STYLE'],'views_per_character':6,'resolution':os.environ['CHAR_RES'],'steps':22,'cfg':7.0},'audio':{'tts_enabled':os.environ['TTS_ENABLED']=='true','tts_language':'zh-CN','tts_voice':chr(40664)+chr(35748)+chr(38899)+chr(33394),'subtitles_enabled':os.environ['SUBS_ENABLED']=='true','bgm_enabled':os.environ['BGM_ENABLED']=='true','bgm_style':chr(21490)+chr(35799)+chr(31649)+chr(24358)+chr(20048)},'ipadapter':{'char_weight':0.80,'face_weight':0.75,'clothing_lock':True,'motion_freedom':chr(20013),'scene_freedom':chr(39640)},'novel_path':os.environ['NOVEL_PATH'],'title':os.environ['TITLE']};json.dump(d,open(os.environ['CONFIG_PATH'],'w',encoding='utf-8'),ensure_ascii=False,indent=2)"
if !ERRORLEVEL! neq 0 (
    echo   [ERROR] Failed to write config
    pause
    exit /b 1
)

echo   Config saved: !CONFIG_PATH!

echo.
echo   Checking services...

powershell -Command "try {$null=Invoke-RestMethod 'http://localhost:8188/system_stats' -TimeoutSec 3;exit 0}catch{exit 1}" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo   [ERROR] ComfyUI not running on :8188
    echo           Start ComfyUI first.
    pause
    exit /b 1
)
echo   [OK] ComfyUI running

powershell -Command "try {$null=Invoke-RestMethod 'http://localhost:8001/docs' -TimeoutSec 3;exit 0}catch{exit 1}" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo   [ERROR] Backend not running on :8001
    echo           Run start_backend.bat first.
    pause
    exit /b 1
)
echo   [OK] Backend running

echo.
echo   Launching pipeline...
echo ============================================================

python -u "%~dp0pipeline.py" --config "!CONFIG_PATH!" !SKIP_CHAR! 2>&1

echo.
echo ============================================================
echo   Output: D:\ComfyUI_new\outputecho ============================================================
pause
