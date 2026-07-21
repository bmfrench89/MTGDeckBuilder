@echo off
REM One-click card-DB enrichment. Downloads the Scryfall "Oracle Cards" bulk file
REM (~40 MB, cached) and writes data\collection\collection_attrs.csv, which every
REM tool auto-merges — giving your WHOLE collection real colors / types / mana value /
REM Scryfall image ids. Run this once, and again whenever you add new cards.
cd /d "%~dp0"

if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate.bat
pip install -q -r webapp\requirements.txt
REM DuckDB streams the big JSON efficiently; optional (stdlib json works too).
pip install -q -r scripts\requirements-optional.txt 2>nul

set "COLL=data\collection\collection.csv"
if not exist "%COLL%" set "COLL=data\collection\collection_snapshot.txt"

echo.
echo == Enriching %COLL% from Scryfall (first run downloads ~40 MB) ==
python scripts\carddb.py --collection "%COLL%" --stats
if errorlevel 1 (
  echo.
  echo Enrichment failed. If you're offline, download "Oracle Cards" JSON from
  echo https://scryfall.com/docs/api/bulk-data and pass it with --bulk.
  pause
  exit /b 1
)

echo.
echo == Rebuilding dashboards so the new data shows up ==
python scripts\refresh.py --collection "%COLL%" --no-visual

echo.
echo == Done. Restart the web app (webapp\run.bat) and hard-refresh your browser. ==
pause
