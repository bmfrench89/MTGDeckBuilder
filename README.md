# MTG Commander Deckbuilder

An end-to-end program for building **Magic: The Gathering Commander (EDH)** decks from
*your* collection — grounded by a Claude skill that role-plays a **40-year veteran and
former World Champion**, and backed by Python tools that do the counting and math so
nothing is eyeballed or guessed.

The guiding principle, learned the hard way (see `docs/handoff.md`): **a champion never
bluffs their own deck.** Every ownership claim is checked against your real collection;
every uncertain card gets verified; every price is labeled an estimate.

---

## What's in here

```
.claude/skills/mtg-deckbuilder/   The skill: persona, grounded workflow, reference knowledge
  SKILL.md                        Entry point — persona + the build loop
  references/
    persona.md                    Voice & philosophy of the champion
    grounding-rules.md            The non-negotiables (read first, every session)
    deckbuilding-principles.md    EDH ratios, curve, roles, power brackets, archetypes
    rules-reference.md            Specific rules facts that were gotten wrong & corrected
    tooling-and-data.md           Network limits, Scryfall image hotlinks, price disclaimers
scripts/                          The engine (stdlib-only Python 3)
  mtglib.py                       Shared parsing + pip math + category heuristics
  analyze_collection.py           Pool stats & tribal/type/color counts ("what can I build?")
  deck_stats.py                   Curve, pip demand, category counts, ownership check
  card_image.py                   Scryfall ID -> hotlinkable card-image URL
  build_dashboard.py              Deck -> rich HTML dashboard (+ visual gallery)
  staples_crossref.py             Staples list vs collection -> owned/missing buy-list
  power.py                        Bracket (1-5) + 0-100 power score; rank all decks
  combo_detector.py               Detect infinite / 2-card combos in a deck or collection (feeds the bracket)
  deck_conflicts.py               Show cards shared across decks vs. owned (+ buy-doubles)
  wishlist.py                     Consolidated wishlist (shared copies + upgrades) -> data/wishlist.md
  similar_commanders.py           "This commander would also work" — alternates by archetype + color fit
  commander_finder.py             "What should I build next?" — commanders ranked by owned support
  carddb.py                       Enrich the whole collection (colors/types/MV/ids) via Scryfall's /cards/collection API
data/reference/                   Game Changers, tutor/fast-mana/combo lists + card_notes (all editable)
data/wishlist.md                  Auto-generated shopping list (shared copies + upgrades)
data/
  collection/                     Your collection (snapshot committed; full CSV you provide)
  decks/                          Saved deck lists (two completed decks preserved here)
docs/handoff.md                   The running session handoff from the prior build
```

## How the skill activates

In a Claude Code / Claude session with this repo, the `mtg-deckbuilder` skill triggers
when you ask to build/tune/analyze a Commander deck, evaluate your collection, get
recommendations or a buy list, check a card, or generate a dashboard. It then follows the
grounded workflow in `SKILL.md`. You don't have to invoke it manually — but you can:
just say what you want ("build me a Rakdos punisher deck", "what can I build?", "tune my
Cloud manabase", "make a dashboard for Y'shtola").

## Quickstart (the tools, run directly)

Everything is stdlib Python 3 — no install step.

```bash
# 1) What do I own? (works on the committed name-only snapshot)
python3 scripts/analyze_collection.py data/collection/collection_snapshot.txt

# 2) How many <tribe> do I really own? (the "don't recommend Ur-Dragon" check)
python3 scripts/analyze_collection.py data/collection/collection_snapshot.txt --name dragon --list

# 3) Analyze a deck: curve, pips, categories, and what you DON'T own
python3 scripts/deck_stats.py \
  --deck data/decks/yshtola-nights-blessed.txt \
  --collection data/collection/collection_snapshot.txt

# 4) Build a shareable dashboard (open the .html in a browser)
python3 scripts/build_dashboard.py \
  --deck data/decks/yshtola-nights-blessed.txt \
  --collection data/collection/collection_snapshot.txt \
  --title "Y'shtola, Night's Blessed" --commander "Y'shtola, Night's Blessed" \
  --theme yshtola --out yshtola-dashboard.html --visual
```

### Unlock full analysis: add your Archidekt CSV

The committed `collection_snapshot.txt` is **name + quantity only**, so it answers
*ownership* but not color / type / tribe / curve / pip questions. Export your collection
from **Archidekt as CSV** (columns: `Quantity, Name, Mana Value, Colors, Identities, Mana
cost, Types, Sub-types, Super-types, Rarity, Scryfall ID`), drop it at
`data/collection/collection.csv`, and re-run any command with
`--collection data/collection/collection.csv`. That turns on:

- real tribal/type counts (`analyze_collection.py --subtype Dragon`, `--tribes`),
- mana curve + colored **pip demand vs. sources** in `deck_stats.py`,
- Scryfall card images in the visual gallery.

## Rich dashboards + companion files

`build_dashboard.py` produces a sectioned dashboard: stat tiles (incl. deck value),
a **Game Plan / player notes** section, a **mana-curve (MV spread)**, ownership, an
interactive **Buy & Replace** panel with **price-threshold toggles** (All / ≤$5 / ≤$10 /
…), and a **decklist grouped by the deck file's own sections**. It auto-detects three
optional companion files next to `<deck>.txt`:

- `<deck>.notes.md` — player notes / game plan (markdown-lite: `#` headings, `-` bullets,
  `**bold**`). Rendered as the Game Plan section.
- `<deck>.buylist.csv` — columns `Card,Price,Tier,Replaces,Reason`. Drives the interactive
  Buy & Replace panel; the toggles filter by price and show a running total.
- `<deck>.attrs.csv` — columns `Name,Type,MV,Colors`. Powers the MV spread without the full
  collection CSV (cards without an entry are noted, not hidden). See
  `data/decks/cosmic-spider-man.attrs.csv` for the pattern.

```bash
python3 scripts/build_dashboard.py --deck data/decks/cosmic-spider-man.txt \
  --collection data/collection/collection.csv --theme spider \
  --title "Cosmic Spider-Man" --out cosmic.html   # notes/buylist/attrs auto-detected
```

The dashboard also shows, for every deck: **card images** in the decklist, a
**Commander Bracket (1–5)** and **0–100 power score** (see `docs/power-and-brackets.md`),
a **Combo Watch** panel (complete or one-piece-away infinite combos), and a
**Cross-Deck Conflicts** panel warning when a card is committed to more decks
than you own copies of. Clicking a card opens a panel with a curated "why it works"
blurb and alternatives (from `data/reference/card_notes.csv`).

## Power ranking & cross-deck conflicts

```bash
# Rank every deck by power, with its bracket
python3 scripts/power.py --rank --collection data/collection/collection.csv

# Bracket + power breakdown for one deck
python3 scripts/power.py --deck data/decks/yshtola-nights-blessed.txt \
  --collection data/collection/collection.csv

# Which cards are double-committed across decks beyond the copies you own?
python3 scripts/deck_conflicts.py --collection data/collection/collection.csv

# Which infinite / 2-card combos are complete — or one piece away — in a deck?
python3 scripts/combo_detector.py --deck data/decks/yshtola-nights-blessed.txt \
  --collection data/collection/collection.csv
python3 scripts/combo_detector.py --all --collection data/collection/collection.csv
python3 scripts/combo_detector.py --collection data/collection/collection.csv \
  --collection-combos          # everything your whole pool can already assemble
```

Bracket rules and the 53-card Game Changers list are grounded in WotC's official
Commander Bracket system and live in editable `data/reference/*.txt` files. The combo
definitions are curated in `data/reference/combos.csv` (`Pieces` are `;`-separated so
card-name commas stay intact); a **complete, cheap two-card** combo is the signal that
pushes a deck to Bracket 4.

## Card database (optional) — do we need a backend DB?

**Short answer: no database for the app's own data.** The collection (~2,800 rows), decks,
and reference tables are tiny and read-mostly; parsing CSV/txt into memory is instant, and
keeping the files as the source of truth means everything is diffable in git and portable.

**Where a DB earns its place: ingesting real card attributes.** The pricing export has no
card attributes (colors/types/mana value). `carddb.py` fixes that — **by default it queries
Scryfall's `/cards/collection` API** (no download, ~1 request per 75 cards), resolving each
owned card by its exact printing:

```bash
python3 scripts/carddb.py --collection data/collection/collection.csv --stats
# offline instead? --download-bulk grabs the ~40 MB Oracle Cards file (DuckDB streams it if installed)
python3 scripts/carddb.py --collection data/collection/collection.csv --download-bulk
```

That writes `data/collection/collection_attrs.csv` (gitignored — it's derived + personal),
which `mtglib.load_collection` auto-merges. From then on **every tool** works collection-wide —
real mana curves, colored pip demand, tribal/type counts, power color-scores, and exact
similar-commander color-fit %. Uploading a fresh export in the web app auto-enriches it.
(No SQL database for the app's own data — the files stay the diffable source of truth; SQLite
would only be warranted if we add write-heavy app state like saved deck versions / edit history.)

## Web app (local front end)

A Flask app in `webapp/` puts a front end over the same scripts (imported, not
duplicated) — a power leaderboard, live deck dashboards, the wishlist, a shared-cards
view, and a collection page where you can upload a new export or add owned-but-missing
cards. It runs locally so your collection + prices stay on your machine.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r webapp/requirements.txt
python3 webapp/app.py            # -> http://127.0.0.1:5000
```

Editing a decklist in the UI re-analyzes it instantly (curve, bracket, power, shared
cards). See `webapp/README.md`. The CLI and the app share `build_dashboard.generate()`,
so both render identical dashboards.

## The two completed decks (preserved)

- **`data/decks/yshtola-nights-blessed.txt`** — Esper (WUB) control/drain.
- **`data/decks/cloud-ex-soldier.txt`** — Naya (RGW) equipment/Voltron.

Both are reconstructed from `docs/handoff.md`. Regenerate their dashboards anytime with
`build_dashboard.py` (themes `yshtola` and `cloud` match the original aesthetics).

## Grounding, in one paragraph

The collection is the source of truth. Count the pool — never spot-check staples (owning
one Ur-Dragon is not a dragon deck). Verify card text for anything recent (Marvel,
Spider-Man, Final Fantasy, Avatar, Lorwyn Eclipsed, newer Strixhaven) with a web search —
one card at a time. Do the manabase math against real pip demand. Prefer destroy-based
wipes when the deck wants its creatures in the graveyard. Be honest about tool limits:
Scryfall/Archidekt APIs and price sites are blocked here, so prices are labeled estimates
and card-image galleries only render in a real browser. Full detail lives in
`.claude/skills/mtg-deckbuilder/references/`.

## Known limitations

- **Network:** Scryfall reachability depends on where the app runs. On a normal machine
  `carddb.py` enriches via Scryfall's `/cards/collection` API and the EDHREC / Commander
  Spellbook clients work; in a locked-down sandbox those may be proxy-blocked (fall back to
  `carddb.py --download-bulk`). Card images always load as browser hotlinks, not server fetches.
- **Category counts are heuristic.** `deck_stats.py` classifies ramp/draw/removal/wipe from
  curated name lists + card types. Treat the numbers as a strong first pass, then eyeball.
- **Prices are estimates.** No live pricing source is reachable.
