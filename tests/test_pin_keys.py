"""Phase B — one canonical pin key, so the engines that ENFORCE pins can see them.

A pin reserves one physical card, but that card's name has two spellings for a split
/ double-faced card, and the subsystems disagree about which they use: deck files and
the collection write `"A // B"`, the EDHREC field snapshot and the card panels often
write `"A"`. Pins were stored under `mtglib._norm(name)` — whichever spelling the
writer happened to hold — so a pin was only visible to readers that happened to match.

The failure is two-sided, and both sides are tripwired below:

* a FULL-NAME pin is invisible to `optimize`'s `reserved` filter (front-face field
  keys), so the optimizer OFFERS a card reserved for another deck;
* a FRONT-FACE pin — exactly what the site-wide panel writes when opened from an
  EDHREC-sourced element — is invisible to `optimize`'s keep-set (deck spelling), so
  the optimizer may CUT a card pinned to that very deck.

The fix is `deckcore.pin_key` (normalized FRONT face) applied at the store, so legacy
and hand-edited rows migrate on first read and every probe collides onto one key.
"""
import auto_build
import deckcore
import mtglib
import optimize
import pytest


# A deliberately synthetic split name. A real one (Murderous Rider // Swift End)
# classifies as `removal`, and with removal already below its band the BAND protects
# it from cuts — which made an earlier version of the keep test pass for the wrong
# reason. Role-neutral keeps the assertion about pin keys.
SPLIT = "Alpha Walker // Beta Strider"
FRONT = "Alpha Walker"


@pytest.fixture
def pins_path(tmp_path, monkeypatch):
    p = str(tmp_path / "pins.csv")
    monkeypatch.setattr(deckcore, "PINS", p)
    return p


# ---- the key itself --------------------------------------------------------------

def test_pin_key_canonicalises_to_the_front_face():
    assert deckcore.pin_key(SPLIT) == "alpha walker"
    assert deckcore.pin_key(FRONT) == "alpha walker"
    assert deckcore.pin_key("Sol Ring") == "sol ring"


def test_pin_key_does_not_split_a_bare_slash_name():
    """`SP//dr, Piloted by Peni` has no spaces around its slashes and is ONE card.
    A naive split once produced a bogus alias that let the optimizer add six copies
    of a singleton (CLAUDE.md, Known traps) — `front_face` only splits on ' // '."""
    assert deckcore.pin_key("SP//dr, Piloted by Peni") == "sp//dr, piloted by peni"


def test_legacy_full_name_rows_migrate_on_read_and_write(pins_path):
    """A pins.csv hand-edited (or written by the old code) under the full name must
    load canonical — that is the whole migration, and it needs no script."""
    with open(pins_path, "w", encoding="utf-8") as f:
        f.write("Card,Deck\n" + SPLIT + ",gamma\n")

    assert deckcore.load_pins() == {"alpha walker": "gamma"}
    deckcore.save_pins(deckcore.load_pins())
    assert "alpha walker,gamma" in open(pins_path, encoding="utf-8").read()


def test_save_pins_canonicalises_a_raw_key_written_in_memory(pins_path):
    deckcore.save_pins({mtglib._norm(SPLIT): "gamma"})
    assert deckcore.load_pins() == {"alpha walker": "gamma"}


def test_pinned_elsewhere_passes_explicit_dicts_through_unchanged():
    """Canonicalisation is the STORE's job. Callers handing in their own dict (the
    existing tests do) must keep getting exactly what they passed."""
    pins = {"sol ring": "deck-a", "mana crypt": "deck-b"}
    assert deckcore.pinned_elsewhere("deck-a", pins) == {"mana crypt"}


# ---- the enforcement tripwires ---------------------------------------------------

def _split_card_deck(tmp_path, monkeypatch, *, deck_spelling, field):
    """Two decks that both want one split card, plus a simple-named card the field
    rates highly so a swap can actually MATERIALISE.

    The simple name matters: `optimize` probes `reserved` with the FIELD key but scores
    with `value_of(resolved_name)`, and for a split card those two spellings differ, so
    a split-card add is margin-blocked before the pin logic is observable. Using a plain
    card as the incoming swap keeps the assertions about pins rather than about that.
    """
    import deck_fit
    rows = ["Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,"
            "Sub-types,Rarity,Scryfall ID,MARKET",
            "1,Test Commander,4,B,B,{3}{B},Legendary Creature,Human,rare,g7,1.00",
            "1,Filler Creature,3,B,B,{2}{B},Creature,Human,common,fc1,0.10",
            "1,Good Card,2,B,B,{1}{B},Creature,Human,rare,gc1,1.00",
            f"1,{SPLIT},3,B,B,{{2}}{{B}},Creature,Human,rare,mr1,1.00",
            "12,Swamp,0,,,,Land,Swamp,common,f6,0.10"]
    (tmp_path / "collection.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    decks = tmp_path / "decks"
    decks.mkdir(exist_ok=True)
    # Deck ONE runs the split card AND a filler, so the optimizer has a real choice of
    # victim — that is what makes "did the pin protect it?" observable.
    (decks / "one.txt").write_text(
        "# Title: One\n# Commander: Test Commander\n# Colors: B\n"
        "\n# --- Commander ---\n1 Test Commander\n"
        f"\n# --- Main ---\n1 {deck_spelling}\n1 Filler Creature\n"
        "\n# --- Lands ---\n12 Swamp\n", encoding="utf-8")
    (decks / "two.txt").write_text(
        "# Title: Two\n# Commander: Test Commander\n# Colors: B\n"
        "\n# --- Commander ---\n1 Test Commander\n"
        "\n# --- Main ---\n1 Filler Creature\n"
        "\n# --- Lands ---\n12 Swamp\n", encoding="utf-8")

    monkeypatch.setattr(deck_fit, "load_field", lambda *a, **k: dict(field))
    monkeypatch.setattr(deck_fit, "load_synergy", lambda *a, **k: {})
    monkeypatch.setattr(deckcore, "load_card_notes", lambda *a, **k: {})
    monkeypatch.setattr(deck_fit, "assess_card", lambda card, *a, **k: {
        "score": 40, "band": "x", "reasons": [], "context": "",
        "role": None, "nameonly": False})
    coll = mtglib.load_collection(str(tmp_path / "collection.csv"))
    return coll, mtglib.index_by_name(coll), str(decks)


def test_a_legacy_full_name_pin_reaches_the_reserved_set(tmp_path, monkeypatch,
                                                         pins_path):
    """THE original bug, asserted where it is observable. `optimize` builds `reserved`
    from `pinned_elsewhere` and probes it with EDHREC field keys, which are front
    faces. A pin written under the full name (the old writer, or a hand edit) produced
    a reserved set the field key could never match, so a card reserved for another deck
    was offered as an add. Canonicalising the store is what closes that."""
    with open(pins_path, "w", encoding="utf-8") as f:
        f.write("Card,Deck\n" + SPLIT + ",one\n")

    reserved = deckcore.pinned_elsewhere("two")
    assert FRONT.lower() in reserved, (
        "the reserved set must contain the key the field snapshot probes with")


def test_a_front_face_pin_protects_the_deck_holding_it_from_cuts(tmp_path, monkeypatch,
                                                                 pins_path):
    """The direction the census found. `keep` gets CANONICAL pin keys while the cut
    loop probes with the DECK's spelling, so a deck listing "A // B" used to sail past
    a pin stored as "a" — and the optimizer could cut the card the player reserved for
    that very deck. With a real swap on offer, the victim must be the filler."""
    # Filler carries a little field weight so the SPLIT card is the CHEAPEST cut and
    # would be taken first if the pin were invisible. Without that the two tie at
    # value 0 and "Filler Creature" wins on the alphabetical tiebreak, which would
    # make this test pass for the wrong reason.
    coll, idx, decks = _split_card_deck(tmp_path, monkeypatch, deck_spelling=SPLIT,
                                        field={"good card": 80, "filler creature": 10})
    with open(pins_path, "w", encoding="utf-8") as f:
        f.write("Card,Deck\n" + FRONT + ",one\n")

    r = optimize.optimize(str(decks) + "/one.txt", coll, idx, decks, apply=False)
    cuts = [c for c, _v, _a, _i, _av in r["swaps"]]
    assert cuts, "the fixture must offer a real swap or this proves nothing"
    assert SPLIT not in cuts, "a card pinned HERE must never be the victim"
    assert cuts == ["Filler Creature"]


def test_auto_build_pool_honours_a_canonical_pin(tmp_path, monkeypatch, pins_path):
    """auto_build filters its pool with the COLLECTION's spelling (full names)."""
    with open(pins_path, "w", encoding="utf-8") as f:
        f.write("Card,Deck\n" + SPLIT + ",one\n")     # legacy full-name row
    reserved = deckcore.pinned_elsewhere("two")

    assert deckcore.pin_key(SPLIT) in reserved, (
        "the collection's full-name spelling must resolve onto the canonical pin key")


def test_the_dashboard_panel_shows_a_canonical_pin_on_a_deck_spelled_key(pins_path):
    """build_dashboard keys its panel details by deck spelling; the pin is canonical."""
    with open(pins_path, "w", encoding="utf-8") as f:
        f.write("Card,Deck\n" + FRONT + ",one\n")
    pins = deckcore.load_pins()
    k = mtglib._norm(SPLIT)

    assert next((pins[x] for x in mtglib.name_keys(k) if x in pins), None) == "one", \
        "the panel probe must find a canonical pin from a deck-spelled key"


SPLIT_LAND = "Gamma Bluff // Delta Shore"
FRONT_LAND = "Gamma Bluff"


def test_the_land_pass_will_not_cut_a_pinned_land(tmp_path, monkeypatch, pins_path):
    """The probe this spec's own first census MISSED. `weak_lands` has its own exact-key
    `keep` test, separate from the cut loop's, so a pinned split/MDFC land could be
    offered as a weak-land upgrade even while the spell pass protected it correctly."""
    import deck_fit
    rows = ["Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,"
            "Sub-types,Rarity,Scryfall ID,MARKET",
            "1,Test Commander,4,B,B,{3}{B},Legendary Creature,Human,rare,g7,1.00",
            f"1,{SPLIT_LAND},0,,,,Land,,rare,gb1,1.00",
            "1,Weak Land,0,,,,Land,,common,wl1,0.10",
            "1,Great Land,0,,,,Land,,rare,gl1,1.00",
            "12,Swamp,0,,,,Land,Swamp,common,f6,0.10"]
    (tmp_path / "collection.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    decks = tmp_path / "decks"; decks.mkdir()
    (decks / "one.txt").write_text(
        "# Title: One\n# Commander: Test Commander\n# Colors: B\n"
        "\n# --- Commander ---\n1 Test Commander\n"
        f"\n# --- Lands ---\n1 {SPLIT_LAND}\n1 Weak Land\n12 Swamp\n", encoding="utf-8")
    monkeypatch.setattr(deck_fit, "load_field",
                        lambda *a, **k: {"great land": 90, "weak land": 5})
    monkeypatch.setattr(deck_fit, "load_synergy", lambda *a, **k: {})
    monkeypatch.setattr(deckcore, "load_card_notes", lambda *a, **k: {})
    monkeypatch.setattr(deck_fit, "assess_card", lambda card, *a, **k: {
        "score": 40, "band": "x", "reasons": [], "context": "",
        "role": None, "nameonly": False})
    with open(pins_path, "w", encoding="utf-8") as f:
        f.write("Card,Deck\n" + FRONT_LAND + ",one\n")   # canonical/front-face pin

    coll = mtglib.load_collection(str(tmp_path / "collection.csv"))
    r = optimize.optimize(str(decks / "one.txt"), coll, mtglib.index_by_name(coll),
                          str(decks), apply=False)
    cut_lands = [old for old, _new, _avail in r["land_swaps"]]
    assert SPLIT_LAND not in cut_lands, "a pinned land must survive the land pass"
