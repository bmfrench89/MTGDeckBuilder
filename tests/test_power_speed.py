"""The CRISPI **Speed** axis — the guard against a fast deck being called slow.

`docs/spec-crispi-axes.md` Phase A. The axis exists because `power.py` printed
"Bracket 4 … 31/100 Casual" for a deck with twelve early two-card infinites: the
bracket saw the combos, the composite score saw no tutors/fast mana/draw, and the row
as a whole was nonsense.

The thing these tests actually protect is the RESOLUTION ORDER, because every wrong
answer here is a confident lie about how fast a deck is:

  * combo evidence outranks the combat clock. `goldfish`'s clock is combat-only and
    says so; a sacrifice-loop deck with 22 creatures presents a mediocre clock and a
    turn-3 kill, and the clock must not be allowed to speak over the loop.
  * "slow" and "unmeasured" are DIFFERENT answers. `goldfish` nulls the median when
    fewer than half the games reach lethal, so a real-but-slow deck arrives with
    `have_data` True and no median. Calling it "unmeasured" understates what was
    measured; printing a turn number overstates it. The rate is the honest answer,
    and this distinction was found in implementation — the spec had collapsed it.
  * `clock=None` is a first-class input. `auto_build`'s synthetic 99 and the bare CLI
    have no simulation, and must degrade to a label rather than a zero.

Offline and pure: every case here is a hand-built dict, so the suite never runs a
Monte Carlo to test the thing that consumes one.
"""
import power


def _clock(**kw):
    """A clock shaped like `goldfish._clock`'s payload, defaults to a usable one."""
    base = {"have_data": True, "median_first_kill": 6, "kill_rate": 0.8,
            "horizon": 10, "bracket_hint": 3, "noncombat_sources": [], "note": None}
    base.update(kw)
    return base


def test_early_combo_outranks_even_a_fast_clock():
    """The defect in one test: a deck with an early infinite is 'combo (early)',
    no matter how the combat clock reads. The Bartolome deck is the live case."""
    axis = power.speed_axis(
        {"complete": [{"name": "A + B", "early": True}]}, _clock(median_first_kill=4))
    assert axis["label"] == "combo (early)"
    assert axis["basis"] == "combo-early"


def test_complete_but_not_early_reads_setup():
    """Y'shtola's #135 line is complete and NOT early — she must read 'combo (setup)',
    which is also why she is not the right deck to test the 'unmeasured' fallback."""
    axis = power.speed_axis({"complete": [{"name": "Seer + Titan", "early": False}]},
                            _clock())
    assert axis["label"] == "combo (setup)"


def test_combat_clock_used_only_when_no_combo():
    axis = power.speed_axis({"complete": []}, _clock(median_first_kill=7))
    assert axis["label"] == "combat T7"
    assert axis["combat_turn"] == 7


def test_slow_is_not_unmeasured():
    """The state the spec collapsed. have_data True + median None means MEASURED and
    slow; the rate is the number, and the label must not claim ignorance."""
    axis = power.speed_axis({"complete": []}, _clock(
        median_first_kill=None, kill_rate=0.09,
        note="Lethal presented in only 9% of games within 10 turns"))
    assert axis["basis"] == "combat-slow"
    assert "slow" in axis["label"] and "9%" in axis["label"]
    assert "unmeasured" not in axis["label"]


def test_no_clock_is_unmeasured_and_never_zero():
    """The honesty case: a deck the goldfish cannot kill with is unmeasured, NOT
    slow and NOT 0. The reason travels from the clock's own note."""
    axis = power.speed_axis({"complete": []}, _clock(
        have_data=False, median_first_kill=None,
        note="No clock: the sim never cast a creature."))
    assert axis["label"] == "unmeasured (no combat clock)"
    assert "never cast a creature" in axis["detail"]
    assert axis["combat_turn"] is None


def test_clock_none_degrades_to_a_label():
    """`clock=None` is legitimate input (auto_build's synthetic 99, bare CLI)."""
    axis = power.speed_axis({"complete": []}, None)
    assert axis["label"] == "unmeasured (no combat clock)"
    assert axis["detail"]           # a reason, not an empty string


def test_missing_detected_does_not_explode():
    assert power.speed_axis(None, None)["basis"] == "unmeasured"


def test_understated_caveat_rides_along_beside_a_combo_label():
    """A drain deck's clock carries an UNDERSTATED warning. It must survive even when
    the combo branch wins, because a reader comparing the two numbers needs it."""
    axis = power.speed_axis({"complete": [{"name": "X", "early": True}]},
                            _clock(noncombat_sources=["Blood Artist"]))
    assert axis["label"] == "combo (early)"
    assert axis["caveat"] and "understates" in axis["caveat"]


def test_bracket_hint_is_reused_not_rederived():
    """Two mappings from median->bracket in two modules is how they start
    disagreeing; the axis must take goldfish's answer verbatim."""
    assert power.speed_axis({"complete": []}, _clock(bracket_hint=4))["bracket_hint"] == 4


def test_every_branch_has_a_short_form_for_the_rank_table():
    """--rank prints in a fixed-width column; a long label there collided with the
    Tier column when this shipped."""
    for detected, clock in (({"complete": [{"name": "X", "early": True}]}, None),
                            ({"complete": [{"name": "X", "early": False}]}, None),
                            ({"complete": []}, _clock()),
                            ({"complete": []}, _clock(median_first_kill=None,
                                                      kill_rate=0.1)),
                            ({"complete": []}, None)):
        axis = power.speed_axis(detected, clock)
        assert axis["short"] and len(axis["short"]) <= 22


def test_clock_for_deck_never_raises(tmp_path):
    """Every failure path (no collection, missing deck, unreadable sim) returns None
    so the axis degrades to a label instead of taking a surface down."""
    assert power.clock_for_deck("whatever.txt", None) is None
    assert power.clock_for_deck(str(tmp_path / "nope.txt"), str(tmp_path / "c.txt")) is None


def test_partial_clock_dict_degrades_instead_of_crashing():
    """speed_axis is public and pure; a clock dict missing `kill_rate` (anything short
    of goldfish's full payload) must yield a label, not a TypeError. Found in the
    Phase A revalidation: `rate * 100` crashed on rate=None for both the slow and
    combat branches."""
    a = power.speed_axis({"complete": []}, {"have_data": True,
                                            "median_first_kill": None})
    assert a["basis"] == "combat-slow" and "0%" in a["label"]
    b = power.speed_axis({"complete": []}, {"have_data": True,
                                            "median_first_kill": 6})
    assert b["label"] == "combat T6"
