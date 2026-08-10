"""Goldfish Monte Carlo — the engine that makes claims no closed form can check.

This is the file that keeps a simulator honest. Three classes of guard:

  * **Convergence** — with mulligans off, the sim's pre-mulligan opening-hand
    statistics must land on `manabase`'s exact hypergeometrics (±2pp at 4,000 games),
    and cards-seen-by-turn must match `manabase.cards_seen` EXACTLY. If the two
    engines disagree on what they both know, nothing they disagree about is credible.
  * **Determinism and pairing** — same seed, byte-identical report; and A/A over
    common random numbers produces deltas of exactly 0.0. That second one is the
    tripwire for any refactor that re-sorts a compiled deck: positional pairing dies
    silently otherwise, and the numbers stay plausible.
  * **Degenerates and data honesty** — all-lands, zero-land, hybrid pips, the
    mulligan floor, the >25% no-data gate.

Every test is offline, in-code or tmp_path, and capped at 4,000 games.
"""
import json
import os

import pytest

import deckcore
import goldfish
import manabase
import mtglib

C = mtglib.Card


# --------------------------------------------------------------------------- #
# Fixtures — hand-built Cards, so the model tier under test is unambiguous
# --------------------------------------------------------------------------- #
def _mono_deck(lands=37, land_name="Island", color="U", cost="{%d}{U}",
               commander_cost="{3}{U}", nonlands=62):
    """A 100-card mono-colored deck on the color-identity fallback tier."""
    cards = [C(name=land_name, quantity=lands, mana_value=0.0, colors={color},
               identity={color}, types=["Land"])]
    for i in range(nonlands):
        cards.append(C(name=f"Spell {i}", quantity=1, mana_value=float(i % 6 + 1),
                       colors={color}, identity={color}, mana_cost=cost % (i % 6),
                       types=["Instant"]))
    cards.append(C(name="Test Commander", quantity=1, mana_value=4.0, colors={color},
                   identity={color}, mana_cost=commander_cost,
                   types=["Legendary", "Creature"]))
    return cards


@pytest.fixture
def mono37():
    return goldfish.compile_deck(_mono_deck(), "Test Commander")


# --------------------------------------------------------------------------- #
# Compilation
# --------------------------------------------------------------------------- #
def test_cost_tokenizer_treats_one_symbol_as_one_pip():
    """The documented deviation from `mtglib.pip_counts`: a hybrid symbol is ONE pip
    payable by either half, not half a pip of each. The fractional split is right for
    aggregate Karsten demand and wrong for "can I cast this"."""
    pips, generic = goldfish.parse_cost("{2}{W/U}{B}")
    assert generic == 2
    assert [(sorted(p), a) for p, a in pips] == [(["U", "W"], 0), (["B"], 0)]
    assert goldfish.parse_cost("{W/P}")[0] == [(frozenset("W"), 0)]     # no life math
    assert goldfish.parse_cost("{2/W}")[0] == [(frozenset("W"), 2)]     # or 2 generic
    assert goldfish.parse_cost("{X}{R}") == ([(frozenset("R"), 0)], 0)  # X = 0
    assert goldfish.parse_cost("{C}{1}") == ([(frozenset("C"), 0)], 1)  # {C} is a pip
    assert goldfish.parse_cost("") == ([], 0)


def test_commander_leaves_the_library_exactly_once():
    cards = _mono_deck()
    c = goldfish.compile_deck(cards, "Test Commander")
    assert c["commander"].name == "Test Commander"
    assert c["library"] == sorted(c["library"], key=lambda s: 0)   # order preserved
    assert len(c["library"]) == 99
    assert not any(s.name == "Test Commander" for s in c["library"])


def test_commander_matching_is_front_face_aware():
    """`' // '` with spaces is the split-card separator — the deck file lists the
    front face and the collection the full name, and `name_keys` has to bridge them
    or the commander gets shuffled into the library."""
    cards = _mono_deck(nonlands=10)
    cards[-1] = C(name="Cmd Front // Cmd Back", quantity=1, mana_value=4.0,
                  colors={"U"}, identity={"U"}, mana_cost="{3}{U}",
                  types=["Legendary", "Creature"])
    c = goldfish.compile_deck(cards, "Cmd Front")
    assert c["commander"] is not None
    assert not any("Cmd Front" in s.name for s in c["library"])


def test_per_copy_expansion_is_in_file_order():
    """The A/B pairing is positional: copies expand where the deck file put them."""
    cards = [C(name="A", quantity=2, mana_value=1.0, mana_cost="{1}", types=["Instant"]),
             C(name="B", quantity=1, mana_value=1.0, mana_cost="{1}", types=["Instant"])]
    lib = goldfish.compile_deck(cards)["library"]
    assert [s.name for s in lib] == ["A", "A", "B"]


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_same_seed_same_report(mono37):
    a = goldfish.simulate(mono37, games=300, seed=7)
    b = goldfish.simulate(mono37, games=300, seed=7)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_different_seeds_differ(mono37):
    a = goldfish.simulate(mono37, games=300, seed=1)
    b = goldfish.simulate(mono37, games=300, seed=2)
    assert a["p_cast_by"] != b["p_cast_by"] or a["keepable_first7"] != b["keepable_first7"]


def test_the_global_rng_is_never_touched(mono37):
    """A sim that reaches for `random.random()` would be reproducible only until some
    other module seeded the global generator."""
    import random
    random.seed(12345)
    before = random.random()
    goldfish.simulate(mono37, games=200, seed=0)
    random.seed(12345)
    assert random.random() == before


# --------------------------------------------------------------------------- #
# Convergence against the closed forms
# --------------------------------------------------------------------------- #
GAMES = 4000
TOL = 0.02          # ±2pp at 4,000 games


def test_keepable_converges_to_the_hypergeometric(mono37):
    rep = goldfish.simulate(mono37, games=GAMES, seed=11, mulligan=False)
    assert abs(rep["keepable_first7"] - manabase.land_odds(37)["keepable"]) < TOL


def test_three_lands_in_the_opener_converges(mono37):
    rep = goldfish.simulate(mono37, games=GAMES, seed=12, mulligan=False)
    exact = manabase.hypergeom_at_least(99, 37, 7, 3)
    assert abs(rep["p_ge3_open"] - exact) < TOL


def test_cards_seen_matches_the_closed_form_exactly(mono37):
    """Not "close" — the same quantity. On the play you skip the turn-1 draw, and both
    engines have to count that the same way or every by-turn comparison is off by one."""
    rep = goldfish.simulate(mono37, games=200, seed=13, mulligan=False)
    assert rep["cards_seen_by_turn"]["4"] == float(manabase.cards_seen(4))
    assert rep["cards_seen_by_turn"]["1"] == float(manabase.cards_seen(1))


# --------------------------------------------------------------------------- #
# Degenerate decks — where a broken model shows up loudest
# --------------------------------------------------------------------------- #
def test_all_lands_deck_casts_the_commander_on_curve():
    cards = [C(name="Plains", quantity=99, mana_value=0.0, colors={"W"},
               identity={"W"}, types=["Land"]),
             C(name="Cmd", quantity=1, mana_value=3.0, colors={"W"}, identity={"W"},
               mana_cost="{2}{W}", types=["Legendary", "Creature"])]
    rep = goldfish.simulate(goldfish.compile_deck(cards, "Cmd"), games=300, seed=5)
    assert rep["p_cast_by"]["3"] == 1.0
    assert rep["screw"] == 0.0
    assert rep["flood"] == 1.0                       # by definition, and honestly so


def test_zero_land_deck_never_casts_anything():
    cards = [C(name=f"S{i}", quantity=1, mana_value=2.0, colors={"W"}, identity={"W"},
               mana_cost="{1}{W}", types=["Instant"]) for i in range(99)]
    cards.append(C(name="Cmd", quantity=1, mana_value=3.0, colors={"W"},
                   identity={"W"}, mana_cost="{2}{W}", types=["Legendary", "Creature"]))
    rep = goldfish.simulate(goldfish.compile_deck(cards, "Cmd"), games=200, seed=5)
    assert rep["p_cast_by"]["8"] == 0.0
    assert rep["screw"] == 1.0
    assert all(c["cast_rate"] == 0.0 for c in rep["cards"])


def test_ample_mono_color_lands_never_block_on_color():
    """One color, plenty of sources: anything that fails to cast failed on quantity of
    mana, never on the color matcher."""
    cards = [C(name="Plains", quantity=60, mana_value=0.0, colors={"W"},
               identity={"W"}, types=["Land"]),
             C(name="One Drop", quantity=39, mana_value=1.0, colors={"W"},
               identity={"W"}, mana_cost="{W}", types=["Creature"]),
             C(name="Cmd", quantity=1, mana_value=1.0, colors={"W"}, identity={"W"},
               mana_cost="{W}", types=["Legendary", "Creature"])]
    rep = goldfish.simulate(goldfish.compile_deck(cards, "Cmd"), games=300, seed=5)
    assert rep["p_cast_by"]["1"] > 0.55              # whenever a Plains is in the opener
    assert rep["p_cast_by"]["3"] == 1.0


def test_a_hybrid_pip_casts_off_either_color_alone():
    """The rule the tokenizer exists to guarantee: `{W/U}` needs W *or* U, not both.
    Under the fractional pip-split it borrowed from `pip_counts`, this card would sit
    in hand forever in a mono-white deck."""
    base = [C(name="Plains", quantity=60, mana_value=0.0, colors={"W"},
              identity={"W"}, types=["Land"]),
            C(name="Cmd", quantity=1, mana_value=1.0, colors={"W"}, identity={"W"},
              mana_cost="{W}", types=["Legendary", "Creature"])]
    hybrid = base + [C(name="Hybrid Thing", quantity=39, mana_value=1.0,
                       colors={"W", "U"}, identity={"W", "U"}, mana_cost="{W/U}",
                       types=["Creature"])]
    mono_u = base + [C(name="Blue Thing", quantity=39, mana_value=1.0, colors={"U"},
                       identity={"U"}, mana_cost="{U}", types=["Creature"])]
    hy = goldfish.simulate(goldfish.compile_deck(hybrid, "Cmd"), games=300, seed=6)
    bl = goldfish.simulate(goldfish.compile_deck(mono_u, "Cmd"), games=300, seed=6)
    assert [c for c in hy["cards"] if c["name"] == "Hybrid Thing"][0]["cast_rate"] == 1.0
    assert [c for c in bl["cards"] if c["name"] == "Blue Thing"][0]["cast_rate"] == 0.0


def test_the_mulligan_floor_stops_at_five(mono37):
    """A deck that can never present a keepable seven mulls exactly twice and keeps
    five — and the pre-mulligan first-7 statistic is measured before any of it, so it
    must be unaffected by the mulligan setting."""
    cards = [C(name="Plains", quantity=99, mana_value=0.0, colors={"W"},
               identity={"W"}, types=["Land"]),
             C(name="Cmd", quantity=1, mana_value=1.0, colors={"W"}, identity={"W"},
               mana_cost="{W}", types=["Legendary", "Creature"])]
    compiled = goldfish.compile_deck(cards, "Cmd")
    rec = goldfish.play_game(__import__("random").Random(1), compiled["commander"],
                             compiled["library"])
    assert rec["mulls"] == goldfish.MULL_FLOOR

    on = goldfish.simulate(mono37, games=800, seed=21, mulligan=True)
    off = goldfish.simulate(mono37, games=800, seed=21, mulligan=False)
    assert on["keepable_first7"] == off["keepable_first7"]
    assert on["mulligan_rate"] > 0 and off["mulligan_rate"] == 0.0


def test_bottoming_sheds_excess_lands_before_spells():
    land = goldfish.compile_card(C(name="Plains", quantity=1, colors={"W"},
                                   identity={"W"}, types=["Land"]))
    spell = goldfish.compile_card(C(name="Big", quantity=1, mana_value=8.0,
                                    mana_cost="{8}", types=["Sorcery"]))
    hand = [land] * 5 + [spell, spell]
    kept, bottomed = goldfish._bottom(hand, 2)
    assert [c.name for c in bottomed] == ["Plains", "Plains"]
    assert sum(1 for c in kept if c.is_land) == 3


# --------------------------------------------------------------------------- #
# Honesty gate + assumptions
# --------------------------------------------------------------------------- #
def test_more_than_a_quarter_unknown_nonlands_trips_the_gate():
    cards = [C(name="Plains", quantity=37, mana_value=0.0, colors={"W"},
               identity={"W"}, types=["Land"])]
    for i in range(40):                      # known
        cards.append(C(name=f"Known {i}", quantity=1, mana_value=2.0, colors={"W"},
                       identity={"W"}, mana_cost="{1}{W}", types=["Instant"]))
    for i in range(23):                      # unowned / unenriched: no mana value
        cards.append(C(name=f"Unknown {i}", quantity=1))
    compiled = goldfish.compile_deck(cards)
    assert compiled["have_data"] is False
    rep = goldfish.simulate(compiled, games=100, seed=1)
    assert rep["have_data"] is False
    assert "enrich" in rep["note"].lower()


def test_the_gate_stays_open_when_the_data_is_there(mono37):
    rep = goldfish.simulate(mono37, games=100, seed=1)
    assert rep["have_data"] is True and rep["note"] is None


def test_assumptions_ship_as_data_and_name_the_fallback(mono37):
    """Substrings, never verbatim prose — a wording fix must not touch five files."""
    rep = goldfish.simulate(mono37, games=100, seed=1)
    joined = " ".join(rep["assumptions"])
    for token in ("Goldfish", "London mulligan", "On the play", "Seeded Monte Carlo",
                  "hypergeometrics"):
        assert token in joined
    assert "IDENTITY" in joined              # this deck is on the fallback tier
    assert rep["model"] == "identity"
    for key in ("screw", "flood", "keepable_first7", "p_cast_by"):
        assert rep["definitions"][key]


def test_definitions_travel_with_the_numbers(mono37):
    rep = goldfish.simulate(mono37, games=100, seed=1)
    assert str(goldfish.SCREW_LANDS) in rep["definitions"]["screw"]
    assert str(goldfish.FLOOD_LANDS) in rep["definitions"]["flood"]


# --------------------------------------------------------------------------- #
# C2 — A/B over common random numbers
# --------------------------------------------------------------------------- #
def _ab_fixture():
    cards = _mono_deck(nonlands=61)
    cards.insert(1, C(name="Old Card", quantity=1, mana_value=6.0, colors={"U"},
                      identity={"U"}, mana_cost="{5}{U}", types=["Sorcery"]))
    coll = list(cards) + [C(name="New Card", quantity=1, mana_value=1.0, colors={"U"},
                            identity={"U"}, mana_cost="{U}", types=["Instant"])]
    return (goldfish.compile_deck(cards, "Test Commander"),
            mtglib.index_by_name(coll))


def test_an_a_a_run_produces_exactly_zero_deltas():
    """The tripwire. Swap a card for itself over common random numbers and EVERY
    per-game difference is 0.0 — no tolerance. If a future refactor re-sorts a
    compiled deck, the positional pairing dies here rather than in production, where
    it would keep printing plausible numbers."""
    compiled, idx = _ab_fixture()
    ab = goldfish.simulate_ab(compiled, "Old Card", "Old Card", idx, games=400, seed=3)
    assert "error" not in ab
    for m, d in ab["deltas"].items():
        assert d["delta"] == 0.0, m
        assert d["ci"] == 0.0, m


def test_pairing_is_narrower_than_two_independent_runs():
    compiled, idx = _ab_fixture()
    ab = goldfish.simulate_ab(compiled, "Old Card", "New Card", idx, games=1500, seed=4)
    tightened = 0
    for m, d in ab["deltas"].items():
        assert d["ci"] <= d["unpaired_ci"] + 1e-9, m
        if d["ci"] < d["unpaired_ci"] - 1e-9:
            tightened += 1
    assert tightened, "common random numbers bought no precision at all"


def test_ab_refuses_a_card_it_cannot_look_up():
    compiled, idx = _ab_fixture()
    ab = goldfish.simulate_ab(compiled, "Old Card", "Definitely Not A Card", idx,
                              games=50, seed=1)
    assert "error" in ab and "a" not in ab
    assert "resolve" in ab["error"]


def test_ab_refuses_to_cut_a_card_the_deck_does_not_run():
    compiled, idx = _ab_fixture()
    ab = goldfish.simulate_ab(compiled, "Not In Deck", "New Card", idx, games=50)
    assert "error" in ab and "a" not in ab


def test_ab_refuses_a_swap_that_would_break_singleton():
    compiled, idx = _ab_fixture()
    ab = goldfish.simulate_ab(compiled, "Old Card", "Spell 0", idx, games=50)
    assert "error" in ab and "singleton" in ab["error"]


# --------------------------------------------------------------------------- #
# C3 — sim_for_deck, the cache, and the CLI
# --------------------------------------------------------------------------- #
DECK = """\
# Title: Sim Deck
# Commander: Test Commander
# Colors: W U

# --- Commander ---
1 Test Commander

# --- Spells ---
1 Sol Ring
2 Arcane Signet
1 Counterspell
1 Serra Angel

# --- Lands ---
20 Island
1 Command Tower
"""


@pytest.fixture
def sim_deck(tmp_path, collection_file):
    p = tmp_path / "simdeck.txt"
    p.write_text(DECK, encoding="utf-8")
    return str(p), collection_file


def test_sim_for_deck_runs_a_saved_deck(sim_deck, tmp_path):
    deck, coll = sim_deck
    rep = goldfish.sim_for_deck(deck, coll, games=200,
                                cache_dir=str(tmp_path / "cache"))
    assert rep is not None
    assert rep["commander"] == "Test Commander"
    assert rep["library"] == 26            # 27 deck cards, commander removed once
    assert rep["assumptions"]


def test_sim_for_deck_returns_none_instead_of_raising(tmp_path, collection_file):
    assert goldfish.sim_for_deck(str(tmp_path / "nope.txt"), collection_file,
                                 games=10, cache_dir=str(tmp_path / "c")) is None


def test_the_cache_is_used_on_the_second_call(sim_deck, tmp_path, monkeypatch):
    deck, coll = sim_deck
    cdir = str(tmp_path / "cache")
    calls = []
    real = goldfish.simulate
    monkeypatch.setattr(goldfish, "simulate",
                        lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    first = goldfish.sim_for_deck(deck, coll, games=150, cache_dir=cdir)
    second = goldfish.sim_for_deck(deck, coll, games=150, cache_dir=cdir)
    assert len(calls) == 1
    assert first == second
    assert os.path.exists(os.path.join(cdir, "simdeck.json"))


def test_editing_the_deck_invalidates_the_cache(sim_deck, tmp_path, monkeypatch):
    """The cache is pure speed. Any deck edit must miss it, or the dashboard would
    show yesterday's deck's numbers next to today's decklist."""
    deck, coll = sim_deck
    cdir = str(tmp_path / "cache")
    calls = []
    real = goldfish.simulate
    monkeypatch.setattr(goldfish, "simulate",
                        lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    goldfish.sim_for_deck(deck, coll, games=150, cache_dir=cdir)
    with open(deck, "a", encoding="utf-8") as f:
        f.write("1 Swords to Plowshares\n")
    os.utime(deck, (0, 10 ** 9))           # a mtime the first key can't have had
    goldfish.sim_for_deck(deck, coll, games=150, cache_dir=cdir)
    assert len(calls) == 2


def test_changing_a_parameter_invalidates_the_cache(sim_deck, tmp_path, monkeypatch):
    deck, coll = sim_deck
    cdir = str(tmp_path / "cache")
    calls = []
    real = goldfish.simulate
    monkeypatch.setattr(goldfish, "simulate",
                        lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    goldfish.sim_for_deck(deck, coll, games=150, seed=0, cache_dir=cdir)
    goldfish.sim_for_deck(deck, coll, games=150, seed=1, cache_dir=cdir)
    goldfish.sim_for_deck(deck, coll, games=200, seed=1, cache_dir=cdir)
    assert len(calls) == 3


def test_no_cache_bypasses_the_cache_entirely(sim_deck, tmp_path, monkeypatch):
    deck, coll = sim_deck
    cdir = str(tmp_path / "cache")
    calls = []
    real = goldfish.simulate
    monkeypatch.setattr(goldfish, "simulate",
                        lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    goldfish.sim_for_deck(deck, coll, games=100, cache=False, cache_dir=cdir)
    goldfish.sim_for_deck(deck, coll, games=100, cache=False, cache_dir=cdir)
    assert len(calls) == 2
    assert not os.path.exists(os.path.join(cdir, "simdeck.json"))


def test_the_cache_writes_only_where_it_was_told(sim_deck, tmp_path):
    deck, coll = sim_deck
    cdir = tmp_path / "cache"
    goldfish.sim_for_deck(deck, coll, games=100, cache_dir=str(cdir))
    assert [p.name for p in cdir.iterdir()] == ["simdeck.json"]


def test_cli_smoke(sim_deck, tmp_path, capsys, monkeypatch):
    deck, coll = sim_deck
    monkeypatch.setattr(goldfish, "CACHE_DIR", str(tmp_path / "cache"))
    assert goldfish.main(["--deck", deck, "--collection", coll, "--games", "150"]) == 0
    out = capsys.readouterr().out
    assert "GOLDFISH" in out and "Assumptions:" in out


def test_cli_json_carries_the_run_parameters(sim_deck, tmp_path, capsys, monkeypatch):
    deck, coll = sim_deck
    monkeypatch.setattr(goldfish, "CACHE_DIR", str(tmp_path / "cache"))
    assert goldfish.main(["--deck", deck, "--collection", coll, "--games", "150",
                          "--seed", "9", "--json", "--no-cache"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["games"] == 150 and rep["seed"] == 9 and rep["assumptions"]


def test_cli_ab_emits_deltas(sim_deck, tmp_path, capsys, monkeypatch):
    deck, coll = sim_deck
    monkeypatch.setattr(goldfish, "CACHE_DIR", str(tmp_path / "cache"))
    rc = goldfish.main(["--deck", deck, "--collection", coll, "--games", "150",
                        "--ab", "Serra Angel=Swords to Plowshares", "--json"])
    assert rc == 0
    ab = json.loads(capsys.readouterr().out)
    assert ab["out"] == "Serra Angel" and ab["in"] == "Swords to Plowshares"
    assert "commander_by_t4" in ab["deltas"]


def test_cli_ab_refusal_degrades_to_exit_1(sim_deck, tmp_path, capsys, monkeypatch):
    deck, coll = sim_deck
    monkeypatch.setattr(goldfish, "CACHE_DIR", str(tmp_path / "cache"))
    rc = goldfish.main(["--deck", deck, "--collection", coll, "--games", "50",
                        "--ab", "Serra Angel=Nonexistent Card"])
    assert rc == 1
    assert "resolve" in capsys.readouterr().out


def test_cli_missing_file_is_a_usage_error(collection_file, capsys):
    assert goldfish.main(["--deck", "/nope/deck.txt",
                          "--collection", collection_file]) == 2


def test_cli_no_mulligan_is_reflected_in_the_assumptions(sim_deck, tmp_path, capsys,
                                                         monkeypatch):
    deck, coll = sim_deck
    monkeypatch.setattr(goldfish, "CACHE_DIR", str(tmp_path / "cache"))
    goldfish.main(["--deck", deck, "--collection", coll, "--games", "100",
                   "--no-mulligan", "--json", "--no-cache"])
    rep = json.loads(capsys.readouterr().out)
    assert rep["mulligan"] is False
    assert any("Mulligans disabled" in a for a in rep["assumptions"])


# --------------------------------------------------------------------------- #
# C6 — the enriched mana model (Card.produced / Card.flags)
# --------------------------------------------------------------------------- #
def _enriched_land(name, produced, flags=(), qty=1):
    return C(name=name, quantity=qty, mana_value=0.0, colors=set(), identity=set(),
             types=["Land"], produced=set(produced), flags=set(flags))


def test_an_enriched_land_taps_for_what_it_produces_not_its_identity():
    land = goldfish.compile_card(_enriched_land("Weird Land", "U", qty=1))
    assert land.produces == frozenset("U")
    assert land.model == "exact"
    # Enriched-and-empty is a real answer, not a missing one.
    maze = goldfish.compile_card(_enriched_land("Maze of Ith", ""))
    assert maze.produces == frozenset() and maze.model == "exact"
    assert not maze.is_producer


def test_an_unenriched_land_falls_back_to_identity_and_says_so():
    land = goldfish.compile_card(C(name="Plain Land", quantity=1, colors={"G"},
                                   identity={"G"}, types=["Land"]))
    assert land.produces == frozenset("G") and land.model == "identity"


def test_a_tapland_gives_nothing_on_the_turn_it_drops():
    """The single clearest thing the enriched tier buys over the closed forms — and
    an A/B over common random numbers is how you see it in isolation."""
    def deck(flags):
        return [_enriched_land("Slow Land", "W", flags, qty=60),
                C(name="One Drop", quantity=39, mana_value=1.0, colors={"W"},
                  identity={"W"}, mana_cost="{W}", types=["Creature"]),
                C(name="Cmd", quantity=1, mana_value=1.0, colors={"W"}, identity={"W"},
                  mana_cost="{W}", types=["Legendary", "Creature"])]
    fast = goldfish.simulate(goldfish.compile_deck(deck(()), "Cmd"), games=400, seed=8)
    slow = goldfish.simulate(goldfish.compile_deck(deck(("etb-tapped",)), "Cmd"),
                             games=400, seed=8)
    assert fast["p_cast_by"]["1"] > 0.5
    assert slow["p_cast_by"]["1"] == 0.0          # nothing is castable on turn one
    assert slow["p_cast_by"]["2"] > 0.0


def test_a_conditional_tapland_is_pessimistically_tapped():
    """Q-A2: where a policy must be picked, pick the one that can't flatter the deck."""
    cond = goldfish.compile_card(_enriched_land("Check Land", "W",
                                                ("etb-tapped-cond",)))
    assert cond.etb_tapped is True


def test_a_colorless_land_pays_generic_but_never_a_colored_pip():
    cards = [_enriched_land("Colorless Land", "C", qty=60),
             C(name="Double White", quantity=20, mana_value=2.0, colors={"W"},
               identity={"W"}, mana_cost="{W}{W}", types=["Creature"],
               produced=set(), flags=set()),
             C(name="Generic Thing", quantity=19, mana_value=2.0, mana_cost="{2}",
               types=["Artifact"], produced=set(), flags=set()),
             C(name="Cmd", quantity=1, mana_value=2.0, mana_cost="{2}",
               types=["Legendary", "Creature"], produced=set(), flags=set())]
    rep = goldfish.simulate(goldfish.compile_deck(cards, "Cmd"), games=300, seed=9)
    by_name = {c["name"]: c for c in rep["cards"]}
    assert by_name["Double White"]["cast_rate"] == 0.0
    assert by_name["Generic Thing"]["cast_rate"] > 0.95   # only if drawn
    assert rep["model"] == "exact"


def test_a_mana2_rock_accelerates_the_commander():
    """Sol Ring's whole point. `mana2` is what makes the rock worth two, and the rock
    is deliberately modeled as active the turn AFTER it resolves."""
    def deck(with_rock):
        cards = [_enriched_land("Plains", "W", qty=40),
                 C(name="Cmd", quantity=1, mana_value=4.0, colors={"W"},
                   identity={"W"}, mana_cost="{3}{W}", types=["Legendary", "Creature"],
                   produced=set(), flags=set())]
        filler = 59
        if with_rock:
            cards.append(C(name="Sol Ring", quantity=20, mana_value=1.0,
                           mana_cost="{1}", types=["Artifact"], produced={"C"},
                           flags={"rock", "ramp", "mana2"}))
            filler -= 20
        cards.append(C(name="Filler", quantity=filler, mana_value=9.0,
                       mana_cost="{9}", types=["Sorcery"], produced=set(),
                       flags=set()))
        return goldfish.compile_deck(cards, "Cmd")
    plain = goldfish.simulate(deck(False), games=400, seed=10)
    ringed = goldfish.simulate(deck(True), games=400, seed=10)
    assert ringed["p_cast_by"]["3"] > plain["p_cast_by"]["3"]


def test_the_model_label_switches_with_coverage():
    enriched = [_enriched_land("E Land", "W", qty=50),
                C(name="E Spell", quantity=50, mana_value=1.0, mana_cost="{W}",
                  types=["Instant"], produced=set(), flags=set())]
    mixed = enriched + [C(name="Plain", quantity=1, mana_value=1.0, colors={"W"},
                          identity={"W"}, mana_cost="{W}", types=["Instant"])]
    assert goldfish.compile_deck(enriched)["model"] == "exact"
    assert goldfish.compile_deck(mixed)["model"] == "mixed"
    cov = goldfish.compile_deck(mixed)["coverage"]
    assert cov["exact"] == 100 and cov["identity"] == 1


def test_an_enriched_run_drops_the_identity_warning(mono37):
    enriched = [_enriched_land("E Land", "U", qty=37),
                C(name="E Spell", quantity=62, mana_value=1.0, mana_cost="{U}",
                  types=["Instant"], produced=set(), flags=set()),
                C(name="Cmd", quantity=1, mana_value=1.0, mana_cost="{U}",
                  types=["Legendary", "Creature"], produced=set(), flags=set())]
    rep = goldfish.simulate(goldfish.compile_deck(enriched, "Cmd"), games=100, seed=1)
    assert not any("IDENTITY" in a for a in rep["assumptions"])
    fallback = goldfish.simulate(mono37, games=100, seed=1)
    assert any("IDENTITY" in a for a in fallback["assumptions"])


# --------------------------------------------------------------------------- #
# C6 — the deck-companion leg: .attrs.csv carries Produced/Flags
# --------------------------------------------------------------------------- #
def test_deck_attrs_without_the_columns_leave_produced_unknown(tmp_path):
    """Column ABSENT means unknown — `apply_attrs` must not write an empty set, or
    every pre-enrichment companion file would silently claim its cards make no mana."""
    p = tmp_path / "d.attrs.csv"
    p.write_text("Name,Type,MV,Colors\nSol Ring,Artifact,1,\n", encoding="utf-8")
    card = C(name="Sol Ring", quantity=1)
    deckcore.apply_attrs([card], deckcore.load_attrs(str(p)))
    assert card.produced is None and card.flags == set()


def test_deck_attrs_carry_produced_and_flags(tmp_path):
    p = tmp_path / "d.attrs.csv"
    p.write_text("Name,Type,MV,Colors,Produced,Flags\n"
                 "Sol Ring,Artifact,1,,C,rock;ramp;mana2\n"
                 "Maze of Ith,Land,0,,,\n", encoding="utf-8")
    ring, maze = C(name="Sol Ring", quantity=1), C(name="Maze of Ith", quantity=1)
    deckcore.apply_attrs([ring, maze], deckcore.load_attrs(str(p)))
    assert ring.produced == {"C"} and ring.flags == {"rock", "ramp", "mana2"}
    assert maze.produced == set() and maze.flags == set()    # empty != absent


def test_a_companion_file_powers_the_enriched_model_end_to_end(tmp_path):
    """A fresh clone has only the name-only snapshot; a deck `.attrs.csv` is how the
    enriched tier reaches the sim anyway."""
    deck = tmp_path / "companion.txt"
    deck.write_text("# Commander: Cmd\n1 Cmd\n40 Slow Land\n58 One Drop\n",
                    encoding="utf-8")
    (tmp_path / "companion.attrs.csv").write_text(
        "Name,Type,MV,Colors,Produced,Flags\n"
        "Cmd,Legendary Creature,1,W,,\n"
        "Slow Land,Land,0,W,W,etb-tapped\n"
        "One Drop,Creature,1,W,,\n", encoding="utf-8")
    coll = tmp_path / "coll.txt"
    coll.write_text("1 Cmd\n40 Slow Land\n58 One Drop\n", encoding="utf-8")
    rep = goldfish.sim_for_deck(str(deck), str(coll), games=200,
                                cache_dir=str(tmp_path / "cache"))
    assert rep is not None and rep["model"] == "exact"
    assert rep["p_cast_by"]["1"] == 0.0        # every land enters tapped
