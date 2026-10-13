@echo off
echo.
echo [A] batch started
cd /d "%~dp0"
echo [B] cd ok, now in: %cd%
echo.
echo [C] running: where py
where py
echo     errorlevel = %errorlevel%
echo.
echo [D] running: where python
where python
echo     errorlevel = %errorlevel%
echo.
echo [E] running: py -3 -c print version
py -3 -c "import sys;print(sys.version)"
echo     errorlevel = %errorlevel%
echo.
echo [F] running: python -c print version
python -c "import sys;print(sys.version)"
echo     errorlevel = %errorlevel%
echo.
echo [G] testing goto
goto jump_test
echo [!!] goto did NOT work
:jump_test
echo [H] goto ok
echo.
echo [I] ALL STEPS FINISHED
pause
