# MTG Commander Deckbuilder

An end-to-end toolkit for building **Magic: The Gathering Commander (EDH)** decks from
*your* collection: a stdlib-only Python analysis engine, a local Flask web app, and a
Claude skill that drives both. The guiding principle throughout: **every claim is
grounded** — ownership is checked against the real collection, uncertain card text gets
verified, and prices are labeled as estimates.

---

## The three layers

1. **`scripts/`** — the engine. Stdlib-only Python 3 (CI enforces this): collection and
   deck parsing, curve/pip/role analysis, power scoring and WotC bracket estimation,
   hypergeometric manabase math, combo detection, deck optimization, full-deck
   auto-building, and self-contained HTML dashboards.
2. **`webapp/`** — a Flask front end over the same scripts (imported, not duplicated):
   a power leaderboard, live editable dashboards, wishlist, collection browser, and
   "Build Next". Installable on a phone as a PWA.
3. **`.claude/skills/`** — the `mtg-deckbuilder` skill: a grounded build/coach workflow
   that runs these CLIs rather than reimplementing them (plus `mtg-mobile` for phone
   setup).

Architecture map and per-module reference: `docs/codemap.md`. Data formats and working
rules: `CLAUDE.md`.

## Quickstart

Everything in `scripts/` is stdlib Python 3 — no install step for the CLI tools.

```bash
# What do I own? (works on the committed name-only snapshot)
python3 scripts/analyze_collection.py data/collection/collection_snapshot.txt

# How many of a tribe do I really own?
python3 scripts/analyze_collection.py data/collection/collection_snapshot.txt --name dragon --list

# Analyze a deck: curve, pips, roles, and what you don't own
python3 scripts/deck_stats.py --deck data/decks/yshtola-nights-blessed.txt \
  --collection data/collection/collection_snapshot.txt

# Rank every deck by power, with its estimated bracket
python3 scripts/power.py --rank --collection data/collection/collection_snapshot.txt
```

Every script takes `--help`; most analysis tools also take `--json`.

### Web app

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r webapp/requirements.txt      # Flask is the only dependency
python3 webapp/app.py                        # -> http://127.0.0.1:5000
```

Windows: double-click `webapp\run.bat` (full guide: `docs/SETUP-windows.md`).
Phone access and hosting options: `webapp/README.md` and `docs/mobile.md`.

### Tests

```bash
pip install -r requirements-dev.txt && pytest    # offline, hermetic; CI runs 3.11 + 3.13
```

## Unlock full analysis: add a collection CSV

The committed `data/collection/collection_snapshot.txt` is **name + quantity only** — it
answers ownership, nothing more. A CSV export at `data/collection/collection.csv`
unlocks color, type, tribe, curve, and pip analysis; **exports from Sorted /
Dragon Shield, ManaBox, Moxfield, Deckbox, Archidekt/ManaPool, and TCGplayer are all
read directly** (`docs/collection-formats.md`). That file is **gitignored — it stays
on your machine**.

**Basic lands are assumed unlimited and are not tracked.** You are expected to own as many
`Forest` / `Island` / `Swamp` / `Mountain` / `Plains` / `Wastes` as any deck needs, so
basics never appear on a buy list or wishlist and never limit a manabase — whatever count
an export happens to carry is ignored.

No rich export? `carddb.py` builds the attributes from Scryfall's `/cards/collection`
API (about one request per 75 cards):

```bash
python3 scripts/carddb.py --collection data/collection/collection.csv --stats
```

It writes `data/collection/collection_attrs.csv` (also gitignored), which
`mtglib.load_collection` merges automatically. Uploading an export through the web app's
Collection page runs the same enrichment. Besides colors/types/mana value it records
**`Produced`** (what each card actually taps for) and **`Flags`** (oracle-derived:
enters-tapped, mana rock/dork, ramp, draw), so colored-source counts stop approximating a
land's output from its color identity — and where that data is missing, every surface
labels the count "identity approx." rather than implying precision.

## What the tools do

- **Dashboards** (`build_dashboard.py`) — one self-contained HTML file per deck: stat
  tiles, mana curve, colored-pip demand vs. sources, ownership, an estimated
  bracket (1–5) and 0–100 power score (`docs/power-and-brackets.md`), Combo Watch
  (complete and one-away combos), cross-deck conflicts, and a decklist grouped by the
  deck file's own sections. Every card opens a panel with a fit score, a grounded
  "why it works" blurb, alternatives, and buy links. Card images are browser hotlinks
  to Scryfall's CDN (`docs/card-images.md`). Themes: `default`, `yshtola`, `cloud`,
  `rakdos`, `spider`.
- **Manabase math** (`manabase.py`) — hypergeometric keepable-hand odds and
  color-source adequacy against Karsten-style targets.
- **Combos** (`combo_detector.py` + curated `data/reference/combos.csv`, plus a
  Commander Spellbook client) — complete or one-piece-away combos per deck or across
  the whole pool; a cheap complete two-card combo is what pushes a deck's bracket up.
- **Cross-deck conflicts** (`deck_conflicts.py`) — cards committed to more decks than
  you own copies of; `pins.csv` can reserve a copy for one deck.
- **Optimizer** (`optimize.py`) — swaps low-value cards for higher-inclusion owned
  cards using EDHREC field data, with hard guardrails (commander/basics/game-plan
  cards protected, role counts kept in range, lands only for lands, idempotent). It
  runs automatically after saves from Build Next and via the app's ⚡ button — never
  after a manual edit, which is always kept as-is.
- **Build Next** (`commander_finder.py` + `auto_build.py`) — ranks commanders by owned
  support and assembles a legal 100-card deck from the owned pool.
- **Field data** (`edhrec.py`) — per-commander inclusion % and synergy. Three-tier
  sourcing: live fetch → disk cache → committed snapshots in `data/reference/field/`
  (refreshed weekly by a GitHub Action), so the signal works even where EDHREC is
  unreachable.
- **Wishlist** (`wishlist.py`) — consolidated copies-to-buy + per-deck upgrades, with
  ManaPool-format export.

## Data

- `data/decks/*.txt` — deck files with `# Key: value` headers and `# --- Section ---`
  groups; optional companions per deck: `.notes.md` (game plan; cards named there are
  protected from the optimizer), `.buylist.csv`, `.attrs.csv`, `.changes.csv` (change
  history, appended by the optimizer).
- `data/reference/` — hand-editable knowledge: curated combos, card notes, the official
  Game Changers list, tutors, role staples, commander candidates, field snapshots.
- `data/collection/` — the committed name-only snapshot plus your private, gitignored
  CSV exports. `owned_additions.txt` records cards the export missed; `pins.csv`
  reserves copies.

## Known limitations

- **Role/category counts are heuristic** — curated name lists plus card types. Strong
  first pass; verify before relying on the numbers.
- **Prices are estimates.** No live pricing feed is wired in.
- **Network access degrades, never crashes.** Scryfall, EDHREC, and Commander Spellbook
  clients are disk-cached and fall back gracefully (EDHREC additionally to the
  committed snapshots). Card images require a browser — the server never fetches them.
