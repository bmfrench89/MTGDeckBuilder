# MTG Deckbuilder — local web app

A front end over the analysis scripts. Runs on your machine so your collection +
prices stay private. The MTG logic is 100% the existing `scripts/` (imported, not
duplicated); this is just Flask routing + templates.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate    # recommended
pip install -r webapp/requirements.txt
python3 webapp/app.py                                  # -> http://127.0.0.1:5000
```

Config via env vars:
- `MTG_COLLECTION` — path to the collection CSV (default `data/collection/collection.csv`)
- `MTG_DECKS_DIR` — deck folder (default `data/decks`)
- `MTG_PORT` — port (default 5000)

## Pages
- **Decks** — power leaderboard (bracket + score); click into any live dashboard, or its image gallery, or edit it.
- **Wishlist** — copies-to-buy + not-owned + per-deck upgrades, with checkboxes.
- **Shared** — cards used across decks beyond owned copies, priced.
- **Collection** — value + top cards, upload a new export, add owned-but-missing cards.

Editing a decklist and saving re-analyzes it instantly (curve, bracket, power, shared cards).
Everything is rendered live; the "Rebuild" button also writes the static `build/` dashboards
and `data/wishlist.md`.

## Note on hosting
Built to run locally. If you ever host it, keep `collection.csv` (purchase prices) out of any
public deployment and add authentication — it's your personal data.
