@echo off
cd /d "%~dp0"
if exist "%~dp0dist\PTShot-M3E\PTShot.exe" (
  start "" "%~dp0dist\PTShot-M3E\PTShot.exe"
  exit /b 0
)
where pythonw >nul 2>nul
if errorlevel 1 (
  echo Python 3.11+ is required. Use the packaged PTShot.exe or install Python.
  pause
  exit /b 1
)
start "" pythonw "%~dp0run.py"
