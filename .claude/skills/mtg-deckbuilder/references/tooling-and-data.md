# Tooling & Data Sources — what works, what's blocked

Know these limits so you neither waste time on blocked calls nor fabricate around them.

## Network reality — depends where Claude Code is running (test, don't assume)
Reachability to Scryfall/Archidekt **varies by environment.** A quick probe beats guessing.
- On a **normal machine** (the player's own — the common case): outbound HTTPS to Scryfall
  works. `python scripts/carddb.py --collection <file>` enriches the WHOLE collection via the
  **`/cards/collection` API** (no ~40 MB download), resolving each card by exact printing →
  real colors / types / mana value / correct-art Scryfall id. Verified 2040/2040 live.
- In a **locked-down sandbox** (some CI): the Scryfall/Archidekt API + bulk data may be
  **proxy-blocked** (403 on CONNECT). Then fall back to `carddb.py --bulk oracle-cards.json`
  (a local file), `WebSearch`/`WebFetch` for one-off oracle text, and the committed snapshot.
- **What works everywhere:**
  - The **collection file** (CSV or name-only list) — always available locally / via Drive.
  - **`WebSearch` / `WebFetch`** for oracle text and rulings — one card at a time. `WebFetch`
    generally only accepts URLs that appeared in a prior search result; don't hand-build URLs
    from memory and expect them to fetch.
  - **Google Drive tools** — the player's `collection_list` doc lives here.
  - **Scryfall image *hotlinking*** in generated HTML — the URL renders in the player's real
    browser even if the current env can't fetch it. Build the URL from the card's Scryfall ID
    (see below) and put it in an `<img>` tag.

## Scryfall image hotlink URL (from a Scryfall ID)
Given a Scryfall ID like `a1b2c3d4-...`, the normal-size front image is:
```
https://cards.scryfall.io/normal/front/<id[0]>/<id[1]>/<id>.jpg
```
i.e. first hex char / second hex char / full-id.jpg. `card_image.py` builds this for you.
Sizes: `small`, `normal`, `large`, `png`, `art_crop`. Backs use `/back/`.

## Card-image HTML rendering
- Card galleries that hotlink Scryfall images will **NOT render in the chat/preview pane**
  (external images are blocked there). **Always warn the player** that the visual deck file only
  displays in a real browser (Chrome/Safari/Edge). Self-contained dashboards with no external
  images render anywhere.
- **Loading MANY images at once (a grid / decklist): batch-resolve, never fire one request
  per card.** Scryfall's by-name endpoint is rate-limited (~2/s), so ~100 `<img>` loads get
  429'd and drop out (blank / just the card name). Resolve names → CDN URLs in batches via
  `POST /cards/collection` (≤75/request); a single image (a panel) can use one by-name fetch.
  The dashboards + web app already do this. **Full rules + why: `docs/card-images.md` (repo root).**

## Prices
- **TCGplayer / Card Kingdom / MTGGoldfish are login-walled / blocked.** You cannot pull live
  quotes. Give clearly **labeled estimate ranges** ("~$8–12, early-2026 estimate") and never
  present an estimate as a live price. Cap buy-list suggestions at whatever budget the player sets.

## Data locations in this repo
- `data/collection/` — drop the Archidekt CSV here (e.g. `collection.csv`). A name-only
  `collection_snapshot.txt` is committed as a fallback.
- `data/decks/` — save finished/in-progress deck lists here (`<name>.txt`, one card per line,
  optional leading quantity).
- `docs/handoff.md` — running session handoff; update it when a deck changes.
