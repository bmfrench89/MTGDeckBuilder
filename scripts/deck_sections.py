#!/usr/bin/env python3
"""Regroup a deck file's sections by card TYPE (EDHREC-style).

The deck-file convention (2026-08-11): sections are card types — Creatures,
Instants, Sorceries, Artifacts, Enchantments, Planeswalkers, Battles, Lands,
Basics — in that order, commander first. Role information (ramp / draw /
Game Changer / tutor …) is not lost by this: it lives in the card details on
both surfaces (dashboard panel + /api/card) via `mtglib.classify` and
`deckcore.load_power_tags`.

Types come from the same data stack every tool uses: the collection (enriched
CSV or snapshot + collection_attrs) overlaid with the deck's own `.attrs.csv`.
A card whose type is still unknown falls back to a HINT from the section it
already sat in (a card under "Equipment" is an artifact; under "Lands" a land);
anything else lands in an explicit "Unsorted" section rather than being
guessed — enrich and re-run to resolve it.

The header comment block and `# Key: value` lines are preserved verbatim.
Idempotent: running it twice changes nothing.

    python3 scripts/deck_sections.py --deck data/decks/x.txt --collection <coll>
    python3 scripts/deck_sections.py --all --collection <coll> --apply
"""
import argparse
import glob
import os
import re
import sys

import mtglib
import deckcore

UNSORTED = "Unsorted (type unknown — enrich and re-run deck_sections)"

# old-section substring -> type section, for cards the data stack can't type.
SECTION_HINTS = (("basic", "Basics"), ("land", "Lands"), ("creature", "Creatures"),
                 ("equipment", "Artifacts"), ("artifact", "Artifacts"),
                 ("enchantment", "Enchantments"), ("planeswalker", "Planeswalkers"),
                 ("instant", "Instants"), ("sorcer", "Sorceries"))

_QTY = re.compile(r"^(\d+)\s+(.+?)\s*$")


def _hint(label):
    low = (label or "").lower()
    for key, section in SECTION_HINTS:
        if key in low:
            return section
    return None


def parse_file(path):
    """-> (header_lines, commander_name, [(old_label, qty, name), …]).
    Header = every line before the first section marker (titles, Notes, blanks)."""
    header, entries, cur = [], [], None
    commander = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            label = deckcore.section_label(line)
            if label is not None:
                cur = label
                continue
            m = _QTY.match(line.strip())
            if m and cur is not None:
                entries.append((cur, int(m.group(1)), m.group(2)))
                continue
            if cur is None:
                header.append(line)
                cm = re.match(r"#\s*Commander:\s*(.+?)\s*$", line)
                if cm:
                    commander = cm.group(1)
            # non-header comment lines inside sections are dropped by a regroup;
            # keep deck prose in the header block or .notes.md instead.
    while header and not header[-1].strip():
        header.pop()
    return header, commander, entries


def regroup(path, collection_path):
    """-> (new_text, stats) — the type-sectioned rewrite of one deck file."""
    header, commander, entries = parse_file(path)
    cards = mtglib.load_collection(collection_path)
    idx = mtglib.index_by_name(cards)
    attrs = deckcore.load_attrs(os.path.splitext(path)[0] + ".attrs.csv")

    buckets = {s: [] for s in deckcore.TYPE_SECTION_ORDER}
    buckets[UNSORTED] = []
    commander_line = None
    hinted = unknown = 0
    for old_label, qty, name in entries:
        if commander and mtglib._norm(name) == mtglib._norm(commander):
            commander_line = (qty, name)
            continue
        types = None
        a = attrs.get(mtglib._norm(name)) if attrs else None
        if a and a.get("type"):
            types = [a["type"]]
        else:
            card = mtglib.lookup(idx, name)
            if card is not None and card.types:
                types = card.types
        section = deckcore.type_bucket(name, types)
        if section is None:
            section = _hint(old_label)
            if section is not None:
                hinted += 1
            else:
                section = UNSORTED
                unknown += 1
        buckets[section].append((qty, name))

    out = list(header)
    if commander_line:                    # never INVENT a commander line the file
        out.append("")                    # didn't have — regroup only reorganizes
        out.append("# --- Commander ---")
        out.append(f"{commander_line[0]} {commander_line[1]}")
    for section in list(deckcore.TYPE_SECTION_ORDER) + [UNSORTED]:
        rows = buckets[section]
        if not rows:
            continue
        out.append("")
        out.append(f"# --- {section} ---")
        out.extend(f"{q} {n}" for q, n in rows)
    text = "\n".join(out) + "\n"
    total = (commander_line[0] if commander_line else 0) + \
        sum(q for rows in buckets.values() for q, _ in rows)
    return text, {"total": total, "hinted": hinted, "unsorted": unknown,
                  "unsorted_names": [n for _, n in buckets[UNSORTED]]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deck", help="deck file to regroup")
    ap.add_argument("--all", action="store_true", help="every deck in data/decks/")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--apply", action="store_true", help="write (default: preview)")
    args = ap.parse_args(argv)
    root = os.path.join(os.path.dirname(__file__), "..", "data", "decks")
    paths = sorted(glob.glob(os.path.join(root, "*.txt"))) if args.all else \
        ([args.deck] if args.deck else [])
    if not paths:
        ap.error("--deck or --all required")
    for path in paths:
        text, st = regroup(path, args.collection)
        tag = "wrote" if args.apply else "preview"
        if args.apply:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        line = (f"{tag} {os.path.basename(path)}: {st['total']} cards, "
                f"{st['hinted']} typed by section hint, {st['unsorted']} unsorted")
        if st["unsorted_names"]:
            line += " (" + ", ".join(st["unsorted_names"]) + ")"
        print(line)
        if not args.apply and len(paths) == 1:
            print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
