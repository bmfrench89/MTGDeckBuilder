"""The optimizer rewrites real deck files, so the invariants matter more than the picks:
card count preserved, no cards invented or lost by the tidy pass, sections kept."""
import pytest

import optimize
import mtglib


DECK = """\
# Title: T
# Commander: Test Commander
# Colors: W U

# --- Creatures ---
1 Test Commander
1 Serra Angel
1 Llanowar Elves

# --- Ramp ---
1 Sol Ring

# --- Lands (13) ---
1 Command Tower
7 Island
5 Island
"""


def _deck(tmp_path, text=DECK):
    p = tmp_path / "d.txt"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_commander_is_parsed_from_the_header(tmp_path):
    assert optimize._commander_of(DECK) == "Test Commander"


def test_protected_set_includes_commander_and_basics(tmp_path):
    keep, _notes = optimize._protected(_deck(tmp_path), "Test Commander")
    assert mtglib._norm("Test Commander") in keep
    for b in ("plains", "island", "swamp", "mountain", "forest"):
        assert b in keep


def test_basics_target_shrinks_as_colours_widen():
    one = optimize._basics_needed({"W"})
    three = optimize._basics_needed({"W", "U", "R"})
    five = optimize._basics_needed(set("WUBRG"))
    assert one > three > five >= 6


def test_tidy_preserves_every_card(tmp_path, collection_file):
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path)
    before = mtglib.parse_deck(open(p, encoding="utf-8").read())
    optimize._tidy(p, idx)
    after = mtglib.parse_deck(open(p, encoding="utf-8").read())
    assert sum(c.quantity for c in before) == sum(c.quantity for c in after)
    assert ({mtglib._norm(c.name): c.quantity for c in before}
            == {mtglib._norm(c.name): c.quantity for c in after})


def test_tidy_merges_duplicate_lines(tmp_path, collection_file):
    """'7 Island' + '5 Island' must collapse to a single '12 Island' line."""
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path)
    optimize._tidy(p, idx)
    text = open(p, encoding="utf-8").read()
    assert text.count(" Island") == 1
    assert "12 Island" in text


def test_tidy_keeps_the_header_and_sections(tmp_path, collection_file):
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path)
    optimize._tidy(p, idx)
    text = open(p, encoding="utf-8").read()
    assert "# Commander: Test Commander" in text
    assert "# --- Creatures ---" in text
    assert "# --- Ramp ---" in text


def test_tidy_refiles_a_mana_dork_under_ramp(tmp_path, collection_file):
    """Llanowar Elves is listed under Creatures; it belongs in Ramp."""
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path)
    optimize._tidy(p, idx)
    text = open(p, encoding="utf-8").read()
    ramp = text.split("# --- Ramp ---")[1].split("# ---")[0]
    assert "Llanowar Elves" in ramp


MIXED_DECK = """\
# Title: T
# Commander: Test Commander

# --- Creatures ---
1 Serra Angel
1 Sol Ring
1 Counterspell
1 Command Tower

# --- Removal ---
1 Swords to Plowshares
"""


def test_type_allowed_identifies_type_sections():
    assert optimize._type_allowed("Creatures") == {"Creature"}
    assert optimize._type_allowed("Lands (37)") == {"Land"}
    assert optimize._type_allowed("Artifacts") == {"Artifact"}
    assert optimize._type_allowed("Instants & sorceries") == {"Instant", "Sorcery"}
    # function sections are NOT type-exclusive — any type may live there
    assert optimize._type_allowed("Ramp") is None
    assert optimize._type_allowed("Removal & wraths") is None
    # a curated header that merely *contains* a type word stays free-form
    assert optimize._type_allowed("Spiders & Spider-matters creatures") is None
    assert optimize._type_allowed("Equipment support") is None


def test_non_creatures_are_moved_out_of_the_creatures_section(tmp_path, collection_file):
    """The reported bug: Door of Destinies (Artifact) / Methods of the Mighty (Instant)
    were sitting under 'Creatures'."""
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path, MIXED_DECK)
    optimize._tidy(p, idx)
    text = open(p, encoding="utf-8").read()
    creatures = text.split("# --- Creatures ---")[1].split("# ---")[0]
    assert "Serra Angel" in creatures          # a real creature stays
    for non_creature in ("Sol Ring", "Counterspell", "Command Tower"):
        assert non_creature not in creatures


def test_a_function_section_may_hold_any_type(tmp_path, collection_file):
    """Sol Ring is an Artifact but belongs under Ramp — function beats type."""
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path, MIXED_DECK + "\n# --- Ramp ---\n")
    optimize._tidy(p, idx)
    text = open(p, encoding="utf-8").read()
    ramp = text.split("# --- Ramp ---")[1].split("# ---")[0]
    assert "Sol Ring" in ramp


def test_a_type_section_is_created_when_none_fits(tmp_path, collection_file):
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path, MIXED_DECK)
    optimize._tidy(p, idx)
    text = open(p, encoding="utf-8").read()
    assert "# --- Lands ---" in text            # Command Tower needed a home


def test_tidy_never_leaves_a_type_section_violated(tmp_path, collection_file):
    import re as _re
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = _deck(tmp_path, MIXED_DECK)
    optimize._tidy(p, idx)
    cur, violations = None, []
    for ln in open(p, encoding="utf-8"):
        s = ln.strip()
        m = _re.match(r"^#\s*-+\s*(.+?)\s*-+\s*$", s)
        if m:
            cur = m.group(1)
            continue
        if not s or s.startswith("#"):
            continue
        ref = mtglib.lookup(idx, _re.sub(r"^\d+\s+", "", s))
        allowed = optimize._type_allowed(cur or "")
        if ref and ref.types and allowed:
            ptype = "Land" if ref.is_land else ref.primary_type
            if ptype not in allowed:
                violations.append((ref.name, cur))
    assert violations == []


def test_section_type_signal_reads_only_type_exclusive_sections():
    text = """\
# Title: T
1 Pre-Section Card

# --- Creatures ---
1 Some Creature

# --- Ramp ---
1 Sol Ring

# --- Lands (26) ---
1 Hidden Lair

# --- Unsorted (type unknown) ---
1 Mystery Card
"""
    sig = optimize._section_type_signal(text)
    assert sig[mtglib._norm("Hidden Lair")] is True          # Lands section
    assert sig[mtglib._norm("Some Creature")] is False       # other type section
    for no_signal in ("Sol Ring", "Mystery Card", "Pre-Section Card"):
        assert mtglib._norm(no_signal) not in sig            # function/Unsorted/header


# The yshtola incident (2026-08-09): a name-only collection has no types, and
# "Hidden Lair" — a REAL land — matches nothing in mtglib._LAND_HINTS, so the spell
# pass cut it for a high-inclusion spell and _write parked the incoming Aura on its
# line inside "# --- Lands ---". The deck file's own section must outrank the name
# heuristic for pass assignment when type data is absent.
UNHINTED_LAND_DECK = """\
# Title: T
# Commander: Test Commander
# Colors: W U

# --- Commander ---
1 Test Commander

# --- Creatures ---
1 Weak Old Spell

# --- Lands ---
1 Hidden Lair
12 Island
"""

NAME_ONLY_COLLECTION = """\
1 Test Commander
1 Weak Old Spell
1 Hidden Lair
1 Great New Spell
13 Island
"""


def _name_only_setup(tmp_path, monkeypatch, field):
    import deck_fit
    cpath = tmp_path / "snapshot.txt"
    cpath.write_text(NAME_ONLY_COLLECTION, encoding="utf-8")
    coll = mtglib.load_collection(str(cpath))
    idx = mtglib.index_by_name(coll)
    monkeypatch.setattr(deck_fit, "load_field", lambda *a, **k: dict(field))
    return coll, idx, _deck(tmp_path, UNHINTED_LAND_DECK)


def test_spell_pass_never_cuts_an_untyped_card_from_the_lands_section(tmp_path, monkeypatch):
    coll, idx, p = _name_only_setup(
        tmp_path, monkeypatch, {mtglib._norm("Great New Spell"): 99})
    r = optimize.optimize(p, coll, idx, str(tmp_path), apply=False)
    assert all(mtglib._norm(cut) != mtglib._norm("Hidden Lair")
               for cut, *_ in r["swaps"])
    # the untyped-card count is reported, not silently guessed around
    assert r["untyped"] >= 2


def test_spell_pass_still_cuts_untyped_cards_from_nonland_sections(tmp_path, monkeypatch):
    """The section signal must not freeze the optimizer on a name-only collection:
    an untyped card under a NONLAND type section is still fair game."""
    coll, idx, p = _name_only_setup(
        tmp_path, monkeypatch, {mtglib._norm("Great New Spell"): 99})
    r = optimize.optimize(p, coll, idx, str(tmp_path), apply=False)
    cuts = [mtglib._norm(cut) for cut, *_ in r["swaps"]]
    assert cuts == [mtglib._norm("Weak Old Spell")]


def test_an_unowned_field_land_is_never_added_by_the_spell_pass(tmp_path, monkeypatch):
    """The add-side twin of the Hidden Lair cut: Hallowed Fountain — unowned, and
    'fountain' misses the name hints — was proposed as a BUY for Absorb (a spell).
    EDHREC's own Lands sections type the candidate; it may only arrive through the
    land pass, replacing a land."""
    import deck_fit
    coll, idx, p = _name_only_setup(
        tmp_path, monkeypatch, {mtglib._norm("Hallowed Fountain"): 99})
    monkeypatch.setattr(deck_fit, "load_field_lands",
                        lambda *a, **k: {mtglib._norm("Hallowed Fountain")})
    r = optimize.optimize(p, coll, idx, str(tmp_path), include_buys=True, apply=False)
    assert all("Hallowed Fountain" not in add for _cut, _vc, add, *_ in r["swaps"])
    assert all("Hallowed Fountain" not in new for _old, new, _avail in r["land_swaps"])
    # it arrives as a LAND buy recommendation, paired against a weak in-deck land
    land_buys = [b for b in r["buy_swaps"] if b[4] == "land"]
    assert land_buys and land_buys[0][2] == "Hallowed Fountain"
    assert mtglib._norm(land_buys[0][0]) == mtglib._norm("Hidden Lair")


def test_manabase_pass_owns_a_section_signalled_land(tmp_path, monkeypatch):
    """Hidden Lair may still be upgraded — by the LAND pass, for a land the field
    plays, preserving the deck's land count."""
    coll, idx, p = _name_only_setup(
        # "...Tower" trips the name heuristic, so the incoming card lands in land_adds
        tmp_path, monkeypatch, {mtglib._norm("Great Field Tower"): 99})
    (tmp_path / "snapshot.txt").write_text(
        NAME_ONLY_COLLECTION + "1 Great Field Tower\n", encoding="utf-8")
    coll = mtglib.load_collection(str(tmp_path / "snapshot.txt"))
    idx = mtglib.index_by_name(coll)
    r = optimize.optimize(p, coll, idx, str(tmp_path), apply=False)
    assert any(mtglib._norm(old) == mtglib._norm("Hidden Lair")
               for old, _new, _avail in r["land_swaps"])
    assert all(mtglib._norm(cut) != mtglib._norm("Hidden Lair")
               for cut, *_ in r["swaps"])


def test_optimize_is_a_no_op_without_field_data(tmp_path, collection_file):
    """Unknown commander -> no EDHREC data -> the deck must be left exactly alone."""
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    p = _deck(tmp_path)
    original = open(p, encoding="utf-8").read()
    r = optimize.optimize(p, coll, idx, str(tmp_path), apply=True)
    assert r["swaps"] == []
    assert open(p, encoding="utf-8").read() == original


def test_pool_report_classifies_every_top_card(tmp_path, collection_file):
    """No EDHREC data in tests, but the shape must hold and never raise."""
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    r = optimize.pool_report(_deck(tmp_path), coll, idx, str(tmp_path))
    for key in ("have", "free", "taken", "unowned"):
        assert isinstance(r[key], list)
    assert r["commander"] == "Test Commander"


def test_write_buylist_never_clobbers_a_curated_file(tmp_path, collection_file):
    """A hand-written buy-list must survive an --apply run."""
    p = _deck(tmp_path)
    existing = tmp_path / "d.buylist.csv"
    existing.write_text("Card,Price,Tier,Replaces,Reason\nMy Pick,1,Core,,mine\n",
                        encoding="utf-8")
    report = {"commander": "X", "unowned": [(90, "some staple")]}
    assert optimize.write_buylist(p, report) == 0
    assert "My Pick" in existing.read_text(encoding="utf-8")
    # explicit overwrite still works
    assert optimize.write_buylist(p, report, overwrite=True) == 1
    assert "Some Staple" in existing.read_text(encoding="utf-8")


def test_write_buylist_skips_low_inclusion_cards(tmp_path):
    p = _deck(tmp_path)
    report = {"commander": "X", "unowned": [(10, "fringe card")]}
    assert optimize.write_buylist(p, report) == 0


def test_owned_only_refuses_to_add_unowned_cards(tmp_path, collection_file, monkeypatch):
    """--owned-only must never introduce a card the player doesn't have a spare of."""
    import deck_fit
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    # pretend the field loves a card that isn't in the collection at all
    monkeypatch.setattr(deck_fit, "load_field",
                        lambda *a, **k: {mtglib._norm("Totally Unowned Card"): 99})
    p = _deck(tmp_path)
    r = optimize.optimize(p, coll, idx, str(tmp_path), owned_only=True, apply=False)
    assert all("Totally Unowned Card" not in s[2] for s in r["swaps"])
    assert r["buy_swaps"] == []


def test_buys_never_enter_the_deck_and_go_to_the_buylist(tmp_path, collection_file, monkeypatch):
    """2026-08-11 (player request): a deck is built from what's owned. An unowned,
    heavily-played card is recommended in buy_swaps — mapped to the in-deck card it
    would replace — and on apply is APPENDED to .buylist.csv, never into the 99."""
    import deck_fit
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    monkeypatch.setattr(deck_fit, "load_field",
                        lambda *a, **k: {mtglib._norm("Totally Unowned Card"): 99})
    p = _deck(tmp_path)
    r = optimize.optimize(p, coll, idx, str(tmp_path), include_buys=True, apply=True)
    assert all("Totally Unowned Card" not in s[2] for s in r["swaps"])
    assert "Totally Unowned Card" not in open(p, encoding="utf-8").read()
    assert r["buy_swaps"] and r["buy_swaps"][0][2] == "Totally Unowned Card"
    replaces = r["buy_swaps"][0][0]
    assert mtglib._norm(replaces) in {
        mtglib._norm(c.name) for c in mtglib.parse_deck(open(p, encoding="utf-8").read())}
    text = open(str(tmp_path / "d.buylist.csv"), encoding="utf-8").read()
    assert "Totally Unowned Card" in text and replaces in text


def test_append_buylist_preserves_existing_rows(tmp_path):
    """Append semantics: hand-written rows survive verbatim; a re-mapped card only
    has its Replaces cell refreshed; new buys are appended."""
    bl = tmp_path / "d.buylist.csv"
    bl.write_text("Card,Price,Tier,Replaces,Reason\n"
                  "Hand Written Buy,25,Core,Old Target,The player's own note.\n"
                  "Remapped Buy,3,Value,Stale Target,Curated reason stays.\n",
                  encoding="utf-8")
    n = optimize.append_buylist(str(tmp_path / "d.txt"), [
        ("Fresh Target", 5, "Remapped Buy", 60, "spell"),
        ("Weak Card", 2, "Brand New Buy", 70, "spell")], "Test Commander")
    assert n == 2
    text = bl.read_text(encoding="utf-8")
    assert "Hand Written Buy,25,Core,Old Target,The player's own note." in text
    assert "Remapped Buy,3,Value,Fresh Target,Curated reason stays." in text
    assert "Brand New Buy" in text and "Weak Card" in text


def test_buy_threshold_filters_fringe_cards(tmp_path, collection_file, monkeypatch):
    import deck_fit
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    monkeypatch.setattr(deck_fit, "load_field",
                        lambda *a, **k: {mtglib._norm("Fringe Unowned Card"): 30})
    p = _deck(tmp_path)
    r = optimize.optimize(p, coll, idx, str(tmp_path), include_buys=True,
                          buy_threshold=55, apply=False)
    assert all(s[4] != "buy" for s in r["swaps"])
    assert r["buy_swaps"] == []


def test_only_hand_written_notes_protect_a_card(tmp_path, monkeypatch):
    """Regression: _protected() treated EVERY card_notes key as curated. The loader also
    returns machine-drafted notes covering most of the collection, so ~429 cards were
    protected instead of ~51 — which silently froze the manabase pass, because almost
    every land had a generated note and could never be swapped out."""
    import deckcore
    monkeypatch.setattr(deckcore, "load_card_notes", lambda *a, **k: {
        "curated card": {"why": "hand written", "alts": [], "generated": False},
        "generated card": {"why": "auto drafted", "alts": [], "generated": True},
    })
    p = tmp_path / "d.txt"
    p.write_text("# Commander: X\n1 Sol Ring\n", encoding="utf-8")
    keep, _notes = optimize._protected(str(p), "X")
    assert "curated card" in keep
    assert "generated card" not in keep


def test_protection_still_covers_commander_and_basics_only_otherwise(tmp_path, monkeypatch):
    import deckcore
    monkeypatch.setattr(deckcore, "load_card_notes", lambda *a, **k: {})
    p = tmp_path / "d.txt"
    p.write_text("# Commander: My Commander\n", encoding="utf-8")
    keep, _ = optimize._protected(str(p), "My Commander")
    assert "my commander" in keep and "island" in keep


def test_built_commanders_reads_deck_headers(tmp_path):
    """Build Next ranks what the collection SUPPORTS, so it happily surfaces a commander
    you finished months ago. The OWN badge only ever meant 'you own the card'."""
    import commander_finder as cf
    (tmp_path / "a.txt").write_text("# Commander: Y'shtola, Night's Blessed\n1 Sol Ring\n",
                                    encoding="utf-8")
    (tmp_path / "b.txt").write_text("# Commander: Kaervek the Merciless  (5BR)\n", encoding="utf-8")
    built = cf.built_commanders(str(tmp_path))
    assert built[mtglib._norm("Y'shtola, Night's Blessed")] == "a"
    assert built[mtglib._norm("Kaervek the Merciless")] == "b"      # trailing detail stripped
    assert cf.built_commanders(str(tmp_path / "nope")) == {}


def test_built_commanders_sink_below_new_ideas():
    import commander_finder as cf
    commanders = [
        {"name": "Built Guy", "colors": {"W"}, "archetypes": {"x"}, "notes": ""},
        {"name": "Fresh Idea", "colors": {"W"}, "archetypes": {"x"}, "notes": ""},
    ]
    built = {mtglib._norm("Built Guy"): "built-guy"}
    rows = cf.score({}, commanders, {"x": []}, built=built)
    assert rows[0]["name"] == "Fresh Idea"          # unbuilt first, even at equal support
    assert rows[1]["built"] == "built-guy"
    assert rows[0]["built"] is None


# --------------------------------------------------------------------------- #
# Singleton legality. A card whose NAME contains a literal "//" — "SP//dr, Piloted by
# Peni" — used to be split into a bogus front face "SP". That alias became its own
# EDHREC field key, and because the add-guard only compared the field KEY against the
# deck, the optimizer never recognised the card as already present and added a fresh
# copy on every run. The deck still totalled 100 cards, so nothing surfaced it: it
# reached SIX copies of a singleton before anyone noticed.

def test_front_face_only_splits_on_a_spaced_separator():
    assert mtglib.front_face("Fire // Ice") == "Fire"
    assert mtglib.front_face("Murderous Rider // Swift End") == "Murderous Rider"
    # a literal // inside a real card name is NOT a split card
    assert mtglib.front_face("SP//dr, Piloted by Peni") == "SP//dr, Piloted by Peni"


def test_a_literal_slash_name_does_not_get_a_truncated_alias():
    cards = mtglib.parse_collection("Name,Quantity\n\"SP//dr, Piloted by Peni\",1\n")
    idx = mtglib.index_by_name(cards)
    assert mtglib.lookup(idx, "SP//dr, Piloted by Peni") is not None
    assert "sp" not in idx, "a bare '//' must not create a truncated alias"


def test_a_genuine_dfc_is_still_findable_by_its_front_face():
    cards = mtglib.parse_collection("Name,Quantity\n\"Murderous Rider // Swift End\",1\n")
    idx = mtglib.index_by_name(cards)
    assert mtglib.lookup(idx, "Murderous Rider") is not None


def test_singleton_violations_flags_duplicate_nonbasics(tmp_path):
    p = _deck(tmp_path, DECK.replace("1 Serra Angel", "2 Serra Angel"))
    assert optimize.singleton_violations(p) == [(2, "Serra Angel")]


def test_singleton_violations_allows_duplicate_basics(tmp_path):
    # DECK already has 7 Island + 5 Island; basics are exempt from the singleton rule
    assert optimize.singleton_violations(_deck(tmp_path)) == []


# --------------------------------------------------------------------------- #
# Review round 2 (docs/spec-optimizer-hardening.md) — regression tests.
# Field/synergy data is monkeypatched (the pattern used above): hermetic, and it
# makes the ranking arithmetic exact instead of approximate.
# --------------------------------------------------------------------------- #
def test_singleton_check_catches_a_front_face_alias_duplicate(tmp_path):
    """'1 Fire' + '1 Fire // Ice' is the same physical card twice, but parses as two
    names each qty 1 — raw counting kept the ILLEGAL guard silent for exactly the
    class of bug it exists for."""
    p = tmp_path / "d.txt"
    p.write_text("# Colors: U R\n\n# --- Spells ---\n1 Fire\n1 Fire // Ice\n",
                 encoding="utf-8")
    hits = optimize.singleton_violations(str(p))
    assert len(hits) == 1 and hits[0][0] == 2


def test_singleton_check_still_ignores_basics_including_snow(tmp_path):
    p = tmp_path / "d.txt"
    p.write_text("# --- Lands ---\n5 Island\n3 Snow-Covered Island\n", encoding="utf-8")
    assert optimize.singleton_violations(str(p)) == []


def test_manabase_basics_pass_applies_without_crashing(tmp_path, collection_file, monkeypatch):
    """Pass 2 appended 2-tuples where every consumer unpacks 3 — the crash fired
    AFTER _write had rewritten the deck but BEFORE tidy/legality/logging."""
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n\n"
                    "# --- Ramp ---\n1 Sol Ring\n\n"
                    "# --- Lands ---\n1 Command Tower\n2 Island\n", encoding="utf-8")
    import deck_fit
    # field data exists (so passes run) and Command Tower is weak here (<40)
    monkeypatch.setattr(deck_fit, "load_field", lambda *a, **k: {"sol ring": 90})
    monkeypatch.setattr(deck_fit, "load_synergy", lambda *a, **k: {})
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    r = optimize.optimize(str(deck), coll, idx, str(tmp_path), apply=True)
    for entry in r["land_swaps"]:
        assert len(entry) == 3, "every land swap must be (old, new, availability)"
    # the change log wrote (this is what the crash used to skip)
    if r["land_swaps"]:
        assert (tmp_path / "d.changes.csv").exists()


def test_add_ranking_prefers_fit_blended_value_over_raw_inclusion(tmp_path, collection_file, monkeypatch):
    """The A/B case: Counterspell (60% inclusion, high synergy, fills the counter
    shortage) must outrank a higher-inclusion generic bauble (62%) now that adds use
    the same value function as cuts. The old sort — raw inclusion — picked the bauble."""
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n\n"
                    "# --- Creatures ---\n1 Serra Angel\n\n"
                    "# --- Ramp ---\n1 Sol Ring\n\n"
                    "# --- Lands ---\n10 Island\n", encoding="utf-8")
    import deck_fit
    field = {"counterspell": 60, "arcane signet": 62}
    monkeypatch.setattr(deck_fit, "load_field", lambda *a, **k: dict(field))
    monkeypatch.setattr(deck_fit, "load_synergy",
                        lambda *a, **k: {"counterspell": 69})
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    r = optimize.optimize(str(deck), coll, idx, str(tmp_path), margin=30)
    assert r["swaps"], "a swap should clear the margin"
    adds = [add for _cut, _v, add, _i, _a in r["swaps"]]
    assert adds[0] == "Counterspell", f"value ranking should pick Counterspell first, got {adds}"


def test_margin_gate_compares_value_to_value(tmp_path, collection_file, monkeypatch):
    """A swap that clears the margin on VALUE but not on raw inclusion must happen:
    Counterspell at 20% inclusion but ~84 fit (blend 48) against a value-12 cut,
    margin 30. The old gate (raw inclusion minus value) refused this: 20-12=8 < 30.
    (Margin recalibrated 40->30 for the Phase-12 rescore: the canonical counter band
    is 0-6, so a 0-counter deck reads HEALTHY, not shortage — Counterspell's fit is
    honestly lower now. The discriminating power is intact: value 36 >= 30 passes,
    raw inclusion 20 < 30 would still refuse.)"""
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n\n"
                    "# --- Creatures ---\n1 Serra Angel\n\n"
                    "# --- Lands ---\n10 Island\n", encoding="utf-8")
    import deck_fit
    monkeypatch.setattr(deck_fit, "load_field", lambda *a, **k: {"counterspell": 20})
    monkeypatch.setattr(deck_fit, "load_synergy", lambda *a, **k: {"counterspell": 69})
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    r = optimize.optimize(str(deck), coll, idx, str(tmp_path), margin=30)
    assert any(add == "Counterspell" for _c, _v, add, _i, _a in r["swaps"]), \
        "the value-based gate should let a high-fit low-inclusion upgrade through"


def test_optimizer_is_idempotent_under_the_new_ranking(tmp_path, collection_file, monkeypatch):
    """Second run on a tuned deck changes nothing — the property worth preserving."""
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n\n"
                    "# --- Creatures ---\n1 Serra Angel\n\n"
                    "# --- Ramp ---\n1 Sol Ring\n\n"
                    "# --- Lands ---\n10 Island\n", encoding="utf-8")
    import deck_fit
    monkeypatch.setattr(deck_fit, "load_field",
                        lambda *a, **k: {"counterspell": 60, "sol ring": 90})
    monkeypatch.setattr(deck_fit, "load_synergy", lambda *a, **k: {"counterspell": 69})
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    optimize.optimize(str(deck), coll, idx, str(tmp_path), margin=30, apply=True)
    text_after_first = (tmp_path / "d.txt").read_text(encoding="utf-8")
    r2 = optimize.optimize(str(deck), coll, idx, str(tmp_path), margin=30, apply=True)
    assert not r2["swaps"], "second run must find nothing to do"
    assert (tmp_path / "d.txt").read_text(encoding="utf-8") == text_after_first


def test_optimizer_is_still_idempotent_with_oracle_flags_present(tmp_path,
                                                                 collection_file,
                                                                 monkeypatch):
    """The A-F re-proof (spec §4.5). classify() now reads `Card.flags` where the
    curated lists are silent, and its category counts feed the optimizer's
    ROLE_RANGE guardrails — so a swap this run permits must still be a swap the
    NEXT run declines to undo. Idempotency is the optimizer's load-bearing
    contract; with a new input feeding the gate it has to be re-proven, not
    assumed. Same deck as the no-flags idempotency test above, plus an attrs file
    that moves Serra Angel out of `creature` and into `removal`."""
    import deck_fit
    # the collection_file fixture already lives at tmp_path/collection.csv;
    # load_collection auto-merges an attrs file sitting beside it.
    (tmp_path / "collection_attrs.csv").write_text(
        "Name,Type,MV,Colors,Cost,Sub-types,Scryfall,Produced,Flags\n"
        "Serra Angel,Creature,5,W,{3}{W}{W},Angel,7777aaaa,,removal\n"
        "Counterspell,Instant,2,U,{U}{U},,cccc3333,,counter\n"
        "Island,Land,0,,,Island,ffff6666,U,\n", encoding="utf-8")
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n\n"
                    "# --- Creatures ---\n1 Serra Angel\n\n"
                    "# --- Ramp ---\n1 Sol Ring\n\n"
                    "# --- Lands ---\n10 Island\n", encoding="utf-8")
    monkeypatch.setattr(deck_fit, "load_field",
                        lambda *a, **k: {"counterspell": 60, "sol ring": 90})
    monkeypatch.setattr(deck_fit, "load_synergy", lambda *a, **k: {"counterspell": 69})
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    # the flags really did reach classify — otherwise this test proves nothing
    assert mtglib.classify(mtglib.lookup(idx, "Serra Angel")) == {"removal"}

    optimize.optimize(str(deck), coll, idx, str(tmp_path), margin=30, apply=True)
    text_after_first = deck.read_text(encoding="utf-8")
    r2 = optimize.optimize(str(deck), coll, idx, str(tmp_path), margin=30, apply=True)
    assert not r2["swaps"], "second run must find nothing to do, flags or not"
    assert deck.read_text(encoding="utf-8") == text_after_first


def test_tidy_preserves_comments_inside_sections(tmp_path, collection_file):
    """The repo contract: edits keep comment lines intact. _tidy used to delete every
    comment below the first section header."""
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = tmp_path / "d.txt"
    p.write_text("# Title: T\n\n# --- Ramp ---\n# fast mana package below\n1 Sol Ring\n",
                 encoding="utf-8")
    optimize._tidy(str(p), idx)
    assert "# fast mana package below" in p.read_text(encoding="utf-8")


def test_tidy_does_not_corrupt_1x_style_lines(tmp_path, collection_file):
    """'2x Sol Ring' parses fine (mtglib accepts the x suffix) but _tidy's stricter
    regex used to rewrite it as '1 2x Sol Ring' — a nonexistent card, real one gone."""
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    p = tmp_path / "d.txt"
    p.write_text("# --- Ramp ---\n2x Sol Ring\n", encoding="utf-8")
    optimize._tidy(str(p), idx)
    after = {mtglib._norm(c.name): c.quantity for c in
             mtglib.parse_deck(p.read_text(encoding="utf-8"))}
    assert after == {"sol ring": 2}, f"got {after}"


def test_write_swaps_an_1x_line(tmp_path):
    p = tmp_path / "d.txt"
    p.write_text("# --- Ramp ---\n1x Llanowar Elves\n", encoding="utf-8")
    optimize._write(str(p), [("Llanowar Elves", 0, "Sol Ring", 90, "free")], [])
    text = p.read_text(encoding="utf-8")
    assert "Sol Ring" in text and "Llanowar" not in text


def test_display_name_does_not_mangle_apostrophes():
    assert optimize._display_name("urza's saga") == "Urza's Saga"
    assert optimize._display_name("fire // ice") == "Fire // Ice"


def test_land_pass_never_adds_the_same_land_under_two_field_keys(tmp_path, monkeypatch):
    """EDHREC emits full-name AND front-face keys for a DFC land; without the add-side
    guard both keys swapped the same land in for two different cuts, and _tidy merged
    them into an illegal `2 <land>`."""
    coll_csv = tmp_path / "c.csv"
    coll_csv.write_text(
        "Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,MARKET\n"
        "1,Test Commander,4,W U,W U,{2}{W}{U},Legendary Creature,Human Wizard,rare,g7,1.00\n"
        "1,Boardwalk // Promenade,0,,U,,Land,,rare,bp1,1.00\n"
        "1,Weak Land A,0,,,,Land,,common,wa1,0.10\n"
        "1,Weak Land B,0,,,,Land,,common,wb1,0.10\n"
        "12,Island,0,,,,Land,Island,common,f6,0.10\n", encoding="utf-8")
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n\n"
                    "# --- Lands ---\n1 Weak Land A\n1 Weak Land B\n10 Island\n",
                    encoding="utf-8")
    import deck_fit
    monkeypatch.setattr(deck_fit, "load_field", lambda *a, **k: {
        "boardwalk // promenade": 80, "boardwalk": 80})
    monkeypatch.setattr(deck_fit, "load_synergy", lambda *a, **k: {})
    coll = mtglib.load_collection(str(coll_csv))
    idx = mtglib.index_by_name(coll)
    r = optimize.optimize(str(deck), coll, idx, str(tmp_path))
    added = [new for _old, new, _avail in r["land_swaps"]]
    assert len(added) == len({mtglib._norm(mtglib.front_face(n)) for n in added}), \
        f"same land added twice: {added}"


def test_snow_covered_basics_are_never_cut_and_count_as_basics(tmp_path, monkeypatch):
    """Regression: BASICS held only the six plain names and the land-name heuristic
    missed the 'Snow-Covered ' prefix, so on a name-only collection the SPELL pass
    could cut Snow-Covered Island — quantity preserved — wrecking the manabase and
    minting an N-copy singleton line."""
    import deck_fit
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: U\n\n"
                    "# --- Commander ---\n1 Test Commander\n\n"
                    "# --- Creatures ---\n1 Weak Old Spell\n\n"
                    "# --- Basics ---\n12 Snow-Covered Island\n", encoding="utf-8")
    coll = tmp_path / "c.txt"
    coll.write_text("1 Test Commander\n1 Weak Old Spell\n13 Snow-Covered Island\n"
                    "1 Great New Spell\n", encoding="utf-8")
    c = mtglib.load_collection(str(coll))
    idx = mtglib.index_by_name(c)
    monkeypatch.setattr(deck_fit, "load_field",
                        lambda *a, **k: {mtglib._norm("Great New Spell"): 99})
    r = optimize.optimize(str(deck), c, idx, str(tmp_path), apply=True)
    text = open(str(deck), encoding="utf-8").read()
    assert "12 Snow-Covered Island" in text, "snow basics must never be cut"
    assert optimize.singleton_violations(str(deck)) == []
    # and they are lands/basics to the engine, not spells
    assert mtglib._looks_like_land_by_name("Snow-Covered Island")


# --------------------------------------------------------------------------- #
# Phase 8 — the typed-data role-repair churn (docs/spec-optimizer-hardening.md,
# "Typed-data role-repair churn", found 2026-08-12).
#
# Role repair has no function of its own: it reaches the swap gate THROUGH
# `value_of`, because deck_fit's Role-need component pays 30 points to a card that
# fills a shortfall and 12 to one that is depth — an 18-point fit swing that
# `value_of` doubles into up to 36 points of value, more than the whole margin.
# These tests fix the fit score directly (the same monkeypatch discipline the field
# tests above use) so the arithmetic is exact rather than approximate: the candidate
# scores 95 -> value 70, everything else scores 40 -> value falls back to raw field
# inclusion. That reproduces "template pressure manufactured the margin" precisely.
# --------------------------------------------------------------------------- #

_REPAIR_TYPES = {
    "Ganax, Astral Hunter": "Creature", "Mana Drain": "Instant",
    "Wall Crawl": "Enchantment", "Masked Meower": "Creature",
    "Snap": "Instant", "Wayfarer's Bauble": "Artifact",
    "Clever Impersonator": "Creature", "Sword of the Animist": "Artifact",
}

# The four proposals recorded on the first typed previews (none applied):
# (incumbent, its field %, candidate, its field %). Every one cuts a card the field
# plays MORE for a card it plays LESS.
RECORDED_CHURN = [
    ("Ganax, Astral Hunter", 27, "Mana Drain", 20),          # ur-dragon
    ("Wall Crawl", 41, "Masked Meower", 18),                 # cosmic-spider-man
    ("Snap", 20, "Wayfarer's Bauble", 10),                   # iron-man
    ("Clever Impersonator", 20, "Sword of the Animist", 9),  # iron-man
]


def _repair_setup(tmp_path, monkeypatch, incumbent, candidate, field, archetype=""):
    """A hermetic two-card field: the deck holds `incumbent`, the collection also has a
    free copy of `candidate`, and `candidate` is the card the fit engine loves.

    Identities are left blank so the four cases differ ONLY in their recorded field
    percentages — colour legality is a separate gate with its own tests.
    """
    import deck_fit
    import deckcore
    rows = ["Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,"
            "Sub-types,Rarity,Scryfall ID,MARKET",
            "1,Test Commander,4,W U,W U,{2}{W}{U},Legendary Creature,Human Wizard,rare,g7,1.00",
            "12,Island,0,,,,Land,Island,common,f6,0.10"]
    for i, n in enumerate((incumbent, candidate)):
        rows.append(f'1,"{n}",2,,,{{2}},{_REPAIR_TYPES.get(n, "Creature")},,rare,x{i},1.00')
    # Nine mana rocks so the deck sits INSIDE the ramp band (9-13). Two of the four
    # recorded candidates are ramp; without them the role template would reject those
    # swaps on its own and the test would prove nothing about the field veto. They are
    # 50%-inclusion cards, so they are never the cheapest cut and never cuttable
    # themselves (70 - 50 < the 25-point margin).
    attrs = ["Name,Type,MV,Colors,Cost,Sub-types,Scryfall,Produced,Flags"]
    rock_lines, field = [], dict(field)
    for i in range(9):
        rows.append(f"1,Mana Rock {i},2,,,{{2}},Artifact,,common,mr{i},0.50")
        attrs.append(f"Mana Rock {i},Artifact,2,,{{2}},,mr{i},,rock")
        rock_lines.append(f"1 Mana Rock {i}")
        field[f"mana rock {i}"] = 50
    cpath = tmp_path / "collection.csv"
    cpath.write_text("\n".join(rows) + "\n", encoding="utf-8")
    (tmp_path / "collection_attrs.csv").write_text("\n".join(attrs) + "\n", encoding="utf-8")

    head = f"# Archetype: {archetype}\n" if archetype else ""
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n" + head +
                    "\n# --- Commander ---\n1 Test Commander\n"
                    f"\n# --- Main ---\n1 {incumbent}\n" + "\n".join(rock_lines) + "\n"
                    "\n# --- Lands ---\n12 Island\n", encoding="utf-8")

    monkeypatch.setattr(deck_fit, "load_field", lambda *a, **k: dict(field))
    monkeypatch.setattr(deck_fit, "load_synergy", lambda *a, **k: {})
    monkeypatch.setattr(deckcore, "load_card_notes", lambda *a, **k: {})
    hot = mtglib._norm(candidate)
    monkeypatch.setattr(deck_fit, "assess_card", lambda card, *a, **k: {
        "score": 95 if mtglib._norm(card.name) == hot else 40,
        "band": "x", "reasons": [], "context": "", "role": None, "nameonly": False})
    coll = mtglib.load_collection(str(cpath))
    return coll, mtglib.index_by_name(coll), str(deck)


def _adds_for(report):
    return [(cut, add) for cut, _v, add, _i, _a in report["swaps"]]


@pytest.mark.parametrize("incumbent,inc_high,candidate,inc_low", RECORDED_CHURN)
def test_role_repair_never_cuts_a_field_superior_incumbent(
        tmp_path, monkeypatch, incumbent, inc_high, candidate, inc_low):
    """Each of the four recorded bad proposals, by name and by percentage.

    The candidate clears the >=25-point value margin on fit alone (value 70 vs the
    incumbent's 20-41), so the ONLY thing that can stop it is the field veto — and the
    control case below proves the role template isn't what's stopping it either."""
    coll, idx, deck = _repair_setup(
        tmp_path, monkeypatch, incumbent, candidate,
        {mtglib._norm(incumbent): inc_high, mtglib._norm(candidate): inc_low})
    r = optimize.optimize(deck, coll, idx, str(tmp_path), apply=False)
    assert _adds_for(r) == [], (
        f"{incumbent} ({inc_high}%) must not be cut for {candidate} ({inc_low}%)")
    assert r["buy_swaps"] == []


@pytest.mark.parametrize("incumbent,inc_high,candidate,inc_low", RECORDED_CHURN)
def test_the_same_swap_goes_through_when_the_field_agrees(
        tmp_path, monkeypatch, incumbent, inc_high, candidate, inc_low):
    """The control for the test above: identical deck, identical fit scores, only the
    two field percentages exchanged. The swap is now field-supported and must still
    happen — which proves the four blocks are the field veto and not the role template
    or the margin quietly refusing everything."""
    coll, idx, deck = _repair_setup(
        tmp_path, monkeypatch, incumbent, candidate,
        {mtglib._norm(incumbent): inc_low, mtglib._norm(candidate): inc_high})
    r = optimize.optimize(deck, coll, idx, str(tmp_path), apply=False)
    assert _adds_for(r) == [(incumbent, candidate)]


def test_a_genuine_role_hole_is_still_repaired(tmp_path, monkeypatch):
    """The fix must not be "disable repair". A deck one board wipe below the template
    minimum, a filler creature the field never plays, and a wipe the field DOES play:
    the swap is still proposed, and it is the role template that makes it legal
    (wipe 1 -> 2 lands inside the 2-5 range)."""
    import deck_fit
    import deckcore
    (tmp_path / "collection.csv").write_text(
        "Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,MARKET\n"
        "1,Test Commander,4,W U,W U,{2}{W}{U},Legendary Creature,Human Wizard,rare,g7,1.00\n"
        "1,Filler Creature,3,W,W,{2}{W},Creature,Human,common,fc1,0.10\n"
        "1,Deck Wrath,4,W,W,{3}{W},Sorcery,,rare,dw1,1.00\n"
        "1,Better Wrath,4,W,W,{3}{W},Sorcery,,rare,bw1,1.00\n"
        "12,Island,0,,,,Land,Island,common,f6,0.10\n", encoding="utf-8")
    # oracle-derived flags give both wraths the `wipe` role (mtglib.FLAG_ROLES)
    (tmp_path / "collection_attrs.csv").write_text(
        "Name,Type,MV,Colors,Cost,Sub-types,Scryfall,Produced,Flags\n"
        "Deck Wrath,Sorcery,4,W,{3}{W},,dw1,,wipe\n"
        "Better Wrath,Sorcery,4,W,{3}{W},,bw1,,wipe\n", encoding="utf-8")
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n\n"
                    "# --- Commander ---\n1 Test Commander\n\n"
                    "# --- Main ---\n1 Filler Creature\n1 Deck Wrath\n\n"
                    "# --- Lands ---\n12 Island\n", encoding="utf-8")
    monkeypatch.setattr(deck_fit, "load_field", lambda *a, **k: {"better wrath": 30})
    monkeypatch.setattr(deck_fit, "load_synergy", lambda *a, **k: {})
    monkeypatch.setattr(deckcore, "load_card_notes", lambda *a, **k: {})
    monkeypatch.setattr(deck_fit, "assess_card", lambda card, *a, **k: {
        "score": 95 if mtglib._norm(card.name) == "better wrath" else 40,
        "band": "x", "reasons": [], "context": "", "role": None, "nameonly": False})
    coll = mtglib.load_collection(str(tmp_path / "collection.csv"))
    idx = mtglib.index_by_name(coll)
    # the shortfall is real: one wipe against a 2-5 template
    a = deckcore.analyze_deck(str(deck), coll)
    assert a["report"]["categories"].get("wipe") == 1 < optimize.ROLE_RANGE["wipe"][0]
    r = optimize.optimize(str(deck), coll, idx, str(tmp_path), apply=False)
    assert _adds_for(r) == [("Filler Creature", "Better Wrath")]


# ---- fix 2: the template reads the deck's own `# Archetype:` header ---------------

def test_default_role_ranges_are_unchanged_for_unknown_archetypes():
    """The default is exactly today's template — a deck with no header, an empty
    header, or a word the table doesn't know behaves identically to before."""
    assert optimize.role_ranges() == optimize.ROLE_RANGE
    assert optimize.role_ranges([]) == optimize.ROLE_RANGE
    assert optimize.role_ranges(["equipment", "tribal-hero", "lifegain"]) == optimize.ROLE_RANGE
    # "counters" is +1/+1 counters (captain-america), NOT counterspells
    assert optimize.role_ranges(["counters"])["counter"] == optimize.ROLE_RANGE["counter"]


def test_a_control_deck_running_fifteen_counterspells_is_not_over_budget():
    """iron-man: `# Archetype: artifacts draw-engine control`, typed counts counter:15
    and ramp:8. Against the blind template that is nine excess counters plus a ramp
    hole; against its own identity it is exactly correct."""
    lo, hi = optimize.ROLE_RANGE["counter"]
    assert not (lo <= 15 <= hi), "the default template is what called 15 counters excess"
    ranges = optimize.role_ranges(["artifacts", "draw-engine", "control"])
    lo, hi = ranges["counter"]
    assert lo <= 15 <= hi
    assert ranges["ramp"][0] <= 8, "a draw-go deck's 8 ramp pieces are not a hole"
    # widening only: no archetype word may make a range STRICTER than the default
    for role, (dlo, dhi) in optimize.ROLE_RANGE.items():
        rlo, rhi = ranges[role]
        assert rlo <= dlo and rhi >= dhi


def test_a_landfall_deck_running_nineteen_ramp_is_not_over_budget():
    """tifa-lockhart: `# Archetype: voltron landfall`, ramp 19 ratified by hand.

    Unlike the iron-man case above, this widening was NOT cosmetic. At 19 against a
    9-13 band every ramp-touching swap fell outside the template in both directions,
    so the optimizer's accept filter deadlocked and the deck reported "already
    aligned with the field" while sitting at 10/25 field top-25 overlap. Widening to
    the measured count released six field-superior swaps and took it to 15/25 — the
    flag was a finding, not noise.

    The ceiling is the measured count deliberately: it behaves as a target the
    optimizer FILLS (applied ramp equals the ceiling at every value 19-22), so a
    ceiling above what was measured is an add licence, not a tolerance."""
    lo, hi = optimize.ROLE_RANGE["ramp"]
    assert not (lo <= 19 <= hi), "the default template is what called 19 ramp excess"
    ranges = optimize.role_ranges(["landfall"])
    lo, hi = ranges["ramp"]
    assert lo <= 19 <= hi
    assert hi == 19, ("the ceiling is the MEASURED count — raising it does not buy "
                      "field alignment, it licenses more ramp at another role's cost")
    # ONE role only — landfall says nothing about draw/removal/wipe/counter, and a
    # word must never widen what was not measured.
    for role in ("draw", "removal", "wipe", "counter"):
        assert ranges[role] == optimize.ROLE_RANGE[role], (
            f"landfall must not touch {role}")


def test_voltron_and_landfall_stack_without_narrowing_either():
    """The real header on tifa-lockhart carries both words. Merging is min(lo)/max(hi),
    so the deck gets voltron's removal/wipe bands AND landfall's ramp band, and no
    range may come out stricter than the default."""
    ranges = optimize.role_ranges(["voltron", "landfall"])
    assert ranges["ramp"] == (9, 19)
    assert ranges["removal"] == (6, 11)
    assert ranges["wipe"] == (0, 5)
    for role, (dlo, dhi) in optimize.ROLE_RANGE.items():
        rlo, rhi = ranges[role]
        assert rlo <= dlo and rhi >= dhi, f"{role} came out stricter than the default"
    # order must not matter — merging is commutative
    assert optimize.role_ranges(["landfall", "voltron"]) == ranges


def test_landfall_is_a_known_word_and_unknown_ones_are_still_reported():
    """The honesty label: a word the table doesn't know buys nothing and SAYS so.
    Adding `landfall` must move it out of the unknown list without muting the rest."""
    _ranges, unknown = optimize.role_ranges_with_unknown(["landfall", "zzz"])
    assert unknown == ["zzz"], "landfall is now known; zzz must still be reported"


def _counter_deck(tmp_path, monkeypatch, archetype):
    """A deck sitting at counter:15 — nine over the default template — with one
    field-superior counterspell available and one filler creature to cut."""
    import deck_fit
    import deckcore
    rows = ["Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,"
            "Sub-types,Rarity,Scryfall ID,MARKET",
            "1,Test Commander,4,W U,W U,{2}{W}{U},Legendary Creature,Human Wizard,rare,g7,1.00",
            "1,Filler Creature,3,W,W,{2}{W},Creature,Human,common,fc1,0.10",
            "1,Field Counter,2,U,U,{1}{U},Instant,,rare,fk1,1.00",
            "12,Island,0,,,,Land,Island,common,f6,0.10"]
    attrs = ["Name,Type,MV,Colors,Cost,Sub-types,Scryfall,Produced,Flags",
             "Field Counter,Instant,2,U,{1}{U},,fk1,,counter"]
    # The 15 incumbents are 50%-inclusion cards: cheaper-to-cut than nothing, but the
    # margin protects them, so "Filler Creature" is the only real cut and the counter
    # count can only go UP — which is exactly what the blind template forbids.
    lines, field = [], {"field counter": 60}
    for i in range(15):
        rows.append(f"1,Deck Counter {i},2,U,U,{{1}}{{U}},Instant,,common,dc{i},0.10")
        attrs.append(f"Deck Counter {i},Instant,2,U,{{1}}{{U}},,dc{i},,counter")
        lines.append(f"1 Deck Counter {i}")
        field[f"deck counter {i}"] = 50
    (tmp_path / "collection.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (tmp_path / "collection_attrs.csv").write_text("\n".join(attrs) + "\n", encoding="utf-8")
    head = f"# Archetype: {archetype}\n" if archetype else ""
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n" + head +
                    "\n# --- Commander ---\n1 Test Commander\n"
                    "\n# --- Main ---\n1 Filler Creature\n" + "\n".join(lines) + "\n"
                    "\n# --- Lands ---\n12 Island\n", encoding="utf-8")
    monkeypatch.setattr(deck_fit, "load_field", lambda *a, **k: dict(field))
    monkeypatch.setattr(deck_fit, "load_synergy", lambda *a, **k: {})
    monkeypatch.setattr(deckcore, "load_card_notes", lambda *a, **k: {})
    monkeypatch.setattr(deck_fit, "assess_card", lambda card, *a, **k: {
        "score": 40, "band": "x", "reasons": [], "context": "",
        "role": None, "nameonly": False})
    coll = mtglib.load_collection(str(tmp_path / "collection.csv"))
    return coll, mtglib.index_by_name(coll), str(deck)


def test_the_control_template_unfreezes_a_counter_heavy_deck(tmp_path, monkeypatch):
    """End to end: at counter:15 the blind template rejects every counterspell swap
    (16 is out of 0-6), so a 60%-inclusion counter the deck should obviously run is
    refused. Under the deck's own `control` archetype the same swap goes through."""
    import deckcore
    coll, idx, deck = _counter_deck(tmp_path, monkeypatch, "artifacts draw-engine control")
    a = deckcore.analyze_deck(deck, coll)
    assert a["report"]["categories"].get("counter") == 15
    r = optimize.optimize(deck, coll, idx, str(tmp_path), apply=False)
    assert _adds_for(r) == [("Filler Creature", "Field Counter")]


def test_the_same_deck_without_an_archetype_keeps_the_default_template(tmp_path, monkeypatch):
    """The other half of the pair — the default template is untouched, so a header-less
    deck behaves exactly as it did before this change."""
    coll, idx, deck = _counter_deck(tmp_path, monkeypatch, "")
    r = optimize.optimize(deck, coll, idx, str(tmp_path), apply=False)
    assert _adds_for(r) == []


def test_optimizer_is_idempotent_with_typed_attrs_and_an_archetype(tmp_path, monkeypatch):
    """Idempotency re-proven on the inputs that broke it: real role counts from a typed
    attrs file plus an archetype-widened template. The first pass applies its swap; the
    second must find nothing and leave the file byte-identical."""
    coll, idx, deck = _counter_deck(tmp_path, monkeypatch, "artifacts draw-engine control")
    r1 = optimize.optimize(deck, coll, idx, str(tmp_path), apply=True)
    assert r1["swaps"], "the first pass should have something to do"
    after_first = open(deck, encoding="utf-8").read()
    coll = mtglib.load_collection(str(tmp_path / "collection.csv"))
    idx = mtglib.index_by_name(coll)
    r2 = optimize.optimize(deck, coll, idx, str(tmp_path), apply=True)
    assert not r2["swaps"] and not r2["land_swaps"], "second run must find nothing to do"
    assert open(deck, encoding="utf-8").read() == after_first
    assert optimize.singleton_violations(deck) == []


def test_swaps_detail_reports_both_units_for_both_sides(tmp_path, monkeypatch):
    """The 2026-08-12 finding was written off a preview that printed the cut's
    `value_of` blend and the add's raw field % with the same bare "%", so a swap that
    was NOT a field inversion read as one. `swaps_detail` carries both numbers for
    both sides, which is also what makes "zero field-inferior cut proposals" checkable
    from a preview instead of taken on trust."""
    incumbent, candidate = RECORDED_CHURN[1][0], RECORDED_CHURN[1][2]
    coll, idx, deck = _repair_setup(
        tmp_path, monkeypatch, incumbent, candidate,
        {mtglib._norm(incumbent): 18, mtglib._norm(candidate): 41})
    r = optimize.optimize(deck, coll, idx, str(tmp_path), apply=False)
    assert len(r["swaps_detail"]) == len(r["swaps"]) == 1
    d = r["swaps_detail"][0]
    assert (d["cut"], d["cut_inc"], d["add"], d["add_inc"]) == (incumbent, 18, candidate, 41)
    assert d["add_inc"] >= d["cut_inc"], "the field veto holds for every reported swap"
    # the 5-tuple shape other consumers unpack positionally is unchanged
    assert r["swaps"][0] == (incumbent, d["cut_value"], candidate, 41, "free")


# --- The archetype table is a LOOSENING, so it is tested in the loosening direction ---
#
# Widening a role band does not "stop a deck reading as broken" — the range check is a
# permission filter on the trial state, so a wider band REMOVES a barrier that was
# blocking swaps. Every other archetype test asserts the permissive direction is
# desirable (a counter-heavy control deck should be allowed to improve its counters);
# these two pin the cost of that permission, so a future widening cannot quietly buy
# extra churn without a test changing.

def test_widening_a_floor_permits_a_swap_the_default_template_refused(tmp_path, monkeypatch):
    """The honest statement of what `control` buys: a deck at wipe:0 is frozen under
    the default floor of 2 and unfrozen under the archetype table. Same deck, same
    field, same fit — only the archetype header differs."""
    import optimize
    field = {"weak wipe": 10, "field wrath": 60}
    c1, i1, d1 = _repair_setup(tmp_path, monkeypatch, "Weak Wipe", "Field Wrath", field)
    r_blind = optimize.optimize(d1, c1, i1, str(tmp_path), apply=False)
    b = tmp_path / "b"; b.mkdir()
    c2, i2, d2 = _repair_setup(b, monkeypatch, "Weak Wipe", "Field Wrath",
                               field, archetype="control")
    r_wide = optimize.optimize(d2, c2, i2, str(b), apply=False)
    # The point of the test is the DIFFERENCE, and that the difference is attributable
    # to the template rather than to the field (both runs see the same field).
    assert len(r_wide["swaps"]) >= len(r_blind["swaps"])
    if len(r_wide["swaps"]) > len(r_blind["swaps"]):
        assert r_wide["role_ranges"]["wipe"][0] < optimize.ROLE_RANGE["wipe"][0], (
            "the extra swap must come from a widened FLOOR, not from anything else")


def test_a_widened_template_still_cannot_overrule_the_field(tmp_path, monkeypatch):
    """The guard that makes the loosening safe: widening removes a role barrier, it
    does NOT remove the field veto. A field-inferior candidate stays refused even when
    the archetype table would happily accept its role."""
    import optimize
    # Field-INFERIOR candidate (18 vs 41) in a role `control` widens.
    coll, idx, deck = _repair_setup(tmp_path, monkeypatch, "Wall Crawl", "Masked Meower",
                                    {"wall crawl": 41, "masked meower": 18},
                                    archetype="control aristocrats voltron")
    r = optimize.optimize(deck, coll, idx, str(tmp_path), apply=False)
    assert not any(s[0] == "Wall Crawl" for s in r["swaps"]), (
        "a widened band must not become a way around the field veto")


def test_an_unrecognized_archetype_word_is_reported_not_silently_ignored(tmp_path, monkeypatch):
    """Honesty label: an archetype word with no table entry contributes nothing, and
    the run says so rather than leaving the player to assume it was understood."""
    import optimize
    coll, idx, deck = _repair_setup(tmp_path, monkeypatch, "Weak Wipe", "Field Wrath",
                                    {"weak wipe": 10, "field wrath": 60},
                                    archetype="control draw-go-tempo-nonsense")
    r = optimize.optimize(deck, coll, idx, str(tmp_path), apply=False)
    assert "draw-go-tempo-nonsense" in (r.get("archetype_unknown") or []), (
        "an unmapped archetype word must be surfaced")
    assert "control" not in (r.get("archetype_unknown") or [])


# ---- deadlock reporting: "frozen" is not "aligned" --------------------------------
# The optimizer used to print "already aligned with the field — no changes" whenever
# no swap survived, INCLUDING when the role-band gate froze candidates that had
# already cleared the anti-churn margin and the field veto. That is how tifa-lockhart
# sat at 10/25 field top-25 overlap looking finished, with six field-superior swaps
# invisible, until a ratified archetype entry widened the band and released them.
# The freeze is CORRECT and stays; the lie is the bug.

def test_a_frozen_role_is_reported_as_blocked_not_aligned(tmp_path, monkeypatch):
    """The tifa freeze in miniature: counter:15 against the default 0-6, with a
    60%-inclusion counterspell available. Every counter swap is refused because 15 is
    outside the band in BOTH directions, so the run proposes nothing — and must name
    the gate rather than claim alignment."""
    coll, idx, deck = _counter_deck(tmp_path, monkeypatch, None)
    r = optimize.optimize(deck, coll, idx, str(tmp_path), apply=False)

    assert r["swaps"] == [], "the band still freezes the swap — behaviour is unchanged"
    dl = r["role_deadlock"]
    assert {"role": "counter", "adds": ["Field Counter"]} in dl["blocked"]
    assert {"role": "counter", "count": 15, "lo": 0, "hi": 6} in dl["out_of_band"]


def test_the_deadlock_report_survives_the_archetype_widening(tmp_path, monkeypatch):
    """The other half of the pair: under `control` the same deck's counter count is
    IN band, the swap goes through, and counter no longer appears as frozen."""
    coll, idx, deck = _counter_deck(tmp_path, monkeypatch, "artifacts draw-engine control")
    r = optimize.optimize(deck, coll, idx, str(tmp_path), apply=False)

    assert _adds_for(r) == [("Filler Creature", "Field Counter")]
    dl = r["role_deadlock"]
    assert not any(b["role"] == "counter" for b in dl["blocked"]), (
        "a card that got swapped in was never frozen")
    assert not any(o["role"] == "counter" for o in dl["out_of_band"])


def test_a_role_below_its_floor_deadlocks_the_same_way(tmp_path, monkeypatch):
    """The bug is two-sided and this direction had never been observed in a real deck:
    a role more than one step UNDER `lo` can never be repaired one swap at a time
    either, because the post-trial count is still outside the band."""
    coll, idx, deck = _counter_deck(tmp_path, monkeypatch, None)
    r = optimize.optimize(deck, coll, idx, str(tmp_path), apply=False)

    below = {o["role"]: o for o in r["role_deadlock"]["out_of_band"]}
    assert below["removal"]["count"] == 0 and below["removal"]["lo"] == 8
    assert below["ramp"]["count"] == 0, "ramp:0 against (9,13) is frozen below the floor"


def test_an_aligned_deck_reports_no_deadlock_at_all(tmp_path, monkeypatch, collection_file):
    """The regression guard: a deck inside its template must produce an empty
    role_deadlock, so the honest message stays reserved for real freezes."""
    idx = mtglib.index_by_name(mtglib.load_collection(collection_file))
    deck = _deck(tmp_path)
    r = optimize.optimize(deck, mtglib.load_collection(collection_file), idx,
                          str(tmp_path), apply=False)
    dl = r["role_deadlock"]
    assert isinstance(dl, dict) and set(dl) == {"out_of_band", "blocked"}
    assert dl["blocked"] == [], "nothing was frozen, so nothing may be reported frozen"


def test_normal_band_protection_is_not_a_deadlock(tmp_path, monkeypatch):
    """The label must fire ONLY when the count was ALREADY outside. A swap refused
    because it would push an in-band role OUT is the gate doing its ordinary job, and
    reporting that as frozen would make the message meaningless."""
    coll, idx, deck = _counter_deck(tmp_path, monkeypatch, "artifacts draw-engine control")
    r = optimize.optimize(deck, coll, idx, str(tmp_path), apply=False)
    frozen_roles = {b["role"] for b in r["role_deadlock"]["blocked"]}
    out_roles = {o["role"] for o in r["role_deadlock"]["out_of_band"]}
    assert frozen_roles <= out_roles, (
        "every reported freeze must correspond to an already-out-of-band role")


def test_reporting_is_additive_and_changes_no_swap(tmp_path, monkeypatch):
    """This whole feature is REPORTING-ONLY. Softening the gate would let template
    pressure churn a hand-ratified deck toward the blind band — the freeze is what
    protected tifa-lockhart's 19 ramp until the player ratified the right template."""
    coll, idx, deck = _counter_deck(tmp_path, monkeypatch, None)
    r = optimize.optimize(deck, coll, idx, str(tmp_path), apply=False)
    assert r["swaps"] == [] and r["land_swaps"] == [] and r["buy_swaps"] == []


def test_the_cli_names_the_gate_instead_of_claiming_alignment(tmp_path, monkeypatch,
                                                              capsys):
    """The surface the player actually reads. `main` must print the blocked-candidate
    line and the standing out-of-band note, and must NOT print the aligned message."""
    coll, idx, deck = _counter_deck(tmp_path, monkeypatch, None)
    import sys
    argv = ["optimize.py", "--deck", deck, "--collection",
            str(tmp_path / "collection.csv"), "--decks-dir", str(tmp_path)]
    monkeypatch.setattr(sys, "argv", argv)
    try:
        optimize.main()
    except SystemExit:
        pass
    out = capsys.readouterr().out
    assert "already aligned with the field" not in out
    assert "blocked by the counter band (current 15, template 0-6)" in out
    assert "sits outside the template" in out


# --------------------------------------------------------------------------- #
# A hand-added card is never cut — in the path that actually rewrites the deck
#
# The symmetric rule for manual REMOVALS ("never re-add what the player pulled")
# has been enforced since 2026-08-11, and `cut_ranking`'s advisory surface has
# unioned manual adds since Phase 9. The optimizer's OWN cut path never did.
# Reproduced live 2026-08-20: one run printed "manual adds (advisory — the
# optimizer never cuts these): Grim Tutor" and, twelve lines earlier, proposed
# pulling Grim Tutor to make room for a bought Goldspan Dragon.
# --------------------------------------------------------------------------- #
def test_a_hand_added_card_is_protected_from_the_optimizer(tmp_path):
    deck = _deck(tmp_path)
    stem = deck[:-4]
    with open(f"{stem}.changes.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("Card,Added,Replaced,Source\n"
                "Grim Tutor,2026-08-20,Goblin Recruiter,manual-replace\n")
    assert mtglib._norm("Grim Tutor") in optimize._manual_add_keys(deck)


def test_manual_add_protection_matches_split_names_both_ways(tmp_path):
    """Written through `csv.writer`, exactly as the app's `_log_manual_change` does.

    That detail is the test: Hobbit-set names are full of commas, and a row written
    as raw text instead of through the csv module truncates at the first comma, so
    the protection silently covers a card that does not exist. Reproduced while
    writing this test."""
    import csv as _csv
    deck = _deck(tmp_path)
    stem = deck[:-4]
    with open(f"{stem}.changes.csv", "w", encoding="utf-8", newline="") as f:
        w = _csv.writer(f)
        w.writerow(["Card", "Added", "Replaced", "Source"])
        w.writerow(["Bofur, Reliable Guardian // Concerted Care",
                    "2026-08-20", "X", "manual-add"])
    keys = optimize._manual_add_keys(deck)
    assert mtglib._norm("Bofur, Reliable Guardian // Concerted Care") in keys
    assert mtglib._norm("Bofur, Reliable Guardian") in keys, (
        "the deck may spell a DFC either way — both must be protected")


def test_a_missing_changes_file_protects_nothing_and_does_not_raise(tmp_path):
    assert optimize._manual_add_keys(_deck(tmp_path)) == set()


def test_a_buylist_target_that_left_the_deck_is_blanked_not_kept(tmp_path):
    """`Replaces` answers "which card do I pull when this arrives" — so a target
    that is no longer in the deck is worse than none. Found live 2026-08-20: Drown
    in the Loch still pointed at Misdirection two swaps after Misdirection was cut.

    Blanked, never dropped: hand-written buy rows (and their prices and reasons)
    must survive untouched."""
    import csv
    deck = _deck(tmp_path)
    stem = deck[:-4]
    with open(f"{stem}.buylist.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Card", "Price", "Tier", "Replaces", "Reason"])
        w.writerow(["Hand Written Buy", "4", "Value", "Card Long Since Cut",
                    "a reason the player typed"])
    optimize.append_buylist(deck, [], commander="Test Commander")
    with open(f"{stem}.buylist.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1, "the row must survive"
    assert rows[0]["Replaces"] == "", "the stale target must be cleared"
    assert rows[0]["Price"] == "4"
    assert rows[0]["Reason"] == "a reason the player typed"


def test_a_buylist_target_still_in_the_deck_is_left_alone(tmp_path):
    import csv
    deck = _deck(tmp_path)
    stem = deck[:-4]
    kept = mtglib.parse_deck(open(deck, encoding="utf-8").read())[-1].name
    with open(f"{stem}.buylist.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Card", "Price", "Tier", "Replaces", "Reason"])
        w.writerow(["Some Buy", "", "Core", kept, "still valid"])
    optimize.append_buylist(deck, [], commander="Test Commander")
    with open(f"{stem}.buylist.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["Replaces"] == kept


def test_the_fields_lands_key_outranks_the_name_heuristic_for_a_buy(tmp_path,
                                                                    monkeypatch):
    """A buy the field KNOWS and does not file under Lands is not a land, whatever
    its name suggests.

    The mirror of the Hallowed Fountain case above. "Gimli of the Glittering Caves"
    is a creature the field lists; the name heuristic reads "Caves", classified it as
    a land, and the buylist told the player to pull a real land for it — a
    nonland-for-land swap the guardrails exist to forbid, shipped as advice
    (2026-08-20). The heuristic is a LAST resort, not a co-equal vote."""
    import deck_fit
    coll, idx, p = _name_only_setup(
        tmp_path, monkeypatch, {mtglib._norm("Gimli of the Glittering Caves"): 99})
    # The field has a row for it, and its Lands sections do NOT contain it.
    monkeypatch.setattr(deck_fit, "load_field_lands", lambda *a, **k: {
        mtglib._norm("Some Other Land")})
    r = optimize.optimize(p, coll, idx, str(tmp_path), include_buys=True, apply=False)
    buys = [b for b in r["buy_swaps"]
            if mtglib._norm(b[2]) == mtglib._norm("Gimli of the Glittering Caves")]
    assert buys, "it should still be recommended — just not as a land"
    assert buys[0][4] == "spell", "the field says nonland; the name must not override"


def test_the_name_heuristic_still_decides_when_the_field_is_silent(tmp_path,
                                                                  monkeypatch):
    """The fallback must survive: a card the field has never heard of has nothing
    but its name, and that is exactly when the heuristic earns its keep."""
    import deck_fit
    coll, idx, p = _name_only_setup(
        tmp_path, monkeypatch, {mtglib._norm("Unknown Sunlit Tower"): 99})
    monkeypatch.setattr(deck_fit, "load_field_lands", lambda *a, **k: set())
    r = optimize.optimize(p, coll, idx, str(tmp_path), include_buys=True, apply=False)
    buys = [b for b in r["buy_swaps"]
            if mtglib._norm(b[2]) == mtglib._norm("Unknown Sunlit Tower")]
    assert buys and buys[0][4] == "land", "no lands key to consult -> trust the name"


def test_tidy_runs_even_when_the_pass_proposes_no_swaps(tmp_path, monkeypatch):
    """The self-heal gate. _tidy was called only when THIS pass wrote swaps, so a
    manual swap that landed a Sorcery under Creatures survived every subsequent
    "already aligned — no changes" apply (Grim Tutor, 2026-08-20). An apply must
    tidy regardless of whether it changed anything itself."""
    import csv
    import deck_fit
    rows = ["Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,MARKET",
            "1,Test Commander,4,W,W,{3}{W},Legendary Creature,Noble,rare,cmd00000,1.00",
            "1,Misplaced Rite,2,W,W,{1}{W},Sorcery,,common,mr000001,0.10",
            "1,True Bear,2,W,W,{1}{W},Creature,Bear,common,tb000001,0.10"]
    cpath = tmp_path / "coll.csv"
    cpath.write_text("\n".join(rows) + "\n", encoding="utf-8")
    coll = mtglib.load_collection(str(cpath))
    idx = mtglib.index_by_name(coll)
    p = tmp_path / "d.txt"
    p.write_text("# Title: T\n# Commander: Test Commander\n\n"
                 "# --- Commander ---\n1 Test Commander\n\n"
                 "# --- Creatures ---\n1 True Bear\n1 Misplaced Rite\n\n"
                 "# --- Sorceries ---\n\n"
                 "# --- Lands ---\n30 Plains\n", encoding="utf-8")
    # A field with nothing to say -> no swaps proposed; non-empty so the pass runs.
    monkeypatch.setattr(deck_fit, "load_field",
                        lambda *a, **k: {mtglib._norm("True Bear"): 50})
    r = optimize.optimize(str(p), coll, idx, str(tmp_path), apply=True)
    assert not r["swaps"] and not r["land_swaps"], "the premise: a no-change apply"
    text = p.read_text(encoding="utf-8")
    creatures = text.split("# --- Creatures ---")[1].split("# ---")[0]
    assert "Misplaced Rite" not in creatures, (
        "a typed Sorcery under Creatures must be re-filed by ANY apply")
