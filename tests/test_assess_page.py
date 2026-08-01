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
