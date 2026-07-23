# Spec & Tracker — Interactive Analytics + AI Deckbuilder

**Type:** feature spec + progress tracker (living document — update status as work lands).
**Owner:** Brendan · **Started:** 2026-07-22 · **Status:** 🟢 Building — Phases 0, 2, 3 shipped; sharpening
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
| 1 | Interactive Collection (browse/search/filter) | ☐ Not started | — |
| 2 | Manabase & consistency engine (flagship) | ☑ Engine + dashboard + wired into auto_build | #20, #23 |
| 3 | Full auto-built decks for Build Next | ☑ v1 + images + on-view analysis (deferred: EDHREC/CSB) | #19, #21, #22, #23 |
| 4 | Full card strategies | ☐ Not started | — |
| 5 | AI coaching skill + export bridge | ☐ Not started | — |

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
- ☐ Extend `carddb.py` to a full local Scryfall bulk DB — *deferred (needs the player's
  machine; Scryfall firewalled in the build env). Consumed by Phase 1/2.*
- ☐ Cached CSB + `pyedhrec` client wrappers — *deferred to their consuming phases (1, 3).*
- ☐ Verify ManaPool & Card Kingdom per-card URL schemes — *best-effort links shipped;
  verify on the live sites (one-line fix in `card_image.purchase_links`).*
**Acceptance:** ☑ verified in a real browser — clicking a card opens the panel with image,
live oracle text, rulings, grounded local data, and three working buy-links.

### Phase 1 — Interactive Collection  ☐
- ☐ Browsable grid/table of all owned cards with images.
- ☐ Live search + filters (color, type, MV, role, owned-count, price, "in a deck?").
- ☐ Each card clickable → panel; shows which of your decks use it.
- ☐ EDHREC inclusion / Lift "how staple is this" chip (degrade if enrichment off).
**Acceptance:** can find any owned card in < 2s of typing; filters compose; honest name-only fallback.

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

### Phase 5 — AI coaching skill + export bridge  ☐
- ☐ Author grounded `mtg-coach` skill: deck critique (rubric), explain-card-role,
  rules/interaction Q&A (RAG), add/cut by candidate-pool selection, upgrade-to-bracket,
  win-condition + pilot/mulligan write-ups, deck-vs-deck.
- ☐ Web app "Export assessment packet" (deck + analytics + oracle text → file the skill reads).
**Acceptance:** in a Claude Code session, the skill critiques a saved deck grounded entirely in
the repo's data + live oracle text, suggesting only real cards; no Anthropic API cost incurred.

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
