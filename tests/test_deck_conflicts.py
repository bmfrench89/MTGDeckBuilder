"""deck_conflicts.scan — cross-deck usage must aggregate by PHYSICAL card.

Regression: usage was keyed by the raw deck-file spelling, so 'Fire // Ice' in
one deck and 'Fire' in another split into two entries that each looked covered —
a real conflict (2 committed, 1 owned) silently vanished."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import deck_conflicts
import mtglib


def _decks(tmp_path):
    (tmp_path / "a.txt").write_text(
        "# Title: A\n# Commander: X\n\n# --- Spells ---\n1 Fire // Ice\n",
        encoding="utf-8")
    (tmp_path / "b.txt").write_text(
        "# Title: B\n# Commander: Y\n\n# --- Spells ---\n1 Fire\n",
        encoding="utf-8")
    return str(tmp_path)


def test_scan_merges_front_face_spellings_into_one_conflict(tmp_path):
    coll = [mtglib.Card(name="Fire // Ice", quantity=1)]
    idx = mtglib.index_by_name(coll)
    usage = deck_conflicts.scan(_decks(tmp_path), idx)
    entries = [u for n, u in usage.items() if "fire" in n.lower()]
    assert len(entries) == 1, "one physical card = one usage entry"
    assert entries[0]["total"] == 2 and entries[0]["owned"] == 1
    conf = deck_conflicts.conflicts(usage)
    assert any("fire" in c["card"].lower() for c in conf), \
        "2 committed vs 1 owned must surface as a conflict"


def test_available_pool_sees_front_face_commitments(tmp_path):
    coll = [mtglib.Card(name="Fire // Ice", quantity=2),
            mtglib.Card(name="Sol Ring", quantity=1)]
    idx = mtglib.index_by_name(coll)
    usage = deck_conflicts.scan(_decks(tmp_path), idx)
    rows = {r[0]: r for r in deck_conflicts.available_pool(usage, coll)}
    assert "Fire // Ice" not in rows or rows["Fire // Ice"][3] == 0, \
        "both copies are committed; none is free"
    assert rows["Sol Ring"][3] == 1
