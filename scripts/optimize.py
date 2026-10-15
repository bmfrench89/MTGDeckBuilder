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
    swap that would push a role out of range is rejected. The template is ARCHETYPE-AWARE
    (`role_ranges`): the deck's `# Archetype:` header widens it, because a draw-go control
    deck running 15 counterspells is correct, not nine cards over budget.
  * The field has a veto over role repair: a swap may never cut a card the field plays
    MORE than the incoming one. Template pressure arrives through `value_of`'s fit blend
    and can manufacture the margin on its own; the field consensus outranks it.
  * Incoming cards are ranked free (a spare copy) > shared (owned but committed to another
    deck) > buy (not owned). Sharing is ON by default: two decks in the same archetype
    legitimately want the same cards, and the player decides which one gets the physical
    copy at sleeving time. Buys are considered by default but NEVER enter the 99
    (2026-08-11, player request: decks are built from what's owned) — each pairs with an
    in-deck card and is appended to `.buylist.csv` with Replaces = that card, so the list
    answers "when this arrives, which card do I pull". `--owned-only` restricts adds to
    spare copies; `--no-buys` skips the buylist recommendations too.

Usage:
  python3 optimize.py --deck data/decks/foo.txt --collection data/collection/collection.csv
  python3 optimize.py --all --collection <coll> --apply
  python3 optimize.py --all --collection <coll> --apply --owned-only   # buildable today
"""
import argparse
import glob
import json
import os
import re
import sys

import mtglib
import deckcore
import clips as clipmod
import deck_conflicts
import deck_fit
import power

# The role template LIVES IN deckcore now (Phase 12) — one table, one widener,
# every consumer. These module attributes are SHIMS kept so existing imports,
# tests and the webapp keep working; do not add numbers here.
ROLE_RANGE = deckcore.ROLE_RANGE
_ARCHETYPE_ROLE_RANGE = deckcore._ARCHETYPE_ROLE_RANGE
role_ranges = deckcore.role_ranges
role_ranges_with_unknown = deckcore.role_ranges_with_unknown
LAND_TARGET = deckcore.LAND_TARGET
BASICS = {"plains", "island", "swamp", "mountain", "forest", "wastes"}


# A field % at which "the field plays it in most decks" outweighs a cut the field
# has no row for. See the no-field-row guard in optimize().
STRONG_CONSENSUS = 50

# The manabase pass (spec-optimizer-judgment Phase A): a land swap needs the incoming
# land to beat the outgoing one by 0.6 colour-equivalents of `manabase.land_mana_score`
# — e.g. a tapped dual to an untapped one (+0.75), a tapped mono land to a basic of a
# main colour. A land the field runs this often is kept: the score can't see abilities.
LAND_SCORE_MARGIN = 0.6

# How many owned, field-silent cards a report offers for a session's read (Phase C).
READS_LIMIT = 8
READS_PER_ROLE = 3
READS_MIN_FIT = 70
# Below this field %, an owned card is never a "riser" (gate-held advice) — so reads
# carry it instead, or nothing would.
RISER_FLOOR = 20
READS_RARE_LIMIT = 6
# A proposal that cuts a card at least this specific to the commander (lift, see
# deck_fit.commander_lift) for one under TRADE_GENERIC_LIFT is flagged: the field is
# trading the deck's own engine for a staple, which is exactly the call a read should make.
TRADE_GENERIC_LIFT = 2.0
# Generic-slot upgrades (2026-10-15, the deck-flow review): a widely played rock or
# removal spell 18 points ahead of a clunkier generic card never cleared the 25-point
# margin. When BOTH cards are generic for this commander (lift under GENERIC_LIFT) the
# bar drops to GENERIC_MARGIN, but only on a gain the FIELD shows (inclusion %, not fit):
# the margin also stops role-template pressure (worth up to 24 points of value) from
# inventing swaps, and that pressure never moves inclusion. Engine slots keep the 25.
GENERIC_LIFT = 2.0
GENERIC_MARGIN = 15
LAND_FIELD_KEEP = 25


def card_value(name, ref, rep, ctx, refs, field):
    """Deprecated shim — the scorer lives in `deck_fit.card_value` now.

    Kept so nothing that imported it from here breaks; `deck_fit` is the right home
    because the fit half of the blend is its own, and putting it there is what lets
    build_dashboard rank cuts without importing this spoke."""
    return deck_fit.card_value(name, ref, rep, ctx, refs, field)


def cut_candidates(deck_path, collection, idx=None, decks_dir=None, limit=12,
                   analysis=None):
    """"If you must cut, start here" — the I/O wrapper around `deck_fit.cut_ranking`.

    ADVISORY AND READ-ONLY: it writes nothing and proposes no replacement. This half
    loads the deck and the field; the ranking itself is in deck_fit so the dashboard
    can compute the same list from what it already has in hand.
    """
    import deckcore
    a = analysis or deckcore.analyze_deck(deck_path, collection)
    idx = idx or a["idx"]
    rep, enriched = a["report"], a["enriched"]
    stem = os.path.basename(deck_path)[:-4] if deck_path.endswith(".txt") \
        else os.path.basename(deck_path)
    commander = _commander_of(open(deck_path, encoding="utf-8").read())
    refs = power.load_refs()
    field = deck_fit.load_field(commander, idx) or {}
    synergy = deck_fit.load_synergy(commander, idx) or {}
    ctx = deck_fit.deck_context(deck_path, enriched, commander, field, synergy)
    ranges, _unknown = role_ranges_with_unknown(ctx.get("archetype"))
    prot = _protected(deck_path, commander)
    prot = prot[0] if isinstance(prot, tuple) else prot
    # The player's own picks, flagged rather than hidden (see cut_ranking's docstring).
    #
    # This was silently a no-op until the Phase 8 acceptance run (2026-08-14) went
    # looking. TWO faults, neither of which could raise: `manual_adds` wants the
    # `.changes.csv`, and was handed the deck `.txt` — `csv.DictReader` over a deck
    # file finds no `Card` column and returns nothing at all; and it returns a LIST OF
    # ROWS, so iterating it yields dicts, which `_norm` would choke on inside a bare
    # `except`. Either alone empties the set. The result was a Cuts surface that
    # ranked hand-added cards with no "your call, not the tool's" flag on them —
    # exactly the protection Phase 9 was written to provide. Match on `name_keys`,
    # like every other membership test here (the ` // ` trap).
    # NB `stem` above is a BASENAME (it labels the report); the companion file needs
    # the full path, or this reads a changes.csv relative to the process's cwd.
    path_stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    try:
        manual = {k for r in deckcore.manual_adds(f"{path_stem}.changes.csv", days=None)
                  for k in mtglib.name_keys(r.get("name") or r.get("key") or "")}
    except Exception:
        manual = set()
    prot = set(prot) | deck_fit.protected_keys(deck_path, commander, enriched)
    out = deck_fit.cut_ranking(enriched, rep, ctx, refs, field,
                               protected=prot | manual, ranges=ranges,
                               cats=dict(rep.get("categories") or {}), limit=limit)
    out.update({"stem": stem, "commander": commander})
    return out


def _display_name(k):
    """Readable casing for a normalized (lowercase) card key when EDHREC's proper
    casing isn't available. str.title() capitalizes after apostrophes — it wrote
    "Urza'S Saga" into deck files and buylists — so only word starts are raised."""
    return " ".join(w[:1].upper() + w[1:] for w in k.split(" "))


def _commander_of(text):
    v = mtglib.deck_header(text, "Commander")
    return re.split(r"\s{2,}|\(", v)[0].strip() if v else ""


def _manual_add_keys(deck_path):
    """`name_keys` for every card the player added by hand, from `<stem>.changes.csv`.

    Returns an empty set on any failure: a missing or malformed companion must not
    take a deck out of the optimizer, it just means there is nothing to protect."""
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    try:
        return {k for r in deckcore.manual_adds(f"{stem}.changes.csv", days=None)
                for k in mtglib.name_keys(r.get("name") or r.get("key") or "")}
    except Exception:
        return set()


def _protected(deck_path, commander):
    """Cards we never cut: the commander, basics, and anything the player called out as
    part of the plan (the deck's notes.md) or curated in card_notes.csv."""
    keep = {mtglib._norm(commander)} | set(BASICS)
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    try:
        notes = open(f"{stem}.notes.md", encoding="utf-8").read().lower()
    except OSError:
        notes = ""
    # The Watch tab's storyboard is curated like the notes: a card a clip shows or
    # names is part of the plan, and cutting it would strand its scene. Riding the
    # notes text means every path below that honours notes honours clips too.
    featured = clipmod.featured_names(deck_path)
    if featured:
        notes += "\n" + "\n".join(featured).lower()
    try:
        # ONLY hand-written notes count as "the player values this card". The loader also
        # returns machine-drafted notes (card_notes.generated.csv) which cover most of the
        # collection — treating those as curated protected ~429 cards instead of ~51 and
        # silently froze the manabase pass, since almost every land had a generated note.
        for k, v in deckcore.load_card_notes().items():
            if not (isinstance(v, dict) and v.get("generated")):
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
    # BOTH keys per card (full name + front face): EDHREC emits both, so a raw-norm
    # set lets the same card count as "missing" under its other alias.
    in_deck = set()
    for c in mtglib.parse_deck(text):
        in_deck |= mtglib.name_keys(c.name)
    usage = deck_conflicts.scan(decks_dir, idx, skip=stem)
    committed = {}
    for n, v in usage.items():
        for ck in mtglib.name_keys(n):       # full + front face: either probe hits
            committed[ck] = v

    have, free, taken, unowned = [], [], [], []
    for k, inc in sorted(field.items(), key=lambda kv: -kv[1])[:top_n]:
        ref = mtglib.lookup(idx, k)
        # match on the resolved name too — one card can have several field keys
        if k in in_deck or (ref and mtglib._norm(ref.name) in in_deck):
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
            w.writerow([_display_name(name), "", tier, "",
                        f"{inc}% of {report['commander']} decks run this — "
                        f"your pool can't fill this slot."])
    return len(rows)


def append_buylist(deck_path, buy_swaps, commander=""):
    """Append buy recommendations to `<deck>.buylist.csv`, each mapped to the in-deck
    card it would replace. Existing rows are NEVER removed or reordered — hand-written
    entries survive. A re-proposed card's Replaces cell is only filled when it is blank
    or stale (names a card no longer in the deck); a target that is still in the deck
    is kept, because it may be a hand-picked one. Prices are left blank (no live feed).

    Runs even with NO buys to append: the stale-target sweep below is exactly what a
    deck needs after a run that proposes nothing, which is the common case for a deck
    already aligned with its field."""
    import csv
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    path = f"{stem}.buylist.csv"
    fields = ["Card", "Price", "Tier", "Replaces", "Reason"]
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8", newline="") as f:
            rd = csv.DictReader(f)
            existing_fields = rd.fieldnames or []
            rows = list(rd)
        # keep the file's column order but guarantee the standard columns exist —
        # a buylist without a Replaces column silently dropped every mapping and
        # made this function report changes forever (never idempotent).
        fields = list(existing_fields) + [c for c in fields if c not in existing_fields]
    existing = {mtglib._norm(r.get("Card") or ""): r for r in rows}
    changed = 0
    # A row NOT re-proposed this run keeps whatever Replaces it had — including a
    # card that has since left the deck, which turns "pull this when the buy
    # arrives" into a lie about a card the player no longer owns a slot for. Found
    # 2026-08-20: Drown in the Loch still pointed at Misdirection two swaps after
    # Misdirection was cut by hand. Blank the cell rather than guess a new target
    # (choosing one needs field data and the land/spell split this function cannot
    # see) — and never drop the row: hand-written buys must survive.
    try:
        in_deck = set()
        for c in mtglib.parse_deck(open(deck_path, encoding="utf-8").read()):
            in_deck |= mtglib.name_keys(c.name)
    except OSError:
        in_deck = None
    stale = 0
    if in_deck:
        for r in rows:
            cut = (r.get("Replaces") or "").strip()
            if cut and not (mtglib.name_keys(cut) & in_deck):
                r["Replaces"] = ""
                stale += 1
                changed += 1
    for cut, _inc_cut, add, inc_add, _kind in buy_swaps:
        k = mtglib._norm(add)
        if k in existing:
            cur = (existing[k].get("Replaces") or "").strip()
            # A target that still names a card IN THE DECK is a decision someone made
            # (often by hand: the beorn-the-fierce buylist, 2026-10-07, was curated
            # card by card and every apply overwrote it with field-driven picks). Only
            # fill a blank or stale cell; the sweep above has already blanked stale ones.
            if cur and in_deck and (mtglib.name_keys(cur) & in_deck):
                continue
            if cur != cut:
                existing[k]["Replaces"] = cut
                changed += 1
            continue
        row = {"Card": add, "Price": "", "Tier": "Core" if inc_add >= 65 else "Value",
               "Replaces": cut,
               "Reason": f"{inc_add}% of {commander or 'this commander'}'s decks run this."}
        rows.append(row)
        existing[k] = row
        changed += 1
    if changed:
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, restval="", extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return changed


def optimize(deck_path, coll, idx, decks_dir, refs=None, margin=25, apply=False,
             max_swaps=40, owned_only=False, include_buys=True, buy_threshold=55, by=""):
    """Return a report dict; writes the deck file when apply=True. `by` labels the
    `.changes.csv` rows an applying run writes (the app's signed-in person)."""
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
    ctx = deck_fit.deck_context(deck_path, a["enriched"], commander, field=field,
                                synergy=deck_fit.load_synergy(commander, idx))
    keep, notes = _protected(deck_path, commander)
    keep |= {c for c, d in deckcore.load_pins().items() if d == stem}   # pinned here = keep
    # A card the player ADDED by hand is never cut, and never offered as a buy's
    # Replaces target either. The symmetric rule for manual REMOVALS has been enforced
    # since 2026-08-11 (`removed_by_hand` below), and `cut_ranking`'s advisory surface
    # has unioned manual adds since Phase 9 — but THIS path, the one that actually
    # rewrites the deck and writes the buylist, never did. Reproduced 2026-08-20:
    # right after Grim Tutor was swapped into smaug-wicked-worm by hand, the same run
    # printed "manual adds (advisory — the optimizer never cuts these): Grim Tutor"
    # AND proposed pulling Grim Tutor for a bought Goldspan Dragon, with two more
    # owned candidates held off it only by the 25-point margin. The advisory line was
    # telling the truth about a different code path.
    keep |= _manual_add_keys(deck_path)

    deck = mtglib.parse_deck(text)
    in_deck = set()
    for c in deck:
        in_deck |= mtglib.name_keys(c.name)     # full-name AND front-face keys

    # Which pass owns each deck card — the land passes or the spell pass. Real type
    # data wins: analyze_deck's enriched cards carry the collection CSV's types AND
    # the deck's own .attrs.csv overlay. Where both are absent (name-only snapshot),
    # the deck file's type-exclusive section outranks the name heuristic — the player
    # filed the card there, and their word beats a substring guess (grounding rule #6).
    # This closed a real hole: the 2026-08-09 run cut Hidden Lair (a genuine land,
    # sitting under "# --- Lands ---") through the SPELL pass because "hidden lair"
    # matches nothing in _LAND_HINTS, and the writer then parked the incoming Aura on
    # its line inside the Lands section.
    enriched_by_key = {}
    for c in a["enriched"]:
        for ck in mtglib.name_keys(c.name):  # a front-face deck line must still find
            enriched_by_key.setdefault(ck, c)   # its own type data (named 'A // B')
    section_land = _section_type_signal(text)

    def is_land_in_deck(name):
        e = enriched_by_key.get(mtglib._norm(name))
        if e is not None and e.has_type_data:
            return e.is_land                 # CSV / .attrs.csv type: the truth
        sig = section_land.get(mtglib._norm(name))
        if sig is not None:
            return sig                       # the player's own filing
        return e.is_land if e is not None else mtglib._looks_like_land_by_name(name)

    # Honesty count for the report: cards whose pass assignment had NO type data
    # behind it. Absent data must be said out loud, not silently guessed around.
    untyped = sum(1 for c in deck
                  if not mtglib.is_basic(c.name)
                  and not ((e := enriched_by_key.get(mtglib._norm(c.name))) is not None
                           and e.has_type_data))
    usage = deck_conflicts.scan(decks_dir, idx, skip=stem)
    committed = {}
    for n, v in usage.items():
        for ck in mtglib.name_keys(n):       # full + front face: either probe hits
            committed[ck] = v["total"]
    # a copy you've PINNED to another deck is spoken for, however well it scores here
    reserved = deckcore.pinned_elsewhere(stem)
    identity = ctx.get("identity") or set()
    cats = dict(rep.get("categories", {}))

    def inc_of(name):
        # name_keys, not the bare key: EDHREC keys an adventure / prepare / MDFC card by
        # its FRONT face ("Beorn, Reluctant Host"), while a verified deck line carries the
        # full "A // B" name. A bare lookup read 52% as 0% and cut the card (2026-10-07).
        return max((field.get(k, 0) for k in mtglib.name_keys(name)), default=0)

    def field_knows(name):
        """True when the field actually HAS a row for this card.

        `inc_of` folds "the field plays this in 0% of decks" and "the field has
        never heard of this card" into the same 0. That is the empty-vs-absent
        distinction CLAUDE.md calls load-bearing, and printing an absent value
        as `0% field` is a measurement claim about data we do not have — so
        every surface that shows an inclusion number asks this first."""
        return any(k in field for k in mtglib.name_keys(name))

    def role_of(name):
        # The enriched card first — it carries the deck's own .attrs.csv types and
        # flags. A bare collection lookup can return a name-only owned_additions row
        # (role "other") or an older-FlagsVer row, so band accounting disagreed with
        # the deck's own category counts (30 mismatches on Beorn; 2026-10-11, R3).
        e = None
        for k in mtglib.name_keys(name):
            e = enriched_by_key.get(k)
            if e is not None:
                break
        r = e if (e is not None and e.has_type_data) else mtglib.lookup(idx, name)
        return deck_fit.primary_role(r) if r else None

    def band_ok_after(cut_role, add_role, counts):
        """Would swapping keep every touched role inside its template band?"""
        trial = dict(counts)
        if cut_role:
            trial[cut_role] = trial.get(cut_role, 0) - 1
        if add_role:
            trial[add_role] = trial.get(add_role, 0) + 1
        return all(lo <= trial.get(role, 0) <= hi
                   for role, (lo, hi) in ranges.items()
                   if role in (cut_role, add_role)), trial

    # ONE value function for both sides of a swap. Cuts always used this blend
    # (field inclusion OR our own fit engine, whichever rates the card higher);
    # adds used raw inclusion, so the two halves of the same comparison disagreed
    # about what "good" means — a 93%-inclusion generic outranked a high-synergy
    # archetype payoff both in the queue and at the margin gate. Same units now.
    # For an unowned candidate lookup fails -> fit 0 -> value == raw inclusion,
    # so buy-candidates rank exactly as before.
    def value_of(name, ref=None):
        return card_value(name, mtglib.lookup(idx, name) if ref is None else ref,
                          rep, ctx, refs, field)

    _fit_only = {}

    def fit_only(name):
        """Value with the field taken out: the units a no-field-row cut is valued in."""
        if name not in _fit_only:
            _fit_only[name] = deck_fit.card_value(name, mtglib.lookup(idx, name),
                                                  rep, ctx, refs, {})
        return _fit_only[name]

    # ---- candidates to bring IN ---------------------------------------------------------
    # Ranked by how much the field plays them, then by availability:
    #   free  = you own a spare copy            (always allowed)
    #   share = owned but committed to another deck — allowed unless owned_only; the player
    #           decides which deck gets the physical card at sleeving time
    #   buy   = not owned at all — considered when include_buys, but NEVER written into
    #           the 99 (2026-08-11, player request: a deck is built from what's owned).
    #           Buys pair against a real in-deck card and are APPENDED to the deck's
    #           .buylist.csv with Replaces = that card, so the list always answers
    #           "when this arrives, which card do I pull".
    # Lands stay in their own bucket: a land must replace a LAND, or the deck's
    # 37-land / 62-spell split silently drifts.
    # EDHREC's own Lands sections, for typing candidates the collection can't:
    # an unowned buy has no ref, and on a name-only snapshot an owned ref has no
    # Types. Without this the spell pass proposed Hallowed Fountain — a land the
    # name heuristic misses — as a BUY for Absorb. Pre-`lands` snapshots return
    # an empty set and the name heuristic carries on alone.
    field_lands = deck_fit.load_field_lands(commander, idx)

    # ---- the player's own removals are decisions, not cooldowns (2026-08-13) ----
    # "Never cut a manual add" has a symmetric rule: never RE-ADD a manual removal.
    # Its absence bit in live data: the player pulled Professor Hojo from cloud on
    # 2026-08-11 (recorded, Source=manual-replace), and the next rescore proposed
    # re-adding him over a fresh victim — the notes-file churn guards name the
    # VICTIM, so the pass just moved to a new one. The decision the player made was
    # about HOJO; `deckcore.manual_removals` reads it straight from the log, and a
    # later manual re-add lifts the hold (newest player action wins). Blocked
    # candidates are REPORTED (`manual_holds`), never silently dropped — the field
    # evidence stays visible, the decision stays the player's.
    removed_by_hand = deckcore.manual_removals(
        os.path.splitext(deck_path)[0] + ".changes.csv")
    manual_holds = []

    adds, land_adds, buy_adds, buy_land_adds = [], [], [], []
    for k, inc in field.items():
        if k in in_deck or mtglib.is_basic(k) or inc <= 0 or k in reserved:
            continue
        if deck_fit.is_banned(k):
            continue                      # never recommend a banned card (audit D1)
        if k in removed_by_hand:
            hold = removed_by_hand[k]
            manual_holds.append({"name": hold["name"], "inc": inc,
                                 "removed": hold["date"]})
            continue
        ref = mtglib.lookup(idx, k)
        if ref is None:
            # owned_only means "buildable from what I have today" — that rules out
            # buying as well as borrowing from another deck.
            if owned_only or not include_buys or inc < buy_threshold:
                continue
            name, avail = proper.get(k, _display_name(k)), "buy"
            # Layering, per CLAUDE.md: the field snapshot's own Lands sections beat
            # the NAME HEURISTIC, which is a last resort — for cards nothing else
            # knows, not a co-equal vote. Letting it vote here classified "Gimli of
            # the Glittering Caves" (a creature the field lists, absent from its
            # Lands sections) as a land on the word "Caves", and the buylist then
            # told the player to pull a real land for it — a nonland-for-land swap
            # the guardrails exist to forbid, shipped as advice (2026-08-20).
            # The field's silence is only informative when it HAS a row for the card
            # and a lands key to be absent from; otherwise fall through as before.
            if field_lands and field_knows(name):
                is_land = k in field_lands
            else:
                is_land = k in field_lands or mtglib._looks_like_land_by_name(name)
        else:
            if ref.identity and not (ref.identity <= identity):
                continue
            # Dedup on the RESOLVED name, not just the field key. Several keys can point
            # at one card (a DFC front face, or an EDHREC alias), and checking only `k`
            # let a card already in the deck come back in as a "new" add — Commander is
            # singleton, so that quietly made the deck illegal.
            if mtglib._norm(ref.name) in in_deck:
                continue
            free = ref.quantity - committed.get(k, 0) >= 1
            if not free and owned_only:
                continue
            name, avail = ref.name, ("free" if free else "share")
            is_land = ref.is_land if ref.has_type_data else (ref.is_land or k in field_lands)
        rank = {"free": 2, "share": 1, "buy": 0}[avail]
        if mtglib.name_keys(name) & in_deck:
            continue
        entry = (value_of(name), rank, name, avail, inc)
        if avail == "buy":
            (buy_land_adds if is_land else buy_adds).append(entry)
        else:
            (land_adds if is_land else adds).append(entry)
    adds.sort(reverse=True)

    # ---- reads: owned cards EDHREC doesn't list (spec-optimizer-judgment Phase C) -------
    # Every candidate above comes from the field's own list, so a card EDHREC has never
    # paired with this commander could not be proposed at all — Samut, Hazoret's
    # Champion (a new set, ~0% field) was the best Ur-Dragon add of 2026-10-14 and only
    # a read of its text found it. These are NOT proposals: no checkbox, never applied.
    # They are the candidates a Claude session reads against the deck's engine (the
    # sleeper audit). Ranked by deck_fit's own score with the field taken out; a free
    # copy, inside the identity, not a land, not held, not reserved, not banned.
    read_pool = []
    for ref in coll:
        k = mtglib._norm(ref.name)
        # A field-listed card BELOW the riser floor reaches no other surface: never a
        # proposal (the margin), never a riser (the floor) — Enlightened Tutor (10% for
        # the Ur-Dragon, owned, a Game Changer) fell through every net on 2026-10-14.
        # So reads are "EDHREC doesn't list it, or lists it under RISER_FLOOR".
        if (not ref.types or ref.is_land or mtglib.is_basic(ref.name)
                or mtglib.name_keys(ref.name) & in_deck
                or (field_knows(ref.name) and inc_of(ref.name) >= RISER_FLOOR)
                or k in reserved or k in removed_by_hand or deck_fit.is_banned(k)):
            continue
        if not ref.identity or not (ref.identity <= identity):
            continue                      # no identity data: never guess it is legal here
        if ref.quantity - committed.get(k, 0) < 1:
            continue
        fit = deck_fit.assess_card(ref, rep, ctx, refs)["score"]
        read_pool.append((fit, ref.name, role_of(ref.name) or "other",
                          inc_of(ref.name) if field_knows(ref.name) else None))
    read_pool.sort(key=lambda t: (-t[0], t[1]))
    land_adds.sort(reverse=True)
    buy_adds.sort(reverse=True)
    buy_land_adds.sort(reverse=True)

    # ---- candidates to cut: low VALUE, not protected, not a land ----
    # Value is deliberately NOT raw popularity. A premium card can be 0% for a commander
    # simply because the field's decks lean a different theme (Cloud's EDHREC data is all
    # Final Fantasy builds, which would happily cut Skyclave Apparition or Cleansing Nova).
    # So a card is worth keeping if the FIELD plays it *or* our own engine rates it highly.
    cuts = []
    for c in deck:
        k = mtglib._norm(c.name)
        # name_keys, not the bare key: `keep` mixes deck-spelled note names with
        # CANONICAL (front-face) pin keys, so a deck listing "A // B" must still match
        # a pin stored as "a". Strict widening — same-spelling keys are in name_keys.
        if (mtglib.name_keys(c.name) & keep) or mtglib.is_basic(c.name):  # snow too
            continue
        # The enriched card first: it carries the deck's own .attrs.csv types. A bare
        # collection lookup can return a NAME-ONLY row (owned_additions.txt has no type
        # data), which scored a typed 10/7 like Gigantic Big Bear as value 0 and put it
        # up for a fit-driven cut (beorn-the-fierce, 2026-10-07).
        e = enriched_by_key.get(k)
        ref = e if (e is not None and e.has_type_data) else mtglib.lookup(idx, c.name)
        if not ref or is_land_in_deck(c.name):
            continue                      # lands handled by the manabase pass
        if deck_fit.named_in_notes(c.name, notes):
            continue                      # named in the player's own game plan
        cuts.append((value_of(c.name, ref), inc_of(c.name), c.name))
    cuts.sort()                           # least valuable first

    # ---- the role-repair gate (2026-08-13; recalibrated same day) -----------------------
    # There is no separate "repair" function to gate: role repair reaches this loop
    # THROUGH `value_of`. deck_fit's Role-need component pays ROLE_PTS_SHORTAGE (26)
    # below target and ROLE_PTS_DEPTH (14) over — a 12-point swing `value_of` doubles
    # to 24, deliberately ONE POINT UNDER the default margin (the Phase-12 cap; a
    # tripwire test pins spread*2 < margin). So today template pressure alone cannot
    # manufacture a swap. Under the ORIGINAL 30/12 points it could — an 18-point swing
    # doubled to 36 — which is how the first typed previews (2026-08-12, none applied)
    # produced these:
    #   Ganax, Astral Hunter (27%) -> Mana Drain (20%)      · ur-dragon
    #   Wall Crawl (41%)           -> Masked Meower (18%)   · cosmic
    #   Snap (20%)                 -> Wayfarer's Bauble (10%)  · iron-man
    #   Clever Impersonator (20%)  -> Sword of the Animist (9%) · iron-man
    # Every one cuts a card the field plays MORE than the one arriving — the exact
    # inversion the >=25-point anti-churn margin exists to prevent.
    #
    # So the field keeps a veto: `inc_add < inc_cut` is refused. Note this can ONLY bite
    # on a fit-driven (i.e. repair-driven) swap. Where the field itself supplies the
    # margin, value_of(add) == inc_add and value_of(cut) >= inc_cut, so clearing the
    # margin already implies inc_add >= inc_cut + margin. A high-fit, low-inclusion
    # upgrade over a card the field plays LESS is still allowed, unchanged.
    #
    # Fix direction 3 from the finding — "suppress repair on hand-ratified decks (recent
    # Source=manual-replace in .changes.csv)" — was DELIBERATELY NOT TAKEN. This veto
    # plus the archetype-aware template kill every observed proposal at the source, and a
    # per-deck suppression rule would have made the optimizer's behaviour depend on edit
    # history that the player can't see from the report.
    #
    # The deck's own template: default ranges, widened by its `# Archetype:` header.
    ranges, archetype_unknown = role_ranges_with_unknown(ctx.get("archetype"))

    # `swaps` keeps its 5-tuple shape (several consumers unpack it positionally);
    # `swaps_detail` carries the SAME swaps with both units spelled out, so the field
    # veto is auditable from a preview instead of taken on trust.
    # Roles whose CURRENT count sits outside the template. The band gate below can
    # never move such a role — a swap touching it lands outside the band whichever
    # way it goes (ramp-for-ramp holds the count, ramp-for-other shifts it by one and
    # it is still outside), so the gate rejects every candidate and the run reports
    # zero swaps. That is a FREEZE, not alignment, and the summary must say so: the
    # deck reading "already aligned" at 10/25 field overlap is what hid tifa-lockhart's
    # six field-superior swaps for the deck's whole life. The freeze itself is correct
    # and deliberately kept — see the reporting note in `main` — because softening the
    # gate would let template pressure churn a hand-ratified deck toward the blind
    # band. The escape hatch is a ratified `_ARCHETYPE_ROLE_RANGE` entry.
    out_of_band = {role: (cats.get(role, 0), lo, hi)
                   for role, (lo, hi) in ranges.items()
                   if not (lo <= cats.get(role, 0) <= hi)}

    swaps, swaps_detail, used_add, used_cut = [], [], set(), set()
    band_blocked = {}                     # role -> {add names it froze}
    for val_add, _rank, add_name, avail, inc_add in adds:
        if len(swaps) >= min(len(cuts), max_swaps):
            break
        add_role = role_of(add_name)
        for val_cut, inc_cut, cut_name in cuts:
            ck = mtglib._norm(cut_name)
            if ck in used_cut or mtglib._norm(add_name) in used_add:
                continue
            if val_add - val_cut < margin:
                gm = min(margin, GENERIC_MARGIN)
                if not (_generic_pair(cut_name, add_name, ctx)
                        and field_knows(cut_name) and field_knows(add_name)
                        and inc_add - inc_cut >= gm and val_add - val_cut >= gm):
                    continue              # not a clear enough upgrade, like-for-like units
            if inc_add < inc_cut:
                continue                  # role repair may not overrule the field (above)
            if (not field_knows(cut_name) and inc_add < STRONG_CONSENSUS
                    and fit_only(add_name) - val_cut < margin):
                # The field has NO row for the cut, so its value is fit-only, while the
                # add's value may be its field %. That compares different units, and the
                # veto above compares against a fake 0. Make the add win in the cut's own
                # units. Without this, Fog (35% field, weak fit) was proposed over Carnage
                # Tyrant, Hulking Raptor and Ghalta the Unstoppable in beorn-the-fierce,
                # whose newer cards EDHREC has little data on (2026-10-07). A missing
                # row can mean "rarely played" OR "too new to have data", so a card the
                # field plays in most decks (STRONG_CONSENSUS) still gets through.
                continue
            cut_role = role_of(cut_name)
            # keep role counts inside the template
            trial = dict(cats)
            if cut_role:
                trial[cut_role] = trial.get(cut_role, 0) - 1
            if add_role:
                trial[add_role] = trial.get(add_role, 0) + 1
            ok = True
            for role, (lo, hi) in ranges.items():
                if role in (cut_role, add_role) and not (lo <= trial.get(role, 0) <= hi):
                    ok = False
                    break
            if not ok:
                # Only a role that was ALREADY outside its band is a deadlock. A
                # rejection because the trial would push an IN-band role out is the
                # gate doing its normal job and must not be reported as frozen.
                for role in {cut_role, add_role} & set(out_of_band):
                    band_blocked.setdefault(role, set()).add(add_name)
                continue
            cats = trial
            swaps.append((cut_name, val_cut, add_name, inc_add, avail))
            swaps_detail.append({"cut": cut_name, "cut_value": val_cut, "cut_inc": inc_cut,
                                 "add": add_name, "add_value": val_add, "add_inc": inc_add,
                                 "avail": avail,
                                 # absent field data is NOT a measured 0% — see
                                 # `field_knows`. A swap where the field has no
                                 # row for the cut card was decided by FIT alone
                                 # (role repair), and the preview must say so
                                 # rather than implying the field endorsed it.
                                 "cut_field_known": field_knows(cut_name),
                                 "add_field_known": field_knows(add_name),
                                 **_lift_detail(cut_name, add_name, ctx)})
            used_cut.add(ck)
            used_add.add(mtglib._norm(add_name))
            break

    # An add that was blocked on one cut but succeeded against another is not frozen;
    # only report what never made it in. Sets are materialised here so both return
    # sites (the no-field early return and the main result) share one shape.
    role_deadlock = {
        "out_of_band": [{"role": r, "count": n, "lo": lo, "hi": hi}
                        for r, (n, lo, hi) in sorted(out_of_band.items())],
        "blocked": [{"role": r, "adds": sorted(a for a in names
                                               if mtglib._norm(a) not in used_add)}
                    for r, names in sorted(band_blocked.items())
                    if any(mtglib._norm(a) not in used_add for a in names)],
    }

    # ---- advisory: field risers the margin gate suppressed ------------------------------
    # The margin gate exists to stop churn, but it also silences a NEW card the field is
    # still adopting (a 30%-inclusion arrival vs an 11% incumbent is a 19-point gain:
    # blocked). Surface those, never act on them: owned with a free copy, would beat the
    # deck's current weakest cut, just not by enough to swap automatically. The player
    # decides; a manual add is then protected forever.
    #
    # `inc_add >= inc_cut` is THE SAME field veto the swap loop applies, and it belongs
    # here for the same reason. Found by the Phase 8 acceptance run against the real
    # collection (2026-08-14): the veto was guarding what the optimizer DOES and not what
    # it ADVISES, so cosmic-spider-man's preview offered Sun-Spider (25%) and Spider-Man,
    # To the Rescue (29%) as "1 pt short of auto-swap" over Wall Crawl (41%) — the exact
    # card, and the exact inversion, the whole churn finding was about. The machine
    # refused the swap and then recommended the player make it by hand. Advice the tool
    # would not take itself is worse than no advice.
    risers = []
    open_cuts = [t for t in cuts if mtglib._norm(t[2]) not in used_cut]
    if open_cuts:
        val_cut, inc_cut, cut_name = open_cuts[0]
        for val_add, _rank, add_name, avail, inc_add in adds:
            if len(risers) >= 6:
                break
            if avail != "free" or mtglib._norm(add_name) in used_add:
                continue
            gap = val_add - val_cut
            if 0 < gap < margin and inc_add >= RISER_FLOOR and inc_add >= inc_cut:
                risers.append({"add": add_name, "add_inc": inc_add,
                               "over": cut_name, "over_inc": inc_cut,
                               "gap": round(gap)})

    # ---- reads, finalised: never a card this run already proposes or flags as a riser.
    # The fit engine leans on whichever role the deck is short of (Beorn's first draft
    # was five board wipes), so at most READS_PER_ROLE per role keeps the list a spread
    # of ideas, and READS_MIN_FIT drops the filler.
    # Two kinds of evidence, two lanes: a card the field lists RARELY carries a real
    # (small) field %, so up to READS_RARE_LIMIT of those rank by it — the fit heuristic
    # undervalues tutors and Enlightened Tutor lost its place to eight role-fillers —
    # and cards the field never lists rank by fit alone, up to READS_LIMIT.
    taken = used_add | {mtglib._norm(x["add"]) for x in risers}
    # Rarely-listed cards rank by LIFT first: 15% of decks at 7x the colour baseline is a
    # stronger sleeper than 19% at 1.2x (a staple that just isn't popular here). Inclusion
    # under LIFT_MIN_INCLUSION earns no lift credit — fringe picks rank by inclusion.
    def _rare_lift(n, inc):
        lf = deck_fit.lift_of(n, ctx)
        return lf["lift"] if lf and inc >= deck_fit.LIFT_MIN_INCLUSION else 0
    rare = sorted((t for t in read_pool
                   if t[3] is not None and mtglib._norm(t[1]) not in taken),
                  key=lambda t: (-_rare_lift(t[1], t[3]), -t[3], -t[0], t[1]))[:READS_RARE_LIMIT]
    reads = []
    for f, n, ro, inc in rare:
        lf = deck_fit.lift_of(n, ctx)
        reads.append({"name": n, "fit": f, "role": ro, "field": inc,
                      "lift": lf["lift"] if lf else None})
    per_role, silent = {}, []
    for f, n, ro, inc in read_pool:
        if f < READS_MIN_FIT or len(silent) >= READS_LIMIT:
            break
        if (inc is not None or mtglib._norm(n) in taken
                or per_role.get(ro, 0) >= READS_PER_ROLE):
            continue
        per_role[ro] = per_role.get(ro, 0) + 1
        silent.append({"name": n, "fit": f, "role": ro, "field": None})
    reads += silent

    # ---- manabase passes. Both need field data: without it every land scores 0 and we
    # can't tell Command Tower from a bad tapland, so we leave the manabase alone. -------
    land_swaps, land_detail = [], []
    lands = [c for c in deck if mtglib.lookup(idx, c.name) and is_land_in_deck(c.name)]
    if not field:
        return {"stem": stem, "commander": commander, "swaps": swaps,
                "land_swaps": [], "buy_swaps": [], "field_size": 0, "risers": risers,
                "untyped": untyped, "archetype": list(ctx.get("archetype") or []),
                "archetype_unknown": archetype_unknown, "manual_holds": manual_holds,
                "reads": reads,
                "role_ranges": ranges, "swaps_detail": swaps_detail,
                "role_deadlock": role_deadlock}

    # ---- the fetch ledger (spec-mana-intelligence Phase E) ------------------------------
    # Both land passes and the buy pairing consult ONE running ledger, because they
    # share victims through used_land: pass 1 can schedule the cut of one Swamp-typed
    # land and pass 2 the conversion of the other in the same run, each individually
    # "leaving one". `type_counts` tracks copies of each basic land type in the deck;
    # `demanded[type]` counts fetcher CARDS whose fetch:* tokens want it — an accepted
    # cut of a fetcher retracts its demand, so a stale demand can't block cuts of
    # lands nobody can fetch any more. A land with no type data skips the guard (it is
    # already in the `untyped` honesty count — never guess, the Hidden Lair rule).
    import manabase as _mb
    type_counts, demanded, fetcher_of = {}, {}, {}
    for c in deck:
        ref = mtglib.lookup(idx, c.name)
        if ref is None:
            continue
        # Types are counted regardless of flag vocabulary — subtypes aren't
        # versioned, only flag TRUST is. Gating the counts on flags_ver would
        # undercount types on a mixed-enrichment collection and over-block.
        if ref.is_land and ref.has_type_data:
            for ty in _mb._land_types(ref):
                type_counts[ty] = type_counts.get(ty, 0) + c.quantity
        if ref.flags_ver < 2:
            continue                      # v1 flags: no fetch demand to trust
        for tok in ref.flags:
            ty = None
            if tok.startswith("fetch:basic-"):
                ty = tok[len("fetch:basic-"):]
            elif tok.startswith("fetch:") and tok not in ("fetch:basic", "fetch:land"):
                ty = tok[len("fetch:"):]
            if ty:
                demanded[ty] = demanded.get(ty, 0) + 1
                fetcher_of.setdefault(ty, []).append(ref.name)

    land_guard = []

    def _guard_blocks(cut_name):
        """The types this cut would strand, with the fetchers that need them —
        or an empty list if the cut is safe / unknowable."""
        ref = mtglib.lookup(idx, cut_name)
        if ref is None or not ref.has_type_data:
            return []                     # unknown types: report via `untyped`, never guess
        deck_qty = next((c.quantity for c in deck
                         if mtglib.name_keys(c.name) & mtglib.name_keys(cut_name)), 1)
        out = []
        for ty in _mb._land_types(ref):
            if demanded.get(ty, 0) > 0 and type_counts.get(ty, 0) - deck_qty <= 0:
                out.append((ty, fetcher_of.get(ty, [])))
        return out

    def _ledger_cut(cut_name):
        """Record an ACCEPTED cut: its land types leave the pool, and — if the cut
        card was itself a fetcher — its demand goes with it."""
        ref = mtglib.lookup(idx, cut_name)
        if ref is None:
            return
        deck_qty = next((c.quantity for c in deck
                         if mtglib.name_keys(c.name) & mtglib.name_keys(cut_name)), 1)
        if ref.is_land and ref.has_type_data:
            for ty in _mb._land_types(ref):
                type_counts[ty] = type_counts.get(ty, 0) - deck_qty
        for tok in ref.flags:
            ty = (tok[len("fetch:basic-"):] if tok.startswith("fetch:basic-") else
                  tok[len("fetch:"):] if tok.startswith("fetch:")
                  and tok not in ("fetch:basic", "fetch:land") else None)
            if ty and demanded.get(ty, 0) > 0:
                demanded[ty] -= 1

    def _ledger_add(add_name):
        ref = mtglib.lookup(idx, add_name)
        if ref is not None and ref.is_land and ref.has_type_data:
            for ty in _mb._land_types(ref):
                type_counts[ty] = type_counts.get(ty, 0) + 1

    # ---- the manabase pass: lands are valued by what they DO for this deck -----------
    # (docs/spec-optimizer-judgment.md, Phase A, 2026-10-14). This replaces two passes:
    # "upgrade a weak land to one the field plays (>= 25 inclusion points)" and "run
    # basics" — a quota of round(lands x (0.42 - 0.04 x (colours-1))) basics justified
    # by basics' 98-99% inclusion. That inclusion only says nearly every deck runs SOME
    # basics, never how many, and the quota traded untapped duals for basics in
    # five-colour decks (nine proposed on the 2026-10-14 Ur-Dragon rebuild, 8+ on
    # Y'shtola). Now each land gets `manabase.land_mana_score` — the deck's colours it
    # makes, weighted by the deck's own pip demand, minus a tapped penalty, plus a bonus
    # for land types the deck's fetchers ask for — and a swap needs the incoming land to
    # be better by LAND_SCORE_MARGIN colour-equivalents. EDHREC inclusion is consulted
    # twice and decides nothing: it breaks ties, and a land the field runs in
    # >= LAND_FIELD_KEEP % of decks is kept, because that usually means an ability the
    # mana score can't see (Bojuka Bog's exile, a creature land).
    import manabase as _mb2
    weights = _mb2.color_weights((a.get("mana") or {}).get("colors"), identity)
    want_types = {t for t, n in demanded.items() if n > 0}

    def _land_ref(name):
        e = enriched_by_key.get(mtglib._norm(name))
        if e is not None and e.has_type_data:
            return e
        return mtglib.lookup(idx, name)

    def _score(name, ref=None):
        ref = ref if ref is not None else _land_ref(name)
        if ref is None:
            if mtglib.is_basic(name):          # basics are unlimited and may be untracked
                ref = mtglib.Card(name=name, quantity=1)
            else:
                return None
        return _mb2.land_mana_score(ref, weights, want_types)

    # Cut candidates: nonbasic, unprotected (commander/pins/manual adds, curated notes,
    # the deck's own .notes.md — matched on FOLDED text, so a name wrapped across two
    # lines still counts; a raw substring test let "Canopy\nVista" through), scorable,
    # and not a land the field leans on. `weak_lands` keeps its (inclusion, name) shape
    # for the buy pairing below but is ordered worst-for-the-deck first.
    scored_cuts = []
    for c in lands:
        if (mtglib.is_basic(c.name) or (mtglib.name_keys(c.name) & keep)
                or deck_fit.named_in_notes(c.name, notes)):
            continue
        s = _score(c.name)
        if s is None or inc_of(c.name) >= LAND_FIELD_KEEP:
            continue
        scored_cuts.append((s, inc_of(c.name), c.name))
    scored_cuts.sort()
    weak_lands = [(inc, name) for _s, inc, name in scored_cuts]

    # Add candidates: owned lands with a FREE copy, inside the identity, not reserved,
    # not held by a manual removal, scorable — whether or not EDHREC lists them (the
    # field no longer gates which lands are considered). Sharing a land with another
    # deck is never proposed: the free pool almost always has an equal land, and a
    # shared copy turns a mana upgrade into a sleeving conflict (the Ur-Dragon rebuild
    # took Captain America's only Unclaimed Territory this way). Basics of each colour
    # are unlimited candidates, so a tapped off-colour land can always become a basic.
    land_cands = []
    for ref in coll:
        k = mtglib._norm(ref.name)
        if (not ref.is_land or not ref.has_type_data or mtglib.is_basic(ref.name)
                or mtglib.name_keys(ref.name) & in_deck or k in reserved
                or k in removed_by_hand or deck_fit.is_banned(k)):
            continue
        if ref.identity and not (ref.identity <= identity):
            continue
        if ref.quantity - committed.get(k, 0) < 1 or not _mb2.land_is_reliable_add(ref):
            continue
        s = _score(ref.name, ref)
        if s is not None:
            land_cands.append([s, inc_of(ref.name), ref.name, False])
    for col in sorted(weights):
        b = deckcore.BASIC_OF_COLOR[col]
        s = _score(b)
        if s is not None:
            land_cands.append([s, inc_of(b), b, True])
    land_cands.sort(key=lambda t: (-t[0], -t[1], t[2]))

    used_land, used_land_add = set(), set()
    for s_cut, _inc_cut, cut_name in scored_cuts:
        ck = mtglib._norm(cut_name)
        if ck in used_land:
            continue
        for cand in land_cands:
            s_add, _inc_add, add_name, unlimited = cand
            if s_add - s_cut < LAND_SCORE_MARGIN:
                break                     # sorted best-first: nothing later clears it
            akeys = mtglib.name_keys(add_name)
            if not unlimited and akeys & used_land_add:
                continue
            blocked = _guard_blocks(cut_name)
            if blocked:
                for ty, who in blocked:
                    land_guard.append({"kept": cut_name, "type": ty, "for": who})
                used_land.add(ck)         # held for its type
                break
            land_swaps.append((cut_name, add_name, "free"))
            land_detail.append({"cut": cut_name, "cut_score": s_cut, "add": add_name,
                                "add_score": s_add})
            used_land.add(ck)
            if not unlimited:
                used_land_add |= akeys
            _ledger_cut(cut_name)
            _ledger_add(add_name)
            if unlimited:
                ity = add_name.lower()
                type_counts[ity] = type_counts.get(ity, 0) + 1
            break

    # ---- buys: recommended, never written into the 99 -----------------------------------
    # Each buy pairs one-to-one with a card that STAYS in the deck (a cut the owned
    # passes didn't consume, or a weak land the land pass left) so the buylist's
    # Replaces column always names a real card to pull when the purchase arrives.
    buy_swaps, used_buy, used_buy_add = [], set(), set()
    for val_add, _rank, add_name, avail, inc_add in buy_adds:
        akeys = mtglib.name_keys(add_name)   # a DFC arrives under two field keys —
        if akeys & used_buy_add:             # without this it hit the buylist twice
            continue
        for val_cut, inc_cut, cut_name in cuts:
            ck = mtglib._norm(cut_name)
            if ck in used_cut or ck in used_buy or val_add - val_cut < margin:
                continue
            if inc_add < inc_cut:
                continue     # same field veto as the owned pass: "buy this 9% card to
                             # replace your 20% card" is bad advice, not a shopping list
            # Same role-band gate the owned pass applies: a Replaces target the tool
            # would refuse to cut itself (Farseek, with ramp AT its floor) is advice
            # it wouldn't take (2026-10-11 audit, R4).
            if not band_ok_after(role_of(cut_name), role_of(add_name), cats)[0]:
                continue
            buy_swaps.append((cut_name, inc_cut, add_name, inc_add, "spell"))
            used_buy.add(ck)
            used_buy_add |= akeys
            break
    for _val, _rank, add_name, avail, inc_add in buy_land_adds:
        akeys = mtglib.name_keys(add_name)
        if akeys & used_buy_add:
            continue
        for inc_cut, cut_name in weak_lands:
            ck = mtglib._norm(cut_name)
            if ck in used_land or ck in used_buy or inc_add - inc_cut < margin:
                continue
            if _guard_blocks(cut_name):
                # Advice the tool would not take itself is worse than none (the
                # riser-veto lesson, 2026-08-14): a Replaces target the land
                # passes refused to cut may not be recommended for pulling either.
                continue
            buy_swaps.append((cut_name, inc_cut, add_name, inc_add, "land"))
            used_buy.add(ck)
            used_buy_add |= akeys
            break

    try:
        import edhrec
        _names = edhrec.field_names(commander, idx)
    except Exception:
        _names = {}
    result = {"stem": stem, "commander": commander, "swaps": swaps,
              "field_coverage": field_coverage(field, _names, in_deck, idx, usage,
                                               commander),
              "land_swaps": land_swaps, "land_detail": land_detail,
              "buy_swaps": buy_swaps, "land_guard": land_guard,
              "field_size": len(field), "risers": risers, "untyped": untyped,
              "archetype": list(ctx.get("archetype") or []),
              "archetype_unknown": archetype_unknown, "manual_holds": manual_holds,
                "reads": reads,
              "role_ranges": ranges, "swaps_detail": swaps_detail,
              "role_deadlock": role_deadlock}
    if apply and (swaps or land_swaps):
        _write(deck_path, swaps, land_swaps)
        record_changes(deck_path, swaps, land_swaps, by=by)
    if apply:
        # _tidy on EVERY apply, not only when this pass wrote swaps. It is idempotent
        # and cheap, and gating it on our own changes left everyone else's misfiles
        # in place forever: a manual swap writes in place (webapp replace, session
        # edits), and the very next `--apply` printed "already aligned — no changes"
        # while Grim Tutor sat under Creatures (2026-08-20; one of 19 misfiled cards
        # found across 7 decks the day the player's phone surfaced one).
        _tidy(deck_path, idx)
        result["illegal"] = singleton_violations(deck_path)
    if apply and buy_swaps:
        result["buylist_appended"] = append_buylist(deck_path, buy_swaps, commander)
    return result


def proposal_key(kind, cut, add):
    """The stable id of one proposed swap, as the ⚡ review form submits it."""
    return f"{kind}|{cut}|{add}"


FIELD_TOP = 25


def field_coverage(field, names, in_deck, idx, usage, commander, top=FIELD_TOP):
    """The field's top-N cards for this commander, split three ways: in the deck, owned
    but out (free, or held by which decks), and not owned.

    The validation number is coverage of what the player OWNS (2026-10-15, the
    deck-flow review): raw top-25 overlap punishes a deck for cards nobody owns, which
    is a buylist fact, not a build fault. Every owned-but-out card should have a
    reason in the deck's notes; this list is where a session reads them off. None
    without field data."""
    if not field:
        return None
    ck = mtglib.name_keys(commander) if commander else set()
    keys = [k for k, _ in sorted(field.items(), key=lambda kv: (-kv[1], kv[0]))
            if not mtglib.is_basic(k) and k not in ck][:top]
    held, total = {}, {}
    for n, v in (usage or {}).items():
        for kk in mtglib.name_keys(n):
            held[kk] = sorted(v.get("decks") or {})
            total[kk] = v.get("total", 0)
    rows = {"in_deck": [], "owned_out": [], "not_owned": []}
    for k in keys:
        name = (names or {}).get(k) or k
        if k in in_deck:
            rows["in_deck"].append(name)
            continue
        ref = mtglib.lookup(idx, name)
        if ref is None or (ref.quantity or 0) <= 0:
            rows["not_owned"].append(name)
            continue
        rows["owned_out"].append({"name": ref.name, "inc": field[k],
                                  "free": (ref.quantity or 0) - total.get(k, 0) > 0,
                                  "held_by": held.get(k, [])})
    owned = len(rows["in_deck"]) + len(rows["owned_out"])
    return {"top": len(keys), "n_in": len(rows["in_deck"]), "owned": owned,
            "owned_pct": round(100 * len(rows["in_deck"]) / owned) if owned else None,
            **rows}


def _generic_pair(cut, add, ctx):
    """True when lift says BOTH cards are generic for this commander (under
    GENERIC_LIFT, both measured). Unmeasured lift is never generic: no data, no discount."""
    cl, al = deck_fit.lift_of(cut, ctx), deck_fit.lift_of(add, ctx)
    return (cl is not None and al is not None
            and cl["lift"] < GENERIC_LIFT and al["lift"] < GENERIC_LIFT)


def _lift_detail(cut, add, ctx):
    """Lift evidence for one swap (deck_fit.commander_lift): each side's multiplier, and
    whether the swap trades a commander-specific card for a generic one. Evidence only:
    the flag never removes a proposal, it tells the reader where to look."""
    cl, al = deck_fit.lift_of(cut, ctx), deck_fit.lift_of(add, ctx)
    cut_lift = cl["lift"] if cl else None
    add_lift = al["lift"] if al else None
    trades = (cut_lift is not None and cut_lift >= deck_fit.LIFT_SIGNATURE
              and (add_lift is None or add_lift < TRADE_GENERIC_LIFT))
    return {"cut_lift": cut_lift, "add_lift": add_lift, "trades_specific": trades}


def proposals(r):
    """The swaps a preview report proposes, flattened for a review surface: one dict
    per swap with its evidence (spec-optimizer-judgment Phase B). Nothing here decides;
    the player ticks, `apply_chosen` writes."""
    out = []
    detail = {(d["cut"], d["add"]): d for d in (r.get("swaps_detail") or [])}
    for s in r.get("swaps") or []:
        cut, _vc, add, inc_add, avail = s
        d = detail.get((cut, add), {})
        out.append({"key": proposal_key("spell", cut, add), "kind": "spell",
                    "cut": cut, "add": add, "avail": avail,
                    "cut_inc": d.get("cut_inc"), "add_inc": inc_add,
                    "cut_field_known": d.get("cut_field_known", True),
                    "add_field_known": d.get("add_field_known", True),
                    "cut_value": d.get("cut_value"), "add_value": d.get("add_value"),
                    "cut_lift": d.get("cut_lift"), "add_lift": d.get("add_lift"),
                    "trades_specific": d.get("trades_specific", False)})
    ldet = {(d["cut"], d["add"]): d for d in (r.get("land_detail") or [])}
    for cut, add, avail in r.get("land_swaps") or []:
        d = ldet.get((cut, add), {})
        out.append({"key": proposal_key("land", cut, add), "kind": "land",
                    "cut": cut, "add": add, "avail": avail,
                    "cut_score": d.get("cut_score"), "add_score": d.get("add_score")})
    return out


# ---- verdicts: a session's read, saved for the phone (deck-flow review bundle B) ------
# The app makes no AI calls (player decision 2026-10-14). A Claude session reads each
# proposal and read against the engine; `--verdict` saves that read beside the deck as
# `<stem>.verdicts.json`, the repo sync carries it to the server, and the ⚡ page shows it
# next to the SAME swap. A verdict is keyed by the proposal key (reads: "read|<name>")
# and only ever written for a key the optimizer proposes right now, so the file cannot
# hold a judgment about a swap nobody suggested.
VERDICTS = ("swap", "skip", "bench", "wishlist")


def verdicts_path(deck_path):
    return os.path.splitext(deck_path)[0] + ".verdicts.json"


def read_key(name):
    return "read|" + name


def load_verdicts(deck_path):
    """{key: {"verdict", "why", "date", "by"}}; {} when the file is absent or broken
    (a bad file costs the annotations, never the page)."""
    try:
        with open(verdicts_path(deck_path), encoding="utf-8") as f:
            raw = (json.load(f) or {}).get("verdicts") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    return {k: v for k, v in raw.items()
            if isinstance(v, dict) and v.get("verdict") in VERDICTS and v.get("why")}


def record_verdicts(deck_path, r, entries, today=None, by="a Claude session"):
    """Save (key, verdict, why) entries for keys CURRENT in report `r`. Returns
    (written keys, stale keys). Raises ValueError on an unknown verdict or empty reason:
    a verdict without its reason is exactly the unexplained call this replaces."""
    import datetime
    current = {p["key"] for p in proposals(r)} | {read_key(x["name"])
                                                  for x in r.get("reads") or []}
    have = load_verdicts(deck_path)
    written, stale = [], []
    for key, verdict, why in entries:
        verdict, why = (verdict or "").strip().lower(), (why or "").strip()
        if verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}: {verdict!r}")
        if not why:
            raise ValueError(f"a verdict needs its reason: {key}")
        if key not in current:
            stale.append(key)
            continue
        have[key] = {"verdict": verdict, "why": why, "by": by,
                     "date": today or datetime.date.today().isoformat()}
        written.append(key)
    if written:
        with open(verdicts_path(deck_path), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"version": 1, "verdicts": dict(sorted(have.items()))}, f,
                      ensure_ascii=False, indent=1)
            f.write("\n")
    return written, stale


def attach_verdicts(props, reads, verdicts):
    """Copies of `props` and `reads` with each one's saved verdict (or None), plus the
    count of saved verdicts whose swap is no longer proposed. Those are never shown
    against a different swap."""
    verdicts = verdicts or {}
    props = [dict(p, verdict=verdicts.get(p["key"])) for p in props]
    reads = [dict(x, verdict=verdicts.get(read_key(x["name"]))) for x in reads]
    live = {p["key"] for p in props} | {read_key(x["name"]) for x in reads}
    return props, reads, sum(1 for k in verdicts if k not in live)


def review_payload(r, verdicts=None):
    """Everything a reviewer needs from one report, JSON-safe (`--json`, the assess
    packet): the checkbox proposals with their evidence, the field-silent `reads`, and
    the advisories. Field numbers are evidence here, never a verdict (Phase C)."""
    props, reads, stale = attach_verdicts(proposals(r), r.get("reads") or [], verdicts)
    return {"stem": r.get("stem"), "commander": r.get("commander"),
            "field_size": r.get("field_size", 0),
            "proposals": props, "reads": reads, "verdicts_stale": stale,
            "risers": r.get("risers") or [], "manual_holds": r.get("manual_holds") or [],
            "land_guard": r.get("land_guard") or [],
            "buys": [{"add": b[2], "add_inc": b[3], "replaces": b[0], "kind": b[4]}
                     for b in r.get("buy_swaps") or []],
            "role_deadlock": r.get("role_deadlock") or {},
            "role_ranges": {k: list(v) for k, v in (r.get("role_ranges") or {}).items()},
            "untyped": r.get("untyped", 0),
            "field_coverage": r.get("field_coverage")}


def apply_chosen(deck_path, coll, idx, decks_dir, chosen, refs=None, by=""):
    """Write ONLY the swaps the player approved (the ⚡ review, Phase B).

    The proposal set is recomputed here, never trusted from the form: a key that no
    longer matches a current proposal (the deck changed since the page was drawn, or
    the form was tampered with) is reported as `stale` and skipped. A subset can also
    break a role band the full run kept — the run validates each swap against the
    counts AFTER the swaps before it — so the chosen swaps are re-checked in order and
    a failing one is reported as `held`, not written. Then the same writer, change log
    (`Source` free/share, so Undo / Undo all work unchanged), `_tidy`, singleton check
    and buylist append an applying run always used."""
    refs = refs or power.load_refs()
    r = optimize(deck_path, coll, idx, decks_dir, refs=refs, apply=False)
    chosen = set(chosen or ())
    swaps = [s for s in r.get("swaps") or []
             if proposal_key("spell", s[0], s[2]) in chosen]
    land_swaps = [s for s in r.get("land_swaps") or []
                  if proposal_key("land", s[0], s[1]) in chosen]
    known = {p["key"] for p in proposals(r)}
    stale = sorted(chosen - known)

    a = deckcore.analyze_deck(deck_path, coll)
    by_key = {}
    for c in a["enriched"]:
        for k in mtglib.name_keys(c.name):
            by_key.setdefault(k, c)

    def _role(name):
        e = by_key.get(mtglib._norm(name))
        ref = e if (e is not None and e.has_type_data) else mtglib.lookup(idx, name)
        return deck_fit.primary_role(ref) if ref else None

    ranges = r.get("role_ranges") or {}
    cats = dict(a["report"].get("categories", {}))
    kept, held = [], []
    for s in swaps:
        cr, ar = _role(s[0]), _role(s[2])
        trial = dict(cats)
        if cr:
            trial[cr] = trial.get(cr, 0) - 1
        if ar:
            trial[ar] = trial.get(ar, 0) + 1
        bad = [ro for ro in (cr, ar) if ro in ranges
               and not (ranges[ro][0] <= trial.get(ro, 0) <= ranges[ro][1])
               and (ranges[ro][0] <= cats.get(ro, 0) <= ranges[ro][1])]
        if bad:
            held.append({"cut": s[0], "add": s[2], "role": bad[0]})
            continue
        cats = trial
        kept.append(s)

    out = dict(r)
    out.update({"swaps": kept, "land_swaps": land_swaps, "stale": stale, "held": held,
                "swaps_detail": [d for d in r.get("swaps_detail") or []
                                 if (d["cut"], d["add"]) in {(s[0], s[2]) for s in kept}]})
    if kept or land_swaps:
        _write(deck_path, kept, land_swaps)
        record_changes(deck_path, kept, land_swaps, by=by)
        added = {k for s in kept for k in mtglib.name_keys(s[2])}
        added |= {k for s in land_swaps for k in mtglib.name_keys(s[1])}
        _tidy(deck_path, idx, only=added)
        out["illegal"] = singleton_violations(deck_path)
        if r.get("buy_swaps"):
            out["buylist_appended"] = append_buylist(deck_path, r["buy_swaps"],
                                                     r.get("commander", ""))
    return out


def singleton_violations(deck_path):
    """Nonbasic cards appearing more than once — Commander is a singleton format.

    Run after every write. A silent duplicate is the worst kind of bug here: the deck
    still totals 100 cards and every dashboard looks healthy, so nothing surfaces it
    until you physically sleeve the deck and come up a card short."""
    deck = mtglib.parse_deck(open(deck_path, encoding="utf-8").read())
    # Aggregate by FRONT-FACE key, not raw name: '1 Fire' + '1 Fire // Ice' is the
    # same physical card twice, but parses as two names each qty 1 — the exact
    # alias-duplicate class this guard was written for, and raw counting missed it.
    counts = {}
    for c in deck:
        if mtglib.is_basic(c.name):
            continue
        k = mtglib._norm(mtglib.front_face(c.name))
        entry = counts.setdefault(k, [0, c.name])
        entry[0] += c.quantity
    return [(q, name) for q, name in counts.values() if q > 1]


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
    # Separate EDHREC-style "Instants" / "Sorceries" sections (the 2026-08-11 convention)
    # are exclusive. Only a COMBINED heading ("Instants & sorceries", "Spells") holds both;
    # that case is matched first in _type_allowed. When "Instants" also allowed Sorcery,
    # _tidy re-filed every sorcery into the first section that "allowed" it — so each
    # optimize --apply pulled sorceries up under Instants (the-ur-dragon, beorn, 2026-10-07).
    (("instant",), {"Instant"}),
    (("sorcery", "sorceries"), {"Sorcery"}),
]
# Where a card goes when no suitable section exists — created in this order, after the
# existing ones. Type-based, which is the convention every decklist site uses.
_FALLBACK_ORDER = [("Creature", "Creatures"), ("Planeswalker", "Planeswalkers"),
                   ("Artifact", "Artifacts"), ("Enchantment", "Enchantments"),
                   ("Instant", "Instants"), ("Sorcery", "Sorceries"),
                   ("Land", "Lands")]


def _type_allowed(section):
    """The card types a section may hold, or None if it isn't type-exclusive."""
    name = re.sub(r"\s*\(\d+\)\s*$", "", section).strip().lower()
    if name.startswith("spell") or ("instant" in name and "sorcer" in name):
        return {"Instant", "Sorcery"}               # a combined section holds both
    for words, types in _TYPE_SECTIONS:
        if any(name.startswith(w) for w in words):
            return types
    return None


def _section_type_signal(text):
    """The deck file's own sections as a land/nonland signal for UNTYPED cards.

    {normalized name: bool} — True for cards under a type-exclusive Lands section,
    False under any other type-exclusive section. Function sections ("Ramp"), the
    Unsorted section and pre-section lines give no signal (the card stays with the
    name heuristic). Never consulted for a card that has real type data."""
    sig, cur = {}, None
    for ln in text.split("\n"):
        s = ln.strip()
        m_sec = re.match(r"^#\s*-+\s*(.+?)\s*-+\s*$", s)
        if m_sec:
            cur = m_sec.group(1)
            continue
        if not s or s.startswith("#") or cur is None:
            continue
        allowed = _type_allowed(cur)
        if allowed is None:
            continue
        m = mtglib._QTY_RE.match(s)
        name = m.group(2) if m else s
        sig[mtglib._norm(name)] = "Land" in allowed
    return sig


def _tidy(deck_path, idx, only=None):
    """Re-file cards under the section that matches their role and merge duplicate lines.

    `only` (a set of normalized names) limits the re-filing to those cards: an approved
    ⚡ run re-files what it ADDED and nothing else, so its one-tap "Undo all" gives back
    the list the player had. Re-filing every card there moved The Warring Triad (an
    artifact creature filed under Artifacts) on every approval, and no undo moved it
    back (UAT F8, 2026-10-15). The full `--apply` pass keeps re-filing everything.
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
        m = mtglib._QTY_RE.match(s)          # the ONE qty-line parser ('1x Name' included)
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
            if only is not None and not (mtglib.name_keys(name) & only):
                keep_here.append(item)            # not this write's card: leave it be
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

    # header block = everything before the first section marker
    first_sec_i = next((i for i, ln in enumerate(lines)
                        if re.match(r"^#\s*-+\s*.+?\s*-+\s*$", ln.strip())), len(lines))
    out = lines[:first_sec_i]
    for sec in order:
        merged, seen_order, comments = {}, [], []
        for item in sections.get(sec, []):
            if item[0] != "card":
                # Keep the player's comment lines — 'edits keep comment lines intact'
                # is the repo contract, and this loop used to delete every comment
                # that lived under a section header. Stored blank lines are dropped;
                # the rebuild manages its own spacing.
                raw = item[1]
                if raw.strip().startswith("#"):
                    comments.append(raw)
                continue
            _t, qty, name = item
            k = mtglib._norm(name)
            if k in merged:
                merged[k][0] += qty                      # collapse duplicate lines
            else:
                merged[k] = [qty, name]
                seen_order.append(k)
        if not seen_order and not comments:
            continue                                     # drop a section left empty
        # refresh a stale "(14)" style count in the header
        total = sum(merged[k][0] for k in seen_order)
        title = re.sub(r"\s*\(\d+\)\s*$", "", sec)
        label = f"{title} ({total})" if re.search(r"\(\d+\)\s*$", sec) else title
        out.append(f"# --- {label} ---")
        out.extend(comments)
        for k in seen_order:
            qty, name = merged[k]
            out.append(f"{qty} {name}")
        out.append("")
    with open(deck_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out).rstrip("\n") + "\n")


def record_changes(deck_path, swaps, land_swaps, by=""):
    """Append what this run changed to `<deck>.changes.csv`.

    The optimizer already knows exactly which cards it brought in, so writing it down is
    nearly free — and it's the only way the dashboard can tell a card that arrived this
    morning from one that's been in the list for months. Appending (rather than
    overwriting) keeps the deck's history. `by` is who pressed ⚡ in the app (empty for
    the CLI and sessions); deckcore.append_changes owns the file format."""
    from datetime import date
    rows = [(add, cut, avail) for cut, _v, add, _i, avail in swaps]
    rows += [(add, cut, avail) for cut, add, avail in land_swaps]
    if not rows:
        return 0
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    today = date.today().isoformat()
    return deckcore.append_changes(f"{stem}.changes.csv",
                                   [(add, today, cut, avail) for add, cut, avail in rows],
                                   by=by)


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
            m = mtglib._QTY_RE.match(s)     # shared parser: '1x Name' must not silently no-op
            name = m.group(2) if m else s
            k = mtglib._norm(name)
            if k in repl and k not in done:
                out.append(f"{m.group(1) if m else '1'} {repl[k]}")
                done.add(k)
                continue
        out.append(ln)
    with open(deck_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out))


def manual_adds_review(deck_path, coll):
    """Advisory read-out on cards the PLAYER added by hand — never an instruction.

    The optimizer deliberately does not touch manual edits, and that stays true: this
    only reports how each hand-picked card scores, because "we left it alone" and "it's
    a good pick" are different statements and the player asked for the second one.
    Returns [] when there's nothing recent, so quiet runs stay quiet.
    """
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    try:
        rows = deckcore.manual_adds(f"{stem}.changes.csv", days=None)
    except Exception:
        return []
    # Only cards STILL IN the deck. `.changes.csv` is append-only history, so a card
    # the player added and then took back out remains a manual-add row forever — and
    # this list is headed "the optimizer never cuts these", which is a claim about a
    # card that is not there to cut. Found by the Phase 8 acceptance run (2026-08-14):
    # y'shtola listed Painful Truths, added and reverted the same day (rows 17-18 of
    # its log), rendered as "(no opinion — not resolvable in the collection)" because
    # it is also unowned. Two confusing statements about a card the deck does not run.
    try:
        in_deck = set()
        for c in mtglib.parse_deck(open(deck_path, encoding="utf-8").read()):
            in_deck |= mtglib.name_keys(c.name)
        rows = [r for r in rows
                if mtglib.name_keys(r.get("name") or r.get("key") or "") & in_deck]
    except OSError:
        pass                     # unreadable deck: report the rows rather than none
    if not rows:
        return []
    out = ["   manual adds (advisory — the optimizer never cuts these):"]
    # Pay the analysis / reference / EDHREC-cache cost once, not once per add.
    analysis, refs, ctx = None, None, None
    try:
        analysis = deckcore.analyze_deck(deck_path, coll)
        refs = power.load_refs()
        commander = _commander_of(open(deck_path, encoding="utf-8").read())
        ctx = deck_fit.deck_context(deck_path, analysis["enriched"], commander,
                                    field=deck_fit.load_field(commander, analysis["idx"]),
                                    synergy=deck_fit.load_synergy(commander, analysis["idx"]))
    except Exception:
        pass
    for r in rows:
        name = r.get("name") or r.get("key")
        v = None
        try:
            v = deckcore.advise_card(deck_path, coll, name, analysis=analysis,
                                     refs=refs, ctx=ctx)
        except Exception:
            v = None
        if v is None:
            out.append(f"     {name:32} (no opinion — not resolvable in the collection)")
            continue
        note = "" if v["has_field"] else "  [fit-only — no field data]"
        out.append(f"     {v['name']:32} {v['score']:>3}/100  {v['band']}{note}")
        if v["alternatives"]:
            out.append("       would also consider: "
                       + ", ".join(a["n"] for a in v["alternatives"]))
    return out


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
                    help="skip buy recommendations entirely (buys never enter the "
                         "deck either way — they go to <deck>.buylist.csv)")
    ap.add_argument("--buy-threshold", type=int, default=55,
                    help="minimum inclusion %% for an unowned card to be "
                         "recommended on the buylist")
    ap.add_argument("--max-swaps", type=int, default=40,
                    help="safety cap on how many cards a single pass may change")
    ap.add_argument("--apply", action="store_true", help="write the changes")
    ap.add_argument("--json", action="store_true",
                    help="print the proposals, reads and advisories as JSON (for a "
                         "Claude session's review; never combined with --apply)")
    ap.add_argument("--verdict", action="append", default=[], nargs=3,
                    metavar=("KEY", "VERDICT", "WHY"),
                    help="save a session's read of one current proposal (KEY as --json "
                         "prints it) or read ('read|<name>'): VERDICT is swap, skip, bench "
                         "or wishlist, WHY the reason. Repeatable. The deck's ⚡ page shows "
                         "it; nothing is applied")
    ap.add_argument("--approve", action="append", default=[], metavar="KIND|OUT|IN",
                    help="write ONLY this proposal (repeatable; keys as --json prints "
                         "them) — what a session runs after the player approves a subset")
    args = ap.parse_args()
    if args.json and (args.apply or args.approve):
        print("error: --json is the review surface; it never writes. Drop --apply/--approve.",
              file=sys.stderr)
        return 2
    if args.verdict:
        if args.all or not args.deck or args.apply or args.approve:
            print("error: --verdict takes one --deck, on its own", file=sys.stderr)
            return 2
        coll = mtglib.load_collection(args.collection)
        r = optimize(args.deck, coll, mtglib.index_by_name(coll), args.decks_dir)
        try:
            written, stale = record_verdicts(args.deck, r, args.verdict)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        for k in written:
            print(f"   saved  {k}")
        for k in stale:
            print(f"   not proposed now, not saved: {k}")
        return 0
    if args.approve:
        if args.all or not args.deck or args.apply:
            print("error: --approve takes one --deck, and replaces --apply",
                  file=sys.stderr)
            return 2
        coll = mtglib.load_collection(args.collection)
        r = apply_chosen(args.deck, coll, mtglib.index_by_name(coll), args.decks_dir,
                         args.approve)
        for cut, _v, add, *_ in r.get("swaps") or []:
            print(f"   applied  {cut}  ->  {add}")
        for cut, add, _a in r.get("land_swaps") or []:
            print(f"   applied  land {cut}  ->  {add}")
        for k in r.get("stale") or []:
            print(f"   not proposed now, skipped: {k}")
        for h in r.get("held") or []:
            print(f"   held: {h['cut']} -> {h['add']} would push {h['role']} out of range")
        for qty, name in r.get("illegal") or []:
            print(f"   !! ILLEGAL: {qty}x {name} — Commander allows one copy")
        return 0

    coll = mtglib.load_collection(args.collection)
    idx = mtglib.index_by_name(coll)
    refs = power.load_refs()
    paths = sorted(glob.glob(os.path.join(args.decks_dir, "*.txt"))) if args.all else [args.deck]
    if args.all:
        # Study copies are deliberate, unowned lists — `--all` (and refresh
        # --optimize) must not tune them toward the collection. Name one with
        # --deck to preview it on purpose (2026-10-11 audit, R11).
        study = [p for p in paths if deck_conflicts.is_study_deck(p)]
        for p in study:
            # stderr under --json: stdout must stay one parseable document
            print(f"skip study copy: {os.path.basename(p)}",
                  file=sys.stderr if args.json else sys.stdout)
        paths = [p for p in paths if p not in study]
    if not paths or paths == [None]:
        print("error: pass --deck or --all", file=sys.stderr)
        return 2

    out_json = []
    for p in paths:
        r = optimize(p, coll, idx, args.decks_dir, refs, margin=args.margin,
                     apply=args.apply, max_swaps=args.max_swaps,
                     owned_only=args.owned_only, include_buys=not args.no_buys,
                     buy_threshold=args.buy_threshold)
        if args.json:
            out_json.append(review_payload(r))
            continue
        print(f"\n=== {r['stem']} — {r['commander']} ({r['field_size']} field cards) ===")
        widened = {role: rng for role, rng in (r.get("role_ranges") or {}).items()
                   if rng != ROLE_RANGE.get(role)}
        if widened:
            # Say which template judged this deck: a control deck's counter count is
            # only "excess" against the default template, and the number changes with
            # the header. Same rule as every other honesty label — beside the number.
            print("   template: widened by archetype "
                  f"({' '.join(r.get('archetype') or [])}) -> "
                  + ", ".join(f"{role} {lo}-{hi}" for role, (lo, hi) in sorted(widened.items())))
        for h in sorted(r.get("manual_holds") or [], key=lambda x: -x["inc"])[:5]:
            print(f"   held: {h['name']} ({h['inc']}% field) — you removed it by hand "
                  f"on {h['removed']}; not re-proposing. Add it back yourself if "
                  f"you've changed your mind.")
        for g in r.get("land_guard") or []:
            who = ", ".join(g["for"][:3]) or "a fetcher"
            print(f"   ~ kept {g['kept']}: last {g['type'].capitalize()}-typed "
                  f"land for {who}")
        if r.get("archetype_unknown"):
            # The label fires on the IGNORED input too, not only on success — an
            # unmapped word buys nothing and the player should not have to guess
            # which half of their header was understood.
            print(f"   note: archetype word(s) not recognised, no widening applied: "
                  f"{', '.join(r['archetype_unknown'])}")
        if r.get("untyped"):
            print(f"   note: {r['untyped']} deck cards have no type data — the land/spell "
                  f"split falls back to the deck's own sections, then name heuristics")
        # "No swaps" has two causes and only one of them is alignment. When the
        # role-band gate froze candidates that had ALREADY cleared the margin and the
        # field veto, saying "aligned" is a lie — it is what let tifa-lockhart sit at
        # 10/25 field overlap looking finished. Name the gate instead. The freeze is
        # deliberate (softening it would churn a hand-ratified deck toward the blind
        # band); the fix is to ratify an archetype entry, not to force the swap.
        dl = r.get("role_deadlock") or {}
        blocked = dl.get("blocked") or []
        if not r["swaps"] and not r["land_swaps"]:
            if blocked:
                for b in blocked:
                    cur, lo, hi = next((o["count"], o["lo"], o["hi"])
                                       for o in dl["out_of_band"] if o["role"] == b["role"])
                    print(f"   no changes — {len(b['adds'])} candidate(s) blocked by the "
                          f"{b['role']} band (current {cur}, template {lo}-{hi})")
                print("   the band freezes this role on purpose; if the count is "
                      "deck-correct, ratify an archetype entry "
                      "(deckcore._ARCHETYPE_ROLE_RANGE) rather than forcing swaps")
            else:
                print("   already aligned with the field — no changes")
        for o in dl.get("out_of_band") or []:
            # Standing fact about the deck, printed even when other roles DID swap —
            # same class of honesty label as `untyped` and `archetype_unknown`.
            print(f"   note: {o['role']} {o['count']} sits outside the template "
                  f"{o['lo']}-{o['hi']} — swaps touching it are frozen")
        for sw in r.get("swaps_detail") or []:
            tag = " [shared]" if sw["avail"] == "share" else ""   # buys never reach swaps
            # BOTH units, both sides. The old line printed the cut's `value_of` blend and
            # the add's raw field % with the same bare "%", which is what made the
            # 2026-08-12 previews read as field inversions ("Ganax, Astral Hunter (27%)"
            # was its VALUE, not its field %) — and the field veto is only auditable
            # from a preview if the two field numbers sit side by side.
            # "no field data" is printed as such — `inc_of` returns 0 both for a
            # card the field plays in 0% of decks and for one it has never seen,
            # and only the first of those is a measurement.
            cf = (f"{sw['cut_inc']:>3}% field" if sw.get("cut_field_known", True)
                  else "no field data")
            af = (f"{sw['add_inc']}% field" if sw.get("add_field_known", True)
                  else "no field data")
            fit_only = "  [fit-driven: the field has no opinion on the cut]" \
                if not sw.get("cut_field_known", True) else ""
            print(f"   {sw['cut']:32} ({cf}, value {sw['cut_value']:>3})"
                  f"  ->  {sw['add']} ({af}){tag}{fit_only}")
            if sw.get("trades_specific"):
                print(f"      !! cuts a card {sw['cut_lift']:g}x as common in this "
                      f"commander's decks as its colours for one at "
                      f"{sw['add_lift'] if sw.get('add_lift') is not None else '?'}x"
                      f" - read it before approving")
        for old, new, avail in r["land_swaps"]:
            tag = " [shared]" if avail == "share" else ""
            print(f"   land  {old:32} ->  {new}{tag}")
        cov = r.get("field_coverage")
        if cov and cov.get("owned"):
            print(f"   field top-{cov['top']}: {cov['n_in']} in the deck · of the "
                  f"{cov['owned']} you own, {cov['n_in']} in ({cov['owned_pct']}%) · "
                  f"{len(cov['not_owned'])} not owned")
            for o in cov["owned_out"]:
                where = "a free copy" if o["free"] else "held by " + ", ".join(o["held_by"])
                print(f"      owned, not in: {o['name']} ({o['inc']}%; {where}) — "
                      f"give it a reason in the notes")
        for cut, ic, add, ia, kind in r.get("buy_swaps", []):
            print(f"   buy   {add} ({ia}%) — would replace {cut} ({ic}%)"
                  f"{'  [land]' if kind == 'land' else ''}  -> .buylist.csv")
        if r.get("buylist_appended"):
            print(f"     appended/updated {r['buylist_appended']} row(s) in "
                  f"{r['stem']}.buylist.csv")
        for qty, name in r.get("illegal") or []:
            print(f"   !! ILLEGAL: {qty}x {name} — Commander allows one copy")

        for line in manual_adds_review(p, coll):
            print(line)

        # Advisory only — cards you own that the margin gate held back. The field
        # hasn't fully adopted them (or the incumbent still rates well); adding one
        # by hand marks it manual and protects it.
        for rz in r.get("risers", []):
            print(f"   ~ own it, gate held it: {rz['add']} ({rz['add_inc']}%) "
                  f"over {rz['over']} ({rz['over_inc']}%) — {rz['gap']} pts short of auto-swap")

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
    if args.json:
        import json
        print(json.dumps(out_json if args.all else out_json[0], indent=2))
        return 0
    if not args.apply:
        print("\n(proposals only — a session reads them, then --apply on the player's go)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
