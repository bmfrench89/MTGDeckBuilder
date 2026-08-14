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


def test_hand_added_cards_reach_the_ranking_as_protected(collection_file, tmp_path):
    """The end-to-end wiring, not just `cut_ranking`'s parameter.

    `cut_candidates` builds the protected set that the test above passes in by
    hand — and it was building an EMPTY one. Two faults, neither able to raise:
    `deckcore.manual_adds` wants the `.changes.csv` and was handed the deck
    `.txt` (a DictReader over a deck file finds no `Card` column and yields
    nothing), and it returns a list of ROWS, so iterating it yields dicts that
    `_norm` would choke on inside a bare `except`. Either one alone empties the
    set, so the Cuts surface ranked hand-picked cards with no "your call, not the
    tool's" flag — the exact protection this phase was written to provide.

    Found by the Phase 8 acceptance run against the real collection (2026-08-14),
    where y'shtola's hand-added Wizard's Staff came back unflagged."""
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n"
                    "\n# --- Commander ---\n1 Test Commander\n"
                    "\n# --- Main ---\n1 Sol Ring\n1 Counterspell\n"
                    "1 Swords to Plowshares\n1 Serra Angel\n"
                    "\n# --- Lands ---\n10 Island\n", encoding="utf-8")
    import datetime
    today = datetime.date.today().isoformat()
    (tmp_path / "d.changes.csv").write_text(
        "Card,Added,Replaced,Source\n"
        f"Serra Angel,{today},,manual-add\n", encoding="utf-8")

    # Prove the flag comes from the MANUAL path and not from curated notes, or the
    # test would pass on a card `_protected` already covers and prove nothing.
    prot, _notes = optimize._protected(str(deck), "Test Commander")
    assert mtglib._norm("Serra Angel") not in prot, \
        "precondition: nothing else protects this card"

    out = optimize.cut_candidates(str(deck), collection_file, limit=20)
    by_name = {r["name"]: r for r in out["rows"]}
    assert by_name["Serra Angel"]["protected"] is True, \
        "a hand-added card must reach the ranking flagged, not bare"
    assert "your call" in by_name["Serra Angel"]["why"]


def test_the_changes_log_is_read_from_the_deck_directory(collection_file, tmp_path,
                                                         monkeypatch):
    """The companion path must be the deck's FULL stem. `cut_candidates` keeps a
    BASENAME stem for labelling the report, and reusing it here would read a
    changes.csv relative to the process's working directory — which happens to
    work when you run the CLI from the repo root and silently stops working
    anywhere else (the web app, a cron job, a console in $HOME)."""
    decks = tmp_path / "decks"
    decks.mkdir()
    deck = decks / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n"
                    "\n# --- Commander ---\n1 Test Commander\n"
                    "\n# --- Main ---\n1 Sol Ring\n1 Serra Angel\n"
                    "\n# --- Lands ---\n10 Island\n", encoding="utf-8")
    import datetime
    today = datetime.date.today().isoformat()
    (decks / "d.changes.csv").write_text(
        "Card,Added,Replaced,Source\n"
        f"Serra Angel,{today},,manual-add\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)          # cwd is NOT the deck's directory
    out = optimize.cut_candidates(str(deck), collection_file, limit=20)
    row = next(r for r in out["rows"] if r["name"] == "Serra Angel")
    assert row["protected"] is True, \
        "the changes.csv was looked up relative to cwd instead of the deck"


def test_manual_adds_review_skips_cards_no_longer_in_the_deck(collection_file, tmp_path):
    """`.changes.csv` is append-only history. A card the player added and then took
    back out stays a manual-add row forever, and this list is headed "the optimizer
    never cuts these" — a claim about a card that is not there to cut.

    Live case (2026-08-14): y'shtola's log adds Painful Truths and then replaces it
    back out with Read the Bones, same day, rows 17-18. The advisory printed
    "Painful Truths  (no opinion — not resolvable in the collection)" — two
    confusing statements about a card the deck does not run."""
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n"
                    "\n# --- Commander ---\n1 Test Commander\n"
                    "\n# --- Main ---\n1 Sol Ring\n1 Serra Angel\n"
                    "\n# --- Lands ---\n10 Island\n", encoding="utf-8")
    import datetime
    today = datetime.date.today().isoformat()
    (tmp_path / "d.changes.csv").write_text(
        "Card,Added,Replaced,Source\n"
        f"Reverted Pick,{today},Serra Angel,manual-replace\n"
        f"Serra Angel,{today},Reverted Pick,manual-replace\n", encoding="utf-8")

    lines = "\n".join(optimize.manual_adds_review(str(deck), collection_file))
    assert "Reverted Pick" not in lines, \
        "a card that was added and taken back out is not a card the deck runs"
    assert "Serra Angel" in lines, "the card that stayed must still be reported"
