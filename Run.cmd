@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment not found. Follow the installation steps in README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m posture_line %*
if errorlevel 1 pause
