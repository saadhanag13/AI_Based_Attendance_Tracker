@echo off
cd /d "%~dp0\frontend"
echo Installing dependencies...
call npm install
echo Starting Next.js frontend on http://localhost:3000 ...
call npm run dev
pause
