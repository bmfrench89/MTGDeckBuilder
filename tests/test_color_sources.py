"""Colored sources are counted from what a land ACTUALLY taps for once the collection
is enriched, and from its color IDENTITY when it isn't — with every surface saying
which it used.

This is the number Karsten pass/fail, the dashboard's pip table and the coaching
packet all rest on, so the honesty label matters as much as the count:
`manabase.py`'s own docstring has admitted the identity approximation is "rough for
oddballs" since day one. Vault of the Archangel is that oddball in one card — color
identity {W,B} from its activation cost, but it taps for {C} and nothing else.
"""
import json

import pytest

import build_dashboard
import deck_stats
import manabase
import mtglib

COLLECTION = """\
Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity
12,Island,0,U,U,,Land,Island,common
1,Vault of the Archangel,0,W B,W B,,Land,,rare
1,Counterspell,2,U,U,{U}{U},Instant,,common
1,Swords to Plowshares,1,W,W,{W},Instant,,uncommon
"""

# Produced says what each land really makes. Vault taps for {C}; the Island for {U}.
ATTRS_ENRICHED = """\
Name,Type,MV,Colors,Cost,Sub-types,Scryfall,Produced,Flags
Island,Land,0,U,,Island,i0001,U,
Vault of the Archangel,Land,0,W B,,,v0001,C,
Counterspell,Instant,2,U,{U}{U},,c0001,,
Swords to Plowshares,Instant,1,W,{W},,s0001,,
"""

# The same file as written before enrichment learned about production.
ATTRS_LEGACY = """\
Name,Type,MV,Colors,Cost,Sub-types,Scryfall
Island,Land,0,U,,Island,i0001
Vault of the Archangel,Land,0,W B,,,v0001
Counterspell,Instant,2,U,{U}{U},,c0001
Swords to Plowshares,Instant,1,W,{W},,s0001
"""

DECK = "1 Counterspell\n1 Swords to Plowshares\n8 Island\n1 Vault of the Archangel\n"


def _report(tmp_path, attrs, deck_text=DECK, name="c"):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    (d / "collection.csv").write_text(COLLECTION, encoding="utf-8")
    (d / "collection_attrs.csv").write_text(attrs, encoding="utf-8")
    idx = mtglib.index_by_name(mtglib.load_collection(str(d / "collection.csv")))
    deck = mtglib.parse_deck(deck_text)
    enriched, missing = deck_stats.analyze(deck, idx)
    return deck_stats.build_report(deck, enriched, missing, idx), enriched


@pytest.fixture
def enriched(tmp_path):
    return _report(tmp_path, ATTRS_ENRICHED, name="enriched")


@pytest.fixture
def legacy(tmp_path):
    return _report(tmp_path, ATTRS_LEGACY, name="legacy")


# ── counting ─────────────────────────────────────────────────────────────────
def test_production_beats_identity_when_it_is_known(enriched):
    """Vault of the Archangel's {W,B} identity buys zero white and zero black
    sources — it taps for {C}. Counting identity credited two colors it can't make."""
    rep, _ = enriched
    assert rep["color_sources"] == {"U": 8}
    # restriction_unknown_lands == 9: this fixture's attrs file predates FlagsVer,
    # so every land is vocabulary v1 — enriched for production, unknown for
    # restriction. Unknown is not restricted and not verified-clean.
    assert rep["color_sources_basis"] == {"produced_lands": 9, "identity_lands": 0,
                                          "restricted_lands": 0,
                                          "restriction_unknown_lands": 9}


def test_without_the_column_it_falls_back_to_identity_and_says_so(legacy):
    rep, _ = legacy
    assert rep["color_sources"] == {"U": 8, "W": 1, "B": 1}
    assert rep["color_sources_basis"]["identity_lands"] == 9
    assert rep["color_sources_basis"]["produced_lands"] == 0


def test_a_colorless_producer_contributes_zero_not_nothing_known(enriched):
    """C is not a WUBRG source, but the land is still counted as ENRICHED — the
    distinction between "makes no colored mana" and "we don't know" is the point."""
    rep, _ = enriched
    assert "C" not in (rep["color_sources"] or {})
    assert rep["color_sources_basis"]["produced_lands"] == 9


def test_an_empty_produced_cell_still_counts_as_a_produced_basis(tmp_path):
    attrs = ATTRS_ENRICHED.replace("Vault of the Archangel,Land,0,W B,,,v0001,C,",
                                   "Vault of the Archangel,Land,0,W B,,,v0001,,")
    rep, _ = _report(tmp_path, attrs, name="empty")
    assert rep["color_sources"] == {"U": 8}
    assert rep["color_sources_basis"] == {"produced_lands": 9, "identity_lands": 0,
                                          "restricted_lands": 0,
                                          "restriction_unknown_lands": 9}


def test_a_mixed_attrs_file_splits_the_buckets(tmp_path):
    """Half enriched, half not: both counts are real and the label still fires."""
    attrs = "\n".join(ln for ln in ATTRS_ENRICHED.splitlines()
                      if not ln.startswith("Vault")) + "\n"
    rep, _ = _report(tmp_path, attrs, name="mixed")
    assert rep["color_sources_basis"] == {"produced_lands": 8, "identity_lands": 1,
                                          "restricted_lands": 0,
                                          "restriction_unknown_lands": 9}
    assert rep["color_sources"] == {"U": 8, "W": 1, "B": 1}


def test_one_unowned_land_is_enough_to_forfeit_a_pure_produced_basis(tmp_path):
    """A deck card the collection has never heard of keeps produced=None. A list with
    any unowned land therefore can never claim a fully-produced basis — deliberate."""
    rep, _ = _report(tmp_path, ATTRS_ENRICHED,
                     deck_text=DECK + "1 Exotic Orchard\n", name="unowned")
    assert rep["color_sources_basis"]["identity_lands"] >= 1
    assert rep["color_sources_basis"]["produced_lands"] == 9


# ── report shape / back-compat ───────────────────────────────────────────────
def test_the_json_report_gains_exactly_one_key(enriched, legacy):
    rep, _ = enriched
    pre_a = {"total_cards", "lands", "nonland", "categories", "curve", "pip_demand",
             "double_pips", "color_sources", "missing_from_collection",
             "quantity_problems", "have_mv", "have_cost", "deck_value",
             "priced_cards"}
    # Two deliberate additions since pre_a: the basis split (Phase A of the
    # color-sources work) and the restricted pool (spec-mana-intelligence B1).
    assert set(rep) - pre_a == {"color_sources_basis", "color_sources_restricted"}
    assert pre_a - set(rep) == set()
    json.dumps(rep)                       # --json must still serialize
    assert set(legacy[0]) == set(rep)     # same shape on both bases


def test_color_sources_keeps_its_exact_shape(legacy):
    rep, _ = legacy
    assert all(isinstance(k, str) and isinstance(v, int)
               for k, v in rep["color_sources"].items())


# ── the labels, on every surface ─────────────────────────────────────────────
def test_print_report_labels_the_approximation_only_when_it_applies(enriched, legacy,
                                                                    capsys):
    deck_stats.print_report(legacy[0])
    assert "counted by color IDENTITY" in capsys.readouterr().out
    deck_stats.print_report(enriched[0])
    assert "counted by color IDENTITY" not in capsys.readouterr().out


def test_manabase_carries_the_basis_through(enriched, legacy):
    assert manabase.analyze(*enriched)["basis"]["identity_lands"] == 0
    assert manabase.analyze(*legacy)["basis"]["identity_lands"] == 9


def test_dashboard_pip_table_flags_the_fallback_only_in_the_fallback_case(enriched,
                                                                         legacy):
    assert "identity approx." in build_dashboard.pip_table(legacy[0])
    assert "identity approx." not in build_dashboard.pip_table(enriched[0])
    # and the header itself is still there either way
    assert "Sources" in build_dashboard.pip_table(enriched[0])
