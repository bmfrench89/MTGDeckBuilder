#!/usr/bin/env python3
"""Commander bracket classifier + 0-100 power ranking for a deck.

Two outputs:
  1. Bracket (1-5) in WotC's Commander Bracket system, from detectable signals
     (Game Changers count, mass land denial, extra-turn cards, tutors, combos).
  2. A 0-100 power score from countable deck qualities (interaction, ramp, card
     advantage, curve, tutors, fast mana, Game Changers), plus a tier label.

Reference card lists live in data/reference/*.txt (one name per line, '#' comments).
They are loaded at runtime so the lists can be curated/verified without code
changes. Small built-in fallbacks are used if a file is missing.

Usage:
  python3 power.py --deck data/decks/cosmic-spider-man.txt --collection coll.csv
  python3 power.py --rank --collection coll.csv               # leaderboard of all decks
  python3 power.py --deck d.txt --collection coll.csv --json
"""
import argparse
import glob
import json
import os
import re
import sys

import mtglib
import deck_stats
import combo_detector
import deckcore   # load_attrs/apply_attrs (attrs power the curve) — no circular import now

REF_DIR_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "data", "reference")

# Built-in fallbacks (small, high-signal). data/reference/*.txt overrides these.
_FALLBACK = {
    "game_changers": {
        "cyclonic rift", "rhystic study", "mystic remora", "smothering tithe",
        "the one ring", "fierce guardianship", "deflecting swat", "demonic tutor",
        "vampiric tutor", "enlightened tutor", "mystical tutor", "gaea's cradle",
        "ancient tomb", "necropotence", "thassa's oracle", "opposition agent",
        "drannith magistrate", "consecrated sphinx", "grand arbiter augustin iv",
    },
    "fast_mana": {
        "mana vault", "grim monolith", "chrome mox", "mox diamond", "mox opal",
        "lotus petal", "ancient tomb", "lion's eye diamond",
    },
    "tutors": {
        "demonic tutor", "vampiric tutor", "mystical tutor", "enlightened tutor",
        "worldly tutor", "diabolic intent", "diabolic tutor", "grim tutor",
        "imperial seal", "gamble", "steelshaper's gift", "stoneforge mystic",
        "green sun's zenith", "chord of calling", "finale of devastation",
        "fabricate", "whir of invention", "tainted pact",
    },
    "extra_turns": {
        "time warp", "temporal manipulation", "capture of jingzhou", "nexus of fate",
        "temporal mastery", "walk the aeons", "time stretch", "expropriate",
        "alrund's epiphany", "karn's temporal sundering",
    },
    "mass_land_denial": {
        "armageddon", "ravages of war", "catastrophe", "winter orb", "static orb",
        "rising waters", "blood moon", "back to basics", "cataclysm",
    },
    "combo_pieces": {
        "thassa's oracle", "demonic consultation", "tainted pact", "underworld breach",
        "isochron scepter", "dramatic reversal", "kiki-jiki, mirror breaker",
        "food chain", "dockside extortionist", "aetherflux reservoir",
    },
}


def load_refs(ref_dir=REF_DIR_DEFAULT):
    refs = {}
    for key, fallback in _FALLBACK.items():
        path = os.path.join(ref_dir, f"{key}.txt")
        if os.path.exists(path):
            names = set()
            with open(path, encoding="utf-8") as f:
                for line in f:
                    s = line.split("#", 1)[0].strip()
                    if s:
                        names.add(mtglib._norm(s))
            refs[key] = names or set(fallback)
        else:
            refs[key] = set(fallback)
    return refs


def _match(enriched, ref_set):
    hits = []
    for c in enriched:
        if mtglib._norm(c.name) in ref_set:
            hits.append(c.name)
    return hits


def avg_mv(enriched):
    vals = [c.mana_value for c in enriched
            if (not c.is_land) and c.mana_value is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def clamp01(x):
    return max(0.0, min(1.0, x))


BRACKET_NAMES = {1: "Exhibition", 2: "Core", 3: "Upgraded", 4: "Optimized",
                 5: "cEDH"}


def read_declared_bracket(deck_path):
    """The player's own `# Bracket: <1-5>` header, or None.

    The detected bracket is a card-count estimate; the PLAYER knows their deck's
    intent, and brackets 1 and 5 are defined by intent rather than by contents at all
    (WotC: Exhibition is "not built to win", cEDH is metagame-tuned). So the header is
    a setting, not an override of the evidence: `assess` reports it BESIDE the
    detected verdict and every surface shows both whenever they differ."""
    try:
        with open(deck_path, encoding="utf-8") as f:
            head = f.read()
    except (OSError, UnicodeDecodeError):
        return None
    v = mtglib.deck_header(head, "Bracket").strip()
    # A LEADING digit with a word boundary: accepts a hand-annotated
    # "# Bracket: 3 (upgraded)" as 3 (the old regex did too, and a fullmatch
    # silently dropped it), rejects "35" (no boundary between the digits) and
    # "banana"/9/empty. The old \s* also crossed the newline, so an EMPTY header
    # above a "1 Sol Ring" line read a phantom Bracket 1 — deck_header fixed that.
    m = re.match(r"([1-5])\b", v)
    return int(m.group(1)) if m else None


def with_declared(assessment, declared):
    """Re-stamp an already-computed assessment with the player's bracket setting.

    `deckcore.analyze_cards` scores cards and has no deck PATH, so it cannot read the
    header; `analyze_deck` does. Rather than thread a second argument through the
    shared pipeline, the setting is applied here — the detected verdict and every
    reason are left exactly as computed, which is the whole contract."""
    if not assessment:
        return assessment
    d = declared if declared in (1, 2, 3, 4, 5) else None
    detected = assessment.get("bracket_detected", assessment.get("bracket"))
    assessment["bracket_declared"] = d
    assessment["bracket_effective"] = d if d else detected
    assessment["bracket_effective_name"] = BRACKET_NAMES.get(
        d if d else detected, assessment.get("bracket_name", ""))
    assessment["bracket_mismatch"] = bool(d and d != detected)
    return assessment


def speed_axis(detected, clock=None):
    """The CRISPI **Speed** axis: how fast this deck actually wins — combo FIRST.

    Spec: `docs/spec-crispi-axes.md` Phase A. The subtlety that makes this a PAIR
    rather than one number: `goldfish`'s clock measures **unblocked combat only** and
    says so in its own payload (`combat_only`, `noncombat_sources`). Scoring Speed off
    that alone would mislabel exactly the decks this axis was built for — the
    Bartolome study deck runs 22 creatures, so it presents a mediocre *combat* clock
    while its real speed is a zero-mana sacrifice loop.

    So the combo evidence outranks the combat evidence, and the combat number is kept
    as CONTEXT rather than replaced:

      1. a complete combo flagged `early`  -> "combo (early)"
      2. a complete combo, none early      -> "combo (setup)"
      3. no combo, clock has a median      -> "combat T<n>"
      4. no combo, clock but NO median      -> "slow (lethal N% by T<horizon>)"
      5. no clock at all                   -> "unmeasured (no combat clock)"

    States 4 and 5 are deliberately distinct, and the spec collapsed them. `goldfish`
    nulls the median when fewer than half the games reach lethal, so a genuinely slow
    creature deck arrives with `have_data` TRUE and `median_first_kill` None. Calling
    that "unmeasured" understates what we know; calling it a turn number overstates
    it. The honest statement is the RATE, which is exactly what the clock's own note
    says.

    Case 5 is the honesty case and must never be a silent 0: a control or drain deck
    that the goldfish cannot kill with is *unmeasured*, not slow. The reason is
    carried verbatim from the clock's own `note`, which already explains whether the
    cause was no creatures cast, unknown power data, or too few lethal games for a
    median.

    `bracket_hint` is REUSED from the clock rather than re-derived here — `goldfish`
    already maps a median onto BRACKET_CLOCK, and a second mapping in a second module
    is how two sources of truth start disagreeing.

    Pure: takes the already-computed `detected` (from `combo_detector`) and an
    optional clock dict. `clock=None` is a first-class input, not an error — the
    bare-CLI and auto-build paths legitimately have no simulation to offer."""
    combos = (detected or {}).get("complete") or []
    early = [c for c in combos if c.get("early")]
    clock = clock or {}
    has_clock = bool(clock.get("have_data"))
    median = clock.get("median_first_kill") if has_clock else None
    rate = clock.get("kill_rate")

    if early:
        basis, label, short = "combo-early", "combo (early)", "combo (early)"
        detail = f"{len(early)} early complete combo(s): {early[0]['name']}"
    elif combos:
        basis, label, short = "combo-setup", "combo (setup)", "combo (setup)"
        detail = (f"{len(combos)} complete combo(s), none flagged early: "
                  f"{combos[0]['name']}")
    elif median is not None:
        basis = "combat"
        label = short = f"combat T{median:g}"
        detail = f"median first lethal turn {median:g} ({rate * 100:.0f}% of games)"
    elif has_clock:
        # THE STATE THE SPEC COLLAPSED (found in implementation, 2026-08-20):
        # `goldfish` nulls the median when fewer than half the games reach lethal, so
        # a real-but-slow deck arrives here with have_data TRUE and median None.
        # Calling that "unmeasured" would be a lie in the other direction — the deck
        # WAS measured and the answer is "slow". Bruce Banner (9% by T10) and Tifa
        # (16%) are the live cases; both are creature decks the combat model simply
        # cannot finish inside the horizon.
        basis, label = "combat-slow", (
            f"slow (lethal {rate * 100:.0f}% by T{clock.get('horizon', '?')})")
        short = f"slow ({rate * 100:.0f}%)"
        detail = clock.get("note") or "clock present, no median within the horizon"
    else:
        basis = "unmeasured"
        label, short = "unmeasured (no combat clock)", "unmeasured"
        detail = (clock.get("note")
                  or "no goldfish simulation available for this deck")

    out = {"label": label, "short": short, "basis": basis, "detail": detail,
           "combat_turn": median, "kill_rate": rate,
           "bracket_hint": clock.get("bracket_hint"), "caveat": None}
    if clock.get("noncombat_sources"):
        # The clock's own UNDERSTATED warning is the whole reason combo outranks it —
        # carry it wherever a combat number is shown, including beside a combo label,
        # because a reader comparing the two deserves to know.
        out["caveat"] = ("combat clock understates this deck: it also wins with "
                         "noncombat damage/drain")
    return out


def assess(enriched, rep, refs, declared=None, clock=None):
    cats = rep["categories"]
    interaction = cats.get("removal", 0) + cats.get("counter", 0) + cats.get("wipe", 0)
    ramp = cats.get("ramp", 0)
    draw = cats.get("draw", 0)
    lands = rep["lands"]
    amv = avg_mv(enriched)

    gc = _match(enriched, refs["game_changers"])
    tutors = _match(enriched, refs["tutors"])
    fast = _match(enriched, refs["fast_mana"])
    extra = _match(enriched, refs["extra_turns"])
    mld = _match(enriched, refs["mass_land_denial"])
    combos = _match(enriched, refs["combo_pieces"])
    detected = combo_detector.detect_for_cards(enriched)

    # ---- Bracket ESTIMATE (WotC Commander Bracket system). Only the "Bracket 3
    #      allows UP TO 3 Game Changers" threshold is officially confirmed; the
    #      broader count→bracket mapping below is our heuristic. Tutors are NOT a
    #      determinant since the Oct-2025 update. The official system also weighs
    #      self-assessed deck intent, which we can't detect. ----
    reasons = []
    if len(gc) >= 4 or mld or len(extra) >= 2:
        bracket, name = 4, "Optimized"
        if len(gc) >= 4:
            reasons.append(f"{len(gc)} Game Changers — over Bracket 3's cap of 3, so "
                           f"Bracket 4+: {', '.join(gc[:5])}{'…' if len(gc) > 5 else ''}")
        if mld:
            reasons.append(f"mass land denial ({', '.join(mld)}) — not allowed below B4")
        if len(extra) >= 2:
            reasons.append(f"{len(extra)} extra-turn spells (chaining risk)")
    elif 1 <= len(gc) <= 3:
        bracket, name = 3, "Upgraded"
        reasons.append(f"{len(gc)} Game Changer(s) — within Bracket 3's cap of 3 "
                       f"(estimated B3): {', '.join(gc)}")
        if extra:
            reasons.append("one extra-turn spell (fine if not chained)")
    else:
        bracket, name = 2, "Core"
        reasons.append("no Game Changers / mass land denial / extra-turn chaining — "
                       "estimated Core (Bracket 2). The official bracket also weighs "
                       "your deck's intent; Bracket 1 is the same guardrails, not built to win.")
    # Real combo detection (combo_detector) supersedes the loose piece count: a
    # COMPLETE, EARLY two-card combo forces Bracket 4; the piece-count note is
    # kept only as a fallback when no complete combo is actually assembled.
    b4_combo, combo_reasons = combo_detector.bracket_signal(detected)
    if b4_combo and bracket < 4:
        bracket, name = 4, "Optimized"
    for r in combo_reasons:
        reasons.append("⚠ " + r)
    if not detected["complete"] and len(combos) >= 2:
        reasons.append(f"⚠ {len(combos)} known combo pieces present "
                       f"({', '.join(combos)}) — no complete combo from the curated "
                       "list, but verify none of these pairs goes infinite.")
    if bracket == 4 and len(gc) >= 7 and (amv is not None and amv <= 2.6):
        name = "Optimized (cEDH-leaning)"
        reasons.append("very high Game Changer density + low curve — likely a "
                       "Bracket 5 (cEDH) deck if tuned to a competitive metagame")

    # ---- Power score (0-100) ----
    comps = []

    def comp(label, weight, ratio, detail):
        s = round(weight * clamp01(ratio), 1)
        comps.append({"name": label, "weight": weight, "score": s, "detail": detail})
        return s, weight

    total = avail = 0.0
    for label, weight, ratio, detail in [
        ("Interaction", 18, interaction / 12, f"{interaction} removal/counter/wipe"),
        ("Ramp", 15, ramp / 11, f"{ramp} ramp sources"),
        ("Card advantage", 15, draw / 10, f"{draw} draw pieces"),
        ("Tutors", 12, len(tutors) / 4, f"{len(tutors)} tutors"),
        ("Fast mana", 8, len(fast) / 3, f"{len(fast)} fast-mana"),
        ("Game Changers", 10, len(gc) / 5, f"{len(gc)} on the list"),
        ("Consistency (lands)", 8, 1 - abs(lands - 37) / 6,
         f"{lands} lands (37 ideal)"),
    ]:
        s, w = comp(label, weight, ratio, detail)
        total += s
        avail += w
    if amv is not None:
        s, w = comp("Curve efficiency", 14, 1 - abs(amv - 2.7) / 2.3,
                    f"avg MV {amv}")
        total += s
        avail += w
    else:
        comps.append({"name": "Curve efficiency", "weight": 14, "score": None,
                      "detail": "avg MV unavailable (add attrs)"})

    power = round(100 * total / avail) if avail else 0
    tier = ("Casual" if power < 32 else "Focused" if power < 55
            else "Optimized" if power < 75 else "High / cEDH")

    # `bracket` deliberately stays the DETECTED number so every existing consumer
    # (ranking, dashboards, the optimizer's reporting) keeps its meaning. The player's
    # setting travels beside it, and `bracket_effective` is what a surface headlines.
    effective = declared if declared in (1, 2, 3, 4, 5) else bracket
    return {
        "bracket": bracket, "bracket_name": name, "bracket_reasons": reasons,
        "bracket_detected": bracket, "bracket_detected_name": name,
        "bracket_declared": declared if declared in (1, 2, 3, 4, 5) else None,
        "bracket_effective": effective,
        "bracket_effective_name": BRACKET_NAMES.get(effective, name),
        "bracket_mismatch": bool(declared in (1, 2, 3, 4, 5) and declared != bracket),
        "power": power, "tier": tier, "components": comps,
        # CRISPI Speed (spec-crispi-axes Phase A). Additive: every existing consumer
        # of this dict keeps working, and `clock=None` yields the honest
        # "unmeasured" label rather than a missing key.
        "speed": speed_axis(detected, clock),
        "signals": {
            "game_changers": gc, "tutors": tutors, "fast_mana": fast,
            "extra_turns": extra, "mass_land_denial": mld, "combo_pieces": combos,
            "combos_complete": [c["name"] for c in detected["complete"]],
            "combos_near": [f"{c['name']} (add {c['missing']})"
                            for c in detected["near"]],
            "interaction": interaction, "ramp": ramp, "draw": draw,
            "lands": lands, "avg_mv": amv,
        },
    }


def clock_for_deck(deck_path, collection_path):
    """The goldfish CLOCK for one deck, or None — the Speed axis's combat half.

    `goldfish` is imported INSIDE this function on purpose. The engine ring keeps
    dependencies pointing inward (`docs/codemap.md`) and `goldfish` itself only
    reaches back for `deckcore.apply_attrs`/`load_attrs`, so a lazy import here is
    the same contract its own loader uses — and it keeps `power` importable with no
    simulation machinery present at all.

    Never raises: a missing collection path, an unreadable deck or a failed sim all
    return None, which `speed_axis` renders as the honest "unmeasured" label. The
    underlying `sim_for_deck` is disk-cached, so the first uncached call costs one
    Monte Carlo (~0.3s) and every later one costs a file read."""
    if not collection_path:
        return None
    try:
        import goldfish
        sim = goldfish.sim_for_deck(deck_path, collection_path)
        return (sim or {}).get("clock")
    except Exception:
        return None


def build_for_deck(deck_path, coll_index, ref_dir=REF_DIR_DEFAULT,
                   collection_path=None):
    with open(deck_path, encoding="utf-8") as f:
        deck = mtglib.parse_deck(f.read())
    enriched, missing = deck_stats.analyze(deck, coll_index)
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    deckcore.apply_attrs(enriched, deckcore.load_attrs(f"{stem}.attrs.csv"))
    rep = deck_stats.build_report(deck, enriched, missing, coll_index)
    return assess(enriched, rep, load_refs(ref_dir),
                  declared=read_declared_bracket(deck_path),
                  clock=clock_for_deck(deck_path, collection_path))


def print_one(deck_path, res):
    print("=" * 60)
    print(f"POWER & BRACKET — {os.path.basename(deck_path)}")
    print("=" * 60)
    if res.get("bracket_declared"):
        print(f"Bracket {res['bracket_effective']} — "
              f"{res['bracket_effective_name']}   (your setting)")
        if res.get("bracket_mismatch"):
            # Both, always: the setting wins the headline, the evidence never
            # disappears. Hiding the detected verdict would make the header a way to
            # silence the analysis rather than to record intent.
            print(f"    detected {res['bracket_detected']} — "
                  f"{res['bracket_detected_name']}, from the card signals below")
    else:
        print(f"Bracket {res['bracket']} — {res['bracket_name']}")
    for r in res["bracket_reasons"]:
        print(f"    · {r}")
    sp = res.get("speed")
    if sp:
        print(f"\nSpeed (CRISPI): {sp['label']}")
        print(f"    · {sp['detail']}")
        if sp.get("caveat"):
            print(f"    · {sp['caveat']}")
    print(f"\nPower score: {res['power']}/100  ({res['tier']})")
    for c in res["components"]:
        s = "—" if c["score"] is None else f"{c['score']:>4}/{c['weight']}"
        print(f"    {c['name']:<22}{s}   {c['detail']}")


def main():
    ap = argparse.ArgumentParser(description="Commander bracket + power ranking.")
    ap.add_argument("--deck", help="a single deck file")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--decks-dir", default="data/decks")
    ap.add_argument("--rank", action="store_true", help="rank all decks in --decks-dir")
    ap.add_argument("--ref-dir", default=REF_DIR_DEFAULT)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        with open(args.collection, encoding="utf-8"):
            coll = mtglib.load_collection(args.collection)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    idx = mtglib.index_by_name(coll)

    if args.rank:
        decks = sorted(glob.glob(os.path.join(args.decks_dir, "*.txt")))
        results = [(d, build_for_deck(d, idx, args.ref_dir, args.collection))
                   for d in decks]
        results.sort(key=lambda x: -x[1]["power"])
        if args.json:
            print(json.dumps([{"deck": os.path.basename(d), **r}
                              for d, r in results], indent=2))
            return 0
        print("POWER RANKING — your decks, strongest first\n")
        print(f"  {'#':<3}{'Deck':<28}{'Bracket':<20}{'Power':>6}  "
              f"{'Speed (CRISPI)':<22}Tier")
        print("  " + "-" * 88)
        for i, (d, r) in enumerate(results, 1):
            name = os.path.basename(d)[:-4]
            # The player's setting leads; a disagreeing detection is shown, never
            # dropped — "(det 4)" is small but it is the evidence.
            b = f"{r['bracket_effective']} {r['bracket_effective_name']}"
            if r.get("bracket_mismatch"):
                b += f" (det {r['bracket_detected']})"
            sp = (r.get("speed") or {}).get("short", "—")
            print(f"  {i:<3}{name:<28}{b:<20}{r['power']:>4}/100  "
                  f"{sp:<22}{r['tier']}")
        return 0

    if not args.deck:
        ap.error("provide --deck, or --rank")
    res = build_for_deck(args.deck, idx, args.ref_dir, args.collection)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print_one(args.deck, res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
