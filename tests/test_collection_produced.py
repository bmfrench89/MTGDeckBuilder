"""The web app's two production-aware surfaces: the /collection coverage tile and the
coaching packet's honesty note — plus the upload round trip.

The upload test exists because `/collection/upload` wraps its inline enrichment in a
bare `except Exception: pass`. That is the right call for a best-effort enrich (the
raw collection still loads without attributes), but it also means a derivation bug
would write a silently truncated attrs file and nothing would ever say so. This test
is the thing that says so.

Nothing here touches the player's real data/: ROOT, COLLECTION_CSV and
COLLECTION_ATTRS are all pointed into tmp_path, and Scryfall is monkeypatched.
"""
import csv
import io
import os
import sys

import pytest

import carddb
import mtglib

SMALL_CSV = """\
Quantity,Name
1,Sol Ring
1,Command Tower
"""

SCRYFALL = {
    "sol ring": {"name": "Sol Ring", "id": "sol-0001", "type_line": "Artifact",
                 "mana_cost": "{1}", "cmc": 1.0, "color_identity": [],
                 "produced_mana": ["C"], "oracle_text": "{T}: Add {C}{C}."},
    "command tower": {"name": "Command Tower", "id": "cmd-0001", "type_line": "Land",
                      "mana_cost": "", "cmc": 0.0, "color_identity": [],
                      "produced_mana": ["W", "U", "B", "R", "G"],
                      "oracle_text": "{T}: Add one mana of any color in your "
                                     "commander's color identity."},
}

ATTRS_ENRICHED = """\
Name,Type,MV,Colors,Cost,Sub-types,Scryfall,Produced,Flags
Sol Ring,Artifact,1,,{1},,sol-0001,C,mana2;ramp;rock
Command Tower,Land,0,,,,cmd-0001,W U B R G,
"""

ATTRS_LEGACY = """\
Name,Type,MV,Colors,Cost,Sub-types,Scryfall
Sol Ring,Artifact,1,,{1},,sol-0001
Command Tower,Land,0,,,,cmd-0001
"""


@pytest.fixture
def fake_scryfall(monkeypatch):
    def post(identifiers, retries=4):
        data, not_found = [], []
        for ident in identifiers:
            c = SCRYFALL.get(mtglib._norm(ident.get("name", "")))
            (data.append(c) if c else not_found.append(ident))
        return data, not_found
    monkeypatch.setattr(carddb, "_post_collection", post)
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy", lambda n: None)


def _app(tmp_path, monkeypatch, attrs_text=None, deck_file=None,
         collection_text=SMALL_CSV):
    """A test client whose ROOT and collection both live under tmp_path.

    Every mutation goes through monkeypatch: `app` is a module-level singleton that
    later test files re-use, and a leaked ROOT turns /sw.js into a 404 three files
    down the suite."""
    coll_dir = tmp_path / "data" / "collection"
    coll_dir.mkdir(parents=True, exist_ok=True)
    (coll_dir / "collection.csv").write_text(collection_text, encoding="utf-8")
    if attrs_text is not None:
        (coll_dir / "collection_attrs.csv").write_text(attrs_text, encoding="utf-8")
    decks = tmp_path / "decks"
    decks.mkdir(exist_ok=True)
    if deck_file:
        import shutil
        shutil.copy(deck_file, decks / "testdeck.txt")
    monkeypatch.setenv("MTG_DECKS_DIR", str(decks))
    monkeypatch.setenv("MTG_COLLECTION", str(coll_dir / "collection.csv"))
    sys.modules.pop("app", None)
    import app
    monkeypatch.setattr(app, "ROOT", str(tmp_path))
    monkeypatch.setattr(app, "COLLECTION", str(coll_dir / "collection.csv"))
    monkeypatch.setattr(app, "COLLECTION_CSV", str(coll_dir / "collection.csv"))
    monkeypatch.setattr(app, "COLLECTION_ATTRS",
                        str(coll_dir / "collection_attrs.csv"))
    monkeypatch.setattr(app, "DECKS_DIR", str(decks))
    app.app.config["TESTING"] = True
    return app, app.app.test_client()


# ── upload round trip ────────────────────────────────────────────────────────
def test_upload_writes_the_nine_column_attrs_file(tmp_path, monkeypatch, fake_scryfall):
    app, client = _app(tmp_path, monkeypatch)
    r = client.post("/collection/upload",
                    data={"csv": (io.BytesIO(SMALL_CSV.encode()), "export.csv")},
                    content_type="multipart/form-data")
    assert r.status_code in (302, 303)
    with open(app.COLLECTION_ATTRS, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == carddb.ATTRS_HEADER
    cells = {r[0]: r for r in rows[1:]}
    assert cells["Sol Ring"][7] == "C"
    assert cells["Sol Ring"][8] == "mana2;ramp;rock"
    assert cells["Command Tower"][7] == "W U B R G"


def test_upload_never_writes_any_tracked_collection_path(tmp_path, monkeypatch, fake_scryfall):
    """The privacy line: a priced export goes to the gitignored CSV only. Guards
    every tracked path under data/collection/, including the attrs snapshot the
    planned Action will commit (docs/spec-network-and-attrs.md §3) — the upload
    route must keep writing the PRIVATE attrs file, never the committed one."""
    app, client = _app(tmp_path, monkeypatch)
    d = os.path.join(tmp_path, "data", "collection")
    client.post("/collection/upload",
                data={"csv": (io.BytesIO(SMALL_CSV.encode()), "export.csv")},
                content_type="multipart/form-data")
    for tracked in ("collection_snapshot.txt", "collection_attrs.snapshot.csv"):
        assert not os.path.exists(os.path.join(d, tracked)), tracked


# ── /collection coverage tile ────────────────────────────────────────────────
def test_collection_tile_reports_production_coverage(tmp_path, monkeypatch):
    _app_mod, client = _app(tmp_path, monkeypatch, ATTRS_ENRICHED)
    html = client.get("/collection").get_data(as_text=True)
    assert "Mana production: known" in html
    assert "2/2" in html


def test_collection_tile_is_honest_when_production_is_unknown(tmp_path, monkeypatch):
    """A pre-A attrs file has full types and zero production — the tile must not let
    that read as 'enriched, all good'."""
    _app_mod, client = _app(tmp_path, monkeypatch, ATTRS_LEGACY)
    html = client.get("/collection").get_data(as_text=True)
    assert "Mana production: unknown" in html
    assert "identity" in html


# ── coaching packet ──────────────────────────────────────────────────────────
DECK = """\
# Title: Packet Deck
# Commander: Test Commander
# Colors: U

# --- Commander ---
1 Test Commander

# --- Spells ---
1 Counterspell

# --- Lands ---
10 Island
"""

PACKET_COLLECTION = """\
Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity
1,Test Commander,4,U,U,{3}{U},Legendary Creature,Human Wizard,rare
1,Counterspell,2,U,U,{U}{U},Instant,,common
12,Island,0,U,U,,Land,Island,common
"""

PACKET_ATTRS = """\
Name,Type,MV,Colors,Cost,Sub-types,Scryfall,Produced,Flags
Test Commander,Legendary Creature,4,U,{3}{U},Human;Wizard,tc0001,,
Counterspell,Instant,2,U,{U}{U},,c0001,,
Island,Land,0,U,,Island,i0001,U,
"""


def _packet(tmp_path, monkeypatch, attrs_text, name):
    deck = tmp_path / f"{name}.txt"
    deck.write_text(DECK, encoding="utf-8")
    _app_mod, client = _app(tmp_path / name, monkeypatch, attrs_text,
                            deck_file=str(deck), collection_text=PACKET_COLLECTION)
    return client.get("/deck/testdeck/assess.txt").get_data(as_text=True)


def test_packet_notes_the_identity_approximation_when_production_is_unknown(
        tmp_path, monkeypatch):
    txt = _packet(tmp_path, monkeypatch, None, "fallback")
    assert "counted by color IDENTITY" in txt


def test_packet_stays_quiet_when_every_land_is_enriched(tmp_path, monkeypatch):
    txt = _packet(tmp_path, monkeypatch, PACKET_ATTRS, "enriched")
    assert "sources:" in txt
    assert "counted by color IDENTITY" not in txt


def test_tile_names_the_snapshot_source_when_only_it_exists(tmp_path, monkeypatch,
                                                            fake_scryfall):
    """A fresh clone served solely by the committed attrs snapshot must show the
    tile ON and say which source is serving — it used to show OFF beside a full
    coverage count, sending sessions off to hand-curate data they already had."""
    app, client = _app(tmp_path, monkeypatch)
    d = os.path.join(tmp_path, "data", "collection")
    with open(os.path.join(d, "collection_attrs.snapshot.csv"), "w",
              encoding="utf-8") as f:
        f.write("Name,Type,MV,Colors,Cost,Sub-types,Produced,Flags\n")
    html = client.get("/collection").data.decode()
    assert "committed snapshot" in html
    assert "image ids" not in html, "no printing ids exist on the snapshot path"


def test_tile_names_the_private_source_when_present(tmp_path, monkeypatch,
                                                    fake_scryfall):
    app, client = _app(tmp_path, monkeypatch)
    d = os.path.join(tmp_path, "data", "collection")
    with open(os.path.join(d, "collection_attrs.csv"), "w", encoding="utf-8") as f:
        f.write("Name,Type\n")
    html = client.get("/collection").data.decode()
    assert "your own export" in html and "image ids" in html
