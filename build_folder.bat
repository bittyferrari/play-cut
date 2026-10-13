@echo off
rem Pure ASCII on purpose - see the note in setup.bat.
rem Builds a portable FOLDER (onedir) instead of a single exe:
rem faster start-up, fewer antivirus false positives.
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

if not exist ".venv\Scripts\python.exe" goto not_installed
if not exist "bin\libmpv-2.dll" goto no_deps
if not exist "bin\ffmpeg.exe" goto no_deps
if not exist "bin\ffprobe.exe" goto no_deps

echo Installing PyInstaller...
".venv\Scripts\python.exe" -m pip install --upgrade pyinstaller
if errorlevel 1 goto pyi_failed

echo.
echo Building portable folder (this takes a few minutes)...
echo.
".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm --clean --onedir --windowed ^
    --name PlayCut ^
    --icon "%CD%\playcut\resources\icon.ico" ^
    --add-data "%CD%\playcut\resources;playcut\resources" ^
    --workpath "build\onedir" ^
    --specpath "build\onedir" ^
    --add-binary "%CD%\bin\libmpv-2.dll;." ^
    --add-binary "%CD%\bin\ffmpeg.exe;bin" ^
    --add-binary "%CD%\bin\ffprobe.exe;bin" ^
    --hidden-import playcut ^
    run_app.py
if errorlevel 1 goto build_failed

if not exist "dist\PlayCut\PlayCut.exe" goto build_failed

echo.
echo Removing unused Qt files...
".venv\Scripts\python.exe" tools\slim_dist.py "dist\PlayCut"
if errorlevel 1 echo [!] Slim step failed - the folder still works, just larger.

rem Intermediate build files are not needed after a successful build
rem (the next build uses --clean anyway).
if exist "build\onedir" rmdir /s /q "build\onedir"

echo.
echo Creating dist\PlayCut.zip ...
if exist "dist\PlayCut.zip" del /q "dist\PlayCut.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\PlayCut' -DestinationPath 'dist\PlayCut.zip'"
if errorlevel 1 echo [!] Zip step failed - the folder itself is still fine.

echo.
echo ============================================================
echo    Done:  dist\PlayCut\PlayCut.exe
echo           dist\PlayCut.zip  (same folder, zipped)
echo    Copy the WHOLE dist\PlayCut folder to another PC
echo    and run PlayCut.exe inside it - no Python needed.
echo ============================================================
echo.
pause
exit /b 0

:not_installed
echo [X] Run setup.bat first.
pause
exit /b 1

:no_deps
echo [X] bin\libmpv-2.dll / ffmpeg.exe / ffprobe.exe not found. Run setup.bat first.
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
