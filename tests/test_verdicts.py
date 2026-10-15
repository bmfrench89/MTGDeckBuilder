"""Saved verdicts: a session's read of each proposal, shown on the phone's ⚡ page.

Deck-flow review bundle B. The app makes no AI calls (player decision 2026-10-14), so a
Claude session records its swap / skip / bench / wishlist verdict with
`optimize.py --verdict`. The file travels with the repo sync, and the ⚡ page shows each
verdict beside the SAME swap only. Everything is hermetic."""
import json
import sys

import pytest

import deckcore
import optimize
import store

R = {"swaps": [("Old Card", 5, "New Card", 60, "free")],
     "swaps_detail": [{"cut": "Old Card", "add": "New Card", "cut_inc": 5, "add_inc": 60,
                       "cut_field_known": True, "add_field_known": True}],
     "land_swaps": [], "buy_swaps": [], "role_ranges": {},
     "reads": [{"name": "Sleeper", "fit": 80, "role": "draw", "field": None}]}
KEY = optimize.proposal_key("spell", "Old Card", "New Card")


def test_record_writes_current_keys_and_refuses_the_rest(tmp_path):
    deck = tmp_path / "d.txt"
    deck.write_text("1 X\n", encoding="utf-8")
    written, stale = optimize.record_verdicts(
        str(deck), R, [(KEY, "Skip", "the cut is the engine"),
                       ("read|Sleeper", "bench", "a fine card, no slot"),
                       ("spell|Ghost|Card", "swap", "never proposed")], today="2026-10-15")
    assert written == [KEY, "read|Sleeper"] and stale == ["spell|Ghost|Card"]
    v = optimize.load_verdicts(str(deck))
    assert v[KEY] == {"verdict": "skip", "why": "the cut is the engine",
                      "by": "a Claude session", "date": "2026-10-15"}
    raw = json.loads((tmp_path / "d.verdicts.json").read_text(encoding="utf-8"))
    assert raw["version"] == 1 and set(raw["verdicts"]) == {KEY, "read|Sleeper"}


def test_a_verdict_needs_a_known_word_and_a_reason(tmp_path):
    deck = str(tmp_path / "d.txt")
    with pytest.raises(ValueError):
        optimize.record_verdicts(deck, R, [(KEY, "maybe", "hmm")])
    with pytest.raises(ValueError):
        optimize.record_verdicts(deck, R, [(KEY, "skip", "  ")])


def test_a_broken_file_costs_the_annotations_not_the_page(tmp_path):
    (tmp_path / "d.verdicts.json").write_text("{not json", encoding="utf-8")
    assert optimize.load_verdicts(str(tmp_path / "d.txt")) == {}
    assert optimize.load_verdicts(str(tmp_path / "missing.txt")) == {}


def test_attach_shows_a_verdict_only_beside_its_own_swap():
    verdicts = {KEY: {"verdict": "skip", "why": "w", "date": "d", "by": "b"},
                "spell|Gone|Card": {"verdict": "swap", "why": "w", "date": "d", "by": "b"}}
    props, reads, stale = optimize.attach_verdicts(optimize.proposals(R), R["reads"], verdicts)
    assert props[0]["verdict"]["verdict"] == "skip"
    assert reads[0]["verdict"] is None
    assert stale == 1


def test_the_review_payload_carries_them(tmp_path):
    p = optimize.review_payload(R, {KEY: {"verdict": "swap", "why": "w", "date": "d",
                                          "by": "b"}})
    json.dumps(p)
    assert p["proposals"][0]["verdict"]["verdict"] == "swap"
    assert p["verdicts_stale"] == 0


def test_the_cli_saves_and_reports(tmp_path, monkeypatch, capsys):
    deck = tmp_path / "d.txt"
    deck.write_text("1 X\n", encoding="utf-8")
    (tmp_path / "c.csv").write_text("Quantity,Name\n1,X\n", encoding="utf-8")
    monkeypatch.setattr(optimize, "optimize", lambda *a, **k: R)
    monkeypatch.setattr(sys, "argv", ["optimize.py", "--deck", str(deck), "--collection",
                                      str(tmp_path / "c.csv"), "--decks-dir", str(tmp_path),
                                      "--verdict", KEY, "skip", "engine card",
                                      "--verdict", "spell|No|Such", "swap", "x"])
    assert optimize.main() == 0
    out = capsys.readouterr().out
    assert f"saved  {KEY}" in out and "not proposed now, not saved: spell|No|Such" in out
    monkeypatch.setattr(sys, "argv", sys.argv[:-8] + ["--verdict", KEY, "perhaps", "x"])
    assert optimize.main() == 2


def test_the_server_keeps_the_file_with_the_deck():
    assert ".verdicts.json" in store.DECK_SUFFIXES


# ---- the ⚡ page -------------------------------------------------------------------------

DECK = """\
# Title: Test Deck
# Commander: Test Commander
# Colors: W U

# --- Commander ---
1 Test Commander

# --- Artifacts ---
1 Sol Ring
"""


@pytest.fixture
def page(tmp_path, monkeypatch, collection_file):
    import app as appmod
    import enrich_bg
    import sync
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "td.txt").write_text(DECK, encoding="utf-8")
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", collection_file)
    monkeypatch.setattr(appmod, "COLLECTION_CSV", str(tmp_path / "coll" / "collection.csv"))
    monkeypatch.setattr(appmod, "ADDITIONS", str(tmp_path / "owned_additions.txt"))
    monkeypatch.setattr(appmod, "PASSWORD", None)
    monkeypatch.setattr(deckcore, "PINS", str(tmp_path / "pins.csv"))
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    monkeypatch.setattr(enrich_bg, "start", lambda *a, **k: "enrichment started")
    monkeypatch.setattr(appmod.optimize, "optimize", lambda *a, **k: R)
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client(), decks


def test_the_review_page_shows_a_saved_read_and_hides_stale_ones(page):
    client, decks = page
    (decks / "td.verdicts.json").write_text(json.dumps({"version": 1, "verdicts": {
        KEY: {"verdict": "skip", "why": "Old Card is the engine", "date": "2026-10-15",
              "by": "a Claude session"},
        "spell|Gone|Card": {"verdict": "swap", "why": "stale reason", "date": "2026-10-01",
                            "by": "a Claude session"}}}), encoding="utf-8")
    html = client.get("/deck/td/optimize").get_data(as_text=True)
    assert "Claude's read (2026-10-15)" in html and "Old Card is the engine" in html
    assert "stale reason" not in html
    assert "Hidden: 1 saved read from an earlier session" in html
