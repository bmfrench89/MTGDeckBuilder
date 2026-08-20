"""deck_sections.py — the EDHREC-style type regroup — plus deckcore.load_power_tags.

What can go wrong: a regroup that loses cards or quantities silently corrupts a
deck; a guessed type defeats the grounding rules; a non-idempotent rewrite churns
git history on every run. Hermetic: decks, collections and reference lists all live
in tmp_path.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import deck_sections
import deckcore
import mtglib


DECK = """# Title: Test Deck
# Commander: Test Commander
# Note: keep me

# --- Commander ---
1 Test Commander

# --- Ramp ---
1 Sol Ring
1 Cultivate

# --- Stuff ---
1 Grizzly Bears
1 Mystery Card

# --- Equipment (2) ---
1 Colossus Hammer

# --- Lands (3) ---
1 Command Tower
2 Forest
"""

ATTRS = """Name,Type
Sol Ring,Artifact
Cultivate,Sorcery
Grizzly Bears,Creature
Colossus Hammer,Artifact
Command Tower,Land
"""


@pytest.fixture
def deck_dir(tmp_path):
    deck = tmp_path / "test-deck.txt"
    deck.write_text(DECK, encoding="utf-8")
    (tmp_path / "test-deck.attrs.csv").write_text(ATTRS, encoding="utf-8")
    coll = tmp_path / "coll.txt"
    coll.write_text("1 Test Commander\n1 Sol Ring\n1 Cultivate\n1 Grizzly Bears\n"
                    "1 Mystery Card\n1 Colossus Hammer\n1 Command Tower\n9 Forest\n",
                    encoding="utf-8")
    return deck, coll


def test_regroup_types_hints_and_honesty(deck_dir):
    deck, coll = deck_dir
    text, st = deck_sections.regroup(str(deck), str(coll))
    assert st["total"] == 9, "regroup must not create or lose cards"
    assert "# Note: keep me" in text, "header block survives verbatim"
    assert text.index("# --- Commander ---") < text.index("# --- Creatures ---"), \
        "commander section stays first"
    # typed by attrs
    assert "# --- Artifacts ---\n1 Sol Ring\n1 Colossus Hammer" in text
    assert "# --- Sorceries ---\n1 Cultivate" in text
    # basics split from nonbasic lands, quantities intact
    assert "# --- Basics ---\n2 Forest" in text
    assert "# --- Lands ---\n1 Command Tower" in text
    # unknown card in an unhinted section is declared, never guessed
    assert st["unsorted_names"] == ["Mystery Card"]
    assert "Unsorted" in text


def test_regroup_is_idempotent(deck_dir):
    deck, coll = deck_dir
    text1, _ = deck_sections.regroup(str(deck), str(coll))
    deck.write_text(text1, encoding="utf-8")
    text2, st2 = deck_sections.regroup(str(deck), str(coll))
    assert text2 == text1
    assert st2["total"] == 9


def test_section_hint_types_when_data_is_absent(tmp_path):
    deck = tmp_path / "d.txt"
    deck.write_text("# Commander: X\n# --- Commander ---\n1 X\n"
                    "# --- Equipment ---\n1 Unknown Blade\n", encoding="utf-8")
    coll = tmp_path / "c.txt"
    coll.write_text("1 X\n1 Unknown Blade\n", encoding="utf-8")
    text, st = deck_sections.regroup(str(deck), str(coll))
    assert "# --- Artifacts ---\n1 Unknown Blade" in text, \
        "an Equipment-section card with no type data files as an artifact"
    assert st["hinted"] == 1 and st["unsorted"] == 0


def test_type_bucket_precedence():
    assert deckcore.type_bucket("Forest", ["Land"]) == "Basics"
    assert deckcore.type_bucket("Baleful Strix", ["Artifact Creature"]) == "Creatures"
    assert deckcore.type_bucket("Buried Ruin", ["Land"]) == "Lands"
    assert deckcore.type_bucket("Who Knows", None) is None
    assert deckcore.type_bucket("Who Knows", []) is None


def test_power_tags_load_and_label(tmp_path):
    ref = tmp_path / "ref"
    ref.mkdir()
    (ref / "game_changers.txt").write_text("# header\nRhystic Study\n", encoding="utf-8")
    (ref / "tutors.txt").write_text("Mystical Tutor\n", encoding="utf-8")
    tags = deckcore.load_power_tags(refdir=str(ref))
    assert tags[mtglib._norm("Rhystic Study")] == ["Game Changer"]
    assert tags[mtglib._norm("Mystical Tutor")] == ["Tutor"]
    assert mtglib._norm("Sol Ring") not in tags, "absent lists degrade to no tag"


SPLIT_BASICS = """# Title: Split Basics
# Commander: Test Commander

# --- Commander ---
1 Test Commander

# --- Basics ---
1 Plains
2 Island
3 Plains
"""


def _split_basics_deck(tmp_path):
    deck = tmp_path / "split.txt"
    deck.write_text(SPLIT_BASICS, encoding="utf-8")
    coll = tmp_path / "c.txt"
    coll.write_text("1 Test Commander\n20 Plains\n20 Island\n", encoding="utf-8")
    return deck, coll


def test_split_basic_lines_merge_with_quantities_intact(tmp_path):
    """The Y'shtola bug: the 2026-08-11 buy migration appended `1 Plains` beside an
    existing `3 Plains` instead of incrementing it, and that path never ran
    `optimize._tidy` (which does merge). Legal, but the deck reads as two Plains
    entries. Merging must SUM — a merge that loses the 3 is far worse than the bug."""
    deck, coll = _split_basics_deck(tmp_path)
    text, st = deck_sections.regroup(str(deck), str(coll))
    assert st["total"] == 7, "merging must not lose or invent a card"
    assert st["merged"] == 1
    basics = text.split("# --- Basics ---")[1].strip().splitlines()
    assert basics == ["4 Plains", "2 Island"], \
        "one merged line, first position kept, quantities summed"
    assert text.count("Plains") == 1


def test_merged_basics_survive_a_second_regroup(tmp_path):
    deck, coll = _split_basics_deck(tmp_path)
    text1, _ = deck_sections.regroup(str(deck), str(coll))
    deck.write_text(text1, encoding="utf-8")
    text2, st2 = deck_sections.regroup(str(deck), str(coll))
    assert text2 == text1, "the merge must be idempotent, not a churning rewrite"
    assert st2["merged"] == 0 and st2["total"] == 7


def test_duplicate_nonbasic_lines_are_left_for_the_violation_report(tmp_path):
    """A nonbasic on two lines is a SINGLETON ILLEGALITY, not untidiness. Merging it
    into `2 Sol Ring` would turn a visible duplicate into a tidier-looking illegal
    line; `optimize.singleton_violations` must still see it either way."""
    import optimize
    deck = tmp_path / "dupe.txt"
    deck.write_text("# Title: D\n# Commander: Test Commander\n\n"
                    "# --- Commander ---\n1 Test Commander\n\n"
                    "# --- Stuff ---\n1 Sol Ring\n1 Sol Ring\n", encoding="utf-8")
    (tmp_path / "dupe.attrs.csv").write_text("Name,Type\nSol Ring,Artifact\n",
                                             encoding="utf-8")
    coll = tmp_path / "c.txt"
    coll.write_text("1 Test Commander\n1 Sol Ring\n", encoding="utf-8")
    text, st = deck_sections.regroup(str(deck), str(coll))
    assert st["merged"] == 0
    assert text.count("1 Sol Ring") == 2, "the duplicate line must survive the regroup"
    deck.write_text(text, encoding="utf-8")
    assert [n for _q, n in optimize.singleton_violations(str(deck))] == ["Sol Ring"]


def test_comment_lines_in_the_header_and_qty_forms_survive_together(tmp_path):
    """The `_QTY_RE` regression guard (spec-repo-hardening Phase 1) crossed with the
    merge: `1x Plains` and a bare `Plains` are card lines mtglib.parse_deck accepts,
    so they must merge like any other basic — not be dropped, and not be treated as
    two different cards. Header comments stay verbatim."""
    deck = tmp_path / "forms.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Note: keep me\n\n"
                    "# --- Commander ---\n1 Test Commander\n\n"
                    "# --- Basics ---\n1x Plains\n2 Plains\nPlains\n", encoding="utf-8")
    coll = tmp_path / "c.txt"
    coll.write_text("1 Test Commander\n20 Plains\n", encoding="utf-8")
    text, st = deck_sections.regroup(str(deck), str(coll))
    assert st["total"] == 5, "1x + 2 + bare = 4 Plains plus the commander"
    assert "# Note: keep me" in text
    assert "# --- Basics ---\n4 Plains" in text
    assert st["merged"] == 2


def test_has_unsorted_is_the_post_sync_filter(deck_dir, tmp_path):
    """webapp/sync.py regroups ONLY decks still carrying unsorted cards; a deck in
    shape must not be rewritten (needless churn in the server's git history)."""
    deck, coll = deck_dir
    text, _ = deck_sections.regroup(str(deck), str(coll))
    assert deck_sections.has_unsorted(str(deck)) is False, \
        "the fixture's sections are function-named, not Unsorted"
    deck.write_text(text, encoding="utf-8")
    assert deck_sections.has_unsorted(str(deck)) is True, \
        "after the regroup the untypeable card sits in an explicit Unsorted section"
    clean = tmp_path / "clean.txt"
    clean.write_text("# Commander: X\n\n# --- Commander ---\n1 X\n"
                     "\n# --- Basics ---\n4 Plains\n", encoding="utf-8")
    assert deck_sections.has_unsorted(str(clean)) is False
    assert deck_sections.has_unsorted(str(tmp_path / "nope.txt")) is False, \
        "a missing file is not a reason to fail a sync"


# --------------------------------------------------------------------------- #
# The other half of the same bug: the app's ADD path. A regroup that merges split
# basic lines is worthless if the write path keeps creating them. Lives here rather
# than in test_deck_edit because it pins the Phase-0 merge contract, not the
# remove/replace contract that file guards.
# --------------------------------------------------------------------------- #
ADD_DECK = """# Title: T
# Commander: Test Commander

# --- Commander ---
1 Test Commander

# --- Lands ---
1 Command Tower

# --- Basics ---
3 Plains
2 Island
"""


def test_app_add_increments_an_existing_basic_line(tmp_path):
    import app
    deck = tmp_path / "d.txt"
    deck.write_text(ADD_DECK, encoding="utf-8")
    assert app._edit_deck_card(str(deck), "add", "Plains", section="Basics") is True
    text = deck.read_text(encoding="utf-8")
    assert "# --- Basics ---\n4 Plains\n2 Island" in text, \
        "a 4th Plains increments the existing line — appending is how the split arose"
    assert text.count("Plains") == 1
    assert "1 Command Tower" in text and "# --- Lands ---" in text, \
        "every other line survives untouched, same contract as remove/replace"


def test_app_add_still_appends_a_basic_the_section_lacks(tmp_path):
    import app
    deck = tmp_path / "d.txt"
    deck.write_text(ADD_DECK, encoding="utf-8")
    app._edit_deck_card(str(deck), "add", "Swamp", section="Basics")
    lines = deck.read_text(encoding="utf-8").split("# --- Basics ---")[1].strip().splitlines()
    assert lines == ["3 Plains", "2 Island", "1 Swamp"], \
        "a basic that isn't there yet is a new line at the end of the section"


def test_app_add_never_merges_a_nonbasic(tmp_path):
    """Merging a nonbasic would write `2 Sol Ring` — an illegal line that reads as a
    deliberate quantity. The twin stays visible for `singleton_violations` (the add
    route calls it right after the write) and for the player."""
    import app
    import optimize
    deck = tmp_path / "d.txt"
    deck.write_text(ADD_DECK.replace("1 Command Tower", "1 Sol Ring"), encoding="utf-8")
    app._edit_deck_card(str(deck), "add", "Sol Ring", section="Lands")
    text = deck.read_text(encoding="utf-8")
    assert "2 Sol Ring" not in text and text.count("1 Sol Ring") == 2
    assert [n for _q, n in optimize.singleton_violations(str(deck))] == ["Sol Ring"]


# --------------------------------------------------------------------------- #
# The post-sync auto-regroup (webapp/sync.py). A pull is how fresh attrs reach the
# server, so it is also when an Unsorted section becomes resolvable. Hermetic: the
# decks dir, the collection and the status file all live in tmp_path.
# --------------------------------------------------------------------------- #
UNSORTED_DECK = """# Title: U
# Commander: Test Commander

# --- Commander ---
1 Test Commander

# --- Unsorted (type unknown — enrich and re-run deck_sections) ---
1 Late Typed Card
"""

CLEAN_DECK = """# Title: C
# Commander: Test Commander

# --- Commander ---
1 Test Commander

# --- Basics ---
4 Plains
"""


def _sync_dir(tmp_path):
    (tmp_path / "u.txt").write_text(UNSORTED_DECK, encoding="utf-8")
    (tmp_path / "c.txt").write_text(CLEAN_DECK, encoding="utf-8")
    (tmp_path / "u.attrs.csv").write_text("Name,Type\nLate Typed Card,Artifact\n",
                                          encoding="utf-8")
    coll = tmp_path / "coll.txt"
    coll.write_text("1 Test Commander\n1 Late Typed Card\n20 Plains\n", encoding="utf-8")
    return coll


def test_post_sync_regroup_touches_only_decks_with_unsorted_cards(tmp_path):
    import sync
    coll = _sync_dir(tmp_path)
    before = (tmp_path / "c.txt").read_text(encoding="utf-8")
    summary = sync.regroup_unsorted(decks_dir=str(tmp_path), collection=str(coll))
    assert "u.txt" in summary and "c.txt" not in summary
    assert "all Unsorted drained" in summary
    assert (tmp_path / "c.txt").read_text(encoding="utf-8") == before, \
        "a deck already in shape must not be rewritten — that is pure git churn"
    text = (tmp_path / "u.txt").read_text(encoding="utf-8")
    assert "# --- Artifacts ---\n1 Late Typed Card" in text
    assert "Unsorted" not in text
    assert sync.regroup_unsorted(decks_dir=str(tmp_path), collection=str(coll)) is None, \
        "nothing left to do → nothing reported"


def test_post_sync_regroup_says_what_it_could_not_type(tmp_path):
    """Honesty label: cards the refreshed attrs still cannot type stay in Unsorted,
    and the sync line says how many rather than implying a clean sweep."""
    import sync
    coll = _sync_dir(tmp_path)
    (tmp_path / "u.attrs.csv").unlink()
    summary = sync.regroup_unsorted(decks_dir=str(tmp_path), collection=str(coll))
    assert "1 card(s) still unsorted" in summary


def test_post_sync_regroup_reports_a_bad_deck_instead_of_raising(tmp_path, monkeypatch):
    import sync
    coll = _sync_dir(tmp_path)

    def boom(path, collection_path):
        raise ValueError("bad deck")

    monkeypatch.setattr(deck_sections, "regroup", boom)
    summary = sync.regroup_unsorted(decks_dir=str(tmp_path), collection=str(coll))
    assert "regroup failed for u.txt: ValueError" in summary


def test_sync_run_never_fails_on_a_regroup_error(tmp_path, monkeypatch):
    """A regroup problem must never turn a good sync into a failed one — the pull
    already happened and the app still needs its reload."""
    import subprocess
    import sync
    monkeypatch.setenv("MTG_AUTO_SYNC", "1")
    monkeypatch.setattr(sync, "STATUS", str(tmp_path / "status.json"))
    monkeypatch.setattr(sync.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0,
                                                                     stdout="sync: done.",
                                                                     stderr=""))
    heads = iter(("aaa", "bbb"))
    monkeypatch.setattr(sync, "_head", lambda: next(heads))
    monkeypatch.setattr(sync, "_touch_wsgi", lambda: None)

    def boom():
        raise RuntimeError("no decks dir")

    monkeypatch.setattr(sync, "regroup_unsorted", boom)
    st = sync.run("auto")
    assert st["ok"] is True and st["pulled"] is True
    # The regroup outcome lives in its OWN field and is deliberately NOT folded
    # into `detail`: appending it used to push the word RECOVERED past the
    # 300-char tail that `status_view` keys the rescue-branch warning off.
    assert "regroup skipped: RuntimeError" in st["regroup"]
    assert st["detail"] == "sync: done."


def test_a_regroup_summary_cannot_bury_the_recovered_warning(tmp_path, monkeypatch):
    """The self-heal warning survives a long regroup summary.

    Reproduces the found regression: `detail` carried the script's RECOVERED
    line, the regroup summary was appended, and `detail[-300:]` truncated the
    word away — so a sync that parked the player's local edits on a rescue
    branch rendered plain green with the homework invisible."""
    import subprocess
    import sync
    monkeypatch.setenv("MTG_AUTO_SYNC", "1")
    monkeypatch.setattr(sync, "STATUS", str(tmp_path / "status.json"))
    recovered = ("sync: RECOVERED — local state parked on pushed branch "
                 "server-rescue-2026-08-13; a session must merge it back. " + "x" * 90)
    monkeypatch.setattr(sync, "subprocess", subprocess)
    monkeypatch.setattr(sync.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(
                            cmd, 0, stdout=recovered, stderr=""))
    heads = iter(("aaa", "bbb"))
    monkeypatch.setattr(sync, "_head", lambda: next(heads))
    monkeypatch.setattr(sync, "_touch_wsgi", lambda: None)
    monkeypatch.setattr(sync, "regroup_unsorted",
                        lambda *a, **k: "regrouped 6 deck(s): " + ", ".join(
                            f"deck-with-a-long-name-{i}.txt" for i in range(6)))
    st = sync.run("auto")
    assert st["recovered"] is True
    view = sync.status_view()
    assert view["cls"] == "warn", "a recovered sync must never render green"
    assert "RECOVERED" in view["text"]
    assert "regrouped 6 deck(s)" in view["text"], "the regroup is still reported"


def test_sync_run_does_not_write_decks_where_sync_is_disabled(tmp_path, monkeypatch):
    """The regroup rides `enabled()`: on a PC, in CI and in this suite nothing may
    rewrite a deck file behind a sync."""
    import subprocess
    import sync
    for var in ("MTG_AUTO_SYNC", "PYTHONANYWHERE_SITE", "PYTHONANYWHERE_DOMAIN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(sync, "STATUS", str(tmp_path / "status.json"))
    monkeypatch.setattr(sync.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0,
                                                                     stdout="ok", stderr=""))
    heads = iter(("aaa", "bbb"))
    monkeypatch.setattr(sync, "_head", lambda: next(heads))
    monkeypatch.setattr(sync, "_touch_wsgi", lambda: None)
    called = []
    monkeypatch.setattr(sync, "regroup_unsorted", lambda *a, **k: called.append(1))
    sync.run("auto")
    assert called == []


def test_regroup_accepts_every_qty_line_form_parse_deck_accepts(tmp_path):
    """Regression: a local qty regex accepted only '<digits> <name>', so '1x Name'
    and bare-name lines — both valid to mtglib.parse_deck — were silently DELETED
    from the deck file by a regroup --apply. Card loss, the worst failure mode."""
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n\n"
                    "# --- Commander ---\n1 Test Commander\n\n"
                    "# --- Stuff ---\n1x Sol Ring\n3x Forest\nGrizzly Bears\n",
                    encoding="utf-8")
    coll = tmp_path / "c.txt"
    coll.write_text("1 Test Commander\n1 Sol Ring\n1 Grizzly Bears\n9 Forest\n",
                    encoding="utf-8")
    text, st = deck_sections.regroup(str(deck), str(coll))
    assert st["total"] == 6, "every card line form must survive the regroup"
    assert "Sol Ring" in text and "Grizzly Bears" in text
    assert "3 Forest" in text


# --- The Replace flow is the path that caused the original misfiles ---

def _deck_with_basics(tmp_path):
    p = tmp_path / "d.txt"
    p.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W\n"
                 "\n# --- Commander ---\n1 Test Commander\n"
                 "\n# --- Lands ---\n1 Command Tower\n"
                 "\n# --- Basics ---\n3 Plains\n", encoding="utf-8")
    return p


def test_replacing_a_card_with_a_basic_does_not_split_the_basic_line(tmp_path):
    """The found gap: Replace wrote `1 Plains` at the OUTGOING card's slot, which
    put a basic under Lands *and* created a second Plains line — both bugs Phase 0
    exists to kill, from the flow that caused the original misfiles."""
    import app as appmod
    p = _deck_with_basics(tmp_path)
    appmod._edit_deck_card(str(p), "replace", "Command Tower", replacement="Plains")
    text = p.read_text(encoding="utf-8")
    assert text.count("Plains") == 1, f"exactly one Plains line, got:\n{text}"
    assert "4 Plains" in text, "the basic merged into its existing line"
    assert "Command Tower" not in text
    lands = text.split("# --- Lands ---")[1].split("# --- Basics ---")[0]
    assert "Plains" not in lands, "a basic must not land in the Lands section"


def test_a_basic_merges_into_its_existing_line_across_sections(tmp_path):
    """A basic belongs on exactly one line file-wide. Scoping the merge search to
    the requested section appended a twin in Basics while a copy sat in Lands — a
    cross-section split the server's Unsorted-only regroup would never drain."""
    import app as appmod
    p = tmp_path / "d.txt"
    p.write_text("# Title: T\n# Commander: C\n# Colors: W\n"
                 "\n# --- Lands ---\n2 Plains\n"
                 "\n# --- Basics ---\n1 Island\n", encoding="utf-8")
    lines = p.read_text(encoding="utf-8").split("\n")
    appmod._insert_deck_card(str(p), lines, "Plains", section="Basics")
    text = p.read_text(encoding="utf-8")
    assert text.count("Plains") == 1, f"no cross-section twin, got:\n{text}"
    assert "3 Plains" in text


# --------------------------------------------------------------------------- #
# --check: the read-only tripwire for misfiled cards
#
# 18 typed cards sat in contradicting type sections across 7 of the 10 real decks
# before the player's phone screenshot surfaced one (a Sorcery under Artifacts,
# 2026-08-20). Tests stay hermetic, so the real decks are guarded by running this
# checker in CI/refresh — these tests prove the checker itself.
# --------------------------------------------------------------------------- #
def _checker_deck(tmp_path, body):
    deck = tmp_path / "c.txt"
    deck.write_text("# Commander: Test Commander\n" + body, encoding="utf-8")
    (tmp_path / "c.attrs.csv").write_text(
        "Name,Type\nSol Ring,Artifact\nCultivate,Sorcery\nGrizzly Bears,Creature\n"
        "Steel Golem,Artifact Creature\nCommand Tower,Land\n", encoding="utf-8")
    coll = tmp_path / "coll.txt"
    coll.write_text("1 Test Commander\n1 Sol Ring\n1 Cultivate\n1 Grizzly Bears\n"
                    "1 Steel Golem\n1 Command Tower\n1 Mystery Card\n", encoding="utf-8")
    return str(deck), str(coll)


def test_check_flags_a_typed_card_in_a_contradicting_type_section(tmp_path):
    deck, coll = _checker_deck(tmp_path, "# --- Artifacts ---\n1 Cultivate\n")
    violations, untyped = deck_sections.check(deck, coll)
    assert [(v[0], v[2], v[3]) for v in violations] == [
        ("Artifacts", "Cultivate", "Sorceries")]
    assert untyped == []
    assert deck_sections.main(["--deck", deck, "--collection", coll, "--check"]) == 3


def test_check_passes_a_clean_deck_and_exits_zero(tmp_path):
    deck, coll = _checker_deck(
        tmp_path, "# --- Sorceries ---\n1 Cultivate\n# --- Artifacts ---\n1 Sol Ring\n")
    violations, _ = deck_sections.check(deck, coll)
    assert violations == []
    assert deck_sections.main(["--deck", deck, "--collection", coll, "--check"]) == 0


def test_check_lets_an_artifact_creature_live_under_creatures(tmp_path):
    """type_bucket says a creature is a creature no matter what else it is —
    the checker must agree, or every Golem becomes a false positive."""
    deck, coll = _checker_deck(tmp_path, "# --- Creatures ---\n1 Steel Golem\n")
    violations, _ = deck_sections.check(deck, coll)
    assert violations == []


def test_check_reports_untyped_without_failing(tmp_path):
    """A fresh export's cards are untyped until the enrichment loop runs; failing
    CI in that window would punish the pipeline for working."""
    deck, coll = _checker_deck(tmp_path, "# --- Instants ---\n1 Mystery Card\n")
    violations, untyped = deck_sections.check(deck, coll)
    assert violations == []
    assert untyped == [("Instants", "Mystery Card")]
    assert deck_sections.main(["--deck", deck, "--collection", coll, "--check"]) == 0


def test_check_ignores_custom_sections_and_the_commander(tmp_path):
    """Only sections that claim to BE a type are policed — a player's 'Combo
    Pieces' section may hold anything, and the commander line is exempt."""
    deck, coll = _checker_deck(
        tmp_path,
        "# --- Commander ---\n1 Test Commander\n"
        "# --- Combo Pieces ---\n1 Cultivate\n1 Sol Ring\n")
    violations, untyped = deck_sections.check(deck, coll)
    assert violations == [] and untyped == []


def test_check_is_read_only(tmp_path):
    deck, coll = _checker_deck(tmp_path, "# --- Artifacts ---\n1 Cultivate\n")
    before = open(deck, encoding="utf-8").read()
    deck_sections.main(["--deck", deck, "--collection", coll, "--check"])
    assert open(deck, encoding="utf-8").read() == before


def test_power_tags_label_both_spellings_of_a_split_name(tmp_path):
    """The label loader and power.py read the SAME curated files; power has matched
    both faces of a split name since 2026-08-20, and the labels must agree — a
    curated "Boom // Bust" that labels nothing when the deck spells "Boom" makes
    the two surfaces silently disagree about the same card."""
    (tmp_path / "mass_land_denial.txt").write_text("Boom // Bust\n", encoding="utf-8")
    tags = deckcore.load_power_tags(refdir=str(tmp_path))
    assert tags.get(mtglib._norm("Boom // Bust")) == ["Mass land denial"]
    assert tags.get(mtglib._norm("Boom")) == ["Mass land denial"]
