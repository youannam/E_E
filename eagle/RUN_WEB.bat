@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\run_web.ps1"
if errorlevel 1 (
  echo.
  echo Eagle Eye could not start. Read the error above.
  pause
)
