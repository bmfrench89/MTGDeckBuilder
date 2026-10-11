"""Track R of docs/spec-app-audit-2026-10.md — roles, flags, finders and data.

Every test here failed before its fix: each pins a defect the 2026-10-11 audit
reproduced against the real code. Hermetic — hand-built Cards and tmp_path only.
"""
import os

import combo_detector
import commander_finder
import deck_conflicts
import deck_fit
import make_icons
import mtglib
import oracle_flags


def card(type_line, text, produced=None):
    return {"type_line": type_line, "oracle_text": text,
            "produced_mana": produced or []}


# --- R13: name folding ---------------------------------------------------------
def test_norm_folds_smart_quotes_and_accents():
    assert mtglib._norm("Nature’s Lore") == mtglib._norm("Nature's Lore")
    assert mtglib._norm("Bartolomé del Presidio") == mtglib._norm("Bartolome del Presidio")
    idx = mtglib.index_by_name([mtglib.Card(name="Rogue's Passage")])
    assert mtglib.lookup(idx, "Rogue’s Passage") is not None


# --- D3: run-together colour cells ------------------------------------------------
def test_a_run_of_colour_letters_is_not_colourless():
    assert mtglib._parse_colorish("WUBRG") == set("WUBRG")
    assert mtglib._parse_colorish("BG") == {"B", "G"}
    assert mtglib._parse_colorish("B G") == {"B", "G"}


# --- S1 (mtglib half): front-face costs only ---------------------------------------
def test_split_card_costs_count_the_front_face_only():
    assert mtglib.pip_counts("{1}{B}{B} // {1}{B}{B}")["B"] == 2
    assert mtglib.is_double_pip("{W} // {1}{W}") is None
    assert mtglib.is_double_pip("{1}{B}{B} // {2}") == "B"


# --- S8 (mtglib half): an attrs overlay never downgrades a richer type list ---------
def test_overlay_keeps_artifact_creature(tmp_path):
    coll = tmp_path / "collection.csv"
    coll.write_text("Quantity,Name,Types\n1,Shuri,Artifact;Creature\n", encoding="utf-8")
    (tmp_path / "collection_attrs.csv").write_text(
        "Name,Type,MV,Colors\nShuri,Creature,2,U\n", encoding="utf-8")
    c = mtglib.lookup(mtglib.index_by_name(mtglib.load_collection(str(coll))), "Shuri")
    assert {t.lower() for t in c.types} == {"artifact", "creature"}


# --- R5 / R9 / R15: curated lists ---------------------------------------------------
def test_curated_role_corrections():
    C = mtglib.Card
    assert mtglib.classify(C(name="Smothering Tithe", types=["Enchantment"])) == {"ramp"}
    assert mtglib.classify(C(name="Skyscanner", types=["Artifact", "Creature"])) == {"draw"}
    assert "counter" not in mtglib.classify(C(name="Misstep", types=["Sorcery"]))
    assert mtglib.classify(C(name="Mental Misstep", types=["Instant"])) == {"counter"}
    assert "draw" not in mtglib.classify(C(name="Syphon Soul", types=["Sorcery"]))
    assert "ramp" not in mtglib.classify(C(name="Pilgrim's Eye",
                                           types=["Artifact", "Creature"]))
    assert mtglib.classify(C(name="Casualties of War", types=["Sorcery"])) == {"removal"}
    for rock in ("Orzhov Signet", "Talisman of Unity", "Charcoal Diamond",
                 "Prismatic Lens"):
        assert mtglib.classify(C(name=rock, types=["Artifact"])) == {"ramp"}, rock


# --- R2 / R12: oracle_flags misreads ----------------------------------------------
def test_treasure_reminder_text_is_not_a_mana_ability():
    f = oracle_flags.derive_flags(card(
        "Creature — Human",
        "When this creature enters, create a Treasure token. (It's an artifact with "
        "\"{T}, Sacrifice this token: Add one mana of any color.\")", ["W", "U", "B"]))
    assert not f & {"dork", "rock", "ramp"}


def test_cycling_reminder_text_is_not_draw():
    f = oracle_flags.derive_flags(card(
        "Land — Plains Island",
        "({T}: Add {W} or {U}.)\nThis land enters tapped.\nCycling {2} ({2}, Discard "
        "this card: Draw a card.)", ["W", "U"]))
    assert "draw" not in f
    assert "etb-tapped" in f                      # real rules text still read


def test_active_voice_damage_sweeper_is_a_wipe():
    f = oracle_flags.derive_flags(card(
        "Sorcery", "Anger of the Gods deals 3 damage to each creature. If a creature "
                   "dealt damage this way would die this turn, exile it instead."))
    assert "wipe" in f


def test_a_blink_is_not_removal_but_verb_not_victim_stands():
    eph = oracle_flags.derive_flags(card(
        "Instant", "Exile target creature you control, then return it to the "
                   "battlefield under its owner's control."))
    assert "removal" not in eph
    assert "removal" in oracle_flags.derive_flags(
        card("Instant", "Exile target creature. Its controller gains life equal to "
                        "its power."))


# --- R1: DFC names in field lookups and notes protection ----------------------------
def test_card_value_finds_a_dfc_by_its_front_face():
    field = {mtglib._norm("Studious First-Year"): 78}
    v = deck_fit.card_value("Studious First-Year // Rampant Growth", None, {}, {}, {},
                            field)
    assert v == 78


def test_notes_naming_the_front_face_protect_the_dfc():
    assert deck_fit.named_in_notes("Studious First-Year // Rampant Growth",
                                   "We keep Studious First-Year for the early land.")
    assert not deck_fit.named_in_notes("Sol Ring", "nothing relevant here")


def test_protected_keys_covers_commander_basics_and_notes(tmp_path):
    deck = tmp_path / "d.txt"
    deck.write_text("# Commander: Cmd\n1 Cmd\n1 Vanilla Bear\n10 Forest\n",
                    encoding="utf-8")
    (tmp_path / "d.notes.md").write_text("Vanilla Bear is the plan.", encoding="utf-8")
    cards = [mtglib.Card(name=n) for n in ("Cmd", "Vanilla Bear", "Forest", "Other")]
    keep = deck_fit.protected_keys(str(deck), "Cmd", cards)
    assert {"cmd", "vanilla bear", "forest"} <= keep
    assert "other" not in keep


# --- D1: banned cards are never recommended --------------------------------------------
def test_banned_list_filters_staples_and_alternatives(tmp_path):
    assert deck_fit.is_banned("Dockside Extortionist")
    assert deck_fit.is_banned("Jeweled Lotus")
    assert not deck_fit.is_banned("Sol Ring")
    staples = tmp_path / "role_staples.csv"
    staples.write_text("Role,Colors,Card\nramp,R,Dockside Extortionist\nramp,,Sol Ring\n",
                       encoding="utf-8")
    names = [c["name"] for c in deck_fit.load_role_staples(str(staples))["ramp"]]
    assert names == ["Sol Ring"]


def test_reference_data_no_longer_recommends_banned_cards():
    here = os.path.join(os.path.dirname(__file__), "..", "data", "reference")
    for fn in ("role_staples.csv", "card_notes.csv"):
        text = open(os.path.join(here, fn), encoding="utf-8").read()
        assert "Dockside Extortionist" not in text, fn
        assert "Jeweled Lotus" not in text, fn


# --- R11: study copies commit no physical cards -------------------------------------
def test_study_decks_are_skipped_by_the_conflict_scan(tmp_path):
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "real.txt").write_text("# Commander: A\n1 A\n1 Sol Ring\n", encoding="utf-8")
    (decks / "study.txt").write_text("# Commander: B\n# Study: yes\n1 B\n1 Sol Ring\n",
                                     encoding="utf-8")
    idx = mtglib.index_by_name([mtglib.Card(name=n, quantity=1)
                                for n in ("Sol Ring", "A", "B")])
    assert deck_conflicts.is_study_deck(str(decks / "study.txt"))
    assert not deck_conflicts.is_study_deck(str(decks / "real.txt"))
    assert deck_conflicts.conflicts(deck_conflicts.scan(str(decks), idx)) == []
    assert deck_conflicts.conflicts(deck_conflicts.scan(str(decks), idx,
                                                        include_study=True))


# --- R14: commander_finder counts only playable support ------------------------------
def test_commander_finder_ignores_off_colour_support():
    coll = [mtglib.Card(name="Counterspell", identity={"U"}, colors={"U"},
                        types=["Instant"]),
            mtglib.Card(name="Blood Artist", identity={"B"}, colors={"B"},
                        types=["Creature"])]
    idx = mtglib.index_by_name(coll)
    cmdrs = [{"name": "Mono B", "colors": {"B"}, "archetypes": {"aristocrats"},
              "notes": ""}]
    rows = commander_finder.score(idx, cmdrs,
                                  {"aristocrats": ["Counterspell", "Blood Artist"]})
    assert rows[0]["support_cards"] == ["Blood Artist"]


# --- R7: bracket reasons state the real piece count ----------------------------------
def test_bracket_reason_names_the_real_piece_count():
    detected = {"complete": [{"name": "A + B + C", "result": "infinite",
                              "early": True, "pieces": ["a", "b", "c"]}], "near": []}
    b4, reasons = combo_detector.bracket_signal(detected)
    assert b4 and "3-card" in reasons[0] and "two-card" not in reasons[0]


# --- R16: --help never overwrites the tracked icons ----------------------------------
def test_make_icons_help_writes_nothing(tmp_path, capsys):
    import pytest
    with pytest.raises(SystemExit):
        make_icons.main(["--help", "--out", str(tmp_path)])
    assert list(tmp_path.iterdir()) == []
