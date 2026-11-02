@echo off
cd /d "%~dp0"
if exist "dist-0.2\PhotoJoy\PhotoJoy.exe" (
  start "" "dist-0.2\PhotoJoy\PhotoJoy.exe"
) else if exist "dist\PhotoJoy\PhotoJoy.exe" (
  start "" "dist\PhotoJoy\PhotoJoy.exe"
) else (
  start "" ".venv\Scripts\pythonw.exe" "run_photojoy.py"
)
