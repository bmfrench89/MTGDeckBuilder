"""The web app in collection-database mode (docs/spec-target-architecture.md Phase 1).

Each test drives the real routes against a tmp database seeded from a tmp export,
tmp decks and a tmp owned_additions.txt. What is pinned: once the database exists,
every write goes to it and none to owned_additions.txt; Upload merges and never
lowers; a count can be edited (with permission) but never invented; the whole
collection downloads; and the page tells the player where their cards live.
Phase 1b adds: deck edits become revisions, and members and the activity log live
in the database (users.json moves in once; no activity.csv is written).
"""
import os
import re

import pytest

import mtglib
import store

EXPORT = """\
Quantity,Name,Types,Price
2,Sol Ring,Artifact,1.50
1,Counterspell,Instant,0.75
"""

DECK = """\
# Title: Live
# Commander: Test Commander
# --- Commander ---
1 Test Commander
# --- Spells ---
1 Sol Ring
"""


def _verify(names):
    known = {"serra angel": "Serra Angel", "sol ring": "Sol Ring"}
    return [{"found": True, "name": known[n.lower()], "source": "scryfall",
             "price_usd": "1.00", "type_line": "Creature", "color_identity": "W"}
            if n.lower() in known else {"found": False, "reason": "no match"}
            for n in names]


@pytest.fixture
def env(tmp_path, monkeypatch):
    import app as appmod
    import deckcore
    import enrich_bg
    import sync
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "live.txt").write_text(DECK, encoding="utf-8")
    coll = tmp_path / "coll"
    coll.mkdir()
    (coll / "collection.csv").write_text(EXPORT, encoding="utf-8")
    adds = coll / "owned_additions.txt"
    db = str(coll / "collection.db")
    store.seed(db, str(coll / "collection.csv"), None, str(adds), str(decks), write=True)
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", db)
    monkeypatch.setattr(appmod, "COLLECTION_DB", db)
    monkeypatch.setattr(appmod, "COLLECTION_CSV", str(coll / "collection.csv"))
    monkeypatch.setattr(appmod, "COLLECTION_ATTRS", str(coll / "collection_attrs.csv"))
    monkeypatch.setattr(appmod, "ADDITIONS", str(adds))
    monkeypatch.setattr(appmod, "PASSWORD", None)
    monkeypatch.setattr(appmod, "_verify_names", _verify)
    monkeypatch.setattr(deckcore, "PINS", str(tmp_path / "pins.csv"))
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    monkeypatch.setattr(enrich_bg, "start", lambda *a, **k: "enrichment started")
    appmod.app.config["TESTING"] = True

    class E:
        app = appmod
        client = appmod.app.test_client()
    E.db, E.adds = db, adds
    return E


def _counts(env):
    return {c.name: c.quantity for c in mtglib.load_collection(env.db)}


def test_the_page_says_where_the_cards_live(env):
    # Since the Collection rebuild: the record and its tools on Manage, intake on Add.
    html = env.client.get("/collection/manage").get_data(as_text=True)
    assert "Your collection lives here" in html
    assert "Download my whole collection" in html and "Set count" in html
    add = env.client.get("/collection/add").get_data(as_text=True)
    assert "Merge this export" in add and "Replace my whole collection" not in add
    assert "owned_additions.txt" not in html + add
    assert "Every change is logged" in env.client.get("/collection").get_data(as_text=True)


def test_adding_one_card_writes_the_database_not_the_file(env):
    env.client.post("/collection/add", data={"name": "Sol Ring", "qty": "1"})
    assert _counts(env)["Sol Ring"] == 3
    assert not env.adds.exists()


def test_a_batch_writes_the_database_not_the_file(env):
    r = env.client.post("/collection/batch", data={"text": "1 Serra Angel\n1 Sol Ring"})
    token = re.search(r'name="token" value="([^"]+)"', r.get_data(as_text=True)).group(1)
    env.client.post("/collection/batch/confirm", data={"token": token})
    got = _counts(env)
    assert got["Serra Angel"] == 1 and got["Sol Ring"] == 3
    assert not env.adds.exists()


def test_a_count_can_be_set_and_is_logged(env):
    r = env.client.post("/collection/set", data={"name": "sol ring", "qty": "1",
                                                 "reason": "traded"})
    assert r.status_code == 302
    assert _counts(env)["Sol Ring"] == 1
    last = store.history(env.db, "Sol Ring")[-1]
    assert (last["action"], last["delta"], last["detail"]) == ("set", -1, "traded")
    assert r.headers["Location"].endswith("/collection/manage#edit")
    html = env.client.get("/collection/manage").get_data(as_text=True)
    assert "Recent changes" in html and "traded" in html


@pytest.mark.parametrize("qty", ["-1", "lots", "1000", ""])
def test_a_bad_count_changes_nothing(env, qty):
    env.client.post("/collection/set", data={"name": "Sol Ring", "qty": qty})
    assert _counts(env)["Sol Ring"] == 2


def test_setting_an_unknown_card_never_invents_it(env):
    env.client.post("/collection/set", data={"name": "Mana Crypt", "qty": "4"})
    assert "Mana Crypt" not in _counts(env)


def test_a_member_without_upload_rights_cannot_lower_a_count(env, monkeypatch):
    monkeypatch.setattr(env.app, "_may_replace_collection", lambda: False)
    r = env.client.post("/collection/set", data={"name": "Sol Ring", "qty": "0"})
    assert r.status_code == 403 and _counts(env)["Sol Ring"] == 2


def test_an_upload_merges_and_never_lowers(env):
    import io
    data = {"csv": (io.BytesIO(b"Quantity,Name\n1,Sol Ring\n2,Counterspell\n1,Mana Vault\n"),
                    "partial.csv")}
    r = env.client.post("/collection/upload", data=data, content_type="multipart/form-data")
    assert r.status_code == 302, "no Upload guard question: a merge can't lose anything"
    got = _counts(env)
    assert got["Sol Ring"] == 2 and got["Counterspell"] == 2 and got["Mana Vault"] == 1


def test_the_whole_collection_downloads(env):
    r = env.client.get("/export/collection.csv")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    back = {c.name: c.quantity for c in mtglib.parse_collection(r.get_data(as_text=True))}
    assert back == _counts(env)


def test_the_seed_report_is_readable(env):
    r = env.client.get("/collection/seed-report.txt")
    assert r.status_code == 200 and "Collection database seed" in r.get_data(as_text=True)


def test_file_mode_keeps_working_and_set_explains_itself(env, monkeypatch, tmp_path):
    csv_path = tmp_path / "coll" / "collection.csv"
    monkeypatch.setattr(env.app, "COLLECTION", str(csv_path))
    html = env.client.get("/collection/manage").get_data(as_text=True)
    assert "Your collection lives here" not in html
    assert "Replace my whole collection" in env.client.get("/collection/add").get_data(as_text=True)
    r = env.client.post("/collection/set", data={"name": "Sol Ring", "qty": "0"},
                        follow_redirects=True)
    assert "needs the collection database" in r.get_data(as_text=True)
    assert env.client.get("/export/collection.csv").status_code == 404


def test_a_tmp_collection_is_never_swapped_for_a_real_database(env, monkeypatch, tmp_path):
    """The auto-switch only ever moves a DEFAULT source to the database."""
    csv_path = str(tmp_path / "coll" / "collection.csv")
    monkeypatch.setattr(env.app, "COLLECTION", csv_path)
    env.client.get("/collection")
    assert env.app.COLLECTION == csv_path


def test_an_app_edit_to_a_deck_is_saved_as_a_revision(env):
    import deckcore
    r = env.client.post("/deck/live/pin", data={"name": "Sol Ring"})
    assert r.status_code == 302
    held = store.stored_files(env.db)
    assert "decks/live.txt" in held and "pins.csv" in held
    assert "sol ring" in held["pins.csv"].lower()
    hist = store.file_history(env.db, "pins.csv")
    assert hist[-1]["action"] == "app /deck/live/pin"
    env.client.post("/deck/live/pin", data={"name": "Sol Ring", "action": "unpin"})
    assert len(store.file_history(env.db, "pins.csv")) == 2


def test_a_refused_write_records_nothing(env):
    env.client.post("/deck/nope/pin", data={"name": "Sol Ring"})
    assert store.stored_files(env.db) == {}


def test_the_decks_download_and_the_page_line(env):
    env.client.post("/deck/live/pin", data={"name": "Sol Ring"})
    r = env.client.get("/export/decks.zip")
    assert r.status_code == 200 and r.mimetype == "application/zip"
    html = env.client.get("/collection/manage").get_data(as_text=True)
    assert "Download all decks" in html and "1 decks and your pins" in html


# --------------------------------------------------------------------------- #
# Members and the activity log live in the database too (Phase 1b, 2026-10-14)
# --------------------------------------------------------------------------- #
def _hash(pw):
    from werkzeug.security import generate_password_hash
    return generate_password_hash(pw)


def _gate(env, monkeypatch):
    monkeypatch.setattr(env.app, "PASSWORD", "owner-pass")
    monkeypatch.setattr(env.app.time, "sleep", lambda s: None)
    return env.app.app.test_client()


def _sign_in(client, name, password):
    return client.post("/login", data={"name": name, "password": password, "next": "/"})


def test_members_added_on_the_people_page_live_in_the_database(env):
    import users
    r = env.client.post("/people", data={"action": "add", "name": "sam",
                                         "password": "sam-password"})
    assert r.status_code == 302
    held = store.people_load(env.db)
    assert set(held["members"]) == {"sam"}
    assert "sam-password" not in held["members"]["sam"]["hash"], "a hash, never the password"
    assert not os.path.exists(users.PATH), "no users.json is written in database mode"
    html = env.client.get("/people").get_data(as_text=True)
    assert "kept in the app's database on the server" in html


def test_a_users_json_moves_in_on_first_read_and_its_members_still_sign_in(env, monkeypatch):
    import json
    import users
    with open(users.PATH, "w", encoding="utf-8") as f:
        json.dump({"owner": {"display": "Ben"}, "members_can_upload": False,
                   "members": {"sam": {"name": "sam", "display": "Sam", "role": "member",
                                       "hash": _hash("sam-password"), "ver": 1,
                                       "disabled": False}}}, f)
    c = _gate(env, monkeypatch)
    r = _sign_in(c, "sam", "sam-password")
    assert r.status_code == 302 and "/login" not in r.headers["Location"]
    assert c.get("/collection").status_code == 200
    assert not os.path.exists(users.PATH) and os.path.exists(users.PATH + ".moved-to-db")
    assert store.people_load(env.db)["owner"] == {"display": "Ben"}


def test_revocation_and_owner_only_pages_work_from_the_database(env, monkeypatch):
    import users
    c = _gate(env, monkeypatch)
    assert users.add_member("sam", "sam-password") is None
    _sign_in(c, "sam", "sam-password")
    assert c.get("/collection").status_code == 200
    assert c.get("/export/activity.csv").status_code == 403, "the log is the owner's"
    users.sign_out_everywhere("sam")
    r = c.get("/collection")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_activity_is_logged_in_the_database_and_never_in_a_file(env, tmp_path):
    import users
    users.set_owner_display("Ben")                       # a member store: named mode
    env.client.post("/deck/live/pin", data={"name": "Sol Ring"})
    env.client.post("/deck/live/pin", data={"name": "Sol Ring", "action": "unpin"})
    env.client.post("/deck/nope/pin", data={"name": "Sol Ring"})      # refused: no row
    rows = store.activity_rows(env.db)
    assert [(r["By"], r["Action"], r["Deck"]) for r in rows] == [
        ("Ben", "unpin", "live"), ("Ben", "pin", "live")]
    assert not (tmp_path / "activity.csv").exists()
    html = env.client.get("/activity").get_data(as_text=True)
    assert "unpin" in html and "Download the whole log" in html
    r = env.client.get("/export/activity.csv")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    lines = r.get_data(as_text=True).splitlines()
    assert lines[0] == "When,By,Action,Deck,Detail" and len(lines) == 3


def test_without_members_nothing_is_logged_in_database_mode_either(env, tmp_path):
    env.client.post("/deck/live/pin", data={"name": "Sol Ring"})
    assert store.people_load(env.db) is None and store.activity_rows(env.db) == []
    assert not (tmp_path / "activity.csv").exists()


def test_rows_an_older_app_left_in_activity_csv_show_up_once(env, tmp_path):
    import users
    users.set_owner_display("Ben")
    (tmp_path / "activity.csv").write_text(
        "When,By,Action,Deck,Detail\n2026-10-13 23:59,Sam,pin,live,Sol Ring\n",
        encoding="utf-8")
    env.client.get("/activity")
    html = env.client.get("/activity").get_data(as_text=True)
    assert html.count("2026-10-13 23:59") == 1


def test_a_member_store_that_cannot_be_read_never_fails_the_edit(env, monkeypatch):
    import sqlite3
    import users
    users.set_owner_display("Ben")

    def locked():
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(users, "exists", locked)
    r = env.client.post("/deck/live/pin", data={"name": "Sol Ring"})
    assert r.status_code == 302, "the pin is saved; only its log row is lost"
    assert store.activity_rows(env.db) == []


# --------------------------------------------------------------------------- #
# Backups: one file the owner can download, never carrying a password hash
# --------------------------------------------------------------------------- #
def test_the_backup_download_is_whole_and_carries_no_hash(env, tmp_path, monkeypatch):
    import sqlite3
    import tempfile
    import users
    scratch = tmp_path / "tmpdir"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    assert users.add_member("sam", "sam-password") is None      # a hash in the database
    env.client.post("/deck/live/pin", data={"name": "Sol Ring"})
    r = env.client.get("/export/backup.db")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    raw = r.get_data()
    assert raw.startswith(b"SQLite format 3\x00")
    assert store.people_load(env.db)["members"]["sam"]["hash"].encode() not in raw
    out = tmp_path / "downloaded.db"
    out.write_bytes(raw)
    con = sqlite3.connect(str(out))
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("holdings", "files", "activity", "members")}
    con.close()
    assert counts["members"] == 0 and counts["activity"] == 1 and counts["files"] >= 2
    assert {c.name: c.quantity for c in mtglib.load_collection(str(out))} == _counts(env)
    assert os.listdir(scratch) == [], "the temporary copy is removed after it is sent"


def test_only_the_owner_gets_a_backup_and_only_in_database_mode(env, monkeypatch, tmp_path):
    import users
    c = _gate(env, monkeypatch)
    assert users.add_member("sam", "sam-password") is None
    _sign_in(c, "sam", "sam-password")
    assert c.get("/export/backup.db").status_code == 403
    assert "Download a backup" not in c.get("/collection/manage").get_data(as_text=True)
    monkeypatch.setattr(env.app, "PASSWORD", None)
    monkeypatch.setattr(env.app, "COLLECTION", str(tmp_path / "coll" / "collection.csv"))
    assert env.client.get("/export/backup.db").status_code == 404


def test_the_page_offers_a_backup_and_counts_the_daily_copies(env):
    for day in ("2026-10-13", "2026-10-14"):
        store.daily_backup(env.db, env.app._backups_dir(), today=day)
    html = env.client.get("/collection/manage").get_data(as_text=True)
    assert "Download a backup" in html
    assert "last 2 days" in html and "newest 2026-10-14" in html
    cards = env.client.get("/collection").get_data(as_text=True)
    assert "last backup 2026-10-14" in cards, "the Cards tab's one quiet line"
