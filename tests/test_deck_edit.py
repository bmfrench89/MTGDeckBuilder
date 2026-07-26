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
