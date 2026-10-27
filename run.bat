@echo off
setlocal
cd /d "%~dp0"

set "VENV=%~dp0venv"
set "LOGDIR=%~dp0logs"

if not exist "%VENV%\Scripts\python.exe" (
    echo.
    echo Virtual environment not found at:
    echo   %VENV%
    echo.
    echo Running setup.bat to create it now...
    echo.
    call "%~dp0setup.bat"
    if errorlevel 1 (
        echo Setup failed. Fix the error above, then run run.bat again.
        pause
        exit /b 1
    )
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
set "LOGFILE=%LOGDIR%\app.log"

echo Starting Qwen Desktop Chat...
echo Log file: %LOGFILE%
echo.

if exist "%VENV%\Scripts\pythonw.exe" (
    "%VENV%\Scripts\pythonw.exe" "%~dp0main.py" >"%LOGFILE%" 2>&1
) else (
    "%VENV%\Scripts\python.exe" "%~dp0main.py" >"%LOGFILE%" 2>&1
)

set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
    echo.
    echo The application exited with code %CODE%.
    echo Last lines of %LOGFILE%:
    echo ------------------------------------------------------------
    powershell -NoProfile -Command "Get-Content -Tail 25 -LiteralPath '%LOGFILE%'" 2>nul
    echo ------------------------------------------------------------
    echo.
    pause
    exit /b %CODE%
)

exit /b 0
