"""Lift: EDHREC's replacement for synergy (2025-12-15), computed for commander pages.

EDHREC's commander pages still show synergy = inclusion - colour baseline. Lift is the
ratio of the same two rates, so the baseline falls out of the numbers every snapshot
already stores. `deck_fit.commander_lift` adds a baseline floor (the inputs are whole
percents) and small-sample shrinkage (EDHREC's formula has none). Lift is evidence: it
feeds the fit score's specificity points, ranks the rarely-listed reads, and flags a
proposal that trades a commander-specific card for a generic one. Everything is
hermetic."""
import json
import sys

import pytest

import deck_fit
import edhrec
import mtglib


# ---- the formula ---------------------------------------------------------------------

def test_lift_is_inclusion_over_the_colour_baseline():
    # Shattered Angel for Giada: 20% of decks, synergy 16 -> baseline 4% -> 5x
    lf = deck_fit.commander_lift(20, 16)
    assert lf["base"] == 4.0 and lf["lift"] == pytest.approx(5.0)
    assert lf["log"] == pytest.approx(0.699, abs=1e-3)


def test_a_universal_staple_reads_as_generic():
    # Sol Ring: 92% here, synergy 8 -> 84% everywhere -> ~1.1x
    assert deck_fit.commander_lift(92, 8)["lift"] == pytest.approx(1.1, abs=0.01)


def test_missing_numbers_are_not_a_measured_1x():
    assert deck_fit.commander_lift(None, 5) is None
    assert deck_fit.commander_lift(0, 5) is None
    assert deck_fit.commander_lift(12, None) is None


def test_the_baseline_has_a_floor():
    """Whole-percent inputs: 6% with synergy 6 is a baseline of 0.5% +- 0.5, and dividing
    by that would mint a 'signature' out of rounding."""
    assert deck_fit.commander_lift(6, 6)["base"] == deck_fit.LIFT_BASE_FLOOR
    assert deck_fit.commander_lift(6, 6)["lift"] == pytest.approx(6.0)


def test_small_samples_shrink_toward_independence():
    big = deck_fit.commander_lift(20, 16, sample=40000)["lift"]
    small = deck_fit.commander_lift(20, 16, sample=30)["lift"]
    unknown = deck_fit.commander_lift(20, 16, sample=None)["lift"]
    assert big == pytest.approx(5.0, abs=0.02), "thousands of decks barely move"
    assert 1.0 < small < big, "30 decks pull most of the way back toward 1x"
    assert unknown == pytest.approx(5.0)


def test_fmt_lift_reads_like_a_person_wrote_it():
    assert deck_fit.fmt_lift({"lift": 4.99}) == "5×"
    assert deck_fit.fmt_lift({"lift": 1.34}) == "1.3×"
    assert deck_fit.fmt_lift({"lift": 12.7}) == "13×"


# ---- the specificity tiers -------------------------------------------------------------

@pytest.mark.parametrize("inc,syn,pts", [
    (45, 42, 15),   # Ashcoat Bear in Beorn: 15x, 45% - a signature card
    (15, 13, 13),   # Bosco: 7x but only 15% of decks - strongly tied
    (65, 47, 13),   # 3.6x and popular - strongly tied
    (18, 12, 11),   # 3x, under 30% - more played here
    (72, 15, 0),    # Beast Within: 1.3x - generic, no specificity credit
    (9, 8, 0),      # 9x but in under 10% of decks - a fringe pick
])
def test_lift_points(inc, syn, pts):
    assert deck_fit._lift_points(deck_fit.commander_lift(inc, syn), inc)[0] == pts


def _card(name):
    return mtglib.Card(name=name, quantity=1, mana_value=3.0, types=["Creature"],
                       identity={"G"}, mana_cost="{2}{G}")


REP = {"total": 100, "lands": 37, "categories": {"ramp": 10, "draw": 10, "removal": 9}}


def _ctx(field, synergy, n=None):
    return {"identity": {"G"}, "archetype": [], "theme": "", "tribal": None,
            "commander": "Test", "field": field, "synergy": synergy, "field_n": n}


def test_a_specific_card_outscores_an_equally_popular_generic_one():
    k_spec, k_gen = mtglib._norm("Specific"), mtglib._norm("Generic")
    field = {k_spec: 15, k_gen: 15}
    syn = {k_spec: 13, k_gen: 2}
    refs = {"game_changers": set(), "tutors": set(), "fast_mana": set()}
    spec = deck_fit._staple_component(_card("Specific"), refs, _ctx(field, syn))
    gen = deck_fit._staple_component(_card("Generic"), refs, _ctx(field, syn))
    assert spec[0] > gen[0]
    assert "as common" in spec[1]


def test_lift_never_lowers_a_popular_staple():
    """The inclusion tier still applies: a 93% staple at 1.05x keeps its 15 points."""
    refs = {"game_changers": set(), "tutors": set(), "fast_mana": set()}
    k = mtglib._norm("Staple")
    pts, _ = deck_fit._staple_component(_card("Staple"), refs, _ctx({k: 93}, {k: 4}))
    assert pts == 15


def test_synergy_alone_keeps_its_old_tiers():
    refs = {"game_changers": set(), "tutors": set(), "fast_mana": set()}
    k = mtglib._norm("X")
    pts, det = deck_fit._staple_component(_card("X"), refs, _ctx({}, {k: 60}))
    assert pts == 15 and "synergy" in det


# ---- the sample size --------------------------------------------------------------------

def test_sample_size_comes_from_the_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(edhrec, "SNAP_DIR", str(tmp_path))
    (tmp_path / "test-commander.json").write_text(json.dumps(
        {"commander": "Test Commander", "inclusion": {}, "synergy": {}, "names": {},
         "sample_decks": 321}), encoding="utf-8")
    assert edhrec.sample_size("Test Commander") == 321
    assert edhrec.sample_size("Nobody At All") is None
    assert deck_fit.load_field_n("") is None


# ---- the optimizer: reads and the trade flag --------------------------------------------

COLL = """\
Quantity,Name,Identities,Types,Sub-types,Mana cost,Mana Value
1,Test Commander,G,Legendary Creature,Elf,{G},1
1,In Deck Spell,G,Instant,,{G},1
1,Rare Generic,G,Instant,,{1}{G},2
1,Rare Specific,G,Instant,,{1}{G},2
1,Rare Fringe,G,Instant,,{1}{G},2
"""

DECK = """\
# Title: L
# Commander: Test Commander
# Colors: G

# --- Commander ---
1 Test Commander

# --- Instants ---
1 In Deck Spell

# --- Basics ---
10 Forest
"""


def _setup(tmp_path, monkeypatch, field, synergy):
    import optimize
    d = tmp_path / "lift"
    d.mkdir(exist_ok=True)
    (d / "collection.csv").write_text(COLL, encoding="utf-8")
    (d / "deck.txt").write_text(DECK, encoding="utf-8")
    monkeypatch.setattr(optimize.deck_fit, "load_field", lambda *a, **k: field)
    monkeypatch.setattr(optimize.deck_fit, "load_synergy", lambda *a, **k: synergy)
    monkeypatch.setattr(optimize.deck_fit, "load_field_lands", lambda *a, **k: set())
    monkeypatch.setattr(optimize.deck_fit, "load_field_n", lambda *a, **k: 5000)
    coll = mtglib.load_collection(str(d / "collection.csv"))
    return d, coll, mtglib.index_by_name(coll)


def test_rarely_listed_reads_rank_by_lift_and_carry_it(tmp_path, monkeypatch):
    """19% at 1.2x is a staple that's merely unpopular here; 12% at 6x is this
    commander's card. The read list puts the specific one first."""
    import optimize
    field = {"in deck spell": 40, "rare generic": 19, "rare specific": 12,
             "rare fringe": 5, "forest": 90}
    synergy = {"in deck spell": 10, "rare generic": 3, "rare specific": 10,
               "rare fringe": 4}
    d, coll, idx = _setup(tmp_path, monkeypatch, field, synergy)
    r = optimize.optimize(str(d / "deck.txt"), coll, idx, str(d))
    rare = [x for x in r["reads"] if x["field"] is not None]
    names = [x["name"] for x in rare]
    assert names.index("Rare Specific") < names.index("Rare Generic")
    spec = next(x for x in rare if x["name"] == "Rare Specific")
    assert spec["lift"] == pytest.approx(6.0, abs=0.1)
    fringe = next(x for x in rare if x["name"] == "Rare Fringe")
    assert names.index("Rare Fringe") > names.index("Rare Generic"), \
        "under LIFT_MIN_INCLUSION a card earns no lift credit in the ranking"
    assert fringe["lift"] is not None, "the number is still shown"


def test_the_trade_flag_marks_engine_for_staple():
    import optimize
    ctx = _ctx({"engine": 30, "staple": 85, "mid": 40},
               {"engine": 25, "staple": 6, "mid": 20}, n=5000)
    d = optimize._lift_detail("Engine", "Staple", ctx)
    assert d["cut_lift"] == pytest.approx(5.9, abs=0.05), "6x, shrunk a little at 5,000 decks"
    assert d["add_lift"] == pytest.approx(1.07, abs=0.015)
    assert d["trades_specific"] is True
    assert optimize._lift_detail("Mid", "Staple", ctx)["trades_specific"] is False, \
        "2x isn't specific enough to warn about"
    assert optimize._lift_detail("Engine", "Unlisted", ctx)["trades_specific"] is True, \
        "an add the field has no numbers for can't vouch for itself either"


def test_review_payload_carries_lift_and_stays_json_safe():
    import optimize
    r = {"swaps": [("A", 5, "B", 60, "free")],
         "swaps_detail": [{"cut": "A", "add": "B", "cut_inc": 5, "add_inc": 60,
                           "cut_field_known": True, "add_field_known": True,
                           "cut_lift": 6.0, "add_lift": 1.1, "trades_specific": True}],
         "land_swaps": [], "reads": [{"name": "R", "fit": 80, "role": "draw",
                                      "field": 12, "lift": 6.0}],
         "buy_swaps": [], "role_ranges": {}}
    p = optimize.review_payload(r)
    json.dumps(p)
    prop = p["proposals"][0]
    assert prop["cut_lift"] == 6.0 and prop["add_lift"] == 1.1 and prop["trades_specific"]
    assert p["reads"][0]["lift"] == 6.0


# ---- an approved ⚡ run re-files only what it added (UAT F8, 2026-10-15) -----------------

TIDY_COLL = """\
Quantity,Name,Identities,Types,Sub-types,Mana cost,Mana Value
1,Test Commander,G,Legendary Creature,Elf,{G},1
1,Old Spell,G,Instant,,{G},1
1,New Spell,G,Instant,,{G},1
1,Robot Friend,,Artifact Creature,Robot,{3},3
"""

TIDY_DECK = """\
# Title: T
# Commander: Test Commander
# Colors: G

# --- Commander ---
1 Test Commander

# --- Instants ---
1 Old Spell

# --- Artifacts ---
1 Robot Friend

# --- Basics ---
10 Forest
"""


def test_an_approved_run_refiles_only_what_it_added(tmp_path, monkeypatch):
    """Robot Friend is an artifact creature the player filed under Artifacts. Approving
    an unrelated swap must not move it: the run's one-tap Undo only reverses the swap,
    so a moved card would never come back."""
    import optimize
    d = tmp_path / "tidy"
    d.mkdir()
    (d / "collection.csv").write_text(TIDY_COLL, encoding="utf-8")
    deck = d / "deck.txt"
    deck.write_text(TIDY_DECK, encoding="utf-8")
    coll = mtglib.load_collection(str(d / "collection.csv"))
    idx = mtglib.index_by_name(coll)
    r = {"swaps": [("Old Spell", 1, "New Spell", 60, "free")], "swaps_detail": [],
         "land_swaps": [], "role_ranges": {}, "buy_swaps": []}
    monkeypatch.setattr(optimize, "optimize", lambda *a, **k: r)
    out = optimize.apply_chosen(str(deck), coll, idx, str(d),
                                {optimize.proposal_key("spell", "Old Spell", "New Spell")})
    assert out["swaps"], "the approved swap was written"
    text = deck.read_text(encoding="utf-8")
    art = text.split("# --- Artifacts ---")[1].split("# ---")[0]
    assert "1 Robot Friend" in art, "an untouched card stays where the player put it"
    assert "1 New Spell" in text.split("# --- Instants ---")[1].split("# ---")[0]


def test_the_full_apply_pass_still_refiles_everything(tmp_path):
    """`--apply` keeps its 2026-08-20 behaviour: misfiles left by manual edits get fixed."""
    import optimize
    d = tmp_path / "tidy2"
    d.mkdir()
    (d / "collection.csv").write_text(TIDY_COLL, encoding="utf-8")
    deck = d / "deck.txt"
    deck.write_text(TIDY_DECK, encoding="utf-8")
    coll = mtglib.load_collection(str(d / "collection.csv"))
    optimize._tidy(str(deck), mtglib.index_by_name(coll))
    art = deck.read_text(encoding="utf-8").split("# --- Artifacts ---")
    assert len(art) == 1 or "Robot Friend" not in art[1].split("# ---")[0]
