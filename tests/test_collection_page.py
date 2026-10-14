"""The Collection page: Cards / Add / Manage sub-tabs over one search language
(docs/spec-collection-rebuild.md §4).

The 2026-10-14 audit found the first card 3.9 screens down under six blocks of admin,
a name-only search, "in a deck" counting study lists, and every filter lost on Back.
These tests pin the rebuilt page's contract:
- each tab carries only its own job;
- the scope chip ANDs the whole typed query, an OR group included;
- study copies are never "in a deck";
- paging never repeats a group header and the URL keeps the depth;
- the Filters sheet composes terms, and reads them back without dropping any;
- every POST lands on the tab its form lives on.
How it behaves in a browser is webapp/uat/flows.js F13 and F14. Hermetic: tmp_path only.
"""
import re

import pytest

import collection_query as cq

CSV_HEAD = ("Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,"
            "Super-types,Rarity\n")
CARDS = """\
1,Sol Ring,1,,,{1},Artifact,,,uncommon
2,Arcane Signet,2,,,{2},Artifact,,,common
1,Counterspell,2,U,U,{U}{U},Instant,,,common
1,Llanowar Elves,1,G,G,{G},Creature,Elf Druid,,common
1,Cultivate,3,G,G,{2}{G},Sorcery,,,common
1,Old Gnawbone,7,G,G,{5}{G}{G},Creature,Dragon,Legendary,mythic
1,Thundermaw Hellkite,5,R,R,{3}{R}{R},Creature,Dragon,,mythic
12,Forest,0,,G,,Land,Forest,Basic,common
"""
REAL = ("# Title: Real Deck\n# Commander: Old Gnawbone\n# Colors: G\n"
        "# --- Commander ---\n1 Old Gnawbone\n# --- Artifacts ---\n1 Sol Ring\n"
        "# --- Lands ---\n30 Forest\n")
STUDY = ("# Title: Study list\n# Study: yes\n# Colors: U\n"
         "# --- Instants ---\n1 Counterspell\n")


@pytest.fixture
def env(tmp_path, monkeypatch):
    import app as appmod
    import deckcore
    import sync
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "real.txt").write_text(REAL, encoding="utf-8")
    (decks / "study.txt").write_text(STUDY, encoding="utf-8")
    coll_dir = tmp_path / "data" / "collection"
    coll_dir.mkdir(parents=True)
    csv_path = coll_dir / "collection.csv"
    csv_path.write_text(CSV_HEAD + CARDS, encoding="utf-8")
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", str(csv_path))
    monkeypatch.setattr(appmod, "COLLECTION_CSV", str(csv_path))
    monkeypatch.setattr(appmod, "COLLECTION_ATTRS", str(coll_dir / "collection_attrs.csv"))
    monkeypatch.setattr(appmod, "ADDITIONS", str(coll_dir / "owned_additions.txt"))
    monkeypatch.setattr(appmod, "PASSWORD", None)
    monkeypatch.setattr(deckcore, "PINS", str(coll_dir / "pins.csv"))
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    appmod.app.config["TESTING"] = True

    class E:
        app = appmod
        client = appmod.app.test_client()
    E.decks, E.csv = decks, csv_path
    return E


def page(env, url):
    r = env.client.get(url)
    assert r.status_code == 200, (url, r.status_code)
    return r.get_data(as_text=True)


def rows(html):
    return re.findall(r'<li class="coll-row" data-card="([^"]+)"', html)


def summary(html):
    return re.search(r'<p class="coll-summary" id="collSummary">(.*?)</p>', html, re.S).group(1)


def test_cards_tab_leads_with_the_search_and_the_cards(env):
    html = page(env, "/collection")
    assert '<nav class="subtabs" aria-label="Collection">' in html
    assert re.search(r'aria-current="page">Cards</a>', html)
    assert html.index('id="collQ"') < html.index('class="coll-row"'), "search, then cards"
    for admin in ("Add a batch of new cards", "Change a card", "Card DB:", "Merge an export",
                  "Most valuable cards"):
        assert admin not in html, f"{admin!r} belongs on Add or Manage now"
    assert len(rows(html)) == 8 and summary(html).startswith("All 8 cards")
    assert "<script src=\"/static/collection.js?v=" in html


def test_add_and_manage_tabs_hold_the_admin(env):
    add = page(env, "/collection/add")
    assert re.search(r'aria-current="page">Add</a>', add)
    assert "Add a batch of new cards" in add and 'id="arrivals"' in add
    assert 'class="coll-row"' not in add
    manage = page(env, "/collection/manage")
    assert re.search(r'aria-current="page">Manage', manage)
    assert "Card DB:" in manage and "Add a batch of new cards" not in manage


def test_a_scope_ands_the_whole_query_or_group_included(env):
    # "(a or b) free>0", never "a or (b free>0)": Old Gnawbone is sleeved, so Free
    # must drop it even though it sits in the first half of the OR.
    html = page(env, "/collection?q=t:dragon+or+t:sorcery&scope=free")
    assert sorted(rows(html)) == ["Cultivate", "Thundermaw Hellkite"]
    assert "free copies &gt; 0" in summary(html)
    assert 'aria-current="true">Free</a>' in html


def test_in_decks_never_counts_a_study_copy(env):
    assert sorted(rows(page(env, "/collection?scope=indeck"))) == ["Forest", "Old Gnawbone",
                                                                  "Sol Ring"]
    assert "Counterspell" in rows(page(env, "/collection?scope=nodeck"))
    assert rows(page(env, "/collection?q=deck:study")) == ["Counterspell"]


def test_chips_remove_their_own_term_and_keep_the_scope(env):
    html = page(env, "/collection?q=t:creature+mv%3E%3D5&scope=free")
    links = re.findall(r'<a class="qchip" href="([^"]+)"', html)
    assert len(links) == 2
    assert "scope=free" in links[0] and "mv" in links[0] and "creature" not in links[0]


def test_paging_keeps_its_place_and_never_repeats_a_header(env):
    many = "".join(f"1,Test Card {i:03d},{i % 7},,,{{{i % 7}}},Artifact,,,common\n"
                   for i in range(230))
    env.csv.write_text(CSV_HEAD + CARDS + many, encoding="utf-8")
    html = page(env, "/collection")
    assert len(rows(html)) == 100
    assert "Showing 100 of 238" in html
    more = re.search(r'id="collMore" href="([^"]+)" data-rows="([^"]+)"', html)
    assert "n=200" in more.group(1) and "offset=100" in more.group(2)
    j = env.client.get(more.group(2).replace("&amp;", "&")).get_json()
    assert j["shown"] == 200 and j["more"] and "n=200" in j["url"]
    assert len(rows(j["html"])) == 100
    assert len(rows(page(env, "/collection?n=200"))) == 200, "Back lands at the same depth"
    # Grouped by mana value, a page boundary inside a group repeats no header.
    first = page(env, "/collection?group=mv&order=name")
    nxt = env.client.get("/collection/rows?group=mv&order=name&offset=100").get_json()
    head = lambda h: re.findall(r'<li class="coll-grp"><h3>([^<]+)<', h)
    assert not set(head(nxt["html"])) & set(head(first)[-1:]), "the group continues"


def test_the_filter_sheet_composes_terms_onto_what_it_cannot_show(env):
    r = env.client.get("/collection?apply=1&q_rest=-t:land&fi_c=G&fi_c=U&fi_cm=has"
                       "&fi_role=ramp&fi_role=draw&fi_mv_lo=1&scope=free")
    assert r.status_code == 302
    loc = r.headers["Location"]
    q = re.search(r"q=([^&]+)", loc).group(1)
    from urllib.parse import unquote_plus
    assert unquote_plus(q) == "-t:land id>=ug (role:ramp or role:draw) mv>=1"  # WUBRG order
    assert "scope=free" in loc
    # Reading it back: the sheet shows what it composed and carries the rest verbatim.
    html = page(env, loc.split("localhost", 1)[-1])
    assert 'name="q_rest" value="-t:land"' in html
    for field in ('name="fi_c" value="G" checked', 'name="fi_c" value="U" checked',
                  'name="fi_cm" value="has" checked', 'name="fi_role" value="ramp" checked',
                  'name="fi_role" value="draw" checked', 'name="fi_mv_lo" value="1"'):
        assert field in html, field


def test_an_or_rest_is_wrapped_before_the_sheet_adds_to_it(env):
    r = env.client.get("/collection?apply=1&q_rest=t:dragon+or+t:sorcery&fi_c=G")
    from urllib.parse import unquote_plus
    assert unquote_plus(re.search(r"q=([^&]+)", r.headers["Location"]).group(1)) == \
        "(t:dragon or t:sorcery) id<=g"


def test_the_live_count_is_what_show_would_give(env):
    j = env.client.get("/api/collection/count?fi_c=G&fi_role=ramp&scope=free").get_json()
    shown = rows(page(env, "/collection?q=id%3C%3Dg+role:ramp&scope=free"))
    assert j["n"] == len(shown) and j["q"] == "id<=g role:ramp"


def test_live_results_are_the_page_partial(env):
    j = env.client.get("/collection/results?q=ur+dragon").get_json()
    assert set(j) >= {"html", "status", "url"}
    assert j["status"].startswith("0 cards") and "No cards match" in j["html"]
    j = env.client.get("/collection/results?q=gnaw").get_json()
    assert rows(j["html"]) == ["Old Gnawbone"] and j["url"].endswith("q=gnaw")


def test_no_match_explains_and_suggests(env):
    html = page(env, "/collection?q=sol+rign")
    assert "No cards match" in html and "Did you mean" in html and "Sol Ring" in html
    assert "https://scryfall.com/search?q=sol%20rign" in html
    html = page(env, "/collection?q=rol:ramp")
    assert "isn&#39;t a keyword this search knows" in html and "Did you mean role:?" in html


def test_the_help_sheet_lists_every_keyword(env):
    html = page(env, "/collection")
    sheet = html[html.index('id="collHelp"'):]
    for row in cq.help_rows():
        first = row["names"][0]
        assert (f"<code>{first}:</code>" in sheet) or (first == "name" and "<code>words</code>" in sheet), first


def test_posts_land_on_the_tab_their_form_lives_on(env):
    r = env.client.post("/collection/add", data={"name": "Sol Ring", "qty": "1"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/collection/add")
    r = env.client.post("/collection/reconcile", data={"action": "keep"})
    assert r.headers["Location"].endswith("/collection/manage")
    r = env.client.post("/collection/batch", data={"text": ""})
    assert r.headers["Location"].endswith("/collection/add")


def test_records_follow_a_deck_edit(env):
    assert "Llanowar Elves" not in rows(page(env, "/collection?scope=indeck"))
    (env.decks / "real.txt").write_text(REAL + "# --- Creatures ---\n1 Llanowar Elves\n",
                                        encoding="utf-8")
    assert "Llanowar Elves" in rows(page(env, "/collection?scope=indeck"))


def test_a_basic_is_never_short_or_unfree(env):
    html = page(env, "/collection?q=forest")
    row = re.search(r'<li class="coll-row" data-card="Forest".*?</li>', html, re.S).group(0)
    assert "basic land" in row and "short" not in row
