"""UX refresh Wave 1.5: the accessibility batch (docs/spec-ux-refresh.md §4).

The 2026-10-14 audit (axe-core plus the sweep) found:
- controls with no accessible name;
- card names a keyboard could never reach;
- a modal panel that left focus behind it;
- links that differed from the text around them only by colour;
- no skip link and no main landmark on the dashboard;
- white native controls on the dark pages;
- 11 px text, 35–40 px tap targets, and inputs that make iOS zoom the page;
- a Pins table whose Apply buttons a phone reached only by scrolling sideways.

Each fix is pinned here. These are static checks of markup and CSS. The sweep
(webapp/uat/sweep.js) measures the rendered result at four widths.
"""
import glob
import os
import re

import build_dashboard as bd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def _unnamed_controls(text):
    """Form controls with no accessible name: no aria-label(ledby), no <label for>,
    not wrapped in a <label>. Hidden inputs and buttons are named by other means."""
    bad = []
    for m in re.finditer(r"<(input|select|textarea)\b([^>]*)>", text):
        tag, attrs = m.group(1), m.group(2)
        t = re.search(r"""type=["']?([\w-]+)""", attrs)
        if tag == "input" and t and t.group(1).lower() in (
                "hidden", "submit", "button", "image", "reset"):
            continue
        if re.search(r"aria-label(ledby)?=", attrs):
            continue
        idm = re.search(r"""\bid=["']([^"']+)""", attrs)
        if idm and re.search(r"""<label[^>]*for=["']%s["']""" % re.escape(idm.group(1)), text):
            continue
        before = text[:m.start()]
        if before.rfind("<label") > before.rfind("</label>"):
            continue
        bad.append(f"<{tag}{attrs[:80]}>")
    return bad


def test_every_form_control_has_a_name():
    files = sorted(glob.glob(os.path.join(ROOT, "webapp", "templates", "*.html")))
    files += sorted(glob.glob(os.path.join(ROOT, "scripts", "assets", "*.html")))
    found = {os.path.relpath(p, ROOT): _unnamed_controls(open(p, encoding="utf-8").read())
             for p in files}
    assert not {k: v for k, v in found.items() if v}, \
        "a placeholder is not a label: give these an aria-label or a <label for>"


def test_the_scan_catches_an_unnamed_control():
    assert _unnamed_controls('<input type="text" placeholder="Card name">')
    assert not _unnamed_controls('<label>Qty <input type="number"></label>')
    assert not _unnamed_controls('<label for="q">Q</label><input id="q">')


def test_touch_targets_and_type_floor_are_tokens():
    tokens = _read("scripts", "assets", "tokens.css")
    assert re.search(r"--target:\s*44px", tokens)
    size = float(re.search(r"--fs-2xs:\s*([\d.]+)rem", tokens).group(1))
    assert size >= 0.75, "the smallest type step stays at 12 px or more"
    css = _read("webapp", "static", "app.css")
    for rule in (r"\.btn\.sm \{[^}]*min-height: var\(--target\)",
                 r"\.thchip \{[^}]*min-height: var\(--target\)",
                 r"input, textarea, select \{[^}]*min-height: var\(--target\)",
                 r"\.colorbtn \{[^}]*width:var\(--target\)"):
        assert re.search(rule, css), rule


def test_fields_never_make_ios_zoom_and_controls_render_dark():
    css = _read("webapp", "static", "app.css")
    coarse = re.search(r"@media \(pointer: coarse\) \{([^}]*\})", css)
    assert coarse and "font-size: 16px" in coarse.group(1)
    root = re.search(r":root \{([^}]*)\}", css).group(1)
    assert "color-scheme: dark" in root


def test_links_in_text_are_underlined_not_colour_only():
    css = _read("webapp", "static", "app.css")
    assert re.search(r":where\(p, li, td[^)]*\) a[^{]*\{\s*text-decoration: underline", css)


def test_a_skip_link_leads_to_the_main_landmark():
    base = _read("webapp", "templates", "base.html")
    assert '<a class="skiplink" href="#main">' in base
    assert '<main class="wrap" id="main"' in base
    assert base.index('class="skiplink"') < base.index('<nav class="rail"'), \
        "the skip link is the first thing a keyboard reaches"


def test_card_names_are_keyboard_reachable_and_focus_comes_back():
    js = _read("webapp", "static", "cardpanel.js")
    assert "setAttribute('tabindex', '0')" in js and "setAttribute('role', 'button')" in js
    assert "MutationObserver" in js, "lists drawn later by script get tab stops too"
    for src in (js, _read("scripts", "assets", "card_panel.html")):
        assert re.search(r"opener\s*=\s*document\.activeElement", src)
        assert re.search(r"opener\.focus\(", src), "focus returns to the card that opened it"


def test_the_pins_table_stacks_on_a_phone():
    pins = _read("webapp", "templates", "pins.html")
    assert '<table class="data stackable">' in pins
    for label in ("Reserved for", "Owned", "Also in", "Move / release"):
        assert f'data-label="{label}"' in pins
    css = _read("webapp", "static", "app.css")
    assert "table.stackable td[data-label]::before" in css


def test_the_dashboard_has_a_landmark_dark_controls_and_full_size_targets(
        deck_file, collection_file):
    html = bd.generate(deck_file, collection_file, title="T", commander="C",
                       editable=True)["dashboard"]
    assert 'class="wrap" role="main" id="main"' in html
    assert "color-scheme:dark" in html
    assert re.search(r"@media \(pointer:coarse\) \{\s*input, select, textarea \{ font-size:16px", html)
    assert re.search(r"\.cm-close \{[^}]*min-width:var\(--target\)", html)
    assert re.search(r"\.printbtn \{ min-height:var\(--target\)", html)
