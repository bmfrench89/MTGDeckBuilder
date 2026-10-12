"""precon.py — official precon decklists from MTGJSON, rendered as deck files.

Hermetic: the network call is monkeypatched to serve fixtures, and every cache and
output file lives in tmp_path. What's guarded is what could LIE about ownership:
taking the wrong product's list, counting a double-faced card twice, counting
basics, or writing a partial list when MTGJSON is down."""
import urllib.error

import mtglib
import precon

INDEX = {"data": [
    {"code": "FDC", "fileName": "WretchedRanks_FDC", "name": "Wretched Ranks",
     "releaseDate": "2026-10-02", "type": "Commander Deck"},
    {"code": "OLD", "fileName": "WretchedRanks_OLD", "name": "Wretched Ranks",
     "releaseDate": "2019-01-01", "type": "Commander Deck"},
    {"code": "THM", "fileName": "WretchedRanksTheme_THM", "name": "Wretched Ranks Theme",
     "releaseDate": "2026-10-02", "type": "Theme Deck"},
]}

DFC = "Bala Ged Recovery // Bala Ged Sanctuary"


def _card(name, count=1, ci=(), side=None):
    c = {"name": name, "count": count, "colorIdentity": list(ci)}
    if side:
        c["side"] = side
    return c


def _deck():
    main = [_card("Sol Ring"), _card("Swamp", 30),
            _card(DFC, side="a"), _card(DFC, side="b")]       # one physical card
    main += [_card(f"Filler Card {i}") for i in range(67)]
    return {"data": {"code": "FDC", "name": "Wretched Ranks", "releaseDate": "2026-10-02",
                     "type": "Commander Deck",
                     "commander": [_card("Test Commander", ci=["B"])],
                     "displayCommander": [_card("Test Commander", ci=["B"])],
                     "mainBoard": main, "sideBoard": []}}


def _serve(monkeypatch, calls=None, fail=False):
    def fake(url, timeout=60):
        if calls is not None:
            calls.append(url)
        if fail:
            raise urllib.error.URLError("403 from the egress proxy")
        if url == precon.DECKLIST_URL:
            return INDEX
        if url == precon.DECK_URL.format("WretchedRanks_FDC"):
            return _deck()
        raise AssertionError(f"unexpected URL {url}")
    monkeypatch.setattr(precon, "_get_json", fake)


def test_find_takes_the_newest_commander_deck_and_reports_the_rest():
    best, others, near = precon.find("  wretched   RANKS ", INDEX["data"])
    assert best["code"] == "FDC"
    assert [d["code"] for d in others] == ["OLD"]
    assert [d["code"] for d in near] == ["THM"]


def test_a_partial_name_is_offered_never_taken():
    best, others, near = precon.find("Ranks", INDEX["data"])
    assert best is None and not others
    assert {d["code"] for d in near} == {"FDC", "OLD", "THM"}


def test_parse_counts_a_double_faced_card_once_and_totals_the_hundred():
    deck = precon.parse(_deck())
    main = dict((name, n) for n, name in deck["boards"]["mainBoard"])
    assert main[DFC] == 1 and deck["skipped_faces"] == 1
    assert main["Swamp"] == 30
    assert deck["total"] == 100
    assert deck["commander"] == "Test Commander" and deck["identity"] == "B"


def test_rendered_file_reads_back_through_the_repo_parsers():
    text = precon.render(precon.parse(_deck()), fetched="2026-10-12")
    assert mtglib.deck_header(text, "Commander") == "Test Commander"
    assert mtglib.deck_header(text, "Colors") == "B"
    assert "2026-10-02" in mtglib.deck_header(text, "Source")
    assert sum(c.quantity for c in mtglib.parse_deck(text)) == 100
    assert "# --- Commander ---" in text and "# --- Mainboard ---" in text


def test_names_for_verification_skip_basics_and_repeat_nothing():
    names = precon.nonbasic_names(precon.parse(_deck()))
    assert "Swamp" not in names
    assert names.count(DFC) == 1
    assert names[0] == "Test Commander" and len(names) == 1 + 1 + 1 + 67


def test_cli_writes_the_deck_file_and_the_verify_list(tmp_path, monkeypatch, capsys):
    _serve(monkeypatch)
    out, names = tmp_path / "precons", tmp_path / "names.txt"
    rc = precon.main(["Wretched Ranks", "--out-dir", str(out), "--names-out", str(names),
                      "--cache-dir", str(tmp_path / "cache")])
    assert rc == 0
    text = (out / "wretched-ranks.txt").read_text(encoding="utf-8")
    assert sum(c.quantity for c in mtglib.parse_deck(text)) == 100
    listed = names.read_text(encoding="utf-8").splitlines()
    assert "Swamp" not in listed and "Sol Ring" in listed
    assert "also matched (not used)" in capsys.readouterr().out


def test_unreachable_mtgjson_writes_nothing_and_exits_2(tmp_path, monkeypatch, capsys):
    _serve(monkeypatch, fail=True)
    out = tmp_path / "precons"
    rc = precon.main(["Wretched Ranks", "--out-dir", str(out),
                      "--cache-dir", str(tmp_path / "cache")])
    assert rc == 2
    assert not out.exists()
    assert "UNREACHABLE" in capsys.readouterr().err


def test_an_unknown_name_exits_3_and_offers_near_misses(tmp_path, monkeypatch, capsys):
    _serve(monkeypatch)
    rc = precon.main(["Ranks", "--cache-dir", str(tmp_path / "cache")])
    assert rc == 3
    err = capsys.readouterr().err
    assert "NOT FOUND" in err and "Wretched Ranks Theme" in err


def test_cache_serves_fresh_copies_offline_and_stale_ones_when_down(tmp_path, monkeypatch):
    calls = []
    _serve(monkeypatch, calls)
    cache = str(tmp_path / "cache")
    deck, _ = precon.fetch("Wretched Ranks", cache)
    assert deck["total"] == 100 and len(calls) == 2
    precon.fetch("Wretched Ranks", cache)                  # fresh: no new requests
    assert len(calls) == 2
    _serve(monkeypatch, fail=True)                          # MTGJSON goes down
    deck, _ = precon.fetch("Wretched Ranks", cache, refresh=True)
    assert deck["total"] == 100                             # the cached copy, not a crash


def test_a_short_list_is_flagged_not_trusted():
    payload = _deck()
    payload["data"]["mainBoard"] = payload["data"]["mainBoard"][:-5]
    assert "WARNING" in precon.summary(precon.parse(payload))
