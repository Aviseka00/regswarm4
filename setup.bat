@echo off
cd /d "%~dp0"
set PY=
where python >nul 2>nul && set PY=python
if "%PY%"=="" where py >nul 2>nul && set PY=py -3
if "%PY%"=="" (
  echo Python was not found. Install Python 3.10+ from python.org and tick "Add to PATH".
  cmd /k
  exit /b 1
)
echo Using: %PY%
echo.
echo Downloading 21 CFR from the official eCFR API...
%PY% ingest\fetch_ecfr.py > setup_log.txt 2>&1
set RC=%errorlevel%
type setup_log.txt
if not "%RC%"=="0" (
  echo.
  echo ==== DOWNLOAD FAILED. The full message above is also saved in setup_log.txt ====
  echo This window stays open - select the text above, copy it, and send it to me.
  cmd /k
  exit /b 1
)
echo.
echo Checking the live workflow and security controls...
%PY% -m unittest discover -s tests
echo.
echo Done. Now double-click run.bat
pause
