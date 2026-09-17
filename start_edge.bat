@echo off
REM ============================================================
REM  [1] Launch Edge with remote debugging port (for boss_batch.py)
REM  - Auto-detects Edge path; profile saved to .\edge_profile\
REM  - First run: log in to Boss in the opened Edge window
REM  - Log out of Boss on your PHONE (web and mobile kick each other)
REM  Full guide (Chinese): see README.md
REM ============================================================
set "EDGE1=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
set "EDGE2=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
if exist "%EDGE1%" (set "EDGE=%EDGE1%") else if exist "%EDGE2%" (set "EDGE=%EDGE2%") else (
    echo [ERROR] Edge not found. Edit the EDGE path at the top of this file.
    pause
    exit /b 1
)
set "PROFILE=%~dp0edge_profile"
echo Starting Edge with remote debugging (port 9223, isolated profile)...
start "" "%EDGE%" --remote-debugging-port=9223 --remote-allow-origins=* --user-data-dir="%PROFILE%" "https://www.zhipin.com/web/geek/job"
timeout /t 8 /nobreak >nul
echo.
echo  In the opened Edge window, please confirm:
echo    1) Your avatar shows at top-right = logged in (if not, log in now; it will be kept)
echo    2) Boss on your PHONE is logged out (otherwise the web session gets kicked)
echo    3) Open http://127.0.0.1:9223/json/version in a browser - it should show JSON
echo.
echo  Then run run_batch.bat to start a delivery batch.
pause
