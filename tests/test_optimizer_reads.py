"""Phase C of docs/spec-optimizer-judgment.md: the session is the judgment layer.

`reads` are owned, free, in-colour cards EDHREC doesn't list for the commander — cards
the optimizer can never PROPOSE (every proposal comes from the field's list), offered
for a Claude session's read instead. `--json` is the session's feed; `--approve`
writes only what the player approved."""
import json
import sys

import mtglib

COLL = """\
Quantity,Name,Identities,Types,Sub-types,Mana cost,Mana Value
1,Test Commander,R G,Legendary Creature,Dragon,{R}{G},2
1,In Deck Spell,R,Instant,,{R},1
1,Field Listed Spell,R,Instant,,{R},1
1,Rare Field Spell,G,Instant,,{G},1
1,Silent Draw A,R,Sorcery,,{1}{R},2
1,Silent Draw B,R,Sorcery,,{1}{R},2
1,Silent Draw C,R,Sorcery,,{1}{R},2
1,Silent Draw D,R,Sorcery,,{1}{R},2
1,Silent Ramp,G,Sorcery,,{1}{G},2
1,Silent Low Fit,G,Sorcery,,{1}{G},2
1,Off Colour Gem,U,Instant,,{U},1
1,Only Copy Elsewhere,G,Instant,,{G},1
1,Silent Land,R G,Land,,,0
"""

DECK = """\
# Title: R
# Commander: Test Commander
# Colors: R G

# --- Commander ---
1 Test Commander

# --- Instants ---
1 In Deck Spell

# --- Basics ---
10 Mountain
"""

OTHER = """\
# Title: O
# Commander: Test Commander
# Colors: R G

# --- Commander ---
1 Test Commander

# --- Instants ---
1 Only Copy Elsewhere
"""

FIT = {"Rare Field Spell": 95, "Silent Draw A": 90, "Silent Draw B": 89, "Silent Draw C": 88, "Silent Draw D": 87,
       "Silent Ramp": 80, "Silent Low Fit": 40, "Off Colour Gem": 99,
       "Only Copy Elsewhere": 99, "Field Listed Spell": 99}
ROLE = {"Silent Draw A": "draw", "Silent Draw B": "draw", "Silent Draw C": "draw",
        "Silent Draw D": "draw", "Silent Ramp": "ramp"}


def _setup(tmp_path, monkeypatch):
    import optimize
    d = tmp_path / "rd"
    d.mkdir(exist_ok=True)
    (d / "collection.csv").write_text(COLL, encoding="utf-8")
    (d / "deck.txt").write_text(DECK, encoding="utf-8")
    (d / "other.txt").write_text(OTHER, encoding="utf-8")
    field = {"in deck spell": 40, "field listed spell": 30, "rare field spell": 10,
             "mountain": 90}
    monkeypatch.setattr(optimize.deck_fit, "load_field", lambda *a, **k: field)
    monkeypatch.setattr(optimize.deck_fit, "load_field_lands", lambda *a, **k: set())
    monkeypatch.setattr(optimize.deck_fit, "load_synergy", lambda *a, **k: {})
    real_assess = optimize.deck_fit.assess_card
    monkeypatch.setattr(optimize.deck_fit, "assess_card",
                        lambda ref, *a, **k: {"score": FIT.get(ref.name, 50)}
                        if ref.name in FIT or ref.name.startswith("Silent")
                        else real_assess(ref, *a, **k))
    real_primary = optimize.deck_fit.primary_role
    monkeypatch.setattr(optimize.deck_fit, "primary_role",
                        lambda c: ROLE.get(c.name) or real_primary(c))
    coll = mtglib.load_collection(str(d / "collection.csv"))
    return d, coll, mtglib.index_by_name(coll)


def test_reads_are_owned_free_in_colour_and_field_silent(tmp_path, monkeypatch):
    import optimize
    d, coll, idx = _setup(tmp_path, monkeypatch)
    r = optimize.optimize(str(d / "deck.txt"), coll, idx, str(d))
    names = [x["name"] for x in r["reads"]]
    assert "Field Listed Spell" not in names, "field-listed cards are proposals' business"
    assert "In Deck Spell" not in names
    assert "Off Colour Gem" not in names, "outside the identity"
    assert "Only Copy Elsewhere" not in names, "no free copy"
    assert "Silent Land" not in names, "lands belong to the mana pass"
    assert "Silent Ramp" in names


def test_a_card_the_field_lists_rarely_is_a_read_not_lost(tmp_path, monkeypatch):
    """Enlightened Tutor (10% for the Ur-Dragon) fell through every net on 2026-10-14:
    under the margin, so no proposal; under RISER_FLOOR, so no riser; on the field's
    list, so no read. A rarely-listed owned card is now a read, with its field %."""
    import optimize
    d, coll, idx = _setup(tmp_path, monkeypatch)
    r = optimize.optimize(str(d / "deck.txt"), coll, idx, str(d))
    rare = [x for x in r["reads"] if x["name"] == "Rare Field Spell"]
    assert rare and rare[0]["field"] == 10
    silent = [x for x in r["reads"] if x["name"] == "Silent Ramp"]
    assert silent and silent[0]["field"] is None
    assert "Field Listed Spell" not in {x["name"] for x in r["reads"]}, ">= RISER_FLOOR"


def test_reads_cap_each_role_and_drop_low_fit(tmp_path, monkeypatch):
    import optimize
    d, coll, idx = _setup(tmp_path, monkeypatch)
    r = optimize.optimize(str(d / "deck.txt"), coll, idx, str(d))
    names = [x["name"] for x in r["reads"]]
    draws = [n for n in names if n.startswith("Silent Draw")]
    assert draws == ["Silent Draw A", "Silent Draw B", "Silent Draw C"], \
        "at most READS_PER_ROLE per role, best fit first"
    assert "Silent Low Fit" not in names, "below READS_MIN_FIT"


def test_reads_never_become_swaps(tmp_path, monkeypatch):
    import optimize
    d, coll, idx = _setup(tmp_path, monkeypatch)
    r = optimize.optimize(str(d / "deck.txt"), coll, idx, str(d))
    read_names = {x["name"] for x in r["reads"]}
    assert not read_names & {s[2] for s in r["swaps"]}
    assert not any(p["add"] in read_names for p in optimize.proposals(r))


def test_json_is_the_review_feed_and_never_writes(tmp_path, monkeypatch, capsys):
    import optimize
    d, _coll, _idx = _setup(tmp_path, monkeypatch)
    before = (d / "deck.txt").read_text(encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["optimize.py", "--deck", str(d / "deck.txt"),
                                      "--collection", str(d / "collection.csv"),
                                      "--decks-dir", str(d), "--json"])
    assert optimize.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert {"proposals", "reads", "risers", "buys", "land_guard"} <= set(payload)
    assert any(x["name"] == "Silent Ramp" for x in payload["reads"])
    assert (d / "deck.txt").read_text(encoding="utf-8") == before
    monkeypatch.setattr(sys, "argv", sys.argv + ["--apply"])
    assert optimize.main() == 2, "--json with --apply is refused"


def test_approve_writes_only_the_named_proposal(tmp_path, monkeypatch, capsys):
    import optimize
    d, coll, idx = _setup(tmp_path, monkeypatch)
    r = {"swaps": [("In Deck Spell", 1, "Field Listed Spell", 30, "free")],
         "swaps_detail": [], "land_swaps": [], "role_ranges": {}, "buy_swaps": []}
    monkeypatch.setattr(optimize, "optimize", lambda *a, **k: r)
    key = optimize.proposal_key("spell", "In Deck Spell", "Field Listed Spell")
    monkeypatch.setattr(sys, "argv", ["optimize.py", "--deck", str(d / "deck.txt"),
                                      "--collection", str(d / "collection.csv"),
                                      "--decks-dir", str(d), "--approve", key,
                                      "--approve", "spell|Nope|Never"])
    assert optimize.main() == 0
    out = capsys.readouterr().out
    assert "applied  In Deck Spell  ->  Field Listed Spell" in out
    assert "not proposed now, skipped: spell|Nope|Never" in out
    text = (d / "deck.txt").read_text(encoding="utf-8")
    assert "1 Field Listed Spell" in text and "In Deck Spell" not in text


def test_review_payload_is_json_safe():
    import optimize
    r = {"stem": "x", "commander": "C", "field_size": 3,
         "swaps": [("A", 5, "B", 60, "free")],
         "swaps_detail": [{"cut": "A", "add": "B", "cut_inc": 5, "add_inc": 60,
                           "cut_field_known": True, "add_field_known": True}],
         "land_swaps": [], "reads": [{"name": "R", "fit": 80, "role": "draw"}],
         "buy_swaps": [("A", 5, "Z", 70, "spell")], "role_ranges": {"draw": (8, 12)}}
    p = optimize.review_payload(r)
    json.dumps(p)
    assert p["buys"] == [{"add": "Z", "add_inc": 70, "replaces": "A", "kind": "spell"}]
    assert p["role_ranges"] == {"draw": [8, 12]}


def test_json_all_stays_parseable_with_a_study_deck(tmp_path, monkeypatch, capsys):
    """`--all` announces skipped study copies; under --json that note goes to stderr,
    or a session's `json.load` of the whole run fails (2026-10-14)."""
    import optimize
    d, _coll, _idx = _setup(tmp_path, monkeypatch)
    (d / "study.txt").write_text(OTHER.replace("# Title: O", "# Title: S\n# Study: yes"),
                                 encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["optimize.py", "--all", "--decks-dir", str(d),
                                      "--collection", str(d / "collection.csv"), "--json"])
    assert optimize.main() == 0
    cap = capsys.readouterr()
    payload = json.loads(cap.out)
    assert isinstance(payload, list) and "skip study copy: study.txt" in cap.err
