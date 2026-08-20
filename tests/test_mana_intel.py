"""Phase B of spec-mana-intelligence: the fetch-target census and the
restricted-source split — the engine answers to "why is Wood Elves in a deck
with only 2 Forests?" (it had five; nothing could say so).

Everything here is hand-built Cards or tmp_path attrs files, hermetic. The
properties that matter:

  * a fetcher's targets are resolved by what its tokens can FIND — typed duals
    satisfy `fetch:forest`, only basics satisfy `fetch:basic-forest`, and a
    union across tokens never counts one land twice;
  * restricted lands leave the Karsten pool and land in their own bucket, and a
    pre-vocabulary land is UNKNOWN — counted as before, labeled, never
    silently promoted to "verified unrestricted";
  * the census refuses to render a confident zero on pre-vocabulary data.
"""
import json

import mtglib
import manabase
import deck_stats

C = mtglib.Card


def _land(name, subtypes=(), qty=1, flags=frozenset(), ver=2, produced=None):
    return C(name=name, types=["Land"], subtypes=list(subtypes), quantity=qty,
             flags=set(flags), flags_ver=ver, produced=produced)


URDRAGON_MINI = [
    C(name="Wood Elves", types=["Creature"], flags={"ramp", "fetch:forest"},
      flags_ver=2, mana_cost="{2}{G}", mana_value=3.0),
    C(name="Farseek", types=["Sorcery"], flags_ver=2, mana_cost="{1}{G}",
      mana_value=2.0,
      flags={"ramp", "fetch:plains", "fetch:island", "fetch:swamp",
             "fetch:mountain"}),
    C(name="Nissa's Pilgrimage", types=["Sorcery"], mana_cost="{2}{G}",
      mana_value=3.0, flags={"ramp", "fetch:basic-forest"}, flags_ver=2),
    _land("Forest", ["Forest"], qty=2, produced={"G"}),
    _land("Sheltered Thicket", ["Mountain", "Forest"], produced={"G", "R"}),
    _land("Scattered Groves", ["Forest", "Plains"], produced={"G", "W"}),
    _land("Mountain", ["Mountain"], qty=4, produced={"R"}),
    _land("Command Tower", produced=set("WUBRG")),
]


def _rows(census):
    return {r["name"]: r for r in census["rows"]}


def test_a_typed_fetcher_counts_typed_duals():
    """The original question, answered by the engine: 2 basics + 2 typed duals
    = 4 Forest cards Wood Elves can actually find here."""
    rows = _rows(manabase.fetch_census(URDRAGON_MINI))
    we = rows["Wood Elves"]
    assert we["targets"] == 4
    assert set(we["target_names"]) == {"Forest", "Sheltered Thicket",
                                       "Scattered Groves"}
    assert we["state"] == "ok"


def test_union_across_tokens_counts_each_land_once():
    """Farseek's four tokens both hit Sheltered Thicket (Mountain) — via
    different letters on Scattered Groves (Plains) — and the union must count
    each land once: 2 duals + 4 Mountains = 6."""
    rows = _rows(manabase.fetch_census(URDRAGON_MINI))
    assert rows["Farseek"]["targets"] == 6


def test_basic_qualified_fetch_excludes_typed_duals():
    """Nissa's Pilgrimage wants BASIC Forests: the two basics qualify, the two
    Forest-typed duals do not — and 2 is under FETCH_THIN, so it reads thin."""
    rows = _rows(manabase.fetch_census(URDRAGON_MINI))
    np_ = rows["Nissa's Pilgrimage"]
    assert np_["targets"] == 2
    assert np_["state"] == "thin"


def test_a_stranded_fetcher_reads_none():
    deck = [C(name="Wood Elves", types=["Creature"],
              flags={"ramp", "fetch:forest"}, flags_ver=2),
            _land("Island", ["Island"], qty=10)]
    rows = _rows(manabase.fetch_census(deck))
    assert rows["Wood Elves"]["state"] == "none"
    assert rows["Wood Elves"]["targets"] == 0


def test_a_fetchland_is_not_its_own_target():
    deck = [_land("Evolving Wilds", flags={"ramp", "fetch:basic"}),
            _land("Forest", ["Forest"], qty=1)]
    rows = _rows(manabase.fetch_census(deck))
    assert rows["Evolving Wilds"]["targets"] == 1, "only the Forest, not itself"


def test_quantities_count_copies_not_rows():
    deck = [C(name="Rampant Growth", types=["Sorcery"], quantity=2,
              flags={"ramp", "fetch:basic"}, flags_ver=2),
            _land("Forest", ["Forest"], qty=5)]
    census = manabase.fetch_census(deck)
    assert census["total_fetchers"] == 2, "sum of quantities, not row count"
    assert _rows(census)["Rampant Growth"]["targets"] == 5


def test_pre_vocabulary_is_refused_not_zeroed():
    """The honesty gate. A deck whose enrichment predates v2 has INVISIBLE
    fetchers, not absent ones — a confident zero here would be a lie."""
    deck = [C(name="Wood Elves", types=["Creature"], flags={"ramp"}, flags_ver=1),
            _land("Forest", ["Forest"], qty=5, ver=1)]
    census = manabase.fetch_census(deck)
    assert census["unknown"] == "pre-vocabulary"
    assert census["rows"] == []


def test_no_subtype_data_is_flagged_via_has_type_data_not_empty_subtypes():
    """The proxy the completeness review forced: Unclaimed Territory is fully
    enriched with NO basic land types — empty subtypes on a typed land is a
    real answer, not missing data. Only a land with no type data at all
    (has_type_data False) triggers the caveat."""
    healthy = [C(name="Wood Elves", types=["Creature"],
                 flags={"ramp", "fetch:forest"}, flags_ver=2),
               _land("Forest", ["Forest"]),
               _land("Unclaimed Territory")]        # typed Land, no subtypes
    assert manabase.fetch_census(healthy)["unknown"] is None

    nameonly = [C(name="Wood Elves", types=["Creature"],
                  flags={"ramp", "fetch:forest"}, flags_ver=2),
                _land("Forest", ["Forest"]),
                # No type data at all: is_land resolves via the name-hint
                # heuristic ("grove" is on the hints list), which is exactly the
                # untyped-land situation the caveat exists for.
                C(name="Vivid Grove", types=[], flags_ver=2)]
    assert manabase.fetch_census(nameonly)["unknown"] == "no-subtype-data"


def test_census_is_json_safe():
    json.dumps(manabase.fetch_census(URDRAGON_MINI))


# --------------------------------------------------------------------------- #
# The restricted split (deck_stats.build_report)
# --------------------------------------------------------------------------- #
def _report(cards):
    idx = mtglib.index_by_name(cards)
    deck = [C(name=c.name, quantity=c.quantity) for c in cards]
    enriched, missing = deck_stats.analyze(deck, idx)
    return deck_stats.build_report(deck, enriched, missing, idx)


def test_a_verified_restricted_land_moves_buckets():
    cards = [_land("Unclaimed Territory", produced=set("WUBRGC"),
                   flags={"mana-restricted"}, ver=2),
             _land("Forest", ["Forest"], produced={"G"}, qty=3)]
    rep = _report(cards)
    assert rep["color_sources"] == {"G": 3}, \
        "the restricted land must not inflate the main pool"
    assert rep["color_sources_restricted"] == {c: 1 for c in "WUBRG"}
    assert rep["color_sources_basis"]["restricted_lands"] == 1
    assert rep["color_sources_basis"]["restriction_unknown_lands"] == 0


def test_a_pre_vocabulary_land_counts_as_today_and_is_labeled_unknown():
    """Unknown is not restricted and not verified-clean. The same land with v1
    flags counts exactly as before the split existed — and the basis says the
    split is incomplete."""
    cards = [_land("Unclaimed Territory", produced=set("WUBRGC"),
                   flags=set(), ver=1),
             _land("Forest", ["Forest"], produced={"G"}, qty=3, ver=1)]
    rep = _report(cards)
    assert rep["color_sources"]["W"] == 1, "counted as unrestricted, as before"
    assert rep["color_sources_restricted"] == {}
    assert rep["color_sources_basis"]["restriction_unknown_lands"] == 4


def test_karsten_status_flips_when_restriction_is_subtracted():
    """The acceptance-shaped case: enough rainbow-restricted lands to clear the
    Karsten count only WITH the overcount. Subtracting them flips ok -> low."""
    restricted = [_land(f"Tribal Land {i}", produced=set("WUBRG"),
                        flags={"mana-restricted"}, ver=2) for i in range(10)]
    real = [_land("Plains", ["Plains"], produced={"W"}, qty=15)]
    spells = [C(name="Angel", types=["Creature"], mana_cost="{1}{W}",
                mana_value=2.0, quantity=4, flags_ver=2)]
    rep_v2 = _report(restricted + real + spells)
    a_v2 = manabase.analyze(rep_v2, restricted + real + spells)
    w_row = next(r for r in a_v2["colors"] if r["color"] == "W")
    assert w_row["sources"] == 15 and w_row["restricted"] == 10
    assert w_row["status"] == "low", "15 < Karsten 19 once the overcount is gone"

    legacy = [_land(f"Tribal Land {i}", produced=set("WUBRG"), ver=1)
              for i in range(10)] + real + spells
    a_v1 = manabase.analyze(_report(legacy), legacy)
    w_old = next(r for r in a_v1["colors"] if r["color"] == "W")
    assert w_old["sources"] == 25 and w_old["status"] == "ok", \
        "pre-vocabulary data keeps today's (overcounted) numbers — labeled, not fixed"


def test_analyze_ships_census_and_restricted_and_serializes():
    rep = _report(URDRAGON_MINI)
    a = manabase.analyze(rep, URDRAGON_MINI)
    assert "fetch" in a and a["fetch"]["total_fetchers"] == 3
    assert all("restricted" in row for row in a["colors"])
    assert "restricted" in a["explain"] and "fetch" in a["explain"]
    json.dumps(a)


# --------------------------------------------------------------------------- #
# Phase C — the census renders on every surface mana already renders on
# --------------------------------------------------------------------------- #
ATTRS_V2_SURFACE = """\
Name,Type,MV,Colors,Cost,Sub-types,Produced,Flags,Power,FlagsVer
Sol Ring,Artifact,1,,{1},,C,mana2;ramp;rock,,2
Island,Land,0,U,,Island,U,,,2
Counterspell,Instant,2,U,{U}{U},,,counter,,2
Serra Angel,Creature,5,W,{3}{W}{W},Angel,,fetch:forest;ramp,4,2
"""

SURFACE_DECK = """\
# Title: T
# Commander: Test Commander
# Colors: W U

# --- Commander ---
1 Test Commander

# --- Main ---
1 Serra Angel
1 Sol Ring
1 Counterspell

# --- Lands ---
10 Island
"""


def _surface_files(tmp_path):
    import shutil, os
    from conftest import COLLECTION_CSV
    d = tmp_path / "sf"
    d.mkdir(exist_ok=True)
    (d / "collection.csv").write_text(COLLECTION_CSV, encoding="utf-8")
    (d / "collection_attrs.csv").write_text(ATTRS_V2_SURFACE, encoding="utf-8")
    (d / "deck.txt").write_text(SURFACE_DECK, encoding="utf-8")
    return str(d / "deck.txt"), str(d / "collection.csv")


def test_dashboard_mana_tab_carries_census_and_panel_note(tmp_path):
    """One renderer serves the app deck page and the CLI dashboard, so this test
    covers both. Serra Angel is a pretend Forest-fetcher in a Forestless deck:
    the census must call it out, and the panel payload must carry the note on
    the card itself."""
    import build_dashboard as bd
    deck, coll = _surface_files(tmp_path)
    h = bd.generate(deck, coll, title="T", commander="Test Commander",
                    sim=None)["dashboard"]
    assert "Fetch census" in h
    assert "no targets" in h
    assert "mcfetch" in h, "the panel's census element must exist in the markup"
    import re
    assert re.search(r'"fetch":\s*{"targets":\s*0', h.replace("'", '"')) or \
        '"fetch": {"targets": 0, "state": "none"}' in h


def test_pre_vocabulary_dashboard_refuses_instead_of_zeroing(tmp_path):
    import build_dashboard as bd
    deck, coll = _surface_files(tmp_path)
    import os
    attrs = os.path.join(os.path.dirname(coll), "collection_attrs.csv")
    open(attrs, "w", encoding="utf-8").write(
        ATTRS_V2_SURFACE.replace(",FlagsVer", "").replace(",,2\n", ",,\n")
        .replace(",4,2\n", ",4,\n"))
    h = bd.generate(deck, coll, title="T", commander="Test Commander",
                    sim=None)["dashboard"]
    assert "enrichment predates the fetch vocabulary" in h
    assert "no targets" not in h, "a confident zero on pre-vocabulary data is a lie"


def test_assess_page_and_packet_carry_the_census(tmp_path, monkeypatch):
    import sys
    sys.modules.pop("app", None)
    deck, coll = _surface_files(tmp_path)
    import shutil, os
    decks = tmp_path / "decks"
    decks.mkdir(exist_ok=True)
    shutil.copy(deck, decks / "deck.txt")
    import app as appmod
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", coll)
    monkeypatch.setattr(appmod, "PASSWORD", None)
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()

    page = client.get("/deck/deck/assess").get_data(as_text=True)
    assert "Fetch census" in page
    assert "no targets" in page

    packet = client.get("/deck/deck/assess.txt?raw=1").get_data(as_text=True)
    assert "FETCH CENSUS" in packet
    assert "Serra Angel: 0 target(s) <-- NO TARGETS" in packet


# --------------------------------------------------------------------------- #
# Phase D — the standing Mana-health advisory
# --------------------------------------------------------------------------- #
def test_banner_fires_for_a_stranded_fetcher_and_not_for_a_healthy_deck(tmp_path):
    import build_dashboard as bd
    deck, coll = _surface_files(tmp_path)
    h = bd.generate(deck, coll, title="T", commander="Test Commander",
                    sim=None)["dashboard"]
    assert "Mana health" in h and "Serra Angel has 0 fetch targets" in h
    assert "⚠ Mana" in h, "the tab label carries the text-only chip"

    # Same deck, fetcher healthy: give it Forests to find.
    import os
    attrs = os.path.join(os.path.dirname(coll), "collection_attrs.csv")
    with open(attrs, "a", encoding="utf-8") as f:
        f.write("Forest,Land,0,G,,Forest,G,,,2\n")
    with open(deck, "a", encoding="utf-8") as f:
        f.write("3 Forest\n")
    h2 = bd.generate(deck, coll, title="T", commander="Test Commander",
                     sim=None)["dashboard"]
    # The fetcher finding is gone. The banner itself may legitimately remain:
    # this 13-land toy deck is under the 36-land floor, and saying so is the
    # OTHER thing the advisory is for.
    assert "Serra Angel has 0 fetch targets" not in h2
    assert "lands (template floor" in h2


def test_a_manual_edit_reevaluates_the_banner_on_the_next_render(tmp_path,
                                                                 monkeypatch):
    """The player's actual question — "how would this work when I sub out cards
    manually?" Answered: the banner is computed at render time from the memoized
    analysis, so the panel's own reload shows the new state. No optimizer, no
    stored state, no flash that lands on a page that can't show it."""
    import sys, shutil
    sys.modules.pop("app", None)
    deck, coll = _surface_files(tmp_path)
    import os
    attrs = os.path.join(os.path.dirname(coll), "collection_attrs.csv")
    with open(attrs, "a", encoding="utf-8") as f:
        f.write("Forest,Land,0,G,,Forest,G,,,2\n")
    decks = tmp_path / "decks"
    decks.mkdir(exist_ok=True)
    with open(deck, encoding="utf-8") as f:
        text = f.read()
    (decks / "deck.txt").write_text(text + "3 Forest\n", encoding="utf-8")

    import app as appmod
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", coll)
    monkeypatch.setattr(appmod, "PASSWORD", None)
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()

    before = client.get("/deck/deck").get_data(as_text=True)
    assert "0 fetch targets" not in before, "healthy while the Forests are in"

    # The player cuts their Forests by hand through the deck editor.
    client.post("/deck/deck/edit", data={"content": text})
    after = client.get("/deck/deck").get_data(as_text=True)
    assert "Serra Angel has 0 fetch targets" in after, \
        "the very next page load re-evaluates — no optimizer involved"


def test_add_route_carries_the_mana_note(tmp_path, monkeypatch):
    import sys, shutil, json as _json
    sys.modules.pop("app", None)
    deck, coll = _surface_files(tmp_path)
    decks = tmp_path / "decks"
    decks.mkdir(exist_ok=True)
    shutil.copy(deck, decks / "deck.txt")
    import app as appmod
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", coll)
    monkeypatch.setattr(appmod, "PASSWORD", None)
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()
    # Serra Angel is already in the deck — advise on it via the read-only twin.
    r = _json.loads(client.get("/api/deck/deck/advise?name=Serra+Angel")
                    .get_data(as_text=True))
    v = r.get("verdict") or r
    assert "0 legal target(s)" in (v.get("mana_note") or ""), v


# --------------------------------------------------------------------------- #
# Phase E — the optimizer may not strand a fetcher (running ledger, both passes)
# --------------------------------------------------------------------------- #
GUARD_COLL = """\
Quantity,Name,Identities,Types,Sub-types
1,Test Commander,W B,Legendary Creature,
1,Farseek Analog,W B,Sorcery,
1,Weak Swamp Dual A,W B,Land,Swamp
1,Weak Swamp Dual B,W B,Land,Swamp
1,Hot Land One,W B,Land,
1,Hot Land Two,W B,Land,
1,Filler,W B,Instant,
"""

GUARD_ATTRS = """\
Name,Type,MV,Colors,Cost,Sub-types,Produced,Flags,Power,FlagsVer
Farseek Analog,Sorcery,2,B,{1}{B},,,fetch:swamp;ramp,,2
Weak Swamp Dual A,Land,0,,,Swamp,W B,,,2
Weak Swamp Dual B,Land,0,,,Swamp,W B,,,2
Hot Land One,Land,0,,,,W B,,,2
Hot Land Two,Land,0,,,,W B,,,2
"""

GUARD_DECK = """\
# Title: G
# Commander: Test Commander
# Colors: W B

# --- Commander ---
1 Test Commander

# --- Spells ---
1 Farseek Analog
1 Filler

# --- Lands ---
1 Weak Swamp Dual A
1 Weak Swamp Dual B
"""


def _guard_run(tmp_path, monkeypatch, deck_text=GUARD_DECK, margin=25):
    import optimize, deck_fit
    d = tmp_path / "g"
    d.mkdir(exist_ok=True)
    (d / "collection.csv").write_text(GUARD_COLL, encoding="utf-8")
    (d / "collection_attrs.csv").write_text(GUARD_ATTRS, encoding="utf-8")
    deck = d / "deck.txt"
    deck.write_text(deck_text, encoding="utf-8")
    coll = mtglib.load_collection(str(d / "collection.csv"))
    idx = mtglib.index_by_name(coll)
    # Both Swamp duals are field-zeros; both Hot Lands clear the margin over
    # them. Without the ledger, pass 1 takes dual A and pass 2 (or a second
    # pass-1 add) takes dual B — each individually "leaving one".
    field = {"weak swamp dual a": 0, "weak swamp dual b": 0,
             "hot land one": 60, "hot land two": 60, "farseek analog": 50,
             "filler": 10}
    monkeypatch.setattr(optimize.deck_fit, "load_field", lambda *a, **k: field)
    monkeypatch.setattr(optimize.deck_fit, "load_field_lands",
                        lambda *a, **k: {"hot land one", "hot land two"})
    monkeypatch.setattr(optimize.deck_fit, "load_synergy", lambda *a, **k: {})
    return optimize.optimize(str(deck), coll, idx, str(d), margin=margin)


def test_the_ledger_spans_passes_one_swap_allowed_one_refused(tmp_path, monkeypatch):
    """THE two-Swamp case. Cutting one Swamp-typed dual is fine (one remains);
    cutting the second would strand Farseek Analog. A per-swap check against the
    ORIGINAL deck would allow both — each individually 'leaves one'."""
    r = _guard_run(tmp_path, monkeypatch)
    cut_names = [c for c, _a, _v in r["land_swaps"]]
    swamps_cut = [c for c in cut_names if "Swamp Dual" in c]
    assert len(swamps_cut) == 1, (
        f"exactly one Swamp dual may go; got {swamps_cut} — the ledger must "
        "carry pass 1's cut into the next check")
    assert r["land_guard"], "the refusal must be REPORTED, not silent"
    g = r["land_guard"][0]
    assert g["type"] == "swamp" and "Farseek Analog" in g["for"]


def test_the_guard_is_inert_without_v2_fetch_data(tmp_path, monkeypatch):
    """Pre-vocabulary flags carry no trustable demand: both duals may be cut,
    exactly as before the guard existed."""
    global GUARD_ATTRS
    old = GUARD_ATTRS
    try:
        GUARD_ATTRS = old.replace(",FlagsVer", "").replace(",,2\n", ",,\n") \
                         .replace("fetch:swamp;ramp,,2", "ramp,,")
        r = _guard_run(tmp_path, monkeypatch)
        assert not r["land_guard"]
    finally:
        GUARD_ATTRS = old


def test_buy_pairing_obeys_the_same_guard(tmp_path, monkeypatch):
    """Advice the tool would not take itself is worse than none: a Replaces
    target the land passes refused to cut may not be recommended for pulling.

    Built so ONLY the buy-pairing's own guard stands in the way (a first draft
    passed with the guard deleted, because pass 1's refusal had already parked
    the land in used_land): no owned land upgrades exist, and enough off-type
    basics that basics repair never runs — the buy pairing is the first and
    only pass to reach the deck's lone Swamp-typed land."""
    import optimize
    d = tmp_path / "bg"
    d.mkdir(exist_ok=True)
    (d / "collection.csv").write_text(
        "Quantity,Name,Identities,Types,Sub-types\n"
        "1,Test Commander,W B,Legendary Creature,\n"
        "1,Farseek Analog,W B,Sorcery,\n"
        "1,Lone Swamp Dual,W B,Land,Swamp\n"
        "4,Plains,W,Land,Plains\n"
        "1,Filler,W B,Instant,\n", encoding="utf-8")
    (d / "collection_attrs.csv").write_text(
        "Name,Type,MV,Colors,Cost,Sub-types,Produced,Flags,Power,FlagsVer\n"
        "Farseek Analog,Sorcery,2,B,{1}{B},,,fetch:swamp;ramp,,2\n"
        "Lone Swamp Dual,Land,0,,,Swamp,W B,,,2\n", encoding="utf-8")
    deck = d / "deck.txt"
    deck.write_text(
        "# Title: BG\n# Commander: Test Commander\n# Colors: W B\n\n"
        "# --- Commander ---\n1 Test Commander\n\n"
        "# --- Spells ---\n1 Farseek Analog\n1 Filler\n\n"
        "# --- Lands ---\n1 Lone Swamp Dual\n4 Plains\n", encoding="utf-8")
    coll = mtglib.load_collection(str(d / "collection.csv"))
    idx = mtglib.index_by_name(coll)
    field = {"lone swamp dual": 0, "unowned hot land": 60,
             "farseek analog": 50, "filler": 10}
    monkeypatch.setattr(optimize.deck_fit, "load_field", lambda *a, **k: field)
    monkeypatch.setattr(optimize.deck_fit, "load_field_lands",
                        lambda *a, **k: {"unowned hot land"})
    monkeypatch.setattr(optimize.deck_fit, "load_synergy", lambda *a, **k: {})
    r = optimize.optimize(str(deck), coll, idx, str(d))
    land_buys = [b for b in r["buy_swaps"] if b[4] == "land"]
    assert not any(b[0] == "Lone Swamp Dual" for b in land_buys), (
        "the buylist named the deck's only Swamp-typed land as the Replaces "
        "target while a fetch:swamp card is in the 99 — advice must obey the "
        "same guard the write passes obey")


def test_the_repair_is_idempotent_with_the_guard(tmp_path, monkeypatch):
    """Apply once, run again: the second run proposes nothing. The stated
    optimizer invariant, preserved through the ledger and the pip-proportional
    chooser (both deterministic)."""
    import optimize, deck_fit
    d = tmp_path / "g"
    d.mkdir(exist_ok=True)
    (d / "collection.csv").write_text(GUARD_COLL, encoding="utf-8")
    (d / "collection_attrs.csv").write_text(GUARD_ATTRS, encoding="utf-8")
    deck = d / "deck.txt"
    deck.write_text(GUARD_DECK, encoding="utf-8")
    coll = mtglib.load_collection(str(d / "collection.csv"))
    idx = mtglib.index_by_name(coll)
    field = {"weak swamp dual a": 0, "weak swamp dual b": 0,
             "hot land one": 60, "hot land two": 60, "farseek analog": 50,
             "filler": 10}
    monkeypatch.setattr(optimize.deck_fit, "load_field", lambda *a, **k: field)
    monkeypatch.setattr(optimize.deck_fit, "load_field_lands",
                        lambda *a, **k: {"hot land one", "hot land two"})
    monkeypatch.setattr(optimize.deck_fit, "load_synergy", lambda *a, **k: {})
    r1 = optimize.optimize(str(deck), coll, idx, str(d), apply=True)
    assert r1["land_swaps"], "precondition: the first run does something"
    r2 = optimize.optimize(str(deck), coll, idx, str(d))
    assert not r2["swaps"] and not r2["land_swaps"], \
        "the second run must be a no-op — idempotency is a stated invariant"


# --------------------------------------------------------------------------- #
# Phase F — auto_build prefers lands its fetchers can find, as a TIEBREAK
# --------------------------------------------------------------------------- #
def _build_pool(tmp_path, with_fetcher):
    """A WU pool where a Forest-typed dual and a plain tapland tie on score; a
    Farseek-class candidate (when present) demands typed lands."""
    import auto_build
    rows = ["Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,MARKET",
            "1,Test Commander,4,W U,W U,{2}{W}{U},Legendary Creature,Human Wizard,rare,cmd00000,1.00"]
    for i in range(40):
        rows.append(f"1,Test Spell {i},{i % 6},U,U,{{{i % 6}}}{{U}},Instant,,common,sp{i:06d},0.10")
    for i in range(40):
        rows.append(f"1,Test Bear {i},{(i % 5) + 1},W,W,{{{i % 5}}}{{W}},Creature,Bear,common,cr{i:06d},0.10")
    for i in range(28):
        rows.append(f"1,Test Land {i},0,,,,Land,,common,ld{i:06d},0.10")
    rows.append("1,Typed Haven,0,,,,Land,Plains,common,th000001,0.10")
    if with_fetcher:
        rows.append("1,Pathfinder,2,W,W,{1}{W},Creature,Scout,common,pf000001,0.10")
    rows.append("40,Island,0,,,,Land,Island,common,isl00000,0.10")
    rows.append("40,Plains,0,,,,Land,Plains,common,pln00000,0.10")
    d = tmp_path / ("bf" if with_fetcher else "bn")
    d.mkdir(exist_ok=True)
    (d / "collection.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    if with_fetcher:
        (d / "collection_attrs.csv").write_text(
            "Name,Type,MV,Colors,Cost,Sub-types,Produced,Flags,Power,FlagsVer\n"
            "Pathfinder,Creature,2,W,{1}{W},Scout,,fetch:plains;ramp,1,2\n"
            "Typed Haven,Land,0,,,Plains,W,,,2\n", encoding="utf-8")
    coll = mtglib.load_collection(str(d / "collection.csv"))
    idx = mtglib.index_by_name(coll)
    return auto_build.build("Test Commander", coll, idx, None, identity="WU")


def _names_and_total(d):
    names, total = set(), 0
    for _label, cards in d["sections"]:
        for c in cards:
            names.add(c["name"])
            total += c["qty"]
    return names, total


def test_typed_dual_wins_the_tie_when_a_fetcher_demands_it(tmp_path):
    d = _build_pool(tmp_path, with_fetcher=True)
    names, total = _names_and_total(d)
    assert "Typed Haven" in names, \
        "with a fetch:plains card in the pool, the Plains-typed land wins its tie"
    assert d["total"] == 100, "the re-rank must never change how many cards are taken"


def test_no_fetcher_means_no_reorder(tmp_path):
    """Without demand the sort key never fires — pool order stands, and the
    build stays exactly 100 legal cards either way."""
    d = _build_pool(tmp_path, with_fetcher=False)
    assert d["total"] == 100


# --------------------------------------------------------------------------- #
# Phase G — the sim admits fetch effects are unmodeled (schema 3)
# --------------------------------------------------------------------------- #
def test_goldfish_admits_fetch_effects_are_unmodeled():
    """Enriched fetchlands are dead lands in the sim, and enrichment makes Wood
    Elves WORSE (a working identity-tier dork becomes a zero-mana body). The
    honesty framework fires on absent data; this was known-WRONG data with no
    label — the assumptions line closes that blind spot."""
    import goldfish
    cards = [
        C(name="Wood Elves", quantity=1, mana_value=3.0, mana_cost="{2}{G}",
          types=["Creature"], produced=set(),
          flags={"ramp", "fetch:forest"}, flags_ver=2, power=1),
        C(name="Evolving Wilds", quantity=1, mana_value=0.0, types=["Land"],
          produced=set(), flags={"ramp", "fetch:basic"}, flags_ver=2),
        C(name="Forest", quantity=35, mana_value=0.0, types=["Land"],
          produced={"G"}),
    ]
    rep = goldfish.simulate(goldfish.compile_deck(cards), games=40, seed=1)
    line = next((a for a in rep["assumptions"] if "Fetch effects" in a), "")
    assert "Evolving Wilds" in line and "Wood Elves" in line

    clean = [C(name="Forest", quantity=37, mana_value=0.0, types=["Land"],
               produced={"G"}),
             C(name="Bear", quantity=1, mana_value=2.0, mana_cost="{1}{G}",
               types=["Creature"], produced=set(), power=2)]
    rep2 = goldfish.simulate(goldfish.compile_deck(clean), games=40, seed=1)
    assert not any("Fetch effects" in a for a in rep2["assumptions"]), \
        "no fetchers, no label — the line must not become boilerplate"


def test_schema_bump_ships_with_the_assumptions_change():
    """Assumptions text is part of the cached report; without the bump, cached
    decks keep the old list until an unrelated mtime change. Pin the current
    value: any change to what a report says must arrive with a bump."""
    import goldfish
    assert goldfish.REPORT_SCHEMA == 4


def test_ab_arm_b_adjusts_the_fetch_flagged_list():
    """simulate_ab's arm B copies the compiled dict — the data-only key must
    track the swap, or arm B's assumptions describe arm A's deck."""
    import goldfish
    cards = [
        C(name="Wood Elves", quantity=1, mana_value=3.0, mana_cost="{2}{G}",
          types=["Creature"], produced=set(),
          flags={"ramp", "fetch:forest"}, flags_ver=2, power=1),
        C(name="Forest", quantity=36, mana_value=0.0, types=["Land"],
          produced={"G"}),
    ]
    coll = cards + [C(name="Vanilla Bear", quantity=1, mana_value=3.0,
                      mana_cost="{2}{G}", types=["Creature"], produced=set(),
                      power=2, flags_ver=2)]
    idx = mtglib.index_by_name(coll)
    comp = goldfish.compile_deck(cards)
    ab = goldfish.simulate_ab(comp, "Wood Elves", "Vanilla Bear", idx,
                              games=40, seed=2)
    assert "error" not in ab
    assert any("Fetch effects" in a for a in ab["a"]["assumptions"])
    assert not any("Fetch effects" in a for a in ab["b"]["assumptions"]), \
        "arm B swapped the only fetcher out — its label must go with it"
