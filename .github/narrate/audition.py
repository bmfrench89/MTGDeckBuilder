#!/usr/bin/env python3
"""Narration AUDITION — runs on a GitHub runner only (docs/spec-watch-voice-and-controls.md
Part C, step 2). Not part of scripts/: it needs third-party model runtimes (Kokoro's torch,
Piper's onnxruntime), which the stdlib-only rule keeps out of the repo's toolkit.

Records the same three Iron Fortress scenes — their `speak` lines, built by
`scripts/clips.py` exactly as the device voice says them — in six free, open-source voices,
so the player can pick one by ear. Writes `data/narration/audition/<voice>-<n>.mp3` (mono,
64 kbps) and `index.json` (voice, engine, licence note, scene text, file, ms, CPU seconds).

This run is also the spike that confirms the model facts the spec assumed: that both
engines install and synthesize on a CPU runner, how long a scene takes, and each Piper
voice's licence (printed from its MODEL_CARD).
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "narration", "audition")
# The audition deck: any deck with clips. Tergrid (the prototype) was deleted 2026-10-14
# with the other non-real decks, so the audition now reads the Ur-Dragon's storyboard.
STEM = "the-ur-dragon"
DECK = os.path.join(ROOT, "data", "decks", f"{STEM}.txt")
PICK = [("The pitch", 0), ("The pitch", 2), ("Make them cheap", 0)]

KOKORO = [("af_heart", "a"), ("af_bella", "a"), ("am_michael", "a"), ("bm_george", "b")]
PIPER = [("en_US-ryan-high", "en/en_US/ryan/high"), ("en_GB-alan-medium", "en/en_GB/alan/medium")]
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"


def scenes():
    raw = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "clips.py"),
                          "--deck", DECK, "--json"], capture_output=True, text=True,
                         check=True).stdout
    clips = {c["title"]: c for c in json.loads(raw)[STEM]["clips"]}
    return [clips[t]["scenes"][i]["speak"] for t, i in PICK]


def to_mp3(wav_path, mp3_path):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path, "-ac", "1",
                    "-b:a", "64k", mp3_path], check=True)
    os.remove(wav_path)


def wav_ms(path):
    with wave.open(path) as w:
        return round(1000 * w.getnframes() / w.getframerate())


def kokoro_voice(voice, lang, texts, rows):
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline
    pipe = KPipeline(lang_code=lang)
    for n, text in enumerate(texts, 1):
        t0 = time.process_time()
        parts = []
        for r in pipe(text, voice=voice, speed=1.0):
            a = getattr(r, "audio", None)
            if a is None:
                a = r[2]
            parts.append(a.numpy() if hasattr(a, "numpy") else np.asarray(a))
        cpu = time.process_time() - t0
        wav = os.path.join(OUT, f"{voice}-{n}.wav")
        sf.write(wav, np.concatenate(parts), 24000)
        ms = wav_ms(wav)
        to_mp3(wav, wav[:-4] + ".mp3")
        rows.append({"voice": voice, "engine": "kokoro-82m", "licence": "Apache-2.0",
                     "scene": n, "text": text, "file": f"{voice}-{n}.mp3", "ms": ms,
                     "cpu_s": round(cpu, 2)})
        print(f"kokoro {voice} scene {n}: {ms} ms audio, {cpu:.1f}s CPU", flush=True)


def piper_voice(name, path, texts, rows):
    from piper import PiperVoice
    d = os.path.join(ROOT, ".cache-piper")
    os.makedirs(d, exist_ok=True)
    model = os.path.join(d, name + ".onnx")
    for suffix in (".onnx", ".onnx.json"):
        if not os.path.exists(model[:-5] + suffix):
            urllib.request.urlretrieve(f"{HF}/{path}/{name}{suffix}", model[:-5] + suffix)
    try:
        card = urllib.request.urlopen(f"{HF}/{path}/MODEL_CARD").read().decode("utf-8")
    except Exception as e:                     # licence unknown is reported, never assumed
        card = f"(MODEL_CARD unavailable: {e})"
    print(f"--- MODEL_CARD {name} ---\n{card}\n---", flush=True)
    lic = next((ln.split(":", 1)[1].strip() for ln in card.splitlines()
                if "licen" in ln.lower() and ":" in ln), "see MODEL_CARD")
    voice = PiperVoice.load(model)
    for n, text in enumerate(texts, 1):
        t0 = time.process_time()
        wav = os.path.join(OUT, f"{name}-{n}.wav")
        with wave.open(wav, "wb") as wf:
            if hasattr(voice, "synthesize_wav"):
                voice.synthesize_wav(text, wf)
            else:
                voice.synthesize(text, wf)
        cpu = time.process_time() - t0
        ms = wav_ms(wav)
        to_mp3(wav, wav[:-4] + ".mp3")
        rows.append({"voice": name, "engine": "piper", "licence": lic, "scene": n,
                     "text": text, "file": f"{name}-{n}.mp3", "ms": ms, "cpu_s": round(cpu, 2)})
        print(f"piper {name} scene {n}: {ms} ms audio, {cpu:.1f}s CPU", flush=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    texts = scenes()
    for i, t in enumerate(texts, 1):
        print(f"scene {i}: {t}", flush=True)
    rows, failed = [], []
    for voice, lang in KOKORO:
        try:
            kokoro_voice(voice, lang, texts, rows)
        except Exception as e:
            failed.append(f"kokoro {voice}: {type(e).__name__}: {e}")
            print("FAILED", failed[-1], flush=True)
    for name, path in PIPER:
        try:
            piper_voice(name, path, texts, rows)
        except Exception as e:
            failed.append(f"piper {name}: {type(e).__name__}: {e}")
            print("FAILED", failed[-1], flush=True)
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"scenes": texts, "takes": rows, "failed": failed}, f, indent=1,
                  ensure_ascii=False)
    total = sum(os.path.getsize(os.path.join(OUT, r["file"])) for r in rows)
    print(f"{len(rows)} takes, {total // 1024} KB; failed: {failed or 'none'}")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
