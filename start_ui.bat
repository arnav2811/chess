@echo off
title Chess Fragments AI Arena - Hosting
echo ========================================================
echo   Chess Fragments AI Arena Server
echo   http://localhost:5000
echo ========================================================

:: Kill any lingering processes on port 5000
echo [*] Checking and clearing port 5000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

echo [*] Launching Chess Fragments Arena in browser...
start "" "http://localhost:5000"

echo [*] Starting Python backend server...
echo     (Press Ctrl+C at any time to stop hosting)
echo ========================================================
python ui_server.py
pause
