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
import os
import re
import socket
import subprocess
import sys

from flask import (Flask, Response, abort, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)

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
    _, idx = collection_index()
    rows = []
    for m in list_decks():
        try:
            res = power.build_for_deck(m["path"], idx)
        except Exception:
            res = None
        rows.append({**m, "assess": res})
    rows.sort(key=lambda r: -(r["assess"]["power"] if r["assess"] else 0))
    return render_template("index.html", decks=rows, page="home")


@app.route("/deck/<stem>")
def deck(stem):
    m = deck_meta(stem)
    if not m:
        abort(404)
    res = bd.generate(m["path"], COLLECTION, title=m["title"],
                      commander=m["commander"], theme=m["theme"], decks_dir=DECKS_DIR,
                      editable=True)
    return res["dashboard"]


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


def _edit_deck_card(path, action, name, replacement=None):
    """Line-based edit of a deck .txt: remove or replace a single card, preserving its
    quantity, section, and everything else. Returns True if a line changed."""
    key = mtglib._norm(name)
    lines = open(path, encoding="utf-8").read().split("\n")
    out, changed = [], False
    for ln in lines:
        s = ln.strip()
        if not changed and s and not s.startswith("#"):
            m = re.match(r"^(\d+)\s+(.*)$", s)
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


@app.route("/deck/<stem>/card", methods=["POST"])
def deck_card(stem):
    """Remove a card from a deck, or replace it with another — in place, from the panel."""
    m = deck_meta(stem)
    if not m:
        abort(404)
    action = request.form.get("action", "")
    name = request.form.get("name", "").strip()
    replacement = request.form.get("replacement", "").strip() or None
    if action in ("remove", "replace") and name:
        _edit_deck_card(m["path"], action, name, replacement)
    return redirect(url_for("deck", stem=stem))


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
    rep, missing = a["report"], a["missing"]
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
    if missing:
        L.append("-- NOT IN COLLECTION (buy-list candidates) --")
        L.append("  " + ", ".join(x.name for x in missing))
        L.append("")
    L.append("-- DECKLIST --")
    L.append(ex.deck_text(m["path"]).strip())
    return "\n".join(L) + "\n"


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
    rows = cf.score(idx, simc.load_commanders(), cf.load_support())
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
    d = auto_build.build(commander, coll, idx, DECKS_DIR, identity=(request.args.get("ci") or None))
    return render_template("build_deck.html", d=d, page="build")


@app.route("/build-next/<path:commander>/deck.txt")
def build_deck_export(commander):
    coll, idx = collection_index()
    d = auto_build.build(commander, coll, idx, DECKS_DIR, identity=(request.args.get("ci") or None))
    return _txt(auto_build.deck_text(d), f"{_deck_slug(commander)}.txt")


@app.route("/build-next/<path:commander>/save", methods=["POST"])
def build_deck_save(commander):
    """Write the auto-built draft to data/decks/ so it joins the leaderboard."""
    coll, idx = collection_index()
    d = auto_build.build(commander, coll, idx, DECKS_DIR, identity=(request.form.get("ci") or None))
    stem = _deck_slug(commander)
    with open(os.path.join(DECKS_DIR, f"{stem}.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(auto_build.deck_text(d))
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
    carddb = {
        "on": os.path.exists(attrs_path),
        "covered": enriched_n,
        "total": len(coll),
        "pct": round(100 * enriched_n / len(coll)) if coll else 0,
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
    d = auto_build.build(commander, coll, idx, DECKS_DIR, identity=(request.args.get("ci") or None))
    deck = mtglib.parse_deck(auto_build.deck_text(d))
    names = {mtglib._norm(x.name) for x in deck} | {mtglib._norm(commander)}
    r = spellbook.find_my_combos([commander], [(x.name, x.quantity) for x in deck])
    for c in r.get("almost", []):
        c["missing"] = [n for n in c["cards"] if mtglib._norm(n) not in names]
    r["almost"] = sorted([c for c in r.get("almost", []) if c.get("missing")],
                         key=lambda c: len(c["missing"]))
    return jsonify(r)


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
