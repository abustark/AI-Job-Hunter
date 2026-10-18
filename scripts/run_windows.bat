@echo off
setlocal
cd /d "%~dp0\.."
if not exist .venv\Scripts\python.exe (
  echo The app environment is missing. Run scripts\setup_windows.bat first.
  pause
  exit /b 1
)
echo Starting AI Job Hunter at http://127.0.0.1:5000
echo Keep this window open while using the app. Press Ctrl+C to stop.
.venv\Scripts\python.exe app.py
if errorlevel 1 (
  echo The app stopped with an error. The port may already be in use; stop the other local server and retry.
  pause
)
