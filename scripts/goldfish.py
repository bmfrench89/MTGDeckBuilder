#!/usr/bin/env python3
"""Goldfish Monte Carlo — does this deck's own machine actually turn over?

A seeded goldfish simulator: shuffle, mulligan by a stated rule, play a land, cast
what the mana allows, ten turns, thousands of times. **No opponent, no interaction,
no combat** — that is the whole point of "goldfishing", and it is the honest limit of
every number here (see `docs/research-simulation.md`: tier 1 is in scope, tier 2 is
deferred, tier 3 is rejected).

Why this exists next to `manabase.py`: those hypergeometrics are EXACT but
UNCONDITIONAL — they cannot express sequencing, land drops, taplands, or
acceleration. A closed form can tell you P(>=3 lands in your opener); only a
simulation can tell you how often the commander is actually on the table by turn 4
*given* that you kept, dropped lands untapped-first, and spent mana greedily. The two
engines answer different questions and are meant to disagree.

What it consumes (the pinned contract, spec-engine-upgrades.md §4.2 — these names and
no others):
  * `Card.produced` — `Optional[set]`. `None` = NOT enriched: fall back to color
    identity **and say so**. `set()` = enriched and genuinely produces no mana
    (Maze of Ith). Conflating the two turns Maze of Ith into a producer, or a whole
    un-enriched deck into a zero-mana one, and the honesty label never fires.
  * `Card.flags` — `etb-tapped`, `etb-tapped-cond`, `rock`, `dork`, `ramp`, `draw`,
    `mana2`/`mana3`.

Two documented deviations from the closed forms, both deliberate:
  * **Pips are compiled here, not by `mtglib.pip_counts`.** That function splits one
    hybrid symbol into fractional pips (correct for aggregate Karsten demand); a
    simulator needs "this ONE pip is payable by W or by U", so `{W/U}` compiles to a
    single pip with two options, `{2/W}` to a pip payable by W *or* two generic, and
    `{X}` to zero. `pip_counts` is untouched.
  * **A land with no color data produces one colorless mana under the fallback
    tier.** `deck_stats` counts it as zero *colored* sources (which is right for
    Karsten math); a land that taps for literally nothing is not a sane default for a
    sim, and would make Sol Ring uncastable off five Wastes. Under the enriched tier
    an empty `produced` really is zero — that distinction survives.

Usage:
  python3 goldfish.py --deck data/decks/d.txt --collection data/collection/collection.csv
  python3 goldfish.py --deck d.txt --collection c.csv --games 5000 --json
  python3 goldfish.py --deck d.txt --collection c.csv --ab "Divination=Rhystic Study"

Every number is a simulated frequency under the assumptions the report ships in
`report['assumptions']`. Render those assumptions wherever you render the numbers.
"""
import argparse
import json
import math
import os
import random
import re
import sys

import mtglib

# Surfaces (dashboard / assess) run this many games inline behind the disk cache;
# the CLI defaults higher because a human waited for it on purpose.
DEFAULT_GAMES = 1500
CLI_GAMES = 5000
TURNS = 10
HAND = 7
MULL_FLOOR = 2          # London mulligan floor: keep at 5 cards, i.e. mull twice max
KEEP_LANDS = (2, 5)     # a keepable opening 7 has this many lands
BOTTOM_KEEP_LANDS = 3   # bottoming starts with lands in excess of this
SCREW_TURN = 4          # "screwed" is judged at the start of this turn
SCREW_LANDS = 3         # ...with fewer than this many lands in play
FLOOD_TURN = 6          # "flooded" is judged by the end of this turn
FLOOD_LANDS = 9         # ...having seen at least this many lands
NO_DATA_LIMIT = 0.25    # >25% unknown nonlands and we report a note, not numbers

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "data", "cache", "goldfish")

_SYM_RE = re.compile(r"\{([^}]+)\}")
_COLORS = "WUBRG"
_MANA_LETTERS = "WUBRGC"

# Screw/flood are judgement calls, so they ship as data: one edit here retunes every
# surface, and every surface prints the definition next to the number (Q-C1).
DEFINITIONS = {
    "p_cast_by": "P(commander on the battlefield by the end of turn N), goldfish, "
                 "no interaction.",
    "keepable_first7": f"First 7 cards (before any mulligan) holding "
                       f"{KEEP_LANDS[0]}-{KEEP_LANDS[1]} lands.",
    "mulligan_rate": "Games that took at least one London mulligan under that rule.",
    "screw": f"Fewer than {SCREW_LANDS} lands in play at the start of turn "
             f"{SCREW_TURN}.",
    "flood": f"{FLOOD_LANDS} or more lands seen by the end of turn {FLOOD_TURN}.",
    "mean_lands_by_turn": "Average lands in play after the land drop on turn N.",
    "cards": "Per card: how often it got cast at all, and how much later than its "
             "mana value it actually landed.",
}


# --------------------------------------------------------------------------- #
# Compilation — deck cards to a flat, fast, per-copy representation
# --------------------------------------------------------------------------- #
class SimCard:
    """One physical copy, compiled. Immutable; shared across games and both A/B arms."""
    __slots__ = ("name", "key", "mv", "pips", "generic", "is_land", "produces",
                 "amount", "etb_tapped", "is_producer", "castable", "model")

    def __init__(self, name, key, mv, pips, generic, is_land, produces, amount,
                 etb_tapped, is_producer, castable, model):
        self.name, self.key, self.mv = name, key, mv
        self.pips, self.generic = pips, generic
        self.is_land, self.produces, self.amount = is_land, produces, amount
        self.etb_tapped, self.is_producer = etb_tapped, is_producer
        self.castable, self.model = castable, model

    def __repr__(self):                                    # pragma: no cover - debug
        return f"<SimCard {self.name} mv={self.mv} model={self.model}>"


def parse_cost(cost):
    """`'{2}{W/U}{B}'` -> (pips, generic), where each pip is `(options, generic_alt)`.

    ONE symbol is at most ONE pip, payable by any letter in `options`:
      `{W}`   -> ({'W'}, 0)          `{W/U}` -> ({'W','U'}, 0)   hybrid: either color
      `{W/P}` -> ({'W'}, 0)          Phyrexian: paying life is not modeled
      `{2/W}` -> ({'W'}, 2)          payable by W, or by two generic
      `{C}`   -> ({'C'}, 0)          colorless is a real requirement, not generic
      `{X}`   -> nothing             X = 0, stated
    Anything unrecognized degrades to one generic rather than raising."""
    pips, generic = [], 0
    for sym in _SYM_RE.findall(cost or ""):
        s = sym.upper().strip()
        if s in ("X", "Y", "Z"):
            continue
        if s.isdigit():
            generic += int(s)
            continue
        parts = [p for p in s.split("/") if p]
        letters = frozenset(p for p in parts if p in _COLORS)
        if not letters:
            if "C" in parts:
                pips.append((frozenset("C"), 0))
            else:
                generic += 1                    # {S}, {H...}, anything odd
            continue
        nums = [int(p) for p in parts if p.isdigit()]
        pips.append((letters, nums[0] if nums else 0))
    return pips, generic


def _amount(flags):
    """How much mana one activation adds (`mana2`/`mana3`; absence means 1)."""
    if "mana3" in flags:
        return 3
    if "mana2" in flags:
        return 2
    return 1


def compile_card(card):
    """One `mtglib.Card` -> one `SimCard`, on whichever mana tier its data supports.

    Tier 1 (`produced is not None`): taps for exactly that set; `etb-tapped` gives
    nothing on the turn it drops, and `etb-tapped-cond` is pessimistically treated the
    same (Q-A2); `rock`/`dork` mark nonland producers; `mana2`/`mana3` set the amount.
    Tier 2 (`produced is None`): any color in `colors or identity` — the exact
    `deck_stats.py` expression, so the sim and the closed forms share one bias —
    untapped, with `classify()`-ramp artifacts/creatures as 1-mana producers.
    A nonland with no mana value at all is uncastable and counted (`model='none'`)."""
    flags = set(card.flags or ())
    is_land = card.is_land
    produced = card.produced

    if is_land:
        model = "exact" if produced is not None else "identity"
    elif card.mana_value is None:
        model = "none"
    elif produced is not None:
        model = "exact"
    else:
        model = "identity"

    if is_land:
        if produced is not None:
            produces = frozenset(p for p in produced if p in _MANA_LETTERS)
            etb = bool({"etb-tapped", "etb-tapped-cond"} & flags)
            amount = _amount(flags)
        else:
            # A land with no color data still taps for something — see the module
            # docstring. Enriched-and-empty (Maze of Ith) stays genuinely zero above.
            produces = frozenset(card.colors or card.identity) or frozenset("C")
            etb, amount = False, 1
        is_producer = bool(produces)
        pips, generic, castable = [], 0, False
    else:
        etb = False
        if produced is not None:
            produces = frozenset(p for p in produced if p in _MANA_LETTERS)
            is_producer = bool(produces) and bool({"rock", "dork"} & flags)
            amount = _amount(flags)
        else:
            # Ramp SORCERIES contribute nothing — a stated limitation, not an oversight.
            is_producer = ("ramp" in mtglib.classify(card)
                           and card.primary_type in ("Artifact", "Creature"))
            produces = frozenset(card.identity or card.colors) or frozenset("C")
            amount = 1
        pips, generic = parse_cost(card.mana_cost)
        if not pips and not generic and card.mana_value:
            generic = int(card.mana_value)     # attrs with an MV but no Cost column
        castable = model != "none"

    return SimCard(name=card.name, key=mtglib._norm(card.name), mv=card.mana_value,
                   pips=pips, generic=generic, is_land=is_land, produces=produces,
                   amount=amount, etb_tapped=etb, is_producer=is_producer,
                   castable=castable, model=model)


def compile_deck(enriched, commander_name=""):
    """Enriched deck cards -> `{commander, library, coverage, ...}`.

    The commander is removed from the library exactly ONCE (the deck file lists it as
    a line) via `mtglib.name_keys`, so the split/DFC trap can't leave a second copy
    shuffled in. Every other copy expands in FILE ORDER — the A/B common-random-numbers
    pairing is positional, so a re-sort here silently breaks pairing while still
    printing plausible numbers."""
    cmd_keys = mtglib.name_keys(commander_name) if commander_name else frozenset()
    commander, library = None, []
    for card in enriched:
        sc = compile_card(card)
        for _ in range(max(1, int(card.quantity or 1))):
            if commander is None and cmd_keys and (mtglib.name_keys(card.name) & cmd_keys):
                commander = sc                 # starts in the command zone
                continue
            library.append(sc)

    return _recount({"commander": commander, "library": library,
                     "commander_name": commander.name if commander else None})


def _recount(compiled):
    """(Re)derive the model tier, coverage counts and the honesty gate from whatever
    cards the compiled deck currently holds — so an A/B arm reports its own coverage
    rather than inheriting arm A's."""
    library, commander = compiled["library"], compiled["commander"]
    cards = library + ([commander] if commander else [])
    coverage = {"exact": 0, "identity": 0, "none": 0}
    for sc in cards:
        coverage[sc.model] += 1
    nonlands = [sc for sc in cards if not sc.is_land]
    no_data = sum(1 for sc in nonlands if sc.model == "none")

    if coverage["identity"] == 0 and coverage["exact"]:
        model = "exact"
    elif coverage["exact"] == 0:
        model = "identity"
    else:
        model = "mixed"

    compiled.update({
        "coverage": coverage, "model": model,
        # >25% of the nonlands with no mana value at all means the sim would be
        # guessing at the deck's whole clock — say so instead (the manabase.py
        # honesty pattern).
        "have_data": not (nonlands and no_data / len(nonlands) > NO_DATA_LIMIT),
        "no_data_nonlands": no_data, "nonlands": len(nonlands)})
    return compiled


# --------------------------------------------------------------------------- #
# Paying for things
# --------------------------------------------------------------------------- #
def _pay(pips, generic, units):
    """Spend `units` (a list of frozensets: what each available mana can be) on a
    cost. Returns the REMAINING units, or None if the cost can't be paid.

    Scarcest colored requirement first, and each is paid by the most restricted
    producer that can cover it, so a rainbow land is kept for the pip only it can
    pay. Generic is then paid from the least flexible mana left. This is a near-exact
    greedy heuristic, not an exhaustive matching — documented as such."""
    avail = list(units)
    pend = list(pips)
    need = generic
    while pend:
        best_i, best_n = 0, None
        for i, (opts, _alt) in enumerate(pend):
            n = 0
            for u in avail:
                if u & opts:
                    n += 1
            if best_n is None or n < best_n:
                best_i, best_n = i, n
                if n == 0:
                    break
        opts, alt = pend.pop(best_i)
        if best_n == 0:
            if alt:
                need += alt              # {2/W} with no W: pay the generic side
                continue
            return None
        pick, pick_len = None, None
        for i, u in enumerate(avail):
            if u & opts and (pick_len is None or len(u) < pick_len):
                pick, pick_len = i, len(u)
        avail.pop(pick)
    if len(avail) < need:
        return None
    if need:
        avail.sort(key=len)              # spend the least flexible mana on generic
        return avail[need:]
    return avail


def _mana_units(lands, producers, turn):
    """What's available this turn: `[frozenset_of_options, ...]`, one entry per mana."""
    units = []
    for sc, entered in lands:
        if sc.etb_tapped and entered == turn:
            continue                     # it came down tapped; nothing this turn
        if not sc.produces:
            continue                     # enriched and genuinely produces nothing
        for _ in range(sc.amount):
            units.append(sc.produces)
    for sc, cast_turn in producers:
        if cast_turn >= turn:
            continue                     # active the turn AFTER it resolves
        for _ in range(sc.amount):
            units.append(sc.produces)
    return units


def _bottom(hand, n):
    """London bottoming: excess lands beyond three first, then highest mana value.

    Returns (kept, bottomed). Cards with no mana value sort as the most expensive —
    they're the ones the sim can't cast at all, so they're the first spells to go."""
    lands = [i for i, c in enumerate(hand) if c.is_land]
    picks = []
    for i in lands[:max(0, len(lands) - BOTTOM_KEEP_LANDS)]:
        if len(picks) >= n:
            break
        picks.append(i)
    if len(picks) < n:
        rest = sorted((i for i in range(len(hand)) if i not in picks),
                      key=lambda i: (-(math.inf if hand[i].mv is None else hand[i].mv), i))
        for i in rest:
            if len(picks) >= n:
                break
            picks.append(i)
    chosen = set(picks)
    return ([c for i, c in enumerate(hand) if i not in chosen],
            [c for i, c in enumerate(hand) if i in chosen])


def _pick_land(hand, have_colors):
    """Untapped first, then whichever land adds the most colors you don't have,
    then file order. Index into `hand`, or None."""
    best, best_key = None, None
    for i, c in enumerate(hand):
        if not c.is_land:
            continue
        key = (1 if c.etb_tapped else 0, -len(c.produces - have_colors), i)
        if best_key is None or key < best_key:
            best, best_key = i, key
    return best


# --------------------------------------------------------------------------- #
# One game
# --------------------------------------------------------------------------- #
def play_game(rnd, commander, library, turns=TURNS, mulligan=True, on_play=True):
    """Play one goldfish game. Returns the per-game record the aggregator folds up."""
    lib = list(library)
    rnd.shuffle(lib)
    first7_lands = sum(1 for c in lib[:HAND] if c.is_land)

    mulls = 0
    while True:
        hand, rest = lib[:HAND], lib[HAND:]
        n_lands = sum(1 for c in hand if c.is_land)
        if (not mulligan or mulls >= MULL_FLOOR
                or KEEP_LANDS[0] <= n_lands <= KEEP_LANDS[1]):
            break
        mulls += 1
        rnd.shuffle(lib)
    if mulls:
        hand, bottomed = _bottom(hand, mulls)
        rest = rest + bottomed

    lands_seen = sum(1 for c in hand if c.is_land)
    cards_seen = len(hand) + mulls          # the mulligan cost is paid, not un-seen
    in_play, producers = [], []
    have_colors = set()
    cast_turn, commander_turn = {}, None
    lands_by_turn, seen_by_turn, lands_at_start = {}, {}, {}
    draws = 0
    flood_seen = 0

    for t in range(1, turns + 1):
        lands_at_start[t] = len(in_play)
        if (t > 1 or not on_play) and draws < len(rest):
            c = rest[draws]
            draws += 1
            hand.append(c)
            cards_seen += 1
            if c.is_land:
                lands_seen += 1
        # After the draw: `manabase.cards_seen(N)` counts turn N's draw as seen by the
        # start of turn N, and the two engines have to agree on that or the closed-form
        # convergence test is comparing different quantities.
        seen_by_turn[t] = cards_seen

        i = _pick_land(hand, have_colors)
        if i is not None:
            sc = hand.pop(i)
            in_play.append((sc, t))
            have_colors |= sc.produces
        lands_by_turn[t] = len(in_play)
        if t == FLOOD_TURN:
            flood_seen = lands_seen

        units = _mana_units(in_play, producers, t)
        if not units:
            continue
        # The commander goes down the moment it's payable — goldfish never recasts it,
        # so commander tax is dead code by design and isn't modeled.
        if commander is not None and commander_turn is None and commander.castable:
            rem = _pay(commander.pips, commander.generic, units)
            if rem is not None:
                commander_turn, units = t, rem
        # ONE pass, highest mana value first. No restart-after-a-cast is needed:
        # paying for something only ever removes mana, so a card that couldn't be paid
        # for a moment ago can't become payable later in the same turn.
        cast_any = False
        for j in sorted(range(len(hand)), key=lambda j: (-(hand[j].mv or 0), j)):
            sc = hand[j]
            if sc.is_land or not sc.castable:
                continue
            rem = _pay(sc.pips, sc.generic, units)
            if rem is None:
                continue
            units = rem
            hand[j] = None
            cast_any = True
            if sc.is_producer:
                producers.append((sc, t))
            if sc.key not in cast_turn:
                cast_turn[sc.key] = t
            if not units:
                break
        if cast_any:
            hand = [c for c in hand if c is not None]

    if turns < FLOOD_TURN:
        flood_seen = lands_seen
    return {"first7_lands": first7_lands, "mulls": mulls,
            "commander_turn": commander_turn, "cast_turn": cast_turn,
            "lands_by_turn": lands_by_turn, "lands_at_start": lands_at_start,
            "seen_by_turn": seen_by_turn, "lands_seen_flood": flood_seen}


# --------------------------------------------------------------------------- #
# Many games
# --------------------------------------------------------------------------- #
def _game_seeds(seed, games):
    """Int seeds only. Seeding a Random with a tuple routes through `hash()`, and
    PYTHONHASHSEED then makes 'same seed, same numbers' false across runs — which is
    the one property the disk cache and the A/B pairing both rest on."""
    master = random.Random(seed)
    return [master.getrandbits(64) for _ in range(games)]


def _run(compiled, seeds, turns, mulligan, on_play):
    commander, library = compiled["commander"], compiled["library"]
    return [play_game(random.Random(s), commander, library, turns, mulligan, on_play)
            for s in seeds]


def _mean(xs):
    return (sum(xs) / len(xs)) if xs else 0.0


def _assumptions(compiled, mulligan, on_play, games):
    cov = compiled["coverage"]
    label = {"exact": "production-aware (enriched: each permanent taps for what "
                      "Scryfall says it taps for)",
             "identity": "COLOR-IDENTITY FALLBACK — an approximation, the same bias "
                         "the hypergeometrics carry",
             "mixed": "mixed: enriched where the collection has been enriched, "
                      "color identity elsewhere"}[compiled["model"]]
    out = [
        "Goldfish: no opponent, no interaction, no combat. This measures whether the "
        "deck's own machine turns over, nothing about how it fares at a table.",
        (f"London mulligan, keep {KEEP_LANDS[0]}-{KEEP_LANDS[1]} lands, floor "
         f"{HAND - MULL_FLOOR} (at most {MULL_FLOOR} mulligans); bottoming takes "
         f"lands beyond {BOTTOM_KEEP_LANDS} first, then the highest mana values.")
        if mulligan else "Mulligans disabled — every opening seven is kept.",
        "On the play (no turn-one draw)." if on_play else "On the draw.",
        f"Mana model: {label}. "
        f"{cov['exact']} enriched · {cov['identity']} by identity · "
        f"{cov['none']} with no data.",
        "Mana rocks and dorks produce from the turn AFTER they resolve — a deliberate "
        "pessimism that costs Sol Ring one turn.",
        "Ramp sorceries (Cultivate, Rampant Growth) add no mana; only artifact and "
        "creature producers are modeled.",
        "Land drops are untapped-first then color-greedy, and spells are cast "
        "highest-mana-value-first. That's a stated pilot approximation.",
        f"Seeded Monte Carlo over {games:,} games — distinct from the exact "
        "hypergeometrics above, and meant to disagree with them: those are "
        "unconditional probabilities, these are sequenced play.",
    ]
    if cov["identity"]:
        out.append(f"[!] {cov['identity']} card(s) modeled from color IDENTITY, not "
                   "actual production. Enrich the collection (scripts/carddb.py) for "
                   "what they really tap for.")
    return out


def _card_rows(compiled, records, games, turns):
    """The sequenced castable-on-curve answer, worst first: how often each card got
    cast at all, and how much later than its mana value it landed when it did."""
    meta = {}
    for sc in compiled["library"]:
        if sc.is_land or sc.mv is None:
            continue
        meta.setdefault(sc.key, {"name": sc.name, "mv": sc.mv})
    hits = {k: [] for k in meta}
    for r in records:
        for k, t in r["cast_turn"].items():
            if k in hits:
                hits[k].append(t)
    rows = []
    for k, m in meta.items():
        ts = hits[k]
        rate = len(ts) / games if games else 0.0
        mean_first = round(_mean(ts), 2) if ts else None
        delta = round(mean_first - max(1.0, m["mv"]), 2) if ts else None
        # Worst-first blends "never got cast" with "landed late": a card cast 40% of
        # the time is worse than one that is always a turn behind schedule.
        penalty = (1 - rate) * turns + (delta or 0.0)
        rows.append({"name": m["name"], "mv": m["mv"], "cast_rate": round(rate, 3),
                     "mean_first_cast": mean_first, "delta": delta,
                     "_p": round(penalty, 4)})
    rows.sort(key=lambda r: (-r["_p"], r["name"]))
    for r in rows:
        r.pop("_p")
    return rows


def simulate(compiled, games=DEFAULT_GAMES, seed=0, turns=TURNS, mulligan=True,
             on_play=True, seeds=None, _records=False):
    """Run the sim and return the report (§6.2). Same inputs -> identical report.

    `seeds` lets an A/B run replay the exact same games in both arms (common random
    numbers). `_records` additionally returns the per-game records the pairing needs."""
    seeds = seeds if seeds is not None else _game_seeds(seed, games)
    games = len(seeds)
    records = _run(compiled, seeds, turns, mulligan, on_play)

    cmd_turns = [r["commander_turn"] for r in records if r["commander_turn"] is not None]
    p_cast_by, cum = {}, 0
    for t in range(1, min(8, turns) + 1):
        cum = sum(1 for x in cmd_turns if x <= t)
        p_cast_by[str(t)] = round(cum / games, 4) if games else 0.0
    keepable = sum(1 for r in records
                   if KEEP_LANDS[0] <= r["first7_lands"] <= KEEP_LANDS[1])
    ge3 = sum(1 for r in records if r["first7_lands"] >= 3)
    screwed = (sum(1 for r in records
                   if r["lands_at_start"].get(SCREW_TURN, 0) < SCREW_LANDS)
               if turns >= SCREW_TURN else None)
    flooded = sum(1 for r in records if r["lands_seen_flood"] >= FLOOD_LANDS)

    rep = {
        "games": games, "seed": seed, "turns": turns, "on_play": on_play,
        "mulligan": mulligan,
        "commander": compiled["commander_name"],
        "library": len(compiled["library"]),
        "have_data": compiled["have_data"],
        "model": compiled["model"], "coverage": dict(compiled["coverage"]),
        "p_cast_by": p_cast_by,
        "mean_cast_turn": round(_mean(cmd_turns), 2) if cmd_turns else None,
        "cast_rate": round(len(cmd_turns) / games, 4) if games else 0.0,
        "keepable_first7": round(keepable / games, 4) if games else 0.0,
        "p_ge3_open": round(ge3 / games, 4) if games else 0.0,
        "mulligan_rate": round(sum(1 for r in records if r["mulls"]) / games, 4)
                         if games else 0.0,
        "screw": round(screwed / games, 4) if (screwed is not None and games) else None,
        "flood": round(flooded / games, 4) if games else 0.0,
        "mean_lands_by_turn": {str(t): round(_mean([r["lands_by_turn"][t]
                                                    for r in records]), 2)
                               for t in range(1, turns + 1)},
        "cards_seen_by_turn": {str(t): round(_mean([r["seen_by_turn"][t]
                                                    for r in records]), 2)
                               for t in range(1, turns + 1)},
        "cards": _card_rows(compiled, records, games, turns),
        "definitions": dict(DEFINITIONS),
        "assumptions": _assumptions(compiled, mulligan, on_play, games),
        "note": None,
    }
    if not compiled["have_data"]:
        rep["note"] = (
            f"{compiled['no_data_nonlands']} of {compiled['nonlands']} nonland cards "
            "have no mana value (unowned, or the collection isn't enriched) — over "
            f"{int(NO_DATA_LIMIT * 100)}%, so these numbers would be fiction. Enrich "
            "the collection (scripts/carddb.py) or add the missing cards.")
    return (rep, records) if _records else rep


# --------------------------------------------------------------------------- #
# A/B over common random numbers
# --------------------------------------------------------------------------- #
AB_METRICS = ("commander_by_t4", "commander_by_t6", "keepable", "screw", "flood",
              "lands_t4")
Z95 = 1.96


def _per_game(record):
    ct = record["commander_turn"]
    return {
        "commander_by_t4": 1.0 if (ct is not None and ct <= 4) else 0.0,
        "commander_by_t6": 1.0 if (ct is not None and ct <= 6) else 0.0,
        "keepable": 1.0 if (KEEP_LANDS[0] <= record["first7_lands"] <= KEEP_LANDS[1])
                    else 0.0,
        "screw": 1.0 if record["lands_at_start"].get(SCREW_TURN, 0) < SCREW_LANDS
                 else 0.0,
        "flood": 1.0 if record["lands_seen_flood"] >= FLOOD_LANDS else 0.0,
        "lands_t4": float(record["lands_by_turn"].get(4, 0)),
    }


def _stdev(xs, mean):
    if len(xs) < 2:
        return 0.0
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1))


def simulate_ab(compiled, out_name, in_name, idx, games=DEFAULT_GAMES, seed=0,
                turns=TURNS, mulligan=True, on_play=True):
    """Swap ONE card and re-run the identical games — common random numbers.

    Arm B replaces the outgoing card's compiled entries **at the same library
    indices**, and both arms replay the same `game_seeds`, so every game differs only
    by the swap. Paired per-game differences then carry a far tighter interval than
    two independent runs would: `d̄ ± 1.96·stdev/√n`.

    The incoming card must resolve in the collection through `mtglib.lookup` — an
    unresolvable name gets a refusal, never an invented card. Returns
    `{'error': ...}` on refusal."""
    library = compiled["library"]
    keys = mtglib.name_keys(out_name)
    positions = [i for i, sc in enumerate(library) if mtglib.name_keys(sc.name) & keys]
    if not positions:
        return {"error": f"'{out_name}' isn't in this deck's library — nothing to swap "
                         "out. (The commander lives in the command zone and can't be "
                         "A/B'd.)"}
    ref = mtglib.lookup(idx, in_name) if idx else None
    if ref is None:
        return {"error": f"Can't resolve '{in_name}' in the collection — refusing to "
                         "simulate a card I can't look up. Add it to the collection "
                         "(or fix the spelling) and re-run."}
    # Singleton guard, positional: the incoming card may occupy the slots being
    # vacated (that's the A/A identity run) but must not already sit elsewhere.
    held = set(positions)
    others = {sc.key for i, sc in enumerate(library) if i not in held}
    if mtglib.name_keys(ref.name) & others:
        return {"error": f"'{ref.name}' is already elsewhere in this deck — a swap "
                         "would break singleton."}

    incoming = compile_card(ref)
    lib_b = list(library)
    for i in positions:
        lib_b[i] = incoming
    comp_b = _recount(dict(compiled, library=lib_b))

    seeds = _game_seeds(seed, games)
    rep_a, rec_a = simulate(compiled, seeds=seeds, seed=seed, turns=turns,
                            mulligan=mulligan, on_play=on_play, _records=True)
    rep_b, rec_b = simulate(comp_b, seeds=seeds, seed=seed, turns=turns,
                            mulligan=mulligan, on_play=on_play, _records=True)

    deltas = {}
    n = len(seeds)
    for m in AB_METRICS:
        a = [_per_game(r)[m] for r in rec_a]
        b = [_per_game(r)[m] for r in rec_b]
        diffs = [y - x for x, y in zip(a, b)]
        d = _mean(diffs)
        sd = _stdev(diffs, d)
        half = Z95 * sd / math.sqrt(n) if n else 0.0
        ma, mb = _mean(a), _mean(b)
        unpaired = (Z95 * math.sqrt(_stdev(a, ma) ** 2 / n + _stdev(b, mb) ** 2 / n)
                    if n else 0.0)
        deltas[m] = {"a": round(ma, 4), "b": round(mb, 4), "delta": round(d, 4),
                     "ci": round(half, 4), "lo": round(d - half, 4),
                     "hi": round(d + half, 4), "unpaired_ci": round(unpaired, 4),
                     "significant": bool(abs(d) > half > 0)}
    return {"out": out_name, "in": ref.name, "games": n, "seed": seed,
            "copies": len(positions), "a": rep_a, "b": rep_b, "deltas": deltas,
            "definitions": dict(DEFINITIONS),
            "assumptions": rep_a["assumptions"] + [
                "A/B uses common random numbers: both arms play the identical shuffles, "
                "so the interval measures the swap, not the luck."]}


# --------------------------------------------------------------------------- #
# The one shared entry point — cached, guarded, used by every surface
# --------------------------------------------------------------------------- #
def _stat(path):
    """(mtime_ns, size) or None. Nanoseconds, not whole seconds: two edits inside one
    second are exactly the case where a stale cached report would look fresh."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [st.st_mtime_ns, st.st_size]


def cache_key(deck_path, collection_path, games, seed, turns, mulligan):
    """Everything that can change the answer, cheaply — no file is parsed to build it.

    Model coverage (which §6.2 also lists) is a pure function of the attrs files
    already keyed here, and computing it would require the very load the cache exists
    to skip; it is recorded in the payload and checked on read instead."""
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    key = {"deck": _stat(deck_path), "deck_attrs": _stat(f"{stem}.attrs.csv"),
           "games": games, "seed": seed, "turns": turns, "mulligan": bool(mulligan)}
    if collection_path:
        d = os.path.dirname(collection_path) or "."
        key["collection"] = _stat(collection_path)
        key["collection_attrs"] = _stat(os.path.join(d, "collection_attrs.csv"))
        # The committed snapshot attrs overlay under the private file — a pulled
        # refresh must invalidate cached sims, or the server keeps serving
        # identity-approximation numbers labelled as enriched.
        key["collection_attrs_snapshot"] = _stat(
            os.path.join(d, "collection_attrs.snapshot.csv"))
    return key


def sim_for_deck(deck_path, collection, games=DEFAULT_GAMES, seed=0, turns=TURNS,
                 mulligan=True, cache=True, cache_dir=None, collection_path=None):
    """Load, enrich, compile and simulate ONE saved deck — behind a disk cache.

    Every surface (dashboard, assess page, assess packet) calls this and nothing else:
    the webapp re-renders `generate()` on every page view, so an uncached inline sim
    would tax every view three times over. The sim is seeded-deterministic, so the
    cache is pure speed — any deck edit, attrs refresh or parameter change misses it.

    Returns the report, or **None** on any failure. One guard here, not three
    hand-rolled copies in the surfaces."""
    import deck_stats                       # local: keeps the bare-stdlib import gate
    import deckcore                         # honest and the engine ring dependency-free
    try:
        if collection_path is None and isinstance(collection, str):
            collection_path = collection
        key = cache_key(deck_path, collection_path, games, seed, turns, mulligan)
        cdir = cache_dir if cache_dir is not None else CACHE_DIR
        stem = os.path.splitext(os.path.basename(deck_path))[0]
        cpath = os.path.join(cdir, f"{stem}.json")
        if cache:
            try:
                with open(cpath, encoding="utf-8") as f:
                    blob = json.load(f)
                if blob.get("key") == key and blob.get("report"):
                    return blob["report"]
            except (OSError, ValueError):
                pass

        coll = (collection if isinstance(collection, list)
                else mtglib.load_collection(collection))
        idx = mtglib.index_by_name(coll)
        with open(deck_path, encoding="utf-8") as f:
            text = f.read()
        deck = mtglib.parse_deck(text)
        enriched, _missing = deck_stats.analyze(deck, idx)
        dstem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
        deckcore.apply_attrs(enriched, deckcore.load_attrs(f"{dstem}.attrs.csv"))
        m = re.search(r"^#\s*Commander\s*:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
        commander = re.split(r"\s{2,}|\(", m.group(1))[0].strip() if m else ""
        compiled = compile_deck(enriched, commander)
        rep = simulate(compiled, games=games, seed=seed, turns=turns, mulligan=mulligan)
        if cache:
            try:
                os.makedirs(cdir, exist_ok=True)
                tmp = cpath + ".part"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"key": key, "report": rep}, f)
                os.replace(tmp, cpath)
            except OSError:
                pass                       # a read-only cache dir is not a failed sim
        return rep
    except Exception:
        return None


def load_for_ab(deck_path, collection, collection_path=None):
    """(compiled, idx) for an A/B run — the same load `sim_for_deck` does, without the
    cache (an A/B is never the hot path). Returns (None, None) on failure."""
    import deck_stats
    import deckcore
    try:
        coll = (collection if isinstance(collection, list)
                else mtglib.load_collection(collection))
        idx = mtglib.index_by_name(coll)
        with open(deck_path, encoding="utf-8") as f:
            text = f.read()
        enriched, _missing = deck_stats.analyze(mtglib.parse_deck(text), idx)
        dstem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
        deckcore.apply_attrs(enriched, deckcore.load_attrs(f"{dstem}.attrs.csv"))
        m = re.search(r"^#\s*Commander\s*:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
        commander = re.split(r"\s{2,}|\(", m.group(1))[0].strip() if m else ""
        return compile_deck(enriched, commander), idx
    except Exception:
        return None, None


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _pct(x):
    return "n/a" if x is None else f"{x * 100:.0f}%"


def print_report(rep):
    print(f"GOLDFISH — {rep['commander'] or 'no commander header'} "
          f"({rep['library']} card library, {rep['games']:,} games, seed {rep['seed']})")
    if not rep["have_data"]:
        print(f"\n[!] {rep['note']}")
    print(f"\nCommander on the battlefield by turn "
          f"({rep['definitions']['p_cast_by']}):")
    print("   " + " · ".join(f"T{t} {_pct(p)}" for t, p in rep["p_cast_by"].items()))
    if rep["mean_cast_turn"] is not None:
        print(f"   mean turn {rep['mean_cast_turn']} (over the "
              f"{_pct(rep['cast_rate'])} of games it landed at all)")
    print(f"\nOpening hands: keepable {_pct(rep['keepable_first7'])} "
          f"({rep['definitions']['keepable_first7']}) · "
          f">=3 lands {_pct(rep['p_ge3_open'])} · "
          f"mulliganed {_pct(rep['mulligan_rate'])}")
    print(f"Screw {_pct(rep['screw'])} ({rep['definitions']['screw']}) · "
          f"flood {_pct(rep['flood'])} ({rep['definitions']['flood']})")
    print("Lands in play: " + " · ".join(f"T{t} {v}" for t, v
                                         in rep["mean_lands_by_turn"].items()))
    worst = [c for c in rep["cards"] if c["cast_rate"] < 1.0 or (c["delta"] or 0) > 0]
    if worst:
        print(f"\nWorst-sequenced cards ({rep['definitions']['cards']}):")
        for c in worst[:12]:
            when = ("never cast" if c["mean_first_cast"] is None
                    else f"first cast T{c['mean_first_cast']} "
                         f"({c['delta']:+g} vs MV {c['mv']:g})")
            print(f"  {c['name']:<34} cast {_pct(c['cast_rate']):>4} · {when}")
    print("\nAssumptions:")
    for a in rep["assumptions"]:
        print(f"  · {a}")


def print_ab(ab):
    print(f"A/B over common random numbers — OUT {ab['out']} / IN {ab['in']} "
          f"({ab['copies']} cop{'y' if ab['copies'] == 1 else 'ies'}, "
          f"{ab['games']:,} paired games, seed {ab['seed']})\n")
    print(f"  {'metric':<18}{'A':>8}{'B':>8}{'delta':>9}{'95% CI':>16}")
    for m, d in ab["deltas"].items():
        print(f"  {m:<18}{d['a']:>8.3f}{d['b']:>8.3f}{d['delta']:>+9.3f}"
              f"   [{d['lo']:+.3f}, {d['hi']:+.3f}]"
              + ("  *" if d["significant"] else ""))
    print("\n  * the interval excludes zero. Unpaired intervals would be "
          + ", ".join(f"{m} ±{d['unpaired_ci']:.3f}" for m, d in ab["deltas"].items())
          + " — the pairing is what makes small deltas readable.")
    print("\nAssumptions:")
    for a in ab["assumptions"]:
        print(f"  · {a}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Seeded goldfish Monte Carlo for a Commander deck.")
    ap.add_argument("--deck", required=True)
    ap.add_argument("--collection", required=True)
    ap.add_argument("--games", type=int, default=CLI_GAMES)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--turns", type=int, default=TURNS)
    ap.add_argument("--no-mulligan", action="store_true",
                    help="keep every opening seven (for comparing to closed forms)")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--ab", metavar='"Out Card=In Card"',
                    help="swap one card and re-run the identical games")
    args = ap.parse_args(argv)

    for path in (args.deck, args.collection):
        if not os.path.exists(path):
            print(f"error: no such file: {path}", file=sys.stderr)
            return 2
    if args.games < 1:
        print("error: --games must be at least 1", file=sys.stderr)
        return 2

    mull = not args.no_mulligan
    if args.ab:
        if "=" not in args.ab:
            print('error: --ab wants "Out Card=In Card"', file=sys.stderr)
            return 2
        out_name, in_name = (s.strip() for s in args.ab.split("=", 1))
        compiled, idx = load_for_ab(args.deck, args.collection)
        if compiled is None:
            print("Goldfish A/B unavailable — the deck or collection couldn't be "
                  "loaded and enriched.")
            return 1
        ab = simulate_ab(compiled, out_name, in_name, idx, games=args.games,
                         seed=args.seed, turns=args.turns, mulligan=mull)
        if ab.get("error"):
            print(ab["error"])
            return 1
        if args.json:
            print(json.dumps(ab, indent=2))
        else:
            print_ab(ab)
        return 0

    rep = sim_for_deck(args.deck, args.collection, games=args.games, seed=args.seed,
                       turns=args.turns, mulligan=mull, cache=not args.no_cache)
    if rep is None:
        print("Goldfish simulation unavailable — the deck or collection couldn't be "
              "loaded and enriched. Check the paths, or enrich with scripts/carddb.py.")
        return 1
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print_report(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
