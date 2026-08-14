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


# --------------------------------------------------------------------------- #
# Printed power (spec-table-ready Phase 1) — the input the goldfish clock needs.
#
# The file carries three states; the Card carries two, and BOTH of the collapsed
# ones mean "do not count this creature's damage":
#   column absent   -> Card.power is None   (never enriched)
#   cell empty      -> Card.power is None   (enriched; the card has no power)
#   cell '*'        -> Card.power is None   (verbatim in the file, unknowable here)
#   cell '4'        -> Card.power == 4
# The empty-vs-absent distinction stays REPRESENTABLE at the file layer — see
# test_deck_attrs_csv_carries_power_and_keeps_absent_meaning_absent below, which
# reads it through deckcore.load_attrs (None for absent, '' for empty).
# --------------------------------------------------------------------------- #
ATTRS_10COL = """\
Name,Type,MV,Colors,Cost,Sub-types,Scryfall,Produced,Flags,Power
Serra Angel,Creature,5,W,{3}{W}{W},Angel,7777aaaa,,,4
Sol Ring,Artifact,1,,{1},,aaaa1111,C,rock;ramp;mana2,
Island,Land,0,,,Island,ffff6666,U,,
"""


def test_power_is_an_int_for_a_creature_and_none_for_a_noncreature(tmp_path,
                                                                   collection_file):
    idx = _with_attrs(tmp_path, collection_file, ATTRS_10COL)
    assert mtglib.lookup(idx, "Serra Angel").power == 4
    # Present column, EMPTY cell: enriched, and this card has no power at all.
    assert mtglib.lookup(idx, "Sol Ring").power is None
    assert mtglib.lookup(idx, "Island").power is None
    # …and the rest of the row still applied, so this is a real overlay, not a skip.
    assert mtglib.lookup(idx, "Sol Ring").produced == {"C"}


ATTRS_9COL_ANGEL = """\
Name,Type,MV,Colors,Cost,Sub-types,Scryfall,Produced,Flags
Serra Angel,Creature,5,W,{3}{W}{W},Angel,7777aaaa,,
Sol Ring,Artifact,1,,{1},,aaaa1111,C,rock;ramp;mana2
"""


def test_power_is_unknown_when_the_column_is_absent(tmp_path, collection_file):
    """The old-format 9-column file, overlaying a row that really is a creature:
    Serra Angel is a 4/4 in real life, and this build must still answer 'unknown'
    rather than invent it. Every column the file DOES carry still lands, so this is
    the absent COLUMN talking, not a skipped row."""
    idx = _with_attrs(tmp_path, collection_file, ATTRS_9COL_ANGEL)
    angel = mtglib.lookup(idx, "Serra Angel")
    assert angel.power is None
    assert angel.mana_value == 5 and "Angel" in angel.subtypes
    # The contrast, in one file: Produced is PRESENT and blank -> set() ("enriched,
    # makes no mana"); Power is ABSENT -> None ("nobody has ever looked").
    assert angel.produced == set()


def test_a_newer_snapshot_power_survives_an_older_private_attrs_file(tmp_path,
                                                                     collection_file):
    """ATTRS_OVERLAYS layers snapshot-then-private, and the private file on the
    player's machine is the OLD 9-column shape. The private file must not blank the
    power the committed snapshot just supplied — the same data-loss trap the
    Produced/Flags layering was built to avoid."""
    import shutil
    d = tmp_path / "coll"
    d.mkdir(exist_ok=True)
    shutil.copy(collection_file, d / "collection.csv")
    (d / "collection_attrs.snapshot.csv").write_text(ATTRS_10COL, encoding="utf-8")
    (d / "collection_attrs.csv").write_text(ATTRS_9COL_ANGEL, encoding="utf-8")
    idx = mtglib.index_by_name(mtglib.load_collection(str(d / "collection.csv")))
    assert mtglib.lookup(idx, "Serra Angel").power == 4


def test_parse_power_reads_numbers_and_refuses_to_invent_them():
    assert mtglib._parse_power("4") == 4
    assert mtglib._parse_power(" 0 ") == 0          # a real 0/1 wall, not "unknown"
    assert mtglib._parse_power("-1") == -1
    assert mtglib._parse_power("2.5") == 2          # Un-set halves are still numbers
    assert mtglib._parse_power("*") is None
    assert mtglib._parse_power("1+*") is None
    assert mtglib._parse_power("") is None
    assert mtglib._parse_power(None) is None


def test_deck_attrs_csv_carries_power_and_keeps_absent_meaning_absent(tmp_path):
    """A deck-level `<stem>.attrs.csv` is what powers the model on a fresh clone
    (same contract Produced/Flags have). This is also where the empty-vs-absent
    distinction is directly observable: load_attrs preserves DictReader's None for
    an absent column and '' for a present-but-blank cell."""
    import deckcore
    with_power = tmp_path / "a.attrs.csv"
    with_power.write_text("Name,Type,MV,Colors,Produced,Flags,Power\n"
                          "Serra Angel,Creature,5,W,,,4\n"
                          "Tarmogoyf,Creature,2,G,,,*\n"
                          "Sol Ring,Artifact,1,,C,rock,\n", encoding="utf-8")
    attrs = deckcore.load_attrs(str(with_power))
    assert attrs["serra angel"]["power"] == "4"
    assert attrs["tarmogoyf"]["power"] == "*"       # verbatim, not swallowed
    assert attrs["sol ring"]["power"] == ""         # PRESENT but empty

    cards = [mtglib.Card(name=n) for n in ("Serra Angel", "Tarmogoyf", "Sol Ring")]
    deckcore.apply_attrs(cards, attrs)
    by = {c.name: c for c in cards}
    assert by["Serra Angel"].power == 4
    assert by["Tarmogoyf"].power is None            # non-numeric = unknown
    assert by["Sol Ring"].power is None

    no_power = tmp_path / "b.attrs.csv"
    no_power.write_text("Name,Type,MV,Colors,Produced,Flags\n"
                        "Serra Angel,Creature,5,W,,\n", encoding="utf-8")
    absent = deckcore.load_attrs(str(no_power))
    assert absent["serra angel"]["power"] is None   # ABSENT, and it reads differently
    known = mtglib.Card(name="Serra Angel", power=4)
    deckcore.apply_attrs([known], absent)
    assert known.power == 4                         # absent never blanks what we knew


def test_card_still_constructs_bare():
    c = mtglib.Card(name="Nothing Special")
    assert c.produced is None and c.flags == set() and c.power is None


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


def test_classify_matches_curated_lists_through_the_front_face():
    """Regression: the curated layer looked up only _norm(full name), so a split
    card stored as 'Murderous Rider // Swift End' (the collection's spelling)
    never matched REMOVAL's 'murderous rider' / 'swift end' entries and silently
    classified by type alone."""
    joined = mtglib.Card(name="Murderous Rider // Swift End", types=["Creature"])
    assert "removal" in mtglib.classify(joined)
    front = mtglib.Card(name="Murderous Rider", types=["Creature"])
    assert "removal" in mtglib.classify(front)


def test_snow_covered_basics_look_like_lands_by_name():
    for b in ("Snow-Covered Island", "Snow-Covered Wastes", "Island"):
        assert mtglib._looks_like_land_by_name(b)
    assert not mtglib._looks_like_land_by_name("Snow Devil")   # a snow SPELL stays one


# --------------------------------------------------------------------------- #
# Layered attrs overlays (docs/spec-network-and-attrs.md §3)
#
# Two attrs files can be on disk: collection_attrs.snapshot.csv (committed,
# name-derived, written by the attrs-snapshot Action so a fresh clone is not
# name-only) and collection_attrs.csv (private, gitignored, exact printings).
# They LAYER — snapshot first, private on top — rather than the private file
# winning outright. The regression that motivated this: the player's real private
# file is the old 7-column shape, so "private wins outright" threw away the
# snapshot's Produced/Flags and put every surface back on the honesty-gated
# fallback tier despite the data being right there on disk.
# --------------------------------------------------------------------------- #
def _with_layered_attrs(tmp_path, collection_file, snapshot_text=None,
                        private_text=None, name="coll"):
    import shutil
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    shutil.copy(collection_file, d / "collection.csv")
    if snapshot_text is not None:
        (d / "collection_attrs.snapshot.csv").write_text(snapshot_text,
                                                         encoding="utf-8")
    if private_text is not None:
        (d / "collection_attrs.csv").write_text(private_text, encoding="utf-8")
    return mtglib.index_by_name(mtglib.load_collection(str(d / "collection.csv")))


def test_snapshot_attrs_alone_enrich_a_fresh_clone(tmp_path, collection_file):
    # The whole point of the Action: no private file, but typed data anyway.
    idx = _with_layered_attrs(tmp_path, collection_file, snapshot_text=ATTRS_9COL)
    sol = mtglib.lookup(idx, "Sol Ring")
    assert sol.types == ["Artifact"]
    assert sol.produced == {"C"} and sol.flags == {"rock", "ramp", "mana2"}


def test_no_attrs_files_leave_produced_unknown(tmp_path, collection_file):
    # The honest degraded path must survive: unknown stays None, never set().
    idx = _with_layered_attrs(tmp_path, collection_file)
    assert mtglib.lookup(idx, "Sol Ring").produced is None


def test_an_old_private_file_keeps_the_snapshots_produced_and_flags(
        tmp_path, collection_file):
    # THE regression this layering exists to prevent. The private 7-column file has
    # no Produced/Flags columns at all, so it must not blank what the snapshot knew.
    idx = _with_layered_attrs(tmp_path, collection_file,
                              snapshot_text=ATTRS_9COL, private_text=ATTRS_7COL)
    sol = mtglib.lookup(idx, "Sol Ring")
    assert sol.produced == {"C"}, "an old private file erased snapshot production data"
    assert sol.flags == {"rock", "ramp", "mana2"}


def test_the_private_file_still_wins_where_it_speaks(tmp_path, collection_file):
    # Layering must not demote the private file: its exact-printing Scryfall id and
    # any non-empty cell override the name-derived snapshot.
    private = ATTRS_7COL.replace("aaaa1111", "PRIVATE-EXACT-PRINTING")
    idx = _with_layered_attrs(tmp_path, collection_file,
                              snapshot_text=ATTRS_9COL, private_text=private)
    assert mtglib.lookup(idx, "Sol Ring").scryfall_id == "PRIVATE-EXACT-PRINTING"


def test_a_stale_snapshot_row_invents_no_card(tmp_path, collection_file):
    # A snapshot listing a card the player has since sold must add nothing — the
    # overlay skips unknown names rather than conjuring a Card (mtglib.overlay_attrs).
    stale = ATTRS_9COL + "Sold Cardname That Is Not Owned,Creature,3,,{2}{G},,zzzz9999,,\n"
    before = len(mtglib.load_collection(str(collection_file)))
    idx = _with_layered_attrs(tmp_path, collection_file, snapshot_text=stale)
    assert mtglib.lookup(idx, "Sold Cardname That Is Not Owned") is None
    assert len({id(c) for c in idx.values()}) == before


# --------------------------------------------------------------------------- #
# deck_header — THE `# Key: value` parser (Phase 12). Sixteen hand-rolled copies
# of this regex existed across thirteen files, every one with the same latent
# bug: `\s*` after the colon crosses the NEWLINE under re.MULTILINE, so an empty
# header absorbed the whole next line as its value.
# --------------------------------------------------------------------------- #
def test_deck_header_reads_a_normal_header():
    text = "# Title: T\n# Commander: Y'shtola, Night's Blessed\n"
    assert mtglib.deck_header(text, "Commander") == "Y'shtola, Night's Blessed"
    assert mtglib.deck_header(text, "commander") == "Y'shtola, Night's Blessed"


def test_an_empty_header_never_absorbs_the_next_line():
    """The live bug: ur-dragon's blank `# Archetype: ` parsed as
    `['#', 'source:', 'auto-generated', ...]` because \\s* ate the newline."""
    text = "# Archetype: \n# Source: auto-generated draft (scripts/auto_build.py)\n"
    assert mtglib.deck_header(text, "Archetype") == ""
    assert mtglib.deck_header(text, "Archetype", default="x") == "x"


def test_an_empty_bracket_header_cannot_read_a_phantom_bracket():
    """The nastiest instance: `# Bracket:` above `1 Sol Ring` — the old \\s* crossed
    the newline and [1-5] matched the quantity digit, declaring a Bracket 1."""
    import power
    import os, tempfile
    text = "# Title: T\n# Bracket:\n\n# --- Main ---\n1 Sol Ring\n"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "x.txt")
        open(p, "w", encoding="utf-8").write(text)
        assert power.read_declared_bracket(p) is None


def test_missing_header_returns_the_default():
    assert mtglib.deck_header("# Title: T\n", "Bracket") == ""
    assert mtglib.deck_header("", "Commander", default="none") == "none"
    assert mtglib.deck_header(None, "Commander") == ""


def test_key_is_a_regex_fragment_for_spelling_variants():
    assert mtglib.deck_header("# Color: W U\n", "Colors?") == "W U"
    assert mtglib.deck_header("# Colors: W U\n", "Colors?") == "W U"


def test_trailing_whitespace_is_stripped_but_inner_spaces_survive():
    assert mtglib.deck_header("# Theme:  dark  souls  \n", "Theme") == "dark  souls"
