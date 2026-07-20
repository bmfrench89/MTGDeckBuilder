#!/usr/bin/env python3
"""Cross-deck card-conflict checker.

Answers: "am I using the same physical card in more than one deck without owning
enough copies?" Scans every deck list in a folder, sums how many copies each card
is committed to across all decks, and compares that to how many you actually own.
Basic lands are exempt (unlimited).

Usage:
  python3 deck_conflicts.py --collection data/collection/collection.csv
  python3 deck_conflicts.py --collection coll.csv --decks-dir data/decks
  python3 deck_conflicts.py --collection coll.csv --deck data/decks/cosmic-spider-man.txt
      # only conflicts that involve that one deck
  python3 deck_conflicts.py --collection coll.csv --json
"""
import argparse
import glob
import json
import os
import sys
from collections import defaultdict

import mtglib

BASICS = {"plains", "island", "swamp", "mountain", "forest", "wastes",
          "snow-covered plains", "snow-covered island", "snow-covered swamp",
          "snow-covered mountain", "snow-covered forest"}


def deck_files(decks_dir):
    return sorted(glob.glob(os.path.join(decks_dir, "*.txt")))


def deck_label(path):
    return os.path.splitext(os.path.basename(path))[0]


def scan(decks_dir, collection_index):
    """Return {card_name: {'owned':n, 'total':n, 'decks':{deck:qty}}} for cards
    committed across decks, and the raw per-deck usage."""
    usage = defaultdict(lambda: {"decks": {}, "total": 0})
    for path in deck_files(decks_dir):
        label = deck_label(path)
        with open(path, encoding="utf-8") as f:
            for card in mtglib.parse_deck(f.read()):
                key = mtglib._norm(card.name)
                if key in BASICS:
                    continue
                u = usage[card.name]
                u["decks"][label] = u["decks"].get(label, 0) + card.quantity
                u["total"] += card.quantity
    for name, u in usage.items():
        ref = mtglib.lookup(collection_index, name)
        u["owned"] = ref.quantity if ref else 0
    return usage


def conflicts(usage, focus_deck=None):
    """A conflict = total committed across decks exceeds owned copies.
    If focus_deck given, only conflicts that include that deck."""
    out = []
    for name, u in usage.items():
        if u["total"] <= u["owned"]:
            continue
        if focus_deck and focus_deck not in u["decks"]:
            continue
        out.append({
            "card": name,
            "owned": u["owned"],
            "committed": u["total"],
            "short": u["total"] - u["owned"],
            "decks": dict(sorted(u["decks"].items())),
        })
    out.sort(key=lambda c: (-c["short"], -c["committed"], c["card"]))
    return out


def conflicts_for_deck(deck_path, collection_index, decks_dir=None):
    """Convenience for the dashboard: conflicts involving one deck."""
    decks_dir = decks_dir or os.path.dirname(deck_path) or "."
    usage = scan(decks_dir, collection_index)
    return conflicts(usage, focus_deck=deck_label(deck_path))


def main():
    ap = argparse.ArgumentParser(description="Cross-deck card conflict checker.")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--decks-dir", default=None,
                    help="folder of deck .txt files (default: dir of --deck, else data/decks)")
    ap.add_argument("--deck", help="only show conflicts involving this deck file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    decks_dir = args.decks_dir or (os.path.dirname(args.deck) if args.deck else "data/decks")
    try:
        with open(args.collection, encoding="utf-8") as f:
            coll = mtglib.parse_collection(f.read())
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    idx = mtglib.index_by_name(coll)
    usage = scan(decks_dir, idx)
    focus = deck_label(args.deck) if args.deck else None
    conf = conflicts(usage, focus)

    if args.json:
        print(json.dumps(conf, indent=2))
        return 0

    decks = sorted({d for u in usage.values() for d in u["decks"]})
    print(f"Scanned {len(decks)} deck(s) in {decks_dir}: {', '.join(decks)}")
    scope = f" involving '{focus}'" if focus else ""
    if not conf:
        print(f"\nNo cross-deck conflicts{scope}. Every shared card is covered by "
              "the copies you own. ✅  (Basic lands are exempt.)")
        return 0
    print(f"\n⚠ {len(conf)} conflict(s){scope} — a card is committed to more decks "
          "than you own copies:\n")
    for c in conf:
        where = ", ".join(f"{d} (x{q})" for d, q in c["decks"].items())
        print(f"  {c['card']}: own {c['owned']}, committed {c['committed']} "
              f"(short {c['short']})")
        print(f"      used in: {where}")
    print("\nFix: buy the extra copies, or swap the card out of a deck. Sharing a "
          "single physical card across decks means they can't be assembled at once.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
