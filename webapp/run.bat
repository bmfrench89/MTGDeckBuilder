@echo off
REM MTG Deckbuilder launcher for Windows. Double-click, or run from a terminal.
REM Sets up a venv, installs Flask, and serves on your network so your phone can reach it.
cd /d "%~dp0.."
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate.bat
pip install -q -r webapp\requirements.txt
if "%MTG_HOST%"=="" set MTG_HOST=0.0.0.0
if "%MTG_PORT%"=="" set MTG_PORT=5000
python webapp\app.py
pause
