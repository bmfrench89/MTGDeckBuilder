#!/usr/bin/env python3
"""Record the Watch tab's narration — runner only (docs/spec-watch-voice-and-controls.md
Part C). Needs a voice-model runtime (Kokoro's torch or Piper's onnxruntime), so it lives
outside scripts/; everything it decides comes from the stdlib `scripts/narration.py`:

  for every deck with clips: narration.plan() → the scenes with no take for the CHOSEN
  voice (data/reference/narration.json) → synthesize each → ffmpeg MP3 (mono, 64 kbps)
  → data/narration/<stem>/<hash>.mp3 + the manifest data/narration/<stem>.json; takes no
  scene uses any more are pruned in the same commit.

No narration.json (no voice picked yet) → nothing to do, exit 0.
"""
import json
import os
import subprocess
import sys
import urllib.request
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import narration  # noqa: E402

HF = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
_kokoro = {}
_piper = {}


def _wav_ms(path):
    with wave.open(path) as w:
        return round(1000 * w.getnframes() / w.getframerate())


def synth_wav(cfg, text, wav):
    if cfg["engine"].startswith("kokoro"):
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
        lang = cfg["voice"][0]                       # af_* → 'a' (US), bm_* → 'b' (UK)
        if lang not in _kokoro:
            _kokoro[lang] = KPipeline(lang_code=lang)
        parts = []
        for r in _kokoro[lang](text, voice=cfg["voice"], speed=cfg["speed"]):
            a = getattr(r, "audio", None)
            a = r[2] if a is None else a
            parts.append(a.numpy() if hasattr(a, "numpy") else np.asarray(a))
        sf.write(wav, np.concatenate(parts), 24000)
    elif cfg["engine"] == "piper":
        from piper import PiperVoice
        name = cfg["voice"]                          # e.g. en_US-ryan-high
        if name not in _piper:
            lang, speaker, quality = name.split("-")
            d = os.path.join(ROOT, ".cache-piper")
            os.makedirs(d, exist_ok=True)
            model = os.path.join(d, name + ".onnx")
            for suffix in (".onnx", ".onnx.json"):
                if not os.path.exists(model[:-5] + suffix):
                    urllib.request.urlretrieve(
                        f"{HF}/{lang.split('_')[0]}/{lang}/{speaker}/{quality}/{name}{suffix}",
                        model[:-5] + suffix)
            _piper[name] = PiperVoice.load(model)
        with wave.open(wav, "wb") as wf:
            v = _piper[name]
            (v.synthesize_wav if hasattr(v, "synthesize_wav") else v.synthesize)(text, wf)
    else:
        raise ValueError(f"unknown engine {cfg['engine']!r}")
    return _wav_ms(wav)


def main():
    cfg = narration.load_config()
    if not cfg:
        print("No narrator chosen (data/reference/narration.json) — nothing to record.")
        return 0
    decks_dir = os.path.join(ROOT, "data", "decks")
    recorded = pruned = 0
    for clips_file in sorted(os.listdir(decks_dir)):
        if not clips_file.endswith(".clips.json"):
            continue
        stem = clips_file[:-len(".clips.json")]
        deck = os.path.join(decks_dir, stem + ".txt")
        if not os.path.exists(deck):
            continue
        raw = json.load(open(os.path.join(decks_dir, clips_file), encoding="utf-8"))
        voice = narration.deck_voice(cfg, raw)
        todo, prune = narration.plan(deck, cfg)
        out_dir = os.path.join(narration.NARRATION_DIR, stem)
        os.makedirs(out_dir, exist_ok=True)
        manifest = narration.load_manifest(stem)
        takes = manifest.get("takes") or {}
        if manifest.get("voice") and manifest["voice"] != voice:
            print(f"{stem}: voice changed — every scene is re-recorded")
        for h, text in todo:
            wav = os.path.join(out_dir, h + ".wav")
            ms = synth_wav(voice, text, wav)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-ac", "1",
                            "-b:a", "64k", os.path.join(out_dir, h + ".mp3")], check=True)
            os.remove(wav)
            takes[h] = {"file": h + ".mp3", "ms": ms}
            recorded += 1
            print(f"{stem}: recorded {h} ({ms} ms): {text[:70]}", flush=True)
        for h in prune:
            t = takes.pop(h, None) or {}
            try:
                os.remove(os.path.join(out_dir, t.get("file") or h + ".mp3"))
            except OSError:
                pass
            pruned += 1
        with open(narration.manifest_path(stem), "w", encoding="utf-8") as f:
            json.dump({"voice": voice, "takes": dict(sorted(takes.items()))}, f, indent=1)
    print(f"recorded {recorded} take(s), pruned {pruned}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
