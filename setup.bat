@echo off
rem Sets up hirejutsu in a .venv folder next to this file. Run it again to update.
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set PYTHON=py -3) else (set PYTHON=python)

if not exist .venv (
    %PYTHON% -m venv .venv || goto :failed
)
.venv\Scripts\python -m pip install --upgrade pip || goto :failed
.venv\Scripts\python -m pip install -e . || goto :failed
.venv\Scripts\hirejutsu init || goto :failed

echo.
echo Done. Next:
echo   1. Copy your resume into the data folder shown above.
echo   2. .venv\Scripts\hirejutsu config --edit
echo   3. .venv\Scripts\hirejutsu run
echo   4. .venv\Scripts\hirejutsu schedule install
exit /b 0

:failed
echo Setup failed. Check that Python 3.10 or newer is installed from https://www.python.org/downloads/
exit /b 1
