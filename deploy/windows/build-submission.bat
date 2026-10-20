@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv-windows\Scripts\python.exe" goto missing
".venv-windows\Scripts\python.exe" tools\package_delivery.py --output "..\D2Guard-Windows-final.zip"
pause
exit /b
:missing
python tools\package_delivery.py --output "..\D2Guard-Windows-final.zip"
pause
