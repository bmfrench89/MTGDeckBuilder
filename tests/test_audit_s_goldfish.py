"""Audit 2026-10-11, track S: goldfish — S1 (parse_cost), S2, S6, S7, S11 (free spells, short A/B).

docs/spec-app-audit-2026-10.md. Each test pins a REPRODUCED wrong number
and fails on the pre-fix code; the point is that the specific lie cannot
come back, not general coverage. Offline and hermetic: hand-built Cards,
or files under tmp_path.
"""
import goldfish
import mtglib

C = mtglib.Card


# --------------------------------------------------------------------------- #
# S1 — split / adventure / MDFC costs are ONE face's cost, not both summed
# --------------------------------------------------------------------------- #
RIDER = "{1}{B}{B} // {1}{B}{B}"


def test_s1_goldfish_compiles_only_the_front_face():
    pips, generic = goldfish.parse_cost(RIDER)
    assert generic == 1
    assert pips == [(frozenset("B"), 0), (frozenset("B"), 0)]
    # Miles Morales (MV 2): {1}{G} on the front, a 6-drop on the back.
    pips, generic = goldfish.parse_cost("{1}{G} // {3}{R}{G}{W}")
    assert (pips, generic) == ([(frozenset("G"), 0)], 1)


# --------------------------------------------------------------------------- #
# S2 — the clock median is over ALL games (non-kills = +inf)
# --------------------------------------------------------------------------- #
def _records(firsts, tables):
    return [{"first_kill": f, "table_kill": t, "unknown_power_casts": 0,
             "creature_casts": 3, "damage": 10} for f, t in zip(firsts, tables)]


def test_s2_first_kill_median_counts_the_games_that_never_killed():
    firsts = [2, 3, 4, 5, 6, 7, None, None, None, None]     # 60% kill rate
    tables = [None] * 10
    clk = goldfish._clock({"library": [], "commander": None},
                          _records(firsts, tables), 10, 10)
    # Kills-only median was 4.5 — the fast 30th percentile wearing a median label.
    assert clk["median_first_kill"] == 6.5
    assert clk["kill_rate"] == 0.6


def test_s2_table_kill_median_is_none_below_half_the_games():
    firsts = [3] * 10
    tables = [5, 6, 7, None, None, None, None, None, None, None]
    clk = goldfish._clock({"library": [], "commander": None},
                          _records(firsts, tables), 10, 10)
    assert clk["median_table_kill"] is None, "30% of games is no median"
    assert clk["table_kill_rate"] == 0.3


def test_s2_first_kill_median_none_when_most_games_never_kill():
    firsts = [2, 3, 4, None, None, None, None, None, None, None]
    clk = goldfish._clock({"library": [], "commander": None},
                          _records(firsts, [None] * 10), 10, 10)
    assert clk["median_first_kill"] is None
    assert clk["bracket_hint"] is None


# --------------------------------------------------------------------------- #
# S6 — the goldfish disk cache keys on EVERY collection input
# --------------------------------------------------------------------------- #
def test_s6_owned_additions_changes_the_cache_key(tmp_path):
    deck = tmp_path / "d.txt"
    deck.write_text("1 Sol Ring\n", encoding="utf-8")
    coll = tmp_path / "coll.txt"
    coll.write_text("1 Sol Ring\n", encoding="utf-8")
    k1 = goldfish.cache_key(str(deck), str(coll), 100, 0, 10, True)
    (tmp_path / "owned_additions.txt").write_text("1 Fireball Guy\n",
                                                  encoding="utf-8")
    k2 = goldfish.cache_key(str(deck), str(coll), 100, 0, 10, True)
    assert k1 != k2


def test_s6_owned_addition_reaches_a_previously_cached_sim(tmp_path, monkeypatch):
    deck = tmp_path / "d.txt"
    deck.write_text("# Commander: Cmd\n1 Cmd\n40 Island\n1 Fireball Guy\n",
                    encoding="utf-8")
    coll = tmp_path / "coll.txt"
    coll.write_text("1 Cmd\n40 Island\n", encoding="utf-8")
    cdir = str(tmp_path / "cache")
    calls = []
    real = goldfish.simulate
    monkeypatch.setattr(goldfish, "simulate",
                        lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    goldfish.sim_for_deck(str(deck), str(coll), games=20, cache_dir=cdir)
    (tmp_path / "owned_additions.txt").write_text("1 Fireball Guy\n",
                                                  encoding="utf-8")
    goldfish.sim_for_deck(str(deck), str(coll), games=20, cache_dir=cdir)
    assert len(calls) == 2, "the player's confirmed card must miss the cache"


# --------------------------------------------------------------------------- #
# S7 — disruption recasts the commander for real, paying commander tax
# --------------------------------------------------------------------------- #
def _recasts(tax, turns=7):
    cmd = C("Red Guy", 1, 1.0, {"R"}, {"R"}, "{R}", ["Creature"], produced=set(),
            power=1)
    mountains = C("Mountain", 99, 0.0, set(), set(), "", ["Land"], ["Mountain"],
                  produced={"R"})
    comp = goldfish.compile_deck([cmd, mountains], "Red Guy")
    sched = {"wipe_turns": (99, 99), "removal_every": 1, "removal_from": 2,
             "commander_tax": tax}
    import random
    rec = goldfish.play_game(random.Random(1), comp["commander"], comp["library"],
                             turns=turns, mulligan=False, disruption=sched,
                             drnd=random.Random(2))
    return rec


def test_s7_commander_is_recast_after_removal_and_tax_is_paid():
    # One land per turn, commander {R}. Removal every turn from T2 while it's out.
    # tax 0: removed T2..T7 and recast the same turn each time -> 6 recasts.
    # tax 2: T2 removed (next cost 3) -> recast T3 (3 lands); T4 removed (cost 5)
    #        -> recast T5; T6 removed (cost 7) -> recast T7. Three recasts.
    assert _recasts(0)["recasts"] == 6
    rec = _recasts(2)
    assert rec["recasts"] == 3
    assert rec["commander_removed"] == 3
    assert rec["commander_turn"] == 1, "first cast is still the first cast"


def test_s7_report_names_removals_and_tax():
    cmd = C("Big Guy", 1, 2.0, {"R"}, {"R"}, "{1}{R}", ["Creature"], produced=set(),
            power=5)
    cards = [cmd, C("Mountain", 99, 0.0, set(), {"R"}, "", ["Land"], ["Mountain"],
                    produced={"R"})]
    comp = goldfish.compile_deck(cards, "Big Guy")
    rep = goldfish.simulate_disrupted(comp, goldfish.DISRUPTION["standard"], games=60)
    dis = rep["disruption"]
    assert dis["commander_tax"] == 2
    assert dis["commander_recasts_per_game"] > 0
    assert dis["commander_recasts_per_game"] <= dis["commander_removals_per_game"]


# --------------------------------------------------------------------------- #
# S11 — free spells, short A/B horizons, and the manabase docstring
# --------------------------------------------------------------------------- #
def test_s11_zero_cost_spell_is_cast_with_no_mana():
    free = C("Free Thing", 99, 0.0, set(), set(), "", ["Artifact"], produced=set())
    comp = goldfish.compile_deck([free])
    rep = goldfish.simulate(comp, games=20, mulligan=False, turns=3)
    row = next(r for r in rep["cards"] if r["name"] == "Free Thing")
    assert row["cast_rate"] == 1.0 and row["mean_first_cast"] == 1.0


def test_s11_rituals_still_cast_the_commander_early():
    """Dropping the early continue must not break the ritual path."""
    cmd = C("Cmd", 1, 3.0, {"B"}, {"B"}, "{1}{B}{B}", ["Creature"], produced=set(),
            power=2)
    rit = C("Dark Ritual", 30, 1.0, {"B"}, {"B"}, "{B}", ["Instant"],
            produced={"B"}, flags={"ritual:3"}, flags_ver=4)
    sw = C("Swamp", 69, 0.0, set(), set(), "", ["Land"], ["Swamp"], produced={"B"})
    comp = goldfish.compile_deck([cmd, rit, sw], "Cmd")
    rep = goldfish.simulate(comp, games=200, seed=3)
    assert rep["p_cast_by"]["1"] > 0.5


def test_s11_ab_refuses_turn_gated_metrics_on_a_short_horizon(collection_file):
    cards = [C("Island", 40, 0.0, {"U"}, {"U"}, "", ["Land"]),
             C("Sol Ring", 1, 1.0, set(), set(), "{1}", ["Artifact"]),
             C("Counterspell", 1, 2.0, {"U"}, {"U"}, "{U}{U}", ["Instant"])]
    comp = goldfish.compile_deck(cards)
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    ab = goldfish.simulate_ab(comp, "Sol Ring", "Swords to Plowshares", idx,
                              games=30, turns=3)
    for m in ("commander_by_t4", "commander_by_t6", "screw", "lands_t4", "flood"):
        assert ab["deltas"][m] is None, m
    assert ab["gated"]["commander_by_t6"] == 6
    assert ab["deltas"]["keepable"] is not None
    full = goldfish.simulate_ab(comp, "Sol Ring", "Swords to Plowshares", idx,
                                games=30, turns=10)
    assert all(v is not None for v in full["deltas"].values())
    assert full["gated"] == {}


def test_s11_print_ab_survives_gated_metrics(collection_file, capsys):
    cards = [C("Island", 40, 0.0, {"U"}, {"U"}, "", ["Land"]),
             C("Sol Ring", 1, 1.0, set(), set(), "{1}", ["Artifact"])]
    comp = goldfish.compile_deck(cards)
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    ab = goldfish.simulate_ab(comp, "Sol Ring", "Swords to Plowshares", idx,
                              games=10, turns=2)
    goldfish.print_ab(ab)
    assert "needs --turns >= 4" in capsys.readouterr().out
