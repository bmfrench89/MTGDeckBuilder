"""The riskiest code in the project: the web app rewrites the player's real deck files
in place (Remove / Replace in the card panel). These lock the behavior down."""
import app  # webapp/app.py — on sys.path via conftest


def read(path):
    return open(path, encoding="utf-8").read()


def test_remove_deletes_only_that_card(deck_file):
    assert app._edit_deck_card(deck_file, "remove", "Sol Ring") is True
    text = read(deck_file)
    assert "Sol Ring" not in text
    assert "Arcane Signet" in text        # neighbours untouched
    assert "Command Tower" in text


def test_replace_preserves_quantity(deck_file):
    # "2 Arcane Signet" -> the replacement must keep the 2
    assert app._edit_deck_card(deck_file, "replace", "Arcane Signet", "Fellwar Stone") is True
    text = read(deck_file)
    assert "2 Fellwar Stone" in text
    assert "Arcane Signet" not in text


def test_replace_preserves_sections_and_headers(deck_file):
    before = read(deck_file)
    app._edit_deck_card(deck_file, "replace", "Sol Ring", "Mind Stone")
    after = read(deck_file)
    for marker in ("# Title: Test Deck", "# Commander: Test Commander",
                   "# --- Ramp ---", "# --- Lands ---", "# --- Commander ---"):
        assert marker in after
    assert len(after.split("\n")) == len(before.split("\n"))   # replace never drops a line


def test_remove_drops_exactly_one_line(deck_file):
    before = read(deck_file).split("\n")
    app._edit_deck_card(deck_file, "remove", "Sol Ring")
    after = read(deck_file).split("\n")
    assert len(after) == len(before) - 1


def test_missing_card_is_a_no_op(deck_file):
    before = read(deck_file)
    assert app._edit_deck_card(deck_file, "remove", "Not A Real Card") is False
    assert read(deck_file) == before          # file untouched, byte for byte


def test_comment_lines_are_never_matched(tmp_path):
    """A card name appearing inside a comment must not be edited."""
    p = tmp_path / "d.txt"
    p.write_text("# Note: Sol Ring is great\n1 Sol Ring\n", encoding="utf-8")
    app._edit_deck_card(str(p), "remove", "Sol Ring")
    text = p.read_text(encoding="utf-8")
    assert "# Note: Sol Ring is great" in text     # comment survives
    assert "\n1 Sol Ring" not in text              # the real entry is gone


def test_only_first_match_is_edited(tmp_path):
    p = tmp_path / "d.txt"
    p.write_text("1 Sol Ring\n1 Sol Ring\n", encoding="utf-8")
    app._edit_deck_card(str(p), "remove", "Sol Ring")
    assert p.read_text(encoding="utf-8").count("Sol Ring") == 1


def test_name_matching_is_normalized(deck_file):
    """Case/punctuation differences still match (mtglib._norm)."""
    assert app._edit_deck_card(deck_file, "remove", "sol ring") is True
    assert "Sol Ring" not in read(deck_file)


def test_replace_without_a_replacement_is_a_no_op(deck_file):
    before = read(deck_file)
    app._edit_deck_card(deck_file, "replace", "Sol Ring", None)
    assert read(deck_file) == before


# --------------------------------------------------------------------------- #
# Adding a card. Same contract as remove/replace: the file changes by exactly the
# intended line and nothing else. These guard the write path; the route-level
# validation (ownership / singleton / color identity) lives in test_add_card.py.
# --------------------------------------------------------------------------- #
def test_add_inserts_at_the_end_of_the_named_section(deck_file):
    assert app._edit_deck_card(deck_file, "add", "Counterspell", section="Ramp") is True
    lines = read(deck_file).split("\n")
    i = lines.index("1 Counterspell")
    # directly after the last card of Ramp, before the Lands header
    assert lines[i - 1] == "2 Arcane Signet"
    assert any(l.startswith("# --- Lands") for l in lines[i + 1:])


def test_add_preserves_every_other_line(deck_file):
    before = read(deck_file).split("\n")
    app._edit_deck_card(deck_file, "add", "Counterspell", section="Ramp")
    after = read(deck_file).split("\n")
    after.remove("1 Counterspell")
    assert after == before, "adding a card must not disturb any other line"


def test_add_falls_back_to_the_end_when_the_section_is_unknown(deck_file):
    """A stale section name must never drop the card on the floor."""
    assert app._edit_deck_card(deck_file, "add", "Counterspell", section="Nope") is True
    text = read(deck_file)
    assert "1 Counterspell" in text


def test_add_without_a_section_still_lands_in_the_file(deck_file):
    app._edit_deck_card(deck_file, "add", "Counterspell")
    assert "1 Counterspell" in read(deck_file)


def test_section_label_reads_the_decks_own_headers(deck_file):
    """Section names are free-form per deck, so the parser must read them, never
    match against a fixed list."""
    assert app._section_label("# --- Ramp ---") == "Ramp"
    assert app._section_label("# --- Ramp (12) ---") == "Ramp"
    assert app._section_label("1 Sol Ring") is None
    assert app._section_label("# Commander: X") is None
