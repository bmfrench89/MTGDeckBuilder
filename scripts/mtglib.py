"""Shared library for the MTG Commander deckbuilder scripts.

Stdlib-only. Parses a player's collection (rich Archidekt CSV or a name-only
list) and deck lists into a common Card structure, and provides the category
heuristics and mana-cost math the other scripts share.

Grounding note: category classification (ramp/draw/removal/wipe) is a HEURISTIC
based on curated name lists plus card types. It is a starting point, not gospel.
Always eyeball the output and verify uncertain cards (see the skill's
grounding-rules.md).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Optional


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


def _parse_csv(text: str) -> list:
    text = _strip_sep_preamble(text)
    reader = csv.DictReader(io.StringIO(text))
    fn = reader.fieldnames or []
    c_qty = _header_index(fn, "quantity", "count", "qty")
    c_name = _header_index(fn, "name", "card name", "card")
    c_mv = _header_index(fn, "mana value", "cmc", "mana_value", "mv")
    c_colors = _header_index(fn, "colors", "color")
    c_ident = _header_index(fn, "identities", "identity", "color identity")
    c_cost = _header_index(fn, "mana cost", "mana_cost", "cost")
    c_types = _header_index(fn, "types", "type")
    c_sub = _header_index(fn, "sub-types", "subtypes", "sub types", "subtype")
    c_super = _header_index(fn, "super-types", "supertypes", "super types")
    c_rarity = _header_index(fn, "rarity")
    c_sid = _header_index(fn, "scryfall id", "scryfall_id", "scryfallid", "id")
    c_set = _header_index(fn, "set code", "set", "edition")
    c_num = _header_index(fn, "card number", "collector number", "number")
    c_price = _header_index(fn, "market", "price", "mid", "low", "purchase price")

    # One physical printing per row. Aggregate by card name: sum quantity, sum
    # value (qty*market), keep the max unit price as representative, keep the
    # richest attribute data seen.
    agg = {}
    for row in reader:
        name = (row.get(c_name) or "").strip() if c_name else ""
        if not name:
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
    return list(agg.values())


_QTY_RE = re.compile(r"^\s*(\d+)\s*[xX]?\s+(.*\S)\s*$")


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
    return n


def load_collection(path: str) -> list:
    """Parse a collection file, then auto-merge sibling overlays if present:
      - `owned_additions.txt/.csv` — cards you confirmed you own but the export
        missed (player info outranks the export, grounding rule #6).
      - `collection_attrs.csv` — card attributes (Type/MV/Colors) for the whole
        collection, e.g. built by carddb.py from a Scryfall card database. This is
        what turns on color/type/curve analysis across every deck."""
    import os
    with open(path, encoding="utf-8") as f:
        cards = parse_collection(f.read())
    d = os.path.dirname(path) or "."
    for extra in ("owned_additions.txt", "owned_additions.csv"):
        ep = os.path.join(d, extra)
        if os.path.exists(ep):
            with open(ep, encoding="utf-8") as f:
                merge_collection(cards, parse_collection(f.read()))
    ap = os.path.join(d, "collection_attrs.csv")
    if os.path.exists(ap):
        with open(ap, encoding="utf-8") as f:
            overlay_attrs(cards, f.read())
    return cards


def index_by_name(cards: list) -> dict:
    """Case-insensitive name -> Card. Handles 'Front // Back' by also indexing
    the front face."""
    idx = {}
    for c in cards:
        idx[_norm(c.name)] = c
        if "//" in c.name:
            front = c.name.split("//")[0].strip()
            idx.setdefault(_norm(front), c)
    return idx


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def lookup(idx: dict, name: str):
    return idx.get(_norm(name)) or idx.get(_norm(name.split("//")[0]))


# --------------------------------------------------------------------------- #
# Mana cost / pip math
# --------------------------------------------------------------------------- #
_SYMBOL_RE = re.compile(r"\{([^}]+)\}")


def pip_counts(mana_cost: str) -> dict:
    """Return {W,U,B,R,G: count} of colored pips in a mana cost string.
    Hybrid symbols like {W/U} count 0.5 to each side; Phyrexian {W/P} counts 1."""
    out = {c: 0.0 for c in "WUBRG"}
    for sym in _SYMBOL_RE.findall(mana_cost or ""):
        s = sym.upper()
        letters = [ch for ch in s if ch in _COLOR_LETTERS]
        if not letters:
            continue
        if "P" in s or len(letters) == 1:
            for ch in letters:
                out[ch] += 1.0 / (len(letters) if "P" not in s else 1)
        else:  # hybrid mana e.g. W/U
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


def _looks_like_land_by_name(name: str) -> bool:
    low = name.lower()
    if low in _BASICS:
        return True
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
}
WIPES = {
    "blasphemous act", "toxic deluge", "cleansing nova", "austere command",
    "vanquish the horde", "time wipe", "extinction event", "final judgment",
    "cave-in", "pyroclasm", "wave of reckoning", "deadly tempest",
    "tragic arrogance", "culling ritual", "crux of fate", "planar collapse",
    "reign of the pit", "casualties of war",
}
COUNTERS = {
    "counterspell", "force of will", "misdirection", "arcane denial", "negate",
    "essence scatter", "memory lapse", "miscalculation", "power sink", "daze",
    "spell snare", "spell blast", "absorb", "sublime epiphany", "remove soul",
    "thwart", "annul", "misstep",
}


def classify(card: Card) -> set:
    """Return the set of roles this card fills (heuristic)."""
    roles = set()
    n = _norm(card.name)
    if card.is_land:
        roles.add("land")
        return roles
    if n in RAMP:
        roles.add("ramp")
    if n in DRAW:
        roles.add("draw")
    if n in REMOVAL:
        roles.add("removal")
    if n in WIPES:
        roles.add("wipe")
    if n in COUNTERS:
        roles.add("counter")
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
