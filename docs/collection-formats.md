# Collection CSV formats — what the app accepts

**Status:** ☑ shipped 2026-08-10 · code: `mtglib._parse_csv` (header aliases +
`_price_header` + game filter) · tests: `tests/test_import_formats.py`

The collection loader reads CSV exports from the major collection apps **directly** —
no conversion step. Upload through the app's Collection page or drop the file at
`data/collection/collection.csv`; either way it stays private (gitignored).

## How it works

There is one parser, in the data hub (`mtglib`), so every consumer — CLI tools, the
web app, enrichment — accepts every format identically. Three mechanisms:

1. **Header aliases.** Each field the app cares about (quantity, name, set code,
   collector number, Scryfall ID, rarity, price, …) matches a list of known header
   spellings across apps. Unknown extra columns are simply ignored.
2. **Price preference.** Price headers vary the most, so they get special handling:
   exact known names first (`MARKET`, `Purchase Price`, …), then any live-market
   column (e.g. Sorted's `Current Price (tcgplayer_marketsellprice)`), then any
   other price column — with "price bought" history last, because scanned cards
   usually carry `0.00` there and it would value the collection at nothing.
3. **Game filter.** Multi-TCG apps (Sorted) export every game in one file with a
   `Collection`/`Game` column; only Magic rows load. An Excel `sep=,` preamble
   line is also handled.

Rows are one-per-printing; the loader aggregates by card name (summed quantity,
summed value, max unit price as representative). Set code + collector number are
kept so **enrichment resolves the exact printing** — attributes the export lacks
(colors, types, mana value) come from Scryfall via `carddb.py` / the upload page's
auto-enrichment, so attribute-less formats still unlock full analysis.

## Verified formats

| App | Signature columns | Notes |
|---|---|---|
| **Sorted** (Dragon Shield's successor) | `Card Name`, `Quantity`, `Set Code`, `Collection` | verified against a real 3,209-row export: names, quantities, printings, market prices, game filter |
| Dragon Shield (legacy) | `Card Name`, `Folder Name`, `Price Bought` | price-bought used only when no market column exists |
| ManaBox | `Name`, `Scryfall ID`, `Set code` | exact printing via Scryfall ID |
| Moxfield | `Count`, `Name`, `Edition` | |
| Deckbox | `Count`, `Edition Code`, `My Price` | set code preferred over set name |
| Archidekt / ManaPool | `Quantity`, `Name`, `Scryfall ID` (+ attribute columns) | the app's native rich format |
| TCGplayer | `Simple Name`, `Set Code` | |

Anything else with a recognizable quantity + name column loads in name-only mode
(ownership answers, no attributes until enriched). A file with neither is rejected
by the CSV/namelist auto-detection, not silently misread.

## What the export's prices mean here

Prices are **estimates** (the app has no live feed): whatever the exporting app
last knew, frozen at export time. The dashboard labels them accordingly.
