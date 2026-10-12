#!/usr/bin/env python3
"""Card intake: turn a pasted list (or a CSV export) into verified card names, then
write them either as a dated batch in `owned_additions.txt` (new cards for the
collection) or as a deck list (a deck the player built outside the app).

docs/spec-card-intake.md §3. The flow is **parse → resolve → preview → write**, and the
preview is the point: each line is shown as ✓ resolved, ? "did you mean …", or ✗ not
found, and only resolved lines are ever written. Nothing here guesses a card.

    parse_text(text)        -> rows (one per input line; an `error` on the bad ones)
    resolve(rows, verify)   -> entries (one per distinct card, merged across lines)
    batch_block(entries)    -> the dated block appended to owned_additions.txt
    reconcile_plan(...)     -> batch rows a new export now covers (retire on one tap)
    apply_retire(path, plan)-> comment those rows out, dated, never deleted
    upload_looks_partial()  -> the Upload guard's "is this really a full export?"

Network goes through ONE injectable call, `carddb.verify_cards` (Scryfall's exact
batch, then a fuzzy retry). When Scryfall can't be reached, a name the app already
knows (the collection, the attrs snapshot) still resolves, labelled `local`, and every
other line comes back `offline`. That's a line to retry, never one to write.

Stdlib-only like the rest of scripts/.

    python3 scripts/intake.py list.txt                     # parse + resolve, preview
    python3 scripts/intake.py list.txt --verified v.json   # resolve from a runner's
                                                           # carddb --verify --json
    python3 scripts/intake.py list.txt --verified v.json --write \\
        --label "the player's card orders"                 # append the dated batch
"""
import argparse
import datetime
import json
import os
import re
import sys
import tempfile
import unicodedata

import deckcore
import mtglib

MAX_LINE_QTY = 99          # per input line, same bound as the Collection page's Add
MAX_ENTRY_QTY = 999        # after merging lines; a guard against a pasted typo

# Section words that exporters print on a line of their own (Arena, Moxfield's MTGA
# copy, MTGO's SIDEBOARD:). They set the section for the lines below and are never
# card names.
_SECTION_WORDS = {
    "commander": "commander", "commanders": "commander", "companion": "companion",
    "deck": "main", "main": "main", "mainboard": "main", "main deck": "main",
    "maindeck": "main",
    "sideboard": "sideboard", "side board": "sideboard", "maybeboard": "maybeboard",
    "maybe": "maybeboard", "considering": "maybeboard", "tokens": "tokens",
    "about": "about",
}
# Sections that hold cards which are NOT in the deck. A collection batch takes every
# line (you still own your sideboard); a deck import leaves these out and says so.
OUTSIDE_DECK = {"sideboard", "maybeboard", "tokens", "about"}

_LEAD_QTY = re.compile(r"^(\d+)\s*[xX×]?\s+(.+)$")
_TRAIL_QTY = re.compile(r"^(.+?)\s+(?:[xX×]\s*(\d+)|(\d+)\s*[xX×])$")
_STAR_MARK = re.compile(r"\s*\*([A-Za-z]{1,8})\*$")            # *F* *E* *CMDR*
_CARET_TAG = re.compile(r"\s*\^[^^]*\^$")                       # Archidekt ^Have,#hex^
_BRACKET = re.compile(r"\s*\[([^\]]*)\]$")                      # [C21]  [Commander{top}]
# A trailing printing: `(C21) 263`, `(PLST) DOM-130`, `(SLD) 1234★`. The set code has no
# spaces, which is what keeps a real name like "B.F.M. (Big Furry Monster)" whole.
_SET_NUM = re.compile(r"\s*\(([A-Za-z0-9]{2,6})\)(?:\s+[A-Za-z0-9★†-]{1,12})?$")
_FINISH = re.compile(
    r"\s*(?:\(|\b)(?:foil|etched|non-?foil|nm|lp|mp|hp|dmg|mint|near mint|"
    r"lightly played|moderately played|heavily played|damaged)\)?$", re.IGNORECASE)


def _clean_name(rest):
    """Strip the markers exporters hang off the end of a card name. Returns
    (name, flags) where flags may hold "commander" or "outside" (Archidekt's
    Maybeboard / Sideboard categories). Loops because the markers stack in any
    order: `Sol Ring (C21) 263 *F*`, `Atraxa (2X2) 190 [Commander{top}]`."""
    flags = set()
    name = rest.strip()
    while True:
        before = name
        m = _STAR_MARK.search(name)
        if m and m.start() > 0:
            if m.group(1).upper() in ("CMDR", "CMD"):
                flags.add("commander")
            name = name[:m.start()]
        m = _CARET_TAG.search(name)
        if m and m.start() > 0:
            name = name[:m.start()]
        m = _BRACKET.search(name)
        if m and m.start() > 0:
            cat = m.group(1).lower()
            if "commander" in cat:
                flags.add("commander")
            if any(w in cat for w in ("maybeboard", "sideboard", "nodeck")):
                flags.add("outside")
            name = name[:m.start()]
        m = _SET_NUM.search(name)
        if m and m.start() > 0:
            name = name[:m.start()]
        m = _FINISH.search(name)
        if m and m.start() > 0 and name[:m.start()].strip():
            name = name[:m.start()]
        name = name.strip()
        if name == before:
            break
    name = re.sub(r"\s+", " ", name.replace("\\!", "!").replace("\\'", "'"))
    return name, flags


def parse_text(text):
    """Parse a pasted list or a CSV export into rows, one per card line:

        {"line": n | None, "raw": str, "qty": int, "name": str,
         "section": "" | "commander" | "main" | "sideboard" | …,
         "commander": bool, "error": ""}

    `error` is set (and the row is never written) for a quantity outside 1..99 or a
    line that is all markers. A CSV goes through the collection loader's own alias
    table, so every export it already reads (ManaBox, Moxfield, TCGplayer, Sorted,
    Archidekt) works here too. Comment lines (`#`, `//`) are skipped, and our own deck
    files paste cleanly: their `# --- Commander ---` header marks the commander."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    if mtglib.detect_format(text) == "csv":
        rows = []
        for c in mtglib.parse_collection(text):
            err = "" if 1 <= c.quantity <= MAX_ENTRY_QTY else \
                f"quantity must be 1-{MAX_ENTRY_QTY} (got {c.quantity})"
            rows.append({"line": None, "raw": c.name, "qty": c.quantity,
                         "name": c.name.strip(), "section": "", "commander": False,
                         "error": err})
        return rows
    rows, section = [], ""
    for n, raw in enumerate(text.split("\n"), 1):
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#"):
            label = deckcore.section_label(s)
            if label is not None:
                low = label.lower()
                section = ("commander" if low.startswith("commander") else
                           _SECTION_WORDS.get(low, "main"))
            continue
        if s.startswith("//"):
            word = s[2:].strip().rstrip(":").lower()
            if word in _SECTION_WORDS:
                section = _SECTION_WORDS[word]
            continue
        word = s.rstrip(":").strip().lower()
        if word in _SECTION_WORDS:
            section = _SECTION_WORDS[word]
            continue
        qty, rest = 1, s
        m = _LEAD_QTY.match(s)
        if m:
            qty, rest = int(m.group(1)), m.group(2)
        else:
            m = _TRAIL_QTY.match(s)
            if m:
                rest, qty = m.group(1), int(m.group(2) or m.group(3))
        name, flags = _clean_name(rest)
        row = {"line": n, "raw": raw.strip(), "qty": qty, "name": name,
               "section": "maybeboard" if "outside" in flags else section,
               "commander": "commander" in flags or section == "commander",
               "error": ""}
        if not name:
            row["error"] = "no card name on this line"
        elif not 1 <= qty <= MAX_LINE_QTY:
            row["error"] = f"quantity must be 1-{MAX_LINE_QTY} (got {qty})"
        elif any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name):
            row["error"] = "a card name can't contain control characters"
        rows.append(row)
    return rows


def _fold(name):
    """NFKD, drop combining marks, casefold, alphanumerics only — the same fold
    carddb uses to accept a pure spelling repair and refuse a substitution."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return "".join(ch for ch in s.casefold() if ch.isalnum())


def same_card(typed, canonical):
    """True when `typed` names `canonical` up to spelling noise: the whole name, or
    any one face of a split / double-faced / adventure card ("Insectile Aberration"
    names "Delver of Secrets // Insectile Aberration")."""
    t = _fold(typed)
    if not t:
        return False
    if t == _fold(canonical):
        return True
    return any(t == _fold(face) for face in canonical.split(" // "))


def known_names(cards=(), extra_names=()):
    """{fold: canonical} for names the app already trusts: collection rows and any
    extra canonical names (the attrs snapshot). The OFFLINE fallback, so a name the
    collection already carries still resolves when Scryfall can't be reached."""
    out = {}
    for name in list(extra_names) + [c.name for c in cards]:
        if not name:
            continue
        out.setdefault(_fold(name), name)
        front = mtglib.front_face(name)
        if front != name:
            out.setdefault(_fold(front), name)
    return out


# "A deck can have any number of cards named Relentless Rats." / "up to seven" — the
# printed exceptions to singleton, read from the verified oracle text, never a list.
_ANY_NUMBER = re.compile(r"deck can have (?:any number of|up to \w+) cards named",
                         re.IGNORECASE)


def _price(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def resolve(rows, verify=None, known=None):
    """Resolve parsed rows to cards. Returns one entry per distinct card (lines that
    spell the same card are merged), in first-seen order:

        {"name": canonical or typed, "typed": [typed spellings], "qty": int,
         "lines": [line numbers], "status": "ok" | "suggest" | "missing" |
         "offline" | "basic" | "error", "suggest": canonical (for "suggest"),
         "price": float | None (estimate, one printing), "type_line": str,
         "identity": "W U" (Scryfall's colour identity), "source": str,
         "reason": str, "commander": bool, "section": str}

    `verify` defaults to `carddb.verify_cards` and is the ONLY network call. A
    "suggest" entry (Scryfall's fuzzy match landed on a different spelling) is
    written only when the player ticks it. "offline" means we could not ask; it is
    never a verdict on the card."""
    if verify is None:
        import carddb
        verify = carddb.verify_cards
    known = known or {}
    groups, order = {}, []
    errors = []
    for r in rows:
        if r.get("error"):
            errors.append({"name": r["name"] or r["raw"], "typed": [r["raw"]],
                           "qty": r["qty"], "lines": [r["line"]], "status": "error",
                           "suggest": "", "price": None, "type_line": "",
                           "identity": "", "source": "", "reason": r["error"],
                           "commander": False, "section": r.get("section", "")})
            continue
        k = mtglib._norm(r["name"])
        g = groups.get(k)
        if g is None:
            g = groups[k] = {"typed": r["name"], "qty": 0, "lines": [],
                             "commander": False, "section": r.get("section", "")}
            order.append(k)
        g["qty"] += r["qty"]
        g["lines"].append(r["line"])
        g["commander"] = g["commander"] or bool(r.get("commander"))
        # A card listed both in the deck and in the sideboard counts as in the deck.
        if g["section"] in OUTSIDE_DECK and r.get("section") not in OUTSIDE_DECK:
            g["section"] = r.get("section", "")

    to_ask = [k for k in order if not mtglib.is_basic(groups[k]["typed"])]
    answers = {}
    if to_ask:
        for k, row in zip(to_ask, verify([groups[k]["typed"] for k in to_ask])):
            answers[k] = row

    merged, out = {}, []
    for k in order:
        g = groups[k]
        typed = g["typed"]
        e = {"name": typed, "typed": [typed], "qty": g["qty"], "lines": g["lines"],
             "status": "", "suggest": "", "price": None, "type_line": "",
             "identity": "", "source": "", "reason": "", "commander": g["commander"],
             "section": g["section"], "any_number": False}
        if mtglib.is_basic(typed):
            e.update(status="basic", source="rule",
                     reason="basic lands are always owned and never tracked")
        else:
            a = answers.get(k) or {}
            if a.get("found"):
                canon = a.get("name") or typed
                e.update(price=_price(a.get("price_usd")),
                         any_number=bool(_ANY_NUMBER.search(a.get("oracle_text") or "")),
                         type_line=a.get("type_line") or "",
                         identity=a.get("color_identity") or "",
                         source=a.get("source") or "scryfall")
                if same_card(typed, canon):
                    e.update(status="ok", name=canon)
                else:
                    e.update(status="suggest", suggest=canon,
                             reason=f"Scryfall's closest match is {canon}")
            else:
                reason = a.get("reason") or "not checked"
                local = known.get(_fold(typed))
                if local and reason.startswith("network"):
                    e.update(status="ok", name=local, source="local",
                             reason="already in your collection (offline, no price)")
                elif reason.startswith("network"):
                    e.update(status="offline",
                             reason="Scryfall couldn't be reached — try again")
                else:
                    e.update(status="missing", reason="no card by this name")
        # Merge two spellings of one card (`Delver of Secrets` + its back face).
        mk = mtglib._norm(e["name"]) if e["status"] == "ok" else None
        if mk and mk in merged:
            m = merged[mk]
            m["qty"] += e["qty"]
            m["lines"] += e["lines"]
            m["typed"] += e["typed"]
            m["commander"] = m["commander"] or e["commander"]
            continue
        if mk:
            merged[mk] = e
        out.append(e)
    for e in out:
        if e["qty"] > MAX_ENTRY_QTY:
            e.update(status="error",
                     reason=f"{e['qty']} copies across the list — over {MAX_ENTRY_QTY}")
    return out + errors


def summary(entries):
    """Counts the preview shows, and the confirm writes exactly the `ok` part of."""
    ok = [e for e in entries if e["status"] == "ok"]
    priced = [e for e in ok if e["price"] is not None]
    return {
        "ok_distinct": len(ok), "ok_copies": sum(e["qty"] for e in ok),
        "suggest": sum(1 for e in entries if e["status"] == "suggest"),
        "missing": sum(1 for e in entries if e["status"] in ("missing", "error")),
        "offline": sum(1 for e in entries if e["status"] == "offline"),
        "basics": sum(e["qty"] for e in entries if e["status"] == "basic"),
        "value": round(sum(e["price"] * e["qty"] for e in priced), 2),
        "priced": len(priced),
    }


def accepted(entries, take_suggestions=()):
    """[(qty, canonical)] the confirm step writes: every `ok` entry, plus each
    `suggest` entry whose index the player ticked (its suggested name, never the
    typed one). Merged by canonical name so a ticked suggestion that turns out to be
    a card already on the list adds to that line instead of duplicating it."""
    take = {int(i) for i in take_suggestions}
    rows, at = [], {}
    for i, e in enumerate(entries):
        if e["status"] == "ok":
            name = e["name"]
        elif e["status"] == "suggest" and i in take:
            name = e["suggest"]
        else:
            continue
        k = mtglib._norm(name)
        if k in at:
            rows[at[k]][0] += e["qty"]
        else:
            at[k] = len(rows)
            rows.append([e["qty"], name])
    return [(q, n) for q, n in rows]


# --------------------------------------------------------------------------- #
# The dated batch block (owned_additions.txt)
# --------------------------------------------------------------------------- #
BATCH_RE = re.compile(r"^#\s*---\s*Batch\s+(\d{4}-\d{2}-\d{2})\b")


def _safe_line(name):
    return bool(name) and not name.lstrip().startswith("#") and \
        not any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name)


BATCH_NOTE = ("# Added in the app. New copies on top of the export; when a future export",
              "# carries them, the upload offers to retire these rows",
              "# (docs/spec-card-intake.md §3).")


def batch_block(rows, label, date=None, note=BATCH_NOTE):
    """The block appended to owned_additions.txt. Names and quantities ONLY: no
    prices, sellers, order numbers or file names (CLAUDE.md, the privacy line)."""
    date = date or datetime.date.today().isoformat()
    rows = [(q, n) for q, n in rows if _safe_line(n) and q > 0]
    copies = sum(q for q, _ in rows)
    label = re.sub(r"[\x00-\x1f\x7f]", " ", label or "pasted list").strip()
    lines = [f"# --- Batch {date} · {label} · {copies} cards ({len(rows)} distinct) ---"]
    lines += [ln if ln.startswith("#") else f"# {ln}" for ln in note]
    lines += [f"{q} {n}" for q, n in rows]
    return "\n".join(lines) + "\n", copies, len(rows)


def append_batch(path, rows, label, date=None, note=BATCH_NOTE):
    """Append one dated block. Returns (copies, distinct). Never rewrites what is
    already in the file — the header comments and older batches stay byte-identical."""
    block, copies, distinct = batch_block(rows, label, date, note)
    if not distinct:
        return 0, 0
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        if not text:
            f.write("# Player-confirmed ownership not in the export yet.\n")
        elif not text.endswith("\n"):
            f.write("\n")
        f.write("\n" + block)
    return copies, distinct


def addition_rows(text):
    """Every card row in owned_additions.txt with where it sits and when it arrived:
    [{"idx": line index, "qty", "name", "date"}]. A row's date is its batch header's
    (`# --- Batch 2026-10-12 · …`) or the nearest dated comment above it
    (`# 2026-10-07: …`); "" when nothing above it is dated."""
    out, date = [], ""
    for i, raw in enumerate((text or "").split("\n")):
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#"):
            # The loader's own date rule (mtglib.parse_additions), so the review
            # and the arrivals view can never disagree about when a row arrived.
            m = mtglib.ADDITIONS_DATE_RE.match(s)
            if m:
                date = m.group(1)
            elif re.match(r"^#\s*---", s):
                date = ""
            continue
        parsed = mtglib._parse_namelist(s)
        if parsed:
            out.append({"idx": i, "qty": parsed[0].quantity, "name": parsed[0].name,
                        "date": date})
    return out


# --------------------------------------------------------------------------- #
# Reconcile on upload — retire batch rows a new export now carries
# --------------------------------------------------------------------------- #
def _qty_by_card(cards):
    out = {}
    for c in cards:
        k = mtglib._norm(mtglib.front_face(c.name))
        out[k] = out.get(k, 0) + c.quantity
    return out


def reconcile_plan(old_cards, new_cards, additions_text):
    """Which addition rows the new export now covers. A row is covered when the new
    export carries more copies than the previous one did: `new − old` copies are
    handed to that card's rows oldest-first, so a row is fully covered when
    *new ≥ old + row qty* and partly covered (keeping its remainder) below that.
    Basics are skipped (never tracked). Pure: nothing is written here.

    -> [{"idx", "name", "qty", "covered"}] in file order."""
    old_q, new_q = _qty_by_card(old_cards), _qty_by_card(new_cards)
    left = {}
    plan = []
    for r in addition_rows(additions_text):
        if mtglib.is_basic(r["name"]):
            continue
        k = mtglib._norm(mtglib.front_face(r["name"]))
        if k not in left:
            left[k] = max(0, new_q.get(k, 0) - old_q.get(k, 0))
        take = min(left[k], r["qty"])
        if take > 0:
            left[k] -= take
            plan.append({"idx": r["idx"], "name": r["name"], "qty": r["qty"],
                         "covered": take})
    return plan


def apply_retire(path, plan, date=None):
    """Comment out the covered rows, dated — never delete them. A partly covered row
    keeps its remainder on the next line. Each planned row is re-checked against the
    file first (same line, same qty, same name), so a file edited since the plan was
    made is never rewritten blind; a mismatched row is skipped and counted.

    Atomic (temp file + os.replace). -> (retired copies, skipped rows)."""
    date = date or datetime.date.today().isoformat()
    lines = open(path, encoding="utf-8").read().split("\n")
    retired = skipped = 0
    for p in sorted(plan, key=lambda x: -x["idx"]):
        i = p["idx"]
        row = mtglib._parse_namelist(lines[i].strip()) if 0 <= i < len(lines) else []
        if (not row or row[0].quantity != p["qty"]
                or mtglib._norm(row[0].name) != mtglib._norm(p["name"])
                or not 0 < p["covered"] <= p["qty"]):
            skipped += 1
            continue
        if p["covered"] == p["qty"]:
            lines[i:i + 1] = [f"# retired {date} (in export): {p['qty']} {p['name']}"]
        else:
            lines[i:i + 1] = [f"# retired {date} (in export): {p['covered']} of "
                              f"{p['qty']} {p['name']}",
                              f"{p['qty'] - p['covered']} {p['name']}"]
        retired += p["covered"]
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".additions-", suffix=".tmp", dir=d)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    os.replace(tmp, path)
    return retired, skipped


# --------------------------------------------------------------------------- #
# Upload guard
# --------------------------------------------------------------------------- #
def upload_looks_partial(current_cards, new_cards):
    """(partial?, facts) — does an upload headed for "replace my whole collection"
    look like a batch of new cards instead? Partial when the file has fewer than
    half the current unique cards, or most current cards are missing from it.
    An empty current collection (a first upload) is never partial."""
    cur = {mtglib._norm(mtglib.front_face(c.name)) for c in current_cards
           if not mtglib.is_basic(c.name)}
    new = {mtglib._norm(mtglib.front_face(c.name)) for c in new_cards
           if not mtglib.is_basic(c.name)}
    facts = {"file_unique": len(new), "file_copies": sum(c.quantity for c in new_cards),
             "current_unique": len(cur),
             "current_copies": sum(c.quantity for c in current_cards),
             "missing": len(cur - new)}
    if not cur:
        return False, facts
    partial = len(new) < 0.5 * len(cur) or (len(cur - new) > 0.5 * len(cur))
    return partial, facts


# --------------------------------------------------------------------------- #
# Deck import — a list the player built outside the app
# --------------------------------------------------------------------------- #
def _types_of(name, entry, idx):
    card = mtglib.lookup(idx, name) if idx else None
    if card is not None and card.types:
        return card.types
    tl = (entry.get("type_line") or "").split(" // ")[0]
    return [tl] if tl else None


def deck_text(cards, commander, title="", colors="", source="", idx=None,
              header_lines=None):
    """A deck file in the repo's format: `# Key: value` headers, then EDHREC-style
    type sections (deckcore.type_bucket). `cards` is [(qty, name, entry)]; types
    come from the collection first and Scryfall's type line second, and a card
    neither can type goes to an explicit Unsorted section, never a guessed one.
    `header_lines`, when given, replaces the generated headers verbatim (a replace
    of an existing deck keeps its own Title / Archetype / Notes)."""
    if header_lines is None:
        header_lines = [f"# Title: {title or commander}", f"# Commander: {commander}"]
        if colors:
            header_lines.append(f"# Colors: {colors}")
        header_lines.append("# Archetype: ")
        if source:
            header_lines.append(f"# Source: {source}")
    buckets = {s: [] for s in deckcore.TYPE_SECTION_ORDER}
    unsorted = []
    cmd_row = None
    for qty, name, entry in cards:
        if mtglib._norm(name) == mtglib._norm(commander):
            cmd_row = (qty, name)
            continue
        sec = deckcore.type_bucket(name, _types_of(name, entry or {}, idx))
        (buckets[sec] if sec else unsorted).append((qty, name))
    out = list(header_lines)
    out += ["", "# --- Commander ---", f"{cmd_row[0] if cmd_row else 1} {commander}"]
    for sec in deckcore.TYPE_SECTION_ORDER:
        if buckets[sec]:
            out += ["", f"# --- {sec} ---"]
            out += [f"{q} {n}" for q, n in sorted(buckets[sec], key=lambda r: r[1].lower())]
    if unsorted:
        out += ["", "# --- Unsorted (type unknown — enrich and re-run deck_sections) ---"]
        out += [f"{q} {n}" for q, n in unsorted]
    return "\n".join(out) + "\n"


def deck_report(entries, commander, coll_idx, identity=None, committed=None):
    """What the deck-import preview shows before anything is written: card count,
    singleton problems, off-identity cards, and the ownership check.

    `committed` is {name key: {other deck label: qty}} (from deck_conflicts.scan,
    keyed by `mtglib.name_keys`), so a card the collection owns once and another
    deck already sleeves is reported as SHARED — the same badge the dashboard uses,
    and never a blocker (grounding rule #8). Basic lands are always owned (rule #9)."""
    rows = [e for e in entries if e["status"] in ("ok", "basic")
            and e.get("section") not in OUTSIDE_DECK]
    total = sum(e["qty"] for e in rows)
    cmd_key = mtglib._norm(commander or "")
    has_cmd = any(mtglib._norm(e["name"]) == cmd_key for e in rows)
    if commander and not has_cmd:
        total += 1                       # the commander line is added on write
    singles = [e["name"] for e in rows
               if e["status"] == "ok" and e["qty"] > 1 and not e.get("any_number")]
    off, unowned, shared = [], [], []
    for e in rows:
        if e["status"] == "basic":
            continue
        ident = set(re.findall(r"[WUBRG]", (e.get("identity") or "").upper()))
        if not ident:
            card = mtglib.lookup(coll_idx, e["name"])
            ident = set(card.identity or ()) if card is not None else set()
        if identity is not None and ident and not ident <= identity:
            off.append(e["name"])
        card = mtglib.lookup(coll_idx, e["name"])
        owned = card.quantity if card is not None else 0
        if owned < e["qty"]:
            unowned.append({"name": e["name"], "need": e["qty"], "own": owned})
        elif committed:
            others = next((committed[k] for k in mtglib.name_keys(e["name"])
                           if k in committed), None) or {}
            if others and owned < e["qty"] + sum(others.values()):
                shared.append({"name": e["name"], "decks": sorted(others), "own": owned})
    left_out = [e["name"] for e in entries
                if e["status"] in ("ok", "basic") and e.get("section") in OUTSIDE_DECK]
    return {"total": total, "singleton": singles, "off_identity": off,
            "unowned": unowned, "shared": shared, "left_out": left_out,
            "has_commander_line": has_cmd}


# --------------------------------------------------------------------------- #
# CLI — the session path (spec §2): parse, resolve against the runner's verified
# names, and append the dated block.
# --------------------------------------------------------------------------- #
def _verify_from_json(path):
    """A `verify` that answers from a saved `carddb.py --verify --json` result (the
    deck-verify runner's output), for a sandbox with no network."""
    data = json.load(open(path, encoding="utf-8"))
    by = {}
    for r in data:
        for n in (r.get("requested"), r.get("name"), r.get("resolved_from")):
            if n:
                by.setdefault(_fold(n), r)

    def verify(names):
        out = []
        for n in names:
            r = by.get(_fold(n))
            if r and r.get("found", True) and r.get("name"):
                out.append(dict(r, found=True))
            else:
                out.append({"found": False, "reason": "not in the verified file"})
        return out
    return verify


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="a pasted list (.txt) or a CSV export of new cards")
    ap.add_argument("--verified", help="resolve from a saved carddb --verify --json file "
                                       "(the sandbox has no Scryfall)")
    ap.add_argument("--write", action="store_true",
                    help="append the dated batch to owned_additions.txt")
    ap.add_argument("--additions", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "collection",
        "owned_additions.txt"))
    ap.add_argument("--label", default="pasted list",
                    help="what the batch is (no order numbers or sellers)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rows = parse_text(open(a.file, encoding="utf-8").read())
    verify = _verify_from_json(a.verified) if a.verified else None
    entries = resolve(rows, verify=verify)
    s = summary(entries)
    if a.json:
        print(json.dumps({"summary": s, "entries": entries}, indent=1, ensure_ascii=False))
    else:
        mark = {"ok": "✓", "suggest": "?", "missing": "✗", "error": "✗",
                "offline": "…", "basic": "–"}
        for e in entries:
            extra = f"  → did you mean {e['suggest']}?" if e["suggest"] else (
                f"  ({e['reason']})" if e["status"] != "ok" and e["reason"] else "")
            print(f"{mark.get(e['status'], ' ')} {e['qty']:>3} {e['name']}{extra}")
        print(f"\n{s['ok_copies']} cards ({s['ok_distinct']} distinct) resolved · "
              f"{s['suggest']} to confirm · {s['missing']} not found · "
              f"{s['offline']} unchecked · {s['basics']} basic land(s) left out")
    if a.write:
        if s["suggest"] or s["missing"] or s["offline"]:
            print("Not written: fix or confirm the lines above first.", file=sys.stderr)
            return 3
        copies, distinct = append_batch(a.additions, accepted(entries), a.label)
        print(f"Appended a batch of {copies} cards ({distinct} distinct) to {a.additions}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
