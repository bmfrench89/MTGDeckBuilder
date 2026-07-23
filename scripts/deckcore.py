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
                m = re.search(r"---\s*(.*?)\s*---", s)
                if m:
                    label = re.sub(r"\s*\(\d+\)\s*$", "", m.group(1)).strip()
                    cur = (label, [])
                    sections.append(cur)
                continue
            m = re.match(r"^(\d+)\s*[xX]?\s+(.*\S)$", s)
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


def load_attrs(path):
    """Optional name -> {type, mv} map to power the MV spread without the full CSV."""
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
            }
    return out


def _default_notes_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "data", "reference", "card_notes.csv")


def load_card_notes(path=None):
    """name(normalized) -> {"why": str, "alts": [names]}. The curated, editable
    knowledge base behind the click-a-card panel. First row per name wins."""
    path = path or _default_notes_path()
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = (r.get("Name") or r.get("Card") or "").strip()
            if not name:
                continue
            k = mtglib._norm(name)
            if k in out:
                continue
            alts = [a.strip() for a in re.split(r"[;|]", r.get("Alternatives") or "")
                    if a.strip()]
            out[k] = {"why": (r.get("Why") or "").strip(), "alts": alts}
    return out


def apply_attrs(enriched, attrs):
    """Overlay type/MV/colors from an attrs map onto enriched deck cards."""
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
    return n


_ROLE_LABEL = {
    "ramp": "Ramp / mana acceleration", "draw": "Card advantage",
    "removal": "Targeted removal", "wipe": "Board wipe", "counter": "Counterspell",
    "land": "Land", "creature": "Creature", "spell": "Instant / sorcery",
    "artifact": "Artifact", "enchantment": "Enchantment",
    "planeswalker": "Planeswalker", "other": "Deck card",
}
