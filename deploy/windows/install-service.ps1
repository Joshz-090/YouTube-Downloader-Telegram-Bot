#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Install the YouTube Downloader bot as a Windows service using NSSM.
.DESCRIPTION
    Downloads NSSM if needed, installs the bot as a service that starts at boot.
    Also creates a Task Scheduler task for daily yt-dlp updates.
.NOTES
    Run as Administrator.
    NSSM: https://nssm.cc/
#>

param(
    [string]$BotDir = "D:\projects\Eyasu\the bot of youtube",
    [string]$ServiceName = "YTDLBot",
    [string]$PythonExe = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Find Python ───────────────────────────────────────────────────────────────
if (-not $PythonExe) {
    $PythonExe = (Get-Command python -ErrorAction SilentlyContinue)?.Source
    if (-not $PythonExe) {
        Write-Error "Python not found in PATH. Please install Python 3.12+ or pass -PythonExe."
        exit 1
    }
}
Write-Host "Using Python: $PythonExe" -ForegroundColor Cyan

# Check .venv exists
$VenvPython = Join-Path $BotDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
    Write-Host "Using venv Python: $PythonExe" -ForegroundColor Cyan
}

# ── Download NSSM ─────────────────────────────────────────────────────────────
$NssmDir = "$env:ProgramFiles\nssm"
$NssmExe = "$NssmDir\nssm.exe"

if (-not (Test-Path $NssmExe)) {
    Write-Host "Downloading NSSM..." -ForegroundColor Yellow
    $NssmZip = "$env:TEMP\nssm.zip"
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $NssmZip
    Expand-Archive -Path $NssmZip -DestinationPath "$env:TEMP\nssm" -Force
    New-Item -ItemType Directory -Path $NssmDir -Force | Out-Null
    Copy-Item "$env:TEMP\nssm\nssm-2.24\win64\nssm.exe" -Destination $NssmExe -Force
    Remove-Item $NssmZip -Force
    Write-Host "NSSM installed to $NssmDir" -ForegroundColor Green
}

# ── Remove existing service if present ────────────────────────────────────────
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing service '$ServiceName'..." -ForegroundColor Yellow
    & $NssmExe stop $ServiceName confirm 2>$null
    & $NssmExe remove $ServiceName confirm 2>$null
    Start-Sleep -Seconds 2
}

# ── Install service ───────────────────────────────────────────────────────────
Write-Host "Installing service '$ServiceName'..." -ForegroundColor Yellow

& $NssmExe install $ServiceName $PythonExe "-m bot.main"

# Configure service settings
& $NssmExe set $ServiceName AppDirectory $BotDir
& $NssmExe set $ServiceName AppEnvironmentExtra "PYTHONPATH=$BotDir"
& $NssmExe set $ServiceName DisplayName "YouTube Downloader Telegram Bot"
& $NssmExe set $ServiceName Description "Telegram bot that downloads YouTube videos"
& $NssmExe set $ServiceName Start SERVICE_AUTO_START
& $NssmExe set $ServiceName AppRestartDelay 10000   # 10s delay before restart
& $NssmExe set $ServiceName AppStopMethodSkip 0
& $NssmExe set $ServiceName AppStopMethodConsole 1500
& $NssmExe set $ServiceName AppStopMethodWindow 1500
& $NssmExe set $ServiceName AppStopMethodThreads 1500

# Logging
$LogDir = Join-Path $BotDir "logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
& $NssmExe set $ServiceName AppStdout (Join-Path $LogDir "bot.log")
& $NssmExe set $ServiceName AppStderr (Join-Path $LogDir "bot-error.log")
& $NssmExe set $ServiceName AppRotateFiles 1
& $NssmExe set $ServiceName AppRotateOnline 1
& $NssmExe set $ServiceName AppRotateBytes 10485760  # 10 MB

Write-Host "Service '$ServiceName' installed successfully!" -ForegroundColor Green

# ── Start the service ─────────────────────────────────────────────────────────
Write-Host "Starting service..." -ForegroundColor Yellow
& $NssmExe start $ServiceName
Start-Sleep -Seconds 3
$svc = Get-Service -Name $ServiceName
Write-Host "Service status: $($svc.Status)" -ForegroundColor Cyan

# ── Scheduled task: daily yt-dlp update ───────────────────────────────────────
Write-Host "`nCreating daily yt-dlp update task..." -ForegroundColor Yellow

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "-m pip install --upgrade yt-dlp" `
    -WorkingDirectory $BotDir

$Trigger = New-ScheduledTaskTrigger -Daily -At "03:00AM"

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName "YTDLBot-UpdateYtDlp" `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Daily yt-dlp upgrade for YouTube Downloader Bot" `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "Scheduled task 'YTDLBot-UpdateYtDlp' created (runs at 3 AM daily)" -ForegroundColor Green

Write-Host "`n✅ Installation complete!" -ForegroundColor Green
Write-Host "   Service: $ServiceName (auto-starts at boot)" -ForegroundColor White
Write-Host "   Logs: $LogDir" -ForegroundColor White
Write-Host "   Manage: nssm start/stop/restart $ServiceName" -ForegroundColor White
