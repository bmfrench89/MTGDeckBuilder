#!/usr/bin/env python3
"""Engine specs: what a deck is FOR, written before the draft and checked after it.

Deck-flow review bundle C (docs/spec-deck-flow-review.md). auto_build used to draft
100 cards from role quotas BEFORE anyone read the commander's engine, and a drafted card
stayed unless the read made a case against it. That is how Consecrated Sphinx sat in
the Ur-Dragon as draft filler. An engine spec turns that around:

  * a session reads the commander and the counted pool, then writes `<stem>.engine.json`:
    the engine cards, the 2-3 packages (enablers + payoffs), optional role aims, and
    keywords for the engine's text;
  * `auto_build.py --engine <spec>` seeds those cards before any quota and labels every
    other non-land card FILLER;
  * `engine_spec.py --deck … --audit` lists every non-land card that is neither engine
    nor package and has no KEEP reason, and exits 3 while any remain. No card is
    innocent until proven guilty.

File shape (version 1):

    {"version": 1, "commander": "Giada, Font of Hope",
     "engine":   ["Bishop of Wings", "Angelic Accord"],
     "packages": [{"name": "life on any turn", "enablers": ["Shattered Angel"],
                   "payoffs": ["Valkyrie Harbinger"]}],
     "aims":     {"draw": 12},
     "keywords": ["gain life", "each end step"],   # case-insensitive phrases
     "keep":     {"Sol Ring": "fast mana; the deck's curve tops at 7"}}

Keywords are case-insensitive phrases matched against oracle text. Pick specific ones
("noncombat damage", "whenever a dragon"): a broad word like "sacrifice" matches half the
pool and ranks nothing.

Sessions write it through this CLI, never by hand:

    python3 scripts/engine_spec.py --deck data/decks/<stem>.txt --init     # from notes
    python3 scripts/engine_spec.py --deck data/decks/<stem>.txt --keep "Card" "why"
    python3 scripts/engine_spec.py --deck data/decks/<stem>.txt --audit   # exit 3 on gaps

stdlib + mtglib only. A missing or broken spec reads as None: no spec, no seeding, and
the audit says so rather than passing.
"""
import argparse
import datetime
import json
import os
import re
import sys

import mtglib

VERSION = 1
LIST_KEYS = ("engine", "keywords")


def spec_path(deck_path):
    return os.path.splitext(deck_path)[0] + ".engine.json"


def load(path):
    """The spec at `path` (a .engine.json, or a deck .txt beside one), or None."""
    if path and path.endswith(".txt"):
        path = spec_path(path)
    try:
        with open(path, encoding="utf-8") as f:
            spec = json.load(f)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(spec, dict):
        return None
    spec.setdefault("version", VERSION)
    for k in LIST_KEYS:
        spec[k] = [x for x in (spec.get(k) or []) if isinstance(x, str) and x.strip()]
    spec["packages"] = [p for p in (spec.get("packages") or []) if isinstance(p, dict)]
    spec["aims"] = {k: int(v) for k, v in (spec.get("aims") or {}).items()
                    if isinstance(v, (int, float))}
    spec["keep"] = {k: v for k, v in (spec.get("keep") or {}).items()
                    if isinstance(k, str) and isinstance(v, str) and v.strip()}
    return spec


def save(path, spec):
    spec = dict(spec, version=VERSION)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(spec, f, ensure_ascii=False, indent=1)
        f.write("\n")


def core_names(spec):
    """Every card the spec names as engine or package (enabler or payoff), in order."""
    out = list((spec or {}).get("engine") or [])
    for p in (spec or {}).get("packages") or []:
        out += [x for x in (p.get("enablers") or []) + (p.get("payoffs") or [])
                if isinstance(x, str)]
    seen, uniq = set(), []
    for n in out:
        k = mtglib._norm(n)
        if k not in seen:
            seen.add(k)
            uniq.append(n)
    return uniq


def core_keys(spec):
    keys = set()
    for n in core_names(spec):
        keys |= mtglib.name_keys(n)
    return keys


def _section_cards(notes_text, heading_prefixes):
    """Bullet card lines under any `## ` heading starting with one of the prefixes.
    Only a `## ` heading ends a section: a `#` or `###` heading does not, so a list goes
    right before the next `## ` (the Captain America placement trap)."""
    out, on = [], False
    for line in (notes_text or "").splitlines():
        if line.startswith("## "):
            low = line.lower()
            on = any(low.startswith(p) for p in heading_prefixes)
            continue
        if on:
            m = re.match(r"^\s*-\s+(.+?)\s*$", line)
            if m:
                out.append(m.group(1))
    return out


def protected_engine_from_notes(notes_text):
    """The card lines under a notes file's protected list: `## Protected engine`, or
    `## Protected cards` (Dina's heading, found by the Fable review)."""
    return _section_cards(notes_text, ("## protected engine", "## protected cards"))


def earmarked_from_notes(notes_text):
    """Cards the notes set aside for ANOTHER deck (`## Earmarked for other decks`). The
    trades lane may offer these even though the notes name them."""
    return _section_cards(notes_text, ("## earmarked",))


# The audit wants a reason only where nothing else argues a card in (Fable review,
# 2026-10-15). 25-40 --keep calls per deck invited rubber stamps, which is anchoring with
# extra steps. A card this commander's field runs in FIELD_EXEMPT% or more of decks
# already has the field's case behind it, so the reasons go where the risk is.
FIELD_EXEMPT = 10


def audit(deck_path, spec=None, field=None):
    """(unexplained non-land cards, core cards missing from the deck). The commander,
    basics and lands are exempt: lands are judged by the mana pass. So is any card the
    commander's field (`field`, {normalized name: %}) runs in FIELD_EXEMPT% or more."""
    spec = spec if spec is not None else load(deck_path)
    text = open(deck_path, encoding="utf-8").read()
    commander = mtglib.deck_header(text, "Commander") or ""
    cmd_keys = mtglib.name_keys(commander) if commander else set()
    core = core_keys(spec)
    keep = set()
    for n in (spec or {}).get("keep") or {}:
        keep |= mtglib.name_keys(n)
    lands = _land_lines(text)
    unexplained, present = [], set()
    for c in mtglib.parse_deck(text):
        keys = mtglib.name_keys(c.name)
        present |= keys
        if keys & cmd_keys or mtglib.is_basic(c.name) or mtglib._norm(c.name) in lands:
            continue
        if keys & (core | keep):
            continue
        if field and max((field.get(k, 0) for k in keys), default=0) >= FIELD_EXEMPT:
            continue
        unexplained.append(c.name)
    missing = [n for n in core_names(spec) if not (mtglib.name_keys(n) & present)]
    return unexplained, missing


def _land_lines(text):
    """Normalized names filed under a Lands/Basics section of the deck file."""
    out, sec = set(), ""
    for line in text.splitlines():
        m = re.match(r"^#\s*-+\s*(.+?)\s*-+\s*$", line.strip())
        if m:
            sec = m.group(1).lower()
            continue
        m = mtglib._QTY_RE.match(line.strip()) if line.strip() else None
        if m and ("land" in sec or "basic" in sec):
            out.add(mtglib._norm(m.group(2)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write and audit a deck's engine spec "
                                             "(<stem>.engine.json).")
    ap.add_argument("--deck", required=True, help="data/decks/<stem>.txt")
    ap.add_argument("--init", action="store_true",
                    help="write a spec from the notes' '## Protected engine' list")
    ap.add_argument("--keep", action="append", default=[], nargs=2,
                    metavar=("CARD", "WHY"), help="record why a non-engine card stays")
    ap.add_argument("--keep-many", action="append", default=[], nargs="+",
                    metavar="WHY_THEN_CARDS",
                    help="one reason for several cards: --keep-many \"why\" \"Card A\" \"Card B\"")
    ap.add_argument("--audit", action="store_true",
                    help="list non-land cards with no engine/package/keep reason; exit 3")
    args = ap.parse_args(argv)
    path = spec_path(args.deck)
    if args.init:
        if os.path.exists(path):
            print(f"error: {path} exists; edit it with --keep", file=sys.stderr)
            return 2
        notes = args.deck[:-4] + ".notes.md" if args.deck.endswith(".txt") else ""
        try:
            engine = protected_engine_from_notes(open(notes, encoding="utf-8").read())
        except OSError:
            engine = []
        text = open(args.deck, encoding="utf-8").read()
        save(path, {"commander": mtglib.deck_header(text, "Commander") or "",
                    "written": datetime.date.today().isoformat(), "engine": engine,
                    "packages": [], "aims": {}, "keywords": [], "keep": {}})
        print(f"wrote {path}: {len(engine)} engine cards from the notes"
              + ("" if engine else " (the notes have no '## Protected engine' list)"))
    for group in args.keep_many:
        if len(group) < 2:
            print("error: --keep-many takes a reason, then one or more cards", file=sys.stderr)
            return 2
        args.keep += [[card, group[0]] for card in group[1:]]
    if args.keep:
        spec = load(path)
        if spec is None:
            print(f"error: no spec at {path}; run --init first", file=sys.stderr)
            return 2
        deck_keys = set()
        for c in mtglib.parse_deck(open(args.deck, encoding="utf-8").read()):
            deck_keys |= mtglib.name_keys(c.name)
        for card, why in args.keep:
            if not why.strip():
                print(f"error: a keep needs its reason: {card}", file=sys.stderr)
                return 2
            if not (mtglib.name_keys(card) & deck_keys):
                print(f"   not in the deck, not kept: {card}")
                continue
            spec["keep"][card] = why.strip()
            print(f"   kept  {card}: {why.strip()}")
        save(path, spec)
    if args.audit:
        spec = load(path)
        if spec is None:
            print(f"no engine spec at {path} — nothing to audit against")
            return 3
        field = None
        try:                              # the field is evidence the CLI fetches; audit()
            import deck_fit               # itself stays pure and takes it as a parameter
            text = open(args.deck, encoding="utf-8").read()
            field = deck_fit.load_field(mtglib.deck_header(text, "Commander") or "")
        except Exception:
            field = None
        unexplained, missing = audit(args.deck, spec, field)
        for n in missing:
            print(f"   engine card not in the deck: {n}")
        for n in unexplained:
            print(f"   no reason to keep: {n}")
        print(f"{len(unexplained)} card(s) without a reason · {len(missing)} engine card(s) "
              f"missing")
        return 3 if unexplained else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
