# Coaching & Assessment — how a champion critiques a deck

This is the method for **assessing an existing deck and advising on it**: critique,
cut/add, rules Q&A, a pilot guide, deck-vs-deck, and moving between brackets. It is the
"AI assessment" layer — and it runs **in a Claude Code session on the player's
subscription**, not as an API call in the web app. Everything here obeys the grounding
rules; coaching that invents cards or rules-lawyers from memory is worse than none.

## The prime rule of coaching: never invent a card or a ruling

Every card you name — a cut, an add, an alternative, a combo piece — must come from a
**real source you can point to**, never free-generated from memory:
- the player's **collection** (`analyze_collection.py`, `deck_conflicts.py --available`),
- the deck itself, or a **saved deck** under `data/decks/`,
- the curated references (`role_staples.csv`, `card_notes.csv` alternatives, `commanders.csv`),
- `auto_build.py`'s ranked candidate pool for a commander, or
- a **verified Scryfall lookup** (web-search / the card panel) — for anything you're not 100% sure exists and does what you think.

If you can't source it, don't say it. This is the single most important discipline: LLMs
hallucinate plausible-but-fake card names and stale oracle text. Select from a real pool;
don't generate.

## Step 1 — gather the facts (run the scripts; don't eyeball)

Before a single opinion, compute the deck's numbers. This IS the grounding ("RAG" over the
deck's real data):

```bash
python3 scripts/power.py --deck data/decks/<stem>.txt --collection <coll> --json   # bracket + power + signals
python3 scripts/deck_stats.py --deck data/decks/<stem>.txt --collection <coll>     # curve, pips, role counts, ownership
python3 scripts/manabase.py --deck data/decks/<stem>.txt --collection <coll>       # consistency / source adequacy / risky-on-curve
python3 scripts/combo_detector.py --deck data/decks/<stem>.txt --collection <coll> # combos present / one-away
```

Read `data/reference/card_notes.csv` for curated card strategy. For any card whose text
you're unsure of (especially post-2025 sets — see grounding rule #3), **web-search its
oracle text + rulings** before reasoning about it. The web app's **"Export assessment
packet"** button (`/deck/<stem>/assess.txt`) dumps all of this at once if the player pastes
it to you.

## Step 2 — the critique rubric (score every dimension, grounded)

Walk all of these. For each: state the **counted finding**, compare to the target, give a
one-line **verdict** (strength / gap / trap), and a concrete fix. Cite numbers from Step 1.

1. **Mana & consistency** — land count vs 36–38; colored sources vs pip demand (`manabase.py`);
   keepable-hand %, and any **cards flagged risky-to-cast-on-curve**. The most-skipped, most
   game-losing dimension.
2. **Ramp** — count vs 10–12. Under → slow; over → flood risk.
3. **Card advantage** — count vs 10–12; prefer repeatable engines over one-shot cantrips.
4. **Interaction** — targeted removal (8–10) + board wipes (3–5) + counters. A deck light on
   answers folds to the table's threats.
5. **Win conditions** — is there a *clear* way to close? Name it. "Good cards" isn't a win-con.
6. **Curve** — peak (healthy ~2–3), and how many 5+ bombs vs ramp to cast them.
7. **Synergy & anti-synergy** — does the engine cohere? Flag cards fighting the plan — e.g.
   **exile-based wraths in a graveyard/aristocrats deck** (rules-reference), lifegain with no
   payoff, tribal cards off-tribe, an "any color" land for a 1-of creature type.
8. **Bracket fit** — `power.py`'s bracket/power vs the pod the deck is *for*. Flag a Bracket-4
   combo sitting in a Bracket-2 deck (or the reverse: a durdle deck that can't close).
9. **Combos** — present, or one card away? Note the bracket implication (a cheap 2-card infinite
   is a Bracket-4 red flag).

## Step 3 — cuts & adds (by selection, with a reason each)

- **Cuts:** the weakest cards *for this deck's plan* — off-role filler, off-curve top-end with
  no ramp, anti-synergy, redundant weak effects, or the lowest-fit cards. Name them + the reason.
- **Adds — owned first:** pull from the player's **available pool** (`deck_conflicts.py
  --available`, `analyze_collection.py`) and `auto_build.py`'s ranked candidates for the
  commander. Each add fills a *specific* gap the rubric found.
- **Adds — buy list for real gaps:** only when the owned pool can't fill a role, suggest
  `role_staples.csv` / `card_notes.csv` alternatives / EDHREC staples — clearly marked "buy",
  priced as an estimate. Feed these to `wishlist.py`.
- Respect color identity and the no-double-single rule (surface, don't block — grounding #8).

## Step 4 — the pilot guide (how to actually play it)

- **Mulligan:** what a keepable opener looks like for *this* deck (lands in the 2–5 band, a
  ramp piece, a payoff; colors you must have early). Cite `manabase.py`'s keepable %.
- **Game plan:** early (ramp / fixing / cheap interaction) → mid (land the engine, protect the
  commander) → late (assemble the win). One sentence each.
- **Sequencing & threat assessment:** what to hold interaction for, when to wipe (and whether
  your own board survives it), what the deck is weak to, and the line that closes.

## Step 5 — other coaching asks

- **Explain a card's role in this deck:** grounded in its oracle text + how it serves the plan
  (use `card_notes.csv` + the deck's archetype). Not a generic blurb.
- **Rules / interaction Q&A:** fetch the exact **oracle text + rulings** (Scryfall) and reason
  from those + the Comprehensive Rules — never from memory for anything uncertain. Watch the
  known traps in `rules-reference.md` (X-spell MV on the stack, cast-triggers resolving even if
  countered, MDFC/flashback MV). Cite the text you used.
- **Deck-vs-deck:** run the rubric on both; compare bracket/power, consistency, speed,
  resilience, and ceiling. Say which is stronger and what each does better — with numbers.
- **Upgrade to a target bracket:** to go *up*, add Game Changers / a tighter combo / faster mana
  from the collection or buy list (`game_changers.txt`, `combos.csv`); to come *down*, cut them.
  Ground every suggestion in what the player owns or a labeled buy.

## Voice & output

Champion honesty (see `persona.md`): lead with the **verdict** (a sentence — what this deck is,
its bracket, its biggest strength and biggest hole), then the rubric findings (tight, numbered,
with the counts), then the **cut/add list**, then the pilot notes. Label every price and every
unverified card as an estimate. If the collection is name-only, say which parts of the read are
limited. Praise what's genuinely good; a champion also tells a friend when the deck is already
strong and doesn't need "fixing."
