#!/usr/bin/env python3
"""Analyze an MTG collection: pool statistics and tribal/type/color queries.

The whole point of this script is Grounding Rule #2: COUNT the pool, never
spot-check. Before you tell the player an archetype is "supported," run a query
here and cite the number.

Usage:
  python3 analyze_collection.py <collection_file>            # summary
  python3 analyze_collection.py <collection_file> --tribes    # top creature subtypes
  python3 analyze_collection.py <collection_file> --subtype Dragon
  python3 analyze_collection.py <collection_file> --type Equipment
  python3 analyze_collection.py <collection_file> --color BR   # color-identity filter
  python3 analyze_collection.py <collection_file> --name goblin # name search
  python3 analyze_collection.py <collection_file> --list        # with any filter, list cards

Works with the rich Archidekt CSV (full analysis) or a name-only list (ownership
counts only; subtype/type/color queries fall back to name matching and warn).
"""
import argparse
import sys
from collections import Counter

import mtglib


def load(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    fmt = mtglib.detect_format(text)
    return mtglib.parse_collection(text), fmt


def total_copies(cards):
    return sum(c.quantity for c in cards)


def total_value(cards):
    return sum(c.value for c in cards)


def value_report(cards, top):
    priced = [c for c in cards if c.price]
    if not priced:
        print("[!] No price data in this collection format. Load the pricing CSV "
              "(with a MARKET/price column) to see collection value.")
        return
    print(f"Total collection value (MARKET): ${total_value(cards):,.2f}")
    print(f"Priced cards: {len(priced)} / {len(cards)} unique\n")
    print(f"Top {top} by unit price:")
    for c in sorted(priced, key=lambda x: -x.price)[:top]:
        st = f" [{c.set_code}]" if c.set_code else ""
        print(f"  ${c.price:>8,.2f}  x{c.quantity:<2} {c.name}{st}")
    print(f"\nTop {top} by total value held (price x quantity):")
    for c in sorted(priced, key=lambda x: -x.value)[:top]:
        st = f" [{c.set_code}]" if c.set_code else ""
        print(f"  ${c.value:>8,.2f}  x{c.quantity:<2} {c.name}{st}")
    print("\n[note] Prices are as-exported; some obscure rows are clearly "
          "mispriced. Treat as rough, not appraisal-grade.")


def summary(cards, fmt):
    have_types = any(c.types for c in cards)
    have_mv = any(c.mana_value is not None for c in cards)
    have_ident = any(c.identity for c in cards)

    print(f"Collection format: {fmt}"
          f"  ({'rich CSV' if fmt == 'csv' else 'name-only list'})")
    print(f"Unique cards : {len(cards)}")
    print(f"Total copies : {total_copies(cards)}")
    if not have_types:
        print("\n[!] No type/color/MV data (name-only list). For color identity, "
              "tribal, curve, and pip analysis, load the full Archidekt CSV export.")

    if have_ident:
        print("\nBy color identity (unique cards):")
        ci = Counter()
        for c in cards:
            key = "".join(sorted(c.identity)) or "Colorless"
            ci[key] += 1
        for key, n in ci.most_common():
            print(f"  {key:<10} {n}")

    if have_types:
        print("\nBy primary type (unique cards):")
        pt = Counter(c.primary_type for c in cards)
        for t, n in pt.most_common():
            print(f"  {t:<14} {n}")

    if have_mv:
        print("\nMana-value curve (nonland unique cards):")
        curve = Counter()
        for c in cards:
            if c.is_land or c.mana_value is None:
                continue
            bucket = int(c.mana_value) if c.mana_value < 7 else 7
            curve[bucket] += 1
        for b in range(0, 8):
            label = f"{b}+" if b == 7 else str(b)
            bar = "#" * curve.get(b, 0)
            print(f"  {label:>2} | {bar} {curve.get(b, 0)}")

    lands = [c for c in cards if c.is_land]
    print(f"\nLands (by {'type' if have_types else 'name heuristic'}): "
          f"{len(lands)} unique / {total_copies(lands)} copies")

    if any(c.price for c in cards):
        print(f"\nCollection value (MARKET): ${total_value(cards):,.2f}"
              "   (run --value for the breakdown)")


def show_tribes(cards, top):
    have_sub = any(c.subtypes for c in cards)
    if not have_sub:
        print("[!] No subtype data in this collection format. Load the Archidekt "
              "CSV to see tribal counts. (Name-only lists can't classify creatures.)")
        return
    counter = Counter()
    for c in cards:
        if "Creature" in c.types or any(t.lower() == "creature" for t in c.types):
            for st in c.subtypes:
                counter[st] += c.quantity
    print(f"Top {top} creature subtypes by copies owned "
          "(tribal support — remember: bodies AND payoffs):")
    for st, n in counter.most_common(top):
        print(f"  {st:<18} {n}")


def filter_cards(cards, args):
    have_types = any(c.types for c in cards)
    have_ident = any(c.identity for c in cards)
    result = cards
    warned = False

    if args.subtype:
        q = args.subtype.lower()
        if have_types and any(c.subtypes for c in cards):
            result = [c for c in result if any(q == s.lower() for s in c.subtypes)]
        else:
            warned = True
            result = [c for c in result if q in c.name.lower()]
    if args.type:
        q = args.type.lower()
        if have_types:
            result = [c for c in result if any(q == t.lower() for t in c.types)]
        else:
            warned = True
            result = [c for c in result if q in c.name.lower()]
    if args.color is not None:
        want = mtglib._parse_colorish(args.color)
        if have_ident:
            result = [c for c in result if c.identity == want]
        else:
            warned = True
            print("[!] No color-identity data; --color ignored (name-only list).")
    if args.name:
        q = args.name.lower()
        result = [c for c in result if q in c.name.lower()]

    return result, warned


def main():
    ap = argparse.ArgumentParser(description="Analyze an MTG collection.")
    ap.add_argument("collection", help="path to collection CSV or name-only list")
    ap.add_argument("--tribes", action="store_true", help="top creature subtypes")
    ap.add_argument("--value", action="store_true", help="collection value report")
    ap.add_argument("--top", type=int, default=25, help="how many rows to show")
    ap.add_argument("--subtype", help="count cards of a creature subtype, e.g. Dragon")
    ap.add_argument("--type", dest="type", help="count cards of a type, e.g. Equipment")
    ap.add_argument("--color", help="filter by exact color identity, e.g. BR or 'B,R'")
    ap.add_argument("--name", help="substring name search")
    ap.add_argument("--list", action="store_true", help="list matching cards")
    args = ap.parse_args()

    try:
        cards, fmt = load(args.collection)
    except FileNotFoundError:
        print(f"error: collection file not found: {args.collection}", file=sys.stderr)
        return 2

    if not cards:
        print("error: no cards parsed from collection.", file=sys.stderr)
        return 2

    if args.tribes:
        show_tribes(cards, args.top)
        return 0

    if args.value:
        value_report(cards, args.top)
        return 0

    if any([args.subtype, args.type, args.color is not None, args.name]):
        result, warned = filter_cards(cards, args)
        label = " ".join(filter(None, [
            f"subtype={args.subtype}" if args.subtype else "",
            f"type={args.type}" if args.type else "",
            f"color={args.color}" if args.color else "",
            f"name~{args.name}" if args.name else "",
        ]))
        if warned:
            print("[!] No type/subtype data — fell back to NAME matching. "
                  "This over/undercounts; load the Archidekt CSV for a real count.\n")
        print(f"Matches for [{label}]: {len(result)} unique / "
              f"{total_copies(result)} copies")
        if args.list or len(result) <= 60:
            for c in sorted(result, key=lambda x: x.name):
                extra = ""
                if c.mana_value is not None:
                    extra = f"  (MV {c.mana_value:g}"
                    if c.types:
                        extra += f", {'/'.join(c.types)}"
                        if c.subtypes:
                            extra += f" — {' '.join(c.subtypes)}"
                    extra += ")"
                qty = f"{c.quantity}x " if c.quantity > 1 else "   "
                print(f"  {qty}{c.name}{extra}")
        else:
            print("  (use --list to print all matches)")
        return 0

    summary(cards, fmt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
