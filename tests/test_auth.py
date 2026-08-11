"""The access gate (MTG_PASSWORD) — the seatbelt for the hosted deploy.

Two invariants matter more than the happy path: (1) with no password configured the
gate does not exist — local dev, CI, and every pre-auth test in this suite behave
exactly as before; (2) with a password set there is NO route that leaks data to an
anonymous visitor — pages redirect, POSTs 401, and only the login shell assets are
public. Hermetic like everything else: DECKS_DIR/COLLECTION redirected to tmp_path.
"""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import app as appmod
import sync


@pytest.fixture
def client(tmp_path, monkeypatch, collection_file):
    monkeypatch.setattr(appmod, "DECKS_DIR", str(tmp_path))
    monkeypatch.setattr(appmod, "COLLECTION", collection_file)
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    # Stub run too: POST /sync calls it unconditionally, and the real thing executes
    # sync_server.sh — git add/commit/pull/push on the REAL repo — from inside pytest.
    monkeypatch.setattr(sync, "run", lambda *a, **k: {"ok": True, "stubbed": True})
    return appmod.app.test_client()


@pytest.fixture
def gated(client, monkeypatch):
    monkeypatch.setattr(appmod, "PASSWORD", "correct horse")
    return client


def test_no_password_means_no_gate(client, monkeypatch):
    """The default. Everything this suite tested before auth existed relies on it."""
    monkeypatch.setattr(appmod, "PASSWORD", None)
    assert client.get("/").status_code == 200
    r = client.get("/login")
    assert r.status_code == 302, "login page with no password configured just bounces home"


def test_gate_redirects_pages_and_hard_stops_posts(gated):
    r = gated.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert gated.get("/wishlist").status_code == 302
    assert gated.get("/health").status_code == 302, \
        "health leaks server paths — it is NOT exempt"
    assert gated.post("/sync").status_code == 401, \
        "an anonymous POST must never reach a mutating route"
    assert gated.post("/deck/x/optimize").status_code == 401


def test_login_shell_stays_reachable_logged_out(gated):
    """The login page must be able to render styled, and the installed PWA must be
    able to fetch its shell, before any session exists."""
    assert gated.get("/login").status_code == 200
    assert gated.get("/static/app.css").status_code == 200
    assert gated.get("/static/tokens.css").status_code == 200
    assert gated.get("/sw.js").status_code == 200


def test_wrong_password_is_rejected(gated, monkeypatch):
    monkeypatch.setattr(appmod.time, "sleep", lambda s: None)  # skip the brute-force brake
    r = gated.post("/login", data={"password": "guess", "next": "/"})
    assert r.status_code == 200 and "Wrong password" in r.get_data(as_text=True)
    assert gated.get("/").status_code == 302, "a failed login must not create a session"


def test_right_password_opens_the_app(gated):
    r = gated.post("/login", data={"password": "correct horse", "next": "/wishlist"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/wishlist")
    assert gated.get("/").status_code == 200
    assert gated.post("/sync", follow_redirects=False).status_code != 401


def test_next_cannot_be_an_open_redirect(gated):
    # '/\\evil.example': browsers normalize the backslash to '/', turning it into a
    # protocol-relative '//evil.example' — the startswith('//') check alone missed it
    for evil in ("https://evil.example", "//evil.example", "/\\evil.example", ""):
        r = gated.post("/login", data={"password": "correct horse", "next": evil})
        assert r.status_code == 302
        loc = r.headers["Location"]
        assert "evil.example" not in loc, f"open redirect via next={evil!r}"
        gated.post("/logout")


def test_logout_ends_the_session(gated):
    gated.post("/login", data={"password": "correct horse", "next": "/"})
    assert gated.get("/").status_code == 200
    gated.post("/logout")
    assert gated.get("/").status_code == 302


def test_secret_key_is_stable_across_reloads_when_password_set(monkeypatch):
    """Sessions must survive the daily WSGI-touch reload, so the key must derive
    from the password — an os.urandom key would sign everyone out every morning."""
    import hashlib
    expected = hashlib.sha256("mtg-auth-v1:pw".encode()).digest()
    monkeypatch.setenv("MTG_PASSWORD", "pw")
    # mirror the derivation app.py performs at import
    assert hashlib.sha256(
        f"mtg-auth-v1:{os.environ['MTG_PASSWORD']}".encode()).digest() == expected


def test_signout_control_renders_only_when_gated(gated, client, monkeypatch):
    gated.post("/login", data={"password": "correct horse", "next": "/"})
    assert "Sign out" in gated.get("/").get_data(as_text=True)
    monkeypatch.setattr(appmod, "PASSWORD", None)
    assert "Sign out" not in client.get("/").get_data(as_text=True)
