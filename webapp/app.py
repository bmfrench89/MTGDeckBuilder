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

from flask import (Flask, Response, abort, flash, jsonify, redirect,
                   render_template, request, send_from_directory, session, url_for)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import memo
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
import proxy_sheet as px

import sync
import enrich_bg


def _txt(text, filename):
    return Response(text + "\n", mimetype="text/plain",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})

def _html_download(html, filename):
    """An HTML page the browser SAVES instead of rendering.

    Safe to hand out as a file because a generated dashboard is already one
    self-contained document — tokens.css and the card panel are inlined by
    `build_dashboard._asset()`, so it opens with no server and no sibling assets.
    The one online dependency is card images, which are hotlinks by design
    (`docs/card-images.md`); the UI says so where the link is offered."""
    return Response(html, mimetype="text/html",
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


def _explain_block(explain, *keys):
    """Render the ENGINE's own "what this means" notes as collapsible <details>.

    The wording lives in `manabase.analyze()["explain"]`, never in the template — one
    source of truth, so the CLI, the generated dashboard and this page cannot drift
    into three different explanations of the same percentage."""
    from markupsafe import Markup, escape
    parts = []
    for k in keys:
        e = (explain or {}).get(k)
        if not e:
            continue
        why = f"<p>{escape(e['why'])}</p>" if e.get("why") else ""
        healthy = (f"<p class='muted fs-xs'>{escape(e['healthy'])}</p>"
                   if e.get("healthy") else "")
        parts.append(f"<details class='explain'><summary>{escape(e['what'])}</summary>"
                     f"{why}{healthy}</details>")
    return Markup("".join(parts))


@app.context_processor
def _explain_helper():
    return {"explain": _explain_block}


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
    m = re.match(r"(.+)", mtglib.deck_header(text, key))
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
        # Read for the Rule-0 table card's identity line; both are optional headers.
        "colors": _hdr(text, "Colors"),
        "archetype": _hdr(text, "Archetype"),
    }


def list_decks():
    stems = sorted(os.path.splitext(os.path.basename(p))[0]
                   for p in _glob_txt(DECKS_DIR))
    return [deck_meta(s) for s in stems]


def _glob_txt(d):
    import glob
    return glob.glob(os.path.join(d, "*.txt"))


def collection_index():
    """The collection + its name index. `load_collection` is memoized on the
    mtimes of every file it reads, so the repeat calls this function makes across
    a request (and across requests) cost one dict build, not a 54 ms re-parse.
    The index itself is rebuilt per call deliberately — it is milliseconds, and a
    shared dict is one more object callers could mutate."""
    coll = mtglib.load_collection(COLLECTION)
    return coll, mtglib.index_by_name(coll)


def _invalidate(stem=None):
    """Drop memoized analysis after a write. `stem` narrows it to one deck's
    entries; no argument drops everything (a collection-level change).

    Called explicitly from every write path rather than left to the mtime keys
    alone: mtime granularity is a filesystem property, and the card panel writes
    a deck and then redirects straight into a re-render — a same-second,
    same-size edit (swapping a card for an equal-length name) is a real way to
    serve the previous analysis. Deck STEMS appear in every key that read that
    deck, which is what makes the substring match precise here."""
    memo.invalidate(stem)


@app.after_request
def _invalidate_after_write(resp):
    """Backstop: any state-changing request drops the whole memo.

    The targeted `_invalidate` calls above are the ones that matter (they fire
    *during* the request, before anything re-reads). This exists so that adding a
    new write route and forgetting the call degrades to "one extra 50 ms rebuild"
    instead of "serves stale analysis until the process restarts". Every read
    path in this app is a GET, so the cost is bounded to genuine writes."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        memo.invalidate()
    return resp


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
        _invalidate(stem)
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
    found, so a stale section name can never drop the card on the floor.

    A second copy of a BASIC land increments the card's existing line instead of
    appending a twin (`3 Plains` -> `4 Plains`). Appending was how Y'shtola's
    Basics ended up holding `1 Plains` and `3 Plains` as separate lines: legal,
    but the page reads as two entries for one card. Only basics merge — a
    nonbasic twin is a singleton illegality `optimize.singleton_violations`
    reports right after this write, and rolling it into `2 <card>` would tuck the
    evidence out of sight.

    The basic search is deliberately FILE-WIDE, not section-scoped: a basic land
    belongs on exactly one line of a deck file, and scoping the search to the
    requested section produced a cross-section split (`2 Plains` under Lands plus
    a fresh `1 Plains` under Basics) that nothing downstream merges — the server's
    auto-regroup only fires on decks with an `Unsorted` section, so such a split
    would live forever.
    """
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
        stop = next((j for j in range(start + 1, len(lines)) if _section_label(lines[j])),
                    len(lines))
        cards = [j for j in range(start + 1, stop)
                 if lines[j].strip() and not lines[j].strip().startswith("#")]
        at = (cards[-1] + 1) if cards else start + 1
    if mtglib.is_basic(name):
        key = mtglib._norm(name)
        for j in range(len(lines)):
            s = lines[j].strip()
            if not s or s.startswith("#"):
                continue
            m = mtglib._QTY_RE.match(s)   # the ONE qty-line parser ('1x Name' included)
            qty, cardname = (int(m.group(1)), m.group(2)) if m else (1, s)
            if mtglib._norm(cardname) == key:
                indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
                lines[j] = f"{indent}{qty + 1} {cardname}"
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write("\n".join(lines))
                return True
    lines.insert(at, f"1 {name}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    return True


def _edit_deck_card(path, action, name, replacement=None, section=None):
    """Line-based edit of a deck .txt: remove, replace, or add a single card, preserving
    quantity, section, and everything else. Returns True if a line changed."""
    keys = mtglib.name_keys(name)
    lines = open(path, encoding="utf-8").read().split("\n")
    if action == "add":
        return _insert_deck_card(path, lines, name, section)
    if action == "replace" and replacement and mtglib.is_basic(replacement):
        # Replacing a card WITH a basic must not write `1 Plains` at the outgoing
        # card's slot: that is simultaneously the split-line bug (a second Plains
        # line) and the misfile bug (a basic sitting under Lands/Creatures) — and
        # it comes from the very flow that misfiled White Auracite and Risky
        # Shortcut. Drop the outgoing line, then merge into the basic's own line.
        dropped = _edit_deck_card(path, "remove", name)
        lines = open(path, encoding="utf-8").read().split("\n")
        _insert_deck_card(path, lines, replacement, section="Basics")
        return dropped
    out, changed = [], False
    for ln in lines:
        s = ln.strip()
        if not changed and s and not s.startswith("#"):
            m = mtglib._QTY_RE.match(s)   # shared parser — '1x Name' must not no-op
            cardname = m.group(2) if m else s
            qty = m.group(1) if m else "1"
            # name_keys, not raw _norm: the panel's data-key can carry EITHER form of
            # a DFC name (decklist figures key the deck file's form, EDHREC/field rows
            # key what the snapshot emits — often the front face alone), so an exact
            # compare silently no-ops on "Smaug, the Great Calamity // Spew Flame" vs
            # "Smaug, the Great Calamity". The route's own singleton guard already
            # matches both keys; the editor must agree with it.
            if mtglib.name_keys(cardname) & keys:
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
            # Refuse loudly, not with a bare redirect: the panel reloads on any
            # redirect, so a silent one looks exactly like a success that changed
            # nothing — the "replace did not work" bug report, twice over.
            return (f"{replacement} is already in this deck — that swap would "
                    "break the singleton rule.", 409)
    if action in ("remove", "replace") and name:
        changed = _edit_deck_card(m["path"], action, name, replacement)
        if not changed:
            return (f"Couldn't find “{name}” in the deck file — nothing was "
                    "changed. (If this card is a buy-list or field suggestion, "
                    "it isn't in the 99 to begin with.)", 404)
        if changed:
            if action == "replace" and replacement:
                _log_manual_change(m["path"], replacement, replaced=name,
                                   source="manual-replace")
            elif action == "remove":
                # A bare Remove is as much a player decision as a Replace, and the
                # never-re-add rule reads the LOG — unlogged, the optimizer could
                # re-propose the exact card through this button (the Hojo
                # mechanism through the other flow). Card column stays empty:
                # nothing came in, and load_changes skips empty-Card rows so the
                # NEW badge and manual-adds advisory are untouched.
                _log_manual_change(m["path"], "", replaced=name,
                                   source="manual-remove")
            _invalidate(stem)
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
    _invalidate(stem)                   # the deck changed — drop it before the
                                        # singleton check and the advise below
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


@app.route("/deck/<stem>/proxies")
def deck_proxies(stem):
    """Print-exact playtest proxies: 63x88mm cells, nine per page.

    Three sheets per deck: the whole deck (?), the buylist (?buylist=1 — the
    real one: decks are owned-cards-only, so what's worth printing is the
    upgrades the player is deciding whether to BUY; sleeve the proxy over the
    card its Replaces names and play first), and ?missing=1 for completeness.
    Geometry and images live in scripts/proxy_sheet.py — one code path with the
    CLI, like every other spoke. Rendered inline (no attachment): the flow is
    open -> print at 100%, not save."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    cells, title = px.build(deck=m["path"], collection=COLLECTION,
                            missing=bool(request.args.get("missing")),
                            buylist=bool(request.args.get("buylist")))
    return px.generate_html(cells, title=title)


@app.route("/export/deck/<stem>.html")
def export_deck_html(stem):
    """The whole dashboard as a downloadable, self-contained HTML report.

    `editable=False` is deliberate, not merely the default: a saved file has no
    server behind it, so Add/Remove/Replace and the bracket form would be dead
    controls posting into the void — the same reasoning that already keeps them
    off CLI-rendered dashboards.

    This is also the PDF path. The repo generates no PDF of its own on purpose
    (`scripts/` is stdlib-only, and card images are browser hotlinks that a
    server-side renderer could not fetch); the browser's own print dialog has the
    images and paginates properly, so Ctrl+P on this file is the export."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    res = bd.generate(m["path"], COLLECTION, title=m["title"],
                      commander=m["commander"], theme=m["theme"],
                      decks_dir=DECKS_DIR, editable=False)
    html = res["dashboard"]
    # Deliberately no singleton banner, unlike /deck/<stem>: that red bar is a
    # live-surface alarm meant to be acted on in the app, and the deck it names
    # can be fixed only there. A downloaded snapshot has nowhere to send you.
    return html if request.args.get("raw") else _html_download(html, f"{stem}.html")


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
            restr = f" (+{c['restricted']} restricted)" if c.get("restricted") else ""
            L.append(f"  {c['color']}: {c['sources']} sources{restr} (Karsten ~{c['karsten_target']}) · "
                     f"P(≥1 opener) {c['p_open']*100:.0f}% · {c['status']}")
        mb = mana.get("basis") or {}
        if mb.get("restricted_lands"):
            L.append(f"  ({mb['restricted_lands']} land(s) make spend-restricted mana — "
                     "counted apart; add back for spells that match)")
        if mb.get("restriction_unknown_lands"):
            L.append(f"  (~{mb['restriction_unknown_lands']} land(s) pre-vocabulary — "
                     "restriction unknown, counted as unrestricted)")
        if mana["risky"]:
            L.append("  risky to cast on curve: " +
                     ", ".join(f"{r['name']} {r['p']*100:.0f}%" for r in mana["risky"]))
        fetch = mana.get("fetch") or {}
        if fetch.get("unknown") == "pre-vocabulary":
            L.append("  fetch census: unavailable — enrichment predates the fetch "
                     "vocabulary (re-enrich to unlock)")
        elif fetch.get("rows"):
            L.append("-- FETCH CENSUS (what can each search actually find HERE?) --")
            for r in fetch["rows"]:
                state = {"none": " <-- NO TARGETS", "thin": " <-- THIN"}.get(r["state"], "")
                L.append(f"  {r['name']}: {r['targets']} target(s){state}")
            if fetch.get("unknown") == "no-subtype-data":
                L.append("  (~ counts may be low: some lands here have no type data)")
        L.append("")
    elif mana is not None:
        L.append("-- CONSISTENCY -- (name-only collection: enrich for colored-source math)\n")
    # Sequenced play — the questions the closed forms above structurally cannot answer.
    # Same cached helper the dashboard calls, so a coach and a page never disagree.
    sim = goldfish.sim_for_deck(m["path"], COLLECTION)
    # "What do I cut" — the most-asked deckbuilding question, ranked by the same
    # value the optimizer scores swaps with. Advisory: it names nothing to replace.
    try:
        cuts = optimize.cut_candidates(m["path"], COLLECTION, idx=idx, limit=10,
                                       analysis=a)
    except Exception:
        cuts = None
    try:
        _opt_prev = optimize.optimize(m["path"], a["coll"], idx, DECKS_DIR,
                                      apply=False)
        holds = _opt_prev.get("manual_holds") or []
    except Exception:
        holds = []
    if holds:
        L.append("-- HELD (your removals, standing) --")
        for h in sorted(holds, key=lambda x: -x["inc"])[:6]:
            L.append(f"  {h['name']} ({h['inc']}% field) — removed by hand "
                     f"{h['removed']}; the optimizer will not re-propose it")
        L.append("")
    if cuts and cuts.get("rows"):
        L.append("-- IF YOU MUST CUT (advisory, ranked lowest value first) --")
        for r in cuts["rows"]:
            flag = " [PROTECTED]" if r["protected"] else ""
            L.append(f"  {r['value']:>3}  {r['name']} — {r['why']}"
                     f"{' · role ' + r['role'] + ' ' + r['role_state'] if r.get('role_state') else ''}"
                     f"{flag}")
        if cuts.get("no_field"):
            L.append("  (no EDHREC field data — fit-only ranking, a weak signal)")
        L.append(f"  {cuts['advisory']}")
        L.append("")
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
        clk = sim.get("clock") or {}
        if clk.get("median_first_kill") is not None:
            L.append(f"  CLOCK: presents lethal median T{clk['median_first_kill']:g} "
                     + " · ".join(f"by T{t} {v*100:.0f}%"
                                  for t, v in (clk.get("p_first_kill_by") or {}).items())
                     + f"   [{d['first_kill']}]")
            if clk.get("median_table_kill") is not None:
                L.append(f"  CLOCK: whole table median T{clk['median_table_kill']:g} "
                         f"  [{d['table_kill']}]")
            if clk.get("bracket_hint"):
                L.append(f"  CLOCK: consistent with the Bracket {clk['bracket_hint']} "
                         f"expectation  [{d['clock_bracket']}]")
        if clk.get("note"):
            L.append(f"  CLOCK: {clk['note']}")
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


def _set_deck_header(path, key, value):
    """Set (or clear) one `# Key: value` header line, preserving everything else.

    Header lines live above the first section marker. An existing key is rewritten in
    place; a new one is appended to the header block, never dropped after a section
    header where the parser would stop seeing it."""
    lines = open(path, encoding="utf-8").read().split("\n")
    pat = re.compile(rf"^#\s*{re.escape(key)}\s*:", re.IGNORECASE)
    first_section = next((i for i, ln in enumerate(lines)
                          if deckcore.section_label(ln) is not None), len(lines))
    at = next((i for i in range(first_section) if pat.match(lines[i].strip())), None)
    if value is None:
        if at is not None:
            lines.pop(at)
    elif at is not None:
        lines[at] = f"# {key}: {value}"
    else:
        insert = first_section
        while insert > 0 and not lines[insert - 1].strip():
            insert -= 1                       # keep the blank line before the section
        lines.insert(insert, f"# {key}: {value}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))


@app.route("/deck/<stem>/bracket", methods=["POST"])
def deck_bracket(stem):
    """Record the player's own bracket for this deck (or clear it).

    The detected bracket is a card-count estimate and stays visible either way —
    brackets 1 and 5 are defined by INTENT rather than contents (Exhibition is "not
    built to win", cEDH is metagame-tuned), which no card scan can see. This header
    records that intent; it never silences the evidence."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    raw = (request.form.get("bracket") or "").strip()
    if raw in ("1", "2", "3", "4", "5"):
        _set_deck_header(m["path"], "Bracket", raw)
        _invalidate(stem)
        flash(f"Bracket set to {raw} for this deck. The detected bracket is still "
              "shown beside it.", "info")
    elif raw in ("", "auto"):
        _set_deck_header(m["path"], "Bracket", None)
        _invalidate(stem)
        flash("Bracket setting cleared — showing the detected bracket only.", "info")
    return redirect(url_for("deck", stem=stem) + "#tab-power")


@app.route("/pins")
def pins_page():
    """Every reserved copy in one place, with one-tap move.

    Pinning was already enforced (auto_build's pool, the optimizer's cuts and adds);
    what was missing was somewhere to SEE the reservations and change them without
    hunting through six deck pages. Moving a pin is one action here rather than
    unpin-then-find-the-other-deck-then-repin, because cards shift between decks
    constantly and friction there is what makes people stop pinning at all."""
    pins = deckcore.load_pins()
    coll, idx = collection_index()
    decks = list_decks()
    by_stem = {d["stem"]: d for d in decks}
    # Which decks actually RUN each pinned card — a pin pointing at a deck that no
    # longer runs the card is the stale state this page exists to surface.
    runs = {}
    for d in decks:
        try:
            for c in mtglib.parse_deck(open(d["path"], encoding="utf-8").read()):
                for k in mtglib.name_keys(c.name):
                    runs.setdefault(k, set()).add(d["stem"])
        except OSError:
            continue
    rows = []
    for key, stem in sorted(pins.items()):
        ref = mtglib.lookup(idx, key)
        in_decks = sorted(runs.get(key, set()))
        rows.append({
            "key": key,
            "name": ref.name if ref else key,
            "deck": stem,
            "deck_title": (by_stem.get(stem) or {}).get("title", stem),
            "owned": ref.quantity if ref else 0,
            "in_decks": in_decks,
            "stale": stem not in in_decks,      # pinned to a deck that doesn't run it
            "contested": len(in_decks) > (ref.quantity if ref else 0),
        })
    return render_template("pins.html", rows=rows, decks=decks, page="pins")


@app.route("/pins/move", methods=["POST"])
def pins_move():
    """Move a pin to another deck, or release it — one action, not two."""
    key = (request.form.get("card") or "").strip()
    target = (request.form.get("deck") or "").strip()
    if key:
        pins = deckcore.load_pins()
        k = mtglib._norm(key)
        if target in ("", "none"):
            pins.pop(k, None)
            flash(f"Released the pin on {key} — every deck can use that copy again.",
                  "info")
        else:
            pins[k] = target                    # one deck per card: this MOVES it
            flash(f"{key} is now reserved for {target}.", "info")
        deckcore.save_pins(pins)
    return redirect(url_for("pins_page"))


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
    # The deck's files are gone; its cached analysis would outlive it. (Pin
    # writes need no invalidation of their own — `analyze_deck` never reads pins;
    # they reach the optimizer through `pinned_elsewhere` and the dashboard
    # through its own `load_pins` call, neither of which is memoized.)
    _invalidate(stem)
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
    # Derived from THE template (deckcore), archetype-aware for THIS deck — this was
    # a fourth hand-copied role table, and it disagreed with the other three.
    arch = deckcore.archetype_words(open(m["path"], encoding="utf-8").read())
    rr = deckcore.role_ranges(arch)
    labels = [("ramp", "Ramp"), ("draw", "Card draw"), ("removal", "Removal"),
              ("wipe", "Wipes"), ("counter", "Counters")]
    roles = [(k, lbl, rr[k][0], rr[k][1]) for k, lbl in labels]
    roles.append(("land", "Lands", deckcore.LAND_RANGE[0], deckcore.LAND_RANGE[1]))
    # Shares the dashboard's disk cache, so visiting both pages after a deck edit
    # costs ONE simulation in total, not one per surface.
    sim = goldfish.sim_for_deck(m["path"], coll, collection_path=COLLECTION)
    return render_template("assess.html", meta=m, a=a, pool=pool, roles=roles,
                           cats=a["report"].get("categories", {}),
                           field_decks=field_decks, sim=sim, page="decks")


def _plan_lines(m, a):
    """The deck's game plan, and an honest label for where it came from.

    The player's own `.notes.md` is the truth when it exists; otherwise a plain
    role-count summary stands in, LABELLED as derived so nobody reads a heuristic as
    the author's intent. Returns (lines, source)."""
    stem = m["path"][:-4] if m["path"].endswith(".txt") else m["path"]
    notes = deckcore.load_notes(f"{stem}.notes.md")
    if notes:
        out = []
        for raw in notes.splitlines():
            s = raw.strip().lstrip("#").strip()
            if not s or s.startswith("<!--"):
                continue
            out.append(s.lstrip("-* ").strip())
            if len(out) >= 6:
                break
        if out:
            return out, "your notes"
    cats = (a.get("report") or {}).get("categories", {})
    sig = (a.get("assessment") or {}).get("signals", {})
    derived = [f"{cats.get('ramp', 0)} ramp · {cats.get('draw', 0)} draw · "
               f"{sig.get('interaction', 0)} interaction pieces",
               f"{(a.get('report') or {}).get('lands', 0)} lands, "
               f"average mana value {sig.get('avg_mv', '—')}"]
    return derived, "derived from role counts — no .notes.md for this deck"


@app.route("/deck/<stem>/table-card")
def deck_table_card(stem):
    """The Rule-0 table card: one screen you can hand across the table.

    Every fact comes from the same engines the dashboard uses (codemap's
    card-knowledge-flow rule — nothing is re-derived here). Bracket 1's Game Changer
    exception literally requires cards be "discussed pregame" and WotC frames the
    bracket as a conversation aid, so this is the artifact the system asks for and no
    surveyed tool generates. Degrades honestly: a source that isn't reachable is named
    as unavailable rather than silently omitted."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    coll, idx = collection_index()
    a = deckcore.analyze_deck(m["path"], coll)
    assessment = a.get("assessment")
    sig = (assessment or {}).get("signals", {})

    combos_present, combos_near, combo_note = [], 0, None
    try:
        sb = spellbook.combos_for_deck(m["path"])
        if sb and not sb.get("error"):
            combos_present = [c.get("name") or ", ".join(c.get("pieces", []))
                              for c in (sb.get("complete") or [])][:6]
            combos_near = len(sb.get("near") or [])
        else:
            combo_note = "combo data unavailable offline — showing local combos only"
    except Exception:
        combo_note = "combo data unavailable offline — showing local combos only"
    local = a.get("combos") or {}
    if not combos_present and local.get("complete"):
        combos_present = [c["name"] for c in local["complete"]][:6]

    sim = goldfish.sim_for_deck(m["path"], coll, collection_path=COLLECTION)
    clock = (sim or {}).get("clock")
    plan, plan_source = _plan_lines(m, a)
    return render_template("table_card.html", meta=m, a=a, assessment=assessment,
                           sig=sig, combos_present=combos_present,
                           combos_near=combos_near, combo_note=combo_note,
                           clock=clock, defs=(sim or {}).get("definitions", {}),
                           plan=plan, plan_source=plan_source, page="decks")


@app.route("/deck/<stem>/mulligan")
def deck_mulligan(stem):
    """Mulligan practice on the deck's REAL hands.

    The 2025-26 trainers that exist are deck-generic and online-only; this deals from
    the actual compiled list, so the hands are the ones the player will really see.
    The sim's verdict is shown AFTER the call with the reasoning behind it, and it is
    framed as a heuristic to compare against rather than a correct answer — the rule
    reads land counts, not card quality, and the page says so."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    return render_template("mulligan.html", meta=m, page="decks")


@app.route("/api/deck/<stem>/hand")
def api_deck_hand(stem):
    """One seeded opening hand plus the sim's verdict and its reasoning.

    Seeded by an explicit `seed` so a hand is reproducible (and so a test can pin
    one); the page draws a fresh seed per hand."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    try:
        seed = int(request.args.get("seed") or 0)
    except ValueError:
        seed = 0
    mulls = max(0, min(goldfish.MULL_FLOOR, int(request.args.get("mulls") or 0)))
    coll, _idx = collection_index()
    try:
        compiled, _idx2 = goldfish.load_for_ab(m["path"], coll,
                                               collection_path=COLLECTION)
    except Exception:
        compiled = None
    if not compiled:
        return jsonify({"error": "could not compile this deck"}), 200
    if not compiled or not compiled.get("library"):
        return jsonify({"error": "no library to draw from"}), 200

    import random as _random
    lib = list(compiled["library"])
    _random.Random(seed).shuffle(lib)
    hand = lib[:goldfish.HAND]
    verdict = goldfish.keep_verdict(hand, mulls=mulls, mulligan=True)
    lands = [c.name for c in hand if c.is_land]
    spells = [{"name": c.name, "mv": c.mv} for c in hand if not c.is_land]
    colors = sorted({p for c in hand if c.is_land for p in (c.produces or ())})
    ramp = [c.name for c in hand if not c.is_land and c.is_producer]
    return jsonify({
        "hand": [{"name": c.name, "land": c.is_land, "mv": c.mv} for c in hand],
        "lands": lands, "spells": spells, "colors": colors, "ramp": ramp,
        "mulls": mulls, "floor": goldfish.HAND - goldfish.MULL_FLOOR,
        "verdict": verdict,
        "band": list(goldfish.KEEP_LANDS),
        "caveat": ("The sim's rule counts LANDS, not card quality — it cannot see that "
                   "your two spells are both uncastable, or that one of them is a "
                   "tutor. Disagreeing with it is often correct."),
        "have_data": bool(compiled.get("have_data", True)),
    })


@app.route("/api/deck/<stem>/ab")
def api_deck_ab(stem):
    """Paired A/B for a proposed swap — "what does this change actually do?"

    The engine has measured swaps over common random numbers since the goldfish
    landed, but only from the CLI; the Replace flow is where the player is actually
    choosing. Advisory and non-blocking: the panel shows it beside the button and the
    edit proceeds whatever this says (or fails to say)."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    out_name = (request.args.get("out") or "").strip()
    in_name = (request.args.get("in") or "").strip()
    if not out_name or not in_name:
        return jsonify({"error": "need out= and in="}), 200
    coll, _idx = collection_index()
    try:
        # Fewer games than a CLI run: this is inline in a click, and the paired
        # design means even a short run separates a real change from noise.
        # Disk-cached on the same key `sim_for_deck` uses plus the swap itself, so
        # looking at the same proposed swap twice costs a file read, not 800 games.
        ab = goldfish.ab_for_deck(m["path"], coll, out_name, in_name, games=400,
                                  seed=0, collection_path=COLLECTION)
    except Exception:
        return jsonify({"error": "simulation unavailable"}), 200
    if not ab:
        return jsonify({"error": "simulation unavailable"}), 200
    if ab.get("error"):
        return jsonify({"error": ab["error"]}), 200
    keep = ("commander_by_t4", "commander_by_t6", "first_kill_turn", "screw")
    return jsonify({
        "out": ab["out"], "in": ab["in"], "games": ab["games"],
        "deltas": {k: v for k, v in ab["deltas"].items() if k in keep},
        "note": ("Paired over identical shuffles, so this measures the swap rather "
                 "than luck. Only starred rows cleared their confidence interval."),
    })


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
        _flash_optimize(r)
    except Exception:
        pass                      # offline / EDHREC down: keep the un-tuned draft
    _invalidate(stem)             # a brand-new deck, and an optimizer pass over it
    return redirect(url_for("deck", stem=stem))


def _flash_optimize(r):
    """Say what the optimizer did, and under WHICH template, on the web surface.

    The CLI has printed the archetype-widened role template since 2026-08-13, but
    the ⚡ button is where the player's finger actually is — and a widened template
    is a LOOSENING (it permits swaps the default refused), so the surface that
    triggers it is the one that must disclose it. Invariant 10: on every surface.
    """
    if not r:
        return
    n = len(r.get("swaps") or []) + len(r.get("land_swaps") or [])
    flash(f"Optimizer: {n} change(s) applied." if n else
          "Optimizer: already aligned with the field — no changes.", "info")
    widened = {role: rng for role, rng in (r.get("role_ranges") or {}).items()
               if rng != optimize.ROLE_RANGE.get(role)}
    if widened:
        flash("Judged under an archetype-widened role template ("
              + " ".join(r.get("archetype") or []) + "): "
              + ", ".join(f"{k} {lo}-{hi}" for k, (lo, hi) in sorted(widened.items()))
              + ".", "info")
    if r.get("archetype_unknown"):
        flash("Archetype word(s) not recognised, no widening applied: "
              + ", ".join(r["archetype_unknown"]) + ".", "warn")
    for h in sorted(r.get("manual_holds") or [], key=lambda x: -x["inc"])[:3]:
        # The CLI has printed these since the rule landed; the ⚡ button — where
        # the player's finger actually is — must too. Withholding a 69%-field
        # card with zero disclosure would violate the rule's own contract:
        # decision durable, evidence VISIBLE.
        flash(f"Held: {h['name']} ({h['inc']}% field) — you removed it by hand on "
              f"{h['removed']}, so it is not re-proposed. Add it back yourself if "
              "you've changed your mind.", "info")
    for g in (r.get("land_guard") or [])[:3]:
        who = ", ".join(g["for"][:2]) or "a fetcher"
        flash(f"Kept {g['kept']}: the last {g['type'].capitalize()}-typed land — "
              f"{who} would have nothing to fetch.", "info")
    if r.get("illegal"):
        flash("!! ILLEGAL after optimize: "
              + ", ".join(f"{q}x {n2}" for q, n2 in r["illegal"])
              + " — Commander allows one copy.", "warn")


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
        _flash_optimize(r)
    except Exception:
        pass
    _invalidate(stem)                   # an applying run rewrote the 99
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
                           carddb=carddb, cards=cards, types=types,
                           enrich_status=enrich_bg.status_view(), page="collection")


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
        _invalidate()             # owned_additions feeds EVERY deck's analysis
    return redirect(url_for("collection_view"))


@app.route("/collection/upload", methods=["POST"])
def collection_upload():
    """Save the uploaded export, then enrich it in the BACKGROUND.

    Enrichment is ~1 Scryfall request per 75 cards — minutes for a real
    collection. Running it inline held the browser open for the whole of that and
    spent one request's worth of a shared CPU quota on it; on this host that is a
    timeout, not a slow page. The upload itself is unchanged and deliberately
    untouched: it writes the PRIVATE, gitignored CSV and never the tracked
    name-only snapshot (that separation closed a real leak — see CLAUDE.md)."""
    f = request.files.get("csv")
    if f and f.filename:
        global COLLECTION
        f.save(COLLECTION_CSV)
        COLLECTION = COLLECTION_CSV
        _invalidate()             # a whole new collection — nothing cached survives
        flash(enrich_bg.start(COLLECTION_CSV, COLLECTION_ATTRS), "info")
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
    # Pass the pins so a staple whose only copy is reserved for another deck is
    # LABELLED rather than silently offered as available.
    return jsonify(edhrec.recommendations(
        commander, idx, pins=deckcore.load_pins(),
        for_stem=request.args.get("for") or None))


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


def _asset_version():
    """A cache-busting version derived from the code itself.

    The service worker's cache name was hand-pinned (`mtgdb-v1`), so every shipped
    change to a cached asset needed someone to remember to bump it — and forgetting
    means an installed phone keeps serving the old CSS/JS with no way for the player
    to tell. Derived from the current git HEAD where available, else the newest mtime
    across the shell files, so it moves on its own."""
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, timeout=5)
        if head.returncode == 0 and head.stdout.strip():
            return head.stdout.strip()
    except Exception:
        pass
    newest = 0
    for d in (os.path.join(ROOT, "webapp", "static"),
              os.path.join(ROOT, "scripts", "assets")):
        try:
            for f in os.listdir(d):
                newest = max(newest, int(os.path.getmtime(os.path.join(d, f))))
        except OSError:
            continue
    return str(newest)


@app.route("/sw.js")
def service_worker():
    """Served from the root, not /static/, because a service worker can only control
    pages at or below its own path — at /static/sw.js it could never manage the app.

    The cache VERSION is substituted at serve time from `_asset_version()`: a stale
    installed worker is invisible to the player, so this must not depend on anyone
    remembering to edit a constant."""
    path = os.path.join(ROOT, "webapp", "static", "sw.js")
    with open(path, encoding="utf-8") as f:
        js = f.read()
    js = js.replace("__ASSET_VERSION__", _asset_version())
    return Response(js, mimetype="application/javascript",
                    headers={"Cache-Control": "no-cache"})


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
