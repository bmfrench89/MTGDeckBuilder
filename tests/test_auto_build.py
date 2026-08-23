"""The auto-builder must always produce a legal deck: exactly 100 cards, nothing outside
the commander's color identity, and no card taken from a deck that already committed it.
Also covers the two bugs found in the tribal rebuild (tribal blindness, self-exclusion)."""
import mtglib
import auto_build
import deck_conflicts


def _build(collection_file, commander="Test Commander", **kw):
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    return auto_build.build(commander, coll, idx, decks_dir=None, **kw)


def test_builds_exactly_100_cards(big_collection_file):
    d = _build(big_collection_file, identity={"W", "U"})
    assert d["total"] == 100
    assert not d.get("short")


def test_small_pool_reports_the_shortfall_honestly(collection_file):
    """A pool too thin for a 99 must say so rather than silently ship a short deck."""
    d = _build(collection_file, identity={"W", "U"})
    assert d["total"] < 100
    assert d.get("short", 0) > 0


def test_never_includes_off_color_cards(big_collection_file):
    """Green cards must never appear in a WU deck."""
    d = _build(big_collection_file, identity={"W", "U"})
    names = {mtglib._norm(c["name"]) for _title, cards in d["sections"] for c in cards}
    assert not any(n.startswith("green thing") for n in names)
    assert d["off_color_skipped"] > 0          # and it counted them


def test_sections_and_counts_are_consistent(big_collection_file):
    d = _build(big_collection_file, identity={"W", "U"})
    listed = sum(c.get("qty", 1) for _t, cards in d["sections"] for c in cards)
    assert listed == d["total"]


def test_deck_text_round_trips(big_collection_file):
    """What we write must parse back to the same 100 cards."""
    d = _build(big_collection_file, identity={"W", "U"})
    parsed = mtglib.parse_deck(auto_build.deck_text(d))
    assert sum(c.quantity for c in parsed) == d["total"]


def test_no_duplicate_nonbasic_cards(big_collection_file):
    """Commander is singleton: no nonbasic may appear twice."""
    d = _build(big_collection_file, identity={"W", "U"})
    names = [c["name"] for _t, cards in d["sections"] for c in cards
             if c["name"] not in ("Island", "Plains", "Swamp", "Mountain", "Forest")]
    assert len(names) == len(set(names))


def test_deck_text_has_required_headers(big_collection_file):
    text = auto_build.deck_text(_build(big_collection_file, identity={"W", "U"}))
    assert "# Commander:" in text and "# Title:" in text


def test_scan_skip_excludes_that_deck(tmp_path):
    """Regression: a REBUILD must not count the deck against itself, or it can't reuse
    its own cards (this is what capped The Ur-Dragon at 7 dragons)."""
    (tmp_path / "a.txt").write_text("# Commander: A\n1 Sol Ring\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("# Commander: B\n1 Sol Ring\n", encoding="utf-8")
    idx = {}
    full = deck_conflicts.scan(str(tmp_path), idx)
    skipped = deck_conflicts.scan(str(tmp_path), idx, skip="a")
    assert full["Sol Ring"]["total"] == 2
    assert skipped["Sol Ring"]["total"] == 1        # deck "a" no longer counted


# --------------------------------------------------------------------------- #
# An UNKNOWN color identity is refused, never guessed
#
# Reproduced live 2026-08-20: Thorin, King of Durin's Folk was added to the
# collection the same day, so he was in the pool but not yet enriched. `identity`
# resolved to set(), `_color_legal` then admitted only colorless cards, and the
# build returned a plausible-looking 43-artifact pile with 0 basics in entirely the
# wrong colors — no error, no warning. `Card.identity` has no None-vs-empty
# distinction to catch it, so `types` is the enrichment tell.
# --------------------------------------------------------------------------- #
def _nameonly_collection(tmp_path, commander="Mystery Commander"):
    """A name-only pool: every card is present but nothing is enriched."""
    p = tmp_path / "nameonly.txt"
    lines = [f"1 {commander}"] + [f"1 Filler Card {i}" for i in range(120)]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def test_an_unenriched_commander_is_refused_not_built_colorless(tmp_path):
    import pytest
    coll = mtglib.load_collection(_nameonly_collection(tmp_path))
    idx = mtglib.index_by_name(coll)
    with pytest.raises(auto_build.UnknownIdentity) as exc:
        auto_build.build("Mystery Commander", coll, idx, decks_dir=None)
    msg = exc.value.message
    assert "UNKNOWN" in msg and "not colorless" in msg
    assert "--identity" in msg, "the refusal must name the way out"
    assert "carddb.py --verify" in msg, "and the verified source for it"


def test_a_commander_absent_from_the_collection_is_also_refused(tmp_path):
    import pytest
    coll = mtglib.load_collection(_nameonly_collection(tmp_path))
    idx = mtglib.index_by_name(coll)
    with pytest.raises(auto_build.UnknownIdentity) as exc:
        auto_build.build("Not In The Pool", coll, idx, decks_dir=None)
    assert "isn't in the collection" in exc.value.message


def test_an_explicit_identity_unblocks_the_same_build(big_collection_file, tmp_path):
    """The escape hatch has to actually work: a verified identity builds normally."""
    coll = mtglib.load_collection(big_collection_file)
    idx = mtglib.index_by_name(coll)
    d = auto_build.build("Test Commander", coll, idx, decks_dir=None, identity="WU")
    assert d["total"] == 100


def test_a_genuinely_colorless_commander_still_builds(tmp_path):
    """The guard keys on ENRICHMENT, not on emptiness — an enriched commander with a
    truly empty identity (Karn, Kozilek) must not be caught by it."""
    rows = ["Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,MARKET",
            "1,Colorless Boss,5,,,{5},Legendary Creature,Construct,rare,clr00000,1.00"]
    for i in range(60):
        rows.append(f"1,Grey Rock {i},2,,,{{2}},Artifact,,common,ar{i:06d},0.10")
    for i in range(30):
        rows.append(f"1,Waste Land {i},0,,,,Land,,common,wl{i:06d},0.10")
    p = tmp_path / "colorless.csv"
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    coll = mtglib.load_collection(str(p))
    idx = mtglib.index_by_name(coll)
    d = auto_build.build("Colorless Boss", coll, idx, decks_dir=None)   # must not raise
    assert d["identity"] in ("C", "")


def test_tribal_tags_must_be_singular_to_resolve(tmp_path):
    """A `tribal-X` tag is matched against card SUBTYPES, which Magic spells singular.

    `tribal-spiders` sat in commanders.csv matching zero cards (the subtype is
    "Spider"); the bug was masked because a commander's own subtypes are candidates
    too, so Spider commanders still found their tribe by accident. This locks the
    contract in both directions."""
    # The commander deliberately has NO subtypes: its own subtypes are candidates too,
    # so leaving one on would mask what the TAG contributes — which is the whole point.
    rows = ["Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,MARKET",
            "1,Tag Only Commander,4,W,W,{3}{W},Legendary Creature,,rare,tag00000,1.00"]
    for i in range(12):
        rows.append(f"1,Web Spinner {i},2,W,W,{{1}}{{W}},Creature,Spider,common,sp{i:06d},0.10")
    p = tmp_path / "spiders.csv"
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    coll = mtglib.load_collection(str(p))
    idx = mtglib.index_by_name(coll)

    tribe, n = auto_build._tribe_and_support(
        "Tag Only Commander", idx, ["tribal-spider"], coll, {"W"})
    assert (tribe, n) == (frozenset({"spider"}), 12), "the singular tag must find the tribe"

    tribe, n = auto_build._tribe_and_support(
        "Tag Only Commander", idx, ["tribal-spiders"], coll, {"W"})
    # An authored tag is now returned even when it matches nothing, with its real
    # count of 0, so `build()` raises the "you own only 0 in-color" warning instead
    # of the tag evaporating. The plural bug is LOUD now rather than a silent no-op;
    # the data guard below is still what keeps it out of the reference file.
    assert (tribe, n) == (frozenset({"spiders"}), 0), "a plural tag matches no subtype"


def test_multi_tribe_commander_unions_its_tags(tmp_path):
    """Kaalia of the Vast: three authored tribes must UNION, not compete.

    Her trigger reads "an Angel, Demon, or Dragon creature card". The old code took
    whichever single `tribal-` tag the collection best supported, so a pool of
    28 Dragons / 13 Angels / 9 Demons built a Dragon deck and dropped 22 cards the
    commander explicitly wants. (In the live repo the tag was worse still —
    `tribal-hero`, copied from Captain America — so the builder filled the 99 with
    Marvel Heroes and put ZERO Angels, Demons or Dragons in a Kaalia deck.)"""
    rows = ["Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,MARKET",
            "1,Multi Tribe Boss,4,W,W B R,{1}{R}{W}{B},Legendary Creature,,rare,mt000000,1.00"]
    for i in range(6):
        rows.append(f"1,Test Angel {i},4,W,W,{{3}}{{W}},Creature,Angel,rare,an{i:06d},0.50")
    for i in range(5):
        rows.append(f"1,Test Demon {i},5,B,B,{{4}}{{B}},Creature,Demon,rare,de{i:06d},0.50")
    for i in range(4):
        rows.append(f"1,Test Dragon {i},6,R,R,{{5}}{{R}},Creature,Dragon,rare,dr{i:06d},0.50")
    p = tmp_path / "add.csv"
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    coll = mtglib.load_collection(str(p))
    idx = mtglib.index_by_name(coll)

    tags = ["reanimator", "tribal-angel", "tribal-demon", "tribal-dragon"]
    tribe, n = auto_build._tribe_and_support(
        "Multi Tribe Boss", idx, tags, coll, {"W", "B", "R"})
    assert tribe == frozenset({"angel", "demon", "dragon"})
    # 6 + 5 + 4 — the UNION. Best-of-one would have answered 6 and built Angels only.
    assert n == 15, f"tags must union, got {n}"


def test_subtype_derived_tribes_still_compete(tmp_path):
    """The union rule applies to AUTHORED tags only; a commander's own type line
    stays a guess, so the collection still picks one. "Orc Dragon" builds Dragons,
    not Orcs-and-Dragons."""
    rows = ["Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,MARKET",
            "1,Orcish Wyrm,5,R,R,{4}{R},Legendary Creature,Orc;Dragon,rare,ow000000,1.00"]
    for i in range(9):
        rows.append(f"1,Grunt {i},2,R,R,{{1}}{{R}},Creature,Orc,common,or{i:06d},0.10")
    for i in range(13):
        rows.append(f"1,Wyrmling {i},5,R,R,{{4}}{{R}},Creature,Dragon,rare,wy{i:06d},0.50")
    p = tmp_path / "orcdragon.csv"
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    coll = mtglib.load_collection(str(p))
    idx = mtglib.index_by_name(coll)

    tribe, n = auto_build._tribe_and_support("Orcish Wyrm", idx, [], coll, {"R"})
    # 13 Dragons beat 9 Orcs; the commander itself is a Dragon so it counts too.
    assert tribe == frozenset({"dragon"}) and n == 14, (tribe, n)


def test_kaalia_row_names_her_three_real_tribes():
    """Guard the DATA: Kaalia's row must not carry a tribe she does not care about.

    It said `tribal-hero` — Captain America's tag — for long enough that
    `auto_build "Kaalia of the Vast"` returned a legal 100 containing zero Angels,
    Demons or Dragons. A wrong tribe is worse than the plural bug above: that one
    matched nothing, this one matched the wrong cards and looked like a real deck."""
    import csv
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "reference", "commanders.csv")
    with open(path, encoding="utf-8") as f:
        rows = {r["Name"]: r for r in csv.DictReader(l for l in f if not l.startswith("#"))}
    tags = set((rows["Kaalia of the Vast"]["Archetypes"] or "").split())
    assert {"tribal-angel", "tribal-demon", "tribal-dragon"} <= tags, tags
    assert "tribal-hero" not in tags, "Kaalia is not a Hero commander"


def test_every_curated_tribal_tag_is_a_real_subtype_shape():
    """Guard the reference file itself: no tribal tag may be plural.

    Reads the repo's own commanders.csv (not a fixture) because the defect lived in
    the DATA, not the code — a test against a fixture would have stayed green."""
    import csv
    import os
    import similar_commanders as simc
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "reference", "commanders.csv")
    plural = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(l for l in f if not l.startswith("#")):
            for tag in (row.get("Archetypes") or "").split():
                if tag.startswith("tribal-") and tag.endswith("s"):
                    plural.append((row["Name"], tag))
    assert not plural, (
        f"plural tribal tags match no subtype and silently do nothing: {plural}")
