"""Phase 4 — the Rule-0 table card.

The artifact players actually use before a game: bracket, Game Changers, mass land
denial, extra turns, combos, speed, game plan — one screen, printable, phone-showable.
These tests pin the two things that make it trustworthy rather than decorative: every
disclosure comes from the same engines the dashboard uses, and a missing data source
is NAMED rather than silently omitted."""
import os

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch, collection_file):
    import app as appmod
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "d.txt").write_text(
        "# Title: Test Deck\n# Commander: Test Commander\n# Colors: W U\n"
        "# Archetype: control\n"
        "\n# --- Commander ---\n1 Test Commander\n"
        "\n# --- Main ---\n1 Sol Ring\n1 Counterspell\n1 Swords to Plowshares\n"
        "\n# --- Lands ---\n10 Island\n", encoding="utf-8")
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", collection_file)
    monkeypatch.setattr(appmod, "PASSWORD", None)
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def test_the_table_card_renders_with_its_disclosures(client):
    r = client.get("/deck/d/table-card")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Test Deck" in body and "Test Commander" in body
    for label in ("Game Changers", "Mass land denial", "Extra turns",
                  "Two-card combos", "What this deck does"):
        assert label in body, f"the {label} disclosure must be on the card"
    assert "estimates, not verdicts" in body


def test_the_plan_says_where_it_came_from(client, tmp_path):
    """A derived plan must never be mistaken for the player's own words."""
    body = client.get("/deck/d/table-card").get_data(as_text=True)
    assert "derived from role counts" in body, (
        "with no .notes.md the card must label its fallback")
    notes = os.path.join(os.path.dirname(client.application.config.get("_x", "") or ""), "")
    # now give the deck real notes and check the label flips
    import app as appmod
    with open(os.path.join(appmod.DECKS_DIR, "d.notes.md"), "w", encoding="utf-8") as f:
        f.write("# Plan\n- Durdle until Test Commander lands, then win.\n")
    body2 = client.get("/deck/d/table-card").get_data(as_text=True)
    assert "Durdle until Test Commander lands" in body2
    assert "Source: your notes" in body2


def test_the_declared_bracket_shows_with_the_detected_one(client):
    """Both, always — the setting is intent, not a way to hide the card evidence."""
    import app as appmod
    path = os.path.join(appmod.DECKS_DIR, "d.txt")
    appmod._set_deck_header(path, "Bracket", "5")
    body = client.get("/deck/d/table-card").get_data(as_text=True)
    assert "your setting" in body
    assert "Card signals detect" in body, "the detected bracket must stay visible"


def test_an_unreachable_combo_source_is_named_not_hidden(client, monkeypatch):
    """Degrading honestly is the whole contract: offline, the card says combo data is
    unavailable rather than printing a confident 'none detected'."""
    import spellbook
    monkeypatch.setattr(spellbook, "combos_for_deck",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no network")))
    body = client.get("/deck/d/table-card").get_data(as_text=True)
    assert "combo data unavailable offline" in body


def test_the_card_is_printable(client):
    """It is meant to be handed across a table — the print rules must exist and drop
    the app chrome."""
    body = client.get("/deck/d/table-card").get_data(as_text=True)
    assert "@media print" in body
    assert "nav, footer, .noprint" in body
