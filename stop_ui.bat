@echo off
title Stop Chess Fragments UI
echo ========================================================
echo   Stopping Chess Fragments UI Server on Port 5000...
echo ========================================================

set count=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
    set /a count+=1
)

if %count% GTR 0 (
    echo   [OK] Server processes on port 5000 terminated.
    echo   [OK] Chess Fragments hosting is stopped!
) else (
    echo   [INFO] No active server was found listening on port 5000.
)

echo ========================================================
timeout /t 2 /nobreak >nul
