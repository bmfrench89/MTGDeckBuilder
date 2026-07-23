# Collection data

This folder holds the player's card collection — the source of truth for every
ownership claim (Grounding Rule #1).

## Files

- **`collection_snapshot.txt`** *(committed)* — a name-only snapshot
  (`<quantity> <card name>` per line) exported from the Google Drive doc
  `collection_list`. Good for **ownership counts**. It can't answer color / type /
  tribe / mana-value / pip questions on its own — those need the full CSV.

- **`collection.csv`** *(gitignored — you provide it; may contain purchase prices)* —
  a CSV export. The parser auto-detects two useful flavors:

  1. **Collection + pricing export** (e.g. Archidekt collection / ManaBox): columns like
     `Folder Name, Quantity, Card Name, Set Code, Set Name, Card Number, Condition,
     Printing, Price Bought, Date Bought, LOW, MID, MARKET` (an Excel `sep=,` preamble
     line is handled automatically). **Unlocks: ownership by exact printing, real
     collection value, and per-deck pricing.** Does NOT carry color/type/mana value —
     but **`enrich.bat` fills those in from Scryfall** (see *Enrichment* below), so this
     flavor is now enough on its own.

  2. **Card-attribute export** (the gold standard): columns
     `Quantity, Name, Mana Value, Colors, Identities, Mana cost, Types, Sub-types,
     Super-types, Rarity, Scryfall ID`. **Unlocks: color-identity checks, mana curve,
     colored-pip demand, tribal/type counts, and Scryfall image hotlinks.**

  You can keep both (e.g. `collection.csv` for pricing + `collection_attrs.csv` for
  attributes) and point `--collection` at whichever a given task needs. To get flavor 2
  from Archidekt, export with the card-data columns enabled (Mana Value, Color Identity,
  Type Line, Scryfall ID), not just the pricing columns.

- **`owned_additions.txt`** *(committed)* — cards you own that aren't in the export yet
  (new pickups, post-cutoff cards the exporter missed). One `<qty> <card name>` per line.
  Every script auto-merges this on top of `collection.csv` via `mtglib.load_collection`,
  because your word outranks the export (grounding rule #6). Add here instead of editing the
  raw export — a re-export won't wipe your corrections.

## Enrichment (colors / types / mana value / image ids)

You don't need the special "card-attribute export" anymore. Run **`enrich.bat`** (or
`python scripts/carddb.py --collection <file>`) and it queries Scryfall's
`/cards/collection` API — **~1 request per 75 cards, no ~40 MB download** — resolving
each card by its **exact printing** (Set Code + Card Number, or a Scryfall ID when the
export has one), falling back to the card name. It writes **`collection_attrs.csv`**
(gitignored), which `mtglib.load_collection` auto-merges, so every tool sees real
colors / types / mana value and the correct-art Scryfall id.

- Works from either export flavor **or** the name-only snapshot.
- Offline? `--download-bulk` grabs Scryfall's ~40 MB Oracle Cards file instead, or pass
  a file you already have with `--bulk oracle-cards.json`.
- Re-run it whenever you add cards. See `docs/card-images.md` for how the ids feed images.

## How to export from Archidekt

Archidekt → your Collection → Export → CSV (include all columns). Save it here as
`collection.csv`. Then the scripts and skill use it automatically.

## Refreshing the snapshot

When the collection changes, either drop a new `collection.csv` here, or re-export
the `collection_list` doc from Google Drive and replace `collection_snapshot.txt`.
