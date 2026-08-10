#!/usr/bin/env python3
"""Scryfall card data for this collection — two modes, one client.

**Enrichment** (`--collection`) fills in card attributes (colors / type / mana value /
what it taps for / oracle-derived flags / Scryfall id) — the fix for the "name-only
export" limitation.

Default: Scryfall's /cards/collection API — ~1 request per 75 cards, no download.
It resolves each owned card by its exact printing (set + collector number, or a
Scryfall id when the export has one) and falls back to the card name. It writes
data/collection/collection_attrs.csv, which mtglib.load_collection auto-merges, so
EVERY tool (curves, power color-scores, tribal counts, similar-commander color-fit
%, the click-a-card fit score) works across the whole collection.

Offline / bulk path: --download-bulk grabs Scryfall's ~40 MB "Oracle Cards" file
(cached), or --bulk points at one you already have. Uses DuckDB to stream it if
installed, else stdlib json.

**Verification** (`--verify`) answers a different question: *is this card real, and
what does it actually say?* It takes card NAMES (repeat the flag), batches them
through the same /cards/collection endpoint, retries each miss once as a fuzzy
name lookup, and prints VERBATIM oracle text — never a paraphrase. A name nothing
resolves is reported UNVERIFIED rather than guessed at, which is how a hallucinated
card dies here instead of in a decklist. Results are cached for 30 days under
data/cache/scryfall/. This is the mode `.claude/agents/card-verifier.md` runs; the
skill's grounding rule 3 ("verify card text past the knowledge cutoff") is the
reason it exists.

The two modes are exclusive: verification never touches the collection file, and
enrichment still requires --collection.

Usage:
  python3 carddb.py --collection data/collection/collection.csv          # API (default)
  python3 carddb.py --collection coll.csv --stats                        # + breakdown
  python3 carddb.py --collection coll.csv --download-bulk                # offline bulk
  python3 carddb.py --bulk oracle-cards.json --collection coll.csv       # local bulk file
  python3 carddb.py --verify "Sol Ring" --verify "Llanowar Elves"        # verify names
  python3 carddb.py --verify "Sol Ring" --json                           # machine-readable
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import mtglib
import oracle_flags

# collection_attrs.csv, in order. Produced/Flags were APPENDED after Scryfall so an
# attrs file written by an older build still loads (mtglib reads columns by header
# name and ignores the ones it doesn't know) and an older build still reads a new
# file. An absent Produced column means "unknown", not "produces nothing".
ATTRS_HEADER = ["Name", "Type", "MV", "Colors", "Cost", "Sub-types", "Scryfall",
                "Produced", "Flags"]

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


def subtypes_of(type_line):
    """Creature/etc. subtypes = the part after the em dash on the FRONT face, one per
    entry. 'Legendary Creature — Human Soldier Hero' -> 'Human;Soldier;Hero' (semicolons
    so mtglib._split_multi keeps them separate). These drive tribal detection
    (deck_fit / auto_build); mtglib reads the 'Sub-types' column."""
    left = (type_line or "").split("//")[0]
    return ";".join(left.split("—", 1)[1].split()) if "—" in left else ""


def _loads(v):
    """duckdb hands a JSON column back as a string; the stdlib path already has the
    parsed value. Anything unreadable degrades to None rather than killing a 40 MB run."""
    if not v or isinstance(v, (list, dict)):
        return v or None
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return None


def _rows_duckdb(bulk_path):
    """Yield Scryfall-shaped card dicts. produced_mana / oracle_text / card_faces are
    selected alongside the original columns so the bulk path derives exactly the same
    Produced/Flags the API path does. The SELECT stays inside build_index's existing
    try/except fallback: CI has no duckdb, and a schema drift here must degrade to the
    stdlib reader rather than fail the run."""
    import duckdb
    con = duckdb.connect()
    q = ("SELECT name, color_identity, type_line, cmc, mana_cost, id, "
         "produced_mana, oracle_text, to_json(card_faces) "
         f"FROM read_json_auto('{bulk_path}', maximum_object_size=100000000) "
         "WHERE name IS NOT NULL")
    for name, ci, type_line, cmc, cost, sid, prod, otext, faces in con.execute(q).fetchall():
        yield {"name": name, "color_identity": list(ci or []), "type_line": type_line,
               "cmc": cmc, "mana_cost": cost, "id": sid,
               "produced_mana": list(prod or []), "oracle_text": otext or "",
               "card_faces": _loads(faces)}
    con.close()


def _rows_json(bulk_path):
    with open(bulk_path, encoding="utf-8") as f:
        data = json.load(f)
    for c in data:
        if c.get("name"):
            yield c


def build_index(bulk_path, use_duckdb=True):
    """name(normalized) -> the same attrs dict the API path builds (colors, type,
    subtypes, mv, cost, id, produced, flags). First printing per name wins."""
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
    for c in rows:
        name = c.get("name")
        if not name:
            continue
        k = mtglib._norm(name)
        if k in idx:
            continue
        # One derivation for both paths — the bulk and API files must not drift.
        idx[k] = _attrs_from_scryfall(c)
    return idx


def _attrs_row(card, a):
    """One collection_attrs.csv row, in ATTRS_HEADER order."""
    return [card.name, a["type"], a["mv"], a["colors"], a["cost"],
            a.get("subtypes", ""), a.get("id", ""),
            a.get("produced", ""), a.get("flags", "")]


def enrich(collection_path, bulk_path, out_path, use_duckdb=True):
    coll = mtglib.load_collection(collection_path)
    index = build_index(bulk_path, use_duckdb)
    matched = 0
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(ATTRS_HEADER)
        for card in sorted(coll, key=lambda c: c.name):
            a = index.get(mtglib._norm(card.name))
            if not a:
                continue
            matched += 1
            w.writerow(_attrs_row(card, a))
    return matched, len(coll), len(index)


# ── Scryfall /cards/collection API enrichment (no bulk download) ─────────────
COLLECTION_URL = "https://api.scryfall.com/cards/collection"
_BATCH = 75  # Scryfall's max identifiers per /cards/collection request


def _post_collection(identifiers, retries=4):
    """POST up to 75 identifiers; return (found cards, not_found identifiers).

    Scryfall answers a burst with 429 and asks for a pause. Enriching a 2,000-card
    collection is ~28 back-to-back requests, so retry with exponential backoff rather
    than failing the whole run (which used to throw away every batch already fetched)."""
    body = json.dumps({"identifiers": identifiers}).encode()
    req = urllib.request.Request(COLLECTION_URL, data=body,
                                 headers={**_HEADERS, "Content-Type": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                j = json.loads(r.read())
            return j.get("data", []), j.get("not_found", [])
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == retries - 1:
                raise
            # Scryfall applies roughly a 30s cooldown once it starts 429ing, so short
            # exponential waits just burn retries — ramp straight into that window.
            wait = (5, 15, 30, 60)[min(attempt, 3)]
            print(f"  (Scryfall {e.code} — waiting {wait}s)", file=sys.stderr)
            time.sleep(wait)
    return [], []


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
    faces = c.get("card_faces") or []
    cost = c.get("mana_cost") or ""
    if not cost and faces:
        cost = " // ".join(f.get("mana_cost", "") for f in faces if f.get("mana_cost"))
    # Omen/adventure/MDFC layouts can carry type_line/cmc only on the FACES. Without this
    # fallback "Scavenger Regent // Exude Toxin" enriched with an empty Type, and the
    # name-based land heuristic then misread a Dragon creature as a land.
    type_line = c.get("type_line") or (faces[0].get("type_line", "") if faces else "")
    cmc = c.get("cmc")
    if cmc is None and faces:
        cmc = faces[0].get("cmc")
    mv = "" if cmc is None else f"{cmc:g}"
    # What it ACTUALLY taps for, plus the oracle-derived flag vocabulary. Both are
    # face-aware (oracle_flags never naive-splits "//"). Produced is written in WUBRGC
    # order to match the existing Colors style; an empty string here means "enriched,
    # produces nothing" — the absence of the whole column is what means "unknown".
    produced = oracle_flags.produced_of(c)
    return {"type": primary_type(type_line),
            "subtypes": subtypes_of(c.get("type_line", "")), "mv": mv,
            "colors": " ".join(ci), "cost": cost, "id": c.get("id", "") or "",
            "produced": " ".join(p for p in "WUBRGC" if p in produced),
            "flags": ";".join(sorted(oracle_flags.derive_flags(c)))}


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
        w.writerow(ATTRS_HEADER)
        for card in sorted(coll, key=lambda c: c.name):
            a = resolved.get(card.name)
            if a:
                w.writerow(_attrs_row(card, a))
    unmatched = sorted(c.name for c in coll if c.name not in resolved)
    return len(resolved), len(coll), unmatched


# ── single-card verification (--verify) ──────────────────────────────────────
# Where verified card objects are cached. Under data/cache/, which is gitignored:
# Scryfall's text is theirs, and a stale copy of it is a grounding hazard, so it
# lives with the other caches and expires.
VERIFY_CACHE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "cache",
                 "scryfall"))
# 30 days. Oracle text is amended (rare) far more slowly than it is asked about, and
# an expired entry costs one request, so this is long on purpose.
VERIFY_TTL = 30 * 24 * 3600
NAMED_URL = "https://api.scryfall.com/cards/named"

# The verified-row contract, in order. Every consumer (the CLI text block, --json,
# the card-verifier agent's table) reads these names and nothing else.
VERIFY_FIELDS = ("requested", "found", "name", "mana_cost", "type_line", "oracle_text",
                 "color_identity", "legal_commander", "set", "collector_number",
                 "scryfall_uri", "reason", "source")


def _verify_key(name):
    """The cache key: `_norm(front_face(name))`. Goes through front_face, so
    'SP//dr, Piloted by Peni' keeps its whole name — a naive split("//") would key it
    as 'sp' and collide with anything else starting there."""
    return mtglib._norm(mtglib.front_face(name))


def _cache_path(key, cache_dir):
    """A filesystem-safe file per key. The key itself is stored INSIDE the file and
    re-checked on read, so the lossy slug (card names carry ':' and '//') can never
    serve one card's text under another card's name."""
    slug = re.sub(r"[^a-z0-9]+", "-", key).strip("-") or "card"
    return os.path.join(cache_dir, slug[:120] + ".json")


def _cache_get(key, cache_dir, ttl=None):
    """The cached Scryfall card object, or None (missing / wrong key / expired /
    unreadable). A bad cache file is a miss, never an exception."""
    ttl = VERIFY_TTL if ttl is None else ttl   # read at call time, not at def time
    path = _cache_path(key, cache_dir)
    try:
        with open(path, encoding="utf-8") as f:
            entry = json.load(f)
    except (OSError, ValueError):
        return None
    if entry.get("key") != key:
        return None
    if time.time() - float(entry.get("fetched") or 0) > ttl:
        return None
    return entry.get("card") or None


def _cache_put(key, card, cache_dir):
    """Best-effort write — an unwritable cache dir must not fail a verification."""
    try:
        os.makedirs(cache_dir, exist_ok=True)
        tmp = _cache_path(key, cache_dir) + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"key": key, "fetched": time.time(), "card": card}, f)
        os.replace(tmp, _cache_path(key, cache_dir))
    except OSError:
        pass


def _legal_commander(c):
    """True / False / None — None means Scryfall didn't tell us, which is NOT 'illegal'.
    Conflating the two is the same class of mistake as produced=None vs set()."""
    legal = (c.get("legalities") or {}).get("commander")
    return None if not legal else legal == "legal"


def _verified_row(requested, c, source):
    return {"requested": requested, "found": True, "name": c.get("name", "") or "",
            "mana_cost": c.get("mana_cost") or _face_costs(c),
            "type_line": c.get("type_line") or _face_types(c),
            # Face-aware join (oracle_flags), never split("//") — the SP//dr bug class.
            "oracle_text": oracle_flags.oracle_text_of(c),
            "color_identity": " ".join(c.get("color_identity") or []),
            "legal_commander": _legal_commander(c),
            "set": (c.get("set") or "").upper(),
            "collector_number": str(c.get("collector_number") or ""),
            "scryfall_uri": c.get("scryfall_uri") or "", "reason": "", "source": source}


def _unverified_row(requested, reason):
    return {"requested": requested, "found": False, "name": "", "mana_cost": "",
            "type_line": "", "oracle_text": "", "color_identity": "",
            "legal_commander": None, "set": "", "collector_number": "",
            "scryfall_uri": "", "reason": reason, "source": ""}


def _face_costs(c):
    faces = c.get("card_faces") or []
    return " // ".join(f.get("mana_cost", "") for f in faces if f.get("mana_cost"))


def _face_types(c):
    faces = c.get("card_faces") or []
    return faces[0].get("type_line", "") if faces else ""


def _ident_key(ident):
    return json.dumps(ident, sort_keys=True)


def _fetch_named_fuzzy(name):
    """One fuzzy /cards/named lookup — the second chance for a misspelling or a
    back-face name that /cards/collection's exact matching rejects. Returns the card
    object or None; never raises."""
    url = NAMED_URL + "?fuzzy=" + urllib.parse.quote(name)
    try:
        return json.loads(_get(url))
    except Exception:
        return None


def verify_cards(names, cache_dir=None, refresh=False, delay=0.1):
    """Verify card NAMES against Scryfall. Returns one dict per requested name, in
    the order asked, shaped by VERIFY_FIELDS.

    Resolution, in three steps:
      1. cache (30 days) — free, and the reason a repeated question costs nothing;
      2. exact names batched through /cards/collection, reconciled **positionally**.
         Scryfall returns `data` in identifier order with the misses listed separately
         in `not_found`; matching the response back BY NAME breaks the moment someone
         asks about a back face or an adventure half, because the returned card is
         named "Front // Back" and the request wasn't;
      3. each miss retried once as a fuzzy name lookup, with the courtesy delay
         Scryfall asks for. The resolved name comes back in `name` while `requested`
         keeps what was asked, so a correction is visible rather than silent.

    Nothing resolves → `found: False` with a reason. That is where a hallucinated
    card name dies. Network failure is the same shape — the report IS the product, so
    an unreachable Scryfall yields UNVERIFIED rows, not an exception and not a guess.
    """
    cache_dir = cache_dir or VERIFY_CACHE_DIR
    names = [n for n in (str(n or "").strip() for n in names) if n]
    rows = {}          # index -> row
    pending = []       # (index, requested name)

    for i, name in enumerate(names):
        card = None if refresh else _cache_get(_verify_key(name), cache_dir)
        if card:
            rows[i] = _verified_row(name, card, "cache")
        else:
            pending.append((i, name))

    for start in range(0, len(pending), _BATCH):
        chunk = pending[start:start + _BATCH]
        idents = [{"name": n} for _i, n in chunk]
        try:
            data, not_found = _post_collection(idents)
        except Exception as e:
            for i, n in chunk:
                rows[i] = _unverified_row(n, f"network unreachable: {e}")
            continue
        misses = [_ident_key(x) for x in (not_found or [])]
        found_iter = iter(data or [])
        for (i, n), ident in zip(chunk, idents):
            key = _ident_key(ident)
            if key in misses:
                misses.remove(key)          # positional: this slot produced no card
                continue
            c = next(found_iter, None)
            if c is None:
                continue
            rows[i] = _verified_row(n, c, "scryfall")
            _cache_put(_verify_key(n), c, cache_dir)
        if delay:
            time.sleep(delay)

    for i, n in pending:                     # step 3 — fuzzy retry for whatever is left
        if i in rows:
            continue
        if delay:
            time.sleep(delay)
        c = _fetch_named_fuzzy(n)
        if c and c.get("name"):
            rows[i] = _verified_row(n, c, "fuzzy")
            _cache_put(_verify_key(n), c, cache_dir)
        else:
            rows[i] = _unverified_row(
                n, "no Scryfall match (exact or fuzzy) — treat the name as unverified")

    return [rows[i] for i in range(len(names))]


def print_verified(rows, out=print):
    """One block per card, or one UNVERIFIED line. Oracle text is printed VERBATIM:
    a paraphrase here is exactly the misreading grounding rule 3 exists to prevent."""
    for r in rows:
        if not r["found"]:
            out(f'UNVERIFIED "{r["requested"]}" — {r["reason"]}')
            continue
        legal = {True: "yes", False: "NO", None: "unknown"}[r["legal_commander"]]
        out(f'{r["name"]}  {r["mana_cost"] or "—"}')
        if mtglib._norm(r["name"]) != mtglib._norm(r["requested"]):
            out(f'  (asked for "{r["requested"]}" — Scryfall resolved it to this card)')
        out(f'  {r["type_line"]}')
        out(f'  identity: {r["color_identity"] or "colorless"} · commander-legal: {legal}'
            f' · {r["set"]} {r["collector_number"]} · via {r["source"]}')
        for line in (r["oracle_text"] or "(no oracle text)").split("\n"):
            out(f'  | {line}')
        if r["scryfall_uri"]:
            out(f'  {r["scryfall_uri"]}')
        out("")


def main():
    ap = argparse.ArgumentParser(
        description="Scryfall card data, two modes. ENRICH the collection with "
                    "colors/types/mana value/production/Scryfall ids (--collection; "
                    "default path is the /cards/collection API, --bulk / --download-bulk "
                    "for offline), or VERIFY named cards' real oracle text (--verify).")
    ap.add_argument("--collection", required=False,
                    help="enrichment mode: the collection CSV to enrich.")
    ap.add_argument("--verify", action="append", metavar="CARD NAME",
                    help="verification mode: verify this card name against Scryfall and "
                         "print its VERBATIM oracle text. Repeat for more cards — they go "
                         "out in one batched request.")
    ap.add_argument("--json", action="store_true",
                    help="with --verify, print the rows as JSON.")
    ap.add_argument("--out", default=None, help="default: <collection dir>/collection_attrs.csv")
    ap.add_argument("--bulk", help="use a local Scryfall bulk JSON (offline).")
    ap.add_argument("--download-bulk", action="store_true",
                    help="download Scryfall's ~40 MB Oracle Cards file, then enrich from it.")
    ap.add_argument("--refresh", action="store_true",
                    help="with --download-bulk, re-download even if a cached copy exists; "
                         "with --verify, ignore the 30-day cache and re-fetch.")
    ap.add_argument("--no-duckdb", action="store_true", help="bulk path only.")
    ap.add_argument("--stats", action="store_true", help="print a color/type breakdown after")
    args = ap.parse_args()

    # Exactly one mode. --collection stopped being argparse-required when --verify
    # arrived, so this check is what still makes enrichment demand it — enrich.bat and
    # the webapp upload route both call the enrichment path and would otherwise get a
    # confusing crash instead of a usage error.
    if bool(args.verify) == bool(args.collection):
        ap.error("choose one mode: --collection <csv> to enrich, or --verify "
                 '"<card name>" (repeatable) to verify card text')

    if args.verify:
        rows = verify_cards(args.verify, refresh=args.refresh)
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            print_verified(rows)
            unverified = [r["requested"] for r in rows if not r["found"]]
            if unverified:
                print(f"{len(unverified)}/{len(rows)} unverified — do not build around "
                      "a card this run could not confirm.", file=sys.stderr)
        return 0   # an UNVERIFIED report is a successful run; the report IS the product

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
        # Coverage of the production data the manabase/goldfish models prefer. Cards
        # without it aren't broken — every consumer falls back to color identity and
        # labels the fallback — but this is the number that says how much is guessed.
        known = sum(1 for c in coll if c.produced is not None)
        pct = round(100 * known / len(coll)) if coll else 0
        print(f"produced known: {known}/{len(coll)} ({pct}%) — the rest fall back to "
              "color identity, and every consumer says so.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
