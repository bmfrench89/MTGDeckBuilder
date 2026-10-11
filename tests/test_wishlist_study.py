"""The wishlist never lists a study copy's buys (`# Study: yes`).

A study deck's `.buylist.csv` is a priced shopping list for a deck the player has not
committed to — the Bracket 4 Tergrid rebuilds carry ~90 rows each. CLAUDE.md promises
the wishlist skips study decks; the conflict scan always did, `load_buylists` did not.
Hermetic: everything lives in tmp_path.
"""
import wishlist

BUY = "Card,Price,Tier,Replaces,Reason\nMox Diamond,999.00,Fast mana,,study buy\n"


def test_load_buylists_skips_study_decks(tmp_path):
    (tmp_path / "real.txt").write_text("# Title: Real\n# Commander: X\n1 X\n", encoding="utf-8")
    (tmp_path / "real.buylist.csv").write_text(BUY.replace("Mox Diamond", "Sol Ring"),
                                                encoding="utf-8")
    (tmp_path / "study.txt").write_text("# Title: Study\n# Commander: Y\n# Study: yes\n1 Y\n",
                                        encoding="utf-8")
    (tmp_path / "study.buylist.csv").write_text(BUY, encoding="utf-8")
    rows = wishlist.load_buylists(str(tmp_path))
    assert [(r["card"], r["deck"]) for r in rows] == [("Sol Ring", "real")]
