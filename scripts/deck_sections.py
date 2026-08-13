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

Duplicate lines for the SAME BASIC land landing in the same section are merged
(`1 Plains` + `3 Plains` -> `4 Plains`, first position kept) — a nonbasic
duplicate is left alone on purpose: that's a singleton illegality
`optimize.singleton_violations` reports, and merging would hide it.

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

# Card lines are parsed with mtglib's ONE qty-line parser plus parse_deck's bare-name
# fallback. A local `^(\d+)\s+` regex once dropped `1x Name` and bare-name lines —
# forms mtglib.parse_deck accepts — so a regroup --apply silently DELETED those cards.


def _place(rows, seen, qty, name):
    """Append `(qty, name)` to a section's rows, merging BASIC-land duplicates.

    Same merging semantics as `optimize._tidy` (sum quantities, keep the first
    line's position and spelling) — deliberately reused rather than reinvented,
    but narrowed: only what `mtglib.is_basic` accepts is merged. A duplicate
    line for a NONBASIC is a singleton illegality that
    `optimize.singleton_violations` reports; collapsing it into `2 Sol Ring`
    here would tidy the evidence into a tidier-looking illegality instead of
    leaving it where the violation report and the player can see it.

    Why basics need this: the 2026-08-11 buy migration appended "a 4th Plains"
    as a NEW line beside an existing `3 Plains`, and that path never ran
    `_tidy`. Two Plains lines are legal but wrong on the page."""
    if mtglib.is_basic(name):
        key = mtglib._norm(name)
        i = seen.get(key)
        if i is not None:
            rows[i] = (rows[i][0] + qty, rows[i][1])
            return
        seen[key] = len(rows)
    rows.append((qty, name))


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
            s = line.strip()
            if cur is not None and s and not s.startswith("#"):
                m = mtglib._QTY_RE.match(s)
                qty, name = (int(m.group(1)), m.group(2).strip()) if m else (1, s)
                entries.append((cur, qty, name))
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


def has_unsorted(path):
    """True when this deck file currently has a non-empty `Unsorted` section.

    The cheap filter for the post-sync auto-regroup (webapp/sync.py): once the
    server has enriched attrs, only the decks still carrying unsorted cards need
    rewriting — every other deck is already in shape and must not be churned."""
    try:
        _hdr, _cmd, entries = parse_file(path)
    except (OSError, UnicodeDecodeError):
        # OSError = missing/unreadable; UnicodeDecodeError (a ValueError, NOT an
        # OSError) = a deck file with invalid UTF-8. Either way the answer is
        # "nothing to regroup here" — an unreadable file must not be reported as
        # a *failed regroup* when no regroup was ever attempted.
        return False
    return any((label or "").strip().lower().startswith("unsorted")
               for label, _q, _n in entries)


def has_section_comments(path):
    """True when this deck file has a comment line INSIDE a section.

    `parse_file` drops those on a regroup (documented above). That is an
    acceptable cost for a deliberate CLI run, but the post-sync auto-regroup
    fires unattended against files the player can hand-edit in the app — and
    CLAUDE.md's edit contract says comment lines survive. `webapp/sync.py` uses
    this to SKIP such a deck rather than silently eat its prose.
    """
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return False
    in_section = False
    for line in lines:
        if deckcore.section_label(line) is not None:
            in_section = True
            continue
        s = line.strip()
        if in_section and s.startswith("#"):
            return True
    return False


def regroup(path, collection_path):
    """-> (new_text, stats) — the type-sectioned rewrite of one deck file."""
    header, commander, entries = parse_file(path)
    cards = mtglib.load_collection(collection_path)
    idx = mtglib.index_by_name(cards)
    attrs = deckcore.load_attrs(os.path.splitext(path)[0] + ".attrs.csv")

    buckets = {s: [] for s in deckcore.TYPE_SECTION_ORDER}
    buckets[UNSORTED] = []
    seen = {s: {} for s in buckets}       # section -> basic name key -> row index
    commander_line = None
    hinted = unknown = merged = 0
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
        before = len(buckets[section])
        _place(buckets[section], seen[section], qty, name)
        if len(buckets[section]) == before:
            merged += 1

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
                  "merged": merged,
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
                f"{st['hinted']} typed by section hint, {st['unsorted']} unsorted, "
                f"{st['merged']} duplicate basic line(s) merged")
        if st["unsorted_names"]:
            line += " (" + ", ".join(st["unsorted_names"]) + ")"
        print(line)
        if not args.apply and len(paths) == 1:
            print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
