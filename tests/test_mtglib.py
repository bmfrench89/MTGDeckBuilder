"""mtglib is the data hub every other module trusts — parsing, name normalization,
and role classification."""
import mtglib


def test_parse_deck_quantities_and_comments():
    deck = mtglib.parse_deck("# a comment\n1 Sol Ring\n2 Arcane Signet\n\n# --- Lands ---\n10 Island\n")
    by = {c.name: c.quantity for c in deck}
    assert by == {"Sol Ring": 1, "Arcane Signet": 2, "Island": 10}


def test_parse_deck_handles_names_with_commas_and_x_prefix():
    deck = mtglib.parse_deck("1 Kiki-Jiki, Mirror Breaker\n3x Lightning Bolt\n")
    by = {c.name: c.quantity for c in deck}
    assert by["Kiki-Jiki, Mirror Breaker"] == 1
    assert by["Lightning Bolt"] == 3


def test_parse_deck_bare_name_defaults_to_one():
    deck = mtglib.parse_deck("Sol Ring\n")
    assert deck[0].name == "Sol Ring" and deck[0].quantity == 1


def test_norm_is_case_and_whitespace_insensitive():
    """_norm lowercases + collapses whitespace. It deliberately KEEPS punctuation, so
    "Y'shtola" and "Yshtola" are different keys — card names differ by apostrophes."""
    assert mtglib._norm("Sol Ring") == mtglib._norm("  SOL   RING ")
    assert mtglib._norm("Y'shtola, Night's Blessed") == "y'shtola, night's blessed"
    assert mtglib._norm("Kiki-Jiki, Mirror Breaker") == mtglib._norm("KIKI-JIKI,  Mirror Breaker")


def test_load_collection_aggregates_printings(collection_file):
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    assert mtglib.lookup(idx, "Arcane Signet").quantity == 2
    assert mtglib.lookup(idx, "Island").quantity == 12


def test_load_collection_reads_attributes(collection_file):
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    c = mtglib.lookup(idx, "Counterspell")
    assert c.mana_value == 2
    assert c.identity == {"U"}
    assert "Instant" in c.types
    angel = mtglib.lookup(idx, "Serra Angel")
    assert "Angel" in angel.subtypes          # subtypes drive tribal detection


def test_lookup_matches_front_face_of_dfc(collection_file):
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    assert mtglib.lookup(idx, "Sol Ring // Whatever") is not None


def test_classify_roles(collection_file):
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    assert "ramp" in mtglib.classify(mtglib.lookup(idx, "Sol Ring"))
    assert "removal" in mtglib.classify(mtglib.lookup(idx, "Swords to Plowshares"))
    assert "counter" in mtglib.classify(mtglib.lookup(idx, "Counterspell"))
    assert "land" in mtglib.classify(mtglib.lookup(idx, "Island"))


def test_land_detection_by_type(collection_file):
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    assert mtglib.lookup(idx, "Command Tower").is_land is True
    assert mtglib.lookup(idx, "Sol Ring").is_land is False


# --------------------------------------------------------------------------- #
# Review round 2 (docs/spec-optimizer-hardening.md)
# --------------------------------------------------------------------------- #
def test_hybrid_phyrexian_pips_split_not_double():
    """{G/W/P} is ONE symbol — it must contribute one pip split across its colours,
    not a full pip per colour (which inflated pip demand and the Karsten math)."""
    out = mtglib.pip_counts("{1}{G/W/P}")
    assert out["G"] == 0.5 and out["W"] == 0.5


def test_mono_phyrexian_still_counts_a_full_pip():
    assert mtglib.pip_counts("{W/P}{W/P}")["W"] == 2.0


def test_plain_hybrid_unchanged():
    out = mtglib.pip_counts("{W/U}")
    assert out["W"] == 0.5 and out["U"] == 0.5


def test_name_keys_covers_both_faces():
    assert mtglib.name_keys("Fire // Ice") == {"fire // ice", "fire"}


def test_name_keys_plain_name_is_one_key():
    assert mtglib.name_keys("Sol Ring") == {"sol ring"}


def test_name_keys_does_not_invent_an_alias_for_a_bare_slash_name():
    """The SP//dr rule: a bare '//' inside a real name must not create a bogus
    front-face key."""
    keys = mtglib.name_keys("SP//dr, Piloted by Peni")
    assert len(keys) == 1


# --------------------------------------------------------------------------- #
# Produced mana + oracle flags (the enrichment contract, spec §4.2)
#
# The load-bearing distinction: produced is None when the attrs file has no
# Produced column at all ("unknown — fall back and SAY SO"), and set() when the
# column is there but empty ("enriched; this really produces no mana"). Code that
# conflates the two silently turns Maze of Ith into a rainbow land, or claims
# precision it doesn't have.
# --------------------------------------------------------------------------- #
ATTRS_9COL = """\
Name,Type,MV,Colors,Cost,Sub-types,Scryfall,Produced,Flags
Command Tower,Land,0,,,,eeee5555,W U B R G,
Sol Ring,Artifact,1,,{1},,aaaa1111,C,rock;ramp;mana2
Island,Land,0,,,Island,ffff6666,U,
Maze of Ith,Land,0,,,,mmmm0000,,
"""

ATTRS_7COL = """\
Name,Type,MV,Colors,Cost,Sub-types,Scryfall
Command Tower,Land,0,,,,eeee5555
Sol Ring,Artifact,1,,{1},,aaaa1111
"""


def _with_attrs(tmp_path, collection_file, attrs_text):
    import os
    import shutil
    d = tmp_path / "coll"
    d.mkdir(exist_ok=True)
    shutil.copy(collection_file, d / "collection.csv")
    (d / "collection_attrs.csv").write_text(attrs_text, encoding="utf-8")
    return mtglib.index_by_name(mtglib.load_collection(str(d / "collection.csv")))


def test_attrs_with_the_new_columns_populate_produced_and_flags(tmp_path,
                                                                collection_file):
    idx = _with_attrs(tmp_path, collection_file, ATTRS_9COL)
    assert mtglib.lookup(idx, "Command Tower").produced == {"W", "U", "B", "R", "G"}
    sol = mtglib.lookup(idx, "Sol Ring")
    assert sol.produced == {"C"} and sol.flags == {"rock", "ramp", "mana2"}


def test_an_empty_produced_cell_is_enriched_not_unknown(tmp_path, collection_file):
    # Maze of Ith isn't in the base collection CSV, so give the empty-Produced row to
    # a card that is — the point is the CELL, not which card carries it.
    idx = _with_attrs(tmp_path, collection_file,
                      ATTRS_9COL.replace("Maze of Ith", "Serra Angel"))
    angel = mtglib.lookup(idx, "Serra Angel")
    assert angel.produced is not None
    assert angel.produced == set()


def test_attrs_without_the_columns_leave_produced_unknown(tmp_path, collection_file):
    """The pre-enrichment 7-column file. Every pre-existing assertion still holds —
    only produced/flags are absent, and absent means None, never set()."""
    idx = _with_attrs(tmp_path, collection_file, ATTRS_7COL)
    tower = mtglib.lookup(idx, "Command Tower")
    assert tower.produced is None
    assert tower.flags == set()
    assert tower.mana_value == 0 and "Land" in tower.types
    assert mtglib.lookup(idx, "Sol Ring").scryfall_id == "aaaa1111"


def test_parse_produced_keeps_wubrgc_and_drops_the_rest():
    assert mtglib._parse_produced("W U B R G C") == set("WUBRGC")
    assert mtglib._parse_produced(" u,g ") == {"U", "G"}
    assert mtglib._parse_produced("") == set()
    assert mtglib._parse_produced(None) == set()
    assert mtglib._parse_produced("S X WU") == set()      # snow / nonsense / pairs


def test_parse_flags_splits_on_semicolons_only():
    """';' is the separator (the combos.csv convention) so a token never splits on a
    comma — and blanks from a trailing ';' are dropped."""
    assert mtglib._parse_flags("rock;ramp;mana2") == {"rock", "ramp", "mana2"}
    assert mtglib._parse_flags(" etb-tapped ; ") == {"etb-tapped"}
    assert mtglib._parse_flags("") == set()
    assert mtglib._parse_flags(None) == set()


def test_card_still_constructs_bare():
    c = mtglib.Card(name="Nothing Special")
    assert c.produced is None and c.flags == set()


def test_two_cards_do_not_share_a_flags_set():
    a, b = mtglib.Card(name="A"), mtglib.Card(name="B")
    a.flags.add("rock")
    assert b.flags == set()


# --------------------------------------------------------------------------- #
# classify() layer 2: oracle-derived flags, only where curation is silent
# (spec §4.5). The precedence contract is the whole feature — a flag may fill a
# gap, never overrule a hand-verified list.
# --------------------------------------------------------------------------- #
def test_flags_fill_a_role_the_curated_lists_never_heard_of():
    """The point of the layer: a card from a set newer than RAMP's last edit still
    lands in the ramp bucket instead of the generic type fallback."""
    c = mtglib.Card(name="Brand New Mana Elf", types=["Creature"],
                    flags={"dork", "ramp"})
    assert mtglib.classify(c) == {"ramp"}


def test_each_interaction_flag_maps_to_its_role():
    for flag, role in (("removal", "removal"), ("wipe", "wipe"),
                       ("counter", "counter"), ("draw", "draw"), ("rock", "ramp")):
        c = mtglib.Card(name=f"Unlisted {flag}", types=["Instant"], flags={flag})
        assert mtglib.classify(c) == {role}, flag


def test_a_curated_card_wins_over_a_contradictory_flag():
    """First-writer-wins, the same shape deckcore.load_card_notes uses. Sol Ring is
    curated RAMP; a regex that read 'draw' in its text must not move it."""
    sol = mtglib.Card(name="Sol Ring", types=["Artifact"], flags={"draw"})
    assert mtglib.classify(sol) == {"ramp"}


def test_mana_shape_flags_map_to_no_role_at_all():
    """etb-tapped / mana2 / mana3 describe HOW a card makes mana — they are goldfish
    inputs, not deck-role categories. A card carrying only those falls through to the
    type fallback exactly as it did before this layer existed."""
    land = mtglib.Card(name="Some Gate", types=["Land"], flags={"etb-tapped"})
    assert mtglib.classify(land) == {"land"}
    rock = mtglib.Card(name="Odd Stone", types=["Artifact"], flags={"mana2"})
    assert mtglib.classify(rock) == {"artifact"}


def test_no_flags_still_falls_through_to_the_type_layer():
    """The regression gate in miniature: an unenriched Card has flags == set(), so
    layer 2 no-ops and the answer is byte-identical to pre-A-F."""
    assert mtglib.classify(mtglib.Card(name="Nobody", types=["Creature"])) == {"creature"}
    assert mtglib.classify(mtglib.Card(name="Nobody", types=["Instant"])) == {"spell"}
    assert mtglib.classify(mtglib.Card(name="Nobody")) == {"other"}


def test_an_unknown_flag_token_adds_no_role():
    c = mtglib.Card(name="Nobody", types=["Creature"], flags={"未来-token"})
    assert mtglib.classify(c) == {"creature"}


def test_flags_reach_classify_through_the_full_collection_load(tmp_path,
                                                               collection_file):
    """End to end: an attrs file on disk → load_collection overlay → classify().
    Serra Angel is in no curated list, so its flags decide; Sol Ring is curated, so
    its flags cannot. Both facts are read out of one real load."""
    attrs = ("Name,Type,MV,Colors,Cost,Sub-types,Scryfall,Produced,Flags\n"
             "Serra Angel,Creature,5,W,{3}{W}{W},Angel,7777aaaa,,removal\n"
             "Sol Ring,Artifact,1,,{1},,aaaa1111,C,draw;rock;ramp;mana2\n")
    idx = _with_attrs(tmp_path, collection_file, attrs)
    assert mtglib.lookup(idx, "Serra Angel").flags == {"removal"}
    assert mtglib.classify(mtglib.lookup(idx, "Serra Angel")) == {"removal"}
    assert mtglib.classify(mtglib.lookup(idx, "Sol Ring")) == {"ramp"}


def test_produced_and_flags_survive_deck_stats_analyze(tmp_path, collection_file):
    """The pipeline trap: deck_stats.analyze rebuilds every deck card as a NEW Card
    from an explicit field list. A field missing from that list never reaches
    build_report, classify(), manabase or the dashboard for any DECK — which would
    no-op this entire feature at deck level while the collection looked fine."""
    import deck_stats
    idx = _with_attrs(tmp_path, collection_file, ATTRS_9COL)
    deck = mtglib.parse_deck("1 Sol Ring\n10 Island\n1 Command Tower\n")
    enriched, _missing = deck_stats.analyze(deck, idx)
    by = {c.name: c for c in enriched}
    assert by["Sol Ring"].produced == {"C"}
    assert by["Sol Ring"].flags == {"rock", "ramp", "mana2"}
    assert by["Command Tower"].produced == {"W", "U", "B", "R", "G"}
