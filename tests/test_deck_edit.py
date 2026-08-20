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


# --------------------------------------------------------------------------- #
# The " // " trap, in the editor itself (2026-08-15). The panel's data-key can
# carry EITHER form of a DFC name — decklist figures key the deck file's own
# form, EDHREC/field rows key what the snapshot emits (often the front face
# alone) — and the route's singleton guard already matches both via name_keys.
# The editor compared raw _norm and silently no-opped on the mismatch, which is
# exactly the live bug report: "I tried to replace a card in the Smaug deck and
# it did not work."
# --------------------------------------------------------------------------- #
DFC_DECK = """\
# Title: Smaug Test
# Commander: Smaug, the Great Calamity // Spew Flame

# --- Commander ---
1 Smaug, the Great Calamity // Spew Flame

# --- Creatures ---
1 Shivan Dragon
"""


def test_replace_matches_a_full_dfc_line_from_its_front_face_key(tmp_path):
    p = tmp_path / "smaug.txt"
    p.write_text(DFC_DECK, encoding="utf-8")
    assert app._edit_deck_card(str(p), "replace",
                               "smaug, the great calamity",          # front-face key
                               "Lathliss, Dragon Queen") is True
    text = p.read_text(encoding="utf-8")
    assert "1 Lathliss, Dragon Queen" in text
    assert "1 Smaug, the Great Calamity // Spew Flame" not in text
    # the header comment naming the commander is untouched — line edits only
    assert "# Commander: Smaug, the Great Calamity // Spew Flame" in text


def test_replace_matches_a_front_face_line_from_the_full_dfc_name(tmp_path):
    p = tmp_path / "smaug.txt"
    p.write_text(DFC_DECK.replace("1 Smaug, the Great Calamity // Spew Flame",
                                  "1 Smaug, the Great Calamity"), encoding="utf-8")
    assert app._edit_deck_card(str(p), "replace",
                               "Smaug, the Great Calamity // Spew Flame",
                               "Lathliss, Dragon Queen") is True
    assert "1 Lathliss, Dragon Queen" in p.read_text(encoding="utf-8")


def test_remove_matches_across_dfc_name_forms(tmp_path):
    p = tmp_path / "smaug.txt"
    p.write_text(DFC_DECK, encoding="utf-8")
    assert app._edit_deck_card(str(p), "remove", "smaug, the great calamity") is True
    assert "1 Smaug" not in p.read_text(encoding="utf-8")


def test_a_bare_double_slash_name_is_not_split(tmp_path):
    """'SP//dr' has no spaces around '//' — it is ONE name, and matching it must
    not invent a bogus 'SP' front face (the alias that once produced six copies
    of a singleton)."""
    p = tmp_path / "spdr.txt"
    p.write_text("# --- Creatures ---\n1 SP//dr, Piloted by Peni\n1 Shivan Dragon\n",
                 encoding="utf-8")
    assert app._edit_deck_card(str(p), "remove", "SP") is False
    assert app._edit_deck_card(str(p), "remove", "SP//dr, Piloted by Peni") is True


# --------------------------------------------------------------------------- #
# Replace re-files by the INCOMING card's type
#
# Writing the replacement at the outgoing card's line put a Sorcery under
# Creatures whenever the types differed — one of the three writers behind the 19
# misfiled cards found on 2026-08-20 (Grim Tutor under Creatures came from this
# exact flow, via the swap the session applied by hand).
# --------------------------------------------------------------------------- #
def _typed_deck(tmp_path):
    p = tmp_path / "typed.txt"
    p.write_text(
        "# Title: T\n# Commander: Test Commander\n\n"
        "# --- Commander ---\n1 Test Commander\n\n"
        "# --- Creatures ---\n1 Grizzly Bears\n1 Llanowar Elves\n\n"
        "# --- Sorceries ---\n1 Cultivate\n\n"
        "# --- Combo Pieces ---\n1 Old Combo Card\n",
        encoding="utf-8")
    return str(p)


def test_replace_refiles_when_the_incoming_type_contradicts_the_section(tmp_path):
    deck = _typed_deck(tmp_path)
    assert app._edit_deck_card(deck, "replace", "Grizzly Bears", "Grim Tutor",
                               types=["Sorcery"]) is True
    text = read(deck)
    assert "Grizzly Bears" not in text
    creatures = text.split("# --- Creatures ---")[1].split("# ---")[0]
    sorceries = text.split("# --- Sorceries ---")[1].split("# ---")[0]
    assert "Grim Tutor" not in creatures
    assert "Grim Tutor" in sorceries


def test_replace_stays_in_place_when_types_are_unknown(tmp_path):
    """Absent type data must not become a guess — in place, exactly as before."""
    deck = _typed_deck(tmp_path)
    assert app._edit_deck_card(deck, "replace", "Grizzly Bears", "Mystery Card",
                               types=None) is True
    creatures = read(deck).split("# --- Creatures ---")[1].split("# ---")[0]
    assert "Mystery Card" in creatures


def test_replace_stays_in_place_when_types_agree(tmp_path):
    deck = _typed_deck(tmp_path)
    assert app._edit_deck_card(deck, "replace", "Grizzly Bears", "Bear Cub",
                               types=["Creature"]) is True
    creatures = read(deck).split("# --- Creatures ---")[1].split("# ---")[0]
    assert "Bear Cub" in creatures
    assert creatures.index("Bear Cub") >= 0


def test_replace_respects_a_custom_section(tmp_path):
    """A player's own grouping ('Combo Pieces') is not a type claim — the incoming
    card stays where the outgoing one sat, whatever its type."""
    deck = _typed_deck(tmp_path)
    assert app._edit_deck_card(deck, "replace", "Old Combo Card", "Grim Tutor",
                               types=["Sorcery"]) is True
    combo = read(deck).split("# --- Combo Pieces ---")[1]
    assert "Grim Tutor" in combo
