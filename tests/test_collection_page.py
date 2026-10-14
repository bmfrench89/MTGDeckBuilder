"""The Collection page's card data (webapp/app.py `_collection_cards`).

"In a deck" is a statement about physical cards. A study copy (`# Study: yes`) holds
none, which is why deck_conflicts, the free pool and the wishlist all skip it. The
Collection page's filter counted study lists anyway, and flagged 97 cards as in use
that sit only in study decks (collection audit 2026-10-14). Hermetic: tmp_path only.
"""
import os

import mtglib


def _write(path, text):
    path.write_text(text, encoding="utf-8")


def test_in_a_deck_ignores_study_copies(tmp_path):
    import app as appmod
    decks = tmp_path / "decks"
    decks.mkdir()
    _write(decks / "real.txt", "# Title: Real\n# Commander: Test Commander\n"
                               "# --- Commander ---\n1 Test Commander\n"
                               "# --- Artifacts ---\n1 Sol Ring\n")
    _write(decks / "study.txt", "# Title: Study\n# Commander: Test Commander\n# Study: yes\n"
                                "# --- Commander ---\n1 Test Commander\n"
                                "# --- Instants ---\n1 Counterspell\n")
    coll = [mtglib.Card(name=n, quantity=1, types=["Artifact"])
            for n in ("Sol Ring", "Counterspell", "Arcane Signet")]
    rows = {r["name"]: r["decks"] for r in appmod._collection_cards(coll, str(decks))}
    assert rows["Sol Ring"] == ["real"]
    assert rows["Counterspell"] == [], "a study copy holds no physical card"
    assert rows["Arcane Signet"] == []
