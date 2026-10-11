#!/usr/bin/env python3
"""Deck clips — the Watch tab's short animated walkthroughs (`<stem>.clips.json`).

A clip is a 30-60 second storyboard: an ordered list of scenes, each with a caption
and the deck's cards placed in zones on a mock table. The player
(`scripts/assets/clips_player.js`, inlined into the dashboard) animates cards from
scene to scene and can narrate with the browser's own voice. Nothing is rendered
to a video file: the clip is rebuilt from this file and the CURRENT decklist on
every page view, so it cannot freeze an old version of the deck.

This module is the grounding gate in front of the player:

  * **Every card a scene shows must be in the deck's current list.** A card that has
    left the deck is dropped from its scene and reported as STALE, and the Watch tab
    says so — a clip never shows a card the deck no longer plays.
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


def _num(v, default=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if f == f else default          # NaN is not a number here


def validate(raw, deck_cards, info=None, where="clips"):
    """Clean a parsed storyboard against the deck. Returns
    {"clips": [...], "stale": [...], "lint": [...], "total": seconds}.

    `deck_cards` is the deck's card names (any spelling `mtglib` understands);
    `info` optionally maps a name key to {"cost": str, "type": str} so the player
    can draw a card frame before (or without) the card art."""
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
            dur = _num(sc.get("dur"), 5.0)
            if not DUR_MIN <= dur <= DUR_MAX:
                lint.append(f"{at}: dur {dur:g}s is outside {DUR_MIN:g}-{DUR_MAX:g}s — clamped")
                dur = min(max(dur, DUR_MIN), DUR_MAX)
            head = str(sc.get("head") or "").strip()
            sub = str(sc.get("sub") or "").strip()
            say = str(sc.get("say") or "").strip()
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
                    if canon is None:
                        # The one finding a viewer must see: the deck changed under
                        # the storyboard. Drop the card, never show it.
                        stale.append(f"'{title}' scene {si}: {name} is no longer in this deck")
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
            lint.append(f"'{title}': no playable scenes — skipped")
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
