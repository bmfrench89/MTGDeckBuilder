# Spec — "Build Next" Full Auto-Built Deck View

**Type:** feature spec + tracker (living). **Created:** 2026-07-22 · **Status:** 🟡 Planned
**Parent:** this is the detailed spec for **Phase 3** of
[spec-interactive-analytics-ai.md](spec-interactive-analytics-ai.md); rationale/constraints in
[research-roadmap.md](research-roadmap.md).

**Status legend:** ☐ not started · ◐ in progress · ☑ done · ⊘ deferred

---

## 1. User story

On the **Build Next** page, each commander is ranked by how much of my collection supports
it. I want to **click a commander (or a "Build this deck" button) and see the full 99-card
deck the app would build for me from the cards I already own** — grouped by role, every card
clickable (Phase 0 panel), with the mana curve, role balance, what's missing, and cards to
buy to finish it. Then export it or save it to my decks.

**Why it matters / differentiation (research):** Archidekt and Moxfield let you *filter to
owned cards* and show EDHREC suggestions, but **neither auto-generates a complete deck from
your collection.** This is the flagship feature that makes the tool an *end-to-end* builder.

## 2. Deckbuilding methodology (research-grounded)

Multiple community templates converge on the same ratios; the app already encodes them in
`deck_fit.FIT_TARGETS`. The builder targets this **house template** (per 99 + commander):

| Role | Target | Notes |
|------|--------|-------|
| Lands | **36–38** | Formula: ~41 − 1 per 3–4 ramp (→ 37 lands w/ 10 ramp). Karsten manabase (Phase 2) refines colored sources. |
| Ramp | **10–12** | Command Zone template emphasizes this. |
| Card draw | **8–12** | Sustained engines + burst. |
| Spot removal | **8–10** | Instant-speed answers. |
| Board wipes | **2–4** | Mass removal. |
| Win-cons / finishers | **2–4** | |
| Commander synergy / theme + flex | **~25–30** | Cards that enable the commander's plan. |

Template references: **Command Zone Template** (Wong/Lee Kwai — Ramp 10–12), **8x8 Theory**
(commander + 35 lands + 8 categories × 8 = 64 spells; 4 core categories always: ramp, draw,
removal, commander synergy), **7×9**, and PreconForge's "mathematical blueprint." All are
explicitly *jumping-off points*, not rigid rules — so the builder targets ranges and reports
where it deviates.

**The statistical target: EDHREC's "average deck."** For any commander, EDHREC compiles real
decklists (from Archidekt/Moxfield/Scryfall) into an *average deck list* — the format's
consensus baseline. Access via `pyedhrec.get_commanders_average_deck`. Use it two ways:
(a) as a **benchmark** ("your build vs. the average — what the field runs that you don't"),
and (b) as the source of **buy-to-complete** suggestions when your pool can't fill a role.

## 3. Build algorithm (`scripts/auto_build.py`)

`build(commander, collection, decks_dir, opts) -> deck` — pure/stdlib, reuses existing engines.

1. **Context** — color identity + archetype tags from `commanders.csv`; tribal from the pool
   (`deck_fit.deck_context`).
2. **Candidate pool** — owned cards that are (a) color-identity-legal and (b) *available*
   (`deck_conflicts.available_pool` excludes copies committed to your other decks; a toggle
   can ignore commitments). Never include an illegal or unavailable card.
3. **Score** — every candidate via `deck_fit.assess_card(card, rep, ctx, refs)` → fit + role.
4. **Fill role quotas greedily** by descending fit within each role: lands → ramp → draw →
   removal → wipes → (counters) → synergy/theme → flex, to the house-template targets, then
   fill toward 99 with the highest-fit in-color owned cards.
5. **Manabase** — proportional to colored-pip demand + owned utility lands now; **upgrade to
   Karsten colored-source targets once the Phase-2 engine lands**.
6. **Gaps** — any role left under target because the pool ran dry → flag it and recommend
   fillers (owned-elsewhere, then `role_staples.csv` / EDHREC staples not owned) with buy-links.
7. **Combos** — run `combo_detector` (later CSB `/find-my-combos`) on the built list → present
   + one-card-away.
8. **Assess** — `power.assess` (bracket + power), deck value, `%` overlap vs EDHREC average.

Output: `{sections:[(role, [cards])], counts, curve, gaps, buys, combos, assessment, value,
edhrec_overlap, honesty}`.

## 4. UX — the full-deck view

New route (e.g. `GET /build-next/<commander>/deck`) + a "Build this deck" action on each
Build Next card. The page shows:
- **Header**: commander (clickable → panel), colors, archetype, "built from N owned cards · M gaps".
- **Stat tiles**: land / ramp / draw / removal / wipe counts **vs target** (green/amber), power
  + bracket, deck value, `%` vs EDHREC average.
- **Mana curve** + **pip demand vs sources** (Karsten castability once Phase 2).
- **The 99 grouped by role/section**, every card a Phase-0 `.cardlink` (image/oracle/rulings/buy).
- **Gaps & buy-to-complete**: under-filled roles + recommended cards you don't own, with the
  three buy-links.
- **Combo watch**: complete + one-away.
- **Actions**: **Export** (.txt / ManaPool via existing `export_manapool`), **Save to my decks**
  (writes `data/decks/<stem>.txt` with headers so it joins the leaderboard + gets a full dashboard).
- **Honesty banner**: "a heuristic draft from your owned pool, not a tuned list"; name-only vs
  enriched caveat.

## 5. Acceptance criteria
- Clicking a commander builds a **legal, in-color, ~100-card** deck **entirely from owned +
  available cards**, role-balanced to the template, with any gaps listed honestly.
- Every card in the view is clickable (Phase-0 panel); curve + role counts + power/bracket shown.
- Exportable and savable (a saved deck appears on the leaderboard with a working dashboard).
- Degrades gracefully on a name-only collection (fewer type-based roles) and says so.

## 6. Dependencies & phasing
- **Buildable now** (core): `deck_fit` + `available_pool` + `commanders.csv` + a proportional
  manabase + local `role_staples`/`combo_detector`. Ships a working draft builder.
- **Better with Phase 1** (enriched collection → real types/roles → sharper fit) and **Phase 2**
  (Karsten manabase for the land base + castability check).
- **EDHREC average-deck benchmark + staple buys**: needs `pyedhrec` (cache; degrade to local
  `role_staples.csv` until available).
- **CSB `/find-my-combos`** upgrade-combo surfacing: Phase-3 data client.

## 7. Tasks
- ☐ `scripts/auto_build.py` — build() + slot-filler + gap detection (core, offline).
- ☐ Manabase v1 (proportional) → v2 (Karsten, when Phase 2 lands).
- ☐ Route `/build-next/<commander>/deck` + "Build this deck" action on Build Next cards.
- ☐ `webapp/templates/build_deck.html` — full-deck view (reuses the Phase-0 panel + curve).
- ☐ Export + **Save to my decks** (write `data/decks/<stem>.txt`).
- ☐ EDHREC average-deck overlap + buy-to-complete (pyedhrec; local fallback).
- ☐ Combo watch on the built list.
- ☐ Honesty/enrichment banners + tests (legal, in-color, ~100 cards, no committed-single reuse).

## 8. Open questions
- Save target: a subfolder (`data/decks/generated/`) vs top-level, and how to mark a deck as
  "auto-generated / draft"?
- Manabase before Phase 2: proportional split good enough, or block full quality on Phase 2?
- EDHREC average-deck for post-2025 commanders (Marvel/FF) — coverage/latency via pyedhrec?

## 9. Sources
- Template ratios: [Command Zone Template (EDH Wiki)](https://edh.fandom.com/wiki/Command_Zone_Template),
  [PreconForge "Ultimate Template"](https://preconforge.com/the-ultimate-commander-deckbuilding-template-the-mathematical-blueprint-for-edh/),
  [Spellweave guide](https://spellweave.app/guides/commander-deck-building)
- [8x8 Theory](https://the8x8theory.tumblr.com/what-is-the-8x8-theory) · [7×9 (EDH Wiki)](https://edh.fandom.com/wiki/7_by_9)
- EDHREC average deck: [How to Use EDHREC](https://edhrec.com/guides/how-to-use-edhrec) ·
  [pyedhrec](https://pypi.org/project/pyedhrec)
- Collection building (no auto-generate today): [Moxfield](https://moxfield.com/), [Archidekt FAQ](https://archidekt.com/faq)

## 10. Changelog
- **2026-07-22** — Spec created from focused research on EDH deckbuilding templates + EDHREC
  average-deck methodology. Planned; not started.
