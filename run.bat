@echo off
cd /d "%~dp0"
set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" where py >nul 2>nul && set PY=py -3
if "%PY%"=="" (
  echo Python was not found. Install Python 3.10+ from python.org and tick "Add to PATH".
  pause
  exit /b 1
)
echo Starting RegSwarm (this window must stay open while you use the app)...
%PY% server.py
echo.
echo RegSwarm stopped. If there is an error above, copy it and send it to me.
pause
