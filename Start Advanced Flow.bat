@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\run_advanced.ps1"
if errorlevel 1 (
  echo.
  echo Advanced Flow failed to start. Press any key to close.
  pause >nul
)
