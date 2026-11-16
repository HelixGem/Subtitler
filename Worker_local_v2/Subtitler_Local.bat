@echo off
setlocal EnableDelayedExpansion
title Subtitler Local v2.0.0

:: ============================================================
::  Subtitler Local — Windows launcher
::  Usage:
::    Subtitler_Local.bat              Start server
::    Subtitler_Local.bat --setup      Run setup wizard
::    Subtitler_Local.bat --model medium
::    Subtitler_Local.bat --port 9000
::    Subtitler_Local.bat --check      Check installation
:: ============================================================

echo ============================================================
echo   Subtitler Local v2.0.0
echo   Self-hosted WhisperX transcription server
echo ============================================================
echo.

:: ============================================================
:: STEP 1 — Locate Python
:: ============================================================

set PYTHON_CMD=

:: Try 'python' first
python --version >nul 2>&1
if !errorlevel! equ 0 (
    set PYTHON_CMD=python
    goto :python_found
)

:: Try 'python3'
python3 --version >nul 2>&1
if !errorlevel! equ 0 (
    set PYTHON_CMD=python3
    goto :python_found
)

:: Try common install paths
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
) do (
    if exist %%P (
        set PYTHON_CMD=%%P
        goto :python_found
    )
)

:: Python not found
echo   [ERROR] Python not found.
echo.
echo   Install Python 3.9 or newer:
echo     https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
echo.
echo   During installation check:
echo     [x] Add Python to PATH
echo.
pause
exit /b 1

:python_found
for /f "tokens=*" %%V in ('!PYTHON_CMD! --version 2^>^&1') do set PY_VERSION=%%V
echo   Python: !PY_VERSION!
echo   Executable: !PYTHON_CMD!
echo.

:: ============================================================
:: STEP 2 — Verify script exists
:: ============================================================

set SCRIPT=%~dp0subtitler_local.py

if not exist "%SCRIPT%" (
    echo   [ERROR] subtitler_local.py not found.
    echo   Expected location: %SCRIPT%
    echo.
    echo   Make sure Subtitler_Local.bat is in the same
    echo   directory as subtitler_local.py
    echo.
    pause
    exit /b 1
)

:: ============================================================
:: STEP 3 — Handle --setup flag
:: ============================================================

if /i "%~1"=="--setup" (
    echo   Running setup wizard...
    echo.
    !PYTHON_CMD! "%SCRIPT%" --setup
    echo.
    echo   Setup finished. Press any key to exit.
    pause >nul
    exit /b 0
)

:: ============================================================
:: STEP 4 — Check installation status
:: ============================================================

echo   Checking installation...
echo.

:: Run --check with visible output so user sees dependency status
!PYTHON_CMD! "%SCRIPT%" --check
set CHECK_RESULT=!errorlevel!

if !CHECK_RESULT! neq 0 (
    echo.
    echo   [!] Some dependencies are missing or not configured.
    echo.
    echo   Running setup wizard...
    echo.

    timeout /t 2 /nobreak >nul

    !PYTHON_CMD! "%SCRIPT%" --setup
    set SETUP_RESULT=!errorlevel!

    :: If user cancelled setup or setup itself failed
    if !SETUP_RESULT! neq 0 (
        echo.
        echo   [!] Setup was cancelled or encountered an error.
        echo   Please re-run: Subtitler_Local.bat --setup
        echo.
        pause
        exit /b 1
    )

    :: Re-check after setup — informational only
    :: Non-zero here means optional components missing (e.g. no models cached)
    :: Server can still start — models download automatically on first use
    echo.
    echo   Re-checking installation...
    !PYTHON_CMD! "%SCRIPT%" --check
    if !errorlevel! neq 0 (
        echo.
        echo   [!] Some optional components are not configured.
        echo   Server will start — missing items download on first use.
        echo   To install everything: Subtitler_Local.bat --setup
        echo.
    )
)

echo   All dependencies satisfied.
echo.

:: ============================================================
:: STEP 5 — Start server
:: ============================================================

echo   Starting server...
echo   Press Ctrl+C to stop.
echo.

!PYTHON_CMD! "%SCRIPT%" %*

:: ============================================================
:: STEP 6 — Exit handling
:: ============================================================

echo.
echo   Server stopped.
echo   Press any key to close this window.
pause >nul
exit /b 0