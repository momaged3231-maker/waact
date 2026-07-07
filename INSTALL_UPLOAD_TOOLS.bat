@echo off
setlocal EnableExtensions
title WAACT - Install Upload Tools

echo ============================================
echo WAACT - Install Upload Tools
echo ============================================
echo.
echo This helper checks Git, GitHub CLI, and Node.js.
echo Git is required for UPLOAD_TO_GITHUB.bat.
echo GitHub CLI is optional but helps with GitHub login.
echo.

where winget >nul 2>nul
if errorlevel 1 goto no_winget

where git >nul 2>nul
if errorlevel 1 (
    echo Git is missing.
    choice /m "Install Git for Windows using winget"
    if not errorlevel 2 winget install --id Git.Git -e --source winget
) else (
    echo Git is already installed.
)

where node >nul 2>nul
if errorlevel 1 (
    echo Node.js is missing.
    choice /m "Install Node.js LTS using winget"
    if not errorlevel 2 winget install --id OpenJS.NodeJS.LTS -e --source winget
) else (
    echo Node.js is already installed.
)

where gh >nul 2>nul
if errorlevel 1 (
    echo GitHub CLI is missing. It is optional.
    choice /m "Install GitHub CLI using winget"
    if not errorlevel 2 winget install --id GitHub.cli -e --source winget
) else (
    echo GitHub CLI is already installed.
)

echo.
echo If any tool was installed, close this window and reopen a new terminal before running UPLOAD_TO_GITHUB.bat.
pause
exit /b 0

:no_winget
echo winget is not available on this Windows installation.
echo Opening manual download pages...
start "" "https://git-scm.com/download/win"
start "" "https://nodejs.org/"
start "" "https://cli.github.com/"
echo.
echo Install Git for Windows first, then reopen a new terminal and run UPLOAD_TO_GITHUB.bat.
pause
exit /b 0
