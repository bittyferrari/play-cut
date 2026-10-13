@echo off
rem Pure ASCII on purpose - see the note in setup.bat.
rem Starts PlayCut with a console window and verbose mpv logging,
rem so any error message stays visible.
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

if not exist ".venv\Scripts\python.exe" (
    echo [X] Not installed yet. Please run setup.bat first.
    pause
    exit /b 1
)

set "PLAYCUT_MPV_LOG=v"

echo.
echo ------------------------------------------------------------
echo  Debug mode. Error messages will stay in this window.
echo  Close PlayCut, then copy the text below if you need help.
echo ------------------------------------------------------------
echo.
".venv\Scripts\python.exe" -m playcut %*
echo.
echo ------------------------------------------------------------
echo  PlayCut exited with code %errorlevel%
echo ------------------------------------------------------------
pause
