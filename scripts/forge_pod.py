"""The household pod: every deck plays every other in Forge's AI simulator.

The player (2026-10-17): "Are you able to create a system where all of our decks can play
against each other in simulations?" This is the Forge household pod the deck-UAT spec
planned (docs/spec-deck-uat.md, Next item 6; the full design is docs/spec-forge-pod.md).

What it does:
1. Exports each deck to Forge's .dck format. Two-faced cards go by their front face, except
   split cards, which Forge names "A // B".
2. Checks every card against Forge's own card scripts (res/cardsfolder/cardsfolder.zip).
   Forge doesn't refuse an unknown card: it quietly removes it at game start, so the deck
   plays short. That's why the unsupported cards are reported per deck, never hidden.
3. Schedules 4-player Commander pods so each deck plays about the same number of games,
   with seats rotated. Every game is its own JVM (`-n 1`): Forge's AI always chooses to go
   first, and a multi-game run starts each later game with a seat that didn't win, so a
   long run biases seats.
4. Runs the pods in parallel and parses each game.
   - A timed-out game prints "Stopping slow match as draw" and then names EVERY surviving
     seat a winner. So that line, or two or more winners, counts as abandoned, never a win.
   - Forge exits 0 even when a deck fails to load, so its output is parsed, never trusted.
5. Writes a results file and prints standings: win share against the 25% a 4-seat pod
   gives by chance, plus head-to-head records.

Forge's AI is fair with aggro and midrange and weak with combo and control. So this is a
smoke test and a rough matchup chart, labelled as limited by the pilots, never a verdict.
Its crash reporter is pointed at this machine (127.0.0.1), so no report leaves it.

Stdlib only. It needs Java 17+ and the Forge release, which `--install` downloads into
data/cache/forge/<version>/ (gitignored).
"""
import argparse
import collections
import concurrent.futures
import datetime
import glob
import io
import json
import os
import random
import re
import subprocess
import sys
import tarfile
import time
import unicodedata
import urllib.request
import zipfile

import deckcore
import mtglib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE_VERSION = "2.0.15"
FORGE_URL = ("https://github.com/Card-Forge/forge/releases/download/forge-2.0.15/"
             "forge-installer-2.0.15.tar.bz2")
FORGE_SIZE = 297081149
JAR = f"forge-gui-desktop-{FORGE_VERSION}-jar-with-dependencies.jar"
DEFAULT_FORGE_DIR = os.path.join(ROOT, "data", "cache", "forge", FORGE_VERSION)
RESULTS_DIR = os.path.join(ROOT, "data", "reference", "pod")
# Forge only falls back to its own crash server when no DSN is configured, and it reads
# external configuration (Main.java), so this keeps every report on this machine.
SENTRY_OFF = "https://off@127.0.0.1/0"
POD_SIZE = 4


# ---- Forge's card names -----------------------------------------------------------

def _fold(name):
    """Forge's lookup ignores case and accents; so does ours."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


def forge_index(zip_path):
    """{folded name: (Forge's name, AI-flagged)} from Forge's card scripts.

    A script's first `Name:` is its card. A split card (AlternateMode:Split) is named
    "A // B"; every other two-faced card is named by its front face, and each face also
    finds it. `AI:RemoveDeck:All` marks a card Forge's own AI plays badly. It stays in
    the deck, and the report flags it."""
    index = {}
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if not info.filename.endswith(".txt"):
                continue
            text = zf.read(info).decode("utf-8", errors="replace")
            names = re.findall(r"^Name:(.+?)\s*$", text, re.M)
            if not names:
                continue
            split = re.search(r"^AlternateMode:Split\s*$", text, re.M) is not None
            primary = " // ".join(names[:2]) if split and len(names) > 1 else names[0]
            flagged = re.search(r"^AI:RemoveDeck:All\s*$", text, re.M) is not None
            for alias in [primary] + names:
                index.setdefault(_fold(alias), (primary, flagged))
    return index


def forge_name(name, index):
    """Forge's name for one of our cards, or None when Forge has no script for it."""
    hit = index.get(_fold(name))
    if hit is None and " // " in name:
        hit = index.get(_fold(mtglib.front_face(name)))
    return hit


# ---- Export -------------------------------------------------------------------------

def export_deck(path, index):
    """A deck file as Forge's .dck text, plus what Forge can't play or plays badly.

    -> {"stem", "title", "dck", "cards", "unsupported": [...], "ai_flagged": [...]}"""
    text = open(path, encoding="utf-8").read()
    stem = os.path.splitext(os.path.basename(path))[0]
    cmd_keys = deckcore.commander_keys(text)
    commanders, main, unsupported, flagged = [], [], [], []
    for c in mtglib.parse_deck(text):
        hit = forge_name(c.name, index)
        if hit is None:
            unsupported.append(c.name)
            continue
        fname, bad = hit
        if bad:
            flagged.append(c.name)
        is_cmd = bool(mtglib.name_keys(c.name) & cmd_keys)
        (commanders if is_cmd else main).append((c.quantity, fname))
    # The deck's stem is its Forge name: it never contains ": " or " vs ", which would
    # break Forge's header and tally lines.
    lines = ["[metadata]", f"Name={stem}", "[Commander]"]
    lines += [f"{q} {n}" for q, n in commanders]
    lines += ["[Main]"] + [f"{q} {n}" for q, n in main]
    return {"stem": stem, "title": mtglib.deck_header(text, "Title") or stem,
            "study": mtglib.deck_header(text, "Study").strip().lower().startswith("y"),
            "dck": "\n".join(lines) + "\n",
            "cards": sum(q for q, _ in commanders + main),
            "unsupported": unsupported, "ai_flagged": flagged}


# ---- Schedule -----------------------------------------------------------------------

def schedule(stems, games_per_deck, size=POD_SIZE, seed=0):
    """Pods of `size` distinct decks, so each deck plays about `games_per_deck` games,
    with seats rotated: in each pod, the deck that has sat first least often sits first.

    Greedy and seeded: each pod takes the decks with the fewest games so far (random
    tie-break), which keeps every count within one of the others."""
    rng = random.Random(seed)
    stems = list(stems)
    if len(stems) < size:
        raise ValueError(f"need at least {size} decks for a {size}-seat pod")
    played = collections.Counter({s: 0 for s in stems})
    seats = {s: collections.Counter() for s in stems}
    pods = []
    total = -(-len(stems) * games_per_deck // size)   # ceiling
    for _ in range(total):
        order = sorted(stems, key=lambda s: (played[s], rng.random()))
        pod = order[:size]
        seated = []
        for seat in range(size):
            pick = min((s for s in pod if s not in seated),
                       key=lambda s: (seats[s][seat], rng.random()))
            seated.append(pick)
            seats[pick][seat] += 1
        for s in pod:
            played[s] += 1
        pods.append(seated)
    return pods


# ---- Run one game -------------------------------------------------------------------

def run_game(forge_dir, dck_dir, seats, timeout=600, seed=1, java="java", heap="2048m"):
    """One Forge game in its own JVM. -> (stdout, stderr, seconds, wall_timeout)."""
    cmd = [java, f"-Xmx{heap}", "-Dfile.encoding=UTF-8", f"-Dsentry.dsn={SENTRY_OFF}",
           "-jar", JAR, "sim", "-D", os.path.join(os.path.abspath(dck_dir), ""),
           "-d", *[f"{s}.dck" for s in seats], "-f", "Commander", "-n", "1",
           "-c", str(timeout), "-q", "-s", str(seed)]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=forge_dir, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout + 180)
        return p.stdout, p.stderr, time.time() - t0, False
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return out, err, time.time() - t0, True


# ---- Parse one game -----------------------------------------------------------------

_WON = re.compile(r"has won\b")


def parse_game(stdout, seats, stderr="", wall_timeout=False):
    """One game's outcome from Forge's quiet output.

    -> {"winner": stem or None, "abandoned": reason or None, "turn": int or None,
        "seconds": float or None, "outcomes": {stem: text}, "unsupported": [...]}

    `turn` is Forge's "Turn N", which counts every player's turn and halves it, so in a
    4-seat pod it is about twice the number of rounds."""
    out = (stdout or "").replace("\r\n", "\n")
    outcomes = {}
    for i, stem in enumerate(seats, 1):
        tag = f"Ai({i})-{stem} "
        for ln in out.splitlines():
            m = re.match(r"^Game Outcome:\s*(.*)$", ln.strip(), re.I)
            if m and m.group(1).startswith(tag):
                outcomes[stem] = m.group(1)[len(tag):].strip()
    winners = [s for s, o in outcomes.items() if _WON.search(o)]
    turn = None
    m = re.search(r"^Game Outcome:\s*Turn\s+(\d+)\s*$", out, re.I | re.M)
    if m:
        turn = int(m.group(1))
    seconds = None
    m = re.search(r"Game Result: Game \d+ ended in (?:a Draw! Took )?(\d+) ms", out)
    if m:
        seconds = int(m.group(1)) / 1000
    abandoned = None
    if wall_timeout:
        abandoned = "the JVM ran past its wall-clock limit"
    elif "Could not load deck" in out or "match cannot start" in out:
        abandoned = "a deck failed to load"
    elif "Stopping slow match as draw" in out:
        abandoned = "timed out (Forge then names every survivor a winner)"
    elif len(winners) > 1:
        abandoned = "more than one winner reported"
    elif "ended in a Draw" in out:
        abandoned = "a draw"
    elif not outcomes:
        abandoned = "no outcome in Forge's output"
    unsupported = sorted(set(re.findall(r'An unsupported card was requested: "([^"]+)"',
                                        (stderr or "") + "\n" + out)))
    return {"winner": winners[0] if not abandoned and len(winners) == 1 else None,
            "abandoned": abandoned, "turn": turn, "seconds": seconds,
            "outcomes": outcomes, "unsupported": unsupported}


def round_of(forge_turn, pod_size=POD_SIZE):
    """Forge's "Turn N" as a round: each player's own turn count. Forge counts every
    seat's turn and halves the total, so a 4-seat game's Turn 26 is round 13."""
    return forge_turn * 2 / pod_size


# ---- Aggregate -------------------------------------------------------------------------

def aggregate(games, stems):
    """Standings and head-to-head from parsed games.

    Win share counts only games that finished; abandoned ones are reported, not scored.
    In a 4-seat pod a deck wins 25% by chance."""
    rows = {s: {"games": 0, "finished": 0, "wins": 0, "abandoned": 0, "turns": []}
            for s in stems}
    h2h = {a: {b: [0, 0] for b in stems if b != a} for a in stems}   # [wins, met]
    for g in games:
        seats = g["seats"]
        for s in seats:
            rows[s]["games"] += 1
            if g["abandoned"]:
                rows[s]["abandoned"] += 1
                continue
            rows[s]["finished"] += 1
            if g["turn"]:
                rows[s]["turns"].append(g["turn"])
        if g["abandoned"]:
            continue
        for a in seats:
            for b in seats:
                if a == b:
                    continue
                h2h[a][b][1] += 1
                if g["winner"] == a:
                    h2h[a][b][0] += 1
        if g["winner"] in rows:
            rows[g["winner"]]["wins"] += 1
    standings = []
    for s, r in rows.items():
        share = r["wins"] / r["finished"] if r["finished"] else None
        avg_turn = sum(r["turns"]) / len(r["turns"]) if r["turns"] else None
        standings.append({"stem": s, "games": r["games"], "finished": r["finished"],
                          "wins": r["wins"], "abandoned": r["abandoned"],
                          "win_share": share, "avg_forge_turn": avg_turn})
    standings.sort(key=lambda d: (-(d["win_share"] or 0), -d["wins"], d["stem"]))
    return {"standings": standings, "head_to_head": h2h}


# ---- Report -------------------------------------------------------------------------

def report(results):
    """Plain-text standings for a results dict."""
    meta, agg = results["meta"], results["aggregate"]
    titles = {d["stem"]: d["title"] for d in results["decks"]}
    lines = [f"Household pod — Forge {meta['forge']} · {meta['games']} games of "
             f"{meta['pod_size']} seats · {meta['finished']} finished, "
             f"{meta['abandoned']} abandoned · {meta['date']}",
             "Forge's AI is a rough pilot (weak with combo and control): a matchup sketch, "
             "never a verdict. Chance in a 4-seat pod is 25%.", ""]
    for r in agg["standings"]:
        share = "  —  " if r["win_share"] is None else f"{r['win_share'] * 100:4.0f}%"
        turn = ("" if r["avg_forge_turn"] is None else
                f" · ends ~round {round_of(r['avg_forge_turn'], meta['pod_size']):.0f}")
        lines.append(f"{share}  {r['wins']:>2}/{r['finished']:<2} {titles.get(r['stem'], r['stem'])}"
                     f"{turn}" + (f" · {r['abandoned']} abandoned" if r["abandoned"] else ""))
    gaps = [d for d in results["decks"] if d["unsupported"]]
    if gaps:
        lines += ["", "Cards Forge can't play (removed at game start, so these decks play short):"]
        for d in gaps:
            lines.append(f"  {d['title']}: {', '.join(d['unsupported'])}")
    return "\n".join(lines) + "\n"


# ---- Read results back (the app's Matchups page) --------------------------------------

def latest_results(results_dir=RESULTS_DIR):
    """The newest results file as (path, results), or (None, None) when no pod has run.
    Newest by the run's own date, then by file name; a file that won't parse is
    skipped."""
    best = None
    for path in glob.glob(os.path.join(results_dir, "*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                res = json.load(f)
            key = (str(res["meta"]["date"]), os.path.basename(path))
            res["aggregate"]["standings"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if best is None or key > best[0]:
            best = (key, path, res)
    return (best[1], best[2]) if best else (None, None)


def matchups(results, stem):
    """One deck's record against each deck it met, as [{"stem", "met", "won",
    "they_won"}]: most-met first, then the decks that beat it most. A third deck can
    win a 4-seat game, so won + they_won can be less than met."""
    h2h = results["aggregate"]["head_to_head"]
    rows = []
    for other, (won, met) in (h2h.get(stem) or {}).items():
        if met:
            theirs = (h2h.get(other) or {}).get(stem, [0, 0])[0]
            rows.append({"stem": other, "met": met, "won": won, "they_won": theirs})
    rows.sort(key=lambda r: (-r["met"], r["won"] - r["they_won"], r["stem"]))
    return rows


# ---- Install --------------------------------------------------------------------------

def install(dest=DEFAULT_FORGE_DIR, url=FORGE_URL, tarball=None):
    """Download (or reuse `tarball`) and unpack the Forge release. Returns the jar path."""
    jar = os.path.join(dest, JAR)
    if os.path.exists(jar):
        return jar
    os.makedirs(dest, exist_ok=True)
    if tarball is None:
        tarball = os.path.join(os.path.dirname(dest), os.path.basename(url))
        if not (os.path.exists(tarball) and os.path.getsize(tarball) == FORGE_SIZE):
            print(f"downloading Forge {FORGE_VERSION} (~{FORGE_SIZE // 2**20} MB) …",
                  file=sys.stderr)
            urllib.request.urlretrieve(url, tarball)
    if os.path.getsize(tarball) != FORGE_SIZE:
        raise SystemExit(f"error: {tarball} is {os.path.getsize(tarball)} bytes, "
                         f"expected {FORGE_SIZE}")
    # Python's bz2 reads multi-stream archives that some tar builds reject.
    with tarfile.open(tarball, "r:bz2") as tf:
        tf.extractall(dest, filter="data")
    return jar


def load_part(path, pods):
    """The games a stopped run already finished, from its `.part` file, as
    {game number: game}. A game counts only when its seats match this run's schedule,
    and a torn line (the run died mid-write) is skipped."""
    done = {}
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return done
    for ln in lines:
        try:
            g = json.loads(ln)
            n = int(g["game"])
        except (ValueError, KeyError, TypeError):
            continue
        if 1 <= n <= len(pods) and g.get("seats") == pods[n - 1]:
            done[n] = g
    return done


# ---- CLI ------------------------------------------------------------------------------

def _deck_paths(decks_dir, only=None, sleeved_only=False):
    paths = sorted(glob.glob(os.path.join(decks_dir, "*.txt")))
    if only:
        want = set(only)
        paths = [p for p in paths if os.path.splitext(os.path.basename(p))[0] in want]
    if sleeved_only:
        import deck_conflicts
        paths = [p for p in paths if not deck_conflicts.is_study_deck(p)]
    return paths


def main(argv=None):
    ap = argparse.ArgumentParser(description="The household pod: decks play each other in "
                                             "Forge's AI simulator (docs/spec-forge-pod.md).")
    ap.add_argument("--forge", default=DEFAULT_FORGE_DIR, help="the unpacked Forge release")
    ap.add_argument("--install", action="store_true", help="download and unpack Forge")
    ap.add_argument("--tarball", help="with --install: a local copy of the release tarball")
    ap.add_argument("--decks-dir", default=os.path.join(ROOT, "data", "decks"))
    ap.add_argument("--deck", action="append", help="a deck stem (repeatable); default all")
    ap.add_argument("--sleeved-only", action="store_true", help="leave the Lab's theory decks out")
    ap.add_argument("--check", action="store_true", help="export and report unsupported cards only")
    ap.add_argument("--games-per-deck", type=int, default=8)
    ap.add_argument("--workers", type=int, default=2, help="JVMs at once (2 GB heap each)")
    ap.add_argument("--heap", default="2048m")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per game before a draw")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", help="results JSON (default data/reference/pod/<date>.json)")
    ap.add_argument("--resume", action="store_true",
                    help="keep the games a stopped run with the same decks and seed finished")
    ap.add_argument("--report", metavar="RESULTS_JSON", help="print standings for a results file")
    args = ap.parse_args(argv)

    if args.report:
        sys.stdout.write(report(json.load(open(args.report, encoding="utf-8"))))
        return 0
    if args.install:
        print(install(args.forge, tarball=args.tarball))
        return 0
    zip_path = os.path.join(args.forge, "res", "cardsfolder", "cardsfolder.zip")
    if not os.path.exists(zip_path):
        print(f"error: no Forge at {args.forge} — run with --install first", file=sys.stderr)
        return 2
    index = forge_index(zip_path)
    decks = [export_deck(p, index) for p in _deck_paths(args.decks_dir, args.deck,
                                                       args.sleeved_only)]
    for d in decks:
        note = (f"{len(d['unsupported'])} unsupported: {', '.join(d['unsupported'])}"
                if d["unsupported"] else "every card supported")
        print(f"{d['stem']}: {d['cards']} cards · {note}"
              + (f" · {len(d['ai_flagged'])} the AI plays badly" if d["ai_flagged"] else ""))
    if args.check:
        return 0
    work = os.path.join(args.forge, "pod-decks")
    os.makedirs(work, exist_ok=True)
    for d in decks:
        with open(os.path.join(work, d["stem"] + ".dck"), "w", encoding="utf-8",
                  newline="\n") as f:
            f.write(d["dck"])
    pods = schedule([d["stem"] for d in decks], args.games_per_deck, seed=args.seed)
    today = datetime.date.today().isoformat()
    out_path = args.out or os.path.join(RESULTS_DIR, today + ".json")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    # Each game is saved the moment it ends, so a run that dies (memory, a reboot)
    # keeps what it played, and --resume picks up from there. The schedule and game i's
    # seed come from --seed, so the rest are the pods an unbroken run would have played.
    part = out_path + ".part"
    done = load_part(part, pods) if args.resume else {}
    games = [done[n] for n in sorted(done)]
    print(f"{len(pods)} games of {POD_SIZE}, {args.workers} at a time"
          + (f", {len(done)} already played" if done else "") + " …", file=sys.stderr)

    def play(i, seats):
        out, err, secs, wall = run_game(args.forge, work, seats, args.timeout,
                                        seed=args.seed * 100000 + i, heap=args.heap)
        g = parse_game(out, seats, err, wall)
        g.update({"game": i + 1, "seats": seats, "wall_seconds": round(secs, 1)})
        return g

    with open(part, "w", encoding="utf-8", newline="\n") as log, \
            concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for g in games:                 # rewritten whole, so a torn line is dropped
            log.write(json.dumps(g, ensure_ascii=False) + "\n")
        log.flush()
        futures = [pool.submit(play, i, seats) for i, seats in enumerate(pods)
                   if i + 1 not in done]
        for n, fut in enumerate(concurrent.futures.as_completed(futures), len(done) + 1):
            g = fut.result()
            games.append(g)
            log.write(json.dumps(g, ensure_ascii=False) + "\n")
            log.flush()
            print(f"  [{n}/{len(pods)}] game {g['game']}: "
                  + (f"{g['winner']} won" if g["winner"] else f"abandoned ({g['abandoned']})")
                  + f" · {g['wall_seconds']:.0f}s", file=sys.stderr)
    games.sort(key=lambda g: g["game"])
    agg = aggregate(games, [d["stem"] for d in decks])
    results = {
        "meta": {"forge": FORGE_VERSION, "date": today,
                 "pod_size": POD_SIZE, "games": len(games),
                 "finished": sum(1 for g in games if not g["abandoned"]),
                 "abandoned": sum(1 for g in games if g["abandoned"]),
                 "games_per_deck": args.games_per_deck, "timeout": args.timeout,
                 "seed": args.seed},
        "decks": [{k: d[k] for k in ("stem", "title", "study", "cards", "unsupported",
                                      "ai_flagged")} for d in decks],
        "games": games, "aggregate": agg}
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.remove(part)
    sys.stdout.write(report(results))
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
