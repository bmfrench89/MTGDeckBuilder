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
    assert oracle_flags.derive_flags(CULTIVATE) == {"ramp", "fetch:basic"}


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


# ── interaction: removal / wipe / counter ────────────────────────────────────
SWORDS = card("Swords to Plowshares", "Instant",
              "Exile target creature. Its controller gains life equal to its power.",
              produced=[])

DAMNATION = card("Damnation", "Sorcery",
                 "Destroy all creatures. They can't be regenerated.", produced=[])

TOXIC_DELUGE = card("Toxic Deluge", "Sorcery",
                    "As an additional cost to cast this spell, pay X life.\n"
                    "All creatures get -X/-X until end of turn.", produced=[])

COUNTERSPELL = card("Counterspell", "Instant", "Counter target spell.", produced=[])

BANISHING_LIGHT = card(
    "Banishing Light", "Enchantment",
    "When Banishing Light enters, exile target nonland permanent an opponent "
    "controls until Banishing Light leaves the battlefield.", produced=[])

# A modal DFC whose front face is a creature and whose back face sweeps.
MODAL_WIPE = card("Bear Front // Sweeping Back", "Creature // Sorcery", text="",
                  produced=[],
                  faces=[{"type_line": "Creature — Bear",
                          "oracle_text": "Vigilance."},
                         {"type_line": "Sorcery",
                          "oracle_text": "Destroy all creatures."}])


def test_swords_style_exile_target_is_removal():
    assert oracle_flags.derive_flags(SWORDS) == {"removal"}


def test_removal_reads_the_verb_not_the_victim():
    """The accepted heuristic, stated in the module docstring: 'destroy target land
    you control' is `removal` too. Narrowing it means parsing targeting restrictions,
    which is a rules engine — the curated lists and human verification are the guard."""
    c = card("Self Sacrifice", "Sorcery", "Destroy target land you control.", produced=[])
    assert "removal" in oracle_flags.derive_flags(c)


def test_an_enchantment_that_exiles_a_target_is_removal():
    assert oracle_flags.derive_flags(BANISHING_LIGHT) == {"removal"}


def test_an_etb_creature_that_destroys_is_not_flagged_removal():
    """Type-gated on purpose: a creature is a creature first, and classify()'s type
    fallback already says so. Flagging it removal would double-count the body."""
    c = card("Ravenous Chupacabra", "Creature — Beast Horror",
             "When this creature enters, destroy target creature an opponent controls.",
             produced=[])
    assert "removal" not in oracle_flags.derive_flags(c)


def test_damnation_style_destroy_all_is_a_wipe():
    assert oracle_flags.derive_flags(DAMNATION) == {"wipe"}


def test_the_each_creature_shrink_form_is_a_wipe():
    assert oracle_flags.derive_flags(TOXIC_DELUGE) == {"wipe"}


def test_the_is_dealt_form_is_a_wipe():
    c = card("Sweeper", "Instant",
             "Each creature is dealt 4 damage.", produced=[])
    assert "wipe" in oracle_flags.derive_flags(c)


def test_a_wipe_is_not_also_spot_removal():
    """'Destroy all' carries no 'target', so the two tokens don't both fire and
    double-count one card across two role buckets."""
    assert "removal" not in oracle_flags.derive_flags(DAMNATION)


def test_counterspell_style_text_is_counter():
    assert oracle_flags.derive_flags(COUNTERSPELL) == {"counter"}


def test_counter_spans_the_qualifier_between_target_and_spell():
    for txt in ("Counter target creature spell.",
                "Counter target noncreature spell.",
                "Counter target spell unless its controller pays {2}."):
        assert "counter" in oracle_flags.derive_flags(
            card("X", "Instant", txt, produced=[])), txt


def test_countering_an_ability_is_not_a_counter_flag():
    c = card("Stifle", "Instant", "Counter target activated or triggered ability.",
             produced=[])
    assert "counter" not in oracle_flags.derive_flags(c)


def test_a_modal_spell_whose_one_face_wipes_is_a_wipe():
    """Face-aware, exactly like the mana tokens: a flag fires if ANY face matches."""
    assert "wipe" in oracle_flags.derive_flags(MODAL_WIPE)


def test_the_new_tokens_do_not_disturb_the_mana_vocabulary():
    assert oracle_flags.derive_flags(SOL_RING) == {"rock", "ramp", "mana2"}
    assert oracle_flags.derive_flags(GUILDGATE) == {"etb-tapped"}


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


# --------------------------------------------------------------------------- #
# v2 vocabulary — fetch targets and spend restrictions
#
# These exist because the v1 search regex needs the literal word "land"
# (`search your library for [^.]*\bland`), and "island" does not match `\bland`.
# The whole typed-fetch class was therefore invisible: Farseek, Nature's Lore and
# Wood Elves carry NO flags at all in the committed collection snapshot — Wood
# Elves does not even register as `ramp`.
# --------------------------------------------------------------------------- #
WOOD_ELVES = card("Wood Elves", "Creature — Elf Scout",
                  "When Wood Elves enters, search your library for a Forest card, "
                  "put it onto the battlefield, then shuffle.")
FARSEEK = card("Farseek", "Sorcery",
               "Search your library for a Plains, Island, Swamp, or Mountain card, "
               "put it onto the battlefield tapped, then shuffle.")
NISSAS_PILGRIMAGE = card("Nissa's Pilgrimage", "Sorcery",
                         "Search your library for up to two basic Forest cards, "
                         "reveal them, put one onto the battlefield tapped and the "
                         "rest into your hand, then shuffle.")
KROSAN_VERGE = card("Krosan Verge", "Land",
                    "This land enters tapped.\n{T}, Sacrifice this land: Search your "
                    "library for a Forest card and a Plains card, put them onto the "
                    "battlefield tapped, then shuffle.")
EVOLVING_WILDS = card("Evolving Wilds", "Land",
                      "{T}, Sacrifice this land: Search your library for a basic land "
                      "card, put it onto the battlefield tapped, then shuffle.")
EXPEDITION_MAP = card("Expedition Map", "Artifact",
                      "{2}, {T}, Sacrifice this artifact: Search your library for a "
                      "land card, put it into your hand, then shuffle.")
DEMONIC_TUTOR = card("Demonic Tutor", "Sorcery",
                     "Search your library for a card, put that card into your hand, "
                     "then shuffle.")
UNCLAIMED_TERRITORY = card(
    "Unclaimed Territory", "Land",
    "As this land enters, choose a creature type.\n{T}: Add {C}.\n"
    "{T}: Add one mana of any color. Spend this mana only to cast a creature spell "
    "of the chosen type.",
    produced=["C", "W", "U", "B", "R", "G"])


def test_a_typed_fetch_names_the_type_it_can_actually_find():
    """The live miss this vocabulary exists for. A typed nonbasic satisfies a
    typed fetch — Wood Elves finds Scattered Groves — so the token is the TYPE,
    not 'basic'."""
    assert oracle_flags.derive_flags(WOOD_ELVES) == {"ramp", "fetch:forest"}


def test_a_multi_type_fetch_emits_one_token_per_type():
    assert oracle_flags.derive_flags(FARSEEK) == {
        "ramp", "fetch:plains", "fetch:island", "fetch:swamp", "fetch:mountain"}


def test_basic_qualified_typed_fetch_is_its_own_token():
    """'a basic Forest card' is NOT satisfied by a Forest-typed dual, so it must
    not share a token with 'a Forest card'."""
    assert oracle_flags.derive_flags(NISSAS_PILGRIMAGE) == {"ramp",
                                                            "fetch:basic-forest"}


def test_two_searches_in_one_clause_are_a_union():
    """Krosan Verge finds a Forest AND a Plains — the tokens describe what it can
    find, and a union is the honest reading."""
    f = oracle_flags.derive_flags(KROSAN_VERGE)
    assert {"fetch:forest", "fetch:plains"} <= f
    assert "etb-tapped" in f, "the v1 land rules still apply to the same card"


def test_basic_land_fetch_stays_generic():
    assert oracle_flags.derive_flags(EVOLVING_WILDS) == {"ramp", "fetch:basic"}


def test_a_fetch_to_hand_is_not_ramp():
    """`ramp` keeps its v1 meaning — onto the battlefield. Expedition Map finds a
    land but accelerates nothing."""
    assert oracle_flags.derive_flags(EXPEDITION_MAP) == {"fetch:land"}


def test_a_tutor_that_names_no_land_fetches_nothing():
    """The clause is read, not the verb: 'search your library for a card' names
    neither a type nor a land, so Demonic Tutor stays silent."""
    assert oracle_flags.derive_flags(DEMONIC_TUTOR) == set()


def test_a_spend_restricted_land_is_flagged_but_still_produces_everything():
    """The two halves must not be conflated. Scryfall genuinely reports every
    colour in produced_mana — the restriction is only in the text, so this token
    is the only way a consumer can tell a rainbow land from a rainbow-for-one-
    tribe land. Counting it as a full source of five colours is an OVERCOUNT,
    which is what the downstream bucket corrects."""
    assert oracle_flags.derive_flags(UNCLAIMED_TERRITORY) == {"mana-restricted"}
    assert oracle_flags.produced_of(UNCLAIMED_TERRITORY) == set("WUBRGC")


def test_the_new_tokens_do_not_disturb_the_mana_vocabulary():
    """THE tripwire for this phase. Every v1 pin must come out unchanged — the
    new tokens are additive, and a regex that co-fires on a v1 fixture would
    silently move role counts, power scores and optimizer guardrails."""
    assert oracle_flags.derive_flags(SOL_RING) == {"rock", "ramp", "mana2"}
    assert oracle_flags.derive_flags(COMMAND_TOWER) == set()
    assert oracle_flags.derive_flags(MAZE_OF_ITH) == set()
    assert oracle_flags.derive_flags(GUILDGATE) == {"etb-tapped"}
    assert oracle_flags.derive_flags(SHOCKLAND) == {"etb-tapped-cond"}
    assert oracle_flags.derive_flags(SWORDS) == {"removal"}


def test_new_tokens_map_to_no_classify_role():
    """Deliberately absent from FLAG_ROLES: lands short-circuit before the flag
    layer anyway, and mapping fetch:* to 'ramp' would reclassify every fetchland
    and move every downstream count."""
    import mtglib
    for token in ("fetch:land", "fetch:basic", "fetch:forest",
                  "fetch:basic-forest", "mana-restricted"):
        assert token not in mtglib.FLAG_ROLES


def test_v2_tokens_are_inert_in_classify_for_uncurated_cards():
    """The end-to-end inertness claim, durable. A card no curated list knows,
    carrying only v2 tokens, must classify exactly as it would without them —
    the type fallback for a creature, the land short-circuit for a land. (The
    live before/after proof at ship time diffed all 2,621 snapshot cards and 6
    decks; this is the piece of it that survives as a test.)"""
    import mtglib
    c = mtglib.Card(name="Uncurated Scout", types=["Creature"],
                    flags={"fetch:forest"}, flags_ver=2)
    assert mtglib.classify(c) == {"creature"}
    land = mtglib.Card(name="Uncurated Grove", types=["Land"],
                       flags={"fetch:basic", "mana-restricted"}, flags_ver=2)
    assert mtglib.classify(land) == {"land"}
