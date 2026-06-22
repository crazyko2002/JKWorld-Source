@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath powershell.exe -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%~dp0run_advanced.ps1""' -WorkingDirectory '%~dp0' -Verb RunAs"
