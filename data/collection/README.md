# Collection data

This folder holds the player's card collection — the source of truth for every
ownership claim (Grounding Rule #1).

## Files

- **`collection_snapshot.txt`** *(committed)* — a name-only snapshot
  (`<quantity> <card name>` per line) exported from the Google Drive doc
  `collection_list`. Good for **ownership counts**. It can't answer color / type /
  tribe / mana-value / pip questions on its own — those need the full CSV.

- **`collection.csv`** *(gitignored by default — you provide it)* — the **full
  Archidekt export**. This is the gold standard. Columns:
  `Quantity, Name, Mana Value, Colors, Identities, Mana cost, Types, Sub-types,
  Super-types, Rarity, Scryfall ID`. It unlocks curve, pip demand, tribal counts,
  and Scryfall image hotlinks (via the Scryfall ID column).

## How to export from Archidekt

Archidekt → your Collection → Export → CSV (include all columns). Save it here as
`collection.csv`. Then the scripts and skill use it automatically.

## Refreshing the snapshot

When the collection changes, either drop a new `collection.csv` here, or re-export
the `collection_list` doc from Google Drive and replace `collection_snapshot.txt`.
