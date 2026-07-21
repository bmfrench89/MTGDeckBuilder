#!/usr/bin/env python3
"""Enrich the whole collection with card attributes (colors / type / mana value)
from a Scryfall card database — the fix for the "name-only export" limitation.

Point it at a Scryfall bulk-data file (download once, locally, from
https://scryfall.com/docs/api/bulk-data — the "Oracle Cards" JSON is ideal), and
it writes data/collection/collection_attrs.csv. mtglib.load_collection auto-merges
that file, so EVERY tool (curves, power color-scores, tribal counts, similar-commander
color-fit %) then works across the entire collection — no per-deck attrs needed.

Uses DuckDB to stream the (large) JSON if installed; falls back to stdlib json.

Usage:
  python3 carddb.py --bulk oracle-cards.json --collection data/collection/collection.csv
  python3 carddb.py --bulk oracle-cards.json --collection coll.csv --stats
"""
import argparse
import csv
import json
import os
import sys

import mtglib

MAIN_TYPES = ["Land", "Creature", "Planeswalker", "Battle", "Artifact",
              "Enchantment", "Instant", "Sorcery"]


def primary_type(type_line):
    left = (type_line or "").split("//")[0].split("—")[0]
    low = left.lower()
    for t in MAIN_TYPES:
        if t.lower() in low:
            return t
    return left.strip().split()[-1] if left.strip() else ""


def _rows_duckdb(bulk_path):
    import duckdb
    con = duckdb.connect()
    q = ("SELECT name, color_identity, type_line, cmc, mana_cost "
         f"FROM read_json_auto('{bulk_path}', maximum_object_size=100000000) "
         "WHERE name IS NOT NULL")
    for name, ci, type_line, cmc, cost in con.execute(q).fetchall():
        yield name, (ci or []), type_line, cmc, cost
    con.close()


def _rows_json(bulk_path):
    with open(bulk_path, encoding="utf-8") as f:
        data = json.load(f)
    for c in data:
        if c.get("name"):
            yield (c["name"], c.get("color_identity", []), c.get("type_line"),
                   c.get("cmc"), c.get("mana_cost"))


def build_index(bulk_path, use_duckdb=True):
    """name(normalized) -> {colors, type, mv, cost}. First printing per name wins."""
    idx = {}
    rows = None
    if use_duckdb:
        try:
            rows = _rows_duckdb(bulk_path)
        except Exception as e:
            print(f"  (duckdb unavailable: {e}; falling back to stdlib json)",
                  file=sys.stderr)
    if rows is None:
        rows = _rows_json(bulk_path)
    for name, ci, type_line, cmc, cost in rows:
        k = mtglib._norm(name)
        if k in idx:
            continue
        idx[k] = {"colors": " ".join(ci), "type": primary_type(type_line),
                  "mv": cmc if cmc is not None else None, "cost": cost or ""}
    return idx


def enrich(collection_path, bulk_path, out_path, use_duckdb=True):
    coll = mtglib.load_collection(collection_path)
    index = build_index(bulk_path, use_duckdb)
    matched = 0
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Name", "Type", "MV", "Colors", "Cost"])
        for card in sorted(coll, key=lambda c: c.name):
            a = index.get(mtglib._norm(card.name))
            if not a:
                continue
            matched += 1
            mv = "" if a["mv"] is None else (f"{a['mv']:g}")
            w.writerow([card.name, a["type"], mv, a["colors"], a["cost"]])
    return matched, len(coll), len(index)


def main():
    ap = argparse.ArgumentParser(description="Enrich the collection from a card DB.")
    ap.add_argument("--bulk", required=True, help="Scryfall bulk JSON (oracle/default cards)")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--out", default=None, help="default: <collection dir>/collection_attrs.csv")
    ap.add_argument("--no-duckdb", action="store_true")
    ap.add_argument("--stats", action="store_true", help="print a color/type breakdown after")
    args = ap.parse_args()

    out = args.out or os.path.join(os.path.dirname(args.collection) or ".",
                                   "collection_attrs.csv")
    try:
        matched, total, dbn = enrich(args.collection, args.bulk, out, not args.no_duckdb)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    pct = round(100 * matched / total) if total else 0
    print(f"card DB: {dbn} cards. Matched {matched}/{total} owned cards ({pct}%).")
    print(f"wrote {out} — load_collection now merges it automatically.")
    if matched < total:
        print(f"  ({total - matched} unmatched — usually tokens or very new cards; "
              "add them to owned_additions or a fresher bulk file.)")

    if args.stats:
        coll = mtglib.load_collection(args.collection)  # now includes attrs
        from collections import Counter
        ci = Counter("".join(sorted(c.identity)) or "Colorless" for c in coll if c.types)
        pt = Counter(c.primary_type for c in coll if c.types)
        print("\nBy color identity:", dict(ci.most_common()))
        print("By primary type  :", dict(pt.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
