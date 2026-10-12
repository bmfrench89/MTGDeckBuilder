"""A second login: a named member whose edits are labelled (docs/spec-second-login.md).

Three promises are pinned here. Back-compat: with no users.json the app is exactly the
single-password app it was (no names, no `By`, no activity log). Revocation: a member
signed out everywhere or disabled is turned away on their very next request, and the
owner's session never is. Labels: every change the app writes says who made it, and
an old four-column `.changes.csv` keeps working everywhere after the migration.
Hermetic: decks, collection, users.json and the activity log all live in tmp_path.
"""
import csv
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DECK = """\
# Title: Test Deck
# Commander: Test Commander
# Colors: W U

# --- Commander ---
1 Test Commander

# --- Artifacts ---
1 Sol Ring
1 Arcane Signet

# --- Basics ---
10 Island
"""


@pytest.fixture
def env(tmp_path, monkeypatch, collection_file):
    import app as appmod
    import deckcore
    import enrich_bg
    import sync
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "td.txt").write_text(DECK, encoding="utf-8")
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", collection_file)
    monkeypatch.setattr(appmod, "COLLECTION_CSV", str(tmp_path / "coll" / "collection.csv"))
    monkeypatch.setattr(appmod, "ADDITIONS", str(tmp_path / "owned_additions.txt"))
    monkeypatch.setattr(appmod, "PASSWORD", "owner-pass")
    monkeypatch.setattr(appmod.time, "sleep", lambda s: None)
    monkeypatch.setattr(deckcore, "PINS", str(tmp_path / "pins.csv"))
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    monkeypatch.setattr(sync, "run", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(enrich_bg, "start", lambda *a, **k: "enrichment started")
    appmod.app.config["TESTING"] = True

    class E:
        app = appmod
        root = tmp_path

    E.decks = decks
    E.new = staticmethod(lambda: appmod.app.test_client())
    return E


def _login(client, password, name=""):
    return client.post("/login", data={"name": name, "password": password, "next": "/"})


def _members(*names):
    import users
    users.set_owner_display("Ben")
    for n in names:
        assert users.add_member(n, f"{n}-password") is None


def _changes(env, stem="td"):
    p = env.decks / f"{stem}.changes.csv"
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


# --------------------------------------------------------------------------- #
# Back-compat: no users.json means today's app
# --------------------------------------------------------------------------- #
def test_without_users_json_the_owner_signs_in_with_the_password_alone(env):
    c = env.new()
    page = c.get("/login").get_data(as_text=True)
    assert 'name="name"' not in page, "no Name field until a member exists"
    assert _login(c, "owner-pass").status_code == 302
    assert c.get("/").status_code == 200


def test_without_users_json_nothing_is_labelled_and_nothing_is_logged(env):
    c = env.new()
    _login(c, "owner-pass")
    c.post("/deck/td/card", data={"action": "remove", "name": "Sol Ring"})
    c.post("/deck/td/bracket", data={"bracket": "3"})
    header = open(env.decks / "td.changes.csv", encoding="utf-8").readline().strip()
    assert header == "Card,Added,Replaced,Source", "four columns, exactly as before"
    assert not (env.root / "activity.csv").exists()


def test_an_old_cookie_with_no_name_is_the_owner(env):
    _members("sam")
    c = env.new()
    with c.session_transaction() as s:
        s["authed"] = True                 # a cookie from before members existed
    assert c.get("/").status_code == 200
    assert c.get("/people").status_code == 200, "and it has the owner's powers"


# --------------------------------------------------------------------------- #
# Sign-in
# --------------------------------------------------------------------------- #
def test_owner_signs_in_with_a_blank_name_or_their_own_name(env):
    _members("sam")
    for name in ("", "Ben", "ben "):
        c = env.new()
        assert _login(c, "owner-pass", name).status_code == 302, name
        assert c.get("/people").status_code == 200


def test_a_member_signs_in_with_their_own_password_only(env):
    _members("sam")
    c = env.new()
    r = _login(c, "owner-pass", "sam")
    assert r.status_code == 200 and "Wrong name or password" in r.get_data(as_text=True)
    assert _login(c, "sam-password", "Sam").status_code == 302, "names are case-folded"
    assert c.get("/").status_code == 200
    assert c.get("/people").status_code == 403


def test_ten_failures_lock_the_name_out(env):
    _members("sam")
    c = env.new()
    for _ in range(10):
        _login(c, "nope", "sam")
    r = _login(c, "sam-password", "sam")
    assert "Too many wrong tries" in r.get_data(as_text=True)
    assert c.get("/").status_code == 302, "still signed out"
    assert _login(env.new(), "owner-pass").status_code == 302, "the owner is not locked"


def test_a_disabled_member_is_refused_and_an_active_session_ends(env):
    import users
    _members("sam")
    c = env.new()
    _login(c, "sam-password", "sam")
    users.set_disabled("sam", True)
    assert c.get("/").status_code == 302
    r = _login(env.new(), "sam-password", "sam")
    assert "Wrong name or password" in r.get_data(as_text=True)


def test_sign_out_everywhere_ends_only_that_members_sessions(env):
    _members("sam")
    member, owner = env.new(), env.new()
    _login(member, "sam-password", "sam")
    _login(owner, "owner-pass")
    assert owner.post("/people", data={"action": "signout", "name": "sam"}).status_code == 302
    r = member.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert owner.get("/").status_code == 200
    assert member.post("/deck/td/bracket", data={"bracket": "2"}).status_code == 401


# --------------------------------------------------------------------------- #
# What a member can and can't do
# --------------------------------------------------------------------------- #
def test_member_cannot_manage_people_or_replace_the_collection(env):
    _members("sam")
    c = env.new()
    _login(c, "sam-password", "sam")
    assert c.get("/people").status_code == 403
    assert c.post("/people", data={"action": "add", "name": "x", "password": "12345678"}
                  ).status_code == 403
    assert c.get("/activity").status_code == 403
    assert c.post("/collection/upload").status_code == 403
    assert c.post("/collection/upload/decide", data={"choice": "replace"}).status_code == 403
    assert c.post("/collection/reconcile", data={"action": "retire"}).status_code == 403


def test_member_may_replace_the_collection_when_the_owner_allows_it(env):
    import users
    _members("sam")
    users.set_members_can_upload(True)
    c = env.new()
    _login(c, "sam-password", "sam")
    assert c.post("/collection/upload").status_code == 302


def test_every_other_write_works_for_a_member(env):
    _members("sam")
    c = env.new()
    _login(c, "sam-password", "sam")
    assert c.post("/deck/td/bracket", data={"bracket": "3"}).status_code == 302
    assert c.post("/deck/td/card", data={"action": "remove", "name": "Arcane Signet"}
                  ).status_code == 302
    assert c.post("/collection/add", data={"name": "Mana Crypt", "qty": "1"}).status_code == 302
    assert c.get("/deck/td/changes").status_code == 200


# --------------------------------------------------------------------------- #
# Labels
# --------------------------------------------------------------------------- #
def test_panel_edits_and_editor_saves_are_labelled(env):
    _members("sam")
    c = env.new()
    _login(c, "sam-password", "sam")
    c.post("/deck/td/card", data={"action": "replace", "name": "Sol Ring",
                                  "replacement": "Counterspell"})
    text = (env.decks / "td.txt").read_text(encoding="utf-8")
    c.post("/deck/td/edit", data={"content": text.replace("1 Arcane Signet\n",
                                                           "1 Serra Angel\n")})
    rows = _changes(env)
    assert [(r["Card"], r["Replaced"], r["Source"], r["By"]) for r in rows] == [
        ("Counterspell", "Sol Ring", "manual-replace", "sam"),
        ("Serra Angel", "", "manual-add", "sam"),
        ("", "Arcane Signet", "manual-remove", "sam")]


def test_the_owner_is_labelled_with_their_display_name(env):
    _members("sam")
    c = env.new()
    _login(c, "owner-pass")
    c.post("/deck/td/card", data={"action": "remove", "name": "Sol Ring"})
    assert _changes(env)[-1]["By"] == "Ben"


def test_editor_saves_are_logged_even_without_members(env):
    """The gap the spec closes for everyone: an editor add is the player's decision
    and must protect the card from the optimizer like a panel Add does."""
    c = env.new()
    _login(c, "owner-pass")
    text = (env.decks / "td.txt").read_text(encoding="utf-8")
    c.post("/deck/td/edit", data={"content": text.replace("1 Sol Ring\n", "1 Mana Crypt\n")
                                  .replace("10 Island", "11 Island")})
    rows = _changes(env)
    assert [(r["Card"], r["Replaced"], r["Source"]) for r in rows] == [
        ("Mana Crypt", "", "manual-add"), ("", "Sol Ring", "manual-remove")]
    import deckcore
    assert [r["name"] for r in deckcore.manual_adds(str(env.decks / "td.changes.csv"),
                                                    days=None)] == ["Mana Crypt"]


def test_an_old_four_column_log_migrates_and_keeps_every_row(env, tmp_path):
    import deckcore
    p = tmp_path / "old.changes.csv"
    p.write_text("Card,Added,Replaced,Source\nSol Ring,2026-10-01,Mind Stone,0.5\n"
                 "Mana Crypt,2026-10-02,,manual-add\n", encoding="utf-8")
    deckcore.append_changes(str(p), [("Counterspell", "2026-10-03", "", "manual-add")],
                            by="Sam")
    rows = list(csv.reader(open(p, encoding="utf-8")))
    assert rows[0] == ["Card", "Added", "Replaced", "Source", "By"]
    assert rows[1] == ["Sol Ring", "2026-10-01", "Mind Stone", "0.5", ""]
    assert rows[3] == ["Counterspell", "2026-10-03", "", "manual-add", "Sam"]
    deckcore.append_changes(str(p), [("Opt", "2026-10-04", "", "x")])     # unlabelled
    assert list(csv.reader(open(p, encoding="utf-8")))[-1] == ["Opt", "2026-10-04", "", "x", ""]
    ch = deckcore.load_changes(str(p), days=None)
    assert ch["counterspell"]["by"] == "Sam" and ch["sol ring"]["by"] == ""
    assert [r["name"] for r in deckcore.manual_adds(str(p), days=None)][:1] == ["Counterspell"]


def test_the_new_badge_names_who_added_the_card():
    import build_dashboard as bd
    html = bd._new_badge("x", {"x": {"days_ago": 0, "added": "2026-10-12", "by": "Sam",
                                     "replaced": ""}})
    assert "Added by Sam today" in html
    assert "by" not in bd._new_badge("x", {"x": {"days_ago": 1, "added": "d", "replaced": ""}})


def test_optimizer_rows_carry_by():
    import inspect
    import optimize
    assert "by" in inspect.signature(optimize.optimize).parameters
    assert "by" in inspect.signature(optimize.record_changes).parameters


# --------------------------------------------------------------------------- #
# Activity log + sync
# --------------------------------------------------------------------------- #
def test_deck_level_actions_write_one_labelled_row_each(env):
    _members("sam")
    c = env.new()
    _login(c, "sam-password", "sam")
    c.post("/deck/td/bracket", data={"bracket": "4"})
    c.post("/deck/td/pin", data={"name": "Sol Ring"})
    c.post("/deck/td/bracket", data={"bracket": "9"})          # refused value: no row
    rows = list(csv.DictReader(open(env.root / "activity.csv", encoding="utf-8")))
    assert [(r["By"], r["Action"], r["Deck"], r["Detail"]) for r in rows] == [
        ("sam", "set bracket", "td", "4"), ("sam", "pin", "td", "Sol Ring")]
    owner = env.new()
    _login(owner, "owner-pass")
    assert "set bracket" in owner.get("/activity").get_data(as_text=True)


def test_sign_ins_are_not_logged(env):
    _members("sam")
    _login(env.new(), "sam-password", "sam")
    assert not (env.root / "activity.csv").exists()


def test_sync_commits_the_activity_log_and_never_the_accounts():
    src = open(os.path.join(ROOT, "sync_server.sh"), encoding="utf-8").read()
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert "data/activity.csv" in code
    assert "data/private" not in code
    ignore = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
    assert "data/private/" in ignore


def test_sync_summary_counts_labelled_rows_per_person():
    import sync_summary
    diff = ("+++ b/data/decks/x.changes.csv\n+Card,Added,Replaced,Source,By\n"
            "+Sol Ring,2026-10-12,,manual-add,Ben\n+Opt,2026-10-12,,0.5,\n"
            "+++ b/data/activity.csv\n+2026-10-12 10:00,Sam,optimize,x,2\n")
    assert sync_summary.summarize(diff) == "Ben: 1 change · Sam: 1 change"
    assert sync_summary.summarize("+++ b/data/decks/x.changes.csv\n+A,d,,s\n") == ""


def test_users_json_is_private(env):
    import stat
    import users
    _members("sam")
    mode = stat.S_IMODE(os.stat(users.PATH).st_mode)
    assert mode & 0o077 == 0, "owner read/write only"
    data = open(users.PATH, encoding="utf-8").read()
    assert "sam-password" not in data, "hashes only"
