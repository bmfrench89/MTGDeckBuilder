#!/usr/bin/env python3
"""Scryfall rulings for one card — the official errata and interaction notes.

`carddb.py --verify` answers *what does this card say*. This answers the next
question: *what has WotC since clarified about it?* Rulings are where the
non-obvious interactions live (layers, timestamps, "this doesn't target",
"you may cast it any time you could cast an instant"), and they are the thing a
coach is most likely to half-remember.

Two GETs: `/cards/named?fuzzy=` resolves the name, then the card's `rulings_uri`
returns the list. Cached 30 days under `data/cache/rulings/` (gitignored). On a
failure the cache is consulted **regardless of age** — a two-month-old ruling is
strictly better than a shrug — and only then does the error payload come back.

Two traps this module is built around:

- **Fuzzy resolution can be confidently wrong.** Ask for a misspelling and
  Scryfall may hand back a different card entirely. The payload always carries
  both `requested` and the resolved `name`, and the CLI prints the mismatch
  loudly. Confirm it before you build on the answer.
- **`' // '` with spaces is the split-card separator.** Names go through
  `mtglib.front_face`; a naive `split("//")` would turn "SP//dr, Piloted by Peni"
  into "SP" and cache one card's rulings under another card's key.

Usage:
  python3 rulings.py "Sol Ring"
  python3 rulings.py "Yshtola, Night's Blessed" --json
  python3 rulings.py "Sol Ring" --refresh
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import mtglib

CACHE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "cache",
                 "rulings"))
# 30 days, matching carddb's verification cache. Rulings are amended far more
# slowly than they are asked about, and an expired entry costs one request.
CACHE_TTL = 30 * 24 * 3600
NAMED_URL = "https://api.scryfall.com/cards/named"
_HEADERS = {"User-Agent": "MTGDeckBuilder/1.0 (personal collection tool)",
            "Accept": "application/json"}


def _key(name):
    """The cache key: `_norm(front_face(name))` — the same key `carddb --verify`
    uses, and for the same reason (see the module docstring's `' // '` note)."""
    return mtglib._norm(mtglib.front_face(name))


def _cache_path(key, cache_dir):
    """A filesystem-safe file per key. Card names carry ':', '//' and apostrophes,
    none of which survive as path components — so the slug is lossy, the true key
    is stored INSIDE the file, and `_cache_get` re-checks it. Without that check a
    collision would serve one card's rulings under another card's name."""
    slug = re.sub(r"[^a-z0-9]+", "-", key).strip("-") or "card"
    return os.path.join(cache_dir, slug[:120] + ".json")


def _cache_get(key, cache_dir, ttl=None, stale_okay=False):
    """The cached payload, or None. `stale_okay=True` ignores the TTL — that is the
    failure path: an old answer beats no answer, as long as it says it's old.
    A corrupt or foreign-keyed cache file is a miss, never an exception."""
    ttl = CACHE_TTL if ttl is None else ttl
    try:
        with open(_cache_path(key, cache_dir), encoding="utf-8") as f:
            entry = json.load(f)
    except (OSError, ValueError):
        return None
    if entry.get("key") != key:
        return None
    age = time.time() - float(entry.get("fetched") or 0)
    if age > ttl and not stale_okay:
        return None
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return None
    payload = dict(payload)
    payload["source"] = "cache"
    if age > ttl:
        payload["source"] = "cache (stale, %s days old)" % int(age // 86400)
    return payload


def _cache_put(key, payload, cache_dir):
    """Best-effort — an unwritable cache dir must not fail a lookup."""
    try:
        os.makedirs(cache_dir, exist_ok=True)
        tmp = _cache_path(key, cache_dir) + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"key": key, "fetched": time.time(), "payload": payload}, f)
        os.replace(tmp, _cache_path(key, cache_dir))
    except OSError:
        pass


def _get_json(url, timeout=25):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _fetch_rulings(uri, delay=0.1):
    """Every page of a rulings list. Scryfall paginates with `has_more`/`next_page`;
    today's rulings lists fit on one page, but the contract says to follow it."""
    out, seen = [], 0
    while uri and seen < 10:
        page = _get_json(uri)
        for r in page.get("data") or []:
            out.append({"date": r.get("published_at") or "",
                        "comment": r.get("comment") or ""})
        uri = page.get("next_page") if page.get("has_more") else None
        seen += 1
        if uri and delay:
            time.sleep(delay)
    return out


def rulings_for(name, cache_dir=None, refresh=False, delay=0.1, ttl=None):
    """Scryfall's rulings for one card. Returns

        {'name': <resolved>, 'oracle_id', 'requested', 'rulings': [{'date','comment'}],
         'error': None, 'source': 'cache' | 'scryfall'}

    and never raises. `requested` keeps what was asked while `name` carries what
    Scryfall resolved — when they differ, the lookup found a *different card*, which
    the caller must confirm before trusting the answer.

    On any network failure the cache is consulted regardless of TTL before the error
    payload is returned."""
    cache_dir = cache_dir or CACHE_DIR
    requested = str(name or "").strip()
    if not requested:
        return {"name": "", "oracle_id": "", "requested": "", "rulings": [],
                "error": "no card name given", "source": ""}
    key = _key(requested)

    if not refresh:
        hit = _cache_get(key, cache_dir, ttl)
        if hit:
            hit["requested"] = requested
            return hit

    try:
        url = NAMED_URL + "?fuzzy=" + urllib.parse.quote(mtglib.front_face(requested))
        card = _get_json(url)
        if delay:
            time.sleep(delay)                    # Scryfall's courtesy delay
        uri = card.get("rulings_uri")
        rows = _fetch_rulings(uri, delay) if uri else []
        payload = {"name": card.get("name") or requested,
                   "oracle_id": card.get("oracle_id") or "",
                   "requested": requested, "rulings": rows, "error": None,
                   "source": "scryfall"}
        _cache_put(key, payload, cache_dir)
        return payload
    except Exception as e:
        stale = _cache_get(key, cache_dir, ttl, stale_okay=True)
        if stale:
            stale["requested"] = requested
            return stale
        return {"name": "", "oracle_id": "", "requested": requested, "rulings": [],
                "error": "Scryfall unreachable (%s) — no cached rulings for this "
                         "card, so treat any interaction claim as unverified." % e,
                "source": ""}


def print_rulings(r, out=print):
    """Resolved name first and a loud line when it isn't what was asked for — a
    fuzzy match to the wrong card is this tool's one silent-failure mode."""
    if r.get("error"):
        out('UNVERIFIED "%s" — %s' % (r["requested"], r["error"]))
        return
    out("%s   (%s)" % (r["name"], r.get("source") or "scryfall"))
    if mtglib._norm(r["name"]) != mtglib._norm(r["requested"]):
        out('  !! asked for "%s" — Scryfall resolved it to "%s". Confirm this is the '
            "card you meant before using these rulings." % (r["requested"], r["name"]))
    if not r["rulings"]:
        out("  (no rulings published for this card)")
        return
    for item in r["rulings"]:
        out("  %s  %s" % (item["date"] or "????-??-??", item["comment"]))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Scryfall rulings for one card — the official clarifications "
                    "behind an interaction. Cached 30 days in data/cache/rulings/; "
                    "on a network failure a stale cached copy is used and labeled.")
    ap.add_argument("card", nargs="*", help="the card name.")
    ap.add_argument("--json", action="store_true", help="machine-readable output.")
    ap.add_argument("--refresh", action="store_true", help="ignore the 30-day cache.")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    name = " ".join(args.card).strip()
    if not name:
        print('error: give a card name, e.g. rulings.py "Sol Ring"', file=sys.stderr)
        return 2

    r = rulings_for(name, refresh=args.refresh)
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print_rulings(r)
    return 1 if r.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
