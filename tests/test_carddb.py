"""carddb writes the file every other tool reads. These tests pin the
collection_attrs.csv contract — the exact 10-column header, what lands in the
Produced/Flags/Power cells, and that a written file survives the round trip back
through mtglib.load_collection.

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
            "oracle_text": "{T}: Add {G}.", "power": "1", "toughness": "1"}

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
    # The fuzzy layer's bare `except Exception` would swallow the booby-trap —
    # a stray fuzzy fetch completed "normally" instead of failing the test
    # (found by the 2026-08-12 implementation review). Trap it before the except.
    monkeypatch.setattr(
        carddb, "_fetch_named_fuzzy",
        lambda n: pytest.fail(f"unexpected live fuzzy fetch for {n!r}"))


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
def test_header_is_the_eleven_pinned_columns_in_order(tmp_path, collection_csv,
                                                      fake_scryfall):
    out = str(tmp_path / "attrs.csv")
    carddb.enrich_api(collection_csv, out, delay=0)
    header, _ = _read(out)
    assert header == ["Name", "Type", "MV", "Colors", "Cost", "Sub-types",
                      "Scryfall", "Produced", "Flags", "Power", "FlagsVer"]
    # New columns come strictly AFTER the ones older readers know, so a file written
    # by this build still loads in an older one and vice versa. Power (2026-08-13)
    # is appended after Flags for exactly the reason Produced/Flags came after
    # Scryfall — the whole back-compat story is positional-append + read-by-name.
    assert header[:7] == carddb.ATTRS_HEADER[:7]
    # FlagsVer (2026-08-14) is appended after Power for the same reason Power came
    # after Flags. It is the one column that describes ANOTHER column: without it a
    # file enriched before a flag token existed is indistinguishable from one where
    # the token genuinely doesn't apply.
    assert header[-1] == "FlagsVer"
    assert header[-2] == "Power"


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


# ── the Power column (spec-table-ready Phase 1) ──────────────────────────────
def test_printed_power_is_written_and_a_noncreature_cell_is_empty(
        tmp_path, collection_csv, fake_scryfall):
    """Empty cell = "enriched, this card has no power" (every noncreature). Only an
    ABSENT column means unknown — the same rule Produced/Flags carry."""
    out = str(tmp_path / "attrs.csv")
    carddb.enrich_api(collection_csv, out, delay=0)
    _, rows = _read(out)
    assert rows["Llanowar Elves"][9] == "1"
    assert rows["Sol Ring"][9] == ""            # an artifact has no power
    assert rows["Command Tower"][9] == ""       # nor a land


def test_power_comes_from_the_front_face_of_a_dfc(tmp_path, monkeypatch):
    """Delver flips into a 3/2, but the card that gets CAST is the 1/1 front face.
    Same face-selection path oracle_flags uses — and never a split("//"), which is
    the SP//dr bug class."""
    delver = {"name": "Delver of Secrets // Insectile Aberration", "id": "dlv-0001",
              "color_identity": ["U"], "cmc": 1.0,
              "card_faces": [
                  {"name": "Delver of Secrets", "type_line": "Creature — Human Wizard",
                   "mana_cost": "{U}", "oracle_text": "At the beginning of your upkeep…",
                   "power": "1", "toughness": "1"},
                  {"name": "Insectile Aberration", "type_line": "Creature — Human Insect",
                   "mana_cost": "", "oracle_text": "Flying", "power": "3",
                   "toughness": "2"}]}
    coll = tmp_path / "c.csv"
    coll.write_text("Quantity,Name\n1,Delver of Secrets // Insectile Aberration\n",
                    encoding="utf-8")
    monkeypatch.setattr(carddb, "_post_collection", lambda idents, retries=4: ([delver], []))
    out = str(tmp_path / "attrs.csv")
    carddb.enrich_api(str(coll), out, delay=0)
    _, rows = _read(out)
    assert rows["Delver of Secrets // Insectile Aberration"][9] == "1"


def test_non_numeric_power_round_trips_verbatim_and_reads_as_unknown(tmp_path,
                                                                     monkeypatch):
    """'*' is stored EXACTLY as printed — nothing is lost in the file — and read back
    as None, because the honest answer to "how hard does it hit" for a Tarmogoyf is
    "that depends", not an invented integer."""
    goyf = {"name": "Tarmogoyf", "id": "goyf-0001",
            "type_line": "Creature — Lhurgoyf", "mana_cost": "{1}{G}", "cmc": 2.0,
            "color_identity": ["G"], "produced_mana": [],
            "oracle_text": "Tarmogoyf's power is equal to the number of card types "
                           "among cards in all graveyards…",
            "power": "*", "toughness": "1+*"}
    coll = tmp_path / "collection.csv"
    coll.write_text("Quantity,Name\n1,Tarmogoyf\n", encoding="utf-8")
    monkeypatch.setattr(carddb, "_post_collection", lambda idents, retries=4: ([goyf], []))
    out = os.path.join(str(tmp_path), "collection_attrs.csv")
    carddb.enrich_api(str(coll), out, delay=0)
    _, rows = _read(out)
    assert rows["Tarmogoyf"][9] == "*"                       # verbatim in the file
    idx = mtglib.index_by_name(mtglib.load_collection(str(coll)))
    assert mtglib.lookup(idx, "Tarmogoyf").power is None     # unknown to consumers


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
    # FlagsVer rides the same trip: written as the current VOCAB_VERSION, read back
    # onto Card.flags_ver. This is what lets a consumer tell "verified — no
    # restriction token applies" from "enriched before the token existed".
    import oracle_flags
    assert mtglib.lookup(idx, "Sol Ring").flags_ver == oracle_flags.VOCAB_VERSION
    # Power survives the same trip: a real int for the creature, None for the cards
    # that have no power at all.
    assert mtglib.lookup(idx, "Llanowar Elves").power == 1
    assert mtglib.lookup(idx, "Sol Ring").power is None


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


def test_a_pre_power_attrs_file_leaves_power_unknown(tmp_path, collection_csv):
    """The 9-column file the player's machine holds today: every column it does
    carry still applies, and the absent Power column reads as unknown — the goldfish
    clock's "enrich to unlock" gate, not a creature that hits for nothing."""
    attrs = os.path.join(os.path.dirname(collection_csv), "collection_attrs.csv")
    with open(attrs, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Name", "Type", "MV", "Colors", "Cost", "Sub-types", "Scryfall",
                    "Produced", "Flags"])
        w.writerow(["Llanowar Elves", "Creature", "1", "G", "{G}", "Elf;Druid",
                    "llan-0001", "G", "dork;ramp"])
    idx = mtglib.index_by_name(mtglib.load_collection(collection_csv))
    elf = mtglib.lookup(idx, "Llanowar Elves")
    assert elf.power is None
    assert elf.produced == {"G"} and elf.flags == {"dork", "ramp"}


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


def test_unmatched_cards_are_simply_absent_from_the_file(tmp_path, fake_scryfall,
                                                          monkeypatch):
    coll = tmp_path / "c.csv"
    coll.write_text("Quantity,Name\n1,Sol Ring\n1,Not A Real Card\n", encoding="utf-8")
    out = str(tmp_path / "attrs.csv")
    # the fuzzy layer also misses — the card must STAY absent, not crash or resolve
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy", lambda n: None)
    matched, total, unmatched = carddb.enrich_api(str(coll), out, delay=0)
    assert (matched, total, unmatched) == (1, 2, ["Not A Real Card"])
    _, rows = _read(out)
    assert list(rows) == ["Sol Ring"]


def test_the_duckdb_fallback_actually_fires_without_duckdb(tmp_path, capsys):
    """`build_index(use_duckdb=True)` must DEGRADE to the stdlib reader, not raise.

    It didn't: `_rows_duckdb` was a generator function, so `import duckdb` ran on
    the first iteration — outside the try/except that documents the fallback — and
    the call raised ModuleNotFoundError. duckdb is an optional dependency
    (scripts/requirements-optional.txt) and is absent here, which is exactly the
    condition the guard exists for."""
    import carddb
    bulk = tmp_path / "bulk.json"
    bulk.write_text(json.dumps([{
        "name": "Test Bear", "color_identity": ["G"], "type_line": "Creature — Bear",
        "cmc": 2, "mana_cost": "{1}{G}", "id": "abc", "power": "2",
        "produced_mana": [], "oracle_text": "", "card_faces": None,
    }]), encoding="utf-8")
    idx = carddb.build_index(str(bulk), use_duckdb=True)
    assert "test bear" in idx, "the stdlib reader must have produced the index"
    assert "duckdb unavailable" in capsys.readouterr().err
