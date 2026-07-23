#!/usr/bin/env python3
"""Manabase & consistency analytics via the hypergeometric distribution.

No games are simulated — every number is exact probability from the deck's
composition: opening-hand and by-turn-N odds for lands and colored sources, plus a
per-card "castable on curve?" check. Colored-source adequacy references Frank
Karsten's 99-card guidelines ("How Many Sources Do You Need to Consistently Cast
Your Spells?", 2022): a reliably castable single-pip color wants ~19 sources and a
double-pip card wants more (~23+; ~30 to have both by turn 2).

Grounding / honesty:
  * Source counts come from each land/rock's color IDENTITY — an approximation of
    what it actually taps for (good for basics, duals, signets; rough for oddballs).
  * The probabilities here are UNCONDITIONAL (not mulligan-adjusted the way
    Karsten's published tables are), so read them as a consistent relative guide,
    not the exact % Karsten prints.
  * Needs color/cost data (enriched collection or a deck `.attrs.csv`); it says so
    and stays quiet when the data isn't there rather than guessing.

See docs/spec-interactive-analytics-ai.md (Phase 2).
"""
import math

import mtglib

DECK = 99            # library size in Commander (100 - commander in the zone)
HAND = 7
# Karsten 99-card colored-source guidelines (mulligan-adjusted, ~90%+ on curve).
KARSTEN_1PIP = 19            # a single-pip color you want reliably
KARSTEN_2PIP = 23           # a color with double-pip cards (raise toward ~30 if early)
# Exact-probability adequacy thresholds used for the pass/warn flags below.
OK_OPEN = 0.85              # want P(>=1 source in opening hand) at least this
OK_DOUBLE = 0.80           # want P(>=2 sources by turn 3) at least this for double-pips


def hypergeom_at_least(pop, successes, draws, k):
    """P(draw >= k successes) when drawing `draws` cards from a `pop`-card
    population containing `successes` successes. Exact (math.comb)."""
    successes = max(0, min(successes, pop))
    draws = max(0, min(draws, pop))
    if k <= 0:
        return 1.0
    if k > successes or k > draws:
        return 0.0
    total = math.comb(pop, draws)
    p_lt = sum(math.comb(successes, i) * math.comb(pop - successes, draws - i)
               for i in range(0, k)) / total          # comb() is 0 when k>n
    return max(0.0, min(1.0, 1.0 - p_lt))


def cards_seen(turn, on_play=True):
    """Cards seen by the start of your `turn` (on the play you skip the turn-1 draw)."""
    return HAND + (turn - 1 if on_play else turn)


def land_odds(lands, deck=DECK):
    """Opening-hand land count distribution + a 'keepable' (2-5 lands) probability."""
    dist = {}
    for n in range(0, HAND + 1):
        dist[n] = (hypergeom_at_least(deck, lands, HAND, n)
                   - hypergeom_at_least(deck, lands, HAND, n + 1))
    keepable = sum(v for n, v in dist.items() if 2 <= n <= 5)
    return {"dist": dist, "keepable": keepable,
            "ge3_open": hypergeom_at_least(deck, lands, HAND, 3),
            "ge4_by_t4": hypergeom_at_least(deck, lands, cards_seen(4), 4)}


def color_odds(sources, deck=DECK):
    return {"ge1_open": hypergeom_at_least(deck, sources, HAND, 1),
            "ge2_by_t3": hypergeom_at_least(deck, sources, cards_seen(3), 2)}


def analyze(rep, enriched, deck=DECK):
    """Consistency report from a deck_stats report (color_sources / pip_demand /
    double_pips / lands) + the enriched card list. Returns None-ish flags when the
    color/cost data isn't available."""
    sources = rep.get("color_sources") or {}
    demand = rep.get("pip_demand") or {}
    doubles = rep.get("double_pips") or {}
    lands = rep.get("lands") or 0
    have_colors = bool(sources or demand)

    colors = []
    for col in "WUBRG":
        dem, src, dbl = demand.get(col, 0), sources.get(col, 0), doubles.get(col, 0)
        if not dem and not src:
            continue
        odds = color_odds(src, deck)
        target = KARSTEN_2PIP if dbl else KARSTEN_1PIP
        # Pass/fail follows Karsten's recommended SOURCE COUNT (the cited guideline);
        # the exact probabilities below are shown as informational context.
        ok = src >= target
        colors.append({
            "color": col, "sources": src, "demand": round(dem, 1), "double_pips": dbl,
            "p_open": round(odds["ge1_open"], 2), "p_two_t3": round(odds["ge2_by_t3"], 2),
            "karsten_target": target, "status": "ok" if ok else "low",
        })

    # per-card castable-on-curve check (unconditional hypergeometric)
    risky = []
    for c in enriched:
        if c.is_land or not c.mana_cost or c.mana_value is None:
            continue
        turn = max(1, int(math.ceil(c.mana_value)))
        seen = cards_seen(turn)
        worst = None
        for col, need in mtglib.pip_counts(c.mana_cost).items():
            need_i = int(math.ceil(need))
            if need_i <= 0:
                continue
            p = hypergeom_at_least(deck, sources.get(col, 0), seen, need_i)
            if worst is None or p < worst["p"]:
                worst = {"color": col, "p": p, "pips": need_i}
        if worst and worst["p"] < OK_OPEN:
            risky.append({"name": c.name, "mv": c.mana_value, "color": worst["color"],
                          "pips": worst["pips"], "p": round(worst["p"], 2)})
    risky.sort(key=lambda x: x["p"])

    return {
        "have_colors": have_colors,
        "lands": lands,
        "land_odds": land_odds(lands, deck) if lands else None,
        "colors": colors,
        "risky": risky[:12],
        "risky_total": len(risky),
    }


if __name__ == "__main__":
    import argparse
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import deck_stats
    import deckcore
    ap = argparse.ArgumentParser(description="Deck manabase / consistency analysis.")
    ap.add_argument("--deck", required=True)
    ap.add_argument("--collection", required=True)
    args = ap.parse_args()
    coll = mtglib.load_collection(args.collection)
    idx = mtglib.index_by_name(coll)
    with open(args.deck, encoding="utf-8") as f:
        deck = mtglib.parse_deck(f.read())
    enriched, missing = deck_stats.analyze(deck, idx)
    stem = args.deck[:-4] if args.deck.endswith(".txt") else args.deck
    deckcore.apply_attrs(enriched, deckcore.load_attrs(f"{stem}.attrs.csv"))
    rep = deck_stats.build_report(deck, enriched, missing, idx)
    a = analyze(rep, enriched)
    if not a["have_colors"]:
        print("No color/cost data — enrich the collection or add a .attrs.csv.")
        raise SystemExit(0)
    lo = a["land_odds"]
    if lo:
        print(f"Lands {a['lands']}: keepable hand {lo['keepable']*100:.0f}% · "
              f">=3 in opener {lo['ge3_open']*100:.0f}% · >=4 by turn 4 {lo['ge4_by_t4']*100:.0f}%")
    print("\nColor sources vs demand (Karsten target · P>=1 opener):")
    for c in a["colors"]:
        flag = "  <-- LOW" if c["status"] == "low" else ""
        print(f"  {c['color']}: {c['sources']:>2} src · demand {c['demand']:>4} · "
              f"target ~{c['karsten_target']} · P {c['p_open']*100:>3.0f}%"
              + (f" · P(>=2 by t3) {c['p_two_t3']*100:.0f}%" if c['double_pips'] else "") + flag)
    if a["risky"]:
        print(f"\n{a['risky_total']} card(s) risky to cast on curve (lowest first):")
        for r in a["risky"]:
            print(f"  {r['name']} (MV {r['mv']:g}, {r['pips']}x{r['color']}): {r['p']*100:.0f}%")
