@echo off
setlocal
cd /d "%~dp0\.."
for /f "delims=" %%P in ('powershell -NoProfile -Command "(Get-Command python -ErrorAction SilentlyContinue).Source"') do set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
  echo Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/windows/ and enable Add Python to PATH.
  pause
  exit /b 1
)
"%PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo Python 3.10 or newer is required.
  pause
  exit /b 1
)
if not exist .venv "%PYTHON_EXE%" -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto failed
python -m pip install -r requirements.txt
if errorlevel 1 goto failed
if not exist .env copy .env.example .env >nul
echo.
echo Setup complete. Run scripts\run_windows.bat to start AI Job Hunter.
pause
exit /b 0
:failed
echo Setup failed. Check your internet connection and Python installation, then try again.
pause
exit /b 1
