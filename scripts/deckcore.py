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


MANUAL_SOURCES = ("manual-add", "manual-replace")


def manual_adds(path, days=NEW_CARD_DAYS):
    """Just the cards the PLAYER put in by hand (Source=manual-*), newest first.

    The optimizer writes its own swaps to the same log, so `Source` is what separates
    "the tool did this" from "the player decided this" — the distinction the advisor
    exists to respect."""
    rows = [dict(v, key=k) for k, v in load_changes(path, days).items()
            if v.get("source") in MANUAL_SOURCES]
    return sorted(rows, key=lambda r: r["days_ago"])


PINS = os.path.join(os.path.dirname(__file__), "..", "data", "collection", "pins.csv")


def load_pins(path=PINS):
    """{normalized card: deck stem} — cards you've reserved for a specific deck.

    When you own ONE copy of a card that three decks want, the arithmetic can't decide
    which deck gets the physical card. A pin is you deciding: that copy belongs to this
    deck, and the other decks must treat it as unavailable no matter how well it scores.
    """
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


def save_pins(pins, path=PINS):
    """Write the pin map back. One deck per card — pinning elsewhere moves it."""
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


def load_attrs(path):
    """Optional name -> {type, mv, colors, produced, flags} map, so a deck can carry
    its own card data without the full collection CSV.

    `Name,Type,MV,Colors[,Produced,Flags]` — the two optional columns are the same
    contract `collection_attrs.csv` uses (spec-engine-upgrades §4.2), and the
    **empty-vs-absent rule is load-bearing** here too. `csv.DictReader` hands back
    `None` for a column that isn't in the header and `''` for a present-but-blank
    cell, and this map preserves exactly that: `None` stays None so `apply_attrs`
    leaves `Card.produced` alone (unknown → every consumer falls back and says so),
    while `''` parses to an empty set (enriched, produces nothing — Maze of Ith).
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
    production-aware `Produced`/`Flags` — onto enriched deck cards.

    A deck-level `.attrs.csv` is what makes the enriched mana model reachable on a
    fresh clone that only has the name-only snapshot. Absent columns are left
    untouched (`produced` stays None), never overwritten with an empty set."""
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
                    "snow-covered mountain", "snow-covered forest"}


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


def analyze_deck(deck_path, collection, refs=None):
    """Load + enrich a saved deck and run the whole analysis pipeline once — the
    single source of truth for the dashboard, the assessment packet, etc.
    `collection` may be a file path or an already-loaded list[Card]. Returns
    {coll, idx, deck, enriched, missing, attrs, report, assessment, mana, combos}."""
    import deck_stats
    import combo_detector
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
        m = re.search(r"^#\s*Commander:\s*(.+)$", open(deck_path, encoding="utf-8").read(),
                      re.M | re.I)
        commander = re.split(r"\s{2,}|\(", m.group(1))[0].strip() if m else ""
    refs = refs or power.load_refs()
    if ctx is None:
        field = deck_fit.load_field(commander, idx) if commander else {}
        ctx = deck_fit.deck_context(deck_path, enriched, commander, field=field,
                                    synergy=deck_fit.load_synergy(commander, idx) if commander else None)
    else:
        field = ctx.get("field") or {}
    fit = deck_fit.assess_card(card, rep, ctx, refs, section)
    in_deck = {mtglib._norm(c.name) for c in enriched}
    try:
        alts = deck_fit.better_alternatives(card, ctx, idx, refs, [], in_deck,
                                            load_role_staples_safe())
    except Exception:
        alts = []
    return {"name": card.name, "score": fit["score"], "band": fit["band"],
            "reasons": fit["reasons"], "context": fit["context"], "role": fit["role"],
            "in_deck": mtglib._norm(card.name) in in_deck,
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
        m = re.search(r"^#\s*Colors:\s*(.+)$", text, re.M)
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
