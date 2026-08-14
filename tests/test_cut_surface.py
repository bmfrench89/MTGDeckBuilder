"""Phase 9 — the "what do I cut" surface.

The single most-articulated deckbuilding pain point, answered with the deck's own
numbers. Two properties make it trustworthy rather than another opinion generator:
it ranks by the SAME value the optimizer scores swaps with (one scorer, no drift),
and it shows the player's protected cards flagged instead of quietly dropping them."""
import deck_fit
import mtglib
import optimize


def _ctx_bits(collection_file, tmp_path):
    import deck_stats
    import deckcore
    import power
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n"
                    "\n# --- Commander ---\n1 Test Commander\n"
                    "\n# --- Main ---\n1 Sol Ring\n1 Counterspell\n"
                    "1 Swords to Plowshares\n1 Serra Angel\n1 Llanowar Elves\n"
                    "\n# --- Lands ---\n10 Island\n", encoding="utf-8")
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    d = mtglib.parse_deck(open(deck, encoding="utf-8").read())
    enriched, missing = deck_stats.analyze(d, idx)
    rep = deck_stats.build_report(d, enriched, missing, idx)
    refs = power.load_refs()
    ctx = deck_fit.deck_context(str(deck), enriched, "Test Commander", {}, {})
    return str(deck), enriched, rep, ctx, refs


def test_the_ranking_uses_the_optimizers_own_scorer(collection_file, tmp_path):
    """If these two ever diverge, the Cuts panel and the optimizer would disagree
    about what a card is worth — which is the drift the shared scorer prevents."""
    _p, enriched, rep, ctx, refs = _ctx_bits(collection_file, tmp_path)
    field = {"counterspell": 40}
    out = deck_fit.cut_ranking(enriched, rep, ctx, refs, field, limit=20)
    by_name = {r["name"]: r for r in out["rows"]}
    for name, row in by_name.items():
        card = next(c for c in enriched if c.name == name)
        assert row["value"] == round(
            deck_fit.card_value(name, card, rep, ctx, refs, field))
    # and optimize's shim resolves to the same function
    assert optimize.card_value("Counterspell",
                               next(c for c in enriched if c.name == "Counterspell"),
                               rep, ctx, refs, field) == deck_fit.card_value(
        "Counterspell", next(c for c in enriched if c.name == "Counterspell"),
        rep, ctx, refs, field)


def test_rows_are_ranked_lowest_value_first(collection_file, tmp_path):
    _p, enriched, rep, ctx, refs = _ctx_bits(collection_file, tmp_path)
    out = deck_fit.cut_ranking(enriched, rep, ctx, refs, {"counterspell": 60}, limit=20)
    vals = [r["value"] for r in out["rows"]]
    assert vals == sorted(vals), "ascending by value — cheapest to lose first"


def test_protected_cards_are_shown_flagged_not_hidden(collection_file, tmp_path):
    """The player asked 'what do I cut'. Silently dropping their protected picks
    answers a different question; flagging them answers theirs honestly."""
    _p, enriched, rep, ctx, refs = _ctx_bits(collection_file, tmp_path)
    prot = {mtglib._norm("Sol Ring")}
    out = deck_fit.cut_ranking(enriched, rep, ctx, refs, {}, protected=prot, limit=20)
    row = next(r for r in out["rows"] if r["name"] == "Sol Ring")
    assert row["protected"] is True
    assert "your call" in row["why"]


def test_lands_are_never_listed(collection_file, tmp_path):
    """The manabase pass owns lands; this surface must not propose cutting them."""
    _p, enriched, rep, ctx, refs = _ctx_bits(collection_file, tmp_path)
    out = deck_fit.cut_ranking(enriched, rep, ctx, refs, {}, limit=50)
    assert not any(r["name"] == "Island" for r in out["rows"])


def test_absent_field_data_is_labelled_not_printed_as_zero(collection_file, tmp_path):
    """`field.get(name, 0)` collapses 'played in 0% of decks' with 'the field has
    never heard of this card'. Only the first is a measurement."""
    _p, enriched, rep, ctx, refs = _ctx_bits(collection_file, tmp_path)
    out = deck_fit.cut_ranking(enriched, rep, ctx, refs, {}, limit=20)
    assert out["no_field"] is True
    assert all(r["field_known"] is False for r in out["rows"])
    assert any("no opinion" in r["why"] for r in out["rows"])


def test_it_writes_nothing(collection_file, tmp_path):
    """Advisory means advisory: the deck file is byte-identical afterwards."""
    p, _e, _r, _c, _f = _ctx_bits(collection_file, tmp_path)
    before = open(p, encoding="utf-8").read()
    optimize.cut_candidates(p, collection_file, limit=5)
    assert open(p, encoding="utf-8").read() == before
