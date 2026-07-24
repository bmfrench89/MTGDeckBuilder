#!/usr/bin/env python3
"""Auto-build a full Commander deck for a commander from the player's OWNED pool.

v1 (Phase 3): rank every owned + *available* card with the deck_fit engine, fill
the house-template role quotas greedily (ramp / draw / removal / wipes / counters),
build a ~37-card manabase (owned in-color nonbasics + basics; proportional now,
Karsten colored-source targets once the Phase-2 engine lands), and report any role
the pool couldn't fill as a "gap to buy". Pure/stdlib — reuses mtglib, deck_fit,
deck_conflicts, similar_commanders, power, combo_detector. Honest heuristic draft,
not a tuned list; it degrades gracefully on a name-only collection (says so).

See docs/spec-build-next-full-deck.md.
"""
import os

import mtglib
import deck_fit
import deck_conflicts
import similar_commanders as simc
import power
import combo_detector
import card_image
import deckcore

DECK_SIZE = 100                 # incl. the commander
LAND_TARGET = 37
# (role, target) in fill priority order — matches deck_fit.FIT_TARGETS / the
# Command Zone + 8x8 templates (see the spec).
ROLE_QUOTA = [("ramp", 11), ("draw", 10), ("removal", 9), ("wipe", 3), ("counter", 4)]
_BASIC = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
ROLE_LABEL = {"ramp": "Ramp", "draw": "Card advantage", "removal": "Removal",
              "wipe": "Board wipes", "counter": "Counters", "creature": "Creatures",
              "spell": "Instants / sorceries", "artifact": "Artifacts",
              "enchantment": "Enchantments", "planeswalker": "Planeswalkers",
              "other": "Synergy / threats", "land": "Lands"}
SECTION_ORDER = ["ramp", "draw", "removal", "wipe", "counter", "creature", "spell",
                 "artifact", "enchantment", "planeswalker", "other"]


def _img(name, idx):
    """Scryfall image URL for a card — CDN via the collection's Scryfall id when
    available, else the image-by-name endpoint."""
    ref = mtglib.lookup(idx, name)
    sid = ref.scryfall_id if (ref and ref.scryfall_id) else ""
    return (card_image.image_url(sid, "normal") if sid
            else card_image.image_url_by_name(name, "normal"))


def _commander(name, commanders):
    k = mtglib._norm(name)
    for c in commanders:
        if mtglib._norm(c["name"]) == k:
            return c
    return None


def _color_legal(card, identity):
    """True/False if the card's identity is known, else None (unknown — name-only)."""
    cid = set(card.identity or [])
    if not cid:
        return None
    return cid <= identity


def _basics_split(n, identity):
    out = {}
    colors = sorted(identity) if identity else []
    if not colors or n <= 0:
        return out
    base, extra = divmod(n, len(colors))
    for i, col in enumerate(colors):
        out[_BASIC[col]] = base + (1 if i < extra else 0)
    return {k: v for k, v in out.items() if v}


_BASIC_COLOR = {v: k for k, v in _BASIC.items()}   # "Plains" -> "W", ...


def _basics_by_demand(n, identity, cards):
    """Split n basics across the identity's colors weighted by the colored-pip
    demand of the chosen nonland cards — so a blue-heavy deck gets more Islands.
    Falls back to an even split when card mana costs aren't known (name-only)."""
    colors = sorted(identity) if identity else []
    if not colors or n <= 0:
        return {}
    demand = {c: 0.0 for c in colors}
    for card in cards:
        if getattr(card, "is_land", False) or not getattr(card, "mana_cost", ""):
            continue
        for col, pips in mtglib.pip_counts(card.mana_cost).items():
            if col in demand:
                demand[col] += pips
    tot = sum(demand.values())
    if tot <= 0:
        return _basics_split(n, identity)
    raw = {c: n * demand[c] / tot for c in colors}
    alloc = {c: int(raw[c]) for c in colors}
    for c in sorted(colors, key=lambda c: -(raw[c] - int(raw[c])))[:n - sum(alloc.values())]:
        alloc[c] += 1
    for c in colors:                     # every demanded color gets >=1 source
        if demand[c] > 0 and alloc[c] == 0:
            donor = max(colors, key=lambda x: alloc[x])
            if alloc[donor] > 1:
                alloc[donor] -= 1
                alloc[c] = 1
    return {_BASIC[c]: v for c, v in alloc.items() if v > 0}


_TRIBAL_MIN = 12  # owned in-color members before a tribal build is honest (grounding rule #2)


def _tribe_and_support(commander_name, idx, archetype, coll, identity):
    """The tribe a commander is built around + how many in-color members you own.
    Candidates: 'tribal-X' archetype tags + the commander's own non-'Human' subtypes;
    pick whichever the collection best supports (so we never force a tribe you can't field)."""
    cands = [a.split("-", 1)[1].lower() for a in archetype if a.startswith("tribal-")]
    ref = mtglib.lookup(idx, commander_name)
    if ref and ref.subtypes:
        cands += [s.lower() for s in ref.subtypes if s.lower() != "human"]
    best, best_n = None, 0
    for tribe in dict.fromkeys(cands):
        n = sum(1 for c in coll
                if tribe in {s.lower() for s in (c.subtypes or [])}
                and (not c.identity or c.identity <= identity))
        if n > best_n:
            best, best_n = tribe, n
    return best, best_n


def build(commander_name, coll, idx, decks_dir, refs=None, respect_commitments=True,
          identity=None, skip_deck=None):
    """Build a deck for `commander_name`. If the commander is in the curated
    commanders.csv we use its colors + archetype tags. Otherwise (any commander
    typed by the player) pass `identity` (WUBRG letters, e.g. from Scryfall's
    color_identity) so we can still filter to in-color cards; archetype is then
    unknown, so synergy/theme scoring is lighter."""
    commanders = simc.load_commanders()
    cmd = _commander(commander_name, commanders)
    known = cmd is not None
    if known:
        identity = set(cmd["colors"])
        archetype = sorted(cmd["archetypes"])
    else:
        archetype = []
        if identity:
            identity = {ch for ch in str(identity).upper() if ch in "WUBRG"}
        else:
            ref = mtglib.lookup(idx, commander_name)
            identity = set(ref.identity) if (ref and ref.identity) else set()
    refs = refs or power.load_refs()
    ctx = {"identity": identity, "archetype": archetype, "theme": "",
           "tribal": None, "commander": commander_name}
    # tribal awareness: does the commander want a tribe, and does the collection support it?
    tribe, tribe_n = _tribe_and_support(commander_name, idx, archetype, coll, identity)
    tribe_warning = None
    if tribe and tribe_n >= _TRIBAL_MIN:
        ctx["tribal"] = tribe
    elif tribe:
        tribe_warning = (f"{commander_name} wants {tribe.title()}s, but you own only {tribe_n} "
                         f"in-color — too few for a tribal build (needs ~{_TRIBAL_MIN}+), so this "
                         f"is a goodstuff draft, not a {tribe.title()} deck.")
    nameonly = not any(c.types for c in coll)

    # Candidate pool: owned minus copies committed to your other decks (basics exempt).
    if respect_commitments:
        usage = deck_conflicts.scan(decks_dir, idx, skip=skip_deck)
        pool_names = [row[0] for row in deck_conflicts.available_pool(usage, coll)]
    else:
        pool_names = [c.name for c in coll]

    cmd_key = mtglib._norm(commander_name)
    rep0 = {"categories": {}, "lands": 0}     # neutral rep so role-need is uniform
    off_color = 0
    cands = []
    for name in pool_names:
        if mtglib._norm(name) == cmd_key:
            continue
        card = mtglib.lookup(idx, name)
        if not card:
            continue
        legal = _color_legal(card, identity)
        if legal is False:
            off_color += 1
            continue
        fit = deck_fit.assess_card(card, rep0, ctx, refs)
        cands.append({"card": card, "name": card.name, "role": deck_fit.primary_role(card),
                      "score": fit["score"], "is_land": card.is_land,
                      "unknown_color": legal is None})
    cands.sort(key=lambda x: -x["score"])

    chosen, keys = [], set()
    def take(c):
        if mtglib._norm(c["name"]) in keys:
            return False
        chosen.append(c); keys.add(mtglib._norm(c["name"])); return True

    # 1) Lands — owned in-color nonbasics, best-fit first, up to LAND_TARGET.
    for c in [x for x in cands if x["is_land"]]:
        if sum(1 for x in chosen if x["is_land"]) >= LAND_TARGET:
            break
        take(c)
    n_nonbasic_land = sum(1 for x in chosen if x["is_land"])

    # 2) Nonland spells — fill role quotas, then synergy/flex to hit the spell budget.
    spell_budget = (DECK_SIZE - 1) - LAND_TARGET            # 62 with 37 lands
    nonland = [x for x in cands if not x["is_land"]]
    by_role = {}
    for c in nonland:
        by_role.setdefault(c["role"], []).append(c)
    gaps = {}
    for role, target in ROLE_QUOTA:
        picked = 0
        for c in by_role.get(role, []):
            if picked >= target or len([x for x in chosen if not x["is_land"]]) >= spell_budget:
                break
            if take(c):
                picked += 1
        if picked < target:
            gaps[role] = target - picked
    # 2b) Tribal seeding — after the role quotas, run your on-tribe creatures FIRST so a
    # shallow tribe (e.g. 13 Dragons, many pricey) actually shows up instead of losing the
    # synergy slots to cheaper off-tribe cards. Deep tribes were already fine; this fixes thin ones.
    tribe = ctx.get("tribal")
    if tribe:
        for c in nonland:
            if sum(1 for x in chosen if not x["is_land"]) >= spell_budget:
                break
            if tribe in {s.lower() for s in (c["card"].subtypes or [])}:
                take(c)
    # synergy / threats / flex — NON-quota roles first (real synergy / creatures /
    # threats), then any remaining by fit for depth, up to the spell budget. This
    # keeps ramp/draw/removal/wipe/counter at their quotas instead of overfilling.
    quota_roles = {r for r, _ in ROLE_QUOTA}
    def n_spells():
        return sum(1 for x in chosen if not x["is_land"])
    for c in nonland:
        if n_spells() >= spell_budget:
            break
        if c["role"] in quota_roles:
            continue
        take(c)
    for c in nonland:
        if n_spells() >= spell_budget:
            break
        take(c)

    short = spell_budget - n_spells()         # pool too shallow to reach 99

    # 3) Manabase basics — weighted by the chosen deck's colored-pip demand.
    basics = _basics_by_demand(LAND_TARGET - n_nonbasic_land, identity,
                               [c["card"] for c in chosen])
    n_basic = sum(basics.values())

    # ---- assemble output ----
    role_of, counts = {}, {}
    for c in chosen:
        r = "land" if c["is_land"] else c["role"]
        role_of.setdefault(r, []).append(c)
        counts[r] = counts.get(r, 0) + 1
    counts["land"] = counts.get("land", 0) + n_basic

    sections = [("Commander", [{"name": commander_name, "qty": 1}])]
    for role in SECTION_ORDER:
        cs = sorted(role_of.get(role, []), key=lambda x: -x["score"])
        if cs:
            sections.append((ROLE_LABEL.get(role, role.title()),
                             [{"name": c["name"], "qty": 1} for c in cs]))
    land_cards = [{"name": c["name"], "qty": 1}
                  for c in sorted(role_of.get("land", []), key=lambda x: -x["score"])]
    land_cards += [{"name": n, "qty": q} for n, q in sorted(basics.items())]
    sections.append((f"Lands ({counts['land']})", land_cards))

    for _title, cs in sections:      # attach a card image URL to every entry
        for c in cs:
            c["img"] = _img(c["name"], idx)

    all_names = [commander_name] + [c["name"] for c in chosen]
    detected = combo_detector.detect(all_names, combo_detector.load_combos())

    # deck-level analysis (power/bracket + manabase) on the built cards
    assessment = mana = None
    try:
        analysis = []
        cc = mtglib.lookup(idx, commander_name)
        if cc:
            analysis.append(cc)
        analysis += [c["card"] for c in chosen]
        for bn, q in basics.items():
            col = _BASIC_COLOR.get(bn)
            analysis.append(mtglib.Card(name=bn, quantity=q, types=["Land"],
                                        identity=({col} if col else set()),
                                        colors=({col} if col else set()), mana_value=0.0))
        _a = deckcore.analyze_cards(analysis, idx, refs)
        assessment, mana = _a["assessment"], _a["mana"]
    except Exception:
        assessment = mana = None

    targets = {"land": LAND_TARGET, "ramp": 11, "draw": 10, "removal": 9,
               "wipe": 3, "counter": 4}
    return {
        "commander": commander_name,
        "identity": "".join(sorted(identity)) or "C",
        "archetypes": archetype,
        "sections": sections,
        "counts": counts, "targets": targets, "gaps": gaps,
        "basics": basics,
        "total": 1 + len(chosen) + n_basic,
        "short": max(0, short),
        "off_color_skipped": off_color,
        "nameonly": nameonly,
        "known_commander": known,
        "tribal": ctx.get("tribal"),
        "tribe_warning": tribe_warning,
        "assessment": assessment,
        "mana": mana,
        "combos": {"complete": [c["name"] for c in detected["complete"]],
                   "near": [f"{c['name']} (add {c['missing']})" for c in detected["near"]]},
        "notes": cmd["notes"] if cmd else "",
    }


def deck_text(deck):
    """Render the built deck as a headered .txt (savable to data/decks/)."""
    lines = [f"# Title: {deck['commander']}",
             f"# Commander: {deck['commander']}",
             f"# Colors: {' '.join(deck['identity']) if deck['identity']!='C' else ''}".rstrip(),
             f"# Archetype: {' '.join(deck['archetypes'])}",
             "# Source: auto-generated draft (scripts/auto_build.py) from owned cards.",
             ""]
    for title, cards in deck["sections"]:
        if not cards:
            continue
        lines.append(f"# --- {title} ---")
        for c in cards:
            lines.append(f"{c['qty']} {c['name']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    import argparse
    import json
    import sys
    ap = argparse.ArgumentParser(description="Auto-build a deck for a commander from owned cards.")
    ap.add_argument("commander")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--decks-dir", default="data/decks")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--txt", action="store_true", help="print the savable deck .txt")
    args = ap.parse_args()
    try:
        coll = mtglib.load_collection(args.collection)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(2)
    idx = mtglib.index_by_name(coll)
    d = build(args.commander, coll, idx, args.decks_dir)
    if args.txt:
        print(deck_text(d)); raise SystemExit(0)
    if args.json:
        print(json.dumps(d, indent=2)); raise SystemExit(0)
    print(f"AUTO-BUILD — {d['commander']}  [{d['identity']}]  ({', '.join(d['archetypes'])})")
    print(f"  total {d['total']} cards" + (f"  (short {d['short']} — pool too shallow)" if d['short'] else ""))
    print("  role     have / target")
    for role in ["land", "ramp", "draw", "removal", "wipe", "counter"]:
        g = f"  GAP {d['gaps'][role]}" if role in d["gaps"] else ""
        print(f"    {role:<9}{d['counts'].get(role,0):>3} / {d['targets'][role]:<3}{g}")
    if d["nameonly"]:
        print("  NOTE: name-only collection — roles/colors are limited; enrich for a sharper build.")
    for title, cards in d["sections"]:
        print(f"\n  {title} ({len(cards)})")
        print("    " + ", ".join(c["name"] for c in cards[:14]) + (" …" if len(cards) > 14 else ""))
