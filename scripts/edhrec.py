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
    n = mtglib.front_face(name).lower()
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
        snap = _load_snapshot(slug)
        if snap:
            # Synthesize the full payload from the committed snapshot, so EVERY
            # consumer — /api/edhrec staples, the panel's same-slot alternatives,
            # the maps — works on a box that can't reach EDHREC (the hosted
            # server). Honestly labeled: source/saved say what's behind it.
            seen, owned, missing, cards = set(), [], [], []
            for k, name in sorted(snap.get("names", {}).items(),
                                  key=lambda kv: -(snap.get("inclusion", {}).get(kv[0]) or 0)):
                ref = mtglib.lookup(coll_index, name)
                card = {"name": name,
                        "inclusion": snap.get("inclusion", {}).get(k),
                        "synergy": snap.get("synergy", {}).get(k, 0),
                        "owned": bool(ref), "qty": ref.quantity if ref else 0}
                cards.append(card)
                if k not in seen and not _is_basic(name):
                    seen.add(k)
                    (owned if ref else missing).append(card)
            label = f"Snapshot (saved {snap.get('saved', '?')})"
            return {**base, "sample_decks": snap.get("sample_decks"),
                    "source": "snapshot", "saved": snap.get("saved"),
                    "sections": [{"header": label, "cards": cards}],
                    "owned": owned, "missing": missing}
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


# --------------------------------------------------------------------------- #
# Committed field snapshots — EDHREC data as a reference artifact.
#
# Why: the live JSON endpoint isn't reachable everywhere the app runs. The hosted
# server (PythonAnywhere free tier) only allows sites with official public API
# docs, which json.edhrec.com is not — so the field signal silently vanished
# there ("fit-only" verdicts, no Buy staples, manabase pass disabled). The fix is
# the same pattern as combos.csv and game_changers.txt: the signal lives in git
# as a small committed file, refreshed from a machine that CAN reach EDHREC
# (`python3 scripts/edhrec.py --snapshot-all ...` on the PC), and every surface —
# server, sandbox, offline dev — reads the same data. Precedence: live/cache
# first (freshest), snapshot as the fallback, {} only when neither exists.
# --------------------------------------------------------------------------- #
SNAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "data", "reference", "field")


def _snapshot_path(slug):
    return os.path.join(SNAP_DIR, slug + ".json")


def _load_snapshot(slug):
    try:
        with open(_snapshot_path(slug), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _distill(rec):
    """The three maps the fit engine consumes, from a recommendations() result."""
    inclusion, synergy, names = {}, {}, {}
    for sec in rec.get("sections", []):
        for c in sec.get("cards", []):
            name = c.get("name")
            if not name:
                continue
            keys = {mtglib._norm(name), mtglib._norm(mtglib.front_face(name))}
            names.setdefault(mtglib._norm(name), name)
            inc, syn = c.get("inclusion"), c.get("synergy")
            for k in keys:
                if inc and inc > inclusion.get(k, 0):
                    inclusion[k] = inc
                if syn is not None and syn > synergy.get(k, -999):
                    synergy[k] = syn
    return {"inclusion": inclusion, "synergy": synergy, "names": names}


def save_snapshot(commander, coll_index=None, ttl=CACHE_TTL):
    """Fetch live and write `data/reference/field/<slug>.json`. Returns the path,
    or None when EDHREC wasn't reachable (an unreachable fetch must never
    overwrite a good committed snapshot with an empty one)."""
    rec = recommendations(commander, coll_index if coll_index is not None else {}, ttl)
    if rec.get("error") or rec.get("source") == "snapshot":
        return None        # only LIVE data may write a snapshot — never itself
    data = _distill(rec)
    if not data["inclusion"]:
        return None
    from datetime import date
    payload = {"commander": commander, "slug": rec["slug"],
               "saved": date.today().isoformat(),
               "sample_decks": rec.get("sample_decks"), **data}
    os.makedirs(SNAP_DIR, exist_ok=True)
    path = _snapshot_path(rec["slug"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1)
    return path


def _snapshot_map(commander, key):
    snap = _load_snapshot(slugify(commander))
    return dict(snap.get(key) or {}) if snap else {}


def synergy_map(commander, coll_index=None, ttl=CACHE_TTL):
    """{normalized name: synergy} — how much MORE this commander plays a card than decks
    in general. Inclusion alone can't tell a signature card from a format staple:
    Command Tower is 93% inclusion / 5 synergy (everyone runs it), while Dragon Tempest is
    77% / 69 (it's a Dragon payoff). Synergy is what makes a card *this deck's* card."""
    rec = recommendations(commander, coll_index if coll_index is not None else {}, ttl)
    if rec.get("error"):
        return _snapshot_map(commander, "synergy")
    if rec.get("source") == "snapshot":
        # The snapshot stores these maps directly — read them lossless rather than
        # re-deriving from the synthesized sections (which only carry `names` keys).
        return _snapshot_map(commander, "synergy")
    out = {}
    for sec in rec.get("sections", []):
        for c in sec.get("cards", []):
            syn = c.get("synergy")
            if syn is None or not c.get("name"):
                continue
            k = mtglib._norm(c["name"])
            if syn > out.get(k, -999):
                out[k] = syn
            front = mtglib.front_face(c["name"])
            if front and front != c["name"]:
                out.setdefault(mtglib._norm(front), syn)
    return out


def field_names(commander, coll_index=None, ttl=CACHE_TTL):
    """{normalized name: EDHREC's properly-cased card name}. Needed because a card the
    player doesn't own has no collection entry to take a display name from — and
    "Sigarda's Aid" title-cased from a normalized key comes out as "Sigarda'S Aid"."""
    rec = recommendations(commander, coll_index if coll_index is not None else {}, ttl)
    if rec.get("error"):
        return _snapshot_map(commander, "names")
    if rec.get("source") == "snapshot":
        # The snapshot stores these maps directly — read them lossless rather than
        # re-deriving from the synthesized sections (which only carry `names` keys).
        return _snapshot_map(commander, "names")
    out = {}
    for sec in rec.get("sections", []):
        for c in sec.get("cards", []):
            name = c.get("name")
            if name:
                out.setdefault(mtglib._norm(name), name)
    return out


def inclusion_map(commander, coll_index=None, ttl=CACHE_TTL):
    """{normalized card name: inclusion %} for a commander — "what share of this
    commander's decks run this card". This is the signal the fit engine was missing: it
    knows a card is on-tribe and cheap, but not that the field considers it an
    auto-include. Returns {} on any failure so scoring silently falls back."""
    rec = recommendations(commander, coll_index if coll_index is not None else {}, ttl)
    if rec.get("error"):
        return _snapshot_map(commander, "inclusion")
    if rec.get("source") == "snapshot":
        # The snapshot stores these maps directly — read them lossless rather than
        # re-deriving from the synthesized sections (which only carry `names` keys).
        return _snapshot_map(commander, "inclusion")
    out = {}
    for sec in rec.get("sections", []):
        for c in sec.get("cards", []):
            inc = c.get("inclusion")
            if not inc:
                continue
            k = mtglib._norm(c["name"])
            if inc > out.get(k, 0):
                out[k] = inc
            front = mtglib.front_face(c["name"])        # DFC front face
            if front and front != c["name"]:
                fk = mtglib._norm(front)
                if inc > out.get(fk, 0):
                    out[fk] = inc
    return out


if __name__ == "__main__":
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="EDHREC staples for a commander, vs your collection.")
    ap.add_argument("commander", nargs="?")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--snapshot", action="store_true",
                    help="write data/reference/field/<slug>.json for COMMANDER")
    ap.add_argument("--snapshot-all", action="store_true",
                    help="snapshot every commander found in --decks-dir deck headers")
    ap.add_argument("--decks-dir", default="data/decks")
    args = ap.parse_args()
    try:
        coll = mtglib.load_collection(args.collection)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(2)
    idx = mtglib.index_by_name(coll)
    if args.snapshot_all or args.snapshot:
        import glob as _glob
        commanders = []
        if args.snapshot_all:
            for pth in sorted(_glob.glob(os.path.join(args.decks_dir, "*.txt"))):
                m = re.search(r"^#\s*Commander\s*:\s*(.+)$",
                              open(pth, encoding="utf-8").read(), re.M | re.I)
                if m:
                    c = re.split(r"\s{2,}|\(", m.group(1))[0].strip()
                    if c and c not in commanders:
                        commanders.append(c)
        else:
            commanders = [args.commander]
        wrote = 0
        for c in commanders:
            path = save_snapshot(c, idx)
            print(f"  {'OK  ' if path else 'FAIL'} {c}" + (f" -> {path}" if path else
                  "  (EDHREC unreachable — kept any existing snapshot)"))
            wrote += bool(path)
        print(f"{wrote}/{len(commanders)} snapshots written. Commit data/reference/field/ "
              "and pull on the server to give every surface the field signal.")
        raise SystemExit(0 if wrote == len(commanders) else 1)
    if not args.commander:
        print("error: pass a commander (or --snapshot-all)", file=sys.stderr)
        raise SystemExit(2)
    rec = recommendations(args.commander, idx)
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
