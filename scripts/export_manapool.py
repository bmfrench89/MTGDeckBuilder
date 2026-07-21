#!/usr/bin/env python3
"""Export plain-text card lists in the format ManaPool's bulk/deck importer eats:
one card per line as `<qty> <name>`. No prices, no set codes — just quantities and
names, which is the near-universal decklist format ManaPool (and Arena/MTGO) accept.

Two things you'd actually paste into ManaPool:
  • a whole deck  (buy the 100)          -> --deck data/decks/foo.txt
  • your buy list (cards you still need) -> --wishlist --collection coll.csv

Usage:
  python3 export_manapool.py --deck data/decks/cosmic-spider-man.txt
  python3 export_manapool.py --wishlist --collection data/collection/collection.csv
  python3 export_manapool.py --wishlist --collection coll.csv --out buy.txt
"""
import argparse
import os
import sys

import mtglib
import wishlist as wl


def _fmt(lines):
    """lines: list of (qty, name) -> ManaPool text, de-duplicated & summed by name."""
    agg = {}
    order = []
    for qty, name in lines:
        name = (name or "").strip()
        if not name:
            continue
        k = mtglib._norm(name)
        if k not in agg:
            agg[k] = [0, name]
            order.append(k)
        agg[k][0] += max(1, int(qty or 1))
    return "\n".join(f"{agg[k][0]} {agg[k][1]}" for k in order)


def deck_text(deck_path):
    with open(deck_path, encoding="utf-8") as f:
        deck = mtglib.parse_deck(f.read())
    return _fmt((c.quantity, c.name) for c in deck)


def wishlist_text(collection_path, decks_dir, include=("shared", "unowned", "upgrades")):
    """The 'cards to buy' list: cross-deck shortfalls + cards you own none of +
    buy-list upgrades. Quantities are how many copies you'd need to add."""
    shared, unowned, upgrades = wl.build(collection_path, decks_dir)
    lines = []
    if "shared" in include:
        lines += [(c["short"], c["card"]) for c in shared]
    if "unowned" in include:
        lines += [(c["short"], c["card"]) for c in unowned]
    if "upgrades" in include:
        lines += [(1, u["card"]) for u in upgrades]
    return _fmt(lines)


def main():
    ap = argparse.ArgumentParser(description="Export a ManaPool-ready card list.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--deck", help="deck file -> full 100-card list")
    src.add_argument("--wishlist", action="store_true", help="cards you still need")
    ap.add_argument("--collection", help="collection CSV (required with --wishlist)")
    ap.add_argument("--decks-dir", default="data/decks")
    ap.add_argument("--out", help="write to a file (default: print to stdout)")
    args = ap.parse_args()

    try:
        if args.deck:
            text = deck_text(args.deck)
        else:
            if not args.collection:
                ap.error("--wishlist needs --collection")
            text = wishlist_text(args.collection, args.decks_dir)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        n = len([ln for ln in text.splitlines() if ln.strip()])
        print(f"wrote {args.out} — {n} line(s). Paste into ManaPool's deck/bulk importer.")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
