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
                      commander=m["commander"], theme=m["theme"], decks_dir=DECKS_DIR)
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
    """Full deck auto-built from the owned pool for this commander (Phase 3 v1)."""
    coll, idx = collection_index()
    d = auto_build.build(commander, coll, idx, DECKS_DIR)
    return render_template("build_deck.html", d=d, page="build")


@app.route("/build-next/<path:commander>/deck.txt")
def build_deck_export(commander):
    coll, idx = collection_index()
    d = auto_build.build(commander, coll, idx, DECKS_DIR)
    return _txt(auto_build.deck_text(d), f"{_deck_slug(commander)}.txt")


@app.route("/build-next/<path:commander>/save", methods=["POST"])
def build_deck_save(commander):
    """Write the auto-built draft to data/decks/ so it joins the leaderboard."""
    coll, idx = collection_index()
    d = auto_build.build(commander, coll, idx, DECKS_DIR)
    stem = _deck_slug(commander)
    with open(os.path.join(DECKS_DIR, f"{stem}.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(auto_build.deck_text(d))
    return redirect(url_for("deck", stem=stem))


@app.route("/collection", methods=["GET"])
def collection_view():
    coll, _ = collection_index()
    priced = [c for c in coll if c.price]
    total = round(sum(c.value for c in coll), 2)
    top = sorted(priced, key=lambda c: -c.price)[:20]
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
                           carddb=carddb, page="collection")


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
        f.save(COLLECTION)
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
