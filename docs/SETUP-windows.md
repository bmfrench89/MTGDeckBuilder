# Windows setup (Documents\Github)

You can't "move" the cloud copy directly — it lives on GitHub. Clone it onto your PC.

## 1. One-time prerequisites
- **Git for Windows** — https://git-scm.com/download/win
- **Python 3.11+** — https://www.python.org/downloads/ (check "Add python.exe to PATH")

## 2. Clone it into your apps folder
Open **PowerShell** (or Git Bash) and run:
```powershell
cd C:\Users\bmfre\Documents\Github
git clone https://github.com/bmfrench89/MTGDeckBuilder.git
cd MTGDeckBuilder
```
That creates `C:\Users\bmfre\Documents\Github\MTGDeckBuilder`.

## 3. Add your private collection file
The pricing export isn't in git (it has your prices). Drop your Archidekt CSV here:
```
C:\Users\bmfre\Documents\Github\MTGDeckBuilder\data\collection\collection.csv
```
(If you don't have it handy, re-export from Archidekt. Without it, the tools still run in
name-only mode off the committed snapshot.)

## 4. Run the web app
Double-click `webapp\run.bat`, **or**:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r webapp\requirements.txt
python webapp\app.py
```
Open http://127.0.0.1:5000 . `run.bat` also prints a `http://192.168.x.x:5000` URL you can open
on your phone (same Wi-Fi).

## 5. (Optional) full card data
Download "Oracle Cards" JSON from https://scryfall.com/docs/api/bulk-data, then:
```powershell
pip install duckdb
python scripts\carddb.py --bulk oracle-cards.json --collection data\collection\collection.csv --stats
```
This enriches the whole collection (colors/types/mana values) so every curve/power/compat number
becomes exact.

## Keeping it in sync
Pull future updates with `git pull`. Your `collection.csv` and `build\` stay local (gitignored).
