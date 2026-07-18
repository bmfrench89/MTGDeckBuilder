#!/usr/bin/env python3
"""Cross-reference a list of "staple" cards for a commander/archetype against the
player's collection: report which staples they OWN and which they're MISSING
(a grounded buy-list).

The "internet -> your shelf" tool. Aggregators like EDHREC distill thousands of
decklists into a most-played list; this diffs that list against what you own.

HONESTY / ENVIRONMENT NOTE: EDHREC and Scryfall block direct page fetches in this
sandbox (403). So the staples file is curated by the assistant from knowledge +
web-search summaries + (when you provide it) an export you paste in — it is NOT a
live scrape. Every staples file should say where its list came from at the top.

Staples file format: one card per line. Optional leading "NN% " or "NN " play
percentage, and optional "# comment". Blank lines and #-lines are ignored.
  63% Sol Ring
  Rakdos Signet   # ramp
  Manabarbs

Usage:
  python3 staples_crossref.py --staples data/staples/kaervek.txt \
      --collection data/collection/collection_snapshot.txt
  python3 staples_crossref.py --staples s.txt --collection c.csv --missing-only
"""
import argparse
import re
import sys

import mtglib

_PCT = re.compile(r"^\s*(\d{1,3})\s*%?\s+(.*\S)\s*$")


def parse_staples(text):
    out = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = _PCT.match(line)
        if m and not line.lower().startswith(("sol ", "the ")):
            pct, name = int(m.group(1)), m.group(2).strip()
        else:
            pct, name = None, line
        out.append((name, pct))
    return out


def main():
    ap = argparse.ArgumentParser(description="Diff staples vs. collection.")
    ap.add_argument("--staples", required=True)
    ap.add_argument("--collection", required=True)
    ap.add_argument("--missing-only", action="store_true")
    ap.add_argument("--owned-only", action="store_true")
    args = ap.parse_args()

    try:
        with open(args.staples, encoding="utf-8") as f:
            staples = parse_staples(f.read())
        with open(args.collection, encoding="utf-8") as f:
            coll = mtglib.parse_collection(f.read())
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    idx = mtglib.index_by_name(coll)
    owned, missing = [], []
    for name, pct in staples:
        ref = mtglib.lookup(idx, name)
        (owned if ref else missing).append((name, pct, ref.quantity if ref else 0))

    total = len(staples)
    if not args.missing_only:
        print(f"OWNED staples: {len(owned)}/{total}")
        for name, pct, qty in sorted(owned, key=lambda x: (-(x[1] or 0), x[0])):
            tag = f"{pct}% " if pct is not None else ""
            q = f"  (x{qty})" if qty > 1 else ""
            print(f"  [x] {tag}{name}{q}")
    if not args.owned_only:
        print(f"\nMISSING (buy-list candidates): {len(missing)}/{total}")
        for name, pct, _ in sorted(missing, key=lambda x: (-(x[1] or 0), x[0])):
            tag = f"{pct}% " if pct is not None else ""
            print(f"  [ ] {tag}{name}")
    if not args.missing_only and not args.owned_only:
        pct_owned = round(100 * len(owned) / total) if total else 0
        print(f"\nYou own {len(owned)} of {total} listed staples ({pct_owned}%).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
