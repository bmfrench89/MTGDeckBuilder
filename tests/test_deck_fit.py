"""The fit engine's "field" signal.

Regression for a real failure: the builder preferred a vanilla 1-drop Hero over Director
Nick Fury (played in 95% of Captain America decks) purely because it cost less mana —
every on-tribe creature scored identically except for the curve component. Feeding EDHREC
inclusion % into the staple component fixes the ordering.
"""
import deck_fit
import mtglib


def _card(name, mv, types=("Creature",), subtypes=("Hero",)):
    return mtglib.Card(name=name, quantity=1, mana_value=mv, colors={"W"}, identity={"W"},
                       mana_cost="{" + str(int(mv)) + "}", types=list(types),
                       subtypes=list(subtypes))


REP = {"categories": {}, "lands": 0}
REFS = {"game_changers": set(), "tutors": set(), "fast_mana": set()}


def _ctx(field=None):
    return {"identity": {"W"}, "archetype": [], "theme": "", "tribal": "hero",
            "commander": "Test", "field": field or {}}


def test_without_field_the_cheap_vanilla_card_wins():
    """Documents the old behaviour: curve is the only differentiator."""
    cheap = deck_fit.assess_card(_card("Vanilla Hero", 1), REP, _ctx(), REFS)["score"]
    payoff = deck_fit.assess_card(_card("Real Payoff", 3), REP, _ctx(), REFS)["score"]
    assert cheap > payoff


def test_field_signal_promotes_the_archetype_auto_include():
    """With EDHREC data, a 95%-played 3-drop must outrank a 0%-played 1-drop."""
    field = {mtglib._norm("Real Payoff"): 95}
    cheap = deck_fit.assess_card(_card("Vanilla Hero", 1), REP, _ctx(field), REFS)["score"]
    payoff = deck_fit.assess_card(_card("Real Payoff", 3), REP, _ctx(field), REFS)["score"]
    assert payoff > cheap


def test_inclusion_tiers_are_monotonic():
    scores = []
    for inc in (10, 25, 45, 65, 85):
        field = {mtglib._norm("X"): inc}
        scores.append(deck_fit.assess_card(_card("X", 3), REP, _ctx(field), REFS)["score"])
    assert scores == sorted(scores)


def test_field_never_lowers_a_curated_staple():
    """A Game Changer keeps its 15 even if the field rarely plays it here."""
    refs = {"game_changers": {mtglib._norm("Big Staple")}, "tutors": set(), "fast_mana": set()}
    plain = deck_fit.assess_card(_card("Big Staple", 3), REP, _ctx(), refs)["score"]
    with_low_field = deck_fit.assess_card(
        _card("Big Staple", 3), REP, _ctx({mtglib._norm("Big Staple"): 5}), refs)["score"]
    assert with_low_field == plain


def test_reason_text_explains_the_field_signal():
    field = {mtglib._norm("Real Payoff"): 95}
    r = deck_fit.assess_card(_card("Real Payoff", 3), REP, _ctx(field), REFS)
    power = [x for x in r["reasons"] if x["label"] == "Power"][0]
    assert "95%" in power["detail"]


def test_missing_field_key_is_safe():
    """No EDHREC data (offline) must not change scoring or raise."""
    a = deck_fit.assess_card(_card("X", 2), REP, _ctx(), REFS)["score"]
    ctx_no_key = {"identity": {"W"}, "archetype": [], "theme": "", "tribal": "hero",
                  "commander": "Test"}                      # no "field" at all
    b = deck_fit.assess_card(_card("X", 2), REP, ctx_no_key, REFS)["score"]
    assert a == b


def test_load_field_is_graceful_without_a_commander():
    assert deck_fit.load_field("") == {}
