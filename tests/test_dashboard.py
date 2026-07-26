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
