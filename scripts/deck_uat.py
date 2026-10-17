#!/usr/bin/env python3
"""Deck UAT: the build's test run. Does this deck pass its own acceptance gates?

The app's UI changes don't merge until `webapp/uat/` passes. A deck shouldn't either. This
module turns the goldfish Monte Carlo (`goldfish.py`, tier 1 of
docs/research-simulation.md) into pass/fail gates a deck has to clear before its notes and
PR. The design is in docs/spec-deck-uat.md; this is v1, gates 1, 2 and 4.

  1. **Consistency.** A keepable opening seven, and not screwed on turn 4.
  2. **The engine turns on.** The deck's own engine is the test oracle. Its cards come from
     `<stem>.engine.json` (engine plus package cards), else the notes'
     `## Protected engine` list. The gate measures how often at least `engine_min` of them
     have been cast by turn `engine_turn`. A Sphinx deck whose Sphinxes never land fails,
     however good its mana looks.
  3. **The commander arrives.** It must be cast by `commander_turn` (default: its mana value
     plus one, inside the horizon) often enough. A deck whose plan runs from the command
     zone (the Ur-Sphinx's eminence) can lower this in its spec, with the reason in its notes.
  4. **Every swap carries an A/B.** `ab()` replays the identical games with one card
     swapped (common random numbers: `goldfish.swap_compiled`) and reports the paired delta
     of every gate metric, with a 95% interval. A session cites it in the verdict.

Thresholds live in each deck's spec as `uat` (`engine_spec.py --uat KEY VALUE`), and
anything a spec leaves out falls back to DEFAULTS. The defaults were calibrated on the
eleven real decks on 2026-10-15, and a gate that every deck fails is noise, not a test.

Every number is a goldfish frequency: no opponent, no interaction (goldfish.py's
`assumptions`, which every report carries). A deck can pass every gate and still lose to a
real table. Gate 3 of the spec, calibrated opponent pushback, is the next step.

stdlib only. Imports the goldfish and engine_spec engines and mtglib; nothing imports this
except the optimizer spoke (`--ab`) and the CLI.

    python3 scripts/deck_uat.py --deck data/decks/<stem>.txt --collection $COLL
    python3 scripts/deck_uat.py --all --collection $COLL           # every deck, exit 3 on a fail
    python3 scripts/deck_uat.py --deck d.txt --collection c.csv --ab "Out Card=In Card"
"""
import argparse
import glob
import json
import math
import os
import sys

import engine_spec
import goldfish
import mtglib

UAT_GAMES = 2000
Z95 = 1.96

# Percent thresholds are stored as whole percents, as the spec's other numbers are. The
# defaults were calibrated on the 11 real decks on 2026-10-15 (docs/spec-deck-uat.md,
# "Calibration"): every deck kept 80-83% and was screwed 13-16%, so 75/25 passes them all
# and still fails a deck cut to ~33 lands. "1+ engine card by turn 6 in half the games"
# passes ten decks (53-97%) and fails Captain America (38%), whose declared engine was
# six sleeper-audit picks rather than its Heroes.
DEFAULTS = {
    "keepable_min": 75,      # % of opening sevens with 2-5 lands
    "screw_max": 25,         # % of games with < 3 lands at the start of turn 4
    "engine_turn": 6,        # the engine is judged at the end of this turn...
    "engine_min": None,      # ...as at least this many of its cards cast (None: 1, or 2
                             # once the list has 25+ cards, so a long list of cheap
                             # package cards can't pass on any one of them)...
    "engine_pct": 50,        # ...in at least this % of games
    "commander_turn": None,  # None = the commander's mana value + 1, capped at the horizon;
                             # a 7+ mana commander is then informational, not a gate
    "commander_pct": 50,     # % of games with the commander cast by then
}
UAT_KEYS = tuple(DEFAULTS)


def thresholds(spec):
    """DEFAULTS overlaid with the spec's `uat` block (unknown keys ignored)."""
    out = dict(DEFAULTS)
    for k, v in ((spec or {}).get("uat") or {}).items():
        if k in out and isinstance(v, (int, float)):
            out[k] = int(v)
    return out


BIG_COMMANDER = 7   # mana value from which the commander gate is informational by default


def engine_min(uat, n_keys):
    """The spec's engine_min, else 1, plus one per 25 engine cards (calibrated: by turn 6
    a deck has seen ~13 cards, so a 22-card list expects ~3 engine cards SEEN and fewer
    cast; one-per-ten failed all eleven decks)."""
    if uat.get("engine_min"):
        return int(uat["engine_min"])
    return 1 + n_keys // 25


def engine_names(deck_path, spec=None):
    """(card names, source). The spec's core (engine plus packages) when the deck has one,
    else the notes' protected list, else ([], None)."""
    spec = spec if spec is not None else engine_spec.load(deck_path)
    names = engine_spec.core_names(spec) if spec else []
    if names:
        return names, "spec"
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    try:
        notes = open(f"{stem}.notes.md", encoding="utf-8").read()
    except OSError:
        notes = ""
    names = engine_spec.protected_engine_from_notes(notes)
    return (names, "notes") if names else ([], None)


def engine_keys(compiled, names):
    """The library keys of the named engine cards the sim can actually cast. Lands and
    uncastable cards are left out: the sim never casts them, so counting them would only
    lower the bar silently."""
    want = set()
    for n in names:
        want |= mtglib.name_keys(n)
    keys, uncastable = set(), []
    for sc in compiled["library"]:
        if not (mtglib.name_keys(sc.name) & want) or sc.is_land:
            continue
        if sc.castable:
            keys.add(sc.key)
        else:
            uncastable.append(sc.name)
    return keys, sorted(set(uncastable))


def _commander_turn(compiled, uat, turns):
    if uat.get("commander_turn"):
        return min(int(uat["commander_turn"]), turns)
    cmd = compiled.get("commander")
    mv = int(cmd.mv) if cmd is not None and cmd.mv is not None else 4
    return min(mv + 1, turns)


def per_game(record, keys, uat, compiled, turns):
    """The binary gate outcomes of ONE game record, as 0/1. These are the units the A/B
    pairs: the same game in both arms, differing only by the swap."""
    et = min(int(uat["engine_turn"]), turns)
    online = sum(1 for k in keys if record["cast_turn"].get(k, 99) <= et)
    need = engine_min(uat, len(keys))
    ct = _commander_turn(compiled, uat, turns)
    cmd_t = record["commander_turn"]
    return {
        "keepable": 1 if goldfish.KEEP_LANDS[0] <= record["first7_lands"]
                    <= goldfish.KEEP_LANDS[1] else 0,
        "screw": (1 if record["lands_at_start"].get(goldfish.SCREW_TURN, 0)
                  < goldfish.SCREW_LANDS else 0) if turns >= goldfish.SCREW_TURN else 0,
        "engine_online": 1 if keys and online >= need else 0,
        "commander_on_time": 1 if cmd_t is not None and cmd_t <= ct else 0,
    }


def gate_report(compiled, records, keys, uat, turns, source=None, uncastable=()):
    """The gates for one simulated deck. Pure: compiled deck plus records in, report out."""
    n = len(records) or 1
    games = [per_game(r, keys, uat, compiled, turns) for r in records]
    rate = {m: sum(g[m] for g in games) / n for m in
            ("keepable", "screw", "engine_online", "commander_on_time")}
    ct = _commander_turn(compiled, uat, turns)
    gates = [
        {"id": "keepable", "label": "Keepable opening seven (2-5 lands)",
         "value": rate["keepable"], "op": ">=", "threshold": uat["keepable_min"] / 100},
        {"id": "screw", "label": f"Screwed (< {goldfish.SCREW_LANDS} lands) on turn "
                                  f"{goldfish.SCREW_TURN}",
         "value": rate["screw"], "op": "<=", "threshold": uat["screw_max"] / 100},
        {"id": "engine_online",
         "label": f"Engine online: {engine_min(uat, len(keys))}+ of {len(keys)} engine "
                  f"cards cast by turn {min(int(uat['engine_turn']), turns)}",
         "value": rate["engine_online"], "op": ">=", "threshold": uat["engine_pct"] / 100},
        {"id": "commander_on_time", "label": f"Commander cast by turn {ct}",
         "value": rate["commander_on_time"], "op": ">=",
         "threshold": uat["commander_pct"] / 100},
    ]
    if not keys:
        # No oracle: the gate can't be judged, and it says so instead of passing.
        gates[2].update(value=None, verdict="no engine cards to test (write a spec or a "
                                            "## Protected engine list)")
    cmd = compiled.get("commander")
    big = (cmd is not None and cmd.mv is not None and cmd.mv >= BIG_COMMANDER
           and not uat.get("commander_turn"))
    if big:
        # A 7+ mana commander is a late finisher by design (and the horizon can't see
        # MV+1). Shown, never failed, until the deck's spec sets its own target.
        gates[3]["info"] = (f"informational: the commander costs {int(cmd.mv)}; set "
                            f"`--uat commander_turn` in the spec to gate it")
    for g in gates:
        if g["value"] is None:
            g["pass"] = False
            continue
        if g.get("info"):
            g["value"] = round(g["value"], 4)
            g["pass"] = True
            continue
        g["value"] = round(g["value"], 4)
        g["pass"] = (g["value"] >= g["threshold"] if g["op"] == ">="
                     else g["value"] <= g["threshold"])
    return {"gates": gates, "pass": all(g["pass"] for g in gates),
            "engine_cards": len(keys), "engine_source": source,
            "engine_uncastable": list(uncastable), "uat": dict(uat)}


def _load(deck_path, collection, collection_path=None):
    compiled, idx = goldfish.load_for_ab(deck_path, collection, collection_path)
    return compiled, idx


def run(deck_path, collection, games=UAT_GAMES, seed=0, turns=goldfish.TURNS,
        collection_path=None):
    """Simulate a saved deck and judge its gates. None when it can't be compiled."""
    compiled, _idx = _load(deck_path, collection, collection_path)
    if not compiled:
        return None
    spec = engine_spec.load(deck_path)
    uat = thresholds(spec)
    names, source = engine_names(deck_path, spec)
    keys, uncastable = engine_keys(compiled, names)
    seeds = goldfish._game_seeds(seed, games)
    rep, records = goldfish.simulate(compiled, seeds=seeds, seed=seed, turns=turns,
                                     _records=True)
    out = gate_report(compiled, records, keys, uat, turns, source, uncastable)
    out.update({"deck": os.path.splitext(os.path.basename(deck_path))[0],
                "commander": compiled["commander_name"], "games": len(seeds),
                "seed": seed, "turns": turns, "note": rep.get("note"),
                "assumptions": rep["assumptions"]})
    return out


def _paired(a, b):
    """(mean delta, half-width of the 95% interval) of paired per-game values."""
    d = [y - x for x, y in zip(a, b)]
    n = len(d)
    if not n:
        return 0.0, 0.0
    mean = sum(d) / n
    var = sum((x - mean) ** 2 for x in d) / (n - 1) if n > 1 else 0.0
    return round(mean, 4), round(Z95 * math.sqrt(var / n), 4)


def ab(deck_path, collection, out_name, in_name, games=UAT_GAMES, seed=0,
       turns=goldfish.TURNS, collection_path=None):
    """Swap ONE card and replay the identical games. Returns the paired delta of every
    gate metric (B minus A, with a 95% interval), or {"error": ...}. The engine cards are
    the deck's, so swapping an engine card out shows up as a drop in engine_online."""
    compiled, idx = _load(deck_path, collection, collection_path)
    if not compiled:
        return {"error": "this deck can't be compiled for a simulation"}
    swap = goldfish.swap_compiled(compiled, out_name, in_name, idx)
    if "error" in swap:
        return swap
    spec = engine_spec.load(deck_path)
    uat = thresholds(spec)
    names, source = engine_names(deck_path, spec)
    keys_a, _ = engine_keys(compiled, names)
    keys_b, _ = engine_keys(swap["compiled"], names)
    seeds = goldfish._game_seeds(seed, games)
    _ra, rec_a = goldfish.simulate(compiled, seeds=seeds, seed=seed, turns=turns,
                                   _records=True)
    _rb, rec_b = goldfish.simulate(swap["compiled"], seeds=seeds, seed=seed, turns=turns,
                                   _records=True)
    ga = [per_game(r, keys_a, uat, compiled, turns) for r in rec_a]
    gb = [per_game(r, keys_b, uat, swap["compiled"], turns) for r in rec_b]
    deltas = {}
    for m in ("engine_online", "commander_on_time", "keepable", "screw"):
        mean, half = _paired([g[m] for g in ga], [g[m] for g in gb])
        deltas[m] = {"delta": mean, "ci95": half,
                     "a": round(sum(g[m] for g in ga) / len(ga), 4),
                     "b": round(sum(g[m] for g in gb) / len(gb), 4)}
    return {"out": out_name, "in": swap["ref"].name, "games": len(seeds), "seed": seed,
            "engine_source": source, "deltas": deltas,
            "note": "Paired over identical shuffles: the interval measures the swap, "
                    "not the luck. Lower is better only for screw."}


def ab_summary(res):
    """One line a verdict can quote: the engine and commander deltas."""
    if not res or res.get("error"):
        return None
    e, c = res["deltas"]["engine_online"], res["deltas"]["commander_on_time"]
    return (f"A/B over {res['games']} paired games: engine online {e['delta'] * 100:+.1f}% "
            f"(±{e['ci95'] * 100:.1f}), commander on time {c['delta'] * 100:+.1f}% "
            f"(±{c['ci95'] * 100:.1f})")


def _pct(x):
    return "n/a" if x is None else f"{x * 100:.0f}%"


def print_report(r):
    mark = "PASS" if r["pass"] else "FAIL"
    lab = " [Lab]" if r.get("lab") else ""
    print(f"{mark}  {r['deck']}{lab} ({r['commander']}): {r['games']} games, seed {r['seed']}, "
          f"engine cards from the {r['engine_source'] or 'nowhere'} "
          f"({r['engine_cards']} castable)")
    for g in r["gates"]:
        if g["value"] is None:
            print(f"   FAIL  {g['label']}: {g.get('verdict')}")
            continue
        op = "≥" if g["op"] == ">=" else "≤"
        if g.get("info"):
            print(f"   info  {g['label']}: {_pct(g['value'])} ({g['info']})")
            continue
        print(f"   {'pass' if g['pass'] else 'FAIL'}  {g['label']}: {_pct(g['value'])} "
              f"(needs {op} {_pct(g['threshold'])})")
    if r["engine_uncastable"]:
        print(f"   note  engine cards the sim can't cast (no mana data): "
              f"{', '.join(r['engine_uncastable'])}")
    if r.get("note"):
        print(f"   note  {r['note']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deck UAT: run a deck's acceptance gates on "
                                             "the goldfish simulator.")
    ap.add_argument("--deck", help="data/decks/<stem>.txt")
    ap.add_argument("--all", action="store_true", help="every deck in --decks-dir, the "
                                                       "Lab's theory decks included and "
                                                       "tagged [Lab]")
    ap.add_argument("--decks-dir", default="data/decks")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--games", type=int, default=UAT_GAMES)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--ab", metavar='"Out Card=In Card"',
                    help="swap one card and report the paired gate deltas")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not args.deck and not args.all:
        print("error: pass --deck or --all", file=sys.stderr)
        return 2
    coll = mtglib.load_collection(args.collection)
    if args.ab:
        if not args.deck or "=" not in args.ab:
            print('error: --ab needs --deck and "Out Card=In Card"', file=sys.stderr)
            return 2
        out_name, in_name = (s.strip() for s in args.ab.split("=", 1))
        res = ab(args.deck, coll, out_name, in_name, args.games, args.seed,
                 collection_path=args.collection)
        if args.json:
            print(json.dumps(res, indent=1))
        elif res.get("error"):
            print(f"error: {res['error']}")
        else:
            print(f"A/B {res['out']} -> {res['in']} ({res['games']} paired games)")
            for m, d in res["deltas"].items():
                print(f"   {m}: {_pct(d['a'])} -> {_pct(d['b'])}  "
                      f"({d['delta'] * 100:+.1f}% ±{d['ci95'] * 100:.1f})")
        return 2 if res.get("error") else 0
    import deck_conflicts
    if args.all:
        # The Lab's theory decks are tested too, tagged [Lab]: a theory deck is still a
        # deck someone may sleeve, and the gates are about the list, not about copies.
        # (They were skipped until 2026-10-16, so `--all` never covered the Lab.)
        paths = sorted(glob.glob(os.path.join(args.decks_dir, "*.txt")))
    else:
        paths = [args.deck]
    reports, failed = [], 0
    for p in paths:
        r = run(p, coll, args.games, args.seed, collection_path=args.collection)
        if r is None:
            print(f"error: {p} can't be compiled for a simulation", file=sys.stderr)
            failed += 1
            continue
        r["lab"] = deck_conflicts.is_study_deck(p)
        reports.append(r)
        failed += 0 if r["pass"] else 1
        if not args.json:
            print_report(r)
    if args.json:
        print(json.dumps(reports if args.all else (reports[0] if reports else None),
                         indent=1))
    elif args.all:
        lab = sum(1 for r in reports if r.get("lab"))
        print(f"{sum(1 for r in reports if r['pass'])} of {len(paths)} deck(s) pass "
              f"every gate" + (f" ({lab} of them in the Lab)" if lab else ""))
    return 3 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
