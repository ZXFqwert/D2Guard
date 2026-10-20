@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
py -3.12 -c "import sys" >nul 2>nul
if errorlevel 1 goto defaultpython
py -3.12 tools\setup_windows.py
goto finished
:defaultpython
python tools\setup_windows.py
:finished
if errorlevel 1 goto failed
echo Setup complete. Use start-console.bat.
pause
exit /b 0
:failed
echo Setup failed. See the error above.
pause
exit /b 1
