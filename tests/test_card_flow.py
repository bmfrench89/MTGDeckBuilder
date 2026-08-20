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


def test_snapshot_records_edhrec_lands_sections(snapdir, monkeypatch):
    """EDHREC's page files cards under typed sections; the Lands ones are the only
    type signal available for a card the collection can't type (unowned buys,
    name-only snapshots). _distill must keep them, live land_names must see them."""
    page = {"container": {"json_dict": {"card": {}, "cardlists": [
        {"header": "Lands", "cardviews": [
            {"name": "Hallowed Fountain", "num_decks": 55, "potential_decks": 100,
             "synergy": 0.0}]},
        {"header": "Instants", "cardviews": [
            {"name": "Counterspell", "num_decks": 60, "potential_decks": 100,
             "synergy": 0.1}]}]}}}
    monkeypatch.setattr(edhrec, "_fetch", lambda *a, **k: page)
    assert edhrec.land_names("Test Commander") == {"hallowed fountain"}
    path = edhrec.save_snapshot("Test Commander")
    data = json.loads(open(path, encoding="utf-8").read())
    assert data["lands"] == ["hallowed fountain"]


def test_land_names_reads_the_snapshot_and_tolerates_old_ones(snapdir, offline):
    (snapdir / "test-commander.json").write_text(json.dumps({
        "slug": "test-commander", "inclusion": {"hallowed fountain": 55},
        "synergy": {}, "names": {}, "lands": ["hallowed fountain"]}),
        encoding="utf-8")
    assert edhrec.land_names("Test Commander") == {"hallowed fountain"}
    # a snapshot written before the `lands` key existed degrades to "no signal"
    (snapdir / "old-commander.json").write_text(json.dumps({
        "slug": "old-commander", "inclusion": {"sol ring": 90},
        "synergy": {}, "names": {}}), encoding="utf-8")
    assert edhrec.land_names("Old Commander") == set()


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


# --------------------------------------------------------------------------- #
# Cohesion round 3 — the assess packet and the reverse combo signal
# --------------------------------------------------------------------------- #
def test_assess_packet_carries_the_merged_buy_view(tmp_path, collection_file, monkeypatch):
    """The coach must read the same shopping list the player sees — one merged,
    provenance-labeled section, not fragments to reassemble."""
    import shutil
    import sys as _sys
    import combo_detector
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "t.txt").write_text("# Title: T\n# Commander: Test Commander\n"
                                 "# Colors: W U\n\n# --- Ramp ---\n1 Sol Ring\n",
                                 encoding="utf-8")
    os.environ["MTG_DECKS_DIR"] = str(decks)
    os.environ["MTG_COLLECTION"] = collection_file
    _sys.modules.pop("app", None)
    import app
    fake = [{"name": "Sol Ring + Widget", "pieces": ["sol ring", "assess widget"],
             "display": ["Sol Ring", "Assess Widget"], "result": "Infinite mana",
             "early": False}]
    monkeypatch.setattr(combo_detector, "load_combos", lambda *a, **k: fake)
    app.app.config["TESTING"] = True
    txt = app.app.test_client().get("/deck/t/assess.txt").get_data(as_text=True)
    assert "CARDS TO BUY" in txt
    assert "Assess Widget" in txt
    assert "[combo" in txt, "provenance labels must survive into the packet"


def test_card_payload_says_what_this_card_completes(tmp_path, collection_file):
    import card_api
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "vito.txt").write_text("# Title: V\n# --- Cards ---\n"
                                    "1 Vito, Thorn of the Dusk Rose\n", encoding="utf-8")
    combos = [{"name": "Exquisite Blood + Vito", "pieces": ["exquisite blood",
               "vito, thorn of the dusk rose"],
               "display": ["Exquisite Blood", "Vito, Thorn of the Dusk Rose"],
               "result": "Drain the table", "early": False, "notes": ""}]
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    payload = card_api.card_payload("Exquisite Blood", idx, str(decks), combos=combos)
    assert payload["completes"] == [{"deck": "vito", "combo": "Exquisite Blood + Vito",
                                     "result": "Drain the table"}]


def test_completes_is_empty_for_an_uninvolved_card(tmp_path, collection_file):
    import card_api
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "d.txt").write_text("# --- Cards ---\n1 Sol Ring\n", encoding="utf-8")
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    payload = card_api.card_payload("Counterspell", idx, str(decks), combos=[])
    assert payload["completes"] == []


# --------------------------------------------------------------------------- #
# The snapshot Action — textual guards (no YAML parser in a stdlib-only suite).
# These catch the drift that would silently break the automation: renaming the
# CLI flag, dropping the write permission, or losing a trigger.
# --------------------------------------------------------------------------- #
def test_snapshot_workflow_matches_the_cli_it_drives():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wf = open(os.path.join(root, ".github", "workflows", "field-snapshots.yml"),
              encoding="utf-8").read()
    assert "--snapshot-all" in wf, "the workflow must call the flag edhrec.py actually has"
    assert "collection_snapshot.txt" in wf, "name-only snapshot only — nothing private"
    assert "contents: write" in wf, "without write permission the commit step 403s"
    for trigger in ("schedule:", "workflow_dispatch:", "data/decks/*.txt"):
        assert trigger in wf, f"missing trigger: {trigger}"
    assert "data/reference/field/" in wf, "must commit the snapshot dir the loaders read"


def test_snapshot_cli_flags_still_exist():
    """The workflow shells out to this exact interface — if a rename lands here
    without updating the YAML, this pins the mismatch to a test name."""
    import edhrec as _e
    src = open(_e.__file__, encoding="utf-8").read()
    assert "--snapshot-all" in src and "save_snapshot" in src


def test_spellbook_degrades_on_a_corrupt_cache(tmp_path, monkeypatch):
    """Regression: the cache-hit path was an unguarded json.load, so a truncated
    cache file CRASHED find_my_combos instead of degrading — the module's own
    contract says errors become an `error` payload. A corrupt file is a miss."""
    import spellbook
    monkeypatch.setattr(spellbook, "CACHE_DIR", str(tmp_path))
    import hashlib as _h
    sig = "|".join(sorted(["Test Commander"])) + "#" + "|".join(sorted(["sol ring"]))
    key = _h.sha1(sig.encode()).hexdigest()[:16]
    (tmp_path / f"{key}.json").write_text('{"present": [truncated', encoding="utf-8")
    def boom(*a, **k):
        raise OSError("egress blocked")
    monkeypatch.setattr(spellbook, "_post", boom)
    out = spellbook.find_my_combos(["Test Commander"], [("sol ring", 1)])
    assert out["error"] and out["present"] == [] and out["almost"] == []


def test_spellbook_failure_is_remembered_for_a_cooldown(tmp_path, monkeypatch):
    """An unreachable CSB used to cost a fresh network attempt on EVERY deck-page
    view: successes cached for a week, failures for nothing. Profiling a warm
    render made it the single biggest cost in the request (315 ms proxied; the
    ceiling is the 25 s socket timeout when a connection hangs rather than
    refuses). The failure is remembered — never served as data — so an outage
    costs one attempt per FAIL_TTL, and a recovered service is picked up as soon
    as the cooldown lapses."""
    import spellbook
    monkeypatch.setattr(spellbook, "CACHE_DIR", str(tmp_path))
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise OSError("egress blocked")
    monkeypatch.setattr(spellbook, "_post", boom)

    first = spellbook.find_my_combos(["Cmd"], [("Sol Ring", 1)])
    second = spellbook.find_my_combos(["Cmd"], [("Sol Ring", 1)])
    assert len(calls) == 1, "the second call must not re-attempt the network"
    assert first["error"] and second["error"], "the error payload is unchanged"
    assert second["present"] == [] and second["almost"] == []
    assert second.get("cooldown") is True

    # Cooldown lapsed → try again, and a success clears the marker for good.
    monkeypatch.setattr(spellbook, "_post",
                        lambda *a, **k: {"results": {"identity": "WU", "included": [],
                                                     "almostIncluded": []}})
    ok = spellbook.find_my_combos(["Cmd"], [("Sol Ring", 1)], fail_ttl=0)
    assert ok["error"] is None and ok["identity"] == "WU"
    import hashlib as _h
    key = _h.sha1(("Cmd" + "#" + "Sol Ring").encode()).hexdigest()[:16]
    assert not os.path.exists(str(tmp_path / f"{key}.fail")), \
        "a success must clear the failure marker, not leave it to expire"


def test_attrs_snapshot_workflow_is_name_only_and_guarded():
    """The committed attrs file's privacy property is enforced, not assumed
    (docs/spec-network-and-attrs.md §3): the workflow may only read the
    name-only snapshot, must refuse to run beside the private CSV, must omit
    printing ids, and must carry the resolution-rate floor. This test is the
    cheapest lock on all four — pointing the Action at the private collection
    fails the suite before it can leak a byte."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wf = open(os.path.join(root, ".github", "workflows",
                           "attrs-snapshot.yml"), encoding="utf-8").read()
    # Assert the LOAD-BEARING strings against comment-stripped CODE: the review
    # mutation-proved that checking the raw text let '--no-ids' and '--min-match'
    # be satisfied by the workflow's own comments while absent from the command.
    code = "\n".join(ln for ln in wf.splitlines()
                      if not ln.lstrip().startswith("#"))
    # The private CSV may be NAMED (the refuse-to-run guard names it to assert
    # its absence) but must never be an INPUT: the only --collection argument
    # is the name-only snapshot.
    assert "--collection data/collection/collection_snapshot.txt" in code
    assert "--collection data/collection/collection.csv" not in code, \
        "the private collection CSV must never be the enrichment input"
    assert "test ! -f data/collection/collection.csv" in code, \
        "the runner must refuse to run beside the private collection"
    assert "--out data/collection/collection_attrs.snapshot.csv" in code
    assert "--no-ids" in code, "printing ids must stay out of the committed file"
    assert "--min-match" in code, "the resolution-rate floor is not optional"
    assert "test ! -f data/collection/collection_attrs.csv" in code, \
        "the sibling-absence guard is what makes the privacy property an invariant"
    assert "contents: write" in code
    assert "group: field-snapshots" in code, \
        "the SHARED concurrency group is what serializes the three main-pushers"
    assert "set +e" not in code, \
        "carddb's non-zero exit is the failure signal — never swallow it"


def test_edhrec_failure_is_remembered_for_a_cooldown(tmp_path, monkeypatch):
    """The hot path's worst case. EDHREC is PERMANENTLY unreachable from the
    hosted app (free-tier allowlist — see the codemap's deployment matrix), and a
    single deck-page render calls `recommendations` three times. Every one of
    those was a fresh doomed round trip: 950 ms of a warm render, measured, on
    every view, on a host where it can never succeed.

    The three-tier read (live → disk cache → committed snapshot) is unchanged —
    remembering the failure only makes tier 1 fail fast so tiers 2 and 3 are
    reached immediately. Nothing here ever stores an empty page as if it were
    real data."""
    import edhrec
    import urllib.request
    monkeypatch.setattr(edhrec, "CACHE_DIR", str(tmp_path))
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise OSError("egress blocked")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    fetch = edhrec._fetch_unblocked          # see the conftest fixture's note
    for _ in range(3):
        with pytest.raises(OSError):
            fetch("test-commander")
    assert len(calls) == 1, "three calls made three doomed network attempts"

    payload = {"container": {"json_dict": {"cardlists": []}}}

    class _Resp:
        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())
    got = fetch("test-commander", fail_ttl=0)              # cooldown lapsed
    assert got == payload
    assert not os.path.exists(str(tmp_path / "test-commander.fail")), \
        "a reachable EDHREC must clear the marker, not wait it out"


def test_a_field_snapshot_is_byte_stable_across_runs(tmp_path, monkeypatch):
    """Committed + runner-regenerated means byte-stability matters.

    Keys that tie on value came out in whatever order the upstream response listed
    them, so two runs over identical data produced a diff that moved a line and
    changed nothing. Four such commits landed on one branch in a single session
    (2026-08-20) — each a merge conflict waiting to happen, carrying no information.
    A snapshot commit should appear only when the FIELD actually changed.

    Drives the real `save_snapshot`, with the same field data presented in two
    different iteration orders — which is exactly what the upstream response did."""
    import edhrec
    monkeypatch.setattr(edhrec, "SNAP_DIR", str(tmp_path))
    monkeypatch.setattr(edhrec, "_snapshot_path",
                        lambda slug: str(tmp_path / f"{slug}.json"))

    def _rec(order):
        # `_distill` reads sections -> cards; ties on inclusion are the case that
        # used to come out in arbitrary order.
        return {"slug": "test-commander", "sample_decks": 100, "source": "live",
                "sections": [{"header": "Creatures",
                              "cards": [{"name": n, "inclusion": 7, "synergy": 1}
                                        for n in order]}]}

    outs = []
    for order in (["zebra", "apple", "mongoose"], ["mongoose", "zebra", "apple"]):
        monkeypatch.setattr(edhrec, "recommendations",
                            lambda *a, _o=order, **k: _rec(_o))
        path = edhrec.save_snapshot("Test Commander", {})
        assert path, "live data must produce a snapshot"
        outs.append(open(path, encoding="utf-8").read())

    assert outs[0] == outs[1], (
        "same field data in a different order must produce an IDENTICAL file")
