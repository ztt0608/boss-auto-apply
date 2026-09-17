@echo off
REM ============================================================
REM  Health check: Edge debug port / Boss login / foreground focus
REM  / synthetic input. Zero-cost (opens no job pages, counts no
REM  deliveries). Run this FIRST when anything misbehaves.
REM  Exit codes: 0 ok / 2 CDP / 3 no page / 4 not logged in / 5 input
REM  Full guide (Chinese): see README.md
REM ============================================================
cd /d "%~dp0"
REM Execute for real - the Store stub (WindowsApps alias) cannot run
py -3 --version >nul 2>nul
if not errorlevel 1 (set "PY=py -3") else (set "PY=python")
%PY% cdp_health.py %*
echo.
pause
