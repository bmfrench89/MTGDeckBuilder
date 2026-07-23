@echo off
REM One-click card-DB enrichment. Queries Scryfall's /cards/collection API
REM (~1 request per 75 cards, NO ~40 MB download) and writes
REM data\collection\collection_attrs.csv, which every tool auto-merges — giving your
REM WHOLE collection real colors / types / mana value / exact-printing Scryfall image
REM ids. Run this once, and again whenever you add new cards.
cd /d "%~dp0"

if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate.bat
pip install -q -r webapp\requirements.txt

set "COLL=data\collection\collection.csv"
if not exist "%COLL%" set "COLL=data\collection\collection_snapshot.txt"

echo.
echo == Enriching %COLL% from the Scryfall API (no download) ==
python scripts\carddb.py --collection "%COLL%" --stats
if errorlevel 1 (
  echo.
  echo Enrichment failed. If you're offline, download "Oracle Cards" JSON from
  echo https://scryfall.com/docs/api/bulk-data and pass it with --bulk,
  echo or run:  python scripts\carddb.py --collection "%COLL%" --download-bulk
  pause
  exit /b 1
)

echo.
echo == Rebuilding dashboards so the new data shows up ==
python scripts\refresh.py --collection "%COLL%" --no-visual

echo.
echo == Done. Restart the web app (webapp\run.bat) and hard-refresh your browser. ==
pause
