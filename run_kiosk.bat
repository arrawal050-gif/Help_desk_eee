@echo off
title Sakhi EEE Campus Kiosk
cd /d "%~dp0"
echo =====================================================================
echo            SAKHI  -  EEE Block Campus Kiosk
echo     Shri Vaishnav Vidyapeeth Vishwavidyalaya, Indore
echo =====================================================================
echo.
echo  Server  : http://localhost:8000
echo  Admin   : http://localhost:8000/admin/
echo  Press CTRL+C to stop.
echo =====================================================================
echo.
start "" "http://localhost:8000"
python main.py
pause
