@echo off
rem One-time setup: creates the Python environment and installs dependencies.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install it from https://www.python.org/downloads/
    echo IMPORTANT: tick "Add Python to PATH" during installation.
    pause
    exit /b 1
)
echo Creating virtual environment...
python -m venv .venv
echo Installing dependencies (this can take a minute)...
.venv\Scripts\pip install -r requirements.txt
echo.
echo Done! Double-click "Start SC2 Tracker.bat" to launch the app.
pause
