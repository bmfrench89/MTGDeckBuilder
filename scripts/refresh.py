#!/usr/bin/env python3
"""One command to regenerate everything: a dashboard (+ visual gallery) for every
deck, plus the consolidated wishlist. Run this after any deck, collection, buy-list,
or ownership change so all artifacts stay in sync.

Each deck's title/theme/commander are read from headers in its .txt file:
    # Title: Cosmic Spider-Man
    # Theme: spider              (default | yshtola | cloud | rakdos | spider)
    # Commander: Cosmic Spider-Man ...
New decks are picked up automatically.

Usage:
  python3 scripts/refresh.py --collection data/collection/collection.csv
  python3 scripts/refresh.py --collection coll.csv --out-dir build --no-visual
"""
import argparse
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def header(text, key, default=""):
    m = re.search(rf"^#\s*{key}\s*:\s*(.+?)\s*$", text, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else default


def main():
    ap = argparse.ArgumentParser(description="Regenerate all dashboards + wishlist.")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--decks-dir", default="data/decks")
    ap.add_argument("--out-dir", default="build")
    ap.add_argument("--no-visual", action="store_true", help="skip card-image galleries")
    ap.add_argument("--size", default="small")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    decks = sorted(glob.glob(os.path.join(args.decks_dir, "*.txt")))
    if not decks:
        print(f"no decks found in {args.decks_dir}", file=sys.stderr)
        return 2

    ok = 0
    for path in decks:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        stem = os.path.splitext(os.path.basename(path))[0]
        title = header(text, "Title") or header(text, "Commander") or stem
        commander = re.split(r"\s{2,}|\(", header(text, "Commander"))[0].strip()
        theme = header(text, "Theme", "default")
        out = os.path.join(args.out_dir, f"{stem}.html")
        cmd = [sys.executable, os.path.join(HERE, "build_dashboard.py"),
               "--deck", path, "--collection", args.collection,
               "--title", title, "--commander", commander,
               "--theme", theme, "--out", out]
        if not args.no_visual:
            cmd += ["--visual", "--size", args.size]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            ok += 1
            print(f"  ✓ {stem}  ({title}, theme={theme})")
        else:
            print(f"  ✗ {stem}: {r.stderr.strip().splitlines()[-1] if r.stderr else 'failed'}")

    # Wishlist
    wl = os.path.join("data", "wishlist.md")
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "wishlist.py"),
         "--collection", args.collection, "--decks-dir", args.decks_dir, "--out", wl],
        capture_output=True, text=True)
    print(r.stdout.strip() if r.returncode == 0 else f"  ✗ wishlist: {r.stderr.strip()}")

    print(f"\nRefreshed {ok}/{len(decks)} dashboards -> {args.out_dir}/  +  {wl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
