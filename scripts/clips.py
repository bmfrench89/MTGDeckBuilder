#!/usr/bin/env python3
"""Deck clips — the Watch tab's short animated walkthroughs (`<stem>.clips.json`).

A clip is a 30-60 second storyboard: an ordered list of scenes, each with a caption
and the deck's cards placed in zones on a mock table. The player
(`scripts/assets/clips_player.js`, inlined into the dashboard) animates cards from
scene to scene and can narrate with the browser's own voice. Nothing is rendered
to a video file: the clip is rebuilt from this file and the CURRENT decklist on
every page view, so it cannot freeze an old version of the deck.

This module is the grounding gate in front of the player:

  * **Every card a scene shows OR names must be in the deck's current list.** Captions
    name cards as `[[Card Name]]` (or `[[Card Name|shown text]]`), and those references
    are checked exactly like the cards on screen. A scene that shows or names a card the
    deck no longer plays is SKIPPED and reported as STALE, and the Watch tab says so:
    its caption was written around that card, so showing the scene without it (or
    naming it) would be advice the deck can no longer follow.
  * **The optimizer leaves featured cards alone.** `featured_names()` feeds the same
    protection as a card named in `.notes.md` (`optimize._protected`,
    `deck_fit.protected_keys`), so an automatic tuning pass can never strand a clip.
  * **Opponents' cards are never named.** A scene shows them as placeholders
    (`{"ph": "Their best creature"}`) — inventing an opponent's board would be
    inventing cards.
  * Everything else (caption length, scene timing, unknown zones) is a LINT warning
    for whoever writes the file; the clip still plays.

File shape (version 1):

    {"version": 1,
     "clips": [{"id": "pitch", "title": "The pitch",
                "scenes": [{"dur": 6, "head": "…", "sub": "…", "say": "…",
                            "turn": 1, "pool": "BBCCC",
                            "cards": [{"name": "Sol Ring", "zone": "mine",
                                       "fx": "tap", "id": "ring"},
                                      {"ph": "Their best creature", "zone": "theirs",
                                       "id": "victim"}]}]}]}

  zones: hero (one big card) · row (a centred line) · mine / theirs (your and an
         opponent's battlefield) · stack (a spell being cast) · grave (a graveyard)
  fx:    glow (a trigger) · tap · dim · back (face down)
  `id` keeps one card element across scenes, so it can slide from zone to zone.

    python3 scripts/clips.py --deck data/decks/<stem>.txt [--json]
    python3 scripts/clips.py --all --check        # exit 3 on any warning (CI runs this)

stdlib + mtglib only; never raises on a bad file — a broken storyboard costs the
deck its Watch tab, never the page.
"""
import argparse
import glob
import json
import os
import re
import sys

import mtglib

VERSION = 1
ZONES = ("hero", "row", "mine", "theirs", "stack", "grave")
FX = ("glow", "tap", "dim", "back")
DUR_MIN, DUR_MAX = 1.0, 20.0
CLIP_MIN, CLIP_MAX = 15.0, 90.0
MAX_CARDS = 8
HEAD_MAX, SUB_MAX, PH_MAX = 80, 200, 40
# Words a viewer can read per second while also watching cards move. Captions are
# shown for the scene's duration, so a scene shorter than its own text is a scene
# nobody can finish reading.
READ_WPS = 3.5
_POOL_RE = re.compile(r"^[WUBRGC]{0,12}$")
# [[Card Name]] or [[Card Name|shown text]] — the community's card-link notation.
_REF_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")


def clips_path(deck_path):
    base = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    return base + ".clips.json"


def _deck_index(deck_cards):
    """name key -> the deck's own spelling, over full names and front faces."""
    idx = {}
    for name in deck_cards:
        for k in mtglib.name_keys(name):
            idx.setdefault(k, name)
    return idx


def _refs(text):
    """(name, shown) for every [[...]] card reference in a caption."""
    return [(m.group(1).strip(), (m.group(2) or m.group(1)).strip())
            for m in _REF_RE.finditer(text or "")]


def _unref(text):
    """Caption text as the viewer sees it: [[Name|shown]] -> shown, [[Name]] -> Name."""
    return _REF_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), text or "")


# ---------------------------------------------------------------------------
# The spoken line (docs/spec-watch-voice-and-controls.md Part B §4): built ONCE
# here, so the device voice and a future recorded narrator say the same words.
# ---------------------------------------------------------------------------
PRONUNCIATIONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "data", "reference", "pronunciations.csv")
_NUM_WORDS = ("zero one two three four five six seven eight nine ten eleven twelve "
              "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty").split()
_SYM_WORDS = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green",
              "C": "colorless", "T": "tap", "Q": "untap", "S": "snow", "E": "energy",
              "X": "X", "Y": "Y", "P": "phyrexian"}
_SYM_RUN_RE = re.compile(r"(?:\{[^{}]{1,6}\})+")
_PT_RE = re.compile(r"([+\-\u2212])(\d+)/([+\-\u2212])(\d+)")


def _sym_word(sym):
    """One mana symbol as said aloud: {3} three, {B} black, {W/U} white or blue,
    {2/W} two or white, {B/P} phyrexian black."""
    parts = [p.strip().upper() for p in sym.split("/")]
    if len(parts) == 2 and parts[1] == "P":
        return "phyrexian " + _sym_word(parts[0])
    if len(parts) > 1:
        return " or ".join(_sym_word(p) for p in parts)
    p = parts[0]
    if p.isdigit():
        n = int(p)
        return _NUM_WORDS[n] if n < len(_NUM_WORDS) else p
    return _SYM_WORDS.get(p, p.lower())


def load_pronunciations(path=PRONUNCIATIONS):
    """[(word, say as)] from `pronunciations.csv` (`Word,Say as`), longest first.
    The list starts EMPTY on purpose: an entry is added only when the player hears a
    name said wrong — a guessed pronunciation is a guess. Missing file = no list."""
    import csv
    try:
        with open(path, encoding="utf-8") as f:
            rows = [((r.get("Word") or "").strip(), (r.get("Say as") or "").strip())
                    for r in csv.DictReader(f)]
    except OSError:
        return []
    return sorted([(w, s) for w, s in rows if w and s], key=lambda t: -len(t[0]))


def spoken(text, pron=()):
    """Caption text -> what the narrator says. `[[Card|shown]]` -> shown; mana symbols
    as words (`{3}{B}{B}` -> "three, black, black"); `+1/+1` -> "plus one plus one";
    MV -> mana value, ETB -> enters; the pronunciation list last (whole words)."""
    t = _unref(text or "")
    for word, say in pron:
        # Whole words, possessives included ("Tergrid's"), never inside a longer word.
        t = re.sub(r"(?<![\w'])" + re.escape(word) + r"(?!\w)", say, t, flags=re.IGNORECASE)
    t = _SYM_RUN_RE.sub(lambda m: " " + ", ".join(
        _sym_word(x) for x in re.findall(r"\{([^{}]+)\}", m.group(0))) + " ", t)

    def _pt(m):
        sign = lambda c: "plus" if c == "+" else "minus"
        num = lambda d: _NUM_WORDS[int(d)] if int(d) < len(_NUM_WORDS) else d
        return f"{sign(m.group(1))} {num(m.group(2))} {sign(m.group(3))} {num(m.group(4))}"
    t = _PT_RE.sub(_pt, t)
    t = re.sub(r"\bMV\b", "mana value", t)
    t = re.sub(r"\bETBs?\b", "enters", t)
    t = t.replace("\u2212", "minus ").replace("\u2014", ", ").replace("\u2026", ", ") \
         .replace("\u00b7", ", ")
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r",\s*,", ",", t)
    return re.sub(r"\s+", " ", t).strip()


def featured_names(deck_path):
    """Every card a deck's storyboard shows or names, read raw (no deck check).

    The optimizer protects these like cards named in `.notes.md`: a clip is curated
    content, and an automatic swap that cut a featured card would strand its scene.
    Never raises; no file (or a broken one) means nothing to protect."""
    try:
        with open(clips_path(deck_path), encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return []
    names = []
    for clip in (raw.get("clips") if isinstance(raw, dict) else None) or []:
        for sc in (clip.get("scenes") if isinstance(clip, dict) else None) or []:
            if not isinstance(sc, dict):
                continue
            for cd in sc.get("cards") or []:
                if isinstance(cd, dict) and cd.get("name"):
                    names.append(str(cd["name"]).strip())
            for field in ("head", "sub", "say"):
                names.extend(n for n, _shown in _refs(str(sc.get(field) or "")))
    return list(dict.fromkeys(n for n in names if n))


def _num(v, default=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if f == f else default          # NaN is not a number here


def validate(raw, deck_cards, info=None, where="clips", pron=None):
    """Clean a parsed storyboard against the deck. Returns
    {"clips": [...], "stale": [...], "lint": [...], "total": seconds}.

    `deck_cards` is the deck's card names (any spelling `mtglib` understands);
    `info` optionally maps a name key to {"cost": str, "type": str} so the player
    can draw a card frame before (or without) the card art. Every scene gets a
    `speak` line (`spoken()`), with `pron` the pronunciation list (default: the
    repo's `pronunciations.csv`)."""
    if pron is None:
        pron = load_pronunciations()
    stale, lint = [], []
    out = {"clips": [], "stale": stale, "lint": lint, "total": 0.0}
    if not isinstance(raw, dict):
        lint.append(f"{where}: top level must be an object")
        return out
    if raw.get("version") != VERSION:
        lint.append(f"{where}: version {raw.get('version')!r} (expected {VERSION})")
    clips = raw.get("clips")
    if not isinstance(clips, list):
        lint.append(f"{where}: 'clips' must be a list")
        return out
    deck = _deck_index(deck_cards)
    info = info or {}
    seen_ids = set()
    for ci, clip in enumerate(clips, 1):
        if not isinstance(clip, dict):
            lint.append(f"clip {ci}: not an object — skipped")
            continue
        title = str(clip.get("title") or f"Clip {ci}").strip()
        cid = re.sub(r"[^a-z0-9-]", "-", str(clip.get("id") or title).lower()).strip("-")
        if cid in seen_ids:
            cid = f"{cid}-{ci}"
        seen_ids.add(cid)
        scenes_in = clip.get("scenes")
        if not isinstance(scenes_in, list) or not scenes_in:
            lint.append(f"'{title}': no scenes — skipped")
            continue
        scenes, total = [], 0.0
        for si, sc in enumerate(scenes_in, 1):
            at = f"'{title}' scene {si}"
            if not isinstance(sc, dict):
                lint.append(f"{at}: not an object — skipped")
                continue
            # Everything this scene shows or names, checked BEFORE it is built: one
            # card that left the deck makes the whole scene stale.
            cards_raw = sc.get("cards") if isinstance(sc.get("cards"), list) else []
            wanted = [str(cd.get("name") or "").strip() for cd in cards_raw
                      if isinstance(cd, dict) and "name" in cd]
            wanted += [n for f in ("head", "sub", "say")
                       for n, _shown in _refs(str(sc.get(f) or ""))]
            gone = [n for n in dict.fromkeys(wanted)
                    if not any(k in deck for k in mtglib.name_keys(n))]
            if gone:
                stale.append(f"{at} skipped: {', '.join(gone)} "
                             f"{'is' if len(gone) == 1 else 'are'} no longer in this deck")
                continue
            dur = _num(sc.get("dur"), 5.0)
            if not DUR_MIN <= dur <= DUR_MAX:
                lint.append(f"{at}: dur {dur:g}s is outside {DUR_MIN:g}-{DUR_MAX:g}s — clamped")
                dur = min(max(dur, DUR_MIN), DUR_MAX)
            head = _unref(str(sc.get("head") or "")).strip()
            sub = _unref(str(sc.get("sub") or "")).strip()
            say = _unref(str(sc.get("say") or "")).strip()
            if not head:
                lint.append(f"{at}: no headline")
            if len(head) > HEAD_MAX:
                lint.append(f"{at}: headline is {len(head)} chars (max {HEAD_MAX})")
            if len(sub) > SUB_MAX:
                lint.append(f"{at}: caption is {len(sub)} chars (max {SUB_MAX})")
            words = len((head + " " + sub).split())
            if words / READ_WPS > dur + 1.0:
                lint.append(f"{at}: {words} words need ~{words / READ_WPS:.0f}s to read "
                            f"but the scene lasts {dur:g}s")
            scene = {"dur": round(dur, 2), "head": head, "sub": sub, "cards": []}
            if say:
                scene["say"] = say
            raw_say = str(sc.get("say") or "").strip() or (
                str(sc.get("head") or "").strip()
                + (". " + str(sc.get("sub") or "").strip() if sc.get("sub") else ""))
            scene["speak"] = spoken(raw_say, pron)
            turn = sc.get("turn")
            if turn is not None:
                t = _num(turn)
                if t is not None and t == int(t) and 1 <= t <= 30:
                    scene["turn"] = int(t)
                else:
                    lint.append(f"{at}: turn {turn!r} ignored")
            pool = sc.get("pool")
            if pool is not None:
                if isinstance(pool, str) and _POOL_RE.match(pool):
                    scene["pool"] = pool
                else:
                    lint.append(f"{at}: pool {pool!r} ignored (WUBRGC letters only)")
            cards_in = sc.get("cards") or []
            if not isinstance(cards_in, list):
                lint.append(f"{at}: 'cards' must be a list — ignored")
                cards_in = []
            if len(cards_in) > MAX_CARDS:
                lint.append(f"{at}: {len(cards_in)} cards (max {MAX_CARDS}) — extra dropped")
                cards_in = cards_in[:MAX_CARDS]
            used = set()
            for cd in cards_in:
                if not isinstance(cd, dict):
                    lint.append(f"{at}: a card entry is not an object — skipped")
                    continue
                zone = cd.get("zone") or "row"
                if zone not in ZONES:
                    lint.append(f"{at}: unknown zone {zone!r} — shown in 'row'")
                    zone = "row"
                fx = [f for f in (cd.get("fx") if isinstance(cd.get("fx"), list)
                                  else [cd.get("fx")] if cd.get("fx") else [])]
                bad_fx = [f for f in fx if f not in FX]
                if bad_fx:
                    lint.append(f"{at}: unknown fx {bad_fx} ignored")
                fx = [f for f in fx if f in FX]
                if "ph" in cd:
                    label = str(cd.get("ph") or "").strip()
                    if not label:
                        lint.append(f"{at}: empty placeholder — skipped")
                        continue
                    if len(label) > PH_MAX:
                        lint.append(f"{at}: placeholder label is {len(label)} chars "
                                    f"(max {PH_MAX})")
                    key = str(cd.get("id") or "ph:" + label)
                    card = {"ph": label, "zone": zone, "key": key}
                elif "name" in cd:
                    name = str(cd.get("name") or "").strip()
                    canon = next((deck[k] for k in mtglib.name_keys(name) if k in deck),
                                 None)
                    if canon is None:      # unreachable: the scene gate ran first
                        stale.append(f"{at}: {name} is no longer in this deck")
                        continue
                    key = str(cd.get("id") or canon)
                    card = {"name": canon, "zone": zone, "key": key}
                    meta = next((info[k] for k in mtglib.name_keys(canon) if k in info),
                                None)
                    if meta:
                        card.update({k: v for k, v in meta.items() if v})
                else:
                    lint.append(f"{at}: a card has neither 'name' nor 'ph' — skipped")
                    continue
                if card["key"] in used:
                    lint.append(f"{at}: {card['key']!r} appears twice — second dropped")
                    continue
                used.add(card["key"])
                if fx:
                    card["fx"] = fx
                scene["cards"].append(card)
            scenes.append(scene)
            total += dur
        if not scenes:
            (stale if any(s.startswith(f"'{title}'") for s in stale) else lint).append(
                f"'{title}': no playable scenes — the whole clip is hidden")
            continue
        if not CLIP_MIN <= total <= CLIP_MAX:
            lint.append(f"'{title}': runs {total:.0f}s (aim for {CLIP_MIN:.0f}-{CLIP_MAX:.0f}s)")
        out["clips"].append({"id": cid, "title": title, "total": round(total, 1),
                             "scenes": scenes})
        out["total"] += total
    out["total"] = round(out["total"], 1)
    return out


def load(deck_path, deck_cards, info=None):
    """The deck's storyboard, validated — or None when the deck has no clips file.

    Never raises: unreadable or malformed JSON comes back as an empty clip list with
    the reason in `lint`, so a bad file costs the Watch tab, never the dashboard."""
    path = clips_path(deck_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        return {"clips": [], "stale": [], "total": 0.0,
                "lint": [f"{os.path.basename(path)}: can't be read ({e})"]}
    return validate(raw, deck_cards, info, where=os.path.basename(path))


def _deck_cards(deck_path):
    with open(deck_path, encoding="utf-8") as f:
        return [c.name for c in mtglib.parse_deck(f.read())]


def _fmt(sec):
    return f"{int(sec // 60)}:{int(round(sec % 60)):02d}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--deck", help="a deck file (data/decks/<stem>.txt)")
    g.add_argument("--all", action="store_true",
                   help="every deck in --decks-dir that has a .clips.json")
    ap.add_argument("--decks-dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "decks"))
    ap.add_argument("--check", action="store_true",
                    help="exit 3 when any clip has a stale card or a lint warning")
    ap.add_argument("--json", action="store_true", help="print the validated storyboard")
    args = ap.parse_args(argv)

    if args.deck:
        decks = [args.deck]
    else:
        decks = sorted(p[:-len(".clips.json")] + ".txt"
                       for p in glob.glob(os.path.join(args.decks_dir, "*.clips.json")))
    problems = 0
    report = {}
    for deck_path in decks:
        stem = os.path.basename(deck_path)[:-4]
        if not os.path.exists(deck_path):
            print(f"{stem}: clips file has no deck ({deck_path} missing)")
            problems += 1
            continue
        res = load(deck_path, _deck_cards(deck_path))
        if res is None:
            print(f"{stem}: no clips file ({os.path.basename(clips_path(deck_path))})")
            continue
        report[stem] = res
        problems += len(res["stale"]) + len(res["lint"])
        if args.json:
            continue
        print(f"{stem}: {len(res['clips'])} clip(s), {_fmt(res['total'])} in all")
        for c in res["clips"]:
            print(f"  {c['title']} ({_fmt(c['total'])}, {len(c['scenes'])} scenes)")
            for s in c["scenes"]:
                print(f"    {s['dur']:>4g}s  {s['head']}")
        for w in res["stale"]:
            print(f"  STALE {w}")
        for w in res["lint"]:
            print(f"  lint  {w}")
    if args.json:
        print(json.dumps(report, indent=1, ensure_ascii=False))
    if args.check and problems:
        print(f"{problems} clip problem(s)", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
