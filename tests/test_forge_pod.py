"""The household pod (scripts/forge_pod.py, docs/spec-forge-pod.md).

Hermetic: a tiny fake Forge card archive and the decks live in tmp_path, and Forge itself
never runs. Forge's real output is a recorded fixture (a 4-seat game run 2026-10-17 on
Forge 2.0.15). These tests pin the things that would silently lie:
- a timed-out game names every survivor a winner, and must count as abandoned;
- two-faced cards must be exported by their front face (split cards keep "A // B"),
  or Forge treats them as unknown and the deck plays short;
- an unsupported card is reported, never dropped quietly;
- the schedule keeps games even and rotates seats.
"""
import collections
import json
import re
import zipfile

import pytest

import forge_pod

REAL_GAME = """Simulation mode
Ai(1)-kami-of-the-crescent-moon vs Ai(2)-tinybones-bauble-burglar vs Ai(3)-vaevictis-asmadi-the-dire vs Ai(4)-tom-bert-and-william - one game of Commander seed 7
Game Outcome: Match Duration 0m : 35s
Game Outcome: Turn 26
Game Outcome: Ai(1)-kami-of-the-crescent-moon has lost because life total reached 0
Game Outcome: Ai(2)-tinybones-bauble-burglar has won because all opponents have lost
Game Outcome: Ai(3)-vaevictis-asmadi-the-dire has lost because life total reached 0
Game Outcome: Ai(4)-tom-bert-and-william has lost because life total reached 0
Match Result: Ai(1)-kami-of-the-crescent-moon: 0 Ai(2)-tinybones-bauble-burglar: 1 Ai(3)-vaevictis-asmadi-the-dire: 0 Ai(4)-tom-bert-and-william: 0

Game Result: Game 1 ended in 36452 ms. Ai(2)-tinybones-bauble-burglar has won!
"""
SEATS = ["kami-of-the-crescent-moon", "tinybones-bauble-burglar",
         "vaevictis-asmadi-the-dire", "tom-bert-and-william"]


def _zip(tmp_path, scripts):
    path = tmp_path / "cardsfolder.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in scripts.items():
            zf.writestr(name, text)
    return str(path)


SCRIPTS = {
    "s/sol_ring.txt": "Name:Sol Ring\nManaCost:1\nTypes:Artifact\n",
    "f/fire_ice.txt": "Name:Fire\nAlternateMode:Split\nALTERNATE\nName:Ice\n",
    "s/studious_first_year.txt": ("Name:Studious First-Year\nAlternateMode:Modal\n"
                                  "ALTERNATE\nName:Rampant Growth\n"),
    "s/scroll_rack.txt": "Name:Scroll Rack\nAI:RemoveDeck:All\n",
    "l/lim_duls_vault.txt": "Name:Lim-Dûl's Vault\n",
    "c/commander_guy.txt": "Name:Commander Guy\n",
    "s/swamp.txt": "Name:Swamp\n",
}


def test_names_follow_forge_split_keeps_both_halves_modal_uses_the_front(tmp_path):
    idx = forge_pod.forge_index(_zip(tmp_path, SCRIPTS))
    assert forge_pod.forge_name("Fire // Ice", idx)[0] == "Fire // Ice"
    assert forge_pod.forge_name("Studious First-Year // Rampant Growth", idx)[0] == \
        "Studious First-Year", "Forge names a modal card by its front face"
    assert forge_pod.forge_name("Rampant Growth", idx)[0] == "Studious First-Year"
    assert forge_pod.forge_name("lim-dul's vault", idx)[0] == "Lim-Dûl's Vault", \
        "case and accents fold, as Forge's lookup does"
    assert forge_pod.forge_name("Scroll Rack", idx) == ("Scroll Rack", True)
    assert forge_pod.forge_name("Never Printed", idx) is None


def test_export_puts_the_commander_first_and_reports_what_forge_cannot_play(tmp_path):
    idx = forge_pod.forge_index(_zip(tmp_path, SCRIPTS))
    deck = tmp_path / "test-deck.txt"
    deck.write_text("# Title: Test Deck\n# Commander: Commander Guy\n\n"
                    "# --- Commander ---\n1 Commander Guy\n\n# --- Artifacts ---\n"
                    "1 Sol Ring\n1 Scroll Rack\n\n# --- Creatures ---\n"
                    "1 Studious First-Year // Rampant Growth\n1 Never Printed\n\n"
                    "# --- Basics ---\n30 Swamp\n", encoding="utf-8")
    d = forge_pod.export_deck(str(deck), idx)
    lines = d["dck"].splitlines()
    assert lines[:4] == ["[metadata]", "Name=test-deck", "[Commander]", "1 Commander Guy"]
    assert "[Main]" in lines and "1 Studious First-Year" in lines and "30 Swamp" in lines
    assert "1 Commander Guy" not in lines[lines.index("[Main]"):], "commander only once"
    assert d["unsupported"] == ["Never Printed"], "reported, never dropped quietly"
    assert d["ai_flagged"] == ["Scroll Rack"]
    assert d["cards"] == 34 and d["stem"] == "test-deck" and d["title"] == "Test Deck"


def test_parse_reads_a_real_game():
    g = forge_pod.parse_game(REAL_GAME, SEATS)
    assert g["winner"] == "tinybones-bauble-burglar" and g["abandoned"] is None
    assert g["turn"] == 26 and g["seconds"] == 36.452
    assert g["outcomes"]["kami-of-the-crescent-moon"] == "has lost because life total reached 0"


def test_a_timed_out_game_is_abandoned_not_won_by_every_survivor():
    out = REAL_GAME.replace(
        "Game Outcome: Match Duration", "Stopping slow match as draw\nGame Outcome: Match Duration"
    ).replace("Ai(3)-vaevictis-asmadi-the-dire has lost because life total reached 0",
              "Ai(3)-vaevictis-asmadi-the-dire has won because all opponents have lost")
    g = forge_pod.parse_game(out, SEATS)
    assert g["winner"] is None and "timed out" in g["abandoned"]
    two_winners = REAL_GAME.replace(
        "Ai(1)-kami-of-the-crescent-moon has lost because life total reached 0",
        "Ai(1)-kami-of-the-crescent-moon has won because all opponents have lost")
    assert forge_pod.parse_game(two_winners, SEATS)["abandoned"] == "more than one winner reported"


def test_load_failures_draws_and_silence_are_abandoned():
    load = "Could not load deck - x.dck, match cannot start\n"
    assert forge_pod.parse_game(load, SEATS)["abandoned"] == "a deck failed to load"
    draw = "Game Result: Game 1 ended in a Draw! Took 1200 ms.\n"
    assert forge_pod.parse_game(draw, SEATS)["abandoned"] == "a draw"
    assert forge_pod.parse_game("", SEATS)["abandoned"] == "no outcome in Forge's output"
    assert forge_pod.parse_game(REAL_GAME, SEATS, wall_timeout=True)["winner"] is None


def test_unsupported_card_messages_are_collected():
    err = 'An unsupported card was requested: "Nope Card" from "".\n'
    assert forge_pod.parse_game(REAL_GAME, SEATS, err)["unsupported"] == ["Nope Card"]


def test_the_schedule_keeps_games_even_and_rotates_seats():
    stems = [f"d{i:02}" for i in range(18)]
    pods = forge_pod.schedule(stems, games_per_deck=8, seed=3)
    assert all(len(p) == 4 and len(set(p)) == 4 for p in pods)
    played = collections.Counter(s for p in pods for s in p)
    assert max(played.values()) - min(played.values()) <= 1
    assert min(played.values()) >= 8
    first = collections.Counter(p[0] for p in pods)
    assert max(first.values()) - min(first.get(s, 0) for s in stems) <= 2, \
        "first seat spread across the decks (Forge's AI always goes first)"
    assert pods == forge_pod.schedule(stems, games_per_deck=8, seed=3), "seeded"


def test_aggregate_scores_finished_games_only():
    win = forge_pod.parse_game(REAL_GAME, SEATS)
    win.update({"seats": SEATS})
    lost = {"seats": SEATS, "winner": None, "abandoned": "a draw", "turn": None}
    agg = forge_pod.aggregate([win, lost], SEATS)
    rows = {r["stem"]: r for r in agg["standings"]}
    tiny = rows["tinybones-bauble-burglar"]
    assert (tiny["games"], tiny["finished"], tiny["wins"], tiny["abandoned"]) == (2, 1, 1, 1)
    assert tiny["win_share"] == 1.0 and rows["tom-bert-and-william"]["win_share"] == 0.0
    assert agg["head_to_head"]["tinybones-bauble-burglar"]["kami-of-the-crescent-moon"] == [1, 1]
    assert agg["standings"][0]["stem"] == "tinybones-bauble-burglar"


def test_a_resumed_run_keeps_only_the_games_this_schedule_would_play(tmp_path):
    pods = [SEATS, list(reversed(SEATS)), SEATS[1:] + SEATS[:1]]
    win = dict(forge_pod.parse_game(REAL_GAME, SEATS), seats=SEATS)
    part = tmp_path / "2026-10-17.json.part"
    part.write_text("\n".join([
        json.dumps(dict(win, game=1)),                      # kept: game 1 sat SEATS
        json.dumps(dict(win, game=2)),                      # a different deck order: replay
        json.dumps(dict(win, game=9)),                      # not in this schedule
        json.dumps(dict(win, game=3, seats=pods[2]))[:40],  # torn mid-write
    ]), encoding="utf-8")
    assert list(forge_pod.load_part(str(part), pods)) == [1]
    assert forge_pod.load_part(str(tmp_path / "missing.part"), pods) == {}


def test_forge_turn_halves_every_seats_turns_so_a_4_seat_turn_26_is_round_13():
    # GameLogFormatter writes ceil(PhaseHandler turn / 2), and that counter counts
    # every seat's turn (read from the 2.0.15 jar's bytecode).
    assert forge_pod.round_of(26, 4) == 13 and forge_pod.round_of(9, 2) == 9


def _results(games, seats=SEATS, date="2026-10-17"):
    return {"meta": {"forge": "2.0.15", "games": len(games), "pod_size": 4, "date": date,
                     "finished": sum(1 for g in games if not g["abandoned"]),
                     "abandoned": sum(1 for g in games if g["abandoned"])},
            "decks": [{"stem": s, "title": s.title(), "study": False, "unsupported": [],
                       "ai_flagged": []} for s in seats],
            "games": games, "aggregate": forge_pod.aggregate(games, seats)}


def test_latest_results_is_the_newest_run_and_skips_a_broken_file(tmp_path):
    assert forge_pod.latest_results(str(tmp_path)) == (None, None)
    win = dict(forge_pod.parse_game(REAL_GAME, SEATS), seats=SEATS)
    (tmp_path / "2026-10-17.json").write_text(json.dumps(_results([win])), encoding="utf-8")
    (tmp_path / "2026-10-03.json").write_text(json.dumps(_results([], date="2026-10-03")),
                                              encoding="utf-8")
    (tmp_path / "2026-10-30.json").write_text("{ half a file", encoding="utf-8")
    path, res = forge_pod.latest_results(str(tmp_path))
    assert path.endswith("2026-10-17.json") and res["meta"]["games"] == 1


def test_matchups_pair_both_sides_of_each_record():
    win = dict(forge_pod.parse_game(REAL_GAME, SEATS), seats=SEATS)
    res = _results([win, dict(win)])
    rows = forge_pod.matchups(res, "kami-of-the-crescent-moon")
    tiny = next(r for r in rows if r["stem"] == "tinybones-bauble-burglar")
    assert (tiny["met"], tiny["won"], tiny["they_won"]) == (2, 0, 2)
    assert rows[0]["stem"] == "tinybones-bauble-burglar", "the decks that beat it first"
    assert len(rows) == 3


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app as appmod
    import enrich_bg
    import sync
    decks = tmp_path / "decks"
    decks.mkdir()
    for stem in SEATS[:3]:          # the fourth deck left the folder after the run
        (decks / f"{stem}.txt").write_text(
            f"# Title: {stem.title()} Now\n# Commander: X\n"
            + ("# Study: yes\n" if stem.startswith("vaevictis") else "")
            + "\n# --- Commander ---\n1 X\n", encoding="utf-8")
    coll = tmp_path / "collection.csv"
    coll.write_text("Quantity,Name\n1,X\n", encoding="utf-8")
    pod = tmp_path / "pod"
    pod.mkdir()
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", str(coll))
    monkeypatch.setattr(appmod, "PASSWORD", None)
    monkeypatch.setattr(appmod, "POD_DIR", str(pod))
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    monkeypatch.setattr(enrich_bg, "start", lambda *a, **k: "enrichment started")
    appmod.app.config["TESTING"] = True
    c = appmod.app.test_client()
    c.pod = pod
    return c


def test_the_matchups_page_without_a_run_says_how_to_start_one(client):
    page = client.get("/matchups").get_data(as_text=True)
    assert "No pod has run yet" in page and "forge_pod.py --install" in page
    assert 'aria-current="page"' in page and "Matchups" in page


def test_the_matchups_page_reads_the_newest_run(client):
    win = dict(forge_pod.parse_game(REAL_GAME, SEATS), seats=SEATS)
    lost = {"seats": SEATS, "winner": None, "abandoned": "a draw", "turn": None,
            "outcomes": {}, "unsupported": []}
    res = _results([win, lost])
    res["decks"][0]["ai_flagged"] = ["Scroll Rack"]
    res["decks"][1]["unsupported"] = ["Nope Card"]
    (client.pod / "2026-10-17.json").write_text(json.dumps(res), encoding="utf-8")
    page = client.get("/matchups").get_data(as_text=True)
    text = re.sub(r"\s+", " ", page)
    assert "never a verdict" in text and "25%" in text
    assert "2 games on 2026-10-17 · 1 finished, 1 stopped without a winner" in text
    # Today's title links to the deck; a deck that left the folder keeps the run's title.
    assert '<a href="/deck/tinybones-bauble-burglar">Tinybones-Bauble-Burglar Now</a>' in page
    assert "Tom-Bert-And-William <span class=\"tag\">not in your decks now</span>" in text
    assert "Won 100% of its finished games" in page and "1 of 1" in text
    assert "(+1 unscored)" in text
    assert ">13<" in page.replace(" ", ""), "Turn 26 in a 4-seat game is each player's 13th"
    assert text.index("Tinybones-Bauble-Burglar Now") < text.index("Kami-Of-The-Crescent-Moon Now")
    assert "Forge can't play Nope Card" in text
    assert "1 of its cards as ones its AI plays badly: Scroll Rack" in text
    assert '<span class="tag">Lab</span>' in page, "the Lab deck is marked"


def test_the_report_says_what_the_numbers_are_and_are_not():
    win = forge_pod.parse_game(REAL_GAME, SEATS)
    win.update({"seats": SEATS})
    results = {"meta": {"forge": "2.0.15", "games": 1, "pod_size": 4, "finished": 1,
                        "abandoned": 0, "date": "2026-10-17"},
               "decks": [{"stem": s, "title": s.title(), "unsupported": [],
                          "ai_flagged": []} for s in SEATS],
               "aggregate": forge_pod.aggregate([win], SEATS)}
    text = forge_pod.report(results)
    assert "never a verdict" in text and "25%" in text
    assert text.index("Tinybones") < text.index("Kami"), "winner first"
