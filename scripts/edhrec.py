#!/usr/bin/env python3
"""EDHREC data client — community staples for a commander, grounded against YOUR
collection.

Fetches the public EDHREC JSON page for a commander (json.edhrec.com), computes each
recommended card's inclusion rate (num_decks / potential_decks), then splits the
recommendations into cards you OWN (grab them off the shelf — add these) vs. cards
you're MISSING (buy targets, ranked by how many decks run them). Stdlib + mtglib only;
responses are cached to disk (EDHREC changes slowly). Network / not-found errors
degrade gracefully to an `error` payload so callers show a note instead of crashing.

Usage:
  python3 edhrec.py "Atraxa, Praetors' Voice" --collection data/collection/collection.csv
"""
import json
import os
import re
import time
import urllib.request

import mtglib

BASE = "https://json.edhrec.com/pages/commanders/%s.json"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "data", "cache", "edhrec")
CACHE_TTL = 7 * 24 * 3600  # a week — inclusion rates drift slowly
_HEADERS = {"User-Agent": "MTGDeckBuilder/1.0 (personal collection tool)",
            "Accept": "application/json"}

# Sections that are noise for an owned/missing headline (synergy- or recency-sorted,
# not the commander's actual staples). Everything else feeds the pool.
_SKIP_SECTIONS = {"New Cards", "High Synergy Cards"}
_BASICS = {"plains", "island", "swamp", "mountain", "forest", "wastes"}


def _is_basic(name):
    """Basic lands are high-inclusion but useless as 'add'/'buy' advice — drop them."""
    return name.lower().replace("snow-covered ", "") in _BASICS


def slugify(name):
    """Commander name -> EDHREC slug. "Atraxa, Praetors' Voice" -> atraxa-praetors-voice.
    Uses the front face of a DFC/partner name; apostrophes drop, other punctuation -> '-'."""
    n = name.split("//")[0].strip().lower()
    n = n.replace("'", "").replace("’", "")           # drop straight + curly apostrophes
    n = re.sub(r"[^a-z0-9]+", "-", n).strip("-")
    return n or "commander"


def _fetch(slug, ttl=CACHE_TTL):
    """Return the parsed EDHREC page for a slug, using a disk cache within `ttl`."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, slug + ".json")
    if os.path.exists(cache) and (time.time() - os.path.getmtime(cache)) < ttl:
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    req = urllib.request.Request(BASE % slug, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.loads(r.read())
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def _sections(page):
    return page.get("container", {}).get("json_dict", {}).get("cardlists") or []


def _inclusion(cv):
    """Percent of this commander's decks that run the card (num_decks/potential_decks)."""
    nd, pot = cv.get("num_decks"), cv.get("potential_decks")
    return round(100 * nd / pot) if (nd and pot) else None


def recommendations(commander, coll_index, ttl=CACHE_TTL):
    """Grounded EDHREC recommendations for `commander`, cross-referenced with the
    collection. Returns owned/missing headline lists (by inclusion) + per-section detail.
    On any failure returns the same shape with an `error` string and empty lists."""
    slug = slugify(commander)
    base = {"commander": commander, "slug": slug,
            "url": "https://edhrec.com/commanders/" + slug}
    try:
        page = _fetch(slug, ttl)
    except Exception as e:  # 404 (unknown commander), network, parse — all non-fatal
        return {**base, "error": str(e), "sample_decks": None,
                "sections": [], "owned": [], "missing": []}

    cmd = page.get("container", {}).get("json_dict", {}).get("card", {})
    seen, owned, missing, sections = set(), [], [], []
    for sec in _sections(page):
        header = sec.get("header", "")
        cards = []
        for cv in sec.get("cardviews", []):
            name = cv.get("name")
            if not name:
                continue
            ref = mtglib.lookup(coll_index, name)
            card = {"name": name, "inclusion": _inclusion(cv),
                    "synergy": round((cv.get("synergy") or 0) * 100),
                    "owned": bool(ref), "qty": ref.quantity if ref else 0}
            cards.append(card)
            k = mtglib._norm(name)
            if header not in _SKIP_SECTIONS and k not in seen and not _is_basic(name):
                seen.add(k)
                (owned if ref else missing).append(card)
        sections.append({"header": header, "cards": cards})

    owned.sort(key=lambda c: -(c["inclusion"] or 0))
    missing.sort(key=lambda c: -(c["inclusion"] or 0))
    return {**base, "sample_decks": cmd.get("num_decks"),
            "sections": sections, "owned": owned, "missing": missing}


if __name__ == "__main__":
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="EDHREC staples for a commander, vs your collection.")
    ap.add_argument("commander")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()
    try:
        coll = mtglib.load_collection(args.collection)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(2)
    rec = recommendations(args.commander, mtglib.index_by_name(coll))
    if rec.get("error"):
        print(f"EDHREC lookup failed for '{rec['slug']}': {rec['error']}")
        raise SystemExit(1)
    print(f"{rec['commander']}  —  {rec['sample_decks'] or '?'} decks on EDHREC  ({rec['url']})")
    print(f"\n✓ STAPLES YOU OWN — add these ({len(rec['owned'])}):")
    for c in rec["owned"][:args.top]:
        print(f"   {str(c['inclusion'] or '?'):>3}%  {c['name']}  ({c['qty']}×)")
    print(f"\n✗ MISSING STAPLES — buy targets ({len(rec['missing'])}):")
    for c in rec["missing"][:args.top]:
        print(f"   {str(c['inclusion'] or '?'):>3}%  {c['name']}")
