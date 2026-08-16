"""Card-notes layering: hand-written notes must always beat machine-drafted ones, and the
generator must refuse to invent anything it can't source."""
import gen_card_notes as gen
import deckcore
import mtglib


CURATED = "Name,Why,Alternatives\nSol Ring,Hand written blurb.,Mana Vault\n"
GENERATED = ("Name,Why,Alternatives\n"
             "Sol Ring,Machine draft that must lose.,X\n"
             "Llanowar Elves,Machine draft that should win.,Y\n")


def _notes_dir(tmp_path):
    (tmp_path / "card_notes.csv").write_text(CURATED, encoding="utf-8")
    (tmp_path / "card_notes.generated.csv").write_text(GENERATED, encoding="utf-8")
    return str(tmp_path / "card_notes.csv")


def test_curated_note_beats_generated(tmp_path):
    notes = deckcore.load_card_notes(_notes_dir(tmp_path))
    assert notes[mtglib._norm("Sol Ring")]["why"] == "Hand written blurb."
    assert notes[mtglib._norm("Sol Ring")]["generated"] is False


def test_generated_fills_uncovered_cards(tmp_path):
    notes = deckcore.load_card_notes(_notes_dir(tmp_path))
    assert notes[mtglib._norm("Llanowar Elves")]["why"] == "Machine draft that should win."
    assert notes[mtglib._norm("Llanowar Elves")]["generated"] is True


def test_generated_layer_can_be_disabled(tmp_path):
    notes = deckcore.load_card_notes(_notes_dir(tmp_path), include_generated=False)
    assert mtglib._norm("Llanowar Elves") not in notes


def test_no_oracle_text_means_no_note():
    """Grounding rule #3: never write a blurb for a card we couldn't verify."""
    assert gen.compose("X", None, "", "Creature", "{1}", {}, {}, {}) is None


def test_a_bare_type_line_is_not_worth_a_note():
    """'A 3-mana creature.' adds nothing the panel doesn't already show."""
    card = mtglib.Card(name="Vanilla", quantity=1, mana_value=3, types=["Creature"])
    assert gen.compose("Vanilla", card, "Vanilla creature with no abilities.",
                       "Creature — Bear", "{2}{G}", {}, {}, {}) is None


def test_mechanic_is_read_from_oracle_text():
    card = mtglib.Card(name="Drawer", quantity=1, mana_value=3, types=["Instant"])
    why = gen.compose("Drawer", card, "Draw three cards.", "Instant", "{2}{U}", {}, {}, {})
    assert why and "draws you cards" in why


def test_field_verdict_is_included_when_the_data_has_it():
    card = mtglib.Card(name="Signature", quantity=1, mana_value=3, types=["Enchantment"])
    field = {"Cmdr": {mtglib._norm("Signature"): 77}}
    syn = {"Cmdr": {mtglib._norm("Signature"): 69}}
    why = gen.compose("Signature", card, "Draw a card.", "Enchantment", "{2}{R}",
                      field, syn, {"Cmdr": True})
    assert "signature pick for Cmdr" in why and "77%" in why


def test_no_duplicate_phrasing():
    """'produces mana - it accelerates your mana' said the same thing twice."""
    card = mtglib.Card(name="Rock", quantity=1, mana_value=2, types=["Artifact"])
    why = gen.compose("Rock", card, "{T}: Add {C}{C}.", "Artifact", "{2}", {}, {}, {})
    assert why.count("mana") <= 2


# --------------------------------------------------------------------------- #
# The oracle fetch shares carddb's Scryfall client (docs/spec-dfc-enrichment.md §3B).
#
# It used to hand-roll the request, the headers and the backoff ladder, which
# meant it also hand-rolled two bugs carddb had already fixed: it asked for the
# full "Front // Back" name (which /cards/collection never matches — the `name`
# identifier matches a SINGLE face), and it split the response name on a bare
# "//". Every double-faced card therefore got no note, silently.

def _fake_post(monkeypatch, cards):
    import carddb
    asked = []

    def post(idents, retries=4):
        asked.extend(idents)
        return (list(cards), [])
    monkeypatch.setattr(carddb, "_post_collection", post)
    monkeypatch.setattr(gen.time, "sleep", lambda *_a: None)
    return asked


def test_the_oracle_fetch_asks_for_the_front_face_and_keys_on_both_names(monkeypatch):
    asked = _fake_post(monkeypatch, [{
        "name": "Murderous Rider // Swift End",
        "type_line": "Creature — Zombie Knight // Instant — Adventure",
        "mana_cost": "{1}{B}{B}",
        "card_faces": [{"oracle_text": "Lifelink."},
                       {"oracle_text": "Destroy target creature or planeswalker."}]}])
    out = gen._fetch_oracle(["Murderous Rider // Swift End"])
    assert asked == [{"name": "Murderous Rider"}], "the combined name never matches"
    # the note lookup may hold either spelling, so both must resolve
    for key in ("murderous rider // swift end", "murderous rider"):
        assert key in out, f"{key!r} did not resolve"
    assert "Lifelink." in out["murderous rider"][0], \
        "a DFC's text lives on its faces, not on the card object"


def test_the_oracle_fetch_never_splits_a_bare_double_slash(monkeypatch):
    """The `SP//dr` trap (CLAUDE.md): the old code's `.split('//')[0].strip()`
    aliased this card to 'SP'."""
    asked = _fake_post(monkeypatch, [{"name": "SP//dr, Piloted by Peni",
                                      "type_line": "Creature — Robot",
                                      "mana_cost": "{2}", "oracle_text": "Flying."}])
    out = gen._fetch_oracle(["SP//dr, Piloted by Peni"])
    assert asked == [{"name": "SP//dr, Piloted by Peni"}]
    assert "sp//dr, piloted by peni" in out
    assert "sp" not in out, "a bare // is part of the name, not a separator"
