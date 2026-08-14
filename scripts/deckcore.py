#!/usr/bin/env python3
"""deckcore — the shared analysis hub (see docs/codemap.md).

Stdlib + `mtglib` only, so every analysis/presentation module can depend on it
WITHOUT importing the heavy `build_dashboard` renderer (which previously owned these
helpers and created circular imports). This module holds:

  * companion-file loaders — deck sections, `.notes.md`, `.buylist.csv`, `.attrs.csv`
    (`load_deck_sections`, `load_notes`, `load_buylist`, `load_attrs`, `apply_attrs`),
  * the curated card-notes knowledge base (`load_card_notes`),
  * shared labels/utilities (`_ROLE_LABEL`, `_to_float_price`).

Later steps add `analyze_deck()` here as the single deck-analysis entry point.
"""
import csv
import os
import re

import memo
import mtglib


def _to_float_price(s):
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def section_label(line):
    """The label out of a `# --- Ramp (12) ---` header line, or None.

    THE one parser for deck section headers. The add-into-section flow depends on the
    labels the API serves matching the labels the insert looks for, so both sides (and
    load_deck_sections below) must call this — a second copy of the regex would let the
    two drift and silently turn every add into 'append to end of file'."""
    s = line.strip()
    if not s.startswith("#"):
        return None
    m = re.search(r"---\s*(.*?)\s*---", s)
    return re.sub(r"\s*\(\d+\)\s*$", "", m.group(1)).strip() if m else None


def real_section_labels(path):
    """Only the labels that exist as actual headers in the file — unlike
    load_deck_sections, which invents a synthetic 'Cards' group for cards that precede
    any header. A picker offering 'Cards' would send the insert hunting for a header
    that isn't there."""
    labels = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            lab = section_label(ln)
            if lab and lab not in labels:
                labels.append(lab)
    return labels


def load_deck_sections(path):
    """Group the deck by the `# --- Label ---` headers in the deck file itself,
    so each build sections its own way ("Spiders", "Ramp", ...)."""
    sections, cur = [], None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            s = raw.strip()
            if not s:
                continue
            if s.startswith("#"):
                label = section_label(s)
                if label is not None:
                    cur = (label, [])
                    sections.append(cur)
                continue
            m = mtglib._QTY_RE.match(s)      # the one qty-line parser (mtglib)
            qty, name = (int(m.group(1)), m.group(2).strip()) if m else (1, s)
            if cur is None:
                cur = ("Cards", [])
                sections.append(cur)
            cur[1].append((qty, name))
    return sections


def load_notes(path):
    return open(path, encoding="utf-8").read() if path and os.path.exists(path) else None


def load_buylist(path):
    if not (path and os.path.exists(path)):
        return None
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "card": (r.get("Card") or "").strip(),
                "price": _to_float_price(r.get("Price")),
                "tier": (r.get("Tier") or "").strip(),
                "replaces": (r.get("Replaces") or "").strip(),
                "reason": (r.get("Reason") or "").strip(),
            })
    return [r for r in rows if r["card"]]


NEW_CARD_DAYS = 14


def load_changes(path, days=NEW_CARD_DAYS):
    """`<deck>.changes.csv` -> {normalized card: {added, replaced, days_ago}} for cards the
    optimizer added within `days`. Lets the dashboard badge what's actually new rather than
    leaving you to diff a 100-card list by eye after every collection refresh."""
    if not (path and os.path.exists(path)):
        return {}
    from datetime import date
    today = date.today()
    out = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = (r.get("Card") or "").strip()
            if not name:
                continue
            try:
                added = date.fromisoformat((r.get("Added") or "").strip())
            except ValueError:
                continue
            ago = (today - added).days
            if ago > days or ago < 0:
                continue
            k = mtglib._norm(name)
            prev = out.get(k)
            if prev is None or ago < prev["days_ago"]:   # keep the most recent entry
                out[k] = {"name": name, "added": added.isoformat(), "days_ago": ago,
                          "replaced": (r.get("Replaced") or "").strip(),
                          "source": (r.get("Source") or "").strip()}
    return out


MANUAL_SOURCES = ("manual-add", "manual-replace", "manual-remove")


def _is_manual(source):
    """Any player-decided source. PREFIX match, not tuple membership: live data
    carries legacy `Source=manual` rows (cloud's Codsworth swap, cosmic's
    Anti-Venom swap) that an exact tuple silently skipped — the Hojo mechanism
    waiting on field drift, for rows whose only defect is a spelling."""
    return (source or "").strip().startswith("manual")


def manual_adds(path, days=NEW_CARD_DAYS):
    """Just the cards the PLAYER put in by hand (Source=manual-*), newest first.

    The optimizer writes its own swaps to the same log, so `Source` is what separates
    "the tool did this" from "the player decided this" — the distinction the advisor
    exists to respect."""
    rows = [dict(v, key=k) for k, v in load_changes(path, days).items()
            if _is_manual(v.get("source"))]
    return sorted(rows, key=lambda r: r["days_ago"])


def manual_removals(path):
    """Cards the PLAYER took OUT by hand — {norm: {"name", "date"}} — no time window.

    The symmetric rule to "never cut a manual add", added when its absence bit in
    live data (2026-08-13): the player pulled Professor Hojo from cloud on
    2026-08-11 (Source=manual-replace, recorded), and the very next rescore
    proposed re-adding him over a different victim. Notes-file churn guards name
    the VICTIM, so the pass just moves to a new one — "a tourniquet, not the fix"
    (spec-optimizer-hardening.md's own words). The decision the player actually
    made was about HOJO, and this reads that decision straight from the log.

    Deliberately unwindowed — a removal is a decision, not a cooldown — and lifted
    the moment a manual row RE-ADDS the card on the same or a later date: the
    newest player action wins, which is the same rule the whole advisor lives by.
    """
    if not (path and os.path.exists(path)):
        return {}
    removed, readded = {}, {}
    with open(path, encoding="utf-8") as f:
        for i, r in enumerate(csv.DictReader(f)):
            if not _is_manual(r.get("Source")):
                continue
            # The file is APPEND-ONLY, so (date, row index) is the actual
            # chronology — date alone ties on same-day sequences, and a same-day
            # add-then-remove (a card the player tried for one afternoon) must
            # resolve to the REMOVAL, its newest action.
            seq = ((r.get("Added") or "").strip(), i)
            out_name = (r.get("Replaced") or "").strip()
            in_name = (r.get("Card") or "").strip()
            if out_name:
                for k in mtglib.name_keys(out_name):
                    if seq >= removed.get(k, {}).get("seq", ("", -1)):
                        removed[k] = {"name": out_name, "date": seq[0], "seq": seq}
            if in_name:
                for k in mtglib.name_keys(in_name):
                    if seq >= readded.get(k, ("", -1)):
                        readded[k] = seq
    return {k: {"name": v["name"], "date": v["date"]}
            for k, v in removed.items()
            if readded.get(k, ("", -1)) < v["seq"]}


PINS = os.path.join(os.path.dirname(__file__), "..", "data", "collection", "pins.csv")


def load_pins(path=None):
    """{normalized card: deck stem} — cards you've reserved for a specific deck.

    When you own ONE copy of a card that three decks want, the arithmetic can't decide
    which deck gets the physical card. A pin is you deciding: that copy belongs to this
    deck, and the other decks must treat it as unavailable no matter how well it scores.
    """
    # Resolved at CALL time, not bound as a default: `path=PINS` captured the module
    # constant at import, so redirecting PINS (a test pointing at tmp_path, or any
    # future per-instance path) silently kept writing the real file.
    path = path or PINS
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            card = (r.get("Card") or "").strip()
            deck = (r.get("Deck") or "").strip()
            if card and deck:
                out[mtglib._norm(card)] = deck
    return out


def save_pins(pins, path=None):
    """Write the pin map back. One deck per card — pinning elsewhere moves it."""
    path = path or PINS                    # call-time, same reason as load_pins
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Card", "Deck"])
        for card, deck in sorted(pins.items()):
            w.writerow([card, deck])


def pinned_elsewhere(stem, pins=None):
    """Normalized cards reserved for a deck OTHER than `stem` — off-limits to it."""
    pins = load_pins() if pins is None else pins
    return {c for c, d in pins.items() if d != stem}


# --------------------------------------------------------------------------- #
# THE role template (Phase 12 of spec-table-ready.md). One table, one widener —
# every consumer imports these. Five independent copies used to exist
# (optimize.ROLE_RANGE, deck_fit.FIT_TARGETS, deck_stats.TARGETS,
# auto_build.ROLE_QUOTA's comment, a webapp hardcode) and they DISAGREED: measured
# on the six real decks, 17 of 30 role judgments differed between the fit scorer
# and the optimizer's filter, so the card panel pushed counterspells into a
# voltron deck while the optimizer correctly refused them. Copies of a judgment
# are not independent judges — they're drift. (`optimize.ROLE_RANGE` etc. remain
# as shims so existing imports and tests keep working.)
# --------------------------------------------------------------------------- #

# (min, max) acceptable count per 99 (deckbuilding-principles.md). The DEFAULT —
# what a deck with no (or an unknown) `# Archetype:` header gets.
ROLE_RANGE = {"ramp": (9, 13), "draw": (8, 12), "removal": (8, 11),
              "wipe": (2, 5), "counter": (0, 6)}
LAND_RANGE = (36, 38)
LAND_TARGET = 37

# Per-archetype widenings, keyed by the words that actually appear in the decks'
# `# Archetype:` headers. Merged by WIDENING only (min(lo), max(hi)) — stacking two
# archetype words can never make a deck's template stricter than the default, and an
# unrecognised word contributes nothing (and is REPORTED, never silently ignored).
#
# Why this exists (2026-08-12, spec-optimizer-hardening.md "Typed-data role-repair
# churn"): the template was archetype-blind, so iron-man — a draw-go control deck
# whose real counts are counter:15, ramp:8, wipe:0 — read as nine excess
# counterspells plus a ramp hole plus a wrath hole. By its ratified identity it is
# exactly correct.
#
# TRAP: "counters" (captain-america) means +1/+1 COUNTERS, not counterspells. It is
# deliberately absent from this table — mapping it to the `counter` role would widen
# a tribal deck's counterspell allowance for a word about creature buffs.
# The other header words in use — equipment, tribal-hero, tribal-spiders, lifegain —
# need no delta: those decks already sit inside the default ranges.
_ARCHETYPE_ROLE_RANGE = {
    # Draw-go control: interaction IS the counterspell suite, so counters run long,
    # sweepers and spot removal run short, and the deck leans on card draw over rocks.
    "control": {"counter": (0, 18), "ramp": (6, 13), "draw": (8, 18),
                "removal": (4, 11), "wipe": (0, 5)},
    "draw-engine": {"draw": (8, 22)},      # a deck named for its draw engine
    "artifacts": {"ramp": (9, 16)},        # mana rocks are artifacts; ramp runs high
    "go-wide": {"wipe": (0, 5)},           # a wrath kills YOUR board first
    "tokens": {"wipe": (0, 5)},
    "aristocrats": {"wipe": (0, 5)},       # sacrifice outlets, not sweepers
    "voltron": {"removal": (6, 11), "wipe": (0, 5)},   # protection over mass removal
}


def archetype_words(text):
    """Deck-file text (or a bare header value) -> the archetype word list.

    THE tokenizer for `# Archetype:` — the words `role_ranges` keys on. Three
    hand-rolled copies of this split appeared within one session of each other,
    which is exactly how the header-regex drift started; one function, everywhere."""
    v = text if ("\n" not in (text or "") and ":" not in (text or "")) else \
        mtglib.deck_header(text, "Archetype")
    return [w for w in re.split(r"[,\s/]+", (v or "").lower().strip()) if w]


def role_ranges(archetype=None):
    """The role template for a deck, widened by its `# Archetype:` words.

    `archetype` is the already-parsed word list `deck_fit.deck_context` puts in
    ctx["archetype"] — the header is read by `mtglib.deck_header` in exactly one
    place; this function does not add a second parser. None / [] / unrecognised
    words -> the default ROLE_RANGE, byte-identical to the archetype-blind days."""
    ranges, _unknown = role_ranges_with_unknown(archetype)
    return ranges


def role_ranges_with_unknown(archetype=None):
    """`role_ranges`, plus the archetype words that matched NO table entry.

    The template is a LOOSENING — a wider band removes a barrier that was blocking
    swaps — so a word the table does not recognise silently buys nothing. Reporting
    the unmatched words is the honesty label for that: the run tells the player
    which part of their `# Archetype:` line it did not understand, instead of
    leaving them to assume it was applied."""
    ranges, unknown = dict(ROLE_RANGE), []
    for word in (archetype or []):
        key = str(word).lower()
        deltas = _ARCHETYPE_ROLE_RANGE.get(key)
        if not deltas:
            unknown.append(str(word))
            continue
        for role, (lo, hi) in deltas.items():
            cur_lo, cur_hi = ranges.get(role, (lo, hi))
            ranges[role] = (min(cur_lo, lo), max(cur_hi, hi))   # widen, never narrow
    return ranges, unknown


def load_attrs(path):
    """Optional name -> {type, mv, colors, produced, flags, power} map, so a deck can
    carry its own card data without the full collection CSV.

    `Name,Type,MV,Colors[,Produced,Flags,Power]` — the three optional columns are the
    same contract `collection_attrs.csv` uses (spec-engine-upgrades §4.2;
    spec-table-ready Phase 1 for Power), and the **empty-vs-absent rule is
    load-bearing** here too. `csv.DictReader` hands back `None` for a column that
    isn't in the header and `''` for a present-but-blank cell, and this map preserves
    exactly that: `None` stays None so `apply_attrs` leaves `Card.produced` alone
    (unknown → every consumer falls back and says so), while `''` parses to an empty
    set (enriched, produces nothing — Maze of Ith). `Power` is carried the same way,
    verbatim (`*` included) — `mtglib._parse_power` is what turns it into an int or
    an honest None.
    Unlike `mtglib.overlay_attrs` these keys are EXACT-CASE, matching the header
    `carddb.py` writes. Headers here are not aliased."""
    if not (path and os.path.exists(path)):
        return None
    out = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = (r.get("Name") or r.get("Card") or "").strip()
            if not name:
                continue
            mv = _to_float_price(r.get("MV"))
            out[mtglib._norm(name)] = {
                "type": (r.get("Type") or "").strip(),
                "mv": mv,
                "colors": (r.get("Colors") or "").strip(),
                "produced": r.get("Produced"),      # None = column absent, keep it
                "flags": r.get("Flags"),
                "power": r.get("Power"),            # verbatim; '*' stays '*'
            }
    return out


def _default_notes_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "data", "reference", "card_notes.csv")


def _read_notes_csv(path, out, generated):
    if not path or not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = (r.get("Name") or r.get("Card") or "").strip()
            if not name:
                continue
            k = mtglib._norm(name)
            if k in out:
                continue                      # first writer wins (curated is read first)
            alts = [a.strip() for a in re.split(r"[;|]", r.get("Alternatives") or "")
                    if a.strip()]
            out[k] = {"why": (r.get("Why") or "").strip(), "alts": alts,
                      "generated": generated}


def load_card_notes(path=None, include_generated=True):
    """name(normalized) -> {"why": str, "alts": [names], "generated": bool}.

    Two layers: the hand-written `card_notes.csv` and, if present, the machine-drafted
    `card_notes.generated.csv` (see scripts/gen_card_notes.py). **Curated always wins** —
    the generated file only fills cards nobody has written up yet, so growing coverage
    never overwrites a human blurb."""
    path = path or _default_notes_path()
    out = {}
    _read_notes_csv(path, out, generated=False)
    if include_generated:
        gen = os.path.join(os.path.dirname(path), "card_notes.generated.csv")
        _read_notes_csv(gen, out, generated=True)
    return out


def apply_attrs(enriched, attrs):
    """Overlay type/MV/colors — and, when the companion carries them, the
    production-aware `Produced`/`Flags` and the printed `Power` — onto enriched deck
    cards.

    A deck-level `.attrs.csv` is what makes the enriched mana model (and the goldfish
    clock) reachable on a fresh clone that only has the name-only snapshot. Absent
    columns are left untouched (`produced` stays None), never overwritten with an
    empty set. Power goes further and only writes a value it could actually parse: a
    blank or `*` cell leaves whatever the collection already knew, because for power
    there is no "known to be nothing" number to overwrite it with."""
    if not attrs:
        return 0
    n = 0
    for c in enriched:
        a = attrs.get(mtglib._norm(c.name))
        if not a:
            continue
        n += 1
        if a["type"]:
            c.types = [a["type"]]
        if a["mv"] is not None:
            c.mana_value = a["mv"]
        if a["colors"]:
            c.identity = mtglib._parse_colorish(a["colors"])
        if a.get("produced") is not None:
            c.produced = mtglib._parse_produced(a["produced"])
        if a.get("flags") is not None:
            c.flags = mtglib._parse_flags(a["flags"])
        if a.get("power") is not None:
            p = mtglib._parse_power(a["power"])
            if p is not None:
                c.power = p
    return n


_ROLE_LABEL = {
    "ramp": "Ramp / mana acceleration", "draw": "Card advantage",
    "removal": "Targeted removal", "wipe": "Board wipe", "counter": "Counterspell",
    "land": "Land", "creature": "Creature", "spell": "Instant / sorcery",
    "artifact": "Artifact", "enchantment": "Enchantment",
    "planeswalker": "Planeswalker", "other": "Deck card",
}


# --------------------------------------------------------------------------- #
# Power-list tags — reference-list membership shown in card details ("Game
# Changer", "Tutor", …). Loaded once; names matched via mtglib._norm.
# --------------------------------------------------------------------------- #
REF_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "reference")
_POWER_TAG_FILES = (("game_changers.txt", "Game Changer"),
                    ("fast_mana.txt", "Fast mana"),
                    ("tutors.txt", "Tutor"),
                    ("extra_turns.txt", "Extra turns"),
                    ("mass_land_denial.txt", "Mass land denial"))
_power_tags = None


def load_power_tags(refdir=None):
    """norm(name) -> [tag, …] for every card on the curated power lists. The tags
    ride along wherever card roles are shown (dashboard details, card panel), so a
    Game Changer or tutor is labeled as such everywhere without re-deriving it."""
    global _power_tags
    if _power_tags is not None and refdir is None:
        return _power_tags
    tags = {}
    for fname, label in _POWER_TAG_FILES:
        path = os.path.join(refdir or REF_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                for ln in f:
                    name = ln.strip()
                    if not name or name.startswith("#"):
                        continue
                    tags.setdefault(mtglib._norm(name), []).append(label)
        except OSError:
            continue                      # a missing list degrades to no tag
    if refdir is None:
        _power_tags = tags
    return tags


# --------------------------------------------------------------------------- #
# Type buckets — the EDHREC-style section convention deck files follow. One
# bucketer, shared by deck_sections.py (migration/regroup) and auto_build
# (future decks), so the two can never drift.
# --------------------------------------------------------------------------- #
TYPE_SECTION_ORDER = ("Creatures", "Instants", "Sorceries", "Artifacts",
                      "Enchantments", "Planeswalkers", "Battles", "Lands", "Basics")
BASIC_LAND_NAMES = {"plains", "island", "swamp", "mountain", "forest", "wastes",
                    "snow-covered plains", "snow-covered island", "snow-covered swamp",
                    "snow-covered mountain", "snow-covered forest",
                    "snow-covered wastes"}


def type_bucket(name, types):
    """EDHREC-style section for a card, or None when the type is unknown.
    Multi-type precedence mirrors EDHREC: a creature is a creature no matter what
    else it is; any nonbasic land files under Lands."""
    if mtglib._norm(name) in BASIC_LAND_NAMES:
        return "Basics"
    tl = {t.strip().lower() for t in (types or []) if t and t.strip()}
    joined = " ".join(tl)
    if not tl:
        return None
    if "creature" in joined:
        return "Creatures"
    if "land" in joined:
        return "Lands"
    if "planeswalker" in joined:
        return "Planeswalkers"
    if "battle" in joined:
        return "Battles"
    if "instant" in joined:
        return "Instants"
    if "sorcery" in joined:
        return "Sorceries"
    if "artifact" in joined:
        return "Artifacts"
    if "enchantment" in joined:
        return "Enchantments"
    return None


# --------------------------------------------------------------------------- #
# Deck analysis — the single pipeline entry point. Engines are imported LOCALLY
# (inside the functions) so this hub keeps only `mtglib` as a top-level import
# and stays free of circular dependencies.
# --------------------------------------------------------------------------- #
def analyze_cards(enriched, idx, refs=None, deck_cards=None, missing=None):
    """Run report + power/bracket + manabase on an already-enriched card list
    (e.g. an auto-built 99). Returns {report, assessment, mana}; assessment/mana
    are None if the underlying engine can't run (e.g. name-only)."""
    import deck_stats
    import power
    import manabase
    rep = deck_stats.build_report(deck_cards if deck_cards is not None else enriched,
                                  enriched, missing or [], idx)
    refs = refs or power.load_refs()
    try:
        assessment = power.assess(enriched, rep, refs)
    except Exception:
        assessment = None
    try:
        mana = manabase.analyze(rep, enriched)
    except Exception:
        mana = None
    return {"report": rep, "assessment": assessment, "mana": mana}


def _reference_key():
    """A fingerprint of the whole reference directory — ~20 `stat` calls.

    `analyze_deck`'s answer depends on curated knowledge it never takes as an
    argument: `game_changers.txt` moves a bracket, `combos.csv` moves the Combo
    Watch, `card_notes.csv` moves the details. Keying only on the deck and the
    collection would cache an answer straight through a reference edit, which is
    exactly the kind of silent staleness this repo does not tolerate."""
    try:
        paths = sorted(e.path for e in os.scandir(REF_DIR)
                       if e.is_file() and e.name.endswith((".txt", ".csv")))
    except OSError:
        return ()
    return memo.stat_key(*paths)


def analyze_deck(deck_path, collection, refs=None):
    """Load + enrich a saved deck and run the whole analysis pipeline once — the
    single source of truth for the dashboard, the assessment packet, etc.
    `collection` may be a file path or an already-loaded list[Card]. Returns
    {coll, idx, deck, enriched, missing, attrs, report, assessment, mana, combos}.

    **Memoized** on the deck file, its `.attrs.csv`/`.notes.md` companions, the
    collection's own input set, and the reference directory — but only when the
    inputs can be fingerprinted. An already-loaded `collection` list and a
    caller-supplied `refs` both bypass the cache entirely: neither can be
    fingerprinted, and a caller who preloaded has already paid the price the
    cache exists to avoid.

    **What comes back on a hit is shared.** The outer dict is copied per call, so
    adding a top-level key is safe; everything inside it — `coll`, `idx`,
    `enriched`, `report`, `assessment` — is the same object every other caller
    holds and must be treated as read-only. `tests/test_memo.py`'s
    byte-identical-render tripwire is what keeps that true."""
    if isinstance(collection, str) and refs is None:
        stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
        key = ("deckcore.analyze_deck",
               memo.stat_key(deck_path, f"{stem}.attrs.csv", f"{stem}.notes.md",
                             *mtglib.collection_inputs(collection)),
               _reference_key())
        # Shallow copy per hit: callers that stash an extra top-level key (the
        # dashboard's `sim`, a route's own bookkeeping) then cannot leak it into
        # the next caller's analysis. The VALUES stay shared — see the docstring.
        return dict(memo.get(key, lambda: _analyze_deck(deck_path, collection, refs)))
    return _analyze_deck(deck_path, collection, refs)


def _analyze_deck(deck_path, collection, refs=None):
    import deck_stats
    import combo_detector
    import power
    coll = collection if isinstance(collection, list) else mtglib.load_collection(collection)
    idx = mtglib.index_by_name(coll)
    with open(deck_path, encoding="utf-8") as f:
        deck = mtglib.parse_deck(f.read())
    enriched, missing = deck_stats.analyze(deck, idx)
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    attrs = load_attrs(f"{stem}.attrs.csv")
    apply_attrs(enriched, attrs)
    core = analyze_cards(enriched, idx, refs, deck_cards=deck, missing=missing)
    try:
        combos = combo_detector.for_deck(deck_path, idx)
    except Exception:
        combos = None
    # The player's `# Bracket:` header lives in the deck FILE, which analyze_cards
    # never sees — stamp it here so every consumer of this pipeline (dashboard,
    # assess packet, table card) shows the setting beside the detected verdict.
    power.with_declared(core["assessment"], power.read_declared_bracket(deck_path))
    return {"coll": coll, "idx": idx, "deck": deck, "enriched": enriched,
            "missing": missing, "attrs": attrs, "report": core["report"],
            "assessment": core["assessment"], "mana": core["mana"], "combos": combos}


def advise_card(deck_path, collection, name, section=None, commander="", analysis=None,
                refs=None, ctx=None):
    """A read-only opinion on how ONE card fits a deck — the same components the
    dashboard already shows for cards in the list, computed for any card by name.

    This is ADVICE, never an action. Nothing here edits a deck, and the optimizer
    still never cuts a card the player added by hand; the player asked to know how
    a manual pick lands, not to have it second-guessed.

    Returns None when the card can't be resolved in the collection (never a guess —
    an unknown name gets no opinion rather than an invented one). Otherwise:
    {name, score, band, reasons[], context, role, in_deck, has_field, field_pct,
     alternatives[]}. `has_field` False means EDHREC data wasn't reachable/cached, so
    the verdict is fit-only — callers must say so rather than implying field backing.

    `analysis`, `refs` and `ctx` let a caller scoring many cards (the optimizer's
    manual-adds review) pay the deck-analysis / reference-file / EDHREC-cache cost
    once instead of once per card. When omitted, each is computed here.
    """
    import deck_fit
    import power
    a = analysis or analyze_deck(deck_path, collection)
    idx, enriched, rep = a["idx"], a["enriched"], a["report"]
    card = mtglib.lookup(idx, name)
    if card is None:
        return None
    if not commander:
        v = mtglib.deck_header(open(deck_path, encoding="utf-8").read(), "Commander")
        commander = re.split(r"\s{2,}|\(", v)[0].strip() if v else ""
    refs = refs or power.load_refs()
    if ctx is None:
        field = deck_fit.load_field(commander, idx) if commander else {}
        ctx = deck_fit.deck_context(deck_path, enriched, commander, field=field,
                                    synergy=deck_fit.load_synergy(commander, idx) if commander else None)
    else:
        field = ctx.get("field") or {}
    fit = deck_fit.assess_card(card, rep, ctx, refs, section)
    in_deck = set()
    for c in enriched:                 # BOTH keys — a raw-_norm set let a front-face
        in_deck |= mtglib.name_keys(c.name)   # staple re-recommend an in-deck split card
    try:
        alts = deck_fit.better_alternatives(card, ctx, idx, refs, [], in_deck,
                                            load_role_staples_safe())
    except Exception:
        alts = []
    return {"name": card.name, "score": fit["score"], "band": fit["band"],
            "reasons": fit["reasons"], "context": fit["context"], "role": fit["role"],
            "in_deck": bool(mtglib.name_keys(card.name) & in_deck),
            "has_field": bool(field),
            "field_pct": field.get(mtglib._norm(card.name)) if field else None,
            "alternatives": alts[:3]}


def load_role_staples_safe():
    import deck_fit
    try:
        return deck_fit.load_role_staples()
    except Exception:
        return {}


def buy_signals(buylist, combos, missing, idx=None):
    """ONE merged 'cards to buy' list from every engine that knows about a gap.

    The Buy view exists to answer 'what should I spend money on for this deck' —
    but that knowledge used to be scattered: the curated `.buylist.csv` rendered,
    while the combo engine's 'one piece away (not owned)' and the decklist's own
    unowned BUY-badged cards each stayed inside their own section. A player could
    read 'add Exquisite Blood to drain the table' in Combo Watch and then find a
    Buy tab that had never heard of the card. Hub rule: signals about a card
    flow together, with provenance, before any spoke renders them.

    Row shape matches `load_buylist` (card/price/tier/replaces/reason) plus
    `source`: 'curated' (always wins dedupe — the player wrote it), 'combo'
    (an unowned piece completing a combo), 'decklist' (in the list, unowned).
    Dedupe is front-face aware, like every membership test in this repo.
    """
    rows, seen = [], set()

    def _add(row):
        keys = mtglib.name_keys(row["card"])
        if keys & seen:
            return
        seen.update(keys)
        rows.append(row)

    for r in (buylist or []):
        _add(dict(r, source="curated"))

    for cb in (combos or {}).get("near", []):
        piece = cb.get("missing")
        if not piece or cb.get("missing_owned"):
            continue                      # owned pieces are a sleeving job, not a buy
        ref = mtglib.lookup(idx, piece) if idx else None
        _add({"card": piece,
              "price": ref.price if ref else None,
              "tier": "Combo",
              "replaces": "",
              "reason": f"Completes a combo: {cb.get('name', piece)} → {cb.get('result', '')}".strip(" →"),
              "source": "combo"})

    for c in (missing or []):
        name = getattr(c, "name", c)
        _add({"card": name, "price": None, "tier": "",
              "replaces": "",
              "reason": "Already in the decklist but not owned (the BUY badge).",
              "source": "decklist"})
    return rows


def new_arrivals(coll, decks_dir, days=30, now=None, limit=12):
    """Cards acquired in the last `days` (per the export's Date Bought column) that
    are in NO deck — the "I just scanned these, where do they go?" signal. Newest
    first. `fits` lists deck stems whose color identity can legally run the card,
    and is empty when the collection carries no color data (name-only snapshot) —
    the list degrades, it never guesses. Basics are noise here and are skipped."""
    import datetime
    import glob
    now = (now or datetime.date.today().isoformat())[:10]
    cutoff = (datetime.date.fromisoformat(now)
              - datetime.timedelta(days=days)).isoformat()
    in_decks, deck_ids = set(), {}
    for p in glob.glob(os.path.join(decks_dir, "*.txt")):
        text = open(p, encoding="utf-8").read()
        for c in mtglib.parse_deck(text):
            in_decks |= mtglib.name_keys(c.name)
        m = re.match(r"(.+)", mtglib.deck_header(text, "Colors?"))
        ids = set((m.group(1) if m else "").replace(",", " ").upper().split())
        deck_ids[os.path.splitext(os.path.basename(p))[0]] = ids
    out = []
    for c in coll:
        d = (c.date_added or "")[:10]
        if not d or d < cutoff or mtglib.is_basic(c.name):
            continue
        if mtglib.name_keys(c.name) & in_decks:
            continue
        fits = sorted(s for s, ids in deck_ids.items()
                      if c.identity and ids and c.identity <= ids)
        out.append({"name": c.name, "qty": c.quantity, "date": d, "fits": fits})
    out.sort(key=lambda r: (r["date"], r["name"]), reverse=True)
    return out[:limit]
