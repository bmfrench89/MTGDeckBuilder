#!/usr/bin/env python3
"""Build Scryfall card-image hotlink URLs from Scryfall IDs.

These URLs render in a real browser even though this sandbox can't fetch them
(see the skill's tooling-and-data.md). Use them for the visual card gallery.

Usage:
  python3 card_image.py <scryfall_id> [--size normal] [--face front]
  python3 card_image.py --deck deck.txt --collection collection.csv [--size small]
      # prints "Card Name<TAB>url" for every deck card that has a Scryfall ID
"""
import argparse
import re
import sys
import urllib.parse

import mtglib

SIZES = {"small", "normal", "large", "png", "art_crop", "border_crop"}


def image_url(scryfall_id: str, size: str = "normal", face: str = "front") -> str:
    """Direct CDN URL — needs the Scryfall UUID (from the attribute CSV)."""
    sid = scryfall_id.strip().lower()
    if len(sid) < 2:
        raise ValueError(f"invalid scryfall id: {scryfall_id!r}")
    ext = "png" if size == "png" else "jpg"
    return (f"https://cards.scryfall.io/{size}/{face}/"
            f"{sid[0]}/{sid[1]}/{sid}.{ext}")


def image_url_by_name(name: str, size: str = "normal") -> str:
    """Scryfall API image-by-name — works from any card NAME (no UUID needed).
    Resolves live in a browser (the API 302-redirects to the image CDN). This is
    how we show images when the collection export has no Scryfall IDs."""
    q = re.sub(r"\s+", " ", name.replace("//", " ")).strip()
    return ("https://api.scryfall.com/cards/named?fuzzy="
            f"{urllib.parse.quote(q)}&format=image&version={size}")


def image_url_by_set(set_code: str, number: str, size: str = "normal") -> str:
    """Scryfall API image by set + collector number (exact printing)."""
    return (f"https://api.scryfall.com/cards/{urllib.parse.quote(set_code.lower())}/"
            f"{urllib.parse.quote(number)}?format=image&version={size}")


def purchase_links(name: str) -> dict:
    """'Buy this card' links by NAME for the card panel (no price feed — we link
    out instead). ManaPool has a direct per-card page (verified:
    manapool.com/card/<slug>); TCGplayer and Card Kingdom use their by-name
    search. All three live here so a corrected scheme is a one-line fix."""
    q = urllib.parse.quote(name)
    slug = re.sub(r"[^a-z0-9]+", "-",
                  name.lower().replace("'", "").replace("’", "")).strip("-")
    return {
        "tcgplayer": f"https://www.tcgplayer.com/search/magic/product?productLineName=magic&q={q}",
        "manapool": f"https://manapool.com/card/{slug}",
        "cardkingdom": f"https://www.cardkingdom.com/catalog/search?search=header&filter%5Bname%5D={q}",
    }


def main():
    ap = argparse.ArgumentParser(description="Scryfall image hotlink URLs.")
    ap.add_argument("scryfall_id", nargs="?", help="a single Scryfall ID")
    ap.add_argument("--deck", help="deck list file")
    ap.add_argument("--collection", help="collection CSV (must have Scryfall IDs)")
    ap.add_argument("--size", default="normal", choices=sorted(SIZES))
    ap.add_argument("--face", default="front", choices=["front", "back"])
    args = ap.parse_args()

    if args.scryfall_id:
        try:
            print(image_url(args.scryfall_id, args.size, args.face))
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        return 0

    if args.deck and args.collection:
        coll = mtglib.load_collection(args.collection)
        with open(args.deck, encoding="utf-8") as f:
            deck = mtglib.parse_deck(f.read())
        idx = mtglib.index_by_name(coll)
        missing_ids = 0
        for d in deck:
            ref = mtglib.lookup(idx, d.name)
            if ref and ref.scryfall_id:
                print(f"{d.name}\t{image_url(ref.scryfall_id, args.size, args.face)}")
            else:
                missing_ids += 1
                print(f"{d.name}\t(no Scryfall ID in collection)", file=sys.stderr)
        if missing_ids:
            print(f"[!] {missing_ids} card(s) had no Scryfall ID — need the CSV "
                  "export (name-only lists have no IDs).", file=sys.stderr)
        return 0

    ap.error("provide a scryfall_id, or both --deck and --collection")


if __name__ == "__main__":
    raise SystemExit(main())
