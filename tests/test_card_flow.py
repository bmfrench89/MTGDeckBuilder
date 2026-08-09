"""Hub-and-spoke card knowledge: a fact about a card must reach every section.

Two flows are pinned here, both born from a live bug report (the player's phone):

1. BUY SIGNALS. Combo Watch said "add Exquisite Blood (not owned)" while the Buy
   tab had never heard of the card — the combo engine's knowledge died inside its
   own section. `deckcore.buy_signals()` is the hub-level merge: curated buylist +
   unowned one-away combo pieces + BUY-badged decklist cards, with provenance.

2. FIELD SNAPSHOTS. The hosted server can't reach json.edhrec.com (PythonAnywhere
   free tier allowlists only documented public APIs), so the field signal silently
   vanished there. `edhrec.save_snapshot()` writes the distilled maps to
   data/reference/field/ — committed like combos.csv — and the map loaders fall
   back to it when live + cache both fail.

Hermetic: combos are monkeypatched lists, EDHREC fetches are monkeypatched, and
snapshot files live in tmp_path via a monkeypatched SNAP_DIR.
"""
import json
import os

import pytest

import deckcore
import edhrec
import mtglib


# --------------------------------------------------------------------------- #
# buy_signals — the merge
# --------------------------------------------------------------------------- #
NEAR = {"near": [
    {"name": "Exquisite Blood + Vito", "result": "Drain the whole table",
     "missing": "Exquisite Blood", "missing_owned": False, "early": False},
    {"name": "Owned-piece combo", "result": "Infinite mana",
     "missing": "Sol Ring", "missing_owned": True, "early": False},
]}


def test_unowned_combo_piece_becomes_a_buy_row():
    rows = deckcore.buy_signals(None, NEAR, [])
    cards = {r["card"]: r for r in rows}
    assert "Exquisite Blood" in cards, "the exact live bug: Combo Watch knew, Buy didn't"
    row = cards["Exquisite Blood"]
    assert row["source"] == "combo"
    assert "Drain the whole table" in row["reason"]


def test_owned_combo_piece_is_not_a_buy():
    """An owned missing piece is a sleeving decision, not a purchase."""
    rows = deckcore.buy_signals(None, NEAR, [])
    assert not any(r["card"] == "Sol Ring" for r in rows)


def test_curated_buylist_wins_the_dedupe():
    """The player's hand-written row beats the generated one — their word wins."""
    curated = [{"card": "Exquisite Blood", "price": 20.0, "tier": "Core",
                "replaces": "", "reason": "hand-written"}]
    rows = deckcore.buy_signals(curated, NEAR, [])
    hits = [r for r in rows if r["card"] == "Exquisite Blood"]
    assert len(hits) == 1 and hits[0]["source"] == "curated"
    assert hits[0]["reason"] == "hand-written"


def test_missing_decklist_cards_join_the_buy_view():
    rows = deckcore.buy_signals(None, {}, [mtglib.Card(name="Rhystic Study")])
    assert any(r["card"] == "Rhystic Study" and r["source"] == "decklist" for r in rows)


def test_dedupe_is_front_face_aware():
    near = {"near": [{"name": "c", "result": "r", "missing": "Fire // Ice",
                      "missing_owned": False, "early": False}]}
    rows = deckcore.buy_signals(None, near, [mtglib.Card(name="Fire")])
    assert len([r for r in rows if "fire" in r["card"].lower()]) == 1


def test_dashboard_buy_tab_exists_from_a_combo_signal_alone(tmp_path, collection_file, monkeypatch):
    """No .buylist.csv at all — a one-away combo must still produce the Buy tab,
    carrying the missing piece. This is the player's screenshot, as a test."""
    import combo_detector
    import build_dashboard as bd
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n\n"
                    "# --- Ramp ---\n1 Sol Ring\n\n# --- Lands ---\n10 Island\n",
                    encoding="utf-8")
    fake = [{"name": "Sol Ring + Widget", "pieces": ["sol ring", "test widget"],
             "display": ["Sol Ring", "Test Widget"], "result": "Infinite mana",
             "early": True}]
    monkeypatch.setattr(combo_detector, "load_combos", lambda *a, **k: fake)
    html = bd.generate(str(deck), collection_file, title="T",
                       commander="Test Commander")["dashboard"]
    assert "id='tab-buy'" in html, "Buy tab must exist with no curated buylist"
    assert "Test Widget" in html
    assert "from Combo Watch" in html


# --------------------------------------------------------------------------- #
# field snapshots — EDHREC data as a committed reference artifact
# --------------------------------------------------------------------------- #
@pytest.fixture
def snapdir(tmp_path, monkeypatch):
    d = tmp_path / "field"
    d.mkdir()
    monkeypatch.setattr(edhrec, "SNAP_DIR", str(d))
    return d


@pytest.fixture
def offline(monkeypatch):
    def boom(*a, **k):
        raise OSError("egress blocked")
    monkeypatch.setattr(edhrec, "_fetch", boom)


def test_maps_fall_back_to_the_committed_snapshot(snapdir, offline):
    (snapdir / "test-commander.json").write_text(json.dumps({
        "commander": "Test Commander", "slug": "test-commander", "saved": "2026-08-09",
        "inclusion": {"sol ring": 90}, "synergy": {"sol ring": 5},
        "names": {"sol ring": "Sol Ring"}}), encoding="utf-8")
    assert edhrec.inclusion_map("Test Commander") == {"sol ring": 90}
    assert edhrec.synergy_map("Test Commander") == {"sol ring": 5}
    assert edhrec.field_names("Test Commander") == {"sol ring": "Sol Ring"}


def test_maps_are_empty_when_neither_network_nor_snapshot_exists(snapdir, offline):
    assert edhrec.inclusion_map("Nobody At All") == {}


def test_the_fit_engine_sees_the_snapshot(snapdir, offline):
    """The end-to-end point of the feature: deck_fit.load_field on an offline box
    (the hosted server) gets real numbers from the committed artifact."""
    import deck_fit
    (snapdir / "test-commander.json").write_text(json.dumps({
        "slug": "test-commander", "inclusion": {"sol ring": 90},
        "synergy": {}, "names": {}}), encoding="utf-8")
    assert deck_fit.load_field("Test Commander") == {"sol ring": 90}


def test_save_snapshot_writes_the_distilled_maps(snapdir, monkeypatch):
    page = {"container": {"json_dict": {"card": {"num_decks": 1234}, "cardlists": [
        {"header": "Staples", "cardviews": [
            {"name": "Sol Ring", "num_decks": 90, "potential_decks": 100,
             "synergy": 0.05}]}]}}}
    monkeypatch.setattr(edhrec, "_fetch", lambda *a, **k: page)
    path = edhrec.save_snapshot("Test Commander")
    assert path and os.path.exists(path)
    data = json.loads(open(path, encoding="utf-8").read())
    assert data["inclusion"]["sol ring"] == 90
    assert data["synergy"]["sol ring"] == 5     # 0.05 -> ×100
    assert data["names"]["sol ring"] == "Sol Ring"
    assert data["saved"]


def test_unreachable_save_never_clobbers_a_good_snapshot(snapdir, offline):
    good = {"slug": "test-commander", "inclusion": {"sol ring": 90},
            "synergy": {}, "names": {}}
    p = snapdir / "test-commander.json"
    p.write_text(json.dumps(good), encoding="utf-8")
    assert edhrec.save_snapshot("Test Commander") is None
    assert json.loads(p.read_text(encoding="utf-8")) == good


def test_live_data_still_wins_over_the_snapshot(snapdir, monkeypatch):
    """Precedence: snapshot is the FALLBACK — a reachable fetch takes priority."""
    (snapdir / "test-commander.json").write_text(json.dumps({
        "slug": "test-commander", "inclusion": {"stale card": 50},
        "synergy": {}, "names": {}}), encoding="utf-8")
    page = {"container": {"json_dict": {"card": {}, "cardlists": [
        {"header": "Staples", "cardviews": [
            {"name": "Fresh Card", "num_decks": 80, "potential_decks": 100,
             "synergy": 0.1}]}]}}}
    monkeypatch.setattr(edhrec, "_fetch", lambda *a, **k: page)
    assert edhrec.inclusion_map("Test Commander") == {"fresh card": 80}


# --------------------------------------------------------------------------- #
# Cohesion round 2 — recommendations from snapshot, CSB one-aways, wishlist
# --------------------------------------------------------------------------- #
def test_recommendations_synthesize_from_the_snapshot(snapdir, offline, tmp_path):
    """/api/edhrec (Build Next staples) and the panel's same-slot alternatives both
    consume recommendations() — on the server they died with an error payload even
    when a snapshot existed. Now they get an honestly-labeled synthesis."""
    (snapdir / "test-commander.json").write_text(json.dumps({
        "slug": "test-commander", "saved": "2026-08-09", "sample_decks": 1234,
        "inclusion": {"sol ring": 90, "rhystic study": 60},
        "synergy": {"sol ring": 5},
        "names": {"sol ring": "Sol Ring", "rhystic study": "Rhystic Study"}}),
        encoding="utf-8")
    coll = [mtglib.Card(name="Sol Ring", quantity=1)]
    idx = mtglib.index_by_name(coll)
    rec = edhrec.recommendations("Test Commander", idx)
    assert rec.get("error") is None or "error" not in rec
    assert rec["source"] == "snapshot" and rec["saved"] == "2026-08-09"
    assert [c["name"] for c in rec["owned"]] == ["Sol Ring"]
    assert [c["name"] for c in rec["missing"]] == ["Rhystic Study"]
    assert "Snapshot (saved 2026-08-09)" in rec["sections"][0]["header"]


def test_save_snapshot_refuses_to_write_from_its_own_snapshot(snapdir, offline):
    """Freshness honesty: a snapshot-sourced rec must never re-stamp itself with
    today's date — only LIVE data writes snapshots."""
    (snapdir / "test-commander.json").write_text(json.dumps({
        "slug": "test-commander", "saved": "2026-01-01",
        "inclusion": {"sol ring": 90}, "synergy": {},
        "names": {"sol ring": "Sol Ring"}}), encoding="utf-8")
    assert edhrec.save_snapshot("Test Commander") is None
    data = json.loads((snapdir / "test-commander.json").read_text(encoding="utf-8"))
    assert data["saved"] == "2026-01-01", "the old snapshot must be untouched"


def test_spellbook_one_aways_convert_to_the_standard_near_shape(tmp_path, monkeypatch):
    import spellbook
    deck = tmp_path / "d.txt"
    deck.write_text("# --- Cards ---\n1 Vito, Thorn of the Dusk Rose\n", encoding="utf-8")
    fake = {"error": None, "present": [], "almost": [
        {"id": 1, "cards": ["Exquisite Blood", "Vito, Thorn of the Dusk Rose"],
         "produces": ["Infinite lifeloss"]},
        {"id": 2, "cards": ["Piece A", "Piece B", "Vito, Thorn of the Dusk Rose"],
         "produces": ["Two away — must be excluded"]},
    ]}
    monkeypatch.setattr(spellbook, "combos_for_deck", lambda *a, **k: fake)
    near = spellbook.near_for_deck(str(deck))
    assert len(near) == 1, "two-away combos are not one-aways"
    n = near[0]
    assert n["missing"] == "Exquisite Blood" and n["csb"] is True
    assert n["result"] == "Infinite lifeloss"


def test_dashboard_merges_csb_one_aways_into_combo_watch_and_buy(tmp_path, collection_file, monkeypatch):
    import spellbook
    import combo_detector
    import build_dashboard as bd
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n\n"
                    "# --- Ramp ---\n1 Sol Ring\n\n# --- Lands ---\n10 Island\n",
                    encoding="utf-8")
    monkeypatch.setattr(combo_detector, "load_combos", lambda *a, **k: [])
    monkeypatch.setattr(spellbook, "near_for_deck", lambda *a, **k: [
        {"name": "Sol Ring + CSB Widget", "result": "Infinite mana",
         "missing": "CSB Widget", "missing_owned": False, "early": False, "csb": True}])
    html = bd.generate(str(deck), collection_file, title="T",
                       commander="Test Commander")["dashboard"]
    assert "CSB Widget" in html
    assert "One piece away" in html, "CSB nears render in Combo Watch"
    assert "id='tab-buy'" in html, "and produce a Buy tab"


def test_dashboard_dedupes_csb_against_combos_csv(tmp_path, collection_file, monkeypatch):
    """The same combo known to both sources must render once, not twice."""
    import spellbook
    import combo_detector
    import build_dashboard as bd
    import re as _re
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n\n"
                    "# --- Ramp ---\n1 Sol Ring\n\n# --- Lands ---\n10 Island\n",
                    encoding="utf-8")
    csvside = [{"name": "Sol Ring + CSB Widget", "pieces": ["sol ring", "csb widget"],
                "display": ["Sol Ring", "CSB Widget"], "result": "Infinite mana",
                "early": False}]
    monkeypatch.setattr(combo_detector, "load_combos", lambda *a, **k: csvside)
    monkeypatch.setattr(spellbook, "near_for_deck", lambda *a, **k: [
        {"name": "Sol Ring + CSB Widget", "result": "Infinite mana",
         "missing": "CSB Widget", "missing_owned": False, "early": False, "csb": True}])
    html = bd.generate(str(deck), collection_file, title="T",
                       commander="Test Commander")["dashboard"]
    m = _re.search(r"One piece away <span class='count'>(\d+)</span>", html)
    assert m and m.group(1) == "1", f"expected 1 near combo, got {m.group(1) if m else 'none'}"


def test_wishlist_includes_unowned_combo_pieces(tmp_path, collection_file, monkeypatch):
    import combo_detector
    import wishlist as wl
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "t.txt").write_text("# Title: T\n# Commander: Test Commander\n"
                                 "# Colors: W U\n\n# --- Ramp ---\n1 Sol Ring\n",
                                 encoding="utf-8")
    fake = [{"name": "Sol Ring + Widget", "pieces": ["sol ring", "wish widget"],
             "display": ["Sol Ring", "Wish Widget"], "result": "Infinite mana",
             "early": False}]
    monkeypatch.setattr(combo_detector, "load_combos", lambda *a, **k: fake)
    _shared, _unowned, upgrades = wl.build(collection_file, str(decks))
    hits = [u for u in upgrades if u["card"] == "Wish Widget"]
    assert hits and "Completes a combo" in hits[0]["reason"]
    assert hits[0]["deck"] == "t"


def test_wishlist_curated_buylist_still_wins(tmp_path, collection_file, monkeypatch):
    import combo_detector
    import wishlist as wl
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "t.txt").write_text("# Title: T\n# Colors: W U\n\n# --- Ramp ---\n1 Sol Ring\n",
                                 encoding="utf-8")
    (decks / "t.buylist.csv").write_text(
        "Card,Price,Tier,Replaces,Reason\nWish Widget,5,Core,,hand-written\n",
        encoding="utf-8")
    fake = [{"name": "c", "pieces": ["sol ring", "wish widget"],
             "display": ["Sol Ring", "Wish Widget"], "result": "r", "early": False}]
    monkeypatch.setattr(combo_detector, "load_combos", lambda *a, **k: fake)
    _s, _u, upgrades = wl.build(collection_file, str(decks))
    hits = [u for u in upgrades if u["card"] == "Wish Widget"]
    assert len(hits) == 1 and hits[0]["reason"] == "hand-written"
