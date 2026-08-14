# Spec — Infrastructure: Hot Paths & Background Work

**Status: APPROVED by the player 2026-08-14 ("review the spec and begin").**
Phase 1 ☑ · Phase 2 ☑ · Phase 3 ☑ — all shipped 2026-08-14 · Phase 4 = PLAYER DECISION (open) ·
Appendix runbook = ops, runnable once PR #113 merges and the server syncs.

**Why this exists (measured, 2026-08-13, in-session):** the Table-Ready season moved
the app from "render precomputed things" to "run engines inline per request," and the
load profile shifted under it. Measured in the dev sandbox (PythonAnywhere free-tier
CPU is roughly 2–4× slower): `mtglib.load_collection` ≈ **54 ms** for 2,621 cards,
`deckcore.analyze_deck` ≈ **48 ms** — and `webapp/app.py`'s `collection_index()`
re-parses the full CSV from scratch at **21 call sites**, once per request, with zero
caching. `/deck/<stem>/assess` now runs **two** full analyses (its own + the one
inside the optimizer preview that feeds `manual_holds`). `/api/deck/<stem>/ab` runs
**800 seeded games inline** per click, uncached. `/collection/upload` still runs full
Scryfall enrichment **synchronously in-request** (the standing known-deferred item in
`spec-repo-hardening.md` — a host-timeout risk and a one-request CPU-quota bite).

**The verdict this spec implements:** the architecture is right — flat files, stdlib
engines, git as data transport, Actions for network — and is NOT re-platformed here.
The fix is a thin caching/backgrounding layer with the same honesty the engines have.

---

## 0. For the implementing session (Opus 5) — binding contract

**Read first, in order:** `CLAUDE.md` · `docs/codemap.md` (dependency rule +
card-knowledge-flow + deployment matrix) · this spec end to end ·
`docs/spec-table-ready.md` §0 (the twelve invariants — ALL still bind; do not re-read
them into something weaker) · `webapp/sync.py` (the background-thread + status-file
pattern you will copy) · `scripts/goldfish.py` `cache_key`/`sim_for_deck` (the
mtime-keyed disk-cache pattern you will copy).

**Execution order:** Phase 1 → then 2 and 3 in either order (independent). Phase 4 is
a PLAYER DECISION, not code. The Appendix runbook is ops, runnable any time after
PR #113 is merged and the server has synced.

**Rules of engagement:** one PR per phase; squash-merge means resync the branch on
`origin/main` after every merge; suite must stay green (baseline at spec time:
**628 tests, exit 0**) and offline/hermetic; `scripts/` stays stdlib-only; substantial
commit messages; tick this spec + update `docs/handoff.md` when a phase lands. The
optimizer `--apply`/⚡ freeze is UNRELATED to this spec and stays governed by handoff
open item 0. If a decision below turns out wrong against the real code, implement the
closest correct thing and record the deviation in the commit message — never silently
reinterpret.

---

## Phase 1 — Process-level memo cache for the analysis pipeline ☑ SHIPPED 2026-08-14

**Result, measured on the real six decks:** a warm dashboard render of
`the-ur-dragon` went **377 ms → 25 ms** (cold, after `memo.invalidate()`: 70 ms).
All six decks render **byte-identical** warm vs cold. Suite 628 → 647, exit 0.

**Two deviations, both recorded here per §0:**

1. **One PR, not one-per-phase.** The session is confined to the standing feature
   branch `claude/mtg-deckbuilder-research-jlpn7o` (PR #113); opening a branch per
   phase was not authorized. Each phase is one substantial commit on that branch
   instead, which preserves the reviewable unit without inventing branches.
2. **The biggest measured win was not in this spec.** Profiling a *warm* render
   showed 318 ms of 377 ms was a blocking `urlopen` to Commander Spellbook — the
   client cached successes for a week and failures for nothing, so an unreachable
   CSB cost a fresh network attempt on **every deck-page view** (ceiling: the 25 s
   socket timeout when a connection hangs rather than refuses). Fixed in the same
   spirit as the rest of the phase: `spellbook.FAIL_TTL` (5 min) remembers the
   failure — never serves it as data — so an outage costs one attempt per cooldown
   and a recovered service is picked up as soon as it lapses. Without this, the
   memo cache alone would have moved a 377 ms render to ~330 ms and the phase's
   acceptance criterion would have been technically met and practically pointless.

**Also worth knowing for Phase 2/3:** the tripwire the spec asked for (two renders
byte-identical) was **mutation-proved insufficient** — a consumer scribbling on a
borrowed `Card.quantity` sails straight past it, because that field never reaches
the HTML. `tests/test_memo.py` therefore carries BOTH: the byte-identical render
*and* `test_consumers_do_not_mutate_the_shared_analysis`, which fingerprints the
cached objects themselves (every `Card` field, `report`, `assessment`, `mana`)
across render + optimizer preview + cut ranking + `advise_card`. Injecting a real
mutator into `build_dashboard` fails the second test and not the first.

**Goal:** a repeat request against unchanged files never re-parses the collection or
re-runs a deck analysis. Highest win-per-effort in the repo.

### 1a. The cache module — `scripts/memo.py` (new; hub-adjacent, imports NOTHING in-repo)

```python
# The shape to build (names are binding — tests reference them):
memo.get(key_parts, build)      # -> cached value or build() result, stored
memo.stat_key(*paths)           # -> tuple of (path, mtime_ns, size) per path,
                                #    (path, None) for missing files — SAME semantics
                                #    as goldfish._stat, which you should read first
memo.invalidate(substr=None)    # drop entries whose key repr contains substr;
                                #    None drops everything
memo.MAX_ENTRIES = 32           # oldest-inserted evicted past this (a dict is
                                #    insertion-ordered; that is enough — no LRU lib)
```

- **Thread-safety is mandatory:** one `threading.Lock` around all dict operations.
  The hosted app serves requests while `webapp/sync.py`'s daily thread runs; an
  unguarded dict here is a real race, not a theoretical one.
- Stdlib only. No repo imports (`os`, `threading` only) — `mtglib` and `deckcore`
  will import it, so it sits BELOW the hubs in the dependency order.

### 1b. Wire it under `mtglib.load_collection` and `deckcore.analyze_deck`

- `mtglib.load_collection(path)` — cache keyed on `stat_key` of **every file the
  loader reads**, which is more than `path`: it auto-merges
  `collection_attrs.csv`, `collection_attrs.snapshot.csv`, and
  `owned_additions.txt` from the same directory (read the loader; enumerate its
  actual reads rather than trusting this list). Missing files key as
  `(path, None)` so their later creation invalidates.
- `deckcore.analyze_deck(deck_path, collection, refs=None)` — cache keyed on: the
  collection key above (when `collection` is a PATH; **when it is an
  already-loaded list, do NOT cache** — you cannot fingerprint a list, and callers
  who preloaded already paid the cost) + `stat_key(deck_path, <stem>.attrs.csv,
  <stem>.notes.md)` + a reference-directory fingerprint: `stat_key` over every
  `data/reference/*.txt|*.csv` (a sorted `os.scandir` — ~20 stats, microseconds).
  `refs is not None` also bypasses the cache (caller-supplied refs are
  unfingerprintable, same rule).
- **The cached value is FROZEN — this is the load-bearing risk of the whole phase.**
  `analyze_deck` returns dicts and Card lists that callers could mutate, which
  would poison every later hit. Required, in this order:
  1. **Audit for mutation.** Grep every consumer of `analyze_deck`'s return and of
     looked-up collection refs for post-hoc assignment:
     `git grep -nE '\b(a|analysis)\["(report|assessment|enriched|coll)"\]\s*\[?.*=' `
     plus assignments to `.quantity`, `.power`, `.produced`, `.flags`, `.types` on
     cards obtained via `mtglib.lookup`. Known-safe by prior reading (verify, don't
     trust): `deck_stats.analyze` builds NEW merged Cards; `apply_attrs` mutates
     those merged copies, not collection cards; `power.with_declared` mutates the
     assessment **inside** `analyze_deck` before it returns (idempotent — a cached
     value is already stamped). Anything else that mutates: fix the caller to copy,
     never deep-copy in the cache (2,621 Cards per hit defeats the point).
  2. Return `dict(cached)` (shallow outer copy) on every hit so callers adding
     top-level keys can't cross-contaminate.
  3. **The tripwire test** (this is what proves the audit, so it must be real):
     render a deck dashboard twice → byte-identical HTML; then run
     `optimize.optimize(..., apply=False)` + `cut_candidates` + a dashboard render
     interleaved, and assert the final render is byte-identical to a render from a
     COLD cache (`memo.invalidate()` between). If this test fails, a mutator
     escaped the audit — find it, do not weaken the test.
- **Explicit invalidation from every app write path**, belt-and-suspenders over
  mtime keys: PythonAnywhere's filesystem may have coarse mtime granularity, and a
  card-panel edit redirects into an immediate re-render — same-second, same-size
  edits (replacing a card with an equal-length name) could serve stale. Call
  `memo.invalidate(stem)` (deck writes) or `memo.invalidate()` (collection writes)
  from: `deck_card`, `deck_add`, `deck_bracket`, `deck_optimize`,
  `build_deck_save`, `deck_delete`, `pins_move`/`deck_pin` (pins feed optimize
  through `pinned_elsewhere` — NOT through `analyze_deck`; trace it and invalidate
  only if a cached value actually embeds pin state), `/collection/add`,
  `/collection/upload`, and `webapp/sync.py` after a pull that moved HEAD.
- `collection_index()` in `webapp/app.py` gets the cached load for free once
  `load_collection` is wired; keep building the index per call unless profiling
  shows it matters (`index_by_name` is a dict build, ~ms).

### 1c. Explicitly NOT in scope (do not implement)

- Threading `analysis=` through `optimize.optimize` to kill the assess packet's
  double-analysis: **redundant once this cache exists** — the second
  `analyze_deck` inside the preview becomes a cache hit. Doing both would be
  busywork; the cache is the fix.
- Caching rendered dashboard HTML. `generate()` output embeds sim results already
  disk-cached by `sim_for_deck`; with 1b, the remaining render cost is template
  assembly (~fast). Revisit only with host-side timings in hand.

### 1d. Tests (hermetic; `tests/test_memo.py` + additions where named)

- `memo.get` builds once, hits second; `stat_key` changes on touch (write a byte),
  on delete, on create-from-missing; eviction past `MAX_ENTRIES`; `invalidate`
  substring semantics; a lock exists (assert `memo._LOCK` is a `threading.Lock` —
  cheap, but pins the intent against a "simplifying" refactor).
- `load_collection` cached: monkeypatch-count the CSV `open` (or `detect_format`)
  and assert one parse across two loads; then touch `owned_additions.txt` and
  assert a re-parse — the merged-inputs key is the part a naive implementation
  gets wrong.
- `analyze_deck` cached + the byte-identical tripwire from 1b.3.
- List-input and `refs=` bypass: pass a loaded list, assert no cache entry.
- Write-path invalidation: a deck edit through the app followed by an immediate
  re-render reflects the edit even when the mtime is FORCED equal
  (`os.utime(path, ns=(old, old))` after the write — simulate the coarse-clock
  host; this is the test that justifies explicit invalidation existing at all).

---

## Phase 2 — Disk-cache the A/B simulation ☑ SHIPPED 2026-08-14

**Result:** `goldfish.ab_for_deck()` — the repeat shift-click is a file read
(115 ms → 0 ms on a real deck at 200 games). The CLI's `--ab` goes through the
same wrapper, so `--no-cache` governs both surfaces from one place. Both guards
mutation-proved: deleting `not rep.get("error")` from the write condition fails
`test_ab_errors_are_never_cached`; dropping the swap out of the key fails
`test_ab_cache_key_separates_swaps_and_normalizes_names`. Suite 647 → 655.

Added beyond the spec's list: the endpoint itself had **no route-level test at
all**, so the wiring change had nothing holding it. `test_the_ab_endpoint_serves_
the_second_click_from_disk` and `..._still_refuses_a_name_it_cannot_resolve` now
cover it.

**Goal:** the Replace-flow preview (`/api/deck/<stem>/ab`, shift-click) and repeat
CLI `--ab` runs hit disk instead of re-running 800 games on shared CPU.

- New `goldfish.ab_for_deck(deck_path, collection, out_name, in_name, *, games,
  seed, turns, mulligan, collection_path=None, cache=True)` — the cached wrapper,
  mirroring `sim_for_deck`'s structure exactly: same `CACHE_DIR` (so
  `tests/conftest.py`'s session fixture already redirects it — verify, don't
  assume), filename `ab-<stem>-<hash>.json` where the hash covers `cache_key(...)`
  **plus** `out`/`in` normalized via `mtglib._norm`, `REPORT_SCHEMA`, and
  `disruption=None` (the API never passes disruption; if that changes, the key
  already carries it).
- The payload cached is `simulate_ab`'s full return. On read, verify the stored
  `schema` matches (the `sim_for_deck` pattern) — stale-shape entries re-run.
- `webapp/app.py`'s `api_deck_ab` switches to it. The route's 400-game default
  stays; a cache hit makes the repeat shift-click instant, which is the actual UX
  complaint being fixed.
- **Traps:** `simulate_ab` returns an `error` payload for unknown names — do NOT
  cache errors (a typo would pin itself). The A/A-exact-zero property must be
  provable through the cache: add to `tests/test_goldfish.py` an A/A run, cache
  cleared, A/A again → byte-identical JSON both times and all deltas exactly 0.0.
- Eviction: none, matching `sim_for_deck` (entries are small JSON; the cache dir
  is gitignored). Note this in the module docstring rather than inventing a
  pruner nobody asked for.

---

## Phase 3 — Background upload enrichment ☑ SHIPPED 2026-08-14

**Result:** `/collection/upload` returns immediately; `webapp/enrich_bg.py` runs
`carddb.enrich_api` in a daemon thread and `/collection` renders its status
(running / done *n/total matched* / error / **interrupted**). The standing
known-deferred item in `spec-repo-hardening.md` is closed there too — as is the
other one on that line, since Phase 11 already made `sw.js` derive its cache
version from git HEAD.

`carddb`'s writer was **not** atomic, so it was fixed in carddb rather than
wrapped here: `write_attrs_csv` (tmp + `os.replace`) now serves both the API and
bulk paths, and `test_both_enrichment_paths_use_the_atomic_writer` fails if a
future edit re-opens the destination directly. Mutation-proved: reverting the
write to a plain `open(…, "w")` fails `test_attrs_are_written_atomically`, which
reads the file from inside the write and asserts a reader only ever sees the old
complete version.

One test outside this file had to change: `test_upload_writes_the_nine_column_
attrs_file` asserted a synchronous round trip. It now waits on the status file —
testing the real backgrounded path rather than a shortcut production no longer
takes. A session-scoped conftest fixture redirects `enrich_bg.STATUS` into tmp,
the same hermetic rule the goldfish cache follows.

**Goal:** `/collection/upload` returns immediately; enrichment runs in a daemon
thread; the player sees honest progress. Closes the standing known-deferred item.

- **Copy the `webapp/sync.py` pattern wholesale** — it already solved every hard
  part of this on this exact host: daemon thread, JSON status file, "already
  running" guard, TTL-stale status handling. Build `webapp/enrich_bg.py` (or a
  section of sync.py — implementer's call, but do not invent a third pattern):
  - `start(csv_path)` → refuses (with a status message) if a run is live; else
    spawns a daemon thread running `carddb.enrich_api` → status JSON
    (`data/cache/enrich_status.json`, gitignored) with
    `{when, state: running|done|error|interrupted, matched, total, detail}`.
  - **Atomic output is mandatory:** the thread writes `collection_attrs.csv` via
    tmp-file + `os.replace` — a half-written attrs file being read mid-run is a
    data-integrity bug, not a performance bug. Check whether `carddb`'s writer is
    already atomic; if not, make the writer atomic IN CARDDB (both API and bulk
    paths — one fix, every caller safe) rather than wrapping it here.
  - On completion: `memo.invalidate()` (Phase 1's cache holds the pre-enrichment
    collection).
  - **PythonAnywhere reality:** daemon threads die on app reload (the WSGI touch,
    a deploy, the daily sync's reload). A status stuck in `running` past a
    generous TTL (30 min) must render as `interrupted — re-upload to retry`, the
    same honest-stale approach `sync.status_view` takes. Do not build resumption.
- Route changes: `/collection/upload` saves the CSV (exactly as now — private
  path, never the snapshot; touch NOTHING about where it writes), calls
  `start()`, flashes "Upload saved — enrichment running in the background", and
  redirects. `/collection` renders the status line (running/done/error/
  interrupted) from the status file. The identity-approximation honesty labels
  already handle the not-yet-enriched window — that is the degrade story and it
  already exists; point the status copy at it ("colors/types appear as enrichment
  completes").
- Tests: monkeypatch the enrich function; assert the route returns before it
  finishes (event/flag pattern), the already-running refusal, the error path
  writing `state: error`, the TTL-interrupted rendering, and the atomic write
  (no partial file visible under a reader opened mid-write — simulate with the
  tmp-name check: the real path either doesn't exist or is complete).

---

## Phase 4 — Host tier (PLAYER DECISION — no code until decided)

The free tier works and everything above keeps it comfortable. The $5 Hacker plan
erases three standing hacks: the quarterly "Run until 3 months" keepalive, the
in-app poor-man's-cron sync thread (becomes a real Scheduled Task running
`sync_server.sh`), and CPU-quota anxiety around the sims. **If the player opts in:**
create a Scheduled Task for the sync, set `MTG_AUTO_SYNC=0`, delete the keepalive
reminder from handoff, and record the change in `docs/handoff.md` "Where the app
runs". If not: nothing changes; this phase closes as "declined, revisit when the
hacks annoy".

---

## Appendix — Runbook: lifting the optimizer freeze from the server (ops, no code)

The acceptance step for handoff open item 0 needs the **full private CSV**, which
exists in exactly two places: the player's PC and the hosted server. After PR #113
merges and the server's daily sync (or the Decks-page ⇅ button) has pulled it, a
**PythonAnywhere Bash console**:

```bash
cd ~/MTGDeckBuilder    # (the server clone's actual path — check `pwd` habits)
python3 scripts/optimize.py --all --collection data/collection/collection.csv
```

PREVIEW ONLY — no `--apply`. Acceptance criteria (from `spec-table-ready.md`
Phase 8): zero field-inferior cut proposals across all six decks; `manual_holds`
lines are expected and correct (Hojo et al.); "already aligned" or field-superior
swaps only. If it passes: update `docs/handoff.md` open item 0 — the freeze is
LIFTED — and the CLAUDE.md top-25-overlap check governs the first real `--apply`.
If it fails: capture the full output into a new section of
`docs/spec-optimizer-hardening.md` and the freeze stands. Either way the result is
committed via the server's own sync (it stages deck-adjacent paths only — the
handoff edit rides the next session instead if the sync won't carry it).

---

## Acceptance (spec-level)

- A warm second render of any deck page parses the collection **zero** times
  (proven by the instrumented test, not by feel).
- The byte-identical tripwire holds across interleaved optimize/cuts/dashboard.
- A same-second, same-size deck edit is never served stale (forced-utime test).
- Repeat A/B of the same swap is a disk hit; A/A stays exactly 0.0 through the
  cache.
- An upload returns immediately; a mid-enrichment reader never sees a partial
  attrs file; a killed thread renders as `interrupted`, never as `running`
  forever.
- Suite green throughout; `scripts/` stdlib-only; no invariant of
  `spec-table-ready.md` §0 weakened.
