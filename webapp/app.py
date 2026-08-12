#!/usr/bin/env python3
"""MTG Commander Deckbuilder — local web front end.

Wraps the stdlib analysis scripts (mtglib, deck_stats, power, deck_conflicts,
wishlist, build_dashboard) in a small Flask app. Runs on localhost so your
collection + prices stay on your machine.

Run:
  pip install -r webapp/requirements.txt      # (use a venv)
  python3 webapp/app.py                        # -> http://127.0.0.1:5000
Config via env: MTG_COLLECTION, MTG_DECKS_DIR, MTG_PORT.
"""
import hashlib
import hmac
import os
import re
import socket
import subprocess
import sys
import time
from datetime import timedelta

from flask import (Flask, Response, abort, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import mtglib
import deck_stats
import power
import deck_conflicts
import wishlist as wl
import build_dashboard as bd
import analyze_collection as ac
import similar_commanders as simc
import commander_finder as cf
import export_manapool as ex
import card_api
import auto_build
import manabase
import combo_detector
import deckcore
import edhrec
import spellbook
import optimize
import goldfish

import sync


def _txt(text, filename):
    return Response(text + "\n", mimetype="text/plain",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})

def _default_collection():
    """Prefer the player's private CSV; fall back to the committed name-only
    snapshot so a fresh clone (which has no collection.csv — it's gitignored)
    still works out of the box."""
    csv_path = os.path.join(ROOT, "data/collection/collection.csv")
    snap = os.path.join(ROOT, "data/collection/collection_snapshot.txt")
    env = os.environ.get("MTG_COLLECTION")
    if env:
        return env
    return csv_path if os.path.exists(csv_path) else snap


COLLECTION = _default_collection()
# Uploads ALWAYS write here — the private, gitignored CSV — never the tracked
# name-only snapshot, so a priced export can't leak into a public repo.
COLLECTION_CSV = os.path.join(ROOT, "data/collection/collection.csv")
COLLECTION_ATTRS = os.path.join(ROOT, "data/collection/collection_attrs.csv")
DECKS_DIR = os.environ.get("MTG_DECKS_DIR", os.path.join(ROOT, "data/decks"))
ADDITIONS = os.path.join(ROOT, "data/collection/owned_additions.txt")

app = Flask(__name__)

# ---- access gate -----------------------------------------------------------
# A hosted copy is reachable by anyone who finds the URL, so the app supports a
# single shared password: set MTG_PASSWORD in the server's environment (on
# PythonAnywhere: an os.environ line in the WSGI file) and every route demands a
# login. Unset — local dev, tests, CI — the gate does not exist and nothing
# below changes behavior. The secret key derives from the password so sessions
# survive app reloads; a random key when no password is set (sessions unused).
PASSWORD = os.environ.get("MTG_PASSWORD") or None
app.secret_key = hashlib.sha256(f"mtg-auth-v1:{PASSWORD}".encode()).digest() \
    if PASSWORD else os.urandom(32)
app.permanent_session_lifetime = timedelta(days=90)  # the PWA stays signed in


def _cookie_secure():
    """Secure-only session cookie whenever the deploy is known to be HTTPS
    (PythonAnywhere always is) or explicitly declared so. Not unconditional:
    a Secure cookie over plain-http LAN dev would silently never be sent and
    every login would 'not stick'."""
    return bool(PASSWORD and (os.environ.get("PYTHONANYWHERE_SITE")
                              or os.environ.get("PYTHONANYWHERE_DOMAIN")
                              or os.environ.get("MTG_COOKIE_SECURE") == "1"))


app.config["SESSION_COOKIE_HTTPONLY"] = True          # no script access to the cookie
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"         # cross-site POSTs carry no session → CSRF brake
app.config["SESSION_COOKIE_SECURE"] = _cookie_secure()
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024   # uploads are ~1–2 MB CSVs; cap the rest


@app.after_request
def _security_headers(resp):
    """Baseline headers on every response. No CSP — the dashboards and app pages
    deliberately use inline scripts/styles (self-contained-file requirement), so a
    useful CSP would be 'unsafe-inline' theater; these three are free wins."""
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp

# Endpoints that must work logged-out: the login page itself, and the shell
# assets the login page + installed PWA need before a session exists.
_PUBLIC_ENDPOINTS = {"login", "static", "service_worker", "shared_tokens"}


def _safe_next(target):
    """Only ever redirect within the app — an absolute URL here would be an
    open-redirect hole on a public host. Backslashes are normalized first:
    browsers treat '/\\evil.example' as '//evil.example' (protocol-relative)."""
    t = (target or "").replace("\\", "/")
    return target if t and t.startswith("/") and not t.startswith("//") \
        else url_for("index")


@app.before_request
def _require_login():
    if not PASSWORD or session.get("authed") \
            or request.endpoint in _PUBLIC_ENDPOINTS:
        return None
    if request.method == "GET":
        return redirect(url_for("login", next=request.full_path.rstrip("?")))
    abort(401)  # unauthenticated POSTs get a hard no, not a redirect-to-form


@app.route("/login", methods=["GET", "POST"])
def login():
    if not PASSWORD or session.get("authed"):
        return redirect(_safe_next(request.args.get("next")))
    error = None
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), PASSWORD):
            session.permanent = True
            session["authed"] = True
            return redirect(_safe_next(request.form.get("next")))
        time.sleep(0.6)  # blunt but effective brake on password guessing
        error = "Wrong password."
    return render_template("login.html", error=error,
                           next=request.values.get("next", "/"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.context_processor
def _auth_flags():
    return {"auth_enabled": bool(PASSWORD)}


@app.before_request
def _auto_sync():
    """Poor-man's cron: on the hosted server (where Scheduled Tasks are paid-only)
    the first request of the day syncs deck edits up and code/snapshots down in a
    background thread. Off everywhere else — sync.enabled() decides. Never allowed
    to take a page down."""
    try:
        sync.maybe_start()
    except Exception:
        pass


@app.errorhandler(500)
def _err(e):  # friendly message instead of a bare stack trace
    return ("<h2>Something went wrong</h2><p>Most often this means the collection "
            "file wasn't found. The app uses <code>data/collection/collection.csv</code> "
            "if present, otherwise the committed snapshot. Add your Archidekt export at "
            "that path (see docs/SETUP-windows.md) and reload.</p>"), 500


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _hdr(text, key, default=""):
    m = re.search(rf"^#\s*{key}\s*:\s*(.+?)\s*$", text, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else default


def deck_meta(stem):
    path = os.path.join(DECKS_DIR, f"{stem}.txt")
    if not os.path.exists(path):
        return None
    text = open(path, encoding="utf-8").read()
    return {
        "stem": stem, "path": path,
        "title": _hdr(text, "Title") or _hdr(text, "Commander") or stem,
        "commander": re.split(r"\s{2,}|\(", _hdr(text, "Commander"))[0].strip(),
        "theme": _hdr(text, "Theme", "default"),
    }


def list_decks():
    stems = sorted(os.path.splitext(os.path.basename(p))[0]
                   for p in _glob_txt(DECKS_DIR))
    return [deck_meta(s) for s in stems]


def _glob_txt(d):
    import glob
    return glob.glob(os.path.join(d, "*.txt"))


def collection_index():
    coll = mtglib.load_collection(COLLECTION)
    return coll, mtglib.index_by_name(coll)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    """Deck leaderboard. Each row carries a small health summary so the page answers
    'which deck needs attention?', not just 'which is strongest'."""
    coll, idx = collection_index()
    # one scan for every deck, rather than one per row
    try:
        usage = deck_conflicts.scan(DECKS_DIR, idx)
    except Exception:
        usage = {}
    short_by_deck = {}
    for name, v in usage.items():
        if v["total"] > v["owned"]:
            for d in v["decks"]:
                short_by_deck[d] = short_by_deck.get(d, 0) + 1

    rows = []
    for m in list_decks():
        try:
            res = power.build_for_deck(m["path"], idx)
        except Exception:
            res = None
        try:
            deck = mtglib.parse_deck(open(m["path"], encoding="utf-8").read())
            total = sum(c.quantity for c in deck)
            to_buy = sum(1 for c in deck if mtglib.lookup(idx, c.name) is None)
        except Exception:
            total, to_buy = None, 0
        label = deck_conflicts.deck_label(m["path"])
        rows.append({**m, "assess": res, "total": total, "to_buy": to_buy,
                     "contested": short_by_deck.get(label, 0)})
    rows.sort(key=lambda r: -(r["assess"]["power"] if r["assess"] else 0))
    brackets = sorted({r["assess"]["bracket"] for r in rows if r["assess"]})
    try:
        # "I just scanned these — where do they go?" Only fires when the collection
        # export carries acquisition dates; empty on the name-only snapshot.
        arrivals = deckcore.new_arrivals(coll, DECKS_DIR)
    except Exception:
        arrivals = []
    return render_template("index.html", decks=rows, brackets=brackets, page="home",
                           arrivals=arrivals,
                           sync_enabled=sync.enabled(), sync_status=sync.status_view())


@app.route("/deck/<stem>")
def deck(stem):
    m = deck_meta(stem)
    if not m:
        abort(404)
    res = bd.generate(m["path"], COLLECTION, title=m["title"],
                      commander=m["commander"], theme=m["theme"], decks_dir=DECKS_DIR,
                      editable=True)
    html = res["dashboard"]
    # Surface the singleton guard on the primary surface. optimize() computes this
    # after every applying run, but the POST routes discard the report — so a
    # violation from ANY source was invisible in the app (CLAUDE.md: this class of
    # bug was silent for four commits; the check exists to be SEEN).
    try:
        bad = optimize.singleton_violations(m["path"])
    except Exception:
        bad = []
    if bad:
        from markupsafe import escape
        msg = " · ".join(f"{q}× {escape(n)}" for q, n in bad)
        banner = ('<div style="background:#7f1d1d;color:#fff;padding:8px 16px;'
                  'font:600 14px system-ui">⚠ ILLEGAL — Commander allows one copy: '
                  f'{msg}</div>')
        html = re.sub(r"(<body[^>]*>)", r"\1" + banner.replace("\\", "\\\\"),
                      html, count=1)
    return html


@app.route("/deck/<stem>/visual")
def deck_visual(stem):
    m = deck_meta(stem)
    if not m:
        abort(404)
    res = bd.generate(m["path"], COLLECTION, title=m["title"], commander=m["commander"],
                      theme=m["theme"], decks_dir=DECKS_DIR, size="small", want_visual=True)
    return res["visual"]


@app.route("/deck/<stem>/edit", methods=["GET", "POST"])
def deck_edit(stem):
    m = deck_meta(stem)
    if not m:
        abort(404)
    if request.method == "POST":
        text = request.form.get("content", "")
        with open(m["path"], "w", encoding="utf-8", newline="\n") as f:
            f.write(text.replace("\r\n", "\n"))
        return redirect(url_for("deck", stem=stem))
    content = open(m["path"], encoding="utf-8").read()
    return render_template("edit.html", meta=m, content=content, page="decks")


# The one section-header parser lives in the deckcore hub; the picker's labels and the
# insert's matching MUST come from the same function or adds silently mis-file.
_section_label = deckcore.section_label


def _insert_deck_card(path, lines, name, section=None):
    """Insert `1 <name>` as the LAST card of `section`, leaving every other byte of the
    file untouched — same contract as remove/replace (quantities, comments, and section
    headers all survive). Falls back to after the final card line if the section isn't
    found, so a stale section name can never drop the card on the floor."""
    want = (section or "").strip().lower()
    start = None
    if want:
        for i, ln in enumerate(lines):
            label = _section_label(ln)
            if label and label.lower() == want:
                start = i
                break
    if start is None:
        last = [i for i, l in enumerate(lines) if l.strip() and not l.strip().startswith("#")]
        at = (last[-1] + 1) if last else len(lines)
    else:
        at = start + 1
        for j in range(start + 1, len(lines)):
            s = lines[j].strip()
            if _section_label(lines[j]):
                break
            if s and not s.startswith("#"):
                at = j + 1
    lines.insert(at, f"1 {name}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    return True


def _edit_deck_card(path, action, name, replacement=None, section=None):
    """Line-based edit of a deck .txt: remove, replace, or add a single card, preserving
    quantity, section, and everything else. Returns True if a line changed."""
    key = mtglib._norm(name)
    lines = open(path, encoding="utf-8").read().split("\n")
    if action == "add":
        return _insert_deck_card(path, lines, name, section)
    out, changed = [], False
    for ln in lines:
        s = ln.strip()
        if not changed and s and not s.startswith("#"):
            m = mtglib._QTY_RE.match(s)   # shared parser — '1x Name' must not no-op
            cardname = m.group(2) if m else s
            qty = m.group(1) if m else "1"
            if mtglib._norm(cardname) == key:
                if action == "remove":
                    changed = True
                    continue
                if action == "replace" and replacement:
                    out.append(f"{qty} {replacement}")
                    changed = True
                    continue
        out.append(ln)
    if changed:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(out))
    return changed


def _log_manual_change(deck_path, card, replaced="", source="manual-add"):
    """Append a player edit to `<deck>.changes.csv` — same schema the optimizer writes.

    Two things fall out of this one row: the dashboard's existing NEW badge lights up,
    and `Source` marks the card as the PLAYER's decision, which is what lets the advisor
    offer an opinion on it without the optimizer ever touching it."""
    import csv as _csv
    from datetime import date
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    path = f"{stem}.changes.csv"
    exists = os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = _csv.writer(f)
        if not exists:
            w.writerow(["Card", "Added", "Replaced", "Source"])
        w.writerow([card, date.today().isoformat(), replaced, source])


def _deck_identity(text):
    """Color identity from the deck's own `# Colors:` header, as a WUBRG set."""
    return set(re.findall(r"[WUBRG]", (_hdr(text, "Colors") or "").upper()))


def _validate_add(meta, stem, name, idx=None):
    """Ordered checks for adding a card. Returns (card, error, warning).

    Ownership and color legality are hard stops — an off-identity card makes the deck
    illegal, which isn't a matter of taste. A pin held by another deck is only a
    warning: the player's word beats their own earlier reservation, but they should
    know they're spending a copy that was spoken for.

    `idx` lets the route share one collection load across validate + advise instead
    of parsing the CSV once per step.
    """
    if idx is None:
        _, idx = collection_index()
    card = mtglib.lookup(idx, name)
    if card is None:
        return None, (f"You don't own a card called “{name}”. Add it to the "
                      "collection first (or check the spelling)."), None
    text = open(meta["path"], encoding="utf-8").read()
    key = mtglib._norm(card.name)
    # Compare on BOTH the full name and the split-card front face. A deck line often
    # carries only the front face ('Fire') while the collection stores 'Fire // Ice';
    # matching raw names alone let the same card in twice — the known " // " trap, so
    # every membership test goes through front_face + _norm, never a naive compare.
    in_deck = set()
    for c in mtglib.parse_deck(text):
        in_deck |= mtglib.name_keys(c.name)
    if mtglib.name_keys(card.name) & in_deck and not mtglib.is_basic(card.name):
        return None, f"{card.name} is already in this deck — Commander is singleton.", None
    ident = _deck_identity(text)
    # Only enforce when we actually have identity data; a name-only collection
    # (fresh clone on the snapshot) must not produce false rejections.
    if card.identity and ident and not card.identity <= ident:
        bad = "".join(sorted(card.identity - ident))
        return None, (f"{card.name} is outside this deck's color identity "
                      f"(needs {bad}). It would make the deck illegal."), None
    warn = None
    try:
        owner = deckcore.load_pins().get(key)
        if owner and owner != stem:
            warn = (f"Heads up: your copy of {card.name} is pinned to “{owner}”. "
                    "Adding it here spends a copy that deck is counting on.")
    except Exception:
        pass
    return card, None, warn


@app.route("/deck/<stem>/card", methods=["POST"])
def deck_card(stem):
    """Remove a card from a deck, or replace it with another — in place, from the panel."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    action = request.form.get("action", "")
    name = request.form.get("name", "").strip()
    replacement = request.form.get("replacement", "").strip() or None
    if action == "replace" and replacement:
        # The same front-face-aware singleton guard the Add path enforces — minus the
        # card being replaced (swapping A for A's other face is still one copy), and
        # minus an ownership block: deck files legitimately hold unowned BUY cards.
        text = open(m["path"], encoding="utf-8").read()
        others = set()
        for c in mtglib.parse_deck(text):
            if not (mtglib.name_keys(c.name) & mtglib.name_keys(name)):
                others |= mtglib.name_keys(c.name)
        if mtglib.name_keys(replacement) & others and not mtglib.is_basic(replacement):
            return redirect(url_for("deck", stem=stem))   # would duplicate — refuse
    if action in ("remove", "replace") and name:
        if _edit_deck_card(m["path"], action, name, replacement):
            if action == "replace" and replacement:
                _log_manual_change(m["path"], replacement, replaced=name,
                                   source="manual-replace")
    return redirect(url_for("deck", stem=stem))


@app.route("/deck/<stem>/add", methods=["POST"])
def deck_add(stem):
    """Add an owned card to a deck and hand back an opinion on how it fits.

    JSON rather than a redirect so the picker can show the verdict at the moment it's
    actionable — and so a rejection explains itself instead of silently doing nothing."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    name = request.form.get("name", "").strip()
    section = (request.form.get("section") or "").strip() or None
    if not name:
        return jsonify({"ok": False, "error": "No card name given."}), 400
    coll, idx = collection_index()      # ONE load for validate + advise
    card, err, warn = _validate_add(m, stem, name, idx=idx)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    _edit_deck_card(m["path"], "add", card.name, section=section)
    _log_manual_change(m["path"], card.name, source="manual-add")
    illegal = []
    try:
        illegal = optimize.singleton_violations(m["path"])
    except Exception:
        pass
    verdict = None
    try:
        verdict = deckcore.advise_card(m["path"], coll, card.name,
                                       section=section, commander=m["commander"])
    except Exception:
        verdict = None
    return jsonify({"ok": True, "card": card.name, "section": section,
                    "warning": warn, "illegal": illegal, "verdict": verdict})


@app.route("/api/deck/<stem>/advise")
def api_deck_advise(stem):
    """Read-only fit opinion for any card against this deck — used by the add picker
    before committing, and by the panel for cards the player added by hand."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    name = (request.args.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    # Same degrade-contract as /deck/<stem>/add: the picker consumes JSON, so an
    # analysis failure must come back as a JSON error, never Flask's HTML 500 page.
    try:
        coll, _ = collection_index()
        v = deckcore.advise_card(m["path"], coll, name,
                                 section=(request.args.get("section") or "").strip() or None,
                                 commander=m["commander"])
    except Exception:
        return jsonify({"error": "Couldn't analyze this deck — no opinion available."}), 500
    if v is None:
        return jsonify({"error": f"{name} isn't in your collection."}), 404
    return jsonify(v)


@app.route("/api/deck/<stem>/sections")
def api_deck_sections(stem):
    """The deck file's OWN section labels, for the add picker. Never a hardcoded list —
    every deck sections itself its own way. Real headers only: load_deck_sections'
    synthetic 'Cards' group has no header line for the insert to find."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    return jsonify(deckcore.real_section_labels(m["path"]))


@app.route("/api/collection/search")
def api_collection_search():
    """Owned-card autocomplete for the 'add anything from my collection' picker. `ci`
    (e.g. WUR) sorts in-color-legal cards first (but still returns off-color ones)."""
    q = request.args.get("q", "").strip().lower()
    ci = set(request.args.get("ci", "") or "")
    if len(q) < 2:
        return jsonify([])
    coll, _ = collection_index()
    out = []
    for c in coll:
        nl = c.name.lower()
        if q in nl:
            legal = ((not c.identity) or c.identity <= ci) if ci else True
            out.append((0 if nl.startswith(q) else 1, not legal, c.name, c.quantity, legal))
    out.sort()
    return jsonify([{"name": n, "qty": qn, "legal": lg} for _p, _l, n, qn, lg in out[:20]])


@app.route("/wishlist", methods=["GET"])
def wishlist_view():
    shared, unowned, upgrades = wl.build(COLLECTION, DECKS_DIR)
    shared.sort(key=lambda c: -((c["price"] or 0) * c["short"]))
    upgrades.sort(key=lambda u: (u["deck"], -(u["price"] or 0)))
    share_cost = round(sum((c["price"] or 0) * c["short"] for c in shared), 2)
    up_cost = round(sum((u["price"] or 0) for u in upgrades), 2)
    return render_template("wishlist.html", shared=shared, unowned=unowned,
                           upgrades=upgrades, share_cost=share_cost, up_cost=up_cost,
                           page="wishlist")


@app.route("/export/wishlist.txt")
def export_wishlist():
    """The 'cards to buy' list as ManaPool-ready text (qty name per line)."""
    inc = request.args.getlist("include") or ["shared", "unowned", "upgrades"]
    text = ex.wishlist_text(COLLECTION, DECKS_DIR, include=tuple(inc))
    raw = request.args.get("raw")
    return text if raw else _txt(text, "manapool-wishlist.txt")


@app.route("/export/deck/<stem>.txt")
def export_deck(stem):
    m = deck_meta(stem)
    if not m:
        abort(404)
    text = ex.deck_text(m["path"])
    raw = request.args.get("raw")
    return text if raw else _txt(text, f"{stem}.txt")


def _assess_packet(m):
    """Paste-able text block: decklist + all computed analytics, for handing a saved
    deck to an mtg-deckbuilder COACHING session (Phase 5 bridge). All grounded numbers,
    no opinions — the coaching happens in Claude Code on the player's subscription."""
    a = deckcore.analyze_deck(m["path"], COLLECTION)
    rep, missing, idx = a["report"], a["missing"], a["idx"]
    assessment, mana, combos = a["assessment"], a["mana"], a["combos"]

    L = [f"=== ASSESSMENT PACKET — {m['title']} ===",
         f"Commander: {m['commander']}",
         "For grounding an mtg-deckbuilder coaching session (see the skill's references/coaching.md).",
         "Paste this whole block and say: \"coach this deck\".", ""]
    if assessment:
        sig = assessment["signals"]
        L.append("-- POWER & BRACKET --")
        L.append(f"Bracket {assessment['bracket']} ({assessment['bracket_name']}) · "
                 f"Power {assessment['power']}/100 ({assessment['tier']})")
        for r in assessment["bracket_reasons"]:
            L.append(f"  · {r}")
        L.append(f"  interaction {sig['interaction']} · ramp {sig['ramp']} · draw {sig['draw']} · "
                 f"lands {sig['lands']} · avg MV {sig['avg_mv']}")
        if sig.get("game_changers"):
            L.append(f"  Game Changers: {', '.join(sig['game_changers'])}")
        L.append("")
    L.append("-- ROLE COUNTS / CURVE / PIPS --")
    L.append("  " + " · ".join(f"{k} {v}" for k, v in sorted(rep.get("categories", {}).items())))
    if rep.get("curve"):
        L.append(f"  curve (MV→count): {rep['curve']}")
    if rep.get("pip_demand"):
        L.append(f"  pip demand: {rep['pip_demand']}  ·  sources: {rep.get('color_sources')}")
        # Never let the coach read a source count as precise when part of it is the
        # color-identity approximation (see deck_stats.build_report).
        approx = (rep.get("color_sources_basis") or {}).get("identity_lands", 0)
        if approx:
            L.append(f"    (note: {approx} land(s) counted by color IDENTITY, not "
                     "actual production — approximate; enrich the collection)")
    L.append("")
    if mana and mana.get("have_colors"):
        L.append("-- CONSISTENCY (hypergeometric) --")
        lo = mana.get("land_odds")
        if lo:
            L.append(f"  keepable hand {lo['keepable']*100:.0f}% · ≥3 lands opener "
                     f"{lo['ge3_open']*100:.0f}% · 4th land by T4 {lo['ge4_by_t4']*100:.0f}%")
        for c in mana["colors"]:
            L.append(f"  {c['color']}: {c['sources']} sources (Karsten ~{c['karsten_target']}) · "
                     f"P(≥1 opener) {c['p_open']*100:.0f}% · {c['status']}")
        if mana["risky"]:
            L.append("  risky to cast on curve: " +
                     ", ".join(f"{r['name']} {r['p']*100:.0f}%" for r in mana["risky"]))
        L.append("")
    elif mana is not None:
        L.append("-- CONSISTENCY -- (name-only collection: enrich for colored-source math)\n")
    # Sequenced play — the questions the closed forms above structurally cannot answer.
    # Same cached helper the dashboard calls, so a coach and a page never disagree.
    sim = goldfish.sim_for_deck(m["path"], COLLECTION)
    L.append("-- GOLDFISH SIMULATION (Monte Carlo, seeded) --")
    if sim is None:
        L.append("  unavailable — the simulation couldn't be run for this deck.\n")
    elif not sim.get("have_data"):
        L.append(f"  {sim.get('note')}\n")
    else:
        d, p = sim["definitions"], sim["p_cast_by"]
        L.append(f"  {sim['games']:,} games, seed {sim['seed']}, "
                 f"{sim['library']}-card library · model: {sim['model']} "
                 f"(enriched {sim['coverage']['exact']} · identity "
                 f"{sim['coverage']['identity']} · no data {sim['coverage']['none']})")
        L.append("  commander in play: " +
                 " · ".join(f"T{t} {v*100:.0f}%" for t, v in p.items())
                 + f"   [{d['p_cast_by']}]")
        L.append(f"  keepable opener {sim['keepable_first7']*100:.0f}% "
                 f"[{d['keepable_first7']}] · mulliganed "
                 f"{sim['mulligan_rate']*100:.0f}%")
        if sim.get("screw") is not None:
            L.append(f"  screw {sim['screw']*100:.0f}% [{d['screw']}] · "
                     f"flood {sim['flood']*100:.0f}% [{d['flood']}]")
        L.append("  lands in play: " +
                 " · ".join(f"T{t} {v}" for t, v in
                            list(sim["mean_lands_by_turn"].items())[:8]))
        worst = [c for c in sim["cards"]
                 if c["cast_rate"] < 1.0 or (c["delta"] or 0) > 0][:5]
        if worst:
            L.append(f"  worst-sequenced [{d['cards']}]:")
            for c in worst:
                when = ("never cast" if c["mean_first_cast"] is None
                        else f"first cast T{c['mean_first_cast']:g} "
                             f"({c['delta']:+g} vs MV {c['mv']:g})")
                L.append(f"    {c['name']} — cast {c['cast_rate']*100:.0f}%, {when}")
        for a in sim["assumptions"]:
            L.append(f"  assumption: {a}")
        L.append("")
    if combos and (combos.get("complete") or combos.get("near")):
        L.append("-- COMBOS (curated) --")
        for c in combos.get("complete", []):
            L.append(f"  present: {c['name']} → {c['result']}")
        for c in combos.get("near", []):
            L.append(f"  one card away: add {c['missing']} → {c['name']}")
        L.append("")
    sb = spellbook.combos_for_deck(m["path"])
    if sb.get("present") or sb.get("almost"):
        L.append("-- COMMANDER SPELLBOOK (full combo DB) --")
        for c in sb.get("present", [])[:25]:
            L.append(f"  present: {' + '.join(c['cards'])} → {', '.join(c['produces']) or '?'}")
        for c in [x for x in sb.get("almost", []) if len(x.get("missing", [])) == 1][:25]:
            L.append(f"  one card away: add {c['missing'][0]} → "
                     f"{' + '.join(c['cards'])} ⇒ {', '.join(c['produces']) or '?'}")
        L.append("")
    # ONE merged buy view, same hub function as the dashboard's Buy tab and the
    # wishlist — the coach reads the same shopping list the player sees, with
    # provenance, instead of re-assembling it from the scattered sections above.
    stem_path = m["path"][:-4] if m["path"].endswith(".txt") else m["path"]
    merged_combos = dict(combos or {})
    try:
        csb_near = spellbook.near_for_deck(m["path"], idx)
        have = {frozenset(mtglib.name_keys(p) for p in c.get("pieces", []))
                for c in merged_combos.get("near", []) + merged_combos.get("complete", [])}
        merged_combos["near"] = list(merged_combos.get("near", [])) + [
            n for n in csb_near
            if frozenset(mtglib.name_keys(p) for p in n["name"].split(" + ")) not in have]
    except Exception:
        pass
    buys = deckcore.buy_signals(deckcore.load_buylist(f"{stem_path}.buylist.csv"),
                                merged_combos, missing, idx)
    if buys:
        L.append("-- CARDS TO BUY (merged: curated buylist + combo pieces + unowned decklist) --")
        for r in buys:
            price = f" ~${r['price']:,.2f}" if r.get("price") is not None else ""
            L.append(f"  [{r.get('source', '?'):8}] {r['card']}{price} — {r['reason']}")
        L.append("")
    try:
        # Advisory: owned cards the optimizer's margin gate held back — a coaching
        # session should see what the field is starting to adopt.
        coll_l = mtglib.load_collection(COLLECTION)
        rz = optimize.optimize(m["path"], coll_l, mtglib.index_by_name(coll_l),
                               DECKS_DIR).get("risers", [])
    except Exception:
        rz = []
    if rz:
        L.append("-- FIELD RISERS (owned; below the auto-swap margin — your call) --")
        for r in rz:
            L.append(f"  {r['add']} ({r['add_inc']}%) over {r['over']} "
                     f"({r['over_inc']}%) — {r['gap']} pts short of auto-swap")
        L.append("")
    L.append("-- DECKLIST --")
    L.append(ex.deck_text(m["path"]).strip())
    return "\n".join(L) + "\n"


@app.route("/deck/<stem>/pin", methods=["POST"])
def deck_pin(stem):
    """Reserve a card's physical copy for this deck (or release it).

    Owning one copy of a card three decks want is a decision the arithmetic can't make.
    Pinning records it: the other decks stop treating that copy as available, and the
    optimizer won't cut it from here."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    name = request.form.get("name", "").strip()
    if name:
        pins = deckcore.load_pins()
        key = mtglib._norm(name)
        if request.form.get("action") == "unpin":
            pins.pop(key, None)
        else:
            pins[key] = stem                      # pinning elsewhere MOVES the pin
        deckcore.save_pins(pins)
    return redirect(url_for("deck", stem=stem))


@app.route("/deck/<stem>/delete", methods=["POST"])
def deck_delete(stem):
    """Delete a deck and its companion files. Git keeps the history, so this is
    recoverable — but it is still destructive, hence POST + a confirm in the UI."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    base = os.path.splitext(m["path"])[0]
    for suffix in (".txt", ".notes.md", ".buylist.csv", ".attrs.csv", ".changes.csv"):
        try:
            os.remove(base + suffix)
        except OSError:
            pass
    # drop any pins that pointed at it, so those copies free up again
    pins = deckcore.load_pins()
    left = {c: d for c, d in pins.items() if d != stem}
    if len(left) != len(pins):
        deckcore.save_pins(left)
    return redirect(url_for("index"))


@app.route("/deck/<stem>/assess")
def deck_assess_page(stem):
    """The assessment as a readable page. Same numbers as the .txt export, which stays
    around because pasting a plain block into a coaching session is a different job."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    coll, idx = collection_index()
    a = deckcore.analyze_deck(m["path"], coll)
    try:
        pool = optimize.pool_report(m["path"], coll, idx, DECKS_DIR)
    except Exception:
        pool = None
    field_decks = None
    try:
        rec = edhrec.recommendations(m["commander"], idx)
        field_decks = None if rec.get("error") else rec.get("sample_decks")
    except Exception:
        pass
    roles = [("ramp", "Ramp", 9, 13), ("draw", "Card draw", 8, 12),
             ("removal", "Removal", 8, 11), ("wipe", "Wipes", 2, 5),
             ("counter", "Counters", 0, 6), ("land", "Lands", 35, 38)]
    # Shares the dashboard's disk cache, so visiting both pages after a deck edit
    # costs ONE simulation in total, not one per surface.
    sim = goldfish.sim_for_deck(m["path"], coll, collection_path=COLLECTION)
    return render_template("assess.html", meta=m, a=a, pool=pool, roles=roles,
                           cats=a["report"].get("categories", {}),
                           field_decks=field_decks, sim=sim, page="decks")


@app.route("/deck/<stem>/assess.txt")
def deck_assess(stem):
    m = deck_meta(stem)
    if not m:
        abort(404)
    text = _assess_packet(m)
    return text if request.args.get("raw") else _txt(text, f"{stem}-assessment.txt")


@app.route("/shared")
def shared_view():
    coll, idx = collection_index()
    usage = deck_conflicts.scan(DECKS_DIR, idx)
    conf = deck_conflicts.conflicts(usage)
    total = round(sum(c["buy_cost"] or 0 for c in conf), 2)
    return render_template("shared.html", conf=conf, total=total, page="shared")


@app.route("/build-next")
def build_next():
    _, idx = collection_index()
    rows = cf.score(idx, simc.load_commanders(), cf.load_support(),
                    built=cf.built_commanders(DECKS_DIR))
    if request.args.get('hide_built'):
        rows = [r for r in rows if not r['built']]
    arch = request.args.get("archetype", "")
    if arch:
        rows = [r for r in rows if arch in r["archetypes"]]
    archetypes = sorted({a for r in rows for a in r["archetypes"]})
    return render_template("build_next.html", rows=rows[:30], archetypes=archetypes,
                           arch=arch, page="build")


def _deck_slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "deck"


@app.route("/build-next/<path:commander>/deck")
def build_deck(commander):
    """Full deck auto-built from the owned pool for this commander (Phase 3 v1).
    `?ci=` (color identity, e.g. from Scryfall) lets any typed commander build even
    if it isn't in the curated commanders.csv."""
    coll, idx = collection_index()
    d = auto_build.build(commander, coll, idx, DECKS_DIR, identity=(request.args.get("ci") or None),
                         skip_deck=_deck_slug(commander))
    return render_template("build_deck.html", d=d, page="build")


@app.route("/build-next/<path:commander>/deck.txt")
def build_deck_export(commander):
    coll, idx = collection_index()
    d = auto_build.build(commander, coll, idx, DECKS_DIR, identity=(request.args.get("ci") or None),
                         skip_deck=_deck_slug(commander))
    return _txt(auto_build.deck_text(d), f"{_deck_slug(commander)}.txt")


@app.route("/build-next/<path:commander>/save", methods=["POST"])
def build_deck_save(commander):
    """Write the auto-built draft to data/decks/, then tune it against what the field
    actually plays so a NEW deck lands optimized. (Manual edits are deliberately left
    alone — see /deck/<stem>/optimize.)"""
    coll, idx = collection_index()
    d = auto_build.build(commander, coll, idx, DECKS_DIR, identity=(request.form.get("ci") or None),
                         skip_deck=_deck_slug(commander))
    stem = _deck_slug(commander)
    path = os.path.join(DECKS_DIR, f"{stem}.txt")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(auto_build.deck_text(d))
    try:
        r = optimize.optimize(path, coll, idx, DECKS_DIR, apply=True)
        if r.get("illegal"):
            app.logger.error("post-optimize ILLEGAL in %s: %s", stem, r["illegal"])
    except Exception:
        pass                      # offline / EDHREC down: keep the un-tuned draft
    return redirect(url_for("deck", stem=stem))


@app.route("/deck/<stem>/optimize", methods=["POST"])
def deck_optimize(stem):
    """Tune an existing deck toward the field on demand (the ⚡ Optimize button)."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    coll, idx = collection_index()
    try:
        r = optimize.optimize(m["path"], coll, idx, DECKS_DIR, apply=True)
        if r.get("illegal"):
            app.logger.error("post-optimize ILLEGAL in %s: %s", stem, r["illegal"])
    except Exception:
        pass
    return redirect(url_for("deck", stem=stem))


_FILTER_ROLES = {"ramp", "draw", "removal", "wipe", "counter"}


def _collection_cards(coll, decks_dir):
    """Every owned card + the metadata the browse grid filters on (name, qty,
    price, type, MV, color identity, roles, which decks use it)."""
    import glob
    decks_of = {}
    for p in sorted(glob.glob(os.path.join(decks_dir, "*.txt"))):
        try:
            txt = open(p, encoding="utf-8").read()
        except OSError:
            continue
        label = os.path.splitext(os.path.basename(p))[0]
        for card in mtglib.parse_deck(txt):
            decks_of.setdefault(mtglib._norm(card.name), set()).add(label)
    rows = []
    for c in coll:
        mv = c.mana_value
        if mv is not None and mv == int(mv):
            mv = int(mv)
        rows.append({
            "name": c.name, "qty": c.quantity,
            "price": round(c.price, 2) if c.price else None,
            "type": c.primary_type if c.types else "",
            "mv": mv,
            "colors": ("".join(sorted(c.identity)) if c.identity else ("C" if c.types else "")),
            "roles": sorted(_FILTER_ROLES & mtglib.classify(c)),
            "decks": sorted(decks_of.get(mtglib._norm(c.name), [])),
        })
    rows.sort(key=lambda r: r["name"].lower())
    return rows


@app.route("/collection", methods=["GET"])
def collection_view():
    coll, idx = collection_index()
    priced = [c for c in coll if c.price]
    total = round(sum(c.value for c in coll), 2)
    top = sorted(priced, key=lambda c: -c.price)[:20]
    cards = _collection_cards(coll, DECKS_DIR)
    types = sorted({r["type"] for r in cards if r["type"]})
    additions = []
    if os.path.exists(ADDITIONS):
        for ln in open(ADDITIONS, encoding="utf-8"):
            s = ln.strip()
            if s and not s.startswith("#"):
                additions.append(s)
    attrs_path = os.path.join(ROOT, "data/collection/collection_attrs.csv")
    enriched_n = sum(1 for c in coll if c.types)
    # Production coverage is a SEPARATE number from type coverage: an attrs file
    # written before enrichment learned about produced_mana has full types and zero
    # production, and everything downstream then falls back to color identity.
    produced_n = sum(1 for c in coll if c.produced is not None)
    snapshot_attrs_path = os.path.join(
        ROOT, "data/collection/collection_attrs.snapshot.csv")
    # Either source counts as "on" — a fresh clone served solely by the committed
    # snapshot used to show the tile OFF beside a full coverage count, and a
    # session reading that started hand-curating names it already had data for.
    attrs_source = ("private" if os.path.exists(attrs_path) else
                    "snapshot" if os.path.exists(snapshot_attrs_path) else None)
    carddb = {
        "on": attrs_source is not None,
        "source": attrs_source,
        "covered": enriched_n,
        "total": len(coll),
        "pct": round(100 * enriched_n / len(coll)) if coll else 0,
        "produced_covered": produced_n,
        "produced_pct": round(100 * produced_n / len(coll)) if coll else 0,
    }
    return render_template("collection.html", unique=len(coll),
                           copies=sum(c.quantity for c in coll), total=total,
                           top=top, has_price=bool(priced), additions=additions,
                           carddb=carddb, cards=cards, types=types, page="collection")


@app.route("/collection/add", methods=["POST"])
def collection_add():
    name = request.form.get("name", "").strip()
    qty = request.form.get("qty", "1").strip() or "1"
    if name:
        header_needed = not os.path.exists(ADDITIONS)
        with open(ADDITIONS, "a", encoding="utf-8") as f:
            if header_needed:
                f.write("# Player-confirmed ownership not in the export yet.\n")
            f.write(f"{qty} {name}\n")
    return redirect(url_for("collection_view"))


@app.route("/collection/upload", methods=["POST"])
def collection_upload():
    f = request.files.get("csv")
    if f and f.filename:
        # Save to the private, gitignored CSV — never the tracked snapshot (a priced
        # export must not land in a public repo). Then enrich the whole collection so
        # colors / types / mana value / image ids are ready and the analytics light up.
        global COLLECTION
        f.save(COLLECTION_CSV)
        COLLECTION = COLLECTION_CSV
        try:
            import carddb
            carddb.enrich_api(COLLECTION_CSV, COLLECTION_ATTRS)
        except Exception:
            pass  # best-effort — the raw collection still loads without attributes
    return redirect(url_for("collection_view"))


@app.route("/refresh", methods=["POST"])
def refresh():
    """Regenerate the static wishlist.md + build/ dashboards (optional convenience)."""
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts/refresh.py"),
                    "--collection", COLLECTION, "--decks-dir", DECKS_DIR],
                   cwd=ROOT, capture_output=True, text=True)
    return redirect(request.referrer or url_for("index"))


@app.route("/sync", methods=["POST"])
def sync_now():
    """Run the GitHub sync on demand (same script as the daily auto-sync and the
    console path). Synchronous — ~10 s — so the redirect lands with the status
    freshly written; any needed reload is deferred past the redirect."""
    sync.run("manual", reload_delay=sync.RELOAD_DELAY)
    return redirect(url_for("index") + "#maint")


@app.route("/api/card/<path:name>")
def api_card(name):
    """Grounded, deck-agnostic payload for the site-wide card panel (Phase 0).
    Local data only; the panel fetches image/oracle/rulings live from Scryfall."""
    _, idx = collection_index()
    return jsonify(card_api.card_payload(name, idx, DECKS_DIR))


@app.route("/api/edhrec/<path:commander>")
def api_edhrec(commander):
    """EDHREC community staples for a commander, cross-referenced with the collection:
    owned (add) vs missing (buy). Cached to disk; degrades to an error payload."""
    _, idx = collection_index()
    return jsonify(edhrec.recommendations(commander, idx))


@app.route("/api/combos/build/<path:commander>")
def api_combos_build(commander):
    """Commander Spellbook combos present / one-away in the auto-built deck for this
    commander (full CSB DB, beyond the curated combos.csv). Cached; degrades gracefully."""
    coll, idx = collection_index()
    d = auto_build.build(commander, coll, idx, DECKS_DIR, identity=(request.args.get("ci") or None),
                         skip_deck=_deck_slug(commander))
    deck = mtglib.parse_deck(auto_build.deck_text(d))
    names = {mtglib._norm(x.name) for x in deck} | {mtglib._norm(commander)}
    r = spellbook.find_my_combos([commander], [(x.name, x.quantity) for x in deck])
    for c in r.get("almost", []):
        c["missing"] = [n for n in c["cards"] if mtglib._norm(n) not in names]
    r["almost"] = sorted([c for c in r.get("almost", []) if c.get("missing")],
                         key=lambda c: len(c["missing"]))
    return jsonify(r)


@app.route("/mobile")
def mobile():
    """How to install this on a phone. Shown in-app so the address and the steps live
    together — reading it off the terminal is the part people get stuck on."""
    host = os.environ.get("MTG_HOST", "127.0.0.1")
    lan = lan_ip() if host == "0.0.0.0" else None
    return render_template("mobile.html", lan=lan,
                           port=int(os.environ.get("MTG_PORT", "5000")), page="mobile")


@app.route("/sw.js")
def service_worker():
    """Served from the root, not /static/, because a service worker can only control
    pages at or below its own path — at /static/sw.js it could never manage the app."""
    return send_from_directory(os.path.join(ROOT, "webapp", "static"), "sw.js",
                               mimetype="application/javascript")


@app.route("/static/tokens.css")
def shared_tokens():
    """Serve the shared design tokens that live with the scripts (the dashboards inline
    the same file), so the web app and generated dashboards can't drift apart."""
    return send_from_directory(os.path.join(ROOT, "scripts", "assets"), "tokens.css",
                               mimetype="text/css")


@app.route("/health")
def health():
    return {"ok": True, "collection": COLLECTION, "decks": len(list_decks())}


def lan_ip():
    """Best-effort local network IP so we can print a phone-reachable URL."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    port = int(os.environ.get("MTG_PORT", "5000"))
    # Default to localhost-only (private). Set MTG_HOST=0.0.0.0 (or use run.sh) to
    # allow other devices on your Wi-Fi — e.g. your phone — to reach it.
    host = os.environ.get("MTG_HOST", "127.0.0.1")
    print("MTG Deckbuilder web app")
    print(f"  this computer : http://127.0.0.1:{port}")
    if host == "0.0.0.0":
        print(f"  on your phone : http://{lan_ip()}:{port}   (same Wi-Fi)")
        print("  (anyone on your network can reach it — see webapp/README 'Phone access')")
    print(f"  collection    : {COLLECTION}")
    app.run(host=host, port=port, debug=False)
