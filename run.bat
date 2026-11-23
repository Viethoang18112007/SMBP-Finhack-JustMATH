@echo off
rem Double-click launcher for Windows. Same as: python run.py
python "%~dp0run.py" %*
if errorlevel 1 pause
