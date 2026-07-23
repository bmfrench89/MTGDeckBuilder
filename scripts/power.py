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
import sys

import mtglib
import deck_stats
import combo_detector

try:
    import build_dashboard  # for load_attrs/apply_attrs (attrs power the curve)
except Exception:
    build_dashboard = None

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


def assess(enriched, rep, refs):
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

    return {
        "bracket": bracket, "bracket_name": name, "bracket_reasons": reasons,
        "power": power, "tier": tier, "components": comps,
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


def build_for_deck(deck_path, coll_index, ref_dir=REF_DIR_DEFAULT):
    with open(deck_path, encoding="utf-8") as f:
        deck = mtglib.parse_deck(f.read())
    enriched, missing = deck_stats.analyze(deck, coll_index)
    if build_dashboard is not None:
        stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
        attrs = build_dashboard.load_attrs(f"{stem}.attrs.csv")
        build_dashboard.apply_attrs(enriched, attrs)
    rep = deck_stats.build_report(deck, enriched, missing, coll_index)
    return assess(enriched, rep, load_refs(ref_dir))


def print_one(deck_path, res):
    print("=" * 60)
    print(f"POWER & BRACKET — {os.path.basename(deck_path)}")
    print("=" * 60)
    print(f"Bracket {res['bracket']} — {res['bracket_name']}")
    for r in res["bracket_reasons"]:
        print(f"    · {r}")
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
        results = [(d, build_for_deck(d, idx, args.ref_dir)) for d in decks]
        results.sort(key=lambda x: -x[1]["power"])
        if args.json:
            print(json.dumps([{"deck": os.path.basename(d), **r}
                              for d, r in results], indent=2))
            return 0
        print("POWER RANKING — your decks, strongest first\n")
        print(f"  {'#':<3}{'Deck':<28}{'Bracket':<20}{'Power':>6}  Tier")
        print("  " + "-" * 66)
        for i, (d, r) in enumerate(results, 1):
            name = os.path.basename(d)[:-4]
            b = f"{r['bracket']} {r['bracket_name']}"
            print(f"  {i:<3}{name:<28}{b:<20}{r['power']:>4}/100  {r['tier']}")
        return 0

    if not args.deck:
        ap.error("provide --deck, or --rank")
    res = build_for_deck(args.deck, idx, args.ref_dir)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print_one(args.deck, res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
