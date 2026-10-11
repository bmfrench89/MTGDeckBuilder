"""Audit 2026-10-11, track S: deck_stats / deckcore — S1 (pip demand), S3, S4, S8, S10, D2.

docs/spec-app-audit-2026-10.md. Each test pins a REPRODUCED wrong number
and fails on the pre-fix code; the point is that the specific lie cannot
come back, not general coverage. Offline and hermetic: hand-built Cards,
or files under tmp_path.
"""
import json
import sys

import pytest

import deck_stats
import deckcore
import goldfish
import mtglib

C = mtglib.Card


def _report(cards, idx=None):
    return deck_stats.build_report(cards, cards, [], idx or {})


# --------------------------------------------------------------------------- #
# S1 — split / adventure / MDFC costs are ONE face's cost, not both summed
# --------------------------------------------------------------------------- #
RIDER = "{1}{B}{B} // {1}{B}{B}"


def test_s1_deck_stats_pip_demand_reads_the_front_face():
    rider = C("Murderous Rider // Swift End", 1, 3.0, {"B"}, {"B"}, RIDER,
              ["Creature"])
    rep = _report([rider])
    assert rep["pip_demand"]["B"] == 2.0
    assert rep["double_pips"] == {"B": 1}


# --------------------------------------------------------------------------- #
# S3 — a deck .attrs.csv's Cost and Sub-types reach the cards
# --------------------------------------------------------------------------- #
def test_s3_attrs_cost_and_subtypes_are_applied(tmp_path):
    p = tmp_path / "d.attrs.csv"
    p.write_text("Name,Type,MV,Colors,Cost,Sub-types,Produced,Flags,Power,FlagsVer\n"
                 "Cabal Ritual,Instant,2,B,{1}{B},,,ritual:3,,4\n"
                 "Crypt Ghast,Creature,4,B,{3}{B},Spirit,,,2,4\n", encoding="utf-8")
    ritual = C("Cabal Ritual")
    ghast = C("Crypt Ghast")
    deckcore.apply_attrs([ritual, ghast], deckcore.load_attrs(str(p)))
    assert ritual.mana_cost == "{1}{B}"
    assert ghast.mana_cost == "{3}{B}"
    assert ghast.subtypes == ["Spirit"]
    # And the sim now sees a black pip, not two generic.
    sc = goldfish.compile_card(ritual)
    assert sc.pips == [(frozenset("B"), 0)] and sc.generic == 1


def test_s3_multi_subtypes_cell_is_semicolon_joined(tmp_path):
    p = tmp_path / "d.attrs.csv"
    p.write_text("Name,Type,MV,Colors,Cost,Sub-types\n"
                 "Accursed Marauder,Creature,2,B,{1}{B},Zombie;Warrior\n",
                 encoding="utf-8")
    c = C("Accursed Marauder")
    deckcore.apply_attrs([c], deckcore.load_attrs(str(p)))
    assert c.subtypes == ["Zombie", "Warrior"]


def test_s3_absent_column_and_empty_cell_leave_the_collection_value(tmp_path):
    absent = tmp_path / "a.attrs.csv"
    absent.write_text("Name,Type,MV,Colors\nSol Ring,Artifact,1,\n", encoding="utf-8")
    empty = tmp_path / "e.attrs.csv"
    empty.write_text("Name,Type,MV,Colors,Cost,Sub-types\nSol Ring,Artifact,1,,,\n",
                     encoding="utf-8")
    for path in (absent, empty):
        ring = C("Sol Ring", mana_cost="{1}", subtypes=["Thing"])
        deckcore.apply_attrs([ring], deckcore.load_attrs(str(path)))
        assert ring.mana_cost == "{1}" and ring.subtypes == ["Thing"]


def test_s3_analyze_deck_pip_demand_uses_the_attrs_cost(tmp_path):
    coll = tmp_path / "coll.txt"
    coll.write_text("1 Tergrid\n1 Bottomless Pit\n30 Swamp\n", encoding="utf-8")
    deck = tmp_path / "d.txt"
    deck.write_text("# Commander: Tergrid\n1 Tergrid\n1 Bottomless Pit\n30 Swamp\n",
                    encoding="utf-8")
    (tmp_path / "d.attrs.csv").write_text(
        "Name,Type,MV,Colors,Cost,Sub-types\n"
        "Bottomless Pit,Enchantment,3,B,{1}{B}{B},\n", encoding="utf-8")
    a = deckcore.analyze_deck(str(deck), str(coll))
    assert a["report"]["pip_demand"]["B"] == 2.0


# --------------------------------------------------------------------------- #
# S4 — the deck_stats CLI applies the deck's .attrs.csv companion
# --------------------------------------------------------------------------- #
def test_s4_deck_stats_cli_counts_attrs_typed_lands(tmp_path, monkeypatch, capsys):
    coll = tmp_path / "coll.txt"
    coll.write_text("1 Baxter Building\n1 Stark Industries\n1 Sol Ring\n",
                    encoding="utf-8")
    deck = tmp_path / "d.txt"
    deck.write_text("1 Baxter Building\n1 Stark Industries\n1 Sol Ring\n",
                    encoding="utf-8")
    (tmp_path / "d.attrs.csv").write_text(
        "Name,Type,MV,Colors\nBaxter Building,Land,0,\nStark Industries,Land,0,\n"
        "Sol Ring,Artifact,1,\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["deck_stats.py", "--deck", str(deck),
                                      "--collection", str(coll), "--json"])
    assert deck_stats.main() == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["lands"] == 2, "name-only heuristics can't see these two lands"


# --------------------------------------------------------------------------- #
# S8 — an attrs Type cell never downgrades a richer type list
# --------------------------------------------------------------------------- #
def test_s8_primary_type_cell_keeps_artifact_creature(tmp_path):
    p = tmp_path / "d.attrs.csv"
    p.write_text("Name,Type,MV,Colors\nSteel Overseer,Creature,3,\n", encoding="utf-8")
    c = C("Steel Overseer", types=["Artifact", "Creature"])
    deckcore.apply_attrs([c], deckcore.load_attrs(str(p)))
    assert c.types == ["Artifact", "Creature"]


@pytest.mark.parametrize("cell", ["Artifact Creature", "Artifact;Creature",
                                  "Legendary Artifact Creature — Golem"])


def test_s8_multi_type_cells_parse_every_type(tmp_path, cell):
    p = tmp_path / "d.attrs.csv"
    p.write_text(f"Name,Type,MV,Colors\nThing,\"{cell}\",3,\n", encoding="utf-8")
    c = C("Thing")
    deckcore.apply_attrs([c], deckcore.load_attrs(str(p)))
    assert c.types == ["Artifact", "Creature"]
    sc = goldfish.compile_card(c)
    assert sc.is_creature and "artifact" in sc.typewords


def test_s8_a_new_type_still_replaces(tmp_path):
    p = tmp_path / "d.attrs.csv"
    p.write_text("Name,Type,MV,Colors\nThing,Land,0,\n", encoding="utf-8")
    c = C("Thing", types=["Creature"])
    deckcore.apply_attrs([c], deckcore.load_attrs(str(p)))
    assert c.types == ["Land"]


# --------------------------------------------------------------------------- #
# S10 — basics the export omits are synthesized, with the colour they make
# --------------------------------------------------------------------------- #
def test_s10_missing_basics_are_synthesized_with_their_colour():
    deck = [C("Tergrid, God of Fright"), C("Snow-Covered Swamp", 20), C("Wastes", 2)]
    idx = mtglib.index_by_name([C("Tergrid, God of Fright", types=["Creature"])])
    enriched, missing = deck_stats.analyze(deck, idx)
    assert [m.name for m in missing] == [], "basics are always owned (rule #9)"
    snow = next(c for c in enriched if c.name == "Snow-Covered Swamp")
    assert snow.is_land and snow.produced == {"B"} and snow.subtypes == ["Swamp"]
    wastes = next(c for c in enriched if c.name == "Wastes")
    assert wastes.produced == {"C"} and wastes.subtypes == []
    rep = deck_stats.build_report(deck, enriched, missing, idx)
    assert rep["color_sources"] == {"B": 20}
    assert rep["color_sources_basis"]["restriction_unknown_lands"] == 0, \
        "a synthesized basic was never enriched — the v1 label is false for it"
    assert rep["color_sources_basis"]["produced_lands"] == 22


def test_s10_unenriched_land_is_not_labelled_pre_vocabulary():
    vault = C("Vault of the Archangel", 1, 0.0, {"W", "B"}, {"W", "B"}, "", ["Land"])
    rep = _report([vault])
    assert rep["color_sources_basis"]["identity_lands"] == 1
    assert rep["color_sources_basis"]["restriction_unknown_lands"] == 0


# --------------------------------------------------------------------------- #
# D2 (deckcore half) — the Buy view never lists something the player has
# --------------------------------------------------------------------------- #
def test_d2_owned_and_basic_rows_are_dropped():
    idx = mtglib.index_by_name([C("Sol Ring", 1), C("Rhystic Study", 1)])
    curated = [{"card": "Sol Ring", "price": 1.0, "tier": "", "replaces": "",
                "reason": "old row"},
               {"card": "Forest", "price": 0.1, "tier": "", "replaces": "",
                "reason": "basic"},
               {"card": "Mana Crypt", "price": 150.0, "tier": "", "replaces": "",
                "reason": "real buy"}]
    near = {"near": [{"name": "c", "result": "r", "missing": "Rhystic Study",
                      "missing_owned": False}]}
    rows = deckcore.buy_signals(curated, near, [C("Snow-Covered Swamp")], idx)
    assert [r["card"] for r in rows] == ["Mana Crypt"]


def test_d2_in_deck_rows_drop_but_the_buy_badge_stays():
    deck = [C("Arcane Signet"), C("Smothering Tithe")]
    curated = [{"card": "Arcane Signet", "price": 1.0, "tier": "", "replaces": "",
                "reason": "already running it"}]
    missing = [C("Smothering Tithe")]          # in the 99, not owned: a real buy
    rows = deckcore.buy_signals(curated, {}, missing, None, deck=deck)
    assert [(r["card"], r["source"]) for r in rows] == [("Smothering Tithe",
                                                         "decklist")]
