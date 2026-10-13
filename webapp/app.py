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
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from urllib.parse import quote, unquote, urlsplit

from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, send_from_directory, session, url_for)
from markupsafe import escape

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
import intake
import proxy_sheet as px

import sync
import enrich_bg
import users


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
_PUBLIC_ENDPOINTS = {"login", "static", "service_worker", "shared_tokens", "web_manifest"}


def _has_control_chars(s, space=True):
    """True when `s` carries a C0 control character or DEL (and, with `space`, a
    space) — the bytes that turn a redirect target into something else: a header
    split, or a tab/newline the browser silently strips."""
    lo = 0x21 if space else 0x20
    return any(ord(ch) < lo or ord(ch) == 0x7F for ch in s)


def _safe_next(target):
    """Only ever redirect within the app — an absolute URL here would be an
    open-redirect hole on a public host.

    Checked on the value as received (already decoded once by Werkzeug) AND on its
    percent-decoded form (W5): browsers strip tab/newline from URLs, so
    `/\\t/evil.example` collapses to the protocol-relative `//evil.example`, a
    `%09` is one decode away from the same, and a raw newline used to 500 inside
    Werkzeug's header check. The received value may hold no whitespace at all; the
    decoded form may hold an encoded space (`/build-next/The%20Ur-Dragon/deck` is a
    real page) but no control character. Backslashes are normalized first:
    browsers treat '/\\evil.example' as '//evil.example'. What survives is a plain
    local path: no scheme, no netloc, one leading slash."""
    raw = target if isinstance(target, str) else ""
    home = url_for("index")
    if not raw:
        return home
    for form, no_space in ((raw, True), (unquote(raw), False)):
        if _has_control_chars(form, space=no_space):
            return home
        t = form.replace("\\", "/")
        try:
            parts = urlsplit(t)
        except ValueError:
            return home
        if parts.scheme or parts.netloc or not t.startswith("/") or t.startswith("//"):
            return home
    return raw


_UNSAFE_METHODS_EXEMPT = ("GET", "HEAD", "OPTIONS")


@app.before_request
def _reject_cross_site_writes():
    """CSRF brake that works with no password set (W4).

    SameSite=Lax only protects a session cookie, and the default local/LAN app has
    no session at all — so a page on any other site could POST to
    /deck/<stem>/delete and the browser would deliver it. Browsers stamp every
    state-changing request with `Origin` (and modern ones with `Sec-Fetch-Site`),
    so a write whose Origin names another host, or that the browser itself labels
    cross-site, is refused. A request carrying neither header (curl, the test
    client, scripts) is not a browser being tricked, and passes.

    `X-Forwarded-Host` is honoured as an alternative match for a tunnel that
    rewrites Host: a cross-site page cannot set that header without a CORS
    preflight this app never grants, so trusting it does not reopen the hole."""
    if request.method in _UNSAFE_METHODS_EXEMPT:
        return None
    if (request.headers.get("Sec-Fetch-Site") or "").strip().lower() == "cross-site":
        abort(403)
    origin = request.headers.get("Origin")
    if origin is None:
        return None
    try:
        origin_host = urlsplit(origin.strip()).netloc.lower()
    except ValueError:
        origin_host = ""
    allowed = {(request.host or "").lower()}
    fwd = request.headers.get("X-Forwarded-Host")
    if fwd:
        allowed.add(fwd.split(",")[0].strip().lower())
    if not origin_host or origin_host not in allowed:
        abort(403)
    return None


def _session_valid():
    """A signed-in session that is still good. The owner's (and every pre-members
    cookie, which carries `authed` but no name) is good until MTG_PASSWORD changes.
    A member's is good while the member exists, is enabled and the stored `ver`
    matches — "Sign out everywhere" and Disable bump it, so an old cookie fails on
    its very next request without touching anyone else's."""
    if not session.get("authed"):
        return False
    who = session.get("who") or users.OWNER_KEY
    if who == users.OWNER_KEY:
        return True
    m = users.member(who)
    return bool(m and not m.get("disabled") and int(m.get("ver", 1)) == session.get("ver"))


@app.before_request
def _require_login():
    if not PASSWORD or request.endpoint in _PUBLIC_ENDPOINTS:
        return None
    if _session_valid():
        return None
    if session.get("authed"):
        session.clear()                   # a member signed out everywhere / disabled
    if request.method == "GET":
        # request.path is DECODED (`/build-next/The Ur-Dragon/deck`); re-quote it so
        # the round trip through ?next= survives _safe_next's no-whitespace rule.
        back = quote(request.path)
        if request.query_string:
            back += "?" + request.query_string.decode("latin-1")
        return redirect(url_for("login", next=back))
    abort(401)  # unauthenticated POSTs get a hard no, not a redirect-to-form


@app.route("/login", methods=["GET", "POST"])
def login():
    """The owner signs in with MTG_PASSWORD and a blank name (or their own name);
    a member with their name and their own password (docs/spec-second-login.md)."""
    if not PASSWORD or _session_valid():
        return redirect(_safe_next(request.args.get("next")))
    error = None
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:64]
        pw = request.form.get("password", "")
        key = users.key_of(name) or users.OWNER_KEY
        owner_names = {users.OWNER_KEY, users.key_of(users.owner_display())}
        if users.locked(key):
            time.sleep(0.6)
            error = "Too many wrong tries for that name — wait 15 minutes."
        elif key in owner_names and hmac.compare_digest(pw, PASSWORD):
            users.clear_failures(key)
            session.clear()
            session.permanent = True
            session["authed"] = True
            session["who"] = users.OWNER_KEY
            return redirect(_safe_next(request.form.get("next")))
        else:
            m = users.check_member(name, pw) if key not in owner_names else None
            if m:
                users.clear_failures(key)
                session.clear()
                session.permanent = True
                session["authed"] = True
                session["who"] = m["name"]
                session["ver"] = int(m.get("ver", 1))
                return redirect(_safe_next(request.form.get("next")))
            users.note_failure(key)
            time.sleep(0.6)  # blunt but effective brake on password guessing
            error = "Wrong name or password." if users.exists() else "Wrong password."
    return render_template("login.html", error=error, named=users.exists(),
                           next=request.values.get("next", "/"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


def _me():
    """(key, display name, role) of whoever is using the app. With no password the
    app is single-user and that is the owner."""
    who = (session.get("who") if PASSWORD else None) or users.OWNER_KEY
    if who == users.OWNER_KEY:
        return users.OWNER_KEY, users.owner_display(), "owner"
    m = users.member(who) or {}
    return who, m.get("display") or who, "member"


def _by():
    """The `By` label for a change: the signed-in person's display name — but only
    once named members exist (users.json). Single-password mode writes exactly what
    it always wrote, which is the spec's back-compat promise."""
    return _me()[1] if users.exists() else ""


def _owner_only():
    if _me()[2] != "owner":
        abort(403)


def _may_replace_collection():
    if _me()[2] == "owner":
        return True
    data = users.load() or {}
    return bool(data.get("members_can_upload"))


def _note(action, deck="", detail=""):
    """Queue one activity-log row for this request; written after a successful
    response (see _write_activity), so a refused write logs nothing."""
    g.setdefault("activity", []).append((action, deck, detail))


def _activity_path():
    return os.path.join(os.path.dirname(os.path.abspath(DECKS_DIR)), "activity.csv")


@app.after_request
def _write_activity(resp):
    """`data/activity.csv` (When,By,Action,Deck,Detail): deck-level actions, labelled.
    Only with named members (users.json) — and sign-ins are never logged. The sync
    commits it so a Claude session can read who changed what."""
    rows = g.pop("activity", None)
    if not rows or resp.status_code >= 400 or not users.exists():
        return resp
    try:
        import csv as _csv
        from datetime import datetime, timezone
        path = _activity_path()
        new = not os.path.exists(path)
        when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        with open(path, "a", encoding="utf-8", newline="") as f:
            w = _csv.writer(f)
            if new:
                w.writerow(["When", "By", "Action", "Deck", "Detail"])
            for action, deck, detail in rows:
                w.writerow([when, _by(), action, deck,
                            re.sub(r"[\x00-\x1f\x7f]", " ", str(detail))[:200]])
    except OSError:
        pass                      # a full disk must not fail the edit it describes
    return resp


@app.context_processor
def _auth_flags():
    key, display, role = _me()
    return {"auth_enabled": bool(PASSWORD), "me_name": display, "me_role": role,
            "named_users": users.exists()}


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


@app.errorhandler(auto_build.UnknownIdentity)
def _unknown_identity(e):
    """A build for a commander whose colors we cannot establish is refused, not faked.

    Every build route already accepts `?ci=` — this turns the refusal into the page
    that says so, instead of a 500 that reads like a broken app."""
    return ("<h2>Can't build this commander yet</h2>"
            f"<p>{escape(e.message).replace(chr(10), '<br>')}</p>"
            "<p>In the app, add <code>?ci=RW</code> (the commander's color identity) "
            "to this URL to build immediately.</p>"), 409


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _hdr(text, key, default=""):
    m = re.match(r"(.+)", mtglib.deck_header(text, key))
    return m.group(1).strip() if m else default


# A deck stem is a FILE NAME, never a path (W1). `<stem>` in a route accepts any
# character but '/', and on Windows a backslash IS a separator: a stem of
# `..\..\collection\owned_additions` resolved outside data/decks/ and the Delete
# route removed it. The allow-list is what _deck_slug and every committed deck
# already produce.
_STEM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")

# A real deck line holds at most ~99 copies (a basics line in a 100-card deck).
# Engines expand quantities card by card — goldfish builds a library list, the
# dashboard renders a figure per copy — so a typo'd `10000 Swamp` took 12 s to
# render and a 20-digit quantity exhausted memory (W11). Above this bound the app
# refuses to analyse the deck and names the line to fix.
MAX_DECK_QTY = 500


def _deck_path(stem):
    """`DECKS_DIR/<stem>.txt` if `stem` is a plain deck name that resolves inside
    DECKS_DIR, else None. The realpath check is the second lock: it also refuses a
    symlink planted in data/decks/ that points elsewhere."""
    if not isinstance(stem, str) or not _STEM_RE.match(stem) or ".." in stem:
        return None
    path = os.path.join(DECKS_DIR, f"{stem}.txt")
    base = os.path.realpath(DECKS_DIR)
    real = os.path.realpath(path)
    try:
        if os.path.commonpath([base, real]) != base or os.path.dirname(real) != base:
            return None
    except ValueError:            # different drives on Windows
        return None
    return path


def _absurd_quantities(text):
    """[(line number, qty text, card)] for every card line above MAX_DECK_QTY."""
    bad = []
    for i, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = mtglib._QTY_RE.match(s)
        if m and int(m.group(1)) > MAX_DECK_QTY:
            bad.append((i, m.group(1), m.group(2)))
    return bad


def _qty_message(bad):
    i, q, name = bad[0]
    q_show = q if len(q) <= 12 else q[:12] + "…"
    more = len(bad) - 1
    return (f"Line {i} reads “{q_show} {name}” — more than {MAX_DECK_QTY} copies "
            "of one card isn't a deck, so it was not analysed"
            + (f" ({more} more line(s) like it)" if more else "")
            + ". Fix the quantity in the deck editor.")


def _analysable_deck(stem, api=False):
    """deck_meta for a route that ANALYSES the deck: 404 when missing, and a
    readable 422 refusal (never a hang or an OOM) when a quantity is absurd. The
    editor, delete, bracket and pin routes use plain deck_meta, so the player can
    always reach the bad line and fix it."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    if m["absurd_qty"]:
        msg = _qty_message(m["absurd_qty"])
        if api:
            abort(Response(json.dumps({"ok": False, "error": msg}), status=422,
                           mimetype="application/json"))
        edit = url_for("deck_edit", stem=stem)
        abort(Response(f"<h2>This deck needs a fix</h2><p>{escape(msg)}</p>"
                       f'<p><a href="{edit}">Open the editor</a></p>',
                       status=422, mimetype="text/html"))
    return m


def deck_meta(stem):
    path = _deck_path(stem)
    if path is None or not os.path.exists(path):
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
        "absurd_qty": _absurd_quantities(text),
    }


def list_decks():
    stems = sorted(os.path.splitext(os.path.basename(p))[0]
                   for p in _glob_txt(DECKS_DIR))
    # A file whose name isn't a valid stem can't be opened by any route (W1), so it
    # isn't listed either — a row whose every link 404s helps nobody.
    return [m for m in (deck_meta(s) for s in stems) if m]


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
# Display order for a colour identity — WUBRG, the order every MTG product prints.
_WUBRG = "WUBRG"


def _deck_pips(meta, idx):
    """The deck's colours, WUBRG-ordered, for its card stripe and pips: the
    `# Colors:` header (the same `_deck_identity` read the add-card check uses), else
    the commander card's identity from the collection. Empty when neither is known —
    the card then shows no pips rather than guessing colourless."""
    letters = _deck_identity("# Colors: " + (meta.get("colors") or ""))
    if not letters and meta.get("commander"):
        card = mtglib.lookup(idx, meta["commander"])
        letters = set(getattr(card, "identity", None) or ()) if card else set()
    return [c for c in _WUBRG if c in letters]


def _role_meters(rep, archetype):
    """Lands / Ramp / Removal / Draw against THIS deck's template band
    (deckcore.role_ranges, widened by its `# Archetype:` words) — the same judgment
    the optimizer and the dashboard use, so the home page cannot disagree with them.
    Each row carries the status word as well as the colour."""
    if not rep:
        return []
    ranges = dict(deckcore.role_ranges(deckcore.archetype_words(archetype or "")),
                  lands=deckcore.LAND_RANGE)
    cats = rep.get("categories") or {}
    out = []
    for key, label in (("lands", "Lands"), ("ramp", "Ramp"),
                       ("removal", "Removal"), ("draw", "Draw")):
        n = rep.get("lands", 0) if key == "lands" else cats.get(key, 0)
        lo, hi = ranges[key]
        st = "short" if n < lo else ("over" if n > hi else "in")
        word = {"short": f"{lo - n} short", "over": f"{n - hi} over", "in": "in range"}[st]
        out.append({"label": label, "n": n, "lo": lo, "hi": hi, "status": st, "word": word})
    return out


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
        qty_error = _qty_message(m["absurd_qty"]) if m["absurd_qty"] else None
        res, rep = None, None
        if not qty_error:                 # an absurd quantity is never simulated
            try:
                # COLLECTION rides along so the CRISPI speed axis gets its combat
                # clock (goldfish, disk-cached); without it every leaderboard row
                # would silently read "unmeasured" — found in the Phase A revalidation.
                res, rep = power.build_for_deck(m["path"], idx, collection_path=COLLECTION,
                                                with_report=True)
            except Exception:
                res, rep = None, None
        try:
            deck = mtglib.parse_deck(open(m["path"], encoding="utf-8").read())
            total = sum(c.quantity for c in deck)
            # Basics are always owned, in unlimited quantity (grounding rule #9,
            # mtglib.is_basic) — the export deliberately omits them, so a lookup
            # miss on a Forest is an artifact, not a card to buy (W8).
            to_buy = sum(1 for c in deck if mtglib.lookup(idx, c.name) is None
                         and not mtglib.is_basic(c.name))
        except Exception:
            total, to_buy = None, 0
        label = deck_conflicts.deck_label(m["path"])
        rows.append({**m, "assess": res, "total": total, "to_buy": to_buy,
                     "contested": short_by_deck.get(label, 0), "qty_error": qty_error,
                     "roles": _role_meters(rep, m.get("archetype")),
                     "identity": _deck_pips(m, idx),
                     "study": deck_conflicts.is_study_deck(m["path"])})
    # Phase D: the 0-100 composite is gone, so the leaderboard sorts on shipped
    # axes — bracket, then how fast the deck actually wins, then interaction.
    # Explainable in one sentence, which the composite never was.
    rows.sort(key=lambda r: power.rank_key_for(r["assess"]))
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
    m = _analysable_deck(stem)
    res = bd.generate(m["path"], COLLECTION, title=m["title"],
                      commander=m["commander"], theme=m["theme"], decks_dir=DECKS_DIR,
                      editable=True, narration_url=url_for("narration_file", stem=stem,
                                                           name="x")[:-1])
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
    m = _analysable_deck(stem)
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
        bad = _absurd_quantities(text)
        if bad:
            # Refuse the save but keep what the player typed in the box, so the
            # fix is one edit away rather than a retype (W11).
            flash(_qty_message(bad).replace("so it was not analysed",
                                            "so nothing was saved"), "warn")
            return render_template("edit.html", meta=m, content=text,
                                   page="decks"), 400
        old_text = open(m["path"], encoding="utf-8").read()
        with open(m["path"], "w", encoding="utf-8", newline="\n") as f:
            f.write(text.replace("\r\n", "\n"))
        n_in, n_out = _log_editor_diff(m["path"], old_text, text)
        if n_in or n_out:
            _note("edit list", stem, f"{n_in} in, {n_out} out")
        _invalidate(stem)
        return redirect(url_for("deck", stem=stem))
    content = open(m["path"], encoding="utf-8").read()
    return render_template("edit.html", meta=m, content=content, page="decks")


def _log_editor_diff(deck_path, old_text, new_text):
    """Log what a full-text editor save changed, as the player's own picks.

    The editor used to record nothing, so a card typed in there had none of the
    protection a card-panel Add gets — the optimizer could cut it on the next ⚡.
    Each card that appeared is a `manual-add`, each that left a `manual-remove`
    (docs/spec-second-login.md §4). Basics are quantities, never decisions."""
    from datetime import date

    def cards(text):
        out = {}
        for c in mtglib.parse_deck(text):
            if not mtglib.is_basic(c.name):
                out.setdefault(mtglib._norm(mtglib.front_face(c.name)), c.name)
        return out
    before, after = cards(old_text), cards(new_text.replace("\r\n", "\n"))
    today = date.today().isoformat()
    rows = [(after[k], today, "", "manual-add") for k in after if k not in before]
    rows += [("", today, before[k], "manual-remove") for k in before if k not in after]
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    deckcore.append_changes(f"{stem}.changes.csv", rows, by=_by())
    return (sum(1 for k in after if k not in before), sum(1 for k in before if k not in after))


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


def _section_of_card(lines, keys):
    """The section label the matching card line currently sits under, or None."""
    cur = None
    for ln in lines:
        label = _section_label(ln)
        if label:
            cur = label
            continue
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        m = mtglib._QTY_RE.match(s)
        if mtglib.name_keys(m.group(2) if m else s) & keys:
            return cur
    return None


def _edit_deck_card(path, action, name, replacement=None, section=None, types=None):
    """Line-based edit of a deck .txt: remove, replace, or add a single card, preserving
    section, comments and everything else. Each action moves exactly ONE copy: a
    multi-copy line is decremented, and a replacement always arrives as `1 <card>`.
    Returns True if a line changed.

    `types` (the REPLACEMENT card's type list, when the caller knows it) lets a
    replace re-file: writing the incoming card at the outgoing card's line put a
    Sorcery under Creatures whenever the types differed — one of the three writers
    behind the 19 misfiled cards found on 2026-08-20 (Grim Tutor under Creatures
    was this exact flow). Unknown types (None or empty) keep the old in-place
    behavior: never guess a section from a name."""
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
        #
        # Only when the outgoing card was actually found (W6): inserting
        # unconditionally turned a stale panel click into a 101st card while the
        # route reported "nothing was changed".
        dropped = _edit_deck_card(path, "remove", name)
        if dropped:
            lines = open(path, encoding="utf-8").read().split("\n")
            _insert_deck_card(path, lines, replacement, section="Basics")
        return dropped
    if action == "replace" and replacement and types:
        target = deckcore.type_bucket(replacement, types)
        cur = _section_of_card(lines, keys)
        # Re-file only when BOTH sections speak type: the outgoing card sits under a
        # canonical type section and the incoming card's type names a different one.
        # A custom section ("Combo Pieces") keeps the player's own grouping.
        if (target and cur and cur in deckcore.TYPE_SECTION_ORDER
                and cur != target):
            dropped = _edit_deck_card(path, "remove", name)
            if dropped:
                lines = open(path, encoding="utf-8").read().split("\n")
                _insert_deck_card(path, lines, replacement, section=target)
            return dropped
    out, changed = [], False
    for ln in lines:
        s = ln.strip()
        if not changed and s and not s.startswith("#"):
            m = mtglib._QTY_RE.match(s)   # shared parser — '1x Name' must not no-op
            cardname = m.group(2) if m else s
            qty = int(m.group(1)) if m else 1
            # name_keys, not raw _norm: the panel's data-key can carry EITHER form of
            # a DFC name (decklist figures key the deck file's form, EDHREC/field rows
            # key what the snapshot emits — often the front face alone), so an exact
            # compare silently no-ops on "Smaug, the Great Calamity // Spew Flame" vs
            # "Smaug, the Great Calamity". The route's own singleton guard already
            # matches both keys; the editor must agree with it.
            if mtglib.name_keys(cardname) & keys:
                # Remove and Replace act on ONE copy (W2). A multi-copy line — a
                # basics line above all — is decremented in place, never dropped:
                # Remove on `21 Swamp` used to delete all 21, and Replace wrote the
                # outgoing quantity onto the incoming card (`21 Unknown Card`).
                indent = ln[:len(ln) - len(ln.lstrip())]
                if action == "remove":
                    changed = True
                    if qty > 1:
                        out.append(f"{indent}{qty - 1} {cardname}")
                    continue
                if action == "replace" and replacement:
                    if qty > 1:
                        out.append(f"{indent}{qty - 1} {cardname}")
                    out.append(f"{indent}1 {replacement}")
                    changed = True
                    continue
        out.append(ln)
    if changed:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(out))
    return changed


def _unsafe_line_value(*values):
    """True when any value would break out of the ONE line it is written to (W9).

    Deck files, owned_additions.txt and pins.csv are line-oriented, so a name
    carrying `\\n` became extra lines: `Fake Card\\n99 Mana Crypt` in the collection
    form recorded 99 Mana Crypts, and the same trick in Replace slipped a second
    copy past the singleton guard. Any C0 control character (or DEL) is refused —
    no real card name has one."""
    return any(v and any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in v)
               for v in values)


_LINE_VALUE_ERROR = ("A card name can't contain a line break or other control "
                     "character — nothing was changed.")


def _log_manual_change(deck_path, card, replaced="", source="manual-add"):
    """Append a player edit to `<deck>.changes.csv` — same schema the optimizer writes.

    Two things fall out of this one row: the dashboard's existing NEW badge lights up,
    and `Source` marks the card as the PLAYER's decision, which is what lets the advisor
    offer an opinion on it without the optimizer ever touching it."""
    from datetime import date
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    deckcore.append_changes(f"{stem}.changes.csv",
                            [(card, date.today().isoformat(), replaced, source)], by=_by())


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
    if card is None and mtglib.is_basic(name):
        # Basics are always owned, in unlimited quantity (grounding rule #9): the
        # export deliberately omits them, so a lookup miss is not "you don't own
        # a Swamp" (W8). A synthesized, type-only card — no identity, so the
        # color check below never fires on it, same as an untyped snapshot row.
        card = mtglib.Card(name=" ".join(name.split()).title(), quantity=0,
                           types=["Land"], supertypes=["Basic"])
    if card is None:
        return None, (f"You don't own a card called “{name}”. Add it to the "
                      "collection first (or check the spelling)."), None
    text = open(meta["path"], encoding="utf-8").read()
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
        pins_ = deckcore.load_pins()      # canonical keys; probe both spellings
        owner = next((pins_[x] for x in mtglib.name_keys(card.name) if x in pins_), None)
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
    if _unsafe_line_value(name, replacement):
        return _LINE_VALUE_ERROR, 400
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
        # The incoming card's types, when the collection knows them, let the editor
        # re-file instead of inheriting the outgoing card's section (see
        # _edit_deck_card). An unknown card passes None — in place, never guessed.
        rtypes = None
        if action == "replace" and replacement:
            _coll, idx = collection_index()
            ref = mtglib.lookup(idx, replacement)
            rtypes = ref.types if (ref and ref.types) else None
        changed = _edit_deck_card(m["path"], action, name, replacement, types=rtypes)
        if not changed:
            return (f"Couldn't find “{name}” in the deck file — nothing was "
                    "changed. (If this card is a buy-list or field suggestion, "
                    "it isn't in the 99 to begin with.)", 404)
        if changed:
            if action == "replace" and replacement:
                _log_manual_change(m["path"], replacement, replaced=name,
                                   source="manual-replace")
                _note("replace card", stem, f"{name} -> {replacement}")
            elif action == "remove":
                # A bare Remove is as much a player decision as a Replace, and the
                # never-re-add rule reads the LOG — unlogged, the optimizer could
                # re-propose the exact card through this button (the Hojo
                # mechanism through the other flow). Card column stays empty:
                # nothing came in, and load_changes skips empty-Card rows so the
                # NEW badge and manual-adds advisory are untouched.
                _log_manual_change(m["path"], "", replaced=name,
                                   source="manual-remove")
                _note("remove card", stem, name)
            _invalidate(stem)
    return redirect(url_for("deck", stem=stem))


@app.route("/deck/<stem>/add", methods=["POST"])
def deck_add(stem):
    """Add an owned card to a deck and hand back an opinion on how it fits.

    JSON rather than a redirect so the picker can show the verdict at the moment it's
    actionable — and so a rejection explains itself instead of silently doing nothing."""
    m = _analysable_deck(stem, api=True)
    name = request.form.get("name", "").strip()
    section = (request.form.get("section") or "").strip() or None
    if not name:
        return jsonify({"ok": False, "error": "No card name given."}), 400
    if _unsafe_line_value(name, section):
        return jsonify({"ok": False, "error": _LINE_VALUE_ERROR}), 400
    coll, idx = collection_index()      # ONE load for validate + advise
    card, err, warn = _validate_add(m, stem, name, idx=idx)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    _edit_deck_card(m["path"], "add", card.name, section=section)
    _log_manual_change(m["path"], card.name, source="manual-add")
    _note("add card", stem, card.name)
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
    m = _analysable_deck(stem, api=True)
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


@app.route("/export/additions.txt")
def export_additions():
    """Every card added by hand that the player's collection site doesn't have yet,
    as `qty name` lines to import there (Archidekt, ManaPool). The next full export
    then carries them, and the Upload's reconcile offer retires the rows."""
    from datetime import date
    text = ex.additions_text(ADDITIONS)
    return _txt(text, f"added-cards-{date.today().isoformat()}.txt")


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
    m = _analysable_deck(stem)
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
    m = _analysable_deck(stem)
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
    deck_cards = a["deck"]          # captured now: `a` is reused as a loop name below
    assessment, mana, combos = a["assessment"], a["mana"], a["combos"]

    L = [f"=== ASSESSMENT PACKET — {m['title']} ===",
         f"Commander: {m['commander']}",
         "For grounding an mtg-deckbuilder coaching session (see the skill's references/coaching.md).",
         "Paste this whole block and say: \"coach this deck\".", ""]
    if assessment:
        sig = assessment["signals"]
        L.append("-- POWER & BRACKET --")
        L.append(f"Bracket {assessment['bracket']} ({assessment['bracket_name']})")
        for nm, k in (("Speed", "speed"), ("Resilience", "resilience"),
                      ("Consistency", "consistency")):
            ax = assessment.get(k)
            if ax:
                L.append(f"  {nm}: {ax['label']} — {ax['detail']}")
        L.append(f"  Interaction: {sig['interaction']} (cEDH band 12-18)")
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
                                merged_combos, missing, idx, deck=deck_cards)
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
    if _unsafe_line_value(name):
        return _LINE_VALUE_ERROR, 400
    if name:
        pins = deckcore.load_pins()
        key = deckcore.pin_key(name)          # canonical, so every engine sees it
        if request.form.get("action") == "unpin":
            pins.pop(key, None)
            _note("unpin", stem, name)
        else:
            pins[key] = stem                      # pinning elsewhere MOVES the pin
            _note("pin", stem, name)
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
        _note("set bracket", stem, raw)
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
    # The card panel posts json=1 and stays on the page. It must NOT get a flash: the
    # message would sit in the session and pop as a stale toast on whatever full page the
    # player loads next, describing a pin they changed minutes ago somewhere else.
    wants_json = bool(request.form.get("json"))
    if _unsafe_line_value(key, target):
        if wants_json:
            return jsonify({"ok": False, "error": _LINE_VALUE_ERROR}), 400
        return _LINE_VALUE_ERROR, 400
    k = deckcore.pin_key(key)             # canonical, so every engine sees it
    pins = deckcore.load_pins() if key else {}
    if key:
        if target in ("", "none"):
            pins.pop(k, None)
            _note("release pin", "", key)
            if not wants_json:
                flash(f"Released the pin on {key} — every deck can use that copy again.",
                      "info")
        else:
            pins[k] = target                    # one deck per card: this MOVES it
            _note("move pin", target, key)
            if not wants_json:
                flash(f"{key} is now reserved for {target}.", "info")
        deckcore.save_pins(pins)
    if wants_json:
        # Echo what was actually STORED, so the panel re-renders from the server's truth
        # rather than from what it optimistically hoped it wrote.
        return jsonify({"ok": True, "pinned": pins.get(k)})
    return redirect(url_for("pins_page"))


@app.route("/deck/<stem>/delete", methods=["POST"])
def deck_delete(stem):
    """Delete a deck and its companion files. Git keeps the history, so this is
    recoverable — but it is still destructive, hence POST + a confirm in the UI."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    base = os.path.splitext(m["path"])[0]
    for suffix in (".txt", ".notes.md", ".buylist.csv", ".attrs.csv", ".changes.csv",
                   ".clips.json"):
        try:
            os.remove(base + suffix)
        except OSError:
            pass
    # drop any pins that pointed at it, so those copies free up again
    pins = deckcore.load_pins()
    left = {c: d for c, d in pins.items() if d != stem}
    if len(left) != len(pins):
        deckcore.save_pins(left)
    _note("delete deck", stem, m["title"])
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
    m = _analysable_deck(stem)
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
    m = _analysable_deck(stem)
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
    m = _analysable_deck(stem)
    return render_template("mulligan.html", meta=m, page="decks")


@app.route("/api/deck/<stem>/hand")
def api_deck_hand(stem):
    """One seeded opening hand plus the sim's verdict and its reasoning.

    Seeded by an explicit `seed` so a hand is reproducible (and so a test can pin
    one); the page draws a fresh seed per hand."""
    m = _analysable_deck(stem, api=True)
    try:
        seed = int(request.args.get("seed") or 0)
    except ValueError:
        seed = 0
    try:
        # Parsed inside the try (W11): `?mulls=abc` used to raise straight into a
        # 500 page, which the trainer's fetch() can't read as JSON.
        mulls = max(0, min(goldfish.MULL_FLOOR, int(request.args.get("mulls") or 0)))
    except ValueError:
        return jsonify({"error": "mulls must be a whole number"}), 400
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
    m = _analysable_deck(stem, api=True)
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
    m = _analysable_deck(stem)
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


def _free_deck_stem(slug):
    """(`stem`, path) for a NEW deck: `slug`, else `slug-2`, `slug-3`, … (W3).

    Build Next's Save used to write straight to `<slug>.txt`, so saving a draft for
    a commander you had already built replaced the hand-tuned list — and left that
    deck's notes, changes log and buylist attached to the stranger. A stem is free
    only when NO companion file exists either: an orphaned `.notes.md` would
    otherwise attach itself to the new list the same way."""
    companions = (".txt", ".notes.md", ".buylist.csv", ".attrs.csv", ".changes.csv",
                  ".clips.json")
    n = 1
    while True:
        stem = slug if n == 1 else f"{slug}-{n}"
        base = os.path.join(DECKS_DIR, stem)
        if not any(os.path.exists(base + sfx) for sfx in companions):
            return stem, base + ".txt"
        n += 1


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
    """Write the auto-built draft to data/decks/ as a NEW deck (`<slug>`, or
    `<slug>-2`, `-3`, … when that name is taken — an existing deck is never
    overwritten), then tune it against what the field actually plays so it lands
    optimized. (Manual edits are deliberately left alone — see
    /deck/<stem>/optimize.)"""
    coll, idx = collection_index()
    d = auto_build.build(commander, coll, idx, DECKS_DIR, identity=(request.form.get("ci") or None),
                         skip_deck=_deck_slug(commander))
    stem, path = _free_deck_stem(_deck_slug(commander))
    # "x" (exclusive create), not "w": a deck saved between the free-name check
    # and here is never clobbered either.
    with open(path, "x", encoding="utf-8", newline="\n") as f:
        f.write(auto_build.deck_text(d))
    _note("new deck (Build Next)", stem, commander)
    if stem != _deck_slug(commander):
        flash(f"You already have a “{_deck_slug(commander)}” deck, so this draft was "
              f"saved alongside it as “{stem}” — nothing was overwritten.", "info")
    try:
        r = optimize.optimize(path, coll, idx, DECKS_DIR, apply=True, by=_by())
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
    # Mirror the CLI's deadlock honesty (invariant 10: every surface). "No changes"
    # because the role-band gate froze candidates is NOT alignment, and the ⚡ button
    # is where the player's finger actually is.
    blocked = (r.get("role_deadlock") or {}).get("blocked") or []
    if n:
        flash(f"Optimizer: {n} change(s) applied.", "info")
    elif blocked:
        parts = ", ".join(f"{len(b['adds'])} by the {b['role']} band" for b in blocked)
        flash(f"Optimizer: no changes — candidates blocked: {parts}. That role's count "
              "sits outside the deck's template, which freezes swaps touching it.",
              "info")
    else:
        flash("Optimizer: already aligned with the field — no changes.", "info")
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
    m = _analysable_deck(stem)
    coll, idx = collection_index()
    try:
        r = optimize.optimize(m["path"], coll, idx, DECKS_DIR, apply=True, by=_by())
        _note("optimize", stem, f"{len(r.get('swaps') or []) + len(r.get('land_swaps') or [])} change(s)")
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
    # owned_additions.txt holds hundreds of rows after a big pickup: summarise it
    # (row count + the latest dated batch) instead of printing every line.
    additions = {"rows": 0, "copies": 0, "latest": ""}
    if os.path.exists(ADDITIONS):
        adds_text = open(ADDITIONS, encoding="utf-8").read()
        rows = intake.addition_rows(adds_text)
        additions["rows"] = len(rows)
        additions["copies"] = sum(r["qty"] for r in rows)
        heads = [ln.strip()[1:].strip(" -") for ln in adds_text.splitlines()
                 if intake.BATCH_RE.match(ln.strip())]
        additions["latest"] = heads[-1] if heads else ""
    reconcile = (_read_json(_reconcile_path()) or {}).get("plan") or []
    try:
        arrivals = deckcore.new_arrivals(coll, DECKS_DIR, limit=10_000)
    except Exception:
        arrivals = []
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
                           reconcile=reconcile, arrivals=arrivals,
                           carddb=carddb, cards=cards, types=types,
                           enrich_status=enrich_bg.status_view(), page="collection")


@app.route("/collection/add", methods=["POST"])
def collection_add():
    name = request.form.get("name", "").strip()
    qty = request.form.get("qty", "1").strip() or "1"
    if _unsafe_line_value(name):
        flash(_LINE_VALUE_ERROR, "warn")
        return redirect(url_for("collection_view"))
    # Digits only, 1..99 (W9): `-5` and `lots` were written verbatim, and the
    # parser read `lots Arcane Signet` as a phantom card named exactly that.
    if not (qty.isascii() and qty.isdigit() and 1 <= int(qty) <= 99):
        flash(f"Quantity must be a whole number from 1 to 99 (got “{qty[:20]}”) — "
              "nothing was added.", "warn")
        return redirect(url_for("collection_view"))
    qty = str(int(qty))
    if name:
        header_needed = not os.path.exists(ADDITIONS)
        with open(ADDITIONS, "a", encoding="utf-8") as f:
            if header_needed:
                f.write("# Player-confirmed ownership not in the export yet.\n")
            f.write(f"{qty} {name}\n")
        _note("add to collection", "", f"{qty} {name}")
        _invalidate()             # owned_additions feeds EVERY deck's analysis
    return redirect(url_for("collection_view"))


@app.route("/collection/upload", methods=["POST"])
def collection_upload():
    """Replace the whole collection with a full export — behind the Upload guard.

    The file is validated into a PENDING copy first (`_install_upload` into a
    gitignored `*.private.csv`), then compared with the current collection. A file
    that looks like a handful of new cards rather than a full export stops here and
    asks (docs/spec-card-intake.md §3): Upload used to swap a 214-card batch in for a
    3,209-card collection with no question, and every deck then read as unowned.
    A normal full export goes straight through, as before.

    Enrichment still runs in the BACKGROUND (minutes of Scryfall round-trips), and
    the upload still writes only the PRIVATE, gitignored CSV — never the tracked
    name-only snapshot (that separation closed a real leak — see CLAUDE.md)."""
    if not _may_replace_collection():
        abort(403)
    f = request.files.get("csv")
    if not (f and f.filename):
        return redirect(url_for("collection_view"))
    pending = _pending_upload_path()
    err = _install_upload(f, pending)
    _drop(_upload_backup_path(pending))   # a backup of a pending file is noise
    if err:
        _drop(pending)
        flash(f"Upload refused — {err} Your previous collection is unchanged.", "warn")
        return redirect(url_for("collection_view"))
    with open(pending, encoding="utf-8") as fh:
        new_cards = mtglib.parse_collection(fh.read())
    current = _raw_collection_cards()
    # Judged against the collection the player SEES (export + added batches), so the
    # question quotes the same card count as the Collection page.
    partial, facts = intake.upload_looks_partial(collection_index()[0], new_cards)
    if partial:
        return render_template("upload_guard.html", facts=facts, page="collection")
    return _replace_collection_from(pending, current)


@app.route("/collection/upload/decide", methods=["POST"])
def collection_upload_decide():
    """The guard's second tap. "batch" (the default) sends the SAME file to the
    batch preview and leaves the collection CSV untouched; "replace" goes ahead."""
    if not _may_replace_collection():
        abort(403)
    pending = _pending_upload_path()
    if not os.path.exists(pending):
        flash("That upload has expired — choose the file again.", "warn")
        return redirect(url_for("collection_view"))
    if request.form.get("choice") == "replace":
        return _replace_collection_from(pending, _raw_collection_cards())
    with open(pending, encoding="utf-8") as fh:
        text = fh.read()
    _drop(pending)                # it may carry prices; the batch keeps names only
    return _batch_preview(text, source="uploaded file")


def _replace_collection_from(pending, previous_cards):
    """Move a validated pending export into place (previous file kept as the
    gitignored backup), offer to retire batch rows it now carries, and start
    background enrichment."""
    global COLLECTION
    os.makedirs(os.path.dirname(COLLECTION_CSV) or ".", exist_ok=True)
    if os.path.exists(COLLECTION_CSV):
        shutil.copy2(COLLECTION_CSV, _upload_backup_path(COLLECTION_CSV))
    os.replace(pending, COLLECTION_CSV)
    COLLECTION = COLLECTION_CSV
    _note("replace collection")
    _invalidate()                 # a whole new collection — nothing cached survives
    try:
        with open(COLLECTION_CSV, encoding="utf-8") as fh:
            new_cards = mtglib.parse_collection(fh.read())
        adds = open(ADDITIONS, encoding="utf-8").read() if os.path.exists(ADDITIONS) else ""
        plan = intake.reconcile_plan(previous_cards, new_cards, adds)
    except Exception:
        plan = []
    if plan:
        _write_json(_reconcile_path(), {"plan": plan, "when": time.time()})
    else:
        _drop(_reconcile_path())
    flash(enrich_bg.start(COLLECTION_CSV, COLLECTION_ATTRS), "info")
    return redirect(url_for("collection_view"))


@app.route("/collection/reconcile", methods=["POST"])
def collection_reconcile():
    """One tap retires the batch rows the new export carries (commented out with
    the date, never deleted); "keep" dismisses the offer and changes nothing."""
    if not _may_replace_collection():
        abort(403)
    data = _read_json(_reconcile_path()) or {}
    plan = data.get("plan") or []
    _drop(_reconcile_path())
    if request.form.get("action") != "retire" or not plan:
        flash("Kept every added card as it was.", "info")
        return redirect(url_for("collection_view"))
    if not os.path.exists(ADDITIONS):
        return redirect(url_for("collection_view"))
    retired, skipped = intake.apply_retire(ADDITIONS, plan)
    _note("retire batch rows", "", f"{retired} cop(ies) now in the export")
    _invalidate()
    msg = f"Retired {retired} card(s) now carried by your export — nothing counts twice."
    if skipped:
        msg += (f" {skipped} row(s) were left alone because the file changed since "
                "the upload.")
    flash(msg, "info")
    return redirect(url_for("collection_view"))


# ---- batch entry (paste → preview → confirm → write) -------------------------
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_PASTE_BYTES = 2 * 1024 * 1024


def _intake_dir():
    """Where previews and the reconcile offer wait for their confirm tap: the
    gitignored `data/cache/intake/`, derived from the collection CSV's folder so a
    test's tmp collection keeps them in tmp too."""
    return os.path.join(os.path.dirname(os.path.dirname(COLLECTION_CSV)), "cache", "intake")


def _pending_upload_path():
    # `*.private.csv` is gitignored: a pending upload is a priced export.
    return os.path.join(os.path.dirname(COLLECTION_CSV), "pending-upload.private.csv")


def _reconcile_path():
    return os.path.join(_intake_dir(), "reconcile.json")


def _drop(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save_preview(kind, payload):
    """Park a preview server-side and hand back a token, so the confirm writes
    EXACTLY what was previewed — never a re-parse, never a tampered form."""
    import secrets
    d = _intake_dir()
    os.makedirs(d, exist_ok=True)
    now = time.time()
    for name in os.listdir(d):            # previews older than a day are abandoned
        p = os.path.join(d, name)
        if name.startswith(("batch-", "deck-")) and now - os.path.getmtime(p) > 86400:
            _drop(p)
    token = secrets.token_urlsafe(12)
    _write_json(os.path.join(d, f"{kind}-{token}.json"), payload)
    return token


def _load_preview(kind, token):
    if not _TOKEN_RE.match(token or ""):
        return None, None
    path = os.path.join(_intake_dir(), f"{kind}-{token}.json")
    return _read_json(path), path


def _raw_collection_cards():
    """The base collection file as parsed, WITHOUT owned_additions — the
    "previous export" the reconcile compares a new one against."""
    try:
        with open(COLLECTION, encoding="utf-8") as fh:
            return mtglib.parse_collection(fh.read())
    except (OSError, UnicodeDecodeError):
        return []


def _verify_names(names):
    """THE network call of card intake (Scryfall: exact batch, then fuzzy). Its own
    function so tests stand in front of it."""
    import carddb
    return carddb.verify_cards(names)


def _known_names(coll):
    """Names the app already trusts, for resolving offline: the collection plus
    the committed attrs snapshot's canonical names."""
    extra = []
    snap = os.path.join(ROOT, "data/collection/collection_attrs.snapshot.csv")
    try:
        import csv as _csv
        with open(snap, encoding="utf-8") as f:
            extra = [r.get("Name", "") for r in _csv.DictReader(f)]
    except OSError:
        pass
    return intake.known_names(coll, extra)


def _read_paste():
    """The pasted text, or an attached .txt/.csv (UTF-8, else Windows-1252)."""
    text = request.form.get("text", "") or ""
    f = request.files.get("file")
    if f and f.filename:
        raw = f.read(MAX_PASTE_BYTES + 1)
        if len(raw) > MAX_PASTE_BYTES or b"\x00" in raw:
            return None, "that file is too large or isn't text."
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = raw.decode("cp1252")
            except UnicodeDecodeError:
                return None, "that file isn't readable text."
    if len(text.encode("utf-8")) > MAX_PASTE_BYTES:
        return None, "that list is too long for one batch."
    return text, None


def _batch_preview(text, source="pasted list"):
    rows = intake.parse_text(text)
    if not rows:
        flash("No card lines found — paste one card per line, like “1 Sol Ring”.", "warn")
        return redirect(url_for("collection_view"))
    coll, _idx = collection_index()
    entries = intake.resolve(rows, verify=_verify_names, known=_known_names(coll))
    token = _save_preview("batch", {"entries": entries, "source": source})
    return render_template("batch_preview.html", entries=entries, token=token,
                           s=intake.summary(entries), source=source,
                           page="collection")


@app.route("/collection/batch", methods=["POST"])
def collection_batch():
    """Step 1 of "Add a batch": parse + resolve and SHOW it. Writes nothing."""
    text, err = _read_paste()
    if err:
        flash(f"Nothing added — {err}", "warn")
        return redirect(url_for("collection_view"))
    return _batch_preview(text, source="uploaded file" if request.files.get("file")
                          and request.files["file"].filename else "pasted list")


@app.route("/collection/batch/confirm", methods=["POST"])
def collection_batch_confirm():
    """Step 2: write exactly the previewed ✓ rows (plus each ticked "did you mean")
    as one dated block in owned_additions.txt, then enrich in the background."""
    data, path = _load_preview("batch", request.form.get("token"))
    if not data:
        flash("That preview has expired — paste the list again.", "warn")
        return redirect(url_for("collection_view"))
    rows = intake.accepted(data["entries"], request.form.getlist("take"))
    _drop(path)
    if not rows:
        flash("Nothing to add — no line resolved to a card.", "warn")
        return redirect(url_for("collection_view"))
    label = "pasted list" if data.get("source") == "pasted list" else "uploaded file"
    copies, distinct = intake.append_batch(ADDITIONS, rows, label)
    _note("add a batch", "", f"{copies} cards ({distinct} distinct)")
    _invalidate()             # owned_additions feeds EVERY deck's analysis
    flash(f"Added {copies} card(s) ({distinct} distinct) as a dated batch. "
          + enrich_bg.start(COLLECTION, COLLECTION_ATTRS), "info")
    return redirect(url_for("collection_view") + "#arrivals")


@app.route("/collection/arrivals")
def collection_arrivals():
    """The New arrivals review: the latest batch and anything newer than 30 days,
    each card with the decks that can play it, field % and fit — a PRIOR, labelled
    as one. Its own page because scoring every arrival against every deck costs a
    few seconds the Collection page shouldn't pay on each visit."""
    coll, _idx = collection_index()
    review = deckcore.arrivals_review(coll, DECKS_DIR, COLLECTION)
    return render_template("arrivals.html", r=review, page="collection")


@app.route("/collection/arrivals.txt")
def collection_arrivals_txt():
    coll, _idx = collection_index()
    review = deckcore.arrivals_review(coll, DECKS_DIR, COLLECTION)
    return Response(deckcore.arrivals_packet(review), mimetype="text/plain")


# ---- deck import (a list the player built outside the app) -------------------
def _deck_choices():
    import glob
    out = []
    for p in sorted(glob.glob(os.path.join(DECKS_DIR, "*.txt"))):
        stem = os.path.splitext(os.path.basename(p))[0]
        m = deck_meta(stem)
        if m:
            out.append({"stem": stem, "title": m["title"]})
    return out


@app.route("/decks/import", methods=["GET"])
def deck_import():
    """Paste (or attach) a deck list: a new deck, or a new list for an existing one."""
    target = request.args.get("target", "")
    return render_template("deck_import.html", decks=_deck_choices(),
                           target=target if deck_meta(target) else "", page="home")


@app.route("/decks/import", methods=["POST"])
def deck_import_preview():
    """Parse + resolve the list and show the import report. Writes nothing."""
    text, err = _read_paste()
    if err:
        flash(f"Nothing imported — {err}", "warn")
        return redirect(url_for("deck_import"))
    target = request.form.get("target", "")
    if target and not deck_meta(target):
        abort(404)
    title = (request.form.get("title") or "").strip()[:120]
    typed_cmd = (request.form.get("commander") or "").strip()[:200]
    if _unsafe_line_value(title, typed_cmd):
        flash(_LINE_VALUE_ERROR, "warn")
        return redirect(url_for("deck_import"))
    rows = intake.parse_text(text)
    if not typed_cmd:
        typed_cmd = next((r["name"] for r in rows if r.get("commander") and not r["error"]), "")
    if not typed_cmd and target:
        typed_cmd = deck_meta(target)["commander"]
    if typed_cmd and not any(mtglib._norm(r["name"]) == mtglib._norm(typed_cmd)
                             for r in rows):
        rows.insert(0, {"line": None, "raw": typed_cmd, "qty": 1, "name": typed_cmd,
                        "section": "commander", "commander": True, "error": ""})
    if not [r for r in rows if not r["error"]]:
        flash("No card lines found — paste one card per line, like “1 Sol Ring”.", "warn")
        return redirect(url_for("deck_import", target=target))
    coll, idx = collection_index()
    entries = intake.resolve(rows, verify=_verify_names, known=_known_names(coll))
    cmd = None
    cmd_from_first = False
    if typed_cmd:
        cmd = next((e for e in entries if e["status"] == "ok"
                    and intake.same_card(typed_cmd, e["name"])), None)
    else:
        # Nothing names the commander: a list whose FIRST card is a legendary
        # creature almost always leads with it (Moxfield and EDHREC copies do).
        # Shown as "taken from the first line" on the preview, never saved silently.
        first = next((e for e in entries if e["status"] in ("ok", "basic")), None)
        tl = (first or {}).get("type_line", "").split(" // ")[0].lower()
        if first and first["status"] == "ok" and "legendary" in tl and "creature" in tl:
            cmd, cmd_from_first = first, True
            first["commander"] = True
    identity = None
    colors = ""
    if cmd:
        ident = set(re.findall(r"[WUBRG]", (cmd.get("identity") or "").upper()))
        if not ident and not cmd.get("type_line"):
            ref = mtglib.lookup(idx, cmd["name"])
            ident = set(ref.identity or ()) if ref is not None else set()
            known = ref is not None and bool(ref.types or ref.identity)
        else:
            known = True
        if known:
            identity = ident
            colors = " ".join(c for c in "WUBRG" if c in ident)
    committed = {}
    for name, u in deck_conflicts.scan(DECKS_DIR, idx, skip=target or None).items():
        for k in mtglib.name_keys(name):
            committed[k] = dict(u["decks"])
    report = intake.deck_report(entries, cmd["name"] if cmd else "", idx,
                                identity=identity, committed=committed)
    # A deck you already have for this commander: importing it as NEW would make
    # every card read as "shared with" the old copy of itself. Offer the replace.
    same_cmd = []
    if cmd and not target:
        same_cmd = [d for d in _deck_choices()
                    if intake.same_card(deck_meta(d["stem"])["commander"] or "-", cmd["name"])]
    token = _save_preview("deck", {"entries": entries, "commander": cmd["name"] if cmd else "",
                                   "typed_commander": typed_cmd, "title": title,
                                   "target": target, "colors": colors,
                                   "same_cmd": [d["stem"] for d in same_cmd]})
    return render_template("deck_import_preview.html", entries=entries, token=token,
                           same_cmd=same_cmd, cmd_from_first=cmd_from_first,
                           cmd=cmd, typed_cmd=typed_cmd, title=title or (cmd or {}).get("name", ""),
                           target=deck_meta(target) if target else None, colors=colors,
                           r=report, s=intake.summary(entries),
                           outside=intake.OUTSIDE_DECK, page="home")


def _import_cards(entries, take):
    """[(qty, name, entry)] for the deck: every resolved card, each ticked
    suggestion, and basic lands — never a sideboard/maybeboard line."""
    take = {int(i) for i in take if str(i).isdigit()}
    rows, at = [], {}
    for i, e in enumerate(entries):
        if e.get("section") in intake.OUTSIDE_DECK:
            continue
        if e["status"] == "ok":
            name = e["name"]
        elif e["status"] == "suggest" and i in take:
            name = e["suggest"]
        elif e["status"] == "basic":
            name = e["name"].title()
        else:
            continue
        k = mtglib._norm(name)
        if k in at:
            rows[at[k]][0] += e["qty"]
        else:
            at[k] = len(rows)
            rows.append([e["qty"], name, e])
    return [tuple(r) for r in rows]


@app.route("/decks/import/confirm", methods=["POST"])
def deck_import_confirm():
    """Write the previewed list: a NEW deck (never over an existing one), or a new
    list for the chosen deck — its headers, notes and companions stay, and the
    difference is logged as the player's own adds/removals, which the optimizer
    never undoes."""
    data, path = _load_preview("deck", request.form.get("token"))
    if not data:
        flash("That preview has expired — paste the list again.", "warn")
        return redirect(url_for("deck_import"))
    commander = data.get("commander") or ""
    if not commander:
        flash("Name the commander (and check it resolves) before saving.", "warn")
        return redirect(url_for("deck_import", target=data.get("target") or ""))
    cards = _import_cards(data["entries"], request.form.getlist("take"))
    coll, idx = collection_index()
    from datetime import date
    target = data.get("target") or ""
    swap_in = request.form.get("replace_stem") or ""
    if swap_in and swap_in in (data.get("same_cmd") or []):
        target = swap_in          # "replace the list of my existing deck instead"
    if target:
        m = deck_meta(target)
        if not m:
            abort(404)
        stem, deck_path = target, m["path"]
        old = {mtglib._norm(c.name): c.name
               for c in mtglib.parse_deck(open(deck_path, encoding="utf-8").read())}
        import deck_sections
        header, _cmd, _entries = deck_sections.parse_file(deck_path)
        header = _set_header(header, "Commander", commander)
        if data.get("colors"):
            header = _set_header(header, "Colors", data["colors"])
        text = intake.deck_text(cards, commander, idx=idx, header_lines=header)
        with open(deck_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        new = {mtglib._norm(n): n for _q, n, _e in cards}
        new.setdefault(mtglib._norm(commander), commander)
        for k, n in new.items():
            if k not in old and not mtglib.is_basic(n):
                _log_manual_change(deck_path, n, source="manual-add")
        for k, n in old.items():
            if k not in new and not mtglib.is_basic(n):
                _log_manual_change(deck_path, "", replaced=n, source="manual-remove")
        _note("replace list (import)", stem,
              f"{len(set(new) - set(old))} in, {len(set(old) - set(new))} out")
        flash(f"Replaced the list of {m['title']}: {len(set(new) - set(old))} card(s) in, "
              f"{len(set(old) - set(new))} out. Those choices are yours — the optimizer "
              "won't undo them.", "info")
    else:
        title = data.get("title") or commander
        stem, deck_path = _free_deck_stem(_deck_slug(title))
        text = intake.deck_text(cards, commander, title=title, colors=data.get("colors", ""),
                                source=f"imported in the app {date.today().isoformat()} "
                                       "(the player's own list)", idx=idx)
        with open(deck_path, "x", encoding="utf-8", newline="\n") as f:
            f.write(text)
        _note("new deck (import)", stem, commander)
        flash(f"Saved “{title}” as a new deck.", "info")
    _drop(path)
    if request.form.get("add_unowned"):
        short = []
        for q, n, _e in cards:
            if mtglib.is_basic(n):
                continue
            ref = mtglib.lookup(idx, n)
            need = q - (ref.quantity if ref is not None else 0)
            if need > 0:
                short.append((need, n))
        if short:
            copies, distinct = intake.append_batch(
                ADDITIONS, short, f"cards for the imported {data.get('title') or commander} deck",
                note=("Player-confirmed at deck import (\"I own these\"): the copies the",
                      "collection lacked for a deck they built. New copies on top of the export;",
                      "a future export that carries them is offered for retirement",
                      "(docs/spec-card-intake.md §3)."))
            flash(f"Added {copies} card(s) you own to your collection as a dated batch. "
                  + enrich_bg.start(COLLECTION, COLLECTION_ATTRS), "info")
    bad = optimize.singleton_violations(deck_path)
    if bad:
        flash("!! Commander allows one copy: " + ", ".join(f"{q}x {n}" for q, n in bad)
              + " — fix it in the editor.", "warn")
    _invalidate(stem)
    return redirect(url_for("deck", stem=stem))


def _set_header(header_lines, key, value):
    """Set `# Key: value` in a deck's header block, replacing the first existing
    line for that key (same shape mtglib.deck_header reads) or appending one."""
    out, done = [], False
    for ln in header_lines:
        if not done and re.match(rf"^#[ \t]*{key}[ \t]*:", ln, re.IGNORECASE):
            out.append(f"# {key}: {value}")
            done = True
        else:
            out.append(ln)
    if not done:
        out.append(f"# {key}: {value}")
    return out


def _upload_backup_path(dest):
    """Where the previous collection goes. Named `*.private.csv` on purpose: that
    pattern is already gitignored, so the backup of a priced export can never be
    swept into a commit (a plain `collection.csv.bak` is NOT ignored)."""
    base, _ext = os.path.splitext(dest)
    return f"{base}.bak.private.csv"


def _install_upload(fileobj, dest):
    """Validate an uploaded export on a temp copy, then swap it in atomically (W7).

    The old route saved straight over the private CSV: a PNG or a cp1252 export
    replaced the collection and then 500'd every page (load_collection reads
    UTF-8), with no copy of what was there before. Now: save to a temp file in the
    SAME directory (so os.replace is atomic), decode as UTF-8 — or as cp1252,
    re-saved as UTF-8, since that is what Excel on Windows writes — parse it with
    the app's own parser, and demand at least one card. Only then is the previous
    file kept as a backup and the new one moved into place. Returns None on
    success, else a sentence saying why nothing changed."""
    d = os.path.dirname(dest) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".upload-", suffix=".tmp", dir=d)
    os.close(fd)
    try:
        fileobj.save(tmp)
        with open(tmp, "rb") as fh:
            raw = fh.read()
        if b"\x00" in raw:
            return "that file is binary, not a CSV or text export."
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("cp1252")
            except UnicodeDecodeError:
                return "the file isn't readable text (neither UTF-8 nor Windows-1252)."
            with open(tmp, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        try:
            cards = mtglib.parse_collection(text)
        except Exception:
            cards = []
        first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        if (cards and mtglib.detect_format(text) == "namelist"
                and first.count(",") >= 2 and not mtglib._QTY_RE.match(first)):
            # A CSV the parser didn't recognise falls through to the name-list
            # reader, which then takes every ROW as a card name ("a,b,c").
            return ("that CSV has no Name/Quantity header row the app recognises "
                    "(export from Archidekt or ManaPool with headers).")
        if not cards:
            return "no cards were found in that file."
        if os.path.exists(dest):
            shutil.copy2(dest, _upload_backup_path(dest))
        os.replace(tmp, dest)
        tmp = None
        return None
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


@app.route("/refresh", methods=["POST"])
def refresh():
    """Regenerate the static wishlist.md + build/ dashboards (optional convenience)."""
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts/refresh.py"),
                    "--collection", COLLECTION, "--decks-dir", DECKS_DIR],
                   cwd=ROOT, capture_output=True, text=True)
    # Back to the page the button was on — but only its PATH, through the same
    # local-only check as login's ?next= (W10): the raw Referer is whatever the
    # requesting page says it is, including another site.
    try:
        back = urlsplit(request.referrer or "").path
    except ValueError:            # e.g. a malformed IPv6 host in the header
        back = ""
    return redirect(_safe_next(back))


@app.route("/sync", methods=["POST"])
def sync_now():
    """Run the GitHub sync on demand (same script as the daily auto-sync and the
    console path). Synchronous — ~10 s — so the redirect lands with the status
    freshly written; any needed reload is deferred past the redirect."""
    sync.run("manual", reload_delay=sync.RELOAD_DELAY)
    _note("sync")
    return redirect(url_for("index") + "#maint")


# ---- people (owner only) and the labels they leave -----------------------------
@app.route("/people", methods=["GET"])
def people():
    """Add a member, reset their password, sign them out everywhere, or disable
    them — docs/spec-second-login.md §2. Owner only, by definition."""
    _owner_only()
    data = users.load() or {}
    return render_template("people.html", members=users.members(data),
                           owner_display=users.owner_display(data),
                           can_upload=bool(data.get("members_can_upload")),
                           gated=bool(PASSWORD), page="people")


@app.route("/people", methods=["POST"])
def people_post():
    _owner_only()
    action = request.form.get("action", "")
    name = (request.form.get("name") or "").strip()
    pw = request.form.get("password") or ""
    if _unsafe_line_value(name, request.form.get("display", "")):
        flash(_LINE_VALUE_ERROR, "warn")
        return redirect(url_for("people"))
    if action == "add":
        err = users.add_member(name, pw, request.form.get("display") or name)
        if err:
            flash(err, "warn")
        else:
            flash(f"Added {name}. Give them the password in person or by text — it isn't "
                  "shown again.", "info")
            _note("add member", "", name)
    elif action == "reset":
        if users.reset_password(name, pw):
            flash(f"New password set for {name}; their old sessions are signed out.", "info")
            _note("reset member password", "", name)
        else:
            flash("Choose a password of at least 8 characters.", "warn")
    elif action == "signout":
        users.sign_out_everywhere(name)
        flash(f"{name} is signed out on every device.", "info")
        _note("sign member out", "", name)
    elif action in ("disable", "enable"):
        users.set_disabled(name, action == "disable")
        flash(f"{name} is {'disabled' if action == 'disable' else 'enabled'}.", "info")
        _note(f"{action} member", "", name)
    elif action == "remove":
        if users.remove(name):
            flash(f"Removed {name}. Their past changes keep their label.", "info")
            _note("remove member", "", name)
    elif action == "owner":
        users.set_owner_display(request.form.get("display") or "")
        flash("Saved your display name.", "info")
    elif action == "upload":
        users.set_members_can_upload(request.form.get("allowed") == "1")
        flash("Saved.", "info")
    return redirect(url_for("people"))


@app.route("/activity")
def activity():
    """The last 100 deck-level actions, newest first (owner only)."""
    _owner_only()
    import csv as _csv
    rows = []
    try:
        with open(_activity_path(), encoding="utf-8") as f:
            rows = list(_csv.DictReader(f))
    except OSError:
        pass
    return render_template("activity.html", rows=list(reversed(rows))[:100],
                           page="people")


@app.route("/deck/<stem>/changes")
def deck_changes(stem):
    """Who changed what in this deck, and when — the deck's `.changes.csv`, newest
    first. Rows from before named members existed (and from the optimizer CLI or a
    session) have no name, and say so rather than guessing one."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    import csv as _csv
    rows = []
    try:
        with open(os.path.splitext(m["path"])[0] + ".changes.csv", encoding="utf-8") as f:
            rows = list(_csv.DictReader(f))
    except OSError:
        pass
    return render_template("changes.html", meta=m, rows=list(reversed(rows))[:200],
                           page="home")


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


# Every asset a page references goes out under a CONTENT-FINGERPRINTED URL —
# `/static/app.css?v=<hash of the file>` — via the `asset()` template global.
#
# Why (2026-10-11, the Arcane Ledger deploy): pages are always fetched fresh, but the
# installed service worker answered `/static/app.css` from its cache, so the first
# open after a deploy rendered the NEW markup with the OLD stylesheet — teal pills,
# 300px icons, the nav spilled across the page (reproduced in a persistent Chromium
# profile: old UI installed -> new UI deployed). With the hash in the URL a page can
# only ever ask for the CSS/JS it was written against: a new deploy is a new URL,
# which no cache — the worker's, the HTTP cache, an old worker that is still in
# control — can answer with yesterday's file.
_ASSET_DIRS = {"tokens.css": os.path.join(ROOT, "scripts", "assets")}
_asset_hashes = {}


def asset_url(name):
    """`/static/<name>?v=<first 10 hex of the file's sha256>`.

    Hashed per (path, mtime, size) so a page view costs one `stat` per asset and the
    file is only re-read when it changed. A missing file yields the plain URL (it
    will 404 exactly as before — the fingerprint never hides a broken reference)."""
    path = os.path.join(_ASSET_DIRS.get(name, os.path.join(ROOT, "webapp", "static")), name)
    try:
        st = os.stat(path)
    except OSError:
        return f"/static/{name}"
    key = (path, st.st_mtime_ns, st.st_size)
    v = _asset_hashes.get(key)
    if v is None:
        with open(path, "rb") as f:
            v = hashlib.sha256(f.read()).hexdigest()[:10]
        _asset_hashes[key] = v
    return f"/static/{name}?v={v}"


app.jinja_env.globals["asset"] = asset_url


@app.route("/static/manifest.webmanifest")
def web_manifest():
    """The PWA manifest, with its icon URLs fingerprinted like every other asset.

    An installed app re-reads its manifest to decide whether the home-screen icon
    changed; served raw, the icon URLs never change, so an old service worker could
    keep answering them from its cache and the new icon would not arrive. Same file
    on disk, URLs rewritten at serve time."""
    with open(os.path.join(ROOT, "webapp", "static", "manifest.webmanifest"),
              encoding="utf-8") as f:
        body = f.read()
    body = re.sub(r'"/static/([^"?]+)"', lambda m: f'"{asset_url(m.group(1))}"', body)
    return Response(body, mimetype="application/manifest+json",
                    headers={"Cache-Control": "no-cache"})


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


_TAKE_RE = re.compile(r"^[0-9a-f]{16}\.mp3$")


@app.route("/narration/<stem>/<name>")
def narration_file(stem, name):
    """One recorded take (docs/spec-watch-voice-and-controls.md Part C), behind the
    login like everything else. Only a file the deck's manifest lists is served — a
    content-hash name, so no path traversal and nothing else in the folder leaks —
    and it is cached forever: the name changes whenever the words or the voice do.
    send_from_directory answers Range requests (206), which phones need for audio."""
    if _deck_path(stem) is None or not _TAKE_RE.match(name):
        abort(404)
    import narration
    takes = narration.load_manifest(stem).get("takes") or {}
    if not any(t.get("file") == name for t in takes.values()):
        abort(404)
    resp = send_from_directory(os.path.join(narration.NARRATION_DIR, stem), name,
                               mimetype="audio/mpeg", conditional=True)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


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
