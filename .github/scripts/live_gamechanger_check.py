#!/usr/bin/env python3
"""Diff data/reference/game_changers.txt against Scryfall's `is:gamechanger`.

Runs on a GitHub runner (open egress) as part of `recertify.yml`. Scryfall exposes
WotC's Game Changers list as a boolean on every card object and keeps it in sync, so
it is the canonical machine-readable source — the answer to the long-open
"where does a syncable list live" question in research-roadmap.md.

Reports a diff and exits non-zero when the lists disagree. It never rewrites the file:
the Game Changers count is the one hard numeric lever in the bracket system, so a
change gets a human's eyes.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIST = os.path.join(ROOT, "data", "reference", "game_changers.txt")
UA = {"User-Agent": "MTGDeckBuilder-recertify/1.0", "Accept": "application/json"}


def scryfall_gamechangers():
    """Every card with `game_changer: true`, followed through pagination."""
    url = ("https://api.scryfall.com/cards/search?q="
           + urllib.parse.quote("is:gamechanger") + "&unique=cards")
    names = set()
    while url:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        for c in data.get("data", []):
            names.add(c["name"].split(" // ")[0].strip().lower())
        url = data.get("next_page")
        if url:
            time.sleep(0.1)                      # Scryfall's requested courtesy delay
    return names


def repo_list():
    out = set()
    with open(LIST, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                out.add(s.split(" // ")[0].strip().lower())
    return out


def main():
    live = scryfall_gamechangers()
    if not live:
        print("FAIL: Scryfall returned no game changers — treating as an error "
              "rather than as an empty list")
        return 1
    ours = repo_list()
    missing = sorted(live - ours)                # WotC added, we don't have
    extra = sorted(ours - live)                  # we list, WotC no longer does
    print(f"Scryfall is:gamechanger = {len(live)} cards; "
          f"data/reference/game_changers.txt = {len(ours)}")
    if not missing and not extra:
        print("IN SYNC — no changes needed.")
        return 0
    for n in missing:
        print(f"  + ADD (on Scryfall, absent here): {n}")
    for n in extra:
        print(f"  - REMOVE (here, not on Scryfall): {n}")
    print("\nOut of sync. Update data/reference/game_changers.txt by hand — this "
          "check deliberately does not rewrite it (power.py's bracket cap reads it).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
