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
