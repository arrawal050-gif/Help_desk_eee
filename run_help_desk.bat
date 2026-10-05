@echo off
title Sakhi EEE Campus Help Desk
cd /d "%~dp0"

echo =====================================================================
echo         SAKHI  -  EEE Block Campus Help Desk
echo     Shri Vaishnav Vidyapeeth Vishwavidyalaya, Indore
echo =====================================================================
echo.
echo  Starting server, please wait...
echo  URL     : http://localhost:8000
echo  Admin   : http://localhost:8000/admin/
echo  Press CTRL+C to stop the server.
echo =====================================================================
echo.

:: Start the FastAPI server in the background
start "" /B python main.py

:: Wait for the server to become ready (poll /api/health)
:WAIT_LOOP
timeout /t 1 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://localhost:8000/api/health | findstr /C:"200" >nul 2>&1
if errorlevel 1 goto WAIT_LOOP

echo  Server is ready! Opening browser...
echo.
start "" "http://localhost:8000"

:: Keep the window open and show server logs
echo  [Server is running. Close this window or press CTRL+C to stop.]
echo.

:: Wait until the python process exits
:KEEP_ALIVE
timeout /t 2 /nobreak >nul
tasklist /FI "IMAGENAME eq python.exe" 2>nul | findstr /I "python.exe" >nul
if not errorlevel 1 goto KEEP_ALIVE

echo.
echo  Server has stopped.
pause
