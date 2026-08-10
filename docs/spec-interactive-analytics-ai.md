# Spec & Tracker — Interactive Analytics + AI Deckbuilder

**Type:** feature spec + progress tracker (living document — update status as work lands).
**Started:** 2026-07-22 · **Status:** 🟢 Phases 0–5 shipped + enrichment (Scryfall API, now **production-aware**, and its flags now feed `classify()`) + EDHREC staples + Commander Spellbook combos + **goldfish Monte Carlo (Phase 7)** + **grounded subagents (Phase 8)** + **a rules layer (Phase 9)** · the **engine-upgrades season is complete** (A, B, C, D, A-F) · remaining: optional polish (EDHREC "Lift", CSB on the saved-deck dashboard, grow card_notes.csv, a card-panel Rules tab)
**Companion docs:** blueprint/rationale in [research-roadmap.md](research-roadmap.md) ·
current project state in [handoff.md](handoff.md) (history lives in `git log`).

> Update rule: when a task ships, tick its box and update the phase status + the
> Changelog at the bottom. Keep the tracker table in sync.

**Status legend:** ☐ not started · ◐ in progress · ☑ done · ⊘ dropped/deferred

---

## 1. Goal

Make the site an end-to-end, **analytics-first Commander deckbuilder for an expert
player**: everything interactive, full auto-built decks in Build Next, full per-card
strategy, and a browsable collection — grounded in real data, with **AI assessments**
delivered as a Claude Code skill. **Scope note (amended 2026-08-10):** tier-1 goldfish
Monte Carlo is now **in scope** per [research-simulation.md](research-simulation.md);
opponent / game simulation remains out of scope (tier 2 deferred, tier 3 rejected).

## 2. Locked decisions (see roadmap for detail)

- **Web app = deterministic analytics** (heuristic, offline, free, grounded). **AI =
  a Claude Code skill** on the subscription — *no* embedded Anthropic API, *no* per-token cost.
- **RAG = the skill's retrieval discipline** (read card DB + fetch Scryfall oracle/rulings
  + run analytics, answer only from that), enforced by skill grounding-rules — not a vector DB.
- **Buy-links ×3**: TCGplayer (Scryfall `purchase_uris`), ManaPool, Card Kingdom. **No price feed.**
- **Optional bridge**: web app "Export assessment packet" → the skill consumes it.
- **Data**: local Scryfall bulk DB (+ rulings), Commander Spellbook API (combos /find-my-combos),
  EDHREC via `pyedhrec` (inclusion / high-synergy / Lift; cached, graceful degradation).
- **Grounding fix**: `power.py` bracket formula was research-refuted — hedge it; use CSB `bracketTag`
  + the confirmed "Bracket 3 ≤ 3 Game Changers" rule.

## 3. Progress tracker

| Phase | Deliverable | Status | PR |
|------|-------------|--------|----|
| 0 | Reusable card panel + `/api/card` + clickable cards | ☑ Done (deferred: bulk DB, CSB/EDHREC clients) | #18 |
| 1 | Interactive Collection (browse/search/filter) | ☑ Done (EDHREC staple chip deferred) | #24 |
| 2 | Manabase & consistency engine (flagship) | ☑ Engine + dashboard + wired into auto_build | #20, #23 |
| 3 | Full auto-built decks for Build Next | ☑ v1 + images + on-view analysis (deferred: EDHREC/CSB) | #19, #21, #22, #23 |
| 4 | Full card strategies | ☑ Grounded "how it works" (role + oracle mechanic + combo + usage) | #33 |
| 5 | AI coaching skill + export bridge | ☑ Done | #25 |
| 7 | Goldfish Monte Carlo (`scripts/goldfish.py`) — sequenced play beside the closed forms | ☑ Engine + CRN A/B + cached loader + dashboard/assess panels | #93 |
| 8 | Grounded subagents (`.claude/agents/`) + `carddb.py --verify` — conclusions instead of transcript dumps | ☑ card-verifier + collection-auditor + the verify CLI + SKILL.md delegation | #94 |
| 9 | Rules layer (`scripts/rules.py` + `scripts/rulings.py`) — the tool behind "never from memory" | ☑ CR fetch/parse/lookup/search/glossary + per-card rulings + the skill's retrieve→read→cite discipline | #95 |

**Also shipped (not in the phase list):** Build Next redesigned to the Decks style + a
"build any commander" box (Scryfall color-identity lookup → any commander, #22); ManaPool
buy-link fixed to the direct card page + Card Kingdom verified (#23); `power.py` bracket
wording hedged to match the one confirmed WotC rule (#23).

**Seed already shipped:** the bottom-sheet card panel + clickable commander links
(PR #17) are the prototype Phase 0 generalizes into a reusable, site-wide component.

---

## 4. Phase specs

### Phase 0 — Foundation & data plumbing  ◐
Unlocks site-wide interactivity + the data layer later phases consume.
- ☑ Reusable card panel component (`webapp/static/cardpanel.{css,js}` + `_cardpanel.html`,
  included by `base.html`) — bottom-sheet, event-delegated so dynamic cards work.
- ☑ `/api/card/<name>` endpoint (`scripts/card_api.py`): roles, MV/type, notes,
  combo membership, "used in decks X/Y", owned/qty, image, **buy-links ×3**.
- ☑ **Rulings** + oracle + image fetched client-side from Scryfall in the panel.
- ☑ Card names clickable site-wide (Build Next, Collection, Wishlist, Shared).
- ☑ **Buy-links ×3** (TCGplayer via search URL; ManaPool + Card Kingdom search URLs).
- ☑ **Whole-collection enrichment** — `carddb.py` enriches via Scryfall's `/cards/collection`
  API by default (exact printing → colors / types / mana value / correct-art ids; bulk kept as
  the offline path). Verified 2040/2040; auto-runs on collection upload. *(Scryfall turned out
  to be reachable on the player's machine — the "firewalled" note applied only to the CI sandbox,
  which also unblocks the EDHREC/CSB clients below.)*
- ☑ **Production-aware enrichment** — `carddb.py` also stores `Produced` (what each card
  actually taps for, from Scryfall `produced_mana`) and `Flags` (oracle-derived:
  `etb-tapped`/`-cond`, `rock`, `dork`, `ramp`, `draw`, `mana2`/`mana3`) via the new
  `scripts/oracle_flags.py`. Two columns appended to `collection_attrs.csv`; an empty cell
  means "produces nothing", an absent column means "unknown". Workstream A of
  [spec-engine-upgrades.md](spec-engine-upgrades.md).
- ☑ **`classify()` reads the flags** — `oracle_flags` gained `removal` / `wipe` / `counter`,
  and `mtglib.classify()` consults `Card.flags` **only where the curated name lists are
  silent** (curated always wins, first-writer-wins). Role/category counts — which feed
  `power.assess`, the dashboard and the optimizer's role-template guardrails — now cover
  cards no hand-maintained list has caught up with. Follow-up A-F of
  [spec-engine-upgrades.md](spec-engine-upgrades.md); the whole **engine-upgrades season is
  complete** (workstreams A, B, C, D + A-F, five PRs).
- ☐ Cached CSB + `pyedhrec` client wrappers — *deferred to their consuming phases (1, 3).*
- ☑ Verify ManaPool & Card Kingdom per-card URL schemes — **verified live 2026-08-10**
  from a GitHub Actions runner (`recertify.yml`): 4/4 straight 200s — ManaPool's direct
  card page for both a plain and an apostrophe name (`/card/urzas-saga`, so the slug
  rule holds) and Card Kingdom's by-name search. No scheme fix needed.
**Acceptance:** ☑ verified in a real browser — clicking a card opens the panel with image,
live oracle text, rulings, grounded local data, and three working buy-links.

### Phase 1 — Interactive Collection  ☑
- ☑ Browsable grid of all owned cards with images (`webapp/static/collection.js`) — lazy,
  IntersectionObserver → batch-resolve CDN images (75/req) so a 1,800-card grid only fetches
  what you scroll to.
- ☑ Live search + filters: name, colors (subset), type, role, "in a deck", "priced", + sort
  (name / value / MV). Client-side, instant.
- ☑ Each card clickable → the shared panel (reuses Phase 0 `data-card`).
- ☑ **"How staple is this" chip** — every card in the grid gets a TOP 100 / TOP 500 / TOP 2K badge
  from Scryfall's `edhrec_rank`, plus a **"Sort: Most played (EDHREC)"** option. Free of extra
  requests: the batch `/cards/collection` call the grid already makes for images returns the rank.
  (Chose Scryfall's shipped rank over `pyedhrec` — it's per-card, collection-wide, and needs no
  new dependency or scraping. `scripts/edhrec.py` still covers per-commander staples.)
**Acceptance:** ☑ verified — search "sol" → 12, "in a deck" → 266, role "ramp" → 40; clicking a
card opens the panel; honest name-only note when filters need enrichment. Staple chip verified
against live data (Sol Ring #1 → TOP 100, Swords to Plowshares #11 → TOP 100, Raging Goblin
#15,821 → no badge).

### Phase 2 — Manabase & consistency engine (FLAGSHIP)  ◐
- ☑ `scripts/manabase.py` — exact hypergeometric engine (`math.comb`), verified against a known
  value (P(≥1 ace in 5) = 0.3412).
- ☑ Opening-hand + by-turn-N odds: keepable-hand %, ≥3 lands in opener, 4th land by T4, per-color
  P(≥1 source) / P(≥2 by T3).
- ☑ Per-card **risky-to-cast-on-curve** check (P of having the colored pips by the card's CMC turn).
- ☑ Per-color source adequacy vs **Karsten** guidelines (~19 single-pip / ~23 double-pip).
- ☑ **"Consistency & Manabase"** dashboard section (degrades to an "enrich to unlock" note on
  a name-only collection; sources come from the enriched collection's `Cost`/colors).
- ☑ Wired into `auto_build`: **pip-demand-weighted basics** + full **power/bracket + Consistency/Manabase**
  analysis shown on the "Build this deck" view (#23).
- ☑ **Colored sources from actual production** — with an enriched collection, each land
  contributes what it really taps for (`Card.produced`) instead of its color identity;
  `deck_stats` reports `color_sources_basis = {'produced_lands': n, 'identity_lands': m}`
  and `print_report` / the manabase CLI / the dashboard pip table / the assess packet each
  print an "identity approx." label whenever `identity_lands > 0`. Unowned lands stay on the
  identity basis by design, so a deck with any unowned land never claims false precision.
**Honest simplifications:** probabilities are UNCONDITIONAL (not Karsten's mulligan-adjusted %),
and where production data is missing sources still approximate a permanent's output from its
color identity (rough for fetches/oddballs) — now always labeled as such.

### Phase 3 — Full auto-built decks for Build Next  ☑
**Detailed spec:** [spec-build-next-full-deck.md](spec-build-next-full-deck.md).
- ☑ `scripts/auto_build.py`: assemble a legal 99 from the owned pool (deck_fit scoring +
  role targets + archetype support + `deck_conflicts.available_pool`, color-identity-legal).
  Now **tribal-aware** (seeds on-tribe creatures) and takes `skip_deck` so a REBUILD can reuse
  its own cards instead of counting the deck against itself.
- ☑ Build Next: commander → "Build this deck" → interactive decklist (curve, roles, the 99),
  plus a Scryfall-autocomplete "build any commander" box.
- ☑ CSB `/find-my-combos` "one card away" upgrade surfacing (`scripts/spellbook.py` → assess packet + Build Next).
- ☑ Export (.txt / ManaPool) + "Save to my decks".
**Acceptance:** produces a 100-card, in-color, role-balanced draft entirely from owned cards, with
gaps-to-buy listed; honest that it's a heuristic draft.

### Phase 4 — Full card strategies  ☑
- ☑ Panel **"Strategy"** section: the curated note when present, else a grounded generated blurb —
  a role/type/MV scaffold (server `card_api._strategy`) + **mechanic tags read off the oracle**
  (client `cardpanel.js`: draws / spot-removal / tutor / ramp / recursion / tokens / protection /
  sacrifice / stax / doubling …) + combo membership + "in N of your decks".
- ☑ Falls back to the live **Scryfall type line** for non-owned cards (e.g. EDHREC buy targets),
  so a clicked card is never blank; rulings already surfaced (Phase 0).
- ◐ Grow `card_notes.csv` opportunistically — ongoing; the generated blurb covers the gap meanwhile.
**Acceptance:** ☑ owned cards always yield a grounded line (Sol Ring → "…accelerates your mana";
A.I.M. Synthoids → "A 2-mana creature"); non-owned fall back to the Scryfall type line + mechanics.

### Phase 5 — AI coaching skill + export bridge  ☑
Chose to **extend the existing `mtg-deckbuilder` skill** rather than fork a separate `mtg-coach`
(same persona / grounding / scripts / collection — coaching is deckbuilding). Runs in Claude
Code on the subscription; no Anthropic API in the app.
- ☑ `references/coaching.md` — the grounded method: rubric critique, cut/add **by candidate
  selection** (never invent cards), rules/interaction Q&A over oracle text + rulings, pilot /
  mulligan guide, deck-vs-deck, upgrade-to-bracket. *(Rules Q&A stopped being policy-only in
  Phase 9: the bullet now carries `rules.py` / `rulings.py` / `carddb --verify`.)*
- ☑ SKILL.md — coaching triggers in the description, a "Coaching & assessment" workflow, and a
  refreshed script list (manabase / combo_detector / auto_build / card_api / carddb / …).
- ☑ Web app **"Export assessment packet"** (`/deck/<stem>/assess.txt` + "📋 Assess" on the Decks
  leaderboard): decklist + power/bracket + consistency + combos + role/curve/pip numbers in one
  paste-able block to hand a deck to a coaching session.
**Acceptance:** ☑ the skill triggers on coaching asks; the assess packet renders grounded numbers
(Bracket 3 / Power 67 / role counts / combos) for a saved deck; scripts it references all run.

---

## 4b. Phase 6 — deck subtabs + manual adds (shipped 2026-08-09)

Added after the app went hosted (see `handoff.md`). Suite grew 127 → **153 tests**.

- ☑ **Deck page subtabs** — spec: [`spec-deck-subtabs.md`](spec-deck-subtabs.md).
  Six CSS-only tabs (Deck / Mana / Power / Buy / Plan / More) inside
  `build_dashboard.generate()`, so both surfaces get them from one change. Sticky tab
  bar, deep-linkable `#tab-buy`, last tab remembered per deck, print restores every
  panel. Empty tabs are dropped.
- ☑ **Add-card flow + advisor** — spec: [`spec-add-card-advisor.md`](spec-add-card-advisor.md).
  `＋ Add card` on the editable deck page: owned-card search → the deck's own section
  labels → validation (ownership · singleton · color identity hard-block · pin warning)
  → one-line insert → `Source=manual-add` in `.changes.csv` → fit verdict. The verdict
  states plainly when no EDHREC field data backs it. `optimize` prints an **advisory**
  manual-adds review and still never cuts a manual pick.
- ☑ **Dead weight — "Pulling the Least Weight"** (from the prior-art survey).
  `deck_fit.dead_weight()` names the cards scoring below the deck's own median fit
  that also show no theme tie and no staple pull, rendered in the Power tab. Measured
  **relative to the deck**, not against a fixed score, so it behaves the same with and
  without EDHREC data. Explicitly not a cut list.
- ☑ **Optimizer add-ranking symmetry + hardening round 2** — shipped; spec and the
  full 11-finding list in [`spec-optimizer-hardening.md`](spec-optimizer-hardening.md).
  Adds now use the same `value_of()` as cuts (sort + margin gate), proven by
  monkeypatched-field A/B tests. ◐ **One step still owed, live:** the CLAUDE.md
  top-25 overlap check on real EDHREC data (run `optimize --all` preview→apply→re-run
  from a machine that can reach EDHREC; revert if any deck drops below ~50%).
- ☐ *(unscheduled)* `auto_build` role-quota overrides — see §5 "consider later".

## 4c. Phase 7 — goldfish Monte Carlo (shipped 2026-08-10)

Workstream C of [`spec-engine-upgrades.md`](spec-engine-upgrades.md) §6, and the first
feature to land under the amended scope note in §1. Suite grew 320 → **375 tests**.

- ☑ **`scripts/goldfish.py`** — a seeded, stdlib, offline simulator: shuffle, London
  mulligan (keep 2–5 lands, floor 5, bottom excess lands beyond three then highest MV),
  on-the-play turn loop, untapped-first/color-greedy land drops, scarcest-color-first
  payment. Reports P(commander by turn N), keepable / mulligan rate / screw / flood,
  mean lands by turn, and the worst-sequenced cards. **The screw and flood definitions
  ship as data** (`report['definitions']`) and every surface prints them, so nobody
  supplies their own and misreads the number.
- ☑ **Two mana tiers, one of them labelled.** With workstream A's `Card.produced` /
  `Card.flags` a permanent taps for exactly what Scryfall says, taplands give nothing on
  the turn they drop (conditional ones pessimistically so, Q-A2), and `mana2`/`mana3`
  rocks accelerate. Without them the sim falls back to `colors or identity` — the exact
  expression `deck_stats` uses, so the sim and the closed forms carry ONE bias — and
  says so in `report['assumptions']`. Over 25% of nonlands with no mana value at all
  trips `have_data: False` and every surface prints the note instead of numbers.
- ☑ **A/B over common random numbers** (`simulate_ab`): both arms replay identical
  shuffles, so a paired confidence interval measures the swap rather than the luck. The
  incoming card must resolve through `mtglib.lookup` — never an invented card. An A/A
  run yields deltas of exactly 0.0, which is the tripwire for any refactor that
  re-sorts a compiled deck.
- ☑ **One cached entry point** — `sim_for_deck` writes `data/cache/goldfish/<stem>.json`
  keyed by deck/attrs mtime+size and the run parameters. The dashboard, the assess page
  and the assess packet all call it, so a page visit costs one simulation *per deck
  edit*, total. It catches everything and returns `None`; one guard, not three.
- ☑ **Surfaces:** a Goldfish Simulation panel in the dashboard's Mana tab (stat tiles
  with definitions, worst-sequenced `.cardlink` table, assumptions footer), the same
  numbers on `/deck/<stem>/assess`, and a `-- GOLDFISH SIMULATION --` block in the
  coaching packet. CLI: `python3 scripts/goldfish.py --deck … --collection … [--ab
  "Out=In"] [--json]`.
- ☑ **Deck-companion leg:** `deckcore.load_attrs`/`apply_attrs` now carry exact-case
  `Produced`/`Flags`, so a deck `.attrs.csv` powers the enriched model on a fresh clone
  with only the name-only snapshot.
- ⊘ **Out of scope, on purpose:** tier-2 scripted opponents, optimizer integration
  (advisory-only, a future spec — the swap gate's idempotency contract is load-bearing),
  and partner commanders (v1 simulates the parsed `# Commander:` line only).
- ⊘ **Recorded deviation:** `research-simulation.md` suggested A/B deltas "in the card
  advisor"; v1 puts them in the CLI instead.

## 4d. Phase 8 — grounded subagents (shipped 2026-08-10)

Workstream D of [`spec-engine-upgrades.md`](spec-engine-upgrades.md) §7. Suite grew
375 → **401 tests**. This phase makes no engine number different — it changes how much
transcript it costs to get one.

- ☑ **`carddb.py --verify "<name>"`** (repeatable, `--json`) — the prerequisite, because
  no CLI could verify a *single* card before: enrichment is whole-collection-only and
  `card_api` carries no oracle text. Names batch through the existing
  `/cards/collection` client and are reconciled **positionally** — Scryfall returns
  `data` in identifier order with the misses listed separately, so matching by name
  breaks the moment someone asks about a back face and the card comes back named
  `Front // Back`. Each miss retries once via `/cards/named?fuzzy=`, which tolerates a
  misspelling and surfaces the correction. Nothing resolves → `found: False`, which is
  where a hallucinated card name dies. Oracle text is joined face-aware; 30-day cache in
  `data/cache/scryfall/`; an unreachable Scryfall yields UNVERIFIED rows and exit 0 —
  the report IS the product.
- ☑ **`.claude/agents/card-verifier.md`** — one batched `--verify`, then one markdown
  table (Requested | Canonical | Cost | Type | Identity | Commander-legal | **verbatim**
  text) plus one `UNVERIFIED:` line. No paraphrase (a paraphrase is the misreading
  grounding rule 3 exists to kill), no hand-built URLs, no memory answers, no search
  transcripts.
- ☑ **`.claude/agents/collection-auditor.md`** — five read-only commands
  (`analyze_collection`, `deck_conflicts [--available]`, `power --rank`,
  `commander_finder`, `edhrec`), verdict-first output, every finding carrying its count
  and the exact producing command. It resolves the collection itself and repeats the
  CLI's name-only degradation warning rather than softening it. The privacy line is
  explicit: counts and ≤10 exemplar names, never `collection.csv` rows or prices
  wholesale — "read-only" alone would not stop Bash from `cat`-ing the private CSV into
  the parent transcript.
- ☑ **Both are `tools: Bash, Read`** and both Read
  `references/grounding-rules.md` first, citing rule numbers rather than carrying a copy
  that drifts. `tests/test_agents.py` pins six structural invariants, so widening an
  agent's tools means deliberately editing a test — the same friction
  `test_design_tokens.py` uses for new tokens.
- ☑ **SKILL.md "Delegate the heavy work"** is the deterministic path (automatic
  delegation is probabilistic), with pointers from workflow steps 3 and 6 and an
  **inline-fallback sentence**: where the Agent tool doesn't exist, the same work happens
  inline and the workflow is unchanged.
- ⊘ **No WebSearch/WebFetch fallback for the verifier** (Q-D1): UNVERIFIED-and-say-so
  beats reopening search-dump transcripts inside the agent. ⊘ **The per-deck coaching
  gather stays in the main session** (Q-D2) — delegating it would strip the champion
  persona of its evidence. ⊘ **Read-only is prompt-enforced**, not hook-enforced; a
  hooks-based hardening is out of scope.
- ⊘ **Acknowledged duplication:** `gen_card_notes.py` already implements batched
  oracle-text fetch. `verify_cards` is a second copy of that plumbing with a different
  contract; refactoring the two together is deliberately out of scope, recorded so it
  reads as a decision rather than an accident.

## 4e. Phase 9 — the rules layer (shipped 2026-08-10)

Workstream B of [`spec-engine-upgrades.md`](spec-engine-upgrades.md) §5. Suite grew
401 → **434 tests**. `coaching.md` had instructed answering rules questions "from the
Comprehensive Rules — never from memory" since Phase 5, with **no tool behind it**; the
whole rules knowledge base was a 38-line corrections file plus web search. This is the
tool.

- ☑ **`scripts/rules.py`** — downloads WotC's official Comprehensive Rules txt once into
  `data/cache/rules/` (gitignored — ~1 MB of copyrighted text revving 5–6× a year; the
  repo is public), parses it into rules / sections / chapters / glossary in **document
  order**, and answers by number (`lookup`, subrules and section/chapter context
  included), by phrase (`search`) or by term (`glossary_lookup`, with the rule refs the
  definition points at). Search scores +2 per distinct term, +5 for all terms, +10 for
  the exact phrase, ties by document order — a shortlist, never an answer.
- ☑ **Manual refresh only.** `--refresh` re-downloads; otherwise any cached copy is used
  and labeled `fetched <date>` from its mtime. No TTL, no `meta.json`, no surprise
  60-second fetch mid-question. First-ever run fetches; every failure returns the
  standard error payload with manual-download instructions and **never raises**.
- ☑ **Zero repo imports** — a first for the engine ring. Every other engine imports
  `mtglib`; rule text has no card names in it.
- ☑ **`scripts/rulings.py`** — Scryfall rulings for ONE card (`/cards/named?fuzzy=` →
  `rulings_uri`, 0.1s courtesy delay, `has_more` followed), 30-day cache in
  `data/cache/rulings/`. On a failure the cache is consulted **regardless of age** —
  stale-and-labeled beats a shrug. `requested` always travels beside the resolved
  `name`, because a fuzzy match can confidently resolve to a *different card*.
- ☑ **The skill learned to ask.** `references/rules-reference.md` now leads with "Ask the
  CR, don't recall it" — the commands, then **retrieve → READ → cite**, then the rule
  that on a degrade you fall back to web search *and say the answer is uncited*. Its five
  original corrections are reframed as **known traps**, not an index. `coaching.md`'s
  rules line and SKILL.md's workflow step 6 + scripts index carry the commands.
- ⊘ **No `/api/rules` route** (§5.4): no UI consumer, and on the hosted server it would be
  *permanently* degraded — wizards.com is not a documented public API, the same wall
  EDHREC hit. It lands with the future card-panel Rules tab. ⊘ **No committed CR excerpt**
  (Q-B1) — verbatim redistribution in miniature; the skill runs on the player's PC.
  ⊘ **No TTL/auto-refresh machinery** and ⊘ **no semantic/RAG search** — bag-of-words plus
  *read the text* is the grounding win.
- ⊘ **Recorded reconciliation:** `research-roadmap.md` planned rulings as a ~24.7 MB bulk
  download through `carddb.py`. Per-card lookups win for a single-player tool (nothing to
  download, a KB-sized cache, works the first time it's asked), so the roadmap line is
  amended rather than left to coexist as a second plan.
- **Residual risk, stated:** the CR layout is unverifiable from a sandbox — a *silent
  partial* parse is what the one-time owner-machine acceptance run
  (`python3 scripts/rules.py 903.1 --refresh` → ≥3,000 rules parsed) exists to catch.

## 5. Open questions (resolve during build)
- EDHREC "Lift" — exposed via any endpoint/`pyedhrec` method yet? Exact formula?
- Full current WotC bracket ruleset beyond B3 ≤ 3 Game Changers (syncable list + criteria).
- ManaPool / Card Kingdom per-card URL schemes (deep-link vs name-search).

## 6. Changelog
- **2026-07-22** — Spec created from the deep-research pass + design decisions. All phases planned; build not started.
- **2026-07-22** — Phase 0 foundation shipped: reusable card panel + `/api/card` + site-wide
  clickable cards + buy-links ×3 + client-side rulings. Verified in a real browser (grounded
  data + live Scryfall oracle). Data-plumbing sub-items (Scryfall bulk DB, CSB/pyedhrec clients,
  ManaPool/CK URL verification) deferred to their consuming phases.
- **2026-07-22** — Phase 3 v1 shipped (auto-build; see spec-build-next-full-deck.md).
- **2026-07-22** — Phase 2 v1 shipped: `scripts/manabase.py` hypergeometric engine + a
  "Consistency & Manabase" dashboard section. Math verified; analyze() validated. Remaining:
  wire it into `auto_build`'s manabase.
- **2026-07-23** — Sharpened the auto-builder: pip-demand-weighted basics; power/bracket +
  Consistency/Manabase now shown on the "Build this deck" view. Bundled: ManaPool buy-link →
  direct card page (verified); `power.py` bracket wording hedged (only "B3 ≤ 3 Game Changers"
  is officially confirmed). Verified end-to-end.
- **2026-07-23** — Phase 1 shipped: interactive Collection — searchable/filterable/sortable
  grid of the whole collection with lazy batch-loaded images, each card clickable → panel.
  Verified (search/filter/sort + panel). EDHREC staple chip deferred to the data client.
- **2026-07-23** — Phase 5 shipped: coaching added to the `mtg-deckbuilder` skill
  (`references/coaching.md` + SKILL.md workflow/triggers) + the web-app "Export assessment
  packet" bridge (`/deck/<stem>/assess.txt`, 📋 Assess on Decks). Grounded critique / cut-add by
  candidate selection / rules Q&A / pilot guide, on the Claude subscription (no API cost).
- **2026-07-23** — Whole-collection enrichment shipped: `carddb.py` defaults to Scryfall's
  `/cards/collection` API (no ~40 MB download), resolving each card by exact printing →
  colors / types / mana value / correct-art id. Verified **2040/2040** on the real collection;
  `load_collection` auto-merges it so every analytic works collection-wide (#29).
- **2026-07-23** — `/collection/upload` now saves to the gitignored `collection.csv` (never the
  tracked snapshot — closes a purchase-price leak into the public repo) and **auto-enriches**
  inline; regenerated the name-only public snapshot (2040 cards). Discovery: Scryfall is reachable
  server-side on the player's machine, **unblocking the deferred EDHREC / Commander Spellbook**
  data clients (#30).
- **2026-07-23** — EDHREC integration shipped: `scripts/edhrec.py` (stdlib, disk-cached) pulls a
  commander's community staples from json.edhrec.com, computes inclusion % and cross-references
  the collection into **owned (add) vs missing (buy)**. Surfaced on the Build Next deck view via
  `/api/edhrec/<commander>` (async, graceful). Verified live: Y'shtola 47,640 decks → 113 owned /
  181 missing; Atraxa 42,910 → 37 / 236. Fills the Phase 1/3 "EDHREC data client" deferral.
- **2026-07-23** — **Phase 4 shipped**: the card panel gained a grounded **"Strategy"** section —
  server role/type/MV scaffold (`card_api._strategy`) + oracle-derived mechanic tags + combo/usage,
  with a Scryfall type-line fallback for non-owned cards so no clicked card is blank. Verified via
  the live `/api/card` payload + rendered panel markers (the in-app browser's per-origin gate blocks
  localhost navigation, so UAT was server-side).
- **2026-07-23** — **Commander Spellbook integration shipped**: `scripts/spellbook.py` (find-my-combos
  API, stdlib, disk-cached) surfaces every combo **present** + **one card away** from CSB's full DB.
  Wired into the coaching **assess packet** (`/deck/<stem>/assess.txt`) and an async section on the
  Build Next view (`/api/combos/build/<commander>`). Verified live: cloud-ex-soldier → 19 one-away
  (add Repercussion → Blasphemous Act → near-infinite damage); Atraxa draft → 8; Y'shtola → 2.
  Fills the Phase 3 "CSB one-away" deferral.
- **2026-08-10** — **Production-aware enrichment shipped** (workstream A of
  [spec-engine-upgrades.md](spec-engine-upgrades.md)): new `scripts/oracle_flags.py` derives
  `produced_mana` + a small oracle flag vocabulary face-aware from a Scryfall card object;
  `carddb.py` writes them as the appended `Produced` / `Flags` columns of
  `collection_attrs.csv` in **both** the API and bulk paths; `mtglib.Card` carries
  `produced` / `flags` and `deck_stats.analyze` propagates them to deck level. Colored-source
  counts now use actual production where it is known and say "identity approx." where it
  isn't (`deck_stats`, manabase CLI, dashboard pip table, assess packet), and `/collection`
  gained a production-coverage line. Suite 259 → 320, offline. Phase 2's identity
  approximation is the thing this closes.
- **2026-08-10** — **Goldfish Monte Carlo shipped** (workstream C of
  [spec-engine-upgrades.md](spec-engine-upgrades.md)) and with it the **scope-lock lift**:
  tier-1 goldfishing is now in scope (§1 above and `research-roadmap.md` amended);
  opponent/game simulation stays out (tier 2 deferred, tier 3 rejected). New
  `scripts/goldfish.py` — seeded, stdlib, offline — shuffles, mulligans (London, keep
  2–5 lands, floor 5), plays lands untapped-first and casts greedily, and reports
  P(commander by turn N), keepable/screw/flood **with their definitions shipped as
  data**, mean lands by turn, and the worst-sequenced cards. Two mana tiers: enriched
  (`Card.produced`/`Card.flags` from workstream A — taplands give nothing on the drop
  turn, `mana2`/`mana3` rocks accelerate) and a color-identity fallback that is
  **labelled as an approximation everywhere it is used**. `simulate_ab` swaps one card
  over **common random numbers** so a paired CI measures the swap and not the luck.
  Everything runs through one cached entry point (`sim_for_deck`,
  `data/cache/goldfish/`) so the dashboard, the assess page and the assess packet cost
  ONE simulation per deck edit between them. `deckcore.load_attrs`/`apply_attrs` learned
  the `Produced`/`Flags` columns, so a deck-level `.attrs.csv` powers the enriched model
  on a fresh clone. One recorded deviation from the research doc: A/B deltas ship in the
  CLI (`--ab "Out=In"`), not in the card advisor — optimizer integration stays
  advisory-only and out of scope (Q-C3). Suite 320 → 375, offline.
- **2026-08-10** — **Grounded subagents shipped** (workstream D of
  [spec-engine-upgrades.md](spec-engine-upgrades.md)): `carddb.py` gained a second mode,
  `--verify "<card name>"` (repeatable, `--json`) — the first tool in the repo that can
  verify a SINGLE card. Names batch through the existing `/cards/collection` client and
  are reconciled **positionally** (name-keyed matching misfiles a back-face request,
  whose card returns named `Front // Back`); each miss retries once via
  `/cards/named?fuzzy=` and any resolved-name correction is surfaced; a name nothing
  resolves comes back `found: False`, which is where a hallucinated card dies. Oracle
  text is joined face-aware — never `split("//")` — and cached 30 days under
  `data/cache/scryfall/`; an unreachable Scryfall yields UNVERIFIED rows and exit 0.
  On top of it, two `.claude/agents/`: **card-verifier** (one batched `--verify` → one
  table of canonical name / cost / type / identity / commander-legality / **verbatim**
  oracle text + one `UNVERIFIED:` line) and **collection-auditor** (five read-only
  analysis commands → verdict first, then findings each carrying its count and the exact
  producing command, with an explicit privacy line: counts and ≤10 exemplar names, never
  the private CSV's rows or prices). Both are `tools: Bash, Read` and both read the
  grounding rules rather than copying them; `tests/test_agents.py` makes widening either
  one a deliberate test edit. SKILL.md gained the "Delegate the heavy work" section
  (>~3 uncertain cards → verifier, any full-pool scan → auditor, the main session keeps
  persona/verdicts/assembly/optimize) plus the inline fallback where no Agent tool
  exists. Honest limit, unchanged from the spec: this cuts context bloat only — every
  engine number is byte-identical. Suite 375 → 401, offline.
- **2026-08-10** — **Rules layer shipped** (workstream B of
  [spec-engine-upgrades.md](spec-engine-upgrades.md)): two new engines. **`rules.py`**
  puts Magic's Comprehensive Rules behind a command — it downloads WotC's official txt
  once into the gitignored `data/cache/rules/` (the CR is ~1 MB of copyrighted text
  revving 5–6× a year; a public repo must not redistribute it), parses it into rules /
  sections / chapters / glossary in document order, and answers by rule number (with
  subrules and section/chapter context), by phrase, or by glossary term. The parser's
  load-bearing detail: the official file **repeats its own headings** — the Contents
  listing names every section and ends with the words "Glossary" and "Credits", so
  slicing the body on the first "Glossary" yields a parsed-looking file with zero rules
  in it. First-Credits / last-Glossary / last-Credits is the fix and `SAMPLE_CR` carries
  the duplication so the guard bites. Refresh is manual (`--refresh`); any cached copy is
  used and labeled `fetched <date>`; nothing raises. It is the first engine in the ring
  with **zero repo imports** — rule text has no card names in it. **`rulings.py`** adds
  Scryfall's rulings for one card (fuzzy name → `rulings_uri`, 30-day cache, `has_more`
  followed), consults that cache regardless of age when the network is down, and always
  prints what was *asked for* beside what Scryfall *resolved* — a fuzzy match can land
  confidently on the wrong card. The skill learned to use them: `rules-reference.md` now
  opens with "Ask the CR, don't recall it" (**retrieve → READ → cite**, and on a degrade
  fall back to web search *and say the answer is uncited*), with its five original
  corrections reframed as known traps; `coaching.md` and SKILL.md carry the commands.
  Cut from v1 on purpose: no `/api/rules` route (permanently degraded on the hosted
  server — wizards.com is not a documented public API), no committed CR excerpt, no
  TTL machinery, no RAG. The roadmap's ~24.7 MB bulk-Rulings plan is **amended**, not
  left to coexist: per-card lookups beat it for a single-player tool. Back-compat: this
  adds two gitignored cache directories and touches no existing data format. Suite
  401 → 434, offline.
- **2026-08-10** — **`classify()` learned to read the oracle flags** (follow-up A-F of
  [spec-engine-upgrades.md](spec-engine-upgrades.md), and the close of the engine-upgrades
  season — five PRs: A, C, D, B, A-F). `oracle_flags` gained the three tokens workstream A
  deliberately deferred — `removal` (destroy/exile *target* on an Instant/Sorcery/
  Enchantment face), `wipe` (destroy/exile *all*, or the each-creature `-X/-X` / "is dealt"
  forms, on an Instant/Sorcery face), `counter` (counter target … spell) — face-aware like
  the rest of the vocabulary. `mtglib.classify()` now consults `Card.flags` **after** the
  five curated name lists and **before** the type fallback: the `if not roles` guard is the
  curated-wins rule, the same first-writer-wins shape `deckcore.load_card_notes` uses to let
  a curated note beat a generated one. So a card from a set newer than `RAMP`'s last edit
  lands in the ramp bucket instead of the generic type bucket, while a hand-verified card can
  never be overruled by a regex. The mana-shape tokens (`etb-tapped`, `mana2`, `mana3`) map to
  no role on purpose — they are goldfish inputs, not deck-role categories. Why this was a
  separate, deliberately small PR: category counts feed `power.assess`, the dashboard and the
  optimizer's role-template guardrails, so the blast radius belonged on its own diff with its
  own proofs. Both were run and both are in the PR body: a `deck_stats --json` categories diff
  on the fixture deck is **byte-identical** (an unenriched collection has `flags == set()`, so
  the layer no-ops), and optimizer idempotency is re-proven *with* flag-bearing attrs present
  rather than assumed. Honest limit, unchanged and now more load-bearing: a *wrong* flag is
  invisible to the honesty labels, which fire when data is absent, not when it is wrong — the
  ~30-card audit after the first real enrichment run is the only guard. Suite 434 → 455,
  offline.
- **2026-08-10** — **The network-gated acceptance steps ran for real** — from a GitHub
  Actions runner (`live-checks` workflow, `claude/live-network-checks` branch), since
  runners have the open egress the dev sandbox lacks. Results: the A1 Scryfall schema
  check passed 16/16 (every `test_oracle_flags.py` fixture validated against live API
  JSON, MDFC shape included, Blasphemous Act confirmed as the documented wipe-regex
  miss); `carddb.py --verify "Sol Ring"` returned the verbatim text live; and the
  real-CR gate **caught the bug it existed to catch** — the 2026 rules landing page
  carries a **literal space** in the CR href (`MagicCompRules 20260807.txt`), which
  `rules._RE_TXT_URL`'s `\s`-excluding class truncated, so `--refresh` reported "no
  link found" with the link in plain sight. Fixed: the regex spans the space (stopping
  at quotes/angle brackets), `_find_txt_url` percent-encodes before fetching, and a
  test pins the real 2026 page shape. Re-verified end to end: 3,161 rules / 739
  glossary entries parsed, effective August 7, 2026, 903.1 answered. The only
  acceptance step still owner-machine-bound is the ~30-card flag audit — the private
  collection never leaves the player's PC. Suite 455 → 456, offline.
- **2026-08-10** — **Recertification institutionalized + the blind spot documented.**
  The season retro asked why the network-gated acceptance steps sat on the owner's
  checklist when GitHub-hosted runners (open egress — `field-snapshots.yml` had proven
  it weekly since it shipped) could run them all along: `docs/codemap.md`'s deployment
  matrix had blurred runners and dev sandboxes into one "CI ❌" column. The matrix now
  separates them and states the rule — reach for a runner before parking a network
  check on the owner's checklist. The throwaway live-checks harness is promoted to
  `.github/workflows/recertify.yml` (`workflow_dispatch`): one click re-runs the
  Scryfall schema + flag audit, live `--verify`, `rulings.py` live (the one Scryfall
  leg never exercised before — and its first run taught us Sol Ring legitimately has
  zero rulings, so the check counts Humility instead), `rules.py --refresh` **end to
  end** through the fixed `_find_txt_url`, and the buy-link scheme probe. First full
  pass green, which also closed the Phase 0 leftover: ManaPool/Card Kingdom URL
  schemes verified live, 4/4, no fix needed.
