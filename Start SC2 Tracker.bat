@echo off
rem Launches SC2 Replay Tracker without a console window.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" run.py
