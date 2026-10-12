"""Recorded narration for the Watch tab (docs/spec-watch-voice-and-controls.md Part C).

The stdlib half is pinned here: the content-hash file names, what still needs recording
and what gets pruned, scene timing that follows the narrator, the serving route's
manifest-only rule with immutable caching and Range support, the service worker's
hands-off, and that a missing take is a note — never a CI failure. No model runs here;
synthesis happens only on a runner (.github/narrate/synthesize.py).
"""
import json
import os

import pytest

import clips
import narration

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = {"engine": "kokoro-82m", "model": "v1.0", "voice": "af_heart", "speed": 1.0}

DECK = """\
# Title: Clip Deck
# Commander: Test Commander
# Colors: W U

# --- Commander ---
1 Test Commander

# --- Artifacts ---
1 Sol Ring
"""
STORY = {"version": 1, "clips": [{"id": "c", "title": "Pitch", "scenes": [
    {"dur": 8, "head": "Cast [[Sol Ring]]", "sub": "It taps for {C}{C}.", "cards": []},
    {"dur": 8, "head": "Then [[Test Commander]]", "cards": []}]}]}


@pytest.fixture
def deck(tmp_path, monkeypatch):
    d = tmp_path / "decks"
    d.mkdir()
    (d / "cd.txt").write_text(DECK, encoding="utf-8")
    (d / "cd.clips.json").write_text(json.dumps(STORY), encoding="utf-8")
    base = tmp_path / "narration"
    base.mkdir()
    monkeypatch.setattr(narration, "NARRATION_DIR", str(base))
    return str(d / "cd.txt"), base


def test_the_take_name_is_stable_and_changes_with_any_input():
    h = narration.take_hash("Hello there.", CFG)
    assert h == narration.take_hash("Hello there.", dict(CFG)) and len(h) == 16
    for change in ({"voice": "am_michael"}, {"engine": "piper"}, {"model": "v1.1"},
                   {"speed": 1.1}):
        assert narration.take_hash("Hello there.", dict(CFG, **change)) != h
    assert narration.take_hash("Hello there!", CFG) != h


def test_no_narrator_chosen_means_nothing_to_record(deck, tmp_path):
    path, _ = deck
    assert narration.load_config(str(tmp_path / "none.json")) is None
    assert narration.plan(path, None) == ([], [])


def test_plan_records_each_line_once_and_prunes_what_nothing_uses(deck):
    path, base = deck
    todo, prune = narration.plan(path, CFG)
    assert len(todo) == 2
    first = todo[0][0]
    (base / "cd.json").write_text(json.dumps({"takes": {
        first: {"file": f"{first}.mp3", "ms": 2000},
        "0123456789abcdef": {"file": "0123456789abcdef.mp3", "ms": 900}}}), encoding="utf-8")
    todo, prune = narration.plan(path, CFG)
    assert [h for h, _ in todo] != [first] and len(todo) == 1
    assert prune == ["0123456789abcdef"], "a take no scene asks for is pruned"


def test_a_deck_can_override_the_voice():
    assert narration.deck_voice(CFG, {"voice": "bm_george"})["voice"] == "bm_george"
    assert narration.deck_voice(CFG, {})["voice"] == "af_heart"


def test_scene_timing_follows_the_narrator():
    assert narration.scene_len(5, 3000) == 5          # the take fits: authored timing
    assert narration.scene_len(5, 6000) == pytest.approx(6.4)   # never cut the voice off
    assert narration.scene_len(5, 0) == 5


def test_attach_times_recorded_scenes_and_counts_the_rest(deck):
    path, base = deck
    res = clips.load(path, clips._deck_cards(path))
    speak = res["clips"][0]["scenes"][0]["speak"]
    h = narration.take_hash(speak, CFG)
    (base / "cd.json").write_text(json.dumps({"takes": {h: {"file": f"{h}.mp3",
                                                              "ms": 9000}}}), encoding="utf-8")
    missing = narration.attach(res, "cd", CFG)
    s1, s2 = res["clips"][0]["scenes"]
    assert s1["audio"] == {"file": f"{h}.mp3", "ms": 9000} and s1["dur"] == pytest.approx(9.4)
    assert "audio" not in s2 and s2["dur"] == 8 and missing == 1
    assert res["clips"][0]["total"] == pytest.approx(17.4)


def test_a_missing_take_is_a_note_not_a_ci_failure(deck, monkeypatch, capsys):
    path, _ = deck
    monkeypatch.setattr(narration, "load_config", lambda path=None: dict(CFG))
    assert clips.main(["--deck", path, "--check"]) == 0
    assert "no recorded narration yet" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Serving and the dashboard
# --------------------------------------------------------------------------- #
@pytest.fixture
def served(deck, monkeypatch, collection_file):
    import app as appmod
    path, base = deck
    monkeypatch.setattr(appmod, "DECKS_DIR", os.path.dirname(path))
    monkeypatch.setattr(appmod, "COLLECTION", collection_file)
    monkeypatch.setattr(appmod, "PASSWORD", None)
    h = "0123456789abcdef"
    (base / "cd").mkdir()
    (base / "cd" / f"{h}.mp3").write_bytes(b"ID3" + b"\x00" * 997)
    (base / "cd" / "notes.txt").write_text("not a take", encoding="utf-8")
    (base / "cd.json").write_text(json.dumps({"takes": {h: {"file": f"{h}.mp3", "ms": 1}}}),
                                  encoding="utf-8")
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client(), h


def test_a_listed_take_is_served_immutable_with_ranges(served):
    c, h = served
    r = c.get(f"/narration/cd/{h}.mp3")
    assert r.status_code == 200 and r.mimetype == "audio/mpeg"
    assert "immutable" in r.headers["Cache-Control"]
    r = c.get(f"/narration/cd/{h}.mp3", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and len(r.data) == 10


@pytest.mark.parametrize("url", ["/narration/cd/notes.txt", "/narration/cd/ffffffffffffffff.mp3",
                                 "/narration/cd/..%2Fcd.json", "/narration/nope/0123456789abcdef.mp3"])
def test_only_manifest_takes_are_served(served, url):
    c, _ = served
    assert c.get(url).status_code == 404


def test_the_service_worker_never_handles_narration():
    sw = open(os.path.join(ROOT, "webapp", "static", "sw.js"), encoding="utf-8").read()
    i = sw.index("startsWith('/narration/')")
    assert sw[i:i + 60].split("\n")[0].rstrip().endswith("return;"), \
        "an early return, before any respondWith"
    assert i < sw.index("respondWith")


def test_standalone_dashboards_keep_the_device_voice(deck, collection_file, monkeypatch):
    import build_dashboard as bd
    path, base = deck
    monkeypatch.setattr(narration, "load_config", lambda path=None: dict(CFG))
    html = bd.generate(path, collection_file, title="T", commander="Test Commander")["dashboard"]
    payload = json.loads(html.split("id='wt-data'>")[1].split("</script>")[0])
    assert payload["audio"] == "" and "audio" not in payload["clips"][0]["scenes"][0]
    html = bd.generate(path, collection_file, title="T", commander="Test Commander",
                       narration_url="/narration/cd/")["dashboard"]
    payload = json.loads(html.split("id='wt-data'>")[1].split("</script>")[0])
    assert payload["audio"] == "/narration/cd/"
    assert "use your device's voice until" in html, "the tab says which scenes aren't recorded"
