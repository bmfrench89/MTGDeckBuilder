#!/usr/bin/env python3
"""Enrich the whole collection with card attributes (colors / type / mana value /
Scryfall id) — the fix for the "name-only export" limitation.

Default: Scryfall's /cards/collection API — ~1 request per 75 cards, no download.
It resolves each owned card by its exact printing (set + collector number, or a
Scryfall id when the export has one) and falls back to the card name. It writes
data/collection/collection_attrs.csv, which mtglib.load_collection auto-merges, so
EVERY tool (curves, power color-scores, tribal counts, similar-commander color-fit
%, the click-a-card fit score) works across the whole collection.

Offline / bulk path: --download-bulk grabs Scryfall's ~40 MB "Oracle Cards" file
(cached), or --bulk points at one you already have. Uses DuckDB to stream it if
installed, else stdlib json.

Usage:
  python3 carddb.py --collection data/collection/collection.csv          # API (default)
  python3 carddb.py --collection coll.csv --stats                        # + breakdown
  python3 carddb.py --collection coll.csv --download-bulk                # offline bulk
  python3 carddb.py --bulk oracle-cards.json --collection coll.csv       # local bulk file
"""
import argparse
import csv
import json
import os
import sys
import time
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


# ── Scryfall /cards/collection API enrichment (no bulk download) ─────────────
COLLECTION_URL = "https://api.scryfall.com/cards/collection"
_BATCH = 75  # Scryfall's max identifiers per /cards/collection request


def _post_collection(identifiers):
    """POST up to 75 identifiers; return (found cards, not_found identifiers)."""
    body = json.dumps({"identifiers": identifiers}).encode()
    req = urllib.request.Request(COLLECTION_URL, data=body,
                                 headers={**_HEADERS, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.loads(r.read())
    return j.get("data", []), j.get("not_found", [])


def _best_identifier(card):
    """Best Scryfall identifier for a collection Card + a key to match the response
    back. Prefer the exact printing (id, then set+number) for the correct art/id;
    fall back to name (resolves attributes fine, incl. DFC/adventure front names)."""
    sid = (getattr(card, "scryfall_id", "") or "").strip()
    if sid:
        return {"id": sid}, ("id", sid)
    setc = (getattr(card, "set_code", "") or "").strip().lower()
    num = str(getattr(card, "collector_number", "") or "").strip()
    if setc and num:
        return {"set": setc, "collector_number": num}, ("sn", setc, num)
    return {"name": card.name}, ("name", mtglib._norm(card.name))


def _response_keys(c):
    """Every key a returned Scryfall card could be matched back on."""
    keys = []
    if c.get("id"):
        keys.append(("id", c["id"]))
    if c.get("set") and c.get("collector_number") is not None:
        keys.append(("sn", str(c["set"]).lower(), str(c["collector_number"])))
    name = c.get("name") or ""
    if name:
        keys.append(("name", mtglib._norm(name)))
        front = name.split("//")[0].strip()   # DFC / adventure front face
        if front:
            keys.append(("name", mtglib._norm(front)))
    return keys


def _attrs_from_scryfall(c):
    ci = c.get("color_identity", []) or []
    cost = c.get("mana_cost") or ""
    if not cost and c.get("card_faces"):
        cost = " // ".join(f.get("mana_cost", "") for f in c["card_faces"]
                           if f.get("mana_cost"))
    cmc = c.get("cmc")
    mv = "" if cmc is None else f"{cmc:g}"
    return {"type": primary_type(c.get("type_line", "")), "mv": mv,
            "colors": " ".join(ci), "cost": cost, "id": c.get("id", "") or ""}


def enrich_api(collection_path, out_path, delay=0.1, log=None):
    """Enrich via Scryfall's /cards/collection API — no ~40 MB bulk download.
    ~1 request per 75 cards. Returns (matched, total, sorted unmatched names)."""
    log = log or (lambda *_a: None)
    coll = mtglib.load_collection(collection_path)
    resolved = {}  # card.name -> attrs

    def run(cards, ident_fn):
        submit, keymap = [], {}
        for card in cards:
            ident, key = ident_fn(card)
            if ident is None:
                continue
            submit.append(ident)
            keymap.setdefault(key, card)
        for i in range(0, len(submit), _BATCH):
            data, _nf = _post_collection(submit[i:i + _BATCH])
            for c in data:
                card = next((keymap[k] for k in _response_keys(c) if k in keymap), None)
                if card is not None:
                    resolved[card.name] = _attrs_from_scryfall(c)
            log(f"  …resolved {len(resolved)}/{len(coll)}")
            time.sleep(delay)

    run(coll, _best_identifier)  # round 1: exact printing where the export has it
    missing = [c for c in coll if c.name not in resolved]
    if missing:  # round 2: name fallback (e.g. ManaPool set code != Scryfall's)
        run(missing, lambda c: ({"name": c.name}, ("name", mtglib._norm(c.name))))

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Name", "Type", "MV", "Colors", "Cost", "Scryfall"])
        for card in sorted(coll, key=lambda c: c.name):
            a = resolved.get(card.name)
            if a:
                w.writerow([card.name, a["type"], a["mv"], a["colors"], a["cost"], a["id"]])
    unmatched = sorted(c.name for c in coll if c.name not in resolved)
    return len(resolved), len(coll), unmatched


def main():
    ap = argparse.ArgumentParser(
        description="Enrich the collection with colors/types/mana value/Scryfall ids. "
                    "Default: Scryfall's /cards/collection API (no download). Use "
                    "--bulk / --download-bulk for the offline bulk-file path.")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--out", default=None, help="default: <collection dir>/collection_attrs.csv")
    ap.add_argument("--bulk", help="use a local Scryfall bulk JSON (offline).")
    ap.add_argument("--download-bulk", action="store_true",
                    help="download Scryfall's ~40 MB Oracle Cards file, then enrich from it.")
    ap.add_argument("--refresh", action="store_true",
                    help="with --download-bulk, re-download even if a cached copy exists.")
    ap.add_argument("--no-duckdb", action="store_true", help="bulk path only.")
    ap.add_argument("--stats", action="store_true", help="print a color/type breakdown after")
    args = ap.parse_args()

    out = args.out or os.path.join(os.path.dirname(args.collection) or ".",
                                   "collection_attrs.csv")
    try:
        if args.bulk or args.download_bulk:
            bulk = args.bulk or download_bulk(force=args.refresh)
            matched, total, dbn = enrich(args.collection, bulk, out, not args.no_duckdb)
            print(f"card DB: {dbn} cards. Matched {matched}/{total} owned cards "
                  f"({round(100 * matched / total) if total else 0}%).")
            unmatched_n = total - matched
        else:
            print("enriching via Scryfall /cards/collection API (no bulk download)…")
            matched, total, unmatched = enrich_api(args.collection, out, log=print)
            print(f"Matched {matched}/{total} owned cards "
                  f"({round(100 * matched / total) if total else 0}%).")
            unmatched_n = len(unmatched)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: enrichment failed ({e}).\n"
              "If Scryfall is unreachable, use the offline path: download 'Oracle Cards' "
              "JSON from https://scryfall.com/docs/api/bulk-data and pass it with --bulk.",
              file=sys.stderr)
        return 2

    print(f"wrote {out} — load_collection now merges it automatically.")
    if unmatched_n:
        print(f"  ({unmatched_n} unmatched — usually tokens, non-English, or very new; "
              "add them to owned_additions or try --download-bulk for a fresh snapshot.)")

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
