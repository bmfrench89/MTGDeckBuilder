"""The web app in collection-database mode (docs/spec-target-architecture.md Phase 1).

Each test drives the real routes against a tmp database seeded from a tmp export,
tmp decks and a tmp owned_additions.txt. What is pinned: once the database exists,
every write goes to it and none to owned_additions.txt; Upload merges and never
lowers; a count can be edited (with permission) but never invented; the whole
collection downloads; and the page tells the player where their cards live.
"""
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
    html = env.client.get("/collection").get_data(as_text=True)
    assert "Your collection lives here" in html
    assert "Download my whole collection" in html and "Set count" in html
    assert "Merge this export" in html and "Replace my whole collection" not in html
    assert "owned_additions.txt" not in html


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
    html = env.client.get("/collection").get_data(as_text=True)
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
    html = env.client.get("/collection").get_data(as_text=True)
    assert "Your collection lives here" not in html and "Replace my whole collection" in html
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
