@echo off
cd /d "%~dp0"
echo Starting SSUST at http://127.0.0.1:8765
echo Leave this window open. Close it to stop the demo.
start "" cmd /c "ping -n 3 127.0.0.1 >nul & start http://127.0.0.1:8765"
python backend\server.py
