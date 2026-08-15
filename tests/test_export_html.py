"""`/export/deck/<stem>.html` — the deck dashboard as a downloadable report.

The feature is "a file you can keep", so these tests pin the three things that make a
downloaded file different from a rendered page: it must arrive as an *attachment*, it
must be genuinely **self-contained** (a file in Downloads has no server behind it, so a
single `/static/` reference would render it broken offline), and it must carry **no dead
controls** — Add/Remove/Replace and the bracket form all POST to routes that do not
exist once the file leaves the app.

The sibling `.txt` export is re-checked here on purpose: the two routes differ only by
their literal suffix, so a shadowing mistake would silently break the older one.

Hermetic like the rest of the suite — DECKS_DIR/COLLECTION redirected into tmp_path.
"""
import pytest

import app as appmod
import sync


@pytest.fixture
def client(tmp_path, monkeypatch, collection_file):
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
    # The auto-sync before_request shells out to git on the REAL repo if enabled.
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def test_the_report_downloads_as_an_html_attachment(client):
    r = client.get("/export/deck/d.html")
    assert r.status_code == 200
    assert "text/html" in r.headers["Content-Type"]
    cd = r.headers.get("Content-Disposition", "")
    assert "attachment" in cd and "d.html" in cd, \
        "the point of the route is a file you keep, not a page you view"


def test_the_downloaded_report_is_self_contained(client):
    """A file in ~/Downloads has no server behind it: every asset must be inlined."""
    body = client.get("/export/deck/d.html").get_data(as_text=True)
    assert "Test Deck" in body and "Sol Ring" in body
    assert "--sp-4" in body, "tokens.css must be inlined, not linked"
    assert "<script src=" not in body
    # Attribute syntax only — tokens.css names its own /static/ path in a comment,
    # which is documentation, not a fetch.
    for ref in ('="/static/', "='/static/"):
        assert ref not in body, \
            "a /static/ reference would 404 the moment the file leaves the app"


def test_the_downloaded_report_has_no_dead_controls(client):
    """Mirrors test_dashboard's editable-surface rule: no server, no edit buttons."""
    body = client.get("/export/deck/d.html").get_data(as_text=True)
    assert 'id="ac-open"' not in body, "the add-card picker would post into the void"
    assert "class='bracketform'" not in body and 'class="bracketform"' not in body


def test_raw_renders_inline_instead_of_downloading(client):
    """Parity with every sibling export, which all take ?raw."""
    r = client.get("/export/deck/d.html?raw=1")
    assert r.status_code == 200
    assert "attachment" not in r.headers.get("Content-Disposition", "")


def test_an_unknown_deck_is_a_404(client):
    assert client.get("/export/deck/nope.html").status_code == 404


def test_the_txt_sibling_still_works(client):
    """The two export routes differ only by literal suffix — neither may shadow
    the other, and `.txt` must not start serving a dashboard."""
    r = client.get("/export/deck/d.txt")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Sol Ring" in body
    assert "<html" not in body.lower(), "the .txt export must stay plain text"


def test_the_report_is_behind_the_auth_gate(client, monkeypatch):
    """A new route is protected by NOT being in _PUBLIC_ENDPOINTS. This is the
    test that notices if someone ever adds it there."""
    monkeypatch.setattr(appmod, "PASSWORD", "correct horse")
    r = client.get("/export/deck/d.html")
    assert r.status_code == 302 and "/login" in r.headers["Location"], \
        "the deck report is collection-derived data — it must never be anonymous"
    assert "export_deck_html" not in appmod._PUBLIC_ENDPOINTS
