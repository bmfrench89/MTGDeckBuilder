"""Dead weight — the cards nothing in the deck is asking for.

Borrowed from the prior-art survey (docs/research-prior-art.md): flegars/mtg-deckbuilder
surfaces "cards that don't synergise with anything else". The value is in what it must
NOT do — it is not a cut list, it never edits a deck, and it must not simply rank the
deck's most expensive cards.

The comparison is relative to the deck's own median rather than an absolute score,
because fit scores shift wholesale depending on whether EDHREC data was reachable. The
suite is offline, so every test here runs in exactly the no-field-data case that broke
the first (absolute-threshold) implementation.
"""
import os
import sys

import pytest

import deck_fit
import deckcore
import power


CARDS = """Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,MARKET
1,Sol Ring,1,,,{1},Artifact,,uncommon,a1,1.50
1,Arcane Signet,2,,,{2},Artifact,,common,b2,0.90
1,Swords to Plowshares,1,W,W,{W},Instant,,uncommon,st,2.00
1,Counterspell,2,U,U,{U}{U},Instant,,common,c3,0.75
1,Vanilla Bear,6,W,W,{5}{W},Creature,Bear,common,v9,0.05
1,Clunky Golem,7,,,{7},Artifact Creature,Golem,common,cg,0.05
12,Island,0,,,,Land,Island,common,f6,0.10
1,Test Commander,4,W U,W U,{2}{W}{U},Legendary Creature,Human Wizard,rare,g7,1.00
"""

DECK = """# Title: T
# Commander: Test Commander
# Colors: W U

# --- Ramp ---
1 Sol Ring
1 Arcane Signet

# --- Interaction ---
1 Swords to Plowshares
1 Counterspell

# --- Creatures ---
1 Vanilla Bear
1 Clunky Golem

# --- Lands ---
10 Island
"""


@pytest.fixture
def built(tmp_path):
    deck = tmp_path / "t.txt"
    deck.write_text(DECK, encoding="utf-8")
    coll = tmp_path / "c.csv"
    coll.write_text(CARDS, encoding="utf-8")
    a = deckcore.analyze_deck(str(deck), str(coll))
    ctx = deck_fit.deck_context(str(deck), a["enriched"], "Test Commander")
    return {"deck": str(deck), "coll": str(coll), "a": a, "ctx": ctx,
            "refs": power.load_refs()}


def _dead(built, **kw):
    return deck_fit.dead_weight(built["a"]["enriched"], built["a"]["report"],
                                built["ctx"], built["refs"], **kw)


def test_flags_the_passengers_and_not_the_functional_cards(built):
    names = {r["name"] for r in _dead(built)}
    assert "Vanilla Bear" in names and "Clunky Golem" in names
    for functional in ("Sol Ring", "Swords to Plowshares", "Counterspell"):
        assert functional not in names, f"{functional} is doing a job — must not be flagged"


def test_is_relative_to_this_decks_own_median(built):
    """The whole point of the relative rule: it works with no field data, where every
    absolute cutoff either fires on everything or nothing."""
    rows = _dead(built)
    assert rows, "offline (no EDHREC data) must still produce a meaningful read"
    med = rows[0]["median"]
    assert all(r["score"] < med for r in rows)


def test_never_flags_a_land(built):
    """The manabase pass owns lands; judging Island on 'theme tie' is meaningless."""
    assert not any(r["name"] == "Island" for r in _dead(built))


def test_respects_cards_the_player_named_in_the_game_plan(built):
    """A card in the player's own notes has an explicit reason to be there. The answer
    to 'why is this here' is not 'the heuristic disagrees'."""
    import mtglib
    prot = {mtglib._norm("Vanilla Bear")}
    assert not any(r["name"] == "Vanilla Bear" for r in _dead(built, protected=prot))


def test_says_why_rather_than_just_naming_a_card(built):
    for r in _dead(built):
        assert r["why"] and "no theme tie" in r["why"]
        assert r["band"]


def test_a_tiny_list_produces_no_outliers(built):
    """With almost no cards there is no meaningful middle to be below."""
    few = built["a"]["enriched"][:2]
    assert deck_fit.dead_weight(few, built["a"]["report"], built["ctx"],
                                built["refs"]) == []


def test_it_does_not_touch_the_deck_file(built):
    before = open(built["deck"], encoding="utf-8").read()
    _dead(built)
    assert open(built["deck"], encoding="utf-8").read() == before


def test_dashboard_shows_it_in_the_power_tab_with_an_offline_caveat(built):
    import build_dashboard as bd
    html = bd.generate(built["deck"], built["coll"], title="T",
                       commander="Test Commander")["dashboard"]
    assert "Pulling the Least Weight" in html
    assert html.index("Pulling the Least Weight") > html.index("data-tab='power'")
    # offline => no field data => the read must admit what it is
    assert "fit-only read" in html
    assert "Not an instruction to cut" in html
