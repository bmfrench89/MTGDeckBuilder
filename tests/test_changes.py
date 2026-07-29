"""The NEW badge: which cards the optimizer added recently.

After a collection refresh the optimizer can swap a dozen cards into a 100-card list;
without a marker you'd have to diff it by eye. `<deck>.changes.csv` records what each run
added, and the dashboard badges anything from the last two weeks.
"""
import csv
import os
from datetime import date, timedelta

import deckcore
import optimize


def _log(tmp_path, rows):
    p = tmp_path / "d.changes.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Card", "Added", "Replaced", "Source"])
        w.writerows(rows)
    return str(p)


def _ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


def test_recent_additions_are_returned(tmp_path):
    ch = deckcore.load_changes(_log(tmp_path, [
        ["Lathliss, Dragon Queen", _ago(0), "Raging Goblin", "free"],
        ["Scourge of Valkas", _ago(3), "Cloud Sprite", "free"],
    ]))
    assert set(ch) == {"lathliss, dragon queen", "scourge of valkas"}
    assert ch["lathliss, dragon queen"]["days_ago"] == 0
    assert ch["scourge of valkas"]["replaced"] == "Cloud Sprite"


def test_old_additions_stop_being_new(tmp_path):
    ch = deckcore.load_changes(_log(tmp_path, [["Sol Ring", _ago(40), "X", "free"]]))
    assert ch == {}


def test_window_is_configurable(tmp_path):
    p = _log(tmp_path, [["Sol Ring", _ago(20), "X", "free"]])
    assert deckcore.load_changes(p) == {}                 # default 14 days
    assert "sol ring" in deckcore.load_changes(p, days=30)


def test_missing_or_malformed_log_is_safe(tmp_path):
    assert deckcore.load_changes(str(tmp_path / "nope.csv")) == {}
    bad = _log(tmp_path, [["Card A", "not-a-date", "", ""], ["", _ago(1), "", ""]])
    assert deckcore.load_changes(bad) == {}


def test_most_recent_entry_wins(tmp_path):
    """A card removed and re-added should report the latest date, not the first."""
    ch = deckcore.load_changes(_log(tmp_path, [
        ["Sol Ring", _ago(12), "A", "free"],
        ["Sol Ring", _ago(2), "B", "free"],
    ]))
    assert ch["sol ring"]["days_ago"] == 2 and ch["sol ring"]["replaced"] == "B"


def test_record_changes_appends_and_keeps_history(tmp_path):
    deck = tmp_path / "d.txt"
    deck.write_text("# Commander: X\n1 Sol Ring\n", encoding="utf-8")
    n = optimize.record_changes(str(deck), [("Old", 0, "New Card", 90, "free")], [])
    assert n == 1
    n2 = optimize.record_changes(str(deck), [], [("Bad Land", "Good Land", "share")])
    assert n2 == 1
    rows = list(csv.DictReader(open(tmp_path / "d.changes.csv", encoding="utf-8")))
    assert [r["Card"] for r in rows] == ["New Card", "Good Land"]   # appended, not replaced
    assert rows[0]["Replaced"] == "Old"


def test_record_changes_is_a_no_op_with_nothing_to_log(tmp_path):
    deck = tmp_path / "d.txt"
    deck.write_text("# Commander: X\n", encoding="utf-8")
    assert optimize.record_changes(str(deck), [], []) == 0
    assert not os.path.exists(tmp_path / "d.changes.csv")
