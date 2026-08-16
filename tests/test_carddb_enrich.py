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


# --------------------------------------------------------------------------- #
# DFC identifiers — the 26-missing-cards bug (docs/spec-dfc-enrichment.md)
# --------------------------------------------------------------------------- #
def test_dfc_submits_the_front_face_but_keys_on_the_full_name():
    """MEASURED, not documented: /cards/collection's `name` matches a SINGLE FACE
    and returns not_found for the combined "Front // Back" string (deck-verify run
    31961993767). Submitting the full name meant EVERY double-faced card missed the
    exact round and fell into the fuzzy pass, where a swallowed 429 dropped 26 of
    them from the committed snapshot with no log line and exit 0.

    The key must stay the FULL name — that is what `resolved` is keyed by, and what
    `_response_keys` will match via `name_keys`."""
    card = mtglib.Card(name="Murderous Rider // Swift End", quantity=1)
    ident, key = carddb._best_identifier(card)
    assert ident == {"name": "Murderous Rider"}, "submit the front face"
    assert key == ("name", "murderous rider // swift end"), "key on the full name"


def test_single_faced_identifiers_are_unchanged():
    card = mtglib.Card(name="Sol Ring", quantity=1)
    assert carddb._best_identifier(card) == ({"name": "Sol Ring"},
                                             ("name", "sol ring"))


def test_a_bare_double_slash_name_is_never_split():
    """The `SP//dr` trap (CLAUDE.md): a bare '//' with no surrounding spaces is part
    of a REAL card name. front_face() already guarantees this; the guard is pinned
    here because this is a new call site for it."""
    card = mtglib.Card(name="SP//dr, Piloted by Peni", quantity=1)
    ident, key = carddb._best_identifier(card)
    assert ident == {"name": "SP//dr, Piloted by Peni"}, "must NOT split on //"
    assert key == ("name", "sp//dr, piloted by peni")


def test_a_front_face_request_matches_the_combined_response(namelist, tmp_path,
                                                            monkeypatch):
    """The seam the whole fix rests on: we ask for "Murderous Rider", Scryfall
    answers with a card NAMED "Murderous Rider // Swift End", and that response must
    still land on the collection row keyed by its full name."""
    coll = namelist(["Murderous Rider // Swift End"])
    out = str(tmp_path / "attrs.csv")
    asked = []

    def fake_post(idents):
        asked.extend(idents)
        return ([_scry("Murderous Rider // Swift End",
                       type_line="Creature — Zombie Knight // Instant — Adventure",
                       cmc=3.0, ci=("B",))], [])

    monkeypatch.setattr(carddb, "_post_collection", fake_post)
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy",
                        lambda n: pytest.fail(f"fuzzy must not run for {n!r}"))
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    matched, total, unmatched = carddb.enrich_api(coll, out)

    assert asked == [{"name": "Murderous Rider"}]
    assert (matched, total, unmatched) == (1, 1, []), "resolved in the EXACT round"
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert rows[0]["Name"] == "Murderous Rider // Swift End"
    assert rows[0]["Type"] == "Creature", "a Dragon/Knight is not a land"


def test_two_rows_sharing_a_front_face_both_resolve(namelist, tmp_path, monkeypatch):
    """A collection may legitimately list the same physical card under both name
    forms. Both fold to ONE submitted identifier and therefore ONE response, and the
    old `next(...)` match resolved whichever key `name_keys` yielded first — it
    returns a frozenset, so the loser was dropped arbitrarily and silently."""
    coll = namelist(["Murderous Rider // Swift End", "Murderous Rider"])
    out = str(tmp_path / "attrs.csv")
    monkeypatch.setattr(carddb, "_post_collection",
                        lambda idents: ([_scry("Murderous Rider // Swift End",
                                               type_line="Creature — Zombie Knight",
                                               ci=("B",))], []))
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy", lambda n: None)
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    matched, total, unmatched = carddb.enrich_api(coll, out)
    assert unmatched == [], "neither row may be silently dropped"
    assert (matched, total) == (2, 2)
    names = {r["Name"] for r in csv.DictReader(open(out, encoding="utf-8"))}
    assert names == {"Murderous Rider // Swift End", "Murderous Rider"}
