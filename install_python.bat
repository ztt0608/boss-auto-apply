@echo off
REM ============================================================
REM  [0a] Python auto-installer (run this if Python is missing)
REM  Strategy: skip if already installed - try winget first -
REM            fallback to silent install of official installer
REM            (Huawei Cloud mirror first, python.org fallback;
REM             per-user install, no admin needed)
REM  Full guide (Chinese): see README.md
REM ============================================================
echo === Python auto-installer ===
REM NOTE: do NOT trust "where python" alone - the Windows Store stub
REM (WindowsApps alias) is found by WHERE but cannot actually run.
REM So we really execute it and check the exit code.
py --version >nul 2>nul
if not errorlevel 1 (echo Python already installed [py launcher]. Nothing to do. & pause & exit /b 0)
python --version >nul 2>nul
if not errorlevel 1 (echo Python already installed [python command]. Nothing to do. & pause & exit /b 0)

echo Python not found. Auto-installing (needs internet, ~2-5 minutes)...
echo.
set "PYL=%LocalAppData%\Programs\Python\Launcher\py.exe"

REM ---- Method 1: winget (built into Win10 1709+) ----
where winget >nul 2>nul
if %errorlevel%==0 (
    echo [Method 1] Trying winget...
    winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements
)
if exist "%PYL%" goto :verify

REM ---- Method 2: official installer, silent ----
REM Offline-friendly: if the installer is bundled in this folder, use it directly
set "INST=%TEMP%\python-3.12.8-amd64.exe"
if exist "%~dp0python-3.12.8-amd64.exe" (
    echo [Method 2] Local installer found in package folder - no download needed.
    set "INST=%~dp0python-3.12.8-amd64.exe"
    goto :runinst
)
echo [Method 2] Downloading official package (Huawei mirror first, python.org fallback)...
powershell -NoProfile -Command "$out=Join-Path $env:TEMP 'python-3.12.8-amd64.exe'; try { Invoke-WebRequest -Uri 'https://mirrors.huaweicloud.com/python/3.12.8/python-3.12.8-amd64.exe' -OutFile $out -UseBasicParsing } catch { Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile $out -UseBasicParsing }"
if not exist "%INST%" (
    echo [FAIL] Download failed. Check network and run this file again.
    pause
    exit /b 1
)
echo Installing silently (per-user, added to PATH, no admin needed)...
:runinst
"%INST%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0

:verify
if not exist "%PYL%" (
    echo [INFO] py launcher not found, trying python command...
    python --version && (echo === Install OK === & pause & exit /b 0)
    echo [INFO] Installer may have finished but PATH is not refreshed in this window.
    echo Close this window and run check_env.bat again. If it still fails,
    echo install manually from python.org.
    pause
    exit /b 0
)
"%PYL%" --version
if errorlevel 1 (
    echo [INFO] Verify failed. Run check_env.bat to re-check.
    pause
    exit /b 1
)
echo.
echo === Python install OK ===
echo Next: run check_env.bat for a full check.
pause
