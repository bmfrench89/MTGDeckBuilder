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
import csv
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
                        names |= mtglib.name_keys(s)     # full name AND front face
            refs[key] = names or set(fallback)
        else:
            refs[key] = set(fallback)
    return refs


def load_resilience_staples(ref_dir=REF_DIR_DEFAULT):
    """`{"protection": {norm, …}, "recursion": {norm, …}}` from the curated CSV.

    A separate file from `role_staples.csv` because that one answers "what could I
    play instead?" (it needs Colors for identity filtering) while this one answers
    "does this deck survive being interacted with?" — different question, different
    consumers, and mixing them would put colour data on rows that never need it.

    Every row is runner-verified: `data/reference/verify-queue.txt` + a `claude/**`
    push makes `deck-verify.yml` print verbatim Scryfall text, and only cards whose
    text actually protects or rebuilds get a row. Missing file -> empty sets, which
    the axis reports as "unmeasured" rather than as a deck with zero protection."""
    out = {"protection": set(), "recursion": set()}
    path = os.path.join(ref_dir, "resilience_staples.csv")
    try:
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(ln for ln in f if not ln.startswith("#")):
                role = (row.get("Role") or "").strip().lower()
                name = (row.get("Card") or "").strip()
                if role in out and name:
                    out[role] |= mtglib.name_keys(name)   # full name AND front face
    except (OSError, csv.Error):
        pass
    return out


def read_declared_resilience(deck_path):
    """The player's own `# Resilience: <low|medium|high>` header, or None.

    Mirrors `read_declared_bracket` deliberately, for the same reason: the counted
    proxy (protection + recursion density) cannot see whether the deck *needs* that
    protection. "If your commander is removed twice, does the deck still function?"
    is a question the player can answer and the data cannot — a 2-protection deck
    with eight redundant engines is resilient, and a 2-protection deck built around
    one commander is not. The header records that judgement; the count stays visible
    beside it, never replaced."""
    try:
        with open(deck_path, encoding="utf-8") as f:
            head = f.read()
    except (OSError, UnicodeDecodeError):
        return None
    v = mtglib.deck_header(head, "Resilience").strip().lower()
    m = re.match(r"(low|medium|high)\b", v)
    return m.group(1) if m else None


def resilience_axis(enriched, staples, declared=None):
    """The CRISPI **Resilience** axis: can this deck survive being interacted with?

    Spec `docs/spec-crispi-axes.md` Phase B, and deliberately the most modest of the
    four. It counts two things the research names — protection density and recursion
    density — and refuses to pretend they are the whole answer.

    The researched bands are conditional, not absolute: **5-8 protection when the
    commander or a key engine must stay on the battlefield, 2-4 when the deck has
    recursion, redundancy or several ways to rebuild.** Which band applies depends on
    commander-dependence, which is NOT derivable from the data this repo holds — so
    the axis reports the counts, names the band each would satisfy, and lets a
    `# Resilience:` header record the player's own verdict.

    An empty staples file yields "unmeasured", never "0 protection": absent data and
    a measured zero are different claims (the same empty-vs-absent rule the collection
    attrs live under)."""
    if not staples or not (staples["protection"] or staples["recursion"]):
        return {"label": "unmeasured", "short": "unmeasured",
                "protection": None, "recursion": None,
                "declared": declared, "basis": "no-list",
                "detail": "no curated resilience list — run the verify queue"}
    prot = len(_match(enriched, staples["protection"]))
    rec = len(_match(enriched, staples["recursion"]))
    if prot >= 5:
        band = "meets the 5-8 band for a commander-dependent deck"
    elif prot >= 2:
        band = "meets the 2-4 band for a deck that rebuilds; thin if the commander is load-bearing"
    else:
        band = "below both researched bands (2-4 rebuilding, 5-8 commander-dependent)"
    return {"label": (declared or f"{prot} protection · {rec} recursion"),
            "short": (declared or f"prot {prot} · rec {rec}"),
            "protection": prot, "recursion": rec, "declared": declared,
            "basis": "declared" if declared else "counted",
            "detail": f"{prot} protection, {rec} recursion — {band}"}


def _match(enriched, ref_set):
    """Curated-list membership, split/DFC-aware.

    Compares on `name_keys` (full name AND front face) rather than a bare `_norm`.
    A curated row written as "Bofur, Reliable Guardian" matched NOTHING while the
    deck line read "Bofur, Reliable Guardian // Concerted Care", so a hand-verified
    protection card scored zero — silently, because a curated list that misses looks
    exactly like a deck that lacks the card. Every ref set is loaded through
    `name_keys` too, so the reverse spelling (curated full name, deck front face)
    matches as well."""
    hits = []
    for c in enriched:
        if mtglib.name_keys(c.name) & ref_set:
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
    # A partial clock dict must degrade, not crash: this is a PUBLIC pure function
    # and its contract says any clock shape short of goldfish's full payload still
    # yields a label. `kill_rate` missing reads as 0.0 — "no lethal games observed"
    # — which routes a median-less clock into the slow branch with an honest 0%.
    rate = clock.get("kill_rate") or 0.0

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


def consistency_axis(rep, tutors, draw):
    """The CRISPI **Consistency** axis: how reliably does the deck find its plan?

    Spec Phase C. Two mechanisms get you there and the research is explicit that
    they trade off: *"lots of tutors reduces the necessity for redundancy, while a
    deck with heavy redundancy and strong draw engines can be extremely consistent
    without a single traditional tutor."* This collection is emphatically the second
    kind — tutors run 0-1 across all nine decks while draw runs 7-15 — so an axis
    that only counted tutors would call every deck here inconsistent and be wrong.

    Redundancy bands from the research: **5-8 copies of an effect is standard, 8-12
    when the deck stalls without it, and 8 is the count that puts an effect in hand
    by turn 3.** Redundancy is measured on the role buckets `classify` already
    produces (ramp/draw/removal), which is a floor on true redundancy rather than
    the whole of it — engine-specific clusters need per-deck knowledge the report
    does not carry, and claiming otherwise would be the kind of false precision
    this repo's honesty labels exist to prevent."""
    cats = rep["categories"]
    # `_match` returns the matched NAMES, and `draw` is already a count — normalise
    # both so the axis never compares a list to an int (caught in implementation).
    tutors = len(tutors) if isinstance(tutors, (list, set, tuple)) else (tutors or 0)
    draw = len(draw) if isinstance(draw, (list, set, tuple)) else (draw or 0)
    clusters = {k: cats.get(k, 0) for k in ("ramp", "draw", "removal")}
    deep = sum(1 for v in clusters.values() if v >= 8)
    ok = sum(1 for v in clusters.values() if 5 <= v < 8)
    if tutors >= 7:
        mech = f"tutor-led ({tutors} tutors)"
    elif deep or ok:
        mech = f"redundancy-led ({deep} role(s) at 8+, {ok} in the 5-7 band)"
    else:
        mech = "thin (no role reaches the 5-copy band, and under 7 tutors)"
    return {"label": mech, "tutors": tutors, "draw": draw, "clusters": clusters,
            "deep_roles": deep,
            "detail": ("bands: 5-8 standard, 8-12 for stall-without-it enablers, "
                       "8 ~ in hand by turn 3 · " + ", ".join(
                           f"{k} {v}" for k, v in clusters.items()))}


def assess(enriched, rep, refs, declared=None, clock=None,
           resilience_staples=None, declared_resilience=None):
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

    # Phase D (spec-crispi-axes, player-ratified 2026-08-20): the 0-100 composite
    # and its tier ADJECTIVE are gone, with no `legacy_power` afterlife. The defect
    # was a single row printing "Bracket 4 … 31/100 Casual" — the bracket saw twelve
    # early infinites while the composite saw no tutors/fast mana/draw. Both halves
    # were right and the row was nonsense, which is exactly why DeckCheck retired
    # power levels for CRISPI in 2026 ("the number was opaque").
    #
    # A number kept but renamed is the same lie with a smaller font: someone
    # re-displays it, and tests then have to assert it ISN'T printed. Deleting it
    # makes the defect UNREPRESENTABLE instead of merely suppressed, and the only
    # consumer was our own leaderboard sort, replaced in the same change. The
    # component table below survives untouched — raw counts were never the problem.

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
        "components": comps,
        # CRISPI Speed (spec-crispi-axes Phase A). Additive: every existing consumer
        # of this dict keeps working, and `clock=None` yields the honest
        # "unmeasured" label rather than a missing key.
        "speed": speed_axis(detected, clock),
        # CRISPI Resilience (Phase B) and Consistency (Phase C). Both additive and
        # both degrade to "unmeasured" without their inputs, never to a zero.
        "resilience": resilience_axis(enriched, resilience_staples,
                                      declared_resilience),
        "consistency": consistency_axis(rep, tutors, draw),
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
                  clock=clock_for_deck(deck_path, collection_path),
                  resilience_staples=load_resilience_staples(ref_dir),
                  declared_resilience=read_declared_resilience(deck_path))


_SPEED_ORDER = {"combo-early": 0, "combo-setup": 1, "combat": 2,
                "combat-slow": 3, "unmeasured": 4}


def _rank_key(item):
    """Rank order after the composite's retirement: bracket, then how fast the deck
    actually wins, then interaction density.

    Every term is a shipped axis, so the ordering is explainable in one sentence —
    which the 0-100 never was. Speed breaks ties within a bracket by BASIS first
    (a deck with an early infinite outranks one that has to attack) and by the
    combat turn inside the combat basis, so faster is genuinely earlier."""
    r = item[1]
    sp = r.get("speed") or {}
    basis = _SPEED_ORDER.get(sp.get("basis"), 9)
    turn = sp.get("combat_turn")
    return (-r.get("bracket_effective", 0), basis,
            turn if turn is not None else 99,
            -r["signals"]["interaction"])


def rank_key_for(assessment):
    """`_rank_key`'s ordering for a bare assessment dict — the webapp leaderboard's
    sort. Public so the two surfaces cannot drift into different orders, which is
    the two-surfaces trap this repo keeps re-learning. A None assessment sorts last
    rather than raising."""
    if not assessment:
        return (1, 9, 99, 0)
    return _rank_key((None, assessment))


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
    for name, key in (("Speed", "speed"), ("Resilience", "resilience"),
                      ("Consistency", "consistency")):
        ax = res.get(key)
        if ax:
            print(f"\n{name} (CRISPI): {ax['label']}")
            print(f"    · {ax['detail']}")
            if ax.get("caveat"):
                print(f"    · {ax['caveat']}")
    print(f"\nInteraction (CRISPI): {res['signals']['interaction']} "
          f"removal/counter/wipe   (cEDH reference band 12-18, incl. 3+ free)")
    print("\nComponent counts (raw, not a score):")
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
        results.sort(key=_rank_key)
        if args.json:
            print(json.dumps([{"deck": os.path.basename(d), **r}
                              for d, r in results], indent=2))
            return 0
        print("POWER RANKING — your decks, strongest first\n")
        print(f"  {'#':<3}{'Deck':<34}{'Bracket':<14}{'Speed':<16}"
              f"{'Resilience':<18}{'Consistency':<16}Inter")
        print("  " + "-" * 106)
        for i, (d, r) in enumerate(results, 1):
            name = os.path.basename(d)[:-4]
            # The player's setting leads; a disagreeing detection is shown, never
            # dropped — "(det 4)" is small but it is the evidence.
            b = f"{r['bracket_effective']} {r['bracket_effective_name']}"
            if r.get("bracket_mismatch"):
                b += f" (det {r['bracket_detected']})"
            sp = (r.get("speed") or {}).get("short", "—")
            rs = (r.get("resilience") or {}).get("short", "—")
            cs = (r.get("consistency") or {}).get("label", "—")
            cs = cs.split(" (")[0]
            print(f"  {i:<3}{name[:33]:<34}{b:<14}{sp:<16}{rs:<18}{cs:<16}"
                  f"{r['signals']['interaction']}")
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
