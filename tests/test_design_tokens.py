"""The web app and the generated dashboards must share ONE visual system.

They're built completely differently — the app links stylesheets, a dashboard inlines
everything so it works offline — so nothing structural stops them drifting apart. These
tests are that guard.
"""
import os
import re

import build_dashboard as bd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS = os.path.join(ROOT, "scripts", "assets", "tokens.css")
APP_CSS = os.path.join(ROOT, "webapp", "static", "app.css")


def _read(p):
    return open(p, encoding="utf-8").read()


def test_tokens_file_defines_the_scales():
    css = _read(TOKENS)
    for tok in ("--fs-2xs", "--fs-md", "--fs-3xl", "--sp-1", "--sp-8",
                "--r-pill", "--el-1", "--line"):
        assert tok in css, f"{tok} missing from tokens.css"


def test_tokens_file_carries_no_colours_or_fonts():
    """Colour + font are the only things a surface may legitimately differ on, so the
    shared file must not fix them — otherwise the deck themes couldn't theme."""
    css = _read(TOKENS)
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)          # ignore commentary
    assert "#" not in body, "tokens.css should not hardcode a hex colour"
    assert "--font-display:" not in body
    assert "Oswald" not in body and "Rajdhani" not in body


def test_app_css_does_not_redefine_the_scale():
    """app.css supplies the web THEME; redefining --fs-*/--sp-* there would silently
    desync it from the dashboards."""
    css = _read(APP_CSS)
    for tok in ("--fs-md:", "--sp-4:", "--r-lg:", "--el-1:"):
        assert tok not in css, f"{tok} is redefined in app.css — it belongs to tokens.css"


def test_app_css_supplies_the_theme():
    css = _read(APP_CSS)
    for tok in ("--accent:", "--panel:", "--font-display:", "--font-body:"):
        assert tok in css


def test_every_dashboard_theme_inlines_the_tokens(deck_file, collection_file):
    """A dashboard is a single self-contained file, so the tokens must be inlined —
    and every theme must get them."""
    for theme in ("default", "yshtola", "cloud", "rakdos", "spider"):
        html = bd.generate(deck_file, collection_file, title="T", commander="C",
                           theme=theme)["dashboard"]
        for tok in ("--fs-2xl", "--sp-5", "--r-lg", "--el-1"):
            assert tok in html, f"{tok} missing from the {theme} dashboard"
        assert '<link rel="stylesheet"' not in html, "dashboard must stay self-contained"


def test_dashboard_and_app_agree_on_a_scale_value(deck_file, collection_file):
    """The actual regression: the same token must resolve to the same value on both."""
    tokens = _read(TOKENS)
    want = re.search(r"--fs-2xl:\s*([0-9.]+rem)", tokens).group(1)
    html = bd.generate(deck_file, collection_file, title="T", commander="C")["dashboard"]
    got = re.search(r"--fs-2xl:\s*([0-9.]+rem)", html).group(1)
    assert got == want


def test_dashboard_css_uses_tokens_not_ad_hoc_sizes(deck_file, collection_file):
    """The dashboard CSS had 18 hand-picked font sizes; they should all be tokens now."""
    html = bd.generate(deck_file, collection_file, title="T", commander="C")["dashboard"]
    style = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    ad_hoc = set(re.findall(r"font-size:\s*((?!var)[0-9.]+r?em)", style))
    assert not ad_hoc, f"ad-hoc font sizes left in the dashboard: {sorted(ad_hoc)}"


def test_no_token_lands_in_a_multi_value_shorthand(deck_file, collection_file):
    """Regression: a blanket `20px -> var(--r-pill)` substitution hit the FIRST value of
    `border-radius:20px 20px 0 0`, giving the card panel a 999px corner — a giant white
    swoop across the sheet. A radius token must never appear beside a raw px value."""
    import glob
    sources = glob.glob(os.path.join(ROOT, "scripts", "assets", "*.css"))
    sources += glob.glob(os.path.join(ROOT, "webapp", "static", "*.css"))
    html = bd.generate(deck_file, collection_file, title="T", commander="C")["dashboard"]
    bad = []
    for text, where in [(_read(f), os.path.basename(f)) for f in sources] + [(html, "dashboard")]:
        for decl in re.findall(r"border-radius:[^;}]+", text):
            if "var(--r-" in decl and re.search(r"\d+px", decl):
                bad.append(f"{where}: {decl.strip()}")
    assert not bad, "radius token mixed with raw px in a shorthand: " + "; ".join(bad)


def test_no_absurd_radius_on_a_wide_surface(deck_file, collection_file):
    """--r-pill is 999px; it belongs on chips and buttons, never on a panel or card."""
    html = bd.generate(deck_file, collection_file, title="T", commander="C")["dashboard"]
    style = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    for sel in (".cm-sheet", ".tile", "section"):
        m = re.search(re.escape(sel) + r"\s*\{[^}]*border-radius:\s*var\(--r-pill\)", style)
        assert not m, f"{sel} must not use the pill radius"


def test_every_data_table_can_scroll(deck_file, collection_file):
    """Regression: two tables were emitted outside .tablewrap, so a wide table pushed the
    whole page sideways on a phone instead of scrolling inside its own box."""
    html = bd.generate(deck_file, collection_file, title="T", commander="C")["dashboard"]
    # every <table class='data'...> must be immediately preceded by a tablewrap div
    for m in re.finditer(r"<table class=['\"]data", html):
        preceding = html[max(0, m.start() - 120):m.start()]
        assert "tablewrap" in preceding, (
            "a data table is not inside .tablewrap — it will overflow the page on mobile")
