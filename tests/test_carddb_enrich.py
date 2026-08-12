"""enrich_api's unattended-run guarantees (docs/spec-network-and-attrs.md §3).

These behaviors exist because the attrs-snapshot Action writes COMMITTED data
with no human watching: a fuzzy match may repair spelling but never substitute
a card; unresolvable names must fail the run loudly (--min-match) instead of
shrinking the file with exit 0; the committed variant omits the Scryfall id
column; and a name-only input must not submit every name twice. All hermetic —
the network layer is monkeypatched at _post_collection/_fetch_named_fuzzy.
"""
import csv
import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import carddb
import mtglib


def _scry(name, type_line="Creature — Dragon Noble", cmc=3.0, ci=("R",)):
    return {"name": name, "type_line": type_line, "cmc": cmc,
            "color_identity": list(ci), "mana_cost": "{2}{R}", "id": "aaaa1111",
            "oracle_text": ""}


# --------------------------------------------------------------------------- #
# _attrs_from_scryfall — the faces-only Sub-types blocker
# --------------------------------------------------------------------------- #
def test_faces_only_cards_keep_their_subtypes():
    """Adventure/omen/MDFC objects can carry type_line only on the faces. Type
    already had the fallback (the Scavenger Regent incident); Sub-types silently
    did not — every faces-only card enriched subtype-less, and subtypes are what
    tribal detection reads. The fix passes the same computed type_line."""
    c = {"name": "Marang River Regent // Coil and Catch",
         "card_faces": [{"type_line": "Creature — Dragon", "cmc": 6.0,
                         "mana_cost": "{4}{U}{U}"},
                        {"type_line": "Sorcery — Omen", "cmc": 3.0}],
         "color_identity": ["U"], "id": "bbbb2222"}
    a = carddb._attrs_from_scryfall(c)
    assert a["type"] == "Creature"
    assert a["subtypes"] == "Dragon", "faces-only card lost its tribe"


# --------------------------------------------------------------------------- #
# The fuzzy guard — repair spelling, never substitute cards
# --------------------------------------------------------------------------- #
@pytest.fixture
def namelist(tmp_path):
    def make(names):
        p = tmp_path / "collection_snapshot.txt"
        p.write_text("".join(f"1 {n}\n" for n in names), encoding="utf-8")
        return str(p)
    return make


def _run_enrich(monkeypatch, collection, out, fuzzy_map=None, **kw):
    """All exact rounds miss; the fuzzy layer serves from fuzzy_map."""
    monkeypatch.setattr(carddb, "_post_collection", lambda idents: ([], list(idents)))
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy",
                        lambda n: (fuzzy_map or {}).get(n))
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    return carddb.enrich_api(collection, out, **kw)


def test_fuzzy_accepts_a_pure_respelling(namelist, tmp_path, monkeypatch):
    """Diacritics and curly apostrophes are what fuzzy is FOR — the fold treats
    'Oin the Brave' as the same name as 'Óin the Brave'."""
    coll = namelist(["Óin the Brave"])
    out = str(tmp_path / "attrs.csv")
    m, t, un = _run_enrich(monkeypatch, coll, out,
                           fuzzy_map={"Óin the Brave": _scry("Oin the Brave")})
    assert (m, t, un) == (1, 1, [])
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert rows[0]["Name"] == "Óin the Brave" and rows[0]["Type"] == "Creature"


def test_fuzzy_never_substitutes_a_different_card(namelist, tmp_path, monkeypatch,
                                                  capsys):
    """The unattended-run rule: a fuzzy hit whose folded name differs is a
    DIFFERENT card. It must stay unmatched and be reported — silently enriching
    the wrong card's attributes into a committed file passes every other guard
    (row count and match rate both improve), which is exactly why this one exists."""
    coll = namelist(["Bilbo's Deadly Slice"])
    out = str(tmp_path / "attrs.csv")
    m, t, un = _run_enrich(monkeypatch, coll, out,
                           fuzzy_map={"Bilbo's Deadly Slice":
                                      _scry("Bilbo, Retired Burglar")})
    assert (m, un) == (0, ["Bilbo's Deadly Slice"])
    assert "fuzzy REJECTED" in capsys.readouterr().err
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert rows == [], "the wrong card must not be written"


def test_fuzzy_off_means_no_fuzzy_requests(namelist, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(carddb, "_post_collection", lambda idents: ([], list(idents)))
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy",
                        lambda n: calls.append(n) or _scry(n))
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    carddb.enrich_api(namelist(["Sol Ring"]), str(tmp_path / "a.csv"), fuzzy=False)
    assert calls == []


# --------------------------------------------------------------------------- #
# Name-only input: one exact round, not two
# --------------------------------------------------------------------------- #
def test_name_only_input_submits_each_name_once(namelist, tmp_path, monkeypatch):
    """Round 2 exists to retry ID-submitted cards BY NAME. On a name-only
    snapshot round 1 already submitted names, so round 2 was a full duplicate
    pass — every request paid twice for identical misses."""
    batches = []
    monkeypatch.setattr(carddb, "_post_collection",
                        lambda idents: batches.append(list(idents)) or ([], list(idents)))
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy", lambda n: None)
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    carddb.enrich_api(namelist(["Sol Ring", "Counterspell"]),
                      str(tmp_path / "a.csv"))
    submitted = [i for b in batches for i in b]
    assert len(submitted) == 2, f"each name once, not twice: {submitted}"


# --------------------------------------------------------------------------- #
# --no-ids: the committed-snapshot shape
# --------------------------------------------------------------------------- #
def test_no_ids_omits_the_scryfall_column_and_still_loads(namelist, tmp_path,
                                                          monkeypatch):
    monkeypatch.setattr(carddb, "_post_collection",
                        lambda idents: ([_scry("Sol Ring", "Artifact", 1.0, ())], []))
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy", lambda n: None)
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    coll = namelist(["Sol Ring"])
    out = str(tmp_path / "collection_attrs.snapshot.csv")
    carddb.enrich_api(coll, out, include_ids=False)
    header = open(out, encoding="utf-8").readline().strip().split(",")
    assert "Scryfall" not in header
    assert header[:2] == ["Name", "Type"] and "Produced" in header
    # the loader treats the absent column as absent, not empty
    cards = mtglib.load_collection(coll)
    ov = open(out, encoding="utf-8").read()
    mtglib.overlay_attrs(cards, ov)
    sol = mtglib.lookup(mtglib.index_by_name(cards), "Sol Ring")
    assert sol.types == ["Artifact"] and sol.scryfall_id == ""


# --------------------------------------------------------------------------- #
# --min-match: unattended runs fail loudly, measured against their own input
# --------------------------------------------------------------------------- #
def test_min_match_fails_the_run_when_resolution_collapses(namelist, tmp_path,
                                                           monkeypatch, capsys):
    """The 429-storm case: _post_collection exhausts retries and returns ([], []),
    enrich_api writes a header-only file, and before this flag the CLI exited 0 —
    a green run committing an empty enrichment. Exit 3 is the Action's signal."""
    monkeypatch.setattr(carddb, "_post_collection", lambda idents: ([], list(idents)))
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy", lambda n: None)
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    coll = namelist(["Sol Ring", "Counterspell"])
    out = str(tmp_path / "a.csv")
    monkeypatch.setattr(sys, "argv",
                        ["carddb.py", "--collection", coll, "--out", out,
                         "--min-match", "95"])
    rc = carddb.main()
    err = capsys.readouterr().err
    assert rc == 3
    assert "below the --min-match floor" in err and "UNMATCHED: Sol Ring" in err


def test_min_match_passes_a_healthy_run(namelist, tmp_path, monkeypatch):
    monkeypatch.setattr(carddb, "_post_collection",
                        lambda idents: ([_scry(i["name"], "Artifact", 1.0, ())
                                         for i in idents], []))
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy", lambda n: None)
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    coll = namelist(["Sol Ring"])
    monkeypatch.setattr(sys, "argv",
                        ["carddb.py", "--collection", coll,
                         "--out", str(tmp_path / "a.csv"), "--min-match", "95"])
    assert carddb.main() == 0
