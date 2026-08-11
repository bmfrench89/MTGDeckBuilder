"""The optimizer rewrites real deck files, so the invariants matter more than the picks:
card count preserved, no cards invented or lost by the tidy pass, sections kept."""
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
    Counterspell at 20% inclusion but ~92 fit (blend 64) against a near-zero-value
    cut, margin 40. The old gate (raw inclusion minus value) refused this."""
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n\n"
                    "# --- Creatures ---\n1 Serra Angel\n\n"
                    "# --- Lands ---\n10 Island\n", encoding="utf-8")
    import deck_fit
    monkeypatch.setattr(deck_fit, "load_field", lambda *a, **k: {"counterspell": 20})
    monkeypatch.setattr(deck_fit, "load_synergy", lambda *a, **k: {"counterspell": 69})
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    r = optimize.optimize(str(deck), coll, idx, str(tmp_path), margin=40)
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
