# The Sleeper Audit — engine-read card review

The method for reviewing cards against decks: new arrivals, a player's "what about
X?" question, or a full pass over the unplaced pool. Named for what it exists to
catch: **Wizard's Staff sat at 4% field inclusion and was nearly skipped — reading
its text against Y'shtola's triggers made it the best add of the session.** Field
numbers are a *prior*; reading the card against the deck's engine is the *verdict*.

Triggers: "review my new cards", "sleeper audit", "did these get scanned?",
"would X make my decks better?", or any time a batch of cards enters the collection.

## The loop

For each deck (or the deck in question):

### 1. Build the candidate pool — counted, not vibed
- **Field hits:** cross-reference unplaced owned cards against the commander's
  field snapshot (`data/reference/field/<stem>.json`). Anything the field plays
  is color-legal and comes with an inclusion %.
- **Gate-held risers:** the optimizer preview's "own it, gate held it" lines.
- **Recent arrivals:** the export's `Date Bought` column (`deckcore.new_arrivals`
  when enriched; a rarity filter — rares/mythics/legends — when not: that tier is
  where sleepers live; commons earn a look only when a themed set matches a deck).
- **Player-named cards:** always, whatever their numbers say.

### 2. Verify text BEFORE judging — no exceptions for post-2025 sets
`carddb.py --verify` / the card-verifier agent when Scryfall is reachable; web
search (Scryfall/Gatherer page snippets) when it isn't; batch 3–4 cards per query.
A card that cannot be verified gets verdict UNVERIFIED and no swap — never judge
from memory of a post-cutoff set. Cite what you verified.

### 3. Read the card against the ENGINE, not the average deck
Name the deck's actual engine first (the `.notes.md` game plan), then ask:
- **What does this card multiply?** A trigger-doubler on a trigger-based
  commander (Wizard's Staff on Y'shtola), a damage-doubler with a {1} equip on
  the commander (Mjölnir on Cap), a free-attach on a Colossus Hammer deck
  (Raubahn) — these score far above their field %.
- **What does it need that the deck must already have?** Sun-Spider tutors
  Equipment/Auras — the deck ran zero, so its 26% field score was a mirage.
  Count the targets before crediting the ability.
- **What does it fight in the deck?** Exile wipes starve a graveyard/aristocrats
  engine (Final Judgment vs Blood Artist — grounding rule 5). Double pips strain
  a 5-color base. "Attacks each combat" clashes with a control plan.
- **Is its 0% real?** Field 0% on a Universes Beyond card under a non-UB
  commander (or vice versa) is usually a coverage gap, not a verdict — Skullclamp,
  Bribery, Blood Artist and Selvala all "score" 0%. An engine piece stays no
  matter what the snapshot says.

### 4. Every card gets ONE of four verdicts — no silent drops
- **SWAP** — with a named cut, the cut's field %, and the engine reason.
- **WISHLIST** — right card, no free copy (`deck_conflicts` says it's committed).
- **BENCH** — playable, doesn't beat an incumbent; say which incumbent and why.
- **SKIP/UNVERIFIED** — with the reason (draft chaff, off-identity, text unverifiable).

### 5. Cuts come from the bottom of the field list — after the engine filter
Build the deck's in-deck field-% list ascending, then STRIKE engine pieces,
`.notes.md`-protected cards, and coverage-gap 0%s before calling anything a cut
target. Respect role counts: count ramp/draw/removal/wipes before and after; a
swap that sinks a role below template needs saying out loud (and ideally a
buylist row already queued to repair it).

### 6. Protect what you add, then validate
- Log every swap in `.changes.csv` with `Source=manual-replace` — that is the
  mechanism that stops the optimizer churning a 4%-field sleeper back out.
- Add the card to the deck's `.attrs.csv` (match the file's column count) and,
  for engine pieces, a line in `.notes.md` saying WHY it's there.
- A verified card with a clear role goes into `mtglib.py`'s curated RAMP/DRAW/
  REMOVAL/WIPES/COUNTERS lists — otherwise the power score punishes the swap it
  can't read (Villainous Wrath cost 5 phantom points until curated as a wipe).
- Then: `deck_stats` (100 cards, nothing missing), `singleton_violations`,
  `power.py --rank`, and re-run the optimizer preview — it must say "already
  aligned", not propose reverts.

### 7. Present swaps before applying
The player sees the full Out → In table with field %s and engine reasons first.
Estimates stay labeled; unverified stays unverified; benched cards get listed
with their reasons — an honest "zero of the 96 Hobbit cards beat an incumbent"
is a finding, not a failure.
