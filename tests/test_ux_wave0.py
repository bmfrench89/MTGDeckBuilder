"""UX refresh Wave 0 — "stop the damage" (docs/spec-ux-refresh.md §3).

The 2026-10-14 audit ran the app's edit flows end to end and found ones that silently
damaged decks or misstated facts: a one-tap Replace put an off-colour card in a deck,
"+ Add card" filed a card under Commander, the ⚡ report vanished with its errors
swallowed, `hidden` lost to a component rule, the table card showed raw markdown, an
unknown price read "$0.00", and nothing was compressed. Each is pinned here.
Hermetic: every deck and collection lives in tmp_path.
"""
import gzip
import os

import pytest

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
    monkeypatch.setattr(appmod, "PASSWORD", None)
    monkeypatch.setattr(deckcore, "PINS", str(tmp_path / "pins.csv"))
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    monkeypatch.setattr(enrich_bg, "start", lambda *a, **k: "enrichment started")
    appmod.app.config["TESTING"] = True

    class E:
        app = appmod
        client = appmod.app.test_client()
        dir = decks
        root = tmp_path

    E.text = staticmethod(lambda: (decks / "td.txt").read_text(encoding="utf-8"))
    return E


# --------------------------------------------------------------------------- #
# 0.1 · Replace is validated
# --------------------------------------------------------------------------- #
def test_replace_refuses_an_off_colour_card(env):
    before = env.text()
    r = env.client.post("/deck/td/card", data={"action": "replace", "name": "Sol Ring",
                                               "replacement": "Llanowar Elves"})
    assert r.status_code == 409 and "color identity" in r.get_data(as_text=True)
    assert env.text() == before, "a refused swap writes nothing"


def test_an_in_colour_replace_still_goes_through(env):
    r = env.client.post("/deck/td/card", data={"action": "replace", "name": "Sol Ring",
                                               "replacement": "Counterspell"})
    assert r.status_code == 302
    assert "Counterspell" in env.text() and "Sol Ring" not in env.text()


@pytest.mark.parametrize("data", [{"action": "remove"},
                                  {"action": "replace", "replacement": "Counterspell"}])
def test_the_commander_is_not_changed_from_a_one_tap_sheet(env, data):
    before = env.text()
    r = env.client.post("/deck/td/card", data={"name": "Test Commander", **data})
    assert r.status_code == 409 and "commander" in r.get_data(as_text=True)
    assert env.text() == before


def test_the_replace_search_offers_only_in_colour_cards(env):
    loose = env.client.get("/api/collection/search?q=an&deck=td").get_json()
    strict = env.client.get("/api/collection/search?q=an&deck=td&strict=1").get_json()
    assert {"name": "Llanowar Elves", "qty": 1, "legal": False} in loose
    assert "Llanowar Elves" not in {x["name"] for x in strict}
    assert all(x["legal"] for x in strict)


# --------------------------------------------------------------------------- #
# 0.2 · Add files by type, and says when the deck leaves 100
# --------------------------------------------------------------------------- #
def test_add_with_no_section_files_the_card_under_its_type(env):
    j = env.client.post("/deck/td/add", data={"name": "Serra Angel", "section": ""}).get_json()
    assert j["ok"] and j["section"] == "Creatures"
    text = env.text()
    assert "# --- Creatures ---\n1 Serra Angel" in text
    assert text.index("# --- Creatures ---") < text.index("# --- Lands ---"), \
        "a new type section opens where the convention puts it"
    assert "This deck now has 15 cards" in j["size_note"]


def test_a_picked_section_is_still_honoured(env):
    env.client.post("/deck/td/add", data={"name": "Serra Angel", "section": "Ramp"})
    text = env.text()
    assert text.index("1 Serra Angel") < text.index("# --- Lands ---")
    assert "# --- Creatures ---" not in text


def test_an_untyped_card_goes_to_unsorted_never_commander(env, tmp_path, monkeypatch):
    import deck_sections
    coll = tmp_path / "untyped.csv"
    coll.write_text("Quantity,Name,Types\n1,Test Commander,Legendary Creature\n"
                    "1,Mystery Card,\n", encoding="utf-8")
    monkeypatch.setattr(env.app, "COLLECTION", str(coll))
    j = env.client.post("/deck/td/add", data={"name": "Mystery Card"}).get_json()
    assert j["ok"] and j["section"] == deck_sections.UNSORTED
    text = env.text()
    assert f"# --- {deck_sections.UNSORTED} ---\n1 Mystery Card" in text
    commander_block = text.split("# --- Commander ---")[1].split("# ---")[0]
    assert "Mystery Card" not in commander_block


def test_the_size_note(env, tmp_path):
    p = tmp_path / "hundred.txt"
    p.write_text("# --- Commander ---\n1 Test Commander\n# --- Basics ---\n99 Island\n",
                 encoding="utf-8")
    assert env.app._deck_size_note(str(p)) is None
    p.write_text("# --- Commander ---\n1 Test Commander\n# --- Basics ---\n100 Island\n",
                 encoding="utf-8")
    assert "101 cards" in env.app._deck_size_note(str(p))


def test_a_remove_that_leaves_the_deck_short_says_so_on_the_deck_page(env):
    r = env.client.post("/deck/td/card", data={"action": "remove", "name": "Sol Ring"},
                        follow_redirects=True)
    assert "This deck now has 13 cards" in r.get_data(as_text=True)


# --------------------------------------------------------------------------- #
# 0.3 · The ⚡ report reaches the player
# --------------------------------------------------------------------------- #
def test_flash_messages_reach_the_generated_deck_page(env):
    with env.client.session_transaction() as s:
        s["_flashes"] = [("info", "Optimizer: <b>2</b> change(s) applied")]
    html = env.client.get("/deck/td").get_data(as_text=True)
    assert 'class="appflashes"' in html
    assert "Optimizer: &lt;b&gt;2&lt;/b&gt; change(s) applied" in html, "escaped, never raw"


def test_a_failing_optimize_is_reported_not_swallowed(env, monkeypatch):
    import optimize

    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(optimize, "optimize", boom)
    html = env.client.post("/deck/td/optimize", follow_redirects=True).get_data(as_text=True)
    assert "Optimize stopped with an error (RuntimeError)" in html


def test_the_optimize_report_names_its_swaps(env):
    from flask import get_flashed_messages
    with env.app.app.test_request_context():
        env.app._flash_optimize({"swaps": [("Out A", 10, "In A", 55, "free")],
                                 "land_swaps": [("Out Land", "In Land", "free")],
                                 "role_deadlock": {"out_of_band": [], "blocked": []}})
        msgs = get_flashed_messages()
    assert any("Out A → In A" in m and "Out Land → In Land" in m for m in msgs)


# --------------------------------------------------------------------------- #
# 0.4 · `hidden` always hides; Assess and the table card get the real clock
# --------------------------------------------------------------------------- #
def test_hidden_always_wins_on_both_surfaces():
    import build_dashboard as bd
    rule = "[hidden] { display: none !important; }"
    assert rule in bd._asset("tokens.css"), "tokens.css is inlined into every dashboard"


def test_assess_and_the_table_card_analyse_with_the_collection_path(env, monkeypatch):
    import deckcore
    seen, real = [], deckcore.analyze_deck

    def spy(path, coll, *a, **k):
        seen.append(coll)
        return real(path, coll, *a, **k)
    monkeypatch.setattr(deckcore, "analyze_deck", spy)
    assert env.client.get("/deck/td/assess").status_code == 200
    assert env.client.get("/deck/td/table-card").status_code == 200
    assert seen and all(isinstance(c, str) for c in seen), \
        "a loaded list has no goldfish clock: 'Speed unmeasured' beside 'combat T9'"


# --------------------------------------------------------------------------- #
# 0.5 · One markdown-lite reader for the Plan tab and the table card
# --------------------------------------------------------------------------- #
NOTES = """\
# The Plan

Five-color **dragons** that ramp
early, then *win* in combat.

- Ramp with rocks
  and dorks
- Protect the commander
<!-- a note to self -->
"""


def test_notes_blocks_join_wrapped_lines():
    import deckcore
    assert deckcore.notes_blocks(NOTES) == [
        ("h", "The Plan"),
        ("p", "Five-color **dragons** that ramp early, then *win* in combat."),
        ("li", "Ramp with rocks and dorks"), ("li", "Protect the commander")]
    assert deckcore.notes_inline_html("a <b> & **bold** *it* snake_case_name 2*3*4") == \
        "a &lt;b&gt; &amp; <b>bold</b> <i>it</i> snake_case_name 2*3*4"


def test_the_table_card_shows_no_raw_markdown(env):
    (env.dir / "td.notes.md").write_text(NOTES, encoding="utf-8")
    html = env.client.get("/deck/td/table-card").get_data(as_text=True)
    assert "<b>dragons</b>" in html and "<i>win</i>" in html and "**" not in html
    assert "<li>The Plan" not in html, "a heading is a title, not a point"
    assert "<li>Ramp with rocks and dorks</li>" in html, "one sentence, one bullet"


def test_the_plan_tab_reads_the_same_way():
    import build_dashboard as bd
    out = bd.notes_html(NOTES)
    assert out.count("<p>") == 1 and "<i>win</i>" in out and "**" not in out
    assert "<li>Ramp with rocks and dorks</li>" in out and "note to self" not in out


# --------------------------------------------------------------------------- #
# 0.6 · Wishlist ticks work; unknown prices say unknown
# --------------------------------------------------------------------------- #
def test_unknown_prices_say_unknown_never_zero(env):
    (env.dir / "td.buylist.csv").write_text(
        "Card,Price,Tier,Replaces,Reason\nMana Crypt,,1,Sol Ring,fast mana\n", encoding="utf-8")
    html = env.client.get("/wishlist").get_data(as_text=True)
    assert "prices unknown" in html and "~$0.00" not in html


def test_wishlist_ticks_are_labelled_and_remembered(env):
    (env.dir / "td.buylist.csv").write_text(
        "Card,Price,Tier,Replaces,Reason\nMana Crypt,120,1,Sol Ring,fast mana\n",
        encoding="utf-8")
    html = env.client.get("/wishlist").get_data(as_text=True)
    assert 'aria-label="Got Mana Crypt"' in html and "localStorage" in html
    assert "not saved" not in html


# --------------------------------------------------------------------------- #
# 0.7 · Words for people: titles not file names, no repo paths, plain verbs
# --------------------------------------------------------------------------- #
def test_deck_titles_replace_file_names(env):
    (env.dir / "td.buylist.csv").write_text(
        "Card,Price,Tier,Replaces,Reason\nMana Crypt,120,1,Sol Ring,fast mana\n",
        encoding="utf-8")
    html = env.client.get("/wishlist").get_data(as_text=True)
    assert '<a href="/deck/td">Test Deck</a>' in html
    j = env.client.get("/api/card/Sol Ring").get_json()
    assert j["deck_titles"] == {"td": "Test Deck"}


def test_change_sources_and_activity_verbs_read_plainly(env):
    (env.dir / "td.changes.csv").write_text(
        "Card,Added,Replaced,Source\nCounterspell,2026-10-14,Sol Ring,manual-replace\n"
        "Swords to Plowshares,2026-10-13,Arcane Signet,free\n", encoding="utf-8")
    html = env.client.get("/deck/td/changes").get_data(as_text=True)
    assert "swapped in by hand" in html and "optimizer swap" in html
    assert "manual-replace" not in html
    assert env.app._activity_verb_filter("set bracket") == "set the bracket"
    assert env.app._activity_verb_filter("something new") == "something new"


def test_no_local_pc_wording_left_for_players(env):
    html = env.client.get("/").get_data(as_text=True)
    assert "your machine" not in html and "Git keeps the history" not in html
    assert "every change is revertable" not in html, "no promise of an undo that isn't built"
    sw = env.client.get("/sw.js").get_data(as_text=True)
    assert "run.bat" not in sw and "PC is awake" not in sw
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for t in ("batch_preview.html", "collection.html", "assess.html", "build_deck.html"):
        src = open(os.path.join(here, "webapp", "templates", t), encoding="utf-8").read()
        for word in ("owned_additions.txt", "enrich.bat", "data/decks/", "commanders.csv"):
            assert word not in src, f"{t} still tells the player about {word}"


# --------------------------------------------------------------------------- #
# 0.8 · Text responses are compressed
# --------------------------------------------------------------------------- #
def test_pages_are_gzipped_when_the_browser_accepts_it(env):
    r = env.client.get("/", headers={"Accept-Encoding": "gzip, br"})
    assert r.headers.get("Content-Encoding") == "gzip"
    assert "Accept-Encoding" in r.headers.get("Vary", "")
    body = gzip.decompress(r.get_data())
    assert body.lstrip().lower().startswith(b"<!doctype html")
    plain = env.client.get("/")
    assert "Content-Encoding" not in plain.headers and plain.get_data() == body


def test_small_and_file_responses_are_left_alone(env):
    tiny = env.client.get("/health", headers={"Accept-Encoding": "gzip"})
    assert "Content-Encoding" not in tiny.headers
    css = env.client.get("/static/app.css", headers={"Accept-Encoding": "gzip"})
    assert css.status_code == 200 and "Content-Encoding" not in css.headers
    head = env.client.head("/", headers={"Accept-Encoding": "gzip"})
    assert "Content-Encoding" not in head.headers


def test_tables_quotes_and_strikethrough_render():
    import build_dashboard as bd
    import deckcore
    text = ("| Card | MV |\n|---|---|\n| Angelic Renewal | 2 |\n\n"
            "> Beorn the Fierce — {3}{G}{G}\n> Trample.\n\nOld ~~plan~~ new plan.\n")
    assert deckcore.notes_blocks(text) == [
        ("table", [["Card", "MV"], ["Angelic Renewal", "2"]]),
        ("quote", "Beorn the Fierce — {3}{G}{G} Trample."), ("p", "Old ~~plan~~ new plan.")]
    out = bd.notes_html(text)
    assert "<th>Card</th>" in out and "<td>Angelic Renewal</td>" in out and "|" not in out
    assert "<blockquote class='notes'>" in out and "<s>plan</s>" in out


def test_a_trimmed_table_card_point_never_leaves_a_marker_open(env):
    long = ("The deck runs a **free, unlimited sacrifice outlet that starts in the command "
            "zone and never stops, turn after turn after turn, for as long as the game "
            "lasts, which is usually a long time indeed in a four-player pod** and wins.")
    out = env.app._brief(long, 80)
    assert out.endswith("…") and "**" not in out
    assert env.app._brief("short and **bold**") == "short and **bold**"
