# MTG Deckbuilder — web app

A front end over the analysis scripts. The MTG logic is 100% the existing `scripts/`
(imported, not duplicated); this layer is Flask routing + templates. Run it locally and
your collection and prices stay on your machine.

## Run

**Windows:** double-click `webapp\run.bat` (or see `docs/SETUP-windows.md` for the full
clone-and-run guide). **macOS/Linux:**

```bash
python3 -m venv .venv && source .venv/bin/activate    # recommended
pip install -r webapp/requirements.txt
python3 webapp/app.py                                  # -> http://127.0.0.1:5000
```

Config via env vars:
- `MTG_COLLECTION` — collection file (default: `data/collection/collection.csv` if
  present, else the committed name-only snapshot)
- `MTG_DECKS_DIR` — deck folder (default `data/decks`)
- `MTG_PORT` — port (default 5000)
- `MTG_HOST` — bind address (default `127.0.0.1`; `0.0.0.0` allows LAN/phone access)
- `MTG_AUTO_SYNC` — force the in-app GitHub sync on (`1`) or off (`0`); by default it
  is on only when a PythonAnywhere host is detected (`docs/spec-in-app-sync.md`)
- `MTG_PASSWORD` — when set, every page requires a one-time sign-in per device
  (shared password, 90-day session; `docs/spec-auth-gate.md`). Unset = no gate,
  for local use.

## Pages

- **Decks** — power leaderboard (bracket + score) with filters; each deck opens a live
  dashboard with six tabs (Deck / Mana / Power / Buy / Plan / More), in-place card
  Remove/Replace/Add via the card panel, an add-card advisor, and one-click optimize.
- **Build Next** — commanders ranked by owned support; auto-builds a full 100 for any
  of them, ready to tweak and save.
- **Wishlist** — copies-to-buy + not-owned + per-deck upgrades, with ManaPool-format
  export (copy or download `qty name` text).
- **Shared** — cards used across decks beyond owned copies, priced.
- **Collection** — value + searchable browser, upload a fresh export (all major app
  formats accepted — `docs/collection-formats.md` — and auto-enriched via Scryfall),
  add owned-but-missing cards.
- **Mobile** — in-app instructions for installing the PWA on a phone.

Editing a decklist and saving re-analyzes it instantly (curve, bracket, power, shared
cards). Everything is rendered live; the Decks page's maintenance card can also rebuild
the static `build/` dashboards + `data/wishlist.md`, and — on a hosted deploy — sync
deck edits to GitHub.

## Run it on your phone

The app is responsive and installable as a PWA. Three options:

### 1. Same Wi-Fi
```bash
./webapp/run.sh            # sets up the venv, binds to 0.0.0.0, prints the phone URL
```
Open the printed `http://<lan-ip>:5000` on the phone, then *Add to Home Screen*.
⚠️ Binding to `0.0.0.0` lets **anyone on your network** reach the app — fine on a home
Wi-Fi, not on untrusted networks.

### 2. A temporary tunnel
```bash
python3 webapp/app.py
cloudflared tunnel --url http://localhost:5000   # or: ngrok http 5000
```
Public HTTPS URL while the tunnel runs; the URL changes each run.

### 3. Always-on hosting
The app runs on any WSGI host (`webapp/pa_wsgi.py` is a ready entry point;
`docs/plan-pythonanywhere-deploy.md` documents a complete free-tier PythonAnywhere
setup, including the daily GitHub sync). **On any hosted copy, set `MTG_PASSWORD`
in the server environment** so the app requires a sign-in (`docs/spec-auth-gate.md`)
— without it, anyone who finds the URL can read and edit everything. Also keep the
private collection CSV out of git (it is gitignored) and treat the URL as sensitive.

## Note on the dev server

`app.run(...)` is Flask's development server — fine for local/LAN personal use. Hosted
deploys should run under a real WSGI server (PythonAnywhere provides uWSGI).
