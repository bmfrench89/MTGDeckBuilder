"""The two advisory engines added after real cards slipped past the optimizer:
new_arrivals ("I just scanned these — where do they go?") and field risers
(owned cards the anti-churn margin gate held back, e.g. a 30%-inclusion arrival
vs an 11% incumbent — a 19-point gain the 25-point gate rightly refuses to swap
but must not silently hide). Advisory means advisory: neither writes anything.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import mtglib
import deckcore
import optimize


# --------------------------------------------------------------------------- #
# Acquisition dates ride along from the export
# --------------------------------------------------------------------------- #
def test_loader_keeps_the_newest_acquisition_date():
    cards = {c.name: c for c in mtglib.parse_collection(
        "Quantity,Name,Date Bought\n"
        "1,Sol Ring,2026-01-05\n"
        "1,Sol Ring,2026-08-01\n"      # bought another copy later
        "1,Counterspell,\n")}
    assert cards["Sol Ring"].date_added == "2026-08-01", \
        "newest date across printings — 'when did I last add copies'"
    assert cards["Counterspell"].date_added == ""


# --------------------------------------------------------------------------- #
# new_arrivals
# --------------------------------------------------------------------------- #
DECK = """\
# Title: T
# Commander: Test Commander
# Colors: W U

# --- Commander ---
1 Test Commander

# --- Spells ---
1 Arcane Signet
"""


@pytest.fixture
def decks_dir(tmp_path):
    d = tmp_path / "decks"
    d.mkdir()
    (d / "testdeck.txt").write_text(DECK, encoding="utf-8")
    return str(d)


def _coll(rows):
    hdr = "Quantity,Name,Identities,Types,Date Bought\n"
    return mtglib.parse_collection(hdr + "".join(rows))


def test_new_arrivals_finds_recent_unused_cards_and_their_homes(decks_dir):
    coll = _coll([
        "1,Mana Drain,U,Instant,2026-08-05\n",          # recent, fits W-U deck
        "1,Lightning Bolt,R,Instant,2026-08-06\n",      # recent, off-color
        "1,Counterspell,U,Instant,2026-01-01\n",        # old news
        "1,Arcane Signet,,Artifact,2026-08-07\n",       # already in a deck
        "4,Island,U,Land,2026-08-07\n",                 # basics are noise
    ])
    out = deckcore.new_arrivals(coll, decks_dir, days=30, now="2026-08-10")
    names = [a["name"] for a in out]
    assert "Mana Drain" in names and "Lightning Bolt" in names
    assert "Counterspell" not in names, "outside the window"
    assert "Arcane Signet" not in names, "already in a deck"
    assert "Island" not in names, "basics never surface"
    md = next(a for a in out if a["name"] == "Mana Drain")
    assert md["fits"] == ["testdeck"], "identity U fits the W-U deck"
    lb = next(a for a in out if a["name"] == "Lightning Bolt")
    assert lb["fits"] == [], "red card has no home in a W-U stable"


def test_new_arrivals_degrades_on_the_nameonly_snapshot(decks_dir):
    """No dates in the export → empty list, never a crash or a guess."""
    coll = mtglib.parse_collection("2 Mana Drain\n1 Sol Ring\n")
    assert deckcore.new_arrivals(coll, decks_dir) == []


# --------------------------------------------------------------------------- #
# field risers — the gate reports what it suppressed
# --------------------------------------------------------------------------- #
RISER_COLL = (
    "Quantity,Name,Identities,Types\n"
    "1,Test Commander,W U,Legendary Creature\n"
    "1,Weak Incumbent,U,Instant\n"
    "1,New Hotness,U,Instant\n"        # 30% vs 11%: held by the gate → riser
    "1,Clear Upgrade,U,Instant\n"      # 45% vs 0%: clears the gate → real swap
    "1,Filler,U,Instant\n"
)

RISER_DECK = """\
# Title: R
# Commander: Test Commander
# Colors: W U

# --- Commander ---
1 Test Commander

# --- Spells ---
1 Weak Incumbent
1 Filler
"""


def test_risers_capture_gate_suppressed_upgrades_without_acting(tmp_path, monkeypatch):
    d = tmp_path / "decks"
    d.mkdir()
    p = d / "riser.txt"
    p.write_text(RISER_DECK, encoding="utf-8")
    coll = mtglib.parse_collection(RISER_COLL)
    idx = mtglib.index_by_name(coll)

    field = {"weak incumbent": 11, "new hotness": 30, "clear upgrade": 45, "filler": 0}
    monkeypatch.setattr(optimize.deck_fit, "load_field", lambda *a, **k: field)
    monkeypatch.setattr(optimize.deck_fit, "load_synergy", lambda *a, **k: {})
    # value == raw inclusion for this test: gate arithmetic is what's under test
    monkeypatch.setattr(optimize.deck_fit, "assess_card", lambda *a, **k: {"score": 0})

    before = p.read_text(encoding="utf-8")
    r = optimize.optimize(str(p), coll, idx, str(d))
    assert ("Filler", 0, "Clear Upgrade", 45, "free") in r["swaps"], \
        "a 45-point gain clears the gate — that's a swap, not a riser"
    adds = [z["add"] for z in r["risers"]]
    assert "New Hotness" in adds, "30 vs 11 is a 19-point gain: suppressed, so reported"
    assert "Clear Upgrade" not in adds, "swapped cards must not double as risers"
    z = next(z for z in r["risers"] if z["add"] == "New Hotness")
    assert z["over"] == "Weak Incumbent" and 0 < z["gap"] < 25
    assert p.read_text(encoding="utf-8") == before, "advisory means nothing was written"
