# Deck UAT: the build's test run (2026-10-15)

**Status:** v1 SHIPPED (gates 1, 2 and 4). Gate 3 and the experiments below are planned.
**Asked for by the player:** "the deck building workflows should include simulations or
gold fishing to test the decks, correct? Almost like UAT … research and see how other apps
and repos handle this step … think outside the box."
**Research write-up:** the *Deck Testing Lab* page
(https://claude.ai/artifact/Pf3MFut6FKjBuJqFyqq13N). It covers the landscape, the sources
and the Argon engine check.

## What the research changed

docs/research-simulation.md (2026-08-10) set a three-tier ladder: tier 1 goldfish
(shipped), tier 2 scripted opponents (deferred), tier 3 full-rules AI pods (rejected,
"decade-scale"). Two findings move it:

- **Tier 2 can be calibrated, not guessed.** Playgroup's Sparring mode publishes
  interaction tables measured from 6,934 real Commander games and 21,480 interaction casts:
  - the mix is spot removal 58%, counters 19%, wipes 13%, bounce 7% and edicts 3%;
  - interaction is quiet early and peaks mid-game;
  - wipes are 2.5× likelier against 3+ creatures, from round 5.

  That turns tier 2 from invented numbers into sourced, labelled assumptions.
- **Tier 3 doesn't mean building an engine.** Forge ships a headless `sim -f Commander`
  mode, so 4-player pods can run on a GitHub runner. The objection that stands is pilot
  quality: Forge's AI is fair with aggro and midrange and weak with combo and control. So
  tier 3 is a smoke test and a rough matchup chart, never a verdict.

LLM pilots (mage-bench on XMage, mtg-player) and RL agents (MageZero) are research, not
signal: about $1+ per LLM game, misread cards, and 1v1 only for MageZero.

## The gates (v1)

`scripts/deck_uat.py` runs the goldfish and judges every deck it's given:

| # | Gate | Default | Notes |
|---|---|---|---|
| 1 | Keepable opening seven (2-5 lands) | ≥ 75% | consistency |
| 1 | Screwed (< 3 lands at the start of turn 4) | ≤ 25% | consistency |
| 2 | **Engine online**: 1+ engine cards cast by turn 6 (2+ once the list has 25+ cards) | ≥ 50% | the deck's own engine is the oracle: the spec's core, else the notes' `## Protected engine` list |
| 2 | Commander cast by its mana value + 1 | ≥ 50% | informational for a 7+ mana commander until the spec sets a target |
| 4 | Every swap carries a paired A/B | — | `deck_uat.ab()`, `optimize.py --json --ab` |

- **Per-deck targets** live in the engine spec: `engine_spec.py --deck … --uat KEY N`. The
  keys are `keepable_min`, `screw_max`, `engine_turn`, `engine_min`, `engine_pct`,
  `commander_turn` and `commander_pct`. A target that differs from the default needs its
  reason in the deck's notes.
- **A failed gate** sends the deck back to the hand pass, and the CLI exits 3.
- **The A/B** replays the identical shuffles with one card swapped (`goldfish.swap_compiled`,
  common random numbers). Swapping a card with itself is exactly zero, a test pins that,
  and the interval measures the swap rather than the luck.

### Calibration (2026-10-15, 2,000 games per deck, seed 0)

| Deck | Engine cards | Engine cards cast by T6: 1+ / 2+ / 3+ | By T8: 1+ / 2+ / 3+ |
|---|---|---|---|
| Bartolomé | 22 (notes) | 86 / 53 / 20 | 96 / 76 / 46 |
| Beorn | 22 (notes) | 74 / 32 / 7 | 89 / 60 / 29 |
| Captain America | 6 (notes) | **38** / 6 / 0 | 54 / 14 / 2 |
| Dina | 12 (notes) | 58 / 18 / 3 | 75 / 37 / 12 |
| Eriette | 38 (spec) | 97 / 86 / 65 | 99 / 97 / 89 |
| Giada | 14 (notes) | 62 / 22 / 3 | 80 / 41 / 13 |
| Kami | 13 (notes) | 72 / 31 / 7 | 83 / 49 / 18 |
| The Ur-Dragon | 21 (notes) | 77 / 35 / 9 | 90 / 62 / 32 |
| The Ur-Sphinx | 20 (spec) | 75 / 36 / 9 | 90 / 61 / 29 |
| Thorin | 13 (notes) | 53 / 15 / 2 | 74 / 35 / 10 |
| Y'shtola | 23 (notes) | 87 / 55 / 23 | 96 / 78 / 50 |

Every deck kept 80-83% of opening sevens and was screwed 13-16% of the time.

- **The thresholds that didn't work:** a first draft asked for "2+ by turn 6", which
  passed only three decks. Then "one per ten listed" failed all eleven. On the play,
  about 13 cards have been seen by turn 6, so a 22-card list expects about 3 engine
  cards *seen*, and fewer cast.
- **The chosen default** passes ten decks and fails Captain America. Its declared engine
  was six sleeper-audit picks, not the Heroes that are its real engine. The gate caught a
  thin declaration.
  - Its spec now declares the 25 Heroes as a package, with keep reasons for the control
    shell. It passes: 2+ of 27 engine cards cast by turn 6 in 57% of games.
  - Its optimizer proposals are unchanged (none either way).
  - All 11 decks pass. Tinybones, Bauble Burglar, built the same night, makes 12: 83%
    engine online, with its commander out by turn 3 in every game.
- **Dina's protected list** was written as `**Bold**, **names** — why` and parsed to
  nothing. `engine_spec._bullet_names` now reads bold names and drops " — " commentary,
  which also fixes Dina's core for the trades lane.

### First live A/B (the Ur-Sphinx)

- **Unesh → Sharding Sphinx:** engine online −2.4% (±0.7), commander on time −4.8% (±0.9).
  Unesh also discounts the commander.
- **The optimizer's Stroke of Midnight → Fellwar Stone:** +1.2% engine and +2.6%
  commander. A rock speeds up a 9-drop. The goldfish can't value removal, so the verdict
  (skip) still stands. That's why the A/B is evidence and never the verdict.

### Found by the first real use (2026-10-15)

- **The A/B refused basics.** Every optimizer land swap into a Swamp came back "Can't
  resolve". Basics are always owned and the export leaves them out, so
  `goldfish.swap_compiled` now builds a missing basic the way the loader builds the
  deck's own. Its singleton guard also exempts basics.
- **A draft read the commander's type line as its strategy.** Tinybones, a Skeleton
  Rogue, drafted as Rogue tribal. A curated commander now takes its tribe only from its
  `tribal-*` tags (auto_build).

## Next (planned, in order)

1. **Gate 3, calibrated pushback.** Rework `goldfish --disruption` around the published
   tables: interaction drawn by mix and round, wipes weighted by board width from round 5,
   and Light/Realistic/Cutthroat intensities. It reports rebuild turns after a wipe,
   engine survival and commander recasts. Every number is labelled as Playgroup's data.
2. **Mutation testing.** Leave-one-out A/B for every non-land card. Load-bearing cards
   (protect them) versus passengers (cut first), as a data-driven protected list.
3. **Worst-game autopsy.** Keep the three worst seeds by engine-online turn. A session
   replays them and names the failure, and an A/B-tested fix goes in the notes as "how
   this deck loses".
4. **Clips as claims.** A Watch-tab scene with a turn number and mana pool is a claim the
   sim can check. The tab then shows how often the line happens.
5. **The phone game log.** A 20-second entry after each real game: won, engine turn, the
   MVP card, the dead card. Over a season it calibrates the gates and tells the optimizer
   which cards never get cast. Real games are the true UAT.
6. **Forge household pod** (optional). Export to `.dck` and run `forge sim -f Commander`
   on a runner. It reports unsupported cards, game length and win share, labelled as
   limited by the pilots.

## What this never claims

A deck can pass every gate and lose to a real table. The gates are goldfish frequencies
under the assumptions every report ships with: no opponent, no interaction, combat
unblocked. They catch a deck that can't do its own thing. They don't rank it against
yours.
