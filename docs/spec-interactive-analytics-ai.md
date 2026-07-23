# Spec & Tracker — Interactive Analytics + AI Deckbuilder

**Type:** feature spec + progress tracker (living document — update status as work lands).
**Owner:** Brendan · **Started:** 2026-07-22 · **Status:** 🟢 Phases 0–3 + 5 shipped + whole-collection enrichment (Scryfall API) · remaining: Phase 4 + data integrations (EDHREC / Commander Spellbook — **now unblocked**, Scryfall is reachable on the player's machine)
**Companion docs:** blueprint/rationale in [research-roadmap.md](research-roadmap.md) ·
session history in [handoff.md](handoff.md).

> Update rule: when a task ships, tick its box and update the phase status + the
> Changelog at the bottom. Keep the tracker table in sync.

**Status legend:** ☐ not started · ◐ in progress · ☑ done · ⊘ dropped/deferred

---

## 1. Goal

Make the site an end-to-end, **analytics-first Commander deckbuilder for an expert
player**: everything interactive, full auto-built decks in Build Next, full per-card
strategy, and a browsable collection — grounded in real data, with **AI assessments**
delivered as a Claude Code skill. **Out of scope: playtesting / goldfishing / game
simulation of any kind.**

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
| 4 | Full card strategies | ☐ Not started | — |
| 5 | AI coaching skill + export bridge | ☑ Done | #25 |

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
- ☐ Cached CSB + `pyedhrec` client wrappers — *deferred to their consuming phases (1, 3).*
- ☐ Verify ManaPool & Card Kingdom per-card URL schemes — *best-effort links shipped;
  verify on the live sites (one-line fix in `card_image.purchase_links`).*
**Acceptance:** ☑ verified in a real browser — clicking a card opens the panel with image,
live oracle text, rulings, grounded local data, and three working buy-links.

### Phase 1 — Interactive Collection  ☑
- ☑ Browsable grid of all owned cards with images (`webapp/static/collection.js`) — lazy,
  IntersectionObserver → batch-resolve CDN images (75/req) so a 1,800-card grid only fetches
  what you scroll to.
- ☑ Live search + filters: name, colors (subset), type, role, "in a deck", "priced", + sort
  (name / value / MV). Client-side, instant.
- ☑ Each card clickable → the shared panel (reuses Phase 0 `data-card`).
- ☐ EDHREC inclusion / Lift "how staple is this" chip — *deferred (needs the pyedhrec data client).*
**Acceptance:** ☑ verified — search "sol" → 12, "in a deck" → 266, role "ramp" → 40; clicking a
card opens the panel; honest name-only note when filters need enrichment.

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
**Honest simplifications:** probabilities are UNCONDITIONAL (not Karsten's mulligan-adjusted %),
and sources approximate a permanent's output from its color identity (rough for fetches/oddballs).

### Phase 3 — Full auto-built decks for Build Next  ☐
**Detailed spec:** [spec-build-next-full-deck.md](spec-build-next-full-deck.md).
- ☐ `scripts/auto_build.py`: assemble a legal 99 from the owned pool (deck_fit scoring +
  role targets + archetype support + `deck_conflicts.available_pool`, color-identity-legal).
- ☐ Build Next: commander → "Build this deck" → interactive decklist (curve, roles, the 99).
- ☐ CSB `/find-my-combos` "one card away" upgrade surfacing.
- ☐ Export + optional "Save to my decks".
**Acceptance:** produces a 100-card, in-color, role-balanced draft entirely from owned cards, with
gaps-to-buy listed; honest that it's a heuristic draft.

### Phase 4 — Full card strategies  ☐
- ☐ Panel shows curated note when present, else a grounded generated "how it works"
  (role + oracle + combo membership + synergy).
- ☐ Rulings surfaced; "works well with" synergy hints.
- ☐ Grow `card_notes.csv` opportunistically.
**Acceptance:** every card the user clicks yields a grounded strategy blurb (never a blank).

### Phase 5 — AI coaching skill + export bridge  ☑
Chose to **extend the existing `mtg-deckbuilder` skill** rather than fork a separate `mtg-coach`
(same persona / grounding / scripts / collection — coaching is deckbuilding). Runs in Claude
Code on the subscription; no Anthropic API in the app.
- ☑ `references/coaching.md` — the grounded method: rubric critique, cut/add **by candidate
  selection** (never invent cards), rules/interaction Q&A over oracle text + rulings, pilot /
  mulligan guide, deck-vs-deck, upgrade-to-bracket.
- ☑ SKILL.md — coaching triggers in the description, a "Coaching & assessment" workflow, and a
  refreshed script list (manabase / combo_detector / auto_build / card_api / carddb / …).
- ☑ Web app **"Export assessment packet"** (`/deck/<stem>/assess.txt` + "📋 Assess" on the Decks
  leaderboard): decklist + power/bracket + consistency + combos + role/curve/pip numbers in one
  paste-able block to hand a deck to a coaching session.
**Acceptance:** ☑ the skill triggers on coaching asks; the assess packet renders grounded numbers
(Bracket 3 / Power 67 / role counts / combos) for a saved deck; scripts it references all run.

---

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
