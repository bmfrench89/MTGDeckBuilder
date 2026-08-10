"""Derive what a card actually PRODUCES, and a small vocabulary of behaviour flags,
from a Scryfall card object.

Dependency-free by design — `re` is the only import, and nothing here touches a file
or the network. It is pure ``dict in → set out`` so `carddb` can call it during
enrichment and persist the results as the `Produced` / `Flags` columns of
`collection_attrs.csv`. No raw oracle text is stored at rest: the flags ARE the
storage, and re-deriving after a vocabulary change costs one enrichment re-run.

Everything is FACE-AWARE. Faces are read through `card_faces` and joined with the
`" // "` separator (`gen_card_notes.py:88-90`) — never a naive ``split("//")``,
which is the `SP//dr, Piloted by Peni` bug class `mtglib.front_face` exists to kill.
A flag fires if any face matches; `etb-tapped` only looks at a Land face's own text.

Grounding note: these flags are a HEURISTIC read of oracle text — a regex is not a
rules engine. Curated lists (`data/reference/card_notes.csv`), the player's own
word, and human verification always win. Consumers must honour the None-vs-empty
contract on `mtglib.Card.produced`: `None` means "not enriched — fall back and say
so", `set()` means "enriched, and it really produces no mana" (Maze of Ith).

v1 flag vocabulary (docs/spec-engine-upgrades.md §4.2):

===================  ========================================================
`etb-tapped`         a Land face that enters tapped, unconditionally
`etb-tapped-cond`    …the same, but qualified by `unless` / `you may pay` /
                     `if` — shocklands, checklands, battle lands. Three-valued
                     on purpose: each consumer picks its own policy.
`rock`               a non-Land Artifact that taps for mana
`dork`               a non-Land Creature that taps for mana
`ramp`               `rock`/`dork`, or the search-a-land-onto-the-battlefield
                     text class (Cultivate, Farseek)
`draw`               draws its own controller cards
`mana2` / `mana3`    one activation adds more than one mana (Sol Ring →
                     `mana2`). Absence of both means one.
`removal`            an Instant/Sorcery/Enchantment face that destroys or exiles
                     a TARGET (Swords to Plowshares, Banishing Light)
`wipe`               an Instant/Sorcery face that destroys/exiles ALL, or hits
                     every creature with a `-X/-X` or damage rider (Damnation,
                     Toxic Deluge, Blasphemous Act)
`counter`            counters a target spell (Counterspell). Not type-gated: a
                     creature or enchantment that counters still counters.
===================  ========================================================

Known limits, stated rather than hidden: variable production ("add {B} for each
Swamp you control") counts as one; hybrid/phyrexian symbols in an Add clause count
as one mana each; ramp sorceries that make treasure are not `ramp`. And the
`removal` regex reads the VERB, not the victim — "destroy target land you control"
is flagged `removal` exactly as "destroy target creature" is. That is the accepted
heuristic (the module docstring's disclaimer is the contract), not an oversight:
narrowing it would mean parsing targeting restrictions, which is a rules engine.
`wipe` covers the two forms the vocabulary names and no others — the active-voice
sweeper ("Blasphemous Act deals 13 damage to each creature") is missed here and
caught by the curated `mtglib.WIPES` list instead, which is exactly the layering
`classify()` relies on: curated first, flags only where curation is silent.
"""

import re

COLORS = "WUBRGC"

# "enters tapped" (post-Foundations) and "enters the battlefield tapped" (older
# printings) are the same event. Centralized here so a future rewording is one edit.
_ETB_TAPPED_RE = re.compile(r"enters (?:the battlefield )?tapped")
# A qualifier in the SAME sentence makes the tapped-ness conditional.
_QUALIFIERS = ("unless", "you may pay", "if ")

# "{T}: Add …" — the mana-producing activated ability. `[^:]*` keeps the match inside
# one ability's cost, so "{T}: Draw a card" followed by another ability can't spoof it.
_TAP_ADD_RE = re.compile(r"\{t\}[^:]*:\s*add ")

# The Cultivate / Farseek text class: fetch a land straight onto the battlefield.
_SEARCH_LAND_RE = re.compile(r"search your library for [^.]*\bland")

# gen_card_notes.py:54's proven draw pattern, widened to the third-person "draws"
# so the opponent/each-player guard below is actually load-bearing.
_DRAW_RE = re.compile(r"draws? (?:a card|\w+ cards)")
_NOT_YOUR_DRAW = ("opponent ", "each player ", "target player ")

# One mana symbol inside an Add clause: coloured/colourless, or a hybrid half-pip.
_MANA_SYM_RE = re.compile(r"\{(?:[wubrgc]|[wubrgc]/[wubrgc])\}")
_GENERIC_SYM_RE = re.compile(r"\{(\d+)\}")
# Everything an "Add" clause covers, up to the end of its sentence/clause.
_ADD_CLAUSE_RE = re.compile(r"\badd\b([^.;\n]*)")

# --- interaction: removal / wipe / counter (spec §4.5) ----------------------------
# Spot removal reads the verb + "target". Deliberately blind to what is being
# targeted — see the "destroy target land you control" note in the module docstring.
_REMOVAL_RE = re.compile(r"\b(?:destroy|exile) target\b")
# A sweeper says "all", or reaches every creature at once with a shrink/damage rider.
_WIPE_ALL_RE = re.compile(r"\b(?:destroy|exile) all\b")
_WIPE_EACH_RE = re.compile(r"\b(?:all|each) creatures?\b[^.]{0,60}?"
                           r"(?:gets? -|is dealt|are dealt)")
# `.{0,40}` spans the qualifier a counterspell puts between the words —
# "counter target creature spell", "counter target noncreature spell".
_COUNTER_RE = re.compile(r"counter target .{0,40}spell")


def faces(c):
    """[(type_line, oracle_text)] — one entry per face, or one for a single-faced card.

    Card-level `type_line` back-fills a face that omits it: Scryfall puts type_line
    and cmc on the card for some layouts and only on the faces for others (the same
    asymmetry `carddb._attrs_from_scryfall` already compensates for)."""
    fs = c.get("card_faces") or []
    if not fs:
        return [(c.get("type_line") or "", c.get("oracle_text") or "")]
    return [(f.get("type_line") or c.get("type_line") or "",
             f.get("oracle_text") or "") for f in fs]


def oracle_text_of(c):
    """Full oracle text, faces joined with `" // "` (the separator mtglib understands).

    Card-level text wins when present; otherwise the faces are joined. Deliberately
    NOT a `split("//")` anywhere — see the module docstring."""
    txt = c.get("oracle_text") or ""
    if txt:
        return txt
    fs = c.get("card_faces") or []
    return " // ".join(f.get("oracle_text", "") or "" for f in fs) if fs else ""


def produced_of(c):
    """set of WUBRGC letters this card can add to a mana pool.

    Card-level `produced_mana` is the authority; face-level values are unioned in as
    belt-and-suspenders (Scryfall reports the card-level union for every layout we
    have seen, but an MDFC whose back face is a land is exactly the shape where a
    missing card-level key would silently cost a colour). An empty set is a real
    answer — "enriched, produces nothing" — not "unknown"."""
    out = set()
    for src in [c] + list(c.get("card_faces") or []):
        for m in (src.get("produced_mana") or []):
            m = str(m).strip().upper()
            # `"" in COLORS` is True — the length check is what actually filters.
            if len(m) == 1 and m in COLORS:
                out.add(m)
    return out


def _mana_added(text):
    """Largest number of mana a single activation adds, per this text. 1 when unknown.

    Alternatives are split on " or " and the best branch wins, so a Guildgate's
    "Add {W} or {U}" is one mana (two choices), while Sol Ring's "Add {C}{C}" is two."""
    best = 1
    for clause in _ADD_CLAUSE_RE.findall(text):
        for alt in clause.split(" or "):
            n = len(_MANA_SYM_RE.findall(alt))
            n += sum(int(g) for g in _GENERIC_SYM_RE.findall(alt))
            best = max(best, n)
    return best


def derive_flags(c):
    """set[str] of v1 vocabulary tokens for a Scryfall card object (see module doc)."""
    flags = set()
    amount = 1
    for type_line, text in faces(c):
        tl = (type_line or "").lower()
        t = (text or "").lower()
        if not t:
            continue
        is_land = "land" in tl

        # etb-tapped / -cond: a LAND face's own text, sentence-scoped qualifier check.
        if is_land:
            for sentence in t.split("."):
                if not _ETB_TAPPED_RE.search(sentence):
                    continue
                if any(q in sentence for q in _QUALIFIERS):
                    flags.add("etb-tapped-cond")
                else:
                    flags.add("etb-tapped")

        taps_for_mana = bool(_TAP_ADD_RE.search(t))
        if taps_for_mana and not is_land:
            if "artifact" in tl:
                flags.add("rock")
            if "creature" in tl:
                flags.add("dork")
        if _SEARCH_LAND_RE.search(t) and "onto the battlefield" in t:
            flags.add("ramp")

        for m in _DRAW_RE.finditer(t):
            before = t[:m.start()]
            if not any(before.endswith(p) for p in _NOT_YOUR_DRAW):
                flags.add("draw")
                break

        # Interaction. The type gates keep an ETB creature ("when this enters,
        # destroy target creature") out of the removal count — that card is a
        # creature first, and classify()'s type fallback already says so.
        is_spell = "instant" in tl or "sorcery" in tl
        if (is_spell or "enchantment" in tl) and _REMOVAL_RE.search(t):
            flags.add("removal")
        if is_spell and (_WIPE_ALL_RE.search(t) or _WIPE_EACH_RE.search(t)):
            flags.add("wipe")
        if _COUNTER_RE.search(t):
            flags.add("counter")

        if not is_land or taps_for_mana:
            amount = max(amount, _mana_added(t))

    if flags & {"rock", "dork"}:
        flags.add("ramp")
    if amount >= 3:
        flags.add("mana3")
    elif amount == 2:
        flags.add("mana2")
    return flags
