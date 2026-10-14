# Spec: the optimizer proposes, judgment decides

**Status:** Phases A and B SHIPPED (2026-10-14). Phase C specified, not started.
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

## Phase C — the session is the judgment layer (NOT STARTED)

1. **Look past EDHREC.** Add a `reads` list to the report: owned, free, in-identity spells
   EDHREC doesn't list, ranked by `deck_fit` fit and engine words (the deck's `.notes.md`,
   archetype, commander text). Never proposed for ticking; shown as "worth a read" on the ⚡
   page and in the packet.
2. **The review packet** (`/deck/<stem>/assess.txt`) gets an "Optimizer proposals" block:
   every proposal and read, with evidence, ready for a session to judge.
3. **`optimize.py --json`** emits `proposals()` plus reads, so a session consumes structured
   data instead of parsing the CLI text.
4. **Skill:** step 5 already says read, then apply on the player's go
   (`SKILL.md`, `tool-contract.md`). Phase C adds a "review the ⚡ proposals" workflow to
   `card-review-method.md`, with the verdict vocabulary (swap / wishlist / bench / skip) applied
   to each proposal.
5. **Spell-pass margin.** Revisit the 25-point field margin once a session reads every
   proposal anyway. It exists to stop churn in an auto-applying world, and that world is gone.

## Not changed (on purpose)

- `auto_build.py` keeps its own basics count. A from-scratch build needs a land template, and
  the optimizer no longer enforces it afterwards.
- `deck_fit.card_value` (`max(field %, (fit − 60) × 2)`) still values spells. Phase C
  revisits this.
- Manual edits are never optimized. Undo semantics are unchanged.
