"""The "Arcane Ledger" UI overhaul (2026-10): the guards that keep its honesty rules.

The redesign is presentation, but three of its pieces make CLAIMS and are tested as
such: a role meter says a count is "in range" / "N short" against a template band (it
must be the deck's archetype-widened band, the one the optimizer uses — not a second
copy that drifts); a status colour must never be the only signal (every meter carries
the word); and the deck page's app bar must appear only where a server exists to
answer its links (never in a CLI / downloaded dashboard).

Hermetic like the rest of the suite: decks and collection live in tmp_path.
"""
import re

import pytest

import build_dashboard as bd
import deckcore

DECK = """\
# Title: Ledger Deck
# Commander: Test Commander
# Colors: W U

# --- Commander ---
1 Test Commander

# --- Artifacts ---
1 Sol Ring

# --- Basics ---
21 Plains
10 Island
"""


@pytest.fixture
def env(tmp_path, monkeypatch, collection_file):
    import app as appmod
    import enrich_bg
    import sync
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "ledger.txt").write_text(DECK, encoding="utf-8")
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", collection_file)
    monkeypatch.setattr(appmod, "PASSWORD", None)
    monkeypatch.setattr(deckcore, "PINS", str(tmp_path / "pins.csv"))
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    monkeypatch.setattr(enrich_bg, "start", lambda *a, **k: "enrichment started")
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


# --------------------------------------------------------------------------- #
# role meters (dashboard)
# --------------------------------------------------------------------------- #
def _rep(lands=35, **cats):
    base = {"ramp": 9, "draw": 7, "removal": 8, "wipe": 2}
    base.update(cats)
    return {"lands": lands, "categories": base}


def test_meter_states_carry_a_word_not_just_a_colour():
    html = bd.role_meters_html(_rep(), deckcore.role_ranges())
    lo, hi = deckcore.LAND_RANGE
    # 35 lands under the land band, 7 draw under 8-12: both say how far short.
    assert f"{lo - 35} short" in html
    assert "1 short" in html
    assert "in range" in html
    for st in re.findall(r"class='rm-st rm-(\w+)'", html):
        assert st in ("in", "short", "over")


def test_meter_reports_over_the_band():
    html = bd.role_meters_html(_rep(ramp=20), deckcore.role_ranges())
    assert "7 over" in html                              # default ramp band is 9-13


def test_meter_uses_the_archetype_widened_band():
    """A landfall deck's ramp ceiling is 19 (deckcore._ARCHETYPE_ROLE_RANGE). The
    meter must read the same widened band the optimizer accepts swaps against —
    otherwise the dashboard calls a ratified deck '6 over'."""
    blind = bd.role_meters_html(_rep(ramp=19), deckcore.role_ranges())
    widened = bd.role_meters_html(_rep(ramp=19), deckcore.role_ranges(["landfall"]))
    assert "6 over" in blind
    assert "6 over" not in widened and "Target 9–19" in widened


def test_dashboard_shows_meters_not_bare_role_tiles(deck_file, collection_file):
    html = bd.generate(deck_file, collection_file, title="T", commander="C",
                       sim=None)["dashboard"]
    assert "class='rmeters'" in html
    assert "Board wipes" in html
    # the old bare number tiles had no target; they must not come back beside the meters
    assert "<div class='tile-label'>Ramp</div>" not in html


# --------------------------------------------------------------------------- #
# app bar: app surface only
# --------------------------------------------------------------------------- #
def test_app_bar_only_on_the_editable_surface(deck_file, collection_file):
    cli = bd.generate(deck_file, collection_file, title="T", commander="C",
                      sim=None)["dashboard"]
    app = bd.generate(deck_file, collection_file, title="T", commander="C",
                      sim=None, editable=True)["dashboard"]
    assert "class='appbar'" not in cli, "a downloaded dashboard has no server to link to"
    assert "class='appbar'" in app and "All decks" in app


def test_app_bar_hides_in_print(deck_file, collection_file):
    from conftest import print_block
    html = bd.generate(deck_file, collection_file, title="T", commander="C",
                       sim=None, editable=True)["dashboard"]
    assert ".appbar" in print_block(html)


def test_app_bar_links_resolve(env):
    """Every href in the app bar must be a real route — a renamed route would leave a
    dead button on every deck page with nothing else noticing."""
    html = env.get("/deck/ledger").get_data(as_text=True)
    bar = re.search(r"<div class='appbar'>.*?</details></div></div>", html, re.S).group(0)
    hrefs = set(re.findall(r"href='([^']+)'", bar))
    assert hrefs, "app bar rendered no links"
    for h in hrefs:
        r = env.get(h)
        assert r.status_code == 200, f"{h} -> {r.status_code}"


# --------------------------------------------------------------------------- #
# decks home
# --------------------------------------------------------------------------- #
def test_deck_card_shows_role_meters_with_words(env):
    html = env.get("/").get_data(as_text=True)
    assert 'class="deckcard"' in html
    # 31 basics -> under the land band; the status is spelled out for screen readers
    lo, hi = deckcore.LAND_RANGE
    assert f"Lands 31 — target {lo}–{hi}, {lo - 31} short" in html
    assert "dot st-short" in html


def test_deck_card_shows_identity_in_wubrg_order(env):
    html = env.get("/").get_data(as_text=True)
    assert "Colour identity: white, blue" in html


def test_secondary_actions_live_in_the_overflow_menu(env):
    html = env.get("/").get_data(as_text=True)
    menu = re.search(r'<details class="menu">.*?</details>', html, re.S).group(0)
    for label in ("Table card", "Assess", "Mulligan practice", "Export .txt", "Delete"):
        assert label in menu


def test_shell_nav_marks_the_current_page(env):
    html = env.get("/wishlist").get_data(as_text=True)
    assert re.search(r'class="tab on"[^>]*aria-current="page"', html)
