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
