"""`carddb.py --verify` is the only tool in the repo that can answer "is this card
real, and what does it actually say?" — the CLI behind
`.claude/agents/card-verifier.md` and behind grounding rule 3.

Everything it can get wrong is a grounding failure, so these tests pin the parts that
lie quietly: the positional reconciliation (name-keyed matching breaks on back-face
requests — the returned card is named "Front // Back" and the request wasn't), the
face-aware oracle join (never `split("//")`, the SP//dr bug class), the True/False/
**None** legality tri-state, and the promise that an unreachable Scryfall produces
UNVERIFIED rows instead of an exception or a guess.

Fully hermetic: `VERIFY_CACHE_DIR` points into tmp_path, `_post_collection` and `_get`
are fakes, and `urlopen` is booby-trapped so a stray live fetch fails the test rather
than passing on a networked machine and failing in CI. The one live check
(`--verify "Sol Ring"` against the real API) is an owner-machine step, recorded in the
PR body — Scryfall is egress-blocked from the sandbox this was written in.
"""
import json

import pytest

import carddb
import mtglib

# ── Scryfall-shaped fixtures ─────────────────────────────────────────────────
SOL_RING = {"name": "Sol Ring", "id": "sol-0001", "type_line": "Artifact",
            "mana_cost": "{1}", "cmc": 1.0, "color_identity": [],
            "oracle_text": "{T}: Add {C}{C}.", "set": "ltc",
            "collector_number": "284", "produced_mana": ["C"],
            "scryfall_uri": "https://scryfall.com/card/ltc/284/sol-ring",
            "legalities": {"commander": "legal"}}

LLANOWAR = {"name": "Llanowar Elves", "id": "llan-0001",
            "type_line": "Creature — Elf Druid", "mana_cost": "{G}", "cmc": 1.0,
            "color_identity": ["G"], "oracle_text": "{T}: Add {G}.", "set": "m19",
            "collector_number": "314", "produced_mana": ["G"],
            "scryfall_uri": "https://scryfall.com/card/m19/314/llanowar-elves",
            "legalities": {"commander": "legal"}}

# Banned in Commander → legal_commander must be False, not None and not True.
BLACK_LOTUS = {"name": "Black Lotus", "id": "lotus-01", "type_line": "Artifact",
               "mana_cost": "{0}", "cmc": 0.0, "color_identity": [],
               "oracle_text": "{T}, Sacrifice Black Lotus: Add three mana of any "
                              "one color.", "set": "lea", "collector_number": "232",
               "scryfall_uri": "https://scryfall.com/card/lea/232/black-lotus",
               "legalities": {"commander": "banned"}}

# No legalities block at all (a token, or a payload shape Scryfall changed) → None.
# "Unknown" is not "illegal"; the same None-vs-empty discipline as Card.produced.
NO_LEGALITIES = {"name": "Mystery Booster Playtest Card", "id": "myst-01",
                 "type_line": "Creature — Human", "mana_cost": "{1}{W}", "cmc": 2.0,
                 "color_identity": ["W"], "oracle_text": "Do the thing.",
                 "set": "cmb1", "collector_number": "1"}

# A real double-faced card from this repo's committed data
# (data/decks/captain-america-first-avenger.txt:48). Card-level oracle_text is absent,
# exactly as Scryfall ships DFCs — the text has to come from the faces.
ELITE_INTERCEPTOR = {
    "name": "Elite Interceptor // Rejoinder", "id": "elite-01",
    "type_line": "Creature — Human Soldier // Instant", "color_identity": ["W"],
    "set": "spm", "collector_number": "17",
    "scryfall_uri": "https://scryfall.com/card/spm/17",
    "legalities": {"commander": "legal"},
    "card_faces": [
        {"name": "Elite Interceptor", "mana_cost": "{2}{W}",
         "type_line": "Creature — Human Soldier", "oracle_text": "Vigilance."},
        {"name": "Rejoinder", "mana_cost": "{1}{W}", "type_line": "Instant",
         "oracle_text": "Target creature gets +2/+2 until end of turn."},
    ]}

BY_NAME = {mtglib._norm(c["name"]): c
           for c in (SOL_RING, LLANOWAR, BLACK_LOTUS, NO_LEGALITIES,
                     ELITE_INTERCEPTOR)}


@pytest.fixture(autouse=True)
def hermetic(monkeypatch, tmp_path):
    """Cache into tmp_path, never sleep, and make any real fetch a failure."""
    monkeypatch.setattr(carddb, "VERIFY_CACHE_DIR", str(tmp_path / "scryfall"))
    monkeypatch.setattr(carddb.time, "sleep", lambda *_a: None)

    def boom(*a, **k):
        raise AssertionError("carddb tried to reach the network")
    monkeypatch.setattr(carddb.urllib.request, "urlopen", boom)


def fake_batch(monkeypatch, data, not_found=(), calls=None):
    """Serve one canned (data, not_found) pair from `_post_collection`, recording the
    identifier lists it was called with."""
    calls = [] if calls is None else calls

    def post(identifiers, retries=4):
        calls.append(list(identifiers))
        return list(data), list(not_found)
    monkeypatch.setattr(carddb, "_post_collection", post)
    return calls


def fake_exact(monkeypatch, calls=None):
    """A `_post_collection` that behaves like Scryfall's exact-name matching: known
    front-face names resolve, everything else lands in not_found."""
    calls = [] if calls is None else calls

    def post(identifiers, retries=4):
        calls.append(list(identifiers))
        data, missing = [], []
        for ident in identifiers:
            c = BY_NAME.get(mtglib._norm(ident.get("name", "")))
            (data.append(c) if c else missing.append(ident))
        return data, missing
    monkeypatch.setattr(carddb, "_post_collection", post)
    return calls


def fake_fuzzy(monkeypatch, resolutions):
    """Serve `/cards/named?fuzzy=` from a {queried name: card} map, at the `_get`
    layer so the URL the code builds is exercised too."""
    seen = []

    def get(url):
        assert url.startswith(carddb.NAMED_URL + "?fuzzy="), url
        asked = carddb.urllib.parse.unquote(url.split("fuzzy=", 1)[1])
        seen.append(asked)
        card = resolutions.get(asked)
        if card is None:
            raise carddb.urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return json.dumps(card).encode()
    monkeypatch.setattr(carddb, "_get", get)
    return seen


# ── the verified row ─────────────────────────────────────────────────────────
def test_a_verified_row_carries_the_whole_contract(monkeypatch):
    fake_batch(monkeypatch, [SOL_RING])
    row, = carddb.verify_cards(["Sol Ring"], delay=0)
    assert set(row) == set(carddb.VERIFY_FIELDS)
    assert row["requested"] == "Sol Ring" and row["found"] is True
    assert row["name"] == "Sol Ring" and row["mana_cost"] == "{1}"
    assert row["type_line"] == "Artifact"
    assert row["oracle_text"] == "{T}: Add {C}{C}."      # verbatim, not paraphrased
    assert row["color_identity"] == "" and row["legal_commander"] is True
    assert (row["set"], row["collector_number"]) == ("LTC", "284")
    assert row["scryfall_uri"].startswith("https://scryfall.com/")
    assert row["reason"] == "" and row["source"] == "scryfall"


@pytest.mark.parametrize("card,expected", [
    (SOL_RING, True), (BLACK_LOTUS, False), (NO_LEGALITIES, None)])
def test_commander_legality_is_three_valued(monkeypatch, card, expected):
    """None means "Scryfall didn't say", which must never render as "not legal"."""
    fake_batch(monkeypatch, [card])
    row, = carddb.verify_cards([card["name"]], delay=0)
    assert row["legal_commander"] is expected


def test_dfc_text_is_joined_from_the_faces(monkeypatch):
    """No card-level oracle_text; both halves must survive, joined with ' // '."""
    fake_batch(monkeypatch, [ELITE_INTERCEPTOR])
    row, = carddb.verify_cards(["Elite Interceptor // Rejoinder"], delay=0)
    assert row["oracle_text"] == ("Vigilance. // Target creature gets +2/+2 until "
                                 "end of turn.")
    assert row["mana_cost"] == "{2}{W} // {1}{W}"
    assert row["type_line"] == "Creature — Human Soldier // Instant"


# ── resolution ───────────────────────────────────────────────────────────────
def test_a_batch_reconciles_positionally_around_a_miss(monkeypatch):
    """The regression this design exists for. Scryfall answers with `data` in
    identifier order and the misses listed separately, so slot 2 having produced
    nothing must shift slot 3's card — and slot 3 asked for a BACK FACE, whose card
    comes back named "Front // Back". Matching the response by name would leave the
    real card attached to the wrong request, or to none at all."""
    fake_batch(monkeypatch, [SOL_RING, ELITE_INTERCEPTOR],
               not_found=[{"name": "Totally Bogus Card"}])
    rows = carddb.verify_cards(["Sol Ring", "Totally Bogus Card", "Rejoinder"],
                               delay=0)
    assert [r["requested"] for r in rows] == ["Sol Ring", "Totally Bogus Card",
                                              "Rejoinder"]
    assert rows[0]["name"] == "Sol Ring"
    assert rows[1]["found"] is False
    assert rows[2]["found"] is True
    assert rows[2]["name"] == "Elite Interceptor // Rejoinder"


def test_a_misspelling_resolves_through_fuzzy_and_the_correction_is_surfaced(
        monkeypatch):
    calls = fake_exact(monkeypatch)
    asked = fake_fuzzy(monkeypatch, {"Sol Rng": SOL_RING})
    row, = carddb.verify_cards(["Sol Rng"], delay=0)
    assert calls and asked == ["Sol Rng"]
    assert row["found"] is True and row["source"] == "fuzzy"
    # `requested` keeps what was asked; `name` carries the canonical card, so the
    # correction is visible instead of silently swallowed.
    assert (row["requested"], row["name"]) == ("Sol Rng", "Sol Ring")


def test_a_back_face_name_resolves_through_the_fuzzy_path(monkeypatch):
    """"Rejoinder" is the back face of a card this collection actually holds. Exact
    matching rejects it; the one fuzzy retry finds the whole card."""
    fake_exact(monkeypatch)
    fake_fuzzy(monkeypatch, {"Rejoinder": ELITE_INTERCEPTOR})
    row, = carddb.verify_cards(["Rejoinder"], delay=0)
    assert row["name"] == "Elite Interceptor // Rejoinder"
    assert "Target creature gets +2/+2" in row["oracle_text"]


def test_a_name_nothing_resolves_is_unverified_not_invented(monkeypatch):
    """Where a hallucinated card name dies."""
    fake_exact(monkeypatch)
    fake_fuzzy(monkeypatch, {})
    row, = carddb.verify_cards(["Blightsteel Squirrel of Ravnica"], delay=0)
    assert row["found"] is False and row["name"] == ""
    assert "no Scryfall match" in row["reason"]


def test_a_network_failure_reports_unverified_and_does_not_raise(monkeypatch):
    """The report IS the product: an unreachable Scryfall must not raise, and must not
    silently answer from memory."""
    def die(identifiers, retries=4):
        raise OSError("proxy said no")
    monkeypatch.setattr(carddb, "_post_collection", die)
    monkeypatch.setattr(carddb, "_get", lambda url: (_ for _ in ()).throw(
        OSError("proxy said no")))
    rows = carddb.verify_cards(["Sol Ring", "Llanowar Elves"], delay=0)
    assert [r["found"] for r in rows] == [False, False]
    assert all("network unreachable" in r["reason"] for r in rows)


# ── the cache ────────────────────────────────────────────────────────────────
def test_a_second_verification_is_served_from_cache(monkeypatch):
    calls = fake_exact(monkeypatch)
    first, = carddb.verify_cards(["Sol Ring"], delay=0)
    second, = carddb.verify_cards(["Sol Ring"], delay=0)
    assert len(calls) == 1, "the cached card was re-fetched"
    assert second["source"] == "cache"
    assert second["oracle_text"] == first["oracle_text"]


def test_refresh_ignores_the_cache(monkeypatch):
    calls = fake_exact(monkeypatch)
    carddb.verify_cards(["Sol Ring"], delay=0)
    row, = carddb.verify_cards(["Sol Ring"], delay=0, refresh=True)
    assert len(calls) == 2 and row["source"] == "scryfall"


def test_an_expired_entry_is_refetched(monkeypatch, tmp_path):
    calls = fake_exact(monkeypatch)
    carddb.verify_cards(["Sol Ring"], delay=0)
    monkeypatch.setattr(carddb, "VERIFY_TTL", -1)   # everything is stale
    carddb.verify_cards(["Sol Ring"], delay=0)
    assert len(calls) == 2


def test_a_cache_file_written_for_another_card_is_never_served(monkeypatch, tmp_path):
    """The cache filename is a lossy slug of the key (card names carry ':' and '//'),
    so the key is stored inside the file and re-checked. A collision must read as a
    miss, never as another card's text."""
    cache = tmp_path / "scryfall"
    cache.mkdir(parents=True, exist_ok=True)
    key = carddb._verify_key("Sol Ring")
    with open(carddb._cache_path(key, str(cache)), "w", encoding="utf-8") as f:
        json.dump({"key": "some other card", "fetched": 9e9, "card": BLACK_LOTUS}, f)
    assert carddb._cache_get(key, str(cache)) is None


# ── CLI ──────────────────────────────────────────────────────────────────────
def _seed_cache(tmp_path, *cards):
    for c in cards:
        carddb._cache_put(carddb._verify_key(c["name"]), c,
                          str(tmp_path / "scryfall"))


def test_cli_prints_verbatim_text_from_a_pre_seeded_cache(tmp_path, monkeypatch,
                                                          capsys):
    """The offline acceptance case: with the cache warm, --verify answers with no
    network at all (urlopen is still booby-trapped)."""
    _seed_cache(tmp_path, SOL_RING, BLACK_LOTUS)
    monkeypatch.setattr("sys.argv", ["carddb.py", "--verify", "Sol Ring",
                                     "--verify", "Black Lotus"])
    assert carddb.main() == 0
    out = capsys.readouterr().out
    assert "{T}: Add {C}{C}." in out                      # verbatim oracle text
    assert "commander-legal: yes" in out and "commander-legal: NO" in out


def test_cli_json_carries_the_rows(tmp_path, monkeypatch, capsys):
    _seed_cache(tmp_path, SOL_RING)
    monkeypatch.setattr("sys.argv", ["carddb.py", "--verify", "Sol Ring", "--json"])
    assert carddb.main() == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["name"] for r in rows] == ["Sol Ring"]
    assert rows[0]["oracle_text"] == "{T}: Add {C}{C}."


def test_cli_reports_unverified_and_still_exits_zero(monkeypatch, capsys):
    """Exit 0 with an UNVERIFIED line: the agent needs the report, and a non-zero exit
    would read as "the tool broke" rather than "the card could not be confirmed"."""
    fake_exact(monkeypatch)
    fake_fuzzy(monkeypatch, {})
    monkeypatch.setattr("sys.argv", ["carddb.py", "--verify", "Not A Card At All"])
    assert carddb.main() == 0
    cap = capsys.readouterr()
    assert 'UNVERIFIED "Not A Card At All"' in cap.out
    assert "1/1 unverified" in cap.err


def test_enrichment_mode_still_requires_a_collection(monkeypatch):
    """--collection stopped being argparse-required when --verify arrived. enrich.bat
    and webapp/app.py's upload route both depend on the enrichment path demanding it."""
    monkeypatch.setattr("sys.argv", ["carddb.py", "--stats"])
    with pytest.raises(SystemExit) as e:
        carddb.main()
    assert e.value.code == 2


def test_bare_invocation_errors(monkeypatch):
    monkeypatch.setattr("sys.argv", ["carddb.py"])
    with pytest.raises(SystemExit) as e:
        carddb.main()
    assert e.value.code == 2


def test_the_two_modes_are_exclusive(monkeypatch, tmp_path):
    coll = tmp_path / "c.csv"
    coll.write_text("Quantity,Name\n1,Sol Ring\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["carddb.py", "--collection", str(coll),
                                     "--verify", "Sol Ring"])
    with pytest.raises(SystemExit) as e:
        carddb.main()
    assert e.value.code == 2
