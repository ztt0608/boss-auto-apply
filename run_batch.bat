@echo off
REM ============================================================
REM  [2] Run one delivery batch
REM  Usage:
REM    run_batch.bat          - deliver 17 (default, recommended per batch)
REM    run_batch.bat 16       - deliver 16
REM    run_batch.bat 0        - scan only, no delivery (delete candidates.json
REM                             first to force a fresh scan)
REM  Prerequisite: run start_edge.bat first and confirm you are logged in.
REM  The batch is truly finished only when the log ends with ===DONE===.
REM  Full guide (Chinese): see README.md
REM ============================================================
cd /d "%~dp0"
set "BATCH=%~1"
if "%BATCH%"=="" set "BATCH=17"
set "BOSS_BATCH=%BATCH%"

REM Execute for real - the Store stub (WindowsApps alias) cannot run
py -3 --version >nul 2>nul
if not errorlevel 1 (set "PY=py -3") else (set "PY=python")
%PY% --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Run install_python.bat first, then check_env.bat.
    pause
    exit /b 1
)

if not exist "config.json" (
    echo [WARN] config.json not found - built-in defaults will be used.
    echo        The defaults target IT / operations jobs, which may not match you.
    echo        Run setup.bat to configure your own keywords, cities and salary.
    echo.
    timeout /t 5 >nul
)

echo Batch target: %BATCH%. Running now (17 items takes ~25-30 min, keep this window open)...
%PY% boss_batch.py > boss_run_latest.log 2>&1
echo.
echo ===== Finished. Last 30 lines of the log: =====
powershell -NoProfile -Command "Get-Content boss_run_latest.log -Tail 30"
echo.
echo Full log: boss_run_latest.log
pause
