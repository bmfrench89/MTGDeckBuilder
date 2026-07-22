# MTG Deckbuilder — Interactive + Analytics + AI Roadmap

**Status:** proposed blueprint (awaiting build kickoff). Created 2026-07-22.
**Source:** deep-research pass (106 agents, 24 sources, 21/25 claims adversarially
verified) + design decisions with the player. This is the durable plan; the
"Open threads" in `docs/handoff.md` point here.

---

## Vision

Turn the site into an **end-to-end, analytics-first Commander deckbuilder for an
expert player**: everything interactive, full auto-built decks for "Build Next",
full per-card strategy, and a browsable/searchable collection — grounded in real
data, with **AI assessments** layered on top. **No playtesting / goldfishing /
game simulation** — every metric is computed from card data, not simulated games.

## Architecture decisions (resolved)

1. **Two surfaces, cleanly split:**
   - **Web app** = 100% deterministic analytics (heuristic Python). Free, offline,
     reproducible, grounded by construction. This is "the site."
   - **AI layer = a Claude Code Skill**, NOT an embedded LLM API. It runs inside a
     Claude Code session on the player's subscription (no per-token API cost),
     reads the repo's data + computed analytics, and produces natural-language
     coaching. Embedding the Anthropic API in the Flask app was rejected: it would
     bill API credits on top of the subscription.
2. **"RAG" here = the skill's retrieval discipline, not a vector DB in the app.**
   Before answering, the skill reads the card DB, fetches exact Scryfall oracle
   text + rulings, and runs the analytics scripts, then answers only from that.
   "Select cards from a real candidate pool, never invent them" and "cite oracle
   text" become **skill grounding-rules** (same pattern as
   `.claude/skills/mtg-deckbuilder/references/grounding-rules.md`). This satisfies
   the research's anti-hallucination guidance with no app-side ML.
3. **Optional bridge:** the web app gets an **"Export assessment packet"** action
   that dumps a deck + all computed analytics + oracle text to a file the skill
   consumes — clean hand-off from browser to Claude Code.
4. **Pricing:** no live price feed. Card panels get **buy-out links** to
   **TCGplayer** (exact printing via Scryfall `purchase_uris`, free/ToS-clean),
   **ManaPool**, and **Card Kingdom** (constructed per-card links; deep-link where
   the URL scheme allows, name-search otherwise). Rough MARKET values from the
   player's own export stay for ballpark sorting only, labeled estimates. This
   drops live "upgrade ROI" math by choice.

## Constraints & grounding (from verified research)

- **Scryfall**: use daily gzipped-JSONL **bulk files** as the local card backbone
  (Scryfall *requires* this over the live API at scale). Live endpoints are
  rate-limited (2 req/s on card endpoints; 429 = 30s lock) — the same limit behind
  the image-loader bug already fixed; Scryfall-ID CDN images are the durable fix.
  ToS forbids paywalling/proxying its data; its prices are "dangerously stale after
  24h" (hence: link out, don't resell).
- **EDHREC** has **no official API**; access via the unofficial `pyedhrec` wrapper
  over `json.edhrec.com`. Cache aggressively, degrade gracefully, expect breakage.
- **Bracket calibration**: only **"Bracket 3 = up to 3 Game Changers"** survived
  verification. The "0 GC=B2 / 1–3=B3 / 4+=B4" formula was **refuted** — and that
  is essentially what `power.py` hardcodes today. Action: hedge the bracket claim,
  weight the other guardrails (mass land denial, extra turns, 2-card combos), and
  lean on Commander Spellbook's per-combo `bracketTag`.
- **AI**: every AI feature must be grounded (candidate-pool selection + RAG over
  rules + live Scryfall oracle). Free card-name generation hallucinates.

## Research-verified additions (what to build, with references)

### Data
- **Commander Spellbook API** — supersede the curated `data/reference/combos.csv`
  with the canonical, auto-updating combo DB (the one EDHREC uses). Official
  Python/TS SDKs. `POST /find-my-combos` returns combos present **and** combos the
  deck is one card short of (`almostIncluded` buckets), plus per-Variant
  `produces` / `prerequisites` / `bracketTag` / legalities. *Low–Med.*
  Ref: `backend.commanderspellbook.com/schema/redoc/`.
- **EDHREC data via `pyedhrec`** — inclusion rates, "high synergy cards",
  top-cards-by-type, average decklists → staple comparison + benchmarking.
  Prefer the successor metric **"Lift"** (EDHREC retiring "synergy" as of Dec 2025).
  *Medium* (unofficial → caching/fallback). Ref: `github.com/stainedhat/pyedhrec`,
  `edhrec.com/faq`.
- **Full local Scryfall bulk DB + Rulings file** (~24.7 MB, keyed by oracle_id) —
  extend `carddb.py`; surface **rulings** in the card panel (not shown today).
  *Medium.* Ref: `scryfall.com/docs/api/bulk-data`.

### Analytics (no games simulated)
- **[FLAGSHIP] Frank Karsten manabase math + hypergeometric engine** — per-card
  "do I have enough colored sources on curve?" using Karsten's 99-card targets
  (single-pip 1-drop = 19 sources, double-pip 2-drop = 26, CC = 30) at his
  (89+M)% castability threshold. The same engine answers opening-hand land odds,
  color-screw %, ramp-by-turn-3, combo-piece-by-turn-N, and keepable-hand %. This
  is the highest-value expert analytic and the natural level-up from our current
  curve + pip-demand. *Medium* (source-counting for duals/fetches/MDFCs +
  hypergeometric). Ref: Karsten "How Many Sources… 2022 Update" (TCGplayer);
  `scipy.stats.hypergeom` or a JS impl.
- **Card-pair synergy graph** — Bayesian co-occurrence over an EDHREC decklist
  corpus → "which cards synergize with X in *this* deck." *Med–High, medium
  confidence* (single academic source).
- **Honest bracket calibration** — correct the refuted GC-count→bracket formula in
  `power.py`; use CSB `bracketTag` + the confirmed B3≤3 rule. *Low.*

### AI assessments (delivered as a Claude Code skill)
- **Structured deck critique** across a fixed rubric: removal / ramp / draw /
  win-cons / anti-synergy / pod-meta / tempo — fed by our deterministic analytics.
- **Add/cut recommendations by candidate-pool SELECTION** (collection + EDHREC
  staples + Scryfall), never free-generation.
- **RAG rules/interaction Q&A + "explain this card's role"** — retrieve
  Comprehensive Rules + live oracle/rulings, answer only from that.
- Plus: upgrade-path to a target bracket, win-condition/line identification,
  pilot/mulligan/sequencing write-ups, threat & removal-suite assessment,
  deck-vs-deck comparison, rule-0/bracket negotiation summaries.

## Phased roadmap

- **Phase 0 — Foundation & data plumbing.** Extract the card panel into a reusable
  web component + `/api/card/<name>` endpoint (role, curve, notes, combos, fit,
  "used in which decks", owned/qty, **rulings**, **buy links** ×3). Stand up the
  Scryfall bulk DB extension and cached CSB + EDHREC clients. → *makes the whole
  site clickable and lands the data layer later phases use.*
- **Phase 1 — Interactive Collection.** Browsable/searchable/filterable grid; each
  card clickable → panel; EDHREC inclusion/Lift "how staple is this" chip;
  "you run this in decks X/Y".
- **Phase 2 — Manabase & consistency engine (flagship).** `scripts/manabase.py` +
  hypergeometric engine; a deck "Consistency & Manabase" tab (source counts vs
  Karsten targets, castability per card, opening-hand/by-turn-N odds).
- **Phase 3 — Full decks for Build Next.** `scripts/auto_build.py` assembles a
  99 from the owned pool (deck_fit scoring + role targets + archetype support +
  available pool, color-identity-legal); CSB `/find-my-combos` for upgrade combos;
  interactive decklist, export, optional Save-to-decks.
- **Phase 4 — Full card strategies.** Curated notes where present, else grounded
  generated "how it works" (role + oracle + combo membership + synergy); rulings;
  synergy hints. Everywhere the panel appears.
- **Phase 5 — AI coaching skill + bridge.** Author the grounded `mtg-coach` skill
  (critique, explain-role, rules Q&A, add/cut, pilot guides) and the web app's
  "Export assessment packet" hand-off. Runs in Claude Code on the subscription.

## Open questions to resolve during build

- Has EDHREC exposed **"Lift"** via any endpoint/`pyedhrec` method yet, and what is
  the exact formula (to match their numbers, not approximate)?
- The full current **WotC bracket ruleset** beyond B3≤3 GC (a syncable
  machine-readable Game Changers list + criteria).
- Verify **ManaPool** and **Card Kingdom** per-card URL schemes (deep-link vs
  name-search).

## Key sources
- Karsten manabase: tcgplayer.com "How Many Sources… 2022 Update"
- Commander Spellbook API: backend.commanderspellbook.com/schema/redoc/
- EDHREC / pyedhrec: github.com/stainedhat/pyedhrec, edhrec.com/faq
- Scryfall bulk/rate-limits/terms: scryfall.com/docs/api
- AI patterns: commander-ai-lab, edh-llm, magic-judge-rag (proof-of-concept refs)
