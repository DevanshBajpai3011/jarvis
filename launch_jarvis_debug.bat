@echo off
title J.A.R.V.I.S. AI System (Debug Mode)
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo ===================================================
echo   Starting J.A.R.V.I.S. with live console logs...
echo ===================================================
python main.py
pause
