@echo off
echo Starting Attendance Tracker...
echo.
echo [1/2] Starting FastAPI backend (port 8000)...
start "Backend - FastAPI" cmd /k "cd /d "%~dp0" && python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 3 /nobreak >nul

echo [2/2] Starting Next.js frontend (port 3000)...
start "Frontend - Next.js" cmd /k "cd /d "%~dp0\frontend" && npm install && npm run dev"

echo.
echo Both services starting. Open http://localhost:3000 in your browser.
echo Press any key to exit this window...
pause >nul
