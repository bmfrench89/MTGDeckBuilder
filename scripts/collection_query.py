#!/usr/bin/env python3
"""The collection query language: one string that filters, sorts and counts the
collection.

The Collection page's search box, `analyze_collection.py --query` and the skill all
speak it, so "how many Dragons do we own, and how many are free?" gets one answer
wherever it is asked (docs/spec-collection-rebuild.md; the research behind it is
docs/research-collection-2026-10.md).

The grammar is a Scryfall-compatible subset, plus words that only an app that knows
the household's decks can answer:

    sol ring    "sol ring"    !"Sol Ring"    /^sol/     name words, phrase, exact, pattern
    t:dragon  c>=g  id<=wug  mv>=3  r:mythic  s:neo  pow>=4  usd<5  produces:g
    is:commander  is:gamechanger  role:ramp  f:commander  has:price
    free>0  decks=0  deck:"Iron Fortress"  for:ur-dragon  is:pinned  is:shared
    added>=2026-10-01  is:new  qty>1  value>20
    a b   both      a or b   either      -a   not a      ( … )   grouping
    order:usd  direction:desc            sorting

`KEYWORDS` is the one table of what parses; the page's help sheet is generated from
it, so the help can never offer a keyword nothing reads (tests pin that).

Three rules decide every answer:

1. **Unknown is not false.** Each condition comes out true, false or UNKNOWN, and
   unknown means the data is absent: a name-only row has no types, a card that was
   never enriched has no mana production. A row whose result is unknown is left out
   and COUNTED, and the summary says why ("12 skipped: no type data yet"). This is
   the repo's empty-vs-absent rule applied to search. `t:legendary` on a collection
   with no supertype data says it cannot answer, instead of answering 0.
2. **A mistake is never a silent zero.** An unknown keyword, a bad number or a broken
   pattern produces a warning that names it, and that term is dropped while the rest
   of the query runs (Scryfall's behaviour). A misspelt `rol:ramp` read as a name
   would otherwise say the household owns no ramp.
3. **Basics are unlimited** (grounding rule 9): every `qty` and `free` comparison
   treats a basic land as having as many copies as any query asks for.

AND binds tighter than OR, as on Scryfall (`a b or c` is `(a b) or c`); a dangling
`or`, an open quote or an empty `key:` left mid-typing are closed or dropped quietly.

Stdlib only. Parsing and evaluation import only `mtglib`; `records()` reads the decks,
pins and curated reference lists through imports made inside it, the way `goldfish`
keeps its loader's imports local.
"""
from __future__ import annotations

import copy
import datetime
import difflib
import operator
import re
from collections import Counter, namedtuple

import mtglib

COLORS = "WUBRG"
NEW_DAYS = 30          # is:new — the window the Collection's "New arrivals" review uses
INF = float("inf")     # a basic land's copies, for every qty/free comparison

# carddb writes ONE type for a card it enriched: the first of these its type line
# contains ("Creature" for an Artifact Creature). So on such a row a main type that
# comes BEFORE the written one is known absent, and one after it may have been
# dropped. That order is what `_has_type` reads; it must match carddb.MAIN_TYPES.
MAIN_TYPES = ("land", "creature", "planeswalker", "battle", "artifact",
              "enchantment", "instant", "sorcery")
SUPERTYPES = ("legendary", "basic", "snow", "world", "ongoing")
OTHER_TYPES = ("kindred", "tribal")
PERMANENT_TYPES = ("land", "creature", "planeswalker", "battle", "artifact", "enchantment")

ROLES = ("ramp", "rock", "dork", "fetch", "draw", "removal", "wipe", "counter", "tutor")
_CLASSIFY_ROLES = {"ramp", "draw", "removal", "wipe", "counter"}

# Scryfall's rarity order.
RARITY = {"common": 0, "uncommon": 1, "rare": 2, "special": 3, "mythic": 4, "bonus": 5}
_RARITY_ALIAS = {"c": "common", "u": "uncommon", "r": "rare", "s": "special",
                 "m": "mythic", "b": "bonus", "mythic rare": "mythic"}

_COLOR_WORDS = {
    "white": "W", "blue": "U", "black": "B", "red": "R", "green": "G",
    "azorius": "WU", "dimir": "UB", "rakdos": "BR", "gruul": "RG", "selesnya": "GW",
    "orzhov": "WB", "izzet": "UR", "golgari": "BG", "boros": "RW", "simic": "GU",
    "bant": "GWU", "esper": "WUB", "grixis": "UBR", "jund": "BRG", "naya": "RGW",
    "abzan": "WBG", "jeskai": "URW", "sultai": "BGU", "mardu": "RWB", "temur": "GUR",
    "chaos": "UBRG", "aggression": "WBRG", "altruism": "WURG", "growth": "WUBG",
    "artifice": "WUBR", "colorless": "C", "colourless": "C",
    "multicolor": "M", "multicolour": "M", "multi": "M",
}

# Power-tag labels (deckcore.load_power_tags) as the slugs `is:` takes.
_TAG_SLUGS = {"Game Changer": "gamechanger", "Fast mana": "fastmana", "Tutor": "tutor",
              "Extra turns": "extraturns", "Mass land denial": "mld"}


class QueryWarning(Exception):
    """A term that cannot be read. The parser drops it and keeps the message."""


# --------------------------------------------------------------------------- #
# Records: one per owned card, with everything a query can ask
# --------------------------------------------------------------------------- #
class Rec:
    """One owned card, as the evaluator sees it. Unknown fields are None, never a
    stand-in value: `price is None` is "no price", while 0.0 would be a real $0."""
    __slots__ = ("card", "name", "qty", "basic", "norm", "compact", "words",
                 "tw", "complete", "primary", "colors", "identity", "mv", "power",
                 "price", "value", "produced", "roles", "enriched", "flags_ver",
                 "tags", "decks", "lists", "committed", "free", "short", "pinned",
                 "added", "banned", "listed_cmd", "rarity", "set_code", "cn")

    @property
    def ndecks(self):
        return len(self.decks)


def _compact(s):
    return re.sub(r"[^a-z0-9]", "", s)


def _name_words(norm):
    return [w for w in re.split(r"[^a-z0-9']+", norm) if w]


def _cost_colors(cost):
    front = mtglib._front_cost(cost)
    return frozenset(ch for sym in re.findall(r"\{([^}]+)\}", front)
                     for ch in sym.upper() if ch in COLORS)


def make_rec(card, *, super_seen=False, tags=(), deck_use=None, lists=(), pin="",
             banned=False, listed_cmd=False):
    """Build one Rec. `super_seen` says the collection carries supertypes at all;
    with it, a row from the export (it has a rarity) has its whole type line."""
    r = Rec()
    r.card = card
    r.name = card.name
    r.qty = card.quantity
    r.basic = mtglib.is_basic(card.name)
    r.norm = mtglib._norm(card.name)
    r.compact = _compact(r.norm)
    r.words = _name_words(r.norm)
    if card.types:
        main = card._type_words()
        sub = set()
        for s in card.subtypes or ():
            low = s.lower().strip()
            sub.add(low)
            sub.update(low.split())
        tw = main | {s.lower() for s in card.supertypes or ()} | sub
        r.tw = frozenset(tw)
        r.primary = next((t for t in MAIN_TYPES if t in tw), "")
        r.complete = bool(card.supertypes) or (super_seen and bool(card.rarity)) \
            or sum(1 for t in MAIN_TYPES if t in tw) >= 2
    else:
        r.tw, r.primary, r.complete = None, "", False
    # Colour IDENTITY: data says it, or an enriched card with none is colourless.
    if card.identity:
        r.identity = frozenset(card.identity)
    elif card.types:
        r.identity = frozenset()
    else:
        r.identity = None
    # COLOURS come from the mana cost. `Card.colors` cannot be trusted for this: the
    # attrs overlay fills an empty export cell with the identity, so every dual land
    # would read as coloured. A costless land is colourless; a costless nonland
    # (suspend cards, colour indicators) takes its identity, which is the indicator.
    if (card.mana_cost or "").strip():
        r.colors = _cost_colors(card.mana_cost)
    elif _has_type(r, "land") is True:
        r.colors = frozenset()
    elif r.identity is not None:
        r.colors = r.identity
    else:
        r.colors = None
    r.mv = card.mana_value
    r.power = card.power
    r.price = card.price
    r.value = (round(card.value, 2) if card.value else round(card.quantity * card.price, 2)) \
        if card.price is not None else None
    r.produced = frozenset(card.produced) if card.produced is not None else None
    r.enriched = bool(card.types) or bool(card.flags)
    r.flags_ver = card.flags_ver
    r.tags = frozenset(tags)
    roles = set(mtglib.classify(card)) & _CLASSIFY_ROLES
    if "ramp" in roles:
        art, cre = _has_type(r, "artifact"), _has_type(r, "creature")
        if "rock" in card.flags or (art is True and cre is not True):
            roles.add("rock")
        if "dork" in card.flags or cre is True:
            roles.add("dork")
    if any(f.startswith("fetch:") for f in card.flags):
        roles.add("fetch")
    if "tutor" in r.tags:
        roles.add("tutor")
    r.roles = frozenset(roles)
    deck_use = deck_use or {}
    r.decks = dict(deck_use)
    r.lists = frozenset(lists)
    r.committed = 0 if r.basic else sum(deck_use.values())
    r.pinned = pin or ""
    reserved = 1 if (r.pinned and r.pinned not in deck_use and not r.basic) else 0
    r.free = INF if r.basic else max(0, r.qty - r.committed - reserved)
    r.short = (not r.basic) and r.committed > r.qty
    r.added = (card.date_added or "")[:10]
    r.banned = bool(banned)
    r.listed_cmd = bool(listed_cmd)
    r.rarity = (card.rarity or "").strip().lower()
    r.rarity = _RARITY_ALIAS.get(r.rarity, r.rarity)
    r.set_code = (card.set_code or "").strip().lower()
    r.cn = (card.collector_number or "").strip().lower()
    return r


def _has_type(r, word):
    """True / False / None (unknown) for "does this card have type `word`"."""
    if word == "basic":
        return r.basic                           # name-based, always known
    if r.basic and word == "land":
        return True
    if r.tw is None:
        return None
    if word in r.tw:
        return True
    if r.complete:
        return False
    if word in MAIN_TYPES:
        if r.primary and MAIN_TYPES.index(word) < MAIN_TYPES.index(r.primary):
            return False                         # carddb would have written it
        return None
    if word in SUPERTYPES or word in OTHER_TYPES:
        return None
    return False                                 # carddb writes every subtype


Deck = namedtuple("Deck", "stem title commander colors study")


class Context:
    """What the evaluator knows beyond the cards: the decks and today's date."""
    def __init__(self, decks=(), today=None, super_seen=False, type_vocab=()):
        self.decks = list(decks)
        self.titles = {d.stem: d.title for d in self.decks}
        self.today = (today or datetime.date.today().isoformat())[:10]
        self.super_seen = super_seen
        self.type_vocab = frozenset(type_vocab)
        self.notes = []

    def find_decks(self, text):
        """Decks whose file name, title or commander contains `text`. An exact file
        name wins outright, so `deck:ur-dragon` never also means `ur-dragon-2`."""
        q = re.sub(r"[-_\s]+", " ", mtglib._norm(text)).strip()
        if not q:
            return []
        exact = [d for d in self.decks if d.stem.lower() == text.strip().lower()]
        if exact:
            return exact
        out = []
        for d in self.decks:
            hay = " | ".join(re.sub(r"[-_\s]+", " ", mtglib._norm(x))
                             for x in (d.stem, d.title, d.commander) if x)
            if q in hay or _compact(q) in _compact(hay):
                out.append(d)
        return out


def records(coll, decks_dir=None, *, pins=None, power_tags=None, commanders=None,
            banned=None, today=None):
    """One `Rec` per owned card, plus the `Context` (decks, date) queries need.

    `decks_dir` is read the way `deck_conflicts.scan` reads it: every `*.txt`, each
    line a physical card, a study copy (`# Study: yes`) holding none. Study lists
    still answer `deck:` (it asks what a list contains), never `decks` or `free`.
    Every argument left None is read from the repo's own files; tests pass theirs."""
    import glob
    import os
    import deck_conflicts
    import deckcore
    if pins is None:
        pins = deckcore.load_pins()
    if power_tags is None:
        power_tags = deckcore.load_power_tags()
    if commanders is None:
        import similar_commanders
        try:
            commanders = {mtglib.card_key(c["name"]) for c in similar_commanders.load_commanders()}
        except OSError:
            commanders = set()
    if banned is None:
        import deck_fit
        banned = deck_fit.load_banned()
    banned = set(banned)

    decks, use, lists = [], {}, {}
    for path in sorted(glob.glob(os.path.join(decks_dir, "*.txt"))) if decks_dir else ():
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        study = deck_conflicts.is_study_deck(path)
        colors = frozenset(re.findall(r"[WUBRG]", mtglib.deck_header(text, "Colors?").upper()))
        decks.append(Deck(stem, mtglib.deck_header(text, "Title") or stem,
                          mtglib.deck_header(text, "Commander"), colors, study))
        for c in mtglib.parse_deck(text):
            k = mtglib.card_key(c.name)
            lists.setdefault(k, set()).add(stem)
            if not study:
                u = use.setdefault(k, {})
                u[stem] = u.get(stem, 0) + c.quantity

    super_seen = any(c.supertypes for c in coll)
    recs, vocab = [], set()
    for c in coll:
        k = mtglib.card_key(c.name)
        tags = set()
        for nk in mtglib.name_keys(c.name):
            tags.update(_TAG_SLUGS.get(t, "") for t in power_tags.get(nk, ()))
        tags.discard("")
        rec = make_rec(c, super_seen=super_seen, tags=tags, deck_use=use.get(k),
                       lists=lists.get(k, ()), pin=pins.get(k, ""),
                       banned=bool(mtglib.name_keys(c.name) & banned),
                       listed_cmd=k in commanders)
        if rec.tw:
            vocab |= rec.tw
        recs.append(rec)
    return recs, Context(decks, today, super_seen, vocab)


# --------------------------------------------------------------------------- #
# Tokenizer
# --------------------------------------------------------------------------- #
Term = namedtuple("Term", "key op value start end quoted regex")
_KEY_RE = re.compile(r"([a-zA-Z]+)(<=|>=|!=|:|=|<|>)")
_FOLD_QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"',
                              "‘": "'", "’": "'"})


def _read_value(s, i):
    """(value, end, quoted, regex) from position i. Unclosed quotes and patterns run
    to the end of the string: that is someone mid-typing, not an error."""
    n = len(s)
    if i < n and s[i] == '"':
        j = s.find('"', i + 1)
        j = n if j < 0 else j
        return s[i + 1:j], min(j + 1, n), True, False
    if i < n and s[i] == "/":
        j = i + 1
        while j < n and not (s[j] == "/" and s[j - 1] != "\\"):
            j += 1
        return s[i + 1:j], min(j + 1, n), False, True
    j = i
    while j < n and not s[j].isspace() and s[j] not in "()":
        j += 1
    return s[i:j], j, False, False


def tokenize(text):
    """The query as tokens: '(' and ')', 'OR', 'NEG', and Term tuples carrying their
    span in the (quote-folded) text, which is what lets a chip remove its own part."""
    s = (text or "").translate(_FOLD_QUOTES)
    out, i, n = [], 0, len(s)
    while i < n:
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "()":
            out.append((ch, i, i + 1))
            i += 1
            continue
        if ch == "-" and i + 1 < n and not s[i + 1].isspace():
            out.append(("NEG", i, i + 1))
            i += 1
            continue
        start = i
        m = _KEY_RE.match(s, i)
        if m:
            value, i, quoted, regex = _read_value(s, m.end())
            out.append(Term(m.group(1).lower(), m.group(2), value, start, i, quoted, regex))
            continue
        if ch == "!":
            value, i, quoted, regex = _read_value(s, i + 1)
            out.append(Term("!", "=", value, start, i, quoted, regex))
            continue
        value, i, quoted, regex = _read_value(s, i)
        if not quoted and not regex and value.lower() == "or":
            out.append(("OR", start, i))
        elif not quoted and not regex and value.lower() == "and":
            continue                                   # AND is already implied
        elif value or quoted:
            out.append(Term("name", ":", value, start, i, quoted, regex))
    return s, out


# --------------------------------------------------------------------------- #
# Parser: expr := and ( OR and )* ; and := unary+ ; unary := NEG unary | primary
# --------------------------------------------------------------------------- #
class Node:
    __slots__ = ("kind", "kids", "term", "start", "end", "fn", "phrase", "reason")

    def __init__(self, kind, kids=(), term=None, start=0, end=0):
        self.kind, self.kids, self.term = kind, list(kids), term
        self.start, self.end = start, end
        self.fn = self.phrase = self.reason = None


class _Parser:
    def __init__(self, toks):
        self.toks, self.i = toks, 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    @staticmethod
    def kind(tok):
        return "TERM" if isinstance(tok, Term) else tok[0]

    def expr(self):
        parts = []
        while True:
            node = self.and_()
            if node is not None:
                parts.append(node)
            tok = self.peek()
            if tok is not None and self.kind(tok) == "OR":
                self.i += 1
                continue                                # a dangling OR is dropped
            break
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return Node("or", parts, start=parts[0].start, end=parts[-1].end)

    def and_(self):
        parts = []
        while True:
            tok = self.peek()
            if tok is None or self.kind(tok) in ("OR", ")"):
                break
            node = self.unary()
            if node is not None:
                parts.append(node)
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return Node("and", parts, start=parts[0].start, end=parts[-1].end)

    def unary(self):
        tok = self.peek()
        if self.kind(tok) == "NEG":
            self.i += 1
            inner = self.unary() if self.peek() is not None and \
                self.kind(self.peek()) not in ("OR", ")") else None
            if inner is None:
                return None
            return Node("not", [inner], start=tok[1], end=inner.end)
        if self.kind(tok) == "(":
            self.i += 1
            inner = self.expr()
            close = self.peek()
            end = tok[2]
            if close is not None and self.kind(close) == ")":
                self.i += 1
                end = close[2]
            elif inner is not None:
                end = inner.end                         # auto-closed at the end
            if inner is None:
                return None
            inner.start, inner.end = tok[1], end        # the chip owns its parens
            return inner
        self.i += 1
        if self.kind(tok) == ")":
            return None                                 # a stray ')' is dropped
        return Node("term", term=tok, start=tok.start, end=tok.end)


# --------------------------------------------------------------------------- #
# Term compilers: each returns (fn(rec) -> True/False/None, phrase, unknown-reason)
# or raises QueryWarning. Registered in KEYWORDS below.
# --------------------------------------------------------------------------- #
_CMP = {":": operator.eq, "=": operator.eq, "!=": operator.ne, "<": operator.lt,
        "<=": operator.le, ">": operator.gt, ">=": operator.ge}
_SYM = {":": "=", "=": "=", "!=": "≠", "<": "<", "<=": "≤", ">": ">", ">=": "≥"}


def _number(t, label):
    try:
        return float(t.value)
    except ValueError:
        raise QueryWarning(f"{label} needs a number, not “{t.value}”, so "
                           f"“{t.key}{t.op}{t.value}” was ignored.")


def _fmt(n):
    return str(int(n)) if float(n).is_integer() else f"{n:g}"


def _c_name(t, ctx):
    v = t.value
    if t.regex:
        try:
            pat = re.compile(v, re.I)
        except re.error:
            raise QueryWarning(f"“/{v}/” isn't a pattern this search can read, so it "
                               "was ignored.")
        return (lambda r: bool(pat.search(r.norm))), f"name matches /{v}/", None
    if t.key == "!":
        want = mtglib._norm(v)
        wf = mtglib._norm(mtglib.front_face(v))
        return (lambda r: r.norm == want or mtglib._norm(mtglib.front_face(r.name)) == wf), \
            f"name is “{v}”", None
    phrase = mtglib._norm(v)
    if not phrase:
        raise QueryWarning("")
    words = [phrase] if t.quoted else phrase.split()
    cw = [_compact(w) for w in words]

    def fn(r):
        for w, c in zip(words, cw):
            if w not in r.norm and not (c and c in r.compact):
                return False
        return True
    return fn, f"name has “{v}”", None


def _c_type(t, ctx):
    words = [w for w in re.split(r"[\s—-]+", t.value.lower()) if w]
    if not words:
        raise QueryWarning("")
    for w in words:
        if (ctx.type_vocab and w not in ctx.type_vocab and w not in MAIN_TYPES
                and w not in SUPERTYPES and w not in OTHER_TYPES):
            near = difflib.get_close_matches(w, sorted(ctx.type_vocab), n=1)
            ctx_warn = (f"No card here has the type “{w}”"
                        + (f" — did you mean t:{near[0]}?" if near else "."))
            ctx.notes.append(ctx_warn)

    def fn(r):
        res = True
        for w in words:
            v = _has_type(r, w)
            if v is False:
                return False
            if v is None:
                res = None
        return res
    supers = any(w in SUPERTYPES or w in OTHER_TYPES for w in words)

    def why(r):
        if r.tw is None:
            return "no type data yet"
        return "no supertype data yet" if supers else "only the main type is known"
    return fn, f"type {' '.join(words)}", why


def _parse_colors(value):
    """A colour value as ('set', frozenset) or ('pred', 'C'|'M') or ('count', n)."""
    v = value.strip().lower()
    if v in _COLOR_WORDS:
        v = _COLOR_WORDS[v].lower()
    if v.isdigit():
        return "count", int(v)
    if v in ("c", "m"):
        return "pred", v.upper()
    if v and set(v) <= set("wubrg"):
        return "set", frozenset(v.upper())
    raise QueryWarning(f"“{value}” isn't a colour (try w, u, b, r, g, a guild name, "
                       "c for colourless or m for multicolour), so it was ignored.")


def _set_compare(kind, q, op):
    """fn(card_set) for a colour-style comparison."""
    if kind == "pred":
        test = (lambda a: len(a) == 0) if q == "C" else (lambda a: len(a) >= 2)
        return (lambda a: not test(a)) if op == "!=" else test
    if kind == "count":
        cmp = _CMP[op]
        return lambda a: cmp(len(a), q)
    return {"=": lambda a: a == q, "!=": lambda a: a != q,
            ">=": lambda a: a >= q, ">": lambda a: a > q,
            "<=": lambda a: a <= q, "<": lambda a: a < q}[op]


def _color_words(kind, q):
    if kind == "pred":
        return "colourless" if q == "C" else "multicolour"
    if kind == "count":
        return f"{q} colour{'s' if q != 1 else ''}"
    return "".join(c for c in COLORS if c in q)


def _c_color(t, ctx):
    kind, q = _parse_colors(t.value)
    op = ">=" if t.op == ":" else t.op
    test = _set_compare(kind, q, op)
    words = {">=": "include", "=": "exactly", "!=": "not exactly", "<=": "within",
             "<": "strictly within", ">": "more than"}
    label = _color_words(kind, q)
    phrase = (f"colours {label}" if kind == "pred" and op in (">=", "=") else
              f"colours {words.get(op, op)} {label}")
    return (lambda r: None if r.colors is None else test(r.colors)), phrase, "no colour data yet"


def _c_identity(t, ctx):
    kind, q = _parse_colors(t.value)
    op = "<=" if t.op == ":" else t.op
    test = _set_compare(kind, q, op)
    words = {"<=": "within", "=": "exactly", "!=": "not exactly", ">=": "includes",
             ">": "more than", "<": "strictly within"}
    label = _color_words(kind, q)
    phrase = (f"identity {label}" if kind == "pred" else
              f"identity {words.get(op, op)} {label}")
    return (lambda r: None if r.identity is None else test(r.identity)), phrase, \
        "no colour data yet"


def _numeric(attr, label, reason, *, unlimited_basics=False):
    def compile_(t, ctx):
        if t.key in ("mv", "cmc", "manavalue") and t.value.lower() in ("even", "odd"):
            want = 0 if t.value.lower() == "even" else 1
            return (lambda r: None if r.mv is None else int(r.mv) % 2 == want), \
                f"{t.value.lower()} mana value", reason
        n = _number(t, label)
        cmp = _CMP[t.op]

        def fn(r):
            v = getattr(r, attr)
            if unlimited_basics and r.basic:
                v = INF if attr == "qty" else v
            return None if v is None else cmp(v, n)
        return fn, f"{label} {_SYM[t.op]} {_fmt(n)}", reason
    return compile_


def _c_power(t, ctx):
    n = _number(t, "power")
    cmp = _CMP[t.op]

    def fn(r):
        if r.power is not None:
            return cmp(r.power, n)
        return False if _has_type(r, "creature") is False else None
    return fn, f"power {_SYM[t.op]} {_fmt(n)}", "no power known"


def _c_money(attr, label):
    def compile_(t, ctx):
        n = _number(t, label)
        cmp = _CMP[t.op]
        return (lambda r: None if getattr(r, attr) is None else cmp(getattr(r, attr), n)), \
            f"est. {label} {_SYM[t.op]} ${_fmt(n)}", "no price yet"
    return compile_


def _c_produces(t, ctx):
    v = t.value.strip().upper()
    if not v or not set(v) <= set("WUBRGC"):
        raise QueryWarning(f"produces: takes mana letters (w u b r g c), not “{t.value}”, "
                           "so it was ignored.")
    q = frozenset(v)
    op = ">=" if t.op == ":" else t.op
    test = _set_compare("set", q, op)
    return (lambda r: None if r.produced is None else test(r.produced)), \
        f"taps for {''.join(c for c in 'WUBRGC' if c in q)}", "no mana-production data yet"


def _c_rarity(t, ctx):
    v = _RARITY_ALIAS.get(t.value.strip().lower(), t.value.strip().lower())
    if v not in RARITY:
        raise QueryWarning(f"“{t.value}” isn't a rarity (common, uncommon, rare, mythic, "
                           "special, bonus), so it was ignored.")
    want, cmp = RARITY[v], _CMP[t.op]
    return (lambda r: None if r.rarity not in RARITY else cmp(RARITY[r.rarity], want)), \
        (f"rarity {v}" if t.op in (":", "=") else f"rarity {_SYM[t.op]} {v}"), "no rarity data"


def _c_set(t, ctx):
    v = t.value.strip().lower()
    if not v:
        raise QueryWarning("")
    neg = t.op == "!="
    return (lambda r: None if not r.set_code else (r.set_code == v) != neg), \
        f"set {'≠ ' if neg else ''}{v.upper()}", "no set data"


def _c_cn(t, ctx):
    v = t.value.strip().lower()
    if not v:
        raise QueryWarning("")
    if v.isdigit() and t.op not in (":", "=", "!="):
        n, cmp = int(v), _CMP[t.op]
        return (lambda r: None if not r.cn else (cmp(int(re.sub(r"\D", "", r.cn) or -1), n))), \
            f"collector number {_SYM[t.op]} {v}", "no collector number"
    neg = t.op == "!="
    return (lambda r: None if not r.cn else (r.cn == v) != neg), \
        f"collector number {v}", "no collector number"


_IS = {}       # value -> (fn, phrase, reason)


def _is_entry(*names, phrase, reason=None):
    def deco(fn):
        for n in names:
            _IS[n] = (fn, phrase, reason)
        return fn
    return deco


def _why_super(r):
    return "no type data yet" if r.tw is None else "no supertype data yet"


@_is_entry("commander", phrase="can be a commander", reason=_why_super)
def _is_commander(r):
    if r.listed_cmd:
        return True
    leg, cre = _has_type(r, "legendary"), _has_type(r, "creature")
    if leg is False or cre is False:
        return False
    return True if (leg and cre) else None


@_is_entry("legendary", "legend", phrase="legendary", reason=_why_super)
def _is_legendary(r):
    return _has_type(r, "legendary")


@_is_entry("spell", phrase="a spell (not a land)", reason="no type data yet")
def _is_spell(r):
    land = _has_type(r, "land")
    return None if land is None else not land


@_is_entry("permanent", phrase="a permanent", reason="no type data yet")
def _is_permanent(r):
    if r.tw is None and not r.basic:
        return None
    if _has_type(r, "instant") is True or _has_type(r, "sorcery") is True:
        return False
    if any(_has_type(r, x) is True for x in PERMANENT_TYPES):
        return True
    return None


@_is_entry("basic", phrase="a basic land")
def _is_basic(r):
    return r.basic


@_is_entry("multicolor", "multicolour", "multi", "gold", phrase="multicolour",
           reason="no colour data yet")
def _is_multi(r):
    return None if r.colors is None else len(r.colors) >= 2


@_is_entry("mono", "monocolor", "monocolour", "monocolored", phrase="one colour",
           reason="no colour data yet")
def _is_mono(r):
    return None if r.colors is None else len(r.colors) == 1


@_is_entry("colorless", "colourless", phrase="colourless", reason="no colour data yet")
def _is_colorless(r):
    return None if r.colors is None else len(r.colors) == 0


@_is_entry("free", phrase="has a free copy")
def _is_free(r):
    return r.free > 0


@_is_entry("pinned", phrase="pinned to a deck")
def _is_pinned(r):
    return bool(r.pinned)


@_is_entry("shared", "short", phrase="in more decks than copies owned")
def _is_shared(r):
    return r.short


@_is_entry("banned", phrase="banned in Commander")
def _is_banned(r):
    return r.banned


for _slug, _label in (("gamechanger", "a Game Changer"), ("fastmana", "fast mana"),
                      ("tutor", "a tutor"), ("extraturns", "an extra-turn card"),
                      ("mld", "mass land denial")):
    _IS[_slug] = ((lambda s: lambda r: s in r.tags)(_slug), _label, None)
_IS["gc"] = _IS["gamechanger"]
_IS["extraturn"] = _IS["extraturns"]


def _c_is(t, ctx):
    v = t.value.strip().lower()
    if v == "new":
        cutoff = (datetime.date.fromisoformat(ctx.today)
                  - datetime.timedelta(days=NEW_DAYS)).isoformat()
        fn, phrase, reason = (lambda r: bool(r.added) and r.added >= cutoff), \
            f"added in the last {NEW_DAYS} days", None
    elif v in _IS:
        fn, phrase, reason = _IS[v]
    else:
        near = difflib.get_close_matches(v, sorted(set(_IS) | {"new"}), n=1)
        raise QueryWarning(f"“{t.key}:{t.value}” isn't something this search knows"
                           + (f" — did you mean is:{near[0]}?" if near else ".")
                           + " It was ignored.")
    if t.key == "not":
        return (lambda r: (lambda x: None if x is None else not x)(fn(r))), \
            f"not {phrase}", reason
    return fn, phrase, reason


_HAS = {"types": (lambda r: r.tw is not None, "type data"),
        "type": (lambda r: r.tw is not None, "type data"),
        "price": (lambda r: r.price is not None, "a price"),
        "date": (lambda r: bool(r.added), "a date added"),
        "production": (lambda r: r.produced is not None, "mana-production data")}


def _c_has(t, ctx):
    v = t.value.strip().lower()
    if v not in _HAS:
        raise QueryWarning(f"“has:{t.value}” isn't something this search knows "
                           f"(try {', '.join('has:' + k for k in ('types', 'price', 'date', 'production'))}), "
                           "so it was ignored.")
    fn, what = _HAS[v]
    return fn, f"has {what}", None


def _c_role(t, ctx):
    v = t.value.strip().lower()
    if v.endswith("s") and v[:-1] in ROLES:
        v = v[:-1]
    if v not in ROLES:
        near = difflib.get_close_matches(v, ROLES, n=1)
        raise QueryWarning(f"“role:{t.value}” isn't a role this search knows"
                           + (f" — did you mean role:{near[0]}?" if near else
                              f" ({', '.join(ROLES)})") + ". It was ignored.")
    neg = t.op == "!="

    def fn(r):
        if v in r.roles:
            res = True
        elif v == "tutor" or r.basic:
            res = False                                  # a curated list: always known
        elif v == "fetch":
            if not r.enriched:
                res = None
            elif _has_type(r, "land") is False:
                res = False
            else:
                res = False if r.flags_ver >= 2 else None
        else:
            res = False if r.enriched else None
        return res if (res is None or not neg) else not res
    return fn, f"role {'≠ ' if neg else ''}{v}", "no card data yet"


def _c_qty(t, ctx):
    return _numeric("qty", "copies owned", None, unlimited_basics=True)(t, ctx)


def _c_free(t, ctx):
    n = _number(t, "free copies")
    cmp = _CMP[t.op]
    return (lambda r: cmp(r.free, n)), f"free copies {_SYM[t.op]} {_fmt(n)}", None


def _c_decks(t, ctx):
    n = _number(t, "decks")
    cmp = _CMP[t.op]
    if t.op in (":", "=") and n == 0:
        phrase = "in no deck"
    else:
        phrase = f"in {_SYM[t.op]} {_fmt(n)} deck{'s' if n != 1 else ''}"
    return (lambda r: cmp(len(r.decks), n)), phrase, None


def _c_in(t, ctx):
    v = t.value.strip().lower()
    if v not in ("deck", "decks", "adeck"):
        raise QueryWarning(f"“in:{t.value}” is a printing search on Scryfall; here "
                           "in:deck is the only one (cards in a sleeved deck). It was ignored.")
    return (lambda r: len(r.decks) > 0), "in a deck", None


def _c_deck(t, ctx):
    found = ctx.find_decks(t.value)
    if not found:
        names = ", ".join(d.stem for d in ctx.decks[:8]) or "none saved yet"
        raise QueryWarning(f"No saved deck matches “{t.value}” (decks: {names}), so "
                           f"“{t.key}:{t.value}” was ignored.")
    stems = {d.stem for d in found}
    label = " or ".join(d.title for d in found)
    neg = t.op == "!="
    return (lambda r: bool(r.lists & stems) != neg), \
        f"{'not ' if neg else ''}in {label}", None


def _c_for(t, ctx):
    found = ctx.find_decks(t.value)
    if not found:
        names = ", ".join(d.stem for d in ctx.decks[:8]) or "none saved yet"
        raise QueryWarning(f"No saved deck matches “{t.value}” (decks: {names}), so "
                           f"“for:{t.value}” was ignored.")
    idents = [d.colors for d in found if d.colors]
    if not idents:
        raise QueryWarning(f"{found[0].title} has no Colors line, so “for:{t.value}” "
                           "was ignored.")

    def fn(r):
        if r.identity is None:
            return None
        return any(r.identity <= ident for ident in idents)
    label = " or ".join(f"{d.title} ({''.join(c for c in COLORS if c in d.colors) or 'C'})"
                        for d in found if d.colors)
    return fn, f"fits {label}", "no colour data yet"


_DATE_RE = re.compile(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?$")


def _c_added(t, ctx):
    m = _DATE_RE.match(t.value.strip())
    if not m:
        raise QueryWarning(f"added needs a date like 2026-10-01, 2026-10 or 2026, not "
                           f"“{t.value}”, so it was ignored.")
    y, mo, d = m.group(1), m.group(2), m.group(3)
    lo = f"{y}-{int(mo or 1):02d}-{int(d or 1):02d}"
    hi = f"{y}-{int(mo or 12):02d}-{int(d or 31):02d}"
    op = t.op
    tests = {":": lambda a: lo <= a <= hi, "=": lambda a: lo <= a <= hi,
             "!=": lambda a: not (lo <= a <= hi), ">=": lambda a: a >= lo,
             ">": lambda a: a > hi, "<=": lambda a: a <= hi, "<": lambda a: a < lo}
    test = tests[op]
    when = t.value.strip()
    words = {":": "in", "=": "in", "!=": "not in", ">=": "on or after", ">": "after",
             "<=": "on or before", "<": "before"}
    if d and op in (":", "="):
        words[op] = "on"
    return (lambda r: None if not r.added else test(r.added)), \
        f"added {words[op]} {when}", "no date added"


def _c_format(t, ctx):
    v = t.value.strip().lower()
    if v not in ("commander", "edh"):
        raise QueryWarning(f"Only Commander legality is known here, so “{t.key}:{t.value}” "
                           "was ignored.")
    if t.key == "banned":
        return (lambda r: r.banned), "banned in Commander", None
    return (lambda r: not r.banned), "legal in Commander", None


def _c_oracle(t, ctx):
    raise QueryWarning(f"Rules text isn't stored yet, so “{t.key}:{t.value}” was ignored. "
                       "Try role:ramp, role:draw, role:removal, role:wipe or role:counter.")


Kw = namedtuple("Kw", "key aliases compile example means support")

# THE vocabulary. The help sheet is generated from this table; `parse` reads nothing
# else. An entry's example must parse clean (tests/test_collection_query.py).
KEYWORDS = (
    Kw("name", (), _c_name, 'sol ring',
       'Name words, all of them; "solring" works. "a phrase", !"Exact Name", /regex/.',
       "full"),
    Kw("t", ("type",), _c_type, "t:dragon",
       "A word on the type line: card type, supertype or subtype.",
       "full where typed"),
    Kw("c", ("color", "colour"), _c_color, "c:g",
       "Colours, from the mana cost. c:g at least green, c=g exactly, c<=gw within, "
       "c:c colourless, c:m multicolour.", "full where costed"),
    Kw("id", ("identity", "ci", "commander"), _c_identity, "id<=g",
       "Colour identity. id:wug and id<=wug fit a WUG deck; id>=g includes green; "
       "id=g exactly.", "full where enriched"),
    Kw("mv", ("cmc", "manavalue"), _numeric("mv", "mana value", "no mana value yet"),
       "mv>=3", "Mana value; mv:even, mv:odd.", "full"),
    Kw("pow", ("power",), _c_power, "pow>=4", "Printed power.", "partial"),
    Kw("r", ("rarity",), _c_rarity, "r:mythic", "Rarity; r>=rare.", "where the export has it"),
    Kw("s", ("set", "e", "edition"), _c_set, "s:neo", "Set code of the printing you own.",
       "where the export has it"),
    Kw("cn", ("number",), _c_cn, "cn:123", "Collector number.", "where the export has it"),
    Kw("usd", ("price",), _c_money("price", "price"), "usd<5",
       "Estimated price per copy (an estimate, not a quote).", "estimate"),
    Kw("value", (), _c_money("value", "value"), "value>20",
       "Copies × estimated price.", "estimate"),
    Kw("produces", (), _c_produces, "produces:g", "Mana the card taps for (c = colourless).",
       "full where enriched"),
    Kw("is", ("not",), _c_is, "is:commander",
       "commander, legendary, gamechanger, fastmana, tutor, extraturns, mld, spell, "
       "permanent, basic, multicolor, mono, colorless, new, free, pinned, shared, "
       "banned. not:x is -is:x.", "full"),
    Kw("has", (), _c_has, "has:price", "types, price, date, production: the data exists.",
       "full"),
    Kw("role", (), _c_role, "role:ramp",
       "ramp, rock, dork, fetch, draw, removal, wipe, counter, tutor (heuristic).",
       "heuristic"),
    Kw("qty", ("copies", "owned"), _c_qty, "qty>1", "Copies owned (basics: unlimited).",
       "full"),
    Kw("free", (), _c_free, "free>0",
       "Copies outside every sleeved deck and pin (basics: unlimited).", "full"),
    Kw("decks", (), _c_decks, "decks>=2",
       "How many sleeved decks use it; decks=0 is in no deck.", "full"),
    Kw("in", (), _c_in, "in:deck", "in:deck is decks>0.", "full"),
    Kw("deck", (), _c_deck, "deck:ur-dragon",
       "In one saved deck, by file name, title or commander (study lists included).",
       "full"),
    Kw("for", (), _c_for, "for:ur-dragon", "Fits that deck's colour identity.", "full"),
    Kw("added", ("date",), _c_added, "added>=2026-10-01",
       "Date added: 2026-10-01, 2026-10 or 2026.", "where dated"),
    Kw("f", ("format", "legal", "banned"), _c_format, "f:commander",
       "Commander legality (from data/reference/banned.txt).", "commander only"),
    Kw("o", ("oracle", "fo", "kw", "keyword"), _c_oracle, "",
       "Rules text: not stored yet, so it warns and suggests role:.", "none yet"),
    Kw("order", ("sort",), None, "order:usd",
       "Sort: name, mv, color, type, rarity, set, usd, value, qty, free, decks, added, power.",
       "full"),
    Kw("direction", ("dir",), None, "direction:desc", "asc or desc.", "full"),
)
_BY_KEY = {}
for _kw in KEYWORDS:
    for _k in (_kw.key,) + _kw.aliases:
        if re.fullmatch(r"[a-z]+", _k):
            _BY_KEY[_k] = _kw
_DIRECTIVES = {"order", "sort", "direction", "dir"}


# --------------------------------------------------------------------------- #
# Ordering and grouping
# --------------------------------------------------------------------------- #
_TYPE_ORDER = ("creature", "planeswalker", "battle", "instant", "sorcery", "artifact",
               "enchantment", "land")


def _color_key(r):
    ident = r.identity
    if ident is None:
        return None
    if not ident:
        return (3, 0)
    idx = tuple(COLORS.index(c) for c in COLORS if c in ident)
    return (0, idx) if len(ident) == 1 else (1, len(ident), idx)


def _type_key(r):
    return _TYPE_ORDER.index(r.primary) if r.primary in _TYPE_ORDER else (
        len(_TYPE_ORDER) if r.tw is not None else None)


# name -> (key(rec) or None for unknown, default direction, label)
ORDERS = {
    "name": (lambda r: r.norm, "asc", "Name"),
    "mv": (lambda r: r.mv, "asc", "Mana value"),
    "color": (_color_key, "asc", "Colour"),
    "type": (_type_key, "asc", "Type"),
    "rarity": (lambda r: RARITY.get(r.rarity), "desc", "Rarity"),
    "set": (lambda r: r.set_code or None, "asc", "Set"),
    "usd": (lambda r: r.price, "desc", "Est. price"),
    "value": (lambda r: r.value, "desc", "Est. value"),
    "qty": (lambda r: r.qty, "desc", "Copies owned"),
    "free": (lambda r: r.qty if r.basic else r.free, "desc", "Free copies"),
    "decks": (lambda r: len(r.decks), "desc", "Decks using it"),
    "added": (lambda r: r.added or None, "desc", "Date added"),
    "power": (lambda r: r.power, "desc", "Power"),
}
_ORDER_ALIAS = {"cmc": "mv", "colour": "color", "price": "usd", "eur": "usd",
                "copies": "qty", "date": "added", "pow": "power", "relevance": "relevance"}


def _group_mv(r, ctx):
    if r.mv is None:
        return (99, "No mana value")
    b = min(int(r.mv), 7)
    return (b, "MV 7+" if b == 7 else f"MV {b}")


def _group_color(r, ctx):
    k = _color_key(r)
    if k is None:
        return ((9,), "No colour data")
    if not r.identity:
        return (k, "Colourless")
    return (k, "".join(c for c in COLORS if c in r.identity))


def _group_type(r, ctx):
    k = _type_key(r)
    if k is None:
        return (99, "No type data")
    return (k, r.primary.title() if r.primary else "Other")


def _group_role(r, ctx):
    for i, role in enumerate(ROLES):
        if role in r.roles:
            return (i, role.title())
    return (len(ROLES), "Other") if r.enriched else (99, "Role unknown")


def _group_deck(r, ctx):
    if not r.decks:
        return ((0,), "In no deck")
    if len(r.decks) == 1:
        stem = next(iter(r.decks))
        return ((1, stem), ctx.titles.get(stem, stem))
    return ((2,), "In several decks")


def _group_added(r, ctx):
    """Newest month first; undated cards last."""
    if not r.added:
        return ((1,), "No date")
    ym = int(r.added[:4]) * 100 + int(r.added[5:7] or 0)
    return ((0, -ym), r.added[:7])


GROUPS = {"type": ("Type", _group_type), "color": ("Colour identity", _group_color),
          "mv": ("Mana value", _group_mv), "role": ("Role", _group_role),
          "deck": ("Deck", _group_deck), "added": ("Month added", _group_added)}


# --------------------------------------------------------------------------- #
# Parse, compile, run
# --------------------------------------------------------------------------- #
class Query:
    """A parsed query: its tree, the sort it asked for, and what it couldn't read."""
    def __init__(self, text):
        self.text = text or ""
        self.source = ""
        self.tree = None
        self.order = None
        self.direction = None
        self.warnings = []
        self.name_words = []
        self.terms = []


def parse(text, ctx=None):
    """Parse and compile `text` against `ctx` (decks, today). Never raises: what it
    can't read becomes a warning, and the rest of the query stands."""
    # A per-parse copy: the app shares one memoised Context across requests, and the
    # notes a parse collects must never leak into a neighbour's.
    ctx = copy.copy(ctx or Context())
    ctx.notes = []
    q = Query(text)
    q.source, toks = tokenize(text)
    p, parts = _Parser(toks), []
    while p.i < len(toks):
        node = p.expr()
        if node is not None:
            parts.append(node)
        if p.i < len(toks):
            p.i += 1                  # a stray ')': skip it and keep reading the rest
    tree = (None if not parts else parts[0] if len(parts) == 1 else
            Node("and", parts, start=parts[0].start, end=parts[-1].end))
    q.tree = _compile(tree, q, ctx)
    q.warnings.extend(n for n in ctx.notes if n not in q.warnings)
    return q


def _compile(node, q, ctx, negated=False):
    if node is None:
        return None
    if node.kind == "term":
        t = node.term
        if t.key in _DIRECTIVES:
            _directive(t, q)
            return None
        if not t.value and not t.quoted:
            return None                                  # `t:` mid-typing, any key
        kw = _BY_KEY.get(t.key) if t.key not in ("!",) else _BY_KEY["name"]
        if kw is None:
            known = sorted(_BY_KEY)
            near = difflib.get_close_matches(t.key, known, n=1)
            q.warnings.append(
                f"“{t.key}{t.op}{t.value}” was ignored: “{t.key}{t.op}” isn't a keyword "
                "this search knows."
                + (f" Did you mean {near[0]}{t.op}?" if near else "")
                + (" To search a name with a colon in it, put it in quotes."
                   if t.op == ":" and not near else ""))
            return None
        try:
            node.fn, node.phrase, node.reason = kw.compile(t, ctx)
        except QueryWarning as w:
            if str(w):
                q.warnings.append(str(w))
            return None
        if kw.key == "name" and not t.regex and t.key != "!" and not negated:
            q.name_words.append(mtglib._norm(t.value))
        q.terms.append(node)
        return node
    if node.kind == "not":
        inner = _compile(node.kids[0], q, ctx, not negated)
        if inner is None:
            return None
        node.kids = [inner]
        return node
    kids = [k for k in (_compile(k, q, ctx, negated) for k in node.kids) if k is not None]
    if not kids:
        return None
    if len(kids) == 1:
        # What's left of a group still owns the group's text, parentheses and dropped
        # terms included, so its chip removes the whole group.
        if node.kind == "or" or q.source[node.start:node.start + 1] == "(":
            kids[0].start, kids[0].end = node.start, node.end
        return kids[0]
    node.kids = kids
    return node


def _directive(t, q):
    v = t.value.strip().lower()
    if t.key in ("order", "sort"):
        v = _ORDER_ALIAS.get(v, v)
        if v in ORDERS or v == "relevance":
            q.order = v
        else:
            q.warnings.append(f"Can't sort by “{t.value}” (try {', '.join(ORDERS)}), so "
                              "the default order was used.")
    else:
        if v in ("asc", "ascending", "up"):
            q.direction = "asc"
        elif v in ("desc", "descending", "down"):
            q.direction = "desc"
        else:
            q.warnings.append(f"direction takes asc or desc, not “{t.value}”.")


def _eval(node, recs, cache):
    if node.kind == "term":
        v = cache.get(id(node))
        if v is None:
            v = cache[id(node)] = [node.fn(r) for r in recs]
        return v
    if node.kind == "not":
        return [None if x is None else not x for x in _eval(node.kids[0], recs, cache)]
    vs = [_eval(k, recs, cache) for k in node.kids]
    out = []
    if node.kind == "and":
        for row in zip(*vs):
            out.append(False if any(x is False for x in row) else
                       None if any(x is None for x in row) else True)
    else:
        for row in zip(*vs):
            out.append(True if any(x is True for x in row) else
                       None if any(x is None for x in row) else False)
    return out


def _phrase(node):
    if node.kind == "term":
        return node.phrase
    if node.kind == "not":
        inner = node.kids[0]
        return f"not {_phrase(inner)}" if inner.kind == "term" else f"not ({_phrase(inner)})"
    if node.kind == "and":
        return " · ".join(f"({_phrase(k)})" if k.kind == "or" else _phrase(k)
                          for k in node.kids)
    return " or ".join(f"({_phrase(k)})" if k.kind == "and" else _phrase(k)
                       for k in node.kids)


def describe(node):
    """The plain-English reading of a compiled tree, the line Scryfall prints under
    its results: one part per top-level condition."""
    if node is None:
        return []
    if node.kind == "and":
        return [_phrase(k) for k in node.kids]
    return [_phrase(node)]


def _relevance(words):
    whole = " ".join(words)

    def key(r):
        starts = sum(1 for w in words if not any(x.startswith(w) for x in r.words))
        not_whole = sum(1 for w in words if w not in r.words)
        return (r.norm != whole, not r.norm.startswith(whole), starts, not_whole, r.norm)
    return key


def _why(node, r):
    return node.reason(r) if callable(node.reason) else node.reason


class Result:
    def __init__(self):
        self.rows, self.groups, self.row_groups = [], [], []
        self.total = self.matched = self.copies = self.free = self.skipped = 0
        self.reasons, self.warnings, self.parts, self.chips = [], [], [], []
        self.summary = self.order = self.direction = self.order_label = ""
        self.group = ""
        self.query = None


def run(text, recs, ctx=None, *, order=None, direction=None, group=None):
    """Filter, sort and (optionally) group `recs` by the query `text`.

    `order`/`direction` from a form control win over `order:`/`direction:` in the
    text only when the text says nothing; the text is the more specific request."""
    ctx = ctx or Context()
    q = parse(text, ctx)
    res = Result()
    res.query = q
    res.total = len(recs)
    res.warnings = list(q.warnings)
    if q.tree is None:
        flags = [True] * len(recs)
    else:
        cache = {}
        flags = _eval(q.tree, recs, cache)
        # A term no card can answer is a statement about the DATA, not the cards:
        # say it once instead of letting the count read as a real zero.
        for node in q.terms:
            vals = cache.get(id(node))
            if vals and node.reason and all(v is None for v in vals):
                why = Counter(_why(node, r) for r in recs).most_common(1)[0][0]
                msg = f"“{node.phrase}” can't be answered for any card yet ({why})."
                if msg not in res.warnings:
                    res.warnings.append(msg)
        reasons = Counter()
        for i, f in enumerate(flags):
            if f is None:
                if not recs[i].enriched and not recs[i].basic:
                    reasons["no card data yet"] += 1      # a name-only row lacks it all
                    continue
                reasons.update({_why(node, recs[i]) for node in q.terms
                                if node.reason and cache.get(id(node)) is not None
                                and cache[id(node)][i] is None})
        res.reasons = reasons.most_common()
    rows = [r for r, f in zip(recs, flags) if f is True]
    res.skipped = sum(1 for f in flags if f is None)
    res.matched = len(rows)
    res.copies = sum(r.qty for r in rows)
    res.free = sum(r.free for r in rows if not r.basic)

    # Sort. Unknown values always sort last, whichever direction.
    o = q.order or order or ("relevance" if q.name_words else "name")
    o = _ORDER_ALIAS.get(o, o)
    if o not in ORDERS and o != "relevance":
        o = "name"
    if o == "relevance" and not q.name_words:
        o = "name"
    if o == "relevance":
        rows.sort(key=_relevance([w for p in q.name_words for w in p.split()]))
        res.direction = "asc"
        res.order_label = "Best match"
    else:
        key, default_dir, label = ORDERS[o]
        d = q.direction or direction or default_dir
        known = [r for r in rows if key(r) is not None]
        unknown = sorted((r for r in rows if key(r) is None), key=lambda r: r.norm)
        known.sort(key=lambda r: r.norm)
        known.sort(key=key, reverse=(d == "desc"))
        rows = known + unknown
        res.direction = d
        res.order_label = label
    res.order = o
    if group in GROUPS:
        gfn = GROUPS[group][1]
        keyed = [(gfn(r, ctx), r) for r in rows]
        keyed.sort(key=lambda kr: kr[0][0])               # stable: keeps the sort inside
        rows = [r for _g, r in keyed]
        res.row_groups = [g[1] for g, _r in keyed]
        seen = {}
        for (gk, label), r in keyed:
            g = seen.get(label)
            if g is None:
                g = seen[label] = {"label": label, "count": 0, "copies": 0, "free": 0}
                res.groups.append(g)
            g["count"] += 1
            g["copies"] += r.qty
            g["free"] += 0 if r.basic else r.free
        res.group = group
    res.rows = rows
    res.parts = describe(q.tree)
    res.summary = summary_line(res)
    res.chips = chips(q)
    return res


def summary_line(res):
    n = res.matched
    if res.query is None or res.query.tree is None:
        head = f"All {n:,} card{'s' if n != 1 else ''}"
    else:
        head = f"{n:,} card{'s' if n != 1 else ''} · " + " · ".join(res.parts)
    if res.skipped:
        why = ", ".join(f"{reason} ({k:,})" for reason, k in res.reasons[:3])
        head += f" · {res.skipped:,} skipped: {why}" if why else f" · {res.skipped:,} skipped"
    return head


def chips(q):
    """One chip per top-level part of the query, each with the query text that
    REMOVES it. An OR group is one chip labelled with its own source text."""
    if q.tree is None:
        return []
    parts = q.tree.kids if q.tree.kind == "and" else [q.tree]
    out = []
    for node in parts:
        label = q.source[node.start:node.end].strip()
        rest = (q.source[:node.start] + " " + q.source[node.end:])
        out.append({"label": label, "means": " · ".join(describe(node)),
                    "remove": re.sub(r"\s+", " ", rest).strip()})
    return out


def help_rows():
    """The help sheet, generated from KEYWORDS so it can only list what parses."""
    rows = []
    for kw in KEYWORDS:
        names = [kw.key] + [a for a in kw.aliases if re.fullmatch(r"[a-z]+", a)]
        rows.append({"key": kw.key, "names": names, "example": kw.example,
                     "means": kw.means, "support": kw.support})
    return rows


# --------------------------------------------------------------------------- #
# Plain-text rendering (the CLI and the skill)
# --------------------------------------------------------------------------- #
def text_report(res, *, limit=60, list_all=False):
    lines = [f"Query: {res.query.text or '(everything)'}",
             f"Means: {' · '.join(res.parts) if res.parts else 'every card'}",
             f"Matches: {res.matched:,} unique / {res.copies:,} copies"
             + (f" ({res.free:,} free)" if res.matched else "")
             + (f" · {res.skipped:,} skipped: "
                + ", ".join(f"{why} ({k:,})" for why, k in res.reasons) if res.skipped else ""),
             f"Order: {res.order_label} ({res.direction})"]
    for w in res.warnings:
        lines.append(f"[!] {w}")
    if "est. " in " ".join(res.parts):
        lines.append("[note] Prices are estimates from the export, not live quotes.")
    shown = res.rows if list_all else res.rows[:limit]
    for i, r in enumerate(shown):
        if res.row_groups and (i == 0 or res.row_groups[i] != res.row_groups[i - 1]):
            g = next(g for g in res.groups if g["label"] == res.row_groups[i])
            lines.append(f"\n== {g['label']} — {g['count']} cards / {g['copies']} copies "
                         f"({g['free']} free)")
        bits = []
        if r.mv is not None:
            bits.append(f"MV {_fmt(r.mv)}")
        if r.primary:
            bits.append(r.primary.title())
        free = "∞" if r.basic else str(r.free)
        decks = ", ".join(sorted(r.decks)) or "—"
        lines.append(f"  {r.qty:>3}x {r.name}" + (f"  ({', '.join(bits)})" if bits else "")
                     + f" · free {free} · decks: {decks}")
    if len(res.rows) > len(shown):
        lines.append(f"  … {len(res.rows) - len(shown):,} more (use --list to print all)")
    return "\n".join(lines)


def to_json(res, *, limit=None):
    rows = res.rows if limit is None else res.rows[:limit]
    return {
        "query": res.query.text, "means": res.parts, "matched": res.matched,
        "copies": res.copies, "free": res.free, "skipped": res.skipped,
        "skipped_why": dict(res.reasons), "warnings": res.warnings,
        "order": res.order, "direction": res.direction,
        "groups": res.groups,
        "cards": [{"name": r.name, "qty": r.qty,
                   "free": None if r.basic else r.free, "decks": sorted(r.decks),
                   "mv": r.mv, "type": r.primary or None,
                   "identity": None if r.identity is None else
                   "".join(c for c in COLORS if c in r.identity),
                   "price": r.price, "added": r.added or None}
                  for r in rows],
    }
