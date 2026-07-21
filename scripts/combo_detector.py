#!/usr/bin/env python3
"""Infinite-combo detector for Commander decks and the collection.

Upgrades the old "N loose combo pieces present, go verify" heuristic (power.py)
into real detection: it knows curated 2- and 3-card combo DEFINITIONS — which
specific cards go together, what they produce, and whether the combo is a cheap,
EARLY two-card line (the WotC Commander-bracket red flag that pushes a deck to
Bracket 4). It reports three things for a deck:

  * complete  — every piece of a combo is in the deck (with an EARLY flag),
  * near      — the deck is one piece away (and whether you already own it),

and, for the whole collection, which combos you could assemble at all.

Data: data/reference/combos.csv
  Name,Pieces,Result,ColorIdentity,Early,Category,Notes
  `Pieces` is a ';'-separated list of card names — card names themselves contain
  commas (e.g. "Kiki-Jiki, Mirror Breaker"), so ';' keeps the field comma-safe.

Grounding: the combo list is CURATED from well-established interactions, not a
live scrape (Scryfall / Commander Spellbook are firewalled in this env). It is a
starting point, not exhaustive — verify an interaction before calling a deck
Bracket 4 on its strength. See the skill's grounding rules.

Usage:
  # combos fully present in one deck (+ 'one piece away', tagged owned/buy)
  python3 combo_detector.py --deck data/decks/yshtola-nights-blessed.txt \
      --collection data/collection/collection.csv
  # scan every deck in a folder
  python3 combo_detector.py --all --collection coll.csv
  # which combos can I assemble from my whole collection?
  python3 combo_detector.py --collection coll.csv --collection-combos
  python3 combo_detector.py --all --collection coll.csv --json
"""
import argparse
import csv
import glob
import io
import json
import os
import sys

import mtglib


def _utf8_console():
    """Windows consoles default to cp1252 and choke on → / ⚠ / • in output.
    Reconfigure stdout/stderr to UTF-8 (no-op where already UTF-8)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


REF_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "data",
                           "reference", "combos.csv")

# Minimal built-in fallback so the tool still runs if the CSV is missing.
_FALLBACK_ROWS = [
    {"Name": "Thassa's Oracle + Demonic Consultation",
     "Pieces": "Thassa's Oracle;Demonic Consultation", "Result": "Win the game",
     "ColorIdentity": "UB", "Early": "yes", "Category": "win",
     "Notes": "Empty your library, then Thassa's Oracle wins on resolution."},
    {"Name": "Devoted Druid + Vizier of Remedies",
     "Pieces": "Devoted Druid;Vizier of Remedies", "Result": "Infinite green mana",
     "ColorIdentity": "GW", "Early": "yes", "Category": "infinite-mana",
     "Notes": "Vizier cancels the -1/-1 counter, so Druid untaps for free."},
]

_TRUE = {"yes", "y", "true", "1", "early"}


def _to_bool(s):
    return str(s or "").strip().lower() in _TRUE


def _parse_identity(s):
    return {ch for ch in str(s or "").upper() if ch in "WUBRG"}


def _combo_from_row(r):
    pieces_raw = [p.strip() for p in (r.get("Pieces") or "").split(";") if p.strip()]
    return {
        "name": (r.get("Name") or " + ".join(pieces_raw)).strip(),
        "pieces": [mtglib._norm(p) for p in pieces_raw],
        "display": pieces_raw,
        "result": (r.get("Result") or "").strip(),
        "identity": _parse_identity(r.get("ColorIdentity")),
        "early": _to_bool(r.get("Early")),
        "category": (r.get("Category") or "").strip(),
        "notes": (r.get("Notes") or "").strip(),
    }


def load_combos(path=REF_DEFAULT):
    """Return the curated combo definitions as a list of dicts. Each combo:
    {name, pieces:[normalized names], display:[original names], result,
     identity:set, early:bool, category, notes}."""
    rows = _FALLBACK_ROWS
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        combo = _combo_from_row(r)
        if len(combo["pieces"]) >= 2:      # a "combo" needs at least two pieces
            out.append(combo)
    return out


def _norm_set(cards):
    """Accept a list of Card objects, card-name strings, or an existing set of
    normalized names, and return a set of normalized names."""
    if isinstance(cards, set):
        return cards
    out = set()
    for c in cards:
        name = getattr(c, "name", c)
        out.add(mtglib._norm(name))
    return out


def detect(present, combos, owned=None):
    """Classify each combo against `present` (a set of normalized names).
      complete: every piece is present.
      near:     exactly one piece missing (annotated with the missing card and,
                if `owned` is given, whether you already own it).
    Both lists are sorted with the most actionable first (early / already-owned).
    """
    present = _norm_set(present)
    owned = _norm_set(owned) if owned is not None else None
    complete, near = [], []
    for cb in combos:
        missing = [p for p in cb["pieces"] if p not in present]
        if not missing:
            complete.append(cb)
        elif len(missing) == 1:
            i = cb["pieces"].index(missing[0])
            item = dict(cb)
            item["missing"] = cb["display"][i]
            item["missing_owned"] = bool(owned is not None and missing[0] in owned)
            near.append(item)
    complete.sort(key=lambda c: (not c["early"], c["name"]))
    near.sort(key=lambda c: (not c.get("missing_owned"), not c["early"], c["name"]))
    return {"complete": complete, "near": near}


def detect_for_cards(cards, combos=None, owned=None):
    """Convenience: detect combos among a list of Card objects (e.g. a deck's
    enriched cards). Used by power.py."""
    return detect(_norm_set(cards), combos or load_combos(), owned)


def for_deck(deck_path, collection_index=None, combos=None):
    """Detect combos in a deck file. If a collection index is given, 'near'
    combos are tagged with whether you already own the missing piece."""
    with open(deck_path, encoding="utf-8") as f:
        deck = mtglib.parse_deck(f.read())
    owned = set(collection_index) if collection_index else None
    return detect(_norm_set(deck), combos or load_combos(), owned)


def for_collection(collection, combos=None):
    """Which combos can the whole collection assemble (all pieces owned)?"""
    return detect(_norm_set(collection), combos or load_combos())["complete"]


def bracket_signal(detected):
    """Turn detected combos into a Bracket verdict for power.py.
    Returns (is_bracket4: bool, reasons: list[str]). A COMPLETE, EARLY two-card
    combo is the WotC red flag that forces Bracket 4; a complete-but-slow combo
    is flagged as a strong signal without forcing the bracket."""
    reasons, b4 = [], False
    for c in detected["complete"]:
        if c["early"]:
            b4 = True
            reasons.append(f"complete early two-card combo — {c['name']} → "
                           f"{c['result']} (cheap 2-card infinite ⇒ Bracket 4)")
        else:
            reasons.append(f"complete combo present — {c['name']} → {c['result']} "
                           "(deterministic, but not a cheap 2-card line; verify speed)")
    return b4, reasons


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_deck(label, detected):
    comp, near = detected["complete"], detected["near"]
    print("=" * 64)
    print(f"COMBO WATCH — {label}")
    print("=" * 64)
    if not comp and not near:
        print("  No known combos, complete or one-away, from the curated list.")
        return
    if comp:
        print(f"\n  Complete combo(s) in the deck ({len(comp)}):")
        for c in comp:
            flag = "  ⚠ EARLY 2-CARD → Bracket 4" if c["early"] else ""
            print(f"    • {c['name']} → {c['result']}{flag}")
            print(f"        {c['notes']}")
    if near:
        print(f"\n  One piece away ({len(near)}):")
        for c in near:
            own = "you OWN it" if c.get("missing_owned") else "not owned"
            print(f"    • {c['name']}: add {c['missing']} ({own}) → {c['result']}")


def main():
    ap = argparse.ArgumentParser(description="Infinite-combo detector for decks "
                                             "and the collection.")
    ap.add_argument("--deck", help="a single deck file")
    ap.add_argument("--all", action="store_true", help="scan every deck in --decks-dir")
    ap.add_argument("--decks-dir", default="data/decks")
    ap.add_argument("--collection", help="collection file (enables owned/buy tags "
                    "and --collection-combos)")
    ap.add_argument("--collection-combos", action="store_true",
                    help="list combos fully assemblable from the whole collection")
    ap.add_argument("--ref", default=REF_DEFAULT, help="combos.csv path")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    _utf8_console()
    combos = load_combos(args.ref)

    coll_index = None
    collection = None
    if args.collection:
        try:
            collection = mtglib.load_collection(args.collection)
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        coll_index = mtglib.index_by_name(collection)

    if args.collection_combos:
        if collection is None:
            ap.error("--collection-combos needs --collection")
        assemblable = for_collection(collection, combos)
        if args.json:
            print(json.dumps([{"name": c["name"], "result": c["result"],
                               "early": c["early"], "category": c["category"]}
                              for c in assemblable], indent=2))
            return 0
        print("=" * 64)
        print("COMBOS YOUR COLLECTION CAN ASSEMBLE (all pieces owned)")
        print("=" * 64)
        if not assemblable:
            print("  None from the curated list — your pool has no complete combo.")
        for c in assemblable:
            flag = "  ⚠ early 2-card" if c["early"] else ""
            print(f"  • {c['name']} → {c['result']}{flag}")
        print(f"\n  {len(assemblable)} of {len(combos)} curated combos are fully owned.")
        print("  (Curated list, not exhaustive — verify before relying on one.)")
        return 0

    targets = []
    if args.all:
        targets = sorted(glob.glob(os.path.join(args.decks_dir, "*.txt")))
    elif args.deck:
        targets = [args.deck]
    else:
        ap.error("provide --deck, --all, or --collection-combos")

    results = {}
    for path in targets:
        label = os.path.splitext(os.path.basename(path))[0]
        results[label] = for_deck(path, coll_index, combos)

    if args.json:
        payload = {}
        for label, det in results.items():
            payload[label] = {
                "complete": [{"name": c["name"], "result": c["result"],
                              "early": c["early"]} for c in det["complete"]],
                "near": [{"name": c["name"], "missing": c["missing"],
                          "missing_owned": c["missing_owned"],
                          "result": c["result"]} for c in det["near"]],
            }
        print(json.dumps(payload, indent=2))
        return 0

    for label, det in results.items():
        _print_deck(label, det)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
