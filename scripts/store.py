"""The collection database: the app's own record of every card the player owns.

docs/spec-target-architecture.md, Phase 1. One SQLite file (stdlib `sqlite3`) on the
server, `data/collection/collection.db`, gitignored and never synced. Once it exists
it IS the collection: exports stop being the base layer and become one-time imports
that can only add.

Two tables carry the meaning:
  * `holdings`: one row per physical card (key = normalized front face), with its
    count and the card data (types, price, …) as JSON.
  * `ledger`: every change ever made (seed, add, set, merge, ingest), who made it and
    why. A count is never edited without a ledger row, so "why do I own 3 of these?"
    always has an answer.

READING is `mtglib.load_collection(<path>.db)`, so every engine is unchanged.
Everything that WRITES lives here.

Seeding (`seed`) is the one-time union the player asked for on 2026-10-13: "I just
need all cards accounted for." No export is the truth; each one is where the cards
were at the time. So a card's starting count is

    max(current export, August list, floor batches) + added batches
    raised to at least what one sleeved deck holds

with every source recorded on the card's seed row. Shared-card shortfalls across
decks are REPORTED, never invented into extra copies.

Phase 1b keeps the rest of the player's data here too: every deck file and pins.csv
with each revision (`files`, `file_revisions`), the named members (`members`, plus the
owner's settings in `meta`) and the labelled activity log (`activity`). Password
hashes arrive and leave as opaque strings: hashing stays in webapp/users.py, so this
module stays stdlib-only, and no export ever includes the `members` table.

CLI:
    python3 scripts/store.py seed   --db D [--export CSV] [--august TXT]
                                    [--additions TXT] [--decks-dir DIR] [--write]
    python3 scripts/store.py ingest --db D --additions TXT
    python3 scripts/store.py stats  --db D
    python3 scripts/store.py capture|restore|history …     (deck files, see below)
    python3 scripts/store.py activity --db D [--limit N]
    python3 scripts/store.py backup --db D --to FILE [--without-hashes]
"""
from __future__ import annotations

import argparse
import csv
import datetime
import glob
import io
import json
import os
import sqlite3
import sys

import mtglib

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS holdings (
    key TEXT PRIMARY KEY, name TEXT NOT NULL, qty INTEGER NOT NULL,
    card TEXT NOT NULL DEFAULT '{}', updated TEXT);
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, key TEXT NOT NULL,
    name TEXT NOT NULL, delta INTEGER NOT NULL, qty_after INTEGER NOT NULL,
    action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', by TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS ledger_key ON ledger(key);
CREATE TABLE IF NOT EXISTS ingested (
    block TEXT PRIMARY KEY, header TEXT, at TEXT, copies INTEGER);
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY, text TEXT NOT NULL, sha TEXT NOT NULL,
    live INTEGER NOT NULL DEFAULT 1, updated TEXT);
CREATE TABLE IF NOT EXISTS file_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, sha TEXT NOT NULL,
    text TEXT, at TEXT NOT NULL, action TEXT NOT NULL, by TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS file_revisions_path ON file_revisions(path);
CREATE TABLE IF NOT EXISTS members (
    key TEXT PRIMARY KEY, display TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member',
    hash TEXT NOT NULL DEFAULT '', ver INTEGER NOT NULL DEFAULT 1,
    disabled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, by TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL, deck TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '');
"""

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                          "data", "collection", "collection.db")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path):
    con = sqlite3.connect(path, timeout=10)
    con.executescript(SCHEMA)
    return con


def exists(path) -> bool:
    """A seeded database: the file is there AND it holds cards."""
    if not (path and os.path.exists(path)):
        return False
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return bool(con.execute("SELECT 1 FROM holdings LIMIT 1").fetchone())
        finally:
            con.close()
    except sqlite3.Error:
        return False


# --------------------------------------------------------------------------- #
# Low-level change: every write goes through _change, which writes the ledger row.
# --------------------------------------------------------------------------- #
def _get(con, key):
    return con.execute("SELECT name, qty, card FROM holdings WHERE key=?",
                       (key,)).fetchone()


def _change(con, name, *, delta=None, to=None, action, detail="", by="", card=None,
            at=None):
    """Apply one change and log it. Exactly one of `delta` / `to`. A count never goes
    below zero. `card` (a dict) replaces the stored card data only when the holding
    had none, or is merged key-by-key when given (richer data wins, nothing lost).
    Returns the new count, or None when nothing changed (no ledger row either)."""
    key = mtglib.card_key(name)
    if not key or mtglib.is_basic(name):
        return None
    row = _get(con, key)
    old = row[1] if row else 0
    new = max(0, (old + delta) if delta is not None else int(to))
    stored = json.loads(row[2]) if row and row[2] else {}
    if card:
        merged = dict(stored)
        # Empty values never overwrite stored data, EXCEPT `produced`: an empty list
        # there means "enriched, makes no mana" (Maze of Ith) — not "unknown".
        merged.update({k: v for k, v in card.items()
                       if k == "produced" or v not in (None, "", [])})
        stored = merged
    if new == old and row is not None and not card:
        return None
    at = at or _now()
    disp = row[0] if row else name
    if row:
        con.execute("UPDATE holdings SET qty=?, card=?, updated=? WHERE key=?",
                    (new, json.dumps(stored, sort_keys=True), at, key))
    else:
        con.execute("INSERT INTO holdings(key, name, qty, card, updated) VALUES(?,?,?,?,?)",
                    (key, disp, new, json.dumps(stored, sort_keys=True), at))
    if new != old or row is None:
        con.execute("INSERT INTO ledger(at, key, name, delta, qty_after, action, detail, by)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (at, key, disp, new - old, new, action, detail, by))
    return new


# --------------------------------------------------------------------------- #
# The operations the app and the sync call.
# --------------------------------------------------------------------------- #
def add_rows(path, rows, *, action="add", detail="", by="", date=None):
    """Add copies: rows = [(qty, name)]. Returns (copies, distinct) actually added."""
    date = date or datetime.date.today().isoformat()
    copies = distinct = 0
    con = connect(path)
    try:
        with con:
            for q, n in rows:
                if q <= 0 or mtglib.is_basic(n):
                    continue
                if _change(con, n, delta=int(q), action=action, detail=detail, by=by,
                           card={"date_added": date}) is not None:
                    copies += int(q)
                    distinct += 1
    finally:
        con.close()
    return copies, distinct


def set_qty(path, name, qty, *, reason="", by=""):
    """Set one card's count (sold, traded, lost, miscounted). Only a card the
    database already holds can be set: a brand-new card goes through Add a batch,
    which verifies the name first. Returns (old, new) or None if unknown."""
    con = connect(path)
    try:
        row = _get(con, mtglib.card_key(name))
        if row is None:
            return None
        with con:
            _change(con, row[0], to=max(0, int(qty)), action="set", detail=reason, by=by)
        return row[1], max(0, int(qty))
    finally:
        con.close()


def merge_export(path, cards, *, by="", label="uploaded export"):
    """Fold a full export in WITHOUT ever lowering a count: each card rises to the
    export's count if that is higher, and the export's card data (price, printing,
    types) is stored either way. Returns {raised, added_copies, new_cards, refreshed}."""
    raised = added = new_cards = refreshed = 0
    con = connect(path)
    try:
        with con:
            for c in cards:
                if mtglib.is_basic(c.name):
                    continue
                key = mtglib.card_key(c.name)
                row = _get(con, key)
                old = row[1] if row else 0
                data = mtglib.card_to_dict(c)
                if c.quantity > old:
                    _change(con, c.name, to=c.quantity, action="merge-export",
                            detail=label, by=by, card=data)
                    raised += 1
                    added += c.quantity - old
                    new_cards += row is None
                else:
                    _change(con, c.name, delta=0, action="merge-export", detail=label,
                            by=by, card=data)
                    refreshed += 1
    finally:
        con.close()
    return {"raised": raised, "added_copies": added, "new_cards": new_cards,
            "refreshed": refreshed}


def ingest(path, additions_path, *, by="sync"):
    """Apply every `owned_additions.txt` block the database hasn't seen yet. This is
    how batches a Claude session commits (and the sync pulls) reach the database.
    Idempotent: a block is recorded by id and never applied twice. A `[floor]`
    block raises counts to its rows instead of adding. Returns (blocks, copies)."""
    if not os.path.exists(additions_path):
        return 0, 0
    with open(additions_path, encoding="utf-8") as f:
        blocks = mtglib.addition_blocks(f.read())
    nb = nc = 0
    con = connect(path)
    try:
        with con:
            seen = {r[0] for r in con.execute("SELECT block FROM ingested")}
            for b in blocks:
                if b["id"] in seen:
                    continue
                copies = 0
                for q, n in b["rows"]:
                    if mtglib.is_basic(n):
                        continue
                    if b["floor"]:
                        row = _get(con, mtglib.card_key(n))
                        if (row[1] if row else 0) < q:
                            _change(con, n, to=q, action="ingest-floor",
                                    detail=b["header"], by=by,
                                    card={"date_added": b["date"]} if b["date"] else None)
                            copies += q - (row[1] if row else 0)
                    else:
                        _change(con, n, delta=q, action="ingest", detail=b["header"],
                                by=by, card={"date_added": b["date"]} if b["date"] else None)
                        copies += q
                con.execute("INSERT INTO ingested(block, header, at, copies) VALUES(?,?,?,?)",
                            (b["id"], b["header"], _now(), copies))
                nb += 1
                nc += copies
    finally:
        con.close()
    return nb, nc


# --------------------------------------------------------------------------- #
# The one-time union.
# --------------------------------------------------------------------------- #
def _live_decks(decks_dir):
    import deck_conflicts
    out = []
    for p in sorted(glob.glob(os.path.join(decks_dir or "", "*.txt"))):
        if deck_conflicts.is_study_deck(p):
            continue
        with open(p, encoding="utf-8") as f:
            out.append((os.path.basename(p)[:-4], mtglib.parse_deck(f.read())))
    return out


def plan_seed(export_path=None, august_path=None, additions_path=None, decks_dir=None):
    """Compute the union WITHOUT writing anything. -> (cards, report).

    cards: {key: {"name", "qty", "card": dict, "src": {...}}}
    report: counts and the lists a person should look at."""
    def read(p):
        if p and os.path.exists(p):
            with open(p, encoding="utf-8-sig") as f:
                return mtglib.parse_collection(f.read())
        return []

    export, august = read(export_path), read(august_path)
    blocks = []
    if additions_path and os.path.exists(additions_path):
        with open(additions_path, encoding="utf-8") as f:
            blocks = mtglib.addition_blocks(f.read())

    acc = {}

    def slot(name):
        k = mtglib.card_key(name)
        if k not in acc:
            acc[k] = {"name": name, "card": {}, "src": {"export": 0, "august": 0,
                      "floor": 0, "added": 0, "deck": 0, "committed": 0, "decks": []}}
        return acc[k]

    for c in export:
        if mtglib.is_basic(c.name):
            continue
        s = slot(c.name)
        s["name"] = c.name                       # the export's spelling wins
        s["src"]["export"] += c.quantity
        s["card"] = mtglib.card_to_dict(c)
    for c in august:
        if mtglib.is_basic(c.name):
            continue
        s = slot(c.name)
        s["src"]["august"] += c.quantity
    for b in blocks:
        for q, n in b["rows"]:
            if mtglib.is_basic(n):
                continue
            s = slot(n)
            s["src"]["floor" if b["floor"] else "added"] = (
                max(s["src"]["floor"], q) if b["floor"] else s["src"]["added"] + q)
            if b["date"] and b["date"] > s["card"].get("date_added", ""):
                s["card"]["date_added"] = b["date"]
    for stem, cards in _live_decks(decks_dir):
        for c in cards:
            if mtglib.is_basic(c.name):
                continue
            s = slot(c.name)
            s["src"]["deck"] = max(s["src"]["deck"], c.quantity)
            s["src"]["committed"] += c.quantity
            s["src"]["decks"].append(stem)

    rep = {"export_rows": len(export), "august_rows": len(august),
           "blocks": len(blocks), "decks": len(_live_decks(decks_dir)),
           "lost_by_export": [], "from_decks_only": [], "short_across_decks": []}
    for k, s in acc.items():
        src = s["src"]
        base = max(src["export"], src["august"], src["floor"])
        qty = max(base + src["added"], src["deck"])
        s["qty"] = qty
        if export and src["august"] > src["export"]:
            rep["lost_by_export"].append((s["name"], src["august"], src["export"]))
        if src["deck"] and base + src["added"] == 0:
            rep["from_decks_only"].append((s["name"], src["deck"], src["decks"]))
        if src["committed"] > qty:
            rep["short_across_decks"].append((s["name"], qty, src["committed"],
                                              src["decks"]))
    rep["unique"] = sum(1 for s in acc.values() if s["qty"] > 0)
    rep["copies"] = sum(s["qty"] for s in acc.values())
    for k in ("lost_by_export", "from_decks_only", "short_across_decks"):
        rep[k].sort(key=lambda t: t[0].lower())
    return acc, rep


def report_text(rep, written=False):
    L = [f"Collection database seed — {'WRITTEN' if written else 'DRY RUN (nothing written)'}",
         f"Sources: export {rep['export_rows']} cards · August list {rep['august_rows']} "
         f"cards · {rep['blocks']} added-card blocks · {rep['decks']} sleeved decks",
         f"Result: {rep['unique']} different cards, {rep['copies']} copies.", ""]

    def section(title, rows, fmt):
        L.append(f"{title}: {len(rows)}")
        L.extend("  " + fmt(r) for r in rows)
        L.append("")
    section("On the August list but missing or lower in the current export (KEPT at the "
            "August count)", rep["lost_by_export"],
            lambda r: f"{r[0]} — August {r[1]}, export {r[2]}")
    section("Only known from a sleeved deck (KEPT: the deck holds it)",
            rep["from_decks_only"], lambda r: f"{r[0]} — {r[1]} in {', '.join(r[2])}")
    section("Shared across decks beyond the copies owned (NOT invented — check these)",
            rep["short_across_decks"],
            lambda r: f"{r[0]} — own {r[1]}, decks list {r[2]}: {', '.join(r[3])}")
    return "\n".join(L)


def seed(path, export_path=None, august_path=None, additions_path=None,
         decks_dir=None, *, write=False, by="seed"):
    """Plan the union and, with write=True, create the database from it. Refuses to
    seed a database that already holds cards (that would double every count).
    Every block in the additions file is marked ingested, so a later `ingest` only
    applies NEW batches. -> report text."""
    acc, rep = plan_seed(export_path, august_path, additions_path, decks_dir)
    if not write:
        return report_text(rep)
    if exists(path):
        raise RuntimeError(f"{path} already holds a collection; refusing to seed twice")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    at = _now()
    con = connect(path)
    try:
        with con:
            for s in acc.values():
                if s["qty"] <= 0:
                    continue
                src = {k: v for k, v in s["src"].items() if v and k != "decks"}
                _change(con, s["name"], to=s["qty"], action="seed",
                        detail=json.dumps(src, sort_keys=True), by=by,
                        card=s["card"] or None, at=at)
            if additions_path and os.path.exists(additions_path):
                with open(additions_path, encoding="utf-8") as f:
                    for b in mtglib.addition_blocks(f.read()):
                        con.execute("INSERT OR IGNORE INTO ingested(block, header, at, "
                                    "copies) VALUES(?,?,?,?)",
                                    (b["id"], b["header"], at,
                                     sum(q for q, _ in b["rows"])))
            con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('seeded_at', ?)",
                        (at,))
            con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('seed_report', ?)",
                        (report_text(rep, written=True),))
    finally:
        con.close()
    return report_text(rep, written=True)


# --------------------------------------------------------------------------- #
# Reads the app shows (counts come from mtglib.load_collection).
# --------------------------------------------------------------------------- #
def meta(path, key):
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            r = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return r[0] if r else None
        finally:
            con.close()
    except sqlite3.Error:
        return None


def recent_changes(path, limit=12):
    """The newest ledger rows, newest first, as dicts. Seed rows are summarised
    into one line by the caller, so they're left out here."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT at, name, delta, qty_after, action, detail, by FROM ledger "
                "WHERE action != 'seed' AND delta != 0 ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    keys = ("at", "name", "delta", "qty_after", "action", "detail", "by")
    return [dict(zip(keys, r)) for r in rows]


def history(path, name):
    """Every ledger row for one card, oldest first."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT at, delta, qty_after, action, detail, by FROM ledger WHERE key=? "
                "ORDER BY id", (mtglib.card_key(name),)).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    keys = ("at", "delta", "qty_after", "action", "detail", "by")
    return [dict(zip(keys, r)) for r in rows]


EXPORT_COLUMNS = ("Quantity", "Name", "Mana Value", "Colors", "Identities", "Mana cost",
                  "Types", "Sub-types", "Super-types", "Rarity", "Scryfall ID",
                  "Set code", "Card number", "Price")


def export_csv(path) -> str:
    """The whole collection as a CSV `mtglib.parse_collection` reads back: the
    backup, and the file to hand any other app. Prices included (private)."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(EXPORT_COLUMNS)
    for c in mtglib._load_db(path):
        w.writerow([c.quantity, c.name,
                    "" if c.mana_value is None else c.mana_value,
                    " ".join(sorted(c.colors)), " ".join(sorted(c.identity)),
                    c.mana_cost, ", ".join(c.types), ", ".join(c.subtypes),
                    ", ".join(c.supertypes), c.rarity, c.scryfall_id, c.set_code,
                    c.collector_number, "" if c.price is None else c.price])
    return out.getvalue()


def snapshot_counts(path, additions_path=None):
    """Names and counts for the committed name-only list, in database mode: the
    holdings MINUS what the additions file still adds on top, because a fresh clone
    loads that list and then merges the additions file again. Floor blocks add
    nothing on load, so they subtract nothing here."""
    counts = {c.name: c.quantity for c in mtglib._load_db(path)}
    keys = {mtglib.card_key(n): n for n in counts}
    if additions_path and os.path.exists(additions_path):
        with open(additions_path, encoding="utf-8") as f:
            for b in mtglib.addition_blocks(f.read()):
                if b["floor"]:
                    continue
                for q, n in b["rows"]:
                    k = mtglib.card_key(n)
                    if k in keys:
                        counts[keys[k]] = max(0, counts[keys[k]] - q)
    return sorted((n, q) for n, q in counts.items() if q > 0)


# --------------------------------------------------------------------------- #
# Decks and pins (Phase 1b, 2026-10-14). The database keeps every deck file and
# pins.csv with EVERY revision; the deck folder is the working copy the engines
# read (they all take a deck path), rebuilt from the database whenever it is gone.
#   capture: disk -> database. After every app write and every sync, so an app
#            edit and a session's committed edit both become a revision.
#   restore: database -> disk. Only where the working copy is missing (a new host,
#            or once the repo stops carrying data), or one file on request.
# Keys are "decks/<file>" and "pins.csv", relative, so tmp dirs work the same.
# --------------------------------------------------------------------------- #
DECK_SUFFIXES = (".txt", ".notes.md", ".attrs.csv", ".buylist.csv", ".changes.csv",
                 ".clips.json", ".verdicts.json", ".engine.json")


def _sha(text):
    import hashlib
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _disk_files(decks_dir, pins_path):
    """{key: absolute path} for every file the database keeps. Flat deck folder
    only; anything that isn't a deck file or a companion is not data we own."""
    out = {}
    if decks_dir and os.path.isdir(decks_dir):
        for f in sorted(os.listdir(decks_dir)):
            p = os.path.join(decks_dir, f)
            if os.path.isfile(p) and f.endswith(DECK_SUFFIXES) and not f.startswith("."):
                out[f"decks/{f}"] = p
    if pins_path and os.path.isfile(pins_path):
        out["pins.csv"] = pins_path
    return out


def _abs(key, decks_dir, pins_path):
    if key == "pins.csv":
        return pins_path
    return os.path.join(decks_dir, key.split("/", 1)[1])


def capture(path, decks_dir, pins_path=None, *, action="capture", by=""):
    """Record every deck file (and pins.csv) whose content differs from the
    database as a new revision; a file that vanished is marked removed (its history
    stays, and `restore` can bring it back). -> {added, changed, removed}."""
    disk = _disk_files(decks_dir, pins_path)
    out = {"added": 0, "changed": 0, "removed": 0}
    at = _now()
    con = connect(path)
    try:
        with con:
            known = {r[0]: (r[1], r[2]) for r in
                     con.execute("SELECT path, sha, live FROM files")}
            for key, p in disk.items():
                try:
                    with open(p, encoding="utf-8") as f:
                        text = f.read()
                except (OSError, UnicodeDecodeError):
                    continue
                sha = _sha(text)
                old = known.get(key)
                if old and old[0] == sha and old[1]:
                    continue
                con.execute("INSERT OR REPLACE INTO files(path, text, sha, live, updated) "
                            "VALUES(?,?,?,1,?)", (key, text, sha, at))
                con.execute("INSERT INTO file_revisions(path, sha, text, at, action, by) "
                            "VALUES(?,?,?,?,?,?)", (key, sha, text, at, action, by))
                out["changed" if old and old[1] else "added"] += 1
            for key, (sha, live) in known.items():
                if live and key not in disk and (
                        key == "pins.csv" and pins_path or key.startswith("decks/") and decks_dir):
                    con.execute("UPDATE files SET live=0, updated=? WHERE path=?", (at, key))
                    con.execute("INSERT INTO file_revisions(path, sha, text, at, action, by) "
                                "VALUES(?,?,NULL,?,?,?)", (key, "", at, f"{action}: removed", by))
                    out["removed"] += 1
    finally:
        con.close()
    return out


def stored_files(path, live_only=True):
    """{key: text} of what the database holds."""
    if not os.path.exists(path):
        return {}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        q = "SELECT path, text FROM files" + (" WHERE live=1" if live_only else "")
        return dict(con.execute(q).fetchall())
    except sqlite3.Error:
        return {}
    finally:
        con.close()


def file_history(path, key):
    """Every revision of one file, oldest first: [{id, at, action, by, removed}]."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = con.execute("SELECT id, at, action, by, text IS NULL FROM file_revisions "
                               "WHERE path=? ORDER BY id", (key,)).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    return [dict(zip(("id", "at", "action", "by", "removed"), r)) for r in rows]


def file_revisions(path, key, limit=30):
    """The newest `limit` revisions of one file WITH their text, newest first:
    [{id, at, action, by, sha, text}]. `text` is None for a revision that records
    the file's removal. Feeds the Changes page's "Restore this version"."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = con.execute("SELECT id, at, action, by, sha, text FROM file_revisions "
                               "WHERE path=? ORDER BY id DESC LIMIT ?",
                               (key, int(limit))).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    return [dict(zip(("id", "at", "action", "by", "sha", "text"), r)) for r in rows]


def deck_working_copy_missing(decks_dir):
    """No deck list on disk at all: a new host, or a clone without data."""
    return not (os.path.isdir(decks_dir) and
                any(f.endswith(".txt") for f in os.listdir(decks_dir)))


def restore(path, decks_dir, pins_path=None, *, key=None, rev=None, by="restore"):
    """Write files back from the database. With no `key`: every LIVE file that is
    missing on disk (never overwrites one that exists). With `key` (and optionally
    `rev`, a revision id): that one file, overwriting, and the write is recorded as
    a new revision so the history shows the restore. -> [keys written]."""
    con = connect(path)
    written = []
    try:
        with con:
            if key:
                if rev:
                    row = con.execute("SELECT text FROM file_revisions WHERE path=? AND id=?",
                                      (key, int(rev))).fetchone()
                else:
                    row = con.execute("SELECT text FROM files WHERE path=?", (key,)).fetchone()
                if not row or row[0] is None:
                    return []
                rows = [(key, row[0])]
            else:
                rows = con.execute("SELECT path, text FROM files WHERE live=1").fetchall()
            for k, text in rows:
                if k == "pins.csv" and not pins_path or k.startswith("decks/") and not decks_dir:
                    continue
                dest = _abs(k, decks_dir, pins_path)
                if not key and os.path.exists(dest):
                    continue
                os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
                tmp = dest + ".restore.tmp"
                with open(tmp, "w", encoding="utf-8", newline="") as f:
                    f.write(text)
                os.replace(tmp, dest)
                written.append(k)
                if key:
                    sha = _sha(text)
                    con.execute("INSERT OR REPLACE INTO files(path, text, sha, live, updated) "
                                "VALUES(?,?,?,1,?)", (k, text, sha, _now()))
                    con.execute("INSERT INTO file_revisions(path, sha, text, at, action, by) "
                                "VALUES(?,?,?,?,?,?)",
                                (k, sha, text, _now(), f"restore{f' rev {rev}' if rev else ''}", by))
    finally:
        con.close()
    return written


def decks_zip(path) -> bytes:
    """Every live deck file and pins.csv from the database, as one zip: the deck
    backup beside the collection CSV."""
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for k, text in sorted(stored_files(path).items()):
            z.writestr(k, text)
    return buf.getvalue()


def decks_summary(path):
    files = stored_files(path)
    decks = sum(1 for k in files if k.startswith("decks/") and k.endswith(".txt"))
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            revs = con.execute("SELECT COUNT(*) FROM file_revisions").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error:
        revs = 0
    return {"decks": decks, "files": len(files), "revisions": revs,
            "pins": "pins.csv" in files}


# --------------------------------------------------------------------------- #
# Members and the activity log (Phase 1b, 2026-10-14).
#
# MEMBERS: the store webapp/users.py used to keep in data/private/users.json, as
# the same dict ({"owner", "members", "members_can_upload"}), so users.py swaps
# its file for these two calls and nothing above it changes. The first read on a
# database with no member store imports users.json ONCE and renames it
# `users.json.moved-to-db`: nothing can then read a stale copy (a member removed
# here can never sign in through an old file), and the renamed file stays as the
# backup. A database that has never had a member store reads as None, which is
# single-password mode, exactly as a missing users.json always was.
#
# ACTIVITY: the deck-level log the app wrote to data/activity.csv. Rows an app
# still running on files appended there (the seconds between a deploy's pull and
# its reload) are taken in by `import_activity` with a cursor, so each is taken
# exactly once and the file itself is never rewritten.
# --------------------------------------------------------------------------- #
ACTIVITY_FIELDS = ("When", "By", "Action", "Deck", "Detail")
MOVED_SUFFIX = ".moved-to-db"


def _meta_get(con, key):
    r = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r[0] if r else None


def _meta_set(con, key, value):
    con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (key, value))


def _private(path):
    """Owner read/write only: password hashes live in this file now, and
    users.json was 0600 for the same reason. SQLite gives its journal the mode of
    the database, so doing this BEFORE a write covers both."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _people_write(con, data):
    con.execute("DELETE FROM members")
    for k, m in sorted((data.get("members") or {}).items()):
        con.execute("INSERT INTO members(key, display, role, hash, ver, disabled) "
                    "VALUES(?,?,?,?,?,?)",
                    (k, m.get("display") or k, m.get("role") or "member",
                     m.get("hash") or "", int(m.get("ver", 1)),
                     1 if m.get("disabled") else 0))
    _meta_set(con, "people", json.dumps(
        {"owner": data.get("owner") or {},
         "members_can_upload": bool(data.get("members_can_upload"))}, sort_keys=True))


def _people_import(con, path, src):
    """Take users.json in, once. -> True when THIS call imported it."""
    try:
        with open(src, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False                 # unreadable: left where it is, nothing guessed
    if not isinstance(data, dict):
        return False
    _private(path)                   # before any hash is written, journal included
    con.execute("BEGIN IMMEDIATE")
    try:
        mine = _meta_get(con, "people") is None   # another worker may have won the race
        if mine:
            _people_write(con, data)
            _meta_set(con, "people_imported", json.dumps(
                {"from": os.path.basename(src), "at": _now(),
                 "members": len(data.get("members") or {})}, sort_keys=True))
        con.commit()
    except BaseException:
        con.rollback()
        raise
    if mine:
        try:
            os.replace(src, src + MOVED_SUFFIX)
        except OSError:
            pass                     # the database wins either way: it has a store now
    return mine


def people_load(path, import_from=None):
    """The member store, or None when there is none (single-password mode).
    `import_from` is users.json: taken in once, the first time the database has no
    store of its own. Database errors propagate on purpose: a sign-in check must
    fail closed, never read a broken database as "no members"."""
    if not (path and os.path.exists(path)):
        return None
    con = connect(path)
    try:
        raw = _meta_get(con, "people")
        if raw is None and import_from and os.path.exists(import_from):
            _people_import(con, path, import_from)
            raw = _meta_get(con, "people")
        if raw is None:
            return None
        people = json.loads(raw)
        members = {k: {"name": k, "display": d, "role": r, "hash": h, "ver": int(v),
                       "disabled": bool(x)}
                   for k, d, r, h, v, x in con.execute(
                       "SELECT key, display, role, hash, ver, disabled FROM members")}
    finally:
        con.close()
    return {"owner": people.get("owner") or {}, "members": members,
            "members_can_upload": bool(people.get("members_can_upload"))}


def people_save(path, data):
    """Replace the member store with `data` (users.py's dict), in one transaction."""
    _private(path)                   # before any hash is written, journal included
    con = connect(path)
    try:
        with con:
            _people_write(con, data)
    finally:
        con.close()


def log_activity(path, rows):
    """Append deck-level actions: rows = [(when, by, action, deck, detail)]."""
    rows = [tuple("" if v is None else str(v) for v in r) for r in rows]
    con = connect(path)
    try:
        with con:
            con.executemany("INSERT INTO activity(at, by, action, deck, detail) "
                            "VALUES(?,?,?,?,?)", rows)
    finally:
        con.close()
    return len(rows)


def activity_rows(path, limit=100):
    """The newest actions first, keyed like the old CSV (When, By, Action, Deck,
    Detail) so the page reads them unchanged."""
    if not os.path.exists(path):
        return []
    con = connect(path)
    try:
        rows = con.execute("SELECT at, by, action, deck, detail FROM activity "
                           "ORDER BY at DESC, id DESC LIMIT ?", (int(limit),)).fetchall()
    finally:
        con.close()
    return [dict(zip(ACTIVITY_FIELDS, r)) for r in rows]


def activity_csv(path) -> str:
    """The whole log, oldest first, in the old file's columns."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(ACTIVITY_FIELDS)
    if os.path.exists(path):
        con = connect(path)
        try:
            w.writerows(con.execute("SELECT at, by, action, deck, detail FROM activity "
                                    "ORDER BY at, id"))
        finally:
            con.close()
    return buf.getvalue()


def import_activity(path, csv_path):
    """Take in the rows of data/activity.csv the database hasn't seen. A cursor in
    meta counts the file's rows already taken, so a re-run takes nothing twice; a
    file that shrank (rewritten by hand) moves the cursor without guessing which
    rows are new. -> rows imported."""
    if not (csv_path and os.path.exists(csv_path)):
        return 0
    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    con = connect(path)
    try:
        con.execute("BEGIN IMMEDIATE")
        try:
            done = int(_meta_get(con, "activity_csv_rows") or 0)
            new = rows[done:] if len(rows) >= done else []
            con.executemany("INSERT INTO activity(at, by, action, deck, detail) "
                            "VALUES(?,?,?,?,?)",
                            [tuple((r.get(k) or "") for k in ACTIVITY_FIELDS) for r in new])
            _meta_set(con, "activity_csv_rows", str(len(rows)))
            con.commit()
        except BaseException:
            con.rollback()
            raise
    finally:
        con.close()
    return len(new)


def people_summary(path):
    """Counts only — never a name's hash: {members, activity}."""
    if not os.path.exists(path):
        return {"members": 0, "activity": 0}
    con = connect(path)
    try:
        return {"members": con.execute("SELECT COUNT(*) FROM members").fetchone()[0],
                "activity": con.execute("SELECT COUNT(*) FROM activity").fetchone()[0]}
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Backups (docs/spec-target-architecture.md §4 and §11). Once this file is the
# only record of the collection, the accounts and the log, it needs copies:
#   * DAILY, on the server: the sync takes one before it changes anything, so a
#     bad batch or capture can be undone by putting yesterday's file back, and
#     keeps the newest few (the free tier's disk is small);
#   * ON REQUEST, for the player: the same copy with the `members` table emptied
#     and the file rebuilt, so a password hash never leaves the server — not even
#     an old one an update left behind in a free page.
# Both use SQLite's online backup, which is consistent while the app writes.
# --------------------------------------------------------------------------- #
BACKUP_PREFIX = "collection-"


def backup(path, dest, *, without_hashes=False):
    """Copy the database to `dest` (owner-only). -> dest."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    tmp = dest + ".tmp"
    with open(tmp, "wb"):
        pass                         # created first, so it is 0600 before any byte lands
    _private(tmp)
    src = sqlite3.connect(path, timeout=10)
    try:
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
            if without_hashes:
                dst.execute("PRAGMA secure_delete=ON")   # zero what DELETE frees …
                if dst.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                               "AND name='members'").fetchone():
                    dst.execute("DELETE FROM members")
                    dst.commit()
                dst.execute("VACUUM")   # … and rebuild, dropping pages freed long ago
        finally:
            dst.close()
    finally:
        src.close()
    os.replace(tmp, dest)
    return dest


def daily_backup(path, backups_dir, *, keep=7, today=None):
    """Today's copy, once a day, then only the newest `keep` remain.
    -> the file written, or None when today's copy already exists."""
    today = today or datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    os.makedirs(backups_dir, exist_ok=True)
    try:
        os.chmod(backups_dir, 0o700)
    except OSError:
        pass
    dest = os.path.join(backups_dir, f"{BACKUP_PREFIX}{today}.db")
    if os.path.exists(dest):
        return None
    backup(path, dest)
    for old in list_backups(backups_dir)[max(1, int(keep)):]:
        try:
            os.remove(os.path.join(backups_dir, old["name"]))
        except OSError:
            pass
    return dest


def list_backups(backups_dir):
    """The daily copies, newest first: [{name, date, bytes}]."""
    out = []
    for p in glob.glob(os.path.join(backups_dir or "", f"{BACKUP_PREFIX}*.db")):
        name = os.path.basename(p)
        out.append({"name": name, "date": name[len(BACKUP_PREFIX):-3],
                    "bytes": os.path.getsize(p)})
    return sorted(out, key=lambda b: b["date"], reverse=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed", help="one-time union of every collection record")
    s.add_argument("--db", default=DEFAULT_DB)
    s.add_argument("--export")
    s.add_argument("--august")
    s.add_argument("--additions")
    s.add_argument("--decks-dir")
    s.add_argument("--write", action="store_true", help="create the database (else dry run)")
    i = sub.add_parser("ingest", help="apply new owned_additions.txt blocks")
    i.add_argument("--db", default=DEFAULT_DB)
    i.add_argument("--additions", required=True)
    t = sub.add_parser("stats", help="cards and copies in the database")
    t.add_argument("--db", default=DEFAULT_DB)
    c = sub.add_parser("capture", help="record deck files and pins.csv as revisions")
    c.add_argument("--db", default=DEFAULT_DB)
    c.add_argument("--decks-dir", required=True)
    c.add_argument("--pins")
    r = sub.add_parser("restore", help="write deck files back from the database")
    r.add_argument("--db", default=DEFAULT_DB)
    r.add_argument("--decks-dir", required=True)
    r.add_argument("--pins")
    r.add_argument("--file", help="one file, e.g. decks/beorn-the-fierce.txt or pins.csv")
    r.add_argument("--rev", type=int, help="a revision id from `history`")
    h = sub.add_parser("history", help="revisions of one deck file")
    h.add_argument("--db", default=DEFAULT_DB)
    h.add_argument("file")
    v = sub.add_parser("activity", help="the newest deck-level actions, newest first")
    v.add_argument("--db", default=DEFAULT_DB)
    v.add_argument("--limit", type=int, default=20)
    b = sub.add_parser("backup", help="a consistent, owner-only copy of the database")
    b.add_argument("--db", default=DEFAULT_DB)
    b.add_argument("--to", required=True, help="the copy to write")
    b.add_argument("--without-hashes", action="store_true",
                   help="empty the members table in the copy (what the app hands out)")
    a = ap.parse_args(argv)
    if a.cmd == "seed":
        print(seed(a.db, a.export, a.august, a.additions, a.decks_dir, write=a.write))
    elif a.cmd == "ingest":
        nb, nc = ingest(a.db, a.additions)
        print(f"ingested {nb} new block(s), {nc} cop(ies)")
    elif a.cmd == "capture":
        print(capture(a.db, a.decks_dir, a.pins, action="cli", by="cli"))
    elif a.cmd == "restore":
        print(restore(a.db, a.decks_dir, a.pins, key=a.file, rev=a.rev, by="cli"))
    elif a.cmd == "history":
        for r in file_history(a.db, a.file):
            print(f"{r['id']:>5}  {r['at']}  {r['action']}{'  (removed)' if r['removed'] else ''}"
                  f"{'  · ' + r['by'] if r['by'] else ''}")
    elif a.cmd == "backup":
        print(backup(a.db, a.to, without_hashes=a.without_hashes))
    elif a.cmd == "activity":
        for r in activity_rows(a.db, limit=a.limit):
            print(f"{r['When']}  {r['By'] or '-'}  {r['Action']}"
                  f"{'  · ' + r['Deck'] if r['Deck'] else ''}"
                  f"{'  · ' + r['Detail'] if r['Detail'] else ''}")
    else:
        cards = mtglib._load_db(a.db) if os.path.exists(a.db) else []
        print(f"{len(cards)} cards, {sum(c.quantity for c in cards)} copies")
        print(decks_summary(a.db))
        print(people_summary(a.db))
    return 0


if __name__ == "__main__":
    sys.exit(main())
