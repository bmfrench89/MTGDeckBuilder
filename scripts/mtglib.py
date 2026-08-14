"""Shared library for the MTG Commander deckbuilder scripts.

Stdlib-only. Parses a player's collection (rich Archidekt CSV or a name-only
list) and deck lists into a common Card structure, and provides the category
heuristics and mana-cost math the other scripts share.

Grounding note: category classification (ramp/draw/removal/wipe) is a HEURISTIC.
It reads, in this order: curated name lists, then the oracle-derived flags
`carddb` writes via `oracle_flags` (consulted only where the curated lists are
silent), then card types. It is a starting point, not gospel. Always eyeball the
output and verify uncertain cards (see the skill's grounding-rules.md).
"""

from __future__ import annotations

import csv
import io
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import memo                    # the one repo import a hub makes, and it points
                               # DOWN: memo imports nothing from here (or anywhere)


# --------------------------------------------------------------------------- #
# Card model
# --------------------------------------------------------------------------- #
@dataclass
class Card:
    name: str
    quantity: int = 1
    mana_value: Optional[float] = None
    colors: set = field(default_factory=set)        # colors of the card itself
    identity: set = field(default_factory=set)      # color identity
    mana_cost: str = ""                             # e.g. "{1}{W}{U}"
    types: list = field(default_factory=list)        # e.g. ["Creature"]
    subtypes: list = field(default_factory=list)     # e.g. ["Cat", "Warlock"]
    supertypes: list = field(default_factory=list)   # e.g. ["Legendary"]
    rarity: str = ""
    scryfall_id: str = ""
    set_code: str = ""
    collector_number: str = ""
    price: Optional[float] = None   # representative (max) MARKET unit price
    value: float = 0.0              # total value across printings: sum(qty*market)
    date_added: str = ""            # newest acquisition date the export carries (ISO)
    # What the card can ACTUALLY add to a mana pool (Scryfall `produced_mana`), and
    # oracle-derived behaviour flags — both written by carddb via oracle_flags.
    # The None-vs-empty distinction is load-bearing and conflating them is a bug:
    #   None    = not enriched. Consumers fall back (to color identity) AND SAY SO.
    #   set()   = enriched, and this card really produces no mana (Maze of Ith).
    produced: Optional[set] = None
    flags: set = field(default_factory=set)   # see oracle_flags for the vocabulary
    # Printed power of the FRONT face, as a number — the input the goldfish clock
    # needs to know how hard a board hits. Three file states collapse into two here,
    # and consumers must handle both as UNKNOWN:
    #   int   = a real printed power (0 included).
    #   None  = unknown OR not a creature. The `Power` column absent (never
    #           enriched), an empty cell (noncreature — no power at all), and a
    #           non-numeric printed power ('*', '1+*', stored verbatim in the file)
    #           all land here. A creature whose power is None is a card the clock
    #           cannot count — it must be reported, not treated as 0.
    power: Optional[int] = None

    @property
    def is_land(self) -> bool:
        if self.types:
            return any(t.lower() == "land" for t in self.types)
        return _looks_like_land_by_name(self.name)

    @property
    def has_type_data(self) -> bool:
        return bool(self.types)

    @property
    def primary_type(self) -> str:
        order = ["Land", "Creature", "Planeswalker", "Artifact",
                 "Enchantment", "Instant", "Sorcery", "Battle"]
        low = [t.lower() for t in self.types]
        for t in order:
            if t.lower() in low:
                return t
        return self.types[0] if self.types else "Unknown"


# --------------------------------------------------------------------------- #
# Collection / deck parsing
# --------------------------------------------------------------------------- #
_COLOR_LETTERS = {"W", "U", "B", "R", "G"}


def _split_multi(value: str) -> list:
    """Archidekt packs multi-values with commas/semicolons/spaces. Normalize."""
    if not value:
        return []
    parts = re.split(r"[;,/]| - ", value)
    return [p.strip() for p in parts if p.strip()]


def _parse_colorish(value: str) -> set:
    """Parse a colors/identity field into a set of WUBRG letters."""
    if not value:
        return set()
    out = set()
    for tok in re.split(r"[;,\s/]+", value.strip()):
        tok = tok.strip().upper()
        if tok in _COLOR_LETTERS:
            out.add(tok)
        elif tok in {"WHITE", "BLUE", "BLACK", "RED", "GREEN"}:
            out.add(tok[0])
    return out


def _parse_produced(value: str) -> set:
    """Parse a `Produced` cell ('W U B', WUBRGC order) into a set of letters.

    Always returns a set, never None: an empty cell is the real answer "enriched and
    produces no mana". Only the caller knows whether the COLUMN existed at all, and
    that is what distinguishes unknown (`Card.produced is None`) from empty."""
    out = set()
    for tok in re.split(r"[;,\s]+", (value or "").strip()):
        tok = tok.strip().upper()
        if len(tok) == 1 and tok in "WUBRGC":
            out.add(tok)
    return out


def _parse_power(value) -> Optional[int]:
    """Parse a `Power` cell into an int, or None when it isn't a plain number.

    Scryfall prints power verbatim and plenty of it isn't a number — `*`, `1+*`,
    `∞`, `?`. Those are stored in the file EXACTLY as printed (nothing is lost) and
    read back as None here, because the honest answer to "how hard does it hit" for
    a `*` creature is "that depends", not a made-up integer. `'2.5'` (Un-set halves)
    truncates toward zero rather than being dropped — it is still a real number.
    An empty cell is None too: a noncreature has no power to read."""
    # NOT `value or ""`: a real power of 0 is falsy, and 0 is a genuine answer
    # (every 0-power creature — Ornithopter, Blood Artist). Only None means
    # "no cell".
    s = "" if value is None else str(value).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        # `int(float(s))` also has to survive 'inf'/'nan', which float() accepts
        # and int() then refuses with OverflowError/ValueError. This parser sits
        # on load_collection's hot path against hand-editable files, so a typo
        # must read as unknown, never take down the whole collection load.
        return int(float(s))          # '2.5' — a real number, just not an integer
    except (ValueError, OverflowError):
        return None


def _parse_flags(value: str) -> set:
    """Parse a `Flags` cell — `;`-joined tokens, the combos.csv convention, so a
    comma inside anything never splits a token. Blanks are dropped."""
    return {t.strip() for t in (value or "").split(";") if t.strip()}


def _strip_sep_preamble(text: str) -> str:
    """Excel-style exports prepend a `sep=,` line. Drop it if present."""
    lines = text.splitlines()
    if lines and lines[0].strip().strip('"').lower().startswith("sep="):
        return "\n".join(lines[1:])
    return text


def detect_format(text: str) -> str:
    """Return 'csv' or 'namelist'."""
    head = _strip_sep_preamble(text).lstrip()
    first_line = head.splitlines()[0] if head.splitlines() else ""
    low = first_line.lower()
    if ("," in first_line and "name" in low
            and ("quantity" in low or "mana" in low or "scryfall" in low
                 or "type" in low)):
        return "csv"
    # A single comma with a known header token still means CSV.
    if low.startswith("quantity,") or low.startswith("count,"):
        return "csv"
    return "namelist"


def _header_index(fieldnames, *aliases):
    low = {f.lower().strip(): f for f in fieldnames if f}
    for a in aliases:
        if a in low:
            return low[a]
    return None


def parse_collection(text: str) -> list:
    """Parse collection text into a list[Card]. Auto-detects CSV vs name list."""
    fmt = detect_format(text)
    if fmt == "csv":
        return _parse_csv(text)
    return _parse_namelist(text)


def _to_float(s):
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _price_header(fieldnames):
    """Price columns vary the most across apps. Exact aliases first; then any
    live-market column (Sorted exports 'Current Price (tcgplayer_…)'); then any
    other price column EXCEPT what-you-paid history, which is the least useful
    value and often 0.00 — it is the last resort, not the first match."""
    exact = _header_index(fieldnames, "market", "price", "mid", "low",
                          "purchase price", "my price")
    if exact:
        return exact
    low = [(f.lower().strip(), f) for f in fieldnames if f]
    for key, f in low:
        if "market" in key:
            return f
    for key, f in low:
        if "price" in key and "bought" not in key:
            return f
    for key, f in low:
        if "price" in key:
            return f
    return None


# Multi-TCG apps (e.g. Sorted) export every game in one file, tagged by a
# game column. Anything except Magic must not enter the pool.
_MTG_GAME_VALUES = {"", "mtg", "magic", "magic: the gathering"}


def _parse_csv(text: str) -> list:
    text = _strip_sep_preamble(text)
    reader = csv.DictReader(io.StringIO(text))
    fn = reader.fieldnames or []
    c_qty = _header_index(fn, "quantity", "count", "qty")
    c_name = _header_index(fn, "name", "card name", "card", "simple name")
    c_mv = _header_index(fn, "mana value", "cmc", "mana_value", "mv")
    c_colors = _header_index(fn, "colors", "color")
    c_ident = _header_index(fn, "identities", "identity", "color identity")
    c_cost = _header_index(fn, "mana cost", "mana_cost", "cost")
    c_types = _header_index(fn, "types", "type")
    c_sub = _header_index(fn, "sub-types", "subtypes", "sub types", "subtype")
    c_super = _header_index(fn, "super-types", "supertypes", "super types")
    c_rarity = _header_index(fn, "rarity")
    c_sid = _header_index(fn, "scryfall id", "scryfall_id", "scryfallid", "id")
    c_set = _header_index(fn, "set code", "edition code", "set", "edition")
    c_num = _header_index(fn, "card number", "collector number", "number")
    c_price = _price_header(fn)
    c_game = _header_index(fn, "collection", "game")
    c_date = _header_index(fn, "date bought", "date added", "date")

    # One physical printing per row. Aggregate by card name: sum quantity, sum
    # value (qty*market), keep the max unit price as representative, keep the
    # richest attribute data seen.
    agg = {}
    for row in reader:
        name = (row.get(c_name) or "").strip() if c_name else ""
        if not name:
            continue
        if c_game and (row.get(c_game) or "").strip().lower() not in _MTG_GAME_VALUES:
            continue
        try:
            qty = int(float((row.get(c_qty) or "1").strip())) if c_qty else 1
        except ValueError:
            qty = 1
        mv = _to_float(row.get(c_mv)) if c_mv else None
        price = _to_float(row.get(c_price)) if c_price else None
        key = _norm(name)
        if key not in agg:
            agg[key] = Card(
                name=name, quantity=0,
                mana_value=mv,
                colors=_parse_colorish(row.get(c_colors, "") if c_colors else ""),
                identity=_parse_colorish(row.get(c_ident, "") if c_ident else ""),
                mana_cost=(row.get(c_cost) or "").strip() if c_cost else "",
                types=_split_multi(row.get(c_types, "")) if c_types else [],
                subtypes=_split_multi(row.get(c_sub, "")) if c_sub else [],
                supertypes=_split_multi(row.get(c_super, "")) if c_super else [],
                rarity=(row.get(c_rarity) or "").strip() if c_rarity else "",
                scryfall_id=(row.get(c_sid) or "").strip() if c_sid else "",
                set_code=(row.get(c_set) or "").strip() if c_set else "",
                collector_number=(row.get(c_num) or "").strip() if c_num else "",
            )
        c = agg[key]
        c.quantity += qty
        if price is not None:
            c.value += qty * price
            if c.price is None or price > c.price:
                c.price = price
        if c.mana_value is None and mv is not None:
            c.mana_value = mv
        if c_date:
            # Newest date across printings — "when did I last add copies", which is
            # what the new-arrivals view asks. ISO dates compare lexically.
            d = (row.get(c_date) or "").strip()[:10]
            if d and d > c.date_added:
                c.date_added = d
    return list(agg.values())


_QTY_RE = re.compile(r"^\s*(\d+)\s*[xX]?\s+(.*\S)\s*$")

_HDR_RE_CACHE = {}


def deck_header(text, key, default=""):
    """THE `# Key: value` deck-header parser — every consumer calls this, none
    carries its own regex. Same rule as `_QTY_RE` and `deckcore.section_label`, and
    for the same reason: sixteen hand-rolled copies of this pattern existed across
    thirteen files, and every one shared the same latent bug.

    The bug: `:\\s*(.+)$` under re.MULTILINE. `\\s` matches a NEWLINE, so an EMPTY
    header absorbed the whole next line as its value — ur-dragon's blank
    `# Archetype: ` parsed as `['#', 'source:', 'auto-generated', …]` in live data,
    and an empty `# Bracket:` sitting above `1 Sol Ring` would have read a phantom
    "Bracket 1". Hence `[ \\t]*`, which stops at the line end, and `(.*?)` so an
    empty value stays on ITS line and falls through to `default` instead of the
    engine scanning onward for a luckier match.

    `key` is a small REGEX FRAGMENT, not a literal — callers pass "Colors?" to
    accept both spellings. All callers are in-repo; don't feed it user input.
    """
    pat = _HDR_RE_CACHE.get(key)
    if pat is None:
        # [ \t\r]* before $: text read in binary or over the wire keeps its \r
        # under MULTILINE ($ sits before \n, after \r) — a value must never carry
        # a carriage return the old lazy readers happened to strip.
        pat = re.compile(rf"^#[ \t]*(?:{key})[ \t]*:[ \t]*(.*?)[ \t\r]*$",
                         re.MULTILINE | re.IGNORECASE)
        _HDR_RE_CACHE[key] = pat
    m = pat.search(text or "")
    v = m.group(1) if m else ""
    return v if v else default


def _parse_namelist(text: str) -> list:
    cards = {}
    for raw in text.splitlines():
        line = raw.strip().replace("\\!", "!").replace("\\'", "'")
        if not line or line.startswith("#"):
            continue
        m = _QTY_RE.match(line)
        if m:
            qty, name = int(m.group(1)), m.group(2).strip()
        else:
            qty, name = 1, line
        # strip trailing set/collector info like "(FIN) 123"
        name = re.sub(r"\s*\((?:[A-Za-z0-9]{2,5})\)\s*\d*\s*$", "", name).strip()
        if not name:
            continue
        if name in cards:
            cards[name].quantity += qty
        else:
            cards[name] = Card(name=name, quantity=qty)
    return list(cards.values())


def parse_deck(text: str) -> list:
    """Parse a deck list (qty name per line). Returns list[Card] (name+qty)."""
    return _parse_namelist(text)


def merge_collection(cards: list, extra: list) -> list:
    """Merge player-confirmed extra ownership into a parsed collection (in place).
    Adds quantities for cards already present; appends new ones."""
    idx = {_norm(c.name): c for c in cards}
    for e in extra:
        k = _norm(e.name)
        if k in idx:
            idx[k].quantity += e.quantity
            if e.price is not None and idx[k].price is None:
                idx[k].price = e.price
        else:
            cards.append(e)
            idx[k] = e
    return cards


def overlay_attrs(cards: list, attrs_text: str) -> int:
    """Overlay card attributes (Type, MV, Colors) from a CSV onto a collection by
    name. Powers collection-wide color/type/curve analysis. Returns #matched."""
    reader = csv.DictReader(io.StringIO(attrs_text))
    fn = reader.fieldnames or []
    c_name = _header_index(fn, "name", "card", "card name")
    c_type = _header_index(fn, "type", "types")
    c_mv = _header_index(fn, "mv", "mana value", "cmc")
    c_colors = _header_index(fn, "colors", "color identity", "identity")
    c_cost = _header_index(fn, "cost", "mana cost")
    c_sub = _header_index(fn, "sub-types", "subtypes", "sub types", "subtype")
    c_sid = _header_index(fn, "scryfall", "scryfall id", "id")
    c_prod = _header_index(fn, "produced", "produced mana")
    c_flags = _header_index(fn, "flags")
    c_power = _header_index(fn, "power")
    idx = index_by_name(cards)
    n = 0
    for row in reader:
        name = (row.get(c_name) or "").strip() if c_name else ""
        card = lookup(idx, name) if name else None
        if not card:
            continue
        n += 1
        if c_type and (row.get(c_type) or "").strip():
            card.types = _split_multi(row[c_type])
        mv = _to_float(row.get(c_mv)) if c_mv else None
        if mv is not None:
            card.mana_value = mv
        if c_colors and (row.get(c_colors) or "").strip():
            card.identity = _parse_colorish(row[c_colors])
            card.colors = card.colors or card.identity
        if c_cost and (row.get(c_cost) or "").strip():
            card.mana_cost = row[c_cost].strip()
        if c_sub and (row.get(c_sub) or "").strip():
            card.subtypes = _split_multi(row[c_sub])
        if c_sid and (row.get(c_sid) or "").strip():
            card.scryfall_id = row[c_sid].strip()
        # Produced/Flags are keyed off the COLUMN's presence, not the cell's content:
        # an empty cell under a present column means "produces nothing", while an
        # attrs file written before enrichment learned these columns leaves
        # produced=None so every consumer falls back and labels the fallback.
        if c_prod:
            card.produced = _parse_produced(row.get(c_prod))
        if c_flags:
            card.flags = _parse_flags(row.get(c_flags))
        # Power is keyed off the CELL, not the column: unlike produced there is no
        # "known to be nothing" integer, so an empty cell and an absent column both
        # read back as None. Writing None over an already-known power would be the
        # real bug here — the snapshot-then-private overlay order (ATTRS_OVERLAYS)
        # layers an OLD private file over a newer snapshot, and blanking on an
        # absent column would erase exactly the data the snapshot just supplied.
        if c_power:
            p = _parse_power(row.get(c_power))
            if p is not None:
                card.power = p
    return n


# Attribute overlays, applied in THIS order — later files win per-column.
#   collection_attrs.snapshot.csv — committed, name-derived, written ONLY by the
#     attrs-snapshot Action. It is what gives a fresh clone (and every sandbox
#     session) typed data; before it existed those started name-only.
#   collection_attrs.csv — private, gitignored, written by carddb against the
#     player's real export (exact printings). Authoritative where it speaks.
# Order matters and is load-bearing: `overlay_attrs` writes a field only when the
# incoming cell is non-empty, and keys Produced/Flags off the COLUMN's presence, so
# layering snapshot-then-private keeps the private file authoritative while letting
# an OLD private file (one written before enrichment learned Produced/Flags — the
# shape on the player's machine today) keep the snapshot's production data instead
# of silently erasing it. Choosing one file instead of layering was the first draft
# of this and it lost exactly that data. See docs/spec-network-and-attrs.md §3.
ATTRS_OVERLAYS = ("collection_attrs.snapshot.csv", "collection_attrs.csv")


# Every file `load_collection` may read, relative to the collection's own
# directory. This list IS the cache key — a file that the loader reads but this
# tuple omits would let an edit to it serve stale forever, so the two must be
# changed together (`tests/test_memo.py` pins the overlays against exactly this).
COLLECTION_INPUTS = ("owned_additions.txt", "owned_additions.csv") + ATTRS_OVERLAYS


def collection_inputs(path: str) -> list:
    """Absolute-ish paths of every file `load_collection(path)` reads, present or
    not. Missing ones matter: they key as `(path, None)` so their later creation
    invalidates the cached load rather than being ignored until the next edit."""
    d = os.path.dirname(path) or "."
    return [path] + [os.path.join(d, x) for x in COLLECTION_INPUTS]


def load_collection(path: str) -> list:
    """Parse a collection file, then auto-merge sibling overlays if present:
      - `owned_additions.txt/.csv` — cards you confirmed you own but the export
        missed (player info outranks the export, grounding rule #6).
      - the `ATTRS_OVERLAYS` files — card attributes (Type/MV/Colors/Produced/
        Flags/Power) for the whole collection, built by carddb.py. This turns on
        color/type/curve analysis across every deck.

    An attrs row whose name is not in the collection is skipped, never invented —
    a stale snapshot listing sold cards adds nothing (see `overlay_attrs`).

    Memoized on the mtimes of ALL of those inputs, not just `path`: the overlays
    are what a sync or an enrichment run rewrites, and keying on the base file
    alone would serve a pre-enrichment collection for the rest of the process's
    life. **The returned list is shared** — every caller gets the same `Card`
    objects, so nothing may mutate them (the audit that established nothing does
    is in `docs/spec-infra-hot-paths.md` §1b; `apply_attrs` is safe because
    `deck_stats.analyze` hands it fresh merged copies, never these)."""
    return memo.get(("mtglib.load_collection", memo.stat_key(*collection_inputs(path))),
                    lambda: _load_collection(path))


def _load_collection(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        cards = parse_collection(f.read())
    d = os.path.dirname(path) or "."
    for extra in ("owned_additions.txt", "owned_additions.csv"):
        ep = os.path.join(d, extra)
        if os.path.exists(ep):
            with open(ep, encoding="utf-8") as f:
                merge_collection(cards, parse_collection(f.read()))
    for attrs in ATTRS_OVERLAYS:
        ap = os.path.join(d, attrs)
        if os.path.exists(ap):
            with open(ap, encoding="utf-8") as f:
                overlay_attrs(cards, f.read())
    return cards


def front_face(name: str) -> str:
    """The front face of a split/DFC name, e.g. 'Fire // Ice' -> 'Fire'.

    Splits only on ' // ' WITH surrounding spaces, which is the separator Scryfall and
    every deck-list format actually use. A bare '//' can be part of a real card name —
    'SP//dr, Piloted by Peni' — and naive `split("//")` turned that into the front face
    'SP'. That bogus alias then made every name-keyed lookup resolve 'sp' to the card,
    so the optimizer never saw it as already-in-deck and added a fresh copy on each run
    (it reached 6 copies of a singleton before this was caught)."""
    return name.split(" // ")[0].strip() if " // " in name else name


def index_by_name(cards: list) -> dict:
    """Case-insensitive name -> Card. Handles 'Front // Back' by also indexing
    the front face."""
    idx = {}
    for c in cards:
        idx[_norm(c.name)] = c
        front = front_face(c.name)
        if front != c.name:
            idx.setdefault(_norm(front), c)
    return idx


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def lookup(idx: dict, name: str):
    return idx.get(_norm(name)) or idx.get(_norm(front_face(name)))


# --------------------------------------------------------------------------- #
# Mana cost / pip math
# --------------------------------------------------------------------------- #
_SYMBOL_RE = re.compile(r"\{([^}]+)\}")


def pip_counts(mana_cost: str) -> dict:
    """Return {W,U,B,R,G: count} of colored pips in a mana cost string.

    Every multi-letter symbol splits one pip across its letters: {W/U} is 0.5/0.5,
    and hybrid-Phyrexian {G/W/P} is likewise 0.5/0.5 — ONE symbol is one pip at most.
    (The old special case gave {G/W/P} a full pip per letter, 2.0 from a single
    symbol, inflating pip demand and the Karsten source math for any deck running
    hybrid-Phyrexian cards.) Mono Phyrexian {W/P} stays a full W pip: paying life is
    the fallback, not the plan."""
    out = {c: 0.0 for c in "WUBRG"}
    for sym in _SYMBOL_RE.findall(mana_cost or ""):
        s = sym.upper()
        letters = [ch for ch in s if ch in _COLOR_LETTERS]
        for ch in letters:
            out[ch] += 1.0 / len(letters)
    return out


def is_double_pip(mana_cost: str) -> Optional[str]:
    """If a cost has 2+ pips of a single color, return that color, else None."""
    counts = {c: 0 for c in "WUBRG"}
    for sym in _SYMBOL_RE.findall(mana_cost or ""):
        s = sym.upper()
        if s in _COLOR_LETTERS:
            counts[s] += 1
    for c, n in counts.items():
        if n >= 2:
            return c
    return None


# --------------------------------------------------------------------------- #
# Land name heuristic (fallback when no type data)
# --------------------------------------------------------------------------- #
_BASICS = {"plains", "island", "swamp", "mountain", "forest", "wastes"}
_LAND_HINTS = (
    "command tower", "path of ancestry", "exotic orchard", "arcane sanctum",
    "plaza of heroes", "spire of industry", "estuary", "catacombs", "fortress",
    "chapel", "river", "town", "hollow", "stream", "expanse", "heath", "ruins",
    "mire", "snarl", "aquifer", "marsh", "beachfront", "passage", "farmland",
    "market", "barrens", "bog", "temple of", "shrine", "prairie", "retreat",
    "grove", "crag", "trail", "village", "vista", "glade", "peaks", "wilds",
    "landscape", "refuge", "guildgate", "tower", "field", "cave", "sanctuary",
    "svyelunite temple", "temple of the false god", "slagheap", "volcano",
    "bloodhall", "springs", "needle", "karst", "woodlot", "bog", "ruins",
    "storage", "citadel of", "academy", "coast", "summit", "monastery",
    "courtyard", "territory", "plaza", "shrine", "peaks", "outpost",
    "bivouac", "orchard", "sanctum", "panorama", "bloodfell",
)


def name_keys(name: str) -> frozenset:
    """Every normalized key this card answers to: the full name AND the split/DFC
    front face. Membership tests (is it already in the deck?) must check both sides —
    EDHREC deliberately emits both keys, and deck lines often carry only the front
    face, so comparing raw `_norm` alone lets the same card in twice (the " // "
    trap, caught live three separate times now)."""
    return frozenset({_norm(name), _norm(front_face(name))})


def is_basic(name: str) -> bool:
    """True for any card exempt from the singleton rule: the six basics and their
    Snow-Covered printings. Name-based on purpose — the exemption must hold even when
    the collection is name-only (fresh clone on the snapshot, no supertype data)."""
    low = name.strip().lower()
    if low.startswith("snow-covered "):
        low = low[len("snow-covered "):]
    return low in _BASICS


def _looks_like_land_by_name(name: str) -> bool:
    low = name.lower()
    if is_basic(name):        # includes Snow-Covered printings — a plain _BASICS
        return True           # check missed them, so snow basics read as spells
    return any(h in low for h in _LAND_HINTS)


# --------------------------------------------------------------------------- #
# Category heuristics (ramp / draw / removal / wipe)
# --------------------------------------------------------------------------- #
RAMP = {
    "sol ring", "arcane signet", "commander's sphere", "fellwar stone",
    "mind stone", "thought vessel", "worn powerstone", "hedron archive",
    "mana prism", "moss diamond", "sky diamond", "coldsteel heart",
    "azorius signet", "rakdos signet", "talisman of dominance",
    "talisman of hierarchy", "talisman of progress", "talisman of conviction",
    "talisman of creativity", "talisman of indulgence", "relic of legends",
    "cultivate", "farseek", "rampant growth", "nature's lore", "kodama's reach",
    "sakura-tribe elder", "llanowar elves", "elvish mystic", "gilded goose",
    "wood elves",
    "priest of titania", "solemn simulacrum", "burnished hart", "wayfarer's bauble",
    "pilgrim's eye", "skyscanner", "archaeomancer's map", "springbloom druid",
    "wild growth", "grow from the ashes", "explorer's scope", "coveted jewel",
}
DRAW = {
    "rhystic study", "mystic remora", "night's whisper", "sign in blood",
    "read the bones", "tome of legends", "staff of the storyteller", "skullclamp",
    "mask of memory", "staggering insight", "dig through time", "sphinx's revelation",
    "syphon mind", "syphon soul", "ambition's cost", "opportunity", "prosperity",
    "brainstorm", "frantic search", "think twice", "winged words", "insight",
    "kindred discovery", "coastal piracy", "reconnaissance mission", "horn of greed",
    "visions of beyond", "harmonize", "sublime epiphany",
    # 2026-08-11 sleeper audit — texts verified against Scryfall/Gatherer pages:
    "riddles in the dark", "sensational spider-man", "valeria richards, precocious",
    "dragonhawk, fate's tempest", "niv-mizzet, visionary",
    "stock up", "bident of thassa", "avengers assemble!",
    # repeatable engines that draw off a deck's own payoffs rather than saying "draw a
    # card" on a cheap spell — these were being scored as generic enchantments, which
    # under-counted card advantage in decks built around big creatures.
    "up the beanstalk", "temur ascendancy", "esper sentinel", "smothering tithe",
    "guardian project", "beast whisperer", "garruk's uprising", "elemental bond",
    "colossal majesty", "the great henge", "toski, bearer of secrets",
}
REMOVAL = {
    "swords to plowshares", "path to exile", "generous gift", "beast within",
    "chaos warp", "assassin's trophy", "vindicate", "infernal grasp",
    "murderous rider", "soul shatter", "lethal scheme", "snuff out", "vendetta",
    "terminate", "unlicensed disintegration", "nameless inversion", "condemn",
    "pacifism", "banishing light", "dispatch", "rip apart", "abrade", "shatter",
    "disenchant", "seal of cleansing", "seal of doom", "seal of fire",
    "crush contraband", "feed the swarm", "mortality spear", "void rend",
    "swift end", "dark banishing", "befoul", "smite", "rending volley",
    # 2026-08-11 sleeper audit — texts verified:
    "web up", "mjölnir, hammer of thor",
}
WIPES = {
    "blasphemous act", "toxic deluge", "cleansing nova", "austere command",
    "vanquish the horde", "time wipe", "extinction event", "final judgment",
    "cave-in", "pyroclasm", "wave of reckoning", "deadly tempest",
    "tragic arrogance", "culling ritual", "crux of fate", "planar collapse",
    "reign of the pit", "casualties of war",
    # 2026-08-11 sleeper audit — text verified (drain + destroy all creatures):
    "villainous wrath",
}
COUNTERS = {
    "counterspell", "force of will", "misdirection", "arcane denial", "negate",
    "essence scatter", "memory lapse", "miscalculation", "power sink", "daze",
    "spell snare", "spell blast", "absorb", "sublime epiphany", "remove soul",
    "thwart", "annul", "misstep",
}

# Layer 2: what an oracle-derived flag means in role terms. The curated lists above
# are hand-maintained and every new set outgrows them; `Card.flags` (written by
# carddb via oracle_flags, see that module for the vocabulary) covers the tail.
# Tokens that describe HOW a card makes mana rather than what job it does
# (`etb-tapped`, `etb-tapped-cond`, `mana2`, `mana3`) map to no role on purpose —
# they are inputs to the goldfish mana model, not deck-role categories.
FLAG_ROLES = {
    "rock": "ramp",
    "dork": "ramp",
    "ramp": "ramp",
    "draw": "draw",
    "removal": "removal",
    "wipe": "wipe",
    "counter": "counter",
}


def classify(card: Card) -> set:
    """Return the set of roles this card fills (heuristic).

    Three layers, in strict precedence order:

    1. **Curated name lists** (RAMP/DRAW/REMOVAL/WIPES/COUNTERS) — hand-verified,
       and they always win.
    2. **Oracle-derived flags** (`Card.flags`, from `oracle_flags`) — consulted
       ONLY when the curated lists said nothing about this card. The `if not
       roles` guard IS the curated-wins rule; it is first-writer-wins, the same
       shape `deckcore.load_card_notes` uses to let a curated note beat a
       generated one. A card the player curated as `ramp` stays `ramp` even if a
       regex read `draw` in its text.
    3. **Card types** — the last-resort fallback ("creature", "spell", …), then
       "other".

    Still a heuristic at every layer: a regex is not a rules engine and a name
    list is only as fresh as its last edit. Eyeball the output and verify
    uncertain cards (see the skill's grounding-rules.md)."""
    roles = set()
    # BOTH keys, full name and front face: a collection stores 'Murderous Rider //
    # Swift End' while the curated lists name the faces — a raw-_norm lookup matched
    # neither, so every split/DFC card silently classified by type alone.
    keys = name_keys(card.name)
    if card.is_land:
        roles.add("land")
        return roles
    if keys & RAMP:
        roles.add("ramp")
    if keys & DRAW:
        roles.add("draw")
    if keys & REMOVAL:
        roles.add("removal")
    if keys & WIPES:
        roles.add("wipe")
    if keys & COUNTERS:
        roles.add("counter")
    # Layer 2 — only where curation is silent. An unenriched card has flags ==
    # set(), so this whole layer no-ops on a collection that has never been
    # through carddb, and category counts are byte-identical to pre-A-F.
    if not roles and card.flags:
        for f in card.flags:
            role = FLAG_ROLES.get(f)
            if role:
                roles.add(role)
    # light type-based fallback
    if not roles and card.types:
        pt = card.primary_type.lower()
        if pt == "creature":
            roles.add("creature")
        elif pt in ("instant", "sorcery"):
            roles.add("spell")
        else:
            roles.add(pt)
    if not roles:
        roles.add("other")
    return roles
