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


# ---- pins: reserving a single copy for one deck -----------------------------------

def test_pins_round_trip(tmp_path):
    p = str(tmp_path / "pins.csv")
    deckcore.save_pins({"sol ring": "deck-a", "arcane signet": "deck-b"}, p)
    assert deckcore.load_pins(p) == {"sol ring": "deck-a", "arcane signet": "deck-b"}


def test_missing_pins_file_is_empty(tmp_path):
    assert deckcore.load_pins(str(tmp_path / "nope.csv")) == {}


def test_pinned_elsewhere_excludes_the_owning_deck(tmp_path):
    pins = {"sol ring": "deck-a", "mana crypt": "deck-b"}
    assert deckcore.pinned_elsewhere("deck-a", pins) == {"mana crypt"}
    assert deckcore.pinned_elsewhere("deck-b", pins) == {"sol ring"}
    assert deckcore.pinned_elsewhere("deck-c", pins) == {"sol ring", "mana crypt"}


def test_optimizer_will_not_take_a_pinned_card(tmp_path, collection_file, monkeypatch):
    """The whole point: a copy reserved for another deck stays reserved, however well it
    scores for this one."""
    import deck_fit, optimize, mtglib as _m
    coll = _m.load_collection(collection_file)
    idx = _m.index_by_name(coll)
    monkeypatch.setattr(deck_fit, "load_field",
                        lambda *a, **k: {_m._norm("Counterspell"): 99})
    monkeypatch.setattr(deckcore, "pinned_elsewhere",
                        lambda stem, pins=None: {_m._norm("Counterspell")})
    deck = tmp_path / "d.txt"
    deck.write_text("# Commander: Test Commander\n# Colors: W U\n\n"
                    "# --- Creatures ---\n1 Serra Angel\n1 Llanowar Elves\n", encoding="utf-8")
    r = optimize.optimize(str(deck), coll, idx, str(tmp_path), apply=False)
    assert all("Counterspell" not in s[2] for s in r["swaps"])
