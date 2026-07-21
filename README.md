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
  deck_conflicts.py               Show cards shared across decks vs. owned (+ buy-doubles)
  wishlist.py                     Consolidated wishlist (shared copies + upgrades) -> data/wishlist.md
  similar_commanders.py           "This commander would also work" — alternates by archetype + color fit
  commander_finder.py             "What should I build next?" — commanders ranked by owned support
data/reference/                   Game Changers + tutor/fast-mana/etc. lists (editable)
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
and a **Cross-Deck Conflicts** panel warning when a card is committed to more decks
than you own copies of.

## Power ranking & cross-deck conflicts

```bash
# Rank every deck by power, with its bracket
python3 scripts/power.py --rank --collection data/collection/collection.csv

# Bracket + power breakdown for one deck
python3 scripts/power.py --deck data/decks/yshtola-nights-blessed.txt \
  --collection data/collection/collection.csv

# Which cards are double-committed across decks beyond the copies you own?
python3 scripts/deck_conflicts.py --collection data/collection/collection.csv
```

Bracket rules and the 53-card Game Changers list are grounded in WotC's official
Commander Bracket system and live in editable `data/reference/*.txt` files.

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

- **Network:** Scryfall API, Scryfall bulk data, and Archidekt API are firewalled in this
  environment. Card verification is via one-at-a-time web search; card images work only as
  browser hotlinks, not server-side fetches.
- **Category counts are heuristic.** `deck_stats.py` classifies ramp/draw/removal/wipe from
  curated name lists + card types. Treat the numbers as a strong first pass, then eyeball.
- **Prices are estimates.** No live pricing source is reachable.
