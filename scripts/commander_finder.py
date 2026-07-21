#!/usr/bin/env python3
"""'What should I build next?' — rank commanders by how much of YOUR collection
already supports them.

For each commander in data/reference/commanders.csv, counts the owned "support
cards" for its archetype(s) (from data/reference/archetype_support.csv) and adds a
small bonus for how deep your collection runs in its colors (basic-land counts as a
proxy). Flags whether you already own the commander.

Usage:
  python3 commander_finder.py --collection data/collection/collection.csv
  python3 commander_finder.py --collection coll.csv --top 12 --owned-commanders
  python3 commander_finder.py --collection coll.csv --archetype aristocrats
"""
import argparse
import csv
import os
import sys

import mtglib
import similar_commanders as simc

SUPPORT = os.path.join(os.path.dirname(__file__), "..", "data", "reference",
                       "archetype_support.csv")


def load_support(path=SUPPORT):
    out = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(r for r in f if not r.lstrip().startswith("#")):
            arch = (row.get("archetype") or "").strip()
            if not arch:
                continue
            cards = [c.strip() for c in (row.get("cards") or "").split(";") if c.strip()]
            out[arch] = cards
    return out


def color_depth(colors, coll_index):
    """Proxy for how deep the collection runs in these colors: owned basics."""
    basics = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
    if not colors:
        return 0
    tot = 0
    for c in colors:
        ref = mtglib.lookup(coll_index, basics.get(c, ""))
        tot += ref.quantity if ref else 0
    return tot / len(colors)  # average basics per color


def score(coll_index, commanders, support):
    rows = []
    for c in commanders:
        owned_support = {}
        for arch in c["archetypes"]:
            for name in support.get(arch, []):
                ref = mtglib.lookup(coll_index, name)
                if ref:
                    owned_support[name] = ref.quantity
        depth = color_depth(c["colors"], coll_index)
        owns_cmd = mtglib.lookup(coll_index, c["name"]) is not None
        rows.append({
            "name": c["name"], "colors": "".join(sorted(c["colors"])) or "C",
            "archetypes": sorted(c["archetypes"]),
            "support_n": len(owned_support),
            "support_cards": sorted(owned_support, key=lambda n: -owned_support[n]),
            "depth": round(depth, 1),
            "owns_commander": owns_cmd,
            # score: owned support pieces dominate; color depth is a light tiebreak
            "score": round(len(owned_support) + depth / 12, 2),
            "notes": c["notes"],
        })
    rows.sort(key=lambda r: (-r["score"], not r["owns_commander"], r["name"]))
    return rows


def main():
    ap = argparse.ArgumentParser(description="Rank commanders by collection support.")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--archetype", help="only commanders with this archetype tag")
    ap.add_argument("--owned-commanders", action="store_true",
                    help="only commanders you already own")
    args = ap.parse_args()

    try:
        coll = mtglib.load_collection(args.collection)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    idx = mtglib.index_by_name(coll)
    commanders = simc.load_commanders()
    rows = score(idx, commanders, load_support())

    if args.archetype:
        rows = [r for r in rows if args.archetype in r["archetypes"]]
    if args.owned_commanders:
        rows = [r for r in rows if r["owns_commander"]]

    print("WHAT SHOULD I BUILD NEXT? — commanders ranked by collection support\n")
    print(f"  {'Support':<9}{'Commander':<34}{'Colors':<8}Own?")
    print("  " + "-" * 66)
    for r in rows[:args.top]:
        own = "OWN" if r["owns_commander"] else "buy"
        print(f"  {r['support_n']:<9}{r['name'][:33]:<34}{r['colors']:<8}{own}")
        top = ", ".join(r["support_cards"][:6])
        print(f"      {'/'.join(r['archetypes'])}  ·  owns: {top}"
              + (" …" if len(r["support_cards"]) > 6 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
