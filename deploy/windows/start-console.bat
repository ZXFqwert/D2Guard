@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if exist ".venv-windows\Scripts\python.exe" goto ready
call setup-windows.bat
if errorlevel 1 exit /b 1
:ready
".venv-windows\Scripts\python.exe" tools\windows_console.py %*
if errorlevel 1 pause
