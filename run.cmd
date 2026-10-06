@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run PowerShell: .\setup.ps1
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8000
