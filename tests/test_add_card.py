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


# --------------------------------------------------------------------------- #
# Review findings — each of these is a regression test for a shipped bug
# --------------------------------------------------------------------------- #
SPLIT_DECK = """# Title: S
# Commander: Test Commander
# Colors: W U R

# --- Spells ---
1 Fire

# --- Lands ---
1 Snow-Covered Island
"""

SPLIT_COLL = """Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,MARKET
2,Fire // Ice,2,U R,U R,{1}{R},Instant,,uncommon,fi1,0.50
4,Snow-Covered Island,0,,U,,Land,Island,common,si1,0.20
1,Test Commander,4,W U R,W U R,{1}{W}{U}{R},Legendary Creature,Human Wizard,rare,g7,1.00
"""


@pytest.fixture
def split_client(tmp_path):
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "s.txt").write_text(SPLIT_DECK, encoding="utf-8")
    coll = tmp_path / "c.csv"
    coll.write_text(SPLIT_COLL, encoding="utf-8")
    os.environ["MTG_DECKS_DIR"] = str(decks)
    os.environ["MTG_COLLECTION"] = str(coll)
    sys.modules.pop("app", None)
    import app
    app.app.config["TESTING"] = True
    c = app.app.test_client()
    c._decks = decks
    return c


def test_front_face_alias_cannot_sneak_in_a_second_copy(split_client):
    """The ' // ' trap: the deck says 'Fire', the collection says 'Fire // Ice' — the
    same physical card. Matching raw names let it in twice; membership must go through
    front_face on both sides."""
    r = split_client.post("/deck/s/add", data={"name": "Fire // Ice"})
    assert r.status_code == 400
    assert "singleton" in r.get_json()["error"].lower()
    assert "Fire // Ice" not in (split_client._decks / "s.txt").read_text(encoding="utf-8")


def test_snow_covered_basics_are_exempt_from_the_singleton_rule(split_client):
    """Snow-Covered Island is a basic land — any number is legal. The exemption used
    the six plain-basic names only, so a second snow basic was falsely refused."""
    r = split_client.post("/deck/s/add", data={"name": "Snow-Covered Island",
                                              "section": "Lands"})
    assert r.status_code == 200 and r.get_json()["ok"] is True


def test_is_basic_names(client):
    import mtglib
    assert mtglib.is_basic("Island") and mtglib.is_basic("Snow-Covered Wastes")
    assert not mtglib.is_basic("Command Tower")
    assert not mtglib.is_basic("Snow-Covered Command Tower")


def test_sections_endpoint_never_offers_the_synthetic_cards_label(tmp_path):
    """Cards before any header get grouped under an invented 'Cards' label for display;
    offering it in the picker sends the insert hunting for a header that isn't there."""
    import deckcore
    p = tmp_path / "d.txt"
    p.write_text("# Title: T\n\n1 Sol Ring\n\n# --- Lands ---\n1 Island\n",
                 encoding="utf-8")
    assert deckcore.real_section_labels(str(p)) == ["Lands"]
    # while the display grouping still shows the synthetic group:
    assert [l for l, _ in deckcore.load_deck_sections(str(p))] == ["Cards", "Lands"]


def test_advise_route_returns_json_when_analysis_fails(client, monkeypatch):
    """The picker consumes JSON; an analysis failure must not surface as an HTML 500."""
    import deckcore
    def boom(*a, **k):
        raise RuntimeError("companion file corrupt")
    monkeypatch.setattr(deckcore, "advise_card", boom)
    r = client.get("/api/deck/testdeck/advise?name=Sol Ring")
    assert r.status_code == 500
    assert "error" in r.get_json()


def test_advise_card_gives_the_same_verdict_with_prebuilt_context(client, collection_file):
    """The refs/ctx fast path for the optimizer's loop must not change the answer."""
    import deckcore, deck_fit, power, mtglib
    deck = str(client._decks / "testdeck.txt")
    a = deckcore.analyze_deck(deck, collection_file)
    refs = power.load_refs()
    ctx = deck_fit.deck_context(deck, a["enriched"], "Test Commander")
    slow = deckcore.advise_card(deck, collection_file, "Sol Ring", commander="Test Commander")
    fast = deckcore.advise_card(deck, collection_file, "Sol Ring", commander="Test Commander",
                                analysis=a, refs=refs, ctx=ctx)
    assert (slow["score"], slow["band"]) == (fast["score"], fast["band"])


def test_replace_refuses_a_card_already_in_the_deck(client):
    """Replace had none of Add's guards: swapping Arcane Signet for Sol Ring (already
    in the deck) silently wrote a duplicate that Add would have hard-rejected."""
    before = _deck_text(client)
    client.post("/deck/testdeck/card", data={"action": "replace",
                                             "name": "Arcane Signet",
                                             "replacement": "Sol Ring"})
    assert _deck_text(client) == before, "a duplicating replace must be refused"


def test_replace_with_a_new_card_still_works_and_is_logged(client):
    client.post("/deck/testdeck/card", data={"action": "replace",
                                             "name": "Arcane Signet",
                                             "replacement": "Counterspell"})
    text = _deck_text(client)
    assert "Counterspell" in text and "Arcane Signet" not in text
    log = (client._decks / "testdeck.changes.csv").read_text(encoding="utf-8")
    assert "manual-replace" in log


def test_dashboard_shows_an_illegal_banner_for_a_duplicate(client):
    """Regression: optimize() computes singleton_violations after every applying
    run, but the webapp's POST routes discarded the report — a violation from ANY
    source was invisible in the app. The deck page now banners it."""
    deck = client._decks / "testdeck.txt"
    deck.write_text(deck.read_text(encoding="utf-8") + "1 Sol Ring\n1 Sol Ring\n",
                    encoding="utf-8")
    html = client.get("/deck/testdeck").get_data(as_text=True)
    assert "ILLEGAL" in html and "Sol Ring" in html


def test_dashboard_shows_no_banner_when_legal(client):
    # the shared fixture deck runs '2 Arcane Signet' (deliberately, for the
    # validation tests) — write a genuinely legal deck for the negative case
    (client._decks / "testdeck.txt").write_text(
        "# Title: T\n# Commander: Test Commander\n# Colors: W U\n\n"
        "# --- Commander ---\n1 Test Commander\n\n"
        "# --- Ramp ---\n1 Sol Ring\n\n# --- Lands ---\n10 Island\n",
        encoding="utf-8")
    html = client.get("/deck/testdeck").get_data(as_text=True)
    assert "ILLEGAL — Commander allows one copy" not in html


# --------------------------------------------------------------------------- #
# Replace/Remove failures explain themselves (2026-08-15). Both failure paths
# used to return a bare redirect; the panel reloads on any redirect, so a
# refused or no-op edit was indistinguishable from success — the live "replace
# did not work" report from the Smaug deck.
# --------------------------------------------------------------------------- #
def test_a_duplicating_replace_returns_409_with_a_reason(client):
    r = client.post("/deck/testdeck/card", data={"action": "replace",
                                                 "name": "Arcane Signet",
                                                 "replacement": "Sol Ring"})
    assert r.status_code == 409
    assert "singleton" in r.get_data(as_text=True).lower()


def test_replacing_a_card_not_in_the_deck_returns_404_with_a_reason(client):
    before = _deck_text(client)
    r = client.post("/deck/testdeck/card", data={"action": "replace",
                                                 "name": "Serra Angel",
                                                 "replacement": "Counterspell"})
    assert r.status_code == 404
    assert "find" in r.get_data(as_text=True).lower()
    assert _deck_text(client) == before


def test_replace_reaches_a_dfc_line_through_its_front_face_key(client):
    """The panel's data-key for EDHREC/field rows is often the FRONT FACE alone,
    while the deck file holds the full 'A // B' name. The editor must bridge the
    two forms the same way the route's singleton guard already does."""
    (client._decks / "testdeck.txt").write_text(
        "# Title: Smaug Test\n\n# --- Commander ---\n"
        "1 Smaug, the Great Calamity // Spew Flame\n\n"
        "# --- Ramp ---\n1 Sol Ring\n", encoding="utf-8")
    r = client.post("/deck/testdeck/card", data={"action": "replace",
                                                 "name": "smaug, the great calamity",
                                                 "replacement": "Counterspell"})
    assert r.status_code in (302, 303), r.get_data(as_text=True)
    text = _deck_text(client)
    assert "1 Counterspell" in text
    assert "1 Smaug" not in text
