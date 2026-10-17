"""Deck UAT: the goldfish turned into acceptance gates (docs/spec-deck-uat.md).

A deck file, its notes and a collection are written into tmp_path, then run through
the real sim at a few hundred games. The gates must pass an engine that can be cast and
fail one that can't. A missing engine list must fail and say why, never pass quietly.
The A/B must stay exactly zero for an identical swap, which is the same common random
numbers tripwire as test_goldfish. Everything is hermetic."""
import json

import pytest

import deck_uat
import engine_spec
import mtglib
import optimize

ENGINE = [f"Engine {i}" for i in range(10)]


def _write(tmp_path, engine_mv=1, commander_mv=2, notes=True, extra=()):
    rows = ["Quantity,Name,Identities,Types,Sub-types,Mana cost,Mana Value",
            f"1,Test Commander,G,Legendary Creature,Elf,{{{commander_mv - 1}}}{{G}},"
            f"{commander_mv}",
            "40,Forest,G,Basic Land,Forest,,0",
            "1,Spare Card,G,Creature,Elf,{2}{G},3"]
    cost = "{G}" if engine_mv == 1 else f"{{{engine_mv - 1}}}{{G}}"
    rows += [f"1,{n},G,Creature,Elf,{cost},{engine_mv}" for n in ENGINE]
    rows += [f"1,Filler {i},G,Creature,Elf,{{2}}{{G}},3" for i in range(52)]
    rows += list(extra)
    coll = tmp_path / "coll.csv"
    coll.write_text("\n".join(rows) + "\n", encoding="utf-8")
    deck = tmp_path / "test-deck.txt"
    lines = ["# Title: T", "# Commander: Test Commander", "", "# --- Commander ---",
             "1 Test Commander", "", "# --- Creatures ---"]
    lines += [f"1 {n}" for n in ENGINE] + [f"1 Filler {i}" for i in range(52)]
    lines += ["", "# --- Lands ---", "37 Forest"]
    deck.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if notes:
        (tmp_path / "test-deck.notes.md").write_text(
            "## Protected engine\n" + "".join(f"- {n}\n" for n in ENGINE),
            encoding="utf-8")
    return str(deck), str(coll)


def _gate(rep, gid):
    return next(g for g in rep["gates"] if g["id"] == gid)


def test_a_castable_engine_passes(tmp_path):
    deck, coll = _write(tmp_path, engine_mv=1)
    rep = deck_uat.run(deck, mtglib.load_collection(coll), games=300)
    assert rep["engine_source"] == "notes" and rep["engine_cards"] == 10
    # 10 one-drops in 99 cards: ~76% of games see one by turn 6 (hypergeometric), so
    # the measured rate sits in the 60s-70s and clears the 50% bar.
    assert 0.6 < _gate(rep, "engine_online")["value"] < 0.85 and rep["pass"]


def test_an_engine_that_cannot_land_in_time_fails(tmp_path):
    deck, coll = _write(tmp_path, engine_mv=8)
    rep = deck_uat.run(deck, mtglib.load_collection(coll), games=300)
    g = _gate(rep, "engine_online")
    assert g["value"] == 0.0 and not g["pass"] and not rep["pass"]


def test_no_engine_list_fails_and_says_why(tmp_path):
    deck, coll = _write(tmp_path, notes=False)
    rep = deck_uat.run(deck, mtglib.load_collection(coll), games=200)
    g = _gate(rep, "engine_online")
    assert g["value"] is None and not g["pass"] and "no engine cards" in g["verdict"]


def test_a_big_commander_is_informational_until_the_spec_gates_it(tmp_path):
    deck, coll = _write(tmp_path, commander_mv=8)
    rep = deck_uat.run(deck, mtglib.load_collection(coll), games=200)
    g = _gate(rep, "commander_on_time")
    assert g.get("info") and g["pass"]
    engine_spec.main(["--deck", deck, "--init", "--uat", "commander_turn", "8",
                      "--uat", "commander_pct", "99"])
    rep = deck_uat.run(deck, mtglib.load_collection(coll), games=200)
    g = _gate(rep, "commander_on_time")
    assert not g.get("info") and not g["pass"], "a spec target makes it a real gate"


def test_spec_targets_override_the_defaults(tmp_path):
    deck, coll = _write(tmp_path, engine_mv=1)
    engine_spec.main(["--deck", deck, "--init", "--uat", "engine_pct", "100",
                      "--uat", "engine_turn", "1", "--uat", "engine_min", "10"])
    assert engine_spec.load(deck)["uat"] == {"engine_pct": 100, "engine_turn": 1,
                                            "engine_min": 10}
    rep = deck_uat.run(deck, mtglib.load_collection(coll), games=200)
    assert not _gate(rep, "engine_online")["pass"]


def test_engine_min_scales_with_the_list():
    assert deck_uat.engine_min({}, 6) == 1
    assert deck_uat.engine_min({}, 24) == 1
    assert deck_uat.engine_min({}, 38) == 2
    assert deck_uat.engine_min({"engine_min": 3}, 6) == 3


def test_ab_of_a_card_with_itself_is_exactly_zero(tmp_path):
    deck, coll = _write(tmp_path)
    res = deck_uat.ab(deck, mtglib.load_collection(coll), "Engine 0", "Engine 0",
                      games=300)
    assert all(d["delta"] == 0.0 and d["ci95"] == 0.0 for d in res["deltas"].values())


def test_ab_cutting_an_engine_card_never_helps_the_engine(tmp_path):
    deck, coll = _write(tmp_path, engine_mv=3)
    res = deck_uat.ab(deck, mtglib.load_collection(coll), "Engine 0", "Spare Card",
                      games=400)
    assert res["deltas"]["engine_online"]["delta"] <= 0
    assert "engine online" in deck_uat.ab_summary(res)


def test_ab_refuses_what_goldfish_refuses(tmp_path):
    deck, coll = _write(tmp_path)
    res = deck_uat.ab(deck, mtglib.load_collection(coll), "Engine 0", "Filler 3")
    assert "singleton" in res["error"]
    res = deck_uat.ab(deck, mtglib.load_collection(coll), "Engine 0", "Never Printed")
    assert "Can't resolve" in res["error"]


def test_ab_can_swap_in_a_basic_the_collection_never_lists(tmp_path):
    """Basics are always owned and the export leaves them out (grounding rule 9), and a
    deck already runs dozens, so neither the lookup nor the singleton guard may refuse
    one. Found 2026-10-15: every optimizer land swap into a Swamp came back
    "Can't resolve"."""
    deck, coll = _write(tmp_path)
    c = mtglib.load_collection(coll)
    res = deck_uat.ab(deck, c, "Filler 0", "Snow-Covered Forest", games=200)
    assert not res.get("error") and res["in"] == "Snow-Covered Forest"
    res = deck_uat.ab(deck, c, "Filler 1", "Forest", games=200)
    assert not res.get("error"), "a basic the deck already runs is no singleton break"
    assert res["deltas"]["screw"]["delta"] <= 0, "one more land never screws more"


def test_the_cli_exits_3_on_a_failed_gate(tmp_path, capsys):
    deck, coll = _write(tmp_path, engine_mv=8)
    assert deck_uat.main(["--deck", deck, "--collection", coll, "--games", "200"]) == 3
    assert "FAIL" in capsys.readouterr().out
    deck2, coll2 = _write(tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path,
                          engine_mv=1)
    assert deck_uat.main(["--deck", deck2, "--collection", coll2, "--games", "200",
                          "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["pass"] is True


def test_uat_targets_are_written_through_the_cli_only_with_known_keys(tmp_path):
    deck, _coll = _write(tmp_path)
    engine_spec.main(["--deck", deck, "--init"])
    assert engine_spec.main(["--deck", deck, "--uat", "vibes", "9"]) == 2
    assert engine_spec.main(["--deck", deck, "--uat", "engine_pct", "lots"]) == 2
    assert engine_spec.load(deck)["uat"] == {}


def test_uat_keys_match_the_gate_defaults():
    assert set(engine_spec.UAT_KEYS) == set(deck_uat.DEFAULTS)


def test_dina_style_bold_bullets_parse_to_card_names():
    notes = ("## Protected cards — do not let the optimizer cut these\n"
             "- **Seal of Doom**, **Nameless Inversion** — added to close a deficit\n"
             "- **Jadar, Ghoulcaller of Nephalia** — the recursion\n"
             "- Mjölnir, Hammer of Thor — 4 damage on ETB\n"
             "- Kid Loki\n")
    assert engine_spec.protected_engine_from_notes(notes) == [
        "Seal of Doom", "Nameless Inversion", "Jadar, Ghoulcaller of Nephalia",
        "Mjölnir, Hammer of Thor", "Kid Loki"]


def test_optimize_attaches_an_ab_to_every_proposal(monkeypatch):
    calls = []

    def fake_ab(deck, coll, out_name, in_name, **kw):
        calls.append((out_name, in_name))
        if in_name == "Bad":
            return {"error": "refused"}
        return {"games": 10, "deltas": {
            "engine_online": {"delta": 0.05, "ci95": 0.01, "a": 0.5, "b": 0.55},
            "commander_on_time": {"delta": 0.0, "ci95": 0.0, "a": 0.5, "b": 0.5},
            "keepable": {"delta": 0.0, "ci95": 0.0, "a": 0.8, "b": 0.8},
            "screw": {"delta": 0.0, "ci95": 0.0, "a": 0.1, "b": 0.1}}}

    monkeypatch.setattr(deck_uat, "ab", fake_ab)
    payload = {"proposals": [{"cut": "Old", "add": "New"}, {"cut": "Old2", "add": "Bad"}]}
    optimize.attach_ab(payload, "d.txt", [], games=10)
    good, bad = payload["proposals"]
    assert good["ab"]["engine_online"]["delta"] == 0.05
    assert "+5.0%" in good["ab_summary"]
    assert bad["ab_error"] == "refused" and "ab" not in bad
    assert calls == [("Old", "New"), ("Old2", "Bad")]


def test_all_covers_the_lab_and_tags_it(tmp_path, capsys):
    """`--all` skipped theory decks until 2026-10-16, so the Lab never got a test run."""
    deck, coll = _write(tmp_path, engine_mv=1)
    text = open(deck, encoding="utf-8").read().replace("# Title: T\n",
                                                       "# Title: T\n# Study: yes\n", 1)
    (tmp_path / "lab-deck.txt").write_text(text, encoding="utf-8")
    (tmp_path / "lab-deck.notes.md").write_text(
        (tmp_path / "test-deck.notes.md").read_text(encoding="utf-8"), encoding="utf-8")
    args = ["--all", "--decks-dir", str(tmp_path), "--collection", coll, "--games", "200"]
    assert deck_uat.main(args + ["--json"]) == 0
    reps = {r["deck"]: r for r in json.loads(capsys.readouterr().out)}
    assert set(reps) == {"test-deck", "lab-deck"}
    assert reps["lab-deck"]["lab"] is True and reps["test-deck"]["lab"] is False
    deck_uat.main(args)
    out = capsys.readouterr().out
    assert "lab-deck [Lab]" in out and "(1 of them in the Lab)" in out
