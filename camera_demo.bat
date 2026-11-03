@echo off
rem Double-click launcher for the camera-mode demo (tools/screen.py).
rem Board on COM10, demo video, horizontal mirror as in the final recording.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist tools\logs mkdir tools\logs
"C:\miniforge3\envs\ztmc\python.exe" tools\screen.py COM10 videos\demo.mp4 --mirror "1 0" --log tools\logs\screen_last.log
if errorlevel 1 pause
