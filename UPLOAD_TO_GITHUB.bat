@echo off
setlocal EnableExtensions EnableDelayedExpansion
title WAACT - Upload Online Demo to GitHub

cd /d "%~dp0"

echo ============================================
echo WAACT - Upload Online Demo to GitHub
echo ============================================
echo.
echo This script will initialize Git if needed, commit the project, and push to GitHub.
echo It will NOT upload ignored secrets like backend\.env, whatsapp-connector\.env, node_modules, or WhatsApp session-data.
echo.

where git >nul 2>nul
if errorlevel 1 (
    echo Git is not installed or not available in PATH.
    echo Install Git for Windows first: https://git-scm.com/download/win
    echo You can run INSTALL_UPLOAD_TOOLS.bat from this folder.
    start "" "https://git-scm.com/download/win"
    pause
    exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
    echo Node.js is not installed or not available in PATH.
    echo Install Node.js 18+ first: https://nodejs.org/
    echo You can run INSTALL_UPLOAD_TOOLS.bat from this folder.
    start "" "https://nodejs.org/"
    pause
    exit /b 1
)

echo Step 1: Running safety checks...
set "NO_PAUSE=1"
call "%~dp0CHECK_BEFORE_UPLOAD.bat"
set "NO_PAUSE="
if errorlevel 1 exit /b 1

echo.
echo Step 2: Preparing Git repository...
if not exist ".git" (
    git init
    if errorlevel 1 goto fail
)

git branch -M main >nul 2>nul

echo.
echo Step 3: Making sure secrets are not tracked...
git rm -r --cached --ignore-unmatch backend/.env backend/.env.codespaces backend/ai_settings.json backend/radius_settings.json backend/router_auto_settings.json backend/waact.db backend/waact.db-shm backend/waact.db-wal backend/chroma_db whatsapp-connector/.env whatsapp-connector/.env.codespaces whatsapp-connector/session-data whatsapp-connector/node_modules .vercel >nul 2>nul

echo.
echo Step 4: Configuring Git user for this repository if missing...
for /f "delims=" %%i in ('git config user.email 2^>nul') do set "GIT_EMAIL=%%i"
if "!GIT_EMAIL!"=="" (
    set /p GIT_EMAIL=Enter your Git email for this repo: 
    if "!GIT_EMAIL!"=="" goto fail
    git config user.email "!GIT_EMAIL!"
)

for /f "delims=" %%i in ('git config user.name 2^>nul') do set "GIT_NAME=%%i"
if "!GIT_NAME!"=="" (
    set /p GIT_NAME=Enter your Git name for this repo: 
    if "!GIT_NAME!"=="" goto fail
    git config user.name "!GIT_NAME!"
)

echo.
echo Step 5: Configuring remote origin...
git remote get-url origin >nul 2>nul
if errorlevel 1 (
    echo Create an empty GitHub repository first, then paste its URL here.
    echo Example: https://github.com/YOUR_USERNAME/waact-online-demo.git
    set /p REPO_URL=GitHub repo URL: 
    if "!REPO_URL!"=="" goto fail
    git remote add origin "!REPO_URL!"
    if errorlevel 1 goto fail
) else (
    for /f "delims=" %%i in ('git remote get-url origin') do set "CURRENT_REMOTE=%%i"
    echo Current origin: !CURRENT_REMOTE!
    set /p CHANGE_REMOTE=Change origin URL? Type y to change, Enter to keep: 
    if /i "!CHANGE_REMOTE!"=="y" (
        set /p REPO_URL=New GitHub repo URL: 
        if "!REPO_URL!"=="" goto fail
        git remote set-url origin "!REPO_URL!"
        if errorlevel 1 goto fail
    )
)

echo.
echo Step 6: Staging files...
git add .
if errorlevel 1 goto fail

echo.
echo Files ready to commit:
git status --short
echo.
echo Review the list above. It must NOT include .env, node_modules, session-data, or waact.db.
set /p CONFIRM=Type YES to commit and push: 
if /i not "!CONFIRM!"=="YES" (
    echo Cancelled by user.
    pause
    exit /b 0
)

echo.
echo Step 7: Committing...
git commit -m "Prepare WAACT online demo deployment"
if errorlevel 1 (
    echo Commit may have failed because there are no changes or Git auth/config issue.
    echo Continuing to push current branch if possible...
)

echo.
echo Step 8: Syncing with GitHub before push...
git ls-remote --exit-code --heads origin main >nul 2>nul
if errorlevel 1 (
    echo Remote branch main does not exist yet - first push will create it.
) else (
    echo Remote branch main exists. Pulling remote updates first...
    git pull --rebase --autostash origin main
    if errorlevel 1 (
        echo.
        echo Rebase pull failed. Trying safe merge for existing GitHub README/initial commit...
        git rebase --abort >nul 2>nul
        git pull --no-rebase --allow-unrelated-histories --no-edit origin main
        if errorlevel 1 goto pullfail
    )
)

echo.
echo Step 9: Pushing to GitHub...
git push -u origin main
if errorlevel 1 goto pushfail

echo.
echo ============================================
echo Upload complete.
echo Next: Open ONLINE_DEMO_UPLOAD_GUIDE.md and continue with Supabase, Codespaces, and Vercel.
echo ============================================
pause
exit /b 0

:pullfail
echo.
echo Pull failed because GitHub has changes that could not be merged automatically.
echo Open the files marked as conflicts, fix them, then run:
echo   git add .
echo   git commit -m "Resolve GitHub sync conflicts"
echo   git push -u origin main
echo.
echo If you do not know how to resolve the conflict, send me the full output above.
pause
exit /b 1

:pushfail
echo.
echo Push failed.
echo If the error says authentication failed, run: gh auth login
echo If the error says rejected/fetch first, run this script again after the pull step above completes.
echo Or push from GitHub Desktop.
pause
exit /b 1

:fail
echo.
echo Script failed or required input was empty.
pause
exit /b 1
