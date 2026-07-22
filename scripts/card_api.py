#!/usr/bin/env python3
"""Grounded, deck-agnostic payload behind the site-wide card panel.

Pure/stdlib (no Flask): given a card NAME + the loaded collection index + the
decks folder, return everything the shared card panel needs from LOCAL data —
role(s), mana value, curated strategy note, combo membership, which of your decks
use the card, owned/quantity, an image URL, and buy-links. The live oracle text /
rulings are fetched client-side from Scryfall by the panel JS (Scryfall is
firewalled server-side in this environment), so this stays offline-safe.

Used by webapp `/api/card/<name>`; importable and testable without a server.
"""
import glob
import os

import mtglib
import card_image
import combo_detector
import build_dashboard as bd   # reuse load_card_notes + role labels (no duplication)


def _decks_using(name, decks_dir):
    """Which deck stems list this card (by normalized name)."""
    key = mtglib._norm(name)
    hits = []
    for path in sorted(glob.glob(os.path.join(decks_dir, "*.txt"))):
        try:
            with open(path, encoding="utf-8") as f:
                deck = mtglib.parse_deck(f.read())
        except OSError:
            continue
        if any(mtglib._norm(c.name) == key for c in deck):
            hits.append(os.path.splitext(os.path.basename(path))[0])
    return hits


def _combos_with(name, combos):
    """Combos this card is a piece of, with its partners and result."""
    key = mtglib._norm(name)
    out = []
    for cb in combos:
        if key in cb["pieces"]:
            partners = [disp for pc, disp in zip(cb["pieces"], cb["display"])
                        if pc != key]
            out.append({"name": cb["name"], "result": cb["result"],
                        "early": cb["early"], "with": partners})
    return out


def card_payload(name, coll_index, decks_dir, notes=None, combos=None):
    """Return the JSON-able payload for one card. `notes`/`combos` may be passed
    in pre-loaded (to avoid re-reading the reference files per request)."""
    ref = mtglib.lookup(coll_index, name)
    notes = notes if notes is not None else bd.load_card_notes()
    combos = combos if combos is not None else combo_detector.load_combos()
    key = mtglib._norm(name)

    roles = sorted(mtglib.classify(ref)) if ref else []
    note = notes.get(key)
    sid = ref.scryfall_id if (ref and ref.scryfall_id) else ""
    image = (card_image.image_url(sid) if sid
             else card_image.image_url_by_name(name))

    return {
        "name": ref.name if ref else name,
        "owned": bool(ref),
        "qty": ref.quantity if ref else 0,
        "mv": ref.mana_value if ref else None,
        "type": ref.primary_type if (ref and ref.types) else None,
        "roles": [bd._ROLE_LABEL.get(r, r.title()) for r in roles],
        "note": {"why": note["why"], "alts": note["alts"]} if note else None,
        "combos": _combos_with(name, combos),
        "decks": _decks_using(name, decks_dir),
        "scryfall_id": sid,
        "image": image,
        "buy": card_image.purchase_links(ref.name if ref else name),
    }


if __name__ == "__main__":   # tiny CLI for spot-checking the payload
    import argparse
    import json
    import sys
    ap = argparse.ArgumentParser(description="Print the card-panel payload for a name.")
    ap.add_argument("name")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--decks-dir", default="data/decks")
    args = ap.parse_args()
    try:
        coll = mtglib.load_collection(args.collection)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(2)
    idx = mtglib.index_by_name(coll)
    print(json.dumps(card_payload(args.name, idx, args.decks_dir), indent=2))
