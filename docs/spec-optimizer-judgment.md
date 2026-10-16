# Spec: the optimizer proposes, judgment decides

**Status:** Phases A, B and C SHIPPED (2026-10-14).
**Origin:** the player, 2026-10-14: *"I want the optimizer fixed. I also think part of the
issue I have with this app is I want more AI intelligent decisions made with you/AI and not
so reliant on EDHREC. I think EDHREC and AIs decisions can overlap and be used to help but
should not be the golden choice."*

## Decisions (player, 2026-10-14)

| # | Question | Answer |
|---|---|---|
| J1 | Where does the AI judgment run? | **Claude sessions only.** The app builds proposals and an evidence packet; no Claude API calls, no API cost. |
| J2 | What does ⚡ do? | **Propose; the player approves.** Nothing is written until swaps are ticked. Closes D1 in `spec-ux-refresh.md` and D4 in `spec-target-architecture.md`. |

## Why: what the field gate got wrong the same day

- **Lands.** The rebuilt Ur-Dragon (five colours, 29 good nonbasics) drew nine proposals to
  trade duals for basics, and Y'shtola 8+. Two causes: land pass 1 swapped lands by EDHREC
  inclusion, and pass 2 enforced a basics QUOTA (`round(lands × (0.42 − 0.04 × (colours − 1)))`)
  justified by basics' 98-99% inclusion. That number says nearly every deck runs some basics;
  it says nothing about how many.
- **New cards.** Samut, Hazoret's Champion (2 mana, all creatures haste: an Ur-Dragon trigger
  the turn a dragon lands) has ~0% field because its set is new. Only reading it found it.
- **Ranking.** For Y'shtola, Misdirection outranked Absorb by field % (12% vs 7%). Read
  against the deck, Misdirection redirects rather than counters, and Absorb's 3 life is a
  Vito drain.
- **A two-card loop.** Ganax + Draconic Visitor is a mandatory "draw the game" loop
  (CR 104.4b). No inclusion number warns about that; Commander Spellbook and the rules did.
- **Candidates.** The spell pass only ever considers cards EDHREC lists (`for k, inc in
  field.items()`), so an owned card the field doesn't know cannot be proposed at all.

## Phase A — lands by mana function (SHIPPED)

`manabase.land_mana_score(card, weights, demanded_types)` values a land in
colour-equivalents:
- **Colours:** the deck's colours it makes, each weighted by the deck's own pip demand
  (`color_weights`: demand ÷ mean, clamped to 0.5–1.5; static per spell list, so a second run
  is a no-op). Credit is capped at two colours: Scryfall lists every colour for choose-a-colour
  lands like Thriving Bluff and Crossroads Village.
- **Filter lands** ({C} natively plus three-plus colours: Study Hall, Rumble Arena, Henge of
  Ramos) earn one colour at 0.75. The test reads everything the land lists. In an R/W deck,
  Henge narrowed to two colours and passed for an untapped dual until that was fixed.
- **Tapped:** −0.75 for always tapped, −0.25 for conditionally tapped.
- **Fetchable:** +0.25 per basic land type the deck's fetchers ask for.
- **Not judged (None):** no produced data (never guess), or none of the deck's colours
  (utility lands, spend-restricted lands).

The optimizer's single land pass:
- **Cuts:** nonbasic, unprotected, scorable lands, where the field runs the land in under
  25% of decks. A higher rate usually means an ability the score can't see, like Bojuka
  Bog's exile.
- **Adds:** owned lands with a FREE copy that list two colours or fewer, plus basics
  (unlimited). The field list doesn't gate this, but a shared copy is never proposed.
- **A swap needs +0.6.** Equal scores break ties on field %, and that's the only other use of
  EDHREC here.
- **The basics quota is gone.**
- **The fetch-type ledger guard is unchanged.**
- **Notes protection now uses the folded match** (`deck_fit.named_in_notes`). A raw substring
  test missed "Canopy\nVista" wrapped across two lines.

**Measured on the live decks (2026-10-14):**
- **Ur-Dragon, Captain America, Dina:** no land proposals.
- **Y'shtola:** one (Sunlit Marsh → Hidden Lair).
- **Kami:** two tapped utility lands → Island.
- **Beorn:** two tapped green lands → Forest.
- **Bartolomé:** proposes **Dakmor Salvage → Caves of Koilos**. Dakmor is a graveyard piece the
  score can't see, which is exactly why Phase B had to ship with Phase A.

## Phase B — ⚡ proposes, the player approves (SHIPPED)

- **The review:** `GET /deck/<stem>/optimize` renders `optimize_review.html`, which lists
  each proposal with a checkbox and its evidence. Spells show field % in and out (or "no
  field data") and whether the add is free or shared; lands show both mana scores. Buys,
  risers, manual holds and fetch-guard keeps are shown as advice. Nothing is written.
- **Applying:** `POST /deck/<stem>/optimize` with `pick=<kind>|<cut>|<add>` calls
  `optimize.apply_chosen`. It recomputes the proposals; a key no longer proposed comes back as
  `stale` and isn't written. It re-checks role bands for the chosen subset, in order, and a
  swap that now breaks a band comes back as `held`. Then it writes through the same writer,
  change log, `_tidy`, singleton check and buylist append as before. The approval is one
  Undo / Undo all, so `Source` stays `free` / `share`.
- **Build Next** saves the draft as built and opens the review.
- **`refresh.py --optimize`** prints proposals and writes nothing.
- **The CLI's `--apply`** is kept, for sessions after a read.

## Phase C — the session is the judgment layer (SHIPPED)

1. **Looking past EDHREC.** The report now has `reads`: owned, free, in-identity, nonland
   cards that EDHREC doesn't list for the commander, so they could never be proposed.
   - **Ranking:** by `deck_fit.assess_card`'s score, with at most `READS_PER_ROLE` (3)
     per role and a `READS_MIN_FIT` (70) floor, up to `READS_LIMIT` (8). The fit engine
     leans on whichever role the deck is short of: Beorn's first draft was five board
     wipes.
   - **Presentation:** never tickable. The ⚡ page shows them as "Worth a read", and a
     read the player wants becomes a manual add.
   - **Honest limit:** ties fall back to alphabetical order, and the fit heuristic is
     role-need-heavy (it surfaced Rabid Attack as Ur-Dragon "draw"). It's a starting pool
     for a read, labelled that way on every surface.
   - **Second lane, the same day.** Enlightened Tutor (owned, a Game Changer, 10% for the
     Ur-Dragon) fell through every net. It was under the margin, so no proposal; under
     `RISER_FLOOR` (20), so no riser; and on the field's list, so not a read. So reads
     now also take owned cards the field lists below `RISER_FLOOR`, in their own lane of
     up to `READS_RARE_LIMIT` (6), ranked by field %. The fit heuristic undervalues tutors,
     so that lane can't share the fit-ranked one. Each read carries its `field` % (or None).
   - **Still a feed, not a net.** With six owned cards at 13-19%, Enlightened Tutor (10%)
     still ranks seventh. The lane wasn't widened further to force it: player-named cards
     are always read (card-review-method step 1), and that is the rule that caught it.
   - **Name-only intake rows have no types**, so a card logged on the player's word isn't
     read until enrichment types it (`attrs-snapshot.yml` on the runner, or `carddb.py`
     locally). Never guessed.
2. **The review packet.** `/deck/<stem>/assess.txt` has a "FOR A CLAUDE READ" block: every
   proposal with its evidence, then the reads, with the instruction to give each one
   swap / wishlist / bench / skip.
3. **`optimize.py --json`** prints `review_payload()`: proposals with keys, reads, risers,
   buys, holds, fetch-guard keeps and role bands. It refuses to run with `--apply`.
   **`--approve "<kind>|<out>|<in>"`** (repeatable) writes only the named proposals,
   through `apply_chosen`, the same path as the ⚡ page.
4. **The skill.** `card-review-method.md` gains "Reviewing the optimizer's proposals", and
   `SKILL.md` step 5, `tool-contract.md` and CLAUDE.md point at `--json` / `--approve`.
5. **The spell margin stays at 25 points** (decided in Phase C). It now only shapes the
   *checkbox* list, which should be short and high-confidence. Everything below the margin
   (risers) and everything EDHREC doesn't list (reads) reaches the player as advice and a
   session as a read. A lower margin would only lengthen the list of field-driven ticks,
   which is the opposite of what the player asked for.

## Phase D — lift replaces synergy (SHIPPED 2026-10-15)

The player: "EDHREC has a new mathematics equation for how to include cards into decks…
review and implement something similar or better if you can evolve it."

**What EDHREC changed.** "From Synergy to Lift: The Math Behind EDHREC's New Era of
Recommendations" (Julia Maddalena, 2025-12-15) retired *synergy* on card pages for *lift*.
Over decks in the shared colour identity, lift(A,B) = P(A and B) / (P(A)·P(B)). It is
shown as log10, where 0 means independent and 1 means ten times as likely. Synergy is a
**difference** of two rates. That made it asymmetric, gave big negative scores to
staples like Sol Ring, and capped specificity at the inclusion rate. Lift is their
**ratio**. EDHREC hasn't moved commander pages to lift yet (their filters make it
harder), and the article describes no small-sample correction.

**What we compute** (`deck_fit.commander_lift`):
- **Commander-card lift:**
  - Commander pages still show inclusion and synergy, and synergy = inclusion − (the
    card's rate across decks in these colours).
  - So every committed snapshot already holds the baseline: baseline = inclusion −
    synergy, and lift = inclusion ÷ baseline.
  - **Not exactly EDHREC's lift** (corrected after the Fable review, 2026-10-15): synergy's
    baseline is the card's rate across ALL decks that could run the card, not across decks
    in the commander's colour identity. For a 4-5 colour commander that inflates every
    card (the Ur-Dragon's reads all sit at 6-14×), so a lift is comparable within one
    commander, not across commanders.
  - **Precision:** since 2026-10-15 snapshots store the baseline to one decimal from the
    raw counts (`base`, `edhrec._base`). Whole-percent inputs had moved 47 of 2,067
    specificity tiers at ≥10% inclusion.
- **A baseline floor of 1%.** Snapshots store whole percents, so a baseline under 1 is
  rounding noise. Without the floor, 6% vs 0% would mint an infinite "signature".
- **Small-sample shrinkage:**
  - The commander's rate is pulled toward the baseline by `LIFT_PRIOR_DECKS` = 100
    pseudo-decks: rate* = (inclusion·N + baseline·100) / (N + 100).
  - At this stable's sample sizes (3,700-51,000 decks) it moves almost nothing.
  - On a 30-deck commander it pulls a 5× reading back to about 2×.
  - `N` is `sample_decks` from the snapshot (`edhrec.sample_size`). Unknown N means no
    shrinkage, never a guess.

**Where it acts:**
- **Fit score:** lift replaced the synergy tiers in `_staple_component`. Calibrated on
  all 2,506 rows of the 10 snapshot files:
  - 15 points: a signature card, ≥ 4× its colours and in ≥ 30% of decks.
  - 13 points: ≥ 4× under 30%, or ≥ 2.5× and in ≥ 30%.
  - 11 points: ≥ 2.5×.
  - Nothing under 10% inclusion, however specific.
  - Results: 68% of cards unchanged, 761 commander-specific cards up 2-5 points (Bear
    tribal in Beorn, Roaming Throne), and 38 popular-but-generic cards down 2 (Fog, The
    Great Henge, all under 2.5×). No card both popular and specific loses anything,
    because the inclusion tier still applies.
  - Synergy without an inclusion row keeps the old tiers.
- **Reads:** rarely-listed reads rank by lift (inclusion ≥ 10%), then inclusion. Live
  result: the Ur-Dragon's list now opens with Broodcaller Scourge (14×), Dragonlord
  Ojutai and Majestic Genesis (13×). The old order was by raw inclusion.
- **Proposals carry `cut_lift` / `add_lift`.** `trades_specific` flags a swap that cuts a
  ≥ 4× card for one under 2×, the engine-for-staple trade. The flag is evidence only and
  never removes a proposal.
- **Surfaces:** the ⚡ page ("× the colour average"), the assess packet's FOR A CLAUDE
  READ block, and `optimize.py --json`.

**Before → after on the live stable** (same cache, same decks):
- Giada, Thorin, Tifa, Sephiroth, the Ur-Dragon, Dina, Captain America and Y'shtola: no
  new proposals.
- Kami gains Psychic Corrosion and Horn of Greed (Kami-specific draw payoffs).
- Beorn gains Quarrel.
- Bartolomé's Blood Artist proposal now cuts Throne of the Grim Captain instead of
  Another Chance.
- The trade flag fired on nothing current.

**Known bias.** For commanders whose EDHREC data is mostly one precon (Y'shtola, Cloud),
lift also lifts that precon's own cards, because they co-occur by construction. The read
should treat a cluster of same-set cards at similar lift as a precon echo, not a
signal.

**Found on the way (UAT F8):** an approved ⚡ run re-filed *every* card in the deck, and
its one-tap Undo only reverses the swaps. An artifact creature the player filed under
Artifacts (The Warring Triad, Bartolomé) moved on every approval and never came back.
`apply_chosen` now re-files only the cards it added (`_tidy(..., only=)`). The full
`--apply` pass keeps re-filing everything, per its 2026-08-20 rationale. F8 failed on
main with the same data and passes now.

## Not changed (on purpose)

- `auto_build.py` keeps its own basics count. A from-scratch build needs a land template, and
  the optimizer no longer enforces it afterwards.
- `deck_fit.card_value` (`max(field %, (fit − 60) × 2)`) still values spells. Phase C
  revisits this.
- Manual edits are never optimized. Undo semantics are unchanged.
