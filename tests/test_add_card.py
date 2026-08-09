"""Adding a card by hand, and the opinion that comes back.

Two things are being protected here. First, validation: an add that would make the deck
illegal (off-identity, duplicate) or that names a card the player doesn't own must be
refused with a reason, not silently ignored. Second, the invariant the whole feature
rests on — the advisor gives an OPINION and never an action, so the optimizer still
never cuts a card the player chose.

Offline and hermetic like the rest of the suite: every deck and collection lives in
tmp_path, and no test reaches the network (EDHREC field data is simply absent, which is
itself one of the cases under test).
"""
import os
import sys

import pytest


@pytest.fixture
def client(tmp_path, collection_file, deck_file):
    import shutil
    decks = tmp_path / "decks"
    decks.mkdir()
    shutil.copy(deck_file, decks / "testdeck.txt")
    os.environ["MTG_DECKS_DIR"] = str(decks)
    os.environ["MTG_COLLECTION"] = collection_file
    sys.modules.pop("app", None)
    import app
    app.app.config["TESTING"] = True
    c = app.app.test_client()
    c._decks = decks
    return c


def _deck_text(client):
    return (client._decks / "testdeck.txt").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Validation — every rejection must explain itself
# --------------------------------------------------------------------------- #
def test_add_accepts_an_owned_in_identity_card(client):
    r = client.post("/deck/testdeck/add", data={"name": "Counterspell", "section": "Ramp"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert "1 Counterspell" in _deck_text(client)


def test_add_refuses_a_card_you_do_not_own(client):
    r = client.post("/deck/testdeck/add", data={"name": "Black Lotus"})
    assert r.status_code == 400
    assert "don't own" in r.get_json()["error"]
    assert "Black Lotus" not in _deck_text(client)


def test_add_refuses_a_duplicate_because_commander_is_singleton(client):
    r = client.post("/deck/testdeck/add", data={"name": "Sol Ring"})
    assert r.status_code == 400
    assert "singleton" in r.get_json()["error"].lower()


def test_add_refuses_a_card_outside_the_color_identity(client):
    """An off-identity card isn't a matter of taste — it makes the deck illegal."""
    r = client.post("/deck/testdeck/add", data={"name": "Llanowar Elves"})
    assert r.status_code == 400
    err = r.get_json()["error"]
    assert "color identity" in err and "G" in err
    assert "Llanowar Elves" not in _deck_text(client)


def test_add_with_no_name_is_rejected(client):
    assert client.post("/deck/testdeck/add", data={"name": "  "}).status_code == 400


# --------------------------------------------------------------------------- #
# The change log — Source is what separates the player's decision from the tool's
# --------------------------------------------------------------------------- #
def test_add_is_logged_as_a_manual_change(client):
    client.post("/deck/testdeck/add", data={"name": "Counterspell", "section": "Ramp"})
    log = (client._decks / "testdeck.changes.csv").read_text(encoding="utf-8")
    assert "Card,Added,Replaced,Source" in log
    assert "Counterspell" in log and "manual-add" in log


def test_manual_adds_filter_ignores_optimizer_rows(tmp_path):
    """The optimizer writes to the same file; only Source=manual-* is the player."""
    import deckcore
    from datetime import date
    p = tmp_path / "d.changes.csv"
    today = date.today().isoformat()
    p.write_text("Card,Added,Replaced,Source\n"
                 f"Counterspell,{today},,manual-add\n"
                 f"Rhystic Study,{today},Divination,auto\n", encoding="utf-8")
    names = [r["name"] for r in deckcore.manual_adds(str(p))]
    assert names == ["Counterspell"]


# --------------------------------------------------------------------------- #
# The advisor — an opinion, and honest about what backs it
# --------------------------------------------------------------------------- #
def test_advise_scores_a_card_with_component_reasons(client):
    v = client.get("/api/deck/testdeck/advise?name=Sol Ring").get_json()
    assert v["name"] == "Sol Ring"
    assert 0 <= v["score"] <= 100 and v["band"]
    labels = {r["label"] for r in v["reasons"]}
    assert {"Color fit", "Role need", "Curve"} <= labels


def test_advise_says_when_there_is_no_field_data(client):
    """Offline, EDHREC data is absent — the verdict must admit that rather than
    implying the field backs it."""
    v = client.get("/api/deck/testdeck/advise?name=Sol Ring").get_json()
    assert v["has_field"] is False


def test_advise_refuses_to_opine_on_an_unknown_card(client):
    """Never invent a card: an unresolvable name gets no opinion at all."""
    r = client.get("/api/deck/testdeck/advise?name=Definitely Not A Card")
    assert r.status_code == 404


def test_add_returns_a_verdict_with_the_card(client):
    body = client.post("/deck/testdeck/add",
                       data={"name": "Counterspell", "section": "Ramp"}).get_json()
    assert body["verdict"] is not None
    assert body["verdict"]["name"] == "Counterspell"
    assert body["verdict"]["in_deck"] is True


def test_sections_endpoint_returns_the_decks_own_labels(client):
    labels = client.get("/api/deck/testdeck/sections").get_json()
    assert labels == ["Commander", "Ramp", "Lands"]


# --------------------------------------------------------------------------- #
# The invariant: advice is not action
# --------------------------------------------------------------------------- #
def test_optimizer_review_is_advisory_and_never_cuts_the_manual_add(client, collection_file):
    import mtglib
    import optimize
    client.post("/deck/testdeck/add", data={"name": "Counterspell", "section": "Ramp"})
    deck = str(client._decks / "testdeck.txt")
    before = open(deck, encoding="utf-8").read()
    lines = optimize.manual_adds_review(deck, mtglib.load_collection(collection_file))
    assert any("advisory" in l for l in lines)
    assert any("Counterspell" in l for l in lines)
    assert open(deck, encoding="utf-8").read() == before, "the review must not edit the deck"


def test_review_is_silent_when_there_are_no_manual_adds(client, collection_file):
    import mtglib
    import optimize
    deck = str(client._decks / "testdeck.txt")
    assert optimize.manual_adds_review(deck, mtglib.load_collection(collection_file)) == []
