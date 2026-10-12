#!/usr/bin/env python3
"""Recorded narration for the Watch tab — the stdlib half (docs/spec-watch-voice-and-controls.md
Part C). The synthesis itself needs a voice-model runtime and lives outside scripts/
(`.github/narrate/synthesize.py`, runner only); everything that decides WHAT to record,
WHERE it lives and HOW LONG a scene runs is here, so the app and CI never need that runtime.

The rules:
  * **Content-addressed.** A take's file is `sha256(speak, engine, model, voice, speed)[:16]`
    `.mp3` — change a caption and only that scene is re-recorded; identical lines share one
    file; a stale take is simply a hash nobody asks for (pruned in the same commit).
  * **The voice is the player's pick**, by ear, in `data/reference/narration.json`
    (`engine`, `model`, `voice`, `speed`). No file = no narrator chosen yet = nothing to
    record, and the device voice (Part B) does all the talking.
  * **Timing follows the narrator.** A recorded scene runs for max(dur, take + 0.4 s),
    narration on or off, so the clip never changes length with the toggle and the voice is
    never cut off.
  * **A missing take is a WARNING, never a failure**: the runner records it on the next
    push, and failing CI on it would block unrelated deck edits.

Manifest: `data/narration/<stem>.json` = {"voice": {...}, "takes": {hash: {"file", "ms"}}}.

    python3 scripts/narration.py --plan [--deck data/decks/<stem>.txt] [--json]
"""
import argparse
import glob
import hashlib
import json
import os
import sys

import clips

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "data", "reference", "narration.json")
NARRATION_DIR = os.path.join(ROOT, "data", "narration")
TAIL_S = 0.4           # breath after the last word before the scene moves on


def load_config(path=CONFIG):
    """The chosen narrator, or None (no pick yet → the device voice does it all)."""
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(cfg, dict) or not cfg.get("engine") or not cfg.get("voice"):
        return None
    return {"engine": str(cfg["engine"]), "model": str(cfg.get("model") or ""),
            "voice": str(cfg["voice"]), "speed": float(cfg.get("speed") or 1.0)}


def deck_voice(cfg, raw_clips):
    """A deck may override the voice with a top-level "voice" in its clips file."""
    if not cfg:
        return None
    v = raw_clips.get("voice") if isinstance(raw_clips, dict) else None
    return dict(cfg, voice=str(v)) if v else cfg


def take_hash(speak, cfg):
    """The file name of one take: any change to the words or the voice is a new file."""
    key = "\x1f".join([speak, cfg["engine"], cfg.get("model", ""), cfg["voice"],
                       f"{float(cfg.get('speed') or 1.0):.3f}"])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def manifest_path(stem, base=None):
    # Read at CALL time, not def time: tests (and any caller) point NARRATION_DIR elsewhere.
    return os.path.join(base or NARRATION_DIR, stem + ".json")


def load_manifest(stem, base=None):
    try:
        with open(manifest_path(stem, base), encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        return {"takes": {}}
    if not isinstance(m, dict) or not isinstance(m.get("takes"), dict):
        return {"takes": {}}
    return m


def scene_len(dur, ms):
    """Seconds a scene runs once it has a take of `ms` milliseconds."""
    return max(float(dur), (ms or 0) / 1000.0 + TAIL_S) if ms else float(dur)


def attach(validated, stem, cfg, base=None):
    """Give each validated scene its take (`audio: {file, ms}`) and re-time it.
    Returns the number of scenes with no take yet (shown on the tab, warned in CI).
    No narrator chosen → nothing attached, 0 missing: the device voice is the plan."""
    if not cfg or not validated or not validated.get("clips"):
        return 0
    takes = load_manifest(stem, base).get("takes") or {}
    missing = 0
    total_all = 0.0
    for c in validated["clips"]:
        total = 0.0
        for sc in c["scenes"]:
            h = take_hash(sc.get("speak") or "", cfg)
            t = takes.get(h)
            if t and t.get("file") == f"{h}.mp3":
                sc["audio"] = {"file": t["file"], "ms": int(t.get("ms") or 0)}
                sc["dur"] = round(scene_len(sc["dur"], sc["audio"]["ms"]), 2)
            else:
                missing += 1
            total += sc["dur"]
        c["total"] = round(total, 1)
        total_all += total
    validated["total"] = round(total_all, 1)
    validated["narration_missing"] = missing
    return missing


def plan(deck_path, cfg, base=None):
    """[(hash, speak)] the runner still has to record for this deck, deduplicated,
    and the hashes the manifest holds that no scene uses any more (to prune)."""
    stem = os.path.splitext(os.path.basename(deck_path))[0]
    try:
        with open(clips.clips_path(deck_path), encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return [], []
    v = deck_voice(cfg, raw)
    if not v:
        return [], []
    res = clips.load(deck_path, clips._deck_cards(deck_path)) or {"clips": []}
    want = {}
    for c in res["clips"]:
        for sc in c["scenes"]:
            want.setdefault(take_hash(sc.get("speak") or "", v), sc.get("speak") or "")
    have = load_manifest(stem, base).get("takes") or {}
    todo = [(h, t) for h, t in want.items() if h not in have]
    prune = sorted(h for h in have if h not in want)
    return todo, prune


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--plan", action="store_true", help="list scenes with no take yet")
    ap.add_argument("--deck", help="one deck (default: every deck with clips)")
    ap.add_argument("--decks-dir", default=os.path.join(ROOT, "data", "decks"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    decks = [a.deck] if a.deck else sorted(
        p[:-len(".clips.json")] + ".txt"
        for p in glob.glob(os.path.join(a.decks_dir, "*.clips.json")))
    out = {}
    for d in decks:
        todo, prune = plan(d, cfg)
        out[os.path.splitext(os.path.basename(d))[0]] = {
            "voice": deck_voice(cfg, {}) if cfg else None,
            "record": [{"hash": h, "speak": t} for h, t in todo], "prune": prune}
    if a.json:
        print(json.dumps(out, indent=1, ensure_ascii=False))
    elif not cfg:
        print("No narrator chosen yet (data/reference/narration.json) — the device voice "
              "narrates every scene. Run the audition (narrate-audition.yml) and pick one.")
    else:
        for stem, r in out.items():
            print(f"{stem}: {len(r['record'])} scene(s) to record, {len(r['prune'])} stale take(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
