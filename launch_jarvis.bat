@echo off
title J.A.R.V.I.S. AI System
cd /d "%~dp0"
call venv\Scripts\activate.bat
start /b pythonw main.py
exit
