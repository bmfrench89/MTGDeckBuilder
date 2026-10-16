#!/usr/bin/env python3
"""Trades between decks: cards another deck holds that would matter more here.

Deck-flow review bundle D (docs/spec-deck-flow-review.md), moved out of optimize.py
after the Fable review (2026-10-15) so the auto-builder can show offers on a fresh draft
too (spokes don't import each other). A library: optimize.py and auto_build.py call it.

An offer is a card that every owned copy of sits in another deck (the DONOR), that is
NOT the donor's core, and that matters here. It comes with a free backfill for the donor
that does the same job, or appears only when the gain clearly beats the donor's loss.
Nothing is applied: a trade changes two decks, so both halves are the player's call.

The donor's core (`deck_core`) is never offered:
  * its engine spec's engine and packages, else its notes' protected list
    (`## Protected engine` / `## Protected cards`);
  * every card its notes NAME. The optimizer already protects those from cuts, and the
    two rules must agree: Fable found Smuggler's Surprise, the hexproof answer in Beorn's
    wipe plan, offered away with Fog as the "backfill";
  * clip-featured cards, cards the player added by hand, and its commander.
A notes section `## Earmarked for other decks` releases named cards on purpose:
Consecrated Sphinx in the Ur-Dragon, set aside for the player's planned Ur-Sphinx deck.
"""
import os
import re

import mtglib
import clips as clipmod
import deck_conflicts
import deck_fit
import deckcore
import engine_spec

TRADE_LIMIT = 6
# What makes a card worth asking for: it's in this deck's engine spec, it's specific to
# this commander (lift >= LIFT_TIED in >= LIFT_MIN_INCLUSION of decks), or the field
# runs it in most decks here. A generic rock worth 42 is a shuffle, not a trade.
TRADE_MIN_VALUE = 60
TRADE_BACKFILL_SLACK = 10   # the backfill may sit this many inclusion points below
# Without a backfill, a trade must be worth clearly more here than the donor's field
# plays it there: Talisman of Conviction (75% of Captain America decks) is not a trade
# just because Captain America's notes don't list it.
TRADE_GAP = 15
# Only these roles name a JOB a backfill can do. "spell", "creature", "artifact" and the
# like only name a card type: Fog is a "spell" and does nothing Smuggler's Surprise does.
FUNCTIONAL_ROLES = {"ramp", "draw", "removal", "wipe", "counter"}


def deck_core(deck_path):
    """(normalized keys, declared?) of a deck's DECLARED core: its engine spec's engine and
    packages, else its notes' protected list; plus clip-featured cards and cards the
    player added by hand. `declared` is False when the deck has neither a spec nor a
    list. (`trade_offers` also treats every notes-named card as core, declared or not.)"""
    keys, declared = set(), False
    core = engine_spec.core_names(engine_spec.load(deck_path))
    if not core:
        try:
            with open(deck_path[:-4] + ".notes.md", encoding="utf-8") as f:
                core = engine_spec.protected_engine_from_notes(f.read())
        except OSError:
            core = []
    if core:
        declared = True
        for n in core:
            keys |= mtglib.name_keys(n)
    for n in clipmod.featured_names(deck_path) or []:
        keys |= mtglib.name_keys(n)
    for r in deckcore.manual_adds(deck_path[:-4] + ".changes.csv", days=None):
        if r.get("key"):
            keys.add(r["key"])
        keys |= mtglib.name_keys(r.get("name") or "")
    keys.discard("")
    return keys, declared


def trade_offers(stem, decks_dir, coll, idx, identity, in_deck, value_of, ctx,
                 engine_keys=frozenset(), limit=TRADE_LIMIT, pins=None):
    """Cards held by other decks that would matter here, each with a like-for-like free
    backfill for the donor (or None when the donor's colours offer none). `stem` is this
    deck's stem, or any name that isn't a deck for a draft that has no file yet."""
    usage = deck_conflicts.scan(decks_dir, idx)
    reserved = deckcore.pinned_elsewhere(stem, pins)
    # the free, typed, non-land pool, with roles, computed ONCE for every backfill search
    free_cards, free_n = [], {}
    for n, _o, _e, f in deck_conflicts.available_pool(usage, coll):
        b = mtglib.lookup(idx, n) if f > 0 else None
        if b is None or not b.types or b.is_land or mtglib.is_basic(b.name):
            continue
        role = deck_fit.primary_role(b)
        if role in FUNCTIONAL_ROLES:
            free_cards.append((b, role, mtglib.name_keys(b.name)))
            free_n[b.name] = f
    donors, used = {}, {}

    def donor(y):
        if y not in donors:
            path = os.path.join(decks_dir, y + ".txt")
            try:
                text = open(path, encoding="utf-8").read()
            except OSError:
                donors[y] = None
                return None
            cmd = mtglib.deck_header(text, "Commander") or ""
            keys, declared = deck_core(path)
            keys |= mtglib.name_keys(cmd) if cmd else set()   # a commander is always core
            try:
                notes = open(path[:-4] + ".notes.md", encoding="utf-8").read()
            except OSError:
                notes = ""
            earmarked = set()
            for n in engine_spec.earmarked_from_notes(notes):
                earmarked |= mtglib.name_keys(n)
            cards = set()
            for c in mtglib.parse_deck(text):
                cards |= mtglib.name_keys(c.name)
            ident = set(re.sub(r"[^WUBRG]", "",
                               (mtglib.deck_header(text, "Colors?") or "").upper()))
            donors[y] = {"path": path, "ident": ident, "core": keys, "declared": declared,
                         "notes": notes, "earmarked": earmarked, "cards": cards,
                         "title": mtglib.deck_header(text, "Title") or y,
                         "field": deck_fit.load_field(cmd, idx) or {}}
        return donors[y]

    offers = []
    for name, v in usage.items():
        keys = mtglib.name_keys(name)
        if mtglib.is_basic(name) or keys & in_deck or v.get("owned", 0) != v.get("total", 0):
            continue                      # basics, ours already, a free copy exists, or
                                          # already over-claimed (moving it solves nothing)
        if keys & reserved:
            continue                      # pinned to another deck: the player decided
        ref = mtglib.lookup(idx, name)
        if ref is None or not ref.types or ref.is_land:
            continue
        if ref.identity and not ref.identity <= identity:
            continue                      # outside this deck's colours
        here = value_of(name, ref)
        lf = deck_fit.lift_of(name, ctx)
        inc_here = max(((ctx.get("field") or {}).get(k, 0) for k in keys), default=0)
        specific = bool(lf and lf["lift"] >= deck_fit.LIFT_TIED
                        and inc_here >= deck_fit.LIFT_MIN_INCLUSION)
        engine = bool(keys & engine_keys)
        if not (engine or here >= TRADE_MIN_VALUE or specific):
            continue
        for y in sorted(v.get("decks") or {}):
            if y == stem:
                continue                  # never our own donor
            d = donor(y)
            if d is None or keys & d["core"]:
                continue                  # the donor's declared core: never offered
            if (deck_fit.named_in_notes(name, d["notes"])
                    and not keys & d["earmarked"]):
                continue                  # its notes name it: core unless earmarked
            role = deck_fit.primary_role(ref)
            inc_there = max((d["field"].get(k, 0) for k in keys), default=0)
            backfill = None
            if role in FUNCTIONAL_ROLES:
                for b, b_role, bkeys in free_cards:
                    if (b_role != role or bkeys & d["cards"] or bkeys & keys
                            or (b.identity and not b.identity <= d["ident"])
                            or used.get(b.name, 0) >= free_n.get(b.name, 0)):
                        continue
                    inc_b = max((d["field"].get(kk, 0) for kk in bkeys), default=0)
                    if inc_b and inc_b >= inc_there - TRADE_BACKFILL_SLACK and (
                            backfill is None or inc_b > backfill["inc"]):
                        backfill = {"name": b.name, "inc": inc_b}
            if backfill is None and here - inc_there < TRADE_GAP:
                continue                  # the donor would lose more than we gain
            if backfill:
                used[backfill["name"]] = used.get(backfill["name"], 0) + 1
            offers.append({"card": ref.name, "from": y, "from_title": d["title"],
                           "value_here": here,
                           "lift_here": lf["lift"] if lf else None, "engine_here": engine,
                           "role_there": role, "inc_there": inc_there,
                           "earmarked": bool(keys & d["earmarked"]),
                           "backfill": backfill})
    offers.sort(key=lambda o: (not o["engine_here"], not o["earmarked"],
                               -o["value_here"], o["card"]))
    return offers[:limit]
