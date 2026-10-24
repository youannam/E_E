@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\run_mobile.ps1"
if errorlevel 1 (
  echo.
  echo Eagle Eye Mobile could not start. Read the error above.
  pause
)
