@echo off
rem GridEasy one-click start for Windows: creates .venv, installs, opens the browser and starts the server.
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo Python 3.11+ is not installed.
  echo Download it from https://www.python.org/downloads/ and tick "Add python.exe to PATH" during install.
  echo Then close this window and double-click start.bat again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv || goto :error
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -e . || goto :error

echo.
echo GridEasy is starting at http://localhost:8000  (press Ctrl+C to stop)
start "" http://localhost:8000
".venv\Scripts\python.exe" -m uvicorn gridease.api.app:app --port 8000
goto :eof

:error
echo.
echo Setup failed - see the messages above.
pause
exit /b 1
