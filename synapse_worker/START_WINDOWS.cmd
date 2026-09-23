@echo off
cd /d "%~dp0"
py -3 worker.py init
if errorlevel 1 goto failed
py -3 worker.py serve
if errorlevel 1 goto failed
exit /b 0
:failed
echo Synapse stopped. Read the error above. Python 3.11 or newer is required.
pause
exit /b 1
