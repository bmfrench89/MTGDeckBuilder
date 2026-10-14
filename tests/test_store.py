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
  * every engine reads it through `mtglib.load_collection`, unchanged;
  * decks and pins are kept with every revision, and restored only where missing;
  * members move in from users.json exactly once (the file is retired so a stale
    copy can never be read), the database turns owner-only, and no download ever
    carries a password hash; activity.csv rows are taken in exactly once.
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
              additions=world.adds, decks=world.decks_dir, pins=str(world.dir / "pins.csv"),
              activity=str(world.dir / "activity.csv"))
    first = collection_db.run(**kw)
    assert first.startswith("collection db: SEEDED") and "decks: saved 3 new" in first
    assert "backup" not in first, "nothing to back up before the seed"
    assert collection_db.run(**kw).startswith(
        "collection db: up to date · decks: up to date · backup: saved collection-")
    with open(world.adds, "a", encoding="utf-8") as f:
        f.write("\n# --- Batch 2026-10-14 · photos · 1 cards (1 distinct) ---\n1 Brainstorm\n")
    third = collection_db.run(**kw)
    assert "ingested 1 new batch" in third and "backup" not in third, "one copy a day"


def test_the_sync_step_respects_an_operator_override(world, monkeypatch):
    import collection_db
    monkeypatch.setenv("MTG_COLLECTION", world.export)
    assert "skipped" in collection_db.run(db=world.db, export=world.export,
                                          august=world.august, additions=world.adds,
                                          decks=world.decks_dir,
                                          pins=str(world.dir / "pins.csv"))
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


# --------------------------------------------------------------------------- #
# Decks and pins (Phase 1b): the database keeps every version; the folder is the
# working copy, rebuilt from the database when it is gone.
# --------------------------------------------------------------------------- #
@pytest.fixture
def decks(world):
    (world.dir / "pins.csv").write_text("Card,Deck\nLightning Bolt,live\n", encoding="utf-8")

    class D:
        db = world.db
        dir = world.decks_dir
        pins = str(world.dir / "pins.csv")
    return D


def test_capture_records_every_deck_file_and_pins(decks):
    assert store.capture(decks.db, decks.dir, decks.pins, action="first", by="t") == \
        {"added": 4, "changed": 0, "removed": 0}
    held = store.stored_files(decks.db)
    assert set(held) == {"decks/live.txt", "decks/other.txt", "decks/study.txt", "pins.csv"}
    assert held["pins.csv"].startswith("Card,Deck")
    assert store.capture(decks.db, decks.dir, decks.pins) == \
        {"added": 0, "changed": 0, "removed": 0}, "an unchanged folder records nothing"


def test_only_deck_files_and_companions_are_kept(decks):
    import os
    for junk in ("notes.txt.bak", ".hidden.txt", "image.png"):
        open(os.path.join(decks.dir, junk), "w").write("x")
    open(os.path.join(decks.dir, "live.notes.md"), "w").write("# plan")
    store.capture(decks.db, decks.dir, decks.pins)
    held = store.stored_files(decks.db)
    assert "decks/live.notes.md" in held
    assert not {"decks/notes.txt.bak", "decks/.hidden.txt", "decks/image.png"} & set(held)


def test_an_edit_and_a_removal_are_revisions_and_nothing_is_lost(decks):
    import os
    store.capture(decks.db, decks.dir, decks.pins, action="first")
    p = os.path.join(decks.dir, "live.txt")
    open(p, "a", encoding="utf-8").write("1 Sol Ring\n")
    os.remove(os.path.join(decks.dir, "other.txt"))
    r = store.capture(decks.db, decks.dir, decks.pins, action="app /deck/live/card", by="me")
    assert r == {"added": 0, "changed": 1, "removed": 1}
    hist = store.file_history(decks.db, "decks/live.txt")
    assert [h["action"] for h in hist] == ["first", "app /deck/live/card"]
    assert hist[-1]["by"] == "me"
    assert "decks/other.txt" not in store.stored_files(decks.db)
    assert "decks/other.txt" in store.stored_files(decks.db, live_only=False), \
        "a removed deck keeps its history"


def test_a_lost_working_copy_is_rebuilt_exactly(decks, tmp_path):
    store.capture(decks.db, decks.dir, decks.pins)
    fresh, pins = tmp_path / "newhost" / "decks", tmp_path / "newhost" / "pins.csv"
    assert store.deck_working_copy_missing(str(fresh))
    written = store.restore(decks.db, str(fresh), str(pins))
    assert sorted(written) == ["decks/live.txt", "decks/other.txt", "decks/study.txt",
                               "pins.csv"]
    assert (fresh / "live.txt").read_text(encoding="utf-8") == LIVE
    assert pins.read_text(encoding="utf-8").startswith("Card,Deck")


def test_a_bulk_restore_never_overwrites_a_file_on_disk(decks):
    import os
    store.capture(decks.db, decks.dir, decks.pins)
    p = os.path.join(decks.dir, "live.txt")
    open(p, "w", encoding="utf-8").write("# edited since\n")
    assert store.restore(decks.db, decks.dir, decks.pins) == []
    assert open(p, encoding="utf-8").read() == "# edited since\n"


def test_one_file_restores_to_an_earlier_version_and_that_is_logged(decks):
    import os
    store.capture(decks.db, decks.dir, decks.pins, action="first")
    p = os.path.join(decks.dir, "live.txt")
    open(p, "w", encoding="utf-8").write("# a bad edit\n")
    store.capture(decks.db, decks.dir, decks.pins, action="bad")
    first = store.file_history(decks.db, "decks/live.txt")[0]["id"]
    assert store.restore(decks.db, decks.dir, decks.pins, key="decks/live.txt", rev=first) \
        == ["decks/live.txt"]
    assert open(p, encoding="utf-8").read() == LIVE
    assert store.file_history(decks.db, "decks/live.txt")[-1]["action"] == f"restore rev {first}"
    assert store.capture(decks.db, decks.dir, decks.pins) == \
        {"added": 0, "changed": 0, "removed": 0}, "the restore already recorded itself"


def test_the_decks_download_holds_every_live_file(decks):
    import io
    import zipfile
    store.capture(decks.db, decks.dir, decks.pins)
    z = zipfile.ZipFile(io.BytesIO(store.decks_zip(decks.db)))
    assert sorted(z.namelist()) == ["decks/live.txt", "decks/other.txt", "decks/study.txt",
                                    "pins.csv"]
    assert z.read("decks/live.txt").decode("utf-8") == LIVE


def test_the_sync_rebuilds_a_missing_deck_folder(world, monkeypatch, tmp_path):
    import shutil
    import collection_db
    monkeypatch.delenv("MTG_COLLECTION", raising=False)
    pins = str(world.dir / "pins.csv")
    kw = dict(db=world.db, export=world.export, august=world.august,
              additions=world.adds, decks=world.decks_dir, pins=pins,
              activity=str(world.dir / "activity.csv"))
    collection_db.run(**kw)
    shutil.rmtree(world.decks_dir)
    assert "decks: RESTORED 3 file(s)" in collection_db.run(**kw)
    assert open(f"{world.decks_dir}/live.txt", encoding="utf-8").read() == LIVE


# --------------------------------------------------------------------------- #
# Members and the activity log (Phase 1b, 2026-10-14: "move members and activity
# into the db too"). The store keeps users.py's dict as-is; hashes are opaque here.
# --------------------------------------------------------------------------- #
PEOPLE = {"owner": {"display": "Ben"}, "members_can_upload": True,
          "members": {"sam": {"name": "sam", "display": "Sam", "role": "member",
                              "hash": "scrypt:NOT-A-REAL-HASH", "ver": 3,
                              "disabled": False}}}


def _users_json(world, data=PEOPLE):
    p = world.dir / "users.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_a_database_without_a_member_store_is_single_password_mode(world):
    _seed(world)
    assert store.people_load(world.db) is None
    assert store.people_load(world.db, import_from=str(world.dir / "absent.json")) is None
    missing = str(world.dir / "never.db")
    assert store.people_load(missing) is None and not os.path.exists(missing), \
        "reading never creates a database"


def test_users_json_moves_in_once_and_the_file_is_retired(world):
    _seed(world)
    src = _users_json(world)
    got = store.people_load(world.db, import_from=src)
    assert got == PEOPLE
    assert not os.path.exists(src) and os.path.exists(src + ".moved-to-db"), \
        "a stale copy can never be read again; the renamed file is the backup"
    assert store.people_load(world.db, import_from=src) == PEOPLE
    note = json.loads(store.meta(world.db, "people_imported"))
    assert note["from"] == "users.json" and note["members"] == 1


def test_the_import_never_overwrites_a_store_the_database_has(world):
    _seed(world)
    store.people_save(world.db, PEOPLE)
    other = dict(PEOPLE, owner={"display": "Someone else"}, members={})
    src = _users_json(world, other)
    assert store.people_load(world.db, import_from=src) == PEOPLE
    assert os.path.exists(src), "a file the database did not take is not renamed"


def test_an_unreadable_users_json_is_left_alone(world):
    _seed(world)
    p = world.dir / "users.json"
    p.write_text("{not json", encoding="utf-8")
    assert store.people_load(world.db, import_from=str(p)) is None
    assert p.exists()


def test_the_member_store_round_trips_and_the_database_turns_private(world):
    import stat
    _seed(world)
    os.chmod(world.db, 0o644)
    data = json.loads(json.dumps(PEOPLE))
    data["members"]["sam"].update(ver=4, disabled=True)
    data["members"]["kit"] = {"name": "kit", "display": "Kit", "role": "member",
                              "hash": "scrypt:ALSO-NOT-REAL", "ver": 1, "disabled": False}
    store.people_save(world.db, data)
    assert store.people_load(world.db) == data
    assert stat.S_IMODE(os.stat(world.db).st_mode) & 0o077 == 0, "hashes: owner only"
    del data["members"]["kit"]
    store.people_save(world.db, data)
    assert set(store.people_load(world.db)["members"]) == {"sam"}, "a removal sticks"


def test_no_download_ever_carries_a_password_hash(world, capsys):
    _seed(world)
    store.people_save(world.db, PEOPLE)
    store.log_activity(world.db, [("2026-10-14 10:00", "Sam", "pin", "live", "Sol Ring")])
    store.capture(world.db, world.decks_dir)
    exports = (store.export_csv(world.db) + store.activity_csv(world.db) +
               store.decks_zip(world.db).decode("latin-1"))
    store.main(["stats", "--db", world.db])
    store.main(["activity", "--db", world.db])
    assert "NOT-A-REAL-HASH" not in exports + capsys.readouterr().out


def test_the_activity_log_reads_newest_first_and_downloads_whole(world):
    _seed(world)
    store.log_activity(world.db, [("2026-10-14 10:00", "Ben", "pin", "live", "Sol Ring"),
                                  ("2026-10-14 10:00", "Sam", "set bracket", "live", "4")])
    store.log_activity(world.db, [("2026-10-14 11:30", "Sam", "optimize", "live", None)])
    rows = store.activity_rows(world.db)
    assert [(r["By"], r["Action"]) for r in rows] == [
        ("Sam", "optimize"), ("Sam", "set bracket"), ("Ben", "pin")]
    assert rows[0] == {"When": "2026-10-14 11:30", "By": "Sam", "Action": "optimize",
                       "Deck": "live", "Detail": ""}
    assert len(store.activity_rows(world.db, limit=1)) == 1
    assert store.activity_csv(world.db).splitlines() == [
        "When,By,Action,Deck,Detail", "2026-10-14 10:00,Ben,pin,live,Sol Ring",
        "2026-10-14 10:00,Sam,set bracket,live,4", "2026-10-14 11:30,Sam,optimize,live,"]


def test_activity_csv_rows_are_taken_in_exactly_once(world):
    _seed(world)
    p = world.dir / "activity.csv"
    p.write_text("When,By,Action,Deck,Detail\n2026-10-12 09:00,Sam,pin,live,Sol Ring\n"
                 "2026-10-12 09:05,Ben,delete deck,old,Old\n", encoding="utf-8")
    assert store.import_activity(world.db, str(p)) == 2
    assert store.import_activity(world.db, str(p)) == 0, "re-runs take nothing twice"
    with open(p, "a", encoding="utf-8") as f:
        f.write("2026-10-12 09:10,Sam,optimize,live,2\n")
    assert store.import_activity(world.db, str(p)) == 1, "only the straggler"
    assert [r["Action"] for r in store.activity_rows(world.db)] == \
        ["optimize", "delete deck", "pin"]
    p.write_text("When,By,Action,Deck,Detail\n", encoding="utf-8")
    assert store.import_activity(world.db, str(p)) == 0, "a rewritten file guesses nothing"
    with open(p, "a", encoding="utf-8") as f:
        f.write("2026-10-13 08:00,Ben,pin,live,Opt\n")
    assert store.import_activity(world.db, str(p)) == 1
    assert store.import_activity(world.db, str(world.dir / "absent.csv")) == 0


def test_the_sync_moves_the_activity_file_in_once(world, monkeypatch):
    import collection_db
    monkeypatch.delenv("MTG_COLLECTION", raising=False)
    act = world.dir / "activity.csv"
    act.write_text("When,By,Action,Deck,Detail\n2026-10-12 09:00,Sam,pin,live,Sol Ring\n",
                   encoding="utf-8")
    kw = dict(db=world.db, export=world.export, august=world.august,
              additions=world.adds, decks=world.decks_dir, pins=str(world.dir / "pins.csv"),
              activity=str(act))
    assert "activity: took in 1 row(s)" in collection_db.run(**kw)
    assert "activity" not in collection_db.run(**kw)
    assert act.exists(), "the file is never rewritten or deleted by the move"


def test_a_bad_activity_file_costs_only_its_own_phrase(world, monkeypatch, tmp_path):
    import collection_db
    monkeypatch.delenv("MTG_COLLECTION", raising=False)
    bad = tmp_path / "not-a-file.csv"
    bad.mkdir()
    line = collection_db.run(db=world.db, export=world.export, august=world.august,
                             additions=world.adds, decks=world.decks_dir,
                             pins=str(world.dir / "pins.csv"), activity=str(bad))
    assert line.startswith("collection db: SEEDED") and "decks: saved 3 new" in line
    assert "activity: skipped" in line



# --------------------------------------------------------------------------- #
# Backups (spec §4/§11): the database is the only record of app-side edits,
# accounts and the log, so the sync keeps daily copies, and the player can download
# one that never carries a password hash.
# --------------------------------------------------------------------------- #
def _tables(path):
    import sqlite3
    con = sqlite3.connect(path)
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("holdings", "ledger", "files", "members", "activity")}
    finally:
        con.close()


def _full_world(world):
    _seed(world)
    store.capture(world.db, world.decks_dir)
    store.people_save(world.db, PEOPLE)
    store.log_activity(world.db, [("2026-10-14 10:00", "Sam", "pin", "live", "Sol Ring")])


def test_a_backup_is_a_complete_private_copy(world):
    import stat
    _full_world(world)
    dest = store.backup(world.db, str(world.dir / "copy.db"))
    assert _tables(dest) == _tables(world.db)
    assert dest.endswith("copy.db") and not os.path.exists(dest + ".tmp")
    assert stat.S_IMODE(os.stat(dest).st_mode) & 0o077 == 0
    assert {c.name: c.quantity for c in mtglib.load_collection(dest)} == \
        {c.name: c.quantity for c in mtglib.load_collection(world.db)}


def test_the_download_copy_carries_no_password_hash_not_even_an_old_one(world):
    import sqlite3
    _full_world(world)
    # An old hash a reset left behind in a freed page. Planted with secure_delete OFF,
    # which is how many SQLite builds run, so the residue is there on every build.
    con = sqlite3.connect(world.db)
    con.execute("PRAGMA secure_delete=OFF")
    con.executemany("INSERT INTO members(key, display, hash) VALUES(?,?,?)",
                    [(f"old{i}", "Old", f"scrypt:AN-OLD-HASH-{i:02d}-" + "z" * 200)
                     for i in range(20)])
    con.commit()
    con.execute("DELETE FROM members WHERE key LIKE 'old%'")
    con.commit()
    con.close()
    full = open(store.backup(world.db, str(world.dir / "full.db")), "rb").read()
    assert b"NOT-A-REAL-HASH" in full, "the server's own copies are complete"
    assert b"AN-OLD-HASH" in full, "precondition: the freed page still holds old bytes"
    dest = store.backup(world.db, str(world.dir / "out.db"), without_hashes=True)
    raw = open(dest, "rb").read()
    assert b"NOT-A-REAL-HASH" not in raw and b"AN-OLD-HASH" not in raw
    counts = _tables(dest)
    assert counts["members"] == 0 and counts["holdings"] == _tables(world.db)["holdings"]
    assert counts["activity"] == 1 and counts["files"] == 3


def test_daily_backups_run_once_a_day_and_keep_the_newest(world):
    _seed(world)
    d = str(world.dir / "backups")
    for day in range(1, 10):
        assert store.daily_backup(world.db, d, keep=7, today=f"2026-10-0{day}")
    assert store.daily_backup(world.db, d, keep=7, today="2026-10-09") is None
    kept = store.list_backups(d)
    assert [b["date"] for b in kept] == [f"2026-10-0{n}" for n in range(9, 2, -1)]
    assert all(b["bytes"] > 0 for b in kept)


def test_the_sync_backs_up_before_it_changes_anything(world, monkeypatch):
    import collection_db
    monkeypatch.delenv("MTG_COLLECTION", raising=False)
    kw = dict(db=world.db, export=world.export, august=world.august,
              additions=world.adds, decks=world.decks_dir, pins=str(world.dir / "pins.csv"),
              activity=str(world.dir / "activity.csv"), backups=str(world.dir / "backups"))
    collection_db.run(**kw)                                        # the seed
    with open(world.adds, "a", encoding="utf-8") as f:
        f.write("\n# --- Batch 2026-10-14 · photos · 1 cards (1 distinct) ---\n"
                "1 Mox Opal\n")
    assert "ingested 1 new batch" in collection_db.run(**kw)
    (copy,) = store.list_backups(str(world.dir / "backups"))
    before = {c.name for c in mtglib.load_collection(str(world.dir / "backups" / copy["name"]))}
    assert "Mox Opal" not in before, "the copy is the state BEFORE the sync's changes"
    assert "Mox Opal" in {c.name for c in mtglib.load_collection(world.db)}


def test_a_failed_backup_never_stops_the_sync(world, monkeypatch):
    import collection_db
    monkeypatch.delenv("MTG_COLLECTION", raising=False)
    blocker = world.dir / "not-a-folder"
    blocker.write_text("x", encoding="utf-8")
    kw = dict(db=world.db, export=world.export, august=world.august,
              additions=world.adds, decks=world.decks_dir, pins=str(world.dir / "pins.csv"),
              activity=str(world.dir / "activity.csv"), backups=str(blocker))
    collection_db.run(**kw)
    line = collection_db.run(**kw)
    assert "collection db: up to date" in line and "backup: FAILED" in line


def test_backups_never_reach_git():
    ignore = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".gitignore"),
                  encoding="utf-8").read()
    assert "data/collection/backups/" in ignore.splitlines()
