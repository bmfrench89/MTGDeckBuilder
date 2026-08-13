# Spec — The "Table-Ready" Season

**Status: ◐ APPROVED by the player 2026-08-13 and IN PROGRESS.** Phases 8, 0 and 1 have
landed (see the ticks below); the rest are unstarted. Execution order and the §0
contract still bind every remaining phase.

**Source:** the competitive-landscape research (`research-competitive-landscape.md` §4)
plus player direction 2026-08-13, two rounds: *(round 1)* goldfish clock, Rule-0 card,
mulligan trainer; auto-bracket kept but overridable; fix the section misfiles and the
split-Plains line; pins v2; Mana-tab explainers. *(round 2)* add the phantom-disruption
experiment, the "what do I cut" surface, and the optimizer role-repair fix that lifts
the gate; spec the 4-player pod simulator but **backlog it**
(→ `spec-pod-simulation.md`); ground the spec in the full repo and fold in any missed
gaps. Ticks land here as work ships; this file is the tracker.

---

## 0. For the implementing session — read this before writing any code

This spec will be executed by a different session/model than the one that wrote it.
Nothing below is optional.

**Read first, in order:** `CLAUDE.md` (working rules — the prime directive, privacy,
stdlib-only, known traps) · `docs/codemap.md` (architecture + the card-knowledge-flow
rule + deployment matrix) · this spec end to end · the per-phase anchors listed inline.
For any deck/card work also `.claude/skills/mtg-deckbuilder/references/grounding-rules.md`.

**Repo-wide invariants that every phase must preserve:**

1. `scripts/` is **stdlib-only** — CI uninstalls Flask and imports every module bare.
2. **Dependencies point inward**: engines/spokes import hubs (`mtglib`, `deckcore`),
   never each other, never `build_dashboard`.
3. Tests are **offline and hermetic** — everything in `tmp_path`; never read/write the
   real `data/`. Network clients are monkeypatched.
4. Every name-membership test goes through `mtglib.name_keys()` / `front_face()` —
   never a naive `split("//")` (the `SP//dr` trap).
5. `optimize.singleton_violations()` runs after every deck write; keep it.
6. Generated dashboards stay **one self-contained file** (assets inlined via
   `_asset()`); the web app links `/static/tokens.css`. No ad-hoc font sizes or spacing
   — tokens only (`tests/test_design_tokens.py` enforces).
7. Deck-file edits preserve quantity, section, and comment lines
   (`tests/test_deck_edit.py` enforces; `optimize._tidy` A2/A3 history shows why).
8. **New webapp routes sit behind the auth gate** (see `docs/spec-auth-gate.md` and how
   existing routes register) — the app is internet-exposed on PythonAnywhere.
9. **Any new/changed webapp static asset or route the installed PWA caches requires a
   `webapp/sw.js` cache-version bump** (`mtgdb-v1` is hand-pinned — known deferral in
   `spec-repo-hardening.md`; a stale service worker will otherwise hide your feature on
   the player's phone).
10. Honesty labels: numbers derived from absent/approximated data say so, beside the
    number, on every surface (the `color_sources_basis` / goldfish-assumptions pattern).
11. PRs are **squash-merged**: one PR per phase, resync the branch on `origin/main`
    after every merge, substantial commit messages (see `git log`), update
    `docs/handoff.md` + this tracker when a phase lands.
12. **The optimizer `--apply` / ⚡ freeze stays in force until Phase 8 lands** (handoff
    open item 0). Phases 0–7 neither run nor modify the optimizer; Phase 9's cut
    surface is read-only advisory and must stay so.

**Execution order:** Phase 8 first or in parallel with 0 (it lifts the standing freeze
and is self-contained). Then the spine 0 → 1 → 2 → 3 → 4. Phases 5, 6, 7, 9, 10, 11
are independent of the spine (9 reads better after 8; 10 requires 2).

---

## Phase 0 — Deck hygiene: sections tell the truth (small)

Two player-visible bugs on the Y'shtola dashboard, both confirmed in
`data/decks/yshtola-nights-blessed.txt`, same root-cause family: **the deck file's
sections are the display**, and two write paths put lines where they don't belong.

- ☑ **0a. Re-run `deck_sections.py --all --apply` on the typed snapshot.** White
  Auracite (Artifact) and Risky Shortcut (Sorcery) sit in *Creatures* (lines 20, 26)
  because the card-panel Replace flow inserts the incoming card at the outgoing card's
  slot, and name-only data couldn't type them out. The committed attrs snapshot (live
  2026-08-12) types all five Unsorted cards *and* both misfiles (verified: Risky
  Shortcut=Sorcery, White Auracite=Artifact, Eye of Nidhogg=Enchantment,
  Tataru/Hermes/Alisaie=Creature, Dancer's Chakrams=Artifact). One idempotent regroup
  fixes all six decks. Verify: no `Unsorted` section remains; 100 cards per deck;
  `singleton_violations` clean; regroup re-run is a no-op.
- ☑ **0b. Merge duplicate same-name lines within a section.** `Basics` holds `1 Plains`
  (line 109) and `3 Plains` (line 111) — the 2026-08-11 migration appended "a 4th
  Plains" as a new line, and that path never ran `optimize._tidy` (which *does* merge
  duplicate lines — reuse its semantics, don't invent new ones). Fix in two layers:
  (1) `deck_sections.py` regroup merges same-name lines landing in the same section
  (sum quantities, keep first position) — for non-basics a duplicate line is an
  illegality `singleton_violations` already flags, so merge only what `mtglib.is_basic`
  accepts and let the violation report handle the rest; (2) the app's add paths
  (`/deck/<stem>/add`, buylist-arrival pulls) increment an existing same-section line
  instead of appending a twin. Tests: split basics survive a regroup merged with
  quantities intact; `test_deck_edit` guarantees still hold.
- ☑ **0c. Auto-resolve Unsorted after server enrichment** (pulled forward from
  `spec-repo-hardening.md` Phase 4 item 9, since 0a makes it recurring): after a sync
  that refreshes attrs, the server re-runs the regroup so future Unsorted sections
  drain without a session. Hook: `webapp/sync.py`'s post-pull step; regroup only decks
  whose Unsorted section is non-empty; log, never fail the sync on a regroup error.
- ☑ **Post-review remediation (2026-08-13):** the regroup summary is **no longer folded
  into `detail`** — appending it pushed the word `RECOVERED` out of the 300-char tail
  that `status_view` keys the rescue-branch warning off, so a self-heal rendered plain
  green with the "a session must merge this branch back" homework invisible
  (reproduced end to end). `recovered` is now a stored boolean and the regroup renders
  from its own field. The unattended regroup **skips decks with in-section comments**
  (`has_section_comments`) rather than eating prose a player hand-wrote, which is
  CLAUDE.md invariant 7 applied to a path nobody is watching, and `has_unsorted` also
  catches `UnicodeDecodeError` (a `ValueError`, not an `OSError`) so an unreadable file
  is not reported as a *failed regroup* that never ran. The card-panel **Replace** flow
  no longer manufactures the very bugs this phase fixes: replacing a card *with* a
  basic used to write `1 Plains` at the outgoing card's slot — a basic under Lands
  **and** a second Plains line — so it now drops the outgoing line and merges into the
  basic's own line, and the basic search is file-wide (a basic belongs on exactly one
  line; a section-scoped search produced a cross-section split the Unsorted-only
  auto-regroup would never drain).

## Phase 1 — Enrichment carries creature Power (small-medium; prerequisite for 2)

The goldfish clock needs to know how hard the board hits. Verified: neither
`collection_attrs.csv` nor the snapshot carries power (header:
`Name,Type,MV,Colors,Cost,Sub-types[,Scryfall],Produced,Flags`).

- ☑ `carddb.py` appends a **`Power`** column in both API and bulk paths (the pinned
  header list is at `carddb.py:58`; append after `Flags` so older files still load —
  same back-compat shape Produced/Flags used). Printed power; `*`/non-numeric stored
  verbatim, treated as unknown by consumers. **Empty-vs-absent rule stated in the
  header comment:** empty = "not a creature / no power"; absent column = "unknown —
  clock unavailable, say so."
- ☑ `mtglib.Card` gains `power` (int | None); `deckcore.load_attrs`/`apply_attrs` and
  deck `.attrs.csv` carry it (exact-case column, same as `Produced`/`Flags`); the
  attrs-snapshot Action regenerates with the new column (its five guards unchanged —
  see `spec-network-and-attrs.md`).
- ☑ Face-aware: front face's power via the same face-selection path `oracle_flags`
  uses. **No toughness column** — nothing in scope consumes it (goldfishing has no
  blockers); add it the day something does.
- ☑ Tests extend `test_carddb.py` (header round-trip) and `test_mtglib.py` (overlay).
- ☑ **Post-review remediation (2026-08-13):** `deck_stats.py`'s explicit Card rebuild
  now copies `power` — without it the column was **inert end to end** (that list is the
  only way a Card field reaches deck-level analysis, so Phase 2 would have read `None`
  for every creature). `_parse_power` no longer drops a real `0` through
  `str(value or "")`, and no longer crashes on `inf`/`nan` (`float()` accepts them and
  `int()` then raises `OverflowError`) — a parser on `load_collection`'s hot path
  against hand-editable files must degrade to unknown, never take down the load.
  `_rows_duckdb` became a non-generator so `build_index`'s documented duckdb fallback
  actually fires (as a generator the `import duckdb` ran lazily *outside* the try, and
  the call raised `ModuleNotFoundError` instead of degrading). The attrs-snapshot Action
  is **not** triggered by `carddb.py`/`oracle_flags.py` edits — a full ~2,600-card
  enrichment per docstring change, contending on the shared concurrency group, is not
  worth it; use the dispatch button or Monday's cron.

## Phase 2 — The goldfish clock (flagship; medium-large)

*"What turn does this deck actually present lethal?"* — the number the official
brackets are defined by since Oct 2025 (B2 ≈ satisfied with T8+ endings, B3 ≈ T6+,
B4 ≈ T4+) and no tool on the market measures. Research §4.1. Anchors:
`goldfish.play_game` (line ~365, the turn loop), `simulate` (~544), `simulate_ab`
(~631), `sim_for_deck` (~733), `print_report` (~817).

- ☐ **Combat model inside the existing turn loop:** creatures the sim casts enter with
  summoning sickness and attack every following turn with printed power (unknown power
  = doesn't attack, counted for the honesty gate). The commander attacks like any
  creature; commander damage tracked; 21-commander-damage kills count.
- ☐ **Two numbers, definitions shipped as data** (extend `report['definitions']`):
  **first-kill turn** (cumulative damage to one 40-life opponent) and **table-kill
  turn** (three sequential 40-life opponents, 120 total). Report medians +
  P(first kill ≤ T4/T6/T8) so the bracket anchors read directly.
- ☐ **Honesty gates.** Combat damage only — drain/burn/X-spell/token noncombat damage
  is NOT modeled in v1, so the clock **understates** decks like Y'shtola
  (Exsanguinate/Vito/Blood Artist); `report['assumptions']` names it and every surface
  prints it. Missing Power data (absent column, or >25% of creature copies unknown) →
  "enrich to unlock" instead of numbers, same gate shape as `have_data`. Alt-win/combo
  decks: CSB combo data is cited beside the clock, never folded in.
- ☐ **Bracket mapping, advisory wording:** "Uncontested goldfish clock: first kill
  median T7 — consistent with the Bracket 3 expectation (~T6+). Real games run
  slower." Never reclassifies the bracket; it renders as evidence in the Power tab
  bracket block and the Rule-0 card.
- ☐ **CRN contract:** the clock rides the existing seeded loop; `--ab "Out=In"` gets
  paired clock deltas for free. **Do not re-sort the compiled deck** — the
  A/A-exact-zero test in `test_goldfish.py` must still pass, now asserting zero on the
  clock fields too.
- ☐ **Surfaces:** goldfish panel tiles (Mana tab) + Power-tab bracket block, both via
  `build_dashboard.generate` (one change, two surfaces); `/deck/<stem>/assess`; the
  coaching packet; `--json`. All through `sim_for_deck` — the new parameters join
  `cache_key`.
- ☐ Tests: a vanilla-creatures fixture with hand-computable clock; the understatement
  label fires when drain-flagged cards are present; the Power-data gate; A/A zero
  including clock fields; cache invalidation on parameter change.

## Phase 3 — Bracket: auto-assigned, player-overridable (small)

Player decision: keep the automatic bracket ("lets me know where the deck sits") and
add an override for disagreement. Anchors: `power.py` bracket block (lines ~112–161),
`docs/power-and-brackets.md` (already current with Oct-2025/Feb-2026 rules — verified).

- ☐ Optional deck header **`# Bracket: <1-5>`** = the player's setting. Absent →
  exactly today's behavior. `mtglib`'s header parse carries it; **add a test that
  `optimize._tidy` and `deck_sections` rewriting a deck preserve unknown/new `# Key:`
  headers** (they should today; pin it before relying on it).
- ☐ Present → every surface shows **both, never silently one**: "Bracket 3 (your
  setting) · detected 4: 5 Game Changers — over the B3 cap". The setting wins headline
  position; the detected verdict and reasons stay visible. `power.assess`/`--json`
  gain `bracket_declared`, `bracket_detected`, `bracket_mismatch`; `--rank` prints the
  setting with detected in parens on mismatch.
- ☐ App control: a selector on the dashboard Power tab (editable surface only, same
  gating as Remove/Replace) writing the header through the existing deck-edit path.
- ☐ Recertify addition: a `recertify.yml` step diffing `data/reference/
  game_changers.txt` against Scryfall's `game_changer` field (canonical
  machine-readable list — research §5) so WotC revisions surface as a one-click check.

## Phase 4 — The Rule-0 table card (small-medium)

One phone-first, print-friendly screen answering the pre-game conversation, assembled
entirely from shipped engines (research §4.2).

- ☐ Route `/deck/<stem>/table-card` (auth-gated) + a "🃏 Table card" link on the
  dashboard More tab and the Decks page. Contents in table order: commander + colors +
  archetype · bracket (player setting if present, detected beside, top reasons) · Game
  Changers named · disclosures (MLD none/list · extra-turn count · 2-card combos
  present via CSB/`combo_detector`, one-away count) · goldfish clock line (Phase 2,
  when available) · win conditions + game plan (first lines of `.notes.md` Plan, else
  role heuristics, **labeled which**) · "estimates, not verdicts" footer.
- ☐ Self-contained render (inlined tokens, print stylesheet, no external assets);
  degrades honestly per missing source (no CSB cache → "combos unverified offline";
  no clock → line omitted). Every fact comes from the same hub/engine call the
  dashboard uses (codemap's card-knowledge-flow rule — no second derivation).
- ☐ Tests: renders offline for a fixture deck; disclosure lines source from engine
  calls (assert via monkeypatch); sw.js bump if cached.

## Phase 5 — Mulligan trainer (medium)

Deal real hands from the real deck; the player calls keep/ship; the sim shows its
verdict and *why*. Research §4.5 — the 2025–26 trainer wave is deck-generic and
online-only; ours is deck-aware and offline.

- ☐ Route `/deck/<stem>/mulligan` (auth-gated): deals from `goldfish.compile_deck`
  with a fresh seed per hand; London flow (keep → bottom-N picker; ship → redeal at 7
  with the sim's floor-5 rule).
- ☐ The reveal after each call: the sim's keep verdict for that exact hand
  (`goldfish`'s mulligan rule — expose it as a pure function if it's currently inline
  in `play_game`) plus evidence: lands, colored sources vs. curve needs, ramp/draw
  present, P(commander on time | keep), screw risk. Neutral wording — the rule is a
  heuristic and the page says so.
- ☐ Per-deck session stats (hands, agreement rate, kept-hand land distribution) in
  **localStorage** v1 — private, offline, zero server state. A future `games.csv` tie-in
  is noted, not built.
- ☐ Tests: dealt-hand endpoint seeded-deterministic; verdict matches the sim's rule on
  fixture hands; no network; sw.js bump.

## Phase 6 — Pins v2: reserved means reserved, moving is easy (medium)

Player intent: a pinned copy is off-limits to other decks' builds, but moving pins must
be easy. Verified current state: `auto_build` (line ~174) excludes
`deckcore.pinned_elsewhere` from its pool; `optimize` keeps pins-here (line ~214) and
refuses pinned-elsewhere adds (~257). The hard core holds; the gaps are softer
surfaces and the moving experience.

- ☐ **Enforcement sweep** — every surface presenting a card as *available* honors pins
  the same way, **labeling rather than hiding** ("Wizard's Staff — pinned to
  iron-man"): `edhrec.recommendations` owned/"add" split (line ~81; currently
  pin-blind), Build Next candidate + combo views, `deck_fit` alternatives /
  `deckcore.new_arrivals` fits, and the add-card validator (stays a **warning** — a
  deliberate add beats the reservation, wording names whose pin is overridden).
- ☐ **Pin management screen** — `/pins` (auth-gated): every pin in one table (card ·
  pinned deck · also-in decks · owned count), one-tap unpin, and **move** (repin) as a
  single action. Linked from Decks and the card panel.
- ☐ **Pins follow deliberate moves** — when Remove/Replace or add moves a pinned card
  into a different deck, offer "move the pin too" in the confirmation (default yes when
  the source deck no longer runs the card). Never silent: the flow's response states
  the `pins.csv` change.
- ☐ **Shared-copy interplay** — the ⇄ badge and `deck_conflicts` name the pin when a
  shortfall involves one ("short 1 copy; 1 pinned to yshtola").
- ☐ Tests: pinned-elsewhere excluded from the EDHREC owned split; move-pin atomicity
  (`deckcore.save_pins` round-trip); badge wording.

## Phase 7 — Mana tab, explained (small)

Every data point gains a plain-language explanation, extending the screw/flood
definitions-as-data pattern rather than inventing a second one.

- ☐ Each stat (keepable %, ≥3-land openers, 4th land by T4, per-color P(≥1)/P(≥2 by
  T3), risky-on-curve, Karsten adequacy, goldfish tiles, clock) gets a collapsible
  "**what this means**" note: one sentence of definition, one of why it matters, one
  of what healthy looks like for this deck's curve (Karsten targets stated as
  guidelines).
- ☐ Notes are **data beside the numbers** — an `explain` dict from the producing
  engine (`manabase.analyze`, `goldfish.simulate`), rendered by both surfaces and
  carried in `--json`. No prose hardcoded in templates.
- ☐ Existing honesty labels (unconditional probabilities, "identity approx.",
  fallback-tier sim) move INTO their stat's explainer so the caveat sits with its
  number.
- ☐ Tests: every rendered stat has a non-empty engine-supplied explainer;
  `test_design_tokens` unchanged.

## Phase 8 — Lift the optimizer gate: the role-repair fix (medium; run FIRST or parallel)

The standing freeze (handoff open item 0; full finding in
`spec-optimizer-hardening.md` "Typed-data role-repair churn"). Root cause, two layers:
`ROLE_RANGE` (`optimize.py:43`) is archetype-blind (a control deck's `counter: 15`
reads as nine excess), and the repair path ignores the ≥25-point field-margin gate, so
template pressure cuts field-superior keeps (observed: Wall Crawl 41% → Masked Meower
18%, and three more, all recorded there).

- ☑ **Fix direction 1 (mandatory):** repair swaps must satisfy the same ≥25-point
  `value_of()` margin as field swaps — kills every observed bad proposal by
  construction.
- ☑ **Fix direction 2 (mandatory):** templates become archetype-aware. The deck header
  `# Archetype:` exists and is unread here — parse it; a `control` archetype widens
  the counter max and relaxes the ramp min; define the per-archetype deltas as a small
  table beside `ROLE_RANGE` with the default = today's ranges. Only archetype words
  actually present in the six decks' headers need mappings; unknown words = default.
- ☑ **Fix direction 3 (explicitly skipped):** suppressing repair on hand-ratified
  decks — the margin gate makes it redundant; record the skip here so it reads as a
  decision.
- ☑ Tests (`test_optimize.py`, monkeypatched-field pattern): each of the four recorded
  bad proposals dies; a genuine role hole (low-value filler, template shortfall,
  margin-clearing candidate) still repairs; idempotency re-proven with typed attrs
  present.
- ☑ **Post-review remediation (2026-08-13, from the adversarial verification pass):**
  the archetype table is a *loosening*, so it gained tests in the loosening direction
  (a widened floor permitting a swap the default refused; a widened band still not
  overruling the field veto); `field_knows()` separates "the field plays this 0% of the
  time" from "the field has no row for this card" and the preview prints `no field
  data` + `[fit-driven]` instead of claiming a measured `0% field`; unmatched
  `# Archetype:` words are reported (`archetype_unknown`) rather than silently buying
  nothing; and the ⚡/Build-Next routes now flash which template judged the deck, since
  a loosening must be disclosed on the surface that triggers it (invariant 10).
- ☐ **Acceptance, live (GitHub runner or player PC — not a sandbox):** `optimize --all`
  preview on real field data across all six decks → zero field-inferior cut proposals;
  the four notes-file churn guards from 2026-08-12 become redundant (leave them in
  place — they're player notes); then and only then update handoff: the
  `--apply`/⚡/`refresh --optimize` freeze is LIFTED. The CLAUDE.md top-25 ≥~50%
  overlap check applies to the first real `--apply` after the lift.

## Phase 9 — The "what do I cut" surface (small-medium; after 8)

The #1 coaching pain in the research (§4.7). The engines exist; this is one honest
view. Anchor: `deck_fit.dead_weight` (line ~338 — below-deck-median fit, no theme tie,
no staple pull; already rendered in the Power tab as "Pulling the Least Weight").

- ☐ A **Cuts panel** extending the Power tab's dead-weight block + a `-- IF YOU MUST
  CUT --` section in the coaching packet: ranked ascending by the same `value_of()`
  the optimizer uses (one scorer, codemap rule), each row carrying its evidence —
  fit vs. deck median, field % (or "no field data"), role surplus/shortage under the
  Phase-8 archetype-aware template, and **protections honored and shown**: commander,
  basics, `card_notes.csv`, `.notes.md`-named, `Source=manual-*` cards appear greyed
  with "protected — your call, not the tool's", never omitted (label-don't-hide).
- ☐ Explicitly **advisory and read-only**: no route writes anything; the panel says
  "a starting point for your judgment, not a cut list" (the dead-weight wording
  precedent).
- ☐ Tests: protected cards present-but-flagged; ordering matches `value_of`; renders
  with and without field data (honest note when absent).

## Phase 10 — Phantom disruption in the goldfish (medium; after 2, EXPERIMENT — scope-gated)

Research §4.6: demand for "an opponent" is really demand for cheap approximations
(Playgroup.gg's Sparring counters/wipes on a timer; Krarkaplayer's inert-160-life
pod). This revisits `research-simulation.md`'s tier-2 deferral in the narrowest
possible way. **Gate: if any part muddies the CRN A/B contract, stop and record — the
A/A-exact-zero test decides.**

- ☐ CLI flag **`--disruption standard`** (default off; off = byte-identical reports —
  prove it): a seeded event schedule per game — one board wipe on a turn drawn from
  {5,6}, spot removal of the highest-power sim creature every N (default 3) turns
  starting T3, and the commander returning to the command zone on its removal with
  tax modeled on recast (the cost model already parses costs — add the +{2}).
- ☐ **CRN isolation:** disruption events draw from a SECOND `random.Random` seeded per
  game index, independent of the shuffle stream, so both A/B arms face identical
  disruption and the pairing survives. The A/A test runs with disruption ON and must
  still yield exact zeros.
- ☐ Report additions (definitions as data): clock and commander-uptime with vs.
  without disruption, rebuild rate (P(board restored within 2 turns of a wipe)).
  Assumptions block: the schedule is a crude stand-in for real opponents and says so.
- ☐ **v1 is CLI + assess-packet only** — no dashboard tiles until the player has seen
  real output and wants them (experiment status).
- ☐ Tests: off = byte-identical; on = deterministic per seed; A/A zero with
  disruption; tax arithmetic on recast.

## Phase 11 — Gap sweep from the repo grounding pass (small items)

Found while grounding this spec against `docs/codemap.md` and the open trackers;
folded here because each intersects this season's surfaces. (The rest of
`spec-repo-hardening.md` Phase 4 stays tracked there — not duplicated.)

- ☐ **11a. Buy-tab rows panel-clickable** (codemap "still open"; hardening #6): rows
  for non-deck cards are plain text because the inlined panel only carries deck-card
  details. Reuse the `.cardlink` markup with the panel's non-owned fallback path
  (Scryfall type-line, Phase-4-era behavior).
- ☐ **11b. CSB one-away combos on saved-deck dashboards** (hardening #7): the client
  (`spellbook.near_for_deck`) exists and Build Next renders it; wire the same merged
  Combo Watch into `build_dashboard.generate` for saved decks — matters more once the
  table card cites combo disclosures.
- ☐ **11c. Goldfish A/B deltas in the card-panel Replace flow** (hardening #5): with
  Phase 2, `simulate_ab` also reports clock deltas — surface the paired CI in the
  Replace confirmation ("this swap: commander on time +2pp ± 1, first kill −0.3
  turns"). Async, degrade to nothing on a cache miss; never block the edit.
- ☐ **11d. `--audit-flags` helper** (hardening #8; handoff acceptance item 2): sample
  N enriched cards, print name / flags / oracle snippet for eyeballing — closes the
  standing ~30-card flag-audit item the owner keeps deferring, and Phase 1 adds a new
  column that needs the same audit path.
- ☐ **11e. sw.js cache versioning done properly** (known-deferred in hardening): this
  season adds two routes and touches dashboards — replace the hand-pinned `mtgdb-v1`
  with a version derived at deploy/sync time (e.g. short git SHA via the existing sync
  path) so installed phones stop holding stale assets. Small, but do it once instead
  of five manual bumps across phases 4/5/6/7/11.

---

## Backlogged, specced elsewhere

- **4-player pod simulation** → `docs/spec-pod-simulation.md` — status BACKLOG by
  player decision 2026-08-13 ("massive undertaking — spec it, backlog it"). Not part
  of this season; its spec defines the promotion criteria.

## Sequencing recap

**8** first or parallel (lifts the freeze) → spine **0 → 1 → 2 → 3 → 4** → **9** (after
8), **10** (after 2), **5 / 6 / 7 / 11** in any order. One PR per phase; resync after
every squash-merge.

## Acceptance (season-level)

- Y'shtola's dashboard: no Unsorted section, no misfiled types, one merged Plains
  line; every already-clean deck unchanged by the same regroup.
- A Power-enriched deck shows a clock with definitions and the understatement caveat;
  an un-enriched clone shows the honest gate instead.
- The Power tab shows detected + player-set bracket together whenever they differ.
- The table card renders offline, one screen, phone and print.
- The mulligan trainer's verdict matches the sim's rule on the same seed, with the why.
- A pinned card never appears as available on any surface without its pin named.
- Every Mana-tab number can explain itself without leaving the page.
- The optimizer freeze is lifted with the four recorded bad proposals provably dead
  and idempotency re-proven; the cut surface never writes.
- `--disruption` off is byte-identical; on, the A/A tripwire still reads exact zero.
