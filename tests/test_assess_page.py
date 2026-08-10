"""The assessment as a readable page.

The numbers were only available as a plain-text download meant for pasting into a coaching
session. These check the HTML page renders the same analysis with real structure.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def client(tmp_path, collection_file, deck_file):
    """A Flask test client pointed at a throwaway deck + collection."""
    import shutil
    decks = tmp_path / "decks"
    decks.mkdir()
    shutil.copy(deck_file, decks / "testdeck.txt")
    os.environ["MTG_DECKS_DIR"] = str(decks)
    os.environ["MTG_COLLECTION"] = collection_file
    for mod in ("app",):
        sys.modules.pop(mod, None)
    import app
    app.app.config["TESTING"] = True
    return app.app.test_client()


def test_assess_page_renders(client):
    r = client.get("/deck/testdeck/assess")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for heading in ("Role balance", "Consistency", "Ownership"):
        assert heading in html


def test_assess_page_explains_bracket_is_not_power(client):
    """The single most misread number on the page."""
    html = client.get("/deck/testdeck/assess").get_data(as_text=True)
    assert "not a power score" in html.lower()


def test_assess_page_flags_roles_outside_the_template(client):
    """A deck with no removal must show an amber tile, not a bare number."""
    html = client.get("/deck/testdeck/assess").get_data(as_text=True)
    assert "tile-warn" in html
    assert "target" in html


def test_every_table_can_scroll(client):
    """Same rule as the dashboard — a wide table must not widen the page on mobile."""
    html = client.get("/deck/testdeck/assess").get_data(as_text=True)
    for m in re.finditer(r"<table", html):
        assert "tablewrap" in html[max(0, m.start() - 200):m.start()]


def test_text_export_still_works(client):
    """The .txt hand-off is a different job and must survive."""
    r = client.get("/deck/testdeck/assess.txt")
    assert r.status_code == 200
    assert "ASSESSMENT PACKET" in r.get_data(as_text=True)


def test_unknown_deck_is_404(client):
    assert client.get("/deck/nope/assess").status_code == 404


# --------------------------------------------------------------------------- #
# Goldfish Monte Carlo — page + packet, both through the shared cached helper
# --------------------------------------------------------------------------- #
def test_assess_page_shows_the_goldfish_section(client):
    html = client.get("/deck/testdeck/assess").get_data(as_text=True)
    assert "Goldfish simulation" in html
    assert "Keepable opener" in html
    assert "lands in play at the start of turn" in html      # the screw definition
    assert "Seeded Monte Carlo" in html                       # the assumptions footer


def test_assess_packet_carries_the_goldfish_block(client):
    text = client.get("/deck/testdeck/assess.txt?raw=1").get_data(as_text=True)
    assert "-- GOLDFISH SIMULATION (Monte Carlo, seeded) --" in text
    assert "keepable opener" in text
    assert "assumption:" in text
    # it lands AFTER the closed forms, which is the order the two engines read in
    assert text.index("-- GOLDFISH SIMULATION") > text.index("-- ROLE COUNTS")


def test_both_surfaces_render_when_the_simulation_is_unavailable(client, monkeypatch):
    """A degraded sim must cost a paragraph, not a 500."""
    import goldfish
    monkeypatch.setattr(goldfish, "sim_for_deck", lambda *a, **k: None)
    html = client.get("/deck/testdeck/assess").get_data(as_text=True)
    assert "Goldfish simulation" in html and "unavailable" in html
    text = client.get("/deck/testdeck/assess.txt?raw=1").get_data(as_text=True)
    assert "-- GOLDFISH SIMULATION (Monte Carlo, seeded) --" in text
    assert "unavailable" in text
