"""The Watch tab's clips: the storyboard gate (clips.py) and the dashboard wiring.

What can lie here is a clip that shows a card the deck no longer plays, or names a
card that was never in it — so the gate drops those and SAYS so, and the page has
to carry that warning. Everything else (timing, caption length) is lint that must
never cost the viewer the clip. Offline and hermetic: every deck is in tmp_path.
"""
import json
import os
import re

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
def test_a_card_that_left_the_deck_is_dropped_and_reported_stale():
    res = clips.validate(_story(_scene([{"name": "Sol Ring"}, {"name": "Mana Crypt"}]),
                                _scene([{"name": "Sol Ring"}], dur=20)),
                         DECK)
    names = [c["name"] for c in res["clips"][0]["scenes"][0]["cards"]]
    assert names == ["Sol Ring"], "a card not in the deck must never reach the player"
    assert len(res["stale"]) == 1 and "Mana Crypt" in res["stale"][0]


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


def test_a_stale_card_puts_an_out_of_date_banner_on_the_tab(deck_file, collection_file):
    _write_clips(deck_file, _story(_scene([{"name": "Sol Ring"}, {"name": "Mana Crypt"}], dur=8),
                                   _scene([], dur=8)))
    html = _gen(deck_file, collection_file)
    assert "These clips are out of date" in html and "Mana Crypt" in html
    data = json.loads(re.search(r"id='wt-data'>(.*?)</script>", html, re.S).group(1))
    assert all(c.get("name") != "Mana Crypt"
               for s in data["clips"][0]["scenes"] for c in s["cards"])


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
