"""The optimizer rewrites real deck files, so the invariants matter more than the picks:
card count preserved, no cards invented or lost by the tidy pass, sections kept."""
import optimize
import mtglib


DECK = """\
# Title: T
# Commander: Test Commander
# Colors: W U

# --- Creatures ---
1 Test Commander
1 Serra Angel
1 Llanowar Elves

# --- Ramp ---
1 Sol Ring

# --- Lands (13) ---
1 Command Tower
7 Island
5 Island
"""


def _deck(tmp_path, text=DECK):
    p = tmp_path / "d.txt"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_commander_is_parsed_from_the_header(tmp_path):
    assert optimize._commander_of(DECK) == "Test Commander"


def test_protected_set_includes_commander_and_basics(tmp_path):
    keep, _notes = optimize._protected(_deck(tmp_path), "Test Commander")
    assert mtglib._norm("Test Commander") in keep
    for b in ("plains", "island", "swamp", "mountain", "forest"):
        assert b in keep


def test_basics_target_shrinks_as_colours_widen():
    one = optimize._basics_needed({"W"})
    three = optimize._basics_needed({"W", "U", "R"})
    five = optimize._basics_needed(set("WUBRG"))
    assert one > three > five >= 6


def test_tidy_preserves_every_card(tmp_path, collection_file):
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path)
    before = mtglib.parse_deck(open(p, encoding="utf-8").read())
    optimize._tidy(p, idx)
    after = mtglib.parse_deck(open(p, encoding="utf-8").read())
    assert sum(c.quantity for c in before) == sum(c.quantity for c in after)
    assert ({mtglib._norm(c.name): c.quantity for c in before}
            == {mtglib._norm(c.name): c.quantity for c in after})


def test_tidy_merges_duplicate_lines(tmp_path, collection_file):
    """'7 Island' + '5 Island' must collapse to a single '12 Island' line."""
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path)
    optimize._tidy(p, idx)
    text = open(p, encoding="utf-8").read()
    assert text.count(" Island") == 1
    assert "12 Island" in text


def test_tidy_keeps_the_header_and_sections(tmp_path, collection_file):
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path)
    optimize._tidy(p, idx)
    text = open(p, encoding="utf-8").read()
    assert "# Commander: Test Commander" in text
    assert "# --- Creatures ---" in text
    assert "# --- Ramp ---" in text


def test_tidy_refiles_a_mana_dork_under_ramp(tmp_path, collection_file):
    """Llanowar Elves is listed under Creatures; it belongs in Ramp."""
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path)
    optimize._tidy(p, idx)
    text = open(p, encoding="utf-8").read()
    ramp = text.split("# --- Ramp ---")[1].split("# ---")[0]
    assert "Llanowar Elves" in ramp


MIXED_DECK = """\
# Title: T
# Commander: Test Commander

# --- Creatures ---
1 Serra Angel
1 Sol Ring
1 Counterspell
1 Command Tower

# --- Removal ---
1 Swords to Plowshares
"""


def test_type_allowed_identifies_type_sections():
    assert optimize._type_allowed("Creatures") == {"Creature"}
    assert optimize._type_allowed("Lands (37)") == {"Land"}
    assert optimize._type_allowed("Artifacts") == {"Artifact"}
    assert optimize._type_allowed("Instants & sorceries") == {"Instant", "Sorcery"}
    # function sections are NOT type-exclusive — any type may live there
    assert optimize._type_allowed("Ramp") is None
    assert optimize._type_allowed("Removal & wraths") is None
    # a curated header that merely *contains* a type word stays free-form
    assert optimize._type_allowed("Spiders & Spider-matters creatures") is None
    assert optimize._type_allowed("Equipment support") is None


def test_non_creatures_are_moved_out_of_the_creatures_section(tmp_path, collection_file):
    """The reported bug: Door of Destinies (Artifact) / Methods of the Mighty (Instant)
    were sitting under 'Creatures'."""
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path, MIXED_DECK)
    optimize._tidy(p, idx)
    text = open(p, encoding="utf-8").read()
    creatures = text.split("# --- Creatures ---")[1].split("# ---")[0]
    assert "Serra Angel" in creatures          # a real creature stays
    for non_creature in ("Sol Ring", "Counterspell", "Command Tower"):
        assert non_creature not in creatures


def test_a_function_section_may_hold_any_type(tmp_path, collection_file):
    """Sol Ring is an Artifact but belongs under Ramp — function beats type."""
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path, MIXED_DECK + "\n# --- Ramp ---\n")
    optimize._tidy(p, idx)
    text = open(p, encoding="utf-8").read()
    ramp = text.split("# --- Ramp ---")[1].split("# ---")[0]
    assert "Sol Ring" in ramp


def test_a_type_section_is_created_when_none_fits(tmp_path, collection_file):
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path, MIXED_DECK)
    optimize._tidy(p, idx)
    text = open(p, encoding="utf-8").read()
    assert "# --- Lands ---" in text            # Command Tower needed a home


def test_tidy_never_leaves_a_type_section_violated(tmp_path, collection_file):
    import re as _re
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path, MIXED_DECK)
    optimize._tidy(p, idx)
    cur, violations = None, []
    for ln in open(p, encoding="utf-8"):
        s = ln.strip()
        m = _re.match(r"^#\s*-+\s*(.+?)\s*-+\s*$", s)
        if m:
            cur = m.group(1)
            continue
        if not s or s.startswith("#"):
            continue
        ref = mtglib.lookup(idx, _re.sub(r"^\d+\s+", "", s))
        allowed = optimize._type_allowed(cur or "")
        if ref and ref.types and allowed:
            ptype = "Land" if ref.is_land else ref.primary_type
            if ptype not in allowed:
                violations.append((ref.name, cur))
    assert violations == []


def test_optimize_is_a_no_op_without_field_data(tmp_path, collection_file):
    """Unknown commander -> no EDHREC data -> the deck must be left exactly alone."""
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    p = _deck(tmp_path)
    original = open(p, encoding="utf-8").read()
    r = optimize.optimize(p, coll, idx, str(tmp_path), apply=True)
    assert r["swaps"] == []
    assert open(p, encoding="utf-8").read() == original
