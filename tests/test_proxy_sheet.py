"""Proxy sheets — the one artifact where paper GEOMETRY is the contract.

A dashboard's print layout may reflow and stay correct; a proxy is wrong if it
is not 63x88mm. So these tests pin the millimetres, the nine-per-sheet chunking,
and the print rules that keep a browser from silently resizing or blanking the
cards — plus the repo's standing rules: exact-printing image identifiers from
the collection, `//` names surviving un-split, and the page staying
self-contained. Offline and hermetic like everything else."""
import pytest

import mtglib
import proxy_sheet as px


DECK = """\
# Title: Geometry Test
# Commander: Test Commander

# --- Commander ---
1 Test Commander

# --- Spells ---
1 Sol Ring
2 Arcane Signet
1 SP//dr, Piloted by Peni

# --- Lands ---
7 Island
"""

# The ManaPool flavor: set + collector number present, so proxies can use the
# player's exact printings.
COLL = """\
"sep=,"
List Type,List Name,Collection,Format,Board,Quantity,Card Name,Set Code,Set Name,Card Number,Condition,Printing,Rarity,Language,Price Bought,Date Bought,Parent List Type,Parent List Name,Current Price (tcgplayer_marketsellprice),List Cover Image,Parent List Cover Image
,,mtg,,,1,Test Commander,TST,Test Set,1,NearMint,Normal,rare,en,1.00,2026-08-01,,,1.00,,
,,mtg,,,1,Sol Ring,TST,Test Set,2,NearMint,Normal,uncommon,en,1.00,2026-08-01,,,1.50,,
,,mtg,,,2,Arcane Signet,TST,Test Set,3,NearMint,Normal,common,en,0.50,2026-08-01,,,0.90,,
,,mtg,,,1,"SP//dr, Piloted by Peni",SPM,"Marvel's Spider-Man",61,NearMint,Normal,rare,en,0.30,2026-08-01,,,0.30,,
,,mtg,,,9,Island,TST,Test Set,100,NearMint,Normal,common,en,0.05,2026-08-01,,,0.05,,
"""


@pytest.fixture
def deck_path(tmp_path):
    p = tmp_path / "geom.txt"
    p.write_text(DECK, encoding="utf-8")
    return str(p)


@pytest.fixture
def coll_path(tmp_path):
    p = tmp_path / "coll.csv"
    p.write_text(COLL, encoding="utf-8")
    return str(p)


def _page(deck_path, coll_path, **kw):
    cells, title = px.build(deck=deck_path, collection=coll_path, **kw)
    return cells, px.generate_html(cells, title=title)


def test_cells_are_exactly_card_sized(deck_path, coll_path):
    _, page = _page(deck_path, coll_path)
    assert "width:63mm" in page and "height:88mm" in page, \
        "a proxy that is not 63x88mm is not a proxy"
    assert "repeat(3, 63mm)" in page, "three columns of exact card width"
    assert "@page" in page and "margin:6mm" in page
    # 189x264mm must fit BOTH Letter and A4 — so the sheet must NOT pin a size.
    assert "size:" not in page.split("@page", 1)[1][:60], \
        "@page must set margin only; the print dialog owns the paper choice"


def test_one_cell_per_physical_copy_nine_per_sheet(deck_path, coll_path):
    cells, page = _page(deck_path, coll_path)
    # 1 commander + 1 + 2 + 1 + 7 islands = 12 copies -> 2 sheets (9 + 3)
    assert len(cells) == 12
    assert page.count("figure class='px'") == 12
    assert page.count("class='sheet'") == 2


def test_exact_printing_identifiers_ride_along(deck_path, coll_path):
    cells, page = _page(deck_path, coll_path)
    sol = next(c for c in cells if c["name"] == "Sol Ring")
    assert sol["set"] == "TST" and sol["num"] == "2", \
        "owned cards must proxy the player's exact printing"
    assert "data-set='TST'" in page and "data-num='2'" in page


def test_split_card_names_survive_unsplit(deck_path, coll_path):
    """The `SP//dr` trap (CLAUDE.md): a naive split('//') would mangle the name."""
    cells, _ = _page(deck_path, coll_path)
    spdr = [c for c in cells if "SP//dr" in c["name"]]
    assert len(spdr) == 1, "SP//dr must remain ONE card with // intact"
    assert spdr[0]["set"] == "SPM"


def test_missing_mode_prints_only_uncovered_copies(deck_path, coll_path):
    """Deck wants 7 Islands? Collection has 9 -> 0 missing. Everything else owned."""
    cells, _ = _page(deck_path, coll_path, missing=True)
    assert cells == [], "a fully-owned deck has nothing to proxy in --missing mode"


def test_missing_mode_counts_copy_shortfall(tmp_path, coll_path):
    p = tmp_path / "wanting.txt"
    p.write_text("# Title: W\n\n# --- S ---\n4 Arcane Signet\n1 Black Lotus\n",
                 encoding="utf-8")
    cells, _ = px.build(deck=str(p), collection=coll_path, missing=True)
    got = {(c["name"]): 0 for c in cells}
    for c in cells:
        got[c["name"]] += 1
    assert got == {"Arcane Signet": 2, "Black Lotus": 1}, \
        "own 2 of 4 wanted -> exactly 2 proxies; unowned card -> 1"


def test_unowned_cards_fall_back_to_by_name_lookup(tmp_path, coll_path):
    p = tmp_path / "wanting.txt"
    p.write_text("# Title: W\n\n# --- S ---\n1 Black Lotus\n", encoding="utf-8")
    cells, _ = px.build(deck=str(p), collection=coll_path)
    lotus = cells[0]
    assert lotus["set"] == "" and "cards/named?fuzzy=" in lotus["url"], \
        "no printing to match — resolve by name at print time"


def test_buylist_mode_reads_the_companion_csv(tmp_path, coll_path):
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: D\n\n# --- S ---\n1 Sol Ring\n", encoding="utf-8")
    (tmp_path / "d.buylist.csv").write_text(
        "Card,Price,Tier,Replaces,Reason\n"
        "Herald's Horn,4.00,core,Manalith,tribal engine\n"
        "Urza's Incubator,8.00,core,Worn Powerstone,cost cutter\n",
        encoding="utf-8")
    cells, title = px.build(deck=str(deck), collection=coll_path, buylist=True)
    assert [c["name"] for c in cells] == ["Herald's Horn", "Urza's Incubator"]
    assert "buylist" in title
    # and a deck with no buylist proxies nothing rather than erroring
    lone = tmp_path / "solo.txt"
    lone.write_text("# Title: S\n\n# --- S ---\n1 Sol Ring\n", encoding="utf-8")
    cells2, _ = px.build(deck=str(lone), collection=coll_path, buylist=True)
    assert cells2 == []


def test_print_rules_protect_the_art_and_hide_the_chrome(deck_path, coll_path):
    _, page = _page(deck_path, coll_path)
    printed = page.split("@media print", 1)[1]
    assert "print-color-adjust:exact" in printed, \
        "the art IS the content — 'Background graphics' must not blank it"
    assert ".bar { display:none; }" in printed
    assert "break-after:page" in printed
    assert "window.print()" in page, "the print button is the whole flow"
    assert "100%" in page, "the page must tell the player: print at 100% scale"


def test_page_is_self_contained_with_hotlinked_images_only(deck_path, coll_path):
    _, page = _page(deck_path, coll_path)
    assert "<script src=" not in page and "<link" not in page
    assert "api.scryfall.com/cards/collection" in page, \
        "batch loader resolves exact printings client-side"
    # name paints under the image: a failed hotlink still names the card
    assert "px-name" in page
    assert "img:not([src])" in page


# --------------------------------------------------------------------------- #
# the route

@pytest.fixture
def client(tmp_path, monkeypatch, coll_path):
    import app as appmod
    import sync
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "d.txt").write_text(DECK, encoding="utf-8")
    (decks / "d.buylist.csv").write_text(
        "Card,Price,Tier,Replaces,Reason\nHerald's Horn,4.00,core,Sol Ring,engine\n",
        encoding="utf-8")
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", coll_path)
    monkeypatch.setattr(appmod, "PASSWORD", None)
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def test_route_serves_the_deck_sheet_inline(client):
    r = client.get("/deck/d/proxies")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "width:63mm" in body and body.count("figure class='px'") == 12
    assert "attachment" not in r.headers.get("Content-Disposition", ""), \
        "the flow is open -> print, not download"


def test_route_buylist_param_switches_to_the_buylist(client):
    body = client.get("/deck/d/proxies?buylist=1").get_data(as_text=True)
    assert "Herald&#x27;s Horn" in body or "Herald's Horn" in body
    assert body.count("figure class='px'") == 1


def test_route_404s_an_unknown_deck_and_sits_behind_the_gate(client, monkeypatch):
    import app as appmod
    assert client.get("/deck/nope/proxies").status_code == 404
    monkeypatch.setattr(appmod, "PASSWORD", "correct horse")
    r = client.get("/deck/d/proxies")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
