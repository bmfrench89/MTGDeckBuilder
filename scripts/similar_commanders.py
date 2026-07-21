#!/usr/bin/env python3
"""'This commander would also work' — find alternate commanders for a deck.

Ranks candidate commanders (from data/reference/commanders.csv) that share the
deck's archetype, and tells you the HONEST color story for each:
  - drop-in    : the candidate's colors cover your deck — the same 99 stay legal.
  - tighter    : candidate is a subset of your colors — you'd trim off-color cards.
  - partial    : shares some colors — keep the overlap + colorless, rebuild the rest.
  - reskin     : same idea, different colors — a fresh shell (your colorless cards carry).
Owned candidates are flagged (grab it off the shelf) vs. a buy.

Deck metadata comes from headers in the deck .txt:
    # Archetype: equipment voltron artifacts
    # Colors: R G W
(falls back to the deck's commander entry in commanders.csv).

Usage:
  python3 similar_commanders.py --deck data/decks/cloud-ex-soldier.txt \
      --collection data/collection/collection.csv
"""
import argparse
import csv
import os
import re
import sys

import mtglib
import build_dashboard as bd  # for load_attrs

REF = os.path.join(os.path.dirname(__file__), "..", "data", "reference", "commanders.csv")


def load_commanders(path=REF):
    out = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(r for r in f if not r.lstrip().startswith("#")):
            name = (row.get("Name") or "").strip()
            if not name:
                continue
            out.append({
                "name": name,
                "colors": mtglib._parse_colorish(row.get("Colors", "")),
                "archetypes": set((row.get("Archetypes") or "").split()),
                "notes": (row.get("Notes") or "").strip(),
            })
    return out


def _hdr(text, key, default=""):
    m = re.search(rf"^#\s*{key}\s*:\s*(.+?)\s*$", text, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else default


def deck_profile(deck_path, commanders):
    text = open(deck_path, encoding="utf-8").read()
    commander = re.split(r"\s{2,}|\(", _hdr(text, "Commander"))[0].strip()
    arch = set(_hdr(text, "Archetype").split())
    colors = mtglib._parse_colorish(_hdr(text, "Colors"))
    # fall back to the commander's own entry
    for c in commanders:
        if mtglib._norm(c["name"]) == mtglib._norm(commander):
            arch = arch or c["archetypes"]
            colors = colors or c["colors"]
            break
    return commander, arch, colors, text


def color_relation(deck_colors, cand_colors):
    if not deck_colors or not cand_colors:
        return "unknown", "colors unknown"
    if cand_colors >= deck_colors:
        return "drop-in", "covers all your colors — the same 99 stay legal"
    if deck_colors >= cand_colors:
        lost = "".join(sorted(deck_colors - cand_colors))
        return "tighter", f"tighter colors — you'd trim your {lost} cards"
    shared = "".join(sorted(deck_colors & cand_colors))
    if shared:
        return "partial", f"shares {shared} — keep the {shared}/colorless core, rebuild the rest"
    return "reskin", "different colors — same idea, a fresh shell (colorless cards carry)"


RANK = {"drop-in": 0, "tighter": 1, "partial": 2, "reskin": 3, "unknown": 4}


def find(deck_path, collection_index, commanders, attrs=None):
    commander, arch, colors, _ = deck_profile(deck_path, commanders)
    # Per-card color identities for exact compat %. Prefer the collection overlay
    # (carddb enrichment covers the whole collection); fall back to a deck attrs file.
    attr_idx = {mtglib._norm(k): v for k, v in (attrs or {}).items()}
    card_ids = []
    with open(deck_path, encoding="utf-8") as f:
        for d in mtglib.parse_deck(f.read()):
            ref = mtglib.lookup(collection_index, d.name)
            ci = ref.identity if (ref and ref.identity) else None
            if ci is None:
                a = attr_idx.get(mtglib._norm(d.name))
                if a and a.get("colors"):
                    ci = mtglib._parse_colorish(a["colors"])
            if ci is not None:
                card_ids.append(ci)
    if not card_ids:
        card_ids = None
    results = []
    for c in commanders:
        if mtglib._norm(c["name"]) == mtglib._norm(commander):
            continue
        shared_arch = arch & c["archetypes"]
        if not shared_arch:
            continue
        rel, why = color_relation(colors, c["colors"])
        owned = mtglib.lookup(collection_index, c["name"]) is not None
        pct = None
        if card_ids is not None and c["colors"]:
            legal = sum(1 for ci in card_ids if ci <= c["colors"])
            pct = round(100 * legal / len(card_ids)) if card_ids else None
        results.append({
            "name": c["name"], "colors": "".join(sorted(c["colors"])) or "C",
            "shared": sorted(shared_arch), "relation": rel, "why": why,
            "owned": owned, "compat_pct": pct, "notes": c["notes"],
        })
    results.sort(key=lambda r: (RANK[r["relation"]], not r["owned"],
                                -len(r["shared"]), r["name"]))
    return commander, sorted(arch), results


def main():
    ap = argparse.ArgumentParser(description="Find similar commanders for a deck.")
    ap.add_argument("--deck", required=True)
    ap.add_argument("--collection", required=True)
    args = ap.parse_args()
    try:
        coll = mtglib.load_collection(args.collection)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    idx = mtglib.index_by_name(coll)
    stem = args.deck[:-4] if args.deck.endswith(".txt") else args.deck
    attrs = bd.load_attrs(f"{stem}.attrs.csv")
    commander, arch, results = find(args.deck, idx, load_commanders(), attrs)

    print(f"Deck commander: {commander}   [{' '.join(arch)}]")
    print(f"\nCommanders that would ALSO run this shell ({len(results)}):\n")
    tag = {"drop-in": "✅ DROP-IN", "tighter": "◐ TIGHTER",
           "partial": "◑ PARTIAL", "reskin": "○ RESKIN", "unknown": "? "}
    for r in results:
        own = "OWNED" if r["owned"] else "buy"
        pct = f"  ~{r['compat_pct']}% of cards stay in color" if r["compat_pct"] is not None else ""
        print(f"  {tag[r['relation']]:<11} {r['name']}  [{r['colors']}]  ({own})")
        print(f"      {r['why']}{pct}")
        print(f"      shares: {', '.join(r['shared'])} · {r['notes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
