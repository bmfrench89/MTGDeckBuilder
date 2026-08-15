"""Shared fixtures. Tests are offline and never touch the player's real data —
every deck/collection used here is written into pytest's tmp_path."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "webapp"))


@pytest.fixture(autouse=True, scope="session")
def _goldfish_cache_in_tmp(tmp_path_factory):
    """The dashboard and the assess surfaces self-compute a goldfish sim, and that
    helper writes a disk cache. Point it at tmp for the whole session so the suite
    never writes into the player's real `data/cache/` — the same hermetic rule every
    other fixture here follows."""
    import goldfish
    goldfish.CACHE_DIR = str(tmp_path_factory.mktemp("goldfish-cache"))


@pytest.fixture(autouse=True, scope="session")
def _enrich_status_in_tmp(tmp_path_factory):
    """Same hermetic rule for the background-enrichment status file: any test that
    exercises `/collection/upload` starts a real (fake-enrich) run, and its status
    JSON would otherwise land in the player's real `data/cache/`."""
    import enrich_bg
    enrich_bg.STATUS = str(tmp_path_factory.mktemp("enrich") / "enrich_status.json")


@pytest.fixture(autouse=True)
def _clean_memo():
    """Start (and leave) every test with an empty analysis memo.

    `memo` is process-global by design — that is what makes it work across
    requests in one web-app worker. In a test process it would also carry state
    across tests, so a suite that passes in file order could fail in isolation
    (or vice versa), which is exactly the kind of ghost this repo's hermetic rule
    exists to prevent. `tests/test_memo.py` opts back in explicitly by populating
    it inside a single test."""
    import memo
    memo.invalidate()
    yield
    memo.invalidate()


@pytest.fixture(autouse=True)
def _no_network_and_no_real_cache(monkeypatch, tmp_path_factory):
    """Hard-stop the network clients for EVERY test, and move their caches to tmp.

    `optimize` reaches EDHREC through `deck_fit.load_field_lands` →
    `edhrec.land_names` → `_fetch`, which `os.makedirs`es and writes into the
    REAL `data/cache/edhrec/`. Individual tests were expected to monkeypatch
    that, and mostly did not (1 of 17 call sites before this fixture): in this
    sandbox the proxy blocks the fetch so it degrades to empty and the suite
    passes, but on the player's PC or a GitHub runner the same suite would hit
    EDHREC and write into the player's real `data/`. That is the hermetic rule
    in CLAUDE.md, so it is enforced here once rather than trusted 17 times.

    A test that WANTS field data still monkeypatches `deck_fit.load_field` /
    `load_synergy` (the established pattern) — those are pure lookups this
    fixture does not touch.
    """
    import edhrec
    cache = tmp_path_factory.mktemp("edhrec-cache")
    monkeypatch.setattr(edhrec, "CACHE_DIR", str(cache), raising=False)

    def _blocked(*_a, **_kw):
        raise AssertionError(
            "a test tried to reach EDHREC over the network — monkeypatch "
            "deck_fit.load_field / load_synergy (or edhrec.<fn>) instead")
    # The real function stays reachable under a second name, for the one test that
    # is ABOUT `_fetch` itself (the failure-cooldown guard). It monkeypatches
    # `urllib.request.urlopen` instead, so it is still offline — it just needs the
    # function this fixture is standing in front of.
    monkeypatch.setattr(edhrec, "_fetch_unblocked", edhrec._fetch, raising=False)
    monkeypatch.setattr(edhrec, "_fetch", _blocked, raising=False)


DECK_TEXT = """\
# Title: Test Deck
# Commander: Test Commander
# Colors: W U
# Archetype: control

# --- Commander ---
1 Test Commander

# --- Ramp ---
1 Sol Ring
2 Arcane Signet

# --- Lands ---
10 Island
1 Command Tower
"""

# Header names match the "card attribute" export flavor mtglib.load_collection reads.
COLLECTION_CSV = """\
Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,MARKET
1,Sol Ring,1,,,{1},Artifact,,uncommon,aaaa1111,1.50
2,Arcane Signet,2,,,{2},Artifact,,common,bbbb2222,0.90
1,Counterspell,2,U,U,{U}{U},Instant,,common,cccc3333,0.75
1,Swords to Plowshares,1,W,W,{W},Instant,,uncommon,dddd4444,2.00
1,Command Tower,0,,,,Land,,common,eeee5555,0.50
12,Island,0,,,,Land,Island,common,ffff6666,0.10
1,Serra Angel,5,W,W,{3}{W}{W},Creature,Angel,uncommon,7777aaaa,0.30
1,Test Commander,4,W U,W U,{2}{W}{U},Legendary Creature,Human Wizard,rare,8888bbbb,1.00
1,Llanowar Elves,1,G,G,{G},Creature,Elf Druid,common,9999cccc,0.25
"""


@pytest.fixture
def deck_file(tmp_path):
    p = tmp_path / "testdeck.txt"
    p.write_text(DECK_TEXT, encoding="utf-8")
    return str(p)


@pytest.fixture
def collection_file(tmp_path):
    p = tmp_path / "collection.csv"
    p.write_text(COLLECTION_CSV, encoding="utf-8")
    return str(p)


@pytest.fixture
def big_collection_file(tmp_path):
    """A pool deep enough for the auto-builder to actually fill a 99 (plus a few
    off-color cards it must refuse to use)."""
    rows = ["Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,MARKET",
            "1,Test Commander,4,W U,W U,{2}{W}{U},Legendary Creature,Human Wizard,rare,cmd00000,1.00"]
    for i in range(40):                                    # in-color spells
        rows.append(f"1,Test Spell {i},{i % 6},U,U,{{{i % 6}}}{{U}},Instant,,common,sp{i:06d},0.10")
    for i in range(40):                                    # in-color creatures
        rows.append(f"1,Test Bear {i},{(i % 5) + 1},W,W,{{{i % 5}}}{{W}},Creature,Bear,common,cr{i:06d},0.10")
    for i in range(30):                                    # in-color nonbasic lands
        rows.append(f"1,Test Land {i},0,,,,Land,,common,ld{i:06d},0.10")
    for i in range(10):                                    # OFF-color — must never appear
        rows.append(f"1,Green Thing {i},2,G,G,{{1}}{{G}},Creature,Elf,common,gn{i:06d},0.10")
    rows.append("40,Island,0,,,,Land,Island,common,isl00000,0.10")
    rows.append("40,Plains,0,,,,Land,Plains,common,pln00000,0.10")
    p = tmp_path / "big_collection.csv"
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return str(p)


def print_block(html):
    """The generated dashboard's whole `@media print { … }` body, brace-matched.

    Tests used to slice a fixed window after the marker (`[:200]`, `[:400]`), which
    made them a hostage to rule ORDER: adding a comment or a rule at the top of the
    block pushed the thing under test out of the window and failed a green change.
    Worse, a windowed substring is only evidence that a STRING is present — which is
    how `.explain > p { display:block }` sat here passing while doing nothing on
    paper. Matching the real block lets a test assert against every rule in it.
    """
    i = html.index("@media print")
    start = html.index("{", i)
    depth = 0
    for j in range(start, len(html)):
        if html[j] == "{":
            depth += 1
        elif html[j] == "}":
            depth -= 1
            if depth == 0:
                return html[start + 1:j]
    raise AssertionError("@media print block is not brace-balanced")
