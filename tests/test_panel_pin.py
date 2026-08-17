"""Phase B — pinning from the SITE-WIDE card panel.

The pin control existed only on the generated dashboard's panel
(`scripts/assets/card_panel.html`). The site-wide panel — `webapp/templates/_cardpanel.html`,
included by `base.html` and opened by any `data-card="…"` element on the collection /
shared / wishlist / index pages — had none, while `pins.html`'s empty state told the player
to pin "from its panel". That is the two-surfaces trap `CLAUDE.md` warns about, live.

Two design decisions these tests pin down, both from the spec review:

* **The picker offers only decks that RUN the card** (`payload.decks`), never every deck.
  A pin on a card nothing plays is exactly the "stale" state `/pins` exists to flag, so the
  panel must not be able to mint one. An ALREADY-stale pin is the exception — it stays
  visible so it can be released.
* **The JSON path must not `flash()`.** The panel posts and stays put; a queued message
  would pop as a stale toast on whatever full page the player loaded next, describing a
  pin they changed minutes ago somewhere else. The `/pins` page's redirect+flash contract
  is unchanged.
"""
import card_api
import deckcore
import mtglib
import pytest


@pytest.fixture
def decks_dir(tmp_path):
    d = tmp_path / "decks"
    d.mkdir()
    for stem in ("alpha", "beta"):
        (d / f"{stem}.txt").write_text(
            f"# Title: Deck {stem}\n# Commander: Cmd {stem}\n"
            f"\n# --- Main ---\n1 Counterspell\n", encoding="utf-8")
    # gamma runs a split card, so the ' // ' trap is exercised end to end
    (d / "gamma.txt").write_text(
        "# Title: Deck gamma\n# Commander: Cmd gamma\n"
        "\n# --- Main ---\n1 Murderous Rider // Swift End\n", encoding="utf-8")
    return str(d)


@pytest.fixture
def pins_path(tmp_path, monkeypatch):
    p = str(tmp_path / "pins.csv")
    monkeypatch.setattr(deckcore, "PINS", p)
    return p


@pytest.fixture
def client(tmp_path, monkeypatch, collection_file, decks_dir, pins_path):
    import app as appmod
    monkeypatch.setattr(appmod, "DECKS_DIR", decks_dir)
    monkeypatch.setattr(appmod, "COLLECTION", collection_file)
    monkeypatch.setattr(appmod, "PASSWORD", None)
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


# --- the payload ------------------------------------------------------------------

def test_payload_names_the_deck_holding_the_copy(collection_file, decks_dir, pins_path):
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    deckcore.save_pins({mtglib._norm("Counterspell"): "alpha"}, path=pins_path)

    d = card_api.card_payload("Counterspell", idx, decks_dir)
    assert d["pinned"] == "alpha"
    # the picker sources from this list, so it must keep working
    assert sorted(d["decks"]) == ["alpha", "beta"]


def test_payload_pinned_is_none_when_nothing_is_reserved(collection_file, decks_dir,
                                                         pins_path):
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    d = card_api.card_payload("Counterspell", idx, decks_dir)
    assert d["pinned"] is None, "absent pins.csv must read as 'not pinned', not crash"


def test_payload_pin_lookup_is_front_face_aware(collection_file, decks_dir, pins_path):
    """A pin recorded under the front face must be found when the panel opens on the
    full split name — `edhrec` and `deck_conflicts` already resolve pins this way."""
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    deckcore.save_pins({mtglib._norm("Murderous Rider"): "gamma"}, path=pins_path)

    d = card_api.card_payload("Murderous Rider // Swift End", idx, decks_dir)
    assert d["pinned"] == "gamma"


def test_payload_survives_an_unreadable_pins_file(collection_file, decks_dir, tmp_path,
                                                  monkeypatch):
    """Pins are best-effort in the panel, exactly as in build_dashboard: a broken file
    means 'no pin', never a 500 on every card the player clicks."""
    bad = tmp_path / "pins.csv"
    bad.mkdir()                      # a directory where a CSV is expected
    monkeypatch.setattr(deckcore, "PINS", str(bad))
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))

    assert card_api.card_payload("Counterspell", idx, decks_dir)["pinned"] is None


def test_api_card_route_exposes_pinned_and_decks(client, pins_path):
    deckcore.save_pins({mtglib._norm("Counterspell"): "beta"}, path=pins_path)
    j = client.get("/api/card/Counterspell").get_json()
    assert j["pinned"] == "beta"
    assert sorted(j["decks"]) == ["alpha", "beta"]


# --- the JSON write path ----------------------------------------------------------

def _flashes(client):
    with client.session_transaction() as sess:
        return sess.get("_flashes", [])


def test_panel_pin_returns_json_and_queues_no_flash(client, pins_path):
    r = client.post("/pins/move",
                    data={"card": "Counterspell", "deck": "alpha", "json": "1"})
    assert r.get_json() == {"ok": True, "pinned": "alpha"}
    assert deckcore.load_pins(path=pins_path)[mtglib._norm("Counterspell")] == "alpha"
    assert _flashes(client) == [], (
        "a flash queued here pops as a stale toast on the next full page load")


def test_panel_release_returns_null_and_queues_no_flash(client, pins_path):
    deckcore.save_pins({mtglib._norm("Counterspell"): "alpha"}, path=pins_path)
    r = client.post("/pins/move",
                    data={"card": "Counterspell", "deck": "none", "json": "1"})
    assert r.get_json() == {"ok": True, "pinned": None}
    assert mtglib._norm("Counterspell") not in deckcore.load_pins(path=pins_path)
    assert _flashes(client) == []


def test_the_pins_page_contract_is_untouched(client, pins_path):
    """Without json=1 the /pins form still redirects AND still flashes — the panel's
    variant must not have quietly changed the management screen's behaviour."""
    r = client.post("/pins/move", data={"card": "Counterspell", "deck": "alpha"})
    assert r.status_code in (302, 303)
    assert deckcore.load_pins(path=pins_path)[mtglib._norm("Counterspell")] == "alpha"
    assert _flashes(client), "the /pins page tells the player what it did"


# --- the surface ------------------------------------------------------------------

def test_the_site_wide_panel_carries_the_pin_control(client):
    """The control lives in a template nothing else asserts on; without this test it can
    be dropped in a refactor and the only symptom is a silently missing feature."""
    body = client.get("/pins").get_data(as_text=True)
    for ident in ("cp-pinwrap", "cp-pin-deck", "cp-pin-btn", "cp-pin-state"):
        assert ident in body, f"{ident} missing from the site-wide card panel"
