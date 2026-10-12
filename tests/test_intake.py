"""Card intake (docs/spec-card-intake.md §3-§5): the batch parser, name resolution,
the dated batch block, reconcile-on-upload, the Upload guard's arithmetic, and the
batch dates the loader and the arrivals review read.

What these protect: a pasted list must land as exactly the cards it names — never a
marker parsed as a name, never a real name with parentheses truncated, never a
"did you mean" written without a tick, never a batch counted twice once the export
catches up, and never a priced or personal detail written into the tracked file.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import deckcore  # noqa: E402
import intake  # noqa: E402
import mtglib  # noqa: E402


def _names(rows):
    return [(r["qty"], r["name"]) for r in rows if not r["error"]]


# --------------------------------------------------------------------------- #
# The parser — every accepted format
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("line, want", [
    ("4 Sol Ring", (4, "Sol Ring")),
    ("4x Sol Ring", (4, "Sol Ring")),
    ("4 x Sol Ring", (4, "Sol Ring")),
    ("Sol Ring", (1, "Sol Ring")),
    ("Sol Ring x2", (2, "Sol Ring")),
    ("Sol Ring 2x", (2, "Sol Ring")),
    ("1 Sol Ring (C21) 263", (1, "Sol Ring")),                 # Arena / ManaBox text
    ("1 Sol Ring (C21) 263 *F*", (1, "Sol Ring")),             # Moxfield foil
    ("1 Sol Ring (C21) 263 *E*", (1, "Sol Ring")),             # etched
    ("1 Sol Ring [C21]", (1, "Sol Ring")),                     # TCGplayer app
    ("1 Sol Ring [C21] NM", (1, "Sol Ring")),                  # condition word
    ("1 Mana Crypt (Foil)", (1, "Mana Crypt")),
    ("1x Fire // Ice ^Have,#37d67a^", (1, "Fire // Ice")),      # Archidekt colour tag
    ("1 Lightning Bolt (PLST) M10-146", (1, "Lightning Bolt")),
])
def test_each_line_format_parses_to_name_and_quantity(line, want):
    assert _names(intake.parse_text(line)) == [want]


def test_real_names_with_parentheses_survive():
    """Only a trailing `(SET) <number>` is a printing. A parenthesised phrase with
    spaces is part of the card's name."""
    rows = intake.parse_text("1 B.F.M. (Big Furry Monster)\n"
                             "1 Erase (Not the Urza's Legacy One)\n")
    assert _names(rows) == [(1, "B.F.M. (Big Furry Monster)"),
                            (1, "Erase (Not the Urza's Legacy One)")]


def test_a_card_named_like_a_marker_is_kept():
    """`Foil` is a real card. A marker is only stripped when a name precedes it."""
    assert _names(intake.parse_text("1 Foil")) == [(1, "Foil")]


def test_quantity_bounds_are_errors_not_cards():
    rows = intake.parse_text("150 Lightning Bolt\n0 Sol Ring\n")
    assert [r["error"] != "" for r in rows] == [True, True]
    assert _names(rows) == []


def test_section_headers_mark_commander_and_outside_cards():
    text = ("Commander\n1 Atraxa, Praetors' Voice\n\nDeck\n1 Sol Ring\n\n"
            "Sideboard\n1 Swords to Plowshares\n// Maybeboard\n1 Path to Exile\n"
            "1 Delver of Secrets [Maybeboard{noDeck}]\n1 Kenrith [Commander{top}]\n")
    rows = {r["name"]: r for r in intake.parse_text(text)}
    assert rows["Atraxa, Praetors' Voice"]["commander"]
    assert rows["Sol Ring"]["section"] == "main" and not rows["Sol Ring"]["commander"]
    assert rows["Swords to Plowshares"]["section"] == "sideboard"
    assert rows["Path to Exile"]["section"] == "maybeboard"
    assert rows["Delver of Secrets"]["section"] == "maybeboard"
    assert rows["Kenrith"]["commander"]


def test_our_own_deck_file_pastes_cleanly():
    text = ("# Title: T\n# Commander: Giada, Font of Hope\n\n# --- Commander ---\n"
            "1 Giada, Font of Hope\n\n# --- Creatures ---\n1 Lyra Dawnbringer\n")
    rows = intake.parse_text(text)
    assert _names(rows) == [(1, "Giada, Font of Hope"), (1, "Lyra Dawnbringer")]
    assert rows[0]["commander"] and not rows[1]["commander"]


def test_a_csv_export_goes_through_the_collection_loader():
    csv = ("Name,Set code,Collector number,Foil,Quantity,Purchase price\n"
           "Sol Ring,C21,263,foil,2,1.50\nCounterspell,MH2,267,normal,1,0.80\n")
    assert sorted(_names(intake.parse_text(csv))) == [(1, "Counterspell"), (2, "Sol Ring")]


# --------------------------------------------------------------------------- #
# Resolution — the one network call is injected
# --------------------------------------------------------------------------- #
def fake_verify(table):
    def verify(names):
        out = []
        for n in names:
            hit = table.get(n.lower())
            if hit is None:
                out.append({"found": False,
                            "reason": "no Scryfall match (exact or fuzzy) — treat the "
                                      "name as unverified"})
            elif hit == "offline":
                out.append({"found": False, "reason": "network unreachable: blocked"})
            else:
                out.append(dict({"found": True, "source": "scryfall", "price_usd": "1.00",
                                 "type_line": "Artifact", "color_identity": ""}, **hit))
        return out
    return verify


def test_resolve_marks_ok_suggest_missing_offline_and_basic():
    verify = fake_verify({
        "sol ring": {"name": "Sol Ring"},
        "sol rng": {"name": "Sol Ring", "source": "fuzzy"},          # a respelling
        "counterspel": {"name": "Countersquall", "source": "fuzzy"}, # a substitution
        "lightning bolt": "offline",
    })
    rows = intake.parse_text("1 sol ring\n1 Counterspel\n1 Nope Card\n"
                             "1 Lightning Bolt\n20 Island\n")
    got = {e["typed"][0]: e for e in intake.resolve(rows, verify=verify)}
    assert got["sol ring"]["status"] == "ok" and got["sol ring"]["name"] == "Sol Ring"
    assert got["Counterspel"]["status"] == "suggest"
    assert got["Counterspel"]["suggest"] == "Countersquall"
    assert got["Nope Card"]["status"] == "missing"
    assert got["Lightning Bolt"]["status"] == "offline", \
        "an unreachable Scryfall is never a verdict on the card"
    assert got["Island"]["status"] == "basic"


def test_a_spelling_repair_is_ok_but_a_different_card_needs_a_tick():
    verify = fake_verify({"sol rng": {"name": "Sol Ring", "source": "fuzzy"}})
    e = intake.resolve(intake.parse_text("1 Sol Rng"), verify=verify)[0]
    assert e["status"] == "suggest", "a fold-different fuzzy hit is a suggestion"
    verify = fake_verify({"lim-dul the necromancer":
                          {"name": "Lim-Dûl the Necromancer", "source": "fuzzy"}})
    e = intake.resolve(intake.parse_text("1 Lim-Dul the Necromancer"), verify=verify)[0]
    assert e["status"] == "ok", "accents are spelling noise, not a different card"


def test_a_back_face_name_resolves_to_the_whole_card_and_merges():
    full = "Delver of Secrets // Insectile Aberration"
    verify = fake_verify({"delver of secrets": {"name": full},
                          "insectile aberration": {"name": full}})
    rows = intake.parse_text("1 Delver of Secrets\n1 Insectile Aberration\n")
    out = [e for e in intake.resolve(rows, verify=verify) if e["status"] == "ok"]
    assert len(out) == 1 and out[0]["name"] == full and out[0]["qty"] == 2


def test_offline_names_the_collection_already_has_still_resolve():
    verify = fake_verify({"sol ring": "offline", "mana crypt": "offline"})
    known = intake.known_names([mtglib.Card(name="Sol Ring", quantity=1)])
    got = {e["typed"][0]: e for e in intake.resolve(
        intake.parse_text("1 sol ring\n1 Mana Crypt\n"), verify=verify, known=known)}
    assert got["sol ring"]["status"] == "ok" and got["sol ring"]["source"] == "local"
    assert got["Mana Crypt"]["status"] == "offline"


def test_duplicates_merge_and_accepted_writes_only_ok_and_ticked():
    verify = fake_verify({"sol ring": {"name": "Sol Ring"},
                          "sol rng": {"name": "Sol Ring", "source": "fuzzy"},
                          "arcane signet": {"name": "Arcane Signet"}})
    rows = intake.parse_text("2 Sol Ring\n1 sol ring\n1 Sol Rng\n1 Arcane Signet\n1 Nope\n")
    entries = intake.resolve(rows, verify=verify)
    assert intake.accepted(entries) == [(3, "Sol Ring"), (1, "Arcane Signet")]
    tick = next(i for i, e in enumerate(entries) if e["status"] == "suggest")
    assert intake.accepted(entries, [tick]) == [(4, "Sol Ring"), (1, "Arcane Signet")], \
        "a ticked suggestion that names a card already listed adds to its line"


def test_any_number_cards_are_read_from_the_oracle_text():
    verify = fake_verify({"relentless rats": {
        "name": "Relentless Rats",
        "oracle_text": "A deck can have any number of cards named Relentless Rats."}})
    e = intake.resolve(intake.parse_text("20 Relentless Rats"), verify=verify)[0]
    assert e["any_number"]
    r = intake.deck_report([e], "", {})
    assert r["singleton"] == []


# --------------------------------------------------------------------------- #
# The batch block — names and quantities only, appended, dated
# --------------------------------------------------------------------------- #
def test_append_batch_writes_one_dated_block_and_keeps_the_file(tmp_path):
    p = tmp_path / "owned_additions.txt"
    p.write_text("# header the player wrote\n1 Old Card\n", encoding="utf-8")
    copies, distinct = intake.append_batch(str(p), [(2, "Sol Ring"), (1, "Mana Crypt")],
                                           "pasted list", date="2026-10-20")
    text = p.read_text(encoding="utf-8")
    assert text.startswith("# header the player wrote\n1 Old Card\n")
    assert "# --- Batch 2026-10-20 · pasted list · 3 cards (2 distinct) ---" in text
    assert text.rstrip().endswith("2 Sol Ring\n1 Mana Crypt")
    assert (copies, distinct) == (3, 2)
    assert "$" not in text


def test_batch_block_refuses_line_breaking_names():
    block, copies, distinct = intake.batch_block(
        [(1, "Fake\n99 Mana Crypt"), (1, "# not a card"), (1, "Sol Ring")], "x")
    assert distinct == 1 and "Mana Crypt" not in block


def test_loader_dates_batch_rows_and_dated_comments(tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    (d / "collection.csv").write_text("Quantity,Name\n1,Sol Ring\n", encoding="utf-8")
    (d / "owned_additions.txt").write_text(
        "# 2026-10-07: photographed for a deck\n1 Mana Crypt\n"
        "# --- Batch 2026-10-12 · pasted list · 2 cards (2 distinct) ---\n"
        "1 Sol Ring\n1 Counterspell\n"
        "# retired 2026-10-20 (in export): 1 Brainstorm\n"
        "# --- Some other block ---\n1 Opt\n", encoding="utf-8")
    coll = {c.name: c for c in mtglib.load_collection(str(d / "collection.csv"))}
    assert coll["Mana Crypt"].date_added == "2026-10-07"
    assert coll["Counterspell"].date_added == "2026-10-12"
    assert coll["Sol Ring"].date_added == "2026-10-12" and coll["Sol Ring"].quantity == 2
    assert coll["Opt"].date_added == "", "a non-batch header ends the dated block"
    assert "Brainstorm" not in coll, "a retired row is a comment"


# --------------------------------------------------------------------------- #
# Reconcile on upload
# --------------------------------------------------------------------------- #
ADDS = ("# --- Batch 2026-10-12 · pasted list · 6 cards (3 distinct) ---\n"
        "1 Sol Ring\n3 Lightning Bolt\n2 Counterspell\n")


def _cards(**qty):
    return [mtglib.Card(name=n.replace("_", " "), quantity=q) for n, q in qty.items()]


def test_covered_rows_are_planned_and_a_partial_keeps_its_remainder():
    old = _cards(Opt=1)
    new = _cards(Opt=1, Sol_Ring=1, Lightning_Bolt=2)
    plan = intake.reconcile_plan(old, new, ADDS)
    assert [(p["name"], p["covered"], p["qty"]) for p in plan] == [
        ("Sol Ring", 1, 1), ("Lightning Bolt", 2, 3)]


def test_nothing_is_covered_when_the_export_did_not_grow():
    old = _cards(Sol_Ring=1)
    assert intake.reconcile_plan(old, _cards(Sol_Ring=1), ADDS) == []


def test_apply_retire_comments_out_and_never_deletes(tmp_path):
    p = tmp_path / "owned_additions.txt"
    p.write_text(ADDS, encoding="utf-8")
    plan = intake.reconcile_plan(_cards(), _cards(Sol_Ring=1, Lightning_Bolt=2), ADDS)
    retired, skipped = intake.apply_retire(str(p), plan, date="2026-10-20")
    text = p.read_text(encoding="utf-8")
    assert (retired, skipped) == (3, 0)
    assert "# retired 2026-10-20 (in export): 1 Sol Ring" in text
    assert "# retired 2026-10-20 (in export): 2 of 3 Lightning Bolt\n1 Lightning Bolt" in text
    assert "2 Counterspell" in text
    coll = {c.name: c.quantity for c in mtglib.parse_additions(text)}
    assert coll == {"Lightning Bolt": 1, "Counterspell": 2}, \
        "a retired row is no longer counted; the remainder still is"


def test_apply_retire_skips_a_row_that_changed_since_the_plan(tmp_path):
    p = tmp_path / "owned_additions.txt"
    p.write_text(ADDS, encoding="utf-8")
    plan = intake.reconcile_plan(_cards(), _cards(Sol_Ring=1), ADDS)
    p.write_text(ADDS.replace("1 Sol Ring", "2 Sol Ring"), encoding="utf-8")
    assert intake.apply_retire(str(p), plan) == (0, 1)
    assert "2 Sol Ring" in p.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Upload guard
# --------------------------------------------------------------------------- #
def test_a_small_file_against_a_big_collection_looks_partial():
    current = _cards(**{f"Card_{i}": 1 for i in range(100)})
    partial, facts = intake.upload_looks_partial(current, _cards(Card_1=1, New_One=1))
    assert partial and facts["file_unique"] == 2 and facts["current_unique"] == 100


def test_a_full_export_and_a_first_upload_are_not_partial():
    current = _cards(**{f"Card_{i}": 1 for i in range(100)})
    full = _cards(**{f"Card_{i}": 1 for i in range(95)}, New_One=1)
    assert not intake.upload_looks_partial(current, full)[0]
    assert not intake.upload_looks_partial([], _cards(Sol_Ring=1))[0]


# --------------------------------------------------------------------------- #
# Deck text + report
# --------------------------------------------------------------------------- #
def test_deck_text_sections_by_type_and_never_guesses():
    entries = {"Lyra Dawnbringer": {"type_line": "Legendary Creature — Angel"},
               "Fire // Ice": {"type_line": "Instant // Instant"},
               "Mystery Card": {"type_line": ""}}
    cards = [(1, "Giada, Font of Hope", {}), (1, "Lyra Dawnbringer", entries["Lyra Dawnbringer"]),
             (1, "Fire // Ice", entries["Fire // Ice"]), (1, "Mystery Card", entries["Mystery Card"]),
             (20, "Plains", {})]
    text = intake.deck_text(cards, "Giada, Font of Hope", title="Angels", colors="W", idx={})
    assert "# Commander: Giada, Font of Hope" in text and "# Colors: W" in text
    sections = [deckcore.section_label(ln) for ln in text.splitlines()
                if deckcore.section_label(ln)]
    assert sections[:4] == ["Commander", "Creatures", "Instants", "Basics"]
    assert sections[-1].startswith("Unsorted")
    assert sum(c.quantity for c in mtglib.parse_deck(text)) == 24


def test_deck_report_counts_ownership_identity_and_singleton():
    entries = [
        {"name": "Giada, Font of Hope", "status": "ok", "qty": 1, "identity": "W", "section": ""},
        {"name": "Sol Ring", "status": "ok", "qty": 1, "identity": "", "section": ""},
        {"name": "Counterspell", "status": "ok", "qty": 2, "identity": "U", "section": ""},
        {"name": "Plains", "status": "basic", "qty": 30, "identity": "", "section": ""},
        {"name": "Path to Exile", "status": "ok", "qty": 1, "identity": "W",
         "section": "sideboard"},
    ]
    idx = mtglib.index_by_name([mtglib.Card(name="Sol Ring", quantity=1),
                                mtglib.Card(name="Giada, Font of Hope", quantity=1)])
    r = intake.deck_report(entries, "Giada, Font of Hope", idx, identity={"W"},
                           committed={"sol ring": {"other-deck": 1}})
    assert r["total"] == 34
    assert r["singleton"] == ["Counterspell"]
    assert r["off_identity"] == ["Counterspell"]
    assert [u["name"] for u in r["unowned"]] == ["Counterspell"]
    assert [u["name"] for u in r["shared"]] == ["Sol Ring"]
    assert r["left_out"] == ["Path to Exile"]


def test_cli_parses_and_resolves_from_a_verified_file(tmp_path, capsys):
    import json
    lst = tmp_path / "list.txt"
    lst.write_text("2 Sol Ring\n1 Nope\n", encoding="utf-8")
    ver = tmp_path / "v.json"
    ver.write_text(json.dumps([{"requested": "Sol Ring", "found": True, "name": "Sol Ring",
                                "price_usd": "1.00", "type_line": "Artifact",
                                "color_identity": ""}]), encoding="utf-8")
    adds = tmp_path / "adds.txt"
    rc = intake.main([str(lst), "--verified", str(ver), "--write", "--additions", str(adds)])
    assert rc == 3 and not adds.exists(), "an unresolved line blocks the write"
    lst.write_text("2 Sol Ring\n", encoding="utf-8")
    assert intake.main([str(lst), "--verified", str(ver), "--write",
                        "--additions", str(adds)]) == 0
    assert "2 Sol Ring" in adds.read_text(encoding="utf-8")
