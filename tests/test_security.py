"""Hardening baseline — headers, cookie flags, upload cap.

These lock in the response-level defenses so a refactor can't silently drop them:
cross-site POSTs must not carry the session (SameSite), the cookie must be
script-inaccessible (HttpOnly) and HTTPS-only on a detected HTTPS host, responses
must refuse MIME sniffing and framing, and a request body can't be unbounded.
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
    return appmod.app.test_client()


def test_security_headers_on_every_response(client):
    for path in ("/", "/health", "/static/app.css"):
        h = client.get(path).headers
        assert h.get("X-Content-Type-Options") == "nosniff", path
        assert h.get("X-Frame-Options") == "DENY", path
        assert h.get("Referrer-Policy") == "same-origin", path


def test_session_cookie_flags():
    assert appmod.app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert appmod.app.config["SESSION_COOKIE_SAMESITE"] == "Lax", \
        "Lax is the CSRF brake: cross-site form POSTs carry no session cookie"


def test_secure_cookie_follows_https_detection(monkeypatch):
    """Secure-only when the host is known-HTTPS (PythonAnywhere) or declared so;
    NOT unconditional — plain-http LAN dev would silently never send the cookie."""
    for var in ("PYTHONANYWHERE_SITE", "PYTHONANYWHERE_DOMAIN", "MTG_COOKIE_SECURE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(appmod, "PASSWORD", "pw")
    assert appmod._cookie_secure() is False, "local http dev: flag off"
    monkeypatch.setenv("PYTHONANYWHERE_SITE", "www.pythonanywhere.com")
    assert appmod._cookie_secure() is True, "hosted (always HTTPS): flag on"
    monkeypatch.delenv("PYTHONANYWHERE_SITE")
    monkeypatch.setenv("MTG_COOKIE_SECURE", "1")
    assert appmod._cookie_secure() is True, "any other HTTPS deploy can opt in"
    monkeypatch.setattr(appmod, "PASSWORD", None)
    assert appmod._cookie_secure() is False, "no gate, no session cookie to protect"


def test_request_bodies_are_capped():
    cap = appmod.app.config["MAX_CONTENT_LENGTH"]
    assert cap == 32 * 1024 * 1024, \
        "collection CSVs are a few MB; an uncapped body lets one request fill the disk"


def test_debug_mode_is_off_in_source():
    """The Werkzeug debugger is remote code execution. debug must be explicit False."""
    src = open(os.path.join(ROOT, "webapp", "app.py"), encoding="utf-8").read()
    assert "debug=False" in src and "debug=True" not in src
