@echo off
setlocal EnableExtensions
title WAACT - Check Before Upload

cd /d "%~dp0"

set "PYTHON=C:\Users\moham\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo ============================================
echo WAACT - Check Before Upload
echo ============================================
echo.

echo [1/5] Checking Python syntax...
cd backend
"%PYTHON%" -m py_compile config.py main.py media_intelligence.py whatsapp\connector.py dashboard\routes.py check_mvp_v1_3.py
if errorlevel 1 goto fail
cd ..

echo.
echo [2/5] Checking WhatsApp connector JavaScript...
node --check whatsapp-connector\index.js
if errorlevel 1 goto fail

echo.
echo [3/5] Checking Vercel proxy JavaScript...
node --check api\proxy.js
if errorlevel 1 goto fail

echo.
echo [4/5] Checking secret files are ignored by git...
git --version >nul 2>nul
if errorlevel 1 (
    echo Git is not installed or not available in PATH. Upload script needs Git.
    goto fail
)

if not exist ".git" (
    git init --quiet
    git branch -M main >nul 2>nul
)

git check-ignore backend\.env >nul 2>nul
if errorlevel 1 (
    echo backend\.env is not ignored. Stop.
    goto fail
)

git check-ignore whatsapp-connector\.env >nul 2>nul
if errorlevel 1 (
    echo whatsapp-connector\.env is not ignored. Stop.
    goto fail
)

git check-ignore whatsapp-connector\session-data >nul 2>nul
if errorlevel 1 (
    echo whatsapp-connector\session-data is not ignored. Stop.
    goto fail
)

echo.
echo [5/5] Running MVP smoke check...
cd backend
"%PYTHON%" check_mvp_v1_3.py
if errorlevel 1 goto fail
cd ..

echo.
echo ============================================
echo Checks passed. You can upload safely.
echo ============================================
if not "%NO_PAUSE%"=="1" pause
exit /b 0

:fail
echo.
echo ============================================
echo Check failed. Fix the error above before upload.
echo ============================================
if not "%NO_PAUSE%"=="1" pause
exit /b 1
