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
import deckcore

# Derived from THE role template in deckcore (Phase 12) — this used to be an
# independent copy with different numbers (ramp 10-12 vs the canonical 9-13),
# which is exactly the drift single-sourcing exists to kill.
TARGETS = dict(deckcore.ROLE_RANGE, lands=deckcore.LAND_RANGE)


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
            # copy known attributes, keep deck quantity.
            # This explicit list is the only way a Card field reaches deck-level
            # analysis: anything omitted here silently never reaches build_report,
            # classify(), manabase or the dashboard for ANY deck. Add new fields.
            merged = mtglib.Card(
                name=ref.name, quantity=d.quantity,
                mana_value=ref.mana_value, colors=ref.colors,
                identity=ref.identity, mana_cost=ref.mana_cost,
                types=ref.types, subtypes=ref.subtypes,
                supertypes=ref.supertypes, rarity=ref.rarity,
                scryfall_id=ref.scryfall_id, set_code=ref.set_code,
                collector_number=ref.collector_number, price=ref.price,
                produced=ref.produced, flags=ref.flags, power=ref.power,
                flags_ver=ref.flags_ver)
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

    # Color sources among lands — what each land ACTUALLY taps for once the
    # collection has been enriched (Card.produced), falling back to its color
    # IDENTITY when it hasn't. The two bases are counted separately so every
    # consumer can label the approximation instead of quietly implying precision.
    # A deck card that isn't in the collection keeps produced=None, so a list with
    # any unowned land can never report a purely produced basis — by design.
    sources = Counter()
    restricted = Counter()
    basis = {"produced_lands": 0, "identity_lands": 0,
             # The restriction split (2026-08-14, spec-mana-intelligence Phase B).
             # `restricted_lands` counts VERIFIED spend-restricted lands (the
             # `mana-restricted` flag at vocabulary v2+) — their letters move to
             # `color_sources_restricted` because "add one mana of any color,
             # spend only on the chosen type" is not a source for most of the
             # deck; counting it was an overcount, and this is the subtraction.
             # `restriction_unknown_lands` counts lands whose flags predate the
             # vocabulary (flags_ver 1): unknown is not restricted and not
             # verified-clean, so they count exactly as before and the label
             # downstream says the split is incomplete. Both keys are ALWAYS
             # present — the shape pin requires legacy and enriched reports to
             # have identical shape.
             "restricted_lands": 0, "restriction_unknown_lands": 0}
    for c in lands:
        if c.produced is not None:
            prod = {p for p in c.produced if p in "WUBRG"}
            basis["produced_lands"] += c.quantity
        else:
            prod = c.colors or c.identity
            basis["identity_lands"] += c.quantity
        if "mana-restricted" in c.flags and c.flags_ver >= 2:
            basis["restricted_lands"] += c.quantity
            for color in prod:
                restricted[color] += c.quantity
            continue
        if c.flags_ver < 2:
            basis["restriction_unknown_lands"] += c.quantity
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
        # Always a dict ({} when nothing is restricted): the shape pin asserts
        # identical report shape on enriched and legacy bases, so this key may
        # never be conditional.
        "color_sources_restricted": dict(restricted),
        "color_sources_basis": basis,
        "missing_from_collection": [m.name for m in missing],
        "quantity_problems": owned_enough(deck_cards, coll_index),
        "have_mv": have_mv,
        "have_cost": have_cost,
        "deck_value": round(deck_value, 2) if priced_n else None,
        "priced_cards": priced_n,
    }


def print_report(rep, ranges=None):
    print("=" * 60)
    print("DECK REPORT")
    print("=" * 60)
    print(f"Total cards : {rep['total_cards']}  "
          f"(target 100 incl. commander)")
    print(f"Lands       : {rep['lands']}   {_flag('lands', rep['lands'], ranges)}")
    print(f"Nonland     : {rep['nonland']}")

    print("\nCategories (heuristic — verify):")
    for role in ["ramp", "draw", "removal", "wipe", "counter"]:
        n = rep["categories"].get(role, 0)
        print(f"  {role:<9}: {n:>2}  {_flag(role, n, ranges)}")
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
        approx = (rep.get("color_sources_basis") or {}).get("identity_lands", 0)
        if approx:
            print(f"  [!] {approx} land(s) counted by color IDENTITY, not actual "
                  "production — sources are an approximation for those. Enrich the "
                  "collection (scripts/carddb.py) to count what they really tap for.")
        restr = (rep.get("color_sources_basis") or {}).get("restricted_lands", 0)
        if restr:
            print(f"  [!] {restr} land(s) make spend-restricted mana — counted "
                  "apart from the sources above (add them back for spells that "
                  "match their restriction).")
        unk = (rep.get("color_sources_basis") or {}).get("restriction_unknown_lands", 0)
        if unk:
            print(f"  [~] {unk} land(s) enriched before the restriction vocabulary "
                  "— restriction status unknown, counted as unrestricted.")

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


def _flag(role, n, ranges=None):
    """`ranges` = an archetype-aware `deckcore.role_ranges()` dict; defaults to the
    blind template for callers with no deck header in hand (the dashboard's lands
    tile). Without it a control deck's CLI report would flag counter:15 as high —
    the exact wrong advice single-sourcing exists to kill."""
    table = dict(ranges, lands=deckcore.LAND_RANGE) if ranges else TARGETS
    if role not in table:
        return ""
    lo, hi = table[role]
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
        print_report(rep, ranges=deckcore.role_ranges(
            deckcore.archetype_words(read(args.deck))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
