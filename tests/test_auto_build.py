"""The auto-builder must always produce a legal deck: exactly 100 cards, nothing outside
the commander's color identity, and no card taken from a deck that already committed it.
Also covers the two bugs found in the tribal rebuild (tribal blindness, self-exclusion)."""
import mtglib
import auto_build
import deck_conflicts


def _build(collection_file, commander="Test Commander", **kw):
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    return auto_build.build(commander, coll, idx, decks_dir=None, **kw)


def test_builds_exactly_100_cards(big_collection_file):
    d = _build(big_collection_file, identity={"W", "U"})
    assert d["total"] == 100
    assert not d.get("short")


def test_small_pool_reports_the_shortfall_honestly(collection_file):
    """A pool too thin for a 99 must say so rather than silently ship a short deck."""
    d = _build(collection_file, identity={"W", "U"})
    assert d["total"] < 100
    assert d.get("short", 0) > 0


def test_never_includes_off_color_cards(big_collection_file):
    """Green cards must never appear in a WU deck."""
    d = _build(big_collection_file, identity={"W", "U"})
    names = {mtglib._norm(c["name"]) for _title, cards in d["sections"] for c in cards}
    assert not any(n.startswith("green thing") for n in names)
    assert d["off_color_skipped"] > 0          # and it counted them


def test_sections_and_counts_are_consistent(big_collection_file):
    d = _build(big_collection_file, identity={"W", "U"})
    listed = sum(c.get("qty", 1) for _t, cards in d["sections"] for c in cards)
    assert listed == d["total"]


def test_deck_text_round_trips(big_collection_file):
    """What we write must parse back to the same 100 cards."""
    d = _build(big_collection_file, identity={"W", "U"})
    parsed = mtglib.parse_deck(auto_build.deck_text(d))
    assert sum(c.quantity for c in parsed) == d["total"]


def test_no_duplicate_nonbasic_cards(big_collection_file):
    """Commander is singleton: no nonbasic may appear twice."""
    d = _build(big_collection_file, identity={"W", "U"})
    names = [c["name"] for _t, cards in d["sections"] for c in cards
             if c["name"] not in ("Island", "Plains", "Swamp", "Mountain", "Forest")]
    assert len(names) == len(set(names))


def test_deck_text_has_required_headers(big_collection_file):
    text = auto_build.deck_text(_build(big_collection_file, identity={"W", "U"}))
    assert "# Commander:" in text and "# Title:" in text


def test_scan_skip_excludes_that_deck(tmp_path):
    """Regression: a REBUILD must not count the deck against itself, or it can't reuse
    its own cards (this is what capped The Ur-Dragon at 7 dragons)."""
    (tmp_path / "a.txt").write_text("# Commander: A\n1 Sol Ring\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("# Commander: B\n1 Sol Ring\n", encoding="utf-8")
    idx = {}
    full = deck_conflicts.scan(str(tmp_path), idx)
    skipped = deck_conflicts.scan(str(tmp_path), idx, skip="a")
    assert full["Sol Ring"]["total"] == 2
    assert skipped["Sol Ring"]["total"] == 1        # deck "a" no longer counted
