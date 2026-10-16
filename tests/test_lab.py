"""The Lab: theory decks get their own view (docs/spec-lab.md).

A theory deck (`# Study: yes`) may use any card the player owns, even one sleeved in
another deck, and it claims no copies. So "ready to sleeve?" means nothing for it.
The Lab asks "what would building it for real take, and from which decks?" instead.
These tests pin:
- the engine's answer (deck_conflicts.lab_sources);
- the one header edit that moves a deck in or out (set_study), byte for byte;
- the two Decks-page views;
- the move route;
- the theory deck's own page: a Lab tab first, the way back to the Lab, and no false
  "fully self-contained" claim.

Hermetic: decks, collection and pins live in tmp_path.
"""
import html as htmlmod
import json
import re

import pytest

import build_dashboard as bd
import deck_conflicts
import mtglib

COLL = """Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,MARKET
1,Real Commander,3,G,G,{2}{G},Legendary Creature,Elf,rare,rc000001,1.00
1,Theory Commander,3,G,G,{2}{G},Legendary Creature,Elf,rare,tc000001,1.00
2,Sol Ring,1,,,{1},Artifact,,uncommon,sr000001,1.00
1,Llanowar Elves,1,G,G,{G},Creature,Elf,common,le000001,0.10
1,Spare Bear,2,G,G,{1}{G},Creature,Bear,common,sb000001,0.10
"""

REAL = """# Title: Y'shtola's Real Deck
# Commander: Real Commander
# Colors: G

# --- Commander ---
1 Real Commander

# --- Creatures ---
1 Llanowar Elves
# a comment the move must never touch

# --- Artifacts ---
1 Sol Ring

# --- Basics ---
30 Forest
"""

THEORY = """# Title: Theory Deck
# Commander: Theory Commander
# Colors: G
# Study: yes

# --- Commander ---
1 Theory Commander

# --- Creatures ---
1 Llanowar Elves
1 Spare Bear
1 Never Printed Here

# --- Artifacts ---
1 Sol Ring

# --- Basics ---
30 Forest
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    import app as appmod
    import deckcore
    import enrich_bg
    import sync
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "real-deck.txt").write_text(REAL, encoding="utf-8")
    (decks / "theory-deck.txt").write_text(THEORY, encoding="utf-8")
    coll = tmp_path / "collection.csv"
    coll.write_text(COLL, encoding="utf-8")
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", str(coll))
    monkeypatch.setattr(appmod, "PASSWORD", None)
    monkeypatch.setattr(deckcore, "PINS", str(tmp_path / "pins.csv"))
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    monkeypatch.setattr(enrich_bg, "start", lambda *a, **k: "enrichment started")
    appmod.app.config["TESTING"] = True

    class E:
        app = appmod
        client = appmod.app.test_client()
    E.decks, E.coll = decks, str(coll)
    return E


def test_lab_sources_say_where_each_card_would_come_from(env):
    idx = mtglib.index_by_name(mtglib.load_collection(env.coll))
    usage = deck_conflicts.scan(str(env.decks), idx)
    theory = mtglib.parse_deck(THEORY)
    lab = deck_conflicts.lab_sources(theory, idx, usage)
    # Sol Ring: 2 owned, 1 in the real deck -> a spare copy. Llanowar Elves: the only
    # copy is in the real deck. Basics are always owned and never listed.
    assert lab["held"] == {"real-deck": ["Llanowar Elves"]} and lab["held_cards"] == 1
    assert lab["free"] == ["Theory Commander", "Spare Bear", "Sol Ring"]
    assert lab["missing"] == ["Never Printed Here"]
    assert "Forest" not in lab["free"] + lab["missing"]


def test_a_theory_deck_never_holds_a_card_from_another_theory_deck(env):
    (env.decks / "theory-two.txt").write_text(THEORY.replace("Theory Deck", "Two"),
                                              encoding="utf-8")
    idx = mtglib.index_by_name(mtglib.load_collection(env.coll))
    lab = deck_conflicts.lab_sources(mtglib.parse_deck(THEORY), idx,
                                     deck_conflicts.scan(str(env.decks), idx))
    assert list(lab["held"]) == ["real-deck"], "study copies commit nothing"


@pytest.mark.parametrize("text", [REAL, REAL.replace("\n", "\r\n"),
                                  "# Title: Bare\n# --- Commander ---\n1 X\n"])
def test_moving_in_and_out_of_the_lab_changes_one_line(text):
    on = deck_conflicts.set_study(text, True)
    added = [ln for ln in on.splitlines() if ln not in text.splitlines()]
    assert added == ["# Study: yes"]
    assert deck_conflicts.set_study(on, True) == on, "idempotent"
    assert deck_conflicts.set_study(on, False) == text, "back out, byte for byte"
    head = on.splitlines()
    assert head.index("# Study: yes") < next(i for i, ln in enumerate(head)
                                             if ln.startswith("# ---"))


def test_your_decks_and_the_lab_are_two_views(env):
    home = env.client.get("/").get_data(as_text=True)
    lab = env.client.get("/lab").get_data(as_text=True)
    assert "Real Deck" in home and "Theory Deck" not in home
    assert "Theory Deck" in lab and "Real Deck</a>" not in lab
    assert 'aria-current="page">Your decks' in home and 'aria-current="page">Lab' in lab
    for page in (home, lab):            # both tabs carry both counts
        assert '<span class="cnt" aria-hidden="true">1</span>' in page
    assert "Ready to sleeve</a>" in home and "Ready to sleeve</a>" not in lab


def test_a_lab_card_says_what_building_it_would_take(env):
    page = env.client.get("/lab").get_data(as_text=True)
    card = re.search(r'<article class="deckcard theory".*?</article>', page, re.S).group(0)
    assert ">Theory</span>" in card
    line = re.sub(r"\s+", " ", re.search(r'<span class="labline">(.*?)</span>\s*<span class="muted labfrom">',
                                         card, re.S).group(1))
    assert line.startswith("1 from other decks · 3 free")
    assert "1 to buy" in line
    assert re.search(r"From\s+Y&#39;shtola&#39;s Real Deck 1", card)
    assert "Make it a real deck" in card and "Move to the Lab" not in card


def test_a_declared_bracket_is_the_headline_with_the_detected_one_beside_it(env):
    """The Decks page headlined the DETECTED bracket. Witherbloom (four two-card combos,
    declared 4) read "Bracket 3" because power.py's curated combo list doesn't know
    those combos, and Y'shtola (declared 4) read 3 the same way. power.with_declared's
    contract is that a surface headlines the setting and shows the detected verdict
    beside it."""
    text = THEORY.replace("# Study: yes", "# Study: yes\n# Bracket: 4")
    (env.decks / "theory-deck.txt").write_text(text, encoding="utf-8")
    page = env.client.get("/lab").get_data(as_text=True)
    card = re.search(r'<article class="deckcard theory".*?</article>', page, re.S).group(0)
    assert re.search(r'<span class="pill b4"[^>]*>Bracket 4 · Optimized</span>', card)
    assert re.search(r'<span class="muted fs-xs">detected [123]</span>', card)
    assert 'data-bracket="4"' in card and 'data-f="b4"' in page


def test_an_empty_lab_explains_itself(env):
    (env.decks / "theory-deck.txt").unlink()
    page = env.client.get("/lab").get_data(as_text=True)
    assert "No theory decks yet" in page and 'id="deckq"' not in page


def test_confirm_text_survives_an_apostrophe_in_the_title(env):
    """A title like Y'shtola's broke the inline confirm() string, and a handler that
    doesn't compile submits without asking. Every confirm is JSON now."""
    page = env.client.get("/").get_data(as_text=True)
    handlers = re.findall(r'onsubmit="return confirm\((.*?)\);"', page)
    assert handlers, "the deck menu has confirms"
    for h in handlers:
        msg = json.loads(htmlmod.unescape(h))
        assert isinstance(msg, str) and msg


def test_move_to_the_lab_and_back_edits_only_the_header(env, tmp_path):
    import deckcore
    deckcore.save_pins({"sol ring": "real-deck", "llanowar elves": "theory-deck"})
    r = env.client.post("/deck/real-deck/lab", data={"to": "lab"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/lab")
    moved = (env.decks / "real-deck.txt").read_text(encoding="utf-8")
    assert deck_conflicts.set_study(REAL, True) == moved
    assert "sol ring" not in deckcore.load_pins(), "its pins free up, as on Delete"
    assert deckcore.load_pins().get("llanowar elves") == "theory-deck"
    r = env.client.post("/deck/real-deck/lab", data={"to": "decks"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/deck/real-deck")
    assert (env.decks / "real-deck.txt").read_text(encoding="utf-8") == REAL


def test_the_move_route_refuses_what_it_does_not_know(env):
    assert env.client.post("/deck/real-deck/lab", data={"to": "nowhere"}).status_code == 400
    assert env.client.post("/deck/no-such-deck/lab", data={"to": "lab"}).status_code == 404
    assert (env.decks / "real-deck.txt").read_text(encoding="utf-8") == REAL


def test_making_it_real_says_how_many_cards_turn_contested(env):
    r = env.client.post("/deck/theory-deck/lab", data={"to": "decks"},
                        follow_redirects=False)
    assert r.status_code == 302
    with env.client.session_transaction() as s:
        msgs = " ".join(m for _c, m in s.get("_flashes", []))
    assert "is a real deck now" in msgs and "1 of its cards are also in other decks" in msgs


def test_a_theory_deck_page_opens_on_the_lab(env):
    page = bd.generate(str(env.decks / "theory-deck.txt"), env.coll, title="Theory Deck",
                       commander="Theory Commander", decks_dir=str(env.decks),
                       editable=True, sim=None)["dashboard"]
    tabs = re.findall(r"<label for='tab-(\w+)'>", page)
    assert tabs[0] == "lab", "a theory deck opens on the Lab"
    lab = re.search(r"<div class='tabpanel' data-tab='lab'>(.*?)</div><div class='tabpanel'",
                    page, re.S).group(1)
    assert "From Y&#x27;shtola&#x27;s Real Deck" in lab or "From Y&#39;shtola&#39;s Real Deck" in lab
    assert "data-key='llanowar elves'" in lab, "a card name opens the card panel"
    assert "Not owned" in lab and "Never Printed Here" in lab
    assert "action='/deck/theory-deck/lab'" in lab and "Make it a real deck" in lab
    assert "href='/lab'" in page and ">The Lab</a>" in page, "the way back is the Lab"
    assert "fully self-contained" not in page
    assert "Theory deck &middot; in the Lab" in page


def test_a_downloaded_theory_dashboard_has_no_dead_button(env):
    page = bd.generate(str(env.decks / "theory-deck.txt"), env.coll, title="Theory Deck",
                       commander="Theory Commander", decks_dir=str(env.decks),
                       editable=False, sim=None)["dashboard"]
    assert "<label for='tab-lab'>" in page and "Make it a real deck" not in page


def test_a_real_deck_page_has_no_lab_tab(env):
    page = bd.generate(str(env.decks / "real-deck.txt"), env.coll, title="Real",
                       commander="Real Commander", decks_dir=str(env.decks),
                       editable=True, sim=None)["dashboard"]
    assert "<label for='tab-lab'>" not in page and ">All decks</a>" in page
