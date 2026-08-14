"""Phase 3 — the player's bracket setting, and the rule that the evidence stays."""
import os

import mtglib
import power


def _deck(tmp_path, bracket=None, extra=""):
    head = f"# Bracket: {bracket}\n" if bracket else ""
    p = tmp_path / "d.txt"
    p.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n" + head +
                 "\n# --- Commander ---\n1 Test Commander\n"
                 "\n# --- Main ---\n1 Sol Ring\n" + extra +
                 "\n# --- Lands ---\n10 Island\n", encoding="utf-8")
    return str(p)


def test_no_header_behaves_exactly_as_before(tmp_path):
    p = _deck(tmp_path)
    assert power.read_declared_bracket(p) is None


def test_the_header_is_read_and_bounded(tmp_path):
    assert power.read_declared_bracket(_deck(tmp_path, 4)) == 4
    # Out-of-range and junk are simply not a setting — never a crash, never a guess.
    assert power.read_declared_bracket(_deck(tmp_path, 9)) is None
    assert power.read_declared_bracket(_deck(tmp_path, "banana")) is None


def test_assess_reports_both_and_keeps_bracket_as_detected(collection_file, tmp_path):
    """`bracket` must KEEP meaning the detected number: every existing consumer reads
    it, and a setting that silently rewrote it would change ranking behaviour."""
    import deck_stats
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    deck = mtglib.parse_deck(open(_deck(tmp_path), encoding="utf-8").read())
    enriched, missing = deck_stats.analyze(deck, idx)
    rep = deck_stats.build_report(deck, enriched, missing, idx)
    refs = power.load_refs()

    plain = power.assess(enriched, rep, refs)
    assert plain["bracket_declared"] is None
    assert plain["bracket_effective"] == plain["bracket"] == plain["bracket_detected"]
    assert plain["bracket_mismatch"] is False

    setted = power.assess(enriched, rep, refs, declared=5)
    assert setted["bracket"] == plain["bracket"], "detected must not be overwritten"
    assert setted["bracket_detected"] == plain["bracket"]
    assert setted["bracket_declared"] == 5
    assert setted["bracket_effective"] == 5
    assert setted["bracket_mismatch"] is (5 != plain["bracket"])
    assert setted["bracket_reasons"] == plain["bracket_reasons"], (
        "the evidence is untouched by the setting")


def test_the_header_survives_a_write_through_the_app(tmp_path, monkeypatch):
    """The setting is stored in the deck file, so the deck-edit contract has to hold:
    the header round-trips and the section/quantity lines are untouched."""
    import app as appmod
    p = _deck(tmp_path)
    before = open(p, encoding="utf-8").read()
    appmod._set_deck_header(p, "Bracket", "3")
    after = open(p, encoding="utf-8").read()
    assert "# Bracket: 3" in after
    assert power.read_declared_bracket(p) == 3
    for line in ("1 Sol Ring", "10 Island", "# --- Lands ---", "1 Test Commander"):
        assert line in after, f"{line} must survive a header write"
    # setting it again REPLACES rather than stacking
    appmod._set_deck_header(p, "Bracket", "2")
    txt = open(p, encoding="utf-8").read()
    assert txt.count("# Bracket:") == 1
    assert power.read_declared_bracket(p) == 2
    # clearing returns the file to its original meaning
    appmod._set_deck_header(p, "Bracket", None)
    assert power.read_declared_bracket(p) is None
    assert open(p, encoding="utf-8").read().count("# Bracket") == 0
    assert "1 Sol Ring" in open(p, encoding="utf-8").read()


def test_a_header_written_before_the_first_section_is_seen_by_the_parser(tmp_path):
    """A header appended AFTER a section marker would parse as nothing. Pin the
    placement, not just the presence."""
    import app as appmod
    p = _deck(tmp_path)
    appmod._set_deck_header(p, "Bracket", "4")
    lines = open(p, encoding="utf-8").read().split("\n")
    import deckcore
    first_section = next(i for i, ln in enumerate(lines)
                         if deckcore.section_label(ln) is not None)
    at = next(i for i, ln in enumerate(lines) if ln.startswith("# Bracket:"))
    assert at < first_section
