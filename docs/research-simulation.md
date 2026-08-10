# Research — Mass playtesting / simulation ("prove what cards mathematically work")

**Status:** assessment + phased ladder, 2026-08-10. Nothing here is implemented;
Phase 1 is the candidate for a future season. This revisits the project's earlier
"no simulation" scope lock with a concrete cost/benefit per tier.

## The idea being assessed

Run AI-piloted MTG matches at scale (tens of thousands of games, Kaggle-style
compute) to measure card performance empirically — win-rate deltas per card
instead of field popularity.

## The honest difficulty ladder

| Tier | What it simulates | Cost to build | Signal quality |
|---|---|---|---|
| 1. Goldfish Monte Carlo | draws, mulligans, mana, curve — no opponent | **small** (stdlib, offline, deterministic) | high for consistency questions |
| 2. Scripted archetype opponents | tier 1 + a damage/interaction clock | medium | rough but comparative |
| 3. Full-rules multiplayer with AI pilots | actual Commander pods | **enormous** | dominated by pilot quality |

**Why tier 3 is a research project, not a feature.** A full rules engine is a
decade-scale effort (the open-source ones — Forge, XMage — are 15+ years old,
Java, and still chase every new set). Commander adds 4-player politics, where the
AI's threat assessment *is* the result: weak pilots "prove" cards that punish
weak pilots. Every new set (and this collection leans new sets: FF, Marvel,
Fallout, LOTR) waits on engine support before it can be measured at all. And
MTG is literally Turing-complete (Churchill et al., 2019) — there is no shortcut
rules kernel. Kaggle solves none of this; it supplies notebooks and GPUs, not a
Magic rules engine. Verdict: **not worth building here, at any scale.**

**Why tier 1 IS worth building.** A goldfish simulator — shuffle, draw, mulligan
by a keepability rule, play lands, cast on curve — needs no opponent model and no
full rules engine, runs thousands of iterations per second in stdlib Python, and
answers with real statistics the questions this app currently answers with
closed-form estimates or not at all:

- P(commander cast by turn N); flood/screw rates per deck as built
- expected turn the deck's curve actually deploys (vs the curve chart's implication)
- keepable-opening-hand % under a stated mulligan rule (extends `manabase.py`'s
  hypergeometrics to *sequenced* play, which closed forms can't reach)
- A/B: swap one card, re-run 10k draws, report the delta with a confidence
  interval — "mathematically prove" at the consistency level, per THIS deck

Fits every house rule: stdlib-only, offline, hermetic-testable (seeded RNG),
deterministic, grounded in the player's actual lists. Estimated size: one module
+ one dashboard/assess surface.

**Tier 2, maybe later:** a scripted "clock" (opponent deals N damage on a curve,
presents M interactions) turns goldfish numbers into rough race/interaction
comparisons. Cheap to add on top of tier 1, but its assumptions need labeling as
assumptions — it measures decks against a stopwatch, not against people.

## What this does NOT replace

Field data (EDHREC) measures *what wins tables in practice* — thousands of human
decisions the simulator cannot model. Simulation measures *whether the deck's own
machine turns over*. They answer different questions; the app should keep both.

## Recommendation

Build **tier 1 (goldfish Monte Carlo)** as the next engine season:
`scripts/goldfish.py` + a Consistency panel (dashboard/assess) + A/B swap deltas
in the card advisor. Defer tier 2 until tier 1 proves useful in real coaching.
Reject tier 3 permanently unless the project's goals change from "build and tune
my decks" to "do simulation research."
