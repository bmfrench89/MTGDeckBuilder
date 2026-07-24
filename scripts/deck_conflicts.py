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


def scan(decks_dir, collection_index, skip=None):
    """Return {card_name: {'owned':n, 'total':n, 'decks':{deck:qty}}} for cards
    committed across decks, and the raw per-deck usage. `skip` (a deck stem) omits that
    deck — used when REBUILDING it, so its own current cards count as available again."""
    usage = defaultdict(lambda: {"decks": {}, "total": 0})
    for path in deck_files(decks_dir):
        if skip and os.path.splitext(os.path.basename(path))[0] == skip:
            continue
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
        u["price"] = ref.price if (ref and ref.price) else None
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
        short = u["total"] - u["owned"]
        out.append({
            "card": name,
            "owned": u["owned"],
            "committed": u["total"],
            "short": short,
            "price": u.get("price"),
            "buy_cost": round(short * u["price"], 2) if u.get("price") else None,
            "decks": dict(sorted(u["decks"].items())),
        })
    out.sort(key=lambda c: (-c["short"], -c["committed"], c["card"]))
    return out


def available_pool(usage, collection, exclude_deck=None):
    """Cards still free to put in a NEW deck without creating a conflict:
    free = owned - copies already committed to OTHER decks. Excludes basics."""
    committed_elsewhere = {}
    for name, u in usage.items():
        n = sum(q for d, q in u["decks"].items() if d != exclude_deck)
        committed_elsewhere[mtglib._norm(name)] = n
    rows = []
    for c in collection:
        k = mtglib._norm(c.name)
        if k in BASICS:
            continue
        free = c.quantity - committed_elsewhere.get(k, 0)
        if free > 0:
            rows.append((c.name, c.quantity, committed_elsewhere.get(k, 0), free))
    rows.sort(key=lambda r: (-r[3], r[0]))
    return rows


def buy_doubles_report(conf):
    """Shopping list: extra copies to buy so all decks can be assembled at once."""
    priced = [c for c in conf if c["buy_cost"] is not None]
    unpriced = [c for c in conf if c["buy_cost"] is None]
    total = round(sum(c["buy_cost"] for c in priced), 2)
    print("BUY-DOUBLES SHOPPING LIST")
    print("Buy these extra copies and every deck can be sleeved at the same time —"
          "\nno swaps, no deck loses a card.\n")
    print(f"  {'Qty':<5}{'Card':<28}{'~each':>8}{'~total':>9}   also in")
    print("  " + "-" * 72)
    for c in sorted(conf, key=lambda x: -(x["buy_cost"] or 0)):
        each = f"${c['price']:.2f}" if c["price"] is not None else "—"
        tot = f"${c['buy_cost']:.2f}" if c["buy_cost"] is not None else "—"
        where = ", ".join(c["decks"])
        print(f"  {c['short']:<5}{c['card']:<28}{each:>8}{tot:>9}   {where}")
    print("  " + "-" * 72)
    n = sum(c["short"] for c in conf)
    print(f"  {n} extra copies · estimated total ~${total:.2f}"
          + (f" (+{len(unpriced)} unpriced)" if unpriced else ""))
    print("\nPrices are your export's MARKET values (rough). Most conflicts are cheap "
          "staples — usually far easier than swapping cards out of a tuned deck.")


def conflicts_for_deck(deck_path, collection_index, decks_dir=None):
    """Convenience for the dashboard: conflicts involving one deck."""
    decks_dir = decks_dir or os.path.dirname(deck_path) or "."
    usage = scan(decks_dir, collection_index)
    return conflicts(usage, focus_deck=deck_label(deck_path))


def shared_for_deck(deck_path, collection_index, decks_dir=None):
    """For badging: every card in this deck that also appears in another deck.
    Returns {normalized_name: {'decks':[...], 'owned':n, 'covered':bool}} where
    covered = you own enough copies for all decks using it."""
    decks_dir = decks_dir or os.path.dirname(deck_path) or "."
    me = deck_label(deck_path)
    usage = scan(decks_dir, collection_index)
    out = {}
    for name, u in usage.items():
        if me not in u["decks"] or len(u["decks"]) < 2:
            continue
        out[mtglib._norm(name)] = {
            "name": name,
            "decks": sorted(u["decks"]),
            "owned": u["owned"],
            "covered": u["total"] <= u["owned"],
        }
    return out


def main():
    ap = argparse.ArgumentParser(description="Cross-deck card conflict checker.")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--decks-dir", default=None,
                    help="folder of deck .txt files (default: dir of --deck, else data/decks)")
    ap.add_argument("--deck", help="only show conflicts involving this deck file")
    ap.add_argument("--buy-doubles", action="store_true",
                    help="print a priced shopping list to buy the extra copies instead")
    ap.add_argument("--available", action="store_true",
                    help="list cards still free to add to a NEW deck (owned minus "
                         "copies committed to other decks); pair with --deck to free "
                         "up that deck's own cards")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    decks_dir = args.decks_dir or (os.path.dirname(args.deck) if args.deck else "data/decks")
    try:
        with open(args.collection, encoding="utf-8"):
            coll = mtglib.load_collection(args.collection)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    idx = mtglib.index_by_name(coll)
    usage = scan(decks_dir, idx)
    focus = deck_label(args.deck) if args.deck else None

    if args.available:
        rows = available_pool(usage, coll, exclude_deck=focus)
        tag = f" (freeing '{focus}')" if focus else ""
        print(f"AVAILABLE POOL{tag} — owned copies not committed to other decks.\n"
              "Build a new deck only from cards with free ≥ the copies you want.\n")
        print(f"  {'Free':<6}{'Owned':<7}{'Elsewhere':<11}Card")
        print("  " + "-" * 60)
        for name, own, elsew, free in rows[:400]:
            print(f"  {free:<6}{own:<7}{elsew:<11}{name}")
        print(f"\n  {len(rows)} distinct cards have at least one free copy.")
        return 0

    conf = conflicts(usage, focus)

    if args.json:
        print(json.dumps(conf, indent=2))
        return 0

    if args.buy_doubles:
        if not conf:
            print("No conflicts — nothing to buy. ✅")
        else:
            buy_doubles_report(conf)
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
