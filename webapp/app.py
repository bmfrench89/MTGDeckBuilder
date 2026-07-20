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
import subprocess
import sys

from flask import (Flask, abort, redirect, render_template, request,
                   send_from_directory, url_for)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import mtglib
import deck_stats
import power
import deck_conflicts
import wishlist as wl
import build_dashboard as bd
import analyze_collection as ac

COLLECTION = os.environ.get("MTG_COLLECTION", os.path.join(ROOT, "data/collection/collection.csv"))
DECKS_DIR = os.environ.get("MTG_DECKS_DIR", os.path.join(ROOT, "data/decks"))
ADDITIONS = os.path.join(ROOT, "data/collection/owned_additions.txt")

app = Flask(__name__)


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


@app.route("/shared")
def shared_view():
    coll, idx = collection_index()
    usage = deck_conflicts.scan(DECKS_DIR, idx)
    conf = deck_conflicts.conflicts(usage)
    total = round(sum(c["buy_cost"] or 0 for c in conf), 2)
    return render_template("shared.html", conf=conf, total=total, page="shared")


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
    return render_template("collection.html", unique=len(coll),
                           copies=sum(c.quantity for c in coll), total=total,
                           top=top, has_price=bool(priced), additions=additions,
                           page="collection")


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


@app.route("/health")
def health():
    return {"ok": True, "collection": COLLECTION, "decks": len(list_decks())}


if __name__ == "__main__":
    port = int(os.environ.get("MTG_PORT", "5000"))
    print(f"MTG Deckbuilder web app → http://127.0.0.1:{port}")
    print(f"  collection: {COLLECTION}")
    print(f"  decks dir : {DECKS_DIR}")
    app.run(host="127.0.0.1", port=port, debug=False)
