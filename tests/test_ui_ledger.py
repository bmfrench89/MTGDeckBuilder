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


# --------------------------------------------------------------------------- #
# card panel: a drawer on wide screens, a bottom sheet on phones — both surfaces
# --------------------------------------------------------------------------- #
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


@pytest.mark.parametrize("path,sheet", [
    (("scripts", "assets", "card_panel.css"), ".cm-sheet"),
    (("webapp", "static", "cardpanel.css"), ".cp-sheet"),
])
def test_card_panel_is_a_drawer_on_wide_screens_only(path, sheet):
    """Both panels (the dashboard's inlined one and the app's) must slide in from the
    right on a wide screen and keep the bottom sheet below that breakpoint. A drawer
    rule outside the media query would put a 480px side panel on a 390px phone."""
    css = _read(*path)
    m = re.search(r"@media\s*\(min-width:\s*900px\)\s*\{(.*)\}\s*$", css, re.S)
    assert m, "no wide-screen drawer block"
    wide = m.group(1)
    assert "justify-content:flex-end" in wide.replace(" ", "")
    assert "translateX(100%)" in wide
    outside = css[:m.start()]
    assert "translateY(100%)" in outside, "phones must keep the bottom sheet"
    assert "translateX" not in outside


def test_dashboard_panel_buttons_lost_the_old_cyan_fallback(deck_file, collection_file):
    html = bd.generate(deck_file, collection_file, title="T", commander="C",
                       sim=None, editable=True)["dashboard"]
    # the default (Ledger) theme never names the old cyan; it reached the page only
    # through the edit buttons' hardcoded var() fallback
    assert "#5BE0D4" not in html


# --------------------------------------------------------------------------- #
# app icon: the SVG and the PNG generator draw the same mark
# --------------------------------------------------------------------------- #
def test_icon_svg_and_png_generator_share_the_geometry():
    import make_icons
    svg = _read("webapp", "static", "icon.svg")
    for r, _colour in make_icons.DIAMONDS:
        top = 256 - int(r)
        assert f"M256 {top} " in svg, f"diamond r={r:g} missing from icon.svg"
    assert "#F2B544" in svg and "#0F1115" in svg
    assert make_icons.AMBER == (0xF2, 0xB5, 0x44) and make_icons.BG == (0x0F, 0x11, 0x15)


def test_icon_render_puts_amber_at_the_centre_and_ink_in_the_ring():
    import make_icons
    size = 32
    rgb = make_icons.render(size)
    px = lambda x, y: tuple(rgb[(y * size + x) * 3:(y * size + x) * 3 + 3])
    assert px(16, 16) == make_icons.AMBER              # the centre gem
    assert px(16, 16 - 4) == make_icons.BG             # inside the ink diamond
    assert px(16, 16 - 8) == make_icons.AMBER          # the outer gem
