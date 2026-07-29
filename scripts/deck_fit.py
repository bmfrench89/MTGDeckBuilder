#!/usr/bin/env python3
"""Score how well a single card fits a specific deck, and suggest stronger options
for its slot. Powers the click-a-card panel's "how it fits + fit score + upgrades".

Everything here is a HEURISTIC built from countable signals — color identity vs the
commander, the card's role vs the deck's actual ramp/removal/draw ratios, its curve
position, whether it's a recognized format staple, and tribal/theme match. It never
invents oracle text; where data is missing (name-only lists) it says so and stays
neutral rather than guessing. Treat the number as a guide, not a verdict.
"""
import csv
import os
import re

import mtglib

REF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "data", "reference")

# Soft target counts per role (matches deck_stats.TARGETS, plus counters/lands).
FIT_TARGETS = {
    "ramp": (10, 12), "draw": (10, 12), "removal": (8, 10),
    "wipe": (3, 5), "counter": (3, 8), "land": (36, 38),
}
_ROLE_PRIORITY = ["ramp", "draw", "removal", "wipe", "counter", "land"]

# The player already grouped the deck by function via `# --- Label ---` headers.
# When we can't read a card's type (name-only list), that grouping is the best
# signal for what job the card is doing.
SECTION_ROLE_HINTS = [
    ("board wipe", "wipe"), ("sweeper", "wipe"), ("wrath", "wipe"), ("wipe", "wipe"),
    ("ramp", "ramp"), ("rock", "ramp"), ("accel", "ramp"), ("mana base", "land"),
    ("manabase", "land"), ("removal", "removal"), ("interaction", "removal"),
    ("spot", "removal"), ("card advantage", "draw"), ("card draw", "draw"),
    ("draw", "draw"), ("counter", "counter"), ("land", "land"),
    ("creature", "creature"), ("engine", "creature"), ("threat", "creature"),
    ("beater", "creature"), ("finisher", "creature"),
]


def section_role(label):
    low = (label or "").lower()
    for key, role in SECTION_ROLE_HINTS:
        if key in low:
            return role
    return None


def load_role_staples(path=None):
    """role -> list of {name, colors(set of WUBRG letters the card needs)}."""
    path = path or os.path.join(REF_DIR, "role_staples.csv")
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        lines = [ln for ln in f if not ln.lstrip().startswith("#")]
    if lines:
        for r in csv.DictReader(lines):
            role = (r.get("Role") or "").strip().lower()
            card = (r.get("Card") or "").strip()
            if not role or not card:
                continue
            colors = set((r.get("Colors") or "").strip().upper()) & set("WUBRG")
            out.setdefault(role, []).append({"name": card, "colors": colors})
    return out


def load_field(commander, coll_index=None):
    """EDHREC inclusion map for a commander ({normalized name: %}) — the "what does the
    field actually run here" signal for `_staple_component`. Network/EDHREC failures are
    non-fatal: an empty map just means scoring falls back to the curated lists."""
    if not commander:
        return {}
    try:
        import edhrec
        return edhrec.inclusion_map(commander, coll_index)
    except Exception:
        return {}


def load_synergy(commander, coll_index=None):
    """EDHREC synergy map ({normalized name: synergy}) — "how much MORE this commander
    plays it than the format". Same graceful-degradation contract as load_field."""
    if not commander:
        return {}
    try:
        import edhrec
        return edhrec.synergy_map(commander, coll_index)
    except Exception:
        return {}


def deck_context(deck_path, enriched, commander="", field=None, synergy=None):
    """Identity (set of WUBRG), archetype keywords, and dominant tribe (if the list
    carries subtypes). Color identity comes from the deck's `# Colors:` header.
    `field` is an optional EDHREC inclusion map (see load_field)."""
    ident, archetype, theme = set(), [], ""
    try:
        with open(deck_path, encoding="utf-8") as f:
            head = f.read()
        m = re.search(r"^#\s*Colors?\s*:\s*(.+)$", head, re.MULTILINE | re.IGNORECASE)
        if m:
            ident = set(re.sub(r"[^WUBRG]", "", m.group(1).upper()))
        a = re.search(r"^#\s*Archetype\s*:\s*(.+)$", head, re.MULTILINE | re.IGNORECASE)
        if a:
            archetype = [w for w in re.split(r"[,\s/]+", a.group(1).lower().strip()) if w]
        t = re.search(r"^#\s*Theme\s*:\s*(.+)$", head, re.MULTILINE | re.IGNORECASE)
        if t:
            theme = t.group(1).strip().lower()
    except OSError:
        pass
    if not ident:  # fall back to the union of known card identities
        for c in enriched:
            ident |= set(c.identity or [])
    # dominant creature subtype, only if the list actually carries subtypes
    from collections import Counter
    subs = Counter()
    for c in enriched:
        for s in (c.subtypes or []):
            subs[s.lower()] += c.quantity
    tribal = None
    if subs:
        name, n = subs.most_common(1)[0]
        if n >= 5:
            tribal = name
    return {"identity": ident, "archetype": archetype, "theme": theme,
            "tribal": tribal, "commander": commander, "field": field or {},
            "synergy": synergy or {}}


def primary_role(card):
    roles = mtglib.classify(card)
    for r in _ROLE_PRIORITY:
        if r in roles:
            return r
    if "creature" in roles:
        return "creature"
    return next(iter(roles)) if roles else "other"


def _color_component(card, ident):
    cid = set(card.identity or [])
    known = bool(card.mana_value is not None or card.types or card.mana_cost)
    if not cid:
        if known:
            return 25, "colorless — fits any deck"
        return 15, "color identity unknown (name-only list)"
    if cid <= ident:
        return 25, f"on-color ({''.join(sorted(cid))})"
    outside = "".join(sorted(cid - ident))
    return 2, f"needs {outside} — outside this deck's identity"


def _role_component(card, rep, section_label=None):
    role = primary_role(card)
    hint = section_role(section_label)
    used_section = False
    if role in ("creature", "other") and hint and hint != "creature":
        role, used_section = hint, True  # trust the player's own grouping
    cats = rep.get("categories", {})
    src = f" (from your '{section_label.strip()}' section)" if used_section else ""
    if role in FIT_TARGETS:
        lo, hi = FIT_TARGETS[role]
        cur = cats.get(role, 0)
        if cur < lo:
            return 30, role, f"a {role} card{src}; deck targets {lo}-{hi} — helps fill that"
        if cur <= hi:
            return 22, role, f"a {role} card{src}; deck has a healthy {cur} ({lo}-{hi} target)"
        return 12, role, f"a {role} card{src}; deck already runs {cur} (>{hi}) — this is depth"
    if role == "creature" or (hint == "creature"):
        return 18, "creature", "a creature the deck plays for its body or ability"
    return 16, "support", "a support piece — exact role not auto-detected from this list"


def _curve_component(card, refs):
    if card.is_land or card.mana_value is None:
        return 10, "curve slot n/a"
    mv = card.mana_value
    if mv <= 2:
        return 15, f"cheap (MV {mv:g}) — easy to cast, great tempo"
    if mv <= 4:
        return 12, f"mid curve (MV {mv:g})"
    if mv <= 6:
        return 9, f"top-end (MV {mv:g})"
    if mtglib._norm(card.name) in refs.get("game_changers", set()):
        return 13, f"expensive (MV {mv:g}) but a payoff bomb"
    return 6, f"expensive (MV {mv:g}) — demands ramp"


def _staple_component(card, refs, ctx=None):
    """How much muscle this card brings. Two signals, best-of:
    (a) the curated format lists (Game Changers / tutors / fast mana), and
    (b) **how much the field actually plays it FOR THIS COMMANDER** (EDHREC inclusion %).

    (b) is what stops the builder preferring a vanilla 1-drop over the archetype's
    auto-include just because it costs less mana — a generic "is it a staple" list can't
    know that Director Nick Fury is in 95% of Captain America decks."""
    n = mtglib._norm(card.name)
    pts, detail = 7, "no special power flag"
    if n in refs.get("game_changers", set()):
        pts, detail = 15, "a recognized Game Changer / format staple"
    elif n in refs.get("tutors", set()) or n in refs.get("fast_mana", set()):
        pts, detail = 11, "an established staple"

    inc = (ctx or {}).get("field", {}).get(n)
    if inc:
        if inc >= 80:
            fpts, fdet = 15, f"an auto-include here — {inc}% of this commander's decks run it"
        elif inc >= 60:
            fpts, fdet = 13, f"a core pick — {inc}% of this commander's decks run it"
        elif inc >= 40:
            fpts, fdet = 11, f"widely played here — {inc}% of decks run it"
        elif inc >= 20:
            fpts, fdet = 9, f"a common pick — {inc}% of decks run it"
        else:
            fpts, fdet = 8, f"seen in {inc}% of this commander's decks"
        if fpts > pts:
            pts, detail = fpts, fdet

    # SYNERGY: how much more THIS commander plays it than decks in general. Inclusion says
    # "popular"; synergy says "specifically wanted here". Command Tower is 93% inclusion but
    # ~5 synergy (generic); Dragon Tempest is 77%/69 (a Dragon payoff). Rewarding synergy
    # promotes a commander's signature cards over cards that are merely widely played.
    syn = (ctx or {}).get("synergy", {}).get(n)
    if syn:
        if syn >= 50:
            spts, sdet = 15, f"a signature card for this commander (+{syn} synergy vs. the format)"
        elif syn >= 30:
            spts, sdet = 13, f"strongly tied to this commander (+{syn} synergy)"
        elif syn >= 15:
            spts, sdet = 11, f"more played here than elsewhere (+{syn} synergy)"
        else:
            spts, sdet = 0, ""
        if spts > pts:
            pts, detail = spts, sdet
    return pts, detail


def _theme_component(card, ctx):
    tribal = ctx.get("tribal")
    if tribal and card.subtypes and tribal in {s.lower() for s in card.subtypes}:
        return 15, f"on-tribe ({tribal.title()})"
    name = card.name.lower()
    for kw in ctx.get("archetype", []):
        if len(kw) >= 4 and kw in name:
            return 12, f"matches the '{kw}' theme"
    return 7, "no explicit theme tie detected"


BANDS = [(82, "Core to the deck"), (66, "Strong fit"), (48, "Solid role-player"),
         (30, "Filler / flex slot"), (0, "Questionable — off-plan")]


def band_for(score):
    for lo, label in BANDS:
        if score >= lo:
            return label
    return BANDS[-1][1]


def assess_card(card, rep, ctx, refs, section_label=None):
    color_pts, color_det = _color_component(card, ctx["identity"])
    role_pts, role, role_det = _role_component(card, rep, section_label)
    curve_pts, curve_det = _curve_component(card, refs)
    stap_pts, stap_det = _staple_component(card, refs, ctx)
    theme_pts, theme_det = _theme_component(card, ctx)
    reasons = [
        {"label": "Color fit", "pts": color_pts, "max": 25, "detail": color_det},
        {"label": "Role need", "pts": role_pts, "max": 30, "detail": role_det},
        {"label": "Curve", "pts": curve_pts, "max": 15, "detail": curve_det},
        {"label": "Power", "pts": stap_pts, "max": 15, "detail": stap_det},
        {"label": "Theme", "pts": theme_pts, "max": 15, "detail": theme_det},
    ]
    score = sum(r["pts"] for r in reasons)
    # A card outside the color identity can't legally be here — cap it hard.
    if color_pts <= 2:
        score = min(score, 25)
    context = _context_line(color_det, role, role_det, stap_pts, theme_pts, theme_det)
    nameonly = not (card.types or card.mana_value is not None or card.mana_cost)
    return {"score": score, "band": band_for(score), "reasons": reasons,
            "context": context, "role": role, "nameonly": nameonly}


def _context_line(color_det, role, role_det, stap_pts, theme_pts, theme_det):
    if color_det.startswith("needs "):
        return f"Careful — this card {color_det.split(' — ')[0]}, so it isn't legal in this deck's colors."
    lead = role_det[0].upper() + role_det[1:]
    bits = [f"{lead}."]
    if theme_pts >= 12:
        bits.append(theme_det[0].upper() + theme_det[1:] + ".")
    if stap_pts >= 11:
        bits.append("It's an established staple, so it earns its slot.")
    return " ".join(bits)


def better_alternatives(card, ctx, idx, refs, curated_alts, in_deck, staples):
    """Return [{n, owned, upgrade, why}] — curated alternatives first, else same-role
    staples that fit the deck's identity and aren't already in the list."""
    out, seen = [], set()
    gc = refs.get("game_changers", set())
    card_is_gc = mtglib._norm(card.name) in gc

    def add(name, why_default):
        k = mtglib._norm(name)
        if k in seen or k == mtglib._norm(card.name):
            return
        seen.add(k)
        ref = mtglib.lookup(idx, name)
        upgrade = (k in gc) and not card_is_gc
        out.append({"n": name, "owned": ref is not None, "upgrade": upgrade,
                    "why": "stronger option — a format staple" if upgrade else why_default})

    for a in (curated_alts or []):
        add(a, "another option for this slot")
    if len(out) < 3:
        role = primary_role(card)
        for s in staples.get(role, []):
            if len(out) >= 4:
                break
            if s["colors"] <= ctx["identity"] and mtglib._norm(s["name"]) not in in_deck:
                add(s["name"], f"a strong {role} option in your colors")
    return out[:4]
