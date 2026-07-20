#!/usr/bin/env python3
"""Analyze a Commander deck list against a collection.

Computes what a champion checks before calling a deck done:
  - Ownership: which cards in the list you DON'T own (Grounding Rule #1/#2).
  - Curve: mana-value histogram of nonland cards.
  - Pip demand: colored pips per color + double-pip count vs. your sources.
  - Category counts: lands / ramp / draw / removal / wipes vs. target ratios.

Usage:
  python3 deck_stats.py --deck data/decks/mydeck.txt --collection data/collection/collection.csv
  python3 deck_stats.py --deck mydeck.txt --collection coll.csv --json

Full analysis needs the rich Archidekt CSV (for MV/cost/types). With a name-only
collection you still get ownership + heuristic category counts, but curve and pip
math are marked unavailable.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict

import mtglib

TARGETS = {
    "lands": (36, 38),
    "ramp": (10, 12),
    "draw": (10, 12),
    "removal": (8, 10),
    "wipe": (3, 5),
}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def analyze(deck_cards, coll_index):
    # Enrich deck cards from the collection where possible.
    enriched = []
    missing = []
    for d in deck_cards:
        ref = mtglib.lookup(coll_index, d.name)
        if ref is None:
            missing.append(d)
            enriched.append(d)  # keep, but unknown data
        else:
            # copy known attributes, keep deck quantity
            merged = mtglib.Card(
                name=ref.name, quantity=d.quantity,
                mana_value=ref.mana_value, colors=ref.colors,
                identity=ref.identity, mana_cost=ref.mana_cost,
                types=ref.types, subtypes=ref.subtypes,
                supertypes=ref.supertypes, rarity=ref.rarity,
                scryfall_id=ref.scryfall_id, set_code=ref.set_code,
                collector_number=ref.collector_number, price=ref.price)
            enriched.append(merged)
    return enriched, missing


def owned_enough(deck_cards, coll_index):
    """Cards where deck quantity exceeds owned copies (or not owned at all)."""
    problems = []
    for d in deck_cards:
        ref = mtglib.lookup(coll_index, d.name)
        owned = ref.quantity if ref else 0
        if owned < d.quantity:
            problems.append((d.name, d.quantity, owned))
    return problems


def build_report(deck_cards, enriched, missing, coll_index):
    have_mv = any(c.mana_value is not None for c in enriched)
    have_cost = any(c.mana_cost for c in enriched)

    total = sum(c.quantity for c in deck_cards)
    lands = [c for c in enriched if c.is_land]
    nonland = [c for c in enriched if not c.is_land]

    # categories
    cat = Counter()
    for c in enriched:
        for role in mtglib.classify(c):
            cat[role] += c.quantity

    # curve
    curve = Counter()
    if have_mv:
        for c in nonland:
            if c.mana_value is None:
                continue
            b = int(c.mana_value) if c.mana_value < 7 else 7
            curve[b] += c.quantity

    # pip demand
    pips = defaultdict(float)
    double = Counter()
    if have_cost:
        for c in nonland:
            for color, n in mtglib.pip_counts(c.mana_cost).items():
                pips[color] += n * c.quantity
            dp = mtglib.is_double_pip(c.mana_cost)
            if dp:
                double[dp] += c.quantity

    # color sources among lands (needs identity/color data on lands)
    sources = Counter()
    for c in lands:
        prod = c.colors or c.identity
        for color in prod:
            sources[color] += c.quantity

    # deck market value (sum of one copy's representative price per deck card)
    deck_value = sum((c.price or 0) * c.quantity for c in enriched)
    priced_n = sum(1 for c in enriched if c.price)

    return {
        "total_cards": total,
        "lands": sum(c.quantity for c in lands),
        "nonland": sum(c.quantity for c in nonland),
        "categories": dict(cat),
        "curve": {str(k): curve[k] for k in sorted(curve)} if have_mv else None,
        "pip_demand": {k: round(v, 1) for k, v in pips.items()} if have_cost else None,
        "double_pips": dict(double) if have_cost else None,
        "color_sources": dict(sources) if sources else None,
        "missing_from_collection": [m.name for m in missing],
        "quantity_problems": owned_enough(deck_cards, coll_index),
        "have_mv": have_mv,
        "have_cost": have_cost,
        "deck_value": round(deck_value, 2) if priced_n else None,
        "priced_cards": priced_n,
    }


def print_report(rep):
    print("=" * 60)
    print("DECK REPORT")
    print("=" * 60)
    print(f"Total cards : {rep['total_cards']}  "
          f"(target 100 incl. commander)")
    print(f"Lands       : {rep['lands']}   {_flag('lands', rep['lands'])}")
    print(f"Nonland     : {rep['nonland']}")

    print("\nCategories (heuristic — verify):")
    for role in ["ramp", "draw", "removal", "wipe", "counter"]:
        n = rep["categories"].get(role, 0)
        print(f"  {role:<9}: {n:>2}  {_flag(role, n)}")
    for role in ["creature", "spell", "artifact", "enchantment",
                 "planeswalker", "other"]:
        if rep["categories"].get(role):
            print(f"  {role:<9}: {rep['categories'][role]:>2}")

    if rep["curve"]:
        print("\nMana curve (nonland):")
        for b in range(0, 8):
            key = str(b)
            n = rep["curve"].get(key, 0)
            label = f"{b}+" if b == 7 else str(b)
            print(f"  {label:>2} | {'#' * n} {n}")

    if rep["pip_demand"]:
        print("\nColored pip demand vs. sources:")
        names = {"W": "White", "U": "Blue", "B": "Black",
                 "R": "Red", "G": "Green"}
        src = rep["color_sources"] or {}
        for color in "WUBRG":
            dem = rep["pip_demand"].get(color, 0)
            if dem == 0 and not src.get(color):
                continue
            dbl = (rep["double_pips"] or {}).get(color, 0)
            s = src.get(color, 0)
            note = ""
            if dem and s and s < dem * 0.4:
                note = "  <-- light on sources for this demand"
            print(f"  {names[color]:<6} demand {dem:>4}  "
                  f"(double-pip cards: {dbl:>2})  sources {s:>2}{note}")
        if not rep["color_sources"]:
            print("  [!] Land color data unavailable — can't count sources. "
                  "Load the CSV (lands need Colors/Identities).")

    if not rep["have_cost"]:
        print("\n[!] No mana-cost data (name-only collection). Curve and pip "
              "demand unavailable — load the Archidekt CSV for full mana math.")

    if rep["deck_value"] is not None:
        print(f"\nDeck value (MARKET, {rep['priced_cards']} priced cards): "
              f"${rep['deck_value']:,.2f}")

    prob = rep["quantity_problems"]
    print("\nOwnership check:")
    if not prob:
        print("  All deck cards are owned in sufficient quantity. ✅")
    else:
        print(f"  {len(prob)} card(s) you don't own enough copies of "
              "(buy-list candidates):")
        for name, want, owned in prob:
            print(f"    - {name}: deck wants {want}, you own {owned}")

    print("\nReminder: category counts are heuristic. Eyeball the list, and "
          "verify any post-2025 card's oracle text before trusting it.")


def _flag(role, n):
    if role not in TARGETS:
        return ""
    lo, hi = TARGETS[role]
    if n < lo:
        return f"(low; aim {lo}-{hi})"
    if n > hi:
        return f"(high; aim {lo}-{hi})"
    return "(ok)"


def main():
    ap = argparse.ArgumentParser(description="Analyze a Commander deck list.")
    ap.add_argument("--deck", required=True, help="deck list file (qty name per line)")
    ap.add_argument("--collection", required=True, help="collection CSV or name list")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    args = ap.parse_args()

    try:
        deck_cards = mtglib.parse_deck(read(args.deck))
        coll = mtglib.load_collection(args.collection)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    coll_index = mtglib.index_by_name(coll)
    enriched, missing = analyze(deck_cards, coll_index)
    rep = build_report(deck_cards, enriched, missing, coll_index)

    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print_report(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
