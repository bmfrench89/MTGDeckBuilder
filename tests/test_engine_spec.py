"""Engine-first builds (deck-flow review bundle C).

A session writes `<stem>.engine.json` before the draft. auto_build seeds its engine and
package cards ahead of every quota, counts them toward their roles, and labels every
other non-land card filler. `engine_spec.py --audit` fails until each filler card is kept
with a reason or cut. The optimizer protects the spec's core, and field-silent reads rank
by the spec's keywords against locally cached oracle text. Everything is hermetic."""
import json
import os

import pytest

import auto_build
import carddb
import engine_spec
import mtglib

NOTES = """# Plan

## Protected engine (don't cut)
- Engine One
- Engine Two

## Interaction
- Swords
"""

DECK = """\
# Title: E
# Commander: Test Commander
# Colors: W

# --- Commander ---
1 Test Commander

# --- Creatures ---
1 Engine One
1 Filler Bear

# --- Instants ---
1 Engine Two
1 Kept Spell

# --- Lands ---
1 Utility Land

# --- Basics ---
30 Plains
"""


@pytest.fixture
def deck(tmp_path):
    p = tmp_path / "e.txt"
    p.write_text(DECK, encoding="utf-8")
    (tmp_path / "e.notes.md").write_text(NOTES, encoding="utf-8")
    return str(p)


def test_init_reads_the_protected_engine_list(deck):
    assert engine_spec.main(["--deck", deck, "--init"]) == 0
    spec = engine_spec.load(deck)
    assert spec["engine"] == ["Engine One", "Engine Two"]
    assert spec["commander"] == "Test Commander"
    assert engine_spec.main(["--deck", deck, "--init"]) == 2, "never overwrites a spec"


def test_audit_fails_until_every_card_has_a_reason(deck, capsys):
    engine_spec.main(["--deck", deck, "--init"])
    assert engine_spec.main(["--deck", deck, "--audit"]) == 3
    out = capsys.readouterr().out
    assert "no reason to keep: Filler Bear" in out and "Kept Spell" in out
    assert "Utility Land" not in out and "Plains" not in out and "Test Commander" not in out
    engine_spec.main(["--deck", deck, "--keep", "Kept Spell", "cheap interaction",
                      "--keep", "Filler Bear", "the only two-drop body"])
    assert engine_spec.main(["--deck", deck, "--audit"]) == 0


def test_keep_needs_a_reason_and_a_card_in_the_deck(deck, capsys):
    engine_spec.main(["--deck", deck, "--init"])
    assert engine_spec.main(["--deck", deck, "--keep", "Kept Spell", "  "]) == 2
    engine_spec.main(["--deck", deck, "--keep", "Not In Deck", "why"])
    assert "not in the deck, not kept: Not In Deck" in capsys.readouterr().out


def test_no_spec_is_never_a_pass(deck):
    assert engine_spec.main(["--deck", deck, "--audit"]) == 3


def test_a_broken_spec_reads_as_none(tmp_path):
    p = tmp_path / "x.engine.json"
    p.write_text("{nope", encoding="utf-8")
    assert engine_spec.load(str(p)) is None


def test_core_names_include_packages_once():
    spec = {"engine": ["A"], "packages": [{"name": "p", "enablers": ["B", "A"],
                                           "payoffs": ["C"]}]}
    assert engine_spec.core_names(spec) == ["A", "B", "C"]


def test_missing_engine_cards_are_reported(deck, capsys):
    engine_spec.save(engine_spec.spec_path(deck),
                     {"engine": ["Engine One", "Gone Card"], "keep": {}})
    _unexplained, missing = engine_spec.audit(deck)
    assert missing == ["Gone Card"]


# ---- auto_build --engine -------------------------------------------------------------

def _pool(tmp_path):
    rows = ["Quantity,Name,Identities,Types,Sub-types,Mana cost,Mana Value",
            "1,Test Commander,W,Legendary Creature,Angel,{W},1",
            "1,Obscure Engine,W,Enchantment,,{5}{W}{W},7",
            "1,Off Colour Piece,B,Enchantment,,{B},1"]
    rows += [f"1,White Soldier {i},W,Creature,Soldier,{{1}}{{W}},2" for i in range(80)]
    p = tmp_path / "pool.csv"
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    coll = mtglib.load_collection(str(p))
    return coll, mtglib.index_by_name(coll)


def test_engine_cards_go_in_first_and_the_rest_is_filler(tmp_path):
    coll, idx = _pool(tmp_path)
    spec = {"engine": ["Obscure Engine", "Off Colour Piece", "Never Owned"],
            "packages": [], "aims": {}, "keywords": [], "keep": {}}
    d = auto_build.build("Test Commander", coll, idx, decks_dir=None, identity={"W"},
                         engine=spec)
    names = {c["name"] for _t, cards in d["sections"] for c in cards}
    assert "Obscure Engine" in names and d["engine_cards"] == ["Obscure Engine"]
    why = {m["name"]: m["why"] for m in d["engine_missing"]}
    assert why == {"Off Colour Piece": "outside the colour identity",
                   "Never Owned": "not owned"}
    assert "Obscure Engine" not in d["filler"] and len(d["filler"]) > 0
    assert d["total"] == 100


def test_spec_aims_are_clamped_into_the_band():
    assert auto_build.role_quota({"W"}, [], {"draw": 13})[0][1] == ("draw", 12), \
        "an aim is clamped into the band (draw 8-12 by default)"


# ---- the optimizer: protection and keyword reads -----------------------------------------

def test_the_optimizer_protects_the_spec_core(deck):
    import optimize
    engine_spec.save(engine_spec.spec_path(deck), {"engine": ["Filler Bear"], "keep": {}})
    _keep, notes = optimize._protected(deck, "Test Commander")
    assert "filler bear" in notes


def test_cached_oracle_text_reads_the_local_cache(tmp_path):
    carddb._cache_put(carddb._verify_key("Niv Test"),
                      {"name": "Niv Test", "oracle_text": "Whenever a source you control "
                       "deals noncombat damage to an opponent, draw."}, str(tmp_path))
    assert "noncombat damage" in carddb.cached_oracle_text("Niv Test", str(tmp_path))
    assert carddb.cached_oracle_text("Never Cached", str(tmp_path)) is None


def test_enrichment_keeps_card_text_only_when_asked(tmp_path, monkeypatch):
    csv = tmp_path / "c.csv"
    csv.write_text("Quantity,Name\n1,Sol Ring\n", encoding="utf-8")
    card = {"name": "Sol Ring", "type_line": "Artifact", "oracle_text": "{T}: Add {C}{C}.",
            "color_identity": [], "cmc": 1.0, "mana_cost": "{1}"}
    monkeypatch.setattr(carddb, "_post_collection", lambda ids: ([card], []))
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    cache = tmp_path / "cache"
    carddb.enrich_api(str(csv), str(tmp_path / "a.csv"), fuzzy=False)
    assert not cache.exists(), "off by default: tests and other callers write nothing"
    carddb.enrich_api(str(csv), str(tmp_path / "b.csv"), fuzzy=False,
                      text_cache_dir=str(cache))
    assert carddb.cached_oracle_text("Sol Ring", str(cache)) == "{T}: Add {C}{C}."


COLL = """\
Quantity,Name,Identities,Types,Sub-types,Mana cost,Mana Value
1,Test Commander,R,Legendary Creature,Dragon,{R},1
1,In Deck Spell,R,Instant,,{R},1
1,Damage Draw,R,Creature,Dragon,{4}{R},5
1,Plain Draw,R,Sorcery,,{1}{R},2
"""

DECK2 = """\
# Title: K
# Commander: Test Commander
# Colors: R

# --- Commander ---
1 Test Commander

# --- Instants ---
1 In Deck Spell

# --- Basics ---
10 Mountain
"""


def test_keyword_matches_rank_first_and_skip_the_fit_floor(tmp_path, monkeypatch):
    import optimize
    d = tmp_path / "kw"
    d.mkdir()
    (d / "collection.csv").write_text(COLL, encoding="utf-8")
    (d / "deck.txt").write_text(DECK2, encoding="utf-8")
    engine_spec.save(str(d / "deck.engine.json"),
                     {"engine": [], "keywords": ["noncombat damage"], "keep": {}})
    monkeypatch.setattr(optimize.deck_fit, "load_field", lambda *a, **k: {"in deck spell": 40})
    monkeypatch.setattr(optimize.deck_fit, "load_synergy", lambda *a, **k: {})
    monkeypatch.setattr(optimize.deck_fit, "load_field_lands", lambda *a, **k: set())
    fits = {"Damage Draw": 55, "Plain Draw": 90}
    real = optimize.deck_fit.assess_card
    monkeypatch.setattr(optimize.deck_fit, "assess_card",
                        lambda ref, *a, **k: {"score": fits[ref.name]} if ref.name in fits
                        else real(ref, *a, **k))
    monkeypatch.setattr(carddb, "cached_oracle_text",
                        lambda n, cache_dir=None: "deals noncombat damage to an opponent"
                        if n == "Damage Draw" else None)
    coll = mtglib.load_collection(str(d / "collection.csv"))
    r = optimize.optimize(str(d / "deck.txt"), coll, mtglib.index_by_name(coll), str(d))
    silent = [x for x in r["reads"] if x["field"] is None]
    assert silent[0]["name"] == "Damage Draw", "the engine match leads despite fit 55"
    assert silent[0]["matches"] == ["noncombat damage"]
