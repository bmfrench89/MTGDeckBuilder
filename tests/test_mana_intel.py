"""Phase B of spec-mana-intelligence: the fetch-target census and the
restricted-source split — the engine answers to "why is Wood Elves in a deck
with only 2 Forests?" (it had five; nothing could say so).

Everything here is hand-built Cards or tmp_path attrs files, hermetic. The
properties that matter:

  * a fetcher's targets are resolved by what its tokens can FIND — typed duals
    satisfy `fetch:forest`, only basics satisfy `fetch:basic-forest`, and a
    union across tokens never counts one land twice;
  * restricted lands leave the Karsten pool and land in their own bucket, and a
    pre-vocabulary land is UNKNOWN — counted as before, labeled, never
    silently promoted to "verified unrestricted";
  * the census refuses to render a confident zero on pre-vocabulary data.
"""
import json

import mtglib
import manabase
import deck_stats

C = mtglib.Card


def _land(name, subtypes=(), qty=1, flags=frozenset(), ver=2, produced=None):
    return C(name=name, types=["Land"], subtypes=list(subtypes), quantity=qty,
             flags=set(flags), flags_ver=ver, produced=produced)


URDRAGON_MINI = [
    C(name="Wood Elves", types=["Creature"], flags={"ramp", "fetch:forest"},
      flags_ver=2),
    C(name="Farseek", types=["Sorcery"], flags_ver=2,
      flags={"ramp", "fetch:plains", "fetch:island", "fetch:swamp",
             "fetch:mountain"}),
    C(name="Nissa's Pilgrimage", types=["Sorcery"],
      flags={"ramp", "fetch:basic-forest"}, flags_ver=2),
    _land("Forest", ["Forest"], qty=2),
    _land("Sheltered Thicket", ["Mountain", "Forest"]),
    _land("Scattered Groves", ["Forest", "Plains"]),
    _land("Mountain", ["Mountain"], qty=4),
    _land("Command Tower"),
]


def _rows(census):
    return {r["name"]: r for r in census["rows"]}


def test_a_typed_fetcher_counts_typed_duals():
    """The original question, answered by the engine: 2 basics + 2 typed duals
    = 4 Forest cards Wood Elves can actually find here."""
    rows = _rows(manabase.fetch_census(URDRAGON_MINI))
    we = rows["Wood Elves"]
    assert we["targets"] == 4
    assert set(we["target_names"]) == {"Forest", "Sheltered Thicket",
                                       "Scattered Groves"}
    assert we["state"] == "ok"


def test_union_across_tokens_counts_each_land_once():
    """Farseek's four tokens both hit Sheltered Thicket (Mountain) — via
    different letters on Scattered Groves (Plains) — and the union must count
    each land once: 2 duals + 4 Mountains = 6."""
    rows = _rows(manabase.fetch_census(URDRAGON_MINI))
    assert rows["Farseek"]["targets"] == 6


def test_basic_qualified_fetch_excludes_typed_duals():
    """Nissa's Pilgrimage wants BASIC Forests: the two basics qualify, the two
    Forest-typed duals do not — and 2 is under FETCH_THIN, so it reads thin."""
    rows = _rows(manabase.fetch_census(URDRAGON_MINI))
    np_ = rows["Nissa's Pilgrimage"]
    assert np_["targets"] == 2
    assert np_["state"] == "thin"


def test_a_stranded_fetcher_reads_none():
    deck = [C(name="Wood Elves", types=["Creature"],
              flags={"ramp", "fetch:forest"}, flags_ver=2),
            _land("Island", ["Island"], qty=10)]
    rows = _rows(manabase.fetch_census(deck))
    assert rows["Wood Elves"]["state"] == "none"
    assert rows["Wood Elves"]["targets"] == 0


def test_a_fetchland_is_not_its_own_target():
    deck = [_land("Evolving Wilds", flags={"ramp", "fetch:basic"}),
            _land("Forest", ["Forest"], qty=1)]
    rows = _rows(manabase.fetch_census(deck))
    assert rows["Evolving Wilds"]["targets"] == 1, "only the Forest, not itself"


def test_quantities_count_copies_not_rows():
    deck = [C(name="Rampant Growth", types=["Sorcery"], quantity=2,
              flags={"ramp", "fetch:basic"}, flags_ver=2),
            _land("Forest", ["Forest"], qty=5)]
    census = manabase.fetch_census(deck)
    assert census["total_fetchers"] == 2, "sum of quantities, not row count"
    assert _rows(census)["Rampant Growth"]["targets"] == 5


def test_pre_vocabulary_is_refused_not_zeroed():
    """The honesty gate. A deck whose enrichment predates v2 has INVISIBLE
    fetchers, not absent ones — a confident zero here would be a lie."""
    deck = [C(name="Wood Elves", types=["Creature"], flags={"ramp"}, flags_ver=1),
            _land("Forest", ["Forest"], qty=5, ver=1)]
    census = manabase.fetch_census(deck)
    assert census["unknown"] == "pre-vocabulary"
    assert census["rows"] == []


def test_no_subtype_data_is_flagged_via_has_type_data_not_empty_subtypes():
    """The proxy the completeness review forced: Unclaimed Territory is fully
    enriched with NO basic land types — empty subtypes on a typed land is a
    real answer, not missing data. Only a land with no type data at all
    (has_type_data False) triggers the caveat."""
    healthy = [C(name="Wood Elves", types=["Creature"],
                 flags={"ramp", "fetch:forest"}, flags_ver=2),
               _land("Forest", ["Forest"]),
               _land("Unclaimed Territory")]        # typed Land, no subtypes
    assert manabase.fetch_census(healthy)["unknown"] is None

    nameonly = [C(name="Wood Elves", types=["Creature"],
                  flags={"ramp", "fetch:forest"}, flags_ver=2),
                _land("Forest", ["Forest"]),
                # No type data at all: is_land resolves via the name-hint
                # heuristic ("grove" is on the hints list), which is exactly the
                # untyped-land situation the caveat exists for.
                C(name="Vivid Grove", types=[], flags_ver=2)]
    assert manabase.fetch_census(nameonly)["unknown"] == "no-subtype-data"


def test_census_is_json_safe():
    json.dumps(manabase.fetch_census(URDRAGON_MINI))


# --------------------------------------------------------------------------- #
# The restricted split (deck_stats.build_report)
# --------------------------------------------------------------------------- #
def _report(cards):
    idx = mtglib.index_by_name(cards)
    deck = [C(name=c.name, quantity=c.quantity) for c in cards]
    enriched, missing = deck_stats.analyze(deck, idx)
    return deck_stats.build_report(deck, enriched, missing, idx)


def test_a_verified_restricted_land_moves_buckets():
    cards = [_land("Unclaimed Territory", produced=set("WUBRGC"),
                   flags={"mana-restricted"}, ver=2),
             _land("Forest", ["Forest"], produced={"G"}, qty=3)]
    rep = _report(cards)
    assert rep["color_sources"] == {"G": 3}, \
        "the restricted land must not inflate the main pool"
    assert rep["color_sources_restricted"] == {c: 1 for c in "WUBRG"}
    assert rep["color_sources_basis"]["restricted_lands"] == 1
    assert rep["color_sources_basis"]["restriction_unknown_lands"] == 0


def test_a_pre_vocabulary_land_counts_as_today_and_is_labeled_unknown():
    """Unknown is not restricted and not verified-clean. The same land with v1
    flags counts exactly as before the split existed — and the basis says the
    split is incomplete."""
    cards = [_land("Unclaimed Territory", produced=set("WUBRGC"),
                   flags=set(), ver=1),
             _land("Forest", ["Forest"], produced={"G"}, qty=3, ver=1)]
    rep = _report(cards)
    assert rep["color_sources"]["W"] == 1, "counted as unrestricted, as before"
    assert rep["color_sources_restricted"] == {}
    assert rep["color_sources_basis"]["restriction_unknown_lands"] == 4


def test_karsten_status_flips_when_restriction_is_subtracted():
    """The acceptance-shaped case: enough rainbow-restricted lands to clear the
    Karsten count only WITH the overcount. Subtracting them flips ok -> low."""
    restricted = [_land(f"Tribal Land {i}", produced=set("WUBRG"),
                        flags={"mana-restricted"}, ver=2) for i in range(10)]
    real = [_land("Plains", ["Plains"], produced={"W"}, qty=15)]
    spells = [C(name="Angel", types=["Creature"], mana_cost="{1}{W}",
                mana_value=2.0, quantity=4, flags_ver=2)]
    rep_v2 = _report(restricted + real + spells)
    a_v2 = manabase.analyze(rep_v2, restricted + real + spells)
    w_row = next(r for r in a_v2["colors"] if r["color"] == "W")
    assert w_row["sources"] == 15 and w_row["restricted"] == 10
    assert w_row["status"] == "low", "15 < Karsten 19 once the overcount is gone"

    legacy = [_land(f"Tribal Land {i}", produced=set("WUBRG"), ver=1)
              for i in range(10)] + real + spells
    a_v1 = manabase.analyze(_report(legacy), legacy)
    w_old = next(r for r in a_v1["colors"] if r["color"] == "W")
    assert w_old["sources"] == 25 and w_old["status"] == "ok", \
        "pre-vocabulary data keeps today's (overcounted) numbers — labeled, not fixed"


def test_analyze_ships_census_and_restricted_and_serializes():
    rep = _report(URDRAGON_MINI)
    a = manabase.analyze(rep, URDRAGON_MINI)
    assert "fetch" in a and a["fetch"]["total_fetchers"] == 3
    assert all("restricted" in row for row in a["colors"])
    assert "restricted" in a["explain"] and "fetch" in a["explain"]
    json.dumps(a)
