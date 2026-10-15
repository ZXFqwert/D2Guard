@echo off
cd /d "%~dp0"
python start_all.py %*
if errorlevel 1 pause
