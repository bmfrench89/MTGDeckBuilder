# Spec & Tracker — Interactive Analytics + AI Deckbuilder

**Type:** feature spec + progress tracker (living document — update status as work lands).
**Owner:** Brendan · **Started:** 2026-07-22 · **Status:** 🟢 Building — Phase 0 in progress
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
| 0 | Reusable card panel + `/api/card` + data plumbing | ◐ In progress | in review |
| 1 | Interactive Collection (browse/search/filter) | ☐ Not started | — |
| 2 | Manabase & consistency engine (flagship) | ☐ Not started | — |
| 3 | Full auto-built decks for Build Next | ☐ Not started | — |
| 4 | Full card strategies | ☐ Not started | — |
| 5 | AI coaching skill + export bridge | ☐ Not started | — |

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

### Phase 2 — Manabase & consistency engine (FLAGSHIP)  ☐
- ☐ `scripts/manabase.py`: colored-source counting per card (handle duals/fetches/MDFCs).
- ☐ Hypergeometric engine (opening-hand + by-turn-N odds; keepable-hand %; color-screw %).
- ☐ Karsten targets per pip/CMC (19/26/30 …) with the (89+M)% castability check per card.
- ☐ Deck "Consistency & Manabase" dashboard tab.
**Acceptance:** per deck, flags each spell as consistently-castable-on-curve or not, and reports
land-count / color-source odds — verified against Karsten's published numbers.

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
