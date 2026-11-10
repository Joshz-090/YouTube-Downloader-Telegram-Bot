@echo off
:: Update yt-dlp and restart the bot service on Windows
:: Run from the bot's project directory

echo [%date% %time%] Updating yt-dlp...

:: Activate venv if it exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python -m pip install --upgrade yt-dlp
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to update yt-dlp
    exit /b 1
)
echo [%date% %time%] yt-dlp updated successfully.

:: Restart NSSM service if installed
sc query YTDLBot >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Restarting YTDLBot service...
    nssm restart YTDLBot
    echo Service restarted.
) else (
    echo Note: YTDLBot service not found. Restart the bot manually.
)

echo [%date% %time%] Done.
