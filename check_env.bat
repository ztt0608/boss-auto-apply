@echo off
REM ============================================================
REM  [0b] Environment self-check for a new PC (~30 seconds)
REM  Checks: Python, bundled websocket-client, Edge
REM  Full guide (Chinese): see README.md
REM ============================================================
cd /d "%~dp0"
echo [1/3] Checking Python ...
REM Execute for real - the Store stub (WindowsApps alias) cannot run
py -3 --version >nul 2>nul
if not errorlevel 1 (set "PY=py -3") else (set "PY=python")
%PY% -c "import sys; print('    OK:', sys.version.split()[0])"
if errorlevel 1 (
    echo    [FAIL] Python not found.
    echo    - Run install_python.bat in this folder to auto-install. Needs internet, 2-5 min.
    pause
    exit /b 1
)
echo [2/3] Checking bundled websocket-client ...
%PY% -c "import os,sys; sys.path.insert(0, os.path.abspath(os.path.join('toolchain','pylibs'))); import websocket; print('    OK:', websocket.__version__)"
if errorlevel 1 (
    echo    [FAIL] Bundled lib broken. Fix with: pip install -r requirements.txt
    pause
    exit /b 1
)
echo [3/3] Checking Edge ...
set "EDGE1=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
set "EDGE2=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
if exist "%EDGE1%" (echo    OK & goto :done)
if exist "%EDGE2%" (echo    OK & goto :done)
echo    [FAIL] Edge not found. Install Edge or edit EDGE path in start_edge.bat
pause
exit /b 1
:done
echo.
echo === All checks passed ===
echo Next: run start_edge.bat, log in to Boss, then run health_check.bat
pause
