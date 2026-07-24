#!/usr/bin/env python3
"""Commander Spellbook client — every combo actually in a deck, plus the ones it's a
single card away from, via CSB's `find-my-combos` API. Expands the curated local
`combos.csv` (~22) to Commander Spellbook's full database (thousands).

Stdlib + mtglib only; responses cached to disk (keyed by the deck's card set). Network
or API errors degrade gracefully to an `error` payload with empty lists, so callers show
a note instead of crashing.

Usage:
  python3 spellbook.py --deck data/decks/mydeck.txt
"""
import hashlib
import json
import os
import re
import time
import urllib.request

import mtglib

API = "https://backend.commanderspellbook.com/find-my-combos"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "data", "cache", "spellbook")
CACHE_TTL = 7 * 24 * 3600
_HEADERS = {"User-Agent": "MTGDeckBuilder/1.0 (personal collection tool)",
            "Accept": "application/json", "Content-Type": "application/json"}


def _post(commanders, main):
    body = json.dumps({
        "commanders": [{"card": c, "quantity": 1} for c in commanders],
        "main": [{"card": n, "quantity": q} for n, q in main],
    }).encode()
    req = urllib.request.Request(API, data=body, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


def _combo(c):
    """Normalize a CSB variant to {id, cards, produces}."""
    return {
        "id": c.get("id"),
        "cards": [u["card"]["name"] for u in c.get("uses", []) if u.get("card")],
        "produces": [p["feature"]["name"] for p in c.get("produces", []) if p.get("feature")],
    }


def find_my_combos(commanders, main, ttl=CACHE_TTL):
    """POST the deck to CSB. Returns {present, almost, identity} (or an error payload).
    `main` is a list of (name, quantity). Cached by the (commanders, cards) signature."""
    sig = "|".join(sorted(commanders)) + "#" + "|".join(sorted(n for n, _ in main))
    key = hashlib.sha1(sig.encode()).hexdigest()[:16]
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, key + ".json")
    if os.path.exists(cache) and (time.time() - os.path.getmtime(cache)) < ttl:
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    try:
        j = _post(commanders, main)
    except Exception as e:
        return {"error": str(e), "present": [], "almost": [], "identity": None}
    res = j.get("results", {})
    out = {
        "identity": res.get("identity"),
        "present": [_combo(c) for c in res.get("included", [])],
        # one/two-away in-identity combos — the actionable upgrades
        "almost": [_combo(c) for c in res.get("almostIncluded", [])],
        "error": None,
    }
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(out, f)
    return out


def _commander_of(text):
    m = re.search(r"^#\s*Commander\s*:\s*(.+?)\s*$", text, re.MULTILINE | re.IGNORECASE)
    return re.split(r"\s{2,}|\(", m.group(1))[0].strip() if m else ""


def combos_for_deck(deck_path, ttl=CACHE_TTL):
    """Parse a deck .txt and return its CSB combos. `almost` combos are annotated with
    the `missing` card(s) not in the deck, ranked so 1-away combos come first."""
    text = open(deck_path, encoding="utf-8").read()
    commander = _commander_of(text)
    deck = mtglib.parse_deck(text)
    names = {mtglib._norm(d.name) for d in deck}
    if commander:
        names.add(mtglib._norm(commander))
    main = [(d.name, d.quantity) for d in deck]
    r = find_my_combos([commander] if commander else [], main, ttl)
    for c in r.get("almost", []):
        c["missing"] = [n for n in c["cards"] if mtglib._norm(n) not in names]
    r["almost"] = sorted([c for c in r.get("almost", []) if c.get("missing")],
                         key=lambda c: len(c["missing"]))
    return r


if __name__ == "__main__":
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="Commander Spellbook combos present / one-away in a deck.")
    ap.add_argument("--deck", required=True)
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()
    try:
        r = combos_for_deck(args.deck)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(2)
    if r.get("error"):
        print(f"Commander Spellbook lookup failed: {r['error']}")
        raise SystemExit(1)
    print(f"Deck identity: {r.get('identity') or '?'}")
    print(f"\nCOMBOS PRESENT ({len(r['present'])}):")
    for c in r["present"][:args.top]:
        print(f"   {' + '.join(c['cards'])}  →  {', '.join(c['produces']) or '?'}")
    one_away = [c for c in r["almost"] if len(c["missing"]) == 1]
    print(f"\nONE CARD AWAY ({len(one_away)} of {len(r['almost'])} near):")
    for c in one_away[:args.top]:
        print(f"   add {c['missing'][0]}  →  {' + '.join(c['cards'])}  ⇒  {', '.join(c['produces']) or '?'}")
