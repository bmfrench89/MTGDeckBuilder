# MTG Deckbuilder — local web app

A front end over the analysis scripts. Runs on your machine so your collection +
prices stay private. The MTG logic is 100% the existing `scripts/` (imported, not
duplicated); this is just Flask routing + templates.

## Run

**Windows:** double-click `webapp\run.bat` (or see `docs/SETUP-windows.md` for the full
clone-and-run guide). **macOS/Linux:**

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

## 📱 Run it on your phone

The app is responsive and installable. Pick the path that fits:

### 1. Same Wi-Fi (easiest, recommended)
Run the server on your computer, bound to your network, and open your computer's LAN
address on the phone.

```bash
./webapp/run.sh            # sets up the venv and binds to 0.0.0.0, prints the phone URL
# or manually:
MTG_HOST=0.0.0.0 python3 webapp/app.py
```

On startup it prints something like `on your phone : http://192.168.1.42:5000`. Type that
into your phone's browser (phone + computer on the same Wi-Fi). The computer must stay on
and running the app.

**Add to Home Screen:** in the phone browser, use Share → *Add to Home Screen*. Thanks to
the web manifest it opens full-screen like a native app (spider-web icon and all).

⚠️ Binding to `0.0.0.0` lets **anyone on your network** reach it. Fine on a home Wi-Fi;
on untrusted networks, don't — or put it behind a token/reverse proxy.

### 2. From anywhere, temporarily — a tunnel
Keep the server local and expose a public HTTPS URL with a tunnel tool:

```bash
python3 webapp/app.py                 # localhost:5000 (leave MTG_HOST as default)
# in another terminal, one of:
cloudflared tunnel --url http://localhost:5000
ngrok http 5000
```

Open the tunnel's `https://…` URL on your phone. Great for quick testing; the URL changes
each run and the tunnel/computer must stay up.

### 3. Always-on — deploy it
Host on a small platform (Render, Railway, Fly.io, PythonAnywhere, a VPS) with a real WSGI
server (`gunicorn webapp.app:app`). If you do this, **protect your data**: keep
`collection.csv` out of the public repo (it's gitignored), add authentication, and serve
over HTTPS. It's your personal collection + prices.

## Note on the dev server
`app.run(...)` is Flask's development server — fine for local/LAN personal use. For a real
deployment use gunicorn/uwsgi behind HTTPS.
