# Spec — The "Table-Ready" Season

**Status: ☐ DRAFT — awaiting player review (2026-08-13).**
**Source:** the competitive-landscape research (`research-competitive-landscape.md` §4)
plus player direction 2026-08-13: *"I like 1, 2, and 5"* (goldfish clock, Rule-0 card,
mulligan trainer), keep auto-assigned brackets but make them overridable, fix the
section misfiles and the split-Plains line, harden and flex the pin feature, and
explain every Mana-tab number. Ticks land here as work ships; this file is the tracker.

**What this season deliberately does NOT touch:** the optimizer. None of these phases
run or modify `optimize.py`, so the role-repair-churn gate
(`spec-optimizer-hardening.md`, handoff open item 0) neither blocks this season nor is
resolved by it. The `--apply`/⚡ freeze stays in force throughout.

---

## Phase 0 — Deck hygiene: sections tell the truth (small; do first)

Two player-visible bugs on the Y'shtola dashboard, both confirmed in
`data/decks/yshtola-nights-blessed.txt`, both with the same root cause family: **the
deck file's sections are the display**, and two write paths put lines where they don't
belong.

- ☐ **0a. Re-run `deck_sections.py --all --apply` on the typed snapshot.** White
  Auracite (Artifact) and Risky Shortcut (Sorcery) sit in the *Creatures* section
  because the card-panel Replace flow inserts the incoming card at the outgoing card's
  slot — right section for like-for-like swaps, wrong the moment a Sorcery replaces a
  creature — and on name-only data the regroup couldn't type them to move them. The
  committed attrs snapshot (live since 2026-08-12) now types all five Unsorted cards
  *and* both misfiles (verified: Risky Shortcut=Sorcery, White Auracite=Artifact, Eye
  of Nidhogg=Enchantment, Tataru/Hermes/Alisaie=Creature, Dancer's Chakrams=Artifact).
  One idempotent regroup resolves the Unsorted section and the misfiles across all six
  decks. Verify: no `Unsorted` section remains; 100 cards per deck; `singleton_violations`
  clean.
- ☐ **0b. Merge duplicate same-name lines within a section.** `Basics` holds `1 Plains`
  (line 109) and `3 Plains` (line 111) as separate lines — the 2026-08-11 buy-migration
  appended "a 4th Plains" as a new line instead of incrementing the existing one, and the
  dashboard renders lines as-is (edit paths must preserve lines, so nothing downstream
  merges them). Fix in two layers: (1) `deck_sections.py` regroup learns to merge
  same-name lines landing in the same section (sum quantities; keep first position;
  basics and any legitimately-multiple card only — for singletons a duplicate line is a
  violation `singleton_violations` already flags, not a merge). (2) The app's add paths
  (`add-card` flow, buylist-arrival pulls, future writers) increment an existing line in
  the target section instead of appending a twin. Tests: a deck with split basics
  survives a regroup merged with quantities intact; `test_deck_edit`'s
  preserve-quantity/section/comment guarantees still hold.

## Phase 1 — Enrichment carries creature Power (small-medium; prerequisite for Phase 2)

The goldfish clock needs to know how hard the board hits. Neither
`collection_attrs.csv` nor the snapshot carries power today (verified: header is
`Name,Type,MV,Colors,Cost,Sub-types[,Scryfall],Produced,Flags`).

- ☐ `carddb.py` appends a **`Power`** column (both API and bulk paths) — the creature's
  printed power; `*`/non-numeric stored verbatim and treated as unknown by consumers.
  Appended **after** existing columns so older attrs files still load (same
  back-compat shape Produced/Flags used). Same **empty-vs-absent rule**, stated in the
  header comment: empty cell = "not a creature / no power", absent column = "unknown —
  clock unavailable, say so."
- ☐ `mtglib.Card` gains `power` (int | None); `deckcore.load_attrs`/`apply_attrs` and
  deck `.attrs.csv` carry it; the attrs-snapshot Action regenerates with the new column
  (its five guards unchanged).
- ☐ MDFC/split faces: front face's power via the same face-aware path `oracle_flags`
  uses. No toughness column — nothing in scope consumes it (goldfishing has no blockers);
  add it the day something does.

## Phase 2 — The goldfish clock (flagship; medium-large)

*"What turn does this deck actually present lethal?"* — the number the official
brackets are now defined by (B2 ≈ satisfied with T8+ endings, B3 ≈ T6+, B4 ≈ T4+) and
no tool on the market measures. Research: `research-competitive-landscape.md` §4.1.

- ☐ **Combat model inside the existing turn loop** (`goldfish.py`): creatures cast by
  the sim enter with summoning sickness, attack every turn thereafter with printed
  power; no blockers, no combat tricks (goldfish = uncontested, and the report says
  so). The commander is cast (already modeled) and attacks like any creature;
  commander-damage kills (21) count.
- ☐ **Two numbers, definitions shipped as data** (same contract as screw/flood):
  **first-kill turn** (cumulative damage to a single 40-life opponent — "presents
  lethal") and **table-kill turn** (120 across three sequential 40-life opponents).
  Report median + P(first kill ≤ T4/T6/T8) so the bracket anchors read directly.
- ☐ **Honesty gates.** Combat damage only — drain/burn/X-spell/token-swarm noncombat
  damage is NOT modeled in v1, so the clock is an **understatement** for decks like
  Y'shtola (Exsanguinate, Vito, Blood Artist); the assumptions block names the
  limitation and the surfaces print it. Missing Power data (un-enriched, or >25% of
  creatures unknown) → the tile prints "enrich to unlock" instead of numbers, same
  gate shape the sim already uses. Alt-win/combo decks: the combo tab's CSB data is
  cited beside the clock, not folded into it.
- ☐ **Bracket mapping, advisory wording**: "Uncontested goldfish clock: first kill
  median T7 — consistent with the Bracket 3 expectation (~T6+). Real games run slower."
  Never reclassifies the bracket by itself; it's evidence on the Power tab and in the
  Rule-0 card.
- ☐ **CRN A/B compatibility**: the clock rides the existing seeded loop, so
  `--ab "Out=In"` automatically reports paired clock deltas ("this swap speeds your
  first kill by 0.4 turns ± 0.2"). The A/A-exact-zero tripwire must still pass — the
  combat model may not re-sort the compiled deck.
- ☐ **Surfaces:** stat tiles in the dashboard Mana tab's goldfish panel + the Power
  tab's bracket block, `/deck/<stem>/assess`, the coaching packet, `--json`. Cache via
  the existing `sim_for_deck` entry point (parameters join the cache key).
- ☐ Tests: a vanilla-creatures fixture deck with hand-computable clock; the
  understatement label fires when drain cards are present; the Power-data gate; A/A
  zero on the extended report.

## Phase 3 — Bracket: auto-assigned, player-overridable (small)

Player decision 2026-08-13: **keep the automatic bracket** ("lets me know where the
deck currently sits") **and add an override** for disagreement — not the
declare-and-flag inversion the research's Moxfield users wanted. Design:

- ☐ Optional deck header **`# Bracket: <1-5>`** = the player's override. Absent →
  today's behavior, detected bracket shown as now.
- ☐ Present → every surface shows **both, never silently one**: "Bracket 3 (your
  setting) · detected 4: 5 Game Changers — over the B3 cap". The override wins for
  display ordering and the Rule-0 card headline; the detected verdict and its reasons
  stay visible (honesty rule: the evidence never disappears). `power.py --rank` and
  `--json` carry `bracket_declared`, `bracket_detected`, and a `mismatch` flag.
- ☐ App control: a small selector on the dashboard Power tab (editable surface only)
  writing the header line through the existing deck-edit path (comment/section
  preservation guaranteed by `test_deck_edit`).
- ☐ Recertify addition: a step diffing `data/reference/game_changers.txt` against
  Scryfall's `game_changer` field (canonical machine-readable list, confirmed in
  research §5) so WotC revisions surface as a one-click check.

## Phase 4 — The Rule-0 table card (small-medium)

One phone-first, print-friendly screen that answers the pre-game conversation —
assembled entirely from shipped engines. Research: §4.2 (Bracket 1's Game-Changer
exception literally requires cards be "discussed pregame"; no tool generates the
artifact).

- ☐ Route `/deck/<stem>/table-card` + a "🃏 Table card" link on the dashboard and Decks
  page. Contents, in table-conversation order: commander + colors + archetype line ·
  bracket (player setting if present, detected beside it, top reasons) · Game Changers
  named · disclosures (mass land denial: none/list · extra turns count · 2-card combos
  present, from CSB, with one-away count) · the goldfish clock line (Phase 2, when
  available) · win conditions + game plan (first lines of `.notes.md` Plan, else role
  heuristics, labeled which) · "estimates, not verdicts" footer.
- ☐ Self-contained render (inlined tokens.css, print stylesheet, no external assets —
  same rules as dashboards); degrades honestly when a data source is absent (no CSB
  cache → "combos unverified offline", no clock → line omitted).
- ☐ Tests: renders for a fixture deck offline; every disclosure line sources from the
  same engine call the dashboard uses (no second derivation).

## Phase 5 — Mulligan trainer (medium)

Deal real hands from the real deck; the player calls keep/ship; the sim shows its
verdict and *why*. Research §4.5: the 2025–26 trainer wave is deck-generic and
online-only; ours is deck-aware and offline.

- ☐ Route `/deck/<stem>/mulligan`: deals from `goldfish.compile_deck` with a fresh
  seed per hand; London flow (keep → bottom N picker, ship → redeal at 7 with the
  floor-5 rule the sim already implements).
- ☐ After the call, the reveal: the sim's keep verdict for that exact hand and the
  evidence — lands, colored sources vs. the deck's curve needs, ramp/draw present,
  P(commander on time | this keep) from the existing engine, screw risk. Agreement or
  disagreement is stated neutrally ("the sim would ship this: 1 land, 9% chance of
  three land drops by T3") — the sim's mulligan rule is a heuristic and the page says
  so.
- ☐ Per-deck session stats (hands seen, agreement rate, kept-hand land distribution)
  in **localStorage** v1 — private, offline, zero server state; a future `games.csv`
  integration is noted, not built.
- ☐ Tests: the dealt-hand endpoint is seeded-deterministic; verdict math matches
  `goldfish`'s mulligan rule on fixture hands; no network.

## Phase 6 — Pins v2: reserved means reserved, moving is easy (medium)

Player intent: *"when I pin a card to a deck I don't want other decks to use it or
count it when a deck is being created… but flexible, cards shift around."* Current
state (verified): `auto_build` excludes `pinned_elsewhere` from its pool and
`optimize` both protects pins-here and refuses adds pinned elsewhere — the hard core
already holds. The gaps are the softer surfaces and the moving experience.

- ☐ **Enforcement sweep** — every surface that presents a card as *available* honors
  pins the same way: the EDHREC owned/missing split (`edhrec.py` — a pinned owned card
  currently shows as an "add"), Build Next's candidate/combo views, `deck_fit`/
  `new_arrivals` fits lists, and the add-card validator (today a *warning*; stays a
  warning — the player's deliberate add beats the reservation, but the wording states
  whose pin is being overridden). Each surface labels rather than hides: "Wizard's
  Staff — pinned to iron-man" beats silent omission (grounding rule: say why).
- ☐ **Pin management screen** — `/pins`: every pin in one table (card · pinned deck ·
  also-in decks · owned count), one-tap unpin, and **move** (repin to another deck) in
  a single action instead of unpin-then-repin. Linked from Decks and the card panel.
- ☐ **Pins follow deliberate moves** — when the card panel's Remove/Replace or the
  add-card flow moves a pinned card *into* a different deck, offer "move the pin too"
  in the confirmation (default yes when the source deck no longer runs the card).
  Never silently: `pins.csv` changes are logged in the flow's response.
- ☐ **Shared-copy interplay** — the ⇄ badge and `deck_conflicts` output name the pin
  when a shortfall involves one ("short 1 copy; 1 copy pinned to yshtola"), so
  over-commitment reports and pins stop being parallel truths.
- ☐ Tests: pinned-elsewhere excluded from the EDHREC owned split; move-pin
  atomicity; the badge wording.

## Phase 7 — Mana tab, explained (small)

Player ask: every existing data point gains a plain-language explanation. The
screw/flood definitions already ship as data and print beside their tiles — extend
that pattern to the whole tab rather than inventing a second one.

- ☐ Each stat block (keepable %, ≥3-land openers, 4th land by T4, per-color P(≥1) /
  P(≥2 by T3), risky-on-curve list, Karsten source adequacy, goldfish tiles, clock)
  gets a collapsible "**what this means**" note: one sentence of definition, one of
  why it matters, one of what a healthy number looks like for this deck's curve
  (Karsten targets where they exist, stated as guidelines).
- ☐ The notes are **data beside the numbers** (a `definitions`/`explain` dict from the
  producing engine, rendered by both surfaces), not prose hardcoded in the template —
  same single-source rule as the screw/flood definitions, so the CLI `--json` carries
  them too.
- ☐ Existing honesty labels (unconditional probabilities, "identity approx.",
  fallback-tier goldfish) move INTO their stat's explainer so the caveat sits with the
  number it qualifies.
- ☐ Tests: every stat the dashboard renders has a non-empty explainer from the engine;
  tokens-only styling (`test_design_tokens` unchanged).

---

## Sequencing

**0 → 1 → 2 → 3 → 4** is the dependency spine (hygiene first; Power column before the
clock; bracket field before the table card that headlines it). **5, 6, 7** are
independent of the spine and of each other — schedule by appetite. Nothing here waits
on, or touches, the optimizer gate.

## Acceptance (season-level)

- Y'shtola's dashboard shows no Unsorted section, no misfiled types, one merged
  Plains line — and every other deck survives the same regroup unchanged where it was
  already clean.
- A deck with enriched Power data shows a clock with definitions and the
  understatement caveat; an un-enriched clone shows the honest gate instead.
- The Power tab shows detected + player-set bracket together whenever they differ.
- The table card renders offline, one screen, phone and print.
- The mulligan trainer's verdict matches the sim's rule on the same seed, always with
  the why.
- A pinned card never appears as available on any surface without its pin named.
- Every Mana-tab number can explain itself without leaving the page.
