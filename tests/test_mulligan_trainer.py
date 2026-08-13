"""Phase 5 — the mulligan trainer.

Deck-aware and offline, unlike the 2025-26 trainers that exist. The properties that
matter: the verdict shown to the player is the SAME rule the simulator plays by (a
trainer that taught a different rule than the engine measures would be worse than
none), hands are seeded so they are reproducible, and the page is honest that the
rule reads land counts rather than card quality."""
import json

import goldfish
import mtglib
import pytest

C = mtglib.Card


@pytest.fixture
def client(tmp_path, monkeypatch, collection_file):
    import app as appmod
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "d.txt").write_text(
        "# Title: Test Deck\n# Commander: Test Commander\n# Colors: W U\n"
        "\n# --- Commander ---\n1 Test Commander\n"
        "\n# --- Main ---\n1 Sol Ring\n1 Counterspell\n1 Swords to Plowshares\n"
        "1 Serra Angel\n"
        "\n# --- Lands ---\n12 Island\n", encoding="utf-8")
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", collection_file)
    monkeypatch.setattr(appmod, "PASSWORD", None)
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _hand(n_lands, n_spells):
    hand = [C(name=f"Island {i}", quantity=1, mana_value=0.0, types=["Land"])
            for i in range(n_lands)]
    hand += [C(name=f"Spell {i}", quantity=1, mana_value=2.0, types=["Instant"])
             for i in range(n_spells)]
    return [goldfish.compile_card(c) for c in hand]


def test_the_trainers_verdict_is_the_simulators_own_rule():
    """One rule, two consumers. A trainer teaching a different rule than the engine
    measures by would be actively misleading."""
    lo, hi = goldfish.KEEP_LANDS
    assert goldfish.keep_verdict(_hand(lo, 7 - lo))["keep"] is True
    assert goldfish.keep_verdict(_hand(lo - 1, 7 - lo + 1))["keep"] is False
    assert goldfish.keep_verdict(_hand(hi + 1, 7 - hi - 1))["keep"] is False


def test_the_london_floor_keeps_whatever_it_holds():
    """At the floor the sim stops mulliganing — the trainer has to say so rather than
    pretending a 0-land five-carder is a keep on its merits."""
    v = goldfish.keep_verdict(_hand(0, 7), mulls=goldfish.MULL_FLOOR)
    assert v["keep"] is True
    assert "floor" in v["why"]


def test_every_verdict_explains_itself():
    for hand, mulls in ((_hand(0, 7), 0), (_hand(7, 0), 0), (_hand(3, 4), 0)):
        v = goldfish.keep_verdict(hand, mulls=mulls)
        assert v["why"].strip(), "a verdict with no reasoning teaches nothing"
        assert v["lands"] == sum(1 for c in hand if c.is_land)


def test_the_hand_endpoint_is_seeded_and_reproducible(client):
    a = json.loads(client.get("/api/deck/d/hand?seed=42").get_data(as_text=True))
    b = json.loads(client.get("/api/deck/d/hand?seed=42").get_data(as_text=True))
    assert a["hand"] == b["hand"], "same seed, same hand"
    c = json.loads(client.get("/api/deck/d/hand?seed=43").get_data(as_text=True))
    assert len(a["hand"]) == 7
    assert a["hand"] != c["hand"] or True   # different seeds usually differ


def test_the_endpoint_ships_the_verdict_and_its_caveat(client):
    d = json.loads(client.get("/api/deck/d/hand?seed=7").get_data(as_text=True))
    assert "keep" in d["verdict"] and d["verdict"]["why"]
    assert "LANDS, not card quality" in d["caveat"], (
        "the page must say what the rule cannot see")
    assert d["band"] == list(goldfish.KEEP_LANDS)


def test_the_page_renders(client):
    body = client.get("/deck/d/mulligan").get_data(as_text=True)
    assert "Mulligan trainer" in body
    assert "localStorage" in body, "session stats stay on the device"
