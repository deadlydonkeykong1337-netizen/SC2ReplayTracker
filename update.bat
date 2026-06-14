@echo off
rem Updates SC2 Replay Tracker to the latest version from GitHub.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1"
echo.
pause
