"""The deck-flow review's quick wins (2026-10-15).

- auto_build's role aims follow archetype and colour: no counterspell quota without blue
  (both the Giada and Thorin drafts pulled in Rebuff the Wicked to fill it), and those
  slots go to protection from the verified resilience list.
- A swap between two GENERIC cards (both under 2x lift) needs only GENERIC_MARGIN, and
  only on a gain the field shows in inclusion %, so role-template pressure still can't
  invent a swap.
- Validation reads owned top-25 coverage, not raw overlap.
Everything is hermetic."""
import pytest

import auto_build
import deckcore
import mtglib


# ---- role aims -------------------------------------------------------------------------

def test_no_counterspell_quota_without_blue():
    q, prot = auto_build.role_quota({"W"}, [])
    assert dict(q)["counter"] == 0 and prot == auto_build.PROTECTION_AIM
    q, prot = auto_build.role_quota({"W", "U"}, [])
    assert dict(q)["counter"] == 4 and prot == 0


def test_archetype_aims_and_how_two_words_combine():
    d = dict(auto_build.role_quota({"U", "B"}, ["control"])[0])
    assert (d["counter"], d["draw"], d["removal"]) == (8, 12, 7)
    assert dict(auto_build.role_quota({"W"}, ["go-wide"])[0])["wipe"] == 1
    # interaction takes the LOWER aim, engine roles the HIGHER
    assert dict(auto_build.role_quota({"W"}, ["voltron", "control"])[0])["removal"] == 7
    assert dict(auto_build.role_quota({"W"}, ["control", "voltron"])[0])["removal"] == 7
    assert dict(auto_build.role_quota({"R"}, ["artifacts", "landfall"])[0])["ramp"] == 15
    assert dict(auto_build.role_quota({"R"}, ["landfall", "artifacts"])[0])["ramp"] == 15


WORDS = sorted(set(auto_build._ARCHETYPE_AIM) | set(deckcore._ARCHETYPE_ROLE_RANGE)
               | {"unknown-word"})


@pytest.mark.parametrize("ident", [{"W"}, {"U"}, {"W", "U", "B", "R", "G"}, set()])
@pytest.mark.parametrize("word", WORDS)
def test_every_aim_sits_inside_its_archetype_band(ident, word):
    """An aim outside the acceptance band builds a deck the optimizer calls broken."""
    bands = deckcore.role_ranges([word])
    for role, aim in auto_build.role_quota(ident, [word])[0]:
        lo, hi = bands[role]
        assert lo <= aim <= hi, f"{word} {sorted(ident)}: {role} {aim} outside {lo}-{hi}"


def _write_pool(tmp_path):
    rows = ["Quantity,Name,Identities,Types,Sub-types,Mana cost,Mana Value",
            "1,Test Commander,W,Legendary Creature,Human,{W},1",
            "1,Swiftfoot Boots,,Artifact,Equipment,{2},2",
            "1,Mana Tithe,W,Instant,,{W},1",
            "1,Rebuff the Wicked,W,Instant,,{W},1"]
    rows += [f"1,White Soldier {i},W,Creature,Soldier,{{1}}{{W}},2" for i in range(80)]
    p = tmp_path / "pool.csv"
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return str(p)


def test_a_mono_white_draft_takes_protection_not_counter_filler(tmp_path):
    coll = mtglib.load_collection(_write_pool(tmp_path))
    d = auto_build.build("Test Commander", coll, mtglib.index_by_name(coll),
                         decks_dir=None, identity={"W"})
    names = {c["name"] for _t, cards in d["sections"] for c in cards}
    assert d["targets"]["counter"] == 0
    assert d["targets"]["protection"] == auto_build.PROTECTION_AIM
    assert "Swiftfoot Boots" in names, "a verified protection piece fills the slot"
    assert d["counts"].get("protection", 0) >= 1


# ---- the generic-slot margin -------------------------------------------------------------

COLL = """\
Quantity,Name,Identities,Types,Sub-types,Mana cost,Mana Value
1,Test Commander,G,Legendary Creature,Elf,{G},1
1,Clunky Rock,,Artifact,,{3},3
1,Popular Rock,,Artifact,,{2},2
"""

DECK = """\
# Title: G
# Commander: Test Commander
# Colors: G

# --- Commander ---
1 Test Commander

# --- Artifacts ---
1 Clunky Rock

# --- Basics ---
10 Forest
"""


def _run(tmp_path, monkeypatch, field, synergy):
    import optimize
    d = tmp_path / "gm"
    d.mkdir(exist_ok=True)
    (d / "collection.csv").write_text(COLL, encoding="utf-8")
    (d / "deck.txt").write_text(DECK, encoding="utf-8")
    monkeypatch.setattr(optimize.deck_fit, "load_field", lambda *a, **k: field)
    monkeypatch.setattr(optimize.deck_fit, "load_synergy", lambda *a, **k: synergy)
    monkeypatch.setattr(optimize.deck_fit, "load_field_lands", lambda *a, **k: set())
    monkeypatch.setattr(optimize.deck_fit, "load_field_n", lambda *a, **k: 5000)
    monkeypatch.setattr(optimize.deck_fit, "assess_card", lambda *a, **k: {"score": 50})
    monkeypatch.setattr(optimize.deck_fit, "primary_role", lambda c: "other")
    coll = mtglib.load_collection(str(d / "collection.csv"))
    r = optimize.optimize(str(d / "deck.txt"), coll, mtglib.index_by_name(coll), str(d))
    return [(s[0], s[2]) for s in r["swaps"]]


def test_a_generic_upgrade_the_field_shows_clears_the_lower_bar(tmp_path, monkeypatch):
    field = {"clunky rock": 4, "popular rock": 22, "forest": 90}
    synergy = {"clunky rock": 0, "popular rock": 2}          # both ~1x: generic
    assert _run(tmp_path, monkeypatch, field, synergy) == [("Clunky Rock", "Popular Rock")]


def test_an_engine_slot_keeps_the_full_margin(tmp_path, monkeypatch):
    field = {"clunky rock": 4, "popular rock": 22, "forest": 90}
    synergy = {"clunky rock": 3, "popular rock": 2}          # the cut is 4x: specific
    assert _run(tmp_path, monkeypatch, field, synergy) == []


def test_unmeasured_lift_gets_no_discount(tmp_path, monkeypatch):
    field = {"clunky rock": 4, "popular rock": 22, "forest": 90}
    assert _run(tmp_path, monkeypatch, field, {}) == []


def test_a_gain_under_the_generic_margin_is_still_refused(tmp_path, monkeypatch):
    field = {"clunky rock": 10, "popular rock": 22, "forest": 90}
    synergy = {"clunky rock": 1, "popular rock": 2}
    assert _run(tmp_path, monkeypatch, field, synergy) == []


# ---- owned top-25 coverage ---------------------------------------------------------------

def test_field_coverage_splits_in_owned_out_and_unowned(tmp_path):
    import optimize
    p = tmp_path / "c.csv"
    p.write_text("Quantity,Name,Identities,Types,Sub-types,Mana cost,Mana Value\n"
                 "1,Test Commander,G,Legendary Creature,Elf,{G},1\n"
                 "1,In Card,G,Instant,,{G},1\n"
                 "1,Free Card,G,Instant,,{G},1\n"
                 "1,Held Card,G,Instant,,{G},1\n", encoding="utf-8")
    coll = mtglib.load_collection(str(p))
    idx = mtglib.index_by_name(coll)
    field = {"test commander": 100, "in card": 90, "free card": 80, "held card": 70,
             "unowned card": 60, "forest": 99}
    names = {"unowned card": "Unowned Card"}
    usage = {"Held Card": {"decks": {"other-deck": 1}, "total": 1, "owned": 1}}
    cov = optimize.field_coverage(field, names, {"in card"}, idx, usage, "Test Commander")
    assert cov["top"] == 4, "the commander and basics never count"
    assert cov["n_in"] == 1 and cov["owned"] == 3 and cov["owned_pct"] == 33
    out = {o["name"]: o for o in cov["owned_out"]}
    assert out["Free Card"]["free"] is True
    assert out["Held Card"]["free"] is False and out["Held Card"]["held_by"] == ["other-deck"]
    assert cov["not_owned"] == ["Unowned Card"]
    assert optimize.field_coverage({}, {}, set(), idx, {}, "X") is None
