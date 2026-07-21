#!/usr/bin/env python3
"""Enrich the whole collection with card attributes (colors / type / mana value)
from a Scryfall card database — the fix for the "name-only export" limitation.

With no --bulk it auto-downloads the "Oracle Cards" bulk file from Scryfall
(~40 MB, cached locally). It then writes data/collection/collection_attrs.csv.
mtglib.load_collection auto-merges that file, so EVERY tool (curves, power
color-scores, tribal counts, similar-commander color-fit %, the click-a-card fit
score) works across the entire collection — no per-deck attrs needed.

Uses DuckDB to stream the JSON if installed; falls back to stdlib json.

Usage:
  python3 carddb.py --collection data/collection/collection.csv          # auto-download
  python3 carddb.py --collection coll.csv --refresh --stats              # re-download
  python3 carddb.py --bulk oracle-cards.json --collection coll.csv       # use a local file
"""
import argparse
import csv
import json
import os
import sys
import urllib.request

import mtglib

BULK_LIST_URL = "https://api.scryfall.com/bulk-data"
# Scryfall asks API clients to send a descriptive User-Agent and an Accept header.
_HEADERS = {"User-Agent": "MTGDeckBuilder/1.0 (personal collection tool)",
            "Accept": "application/json"}


def _get(url):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def download_bulk(kind="oracle_cards", dest=None, force=False):
    """Download a Scryfall bulk-data file (default 'oracle_cards' — one entry per
    card, ~40 MB, exactly what we need for colors/types/MV/ids). Returns the path.
    Skips the download if a cached copy already exists unless force=True."""
    dest = dest or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "data", "collection", f"scryfall-{kind}.json")
    dest = os.path.abspath(dest)
    if os.path.exists(dest) and not force:
        print(f"using cached bulk file: {dest} (pass --refresh to re-download)")
        return dest
    print("finding the latest Scryfall bulk file…")
    catalog = json.loads(_get(BULK_LIST_URL))
    entry = next((b for b in catalog.get("data", []) if b.get("type") == kind), None)
    if not entry:
        raise RuntimeError(f"Scryfall has no bulk type '{kind}'")
    uri, size = entry["download_uri"], entry.get("size", 0)
    print(f"downloading {entry.get('name', kind)} (~{size // (1024*1024)} MB) …")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(uri, headers=_HEADERS)
    tmp = dest + ".part"
    with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, dest)
    print(f"saved {dest}")
    return dest

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
    q = ("SELECT name, color_identity, type_line, cmc, mana_cost, id "
         f"FROM read_json_auto('{bulk_path}', maximum_object_size=100000000) "
         "WHERE name IS NOT NULL")
    for name, ci, type_line, cmc, cost, sid in con.execute(q).fetchall():
        yield name, (ci or []), type_line, cmc, cost, sid
    con.close()


def _rows_json(bulk_path):
    with open(bulk_path, encoding="utf-8") as f:
        data = json.load(f)
    for c in data:
        if c.get("name"):
            yield (c["name"], c.get("color_identity", []), c.get("type_line"),
                   c.get("cmc"), c.get("mana_cost"), c.get("id"))


def build_index(bulk_path, use_duckdb=True):
    """name(normalized) -> {colors, type, mv, cost, id}. First printing per name wins."""
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
    for name, ci, type_line, cmc, cost, sid in rows:
        k = mtglib._norm(name)
        if k in idx:
            continue
        idx[k] = {"colors": " ".join(ci), "type": primary_type(type_line),
                  "mv": cmc if cmc is not None else None, "cost": cost or "",
                  "id": sid or ""}
    return idx


def enrich(collection_path, bulk_path, out_path, use_duckdb=True):
    coll = mtglib.load_collection(collection_path)
    index = build_index(bulk_path, use_duckdb)
    matched = 0
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Name", "Type", "MV", "Colors", "Cost", "Scryfall"])
        for card in sorted(coll, key=lambda c: c.name):
            a = index.get(mtglib._norm(card.name))
            if not a:
                continue
            matched += 1
            mv = "" if a["mv"] is None else (f"{a['mv']:g}")
            w.writerow([card.name, a["type"], mv, a["colors"], a["cost"],
                        a.get("id", "")])
    return matched, len(coll), len(index)


def main():
    ap = argparse.ArgumentParser(
        description="Enrich the collection with colors/types/mana value/Scryfall ids "
                    "from a Scryfall bulk file. With no --bulk it auto-downloads one.")
    ap.add_argument("--bulk", help="path to a Scryfall bulk JSON. Omit to auto-download.")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--out", default=None, help="default: <collection dir>/collection_attrs.csv")
    ap.add_argument("--refresh", action="store_true",
                    help="re-download the bulk file even if a cached copy exists")
    ap.add_argument("--no-duckdb", action="store_true")
    ap.add_argument("--stats", action="store_true", help="print a color/type breakdown after")
    args = ap.parse_args()

    bulk = args.bulk
    if not bulk:
        try:
            bulk = download_bulk(force=args.refresh)
        except Exception as e:
            print(f"error: could not download the Scryfall bulk file ({e}).\n"
                  "If you're offline or behind a proxy, download 'Oracle Cards' JSON from "
                  "https://scryfall.com/docs/api/bulk-data and pass it with --bulk.",
                  file=sys.stderr)
            return 2

    out = args.out or os.path.join(os.path.dirname(args.collection) or ".",
                                   "collection_attrs.csv")
    try:
        matched, total, dbn = enrich(args.collection, bulk, out, not args.no_duckdb)
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
