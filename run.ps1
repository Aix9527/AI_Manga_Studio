# V11 AI Movie Pipeline - PowerShell Launcher
# Usage: .\run.ps1 "C:\path\to\novel.txt"
#    or drag .txt onto this script

param(
    [Parameter(Mandatory=$true)]
    [string]$NovelPath
)

if (-not (Test-Path $NovelPath)) {
    Write-Host "[ERROR] 文件不存在: $NovelPath" -ForegroundColor Red
    pause
    exit 1
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runner = Join-Path $ScriptDir "backend_v11\run_pipeline.py"

Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "  V11 AI Movie Pipeline" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "  Novel: $(Split-Path $NovelPath -Leaf)" -ForegroundColor Yellow
Write-Host ""

python $Runner --novel $NovelPath

Write-Host ""
Write-Host "Done. Press any key to exit..." -ForegroundColor Green
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
