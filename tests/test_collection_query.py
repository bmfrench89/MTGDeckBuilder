"""The collection query language (scripts/collection_query.py).

One string filters, sorts and counts the collection for the Collection page,
`analyze_collection.py --query` and the skill. These tests pin what the 2026-10-14
collection research measured on the old page, and the rules that keep a search
honest:
- "sol" ranks Sol Ring first, and "solring" and "ur dragon" find their cards;
- t:dragon counts every Dragon, not just the ones named "Dragon";
- "free green ramp" has two right answers (id<=g and id>=g), both reachable;
- a row with missing data is skipped and counted, never read as false;
- a typo warns and is ignored, never a silent zero;
- basics are unlimited, and study decks hold no physical cards.
Hermetic: every card is built here, every deck lives in tmp_path.
"""
import json
import os
import subprocess
import sys

import collection_query as cq
import mtglib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = "2026-10-14"


def C(name, qty=1, types=(), sub=(), sup=(), ident="", cost="", mv=None, **kw):
    return mtglib.Card(name=name, quantity=qty, types=list(types), subtypes=list(sub),
                       supertypes=list(sup), identity=set(ident), colors=set(ident),
                       mana_cost=cost, mana_value=mv, **kw)


def build(cards, decks=None, tmp_path=None, pins=None, **kw):
    ddir = None
    if decks is not None:
        ddir = tmp_path / "decks"
        ddir.mkdir(exist_ok=True)
        for stem, text in decks.items():
            (ddir / f"{stem}.txt").write_text(text, encoding="utf-8")
    return cq.records(cards, str(ddir) if ddir else None, pins=pins or {}, power_tags={},
                      commanders=set(), banned=set(), today=TODAY, **kw)


def names(res):
    return [r.name for r in res.rows]


# --------------------------------------------------------------------------- #
# Names: the three searches the audit watched fail
# --------------------------------------------------------------------------- #
SOL = [C("Absolute Grace", types=["Enchantment"]), C("Desolate Mire", types=["Land"]),
       C("Isolated Chapel", types=["Land"]), C("Solemn Simulacrum", types=["Artifact"]),
       C("Sol Ring", types=["Artifact"]), C("The Ur-Dragon", types=["Creature"],
                                            sub=["Dragon", "Avatar"])]


def test_sol_ranks_sol_ring_first():
    recs, ctx = build(SOL)
    res = cq.run("sol", recs, ctx)
    assert names(res)[0] == "Sol Ring", "a whole-word prefix beats a substring"
    assert res.order_label == "Best match"
    assert names(res).index("Solemn Simulacrum") < names(res).index("Desolate Mire")


def test_solring_and_ur_dragon_find_their_cards():
    recs, ctx = build(SOL)
    assert names(cq.run("solring", recs, ctx)) == ["Sol Ring"]
    assert names(cq.run("ur dragon", recs, ctx)) == ["The Ur-Dragon"]
    assert names(cq.run('"sol ring"', recs, ctx)) == ["Sol Ring"]
    assert names(cq.run('!"sol ring"', recs, ctx)) == ["Sol Ring"]
    assert names(cq.run("/^sol/", recs, ctx)) == ["Sol Ring", "Solemn Simulacrum"]


def test_phone_smart_quotes_still_quote():
    recs, ctx = build(SOL)
    assert names(cq.run("“sol ring”", recs, ctx)) == ["Sol Ring"]


# --------------------------------------------------------------------------- #
# Types: count the pool, never the name
# --------------------------------------------------------------------------- #
DRAGONS = [C("Old Gnawbone", types=["Creature"], sub=["Dragon"], ident="G"),
           C("Thundermaw Hellkite", types=["Creature"], sub=["Dragon"], ident="R"),
           C("Lathliss, Dragon Queen", types=["Creature"], sub=["Dragon"], ident="R"),
           C("Dragon's Hoard", types=["Artifact"]),
           C("Llanowar Elves", types=["Creature"], sub=["Elf", "Druid"], ident="G"),
           C("Mystery Card")]                                     # name-only row


def test_t_dragon_counts_every_dragon_and_counts_what_it_skipped():
    recs, ctx = build(DRAGONS)
    res = cq.run("t:dragon", recs, ctx)
    assert sorted(names(res)) == ["Lathliss, Dragon Queen", "Old Gnawbone",
                                  "Thundermaw Hellkite"], "the hoard is no Dragon"
    assert res.skipped == 1 and res.reasons == [("no card data yet", 1)]
    assert "1 skipped: no card data yet (1)" in res.summary
    assert names(cq.run("dragon", recs, ctx)) == ["Dragon's Hoard", "Lathliss, Dragon Queen"]


def test_a_type_nobody_has_suggests_the_near_miss():
    recs, ctx = build(DRAGONS)
    res = cq.run("t:dragons", recs, ctx)
    assert any("did you mean t:dragon?" in w for w in res.warnings)


def test_a_type_line_carddb_cut_short_is_unknown_not_false():
    # carddb writes ONE main type (the first of land, creature, …, sorcery). A row
    # that says "Creature" may be an Artifact Creature, but can never be a Land.
    golem = C("Solemn Simulacrum", types=["Creature"], sub=["Golem"])
    recs, ctx = build([golem])
    r = recs[0]
    assert cq._has_type(r, "creature") is True
    assert cq._has_type(r, "artifact") is None, "may have been dropped"
    assert cq._has_type(r, "land") is False, "would have been the written type"
    assert cq._has_type(r, "legendary") is None
    assert cq._has_type(r, "golem") is True and cq._has_type(r, "elf") is False
    res = cq.run("t:artifact", recs, ctx)
    assert res.matched == 0 and res.reasons == [("only the main type is known", 1)]


def test_an_export_row_has_its_whole_type_line():
    rich = C("Sol Ring", types=["Artifact"], rarity="uncommon")
    legend = C("Old Gnawbone", types=["Creature"], sub=["Dragon"], sup=["Legendary"],
               rarity="mythic")
    recs, ctx = build([rich, legend])
    assert cq._has_type(recs[0], "creature") is False
    assert cq._has_type(recs[0], "legendary") is False, "the export says no supertype"
    assert names(cq.run("t:legendary", recs, ctx)) == ["Old Gnawbone"]
    assert names(cq.run("is:commander", recs, ctx)) == ["Old Gnawbone"]


def test_no_supertype_data_anywhere_says_so_instead_of_zero():
    recs, ctx = build(DRAGONS)
    res = cq.run("t:legendary", recs, ctx)
    assert res.matched == 0 and res.skipped == len(recs)
    assert any("can't be answered for any card yet" in w for w in res.warnings)


# --------------------------------------------------------------------------- #
# Colour: identity vs colours, and the two honest "green" answers
# --------------------------------------------------------------------------- #
# Rarity marks an export row, and Forest's Basic supertype shows the export carries
# supertypes, so these rows have whole type lines (see _has_type).
RAMP = [C("Sol Ring", types=["Artifact"], cost="{1}", mv=1, rarity="uncommon"),
        C("Arcane Signet", types=["Artifact"], cost="{2}", mv=2, rarity="common"),
        C("Llanowar Elves", types=["Creature"], sub=["Elf"], ident="G", cost="{G}", mv=1,
          rarity="common"),
        C("Cultivate", types=["Sorcery"], ident="G", cost="{2}{G}", mv=3, rarity="common"),
        C("Simic Signet", types=["Artifact"], ident="GU", cost="{2}", mv=2, rarity="common"),
        C("Talisman of Indulgence", types=["Artifact"], ident="BR", cost="{2}", mv=2,
          rarity="uncommon"),
        C("Kodama's Reach", types=["Sorcery"], ident="G", cost="{2}{G}", mv=3,
          rarity="common"),
        C("Wood Elves", qty=2, types=["Creature"], sub=["Elf"], ident="G", cost="{2}{G}",
          mv=3, rarity="common"),
        C("Hallowed Fountain", types=["Land"], ident="WU", rarity="rare"),
        C("Forest", qty=1, types=["Land"], sup=["Basic"], ident="G", rarity="common")]
DECKS = {"elves": "# Title: Elves\n# Commander: Test\n# Colors: G\n"
                  "# --- Creatures ---\n1 Wood Elves\n# --- Sorceries ---\n1 Kodama's Reach\n"
                  "# --- Lands ---\n30 Forest\n",
         "study": "# Title: Study list\n# Study: yes\n# Colors: G\n"
                  "# --- Sorceries ---\n1 Cultivate\n"}


def test_free_green_ramp_has_both_answers(tmp_path):
    recs, ctx = build(RAMP, DECKS, tmp_path)
    fits = cq.run("id<=g role:ramp free>0", recs, ctx)
    has_g = cq.run("id>=g role:ramp free>0", recs, ctx)
    assert sorted(names(fits)) == ["Arcane Signet", "Cultivate", "Llanowar Elves",
                                   "Sol Ring", "Wood Elves"]
    assert sorted(names(has_g)) == ["Cultivate", "Llanowar Elves", "Simic Signet",
                                    "Wood Elves"]
    assert fits.summary.startswith("5 cards · identity within G · role ramp · free copies > 0")
    assert "Kodama's Reach" not in names(fits), "its one copy is sleeved"


def test_colours_come_from_the_cost_not_the_identity():
    # The attrs overlay fills an empty Colors cell with the identity, so a dual land
    # read as white and blue. The mana cost says colourless.
    recs, ctx = build(RAMP)
    assert "Hallowed Fountain" in names(cq.run("c:c", recs, ctx))
    assert "Hallowed Fountain" not in names(cq.run("c:w", recs, ctx))
    assert "Hallowed Fountain" in names(cq.run("id>=w", recs, ctx))
    assert names(cq.run("c=g t:creature", recs, ctx)) == ["Llanowar Elves", "Wood Elves"]
    assert names(cq.run("id:simic t:artifact", recs, ctx)) == ["Arcane Signet",
                                                                "Simic Signet", "Sol Ring"]
    assert names(cq.run("id:m", recs, ctx)) == ["Hallowed Fountain", "Simic Signet",
                                                "Talisman of Indulgence"]


# --------------------------------------------------------------------------- #
# The household words: free, decks, deck:, for:, pins, basics, study decks
# --------------------------------------------------------------------------- #
def test_study_lists_answer_deck_but_hold_no_physical_cards(tmp_path):
    recs, ctx = build(RAMP, DECKS, tmp_path)
    by = {r.name: r for r in recs}
    assert by["Cultivate"].decks == {} and by["Cultivate"].free == 1
    assert names(cq.run("deck:study", recs, ctx)) == ["Cultivate"]
    assert names(cq.run('deck:"study list"', recs, ctx)) == ["Cultivate"]
    assert sorted(names(cq.run("decks>0 -is:basic", recs, ctx))) == ["Kodama's Reach",
                                                                     "Wood Elves"]
    assert names(cq.run("in:deck -t:land", recs, ctx)) == ["Kodama's Reach", "Wood Elves"]
    assert by["Wood Elves"].free == 1 and by["Kodama's Reach"].free == 0


def test_basics_are_unlimited(tmp_path):
    recs, ctx = build(RAMP, DECKS, tmp_path)
    forest = next(r for r in recs if r.name == "Forest")
    assert forest.decks == {"elves": 30} and not forest.short
    for q in ("qty>5", "free>0", "free>=99", "is:free"):
        assert "Forest" in names(cq.run(q, recs, ctx)), q
    assert "Forest" not in names(cq.run("is:shared", recs, ctx))


def test_a_pin_reserves_a_copy_and_is_shared_means_short(tmp_path):
    decks = dict(DECKS, more="# Title: More\n# Colors: G\n# --- Sorceries ---\n"
                             "1 Kodama's Reach\n")
    recs, ctx = build(RAMP, decks, tmp_path, pins={"llanowar elves": "elves"})
    by = {r.name: r for r in recs}
    assert by["Llanowar Elves"].free == 0, "pinned to a deck that doesn't list it yet"
    assert names(cq.run("is:pinned", recs, ctx)) == ["Llanowar Elves"]
    assert names(cq.run("is:shared", recs, ctx)) == ["Kodama's Reach"]
    assert names(cq.run("decks>=2", recs, ctx)) == ["Kodama's Reach"]


def test_for_a_deck_reads_its_colour_line(tmp_path):
    recs, ctx = build(RAMP, DECKS, tmp_path)
    got = names(cq.run("for:elves t:artifact", recs, ctx))
    assert got == ["Arcane Signet", "Sol Ring"]
    res = cq.run("deck:nonesuch", recs, ctx)
    assert any("No saved deck matches" in w for w in res.warnings)
    assert res.matched == len(recs), "an unreadable term is dropped, not a silent zero"


def test_new_and_added_dates():
    cards = [C("Sol Ring", types=["Artifact"], date_added="2026-10-10"),
             C("Arcane Signet", types=["Artifact"], date_added="2026-08-01"),
             C("Mind Stone", types=["Artifact"])]
    recs, ctx = build(cards)
    assert names(cq.run("is:new", recs, ctx)) == ["Sol Ring"]
    res = cq.run("added>=2026-09", recs, ctx)
    assert names(res) == ["Sol Ring"] and res.reasons == [("no date added", 1)]
    assert names(cq.run("added:2026-08", recs, ctx)) == ["Arcane Signet"]
    assert names(cq.run("added<2026-10-10", recs, ctx)) == ["Arcane Signet"]
    assert names(cq.run("-has:date", recs, ctx)) == ["Mind Stone"]


# --------------------------------------------------------------------------- #
# Grammar: precedence, negation, groups, mid-typing, mistakes
# --------------------------------------------------------------------------- #
def test_and_binds_tighter_than_or():
    recs, ctx = build(RAMP)
    # (t:creature mv=3) or t:land — Scryfall's precedence; Cockatrice's would differ.
    got = names(cq.run("t:creature mv=3 or t:land", recs, ctx))
    assert got == ["Forest", "Hallowed Fountain", "Wood Elves"]
    got = names(cq.run("t:creature (mv=3 or t:land)", recs, ctx))
    assert got == ["Wood Elves"]


def test_negation_and_not_and_groups():
    recs, ctx = build(RAMP)
    assert "Sol Ring" not in names(cq.run("-t:artifact", recs, ctx))
    assert names(cq.run("-(t:artifact or t:land) -mv=3", recs, ctx)) == ["Llanowar Elves"]
    assert names(cq.run("not:basic t:land", recs, ctx)) == ["Hallowed Fountain"]


def test_half_typed_queries_are_closed_or_dropped_quietly():
    recs, ctx = build(RAMP)
    for q in ("t:", "ro:", "t:creature or", "or t:creature", "(t:creature", 't:creature "',
              "t:creature -", "t:creature )"):
        res = cq.run(q, recs, ctx)
        assert not res.warnings, (q, res.warnings)
    assert names(cq.run("(t:creature", recs, ctx)) == ["Llanowar Elves", "Wood Elves"]
    # A stray ')' mid-query once ended the parse: everything after it vanished.
    assert names(cq.run("t:creature ) mv=1", recs, ctx)) == ["Llanowar Elves"]


def test_a_typo_warns_and_is_never_a_silent_zero():
    recs, ctx = build(RAMP)
    res = cq.run("rol:ramp", recs, ctx)
    assert res.matched == len(recs)
    assert any("Did you mean role:?" in w for w in res.warnings)
    res = cq.run("role:rmap t:creature", recs, ctx)
    assert any("did you mean role:ramp?" in w for w in res.warnings)
    assert names(res) == ["Llanowar Elves", "Wood Elves"], "the rest of the query stands"
    for q, needle in (("mv>=x", "needs a number"), ("/[/", "isn't a pattern"),
                      ("o:draw", "Rules text isn't stored"), ("f:modern", "Only Commander"),
                      ("is:sparkly", "isn't something this search knows"),
                      ("c:purple", "isn't a colour"), ("order:vibes", "Can't sort by")):
        res = cq.run(q, recs, ctx)
        assert any(needle in w for w in res.warnings), q


def test_order_direction_and_unknown_last():
    cards = [C("A", types=["Artifact"], mv=3, price=2.0), C("B", types=["Artifact"], mv=1),
             C("C", types=["Artifact"], mv=5, price=9.0), C("D", types=["Artifact"])]
    recs, ctx = build(cards)
    assert names(cq.run("order:mv", recs, ctx)) == ["B", "A", "C", "D"]
    assert names(cq.run("order:mv direction:desc", recs, ctx)) == ["C", "A", "B", "D"]
    assert names(cq.run("order:usd", recs, ctx)) == ["C", "A", "B", "D"], "unpriced last"
    assert names(cq.run("", recs, ctx, order="usd", direction="asc")) == ["A", "C", "B", "D"]
    res = cq.run("t:artifact", recs, ctx, group="mv")
    assert [g["label"] for g in res.groups] == ["MV 1", "MV 3", "MV 5", "No mana value"]


def test_chips_remove_their_own_text():
    recs, ctx = build(RAMP)
    res = cq.run('t:creature (mv=1 or mv=3) -"wood"', recs, ctx)
    assert [c["label"] for c in res.chips] == ["t:creature", "(mv=1 or mv=3)", '-"wood"']
    assert res.chips[1]["remove"] == 't:creature -"wood"'
    assert res.chips[1]["means"] == "mana value = 1 or mana value = 3"


# --------------------------------------------------------------------------- #
# The help is generated from the table, and the table is honest
# --------------------------------------------------------------------------- #
def test_every_help_example_parses_clean(tmp_path):
    recs, ctx = build(RAMP + DRAGONS[:1],
                      dict(DECKS, **{"ur-dragon": "# Title: Ur\n# Colors: WUBRG\n"}), tmp_path)
    rows = cq.help_rows()
    assert {r["key"] for r in rows} >= {"name", "t", "id", "free", "decks", "deck", "for",
                                        "role", "is", "order"}
    for row in rows:
        if not row["example"]:
            continue
        res = cq.run(row["example"], recs, ctx)
        # Parse warnings only: "no set data" is about this fixture, not the example.
        assert not res.query.warnings, (row["example"], res.query.warnings)


def test_every_keyword_compiles_or_is_a_directive():
    for kw in cq.KEYWORDS:
        assert kw.compile is not None or kw.key in ("order", "direction"), kw.key
    for slug in ("commander", "gamechanger", "free", "pinned", "shared", "new", "basic"):
        assert slug in cq._IS or slug == "new"


# --------------------------------------------------------------------------- #
# The CLI the skill runs
# --------------------------------------------------------------------------- #
def test_analyze_collection_query_flag(tmp_path):
    coll = tmp_path / "collection.csv"
    coll.write_text(
        "Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity\n"
        "1,Old Gnawbone,7,G,G,{5}{G}{G},Creature,Dragon,mythic\n"
        "1,Thundermaw Hellkite,5,R,R,{3}{R}{R},Creature,Dragon,mythic\n"
        "1,Llanowar Elves,1,G,G,{G},Creature,Elf Druid,common\n", encoding="utf-8")
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "d.txt").write_text("# Title: D\n# Colors: R\n1 Thundermaw Hellkite\n",
                                 encoding="utf-8")
    script = os.path.join(ROOT, "scripts", "analyze_collection.py")
    out = subprocess.run([sys.executable, script, str(coll), "--query", "t:dragon free>0",
                          "--decks-dir", str(decks)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "Matches: 1 unique / 1 copies (1 free)" in out.stdout
    assert "Old Gnawbone" in out.stdout and "Thundermaw" not in out.stdout
    js = subprocess.run([sys.executable, script, str(coll), "--query", "t:dragon",
                         "--decks-dir", str(decks), "--json"], capture_output=True, text=True)
    data = json.loads(js.stdout)
    assert data["matched"] == 2 and data["means"] == ["type dragon"]
    hp = subprocess.run([sys.executable, script, str(coll), "--query-help"],
                        capture_output=True, text=True)
    assert "free>0" in hp.stdout and "deck:" in hp.stdout
