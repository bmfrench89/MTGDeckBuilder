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
import deckcore

REF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "data", "reference")

# The role template lives in deckcore (Phase 12): ONE table, archetype-aware,
# shared with the optimizer's accept filter so the scorer and the filter can never
# disagree about whether a deck is short on a role. The old FIT_TARGETS here was an
# independent copy with different numbers — measured on the six real decks, 17 of
# 30 role judgments disagreed with the optimizer, so this scorer pushed
# counterspells into a voltron deck the optimizer correctly refused them for.
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


def load_field_lands(commander, coll_index=None):
    """Cards EDHREC itself files as lands for this commander — the add-side type
    signal for candidates the collection can't type. Same degrade contract:
    an empty set just means the consumer falls back to its name heuristic."""
    if not commander:
        return set()
    try:
        import edhrec
        return edhrec.land_names(commander, coll_index)
    except Exception:
        return set()


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
        # One parser for every header (mtglib.deck_header) — the hand-rolled copies
        # this replaced shared the newline-crossing bug that made ur-dragon's empty
        # `# Archetype: ` swallow the next line as its archetype.
        c = mtglib.deck_header(head, "Colors?")
        if c:
            ident = set(re.sub(r"[^WUBRG]", "", c.upper()))
        archetype = deckcore.archetype_words(head)
        t = mtglib.deck_header(head, "Theme")
        if t:
            theme = t.strip().lower()
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
    ranges, unknown = deckcore.role_ranges_with_unknown(archetype)
    return {"identity": ident, "archetype": archetype, "theme": theme,
            "tribal": tribal, "commander": commander, "field": field or {},
            "synergy": synergy or {},
            # The archetype-aware role template, computed ONCE per deck. Every
            # assess_card call reads it from here; "land" rides along so the one
            # lookup table answers every role.
            "role_ranges": dict(ranges, land=deckcore.LAND_RANGE),
            "archetype_unknown": unknown}


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


# Role points. The SPREAD is load-bearing, not just the values: value_of doubles a
# fit difference into swap value, so (shortage - depth) * 2 must stay UNDER the
# optimizer's 25-point margin — otherwise template pressure alone can buy a swap
# with no field or quality support behind it, which is the 2026-08-12 churn
# mechanism. 26/22/14 caps the pure-role swing at 24. A tripwire test pins this;
# widening the spread past the margin is a design change, not a tuning knob.
ROLE_PTS_SHORTAGE = 26
ROLE_PTS_HEALTHY = 22
ROLE_PTS_DEPTH = 14


def _role_component(card, rep, section_label=None, ctx=None):
    role = primary_role(card)
    hint = section_role(section_label)
    used_section = False
    if role in ("creature", "other") and hint and hint != "creature":
        role, used_section = hint, True  # trust the player's own grouping
    cats = rep.get("categories", {})
    src = f" (from your '{section_label.strip()}' section)" if used_section else ""
    ctx = ctx or {}
    ranges = ctx.get("role_ranges") or dict(deckcore.ROLE_RANGE,
                                            land=deckcore.LAND_RANGE)
    widened = ranges.get(role) != dict(deckcore.ROLE_RANGE,
                                       land=deckcore.LAND_RANGE).get(role)
    wtag = " [band widened by archetype]" if widened else ""

    # Template-vs-field disagreement, surfaced per CARD with data we actually
    # have. The template and the field are genuinely independent voters (theory
    # vs. what real decks do), so when they pull apart the honest move is to show
    # both with provenance and let the player judge — never to resolve silently.
    # Absent field data stays silent: no row is NOT a measured 0%.
    def _field_note(shortage):
        pct = (ctx.get("field") or {}).get(mtglib._norm(card.name))
        if pct is None:
            return ""
        if shortage and pct < 10:
            return (f" — though the field plays this one in {pct}% of decks here: "
                    "the template wants the role, not necessarily this card")
        if not shortage and pct >= 25:
            return f" — and the field endorses this copy ({pct}% of decks)"
        return ""

    if role in ranges:
        lo, hi = ranges[role]
        cur = cats.get(role, 0)
        if cur < lo:
            return (ROLE_PTS_SHORTAGE, role,
                    f"a {role} card{src}; deck targets {lo}-{hi}{wtag} — helps fill "
                    f"that{_field_note(True)}")
        if cur <= hi:
            return (ROLE_PTS_HEALTHY, role,
                    f"a {role} card{src}; deck has a healthy {cur} "
                    f"({lo}-{hi} target{wtag})")
        return (ROLE_PTS_DEPTH, role,
                f"a {role} card{src}; deck already runs {cur} (>{hi}{wtag}) — this "
                f"is depth{_field_note(False)}")
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
    role_pts, role, role_det = _role_component(card, rep, section_label, ctx)
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


def dead_weight(enriched, rep, ctx, refs, protected=None, section_of=None, limit=8):
    """Cards pulling the least weight — RELATIVE to the rest of this same deck.

    This answers a different question from "what should I cut". The optimizer decides
    cuts and has its own guardrails; this just names the cards nothing in the deck is
    asking for, so a 100-card list stops hiding its passengers. It never edits anything.

    The comparison is deliberately relative, not an absolute score threshold. Fit scores
    shift wholesale depending on whether EDHREC field data was reachable — offline, an
    ordinary on-colour creature can score in the 60s, so any fixed cutoff either fires
    constantly or never fires at all. Asking "which cards score lowest in THIS deck"
    behaves identically online and off, and is the question a player actually has.

    A card must also clear two absolute conditions: no theme tie and no staple/field/
    synergy pull. Both are the floor value (7). That's the "synergises with nothing"
    test — without it this would just be a list of the deck's most expensive cards.

    Skipped: lands (the manabase pass owns those), cards with no type data (nothing to
    judge), the commander, and anything the player named in their own game plan — they
    already said why those are there, and "the heuristic disagrees" isn't an answer.
    """
    protected = protected or set()
    scored = []
    for c in enriched:
        k = mtglib._norm(c.name)
        if k in protected or c.is_land or not c.types:
            continue
        fit = assess_card(c, rep, ctx, refs, (section_of or {}).get(k))
        pts = {r["label"]: r["pts"] for r in fit["reasons"]}
        scored.append((c, fit, pts))
    if len(scored) < 4:                   # too small a sample to call anything an outlier
        return []
    ranked = sorted(s[1]["score"] for s in scored)
    median = ranked[len(ranked) // 2]
    out = []
    for c, fit, pts in scored:
        if pts.get("Theme", 0) > 7 or pts.get("Power", 0) > 7:
            continue                      # has a theme tie or real muscle — not dead
        if pts.get("Role need", 0) >= ROLE_PTS_HEALTHY:
            # Serving a role at a SHORTAGE or HEALTHY count is, by definition, a
            # job — a deck's only counterspell is load-bearing even when its raw
            # score sits below the median. Explicit since Phase 12: the old
            # inflated shortage bonus (30) kept such cards above the median by
            # accident, and narrowing the swing exposed that the median test alone
            # was doing this work by luck, not by design. Depth cards
            # (over-target) stay flaggable — those ARE the passenger candidates.
            continue
        if fit["score"] >= median:
            continue                      # at or above this deck's own middle
        why = []
        # _role_component's scale: 26 = fills a shortage · 22 = a role at a
        # healthy count (both excluded above) · 18 = generic creature body ·
        # 16 = role not detected · 14 = over-target depth.
        if pts.get("Role need", 0) <= 18:
            why.append("fills no role the deck is short on")
        why += ["no theme tie", "not a staple here"]
        out.append({"name": c.name, "score": fit["score"], "band": fit["band"],
                    "role": fit["role"], "why": " · ".join(why),
                    "median": median, "mana_value": c.mana_value})
    out.sort(key=lambda r: r["score"])
    return out[:limit] if limit else out


def card_value(name, ref, rep, ctx, refs, field):
    """What one card is worth to THIS deck: `max(field %, (fit-60)x2)`.

    The number BOTH sides of every optimizer swap are measured by, and the number the
    Cuts surface ranks by. One scorer, two consumers — a second implementation would
    drift, which is exactly what the codemap's card-knowledge-flow rule exists to
    prevent. `optimize.card_value` is a shim onto this."""
    inc = field.get(mtglib._norm(name), 0) if field else 0
    fit = (assess_card(ref, rep, ctx, refs)["score"]
           if (ref and ref.types) else 0)
    return max(inc, (fit - 60) * 2)       # fit 85 -> 50, fit 70 -> 20, fit <=60 -> 0


def cut_ranking(enriched, rep, ctx, refs, field, protected=None, ranges=None,
                cats=None, limit=12):
    """"If you must cut, start here" — ranked ascending by the optimizer's own value.

    ADVISORY AND READ-ONLY. It writes nothing, proposes no replacement, and is NOT a
    cut list: it answers the single most-asked deckbuilding question with the deck's
    own numbers and then stops. Pure — no file or network I/O — so the dashboard can
    call it from what it already holds; `optimize.cut_candidates` is the I/O wrapper.

    Protected cards (commander, basics, curated notes, `.notes.md` names, manual
    picks) are INCLUDED and flagged, never filtered out. Hiding them would answer a
    different question than the player asked; showing them as "your call, not the
    tool's" respects the decision while staying honest that the arithmetic ranks them
    low. Lands are skipped — the manabase pass owns those.
    """
    protected = protected or set()
    ranges = ranges or {}
    cats = cats or {}
    rows = []
    for c in enriched:
        if c.is_land or not c.types:
            continue
        n = mtglib._norm(c.name)
        keys = set(mtglib.name_keys(c.name))
        val = card_value(c.name, c, rep, ctx, refs, field)
        known = n in (field or {})
        role = primary_role(c)
        state = None
        if role and role in ranges:
            lo, hi = ranges[role]
            have = cats.get(role, 0)
            state = "surplus" if have > hi else "shortage" if have < lo else "in range"
        is_prot = bool(keys & set(protected))
        rows.append({
            "name": c.name, "value": round(val),
            "field": (field or {}).get(n), "field_known": known,
            "role": role, "role_state": state, "protected": is_prot,
            "why": ("protected — your call, not the tool's" if is_prot else
                    ("the field has no opinion on this card" if not known else
                     f"the field plays it in {(field or {}).get(n)}% of decks")),
        })
    rows.sort(key=lambda r: (r["value"], r["name"]))
    return {
        "rows": rows[:limit], "field_size": len(field or {}), "no_field": not field,
        "advisory": ("A starting point for your judgment, not a cut list. Ranked by "
                     "the same value the optimizer uses — max(field %, fit) — so a low "
                     "number means 'nothing in this deck is asking for it', not 'this "
                     "card is bad'."),
    }
