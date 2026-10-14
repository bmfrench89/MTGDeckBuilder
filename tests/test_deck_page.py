"""UX refresh Wave 1.2: the deck page on a phone (docs/spec-ux-refresh.md §4).

The 2026-10-14 audit measured 1.7–11.9 screens of scrolling to reach one card on a
phone. The tabs sat about two screens down, under ten tiles, and the Deck tab was
nothing but card art. These tests pin:
- the one-line glance that replaces the tiles on a phone;
- a decklist rendered as BOTH a text list and the image grid, with the same cards
  and the same panel hooks;
- a no-JavaScript fallback that is exactly the old grid;
- print still gets the whole grid;
- tap-to-zoom on both panels.
How the page behaves in a real browser is webapp/uat/flows.js F12.
"""
import os
import re

import build_dashboard as bd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _html(deck_file, collection_file, **kw):
    return bd.generate(deck_file, collection_file, title="T", commander="C", **kw)["dashboard"]


def test_every_card_is_both_a_tile_and_a_row_with_the_same_panel_key(deck_file, collection_file):
    html = _html(deck_file, collection_file, editable=True)
    tiles = re.findall(r"<figure class='mc' data-key='([^']+)'", html)
    rows = re.findall(r"<li class='dl-row' data-key='([^']+)'", html)
    assert tiles and sorted(tiles) == sorted(rows), "the two views list the same cards"
    panel = open(os.path.join(ROOT, "scripts", "assets", "card_panel.html"), encoding="utf-8").read()
    assert ".dl-row[data-key]" in panel, "a row opens the same card panel as a tile"


def test_without_javascript_the_page_is_the_old_grid(deck_file, collection_file):
    html = _html(deck_file, collection_file)
    assert "<div class='dl' data-view='grid'>" in html
    assert ".dl[data-view='grid'] .dl-list, .dl[data-view='list'] .cardgrid" in html
    # The view is chosen before first paint (no grid flash on a phone), then wired.
    assert "localStorage.getItem('mtg.deckview')" in html
    assert "matchMedia('(max-width: 640px)').matches)?'list':'grid'" in html
    assert "var KEY = 'mtg.deckview'" in html, "decklist.js is inlined: one self-contained file"
    assert '<link rel="stylesheet"' not in html


def test_a_row_is_a_labelled_button_with_a_decorative_thumbnail(deck_file, collection_file):
    html = _html(deck_file, collection_file)
    row = re.search(r"<li class='dl-row'[^>]*>.*?</li>", html).group(0)
    assert "tabindex='0'" in row and "role='button'" in row and "aria-label='" in row
    assert re.search(r"<img class='dl-thumb' loading='lazy' data-src='[^']+' data-name='[^']+' alt=''>", row)
    # The cost closes the row; nothing numeric sits before the name, where it would
    # read as a quantity.
    name_at = row.index("<span class='dl-name'>")
    assert "class='mv" not in row[:name_at]
    assert "<span class='dl-cost' title='Mana cost'><span class='pip" in row or "class='dl-mv'>MV" in row


def test_a_cost_is_pips_front_face_first():
    assert bd.cost_pips("{2}{W}{U}") == ("<span class='pip p-n'>2</span><span class='pip p-w'>W</span>"
                                         "<span class='pip p-u'>U</span>")
    assert bd.cost_pips("{1}{G} // {3}{G}{G}").count("pip p-") == 2, "the front face's cost"
    assert "p-r'>RG<" in bd.cost_pips("{R/G}") and bd.cost_pips("") == ""
    loader = open(os.path.join(ROOT, "scripts", "assets", "card_images.html"), encoding="utf-8").read()
    assert "getAttribute('data-name')||img.getAttribute('alt')" in loader, \
        "a decorative thumbnail still gets its image"


def test_sections_fold_and_the_filter_has_a_name(deck_file, collection_file):
    html = _html(deck_file, collection_file)
    assert "<button type='button' class='dl-tog' aria-expanded='true'>" in html
    assert "aria-label='Find a card in this deck'" in html
    assert "<div class='dl-views' role='group' aria-label='Show cards as'>" in html
    assert "<p class='dl-none muted' hidden>No card in this deck matches.</p>" in html


def test_paper_always_gets_the_whole_grid(deck_file, collection_file):
    html = _html(deck_file, collection_file)
    pr = html[html.index("@media print"):]
    assert ".dl .cardgrid {{ display:grid !important; }}".replace("{{", "{").replace("}}", "}") in pr
    assert ".dl-tools, .dl-list, .glance > summary" in pr


def test_the_glance_line_counts_like_the_meters():
    rep = {"total_cards": 100, "lands": 30, "categories": {"ramp": 10, "draw": 10, "removal": 9, "wipe": 2}}
    line = bd.glance_line(rep, {"bracket": 3, "speed": {"short": "T7"}})
    assert line.startswith("100 cards · Bracket 3 · T7 · ")
    assert "off target" in line, "30 lands sits below the land band"
    ranges = {k: (0, 99) for k in ("ramp", "draw", "removal", "wipe", "counter", "protection")}
    rep_ok = dict(rep, lands=37)
    assert bd.glance_line(rep_ok, None, ranges).endswith("every role in range")


def test_the_tiles_fold_under_the_glance_on_a_phone(deck_file, collection_file):
    html = _html(deck_file, collection_file)
    assert '<details class="glance" id="glance" open>' in html
    block = html[html.index('<details class="glance"'):html.index("</details>", html.index('<details class="glance"'))]
    assert '<div class="tiles">' in block, "the tiles live inside the fold"
    assert "<span class=\"glance-line\">" in block
    assert "getElementById('glance')" in html and "localStorage.getItem('mtg.glance')" in html
    assert "@media (min-width:641px) { .glance > summary { display:none; } }" in html


def test_the_tab_row_says_when_more_tabs_sit_past_its_edge(deck_file, collection_file):
    html = _html(deck_file, collection_file)
    assert "nav.classList.toggle('more-r'" in html and ".tabs.more-r" in html


def test_both_panels_open_the_card_full_size():
    deck = open(os.path.join(ROOT, "scripts", "assets", "card_panel.html"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "webapp", "static", "cardpanel.js"), encoding="utf-8").read()
    for src, cls in ((deck, "cm-zoom"), (app, "cp-zoom")):
        assert cls in src and "full size" in src
        assert re.search(r"e\.key\s*===?\s*'Escape'", src), "Escape closes the zoom"
