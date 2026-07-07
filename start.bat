@echo off
title WAACT - WhatsApp Automation System
set "PYTHON=C:\Users\moham\AppData\Local\Programs\Python\Python312\python.exe"
echo ============================================
echo    WAACT - WhatsApp Automation
echo ============================================
echo.

cd /d "%~dp0"

echo [1/5] Checking Python dependencies...
cd backend
%PYTHON% -c "import fastapi, uvicorn, sqlalchemy, chromadb, openai, tiktoken, apscheduler, httpx, jinja2, multipart, aiofiles, numpy" >nul 2>nul
if errorlevel 1 (
    echo Missing dependencies. Installing once...
    %PYTHON% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Dependency install failed.
        echo If the error mentions chroma-hnswlib / Visual C++ Build Tools, install dependencies manually once, then run start.bat again.
        echo The app can still run if dependencies are already installed.
        pause
        exit /b 1
    )
) else (
    echo Dependencies already installed - skipping pip install.
)
cd ..

echo [2/5] Initializing database and knowledge base...
cd backend
%PYTHON% seed_knowledge.py
cd ..

echo [3/5] Creating .env file if needed...
if not exist "backend\.env" (
    copy "backend\.env.example" "backend\.env"
    echo Created .env file - please set your OPENAI_API_KEY in backend\.env
)

echo [4/5] Freeing port 8000 if needed...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$conn=Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1; if ($conn) { Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue; Write-Host ('Stopped process on port 8000: ' + $conn.OwningProcess) } else { Write-Host 'Port 8000 is free' }"

echo [5/5] Starting backend server...
echo.
echo Dashboard: http://localhost:8000
echo API:       http://localhost:8000/api/health
echo.
echo NOTE: To connect WhatsApp, run in another terminal:
echo   cd whatsapp-connector ^&^& npm install ^&^& npm start
echo   Then scan the QR code with WhatsApp.
echo.

cd backend
%PYTHON% -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
