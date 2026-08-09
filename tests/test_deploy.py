"""The hosted deploy — what has to hold for one URL to serve every device.

Two things silently break a WSGI host deploy, and neither shows up when you run the
app locally: the entry point the host imports, and a /static/ file mapping that
shadows the shared design tokens. These lock both down.

Hermetic like the rest of the suite: DECKS_DIR is redirected into tmp_path before any
route that would otherwise read the player's real data/decks/.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _client(tmp_path, monkeypatch):
    """A test client for the app exactly as the host imports it."""
    import app
    import pa_wsgi
    monkeypatch.setattr(app, "DECKS_DIR", str(tmp_path))
    return pa_wsgi.application.test_client()


def test_wsgi_entry_exposes_a_flask_application():
    """The host imports the name `application` — that name is the contract."""
    import pa_wsgi
    assert hasattr(pa_wsgi, "application"), "the host imports `application`; don't rename it"
    assert callable(pa_wsgi.application)
    assert hasattr(pa_wsgi.application, "wsgi_app"), "should be the Flask app object itself"


def test_wsgi_entry_is_self_locating():
    """It must work from any checkout path, so the repo carries no user-specific path.
    The username belongs only in /var/www/..., which is not in this repo."""
    src = open(os.path.join(ROOT, "webapp", "pa_wsgi.py"), encoding="utf-8").read()
    assert "/home/" not in src.split('"""')[-1], "pa_wsgi.py must not hardcode a home directory"


def test_wsgi_entry_boots_and_serves_health_on_defaults(tmp_path, monkeypatch):
    """A fresh host has no MTG_* env vars set. Booting on defaults alone is what makes
    the deploy clone-and-go rather than a configuration exercise."""
    for var in ("MTG_COLLECTION", "MTG_DECKS_DIR", "MTG_HOST", "MTG_PORT"):
        monkeypatch.delenv(var, raising=False)
    r = _client(tmp_path, monkeypatch).get("/health")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_tokens_css_is_served_by_a_route_not_a_file_in_static(tmp_path, monkeypatch):
    """THE DEPLOY TRAP. /static/tokens.css is a Flask route serving
    scripts/assets/tokens.css. Mapping /static/ -> webapp/static/ on the host (the
    standard "serve static files directly" optimization) shadows that route and 404s
    the shared scales on every page. Keeping the file OUT of webapp/static is what
    keeps that mistake loud instead of silent."""
    stray = os.path.join(ROOT, "webapp", "static", "tokens.css")
    assert not os.path.exists(stray), (
        "a copy of tokens.css in webapp/static would drift from scripts/assets/tokens.css — "
        "the app serves the canonical file by route")
    r = _client(tmp_path, monkeypatch).get("/static/tokens.css")
    assert r.status_code == 200, "the tokens route must win over Flask's static handler"
    assert "--fs-md" in r.get_data(as_text=True)


def test_service_worker_is_actually_served_from_the_app_root(tmp_path, monkeypatch):
    """test_pwa.py asserts the route exists in the source; this proves it answers.
    Scope rule: at /static/sw.js the worker could never control the app."""
    r = _client(tmp_path, monkeypatch).get("/sw.js")
    assert r.status_code == 200
    assert "SHELL" in r.get_data(as_text=True)
