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

CLI:
    python3 scripts/store.py seed   --db D [--export CSV] [--august TXT]
                                    [--additions TXT] [--decks-dir DIR] [--write]
    python3 scripts/store.py ingest --db D --additions TXT
    python3 scripts/store.py stats  --db D
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
    a = ap.parse_args(argv)
    if a.cmd == "seed":
        print(seed(a.db, a.export, a.august, a.additions, a.decks_dir, write=a.write))
    elif a.cmd == "ingest":
        nb, nc = ingest(a.db, a.additions)
        print(f"ingested {nb} new block(s), {nc} cop(ies)")
    else:
        cards = mtglib._load_db(a.db) if os.path.exists(a.db) else []
        print(f"{len(cards)} cards, {sum(c.quantity for c in cards)} copies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
