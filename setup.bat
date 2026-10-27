@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  Qwen Desktop Chat - first time setup
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH.
    echo         Install Python 3.11 or newer from https://www.python.org/downloads/
    echo         and tick "Add python.exe to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

if exist "venv\Scripts\python.exe" (
    echo Virtual environment already exists at .\venv - reusing it.
) else (
    echo Creating virtual environment in .\venv ...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment.
        pause
        exit /b 1
    )
)

echo.
echo Installing dependencies from requirements.txt ...
"venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed. See the messages above.
    pause
    exit /b 1
)

echo.
echo Verifying the installation ...
"venv\Scripts\python.exe" -c "import PySide6, keyring, markdown, pygments; print('  PySide6  OK'); print('  keyring  OK'); print('  markdown OK'); print('  pygments OK')"
if errorlevel 1 (
    echo.
    echo [ERROR] Verification failed: a required package is missing.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Setup finished successfully.
echo  Start the app by double-clicking run.bat
echo ============================================================
echo.
pause
exit /b 0
