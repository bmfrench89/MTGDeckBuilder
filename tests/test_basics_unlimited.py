"""Basic lands are always owned — never a shortfall, never a buy-list candidate.

Grounding rule #9 (player-ratified 2026-08-17): the player owns hundreds of every
basic and deliberately does not track them in the collection export, so whatever
count a file happens to carry is an artifact, not a ceiling.

This is a regression test with a real history. `mtglib.is_basic` has been the
repo-wide exemption since `deck_conflicts` and `optimize` adopted it, but
`deck_stats.owned_enough()` was never updated — so a mono-green deck running 30
Forests against a snapshot recording 16 reported

    Forest: deck wants 30, you own 16

under "Ownership check", and `build_dashboard.ownership_block` rendered the same row
under **Buy-list candidates**. That is the one purchase this project must never
suggest, and it is exactly the failure a doc alone cannot prevent: the tooling has to
agree with the rule.
"""
import build_dashboard
import deck_stats
import mtglib

# 16 Forests recorded — the real snapshot's count, and far fewer than a deck runs.
COLLECTION = """\
Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity
16,Forest,0,G,G,,Land,Forest,common
1,Llanowar Elves,1,G,G,{G},Creature,Elf Druid,common
"""


def _index(tmp_path):
    p = tmp_path / "collection.csv"
    p.write_text(COLLECTION, encoding="utf-8")
    return mtglib.index_by_name(mtglib.load_collection(str(p)))


def test_basics_are_never_an_ownership_shortfall(tmp_path):
    """30 Forests against 16 recorded is not a gap — it is a fully built manabase."""
    idx = _index(tmp_path)
    deck = mtglib.parse_deck("# --- Basics ---\n30 Forest\n1 Llanowar Elves\n")

    assert deck_stats.owned_enough(deck, idx) == []


def test_non_basics_are_still_reported(tmp_path):
    """The exemption is surgical: a real shortfall must still surface."""
    idx = _index(tmp_path)
    deck = mtglib.parse_deck("3 Llanowar Elves\n30 Forest\n")

    problems = deck_stats.owned_enough(deck, idx)
    assert problems == [("Llanowar Elves", 3, 1)]


def test_every_basic_and_snow_printing_is_exempt(tmp_path):
    """Covers all six basics plus Snow-Covered, on a collection that lists none of
    them — `is_basic` is name-based precisely so this holds with no data at all."""
    idx = _index(tmp_path)
    names = ["Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes",
             "Snow-Covered Forest", "Snow-Covered Island"]
    deck = mtglib.parse_deck("".join(f"20 {n}\n" for n in names))

    assert deck_stats.owned_enough(deck, idx) == []


def test_dashboard_does_not_offer_to_sell_you_forests(tmp_path):
    """The rendered surface, not just the function — this is where the player saw it."""
    idx = _index(tmp_path)
    deck = mtglib.parse_deck("30 Forest\n1 Llanowar Elves\n")
    enriched, missing = deck_stats.analyze(deck, idx)
    rep = deck_stats.build_report(deck, enriched, missing, idx)

    assert rep["quantity_problems"] == []
    html = build_dashboard.ownership_block(rep)
    assert "Buy-list candidates" not in html
    assert "Forest" not in html
