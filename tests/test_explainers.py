"""Phase 7 — every Mana-tab number can explain itself.

The rule under test is single-sourcing: the wording lives in the ENGINE and is
rendered by the surfaces, so the CLI, the generated dashboard, the app page and
--json can never drift into different explanations of the same percentage. It is the
same contract goldfish's screw/flood definitions already had, extended to the whole
tab — and the honesty caveats now sit WITH the number they qualify instead of in a
footer read after the fact."""
import build_dashboard as bd
import manabase


def test_the_engine_ships_an_explainer_for_every_stat_it_reports():
    ex = manabase._explain(37, 99, {})
    for key in ("keepable", "ge3_open", "ge4_by_t4", "sources", "risky",
                "unconditional"):
        assert key in ex, f"{key} has a number but no explanation"
        for part in ("what", "why", "healthy"):
            assert ex[key][part].strip(), f"{key}.{part} must not be empty"


def test_analyze_carries_the_explainers_into_the_payload(collection_file, tmp_path):
    import deck_stats
    import mtglib
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    deck = mtglib.parse_deck(
        "# Commander: Test Commander\n\n# --- Main ---\n1 Counterspell\n"
        "1 Swords to Plowshares\n\n# --- Lands ---\n10 Island\n")
    enriched, missing = deck_stats.analyze(deck, idx)
    rep = deck_stats.build_report(deck, enriched, missing, idx)
    out = manabase.analyze(rep, enriched)
    assert out["explain"], "--json consumers get the notes too"


def test_the_identity_approximation_caveat_rides_its_own_stat():
    """The honesty label must sit with the number it qualifies. Sources counted by
    color identity are an approximation of THAT stat, so the warning belongs in the
    sources explainer, not in a page footer."""
    clean = manabase._explain(37, 99, {"identity_lands": 0})
    approx = manabase._explain(37, 99, {"identity_lands": 4})
    assert "IDENTITY" in approx["sources"]["healthy"]
    assert "4 land" in approx["sources"]["healthy"]
    assert "IDENTITY" not in clean["sources"]["healthy"], (
        "no caveat when there is nothing to caveat")


def test_the_dashboard_renders_notes_from_the_engine_not_its_own_prose():
    ex = {"keepable": {"what": "WHAT-MARKER", "why": "WHY-MARKER",
                       "healthy": "HEALTHY-MARKER"}}
    html = bd.explain_html(ex, "keepable")
    for marker in ("WHAT-MARKER", "WHY-MARKER", "HEALTHY-MARKER"):
        assert marker in html
    assert "<details" in html and "<summary" in html


def test_an_absent_explainer_renders_nothing_rather_than_an_empty_box():
    assert bd.explain_html({}, "keepable") == ""
    assert bd.explain_html(None, "keepable", "sources") == ""


def test_explainers_print_expanded(deck_file, collection_file):
    """A collapsed <details> has no way to open on paper — the caveat is part of the
    number, so the generated dashboard's print rules must force it visible."""
    html = bd.generate(deck_file, collection_file, title="T", commander="Test Commander",
                       sim=None)["dashboard"]
    assert "@media print" in html
    printed = html.split("@media print", 1)[1][:400]
    assert ".explain > p" in printed and "display:block !important" in printed
