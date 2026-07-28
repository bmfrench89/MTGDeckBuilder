#!/usr/bin/env python3
"""Optimize an EXISTING deck against what the field actually plays.

The auto-builder assembles a deck from scratch; this tunes a deck you already have without
throwing away its identity. It swaps cards the field rarely plays for high-inclusion cards
you already own and aren't using elsewhere, then repairs the manabase.

Design rules (learned from a pass that tried to cut Exsanguinate out of Y'shtola):
  * A swap only happens when the incoming card is played MUCH more for this commander than
    the outgoing one (`--margin`, default 25 points of inclusion). That keeps a well-tuned
    deck nearly untouched while an off-base deck gets rebuilt.
  * Engine pieces are protected: the commander, basics, anything named in the deck's
    `.notes.md` game plan or in `card_notes.csv`, and anything the field itself plays.
  * Role counts (ramp / draw / removal / wipe / counter) must stay inside the template — a
    swap that would push a role out of range is rejected.
  * Only cards with a FREE copy (owned minus committed to your other decks) can come in.

Usage:
  python3 optimize.py --deck data/decks/foo.txt --collection data/collection/collection.csv
  python3 optimize.py --all --collection <coll> --apply
"""
import argparse
import glob
import os
import re
import sys

import mtglib
import deckcore
import deck_conflicts
import deck_fit
import power

# Role template (deckbuilding-principles.md). (min, max) per 99.
ROLE_RANGE = {"ramp": (9, 13), "draw": (8, 12), "removal": (8, 11),
              "wipe": (2, 5), "counter": (0, 6)}
LAND_TARGET = 37
BASICS = {"plains", "island", "swamp", "mountain", "forest", "wastes"}


def _commander_of(text):
    m = re.search(r"^#\s*Commander\s*:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    return re.split(r"\s{2,}|\(", m.group(1))[0].strip() if m else ""


def _protected(deck_path, commander):
    """Cards we never cut: the commander, basics, and anything the player called out as
    part of the plan (the deck's notes.md) or curated in card_notes.csv."""
    keep = {mtglib._norm(commander)} | set(BASICS)
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    try:
        notes = open(f"{stem}.notes.md", encoding="utf-8").read().lower()
    except OSError:
        notes = ""
    try:
        for k in deckcore.load_card_notes():
            keep.add(k)
    except Exception:
        pass
    return keep, notes


def _basics_needed(identity, n_lands=LAND_TARGET):
    """How many of the deck's lands should be basics. Scaled to the deck's ACTUAL land
    count (not a fixed 37) and shrinking as the identity widens, since more colours need
    more fixing. Basics are 98-99% inclusion in every archetype, so zero is a bug."""
    ncol = max(1, len(identity or []))
    return max(0, min(n_lands, round(n_lands * (0.42 - 0.04 * (ncol - 1)))))


def optimize(deck_path, coll, idx, decks_dir, refs=None, margin=25, apply=False,
             max_swaps=40):
    """Return a report dict; writes the deck file when apply=True."""
    refs = refs or power.load_refs()
    stem = os.path.splitext(os.path.basename(deck_path))[0]
    text = open(deck_path, encoding="utf-8").read()
    commander = _commander_of(text)

    a = deckcore.analyze_deck(deck_path, coll)      # accepts a loaded collection
    rep = a["report"]
    field = deck_fit.load_field(commander, idx)
    ctx = deck_fit.deck_context(deck_path, a["enriched"], commander, field=field)
    keep, notes = _protected(deck_path, commander)

    deck = mtglib.parse_deck(text)
    in_deck = {mtglib._norm(c.name) for c in deck}
    usage = deck_conflicts.scan(decks_dir, idx, skip=stem)
    committed = {mtglib._norm(n): v["total"] for n, v in usage.items()}
    identity = ctx.get("identity") or set()
    cats = dict(rep.get("categories", {}))

    def inc_of(name):
        return field.get(mtglib._norm(name), 0)

    def role_of(name):
        r = mtglib.lookup(idx, name)
        return deck_fit.primary_role(r) if r else None

    # ---- candidates to bring IN: owned, free, in-colour, played here, not already in ----
    # Lands are kept in their own bucket: a land must replace a LAND, or the deck's
    # 37-land / 62-spell split silently drifts.
    adds, land_adds = [], []
    for c in coll:
        k = mtglib._norm(c.name)
        if k in in_deck or k in BASICS:
            continue
        if c.identity and not (c.identity <= identity):
            continue
        if c.quantity - committed.get(k, 0) < 1:
            continue
        inc = field.get(k, 0)
        if inc <= 0:
            continue
        (land_adds if c.is_land else adds).append((inc, c.name))
    adds.sort(reverse=True)
    land_adds.sort(reverse=True)

    # ---- candidates to cut: low VALUE, not protected, not a land ----
    # Value is deliberately NOT raw popularity. A premium card can be 0% for a commander
    # simply because the field's decks lean a different theme (Cloud's EDHREC data is all
    # Final Fantasy builds, which would happily cut Skyclave Apparition or Cleansing Nova).
    # So a card is worth keeping if the FIELD plays it *or* our own engine rates it highly.
    def value_of(name, ref=None):
        ref = ref or mtglib.lookup(idx, name)
        inc = inc_of(name)
        fit = deck_fit.assess_card(ref, rep, ctx, refs)["score"] if (ref and ref.types) else 0
        return max(inc, (fit - 60) * 2)   # fit 85 -> 50, fit 70 -> 20, fit <=60 -> 0

    cuts = []
    for c in deck:
        k = mtglib._norm(c.name)
        if k in keep or k in BASICS:
            continue
        ref = mtglib.lookup(idx, c.name)
        if not ref or ref.is_land:
            continue                      # lands handled by the manabase pass
        if c.name.lower() in notes:
            continue                      # named in the player's own game plan
        cuts.append((value_of(c.name, ref), inc_of(c.name), c.name))
    cuts.sort()                           # least valuable first

    swaps, used_add, used_cut = [], set(), set()
    for inc_add, add_name in adds:
        if len(swaps) >= min(len(cuts), max_swaps):
            break
        add_role = role_of(add_name)
        for val_cut, inc_cut, cut_name in cuts:
            ck = mtglib._norm(cut_name)
            if ck in used_cut or mtglib._norm(add_name) in used_add:
                continue
            if inc_add - val_cut < margin:
                continue                  # not a clear enough upgrade
            cut_role = role_of(cut_name)
            # keep role counts inside the template
            trial = dict(cats)
            if cut_role:
                trial[cut_role] = trial.get(cut_role, 0) - 1
            if add_role:
                trial[add_role] = trial.get(add_role, 0) + 1
            ok = True
            for role, (lo, hi) in ROLE_RANGE.items():
                if role in (cut_role, add_role) and not (lo <= trial.get(role, 0) <= hi):
                    ok = False
                    break
            if not ok:
                continue
            cats = trial
            swaps.append((cut_name, val_cut, add_name, inc_add))
            used_cut.add(ck)
            used_add.add(mtglib._norm(add_name))
            break

    # ---- manabase passes. Both need field data: without it every land scores 0 and we
    # can't tell Command Tower from a bad tapland, so we leave the manabase alone. -------
    land_swaps = []
    lands = [c for c in deck if (mtglib.lookup(idx, c.name) and mtglib.lookup(idx, c.name).is_land)]
    if not field:
        return {"stem": stem, "commander": commander, "swaps": swaps,
                "land_swaps": [], "field_size": 0}

    # pass 1: upgrade weak nonbasic lands to ones the field actually plays
    weak_lands = sorted((inc_of(c.name), c.name) for c in lands
                        if mtglib._norm(c.name) not in BASICS
                        and mtglib._norm(c.name) not in keep
                        and c.name.lower() not in notes)
    used_land = set()
    for inc_add, add_name in land_adds:
        for inc_cut, cut_name in weak_lands:
            ck = mtglib._norm(cut_name)
            if ck in used_land or inc_add - inc_cut < margin:
                continue
            land_swaps.append((cut_name, add_name))
            used_land.add(ck)
            break

    # ---- manabase pass 2: run basics (98-99% inclusion in every archetype) --------------
    n_lands = sum(c.quantity for c in lands)
    n_basic = sum(c.quantity for c in lands if mtglib._norm(c.name) in BASICS)
    want_basic = _basics_needed(identity, n_lands)
    if n_basic < want_basic:
        worst = [(i, n) for i, n in weak_lands if mtglib._norm(n) not in used_land]
        need = want_basic - n_basic
        colors = sorted(identity) or ["C"]
        cname = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
        i = 0
        for inc_l, land in worst:
            if need <= 0:
                break
            if inc_l >= 40:               # a genuinely-played fixing land: keep it
                continue
            land_swaps.append((land, cname.get(colors[i % len(colors)], "Wastes")))
            i += 1
            need -= 1

    result = {"stem": stem, "commander": commander, "swaps": swaps,
              "land_swaps": land_swaps, "field_size": len(field)}
    if apply and (swaps or land_swaps):
        _write(deck_path, swaps, land_swaps)
        _tidy(deck_path, idx)
    return result


# role -> keywords that identify the right section header in a deck file
_SECTION_HINT = {
    "land": ("land",), "ramp": ("ramp", "mana"), "draw": ("draw", "card advantage"),
    "removal": ("removal", "interaction"), "wipe": ("wipe", "wrath", "board"),
    "counter": ("counter",), "creature": ("creature", "threat"),
}


def _tidy(deck_path, idx):
    """Re-file cards under the section that matches their role and merge duplicate lines.
    Only sections the file ALREADY has are used, so the player's own grouping is kept —
    this just stops a swapped-in ramp spell from sitting under '--- Creatures ---', and
    collapses '1 Forest' + '7 Forest' into one line."""
    lines = open(deck_path, encoding="utf-8").read().split("\n")
    header, sections, order, cur = [], {}, [], None
    for ln in lines:
        s = ln.strip()
        m_sec = re.match(r"^#\s*-+\s*(.+?)\s*-+\s*$", s)
        if m_sec:
            cur = m_sec.group(1)
            if cur not in sections:
                sections[cur] = []
                order.append(cur)
            continue
        if not s or s.startswith("#"):
            (header if cur is None else sections.setdefault(cur, [])).append(("raw", ln))
            continue
        m = re.match(r"^(\d+)\s+(.*)$", s)
        qty, name = (int(m.group(1)), m.group(2)) if m else (1, s)
        sections.setdefault(cur or (order[0] if order else "Cards"), []).append(("card", qty, name))

    def best_section(role):
        for kw in _SECTION_HINT.get(role, ()):
            for sec in order:
                if kw in sec.lower():
                    return sec
        return None

    # move mis-filed cards
    moved = {sec: [] for sec in order}
    for sec in order:
        keep_here = []
        for item in sections.get(sec, []):
            if item[0] != "card":
                keep_here.append(item)
                continue
            _t, qty, name = item
            ref = mtglib.lookup(idx, name)
            role = "land" if (ref and ref.is_land) else (deck_fit.primary_role(ref) if ref else None)
            target = best_section(role) if role else None
            if target and target != sec and any(k in sec.lower() for k in
                                                ("creature", "land", "ramp", "draw", "removal", "wipe", "counter")):
                moved[target].append(item)
            else:
                keep_here.append(item)
        sections[sec] = keep_here
    for sec, items in moved.items():
        sections[sec].extend(items)

    out = list(l for _t, l in header) if header and header[0][0] == "raw" else []
    out = [ln for ln in lines[:0]]                      # rebuilt below
    # header block = everything before the first section marker
    first_sec_i = next((i for i, ln in enumerate(lines)
                        if re.match(r"^#\s*-+\s*.+?\s*-+\s*$", ln.strip())), len(lines))
    out = lines[:first_sec_i]
    for sec in order:
        merged, seen_order = {}, []
        for item in sections.get(sec, []):
            if item[0] != "card":
                continue
            _t, qty, name = item
            k = mtglib._norm(name)
            if k in merged:
                merged[k][0] += qty                      # collapse duplicate lines
            else:
                merged[k] = [qty, name]
                seen_order.append(k)
        if not seen_order:
            continue                                     # drop a section left empty
        # refresh a stale "(14)" style count in the header
        total = sum(merged[k][0] for k in seen_order)
        title = re.sub(r"\s*\(\d+\)\s*$", "", sec)
        label = f"{title} ({total})" if re.search(r"\(\d+\)\s*$", sec) else title
        out.append(f"# --- {label} ---")
        for k in seen_order:
            qty, name = merged[k]
            out.append(f"{qty} {name}")
        out.append("")
    with open(deck_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out).rstrip("\n") + "\n")


def _write(deck_path, swaps, land_swaps):
    """Apply swaps line-by-line, preserving quantity, section and every other line."""
    repl = {mtglib._norm(c): a for c, _ic, a, _ia in swaps}
    for old, new in land_swaps:
        repl.setdefault(mtglib._norm(old), new)
    lines = open(deck_path, encoding="utf-8").read().split("\n")
    out, done = [], set()
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith("#"):
            m = re.match(r"^(\d+)\s+(.*)$", s)
            name = m.group(2) if m else s
            k = mtglib._norm(name)
            if k in repl and k not in done:
                out.append(f"{m.group(1) if m else '1'} {repl[k]}")
                done.add(k)
                continue
        out.append(ln)
    with open(deck_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out))


def main():
    ap = argparse.ArgumentParser(description="Optimize a deck against what the field plays.")
    ap.add_argument("--deck")
    ap.add_argument("--all", action="store_true", help="every deck in --decks-dir")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--decks-dir", default="data/decks")
    ap.add_argument("--margin", type=int, default=25,
                    help="minimum inclusion-%% gain for a swap (higher = more conservative)")
    ap.add_argument("--max-swaps", type=int, default=40,
                    help="safety cap on how many cards a single pass may change")
    ap.add_argument("--apply", action="store_true", help="write the changes")
    args = ap.parse_args()

    coll = mtglib.load_collection(args.collection)
    idx = mtglib.index_by_name(coll)
    refs = power.load_refs()
    paths = sorted(glob.glob(os.path.join(args.decks_dir, "*.txt"))) if args.all else [args.deck]
    if not paths or paths == [None]:
        print("error: pass --deck or --all", file=sys.stderr)
        return 2

    for p in paths:
        r = optimize(p, coll, idx, args.decks_dir, refs, margin=args.margin,
                     apply=args.apply, max_swaps=args.max_swaps)
        print(f"\n=== {r['stem']} — {r['commander']} ({r['field_size']} field cards) ===")
        if not r["swaps"] and not r["land_swaps"]:
            print("   already aligned with the field — no changes")
        for cut, ic, add, ia in r["swaps"]:
            print(f"   {ic:>3}% {cut:32} ->  {ia:>3}% {add}")
        for old, new in r["land_swaps"]:
            print(f"   land  {old:32} ->  {new}")
    if not args.apply:
        print("\n(dry run — pass --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
