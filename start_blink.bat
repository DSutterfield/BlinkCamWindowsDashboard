@echo off
setlocal

REM 2026-08-03 Dan/Sage:
REM Use the folder containing this launcher rather than a hard-coded path.
REM Run the virtual-environment Python directly, so activation is unnecessary.

set "APP_DIR=%~dp0"
set "PYTHON=%APP_DIR%.venv\Scripts\python.exe"

echo Checking Blink DVR processes...

REM --- Verify the project virtual environment exists ---
if not exist "%PYTHON%" (
    echo.
    echo ERROR: Python was not found at:
    echo %PYTHON%
    echo.
    pause
    exit /b 1
)

REM --- Start the clip poller if not running ---
tasklist /V /FI "IMAGENAME eq python.exe" 2>nul | findstr /C:"BlinkDVR" >nul
if errorlevel 1 (
    echo   Starting clip poller...
    start "BlinkDVR" /MIN cmd /k ""%PYTHON%" "%APP_DIR%blink_dvr.py""
) else (
    echo   Clip poller already running.
)

REM --- Start the web dashboard if not running ---
tasklist /V /FI "IMAGENAME eq python.exe" 2>nul | findstr /C:"BlinkWeb" >nul
if errorlevel 1 (
    echo   Starting web dashboard...
    start "BlinkWeb" /MIN cmd /k ""%PYTHON%" "%APP_DIR%web_app.py""
) else (
    echo   Web dashboard already running.
)

REM --- Give Flask time to start, then open the browser ---
echo   Waiting for web server to be ready...
timeout /t 6 /nobreak >nul
start "" http://localhost:5000

echo Done.
endlocal