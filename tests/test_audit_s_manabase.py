"""Audit 2026-10-11, track S: manabase — S1 (castability), S5, S9, S11 (docstring).

docs/spec-app-audit-2026-10.md. Each test pins a REPRODUCED wrong number
and fails on the pre-fix code; the point is that the specific lie cannot
come back, not general coverage. Offline and hermetic: hand-built Cards,
or files under tmp_path.
"""
import deck_stats
import manabase
import mtglib

C = mtglib.Card


def _report(cards, idx=None):
    return deck_stats.build_report(cards, cards, [], idx or {})


# --------------------------------------------------------------------------- #
# S1 — split / adventure / MDFC costs are ONE face's cost, not both summed
# --------------------------------------------------------------------------- #
RIDER = "{1}{B}{B} // {1}{B}{B}"


def test_s1_manabase_checks_two_black_pips_not_four():
    rider = C("Murderous Rider // Swift End", 1, 3.0, {"B"}, {"B"}, RIDER,
              ["Creature"])
    swamps = C("Swamp", 12, 0.0, set(), set(), "", ["Land"], ["Swamp"],
               produced={"B"}, flags_ver=2)
    cards = [rider, swamps]
    a = manabase.analyze(_report(cards), cards)
    rows = [r for r in a["risky"] if r["name"].startswith("Murderous")]
    assert rows and rows[0]["pips"] == 2, rows


# --------------------------------------------------------------------------- #
# S5 — a colour with zero pip demand is never LOW
# --------------------------------------------------------------------------- #
def test_s5_zero_demand_colour_is_not_low():
    rep = {"color_sources": {"B": 30, "W": 1}, "pip_demand": {"B": 40.0, "W": 0.0},
           "double_pips": {"B": 10}, "lands": 31, "color_sources_restricted": {},
           "color_sources_basis": {}}
    a = manabase.analyze(rep, [])
    w = next(c for c in a["colors"] if c["color"] == "W")
    assert w["status"] == "n/a"
    b = next(c for c in a["colors"] if c["color"] == "B")
    assert b["status"] == "ok"


def test_s5_unknown_demand_keeps_the_source_check():
    """No cost data at all is not 'zero demand' — that case keeps its flag."""
    rep = {"color_sources": {"W": 3}, "pip_demand": None, "double_pips": None,
           "lands": 30, "color_sources_restricted": {}, "color_sources_basis": {}}
    a = manabase.analyze(rep, [])
    assert a["colors"][0]["status"] == "low"


# --------------------------------------------------------------------------- #
# S9 — a hybrid pip is paid by the union of its colours' sources
# --------------------------------------------------------------------------- #
def test_s9_hybrid_pip_is_checked_against_the_union():
    hybrid = C("Hybrid One-Drop", 1, 1.0, {"B", "G"}, {"B", "G"}, "{B/G}",
               ["Creature"])
    lands = [C("Swamp", 15, 0.0, set(), set(), "", ["Land"], ["Swamp"],
               produced={"B"}),
             C("Forest", 15, 0.0, set(), set(), "", ["Land"], ["Forest"],
               produced={"G"})]
    cards = [hybrid] + lands
    a = manabase.analyze(_report(cards), cards)
    # 15 sources of either colour alone: ~70% by T1. 30 B-or-G sources: ~94%.
    assert not [r for r in a["risky"] if r["name"] == "Hybrid One-Drop"], a["risky"]


def test_s9_creakwood_liege_is_one_requirement_not_two():
    liege = C("Creakwood Liege", 1, 4.0, {"B", "G"}, {"B", "G"},
              "{1}{B/G}{B/G}{B/G}", ["Creature"])
    lands = [C("Swamp", 18, 0.0, set(), set(), "", ["Land"], ["Swamp"],
               produced={"B"}),
             C("Forest", 18, 0.0, set(), set(), "", ["Land"], ["Forest"],
               produced={"G"})]
    cards = [liege] + lands
    a = manabase.analyze(_report(cards), cards)
    rows = [r for r in a["risky"] if r["name"] == "Creakwood Liege"]
    assert all(r["color"] == "B/G" and r["pips"] == 3 for r in rows), rows


def test_s9_mono_costs_are_checked_exactly_as_before():
    assert manabase.pip_groups("{2}{W}{W}{U}") == {frozenset("W"): 2,
                                                   frozenset("U"): 1}


# --------------------------------------------------------------------------- #
# S11 — free spells, short A/B horizons, and the manabase docstring
# --------------------------------------------------------------------------- #
def test_s11_manabase_docstring_describes_the_production_model():
    doc = manabase.__doc__
    assert "Source counts come from each land/rock's color IDENTITY" not in doc
    assert "produced" in doc and "union" in doc
