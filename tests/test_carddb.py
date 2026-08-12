"""carddb writes the file every other tool reads. These tests pin the
collection_attrs.csv contract — the exact 9-column header, what lands in the new
Produced/Flags cells, and that a written file survives the round trip back through
mtglib.load_collection.

Fully offline: `_post_collection` is monkeypatched with canned Scryfall-shaped dicts
and `urlopen` is booby-trapped, so a stray live fetch fails the test rather than
quietly working on someone's machine and not in CI.
"""
import csv
import json
import os

import pytest

import carddb
import mtglib

# ── Scryfall-shaped fixtures (the same shapes tests/test_oracle_flags.py pins) ──
SOL_RING = {"name": "Sol Ring", "id": "sol-0001", "type_line": "Artifact",
            "mana_cost": "{1}", "cmc": 1.0, "color_identity": [],
            "produced_mana": ["C"], "oracle_text": "{T}: Add {C}{C}."}

COMMAND_TOWER = {"name": "Command Tower", "id": "cmd-0001", "type_line": "Land",
                 "mana_cost": "", "cmc": 0.0, "color_identity": [],
                 "produced_mana": ["W", "U", "B", "R", "G"],
                 "oracle_text": "{T}: Add one mana of any color in your commander's "
                                "color identity."}

MAZE_OF_ITH = {"name": "Maze of Ith", "id": "maze-0001", "type_line": "Land",
               "mana_cost": "", "cmc": 0.0, "color_identity": [],
               "produced_mana": [],
               "oracle_text": "{T}: Untap target attacking creature."}

LLANOWAR = {"name": "Llanowar Elves", "id": "llan-0001",
            "type_line": "Creature — Elf Druid", "mana_cost": "{G}", "cmc": 1.0,
            "color_identity": ["G"], "produced_mana": ["G"],
            "oracle_text": "{T}: Add {G}."}

GUILDGATE = {"name": "Azorius Guildgate", "id": "gate-0001",
             "type_line": "Land — Gate", "mana_cost": "", "cmc": 0.0,
             "color_identity": ["W", "U"], "produced_mana": ["W", "U"],
             "oracle_text": "Azorius Guildgate enters the battlefield tapped.\n"
                            "{T}: Add {W} or {U}."}

CARDS = [SOL_RING, COMMAND_TOWER, MAZE_OF_ITH, LLANOWAR, GUILDGATE]

COLLECTION = """\
Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity
1,Sol Ring,,,,,,,
1,Command Tower,,,,,,,
1,Maze of Ith,,,,,,,
1,Llanowar Elves,,,,,,,
1,Azorius Guildgate,,,,,,,
"""


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any real fetch is a test failure, not a slow test."""
    def boom(*a, **k):
        raise AssertionError("carddb tried to reach the network")
    monkeypatch.setattr(carddb.urllib.request, "urlopen", boom)


@pytest.fixture
def collection_csv(tmp_path):
    p = tmp_path / "collection.csv"
    p.write_text(COLLECTION, encoding="utf-8")
    return str(p)


@pytest.fixture
def fake_scryfall(monkeypatch):
    """Serve the canned cards for name identifiers; count the calls."""
    calls = []
    by_name = {mtglib._norm(c["name"]): c for c in CARDS}

    def post(identifiers, retries=4):
        calls.append(list(identifiers))
        data, not_found = [], []
        for ident in identifiers:
            c = by_name.get(mtglib._norm(ident.get("name", "")))
            (data.append(c) if c else not_found.append(ident))
        return data, not_found

    monkeypatch.setattr(carddb, "_post_collection", post)
    return calls


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], {r[0]: r for r in rows[1:]}


# ── the pinned header ────────────────────────────────────────────────────────
def test_header_is_the_nine_pinned_columns_in_order(tmp_path, collection_csv,
                                                    fake_scryfall):
    out = str(tmp_path / "attrs.csv")
    carddb.enrich_api(collection_csv, out, delay=0)
    header, _ = _read(out)
    assert header == ["Name", "Type", "MV", "Colors", "Cost", "Sub-types",
                      "Scryfall", "Produced", "Flags"]
    # New columns come strictly AFTER Scryfall so an older reader keeps working.
    assert header[:7] == carddb.ATTRS_HEADER[:7]


def test_bulk_path_writes_the_same_header(tmp_path, collection_csv):
    bulk = tmp_path / "bulk.json"
    bulk.write_text(json.dumps(CARDS), encoding="utf-8")
    out = str(tmp_path / "attrs.csv")
    carddb.enrich(collection_csv, str(bulk), out, use_duckdb=False)
    header, _ = _read(out)
    assert header == carddb.ATTRS_HEADER


# ── the cells ────────────────────────────────────────────────────────────────
def test_produced_is_wubrgc_ordered_and_flags_are_semicolon_joined(
        tmp_path, collection_csv, fake_scryfall):
    out = str(tmp_path / "attrs.csv")
    carddb.enrich_api(collection_csv, out, delay=0)
    _, rows = _read(out)
    assert rows["Sol Ring"][7] == "C"
    assert rows["Sol Ring"][8] == "mana2;ramp;rock"          # sorted, ';'-joined
    assert rows["Command Tower"][7] == "W U B R G"           # WUBRGC, not alphabetical
    assert rows["Command Tower"][8] == ""
    assert rows["Llanowar Elves"][8] == "dork;ramp"
    assert rows["Azorius Guildgate"][8] == "etb-tapped"


def test_a_card_that_produces_nothing_writes_an_empty_cell(tmp_path, collection_csv,
                                                           fake_scryfall):
    """Empty cell = "enriched, produces nothing". Only an ABSENT column means unknown."""
    out = str(tmp_path / "attrs.csv")
    carddb.enrich_api(collection_csv, out, delay=0)
    _, rows = _read(out)
    assert rows["Maze of Ith"][7] == ""
    assert rows["Maze of Ith"][8] == ""


def test_bulk_and_api_paths_derive_identical_cells(tmp_path, collection_csv,
                                                   fake_scryfall):
    """One derivation, two writers — the offline file must not drift from the API file."""
    bulk = tmp_path / "bulk.json"
    bulk.write_text(json.dumps(CARDS), encoding="utf-8")
    api_out, bulk_out = str(tmp_path / "a.csv"), str(tmp_path / "b.csv")
    carddb.enrich_api(collection_csv, api_out, delay=0)
    carddb.enrich(collection_csv, str(bulk), bulk_out, use_duckdb=False)
    assert open(api_out, encoding="utf-8").read() == open(bulk_out, encoding="utf-8").read()


def test_existing_columns_are_untouched(tmp_path, collection_csv, fake_scryfall):
    out = str(tmp_path / "attrs.csv")
    carddb.enrich_api(collection_csv, out, delay=0)
    _, rows = _read(out)
    assert rows["Llanowar Elves"][:7] == ["Llanowar Elves", "Creature", "1", "G",
                                          "{G}", "Elf;Druid", "llan-0001"]


# ── write → overlay round trip ───────────────────────────────────────────────
def test_round_trip_into_load_collection(tmp_path, collection_csv, fake_scryfall):
    """The end-to-end claim: enrich writes it, load_collection reads it back, and the
    None-vs-empty distinction survives the file."""
    out = os.path.join(os.path.dirname(collection_csv), "collection_attrs.csv")
    carddb.enrich_api(collection_csv, out, delay=0)
    idx = mtglib.index_by_name(mtglib.load_collection(collection_csv))
    assert mtglib.lookup(idx, "Sol Ring").produced == {"C"}
    assert mtglib.lookup(idx, "Sol Ring").flags == {"rock", "ramp", "mana2"}
    assert mtglib.lookup(idx, "Command Tower").produced == {"W", "U", "B", "R", "G"}
    maze = mtglib.lookup(idx, "Maze of Ith")
    assert maze.produced == set() and maze.produced is not None   # enriched, produces none
    assert mtglib.lookup(idx, "Azorius Guildgate").flags == {"etb-tapped"}


def test_an_attrs_file_without_the_columns_still_means_unknown(tmp_path,
                                                               collection_csv):
    """The pre-A 7-column file: load_collection must leave produced None, never set()."""
    attrs = os.path.join(os.path.dirname(collection_csv), "collection_attrs.csv")
    with open(attrs, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Name", "Type", "MV", "Colors", "Cost", "Sub-types", "Scryfall"])
        w.writerow(["Sol Ring", "Artifact", "1", "", "{1}", "", "sol-0001"])
    idx = mtglib.index_by_name(mtglib.load_collection(collection_csv))
    c = mtglib.lookup(idx, "Sol Ring")
    assert c.produced is None and c.flags == set()


# ── signature + stats ────────────────────────────────────────────────────────
def test_enrich_api_stays_safe_for_positional_callers():
    """webapp/app.py and enrich.bat call this positionally — reordering or
    inserting a parameter would break the upload route silently (its except
    swallows everything). Pinning the EXACT list proved over-tight in 2026-08-12
    (it failed on trailing keyword-with-default additions, which positional
    callers never see), so this asserts the real invariant instead: the original
    four stay first and in order, and everything added after them has a default."""
    import inspect
    sig = inspect.signature(carddb.enrich_api)
    params = list(sig.parameters)
    assert params[:4] == ["collection_path", "out_path", "delay", "log"]
    for name in params[4:]:
        assert sig.parameters[name].default is not inspect.Parameter.empty, \
            f"{name} must have a default — positional callers pass only the first two"


def test_stats_prints_the_produced_coverage_line(tmp_path, collection_csv,
                                                 fake_scryfall, capsys, monkeypatch):
    out = os.path.join(os.path.dirname(collection_csv), "collection_attrs.csv")
    monkeypatch.setattr("sys.argv", ["carddb.py", "--collection", collection_csv,
                                     "--out", out, "--stats"])
    assert carddb.main() == 0
    printed = capsys.readouterr().out
    assert "produced known: 5/5" in printed


def test_unmatched_cards_are_simply_absent_from_the_file(tmp_path, fake_scryfall):
    coll = tmp_path / "c.csv"
    coll.write_text("Quantity,Name\n1,Sol Ring\n1,Not A Real Card\n", encoding="utf-8")
    out = str(tmp_path / "attrs.csv")
    matched, total, unmatched = carddb.enrich_api(str(coll), out, delay=0)
    assert (matched, total, unmatched) == (1, 2, ["Not A Real Card"])
    _, rows = _read(out)
    assert list(rows) == ["Sol Ring"]
