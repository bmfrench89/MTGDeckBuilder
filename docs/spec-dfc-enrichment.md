# Spec — DFC enrichment: 26 double-faced cards have no attributes

**Status: ☐ DRAFT FOR PLAYER REVIEW — do not implement until approved.** Written
2026-08-16 after a measured investigation (deep-research pass + a live probe on the
deck-verify runner). Player asked for the issue identified fully, researched, and
spec'd before any code changes.

**Branch when approved:** `claude/deck-export-html-pdf-ofyd6d` (or a fresh one) ·
one PR, squash-merged.

---

## 0. For the implementing session — read this before writing any code

**Read first:** `CLAUDE.md` · `docs/codemap.md` · `docs/spec-network-and-attrs.md`
(§3 PRIVACY especially) · this spec end to end · `scripts/carddb.py` lines 262–470 ·
`.github/workflows/attrs-snapshot.yml`.

**Invariants this work can break:**

1. `scripts/` is **stdlib-only**. Every fix below is `urllib` + `time` + `csv`.
2. Network clients **degrade, never crash**, and are **disk-cached**. (§1.6 is a live
   violation of the caching half.)
3. **Empty vs absent is load-bearing.** An empty attrs cell = "enriched, produces
   nothing"; an absent column = "unknown, fall back AND say so". A missing *row* is
   the absent case for every column at once — which is exactly why §2's land misfires
   are the severe half of this bug.
4. The **` // ` trap**: never `split("//")`. All name handling goes through
   `mtglib.front_face` / `_norm` / `name_keys` / `lookup`. This spec adds a *new*
   caller of `front_face`, so the rule tightens rather than loosens.
5. Tests are **offline and hermetic** — `tmp_path` only, network monkeypatched.
6. The committed snapshot carries **no Scryfall ids** (`--no-ids`, privacy).
7. Substantial commit messages; update `docs/handoff.md` when this lands.

---

## 1. The bug, as measured

### 1.1 Symptom
26 of the player's 40 `Front // Back` cards have **no row** in
`data/collection/collection_attrs.snapshot.csv` — not a blank row, no row. All 2,651
single-faced cards are enriched. Those 26 therefore carry no Type, MV, Colors,
Sub-types, Produced, Flags or Power anywhere in the app.

### 1.2 Root cause, in four links

**(a) Scryfall's `/cards/collection` `name` identifier matches a SINGLE FACE, never the
combined `Front // Back` string.** Measured on the runner 2026-08-16, run
`31961993767`, using `verify_cards` — which hits the *same endpoint with the same
identifier shape* as enrichment and labels each row `via scryfall` (exact matched) or
`via fuzzy` (exact failed, retry rescued):

| Query submitted | Result |
|---|---|
| `Murderous Rider` (front) | **via scryfall** → resolved to `Murderous Rider // Swift End` |
| `Marang River Regent` (front) | **via scryfall** → `Marang River Regent // Coil and Catch` |
| `Scavenger Regent` (front) | **via scryfall** → `Scavenger Regent // Exude Toxin` |
| `Gollum, Silent Slinker` (front) | **via scryfall** → `Gollum, Silent Slinker // Meager Meal` |
| `Smaug, the Great Calamity` (front) | **via scryfall** → `Smaug, the Great Calamity // Spew Flame` |
| `Swift End` (**back** face) | **via scryfall** → `Murderous Rider // Swift End` |
| `Murderous Rider // Swift End` (combined) | **via fuzzy** ← exact FAILED |
| `Scavenger Regent // Exude Toxin` (combined) | **via fuzzy** ← exact FAILED |
| `Sol Ring` (single-faced control) | **via scryfall** |

5/5 front faces and the back face exact-match; both combined forms fail. The control
proves the probe itself sound. **This is the measured foundation of the whole fix.**

**(b) So every DFC misses round 1, every run.** `_best_identifier`
(`carddb.py:290-301`) submits `{"name": card.name}` — the *full* name — whenever the
input has no id/set+number, which is always true of the name-only snapshot the
committed-artifact workflow runs on. Arithmetic proof from the production log (run
`31902112537`): round 1 resolved exactly **2651/2691**, and 2691 − 2651 = **40** =
exactly the DFC count.

**(c) All 40 then fall into the fuzzy rescue pass**, one sequential
`GET /cards/named?fuzzy=` each with `time.sleep(0.1)` — ~10 req/s, at or over
Scryfall's asked-for pacing.

**(d) `_fetch_named_fuzzy` swallows the throttle.** `carddb.py:551-559` wraps its one
GET in `except Exception: return None`, documented "never raises". The caller
(`:417-420`) turns that `None` into a bare `continue`: **no counter, no log line, and
no distinction between HTTP 429, 503, 404, a URLError, or a genuine "no such card".**
Unlike `_post_collection` (`:265-287`), which has a proper `(5, 15, 30, 60)` backoff
ladder for 429/503, the fuzzy path has no retry and no backoff at all — so once
Scryfall starts throttling, the loop keeps firing every ~0.2 s and never lets the
cooldown window close. Everything after the first throttle is lost.

### 1.3 Proof it is a transport wall, not a per-card property
Across the three committed snapshot runs, DFC coverage is a **contiguous prefix in
file order that moves between runs**: 20/37, 19/37, 14/40 — while non-DFC resolution is
exactly 100.0% every time. A per-card explanation ("these names are unresolvable")
cannot produce a boundary that moves. The snapshot is alphabetically sorted, which is
why the boundary *looks* alphabetical.

Timing corroborates: the whole enrich step ran **54.14 s**, so 26 × 60 s timeouts are
arithmetically impossible — every one of the 26 failures returned *immediately*, i.e.
an HTTP status, not a hang.

### 1.4 Why nothing caught it
- `--min-match 95` passed at **2665/2691 = 99.03 %**.
- A row-count regression gate would **also** have passed: the most recent run wrote
  **62 more rows** than the previous one while losing **5 more DFCs**.
- The `unmatched` list is computed (`:443`) and then **discarded at the print
  boundary** — the diagnosis existed in memory the whole time and was thrown away.

### 1.5 A previously-fixed bug has silently regressed
`carddb.py:327` carries this comment:

> *Omen/adventure/MDFC layouts can carry type_line/cmc only on the FACES. Without this
> fallback "Scavenger Regent // Exude Toxin" enriched with an empty Type, and the
> name-based land heuristic then misread a Dragon creature as a land.*

That card is **in the failing 26 today**. The earlier fix is correct and still there —
it simply never runs, because the card no longer reaches enrichment at all. Same
symptom, different cause, and the guard that was supposed to prevent it can't see it.

### 1.6 Two standing violations found on the way
- **The fuzzy pass bypasses the disk cache entirely.** `_cache_get`/`_cache_put`
  (`:481-507`) are called only from `verify_cards`. Enrichment's fuzzy call goes
  straight to the network, so nothing accumulates between runs and every run re-pays
  for every miss — against the repo's "network clients must be disk-cached" rule.
- **`_best_identifier`'s docstring asserts the opposite of measured behaviour**
  ("resolves attributes fine, incl. DFC/adventure front names"), while
  `_fetch_named_fuzzy`'s docstring at `:553` half-knows the truth ("a back-face name
  that `/cards/collection`'s exact matching rejects"). The two contradict each other,
  and the wrong one is the one a future session will trust.

---

## 2. Impact — one tier is honest, one tier is a lie

**Tier 1 — honest unknown (24 of 26).** `classify()` returns `{'other'}`; they cost
role-count accuracy and curve presence but never assert anything false.
`deck_sections` handles them perfectly (routes to the explicit `Unsorted` section).

**Tier 2 — silently WRONG (2 of 26).** With no types, `Card.is_land` falls through to
the `_LAND_HINTS` substring heuristic, and `classify()` checks `is_land` **first** and
returns early — before the curated lists, oracle flags or type fallback ever run:

| Card | What it is | Why it misfires |
|---|---|---|
| `Marang River Regent // Coil and Catch` | **Dragon creature** (verified: `Creature — Dragon // Instant — Omen`) | hint `"river"` |
| `Scavenger Regent // Exude Toxin` | **Dragon creature** (verified: `Creature — Dragon // Sorcery — Omen`) | `"cave"` matched **inside "S-cave-nger"** |

The second is a separate latent defect worth its own line: `_LAND_HINTS` matches on
**bare substrings**, so any card whose name merely contains a hint word can be
misread. Ten collection cards contain the substring "cave"; **49 non-land cards
collection-wide have names that would trip a land hint** if their attrs row ever went
missing. That number is the blast radius of *any* future enrichment drop, not just
this one.

**Where a wrong `is_land` propagates:**
- `optimize.py:418` routes it into the **manabase** pass as a land candidate — and
  EDHREC cannot veto it (the field snapshot's `lands` key correctly omits Scavenger
  Regent, but the code path never consults it for this). Worst concrete outcome: the
  optimizer swaps a 2-mana creature into a deck **in place of a real land** and reports
  it as a manabase improvement.
- `auto_build` both **inflates** the land count and **shorts the basics** — the
  misfire counts toward `n_nonbasic_land`, which is subtracted from the basics budget,
  so a fresh build ships one real land short while reporting a full manabase.
- `auto_build` then **launders the guess**: it writes the card into a literal
  `# --- Lands ---` section, and thereafter the deck's own section beats the heuristic
  (the Hidden Lair layering) — a machine guess becomes indistinguishable from player
  intent.
- `goldfish` treats them as playable colorless lands, and its `have_data` honesty gate
  counts **only nonlands**, so a card miscast as a land is removed from the denominator
  and can never trip the gate.
- `deck_stats` counts them as lands with **no caveat on the count itself** (the
  identity-basis caveat is about source precision, a different claim).

**Severity today: latent, not active.** Neither misfiring card is in any of the nine
decks right now. The mechanism is live and the at-risk pool is 49 cards, but nothing
in the current stable is wrong because of it. That honesty matters for prioritisation:
this is a *correctness-of-the-machine* fix, not a fire.

---

## 3. The fix

Five parts. **A is the cure; B–D are why it can't come back; E is cleanup.**

### Phase A — resolve DFCs in round 1 (the actual fix)
In `_best_identifier`'s name branch only, submit **`mtglib.front_face(card.name)`**
instead of the full name, while keeping the keymap key on the **full** normalized name.

Why the response still matches: `_response_keys` (`:304-317`) already emits
`mtglib.name_keys(name)` for the returned card, which is `{full, front_face}` — so a
true DFC hit (returned as `Front // Back`) matches the full-name key, and a
single-faced card that merely shares a front-face string matches on its own name. No
change needed to `_response_keys`.

Expected effect: **all 40 DFCs resolve in round 1**, the fuzzy pass drops from ~40
requests to ~0, and the rate-limit exposure that caused this disappears rather than
being merely survivable.

Also rewrite the `_best_identifier` docstring (§1.6) — it currently teaches the bug.

### Phase B — one shared request helper with backoff
Extract `_request_json(url, data=None, retries=4)` inside `carddb`, carrying the
existing `(5, 15, 30, 60)` ladder, and have **both** `_post_collection` and
`_fetch_named_fuzzy` call it. The ladder is already hand-tuned to Scryfall's ~30 s
cooldown and is currently duplicated verbatim in `gen_card_notes.py:78-84`.

**Hazard to respect:** `_fetch_named_fuzzy`'s "never raises" contract is load-bearing
for `verify_cards` (`:617-628` treats `None` as "no Scryfall match → unverified"). So
give it a **three-way** outcome: `404 → None` (genuine miss, unchanged), everything
else **raises after the ladder**, and `verify_cards` wraps its step-3 call in the same
`try/except` shape it already uses at `:598`. An outage then yields UNVERIFIED rows,
never a false "no such card".

### Phase C — pacing
Raise the fuzzy-pass delay from `0.1` to **`0.7` s**. This is not a guess: it is the
repo's own empirically-derived number, documented in `scripts/proxy_sheet.py:186-187`
(*"700ms stays under Scryfall's ~2/s API limit; 400ms was OVER it, so a dead batch
turned into a page of 429 broken-image glyphs"*). After Phase A the fuzzy pass should
be near-empty anyway, so the cost is ~0.

### Phase D — make the silent drop impossible
1. Count **transport failures separately from genuine misses**, and return both.
2. Print the `unmatched` list (or the first N) unconditionally — it is already computed
   and thrown away.
3. **A transport-error drop must fail the run**, not commit a partial file. Exit codes
   `2` (network/total) and `3` (below `--min-match`) exist; add a distinct signal for
   "resolution incomplete due to transport", or fold it into `2`.
4. **Strengthen the gate**, since both `--min-match 95` and a row-count regression are
   proven blind here: add a **per-category floor** — e.g. DFC coverage must be ≥ 95 %
   of DFCs *in this run's own input*, measured independently of the overall rate.

### Phase E — wire the fuzzy pass into the existing disk cache
Use the 30-day `VERIFY_CACHE_DIR` that `verify_cards` already maintains, so runs
improve monotonically and a re-run costs zero requests. Closes §1.6's caching
violation.

### Phase F — backfill
After A–E land, one `workflow_dispatch` of `attrs-snapshot` regenerates the committed
file with all 40 DFCs. No manual data entry, and nothing to hand-write.

---

## 4. Deliberately NOT doing

- **Not** hardening only the fuzzy pass. That treats the symptom; Phase A removes the
  40 unnecessary requests entirely.
- **Not** switching the committed-snapshot job to the private CSV for stronger
  identifiers (set + collector number). The name-only input is a deliberate privacy
  boundary (`spec-network-and-attrs.md` §3) and Phase A makes name-only sufficient.
- **Not** adding a row-count regression gate as the primary defence — measured blind
  (§1.4).
- **Not** touching `_LAND_HINTS` in this spec. The substring bug ("S-cave-nger") is
  real and worth fixing, but it is a *second* defect on a *different* engine, and
  bundling it would make this PR's blast radius the whole classifier. **Recommend a
  follow-up spec**; see §7.
- **Not** fixing `download_bulk()`. The research pass reported Scryfall's bulk-data
  format changed in July 2026 in a way that may already break it — flagged as
  unverified, out of scope, and noted in §7.

---

## 5. Tests (offline, hermetic, `tmp_path`)

Extend `tests/test_carddb_enrich.py` / `test_carddb.py`:

1. **The identifier**: `_best_identifier` on a `Front // Back` card submits the
   **front face** and keys on the **full** name. On a single-faced card, unchanged.
2. **Round-trip match**: a fake Scryfall response named `Front // Back` matches a
   request submitted as `Front`, via `_response_keys` — the seam Phase A depends on.
3. **The `SP//dr` guard**: a card whose name contains a bare `//` with no spaces is
   submitted **whole**, never split. (`front_face` already guarantees this; the test
   pins it at this new call site.)
4. **Transport vs miss**: monkeypatched 429 → the card is counted as a *transport
   failure*, the run does **not** exit 0, and the CSV is **not** written as partial. A
   monkeypatched 404 → counted as a genuine miss, run proceeds.
5. **Backoff shared**: `_fetch_named_fuzzy` retries a 429 on the ladder and raises on
   exhaustion; `verify_cards` still yields an UNVERIFIED row rather than propagating.
6. **The gate bites**: a synthetic run resolving 99 % overall but only 40 % of DFCs
   **fails** — the precise shape that shipped today.
7. **Cache**: a second fuzzy lookup for the same name issues **zero** requests.

---

## 6. Acceptance

- `pytest` exit 0 offline; suite count recorded before/after in the commit body.
- `scripts/` still imports bare with Flask uninstalled.
- **The real proof is a runner run**: `workflow_dispatch` `attrs-snapshot`, then
  confirm `collection_attrs.snapshot.csv` contains **40/40** DFCs, that the log shows
  the fuzzy pass issuing ~0 requests, and that `classify()` on
  `Marang River Regent // Coil and Catch` and `Scavenger Regent // Exude Toxin` returns
  a **creature**, not `{'land'}`.
- Re-run the optimizer preview on all nine decks: still "already aligned" (this fix
  must not churn any deck).

---

## 7. Open questions for the player

1. **Scope** — ship A–F as one PR, or split Phase A (the cure, small) from B–E (the
   hardening, larger)?
2. **The `_LAND_HINTS` substring bug** — "S-cave-nger" matching "cave" is a live
   defect independent of enrichment. Follow-up spec, fold in here, or leave it?
3. **`download_bulk()`** — reported as possibly broken by a July 2026 Scryfall format
   change. Unverified. Worth a probe, or leave it (the API path is the default and
   works)?
