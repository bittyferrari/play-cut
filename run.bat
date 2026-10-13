@echo off
rem Pure ASCII on purpose - see the note in setup.bat.
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

if not exist ".venv\Scripts\pythonw.exe" goto not_installed
if not exist "bin\libmpv-2.dll" goto no_libmpv

rem pythonw keeps the black console window from appearing
start "PlayCut" ".venv\Scripts\pythonw.exe" -m playcut %*
exit /b 0

:not_installed
echo.
echo [X] Not installed yet. Please run setup.bat first.
echo.
pause
exit /b 1

:no_libmpv
echo.
echo [X] bin\libmpv-2.dll is missing - the player cannot start.
echo     Run setup.bat again, or follow the manual download
echo     instructions it prints.
echo.
pause
exit /b 1
