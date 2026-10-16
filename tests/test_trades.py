"""Trades between decks (deck-flow review bundle D).

A card offered as a trade must be (1) held in full by another deck, (2) not part of that
deck's core (engine spec, '## Protected engine' list, clip-featured, hand-added; a deck
with no declared core protects everything its notes name), and (3) worth asking for here
(engine, commander-specific, or 60+). It comes with a free backfill in the same role, or
only when the gain clearly beats the donor's loss. Nothing is applied. Hermetic."""
import pytest

import deck_fit
import engine_spec
import mtglib
import optimize

COLL = """\
Quantity,Name,Identities,Types,Sub-types,Mana cost,Mana Value
1,Here Commander,G,Legendary Creature,Elf,{G},1
1,There Commander,G,Legendary Creature,Bear,{G},1
1,Wanted Card,G,Enchantment,,{2}{G},3
1,Core Card,G,Enchantment,,{2}{G},3
1,Named Card,G,Enchantment,,{2}{G},3
1,Spare Card,G,Enchantment,,{2}{G},3
"""


def _deck(title, commander, cards):
    return (f"# Title: {title}\n# Commander: {commander}\n# Colors: G\n\n"
            f"# --- Commander ---\n1 {commander}\n\n# --- Enchantments ---\n"
            + "".join(f"1 {c}\n" for c in cards) + "\n# --- Basics ---\n30 Forest\n")


ROLES = {}


@pytest.fixture
def world(tmp_path, monkeypatch):
    ROLES.clear()
    d = tmp_path / "decks"
    d.mkdir()
    (tmp_path / "c.csv").write_text(COLL, encoding="utf-8")
    (d / "here.txt").write_text(_deck("Here", "Here Commander", []), encoding="utf-8")
    (d / "there.txt").write_text(
        _deck("There Deck", "There Commander", ["Wanted Card", "Core Card", "Named Card"]),
        encoding="utf-8")
    fields = {"Here Commander": {"wanted card": 30, "core card": 30, "named card": 30},
              "There Commander": {"wanted card": 10, "spare card": 15}}
    monkeypatch.setattr(deck_fit, "load_field", lambda cmd, *a, **k: fields.get(cmd, {}))
    monkeypatch.setattr(deck_fit, "primary_role", lambda c: ROLES.get(c.name, "draw"))
    coll = mtglib.load_collection(str(tmp_path / "c.csv"))
    return d, coll, mtglib.index_by_name(coll)


def _offers(world, value=65, engine=frozenset(), ctx=None):
    d, coll, idx = world
    return optimize.trade_offers("here", str(d), coll, idx, {"G"}, set(),
                                 lambda n, ref=None: value, ctx or {"field": {}}, engine)


def test_a_declared_core_is_never_offered(world):
    d = world[0]
    (d / "there.notes.md").write_text("## Protected engine\n- Core Card\n", encoding="utf-8")
    names = {o["card"] for o in _offers(world)}
    assert "Core Card" not in names
    assert {"Wanted Card", "Named Card"} <= names, "a declared core frees everything else"


def test_without_a_declared_core_every_named_card_is_core(world):
    d = world[0]
    (d / "there.notes.md").write_text("# Plan\nNamed Card is the whole point.\n",
                                      encoding="utf-8")
    names = {o["card"] for o in _offers(world)}
    assert "Named Card" not in names and "Wanted Card" in names


def test_an_offer_carries_a_backfill_and_uses_it_once(world):
    d = world[0]
    (d / "there.notes.md").write_text("## Protected engine\n- Core Card\n", encoding="utf-8")
    offers = _offers(world)
    with_bf = [o for o in offers if o["backfill"]]
    assert len(with_bf) == 1 and with_bf[0]["backfill"]["name"] == "Spare Card", \
        "one free Spare Card backfills one trade, not two"
    assert offers[0]["from_title"] == "There Deck"


def test_no_backfill_and_no_clear_gain_means_no_offer(world):
    d = world[0]
    (d / "there.notes.md").write_text("## Protected engine\n- Core Card\n", encoding="utf-8")
    # value 60 here vs 10% there: gain 50, offered even without a backfill
    assert len(_offers(world, value=60)) == 2
    # a weak card here never qualifies at all
    assert _offers(world, value=30) == []


def test_engine_cards_here_qualify_and_lead(world):
    d = world[0]
    (d / "there.notes.md").write_text("## Protected engine\n- Core Card\n", encoding="utf-8")
    offers = _offers(world, value=20, engine=mtglib.name_keys("Named Card"))
    assert [o["card"] for o in offers] == ["Named Card"]
    assert offers[0]["engine_here"] is True


def test_a_card_with_a_free_copy_is_not_a_trade(world, tmp_path):
    d, _c, _i = world
    (tmp_path / "c.csv").write_text(COLL.replace("1,Wanted Card", "2,Wanted Card"),
                                    encoding="utf-8")
    coll = mtglib.load_collection(str(tmp_path / "c.csv"))
    (d / "there.notes.md").write_text("## Protected engine\n- Core Card\n", encoding="utf-8")
    offers = optimize.trade_offers("here", str(d), coll, mtglib.index_by_name(coll), {"G"},
                                   set(), lambda n, ref=None: 65, {"field": {}})
    assert "Wanted Card" not in {o["card"] for o in offers}, "a free copy is a proposal's job"


def test_deck_core_reads_spec_list_clips_and_hand_adds(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text(_deck("X", "Here Commander", ["A", "B"]), encoding="utf-8")
    keys, declared = optimize.deck_core(str(p))
    assert declared is False and keys == set()
    (tmp_path / "x.notes.md").write_text("## Protected engine\n- A\n", encoding="utf-8")
    keys, declared = optimize.deck_core(str(p))
    assert declared and mtglib._norm("A") in keys
    engine_spec.save(str(tmp_path / "x.engine.json"), {"engine": ["B"], "keep": {}})
    keys, _ = optimize.deck_core(str(p))
    assert mtglib._norm("B") in keys and mtglib._norm("A") not in keys, "the spec wins"
    (tmp_path / "x.changes.csv").write_text(
        "Card,Added,Replaced,Source\nA,2026-10-15,Z,manual-replace\n", encoding="utf-8")
    keys, _ = optimize.deck_core(str(p))
    assert mtglib._norm("A") in keys, "the player's own add is core"



# ---- the Fable review fixes (2026-10-15) --------------------------------------------------

def test_a_card_the_donors_notes_name_stays_core_even_with_a_declared_list(world):
    """Smuggler's Surprise was offered out of Beorn, whose wipe plan names it, because a
    declared list used to switch the notes check off. The optimizer protects notes-named
    cards from cuts; the trades lane must agree."""
    d = world[0]
    (d / "there.notes.md").write_text(
        "## Protected engine\n- Core Card\n\n## Wipe plan\nKeep Named Card up.\n",
        encoding="utf-8")
    names = {o["card"] for o in _offers(world)}
    assert "Named Card" not in names and "Wanted Card" in names


def test_an_earmark_releases_a_named_card(world):
    d = world[0]
    (d / "there.notes.md").write_text(
        "## Protected engine\n- Core Card\n\nNamed Card is earmarked.\n\n"
        "## Earmarked for other decks\n- Named Card\n", encoding="utf-8")
    offers = _offers(world)
    named = [o for o in offers if o["card"] == "Named Card"]
    assert named and named[0]["earmarked"] is True
    assert offers[0]["card"] == "Named Card", "an earmarked card leads the list"


def test_a_backfill_must_do_the_same_job(world):
    """Fog is a 'spell'; so is Smuggler's Surprise. A type is not a job: no backfill."""
    d = world[0]
    (d / "there.notes.md").write_text("## Protected engine\n- Core Card\n", encoding="utf-8")
    ROLES.update({"Wanted Card": "spell", "Named Card": "spell", "Spare Card": "spell"})
    offers = _offers(world, value=60)
    assert offers and all(o["backfill"] is None for o in offers)


def test_a_pinned_card_is_never_offered(world):
    d, coll, idx = world
    (d / "there.notes.md").write_text("## Protected engine\n- Core Card\n", encoding="utf-8")
    offers = optimize.trade_offers("here", str(d), coll, idx, {"G"}, set(),
                                   lambda n, ref=None: 65, {"field": {}},
                                   pins={"wanted card": "there"})
    assert "Wanted Card" not in {o["card"] for o in offers}
