"""The Watch tab's clips: the storyboard gate (clips.py) and the dashboard wiring.

What can lie here is a clip that shows a card the deck no longer plays, or names a
card that was never in it — so the gate drops those and SAYS so, and the page has
to carry that warning. Everything else (timing, caption length) is lint that must
never cost the viewer the clip. Offline and hermetic: every deck is in tmp_path.
"""
import json
import os
import re

import pytest

import build_dashboard as bd
import clips


def _write_clips(deck_file, obj):
    path = clips.clips_path(deck_file)
    with open(path, "w", encoding="utf-8") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))
    return path


def _scene(cards, head="Head", sub="", dur=5, **kw):
    return dict({"dur": dur, "head": head, "sub": sub, "cards": cards}, **kw)


def _story(*scenes, title="Clip"):
    return {"version": 1, "clips": [{"id": "c1", "title": title, "scenes": list(scenes)}]}


DECK = ["Test Commander", "Sol Ring", "Arcane Signet", "Island", "Command Tower",
        "Fire // Ice"]


# --------------------------------------------------------------------------- #
# the gate
# --------------------------------------------------------------------------- #
def test_a_scene_showing_a_card_the_deck_lost_is_skipped_and_reported():
    """Its caption was written around that card. Dropping only the card (the first
    version) left captions like "Mox Diamond, Lotus Petal and Ancient Tomb" over cards
    that were no longer there — so the whole scene goes, and says why."""
    res = clips.validate(_story(_scene([{"name": "Sol Ring"}, {"name": "Mana Crypt"}],
                                       head="Gone"),
                                _scene([{"name": "Sol Ring"}], head="Kept", dur=20)),
                         DECK)
    assert [s["head"] for s in res["clips"][0]["scenes"]] == ["Kept"]
    assert len(res["stale"]) == 1
    assert "Mana Crypt" in res["stale"][0] and "skipped" in res["stale"][0]


def test_a_caption_naming_a_card_the_deck_lost_skips_its_scene_too():
    res = clips.validate(_story(_scene([], head="Cast [[Mana Crypt]]", dur=8),
                                _scene([], sub="then [[Sol Ring|the Ring]] and [[Fire]]",
                                       dur=8)), DECK)
    (scene,) = res["clips"][0]["scenes"]
    assert scene["sub"] == "then the Ring and Fire", "brackets never reach the viewer"
    assert len(res["stale"]) == 1 and "Mana Crypt" in res["stale"][0]


def test_a_clip_whose_every_scene_is_stale_is_hidden_and_says_so():
    res = clips.validate(_story(_scene([{"name": "Mana Crypt"}], dur=10),
                                _scene([], head="[[Mox Diamond]]", dur=10)), DECK)
    assert res["clips"] == []
    assert any("whole clip is hidden" in s for s in res["stale"])


def test_featured_names_cover_scene_cards_and_caption_refs(deck_file):
    _write_clips(deck_file, _story(
        _scene([{"name": "Sol Ring"}, {"ph": "Their creature"}],
               sub="with [[Arcane Signet|a Signet]]", say="[[Command Tower]]", dur=10),
        _scene([], dur=10)))
    assert clips.featured_names(deck_file) == ["Sol Ring", "Arcane Signet", "Command Tower"]
    _write_clips(deck_file, "{broken")
    assert clips.featured_names(deck_file) == []


def test_cards_a_clip_features_are_protected_from_the_optimizer(deck_file, monkeypatch):
    """An automatic tuning pass must never strand a scene: a featured card is curated
    content, protected exactly like a card named in the deck's notes."""
    import deck_fit
    import deckcore
    import mtglib
    import optimize
    monkeypatch.setattr(deckcore, "load_card_notes", lambda *a, **k: {})
    _write_clips(deck_file, _story(_scene([{"name": "Sol Ring"}], sub="[[Arcane Signet]]",
                                          dur=10), _scene([], dur=10)))
    cards = [mtglib.Card(name=n) for n in ("Sol Ring", "Arcane Signet", "Command Tower")]
    keep = deck_fit.protected_keys(deck_file, "Test Commander", cards, notes_text="")
    assert {"sol ring", "arcane signet"} <= keep and "command tower" not in keep
    _keep, notes = optimize._protected(deck_file, "Test Commander")
    assert deck_fit.named_in_notes("Sol Ring", notes)
    assert deck_fit.named_in_notes("Arcane Signet", notes)
    assert not deck_fit.named_in_notes("Command Tower", notes)


def test_names_resolve_to_the_decks_own_spelling_through_front_faces():
    res = clips.validate(_story(_scene([{"name": "Fire"}, {"name": "sol ring"}]),
                                _scene([], dur=15)), DECK)
    names = [c["name"] for c in res["clips"][0]["scenes"][0]["cards"]]
    # the deck's spelling is what the decklist's <img alt> carries — the player
    # finds its art by that exact string
    assert names == ["Fire // Ice", "Sol Ring"]
    assert not res["stale"]


def test_a_bare_double_slash_is_not_a_split_card():
    """The " // " trap (CLAUDE.md): 'SP//dr' must not front-face to 'SP'."""
    res = clips.validate(_story(_scene([{"name": "SP"}]), _scene([], dur=15)),
                         ["SP//dr, Piloted by Peni"])
    assert res["stale"], "'SP' is not a card in this deck"


def test_opponent_cards_are_placeholders_and_keep_their_key_across_scenes():
    res = clips.validate(_story(
        _scene([{"ph": "Their best creature", "id": "v", "zone": "theirs"}]),
        _scene([{"ph": "Their best creature", "id": "v", "zone": "mine"}], dur=12)), DECK)
    s1, s2 = res["clips"][0]["scenes"]
    assert s1["cards"][0] == {"ph": "Their best creature", "zone": "theirs", "key": "v"}
    assert s2["cards"][0]["key"] == "v" and s2["cards"][0]["zone"] == "mine"
    assert not res["stale"] and not res["lint"]


def test_lint_never_costs_the_clip():
    res = clips.validate(_story(
        _scene([{"name": "Sol Ring", "zone": "nowhere", "fx": ["glow", "sparkle"]},
                {"name": "Sol Ring"}],                      # duplicate key
               head="x" * 100, dur=99, pool="BBQ", turn="soon"),
        _scene([{"neither": 1}], dur=1)), DECK)
    sc = res["clips"][0]["scenes"][0]
    assert sc["dur"] == clips.DUR_MAX                      # clamped, still plays
    assert sc["cards"] == [{"name": "Sol Ring", "zone": "row", "key": "Sol Ring",
                            "fx": ["glow"]}]
    assert "pool" not in sc and "turn" not in sc
    joined = " | ".join(res["lint"])
    for needle in ("unknown zone", "unknown fx", "appears twice", "headline is",
                   "clamped", "pool", "turn", "neither 'name' nor 'ph'"):
        assert needle in joined, needle
    assert not res["stale"]


def test_a_caption_too_long_to_read_in_its_scene_is_flagged():
    words = " ".join(["word"] * 30)
    res = clips.validate(_story(_scene([], sub=words, dur=3), _scene([], dur=15)), DECK)
    assert any("to read" in w for w in res["lint"])


def test_card_frames_carry_cost_and_type_when_info_is_given():
    info = {"sol ring": {"cost": "{1}", "type": "Artifact"}}
    res = clips.validate(_story(_scene([{"name": "Sol Ring"}]), _scene([], dur=15)),
                         DECK, info)
    card = res["clips"][0]["scenes"][0]["cards"][0]
    assert card["cost"] == "{1}" and card["type"] == "Artifact"


def test_load_is_none_without_a_file_and_never_raises_on_a_bad_one(deck_file):
    assert clips.load(deck_file, DECK) is None
    _write_clips(deck_file, "{not json")
    res = clips.load(deck_file, DECK)
    assert res["clips"] == [] and "can't be read" in res["lint"][0]
    _write_clips(deck_file, json.dumps([1, 2, 3]))
    assert clips.load(deck_file, DECK)["clips"] == []


def test_cli_check_fails_on_a_stale_card_and_passes_clean(deck_file, capsys):
    _write_clips(deck_file, _story(_scene([{"name": "Sol Ring"}], dur=10),
                                   _scene([{"name": "Test Commander"}], dur=10)))
    assert clips.main(["--deck", deck_file, "--check"]) == 0
    _write_clips(deck_file, _story(_scene([{"name": "Black Lotus"}], dur=10),
                                   _scene([], dur=10)))
    assert clips.main(["--deck", deck_file, "--check"]) == 3
    assert "STALE" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# the dashboard (both surfaces render through generate())
# --------------------------------------------------------------------------- #
def _gen(deck_file, collection_file, **kw):
    return bd.generate(deck_file, collection_file, title="T", commander="Test Commander",
                       **kw)["dashboard"]


def test_no_clips_file_means_no_watch_tab_and_no_player_bytes(deck_file, collection_file):
    html = _gen(deck_file, collection_file)
    assert "tab-watch" not in html
    assert "wt-root" not in html and ".wt-stage" not in html


def test_watch_tab_renders_the_validated_storyboard(deck_file, collection_file):
    _write_clips(deck_file, _story(
        _scene([{"name": "Test Commander", "zone": "hero"}], head="The pitch", dur=8),
        _scene([{"name": "Sol Ring", "zone": "mine", "fx": "tap"},
                {"ph": "Their best creature", "zone": "theirs"}], head="Go", dur=8),
        title="The pitch"))
    for editable in (False, True):
        html = _gen(deck_file, collection_file, editable=editable)
        assert "<label for='tab-watch'>Watch</label>" in html
        m = re.search(r"<script type='application/json' id='wt-data'>(.*?)</script>", html, re.S)
        data = json.loads(m.group(1))
        sc = data["clips"][0]["scenes"]
        assert sc[0]["cards"][0]["name"] == "Test Commander"
        # frames carry the collection's cost/type for the no-art fallback
        assert sc[1]["cards"][0]["cost"] == "{1}" and sc[1]["cards"][0]["type"] == "Artifact"
        assert "clips_player.js" in html and ".wt-stage" in html   # player inlined
        assert not re.search(r"<script[^>]+src=", html), "dashboard must stay self-contained"
        # no-script / print fallback: the storyboard as a readable outline
        assert "<ol class='wt-outline'>" in html and "The pitch" in html


def test_a_stale_scene_puts_an_out_of_date_banner_on_the_tab(deck_file, collection_file):
    _write_clips(deck_file, _story(_scene([{"name": "Sol Ring"}, {"name": "Mana Crypt"}],
                                          head="Gone", dur=8),
                                   _scene([], head="Kept", dur=8)))
    html = _gen(deck_file, collection_file)
    assert "These clips are out of date" in html and "Mana Crypt" in html
    assert "1 scene shows or names a card that has left the deck" in html
    data = json.loads(re.search(r"id='wt-data'>(.*?)</script>", html, re.S).group(1))
    assert [s["head"] for s in data["clips"][0]["scenes"]] == ["Kept"]


def test_a_fully_stale_storyboard_keeps_the_tab_to_say_why(deck_file, collection_file):
    """The day a deck change strands every scene, the tab must not silently vanish."""
    _write_clips(deck_file, _story(_scene([{"name": "Mana Crypt"}], dur=10),
                                   _scene([], head="[[Mox Diamond]]", dur=10)))
    html = _gen(deck_file, collection_file)
    assert "<label for='tab-watch'>Watch</label>" in html
    assert "These clips are out of date" in html
    assert "wt-data" not in html and "clips_player.js" not in html   # no player to run


def test_caption_text_cannot_break_out_of_the_payload(deck_file, collection_file):
    _write_clips(deck_file, _story(_scene([], head="</script><script>alert(1)</script>",
                                          dur=8), _scene([], dur=8)))
    html = _gen(deck_file, collection_file)
    payload = re.search(r"id='wt-data'>(.*?)</script>", html, re.S).group(1)
    assert "</script>" not in payload and "<script>" not in payload
    assert json.loads(payload)["clips"][0]["scenes"][0]["head"].startswith("</script>")


def test_a_broken_clips_file_costs_the_tab_not_the_page(deck_file, collection_file):
    _write_clips(deck_file, "{oops")
    html = _gen(deck_file, collection_file)
    assert "Decklist by Section" in html and "tab-watch" not in html


def test_player_css_uses_tokens_not_ad_hoc_sizes():
    css = open(os.path.join(os.path.dirname(bd.__file__), "assets", "clips_player.css"),
               encoding="utf-8").read()
    assert not re.findall(r"font-size:\s*((?!var)[0-9.]+(?:r?em|px))", css)


def test_player_css_braces_balance():
    """A stray `}` makes the browser drop the next rule SILENTLY (2026-10-11: moving
    the phone block left one behind and the zone bands lost their styles). Comments
    are stripped first so a brace in prose can't fool the count."""
    css = open(os.path.join(os.path.dirname(bd.__file__), "assets", "clips_player.css"),
               encoding="utf-8").read()
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    depth = 0
    for ch in css:
        depth += {"{": 1, "}": -1}.get(ch, 0)
        assert depth >= 0, "a closing brace with nothing open"
    assert depth == 0, "an unclosed block"


# --------------------------------------------------------------------------- #
# Video-style controls + the narrator (docs/spec-watch-voice-and-controls.md A, B)
# --------------------------------------------------------------------------- #
def test_the_player_has_video_controls_with_labels(deck_file, collection_file):
    _write_clips(deck_file, _story(_scene([{"name": "Sol Ring"}], head="Go", dur=8),
                                   _scene([], head="Again", dur=8)))
    html = _gen(deck_file, collection_file)
    for label in ("Previous scene", "Play", "Stop", "Next scene", "Narration off",
                  "Choose a voice"):
        assert f"aria-label='{label}'" in html, label
    assert "wt-restart" not in html, "Stop + Play replaced the restart button"
    # the bar sits under the picture and ABOVE the captions
    assert html.index("class='wt-stage'") < html.index("class='wt-ctrl'") \
        < html.index("class='wt-caps'")
    assert "class='wt-flash'" in html and "class='wt-voices' hidden" in html


def test_every_scene_carries_its_spoken_line():
    res = clips.validate(_story(
        _scene([], head="Cast [[Sol Ring|the Ring]]", sub="It taps for {C}{C}.", dur=8),
        _scene([], head="Ignored", say="Say {3}{U}{U} instead", dur=8)), DECK, pron=[])
    a, b = res["clips"][0]["scenes"]
    assert a["speak"] == "Cast the Ring. It taps for colorless, colorless."
    assert b["speak"] == "Say three, blue, blue instead"


@pytest.mark.parametrize("text, said", [
    ("{3}{B}{B}", "three, black, black"),
    ("{W/U} or {2/W}", "white or blue or two or white"),
    ("{B/P}", "phyrexian black"),
    ("{T}: add {G}", "tap: add green"),
    ("Put a +1/+1 counter", "Put a plus one plus one counter"),
    ("It gets −2/−2", "It gets minus two minus two"),
    ("MV 3, ETB tapped", "mana value 3, enters tapped"),
    ("[[Fire // Ice|Fire]] — then", "Fire, then"),
    ("A wrath is coming —. Destroy all creatures.", "A wrath is coming. Destroy all creatures."),
    ("Ready?. Go", "Ready? Go"),
])
def test_spoken_reads_symbols_the_way_a_player_says_them(text, said):
    assert clips.spoken(text) == said


def test_pronunciations_apply_as_whole_words_and_the_list_starts_empty():
    pron = [("Tergrid", "Tur-grid")]
    assert clips.spoken("Tergrid's ally, not Tergridz", pron) == "Tur-grid's ally, not Tergridz"
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "reference", "pronunciations.csv")
    with open(path, encoding="utf-8") as f:
        assert f.read().strip() == "Word,Say as", \
            "entries are added only when the player hears a name said wrong"
    assert clips.load_pronunciations(path) == []


def _node(script):
    import shutil
    import subprocess
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    js = os.path.join(os.path.dirname(bd.__file__), "assets", "clips_player.js")
    out = subprocess.run(["node", "-e", f"const S=require({json.dumps(js)});{script}"],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_voice_ranking_prefers_natural_voices_in_english():
    voices = [{"name": "Microsoft David Desktop - English (United States)", "lang": "en-US"},
              {"name": "Microsoft Aria Online (Natural) - English (United States)",
               "lang": "en-US"},
              {"name": "Samantha", "lang": "en-US"},
              {"name": "Samantha (Enhanced)", "lang": "en-US"},
              {"name": "Google UK English Female", "lang": "en-GB"},
              {"name": "Thomas", "lang": "fr-FR"},
              {"name": "Zarvox", "lang": "en-US"},
              {"name": "eSpeak English", "lang": "en"}]
    order = _node(f"console.log(JSON.stringify(S.rank({json.dumps(voices)}).map(v => v.name)))")
    assert order.index("Microsoft Aria Online (Natural) - English (United States)") < \
        order.index("Microsoft David Desktop - English (United States)")
    assert order.index("Samantha (Enhanced)") < order.index("Samantha")
    assert "Thomas" not in order, "the menu lists English voices only"
    assert order[-2:] == ["Zarvox", "eSpeak English"] or set(order[-2:]) == {
        "Zarvox", "eSpeak English"}, "novelty and eSpeak voices rank last"


def test_sentence_splitter_keeps_names_and_costs_whole():
    parts = _node("console.log(JSON.stringify(S.sentences("
                  "'Tap Mana Vault. Then cast {3}{B}{B}. Dr. Strange waits! "
                  "B.F.M. is big. Pay 1.5 more.')))")
    assert parts == ["Tap Mana Vault.", "Then cast {3}{B}{B}.", "Dr. Strange waits!",
                     "B.F.M. is big.", "Pay 1.5 more."]
