"""Phase 6 — pins v2: reserved means reserved, and moving one is cheap.

The hard core (auto_build's pool, the optimizer's cuts and adds) already honoured
pins. These tests cover what did NOT: the surfaces that present a card as available,
the management screen, and the fact that a shortfall and a pin stop being told as two
unrelated stories."""
import sys

import deck_conflicts
import deckcore
import edhrec
import mtglib
import pytest


def test_edhrec_labels_a_staple_reserved_for_another_deck():
    """The gap this closes: a staple whose only copy is pinned elsewhere was offered
    as an ordinary owned 'add'. It is still LISTED — hiding it would leave the player
    wondering where a staple went — but now it says whose it is."""
    pins = {mtglib._norm("Sol Ring"): "other-deck"}
    assert edhrec._pinned_elsewhere("Sol Ring", pins, "this-deck") == "other-deck"
    assert edhrec._pinned_elsewhere("Sol Ring", pins, "other-deck") is None, (
        "a card pinned to THIS deck is available here")
    assert edhrec._pinned_elsewhere("Sol Ring", {}, "this-deck") is None


def test_pin_lookup_is_front_face_aware():
    """A pin recorded under either spelling of a split card must be found — the
    ' // ' trap that has bitten this repo three times."""
    pins = {mtglib._norm("Murderous Rider"): "deck-a"}
    assert edhrec._pinned_elsewhere("Murderous Rider // Swift End", pins, "deck-b") \
        == "deck-a"
    assert deck_conflicts._pin_of("Murderous Rider // Swift End", pins) == "deck-a"


def test_a_shortfall_names_the_deck_holding_the_copy(tmp_path, collection_file):
    """A conflict row and a pin describe the same physical card. Reporting them
    separately is what made them read as unrelated facts."""
    decks = tmp_path / "decks"
    decks.mkdir()
    for stem in ("a", "b"):
        (decks / f"{stem}.txt").write_text(
            f"# Commander: C{stem}\n\n# --- Main ---\n1 Counterspell\n", encoding="utf-8")
    coll = mtglib.load_collection(collection_file)   # 1x Counterspell
    idx = mtglib.index_by_name(coll)
    usage = deck_conflicts.scan(str(decks), idx)
    rows = deck_conflicts.conflicts(usage, pins={mtglib._norm("Counterspell"): "a"})
    row = next(r for r in rows if r["card"] == "Counterspell")
    assert row["short"] == 1
    assert row["pinned_to"] == "a"
    # ...and with no pins supplied the field is present but empty, never missing
    rows2 = deck_conflicts.conflicts(usage)
    assert next(r for r in rows2 if r["card"] == "Counterspell")["pinned_to"] is None


def test_cli_report_names_the_pin_holding_the_copy(tmp_path, monkeypatch, capsys,
                                                   collection_file):
    """`conflicts()` has always built `pinned_to`, but main() never loaded the pins —
    so the CLI, the surface a session actually reads, printed a shortfall with no
    hint that the repo already knew which deck won the card."""
    decks = tmp_path / "decks"
    decks.mkdir()
    for stem in ("a", "b"):
        (decks / f"{stem}.txt").write_text(
            f"# Commander: C{stem}\n\n# --- Main ---\n1 Counterspell\n",
            encoding="utf-8")
    pins_path = str(tmp_path / "pins.csv")
    monkeypatch.setattr(deckcore, "PINS", pins_path)
    deckcore.save_pins({mtglib._norm("Counterspell"): "a"}, path=pins_path)
    monkeypatch.setattr(sys, "argv", ["deck_conflicts.py", "--collection",
                                      collection_file, "--decks-dir", str(decks)])
    assert deck_conflicts.main() == 0
    out = capsys.readouterr().out
    assert "Counterspell" in out
    assert "pinned to: a" in out


@pytest.fixture
def client(tmp_path, monkeypatch, collection_file):
    import app as appmod
    decks = tmp_path / "decks"
    decks.mkdir()
    for stem in ("alpha", "beta"):
        (decks / f"{stem}.txt").write_text(
            f"# Title: Deck {stem}\n# Commander: Cmd {stem}\n"
            f"\n# --- Main ---\n1 Counterspell\n", encoding="utf-8")
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", collection_file)
    monkeypatch.setattr(appmod, "PASSWORD", None)
    monkeypatch.setattr(deckcore, "PINS", str(tmp_path / "pins.csv"))
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def test_the_pins_page_lists_reservations_and_flags_stale_ones(client, tmp_path):
    deckcore.save_pins({mtglib._norm("Counterspell"): "alpha",
                        mtglib._norm("Sol Ring"): "alpha"},
                       path=str(tmp_path / "pins.csv"))
    body = client.get("/pins").get_data(as_text=True)
    assert "Counterspell" in body
    # Sol Ring is pinned to alpha but alpha does not run it -> stale, and saying so
    # is the whole point: a pin holding a copy nothing uses is invisible otherwise.
    assert "stale" in body


def test_moving_a_pin_is_one_action(client, tmp_path):
    pins_path = str(tmp_path / "pins.csv")
    deckcore.save_pins({mtglib._norm("Counterspell"): "alpha"}, path=pins_path)
    r = client.post("/pins/move", data={"card": "Counterspell", "deck": "beta"})
    assert r.status_code in (302, 303)
    assert deckcore.load_pins(path=pins_path)[mtglib._norm("Counterspell")] == "beta"


def test_releasing_a_pin_frees_the_copy(client, tmp_path):
    pins_path = str(tmp_path / "pins.csv")
    deckcore.save_pins({mtglib._norm("Counterspell"): "alpha"}, path=pins_path)
    client.post("/pins/move", data={"card": "Counterspell", "deck": "none"})
    assert mtglib._norm("Counterspell") not in deckcore.load_pins(path=pins_path)
