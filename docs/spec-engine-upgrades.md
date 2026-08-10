# Spec — Engine upgrades: production-aware enrichment, a rules layer, goldfish Monte Carlo, subagents

**Status:** ☐ design awaiting owner interview, 2026-08-10 · nothing implemented ·
four workstreams (A–D), each with implementation-ready tasks sized for a fresh
session with no conversation context. Every current-state claim below was
verified against the code at `c23b3ca` by independent review and adversarial
fact-check passes; corrections from those passes are folded in. Suite baseline
today: **259 tests collected** (CLAUDE.md's "231" is stale — fixed by the first
landing PR, task X-1).

**Interview first:** section 9 lists every decision the owner must ratify, each
with a recommendation. Everything else in this document is settled design.

---

## 1. Why these four

The engine's known soft spots, each matched to the cheapest fix that ships:

- **A. Production-aware enrichment.** `manabase.py` admits its color sources are
  approximated from color *identity*, "rough for oddballs" (`manabase.py:12-14`),
  and `classify()` depends on curated name lists that every new set outgrows.
  Scryfall already returns `produced_mana` and `oracle_text` on the endpoint
  `carddb.py` calls — the data is discarded today (`carddb.py:217-233`).
- **B. Rules layer.** Rules knowledge is a 38-line corrections file plus
  web search (`references/rules-reference.md`, `SKILL.md:39-41,98-100`).
  `coaching.md:89` already *instructs* answering from the Comprehensive Rules —
  there is just no tool to do it. `research-roadmap.md:103-104` planned this.
- **C. Goldfish Monte Carlo.** Approved direction per `docs/research-simulation.md`
  (tier 1 in scope; tier 2 **deferred**, tier 3 rejected — the doc defers 2, it
  does not reject it). Answers sequenced-play questions the closed forms
  structurally cannot (`manabase.py` is exact but unconditional). Prototype
  benchmark, reproduced independently: ~50µs/game → 10,000 games ≈ 0.5s.
- **D. Subagents.** A 4-day session died by transcript — many per-card WebSearch
  round-trips plus repeated full-pool listings (`deck_conflicts --available`
  alone is 407 lines/17.8KB, measured). Two bounded agents return conclusions
  instead of dumps. Agents cut context bloat only; they do not make the engine
  smarter — A/B/C do that.

## 2. Dependency order

```
A (enrichment core) ──▶ C task C6 (enriched mana model)
A ──▶ A-F (classify() integration — separate follow-up PR)
B, D: independent of A/C and of each other
```

Recommended sequence: **A → C**, with **B** and **D** interleaved anywhere.
C tasks C1–C5 do not wait on A (they ship on a labeled fallback model); only C6
consumes A's fields. Coordination note: A task A3 and D task D1 both edit
`scripts/carddb.py` — land A3 first or rebase D on it.

Each workstream is one PR (A-F is a second, small PR). PRs are squash-merged;
re-sync the branch on `origin/main` between them.

## 3. The scope-lock lift (formal)

`docs/spec-interactive-analytics-ai.md:20-21` and `docs/research-roadmap.md:16-17`
still declare "Out of scope: playtesting / goldfishing / game simulation of any
kind." `docs/research-simulation.md` (2026-08-10) revisited that lock with a
costed ladder and put **tier-1 goldfish in scope**. Workstream C's docs task
amends both lock lines to: *"tier-1 goldfish Monte Carlo now in scope per
docs/research-simulation.md; opponent/game simulation remains out of scope
(tier 2 deferred, tier 3 rejected)."* The tracker has **no existing row to
tick** — per its own update rule (`spec-interactive-analytics-ai.md:8-10`) the
landing PR **adds** a row, updates the header status line, and appends a
Changelog entry. One recorded deviation: `research-simulation.md:62` recommends
A/B deltas "in the card advisor"; v1 puts A/B in the CLI instead (§6, cut list).

---

## 4. Workstream A — production-aware enrichment (`produced_mana` + oracle-derived flags)

### 4.1 The gap, verified

- `carddb.py` enriches via Scryfall `POST /cards/collection` in 75-card batches
  (`carddb.py:158-184`) and writes `collection_attrs.csv` with exactly
  `Name,Type,MV,Colors,Cost,Sub-types,Scryfall` in both the API path (`:265-272`)
  and the bulk path (`:143-153`). `_attrs_from_scryfall` (`:217-233`) already
  handles `card_faces` fallbacks but reads **no** `oracle_text` and **no**
  `produced_mana`.
- `deck_stats.build_report` counts color sources from **lands only** via
  `c.colors or c.identity` (`deck_stats.py:107-112`) — identity, not actual
  production. Consumers: `manabase.py:77`, `build_dashboard.py:160` (header
  string at `:173`), coach packet `webapp/app.py:613`.
- `classify()` (`mtglib.py:513-541`) is curated-name-sets first
  (RAMP/DRAW/REMOVAL/WIPES/COUNTERS, `:460-510`), then a type fallback. It never
  sees oracle text. `gen_card_notes.py:88-90` proves the face-aware
  oracle-text-join pattern in-repo already.
- `overlay_attrs` (`mtglib.py:282-316`) reads columns by header-name alias via
  `_header_index` and ignores unknown columns — appended columns are
  back-compatible in both directions. **But** `deckcore.load_attrs`
  (`deckcore.py:186-202`) uses fixed exact-case keys, *not* aliases — deck-level
  companions must match header case exactly.
- **The pipeline trap (found in adversarial review):** `deck_stats.analyze()`
  rebuilds each enriched deck card as a **new** `mtglib.Card`, copying an
  explicit field list (`deck_stats.py:50-57`). Any new Card field not added to
  that copy silently never reaches `build_report`, `classify()`, `manabase`, or
  the dashboard for any *deck*. Task A2 owns this.
- Second trap: `auto_build.py:305-309` constructs basic-land Cards directly; with
  `produced=None` every freshly built deck would forever render the
  "identity approx." warning. One-line fix in A2.

### 4.2 The pinned data contract (A produces it; C, and later classify(), consume it)

This section is the single source of truth both workstreams reference.

- **`Card.produced: Optional[set]`** — `None` = unknown (consumers take their
  labeled fallback); **`set()` = enriched and known to produce no mana** (e.g.
  Maze of Ith). This None-vs-empty distinction is load-bearing; any code path
  that conflates them is a review-blocking bug.
- **`Card.flags: set[str]`** — v1 token vocabulary (C-critical set only):
  - `etb-tapped` — Land face whose own text matches
    `enters (the battlefield )?tapped` (covers pre- and post-Foundations
    wording) with no `unless` / `you may pay` / `if ` qualifier in the sentence.
  - `etb-tapped-cond` — same match *with* a qualifier (check/shock/battle
    lands). Three-valued on purpose; the sim picks its policy per run.
  - `rock` — Artifact non-Land matching `\{T\}[^:]*:\s*[Aa]dd `.
  - `dork` — Creature non-Land, same pattern.
  - `ramp` — `rock`/`dork` present, or the search-library-for-land-onto-battlefield
    text class (Cultivate/Farseek).
  - `draw` — the proven `gen_card_notes.py:54` draw pattern, not preceded by
    `opponent |each player |target player `.
  - `mana2` / `mana3` — production amount when one activation adds >1 mana
    (count symbols in the longest `Add` clause; Sol Ring → `mana2`). Absence = 1.
  - **Cut from v1:** `removal`/`wipe`/`counter` tokens and *all* `classify()`
    consumption — moved to follow-up A-F (§4.5), because they change category
    counts that feed `power.assess` and the optimizer's role-template guardrails
    (`optimize.py:175,274-279`), doubling the blast radius of an enrichment PR.
- **CSV format** — two columns strictly **appended** to `collection_attrs.csv`:
  header becomes `Name,Type,MV,Colors,Cost,Sub-types,Scryfall,Produced,Flags`.
  `Produced` = space-joined letters in WUBRGC order (matches the existing
  `Colors` style); empty cell = produces nothing; column absent = unknown.
  `Flags` = `;`-joined tokens (semicolons survive commas in names, the
  `combos.csv` convention). No raw oracle text at rest — flags are derived at
  enrichment time; re-deriving after a vocabulary change costs one enrich re-run
  or zero via the cached bulk file. The file stays gitignored/private.
- **Propagation paths that must carry the fields** (each named in a task):
  `mtglib.overlay_attrs` (A2) · `deck_stats.analyze`'s explicit field-list copy
  (A2) · `auto_build` constructed basics (A2) · `deckcore.load_attrs/apply_attrs`
  deck companions (landed in **C6**, exact-case headers `Produced`/`Flags`).

### 4.3 Tasks

**A1 — `scripts/oracle_flags.py`: face-aware derivation (new engine module).**
Pure stdlib (`re` only; no mtglib, no spokes), dict-in/set-out over a Scryfall
card object: `oracle_text_of(c)` (card-level, else `" // ".join` of face texts —
copy `gen_card_notes.py:88-90`, **not** the naive `split("//")` at
`gen_card_notes.py:93`/`carddb.py:211`, which is the SP//dr bug class);
`produced_of(c) -> set` (union of card-level `produced_mana` and any face-level
values, filtered to WUBRGC — the face union is belt-and-suspenders, labeled as
such); `derive_flags(c) -> set` per the §4.2 vocabulary, face-aware (a flag
fires if any face matches; `etb-tapped` checks the Land face's own text;
sentence-split on `.` before qualifier checks). Module docstring carries the
grounding note: flags are heuristic; curated lists and human verification win.
*Tests* (`tests/test_oracle_flags.py`, dict fixtures only, no I/O): Command
Tower → full produced set, no flags; Sol Ring → `{'rock','ramp','mana2'}`,
produced `{'C'}`; Llanowar Elves → `{'dork','ramp'}`; an MDFC shaped like
Malakir Rebirth // Malakir Mire (card-level `produced_mana`, back-face Land
etb-tapped text) → produced + `etb-tapped`; Guildgate → `etb-tapped`;
checkland → `etb-tapped-cond` only; shockland → `etb-tapped-cond`;
Divination → `draw`; "each opponent draws" → no `draw`; Cultivate text →
`ramp`; vanilla creature → empty flags, empty produced set.
*Acceptance:* offline green on 3.11/3.13; `python3 -c 'import oracle_flags'`
passes CI's bare-stdlib gate; **plus a one-time schema check on the player's
machine** — run the fixtures' shapes against real Scryfall JSON or the cached
`data/collection/scryfall-oracle_cards.json` (this sandbox cannot: Scryfall is
proxy-blocked here, verified live; the MDFC fixture shape rests on the
documented schema, so validate it once against reality).

**A2 — `mtglib` Card model + every propagation path.**
Add `produced: Optional[set] = None` and `flags: set = field(default_factory=set)`
to `Card` (`mtglib.py:25-42`) with the None-vs-empty comment; helpers
`_parse_produced` (whitespace-split, keep WUBRGC) and `_parse_flags` (`;`-split,
strip, drop empties). `overlay_attrs`: `_header_index(fn, 'produced',
'produced mana')` / `_header_index(fn, 'flags')`; only when the header exists,
set the field (empty cell → `set()`); when absent, touch nothing. **Extend the
explicit field list in `deck_stats.analyze`'s Card copy (`deck_stats.py:50-57`)
with both fields** — this is the fix without which the whole workstream no-ops
at deck level. **Set `produced={col}` on `auto_build.py:305-309` basics.**
*Tests:* extend `test_mtglib` with tmp_path collection+attrs fixtures WITH the
new columns (Command Tower `'W U B R G'`; Sol Ring `'C'` + `rock;ramp;mana2`;
a Maze-like land with empty `Produced` → `set()`, not None) and WITHOUT them
(the exact current 7-column header → `produced is None`, `flags == set()`, all
pre-existing assertions intact); parse-helper edge cases; a deck-level test
proving the fields survive `deck_stats.analyze`'s copy.
*Acceptance:* all existing tests unchanged and green; no naive `split('//')`
introduced; `Card()` still constructs bare.

**A3 — `carddb` writes `Produced` + `Flags` in both paths; `--stats` coverage.**
`import oracle_flags`. API path: `_attrs_from_scryfall` adds
`'produced': ' '.join(l for l in 'WUBRGC' if l in produced_of(c))` and
`'flags': ';'.join(sorted(derive_flags(c)))`; the writer (`:265-272`) emits the
9-column header (new columns strictly after `Scryfall`). Bulk path: `_rows_*`
pass the full card dict through; the duckdb SELECT adds
`produced_mana, oracle_text, to_json(card_faces)` **inside the existing
try/except-to-stdlib fallback** (`:120-127`) since CI has no duckdb;
`build_index` and the bulk writer emit the same columns. `--stats` prints one
coverage line (`produced known: n/total`). `enrich_api`'s signature is
unchanged — `webapp/app.py:933` and `enrich.bat` pick everything up for free.
*Tests* (`tests/test_carddb.py`, new, fully offline): monkeypatch
`_post_collection` with canned dicts → 9-column header, correct cells per
fixture; bulk path from a tiny JSON array with `use_duckdb=False`; round-trip
through `mtglib.load_collection` proving write→overlay end-to-end; any
accidental `urlopen` fails the test.
*Acceptance:* header exactly as pinned; round-trip proven; signature untouched;
bare-import CI gate passes.

**A4 — `deck_stats` actual-production sources + labeled fallback everywhere.**
In `build_report` (`deck_stats.py:107-112`): per land,
`prod = ({l for l in c.produced if l in 'WUBRG'} if c.produced is not None else
(c.colors or c.identity))`; track counts and add report key
`color_sources_basis = {'produced_lands': n, 'identity_lands': m}` (flat counts
— every consumer only needs "is `identity_lands > 0`"; the three-state enum
from the draft was cut as vocabulary overreach). `color_sources` keeps its
exact shape. **Fixture-pinned semantics for unowned/missing lands:** deck cards
absent from the collection keep `produced=None` and count as `identity_lands`
— a deck with any unowned land can never claim a pure produced basis; a test
pins this. Labels: `print_report` appends the identity-approximation line when
`identity_lands > 0` — placed inside the existing `if rep['pip_demand']:` gate
(`:162`), same suppression as today's `:178-180` warning, stated here so it's a
decision not an accident. `manabase.analyze` passes `basis` through and the CLI
prints the same label; `build_dashboard` appends ` (identity approx.)` to
`src_hdr` (`build_dashboard.py:173`) when applicable.
*Tests:* a land with identity `{W,U}` but `Produced 'U'` counts as U only;
same deck, attrs without the column → W and U (fallback) with
`identity_lands > 0`; mixed file → correct per-bucket counts; empty-`Produced`
land contributes zero under a produced basis (proven distinct from no-data);
a deck containing one unowned land never reports `identity_lands == 0`;
JSON back-compat (only the new key added); dashboard smoke shows
`identity approx.` only in the fallback case.
*Acceptance:* all basis states correct; existing `test_manabase`/`test_dashboard`
green; pre-A attrs file diff = the added key only.

**A5 — webapp surfaces.**
Assess packet (`app.py:613-629`): append the identity-approximation note beside
the sources line when `identity_lands > 0`. `/collection` coverage tile
(`app.py:896-901`): add `produced_covered = sum(1 for c in coll if c.produced
is not None)` (interview Q-A6; small). Upload round-trip test: POST a small CSV
to `/collection/upload` with `_post_collection` monkeypatched and app config
paths pointed into tmp_path; assert the written attrs file has 9 columns —
this closes the risk that the route's `try/except Exception: pass`
(`app.py:934-935`) would swallow a derivation bug silently.
*Acceptance:* labels render both ways; upload writes the new columns; no test
touches real `data/`.

**A6 — docs.**
CLAUDE.md: Data-formats collection bullet (columns + empty-vs-absent rule in
one sentence) and the `.attrs.csv` shape note `(Name,Type,MV,Colors[,Produced,Flags])`.
`docs/codemap.md`: **per-module table row for `oracle_flags`** (the table must
cover every module) + dependency edge `carddb → oracle_flags` + one Card-
knowledge-flow row ("what it actually taps for / oracle-derived flags").
Tracker: this extends Phase 2 (manabase, still ◐ at
`spec-interactive-analytics-ai.md:96`) and the enrichment status line — update
per the tracker's own rule (box + status + Changelog). Secondary docs that
describe attrs contents: `data/collection/README.md:29,46` · `README.md:81` ·
`SKILL.md:192-194` · `references/tooling-and-data.md:8`. `docs/handoff.md` in
place. `docs/research-simulation.md`: add the §4.2 precondition contract note.
*Acceptance:* a fresh session reading CLAUDE.md + codemap can state the format
and the None-vs-empty rule without reading code.

### 4.4 Risks

- **Stale attrs files** are the steady state until the player re-runs
  `enrich.bat` — every consumer must treat `produced=None` as "fall back and
  say so". Review-blocking failure mode: treating None like empty-set.
- **Oracle wording churn** ("enters tapped" vs "enters the battlefield tapped",
  future rewordings): centralized in `oracle_flags.py`, one regex to fix;
  absence degrades to the untapped assumption (wrong-side-safe and labeled).
- **Conditional-tapland misclassification** on odd `if` clauses: bounded by the
  three-token design; tests pin basic/shock/check/gate/refuge classes.
- **duckdb schema drift** on the new SELECT: covered by keeping it inside the
  existing stdlib fallback and testing the stdlib path (CI has no duckdb).

### 4.5 Follow-up A-F (separate small PR, after A + C land)

`classify()` consumes flags where curated lists are silent (`if not roles and
card.flags:` before the type fallback — curated always wins, mirroring
`load_card_notes`' first-writer-wins at `deckcore.py:220`), plus the
`removal`/`wipe`/`counter` tokens. Required in that PR: a before/after
`deck_stats --json` categories diff on the fixture deck, a re-run of
`test_optimize`, and an explicit re-verification of optimizer **idempotency**
(category counts feed its role guardrails — this must be re-proven, not
assumed). Interview Q-A3 ratifies timing.

---

## 5. Workstream B — Comprehensive Rules layer

### 5.1 The gap, verified

Rules knowledge = `references/rules-reference.md` (exactly 38 lines: five
corrections once gotten wrong + a "search Scryfall/Gatherer" habit) and
web search per `SKILL.md:39-41,98-100`. `coaching.md:89` already instructs
"from those + the Comprehensive Rules — never from memory" with no tool behind
it. Card *rulings* are browser-side only (`card_api.py:6-9`,
`cardpanel.js:117-145`). The fetch/cache/degrade idiom to mirror:
`edhrec.py:23-28,50-62` (note: on failure edhrec tries its committed snapshot
*before* the error payload — B has no snapshot tier in v1, by decision Q-B1);
`carddb.py:44-72` (`.part` + `os.replace`), `:171-184` (backoff), `:308-315`
(manual-path instructions). CLI exits: 2 usage / 1 degraded
(`spellbook.py:106-113`; carddb's exit-2-on-network is the family outlier —
new CLIs follow spellbook/edhrec).

**Egress reality (verified live from this sandbox):** `magic.wizards.com` and
`api.scryfall.com` both proxy-403 here. Per `codemap.md:118-125`: the player's
PC reaches everything; the hosted server reaches documented public APIs only
(Scryfall yes, wizards.com **no**); CI/sandboxes reach nothing. So the CR layer
is a **player's-PC feature** in v1 — the skill runs there; the hosted app has
no rules surface (and that is why the `/api/rules` route is cut, §5.4).

### 5.2 Design decisions

- **Download-on-demand + gitignored cache; never commit the CR.** The CR is
  ~1MB of copyrighted WotC text revving ~5-6×/year; committing it to a public
  repo is wholesale redistribution and a recurring megabyte diff. Cache under
  `data/cache/rules/` (`.gitignore:33` already covers it). A distilled
  committed snapshot (e.g. chapter 903 + glossary) is interview Q-B1, default no.
- **Manual refresh only.** `--refresh` re-downloads; otherwise any cached copy
  is used with an honest `fetched <date>` label derived from file mtime (no
  `meta.json` sidecar, no TTL machinery, no surprise 60s mid-query fetch
  stalls — cut on review). First-ever run fetches; every failure path returns
  the standard `{'error': ...}` payload with the manual-download note
  (`https://magic.wizards.com/en/rules` + `--file <path>`), never raises.
- **`rules.py` has zero repo imports** — a first for the engine ring (every
  other engine imports mtglib; rule text has no card names). Stated as a first
  in its codemap row, not analogized.
- **Module-level memo** of the parsed CR keyed by (path, mtime) so repeated
  queries in one process parse once.
- **Parser:** the official txt layout — Contents listing closed by the first
  `Credits` line, body to the last `Glossary` line, glossary to the last
  `Credits`; rules `^(\d{3})\.(\d+)([a-z])?\.?\s`, sections `^(\d{3})\.\s`,
  chapters `^([1-9])\.\s`; `Example:` lines attach to the current rule; any
  other non-blank line is a continuation (degrades to concatenation, never a
  crash). Encodings: `utf-8-sig` then `cp1252`. A 0-rule parse sets an explicit
  error rather than returning empty. **The layout is unverifiable from this
  sandbox** — acceptance requires a one-time parse-count sanity run against the
  real file on the player's machine.
- **Search scoring, simplified** (cut the positional bonus): +2 per distinct
  term present, +5 all terms, +10 exact phrase; ties by document order
  (earlier = more fundamental); snippet ±120 chars. The skill's instruction is
  retrieve-then-**read**-then-cite — ranking is a shortlist, never an answer.
- **Windows console:** CR text is full of em-dashes/curly quotes and the
  player's primary machine is Windows — the CLI wraps stdout with
  `errors='replace'` (no sibling needed this; card names are ASCII-safe).
- **`rulings.py` ships in v1 as the first-cut-if-long piece** (interview Q-B2):
  per-card Scryfall rulings via `/cards/named?fuzzy=` + `rulings_uri`, cache
  `data/cache/rulings/<_norm(name)>.json`, 30-day TTL with stale-okay,
  `mtglib.front_face` on the way in (the `' // '` trap), resolved-name echoed
  prominently (fuzzy can resolve a misspelling to the *wrong* card — the
  payload surfaces it, the skill must confirm). Scryfall etiquette: 0.1s
  courtesy delay between the two GETs (the `carddb.py:162-184` precedent) and
  handle `has_more` pagination. **Roadmap reconciliation recorded:**
  `research-roadmap.md:78-80` planned a ~24.7MB bulk-Rulings path through
  carddb; per-card named lookups beat it for a single-player tool (on-demand,
  KB-sized cache, no bulk download) — the roadmap line is amended so two
  rulings plans don't coexist.

### 5.3 Tasks

**B1 — `rules.py` fetch/cache/load.** Constants (`LANDING`, `CACHE_DIR`,
`_HEADERS` with the repo UA); `_find_txt_url(html)` regex
`https?://[^"\'\s]*MagicComp[Rr]ules[^"\'\s]*\.txt` with `--url` override;
`fetch_cr` (`.part` + `os.replace`); `load_cr(path=None, cache_dir=…,
fetch=True)` precedence explicit-path → cached file (labeled with mtime date) →
live fetch (first run only) → error payload; (path, mtime)-keyed memo;
`_decode` utf-8-sig→cp1252. Never raises.
*Tests:* fixture-path load without network; empty cache + `urlopen`
monkeypatched to raise → error payload, nothing raised; old-mtime cache +
blocked network → loads with the date label; cp1252 fixture; URL extraction
from a synthetic landing snippet.

**B2 — parser.** `parse_cr(text)` exactly per §5.2 →
`{'effective','chapters','sections','rules','children','glossary'}` in document
order.
*Tests:* the ~60-line `SAMPLE_CR` fixture (title, effective date, Contents
listing including duplicate headings + `Glossary`/`Credits` lines, chapters
1/100/601/903, rules incl. `601.2a`/`601.2b` + an `Example:` line, glossary
`Deathtouch` with "See rule 702.2." and `Dies`, `Credits`): exact rule count;
`601.2a` text; `children['601.2']`; Example attached not parsed as a rule;
**`rules['100.1']` holds body text, not the Contents heading** (the
duplicated-heading guard); effective date; Contents-removed and empty-glossary
robustness.

**B3 — query surface.** `normalize_ref` (`'601.2A.'` → `'601.2a'`);
`lookup(cr, ref)` (full rule with embedded children + section/chapter context;
bare section → title + rule numbers; miss → None; error payloads pass
through); `search(cr, query, limit=8)` per the simplified scoring;
`glossary_lookup` (exact → prefix → substring; `see_rules` refs scraped from
the definition).
*Tests:* each behavior above; deterministic ranking on the fixture; no query
path raises on an error/empty payload.

**B4 — CLI.** `main(argv=None) -> int`; positional auto-detect
(rule-ref-shaped → lookup, else glossary→search fall-through), `--search`,
`--gloss`, `--json`, `--file`, `--url`, `--refresh`, `--limit`. Degrade prints
the manual-download note to stderr, exit 1; usage errors exit 2; stdout wrapped
`errors='replace'`.
*Tests:* `--json` round-trip via capsys; search hit; miss → 1; degrade → 1 with
the note; all offline (`--file` fixtures; urlopen monkeypatched in the degrade
case).

**B5 — `tests/test_rules.py`** — the file holding every case above (~16 tests),
`SAMPLE_CR` at module level, tmp_path only, autouse network-block helper for
the degrade tests.
*Acceptance for B1–B5 together:* green on 3.11/3.13 offline; `python3 -c
'import rules'` under the bare-stdlib gate (import-safe: no network or side
effects at import time — the CI loop imports every scripts module); **one-time
real-file gate on the player's machine:** `python3 scripts/rules.py 903.1
--refresh` fetches, parses ≥3,000 rules, and answers.

**B6 — `rulings.py` + `tests/test_rulings.py`** per §5.2: `rulings_for(name)`
(fuzzy resolve → rulings fetch → cache; stale-okay on failure; error payload
otherwise), CLI with resolved-name-prominent output, exits 0/1/2.
*Tests:* canned two-step fetch → payload + cache file; second call from cache
with the fetch raising; cold cache + raising fetch → error payload, exit 1;
resolved≠requested surfaced; front_face applied (an `SP//dr`-style name does
not naive-split); `has_more` page joined.

**B7 — skill + docs.** `rules-reference.md` gains the leading "Ask the CR,
don't recall it" section (commands; cite rule numbers from retrieved text;
retrieve-then-read-then-cite; on degrade fall back to web search **and say the
answer is uncited**; the five corrections reframed as known traps).
**`coaching.md:89`** gets the command so the coach flow learns it (it already
states the policy). `SKILL.md` scripts index + workflow step 6 line. codemap:
two engine rows (`rules`: deps none — a first; `rulings`: mtglib) + the network
matrix rows (player PC ✅ / hosted ❌ wizards.com · ✅ scryfall / CI ❌).
`research-roadmap.md:78-80` amended per the reconciliation. CLAUDE.md commands
block one-liner (Q-B3). Tracker rules-Q&A line (`:139`, `:204`) per its update
rule. `docs/handoff.md` in place. Back-compat statement for the record: this
workstream adds two gitignored cache dirs and touches no existing format.

### 5.4 Cut from v1 (and why)

- **`/api/rules` webapp route.** No UI consumer; the skill runs the CLI; on the
  hosted server it would be *permanently* degraded (wizards.com unreachable
  from PythonAnywhere, no snapshot tier) and each request would re-attempt a
  60s fetch. Lands with the future card-panel Rules tab, with the memo + a
  negative-fetch short-circuit specced then.
- **TTL/auto-refresh machinery, `meta.json`** — replaced by `--refresh` +
  mtime label.
- **Semantic/RAG search** — bag-of-words + read-the-text is the grounding win.

### 5.5 Risks

Landing-page scrape brittleness (mitigated by `--url`/`--file` + cached copy;
live path verifiable only on the player's PC) · CR format drift (continuation-
line degrade + 0-rule error; a *silent partial* parse is the residual risk the
real-file acceptance gate exists for) · search-quality overtrust (instruction
frames it as retrieve-then-read) · fuzzy-resolution wrong-card cache in
rulings (resolved-name surfacing + skill confirmation) · if anyone ever
commits a cached CR the repo redistributes it (docs say keep it out of git;
`data/cache/` is already ignored).

---

## 6. Workstream C — goldfish Monte Carlo (`scripts/goldfish.py`)

### 6.1 The gap, verified

`manabase.py` is exact but unconditional — it cannot express sequencing, land
drops, taplands, or acceleration (`manabase.py:2-9,99-117`). Enriched deck
Cards carry `mana_value`/`mana_cost`/`types`/`is_land` but nothing about
production (until A). `deckcore.analyze_cards` runs `build_report` **unguarded**
and guards only `power.assess`/`manabase.analyze` with try/except→None
(`deckcore.py:283-293`) — goldfish stays *out* of deckcore entirely and defines
its own guard (§6.2). The dashboard's Mana tab assembles `manabase_html`
(`build_dashboard.py:611-649,844-847`); the assess packet's CONSISTENCY block
is `app.py:615-629`. **Hot-path fact that shaped the design:** the webapp
renders `bd.generate()` on *every* `/deck/<stem>` page view (`app.py:269-277`,
`:285-286` for `/visual`) — an uncached inline sim would tax every view, and
the assess page/packet would recompute it besides. Benchmark (reproduced):
~50µs/game prototype; real engine estimated 100-200µs/game.

### 6.2 Design decisions

- **Engine-ring module.** Top-level imports `math, random, json, argparse,
  mtglib` only; `deck_stats`/`deckcore` inside the loader/CLI path (the
  `manabase.__main__` pattern). Never imports spokes.
- **One shared entry with a disk cache — the hot-path answer.**
  `sim_for_deck(deck_path, collection, games=1500, seed=0, turns=10,
  cache=True) -> report | None`: loads/enriches/compiles, then consults
  `data/cache/goldfish/<stem>.json` keyed inside the file by
  `{deck mtime+size, attrs mtime, games, seed, turns, model coverage}`;
  recompute on any mismatch. The sim is seeded-deterministic, so the cache is
  pure speed, invalidated by any deck edit. All three surfaces (dashboard,
  assess page, packet) call this one helper; it catches everything and returns
  None + a note — one guard, not three hand-rolled copies. `data/cache/` is
  already gitignored. Cold cost ~0.15-0.3s per deck edit; warm cost ~file read.
- **Compilation.** Commander removed from the library once via
  `mtglib.name_keys` (the deck file lists it as a line); per-copy expansion in
  file order (CRN pairing is positional); library size reported, never assumed
  99. **Mana costs compile via a goldfish-local symbol tokenizer**
  (`re.findall(r'\{([^}]+)\}', cost)`) into a list of pip-sets — **each hybrid
  symbol is one pip payable by any of its letters** (`{W/U}` → `{W,U}`;
  `{W/P}` → `{W}`, life-payment not modeled; `{2/W}` → payable by W or 2
  generic; `{X}` = 0, stated). This replaces the draft's ceil-of-fractions
  rule, which would have demanded both halves of a hybrid at once —
  contradicting its own guarantee. `mtglib.pip_counts` stays untouched for the
  closed forms; the deviation is documented in the module docstring.
- **Mana model, two tiers per card (the §4.2 contract):** with `Card.produced`
  present — lands tap for exactly that set, `etb-tapped` lands give nothing the
  turn they drop (`etb-tapped-cond` policy: pessimistic/tapped by default,
  Q-C2), `rock`/`dork` flags make producers active the turn after cast,
  `mana2`/`mana3` set the amount. Fallback (`produced is None`) — any color in
  `colors or identity` (the exact `deck_stats.py:110` expression: the sim and
  the closed forms share one bias), untapped, `classify()`-ramp
  Artifacts/Creatures as 1-mana any-identity-color producers; ramp sorceries
  contribute nothing (stated limitation). `mana_value is None` (unowned,
  unenriched) → uncastable, counted; >25% such nonlands → `have_data: False`
  and every surface prints the note instead of numbers (the `manabase.py:149-151`
  honesty pattern).
- **Assumptions as data.** `report['assumptions']` carries the mulligan rule,
  the on-play convention, the model tier with coverage counts, and the
  goldfish-only disclaimer. Surfaces render the list; **tests assert stable
  substrings/keys, not verbatim prose** (so a wording fix doesn't touch five
  files).
- **RNG.** `master = random.Random(seed)`; per-game
  `random.Random(master.getrandbits(64))`. Int seeds only (tuple seeding goes
  through `hash()` and PYTHONHASHSEED breaks cross-run determinism); never the
  global `random`; all iteration in stable compile order. Same inputs →
  byte-identical report.
- **Turn loop.** London mulligan (keep 2-5 lands, floor 5, bottom excess lands
  beyond 3 then highest-MV); first-7 recorded pre-mulligan (converges to
  `manabase.land_odds`); on-play (no t1 draw, matching `cards_seen`); land drop
  untapped-first then color-greedy; commander cast first when payable (plain
  MV — **commander-tax accounting cut**: goldfish never recasts, the code
  would be dead by design); greedy highest-MV castable; payment matcher
  scarcest-color-first, mono-producers before rainbow (near-exact heuristic,
  documented as such).
- **Metrics (trimmed to what `research-simulation.md:37-42` asked for):**
  commander `p_cast_by` t1-8 + mean; `keepable_first7`; mulligan rate;
  screw (`<3 lands in play at the start of turn 4`) / flood (`9+ lands seen by
  end of turn 6`) with definitions shipped as data (Q-C1); `mean_lands_by_turn`;
  the per-card table `{name, mv, cast_rate, mean_first_cast, delta}` sorted
  worst-first — the sequenced castable-on-curve answer, which *is* the curve-
  deployment story. Cut: mana-utilization series, the `MV≥10` deployment
  scalar, discordant-count reporting (invented metrics / statistical polish).
- **A/B over common random numbers.** Arm B replaces the outgoing card's
  compiled entries at the same library indices; both arms replay the identical
  `game_seeds`; paired per-game differences on the headline metrics with
  `d̄ ± 1.96·stdev/√n`. Incoming card resolves through `mtglib.lookup` against
  the collection — refuse otherwise (never invent). The A/A-exact-zero test is
  the tripwire for any refactor that re-sorts compiled decks (positional
  pairing silently dies otherwise, while still producing plausible numbers).

### 6.3 Tasks

**C1 — core engine.** Compilation (incl. the pip-set tokenizer), RNG
discipline, mulligan, turn loop, payment matcher, `simulate()` with the full
report + assumptions + `have_data` gate. Pure functions, no I/O.
*Tests* (`tests/test_goldfish.py`; ≤4,000 games per test, all in-code or
tmp_path): seeded determinism (`==` same seed, differs across seeds);
closed-form convergence with mulligans off, ±2pp at 4,000 games — 37-land deck
vs `manabase.land_odds(37)['keepable']` and `hypergeom_at_least(99,37,7,3)`;
cards seen at start of t4 `== cards_seen(4)` exactly; degenerate decks
(all-lands → commander cast on its MV turn 100%, screw 0; zero-land → never
cast, screw 100%; mono-color ample lands → no color blocks); hybrid pip: a
`{W/U}` spell casts off either color alone (the rule §6.2 exists to
guarantee); mulligan floor (mulls exactly twice then keeps 5; first-7 stat
unaffected); honesty gate + label substrings.
*Acceptance:* green 3.11/3.13 offline; bare-import gate; 5,000 games of a
37-land deck < 2s.

**C2 — A/B + CRN.** `simulate_ab` per §6.2.
*Tests:* A/A → every delta exactly 0.0, zero-width CI (no tolerance); paired
CI strictly narrower than the unpaired CI computed from the same two runs;
unresolvable in-card → refusal note, no report.

**C3 — `sim_for_deck` + CLI.** The shared cached loader (deck parse →
`deck_stats.analyze` → `deckcore.apply_attrs` → commander from the
`# Commander:` header, `optimize.py:53-55` regex — deckcore/deck_stats imported
inside the function); the cache key/invalidations; `main()` with `--deck
--collection --games --seed --turns --no-mulligan --no-cache --json --ab "Out
Card=In Card"`; text report ends with the assumptions block, always; errors
degrade to a note + exit code per the spellbook convention.
*Tests:* CLI smoke on tmp_path fixtures (exit 0, `--json` parses and carries
seed/games/assumptions; `--ab` emits deltas; missing file → exit 2); cache
behavior — second call with unchanged inputs reads the cache (observable via a
counter monkeypatch), an edited deck file recomputes, `--no-cache` bypasses;
cache writes land only under the given cache dir.

**C4 — dashboard panel.** `goldfish_html(sim)` modeled on `manabase_html`
(stat tiles: commander by T4/T6, keepable, screw, flood — each tile carrying
its definition string; the worst-sequenced table with `.cardlink` spans so the
panel hooks fire on both surfaces; muted assumptions footer including "seeded
Monte Carlo — distinct from the exact hypergeometrics above"). `generate()`
accepts an optional `sim=` and also self-computes via `sim_for_deck` when not
passed; `sim=None` omits the section. Appended into `mana_sec`
(`build_dashboard.py:846-847,867`). No new CSS; the file stays self-contained.
*Tests:* heading + label substrings present (fallback fixture); self-
containment assertions still pass; `generate()` intact when goldfish raises
(monkeypatched) — section absent, page renders.
*Acceptance:* CLI-rendered and app-rendered dashboards show identical numbers
for the same deck/seed (shared `generate()`, shared cache); warm page render
adds ~a file read.

**C5 — assess surfaces.** Packet block `-- GOLDFISH SIMULATION (Monte Carlo,
seeded) --` after CONSISTENCY (`app.py:615-629`): headline metrics with
definitions, worst-5 table, assumptions; degrade line on None. Assess page:
`sim` passed to `assess.html`, a card section under the manabase card,
`data-card` spans, muted footer. Both go through `sim_for_deck` (cache shared
with the dashboard — a page visit costs one sim per deck edit, total).
*Tests:* page + packet contain the heading/definition substrings; both render
when the sim is unavailable.

**C6 — enriched-model consumption (the only A-dependent task).**
Consume `Card.produced` / `Card.flags` per the §4.2 contract (no other field
names); `model='exact'` per enriched card, coverage counts, label switch.
**Plus the deck-companion leg A deferred here:** extend
`deckcore.load_attrs/apply_attrs` to carry `Produced`/`Flags` (exact-case
headers; column-absent ⇒ untouched ⇒ `None`), so a deck-level `.attrs.csv`
powers the enriched model on a fresh clone with the name-only snapshot.
Buildable and fully testable with hand-built Cards before A lands.
*Tests:* tapland gives nothing on its drop turn (CRN A/B shows the delta);
`{C}`-only land pays generic never pips (a `{W}{W}` spell stays uncast in a
C-lands deck); `mana2` rock accelerates the commander in a constructed hand;
label + coverage correct; mixed decks; **all C1-fallback tests pass unchanged
with the fields absent**; companion-file row round-trips through
`analyze_deck` into the sim.

**C7 — docs + the scope-lock lift (§3).** codemap: engine-ring node + table
row (`goldfish | seeded goldfish MC: commander-by-turn, keepable/screw/flood,
sequenced first-cast, CRN A/B | mtglib (deck_stats/deckcore in loader only)`) +
build_dashboard's new dep; the two lock-line amendments + tracker row/status/
Changelog + the card-advisor deviation note; `research-simulation.md` status
line; CLAUDE.md **Engines list** + commands block + test count; handoff in
place.

### 6.4 Risks

Fallback-model optimism (taplands/utility lands over-credited — labeled, and
identical to the closed forms' existing bias, so the two engines stay
comparable) · two-engines-two-answers on one panel (per-number provenance
labels; sim ≠ hypergeometric is a feature, explained) · greedy policies are a
stated pilot approximation (per-card deltas inherit their blind spots) ·
cache staleness if the key misses an input (key includes attrs mtime; tests
pin invalidation) · CRN positional-pairing fragility (the A/A-zero tripwire).

---

## 7. Workstream D — subagents (`.claude/agents/`)

### 7.1 The gap, verified

No `.claude/agents/` exists; no repo mention of subagents. The two
transcript-killing shapes: per-card verification (`SKILL.md:39-41,98-100` —
each inline WebSearch dumps a results page) and full-pool scans (measured
against the committed snapshot: `deck_conflicts --available` 407 lines/17.8KB;
`power --rank` 10 lines; `analyze_collection --subtype Dragon --list` 22
lines). No CLI can verify a single card's oracle text today: `carddb.py` is
whole-collection-only (`--collection` required, `:282`) and discards
oracle_text/legalities; `card_api.py` is single-card but has no oracle text
(client-side by design, `card_api.py:6-9`). Prior art acknowledged:
`gen_card_notes.py:68-98` already implements batched oracle-text fetch —
`verify_cards` is a second copy of that plumbing; refactoring gen_card_notes
onto it is deliberately out of scope (recorded here so the duplication is a
decision, not an accident). **Trap:** `carddb.py:211` contains a naive
`split("//")` (harmless where it sits, but it is the SP//dr bug class —
`mtglib.front_face`'s docstring names it); new code must not copy it.

### 7.2 Design decisions

- **Exactly two agents.** One per bloat shape. A third coach agent would fork
  the skill (the champion persona must reason over the compact per-deck
  numbers itself), and agent descriptions compete for automatic delegation —
  two sharp ones trigger; five fuzzy ones misfire. A field-researcher agent is
  deferred (edhrec.py + committed field snapshots already compact that).
- **Prerequisite: `carddb.py --verify`** (the agents run CLIs, never
  reimplement). `verify_cards(names)` → ordered dicts `{requested, found,
  name, mana_cost, type_line, oracle_text, color_identity, legal_commander,
  set, collector_number, scryfall_uri, reason, source}`. Cache
  `data/cache/scryfall/<_norm(front_face(name))>.json`, 30-day TTL, `--refresh`
  honored. **Resolution, corrected on review:** batch exact names through the
  existing `_post_collection`; reconcile **positionally** (Scryfall returns
  `data` in identifier order with `not_found` listed separately — name-keyed
  matching breaks on back-face/adventure-half requests); each `not_found` name
  then retries once via `/cards/named?fuzzy=` with a 0.1s courtesy delay
  (misspellings tolerated; resolved-name corrections surfaced; nothing found →
  `found=False` — hallucinated names die here). Oracle text via the face-aware
  join (never the naive split). Network failure → per-batch
  `found=False, reason='network unreachable: …'`, exit 0 — the report is the
  product. `--collection` flips to `required=False` with a post-parse check
  that exactly one mode was requested — **plus a regression test that
  enrichment mode still demands `--collection`** (`enrich.bat:18` and
  `webapp/app.py:932-933` depend on it).
- **Verbatim text, not paraphrase.** The verifier's table carries (truncated)
  *verbatim* oracle text; agent paraphrase is exactly the misreading vector
  grounding rule 3 exists to kill. Full text on request for build-arounds.
- **Grounding rules single-sourced.** Both agent prompts begin by Reading
  `.claude/skills/mtg-deckbuilder/references/grounding-rules.md` and cite rule
  *numbers* only (verifier: 3, 7; auditor: 1, 2, 7, 8). No second copy to
  drift.
- **Privacy line in the auditor:** never print `collection.csv` rows or prices
  wholesale — counts and ≤10 exemplar names only ("read-only" alone does not
  stop Bash from `cat`-ing the private CSV into the parent transcript).
- **Toolbox correction:** `staples_crossref.py` requires `--staples` (verified
  via `--help`) — dropped from the auditor's toolbox (five commands remain:
  analyze_collection, deck_conflicts [`--available`], power `--rank`,
  commander_finder, edhrec). `analyze_collection` has no `--json`; the prompt's
  "prefer `--json` where offered" stands.
- **Defaults, not open questions** (per review): `model:` unset (inherit);
  `tools: Bash, Read` for both (write-blocking; Bash redirection stays a
  prompt-level prohibition, honestly noted); widening a future agent's tools =
  deliberately editing the structural test, the same friction
  `test_design_tokens` uses for new tokens.

### 7.3 Tasks

**D1 — `carddb.py --verify`** per §7.2 (constants `VERIFY_CACHE_DIR`,
`VERIFY_TTL`; `verify_cards`; argparse `--verify` append + `--json`; text
block per card or `UNVERIFIED "<requested>" — <reason>`; module docstring/usage
updated — it currently reads enrichment-only).

**D2 — `tests/test_carddb_verify.py`** (hermetic; `VERIFY_CACHE_DIR` and
`_post_collection` monkeypatched): verified row fields incl. `legal_commander`
True/False/None; DFC text joined from faces; positional reconciliation with a
`not_found` in mid-batch; fuzzy fallback resolves a misspelling and surfaces
the corrected name; back-face request resolves via the fuzzy path (name chosen
from committed repo data — Scryfall is unreachable from this sandbox, verified);
network error → found=False, no exception; cache hit leaves the fake's call
count at 1; **enrichment mode still requires `--collection`; bare invocation
errors**. *Acceptance is the offline suite plus a pre-seeded-cache fixture
proving text/`--json` output;* the live check (`--verify "Sol Ring"` on a
networked machine) is a player-PC step, not a CI gate.

**D3 — `.claude/agents/card-verifier.md`.** Frontmatter `name` /
folded `description` (capability sentence → PROACTIVE trigger: "more than ~3
uncertain cards", the post-2025 set list → input/output contract) /
`tools: Bash, Read`. Body: mechanical-verifier role; Read grounding-rules
first (rules 3, 7); one batched `--verify` invocation, no hand-built URLs, no
memory answers; canonical-name corrections reported; output = one markdown
table (Requested | Canonical | Cost | Type | Identity | Commander-legal |
Verbatim text) + one `UNVERIFIED:` line; no transcripts, no advice.

**D4 — `.claude/agents/collection-auditor.md`.** Same shape; triggers ("what
can I build", "how many X do I own", "which decks share cards", "rank my
decks"); Read grounding-rules first (rules 1, 2, 7, 8); collection resolution
(private CSV if present, else the snapshot — state which, repeat the CLI's
degradation warning); the five-command toolbox; hard limits (READ-ONLY: no
`--apply`, never optimize/refresh/wishlist/enrichment, no redirection into the
repo, no edits under `data/`; the privacy line; ≤10 exemplars; never name a
card a CLI didn't print; label estimates); verdict-first output with each
finding carrying its count and the exact producing command.

**D5 — SKILL.md "Delegate the heavy work (subagents)"** inserted after
workflow step 8 (`:109`), before Coaching (`:111`): when the Agent tool
exists, >~3 uncertain cards → card-verifier; any full-pool scan → auditor; the
main session keeps persona/verdicts/assembly/optimize decisions; **inline
fallback sentence** (no Agent tool → same work inline, unchanged workflow).
Pointer lines appended to steps 3 and 6. **Plus the SKILL.md scripts-index
entry for carddb (`:192-194`) gains `--verify`** — the non-delegated inline
path must learn the mode exists.

**D6 — `tests/test_agents.py`**, trimmed to six invariants in the
`test_design_tokens` style (stdlib os/re, regex frontmatter parse, docstring
stating the convention — deliberately no yaml import): expected agent files
exist; frontmatter has name/description/tools; name == filename stem; tools
set == `{Bash, Read}`; the literal grounding-rules path present in each body
*and* the file exists; SKILL.md names both agents. (Cut on review: the
path-token extractor and the description-length check — fragile, low value.)
*Verify the guard bites:* temporarily widen a tools list and break the path —
both must fail with clear messages — then restore green.

**D7 — docs.** codemap: **the carddb per-module row** (`:163`) gains
`--verify`; the coaching-skill section (`:185-187`) notes the two agents and
what each delegates; optionally the network matrix gains `data/cache/scryfall/`.
CLAUDE.md: the Layout tree line for `.claude/` (agents now exist) + test
count. Tracker per its update rule. Handoff in place (one sentence: agents
exist, when the skill delegates, carddb gained `--verify`).

### 7.4 Honest limits (kept from review)

Agents cut context bloat only — every engine number is byte-identical.
Automatic delegation is probabilistic (the SKILL.md section is the
deterministic path; there is no mechanical enforcement). Subagents exist where
the Agent tool exists — a phone session benefits only insofar as the heavy
session runs in Claude Code and the phone reads its outputs. In an
egress-blocked sandbox every uncached `--verify` is honestly UNVERIFIED.
Read-only is prompt-enforced for Bash; a hooks-based hardening is possible
later, out of scope.

---

## 8. Cross-cutting requirements (every PR)

- **X-1, first landing PR:** fix CLAUDE.md's "231 tests" (259 collected today;
  keep it current thereafter — handoff.md says 255 and gets the same fix).
- **codemap discipline:** every new module gets a per-module table row and its
  dependency edges; `docs/codemap.md` is the architecture authority.
- **Tracker discipline:** `spec-interactive-analytics-ai.md` updates follow its
  own rule — box + phase status + Changelog, adding rows where none exist.
- **handoff.md in place** every time — current-state only, no dated layers.
- **Egress reality:** this sandbox blocks `api.scryfall.com` *and*
  `magic.wizards.com` (both verified live during review). Hermetic tests are
  the executable gate everywhere; exactly two acceptance steps require one run
  on the player's machine (A1's Scryfall-schema check, B5's real-CR parse), and
  D2's live `--verify` check is likewise a player-PC step.
- **Suite growth estimate:** A ~+25 · B ~+22 · C ~+16 · D ~+12 → ~330-335
  total. CI (3.11/3.13, bare-import stdlib gate) needs no workflow change —
  every new scripts module must therefore be import-safe with no side effects.
- **Commit style** per CLAUDE.md: outcome subject, root-cause/fix/verification
  body.

## 9. Interview questions (each with a recommendation)

**Workstream A**
- **Q-A1** Rocks/dorks counted toward `color_sources`? *Rec: no — lands-only
  in v1; changing manabase pass/fail semantics deserves its own diff.*
- **Q-A2** `etb-tapped-cond` default policy where one must be picked?
  *Rec: pessimistic (tapped) in goldfish; manabase ignores the distinction.*
- **Q-A3** `classify()` flag integration (A-F) timing? *Rec: separate PR after
  A+C land, with the categories diff + optimizer idempotency re-proof; no
  `--legacy-classify` escape hatch unless the diff is ugly.*
- **Q-A4** `mana2`/`mana3` amount tokens in v1? *Rec: yes — Sol Ring fidelity
  is cheap (one regex) and goldfish is the consumer that wants it.*
- **Q-A5** Ratify permanent vocabulary: columns `Produced`/`Flags`, token
  spellings, `color_sources_basis` key shape. *Rec: as pinned in §4.2.*
- **Q-A6** `/collection` coverage tile for produced/flags? *Rec: yes, small.*

**Workstream B**
- **Q-B1** Commit a distilled CR excerpt (903 + glossary) so rules work on the
  hosted app/sandboxes? *Rec: no in v1 — verbatim-text concern in miniature;
  the skill runs on the player's PC. Revisit with the card-panel Rules tab.*
- **Q-B2** `rulings.py` in v1? *Rec: yes (small, high leverage for the skill);
  it is the designated first cut if the session runs long.*
- **Q-B3** CLAUDE.md commands block gets the rules/rulings one-liners?
  *Rec: yes — it's the doc every session reads.*

**Workstream C**
- **Q-C1** Screw/flood definitions (`<3 lands in play at start of t4` / `9+
  seen by end of t6`)? *Rec: accept; they ship as data so tuning is one edit.*
- **Q-C2** Sim budget/caching: accept the `sim_for_deck` disk cache (1,500
  games inline, recompute on deck edit)? *Rec: yes — cold ~0.2-0.3s per edit,
  warm ~free; the lazy-button alternative adds UI for no gain.*
- **Q-C3** Optimizer integration (goldfish deltas near `risers` /
  `manual_adds_review`)? *Rec: advisory-only, follow-up spec; never in the
  swap gate — the gate's idempotency contract is load-bearing.*
- **Q-C4** Partners/backgrounds (two command-zone cards)? *Rec: v1 simulates
  the parsed `# Commander:` only; partners are a follow-up.*
- **Q-C5** On-the-draw mode? *Rec: engine signature supports it from day 1
  (`on_play=False`), no surface exposes it in v1.*

**Workstream D**
- **Q-D1** WebSearch/WebFetch fallback for the verifier when Scryfall is
  blocked? *Rec: no — strict Bash+Read; UNVERIFIED-and-say-so beats
  reopening search-dump transcripts inside the agent.*
- **Q-D2** Delegate the per-deck coaching gather (4 CLIs) to the auditor?
  *Rec: no — the champion persona reasons over those compact numbers directly;
  delegating strips the coach of its evidence.*

**Sequencing**
- **Q-S1** Confirm the order: A → C, with B and D interleaved; A-F after A+C.
  *Rec: as stated. Each workstream is one PR on a fresh branch off
  `origin/main`.*
