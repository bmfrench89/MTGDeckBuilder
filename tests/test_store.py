"""The collection database (scripts/store.py) and its seed (docs/spec-target-
architecture.md, Phase 1).

The player's rule, 2026-10-13: "Both ManaPool and any other export is just where I
had cards at the time. I just need all cards accounted for." What is pinned here:
  * the seed is a UNION: the higher of export and August list, plus added batches,
    raised to what one sleeved deck holds, and never double-counted;
  * a `[floor]` batch raises a count, it never adds (in the database AND on a
    fresh clone that still reads files);
  * shared-card shortfalls across decks are reported, never invented;
  * every change is logged, an upload can only raise a count, and the database is
    never seeded twice;
  * batches a session commits are ingested exactly once, even after a row in them
    is retired;
  * every engine reads it through `mtglib.load_collection`, unchanged.
"""
import json
import os

import pytest

import mtglib
import store

EXPORT = """\
Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,Price
2,Sol Ring,1,,,{1},Artifact,,uncommon,aaaa,1.50
1,Counterspell,2,U,U,{U}{U},Instant,,common,bbbb,0.75
3,Island,0,,U,,Land,Island,common,cccc,0.05
"""

AUGUST = """\
# old list
1 Sol Ring
2 Counterspell
1 Tireless Tracker
1 Brainstorm
"""

ADDITIONS = """\
# Player-confirmed ownership not in the export yet.

# --- Batch 2026-10-12 · orders · 2 cards (2 distinct) ---
# Added in the app.
1 Brainstorm
1 Lightning Bolt

# --- Batch 2026-10-13 · Owned cards the export is missing · 1 cards (1 distinct) ---
# [floor] already on the August list
1 Tireless Tracker
"""

LIVE = """\
# Title: Live
# Commander: Kami of the Crescent Moon
# --- Commander ---
1 Kami of the Crescent Moon
# --- Spells ---
1 Howling Mine
1 Lightning Bolt
1 Counterspell
# --- Basics ---
20 Island
"""

OTHER = """\
# Title: Other
# Commander: Someone Else
# --- Commander ---
1 Someone Else
# --- Spells ---
1 Lightning Bolt
"""

STUDY = """\
# Title: Study
# Commander: Nobody
# Study: yes
# --- Spells ---
1 Mana Crypt
"""


@pytest.fixture
def world(tmp_path):
    coll = tmp_path / "coll"
    coll.mkdir()
    (coll / "collection.csv").write_text(EXPORT, encoding="utf-8")
    (coll / "collection_snapshot.txt").write_text(AUGUST, encoding="utf-8")
    (coll / "owned_additions.txt").write_text(ADDITIONS, encoding="utf-8")
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "live.txt").write_text(LIVE, encoding="utf-8")
    (decks / "other.txt").write_text(OTHER, encoding="utf-8")
    (decks / "study.txt").write_text(STUDY, encoding="utf-8")

    class W:
        db = str(coll / "collection.db")
        export = str(coll / "collection.csv")
        august = str(coll / "collection_snapshot.txt")
        adds = str(coll / "owned_additions.txt")
        decks_dir = str(decks)
        dir = coll
    return W


def _seed(w, **kw):
    return store.seed(w.db, w.export, w.august, w.adds, w.decks_dir, write=True, **kw)


def _counts(path):
    return {c.name: c.quantity for c in mtglib.load_collection(path)}


# --------------------------------------------------------------------------- #
# The union
# --------------------------------------------------------------------------- #
def test_the_seed_is_the_union_without_double_counting(world):
    _seed(world)
    got = _counts(world.db)
    assert got["Sol Ring"] == 2, "max(export 2, August 1)"
    assert got["Counterspell"] == 2, "the August list's higher count survives an export that lost one"
    assert got["Brainstorm"] == 2, "August 1 + one added copy"
    assert got["Lightning Bolt"] == 1, "added once; two decks listing it don't invent a second"
    assert got["Tireless Tracker"] == 1, "a [floor] row raises to 1, it doesn't add a second"
    assert got["Howling Mine"] == 1 and got["Kami of the Crescent Moon"] == 1, \
        "a card a sleeved deck holds is owned even when no list has it"
    assert "Island" not in got, "basics are never tracked"
    assert "Mana Crypt" not in got, "a study deck commits no physical card"


def test_the_report_names_what_a_person_should_look_at(world):
    text = _seed(world)
    assert "Counterspell — August 2, export 1" in text
    assert "Howling Mine — 1 in live" in text
    assert "Lightning Bolt — own 1, decks list 2" in text
    assert store.meta(world.db, "seed_report") == text


def test_the_export_spelling_and_card_data_win(world):
    _seed(world)
    sol = mtglib.index_by_name(mtglib.load_collection(world.db))["sol ring"]
    assert sol.price == 1.5 and sol.types == ["Artifact"] and sol.scryfall_id == "aaaa"
    assert sol.value == 3.0, "value follows the stored count"


def test_a_dry_run_writes_nothing(world):
    text = store.seed(world.db, world.export, world.august, world.adds, world.decks_dir)
    assert "DRY RUN" in text and not os.path.exists(world.db)


def test_it_is_never_seeded_twice(world):
    _seed(world)
    with pytest.raises(RuntimeError):
        _seed(world)
    assert _counts(world.db)["Sol Ring"] == 2


def test_every_seed_count_carries_its_sources(world):
    _seed(world)
    h = store.history(world.db, "Counterspell")
    assert h[0]["action"] == "seed"
    assert json.loads(h[0]["detail"]) == {"august": 2, "committed": 1, "deck": 1, "export": 1}


# --------------------------------------------------------------------------- #
# Reading it is the engines' ordinary path
# --------------------------------------------------------------------------- #
def test_attrs_overlays_still_apply_and_additions_are_not_merged_again(world):
    (world.dir / "collection_attrs.csv").write_text(
        "Name,Type,MV,Colors,Produced\nHowling Mine,Artifact,2,,\n", encoding="utf-8")
    _seed(world)
    idx = mtglib.index_by_name(mtglib.load_collection(world.db))
    assert idx["howling mine"].types == ["Artifact"]
    assert idx["howling mine"].produced == set(), "empty Produced cell = makes no mana"
    assert idx["brainstorm"].quantity == 2, "owned_additions is IN the database, not added on top"


def test_none_versus_empty_production_survives_the_round_trip(world):
    _seed(world)
    store.merge_export(world.db, [mtglib.Card(name="Command Tower", quantity=1,
                                              produced=set("WUBRG"))])
    store.merge_export(world.db, [mtglib.Card(name="Maze of Ith", quantity=1, produced=set())])
    idx = mtglib.index_by_name(mtglib.load_collection(world.db))
    assert idx["command tower"].produced == set("WUBRG")
    assert idx["maze of ith"].produced == set()
    assert idx["sol ring"].produced is None, "never enriched stays unknown"


# --------------------------------------------------------------------------- #
# Changes
# --------------------------------------------------------------------------- #
def test_set_add_and_their_ledger(world):
    _seed(world)
    assert store.set_qty(world.db, "Sol Ring", 1, reason="traded", by="me") == (2, 1)
    assert store.add_rows(world.db, [(2, "Sol Ring"), (5, "Forest")]) == (2, 1), \
        "basics are skipped"
    assert store.set_qty(world.db, "Not A Card", 3) is None, "set never invents a card"
    assert [(h["action"], h["delta"], h["qty_after"])
            for h in store.history(world.db, "Sol Ring")] == \
        [("seed", 2, 2), ("set", -1, 1), ("add", 2, 3)]
    assert store.set_qty(world.db, "Sol Ring", 0) == (3, 0)
    assert "Sol Ring" not in _counts(world.db), "a count of 0 no longer counts as owned"


def test_an_export_merge_never_lowers_a_count(world):
    _seed(world)
    res = store.merge_export(world.db, mtglib.parse_collection(
        "Quantity,Name,Price\n1,Sol Ring,9.99\n4,Brainstorm,0.5\n1,Mana Vault,40\n"))
    got = _counts(world.db)
    assert got["Sol Ring"] == 2, "a partial or older export can't lose a card"
    assert got["Brainstorm"] == 4 and got["Mana Vault"] == 1
    assert res == {"raised": 2, "added_copies": 3, "new_cards": 1, "refreshed": 1}
    assert mtglib.index_by_name(mtglib.load_collection(world.db))["sol ring"].price == 9.99, \
        "the export's price still refreshes the stored card"


def test_the_whole_collection_downloads_as_a_csv_that_reads_back(world):
    _seed(world)
    back = {c.name: c.quantity for c in mtglib.parse_collection(store.export_csv(world.db))}
    assert back == _counts(world.db)


# --------------------------------------------------------------------------- #
# Batches a session commits
# --------------------------------------------------------------------------- #
def test_new_batches_are_ingested_once(world):
    _seed(world)
    assert store.ingest(world.db, world.adds) == (0, 0), "the seed already counted these"
    with open(world.adds, "a", encoding="utf-8") as f:
        f.write("\n# --- Batch 2026-10-14 · photos · 2 cards (1 distinct) ---\n2 Sol Ring\n")
    assert store.ingest(world.db, world.adds) == (1, 2)
    assert store.ingest(world.db, world.adds) == (0, 0)
    assert _counts(world.db)["Sol Ring"] == 4


def test_retiring_a_row_does_not_reingest_its_batch(world):
    _seed(world)
    text = open(world.adds, encoding="utf-8").read()
    open(world.adds, "w", encoding="utf-8").write(
        text.replace("1 Lightning Bolt", "# retired 2026-10-14 (in export): 1 Lightning Bolt"))
    assert store.ingest(world.db, world.adds) == (0, 0)
    assert _counts(world.db)["Brainstorm"] == 2


def test_an_ingested_floor_batch_raises_and_never_adds(world):
    _seed(world)
    with open(world.adds, "a", encoding="utf-8") as f:
        f.write("\n# --- Batch 2026-10-14 · floor · 3 cards (2 distinct) ---\n"
                "# [floor]\n2 Sol Ring\n1 Ancient Tomb\n")
    assert store.ingest(world.db, world.adds) == (1, 1)
    got = _counts(world.db)
    assert got["Sol Ring"] == 2 and got["Ancient Tomb"] == 1


def test_a_fresh_clone_reads_floor_batches_as_floors_too(world):
    """File mode (no database): the floor row must not stack on the August copy."""
    got = _counts(world.august)
    assert got["Tireless Tracker"] == 1
    assert got["Brainstorm"] == 2 and got["Lightning Bolt"] == 1


def test_the_committed_list_leaves_out_what_the_additions_file_adds_back(world):
    _seed(world)
    counts = dict(store.snapshot_counts(world.db, world.adds))
    assert counts["Brainstorm"] == 1 and "Lightning Bolt" not in counts
    assert counts["Tireless Tracker"] == 1, "a floor row subtracts nothing"


# --------------------------------------------------------------------------- #
# The sync step
# --------------------------------------------------------------------------- #
def test_the_sync_seeds_once_then_ingests(world, monkeypatch):
    import collection_db
    monkeypatch.delenv("MTG_COLLECTION", raising=False)
    kw = dict(db=world.db, export=world.export, august=world.august,
              additions=world.adds, decks=world.decks_dir)
    assert collection_db.run(**kw).startswith("collection db: SEEDED")
    assert collection_db.run(**kw) == "collection db: up to date"
    with open(world.adds, "a", encoding="utf-8") as f:
        f.write("\n# --- Batch 2026-10-14 · photos · 1 cards (1 distinct) ---\n1 Brainstorm\n")
    assert "ingested 1 new batch" in collection_db.run(**kw)


def test_the_sync_step_respects_an_operator_override(world, monkeypatch):
    import collection_db
    monkeypatch.setenv("MTG_COLLECTION", world.export)
    assert "skipped" in collection_db.run(db=world.db, export=world.export,
                                          august=world.august, additions=world.adds,
                                          decks=world.decks_dir)
    assert not os.path.exists(world.db)


def test_the_sync_step_never_fails_the_sync(monkeypatch, capsys):
    import collection_db
    monkeypatch.setattr(collection_db, "run", lambda: 1 / 0)
    assert collection_db.main() == 0
    assert "skipped (ZeroDivisionError" in capsys.readouterr().out


def test_the_sync_script_runs_the_step_after_the_pull_and_never_fails_on_it():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "sync_server.sh"), encoding="utf-8").read()
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    call = code.find("python3 webapp/collection_db.py || true")
    assert call != -1
    assert code.find("git pull --rebase") < call < code.find('echo "sync: pushing'), \
        "after the pull (so session batches have arrived), before the push"


def test_the_database_is_never_committed():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ignore = open(os.path.join(root, ".gitignore"), encoding="utf-8").read()
    assert "data/collection/*.db" in ignore
