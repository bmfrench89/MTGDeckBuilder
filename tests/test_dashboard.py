"""Dashboard rendering. These exist mainly as the safety net for refactoring
build_dashboard.py — the rendered HTML must stay self-contained and keep the card panel,
the editable controls, and the image loader intact."""
import build_dashboard as bd


def _html(deck_file, collection_file, **kw):
    return bd.generate(deck_file, collection_file, title="Test Deck",
                       commander="Test Commander", **kw)["dashboard"]


def test_dashboard_renders_and_is_self_contained(deck_file, collection_file):
    html = _html(deck_file, collection_file)
    assert html.lstrip().lower().startswith("<!doctype html")
    assert "</html>" in html
    # no external stylesheet/script other than the Google-fonts link the themes use
    assert "<script src=" not in html


def test_dashboard_includes_the_card_panel(deck_file, collection_file):
    html = _html(deck_file, collection_file)
    for marker in ('id="cardmodal"', 'id="cm-name"', 'id="cm-fit"', 'id="cm-oracle"'):
        assert marker in html


def test_dashboard_lists_the_deck_cards(deck_file, collection_file):
    html = _html(deck_file, collection_file)
    assert "Sol Ring" in html and "Arcane Signet" in html


def test_editing_is_off_by_default(deck_file, collection_file):
    """CLI-generated files have no backend to POST to, so editing must be disabled."""
    assert "var EDITABLE=false" in _html(deck_file, collection_file)


def test_editable_dashboard_exposes_the_edit_controls(deck_file, collection_file):
    html = _html(deck_file, collection_file, editable=True)
    assert "var EDITABLE=true" in html
    for marker in ('id="cm-editwrap"', 'id="cm-remove"', 'id="cm-search"',
                   "/api/collection/search"):
        assert marker in html


def test_image_loader_uses_the_batch_endpoint(deck_file, collection_file):
    """Regression: images must batch-resolve via /cards/collection, never fire one
    rate-limited /cards/named request per card (see docs/card-images.md)."""
    html = _html(deck_file, collection_file)
    assert "api.scryfall.com/cards/collection" in html


def test_generate_returns_report_and_assessment(deck_file, collection_file):
    res = bd.generate(deck_file, collection_file, title="T", commander="Test Commander")
    assert "report" in res and res["report"]["total_cards"] > 0
    assert "dashboard" in res


def test_visual_gallery_is_optional(deck_file, collection_file):
    assert bd.generate(deck_file, collection_file, title="T", commander="C")["visual"] is None
    assert bd.generate(deck_file, collection_file, title="T", commander="C",
                       want_visual=True)["visual"] is not None


# --------------------------------------------------------------------------- #
# Subtabs — the deck page is regrouped into tabs, and the rule is that nothing
# is LOST by the regrouping: hidden panels stay in the DOM (the card panel needs
# its targets) and printing restores every section.
# --------------------------------------------------------------------------- #
def test_tabs_render_with_one_default_and_matching_panels(deck_file, collection_file):
    import re
    html = _html(deck_file, collection_file)
    ids = set(re.findall(r"id='tab-(\w+)'", html))
    panels = set(re.findall(r"<div class='tabpanel' data-tab='(\w+)'", html))
    assert ids, "no tabs rendered"
    assert ids == panels, "every tab input needs exactly one panel and vice versa"
    assert html.count("class='tabinput' checked") == 1, "exactly one tab starts open"
    assert "<nav class='tabs'" in html


def test_tabs_do_not_drop_any_section(deck_file, collection_file):
    """The regrouping is presentation only — every heading that rendered before a
    tab existed must still be in the document."""
    import re
    html = _html(deck_file, collection_file)
    headings = set(re.findall(r"<h2>([^<]+)</h2>", html))
    for expected in ("Decklist by Section", "Ownership", "Mana Curve (MV Spread)"):
        assert expected in headings


def test_hidden_tabs_keep_their_content_in_the_dom(deck_file, collection_file):
    """Hidden, not omitted: the card panel binds to figure.mc[data-key] across the
    whole page, so a panel that removed its cards would silently break clicking."""
    html = _html(deck_file, collection_file)
    assert ".tabpanel { display:none; }" in html
    # Ownership lives in a non-default tab position but is still present
    assert "Ownership" in html


def test_printing_restores_every_tab(deck_file, collection_file):
    html = _html(deck_file, collection_file)
    assert "@media print" in html
    printed = html.split("@media print", 1)[1][:200]
    assert "display:block !important" in printed


def test_tabs_add_no_external_assets(deck_file, collection_file):
    html = _html(deck_file, collection_file)
    assert "<script src=" not in html
    assert '<link rel="stylesheet"' not in html


def test_every_theme_renders_the_tab_bar(deck_file, collection_file):
    for theme in ("default", "yshtola", "cloud", "rakdos", "spider"):
        html = _html(deck_file, collection_file, theme=theme)
        assert "<nav class='tabs'" in html, f"{theme} lost the tab bar"


# --------------------------------------------------------------------------- #
# Add-card picker — editable surface only (a file on disk has no server to POST to)
# --------------------------------------------------------------------------- #
def test_add_card_picker_only_on_the_editable_surface(deck_file, collection_file):
    editable = _html(deck_file, collection_file, editable=True)
    readonly = _html(deck_file, collection_file)
    assert 'id="ac-open"' in editable
    assert 'id="ac-open"' not in readonly, "a CLI dashboard has no server — no dead controls"
    assert ".ac-open" in editable and ".ac-open" not in readonly


def test_dashboard_degrades_when_the_fit_engine_fails(deck_file, collection_file, monkeypatch):
    """Regression: the dead-weight/has_field additions read `ctx` and `refs` OUTSIDE the
    try-block that assigns them, so a deck_context failure crashed generate() with
    UnboundLocalError instead of rendering a degraded page. 'Degrades, never crashes'
    is this repo's rule — a broken reference file must never take the dashboard down."""
    import deck_fit
    def boom(*a, **k):
        raise RuntimeError("reference data unavailable")
    monkeypatch.setattr(deck_fit, "deck_context", boom)
    html = _html(deck_file, collection_file)
    assert html.lstrip().lower().startswith("<!doctype html")
    assert "Sol Ring" in html                      # the decklist still rendered


def test_image_loader_survives_a_failed_batch():
    """The live phone bug: one failed batch POST used to dump every card onto the
    rate-limited by-name endpoint at 2.5/s — a page of 429 broken-image glyphs
    (the exact failure docs/card-images.md documents). The loader must retry the
    batch, pace any fallback under Scryfall's ~2/s limit, and clear a failed src
    so a card degrades to its name, never a broken icon. Textual guards here;
    behavior was verified in a real browser (healthy / flaky / down scenarios)."""
    loader = bd._asset("card_images.html")
    assert "runBatch(batch, attempt+1)" in loader, "batch retry missing"
    assert ",700)" in loader and ",400)" not in loader, "fallback must pace under ~2/s"
    assert "removeAttribute('src')" in loader, "a 429'd image must degrade to its name"


def test_app_side_grid_loader_has_the_same_protections():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(root, "webapp", "static", "cardgrid.js"),
              encoding="utf-8").read()
    assert "runBatch(batch, attempt + 1)" in js, "batch retry missing"
    assert ", 700)" in js and ", 400)" not in js, "fallback must pace under ~2/s"
    assert "removeAttribute('src')" in js, "a 429'd image must degrade to its name"


# --------------------------------------------------------------------------- #
# Goldfish Monte Carlo panel (Mana tab)
# --------------------------------------------------------------------------- #
def test_goldfish_panel_renders_whole(deck_file, collection_file):
    """One render, every invariant — `generate()` is the expensive call in this file.

    The panel has to carry three things at once: the DEFINITIONS of screw/flood (they
    are judgement calls the engine ships as data, and a reader who supplies their own
    misreads the number), the PROVENANCE line (two engines sit on one tab and are
    meant to disagree — without it a reader averages them), and BOTH card-panel hooks
    (generated dashboards fire on `.cardlink[data-key]`, app templates on `data-card`,
    so a selector change on one surface must not silently no-op the other)."""
    html = _html(deck_file, collection_file)
    assert "Goldfish Simulation" in html
    for marker in ("Keepable opener", "Flooded",
                   "lands in play at the start of turn",
                   "or more lands seen by the end of turn"):
        assert marker in html
    assert "Seeded Monte Carlo" in html
    assert "distinct from the exact hypergeometrics" in html
    i = html.find("Worst-sequenced cards")
    assert i > 0
    block = html[i:i + 3000]
    assert "data-key=" in block and "data-card=" in block
    # self-containment is the dashboard's contract; the new section is no exception
    assert "<script src=" not in html


def test_passing_sim_none_omits_the_section(deck_file, collection_file):
    html = bd.generate(deck_file, collection_file, title="T",
                       commander="Test Commander", sim=None)["dashboard"]
    assert "Goldfish Simulation" not in html


def test_the_page_still_renders_when_the_simulation_fails(deck_file, collection_file,
                                                          monkeypatch):
    """A failed sim costs the page a section, never the render — the one failure mode
    this repo forbids."""
    import goldfish

    def boom(*a, **k):
        raise RuntimeError("no")
    monkeypatch.setattr(goldfish, "sim_for_deck", boom)
    html = _html(deck_file, collection_file)
    assert "Goldfish Simulation" not in html
    assert html.lstrip().lower().startswith("<!doctype html")
    assert "Consistency &amp; Manabase" in html


def test_buy_tab_rows_are_panel_clickable(deck_file, collection_file, tmp_path):
    """Known gap (codemap "still open"): Buy rows were plain text, so the cards a Buy
    tab exists FOR — combo pieces and buy targets, none of them in the deck — were the
    only unclickable names on the page."""
    import build_dashboard as bd
    buylist = tmp_path / "testdeck.buylist.csv"
    buylist.write_text("Card,Price,Tier,Replaces,Reason\n"
                       "Rhystic Study,35.00,A,Divination,better draw\n", encoding="utf-8")
    html = bd.generate(deck_file, collection_file, title="T",
                       commander="Test Commander", sim=None)["dashboard"]
    assert 'data-card="Rhystic Study"' in html, "the buy target must open the panel"
    assert 'data-card="Divination"' in html, "so must the card it replaces"
