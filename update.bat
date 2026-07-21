@echo off
REM One-click update: pull the latest from GitHub and rebuild dashboards + wishlist.
REM Put this at the repo root (it is). Double-click it, or run from a terminal.
cd /d "%~dp0"

echo == Pulling latest from GitHub ==
git pull
if errorlevel 1 (
  echo.
  echo Git pull failed. If you have local edits, commit or stash them first.
  pause
  exit /b 1
)

if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate.bat
pip install -q -r webapp\requirements.txt

set "COLL=data\collection\collection.csv"
if not exist "%COLL%" set "COLL=data\collection\collection_snapshot.txt"

echo.
echo == Rebuilding dashboards + wishlist from %COLL% ==
python scripts\refresh.py --collection "%COLL%"

echo.
echo == Up to date. Run webapp\run.bat to launch the app. ==
pause
