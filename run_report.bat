@echo off
REM ============================================================
REM  [3] Generate today's daily report (日报_YYYY-MM-DD.md)
REM  Optional Feishu push if configured, otherwise skipped.
REM  Full guide (Chinese): see README.md
REM ============================================================
cd /d "%~dp0"
REM Execute for real - the Store stub (WindowsApps alias) cannot run
py -3 --version >nul 2>nul
if not errorlevel 1 (set "PY=py -3") else (set "PY=python")
%PY% daily_report.py
echo.
pause
