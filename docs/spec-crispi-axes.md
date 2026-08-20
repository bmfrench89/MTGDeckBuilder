# Spec — CRISPI axes for power.py (four honest numbers, one retired headline)

**Status: READY FOR IMPLEMENTATION — handoff to the next implementing session
(written by Fable 5, 2026-08-20, from the research in
`.claude/skills/mtg-deckbuilder/references/strategy-shapes.md`).**
Research PR: #140. Nothing here is started; every claim below was re-verified against
the code on 2026-08-20, including two corrections to #140's own audit.

## Session rules (house rules that bit this season — do not relearn them)

- **Tool contract first.** It is injected by the SessionStart hook; follow it. Any card
  named for a curated list goes through `data/reference/verify-queue.txt` + a branch push,
  never web search past 3 cards.
- **Dependencies point inward** (`docs/codemap.md`). Engines never import engines;
  `deckcore` is the hub that composes them — `_analyze_deck` already imports
  `deck_stats`, `combo_detector` and `power` locally. **Route new cross-engine data
  through `deckcore`, never by importing `goldfish` from `power`.**
- `scripts/` is stdlib-only; tests are offline/hermetic in `tmp_path`; dashboards stay
  one self-contained file; `memo`'s byte-identical-render tripwire must keep passing.
- The goldfish A/B pairs positionally (common random numbers). **Nothing may re-sort a
  compiled deck**; `test_goldfish`'s A/A-exact-zero test is the tripwire.
- Squash-merge workflow; re-sync the branch to `origin/main` before starting.

## The defect, with its receipts

`power.py --rank` printed this on 2026-08-19 (reproducible):

```
bartolome-del-presidio-600-combos   Bracket 4 Optimized   31/100 Casual
```

Bracket 4 and "31/100 Casual" in one row. The bracket subsystem sees two-card infinites;
the 0–100 sees no tutors, no fast mana, no draw. Both are right about what they measure —
**the composite headline is the bug**. This is exactly the failure that made DeckCheck
retire single-number power levels for CRISPI (Consistency, Resilience, Interaction,
Speed) in 2026: *"power levels were competing with brackets, and the number was opaque."*

## What already exists — build on it, do not rebuild it

Re-audited against the code (this corrects #140, which understated the repo twice):

| Axis | Today |
|---|---|
| Interaction | `power.assess` counts it (`signals.interaction`, 10–14 across the stable) |
| Consistency | lands + tutors counted; **redundancy not counted anywhere** |
| Speed | **`goldfish.py` already computes the fundamental turn**: the `clock` block's `median_first_kill`, `median_table_kill`, `kill_rate`, `mean_damage_by_turn_end`. `power.py` never reads it |
| Resilience | `goldfish.py --disruption standard` (Table-Ready Phase 10, EXPERIMENT, off by default) already models one wipe (turn 5–6), spot removal every 3 turns, commander tax. No protection *counting* exists anywhere (`grep -riE "protect|resilien|redundan" scripts/` → only dashboard cut-protection, unrelated) |

**Hard boundary:** `docs/spec-pod-simulation.md` is BACKLOGGED by player decision
2026-08-13. Statistical opponents beyond the Phase 10 probe are out of scope here.
This spec consumes shipped machinery only.

## Phase A — Speed (smallest change, largest honesty gain)

The number exists; wire it through the hub:

1. `deckcore._analyze_deck` already stashes a goldfish `sim` for the dashboard path —
   confirm where (build_dashboard attaches it; see the memoized `analyze_deck`
   docstring's warning about per-hit top-level keys). Expose the cached goldfish result
   (or just its `clock` dict) in the analysis dict under a stable key, using the
   existing cached loader so cost is paid once. **Respect the memo contract**: values on
   a cache hit are shared and read-only.
2. `power.assess` gains an optional `clock=None` parameter (deckcore passes it; the bare
   CLI path may pass None and must degrade to today's output byte-identically).
3. Score: map `median_first_kill` onto the researched bands — goldfish kill by turn ~7 ≈
   the Bracket-2 floor; earlier is faster. Emit it as a **separate axis**, not a weight
   inside the 0–100. When `clock.have_data` is false or kill_rate is ~0 (control shells
   that goldfish cannot kill with), the axis prints **"unmeasured (no combat clock)"** —
   an honest label, never a silent 0. That label matters: Y'shtola wins through drain
   loops the goldfish cannot see; do not let the axis call her "slow" — call her
   unmeasured and say why.
4. Determinism: same seed policy as the dashboard's goldfish panel; the axis must be
   byte-stable across runs (memo tripwire).

## Phase B — Resilience (two counted layers + one labelled experiment)

1. **Counted, layer 1 — protection.** A curated `data/reference/protection_staples.csv`
   (name + why), seeded ONLY with verified owned cards (queue names through
   `verify-queue.txt`; the runner confirms text). Research targets to print beside the
   count: **5–8 when the commander/engine must live, 2–4 when the deck rebuilds.**
   Adding an oracle-derived `protect` flag to `oracle_flags.py` is allowed but is a
   **vocabulary change: bump `VOCAB_VERSION`, honour the FlagsVer contract** (flags and
   version are one write; pre-bump files read as the old version, never as current).
2. **Counted, layer 2 — commander-dependence.** The one-question test from the research:
   "if the commander is removed twice, does the deck still function?" Approximate it
   honestly: fraction of nonland cards whose role depends on the commander is NOT
   derivable from data we have — so v1 ships the *proxy* pair (protection count,
   recursion count via existing `classify` roles) plus a `# Resilience:` deck-header
   override the player can ratify per deck, mirroring `# Bracket:`'s
   declared-vs-detected pattern in `power.read_declared_bracket`.
3. **Experiment, clearly labelled.** Offer `--disruption` A/B deltas
   (cast_rate / mean_cast_turn / clock under `standard` vs `none`) in the goldfish CLI
   report as a *labelled experiment line* — but **do NOT fold it into the axis score by
   default**. Phase 10's own caveat ("a crude stand-in for opponents") is printed with
   it. Player ratification required before it ever becomes part of the number.

## Phase C — Consistency gains redundancy

Count effect-cluster depth from existing `classify` roles + `card_notes` engine tags:
for the deck's top engine roles, how many interchangeable copies exist? Print against
the researched bands: **5–8 standard, 8–12 for stall-without-it enablers, 8 ≈ in hand
by turn 3.** The stable's signature (tutors 0–1 everywhere, draw 7–15) means redundancy
IS this collection's consistency mechanism — the axis should say that in words, the way
`manabase.py` prints "identity approx." labels.

## Phase D — Presentation: the axes replace the headline

1. CLI (`power.py print_one/--rank`), assess packet, and dashboard tile show **four
   axes + the bracket**, never a single composite next to the bracket. The 0–100
   survives one release as `legacy power` in `--json` only (consumers: webapp
   leaderboard sorts — check `webapp/app.py` `/` route), then the player decides its
   fate. **Never print bracket and a composite adjective in the same row again** — that
   is the defect line.
2. Both surfaces share `generate()` — check CLI dashboards *and* the app when touching
   the tile (two-surfaces trap in CLAUDE.md).
3. `docs/power-and-brackets.md` gets rewritten to describe axes + bracket; handoff
   updated; tick nothing in the interactive-analytics tracker (this is not one of its
   phases).

## Tests (house style: docstrings say WHY; offline; tmp_path)

- Speed axis: clock present → scored; `clock=None` → byte-identical legacy output;
  drain-shell deck (no creatures) → "unmeasured" label, never 0. Seeded determinism.
- Resilience: protection CSV parsed; `# Resilience:` header round-trips
  declared-vs-detected like `# Bracket:`; FlagsVer bump guarded if the flag route is
  taken (extend `test_carddb_verify`/`test_mtglib` patterns).
- Consistency: redundancy counts on a synthetic tmp_path deck with known clusters.
- Presentation: the defect line is a regression test — assert the rank output never
  emits a bracket AND a composite tier word in one row.
- The untouched suites stay green: 849 at handoff time (memo, goldfish A/A, dashboard
  byte-identical, tool-contract guard — the new CSV/reference must be added to the
  contract if it becomes session-facing, or the guard will rightly fail the build).

## Acceptance

1. `power.py --rank` on the real stable shows four axes + bracket per deck; the
   Bartolomé row reads Bracket 4 with fast/consistent-combo axes and NO "Casual".
2. Y'shtola reads Speed: unmeasured (no combat clock) — with the reason printed.
3. Second run of everything is byte-identical (memo tripwire); 849+ tests pass.
4. No new engine→engine import (`grep "import goldfish" scripts/power.py` is empty).

## Deliberate non-goals

- No pod simulation, no new disruption profiles, no promotion of Phase 10 (backlogged).
- No new network calls anywhere; protection list verified via the runner queue only.
- No change to bracket detection or the optimizer.
- No weights/tuning debates in v1: axes are printed raw with their bands; a composite
  "Performance Index" average is explicitly deferred to player ratification.

## Open questions for the player (ask before Phase B.3 and D.1; everything else proceeds)

1. May the disruption A/B delta ever feed the Resilience *score*, or stay a printed
   experiment forever?
2. Does the legacy 0–100 die immediately or live one release in `--json`?
