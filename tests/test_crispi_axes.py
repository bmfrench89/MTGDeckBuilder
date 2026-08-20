"""CRISPI Resilience + Consistency, and the guard that the composite stays dead.

`docs/spec-crispi-axes.md` Phases B, C and D. The defect these replace was one row:

    bartolome-del-presidio-600-combos   Bracket 4 Optimized   31/100 Casual

Bracket 4 and "Casual" together, because the bracket saw twelve early infinites
while the composite saw no tutors, no fast mana and no draw. Phase D deleted the
0-100 and its tier adjective outright rather than renaming them to `legacy_power`,
on the reasoning that a number kept but renamed is the same lie in a smaller font —
and that deleting it makes the defect UNREPRESENTABLE instead of merely suppressed.

`test_composite_is_gone_from_the_payload` is that guarantee. If a future change
reintroduces a roll-up, it fails here rather than in a player's terminal.
"""
import os

import power

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _staples(prot=(), rec=()):
    import mtglib
    return {"protection": {mtglib._norm(n) for n in prot},
            "recursion": {mtglib._norm(n) for n in rec}}


def _cards(*names):
    import mtglib
    return [mtglib.Card(quantity=1, name=n) for n in names]


# ---------------------------------------------------------------- Resilience
def test_no_curated_list_is_unmeasured_not_zero_protection():
    """Absent data and a measured zero are different claims — the same
    empty-vs-absent rule the collection attrs live under. A deck scored against an
    empty list has not been found wanting; it has not been looked at."""
    ax = power.resilience_axis(_cards("Sol Ring"), _staples())
    assert ax["label"] == "unmeasured"
    assert ax["protection"] is None and ax["recursion"] is None


def test_counts_protection_and_recursion_separately():
    ax = power.resilience_axis(
        _cards("Swiftfoot Boots", "Lightning Greaves", "Sun Titan", "Sol Ring"),
        _staples(prot=["Swiftfoot Boots", "Lightning Greaves"], rec=["Sun Titan"]))
    assert (ax["protection"], ax["recursion"]) == (2, 1)


def test_bands_are_reported_conditionally_not_as_a_verdict():
    """The research bands are conditional on commander-dependence (5-8 if the
    commander must live, 2-4 if the deck rebuilds), and the data cannot tell which
    applies. The axis must name the band, never declare pass/fail."""
    thin = power.resilience_axis(_cards("Sol Ring"), _staples(prot=["Swiftfoot Boots"]))
    assert "below both researched bands" in thin["detail"]
    mid = power.resilience_axis(
        _cards("Swiftfoot Boots", "Lightning Greaves"),
        _staples(prot=["Swiftfoot Boots", "Lightning Greaves"]))
    assert "2-4" in mid["detail"]


def test_declared_header_leads_but_the_count_survives(tmp_path):
    """Mirrors `# Bracket:` — the player's judgement headlines, the evidence is
    never dropped, because the header records intent rather than silencing data."""
    d = tmp_path / "x.txt"
    d.write_text("# Commander: X\n# Resilience: high\n\n1 Sol Ring\n", encoding="utf-8")
    assert power.read_declared_resilience(str(d)) == "high"
    ax = power.resilience_axis(_cards("Swiftfoot Boots"),
                               _staples(prot=["Swiftfoot Boots"]), declared="high")
    assert ax["label"] == "high" and ax["protection"] == 1


def test_declared_resilience_rejects_junk(tmp_path):
    d = tmp_path / "y.txt"
    d.write_text("# Resilience: banana\n\n1 Sol Ring\n", encoding="utf-8")
    assert power.read_declared_resilience(str(d)) is None


def test_every_curated_row_is_one_of_the_two_roles():
    """The shipped CSV is runner-verified; a typo'd Role would silently drop cards
    from the count rather than erroring."""
    st = power.load_resilience_staples()
    assert st["protection"] and st["recursion"]


# --------------------------------------------------------------- Consistency
def _rep(ramp=0, draw=0, removal=0):
    return {"categories": {"ramp": ramp, "draw": draw, "removal": removal}}


def test_redundancy_led_is_a_real_answer_not_a_failure():
    """This collection runs 0-1 tutors across all nine decks. An axis that only
    counted tutors would call every one of them inconsistent, which the research
    explicitly contradicts: redundancy plus draw is a valid consistency mechanism."""
    ax = power.consistency_axis(_rep(ramp=11, draw=15, removal=7), tutors=1, draw=15)
    assert ax["label"].startswith("redundancy-led")
    assert ax["deep_roles"] == 2


def test_tutor_led_when_the_deck_actually_tutors():
    ax = power.consistency_axis(_rep(ramp=2), tutors=9, draw=4)
    assert ax["label"].startswith("tutor-led")


def test_thin_when_neither_mechanism_is_present():
    ax = power.consistency_axis(_rep(ramp=2, draw=3, removal=1), tutors=0, draw=3)
    assert ax["label"].startswith("thin")


def test_tutors_may_arrive_as_a_name_list():
    """`_match` hands back matched NAMES while `draw` is already a count; comparing
    a list to an int raised a TypeError when this shipped."""
    ax = power.consistency_axis(_rep(ramp=9), tutors=["A", "B"], draw=["x"])
    assert ax["tutors"] == 2 and ax["draw"] == 1


# ------------------------------------------------------- Phase D: it stays dead
def test_composite_is_gone_from_the_payload():
    """The defect made unrepresentable. No 0-100, no tier adjective — deleted, not
    renamed to `legacy_power`, because a renamed number gets re-displayed and the
    tests then have to assert it ISN'T printed."""
    import deck_stats, deckcore, mtglib
    idx = mtglib.index_by_name(mtglib.load_collection(
        os.path.join(ROOT, "data/collection/collection_snapshot.txt")))
    deck = mtglib.parse_deck(open(
        os.path.join(ROOT, "data/decks/yshtola-nights-blessed.txt"),
        encoding="utf-8").read())
    enr, miss = deck_stats.analyze(deck, idx)
    rep = deck_stats.build_report(deck, enr, miss, idx)
    a = power.assess(enr, rep, power.load_refs())
    for dead in ("power", "tier", "legacy_power"):
        assert dead not in a, f"the retired composite came back as {dead!r}"
    for axis in ("speed", "resilience", "consistency"):
        assert a[axis]["label"]
    assert a["components"], "raw component counts must SURVIVE — they were never the bug"


def test_rank_order_is_bracket_then_speed_then_interaction():
    def mk(bracket, basis, turn, inter):
        return (None, {"bracket_effective": bracket,
                       "speed": {"basis": basis, "combat_turn": turn},
                       "signals": {"interaction": inter}})
    rows = [mk(3, "combat", 9, 10), mk(4, "combo-early", None, 2),
            mk(3, "combo-setup", None, 13), mk(3, "combat", 6, 10)]
    order = [r[1]["bracket_effective"] for r in sorted(rows, key=power._rank_key)]
    assert order[0] == 4, "highest bracket leads"
    ranked = sorted(rows, key=power._rank_key)
    assert ranked[1][1]["speed"]["basis"] == "combo-setup", "combo beats combat"
    assert ranked[2][1]["speed"]["combat_turn"] == 6, "faster combat beats slower"


def test_rank_key_for_handles_a_missing_assessment():
    """The webapp builds rows whose assess can be None; sorting must not raise."""
    assert power.rank_key_for(None)[0] == 1


def test_curated_lists_match_split_and_dfc_names_both_ways(tmp_path):
    """A curated row and a deck line may spell the same card differently.

    Found live 2026-08-20: `resilience_staples.csv` carried "Bofur, Reliable
    Guardian" while the deck line read "Bofur, Reliable Guardian // Concerted Care",
    so a hand-verified protection card scored ZERO. The failure is invisible — a
    curated list that misses looks exactly like a deck that lacks the card — which is
    why this matters more than the one row that exposed it: `_match` backs the Game
    Changer, tutor, fast-mana, extra-turn, mass-land-denial and combo-piece lists too,
    and a Game Changer that fails to match silently mis-brackets a deck."""
    import mtglib
    ref = tmp_path / "resilience_staples.csv"
    ref.write_text(
        "Role,Card\n"
        'protection,"Bofur, Reliable Guardian"\n'          # curated: FRONT FACE only
        'recursion,"Lake-town Mariners // Gone Fishing"\n',  # curated: FULL name
        encoding="utf-8")
    staples = power.load_resilience_staples(str(tmp_path))

    full = mtglib.Card(name="Bofur, Reliable Guardian // Concerted Care")
    front = mtglib.Card(name="Lake-town Mariners")
    assert power._match([full], staples["protection"]) == [full.name], (
        "deck line carries the full split name, curated row the front face")
    assert power._match([front], staples["recursion"]) == [front.name], (
        "and the reverse spelling must match too")

    other = mtglib.Card(name="Some Unrelated Card")
    assert power._match([other], staples["protection"]) == []
