"""oracle_flags turns Scryfall's oracle text into the small vocabulary the mana model
and the enrichment columns are built on — so a wrong regex here silently mis-states
what a whole collection taps for.

Every fixture is a hand-written dict shaped like a Scryfall card object: no I/O, no
network, and no dependency on the player's data. The shapes come from Scryfall's
documented card schema; per docs/spec-engine-upgrades.md §4.3 the MDFC shape gets a
one-time check against real Scryfall JSON on the owner's machine, since this sandbox
cannot reach api.scryfall.com.
"""
import oracle_flags


def card(name, type_line, text="", produced=None, faces=None):
    c = {"name": name, "type_line": type_line, "oracle_text": text}
    if produced is not None:
        c["produced_mana"] = produced
    if faces is not None:
        c["card_faces"] = faces
    return c


COMMAND_TOWER = card(
    "Command Tower", "Land",
    "{T}: Add one mana of any color in your commander's color identity.",
    produced=["W", "U", "B", "R", "G"])

SOL_RING = card("Sol Ring", "Artifact", "{T}: Add {C}{C}.", produced=["C"])

LLANOWAR_ELVES = card("Llanowar Elves", "Creature — Elf Druid",
                      "{T}: Add {G}.", produced=["G"])

# MDFC: card-level produced_mana, and the LAND is the back face.
MALAKIR = card(
    "Malakir Rebirth // Malakir Mire", "Instant // Land", text="",
    produced=["B"],
    faces=[{"name": "Malakir Rebirth", "type_line": "Instant",
            "oracle_text": "Until end of turn, target creature you control gains "
                           "\"When this creature dies, return it to the battlefield "
                           "tapped under its owner's control.\""},
           {"name": "Malakir Mire", "type_line": "Land",
            "oracle_text": "Malakir Mire enters tapped.\n{T}: Add {B}."}])

GUILDGATE = card("Azorius Guildgate", "Land — Gate",
                 "Azorius Guildgate enters the battlefield tapped.\n"
                 "{T}: Add {W} or {U}.", produced=["W", "U"])

CHECKLAND = card("Glacial Fortress", "Land",
                 "Glacial Fortress enters tapped unless you control a Plains or an "
                 "Island.\n{T}: Add {W} or {U}.", produced=["W", "U"])

SHOCKLAND = card("Hallowed Fountain", "Land — Plains Island",
                 "As Hallowed Fountain enters, you may pay 2 life. If you don't, it "
                 "enters tapped.\n{T}: Add {W} or {U}.", produced=["W", "U"])

MAZE_OF_ITH = card("Maze of Ith", "Land",
                   "{T}: Untap target attacking creature. Prevent all combat damage "
                   "that would be dealt to and dealt by that creature this turn.",
                   produced=[])

DIVINATION = card("Divination", "Sorcery", "Draw two cards.", produced=[])

GROUP_DRAW = card("Symmetrical Draw", "Sorcery",
                  "Each opponent draws a card.", produced=[])

CULTIVATE = card("Cultivate", "Sorcery",
                 "Search your library for up to two basic land cards, reveal those "
                 "cards, and put one onto the battlefield tapped and the other into "
                 "your hand, then shuffle.", produced=[])

VANILLA = card("Grizzly Bears", "Creature — Bear", "", produced=[])


# ── produced_mana ────────────────────────────────────────────────────────────
def test_command_tower_produces_every_color_and_flags_nothing():
    assert oracle_flags.produced_of(COMMAND_TOWER) == {"W", "U", "B", "R", "G"}
    assert oracle_flags.derive_flags(COMMAND_TOWER) == set()


def test_produced_is_filtered_to_wubrgc():
    """Scryfall has emitted non-mana entries before; anything outside WUBRGC is dropped."""
    c = card("Weird", "Land", "{T}: Add {C}.", produced=["C", "S", "", "g"])
    assert oracle_flags.produced_of(c) == {"C", "G"}


def test_produced_unions_face_level_values():
    """Belt-and-suspenders: an MDFC whose land face is the only producer must not lose
    its colour if a layout ever omits the card-level key."""
    c = card("Front // Back", "Instant // Land", faces=[
        {"type_line": "Instant", "oracle_text": "Draw a card."},
        {"type_line": "Land", "oracle_text": "{T}: Add {R}.", "produced_mana": ["R"]}])
    assert oracle_flags.produced_of(c) == {"R"}


def test_empty_produced_is_a_real_answer_not_unknown():
    assert oracle_flags.produced_of(MAZE_OF_ITH) == set()
    assert oracle_flags.produced_of(VANILLA) == set()


# ── oracle_text_of ───────────────────────────────────────────────────────────
def test_oracle_text_joins_faces_with_the_spaced_separator():
    txt = oracle_flags.oracle_text_of(MALAKIR)
    assert " // " in txt
    assert "Malakir Mire enters tapped." in txt


def test_oracle_text_prefers_the_card_level_text():
    assert oracle_flags.oracle_text_of(SOL_RING) == "{T}: Add {C}{C}."


def test_oracle_text_of_a_textless_card_is_empty():
    assert oracle_flags.oracle_text_of(VANILLA) == ""


# ── rocks, dorks, ramp, amounts ──────────────────────────────────────────────
def test_sol_ring_is_a_two_mana_rock():
    assert oracle_flags.derive_flags(SOL_RING) == {"rock", "ramp", "mana2"}
    assert oracle_flags.produced_of(SOL_RING) == {"C"}


def test_llanowar_elves_is_a_dork_and_adds_one():
    flags = oracle_flags.derive_flags(LLANOWAR_ELVES)
    assert flags == {"dork", "ramp"}
    assert "mana2" not in flags and "mana3" not in flags


def test_three_mana_activation_is_mana3():
    c = card("Big Rock", "Artifact", "{T}: Add {C}{C}{C}.", produced=["C"])
    assert "mana3" in oracle_flags.derive_flags(c)
    assert "mana2" not in oracle_flags.derive_flags(c)


def test_generic_amount_counts_toward_the_mana_tokens():
    c = card("Worn Powerstone", "Artifact", "{T}: Add {2}.", produced=["C"])
    assert "mana2" in oracle_flags.derive_flags(c)


def test_cultivate_text_is_ramp_without_being_a_rock():
    assert oracle_flags.derive_flags(CULTIVATE) == {"ramp"}


def test_a_land_that_taps_for_mana_is_never_a_rock_or_dork():
    assert oracle_flags.derive_flags(COMMAND_TOWER) == set()
    assert "rock" not in oracle_flags.derive_flags(GUILDGATE)


# ── enters-tapped, three-valued on purpose ───────────────────────────────────
def test_guildgate_enters_tapped_unconditionally():
    assert oracle_flags.derive_flags(GUILDGATE) == {"etb-tapped"}


def test_checkland_is_conditional_only():
    assert oracle_flags.derive_flags(CHECKLAND) == {"etb-tapped-cond"}


def test_shockland_is_conditional_only():
    assert oracle_flags.derive_flags(SHOCKLAND) == {"etb-tapped-cond"}


def test_post_foundations_and_older_wordings_both_match():
    old = card("Old", "Land", "Old enters the battlefield tapped.", produced=["W"])
    new = card("New", "Land", "New enters tapped.", produced=["W"])
    assert oracle_flags.derive_flags(old) == oracle_flags.derive_flags(new) == {"etb-tapped"}


def test_mdfc_land_back_face_carries_etb_tapped():
    assert oracle_flags.produced_of(MALAKIR) == {"B"}
    assert oracle_flags.derive_flags(MALAKIR) == {"etb-tapped"}


def test_a_nonland_that_puts_something_in_tapped_is_not_etb_tapped():
    """Cultivate puts a land onto the battlefield tapped — that is not the card
    entering tapped, and etb-tapped only ever reads a LAND face's own text."""
    assert "etb-tapped" not in oracle_flags.derive_flags(CULTIVATE)
    assert "etb-tapped-cond" not in oracle_flags.derive_flags(CULTIVATE)


def test_maze_of_ith_produces_nothing_and_flags_nothing():
    assert oracle_flags.produced_of(MAZE_OF_ITH) == set()
    assert oracle_flags.derive_flags(MAZE_OF_ITH) == set()


# ── draw ─────────────────────────────────────────────────────────────────────
def test_divination_draws():
    assert oracle_flags.derive_flags(DIVINATION) == {"draw"}


def test_symmetrical_group_draw_is_not_your_draw():
    assert "draw" not in oracle_flags.derive_flags(GROUP_DRAW)
    each = card("Wheel", "Sorcery", "Each player draws seven cards.", produced=[])
    assert "draw" not in oracle_flags.derive_flags(each)
    targeted = card("Gift", "Instant", "Target player draws two cards.", produced=[])
    assert "draw" not in oracle_flags.derive_flags(targeted)


def test_vanilla_creature_has_no_flags_and_no_production():
    assert oracle_flags.derive_flags(VANILLA) == set()
    assert oracle_flags.produced_of(VANILLA) == set()


# ── structural ───────────────────────────────────────────────────────────────
def test_module_imports_nothing_but_re():
    """CI imports every scripts/*.py with no third-party packages installed, and this
    module is deliberately the leaf of the enrichment path — keep it stdlib-thin."""
    import ast
    src = open(oracle_flags.__file__, encoding="utf-8").read()
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported == {"re"}


def test_a_bare_dict_never_raises():
    assert oracle_flags.produced_of({}) == set()
    assert oracle_flags.derive_flags({}) == set()
    assert oracle_flags.oracle_text_of({}) == ""
