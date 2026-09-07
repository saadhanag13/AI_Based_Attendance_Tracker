@echo off
title Face Recognition Attendance System

echo ==========================================
echo   Face Recognition Attendance System
echo ==========================================
echo.

REM Go to this folder
cd /d "C:\Users\Libeesh Saravanan\Downloads\attendance-main\attendance-main"

REM Create venv if it doesn't exist
if not exist ".venv" (
    echo Creating virtual environment...
    uv venv --python 3.11
)

REM Install/update dependencies
echo Installing dependencies...
uv pip install -r requirements.txt

echo.
echo Starting Streamlit...
start "" http://localhost:8501

uv run python -m streamlit run app.py

pause