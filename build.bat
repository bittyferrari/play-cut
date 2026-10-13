@echo off
rem Pure ASCII on purpose - see the note in setup.bat.
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

if not exist ".venv\Scripts\python.exe" goto not_installed
if not exist "bin\libmpv-2.dll" goto no_deps

echo Installing PyInstaller...
".venv\Scripts\python.exe" -m pip install --upgrade pyinstaller
if errorlevel 1 goto pyi_failed

echo.
echo Building standalone exe (this takes a few minutes)...
echo.
".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm --clean --onefile --windowed ^
    --name PlayCut ^
    --icon "playcut\resources\icon.ico" ^
    --add-data "playcut\resources;playcut\resources" ^
    --add-binary "bin\libmpv-2.dll;." ^
    --add-binary "bin\ffmpeg.exe;bin" ^
    --add-binary "bin\ffprobe.exe;bin" ^
    --hidden-import playcut ^
    run_app.py
if errorlevel 1 goto build_failed

echo.
echo ============================================================
echo    Done:  dist\PlayCut.exe
echo    That single file runs on any Windows PC - no Python needed.
echo ============================================================
echo.
pause
exit /b 0

:not_installed
echo [X] Run setup.bat first.
pause
exit /b 1

:no_deps
echo [X] bin\libmpv-2.dll not found. Run setup.bat first.
pause
exit /b 1

:pyi_failed
echo [X] PyInstaller installation failed.
pause
exit /b 1

:build_failed
echo [X] Build failed.
pause
exit /b 1
