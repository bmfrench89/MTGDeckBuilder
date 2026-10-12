#!/usr/bin/env python3
"""Official precon decklists — exactly what's in a product the player bought.

"I bought these precons" means ~300 cards arrive at once, and every one must be
named exactly before it can be counted (grounding rule #1). A 2026 precon is past
any model's memory, and web summaries of one decklist disagree with each other on
the counts — so neither is a source. MTGJSON publishes every official precon as a
machine-readable decklist (`DeckList.json` → `decks/<fileName>.json`); this fetches
the real list and renders it in the repo's deck-file format.

Network: MTGJSON is unreachable from a sandbox (the egress proxy answers 403), so a
session runs this through `deck-verify.yml`'s `precons` input. The runner fetches the
lists, verifies every card against Scryfall in the same run, enriches each list into
a companion `.attrs.csv`, and commits them to `data/reference/precons/`. Cached under
`data/cache/precon/` (gitignored); on a failure a cached copy is used regardless of
age, and only then does the command report UNREACHABLE (exit 2).

A precon file is a REFERENCE — what came in the box. It is not a deck the player
plays (those live in `data/decks/`) and not ownership: the cards become owned when a
session adds them to `owned_additions.txt` as a dated batch
(`docs/spec-card-intake.md`).

Usage:
  python3 precon.py "Wretched Ranks" "Multiverse Reforged" --out-dir data/reference/precons
  python3 precon.py --list "Foundations"
  python3 precon.py "Wretched Ranks" --json
"""
import argparse
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

import mtglib

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CACHE_DIR = os.path.join(ROOT, "data", "cache", "precon")
DECKLIST_URL = "https://mtgjson.com/api/v5/DeckList.json"
DECK_URL = "https://mtgjson.com/api/v5/decks/{}.json"
INDEX_TTL = 24 * 3600         # new products appear daily around a release
DECK_TTL = 30 * 24 * 3600     # a released list only changes for errata
_HEADERS = {"User-Agent": "MTGDeckBuilder/1.0 (personal collection tool)",
            "Accept": "application/json"}
_WUBRG = "WUBRG"
BOARDS = (("commander", "Commander"), ("mainBoard", "Mainboard"),
          ("sideBoard", "Sideboard (in the box, not in the 100)"))


class Unreachable(Exception):
    """MTGJSON could not be reached and nothing usable was cached."""


def _get_json(url, timeout=60):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":          # served gzipped without a Content-Encoding
        raw = gzip.decompress(raw)
    return json.loads(raw)


def _cache_file(key, cache_dir):
    return os.path.join(cache_dir, re.sub(r"[^A-Za-z0-9_.-]+", "_", key) + ".json")


def _cached(url, key, ttl, cache_dir, refresh=False):
    """`url`'s JSON, through a disk cache. A fresh cache entry is served without a
    request; on a network failure ANY cached copy is served (a week-old list of a
    released product beats no list) before Unreachable is raised. Never writes a
    partial file: the payload goes to `.part` and is renamed into place."""
    path = _cache_file(key, cache_dir)
    entry = None
    try:
        with open(path, encoding="utf-8") as f:
            entry = json.load(f)
    except (OSError, ValueError):
        entry = None
    if entry and not refresh and time.time() - float(entry.get("fetched") or 0) < ttl:
        return entry["payload"]
    try:
        payload = _get_json(url)
    except (urllib.error.URLError, OSError, ValueError) as e:
        if entry:
            return entry["payload"]
        raise Unreachable(f"{url}: {e}") from e
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(path + ".part", "w", encoding="utf-8") as f:
            json.dump({"fetched": time.time(), "payload": payload}, f)
        os.replace(path + ".part", path)
    except OSError:
        pass                                      # an unwritable cache is not fatal
    return payload


def deck_index(cache_dir=CACHE_DIR, refresh=False):
    """Every deck MTGJSON knows: [{code, fileName, name, releaseDate, type}]."""
    data = _cached(DECKLIST_URL, "DeckList", INDEX_TTL, cache_dir, refresh)
    return [d for d in (data or {}).get("data") or [] if isinstance(d, dict)]


def _fold(s):
    return re.sub(r"\s+", " ", (s or "").replace("’", "'")).strip().casefold()


def find(query, index):
    """(best match or None, other exact matches, near misses).

    Exact name match only (case/whitespace/curly-apostrophe folded) — or the
    MTGJSON fileName itself. A substring hit is offered as a near miss, never
    taken: "Ranks" must not silently become some other product's deck. Among exact
    matches (a deck name reused by a later product), a Commander Deck beats other
    types and the newest release wins; the rest are reported."""
    q = _fold(query)
    exact = [d for d in index if _fold(d.get("name")) == q or d.get("fileName") == query]
    exact.sort(key=lambda d: d.get("releaseDate") or "", reverse=True)   # newest first,
    exact.sort(key=lambda d: d.get("type") != "Commander Deck")          # then stable by type
    near = [d for d in index if q and q in _fold(d.get("name")) and d not in exact]
    return (exact[0] if exact else None), exact[1:], near[:10]


def _board(cards):
    """[(count, name)] for one board: copies of a name summed, back faces skipped.

    MTGJSON can carry a double-faced card's faces as separate entries (`side`
    'a'/'b') that share one `name` ("Front // Back"); counting both would put two
    copies of a card the box holds once. Only side 'a' (or no side) counts."""
    out, skipped = {}, 0
    for c in cards or []:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        if c.get("side") not in (None, "", "a"):
            skipped += 1
            continue
        try:
            n = max(1, int(c.get("count") or 1))
        except (TypeError, ValueError):
            n = 1
        out[c["name"]] = out.get(c["name"], 0) + n
    return [(n, name) for name, n in out.items()], skipped


def parse(payload, entry=None):
    """MTGJSON deck JSON → {name, code, release, type, commanders, boards, identity,
    total, skipped_faces}. `total` counts the commander + mainboard (the 100); the
    sideboard is listed and counted separately because a box can hold an extra
    card that is not part of the deck."""
    data = (payload or {}).get("data") or {}
    entry = entry or {}
    boards, skipped = {}, 0
    for key, _label in BOARDS:
        rows, s = _board(data.get(key))
        boards[key] = rows
        skipped += s
    shown = [c.get("name") for c in data.get("displayCommander") or [] if c.get("name")]
    cmdr_names = [name for _n, name in boards["commander"]]
    face = (shown or cmdr_names or [""])[0]
    ident = set()
    for c in data.get("commander") or []:
        ident.update(x for x in (c.get("colorIdentity") or []) if x in _WUBRG)
    return {
        "name": data.get("name") or entry.get("name") or "",
        "code": data.get("code") or entry.get("code") or "",
        "release": data.get("releaseDate") or entry.get("releaseDate") or "",
        "type": data.get("type") or entry.get("type") or "",
        "file": entry.get("fileName") or "",
        "commander": face,
        "commanders": cmdr_names,
        "boards": boards,
        "identity": "".join(c for c in _WUBRG if c in ident),
        "total": sum(n for n, _ in boards["commander"]) + sum(n for n, _ in boards["mainBoard"]),
        "skipped_faces": skipped,
    }


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", _fold(name)).strip("-") or "precon"


def render(deck, fetched=None):
    """The deck-file text (`# Key: value` headers, `# --- Section ---` groups)."""
    fetched = fetched or time.strftime("%Y-%m-%d")
    others = [c for c in deck["commanders"] if c != deck["commander"]]
    lines = [f"# Title: {deck['name']}",
             f"# Commander: {deck['commander']}",
             f"# Colors: {deck['identity'] or 'C'}",
             "# Archetype: Precon",
             f"# Source: MTGJSON deck \"{deck['name']}\" ({deck['code']}, {deck['type']}), "
             f"released {deck['release'] or 'unknown'}; fetched {fetched}"]
    if others:
        lines.append(f"# Note: other commander option(s) in the box: {', '.join(others)}")
    for key, label in BOARDS:
        rows = deck["boards"][key]
        if not rows:
            continue
        lines.append(f"# --- {label} ---")
        lines += [f"{n} {name}" for n, name in rows]
    return "\n".join(lines) + "\n"


def nonbasic_names(deck):
    """Every distinct card name in the box except basic lands (rule #9: basics are
    always owned and never tracked, so they are never verified, priced or added)."""
    seen = []
    for key, _label in BOARDS:
        for _n, name in deck["boards"][key]:
            if not mtglib.is_basic(name) and name not in seen:
                seen.append(name)
    return seen


def fetch(query, cache_dir=CACHE_DIR, refresh=False, index=None):
    """(deck dict | None, message). Raises Unreachable only when MTGJSON is down
    AND nothing is cached."""
    index = deck_index(cache_dir, refresh) if index is None else index
    best, others, near = find(query, index)
    if not best:
        hint = "; ".join(f"{d.get('name')} ({d.get('code')}, {d.get('releaseDate')})"
                         for d in near) or "none"
        return None, f"NOT FOUND: no MTGJSON deck named {query!r}. Near misses: {hint}"
    payload = _cached(DECK_URL.format(best["fileName"]), best["fileName"], DECK_TTL,
                      cache_dir, refresh)
    deck = parse(payload, best)
    msg = ""
    if others:
        msg = "also matched (not used): " + "; ".join(
            f"{d.get('name')} ({d.get('code')}, {d.get('type')}, {d.get('releaseDate')})"
            for d in others)
    return deck, msg


def summary(deck):
    b = deck["boards"]
    count = lambda key: sum(n for n, _ in b[key])
    basics = sum(n for key, _l in BOARDS for n, name in b[key] if mtglib.is_basic(name))
    lines = [f"== {deck['name']} — {deck['code']} {deck['type']}, released {deck['release']}",
             f"   commander: {deck['commander']}"
             + (f"  (also: {', '.join(c for c in deck['commanders'] if c != deck['commander'])})"
                if len(deck["commanders"]) > 1 else ""),
             f"   identity: {deck['identity'] or 'C'} · commander {count('commander')} + "
             f"mainboard {count('mainBoard')} = {deck['total']}"
             + (f" · sideboard {count('sideBoard')}" if b["sideBoard"] else "")
             + f" · basics {basics} · distinct non-basic {len(nonbasic_names(deck))}"]
    if deck["total"] != 100:
        lines.append(f"   WARNING: commander + mainboard = {deck['total']}, not 100 — "
                     "read the list before trusting it")
    if deck["skipped_faces"]:
        lines.append(f"   ({deck['skipped_faces']} back-face entries folded into their cards)")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("names", nargs="*", help="precon deck names, e.g. \"Wretched Ranks\"")
    ap.add_argument("--list", metavar="QUERY", help="list MTGJSON decks whose name contains QUERY")
    ap.add_argument("--out-dir", help="write <slug>.txt deck files here")
    ap.add_argument("--names-out", help="append every distinct non-basic card name here "
                                        "(one per line — the verify step's input)")
    ap.add_argument("--json", action="store_true", help="print the parsed decks as JSON")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache's age")
    ap.add_argument("--cache-dir", default=CACHE_DIR)
    a = ap.parse_args(argv)
    if not a.names and not a.list:
        ap.error("name at least one precon, or use --list QUERY")
    try:
        index = deck_index(a.cache_dir, a.refresh)
    except Unreachable as e:
        print(f"UNREACHABLE: MTGJSON ({e}). A sandbox has no route to it — run this "
              "through deck-verify.yml's `precons` input instead.", file=sys.stderr)
        return 2
    if a.list:
        q = _fold(a.list)
        hits = [d for d in index if q in _fold(d.get("name")) or q in _fold(d.get("code"))]
        for d in sorted(hits, key=lambda d: d.get("releaseDate") or ""):
            print(f"{d.get('releaseDate') or '?':10}  {d.get('code') or '?':6}  "
                  f"{d.get('type') or '?':18}  {d.get('name')}")
        print(f"{len(hits)} deck(s)")
        if not a.names:
            return 0
    decks, rc = [], 0
    for q in a.names:
        try:
            deck, msg = fetch(q, a.cache_dir, a.refresh, index=index)
        except Unreachable as e:
            print(f"UNREACHABLE: {q}: {e}", file=sys.stderr)
            rc = 2
            continue
        if not deck:
            print(msg, file=sys.stderr)
            rc = rc or 3
            continue
        decks.append(deck)
        if not a.json:
            print(summary(deck))
            if msg:
                print("   " + msg)
        if a.out_dir:
            os.makedirs(a.out_dir, exist_ok=True)
            path = os.path.join(a.out_dir, slug(deck["name"]) + ".txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(render(deck))
            if not a.json:
                print(f"   wrote {os.path.relpath(path)}")
        if not a.json:
            print("   " + render(deck).replace("\n", "\n   ").rstrip())
    if a.names_out and decks:
        with open(a.names_out, "a", encoding="utf-8") as f:
            for deck in decks:
                f.writelines(n + "\n" for n in nonbasic_names(deck))
    if a.json:
        print(json.dumps(decks, indent=1, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main())
