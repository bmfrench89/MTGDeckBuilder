"""UX refresh Wave 1.1: every edit can be undone (docs/spec-ux-refresh.md §4).

An undo never rewrites history. It is a new change row (`Source=manual-undo:<row>`)
that reverses an earlier one. What is pinned here:
- each one-tap edit, an Add, an editor save and a whole ⚡ run come back exactly;
- the result is the player's own choice, so the optimizer never churns it;
- the deck, not just the log, decides whether an undo is still possible;
- a stale page or a broken hand-written log row undoes nothing;
- the toast survives the panel's reload;
- an earlier stored version can be restored, and that restore can itself be undone.
Hermetic: every deck, log and database lives in tmp_path.
"""
import os

import pytest

import deckcore
import store

DECK = """\
# Title: Test Deck
# Commander: Test Commander
# Colors: W U

# --- Commander ---
1 Test Commander

# --- Ramp ---
1 Sol Ring
1 Arcane Signet

# --- Lands ---
10 Island
1 Command Tower
"""


@pytest.fixture
def env(tmp_path, monkeypatch, collection_file):
    import app as appmod
    import enrich_bg
    import sync
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "td.txt").write_text(DECK, encoding="utf-8")
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", collection_file)
    monkeypatch.setattr(appmod, "COLLECTION_CSV", str(tmp_path / "coll" / "collection.csv"))
    monkeypatch.setattr(appmod, "ADDITIONS", str(tmp_path / "owned_additions.txt"))
    monkeypatch.setattr(appmod, "PASSWORD", None)
    monkeypatch.setattr(deckcore, "PINS", str(tmp_path / "pins.csv"))
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    monkeypatch.setattr(enrich_bg, "start", lambda *a, **k: "enrichment started")
    appmod.app.config["TESTING"] = True

    class E:
        app = appmod
        client = appmod.app.test_client()
        dir = decks
        log = str(decks / "td.changes.csv")

    E.text = staticmethod(lambda: (decks / "td.txt").read_text(encoding="utf-8"))
    return E


def _flashes(env):
    with env.client.session_transaction() as s:
        return list(s.get("_flashes", []))


def _offer(env):
    toasts = [m for c, m in _flashes(env) if c == "undo"]
    assert toasts, "an Undo toast was offered"
    return toasts[-1]


def _undo(env, offer, **extra):
    return env.client.post("/deck/td/undo",
                           data={"rows": offer["rows"], "sig": offer["sig"], **extra})


def _write_log(env, rows):
    with open(env.log, "w", encoding="utf-8", newline="") as f:
        f.write("Card,Added,Replaced,Source\n" + "".join(r + "\n" for r in rows))


# --------------------------------------------------------------------------- #
# One-tap edits come back exactly
# --------------------------------------------------------------------------- #
def test_a_replace_is_undone_exactly_and_logged_as_the_players_choice(env):
    r = env.client.post("/deck/td/card", data={"action": "replace", "name": "Sol Ring",
                                               "replacement": "Counterspell"})
    assert r.status_code == 302
    offer = _offer(env)
    assert offer["text"] == "Replaced Sol Ring with Counterspell." and offer["label"] == "Undo"
    r = _undo(env, offer)
    assert r.status_code == 303
    assert env.text() == DECK, "the list reads exactly as it did"
    last = deckcore.change_rows(env.log)[-1]
    assert (last["card"], last["replaced"], last["source"]) == \
        ("Sol Ring", "Counterspell", "manual-undo:0")
    # The optimizer's own guard inputs: what came back is protected, what went out
    # is held, so a later ⚡ never swaps the undo back.
    assert "counterspell" in deckcore.manual_removals(env.log)
    assert "Sol Ring" in {a["name"] for a in deckcore.manual_adds(env.log, days=None)}


def test_a_remove_is_undone(env):
    env.client.post("/deck/td/card", data={"action": "remove", "name": "Arcane Signet"})
    assert "Arcane Signet" not in env.text()
    _undo(env, _offer(env))
    assert "1 Arcane Signet" in env.text()
    assert deckcore.change_rows(env.log)[-1]["source"] == "manual-undo:0"


def test_an_add_is_undone_and_the_section_it_opened_goes_with_it(env):
    j = env.client.post("/deck/td/add", data={"name": "Serra Angel", "section": ""}).get_json()
    assert j["ok"] and "# --- Creatures ---" in env.text()
    assert j["undo"]["text"] == "Added Serra Angel."
    r = env.client.post("/deck/td/undo", data={"rows": j["undo"]["rows"],
                                               "sig": j["undo"]["sig"]})
    assert r.status_code == 303
    assert env.text() == DECK, "the card and the Creatures header it opened are both gone"


def test_an_editor_save_is_undone(env):
    edited = DECK.replace("1 Sol Ring\n", "1 Serra Angel\n")
    env.client.post("/deck/td/edit", data={"content": edited})
    offer = _offer(env)
    assert offer["text"] == "List saved: 1 card in, 1 out."
    _undo(env, offer)
    text = env.text()
    assert "Serra Angel" not in text and "1 Sol Ring" in text


def test_a_whole_optimizer_run_is_one_undo(env, monkeypatch):
    """The ⚡ approval (spec-optimizer-judgment Phase B): the ticked swaps are applied
    as one run, and that run is ONE undo."""
    import optimize

    def run(path, coll, idx, decks_dir, chosen, by=""):
        assert sorted(chosen) == ["spell|Arcane Signet|Swords to Plowshares",
                                  "spell|Sol Ring|Counterspell"]
        text = open(path, encoding="utf-8").read()
        text = text.replace("1 Sol Ring", "1 Counterspell") \
                   .replace("1 Arcane Signet", "1 Swords to Plowshares")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        swaps = [("Sol Ring", 1, "Counterspell", 50, "free"),
                 ("Arcane Signet", 1, "Swords to Plowshares", 40, "share")]
        optimize.record_changes(path, swaps, [], by=by)
        return {"swaps": swaps, "land_swaps": []}
    monkeypatch.setattr(env.app.optimize, "apply_chosen", run)
    env.client.post("/deck/td/optimize",
                    data={"pick": ["spell|Sol Ring|Counterspell",
                                   "spell|Arcane Signet|Swords to Plowshares"]})
    offer = _offer(env)
    assert offer["label"] == "Undo all" and offer["rows"] == "0,1"
    _undo(env, offer)
    assert env.text() == DECK
    held = deckcore.manual_removals(env.log)
    assert {"counterspell", "swords to plowshares"} <= set(held)


def test_opening_optimize_proposes_and_writes_nothing(env, monkeypatch):
    """⚡ is a REVIEW: the page lists proposals with checkboxes and the deck file and
    its change log are untouched (player decision 2026-10-14, "propose, I approve")."""
    import optimize
    report = {"swaps": [("Sol Ring", 1, "Counterspell", 50, "free")],
              "swaps_detail": [{"cut": "Sol Ring", "add": "Counterspell", "cut_inc": 10,
                                "add_inc": 50, "cut_field_known": True,
                                "add_field_known": True}],
              "land_swaps": [], "field_size": 9}
    monkeypatch.setattr(env.app.optimize, "optimize", lambda *a, **k: report)
    before = env.text()
    page = env.client.get("/deck/td/optimize").get_data(as_text=True)
    assert 'name="pick" value="spell|Sol Ring|Counterspell"' in page
    assert "Nothing changes until you tick" in page
    assert env.text() == before
    import os
    assert not os.path.exists(env.log)


def test_the_review_lists_field_silent_reads_without_checkboxes(env, monkeypatch):
    """Phase C: owned cards EDHREC doesn't list appear as "Worth a read" — never as a
    tickable swap, because only a read (a session's, or the player's) can judge them."""
    report = {"swaps": [], "land_swaps": [], "field_size": 9,
              "reads": [{"name": "Samut, Hazoret's Champion", "fit": 81, "role": "creature"}]}
    monkeypatch.setattr(env.app.optimize, "optimize", lambda *a, **k: report)
    page = env.client.get("/deck/td/optimize").get_data(as_text=True)
    assert "Worth a read" in page and "Hazoret" in page
    assert 'name="pick"' not in page


def test_the_assess_packet_carries_the_proposals_for_a_claude_read(env, monkeypatch):
    report = {"swaps": [("Sol Ring", 1, "Counterspell", 50, "free")],
              "swaps_detail": [{"cut": "Sol Ring", "add": "Counterspell", "cut_inc": 10,
                                "add_inc": 50, "cut_field_known": True,
                                "add_field_known": True}],
              "land_swaps": [], "field_size": 9, "risers": [], "manual_holds": [],
              "reads": [{"name": "Silent Gem", "fit": 81, "role": "draw"}]}
    monkeypatch.setattr(env.app.optimize, "optimize", lambda *a, **k: report)
    text = env.client.get("/deck/td/assess.txt?raw=1").get_data(as_text=True)
    assert "FOR A CLAUDE READ" in text
    assert "[spell] Sol Ring (10%) -> Counterspell (50%; a free copy)" in text
    assert "Silent Gem (fit 81, draw, not on EDHREC's list)" in text
    assert "Field % and lift are evidence, not the verdict" in text
    assert "1x = generic" in text, "the packet says what lift means"


def test_applying_with_nothing_ticked_changes_nothing(env, monkeypatch):
    import optimize
    called = []
    monkeypatch.setattr(env.app.optimize, "apply_chosen",
                        lambda *a, **k: called.append(1) or {})
    before = env.text()
    r = env.client.post("/deck/td/optimize", data={})
    assert r.status_code == 302 and r.headers["Location"].endswith("/deck/td/optimize")
    assert not called and env.text() == before


def test_the_changes_page_offers_undo_per_row_and_per_run(env, monkeypatch):
    _write_log(env, ["Counterspell,2026-10-14,Sol Ring,free",
                     "Swords to Plowshares,2026-10-14,Arcane Signet,share"])
    (env.dir / "td.txt").write_text(
        DECK.replace("1 Sol Ring", "1 Counterspell")
            .replace("1 Arcane Signet", "1 Swords to Plowshares"), encoding="utf-8")
    html = env.client.get("/deck/td/changes").get_data(as_text=True)
    assert "Undo all 2" in html
    assert 'aria-label="Undo: Counterspell replacing Sol Ring"' in html
    rows = deckcore.change_rows(env.log)
    r = env.client.post("/deck/td/undo", data={"rows": "0,1", "sig": deckcore.change_sig(rows),
                                               "next": "changes"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/deck/td/changes")
    html = env.client.get("/deck/td/changes").get_data(as_text=True)
    assert html.count(">Undone<") == 2
    assert 'aria-label="Redo: Sol Ring replacing Counterspell"' in html
    assert "Undo all" not in html


def test_an_undo_can_be_redone(env):
    env.client.post("/deck/td/card", data={"action": "replace", "name": "Sol Ring",
                                           "replacement": "Counterspell"})
    _undo(env, _offer(env))
    redo = _offer(env)
    assert redo["label"] == "Redo"
    _undo(env, redo)
    assert "1 Counterspell" in env.text() and "Sol Ring" not in env.text()


# --------------------------------------------------------------------------- #
# The deck, not just the log, decides
# --------------------------------------------------------------------------- #
def test_the_same_undo_twice_does_nothing_the_second_time(env):
    env.client.post("/deck/td/card", data={"action": "replace", "name": "Sol Ring",
                                           "replacement": "Counterspell"})
    offer = _offer(env)
    _undo(env, offer)
    after = env.text()
    _flashes(env)
    rows = deckcore.change_rows(env.log)
    r = env.client.post("/deck/td/undo", data={"rows": "0", "sig": deckcore.change_sig(rows[:1])})
    assert r.status_code == 303 and env.text() == after
    assert any("already undone" in m for c, m in _flashes(env) if c == "warn")


def test_a_card_that_has_since_left_is_not_put_back_twice(env):
    _write_log(env, ["Counterspell,2026-10-14,Sol Ring,manual-replace"])
    rows = deckcore.change_rows(env.log)
    r = env.client.post("/deck/td/undo", data={"rows": "0", "sig": deckcore.change_sig(rows)})
    assert r.status_code == 303 and env.text() == DECK
    warn = " ".join(m for c, m in _flashes(env) if c == "warn")
    assert "Counterspell has since left the deck" in warn


def test_an_undo_never_takes_out_the_commander(env):
    _write_log(env, ["Test Commander,2026-10-14,,manual-add"])
    rows = deckcore.change_rows(env.log)
    env.client.post("/deck/td/undo", data={"rows": "0", "sig": deckcore.change_sig(rows)})
    assert env.text() == DECK
    assert any("commander" in m for c, m in _flashes(env) if c == "warn")


def test_an_undo_never_brings_back_an_off_colour_card(env):
    _write_log(env, [",2026-10-14,Llanowar Elves,manual-remove"])
    rows = deckcore.change_rows(env.log)
    env.client.post("/deck/td/undo", data={"rows": "0", "sig": deckcore.change_sig(rows)})
    assert env.text() == DECK
    assert any("outside this deck's colours" in m for c, m in _flashes(env) if c == "warn")


def test_a_stale_page_undoes_nothing(env):
    env.client.post("/deck/td/card", data={"action": "replace", "name": "Sol Ring",
                                           "replacement": "Counterspell"})
    offer = dict(_offer(env), sig="0" * 12)
    before = env.text()
    r = _undo(env, offer)
    assert r.status_code == 303 and r.headers["Location"].endswith("/deck/td/changes")
    assert env.text() == before
    assert any("moved on" in m for c, m in _flashes(env) if c == "warn")


def test_a_broken_hand_written_row_is_never_acted_on(env):
    # An unquoted comma, as a session once wrote by hand: the row parses as
    # Replaced="Selvala", and undoing it would add half a card name to the deck.
    (env.dir / "td.txt").write_text(DECK.replace("1 Sol Ring", "1 Canopy Vista"),
                                    encoding="utf-8")
    _write_log(env, ["Canopy Vista,2026-08-14,Selvala, Heart of the Wilds,manual-replace"])
    rows = deckcore.change_rows(env.log)
    assert rows[0]["ok"] is False
    html = env.client.get("/deck/td/changes").get_data(as_text=True)
    assert "aria-label=\"Undo:" not in html
    before = env.text()
    env.client.post("/deck/td/undo", data={"rows": "0", "sig": deckcore.change_sig(rows)})
    assert env.text() == before and "Selvala" not in env.text()


def test_a_returning_card_files_where_the_deck_files_it(env):
    # The deck's own attrs outrank the collection, exactly as deck_sections files:
    # a UAT undo once put The Warring Triad under Creatures (collection) when the
    # deck files it under Artifacts (its attrs), and CI would have called it misfiled.
    (env.dir / "td.attrs.csv").write_text("Name,Type,MV,Colors\nSerra Angel,Artifact,5,W\n",
                                          encoding="utf-8")
    (env.dir / "td.txt").write_text(
        DECK.replace("# --- Lands ---", "# --- Artifacts ---\n1 Mind Stone\n\n"
                                        "# --- Instants ---\n1 Counterspell\n\n# --- Lands ---"),
        encoding="utf-8")
    _write_log(env, ["Counterspell,2026-10-14,Serra Angel,free"])
    rows = deckcore.change_rows(env.log)
    env.client.post("/deck/td/undo", data={"rows": "0", "sig": deckcore.change_sig(rows)})
    text = env.text()
    assert "Counterspell" not in text
    assert "# --- Artifacts ---\n1 Mind Stone\n1 Serra Angel\n" in text, \
        "filed under Artifacts, as the deck's attrs say"
    assert "# --- Creatures ---" not in text
    assert "# --- Instants ---" not in text, "the section the undo emptied is gone"


def test_a_row_short_only_of_its_by_cell_is_still_whole(env):
    with open(env.log, "w", encoding="utf-8", newline="") as f:
        f.write("Card,Added,Replaced,Source,By\n"
                "Counterspell,2026-10-14,Sol Ring,manual-replace\n"      # no By cell
                "Swords to Plowshares,2026-10-14,Arcane Signet,free,Sam,extra\n")
    rows = deckcore.change_rows(env.log)
    assert [r["ok"] for r in rows] == [True, False]


def test_undone_rows_follow_redo_chains():
    rows = [{"i": 0, "undoes": None}, {"i": 1, "undoes": 0}, {"i": 2, "undoes": 1},
            {"i": 3, "undoes": 2}]
    assert deckcore.undone_rows(rows[:2]) == {0}
    assert deckcore.undone_rows(rows[:3]) == {1}, "a redo puts row 0 back in force"
    assert deckcore.undone_rows(rows) == {0, 2}


# --------------------------------------------------------------------------- #
# The toast
# --------------------------------------------------------------------------- #
def test_the_toast_shows_on_the_deck_page_and_on_app_pages(env):
    env.client.post("/deck/td/card", data={"action": "replace", "name": "Sol Ring",
                                           "replacement": "Counterspell"})
    html = env.client.get("/deck/td").get_data(as_text=True)
    assert "data-utoast" in html and "Replaced Sol Ring with Counterspell." in html
    assert 'action="/deck/td/undo"' in html and 'role="status"' in html
    rows = deckcore.change_rows(env.log)
    env.client.post("/deck/td/undo", data={"rows": "0", "sig": deckcore.change_sig(rows),
                                           "next": "changes"})
    html = env.client.get("/deck/td/changes").get_data(as_text=True)
    assert "data-utoast" in html and ">Redo<" in html
    assert "{&#39;text&#39;" not in html and "{'text'" not in html, "never a raw dict"


def test_the_panel_keeps_the_toast_for_its_reload():
    # A followed redirect renders the deck page inside the fetch and spends the
    # flashed toast before the reload that should show it.
    src = open(os.path.join(os.path.dirname(__file__), "..", "scripts", "assets",
                            "card_panel.html"), encoding="utf-8").read()
    assert "/card',{method:'POST',body:f,redirect:'manual'}" in src
    assert "opaqueredirect" in src


# --------------------------------------------------------------------------- #
# Earlier versions (database mode)
# --------------------------------------------------------------------------- #
@pytest.fixture
def dbenv(env, tmp_path, monkeypatch):
    coll = tmp_path / "coll"
    coll.mkdir(exist_ok=True)
    (coll / "collection.csv").write_text(
        "Quantity,Name,Types,Identities\n1,Sol Ring,Artifact,\n1,Counterspell,Instant,U\n"
        "1,Arcane Signet,Artifact,\n1,Test Commander,Legendary Creature,W U\n",
        encoding="utf-8")
    db = str(coll / "collection.db")
    store.seed(db, str(coll / "collection.csv"), None, str(tmp_path / "adds.txt"),
               str(env.dir), write=True)
    monkeypatch.setattr(env.app, "COLLECTION", db)
    monkeypatch.setattr(env.app, "COLLECTION_DB", db)
    store.capture(db, str(env.dir), None, action="seed")
    env.db = db
    return env


def test_an_earlier_version_is_restored_and_the_restore_can_be_undone(dbenv):
    env = dbenv
    env.client.post("/deck/td/card", data={"action": "replace", "name": "Sol Ring",
                                           "replacement": "Counterspell"})
    _flashes(env)
    hist = store.file_history(env.db, "decks/td.txt")
    first = hist[0]["id"]
    html = env.client.get("/deck/td/changes").get_data(as_text=True)
    assert "Earlier versions" in html and "The list now" in html
    assert f'name="rev" value="{first}"' in html
    r = env.client.post("/deck/td/restore", data={"rev": first})
    assert r.status_code == 303
    assert env.text() == DECK
    offer = _offer(env)
    assert offer["text"].startswith("Restored the list from") and "1 in, 1 out" in offer["text"]
    _undo(env, offer)
    assert "1 Counterspell" in env.text() and "Sol Ring" not in env.text()


def test_restore_is_refused_on_files_and_for_unknown_versions(env):
    r = env.client.post("/deck/td/restore", data={"rev": "1"})
    assert r.status_code == 303 and env.text() == DECK
    assert any("database" in m for c, m in _flashes(env) if c == "warn")
    html = env.client.get("/deck/td/changes").get_data(as_text=True)
    assert 'id="versions"' not in html, "no versions list without the database"
