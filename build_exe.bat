@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  Qwen Desktop Chat - build a Windows executable
echo ============================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] The virtual environment is missing. Run setup.bat first.
    pause
    exit /b 1
)

echo Installing PyInstaller (skipped if already present) ...
"venv\Scripts\python.exe" -m pip install --upgrade pyinstaller --quiet
if errorlevel 1 (
    echo [ERROR] Could not install PyInstaller.
    pause
    exit /b 1
)

echo.
echo Building. This can take a few minutes ...
echo.

rem --windowed  : no console window
rem --name      : product name (also the folder name in dist\)
rem The app reads no bundled data files: all data lives in %USERPROFILE%\.qwen-desktop-chat
"venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --name "Qwen Desktop Chat" ^
    --collect-submodules keyring ^
    --hidden-import keyring.backends.Windows ^
    main.py

if errorlevel 1 (
    echo.
    echo [ERROR] The build failed. Read the PyInstaller output above.
    echo         A common cause is a missing hidden import; add one with
    echo         --hidden-import ^<module^> and run this script again.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Build finished.
echo  The executable is in:  dist\Qwen Desktop Chat\
echo  Run:                   dist\Qwen Desktop Chat\Qwen Desktop Chat.exe
echo ============================================================
echo.
echo Notes:
echo   - The .exe does NOT contain your API key. The key stays in
echo     Windows Credential Manager under "QwenDesktopChat".
echo   - Chat history is kept in %%USERPROFILE%%\.qwen-desktop-chat
echo     so it survives rebuilding and replacing the app folder.
echo.
pause
exit /b 0
