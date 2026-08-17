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


# --------------------------------------------------------------------------- #
# Slice 3 — the hardening (docs/spec-dfc-enrichment.md §3B–E).
#
# One shared request ladder, a three-way fuzzy outcome, and a run that refuses
# to write a file it could not finish. The bug being closed: `_fetch_named_fuzzy`
# swallowed every exception into None, so "the proxy blocked us" and "Scryfall
# says no such card" were indistinguishable — and the second one writes a short
# attrs file with exit 0, which every downstream consumer reads as "not enriched
# yet" and quietly answers from the name heuristics instead.

def test_one_ladder_serves_both_request_paths(monkeypatch):
    """Both callers must go through `_request_json`, or the backoff exists twice
    and drifts. Also pins the ladder itself: 429 waits, then succeeds."""
    waits, attempts = [], {"n": 0}
    monkeypatch.setattr(carddb.time, "sleep", lambda s: waits.append(s))

    class _Resp:
        def __init__(self, body): self.body = body
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def urlopen(req, timeout=None):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise carddb.urllib.error.HTTPError("u", 429, "Too Many", {}, None)
        return _Resp(b'{"data": [], "not_found": []}')

    monkeypatch.setattr(carddb.urllib.request, "urlopen", urlopen)
    assert carddb._post_collection([{"name": "Sol Ring"}]) == ([], [])
    assert waits == [5, 15], "Scryfall's ~30s cooldown — not short exponential waits"


def test_the_ladder_does_not_burn_retries_on_a_dead_socket(monkeypatch):
    """Only 429/503 are worth waiting out. A blocked proxy must fail NOW, not
    after 110 seconds of politeness."""
    slept = []
    monkeypatch.setattr(carddb.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(carddb.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("proxy said no")))
    with pytest.raises(OSError):
        carddb._request_json("https://api.scryfall.com/cards/named?fuzzy=x")
    assert slept == []


def test_fuzzy_tells_a_genuine_miss_from_an_outage(monkeypatch):
    """The three-way outcome. A 404 is an answer; anything else is a failure to
    ask, and the difference is what makes the silent drop impossible."""
    def urlopen(req, timeout=None):
        raise carddb.urllib.error.HTTPError("u", 404, "Not Found", {}, None)
    monkeypatch.setattr(carddb.urllib.request, "urlopen", urlopen)
    assert carddb._fetch_named_fuzzy("Blightsteel Squirrel of Ravnica") is None

    def boom(req, timeout=None):
        raise carddb.urllib.error.HTTPError("u", 500, "Server Error", {}, None)
    monkeypatch.setattr(carddb.urllib.request, "urlopen", boom)
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    with pytest.raises(carddb.urllib.error.HTTPError):
        carddb._fetch_named_fuzzy("Sol Ring")


def test_a_transport_failure_refuses_to_write_a_partial_file(namelist, tmp_path,
                                                             monkeypatch):
    """The heart of slice 3. One card cannot be looked up at all — the run must
    raise instead of leaving a file that LOOKS like a complete enrichment."""
    coll = namelist(["Sol Ring", "Llanowar Elves"])
    out = tmp_path / "attrs.csv"
    monkeypatch.setattr(carddb, "_post_collection", lambda idents: ([], list(idents)))
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy",
                        lambda n: (_ for _ in ()).throw(OSError("proxy said no")))
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    with pytest.raises(RuntimeError) as e:
        carddb.enrich_api(str(coll), str(out))
    assert "transport failure" in str(e.value) and "Sol Ring" in str(e.value)
    assert not out.exists(), "a partial attrs file is worse than no attrs file"


def test_a_genuine_miss_still_writes_and_reports(namelist, tmp_path, monkeypatch):
    """The other half of the same contract: Scryfall answering 'no such card' is
    NOT a failure. The file is written and the name comes back as unmatched."""
    coll = namelist(["Sol Ring", "Blightsteel Squirrel of Ravnica"])
    out = tmp_path / "attrs.csv"
    monkeypatch.setattr(
        carddb, "_post_collection",
        lambda idents: ([_scry("Sol Ring", type_line="Artifact", ci=())],
                        [i for i in idents if i.get("name") != "Sol Ring"]))
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy", lambda n: None)
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    matched, total, unmatched = carddb.enrich_api(str(coll), str(out))
    assert (matched, total) == (1, 2)
    assert unmatched == ["Blightsteel Squirrel of Ravnica"]
    assert out.exists()


def test_the_fuzzy_pass_is_paced_for_scryfalls_real_rate_limit(namelist, tmp_path,
                                                               monkeypatch):
    """proxy_sheet.py measured the limit at ~2/s and found 400ms already OVER it.
    The fuzzy pass used to run at 0.1s, i.e. 10/s."""
    coll = namelist(["Sol Ring"])
    slept = []
    monkeypatch.setattr(carddb, "_post_collection", lambda idents: ([], list(idents)))
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy", lambda n: None)
    monkeypatch.setattr(carddb.time, "sleep", lambda s: slept.append(s))
    carddb.enrich_api(str(coll), str(tmp_path / "a.csv"))
    assert 0.7 in slept, f"fuzzy pass must pace at 0.7s, slept {slept}"


def test_the_fuzzy_cache_is_opt_in_and_never_guesses_a_path(namelist, tmp_path,
                                                            monkeypatch):
    """Wiring the fuzzy pass into VERIFY_CACHE_DIR is the point (§3E) — but
    defaulting to it made the SUITE write into the player's real
    data/cache/scryfall. A library function does not choose a path under data/."""
    coll = namelist(["Sol Ring"])
    calls = []
    monkeypatch.setattr(carddb, "_post_collection", lambda idents: ([], list(idents)))
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy",
                        lambda n: (calls.append(n),
                                   _scry("Sol Ring", type_line="Artifact", ci=()))[1])
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    monkeypatch.setattr(carddb, "_cache_put", lambda *a, **k:
                        pytest.fail("wrote to a cache nobody asked for"))
    carddb.enrich_api(str(coll), str(tmp_path / "a.csv"))       # no cache_dir

    monkeypatch.undo()
    cache = tmp_path / "cache"
    monkeypatch.setattr(carddb, "_post_collection", lambda idents: ([], list(idents)))
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy",
                        lambda n: (calls.append(n),
                                   _scry("Sol Ring", type_line="Artifact", ci=()))[1])
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    n_before = len(calls)
    for _ in range(2):
        carddb.enrich_api(str(coll), str(tmp_path / "b.csv"),
                          fuzzy_cache_dir=str(cache))
    assert len(calls) - n_before == 1, "the second run must be served from cache"
    assert cache.is_dir() and list(cache.iterdir())


def test_the_min_match_floor_applies_per_category_not_just_overall(
        namelist, tmp_path, monkeypatch, capsys):
    """The measured blindness (§1.4): 26 of 40 double-faced cards missing left the
    run at 99% overall, and `--min-match 95` waved it through. Here 1 of 21 cards
    misses — 95.2% overall, which clears the floor — but it is the ONLY DFC in the
    input, so DFC coverage is 0% and the run must fail."""
    names = [f"Filler {i}" for i in range(20)] + ["Marang River Regent // Coil and Catch"]
    coll = namelist(names)
    monkeypatch.setattr(
        carddb, "_post_collection",
        lambda idents: ([_scry(i["name"], "Artifact", 1.0, ()) for i in idents
                         if i["name"].startswith("Filler")],
                        [i for i in idents if not i["name"].startswith("Filler")]))
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy", lambda n: None)
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    monkeypatch.setattr(sys, "argv",
                        ["carddb.py", "--collection", coll,
                         "--out", str(tmp_path / "a.csv"), "--min-match", "95"])
    rc = carddb.main()
    cap = capsys.readouterr()
    assert rc == 3, "an overall rate that clears the floor must not hide the category"
    assert "double-faced coverage 0.0%" in cap.err
    assert "UNMATCHED DFC: Marang River Regent // Coil and Catch" in cap.err
    assert "double-faced cards: 0/1 resolved" in cap.out


def test_the_misses_are_printed_even_on_a_run_that_passes(namelist, tmp_path,
                                                          monkeypatch, capsys):
    """The unmatched list was computed and thrown away unless --min-match tripped,
    which is how a category could vanish from a green run in silence."""
    coll = namelist(["Sol Ring", "Blightsteel Squirrel of Ravnica"])
    monkeypatch.setattr(
        carddb, "_post_collection",
        lambda idents: ([_scry("Sol Ring", "Artifact", 1.0, ())],
                        [i for i in idents if i.get("name") != "Sol Ring"]))
    monkeypatch.setattr(carddb, "_fetch_named_fuzzy", lambda n: None)
    monkeypatch.setattr(carddb.time, "sleep", lambda *_: None)
    monkeypatch.setattr(sys, "argv",
                        ["carddb.py", "--collection", coll,
                         "--out", str(tmp_path / "a.csv")])
    assert carddb.main() == 0, "a genuine miss is not a failed run"
    assert "UNMATCHED: Blightsteel Squirrel of Ravnica" in capsys.readouterr().err
