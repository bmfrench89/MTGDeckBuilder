"""Track W of the 2026-10 whole-app audit (docs/spec-app-audit-2026-10.md, W1–W11).

Every test here reproduces a defect the auditor saw in the running app and fails on
the code before the fix: a path-traversing deck stem, Remove/Replace eating a whole
basics line, Build Next overwriting a tuned deck, cross-site writes with no password
set, an open redirect, a garbage upload replacing the private collection, basics read
as unowned, newline injection into line-oriented files, a spoofed Referer, and an
absurd quantity hanging the process.

Hermetic like the rest of the suite: decks, collection, additions, pins and the
upload target all live in tmp_path, and the network clients are blocked by conftest.
"""
import io
import os
import time

import pytest

DECK = """\
# Title: Basics Deck
# Commander: Test Commander
# Colors: W U

# --- Commander ---
1 Test Commander

# --- Artifacts ---
1 Sol Ring
# a comment the editor must never touch: Swamp

# --- Basics ---
21 Swamp
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
    (decks / "basics.txt").write_text(DECK, encoding="utf-8")
    coll_dir = tmp_path / "coll"
    coll_dir.mkdir()
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", collection_file)
    monkeypatch.setattr(appmod, "COLLECTION_CSV", str(coll_dir / "collection.csv"))
    monkeypatch.setattr(appmod, "COLLECTION_ATTRS", str(coll_dir / "collection_attrs.csv"))
    monkeypatch.setattr(appmod, "ADDITIONS", str(tmp_path / "owned_additions.txt"))
    monkeypatch.setattr(appmod, "PASSWORD", None)
    monkeypatch.setattr(deckcore, "PINS", str(tmp_path / "pins.csv"))
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    monkeypatch.setattr(enrich_bg, "start", lambda *a, **k: "enrichment started")
    appmod.app.config["TESTING"] = True

    class E:
        app = appmod
        client = appmod.app.test_client()
        root = tmp_path

    E.decks = decks
    E.coll_dir = coll_dir
    return E


def _text(env, stem="basics"):
    return (env.decks / f"{stem}.txt").read_text(encoding="utf-8")


def _total(env, text):
    return sum(c.quantity for c in env.app.mtglib.parse_deck(text))


# --------------------------------------------------------------------------- #
# W1 — a deck stem is a file name, never a path
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("stem", ["..\\outside", "../outside", "a/b", "C:\\Windows\\win",
                                  ".hidden", "", "a..b", "-x", "x y", "x\n"])
def test_deck_path_refuses_anything_but_a_plain_name(env, stem):
    assert env.app._deck_path(stem) is None


@pytest.mark.parametrize("stem", ["basics", "beorn-the-fierce", "Deck_2.v1"])
def test_deck_path_accepts_real_stems(env, stem):
    assert env.app._deck_path(stem) == os.path.join(str(env.decks), f"{stem}.txt")


def test_backslash_stem_cannot_delete_a_file(env):
    """On Windows `..\\..\\collection\\owned_additions` resolved outside data/decks/ and
    the Delete route removed the file. On POSIX the same stem names a literal file
    inside decks/, which the old code deleted just as happily — so this test bites
    on either OS."""
    victim = env.decks / "..\\outside.txt"
    victim.write_text("1 Sol Ring\n", encoding="utf-8")
    r = env.client.post("/deck/..%5Coutside/delete")
    assert r.status_code == 404
    assert victim.exists()


def test_symlink_out_of_the_decks_dir_is_refused(env):
    outside = env.root / "secret.txt"
    outside.write_text("# Title: secret\n1 Sol Ring\n", encoding="utf-8")
    try:
        os.symlink(outside, env.decks / "evil.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert env.app.deck_meta("evil") is None
    assert env.client.post("/deck/evil/edit", data={"content": "x"}).status_code == 404
    assert outside.read_text(encoding="utf-8").startswith("# Title: secret")


# --------------------------------------------------------------------------- #
# W2 — Remove / Replace move exactly ONE copy
# --------------------------------------------------------------------------- #
def test_remove_one_basic_decrements_the_line(env):
    before = _text(env)
    r = env.client.post("/deck/basics/card", data={"action": "remove", "name": "Swamp"})
    assert r.status_code == 302
    after = _text(env)
    assert "\n20 Swamp\n" in after
    assert _total(env, after) == _total(env, before) - 1
    assert "# a comment the editor must never touch: Swamp" in after
    assert "# --- Basics ---" in after


def test_replace_a_basic_writes_one_copy_of_the_incoming_card(env):
    before = _text(env)
    r = env.client.post("/deck/basics/card", data={"action": "replace", "name": "Swamp",
                                                    "replacement": "Totally Unknown Card"})
    assert r.status_code == 302
    after = _text(env)
    assert "\n20 Swamp\n1 Totally Unknown Card\n" in after
    assert "21 Totally Unknown Card" not in after
    assert _total(env, after) == _total(env, before)
    assert env.app.optimize.singleton_violations(str(env.decks / "basics.txt")) == []


def test_replace_a_basic_with_another_basic_moves_one_copy(env):
    env.client.post("/deck/basics/card", data={"action": "replace", "name": "Swamp",
                                               "replacement": "Island"})
    after = _text(env)
    assert "\n20 Swamp\n" in after and "\n11 Island\n" in after


def test_editor_unit_decrements_with_1x_syntax(tmp_path):
    import app
    p = tmp_path / "d.txt"
    p.write_text("# --- Basics ---\n3x Plains\n", encoding="utf-8")
    assert app._edit_deck_card(str(p), "remove", "Plains") is True
    assert p.read_text(encoding="utf-8") == "# --- Basics ---\n2 Plains\n"


# --------------------------------------------------------------------------- #
# W3 — Build Next never overwrites an existing deck
# --------------------------------------------------------------------------- #
def test_build_next_save_picks_a_free_stem(env, monkeypatch):
    import auto_build
    import optimize
    monkeypatch.setattr(auto_build, "build", lambda *a, **k: {"draft": True})
    monkeypatch.setattr(auto_build, "deck_text",
                        lambda d: "# Title: Draft\n# Commander: Test Commander\n"
                                  "# --- Commander ---\n1 Test Commander\n")
    monkeypatch.setattr(optimize, "optimize", lambda *a, **k: {})
    tuned = "# Title: My hand-tuned list\n# Commander: Test Commander\n1 Test Commander\n"
    (env.decks / "test-commander.txt").write_text(tuned, encoding="utf-8")
    (env.decks / "test-commander.notes.md").write_text("plan", encoding="utf-8")

    r = env.client.post("/build-next/Test Commander/save")
    assert r.status_code == 302 and r.headers["Location"].endswith("/deck/test-commander-2")
    assert _text(env, "test-commander") == tuned, "the tuned deck was overwritten"
    assert "Draft" in _text(env, "test-commander-2")

    r = env.client.post("/build-next/Test Commander/save")
    assert r.headers["Location"].endswith("/deck/test-commander-3")
    assert _text(env, "test-commander") == tuned


def test_orphaned_companion_also_reserves_the_stem(env):
    (env.decks / "solo.notes.md").write_text("old plan", encoding="utf-8")
    stem, path = env.app._free_deck_stem("solo")
    assert stem == "solo-2" and path.endswith("solo-2.txt")


# --------------------------------------------------------------------------- #
# W4 — cross-site writes are refused even with no password set
# --------------------------------------------------------------------------- #
def test_cross_origin_delete_is_refused(env):
    r = env.client.post("/deck/basics/delete",
                        headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    assert (env.decks / "basics.txt").exists()


def test_sec_fetch_site_cross_site_is_refused(env):
    r = env.client.post("/deck/basics/edit", data={"content": "# pwned\n"},
                        headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert _text(env) == DECK


def test_null_origin_is_refused(env):
    r = env.client.post("/deck/basics/delete", headers={"Origin": "null"})
    assert r.status_code == 403


def test_same_origin_and_headerless_writes_still_work(env):
    r = env.client.post("/deck/basics/bracket", data={"bracket": "3"},
                        headers={"Origin": "http://localhost",
                                 "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302
    r = env.client.post("/deck/basics/bracket", data={"bracket": "2"})   # curl-style
    assert r.status_code == 302
    assert "# Bracket: 2" in _text(env)


def test_cross_origin_get_is_not_blocked(env):
    r = env.client.get("/health", headers={"Origin": "http://evil.example",
                                           "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# W5 — _safe_next allows local paths only, and never 500s
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("target", ["/\t/evil.example", "/\n/evil.example",
                                    "/%09/evil.example", "/%0a/evil.example",
                                    "/ /evil.example", "/\\evil.example", "//evil.example",
                                    "/%2F/evil.example", "https://evil.example/",
                                    "evil.example", "javascript:alert(1)", "/\x7f/x",
                                    None, ""])
def test_safe_next_rejects_non_local_targets(env, target):
    with env.app.app.test_request_context("/"):
        assert env.app._safe_next(target) == "/"


@pytest.mark.parametrize("target", ["/deck/beorn", "/deck/x?tab=power#cuts", "/",
                                    "/build-next/The%20Ur-Dragon/deck"])
def test_safe_next_keeps_local_paths(env, target):
    with env.app.app.test_request_context("/"):
        assert env.app._safe_next(target) == target


def test_login_round_trip_keeps_a_path_with_spaces(env, monkeypatch):
    """The no-whitespace rule must not cost the player their page: the login
    redirect re-quotes the decoded path, so it comes back intact."""
    from urllib.parse import parse_qs, urlsplit
    monkeypatch.setattr(env.app, "PASSWORD", "pw")
    r = env.client.get("/build-next/The Ur-Dragon/deck?ci=WUBRG")
    nxt = parse_qs(urlsplit(r.headers["Location"]).query)["next"][0]
    r = env.client.post("/login", data={"password": "pw", "next": nxt})
    assert r.headers["Location"] == "/build-next/The%20Ur-Dragon/deck?ci=WUBRG"


def test_login_with_a_newline_next_redirects_home_instead_of_500(env, monkeypatch):
    monkeypatch.setattr(env.app, "PASSWORD", "pw")
    r = env.client.post("/login", data={"password": "pw", "next": "/\n/evil.example"})
    assert r.status_code == 302 and r.headers["Location"] == "/"


# --------------------------------------------------------------------------- #
# W6 — replace-with-basic changes nothing when the outgoing card is absent
# --------------------------------------------------------------------------- #
def test_replace_missing_card_with_a_basic_is_a_no_op(env):
    r = env.client.post("/deck/basics/card", data={"action": "replace",
                                                    "name": "Card Not In Deck",
                                                    "replacement": "Swamp"})
    assert r.status_code == 404
    assert _text(env) == DECK


# --------------------------------------------------------------------------- #
# W7 — an upload is validated before it replaces anything
# --------------------------------------------------------------------------- #
GOOD_CSV = "Quantity,Name\n1,Sol Ring\n"


def _upload(env, data, name="export.csv"):
    return env.client.post("/collection/upload",
                           data={"csv": (io.BytesIO(data), name)},
                           content_type="multipart/form-data")


@pytest.mark.parametrize("data", [b"\x89PNG\r\n\x1a\n\x00\x00garbage\xff\xfe", b"",
                                  b"a,b,c\n1,2,3\n", b"\n\n#only a comment\n"])
def test_bad_upload_keeps_the_previous_collection(env, data):
    dest = env.coll_dir / "collection.csv"
    dest.write_text(GOOD_CSV, encoding="utf-8")
    r = _upload(env, data)
    assert r.status_code == 302
    assert dest.read_text(encoding="utf-8") == GOOD_CSV
    assert not [p for p in os.listdir(env.coll_dir) if p.endswith(".tmp")], \
        "the temp copy must be cleaned up"
    assert env.client.get("/collection").status_code == 200


def test_good_upload_replaces_and_keeps_a_gitignored_backup(env):
    dest = env.coll_dir / "collection.csv"
    dest.write_text(GOOD_CSV, encoding="utf-8")
    from conftest import COLLECTION_CSV
    r = _upload(env, COLLECTION_CSV.encode("utf-8"))
    assert r.status_code == 302
    assert dest.read_text(encoding="utf-8") == COLLECTION_CSV
    bak = env.coll_dir / "collection.bak.private.csv"
    assert bak.read_text(encoding="utf-8") == GOOD_CSV
    # The backup holds a priced export: it must match a pattern .gitignore covers.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ignore = open(os.path.join(root, ".gitignore"), encoding="utf-8").read()
    assert "data/collection/*.private.csv" in ignore


def test_cp1252_upload_is_resaved_as_utf8(env):
    raw = "Quantity,Name\n1,Lim-Dûl the Necromancer\n1,Jötun Grunt\n".encode("cp1252")
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")
    assert _upload(env, raw).status_code == 302
    text = (env.coll_dir / "collection.csv").read_text(encoding="utf-8")
    assert "Lim-Dûl the Necromancer" in text
    assert env.app.COLLECTION == str(env.coll_dir / "collection.csv")
    assert env.client.get("/collection").status_code == 200


# --------------------------------------------------------------------------- #
# W8 — basics are always owned
# --------------------------------------------------------------------------- #
def test_leaderboard_does_not_count_basics_as_to_buy(env):
    html = env.client.get("/").get_data(as_text=True)
    # Swamp is not in the test collection; everything else in the deck is owned.
    import re
    assert not re.search(r"\d+ to buy", html), re.findall(r".{40}\d+ to buy", html)

def test_add_picker_accepts_an_unlisted_basic(env):
    r = env.client.post("/deck/basics/add", data={"name": "swamp", "section": "Basics"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["ok"] is True
    assert "\n22 Swamp\n" in _text(env)


def test_add_picker_accepts_snow_basics(env):
    r = env.client.post("/deck/basics/add", data={"name": "Snow-Covered Forest"})
    assert r.status_code == 200 and r.get_json()["card"] == "Snow-Covered Forest"


# --------------------------------------------------------------------------- #
# W9 — no line breaks into line-oriented files; quantities are digits
# --------------------------------------------------------------------------- #
def test_replace_with_an_injected_newline_is_refused(env):
    r = env.client.post("/deck/basics/card", data={
        "action": "replace", "name": "Sol Ring",
        "replacement": "Mindslicer\n1 Mindslicer\n# --- Commander ---\n1 Sol Ring"})
    assert r.status_code == 400
    assert _text(env) == DECK


def test_add_with_an_injected_newline_is_refused(env):
    r = env.client.post("/deck/basics/add", data={"name": "Island\n1 Mana Crypt"})
    assert r.status_code == 400
    assert _text(env) == DECK


def test_collection_add_refuses_injection_and_bad_quantities(env):
    adds = env.root / "owned_additions.txt"
    env.client.post("/collection/add", data={"name": "Fake Card\n99 Mana Crypt", "qty": "1"})
    for q in ("-5", "lots", "0", "100", "1e3", "٣"):
        env.client.post("/collection/add", data={"name": "Arcane Signet", "qty": q})
    assert not adds.exists() or "Mana Crypt" not in adds.read_text(encoding="utf-8")
    assert not adds.exists() or "Arcane Signet" not in adds.read_text(encoding="utf-8")
    env.client.post("/collection/add", data={"name": "Arcane Signet", "qty": "03"})
    assert adds.read_text(encoding="utf-8").splitlines()[-1] == "3 Arcane Signet"


def test_pin_routes_refuse_injected_newlines(env):
    r = env.client.post("/deck/basics/pin", data={"name": "Sol Ring\nbad,row"})
    assert r.status_code == 400
    r = env.client.post("/pins/move", data={"card": "Sol Ring", "deck": "x\ny", "json": "1"})
    assert r.status_code == 400
    assert not (env.root / "pins.csv").exists()


# --------------------------------------------------------------------------- #
# W10 — /refresh redirects to a local path only
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("referer,expected", [
    ("http://evil.example/phish.html", "/phish.html"),
    ("http://evil.example//evil.example/x", "/"),
    ("http://localhost/deck/basics?x=1", "/deck/basics"),
    (None, "/"),
])
def test_refresh_ignores_a_foreign_referer(env, monkeypatch, referer, expected):
    monkeypatch.setattr(env.app.subprocess, "run", lambda *a, **k: None)
    headers = {"Referer": referer} if referer else {}
    r = env.client.post("/refresh", headers=headers)
    assert r.status_code == 302
    assert r.headers["Location"] == expected


# --------------------------------------------------------------------------- #
# W11 — absurd quantities are refused fast; bad mulls is a 400
# --------------------------------------------------------------------------- #
def test_a_20_digit_quantity_is_detected(env):
    """Unit-level only, on purpose: before the fix this deck OOM-killed the whole
    pytest process through the route, which is no way for a regression to report."""
    bad = env.app._absurd_quantities("1 Sol Ring\n100000000000000000000 Swamp\n")
    assert bad == [(2, "100000000000000000000", "Swamp")]
    assert env.app._absurd_quantities(DECK) == []


@pytest.mark.parametrize("qty", ["10000"])
def test_absurd_quantity_is_refused_without_analysis(env, qty):
    (env.decks / "weird.txt").write_text(
        "# Title: X\n# Commander: Test Commander\n# --- Commander ---\n"
        f"1 Test Commander\n# --- Basics ---\n{qty} Swamp\n", encoding="utf-8")
    t = time.time()
    r = env.client.get("/deck/weird")
    assert r.status_code == 422 and b"Fix the quantity" in r.data
    r = env.client.get("/api/deck/weird/hand?seed=1")
    assert r.status_code == 422 and "error" in r.get_json()
    r = env.client.get("/")
    assert r.status_code == 200 and "quantity typo" in r.get_data(as_text=True)
    assert time.time() - t < 10
    # The editor stays reachable, so the player can fix the line.
    assert env.client.get("/deck/weird/edit").status_code == 200


def test_editor_refuses_to_save_an_absurd_quantity(env):
    r = env.client.post("/deck/basics/edit", data={"content": DECK + "5000 Island\n"})
    assert r.status_code == 400
    assert "5000 Island" in r.get_data(as_text=True), "the typed text must survive"
    assert _text(env) == DECK


def test_hand_with_non_numeric_mulls_is_a_400(env):
    r = env.client.get("/api/deck/basics/hand?mulls=abc")
    assert r.status_code == 400
    assert "error" in r.get_json()
