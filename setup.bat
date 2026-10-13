@echo off
rem ---------------------------------------------------------------
rem  PlayCut setup
rem  NOTE: this file is intentionally pure ASCII and does NOT call
rem  "chcp". cmd.exe tracks its read position as a byte offset, and
rem  switching the code page in the middle of a batch file makes it
rem  lose that position and abort. All Chinese messages are printed
rem  by Python instead.
rem ---------------------------------------------------------------
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

echo.
echo ============================================================
echo    PlayCut  setup
echo ============================================================
echo.

rem ---- locate Python ---------------------------------------------
rem  NOTE: every %PY% invocation below is prefixed with "call".
rem  Version managers such as pyenv-win put a python.BAT shim on
rem  PATH; invoking a .bat from a .bat without "call" transfers
rem  control and never returns, which kills this script silently.
set "PY="
where py >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto have_python
where python >nul 2>&1
if not errorlevel 1 set "PY=python"
:have_python
if not defined PY goto no_python

call %PY% -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
if errorlevel 1 goto old_python

for /f "delims=" %%v in ('call %PY% -c "import sys;print(sys.version.split()[0])"') do set "PYVER=%%v"
echo [1/3] Python %PYVER% found.
echo.

rem ---- virtual environment ---------------------------------------
echo [2/3] Creating environment and installing packages...
echo       (first run takes a few minutes)
echo.
if not exist ".venv\Scripts\python.exe" call %PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" goto venv_failed

".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pip_failed
echo.

rem ---- libmpv + ffmpeg -------------------------------------------
echo [3/3] Downloading libmpv and ffmpeg...
echo.
".venv\Scripts\python.exe" tools\fetch_deps.py
if errorlevel 1 goto deps_failed

echo.
echo ============================================================
echo    Done.  Double-click  run.bat  to start PlayCut.
echo    (build.bat makes a standalone PlayCut.exe)
echo ============================================================
echo.
pause
exit /b 0

rem ================================================================
:no_python
echo [X] Python not found.
echo.
echo     Install Python 3.10+ from:
echo         https://www.python.org/downloads/
echo     IMPORTANT: tick "Add Python to PATH" during install.
echo.
echo     Or run this in a terminal:
echo         winget install Python.Python.3.12
echo.
echo     Then run setup.bat again.
echo.
pause
exit /b 1

:old_python
echo [X] Your Python is too old. Version 3.9 or newer is required.
echo     Get it from https://www.python.org/downloads/
echo.
pause
exit /b 1

:venv_failed
echo [X] Could not create the .venv environment.
echo     Try deleting the .venv folder and running setup.bat again.
echo.
pause
exit /b 1

:pip_failed
echo [X] Package installation failed. Check your internet connection.
echo.
pause
exit /b 1

:deps_failed
echo.
echo ============================================================
echo    Some downloads failed - see the instructions above.
echo ============================================================
echo.
pause
exit /b 1
