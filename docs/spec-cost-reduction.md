# Spec — commander cost reduction in the cost model

**Status: ✅ SHIPPED 2026-08-20.** Built on the player's "build it", after three
wrong verdicts on the Ur-Dragon deck in one day traced to the same hole: goldfish
paid printed mana costs while the deck's commander IS a cost reducer. The receipts
(all in `the-ur-dragon.notes.md`): Radagast measured a downgrade (+0.016 turns),
restoring Ureni measured a downgrade (+0.019), and "commander cast in 31% of games /
too top-heavy" was the original mis-diagnosis — eminence works **from the command
zone** (verified, runner run 32367856797), so its −1 needs no cast.

## Design

**One source of truth: oracle text at enrichment time.** `oracle_flags` (v3) derives
machine-readable tokens; `carddb` writes them into the attrs Flags column; every
consumer reads `Card.flags`. No curated list, no second path — and a FlagsVer < 3
file simply yields no tokens, which reproduces the old behavior exactly (the
empty-vs-absent rule: absence degrades, never lies).

**Token grammar** (mirrors `fetch:*`):
- `discount-cmd:<type>:<n>` — eminence class: *"As long as ~ is in the command zone
  or on the battlefield, other \<Type\> spells you cast cost {n} less."* Active from
  turn one; **never applies to the commander itself** ("other").
- `discount:<type>:<n>` — battlefield static (*"Dragon spells you cast cost {1}
  less"* — Sarkhan, Dragonspeaker Shaman). Active only while the permanent is on
  the battlefield.
- `discount-first:<type>:<n>` — *"The first \<type\> spell you cast each turn costs
  {n} less"* (Radagast). Once per turn; the slot is positional, so a matching spell
  cast before the reducer landed still spends it.

`<type>` is one lowercase word — a subtype ("dragon", "vehicle", "hero"), a card
type ("artifact"), or "creature"/"noncreature", which read the creature bit. The
matcher (`goldfish._disc_matches`) resolves subtype and type words against one
`typewords` set; a word the matcher could not match while the label claimed it
was modeled was the one defect found in v1's collection-wide sweep (Lyse Hext's
"noncreature") and is now pinned by test. Riders the
grammar cannot express (Goreclaw's "with power 4 or greater") deliberately match
**nothing**: a missed discount degrades to today's behavior; a wrong one lies.
Sentence-scoped regexes; the eminence sentence is excluded from the static pattern.

**Goldfish hook.** `SimCard` gains `discounts` and `subtypes` (immutable, shared —
the CRN contract is untouched). At pay time the discount reduces the **generic
portion only, floored at zero** — colored pips are never reduced. Eminence comes
from the commander card's flags and is always on; battlefield discounts are read
off `board` (creatures only in v1 — `board` is the only battlefield the sim
tracks); `first` tokens are consumed by the first matching cast each turn.
Discounts change casting *decisions*, never the shuffle stream — the A/A
exact-zero tripwire now runs with discounts on.

**Honesty label.** The assumptions block always states the situation: either
"Cost reduction modeled: dragon spells −1 (eminence …)" or "No cost reduction
detected … re-enrich if this deck's commander reduces costs." `REPORT_SCHEMA`
bumped 3 → 4 so no cached sim serves pre-model numbers.

## What v1 deliberately does not model

- Noncreature battlefield reducers (an enchantment reducer never enters `board`).
- Conditional/ridered discounts (Goreclaw class) and "costs less for each …" scaling.
- Cost increases (taxes) — a different mechanic, out of scope.

## Rollout

Merging does NOT regenerate attrs by itself (`attrs-snapshot.yml` triggers on
snapshot changes, cron, and the dispatch button — deliberately not on script
edits). The shipped path: merge → dispatch `attrs-snapshot.yml` on main (the
documented shape-change button) → pull → FlagsVer 3 attrs carry the tokens →
re-measure. Until then every deck reports "No cost reduction detected", which is
true of the data it has.
