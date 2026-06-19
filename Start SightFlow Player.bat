@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\run_player.ps1"
if errorlevel 1 (
  echo.
  echo SightFlow Player failed to start. Press any key to close.
  pause >nul
)

