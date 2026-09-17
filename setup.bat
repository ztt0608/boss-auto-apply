@echo off
REM ============================================================
REM  [0a] Configuration wizard - generate config.json
REM  Set your own job keywords, cities, salary range and pace.
REM  Re-runnable: the old file is backed up as config.json.bak
REM  Full guide (Chinese): see README.md
REM ============================================================
cd /d "%~dp0"

REM Execute for real - the Store stub (WindowsApps alias) cannot run
py -3 --version >nul 2>nul
if not errorlevel 1 (set "PY=py -3") else (set "PY=python")
%PY% --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Run install_python.bat first, then check_env.bat.
    pause
    exit /b 1
)

%PY% setup_config.py
if errorlevel 1 (
    echo.
    echo [ERROR] Setup did not finish. See the messages above.
    pause
    exit /b 1
)
exit /b 0
