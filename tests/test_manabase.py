"""The hypergeometric engine — the flagship analytic. Verified against values that can be
computed by hand, so a refactor can't quietly change the probabilities."""
import manabase


def test_known_value_ace_in_opening_five():
    """P(>=1 ace in a 5-card draw from a 52-card deck) = 0.3412 (classic check)."""
    assert round(manabase.hypergeom_at_least(52, 4, 5, 1), 4) == 0.3412


def test_certainty_and_impossibility():
    # every card is a hit -> certain
    assert manabase.hypergeom_at_least(10, 10, 3, 1) == 1.0
    # no hits in the deck -> impossible
    assert manabase.hypergeom_at_least(10, 0, 3, 1) == 0.0
    # asking for more hits than exist -> impossible
    assert manabase.hypergeom_at_least(10, 2, 5, 3) == 0.0


def test_probability_is_monotonic_in_sources():
    """More sources can never lower the odds — guards against an inverted formula."""
    p = [manabase.hypergeom_at_least(99, s, 7, 1) for s in (10, 15, 20, 25)]
    assert p == sorted(p)


def test_probability_is_monotonic_in_cards_drawn():
    p = [manabase.hypergeom_at_least(99, 20, n, 1) for n in (7, 8, 9, 10)]
    assert p == sorted(p)


def test_probabilities_stay_in_range():
    for args in [(99, 37, 7, 3), (99, 20, 7, 1), (60, 24, 7, 2)]:
        assert 0.0 <= manabase.hypergeom_at_least(*args) <= 1.0


def test_karsten_targets_present():
    """The published Karsten guideline numbers the report compares against."""
    assert manabase.KARSTEN_1PIP > 0 and manabase.KARSTEN_2PIP > manabase.KARSTEN_1PIP
