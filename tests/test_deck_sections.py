"""deck_sections.py — the EDHREC-style type regroup — plus deckcore.load_power_tags.

What can go wrong: a regroup that loses cards or quantities silently corrupts a
deck; a guessed type defeats the grounding rules; a non-idempotent rewrite churns
git history on every run. Hermetic: decks, collections and reference lists all live
in tmp_path.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import deck_sections
import deckcore
import mtglib


DECK = """# Title: Test Deck
# Commander: Test Commander
# Note: keep me

# --- Commander ---
1 Test Commander

# --- Ramp ---
1 Sol Ring
1 Cultivate

# --- Stuff ---
1 Grizzly Bears
1 Mystery Card

# --- Equipment (2) ---
1 Colossus Hammer

# --- Lands (3) ---
1 Command Tower
2 Forest
"""

ATTRS = """Name,Type
Sol Ring,Artifact
Cultivate,Sorcery
Grizzly Bears,Creature
Colossus Hammer,Artifact
Command Tower,Land
"""


@pytest.fixture
def deck_dir(tmp_path):
    deck = tmp_path / "test-deck.txt"
    deck.write_text(DECK, encoding="utf-8")
    (tmp_path / "test-deck.attrs.csv").write_text(ATTRS, encoding="utf-8")
    coll = tmp_path / "coll.txt"
    coll.write_text("1 Test Commander\n1 Sol Ring\n1 Cultivate\n1 Grizzly Bears\n"
                    "1 Mystery Card\n1 Colossus Hammer\n1 Command Tower\n9 Forest\n",
                    encoding="utf-8")
    return deck, coll


def test_regroup_types_hints_and_honesty(deck_dir):
    deck, coll = deck_dir
    text, st = deck_sections.regroup(str(deck), str(coll))
    assert st["total"] == 9, "regroup must not create or lose cards"
    assert "# Note: keep me" in text, "header block survives verbatim"
    assert text.index("# --- Commander ---") < text.index("# --- Creatures ---"), \
        "commander section stays first"
    # typed by attrs
    assert "# --- Artifacts ---\n1 Sol Ring\n1 Colossus Hammer" in text
    assert "# --- Sorceries ---\n1 Cultivate" in text
    # basics split from nonbasic lands, quantities intact
    assert "# --- Basics ---\n2 Forest" in text
    assert "# --- Lands ---\n1 Command Tower" in text
    # unknown card in an unhinted section is declared, never guessed
    assert st["unsorted_names"] == ["Mystery Card"]
    assert "Unsorted" in text


def test_regroup_is_idempotent(deck_dir):
    deck, coll = deck_dir
    text1, _ = deck_sections.regroup(str(deck), str(coll))
    deck.write_text(text1, encoding="utf-8")
    text2, st2 = deck_sections.regroup(str(deck), str(coll))
    assert text2 == text1
    assert st2["total"] == 9


def test_section_hint_types_when_data_is_absent(tmp_path):
    deck = tmp_path / "d.txt"
    deck.write_text("# Commander: X\n# --- Commander ---\n1 X\n"
                    "# --- Equipment ---\n1 Unknown Blade\n", encoding="utf-8")
    coll = tmp_path / "c.txt"
    coll.write_text("1 X\n1 Unknown Blade\n", encoding="utf-8")
    text, st = deck_sections.regroup(str(deck), str(coll))
    assert "# --- Artifacts ---\n1 Unknown Blade" in text, \
        "an Equipment-section card with no type data files as an artifact"
    assert st["hinted"] == 1 and st["unsorted"] == 0


def test_type_bucket_precedence():
    assert deckcore.type_bucket("Forest", ["Land"]) == "Basics"
    assert deckcore.type_bucket("Baleful Strix", ["Artifact Creature"]) == "Creatures"
    assert deckcore.type_bucket("Buried Ruin", ["Land"]) == "Lands"
    assert deckcore.type_bucket("Who Knows", None) is None
    assert deckcore.type_bucket("Who Knows", []) is None


def test_power_tags_load_and_label(tmp_path):
    ref = tmp_path / "ref"
    ref.mkdir()
    (ref / "game_changers.txt").write_text("# header\nRhystic Study\n", encoding="utf-8")
    (ref / "tutors.txt").write_text("Mystical Tutor\n", encoding="utf-8")
    tags = deckcore.load_power_tags(refdir=str(ref))
    assert tags[mtglib._norm("Rhystic Study")] == ["Game Changer"]
    assert tags[mtglib._norm("Mystical Tutor")] == ["Tutor"]
    assert mtglib._norm("Sol Ring") not in tags, "absent lists degrade to no tag"
