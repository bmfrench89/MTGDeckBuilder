"""Phase A of docs/spec-optimizer-judgment.md: lands are valued by what they do for
the deck (manabase.land_mana_score), not by EDHREC inclusion, and there is no basics
quota. The regression that started it: on 2026-10-14 the optimizer proposed trading
nine of the rebuilt Ur-Dragon's duals for basics, and 8+ of Y'shtola's, because basics
sit at 76-99% inclusion and the old pass 2 filled a basics quota."""
import mtglib
import manabase


def _card(name, produced, flags=(), subtypes=()):
    return mtglib.Card(name=name, quantity=1, types=["Land"], subtypes=list(subtypes),
                       produced=set(produced) if produced is not None else None,
                       flags=set(flags), flags_ver=4)


W5 = {c: 1.0 for c in "WUBRG"}


# --------------------------------------------------------------------------- #
# the score
# --------------------------------------------------------------------------- #
def test_untapped_dual_beats_tapped_dual_beats_tapped_mono():
    untapped = manabase.land_mana_score(_card("U Dual", "RG"), W5)
    cond = manabase.land_mana_score(_card("C Dual", "RG", ["etb-tapped-cond"]), W5)
    tapped = manabase.land_mana_score(_card("T Dual", "RG", ["etb-tapped"]), W5)
    mono_t = manabase.land_mana_score(_card("T Mono", "R", ["etb-tapped"]), W5)
    basic = manabase.land_mana_score(mtglib.Card(name="Mountain", quantity=1), W5)
    assert untapped > cond > tapped > basic > mono_t
    assert basic == 1.0


def test_a_basic_scores_without_any_collection_row():
    """Basics are unlimited and often untracked: name alone is enough."""
    assert manabase.land_mana_score(mtglib.Card(name="Snow-Covered Island", quantity=1),
                                    W5) == 1.0


def test_unenriched_or_colourless_or_restricted_lands_are_not_judged():
    assert manabase.land_mana_score(_card("Mystery", None), W5) is None
    assert manabase.land_mana_score(_card("Reliquary Tower", "C"), W5) is None
    haven = _card("Haven of the Spirit Dragon", "WUBRGC", ["mana-restricted"])
    assert manabase.land_mana_score(haven, W5) is None
    off = _card("Off Colour Dual", "WU")
    assert manabase.land_mana_score(off, {"R": 1.0, "G": 1.0}) is None


def test_choose_a_colour_lands_are_capped_at_two_colours():
    """Scryfall lists every colour for Thriving Bluff / Crossroads Village."""
    thriving = manabase.land_mana_score(_card("Thriving Bluff", "WUBRG", ["etb-tapped"]), W5)
    tapped_dual = manabase.land_mana_score(_card("T Dual", "RG", ["etb-tapped"]), W5)
    assert thriving == tapped_dual


def test_filter_lands_earn_one_discounted_colour_even_in_a_two_colour_deck():
    """The filter test reads everything the land lists: in an R/W deck Henge of Ramos
    narrows to two colours and passed for an untapped dual before this was fixed."""
    henge = _card("Henge of Ramos", "WUBRGC")
    rw = {"R": 1.0, "W": 1.0}
    assert manabase.is_filter_land(henge)
    assert manabase.land_mana_score(henge, rw) < manabase.land_mana_score(_card("D", "RW"), rw)
    painland = _card("Caves of Koilos", "WBC")          # {C} + two colours: a real dual
    assert not manabase.is_filter_land(painland)


def test_reliable_adds_list_at_most_two_colours():
    assert manabase.land_is_reliable_add(_card("D", "RG"))
    assert manabase.land_is_reliable_add(_card("Painland", "WBC"))
    assert not manabase.land_is_reliable_add(_card("Rhystic Cave", "WUBRG"))
    assert not manabase.land_is_reliable_add(_card("Henge of Ramos", "WUBRGC"))


def test_fetchable_types_the_deck_wants_add_a_bonus():
    typed = _card("Typed Dual", "RG", ["etb-tapped-cond"], ["Mountain", "Forest"])
    plain = _card("Plain Dual", "RG", ["etb-tapped-cond"])
    assert (manabase.land_mana_score(typed, W5, {"forest"})
            > manabase.land_mana_score(plain, W5, {"forest"}))
    assert (manabase.land_mana_score(typed, W5, set())
            == manabase.land_mana_score(plain, W5, set()))


def test_colour_weights_follow_pip_demand_and_are_clamped():
    rows = [{"color": "R", "demand": 40}, {"color": "G", "demand": 20},
            {"color": "W", "demand": 0}]
    w = manabase.color_weights(rows, set("RGW"))
    assert w["R"] == 1.5 and w["W"] == 0.5 and 0.5 < w["G"] < 1.5
    assert manabase.color_weights([], set("RG")) == {"R": 1.0, "G": 1.0}


# --------------------------------------------------------------------------- #
# the optimizer's manabase pass
# --------------------------------------------------------------------------- #
COLL = """\
Quantity,Name,Identities,Types,Sub-types,Mana cost
1,Test Commander,W U B R G,Legendary Creature,,{W}{U}{B}{R}{G}
1,Spell R,R,Instant,,{1}{R}
1,Spell G,G,Instant,,{1}{G}
1,Spell U,U,Instant,,{1}{U}
1,Spell B,B,Instant,,{1}{B}
1,Spell W,W,Instant,,{1}{W}
1,Good Dual RG,R G,Land,
1,Good Dual UB,U B,Land,
1,Tapped Mono R,R,Land,
1,Free Untapped Dual WR,W R,Land,
1,Field Fave Land,R,Land,
1,Shared Dual GW,G W,Land,
1,Rainbow Cave,,Land,
"""

ATTRS = """\
Name,Type,MV,Colors,Cost,Sub-types,Produced,Flags,Power,FlagsVer
Good Dual RG,Land,0,,,,R G,,,4
Good Dual UB,Land,0,,,,U B,,,4
Tapped Mono R,Land,0,,,,R,etb-tapped,,4
Free Untapped Dual WR,Land,0,,,,W R,,,4
Field Fave Land,Land,0,,,,R,etb-tapped,,4
Shared Dual GW,Land,0,,,,G W,,,4
Rainbow Cave,Land,0,,,,W U B R G,,,4
"""

DECK = """\
# Title: T
# Commander: Test Commander
# Colors: W U B R G

# --- Commander ---
1 Test Commander

# --- Spells ---
1 Spell R
1 Spell G
1 Spell U
1 Spell B
1 Spell W

# --- Lands ---
1 Good Dual RG
1 Good Dual UB
{extra}
# --- Basics ---
2 Forest
1 Island
"""

OTHER_DECK = """\
# Title: O
# Commander: Test Commander
# Colors: W U B R G

# --- Commander ---
1 Test Commander

# --- Lands ---
1 Shared Dual GW
"""


def _run(tmp_path, monkeypatch, extra="", field=None, notes=None, apply=False):
    import optimize
    d = tmp_path / "lm"
    d.mkdir(exist_ok=True)
    (d / "collection.csv").write_text(COLL, encoding="utf-8")
    (d / "collection_attrs.csv").write_text(ATTRS, encoding="utf-8")
    deck = d / "deck.txt"
    if not deck.exists():
        deck.write_text(DECK.format(extra=extra), encoding="utf-8")
    (d / "other.txt").write_text(OTHER_DECK, encoding="utf-8")
    if notes is not None:
        (d / "deck.notes.md").write_text(notes, encoding="utf-8")
    coll = mtglib.load_collection(str(d / "collection.csv"))
    idx = mtglib.index_by_name(coll)
    # Basics at the real field's 76-99%, every other land at 0 — the exact shape that
    # made the old passes trade duals for basics.
    fld = {"forest": 90, "island": 85, "mountain": 92, "plains": 80, "swamp": 80,
           "spell r": 30, "spell g": 30, "spell u": 30, "spell b": 30, "spell w": 30}
    fld.update(field or {})
    monkeypatch.setattr(optimize.deck_fit, "load_field", lambda *a, **k: fld)
    monkeypatch.setattr(optimize.deck_fit, "load_field_lands", lambda *a, **k: set())
    monkeypatch.setattr(optimize.deck_fit, "load_synergy", lambda *a, **k: {})
    return optimize.optimize(str(deck), coll, idx, str(d), apply=apply), deck


def test_an_untapped_dual_is_never_traded_for_a_basic(tmp_path, monkeypatch):
    """THE regression. Basics at 90% inclusion, duals at 0%: no swap may touch them."""
    r, _deck = _run(tmp_path, monkeypatch)
    cut = {c for c, _a, _v in r["land_swaps"]}
    assert not cut & {"Good Dual RG", "Good Dual UB"}, r["land_swaps"]
    assert all(not mtglib.is_basic(a) for _c, a, _v in r["land_swaps"])


def test_a_tapped_mono_land_becomes_an_untapped_dual_and_it_is_idempotent(tmp_path,
                                                                         monkeypatch):
    r1, deck = _run(tmp_path, monkeypatch, extra="1 Tapped Mono R\n", apply=True)
    assert r1["land_swaps"] == [("Tapped Mono R", "Free Untapped Dual WR", "free")]
    assert r1["land_detail"][0]["add_score"] > r1["land_detail"][0]["cut_score"]
    r2, _ = _run(tmp_path, monkeypatch)
    assert not r2["land_swaps"], "a second run must be a no-op"


def test_the_pass_considers_owned_lands_the_field_never_lists(tmp_path, monkeypatch):
    """Field % no longer gates candidates: Free Untapped Dual WR has no field row."""
    r, _ = _run(tmp_path, monkeypatch, extra="1 Tapped Mono R\n")
    assert any(a == "Free Untapped Dual WR" for _c, a, _v in r["land_swaps"])


def test_a_land_the_field_leans_on_is_kept(tmp_path, monkeypatch):
    """Bojuka Bog-style: the score can't see an ability; >=25% field is the hint."""
    r, _ = _run(tmp_path, monkeypatch, extra="1 Field Fave Land\n",
                field={"field fave land": 40})
    assert not any(c == "Field Fave Land" for c, _a, _v in r["land_swaps"])


def test_a_land_named_in_the_notes_across_a_line_wrap_is_protected(tmp_path, monkeypatch):
    """The Canopy Vista bug: "Tapped Mono\\nR" wrapped in .notes.md was not matched by a
    raw substring test."""
    r, _ = _run(tmp_path, monkeypatch, extra="1 Tapped Mono R\n",
                notes="Keep the Tapped Mono\nR: it is here on purpose.\n")
    assert not r["land_swaps"]


def test_shared_or_unreliable_lands_are_never_brought_in(tmp_path, monkeypatch):
    """Shared Dual GW is another deck's only copy; Rainbow Cave lists five colours (the
    Rhystic Cave / Crossroads Village trap). Neither may arrive by mana score alone."""
    r, _ = _run(tmp_path, monkeypatch, extra="1 Tapped Mono R\n")
    added = {a for _c, a, _v in r["land_swaps"]}
    assert not added & {"Shared Dual GW", "Rainbow Cave"}


# --------------------------------------------------------------------------- #
# Phase B: apply only what the player ticked
# --------------------------------------------------------------------------- #
def _apply(tmp_path, monkeypatch, chosen):
    import optimize
    _run(tmp_path, monkeypatch, extra="1 Tapped Mono R\n")          # writes the fixture
    d = tmp_path / "lm"
    coll = mtglib.load_collection(str(d / "collection.csv"))
    idx = mtglib.index_by_name(coll)
    return optimize.apply_chosen(str(d / "deck.txt"), coll, idx, str(d), chosen), d


def test_apply_chosen_writes_only_the_ticked_swap(tmp_path, monkeypatch):
    import optimize
    key = optimize.proposal_key("land", "Tapped Mono R", "Free Untapped Dual WR")
    r, d = _apply(tmp_path, monkeypatch, [key])
    text = (d / "deck.txt").read_text(encoding="utf-8")
    assert "1 Free Untapped Dual WR" in text and "Tapped Mono R" not in text
    assert r["land_swaps"] == [("Tapped Mono R", "Free Untapped Dual WR", "free")]
    log = (d / "deck.changes.csv").read_text(encoding="utf-8")
    assert "Free Untapped Dual WR" in log and "Tapped Mono R" in log


def test_apply_chosen_never_writes_a_swap_it_is_not_proposing(tmp_path, monkeypatch):
    """A stale or edited form: the key is reported and nothing is written."""
    import optimize
    forged = optimize.proposal_key("land", "Good Dual RG", "Rainbow Cave")
    r, d = _apply(tmp_path, monkeypatch, [forged])
    assert r["stale"] == [forged]
    text = (d / "deck.txt").read_text(encoding="utf-8")
    assert "Good Dual RG" in text and "Rainbow Cave" not in text
    assert not (d / "deck.changes.csv").exists()


def test_proposals_flatten_a_report_with_its_evidence():
    import optimize
    r = {"swaps": [("A", 5, "B", 60, "free")],
         "swaps_detail": [{"cut": "A", "add": "B", "cut_inc": 5, "add_inc": 60,
                           "cut_field_known": True, "add_field_known": True}],
         "land_swaps": [("L1", "L2", "free")],
         "land_detail": [{"cut": "L1", "add": "L2", "cut_score": 0.25, "add_score": 2.0}]}
    ps = optimize.proposals(r)
    assert [p["key"] for p in ps] == ["spell|A|B", "land|L1|L2"]
    assert ps[0]["cut_inc"] == 5 and ps[1]["add_score"] == 2.0
