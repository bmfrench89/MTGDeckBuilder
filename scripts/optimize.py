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
  * Incoming cards are ranked free (a spare copy) > shared (owned but committed to another
    deck) > buy (not owned). Sharing and buying are ON by default: two decks in the same
    archetype legitimately want the same cards, and the player decides which one gets the
    physical copy at sleeving time. Unowned picks are badged "BUY" on the dashboard.
    `--owned-only` restricts to spare copies; `--no-buys` keeps the list fully owned.

Usage:
  python3 optimize.py --deck data/decks/foo.txt --collection data/collection/collection.csv
  python3 optimize.py --all --collection <coll> --apply
  python3 optimize.py --all --collection <coll> --apply --owned-only   # buildable today
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


def pool_report(deck_path, coll, idx, decks_dir, top_n=25):
    """Why a deck can't get closer to the field: of the commander's top-N most-played
    cards, how many are already in, FREE to add, locked in another deck, or unowned.

    Without this a deck whose card pool is exhausted just looks 'badly built'. A 7th deck
    sharing an archetype with an existing one (two equipment decks) will have every staple
    committed elsewhere, and the honest answer is 'buy these' or 'don't run both'."""
    stem = os.path.splitext(os.path.basename(deck_path))[0]
    text = open(deck_path, encoding="utf-8").read()
    commander = _commander_of(text)
    field = deck_fit.load_field(commander, idx)
    in_deck = {mtglib._norm(c.name) for c in mtglib.parse_deck(text)}
    usage = deck_conflicts.scan(decks_dir, idx, skip=stem)
    committed = {mtglib._norm(n): v for n, v in usage.items()}

    have, free, taken, unowned = [], [], [], []
    for k, inc in sorted(field.items(), key=lambda kv: -kv[1])[:top_n]:
        ref = mtglib.lookup(idx, k)
        if k in in_deck:
            have.append((inc, ref.name if ref else k))
        elif not ref:
            unowned.append((inc, k))
        elif ref.quantity - committed.get(k, {}).get("total", 0) >= 1:
            free.append((inc, ref.name))
        else:
            where = sorted(committed.get(k, {}).get("decks", {}))
            taken.append((inc, ref.name, where))
    return {"commander": commander, "top_n": top_n, "have": have, "free": free,
            "taken": taken, "unowned": unowned, "field_size": len(field)}


def write_buylist(deck_path, report, min_inclusion=40, overwrite=False):
    """Turn the unowned field staples into a <deck>.buylist.csv the dashboard renders.
    Never clobbers a hand-written buy-list unless explicitly told to."""
    rows = [(inc, name) for inc, name in report["unowned"] if inc >= min_inclusion]
    if not rows:
        return 0
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    if os.path.exists(f"{stem}.buylist.csv") and not overwrite:
        return 0
    import csv
    with open(f"{stem}.buylist.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Card", "Price", "Tier", "Replaces", "Reason"])
        for inc, name in rows:
            tier = "Core" if inc >= 65 else "Value"
            w.writerow([name.title(), "", tier, "",
                        f"{inc}% of {report['commander']} decks run this — "
                        f"your pool can't fill this slot."])
    return len(rows)


def optimize(deck_path, coll, idx, decks_dir, refs=None, margin=25, apply=False,
             max_swaps=40, owned_only=False, include_buys=True, buy_threshold=55):
    """Return a report dict; writes the deck file when apply=True."""
    refs = refs or power.load_refs()
    stem = os.path.splitext(os.path.basename(deck_path))[0]
    text = open(deck_path, encoding="utf-8").read()
    commander = _commander_of(text)

    a = deckcore.analyze_deck(deck_path, coll)      # accepts a loaded collection
    rep = a["report"]
    field = deck_fit.load_field(commander, idx)
    try:
        import edhrec
        proper = edhrec.field_names(commander, idx)   # real casing for unowned cards
    except Exception:
        proper = {}
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

    # ---- candidates to bring IN ---------------------------------------------------------
    # Ranked by how much the field plays them, then by availability:
    #   free  = you own a spare copy            (always allowed)
    #   share = owned but committed to another deck — allowed unless owned_only; the player
    #           decides which deck gets the physical card at sleeving time
    #   buy   = not owned at all — allowed when include_buys, so a deck can show its IDEAL
    #           list. The dashboard badges these "BUY" (they're `missing` to deck_stats).
    # Lands stay in their own bucket: a land must replace a LAND, or the deck's
    # 37-land / 62-spell split silently drifts.
    adds, land_adds = [], []
    for k, inc in field.items():
        if k in in_deck or k in BASICS or inc <= 0:
            continue
        ref = mtglib.lookup(idx, k)
        if ref is None:
            # owned_only means "buildable from what I have today" — that rules out
            # buying as well as borrowing from another deck.
            if owned_only or not include_buys or inc < buy_threshold:
                continue
            name, is_land, avail = proper.get(k, k.title()), False, "buy"
        else:
            if ref.identity and not (ref.identity <= identity):
                continue
            free = ref.quantity - committed.get(k, 0) >= 1
            if not free and owned_only:
                continue
            name, is_land, avail = ref.name, ref.is_land, ("free" if free else "share")
        rank = {"free": 2, "share": 1, "buy": 0}[avail]
        (land_adds if is_land else adds).append((inc, rank, name, avail))
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
    for inc_add, _rank, add_name, avail in adds:
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
            swaps.append((cut_name, val_cut, add_name, inc_add, avail))
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
    for inc_add, _rank, add_name, avail in land_adds:
        for inc_cut, cut_name in weak_lands:
            ck = mtglib._norm(cut_name)
            if ck in used_land or inc_add - inc_cut < margin:
                continue
            land_swaps.append((cut_name, add_name, avail))
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


# FUNCTION sections can hold any card type — Sol Ring belongs under "Ramp" even though
# it's an artifact. Keyed by role -> header keywords.
_SECTION_HINT = {
    "ramp": ("ramp", "mana"), "draw": ("draw", "card advantage"),
    "removal": ("removal", "interaction"), "wipe": ("wipe", "wrath"),
    "counter": ("counter",),
}

# TYPE sections may ONLY hold cards of that type. A section counts as type-exclusive when
# its header *starts with* the type word, so a curated header like "Spiders & Spider-matters
# creatures" or "Equipment support" is left alone — only plain "Creatures", "Lands",
# "Artifacts" … are policed. This is the rule the screenshot was violating: Door of
# Destinies (Artifact) and Methods of the Mighty (Instant) were filed under "Creatures".
_TYPE_SECTIONS = [
    (("creature",), {"Creature"}),
    (("land",), {"Land"}),
    (("artifact",), {"Artifact"}),
    (("enchantment",), {"Enchantment"}),
    (("planeswalker",), {"Planeswalker"}),
    (("instant", "sorcery", "sorceries", "spell"), {"Instant", "Sorcery"}),
]
# Where a card goes when no suitable section exists — created in this order, after the
# existing ones. Type-based, which is the convention every decklist site uses.
_FALLBACK_ORDER = [("Creature", "Creatures"), ("Planeswalker", "Planeswalkers"),
                   ("Artifact", "Artifacts"), ("Enchantment", "Enchantments"),
                   ("Instant", "Instants & sorceries"), ("Sorcery", "Instants & sorceries"),
                   ("Land", "Lands")]


def _type_allowed(section):
    """The card types a section may hold, or None if it isn't type-exclusive."""
    name = re.sub(r"\s*\(\d+\)\s*$", "", section).strip().lower()
    for words, types in _TYPE_SECTIONS:
        if any(name.startswith(w) for w in words):
            return types
    return None


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

    def function_section(role):
        """An existing function-named section for this role (any card type may live there)."""
        for kw in _SECTION_HINT.get(role, ()):
            for sec in order:
                if kw in sec.lower() and _type_allowed(sec) is None:
                    return sec
        return None

    def type_section(ptype):
        for sec in order:
            allowed = _type_allowed(sec)
            if allowed and ptype in allowed:
                return sec
        return None

    # Re-file. Priority: a function section for the card's role (keeps Sol Ring under
    # "Ramp"), else a section matching its TYPE, else create a type section. A card is only
    # forced to move when its current section is type-exclusive and contradicts its type.
    moved = {sec: [] for sec in order}
    for sec in order:
        keep_here, allowed_here = [], _type_allowed(sec)
        for item in sections.get(sec, []):
            if item[0] != "card":
                keep_here.append(item)
                continue
            _t, qty, name = item
            ref = mtglib.lookup(idx, name)
            if not ref or not ref.types:
                keep_here.append(item)            # unknown card: never shuffle it around
                continue
            ptype = "Land" if ref.is_land else ref.primary_type
            role = "land" if ref.is_land else deck_fit.primary_role(ref)
            misfiled = allowed_here is not None and ptype not in allowed_here
            target = function_section(role) or type_section(ptype)
            if target is None and misfiled:
                for t, label in _FALLBACK_ORDER:   # create the right type section
                    if t == ptype:
                        if label not in sections:
                            sections[label] = []
                            order.append(label)
                            moved.setdefault(label, [])
                        target = label
                        break
            if target and target != sec and (misfiled or allowed_here is not None):
                moved.setdefault(target, []).append(item)
            else:
                keep_here.append(item)
        sections[sec] = keep_here
    for sec, items in moved.items():
        sections.setdefault(sec, []).extend(items)

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
    repl = {mtglib._norm(c): a for c, _ic, a, _ia, *_ in swaps}
    for old, new, *_ in land_swaps:
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
    ap.add_argument("--owned-only", action="store_true",
                    help="only add cards with a FREE copy (never share or buy)")
    ap.add_argument("--no-buys", action="store_true",
                    help="don't add cards you don't own")
    ap.add_argument("--buy-threshold", type=int, default=55,
                    help="minimum inclusion %% for an unowned card to be added")
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
                     apply=args.apply, max_swaps=args.max_swaps,
                     owned_only=args.owned_only, include_buys=not args.no_buys,
                     buy_threshold=args.buy_threshold)
        print(f"\n=== {r['stem']} — {r['commander']} ({r['field_size']} field cards) ===")
        if not r["swaps"] and not r["land_swaps"]:
            print("   already aligned with the field — no changes")
        for cut, ic, add, ia, avail in r["swaps"]:
            tag = {"buy": " [BUY]", "share": " [shared]"}.get(avail, "")
            print(f"   {ic:>3}% {cut:32} ->  {ia:>3}% {add}{tag}")
        for old, new, avail in r["land_swaps"]:
            tag = {"buy": " [BUY]", "share": " [shared]"}.get(avail, "")
            print(f"   land  {old:32} ->  {new}{tag}")

        # Why can't it get closer? A deck with no free staples isn't badly built —
        # its pool is exhausted, and that needs saying out loud.
        rep = pool_report(p, coll, idx, args.decks_dir)
        n = rep["top_n"]
        print(f"   pool vs the field's top {n}: {len(rep['have'])} in deck · "
              f"{len(rep['free'])} free to add · {len(rep['taken'])} in another deck · "
              f"{len(rep['unowned'])} not owned")
        if rep["taken"]:
            byd = {}
            for _inc, _name, where in rep["taken"]:
                for d in where:
                    byd[d] = byd.get(d, 0) + 1
            worst = sorted(byd.items(), key=lambda kv: -kv[1])[:2]
            print("     locked in: " + ", ".join(f"{d} ({c})" for d, c in worst))
        # Only shout when the deck is genuinely far from the field AND has nothing left to
        # draw on — a deck at 21/25 with no free cards is finished, not starved.
        if not rep["free"] and len(rep["have"]) < n * 0.6 and (rep["unowned"] or rep["taken"]):
            print("     -> this deck can't improve from your collection: buy the gaps, "
                  "or free copies from the deck(s) above.")
        if args.apply:
            n_buy = write_buylist(p, rep)
            if n_buy:
                print(f"     wrote {r['stem']}.buylist.csv ({n_buy} staples to buy)")
    if not args.apply:
        print("\n(dry run — pass --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
