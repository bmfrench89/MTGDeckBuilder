# Combo Shapes — read cards for their SLOT, not their power level

Derived 2026-08-19 from the Bartolomé del Presidio deck tech
["1 Deck, 27 Dollars, 600 Infinite COMBOS"](https://www.youtube.com/watch?v=1Yusxsud5BE),
and from the fact that this repo's own `combo_detector` looked at that 100-card deck —
which contains 44 distinct two-card infinites — and printed
`No known combos, complete or one-away.`

**The lesson: a combo deck is usually not a list of combos. It is a LATTICE** — two or
three interchangeable card *classes* whose members combine freely. Evaluate cards by
which slot they fill, and the combo count falls out as multiplication.

## The four slots

| Slot | What it must do | Owned examples |
|---|---|---|
| **OUTLET** | Sacrifice repeatedly for **zero mana**, no once-per-turn | Viscera Seer, Woe Strider, Yahenni Undying Partisan, Bartolomé del Presidio |
| **LOOP** | Return the creature to the battlefield **the instant it dies** | Angelic Renewal, Gift of Immortality |
| **RETURNER** | A creature whose **enter trigger** returns that LOOP card from the graveyard | Sun Titan, Angel of Indemnity, Brotherhood Outcast |
| **PAYOFF** | Convert each death into damage, life, mill or cards | Blood Artist, Zulaport Cutthroat, Bastion of Remembrance |

Sacrifice the RETURNER → the LOOP card brings it back → its enter trigger brings the LOOP
card back → repeat, **at zero mana**. Infinite deaths. The PAYOFF ends the game.

**Combo count = |LOOP × RETURNER legal pairs| × |PAYOFF|.** In the source deck that is
44 × 6 = 264, doubled by a second OUTLET — which is how the video honestly claims ~600.

## The gates that decide a pairing — check every one

Most wrong answers come from skipping one of these:

1. **Mana-value cap.** Sun Titan returns permanents MV ≤ 3, Angel of Indemnity ≤ 4,
   Shepherd of the Cosmos ≤ 2. A LOOP card above the cap is not a combo.
2. **Aura vs. enchantment.** Brotherhood Outcast, Danitha and Boonweaver return an *Aura*.
   **Angelic Renewal is a plain enchantment, not an Aura** — those three cannot return it.
   This single distinction removed 3 of a naive 47 pairings.
3. **Immediate vs. delayed return.** **Gift of Immortality is the trap.** Its *creature*
   returns immediately; only the *Aura* waits for the end step. With a bare OUTLET that is
   once per turn. With a RETURNER that re-fetches the Aura at once, it is fully infinite.
   Read *which half* of the card is delayed.
4. **"another" vs. "a".** Viscera Seer sacrifices *a* creature (itself included); Yahenni
   and Bartolomé need *another*. Matters for whether the outlet can eat itself as the last
   fodder.
5. **Does the trigger read the graveyard?** If yes — and for every RETURNER it does —
   then **Rest in Peace / Grafdigger's Cage turns off the entire lattice at once.** Say so.
6. **Intervening-if gates.** Redemption Choir's Coven needs three creatures with different
   powers *each time it re-enters*. Still infinite, but not free — mark it, don't hide it.

## How to count honestly

- Enumerate LOOP × RETURNER and **print the illegal pairs with the reason**. A count you
  can't itemize is a guess.
- Say which slot the *commander* fills. A free outlet in the command zone is the single
  biggest multiplier in Commander, because it is never a card you have to draw.
- The kill count is engines × payoffs. State both factors, never just the product.

## Writing it into `combos.csv`

- **Use the canonical accented name.** `mtglib._norm` does **not** fold accents; pieces
  written `Bartolome` silently degrade every row to "one piece away — add Bartolomé (not
  owned)" instead of erroring.
- **Rows are card-sets, so encode the PATTERN, not one commander.** The first pass wrote
  45 rows all naming Bartolomé and the KB could not see the identical engine sitting in
  the player's own Y'shtola deck. Add a row per owned OUTLET.
- `--collection-combos` is then the payoff: it answers *"what infinite can I physically
  build today?"* Before this method the answer was **0 of 22**; after, **15 of 82**.

## Where to point this next

Any commander that is a **free, repeatable sacrifice outlet** is a lattice host. When
scouting, filter the pool for that text first and archetype second — it outranks tribal
synergy, because it is the one effect that turns two unrelated cards into a win.

---

# Extension: token, treasure and copy lattices (2026-08-19)

Added after a second deck-tech request (video `j37Rsj4mqhU`, **not viewable** — YouTube is
egress-blocked here and the ID did not resolve through search, so this section is derived
from verified card text and first principles, **not** from that creator's list). Everything
below was checked against Scryfall this session.

## 1. The PAYOFF slot has sub-types, and they are not equal

The lattice in the first half produces **infinite deaths at zero mana**. What you bolt on
decides the ceiling:

| Payoff type | Example | Result | Catch |
|---|---|---|---|
| death → drain | Blood Artist, Zulaport Cutthroat | wins on the spot | blanked by lifegain hate / Platinum Angel |
| **death → mana** | **Ashnod's Altar** (`Sacrifice a creature: Add {C}{C}`), **Pitiless Plunderer** (`Whenever another creature you control dies, create a Treasure token`) | **infinite mana** | **is not a win — see §2** |
| death → mill | Scavenger's Talent lvl 2 | decks the table | slow vs. a big library |
| death → cards | Corpse Augur | — | **not loopable**: it dies once, it is not the recurring creature |

**Rule: infinite mana is a resource, not a win. Always name the sink in the same breath.**
A deck that "goes infinite" and then does nothing has lost to its own combo.

## 2. Cards that fill TWO slots are worth more than two cards

**Ashnod's Altar is simultaneously the OUTLET and the death→mana payoff.** That is the whole
reason it is a staple — it collapses two lattice slots into one card, which shortens every
combo in the deck by a piece. Phyrexian Altar does the same and fixes colour. When scouting,
weight a dual-slot card far above a card that only does one job better.

## 3. The COPY lattice — same skeleton, different verb

Instead of *dies → returns*, it is *enters → copies → untaps the copier*:

- **Kiki-Jiki, Mirror Breaker** — `{T}: Create a token that's a copy of target nonlegendary
  creature you control, except it has haste. Sacrifice it at the beginning of the next end
  step.` Pair with any creature whose ETB **untaps Kiki** (Zealous Conscripts, Pestermite,
  Deceiver Exarch) or blinks him back untapped. Infinite hasty bodies.
- **Two gates people miss.** The copy target must be **nonlegendary** (so Kiki cannot copy
  himself, and cannot copy most commanders), and the tokens **die at the next end step** —
  so a copy loop must **win this turn**. A drain payoff or haste damage is mandatory; "I
  have infinite blockers" is not a combo.

## 4. Doublers are MULTIPLIERS, not engine pieces — do not slot them as combo cards

Doubling Season, Parallel Lives, Anointed Procession, Mondrak scale a **finite** engine.
On an already-infinite loop they do nothing: **infinity × 2 is still infinity.** Counting a
doubler as a combo piece is a classic mis-slot and inflates a combo census with lines that
are not combos. (The genuine exception is a doubler that changes a *rate into a threshold* —
e.g. doubling loyalty counters to ultimate a planeswalker immediately.)

**Academy Manufactor is not a doubler, it is a transmuter**: `if you would create one or more
Clue, Food, or Treasure tokens, create that many of each instead`. On an infinite Treasure
loop it converts one infinite resource into three — infinite Clues (draw your deck) and
infinite Food (arbitrary life) alongside the mana. Slot it as a **payoff amplifier**, and
note it makes the loop draw-your-library, which needs a Thassa's-Oracle-style out or you deck.

## 5. Where this collection actually stands (counted 2026-08-19, snapshot 2,691 uniques)

**This shape is NOT supported.** Honest counts, not vibes:

| Class | Owned |
|---|---|
| death → mana outlets | **2 / 15** — Deadly Dispute ×2, Songs of the Damned, and **both are one-shot spells, not repeatable outlets** |
| copy engines | **1 / 16** — Rite of Replication (a one-shot, not a loop) |
| token/treasure doublers | 3 / 15 — Roaming Throne, Wizard's Staff, Delney (all *trigger* doublers, not token doublers) |
| treasure makers | 3 / 16 — Seize the Spoils ×3, Big Score, Wayfarer's Bauble |
| mana sinks | 2 / 11 — **Exsanguinate**, Profane Command |

No Ashnod's Altar, no Phyrexian Altar, no Pitiless Plunderer, no Dockside, no Kiki-Jiki,
no Doubling Season. **Do not build toward this shape from this collection today.**

**CORRECTION (same day):** that verdict was true of the *staples list* and wrong about the
*archetype* — scanning a generic staples list is the wrong instrument for "is X supported".
The player owns **Smaug, Wicked Worm x2** (a treasure commander already verified in
`commanders.csv` with a saved field snapshot), plus Smaug the Magnificent, Smaug the
Impenetrable, Hellkite Tyrant, The Reaver Cleaver and The Sackville-Bagginses — a complete
owned treasure package that a commander-page scan finds immediately and a staples scan
never will. The deck now exists (`data/decks/smaug-wicked-worm.txt`, 72/100, field 13/25).
**Rule: count archetype support against the pool AND the owned-commander pages, never
against a staples list alone.**

**The one buy that matters: `Ashnod's Altar`.** Y'shtola already runs **Sun Titan + Angelic
Renewal** (the loop) and **Exsanguinate** (the sink). Ashnod's Altar is the only missing
piece, and because it is outlet *and* mana payoff at once it gives that deck a **second,
independent infinite kill** that does not care whether Blood Artist has been removed —
infinite {C} into a lethal `{X}{B}{B}` Exsanguinate. Prices unverified: no feed is reachable
from this sandbox.

---

# Extension 2: the MULTIPLICATIVE lattice — "crazy amounts" is not "infinite"

Written 2026-08-19 from a real decklist the player supplied for the video that could not be
reached (see Extension 1): **Thorin, King of Durin's Folk** Boros Dwarf tribal, 99 + commander,
20 lands. Every card cited here was verified against Scryfall this session.

**Thorin** — `{3}{R}{W}` Legendary Creature — Dwarf Noble 4/4 (The Hobbit Eternal):
*"Whenever Thorin or another Dwarf you control enters, create a Treasure token. Other Dwarves
you control get +1/+0 for each artifact token you control."*

## The finding: this deck has NO infinite combo, and that is by design

Read the three copy engines:

- **Molten Echoes** — *"Whenever a **nontoken** creature you control of the chosen type enters…"*
- **Flameshadow Conjuring** — *"Whenever a **nontoken** creature you control enters…"*
- **Cadric, Soul Kindler** — *"Whenever another **nontoken** legendary permanent you control enters…"*

> ## The one-word diagnostic
> **When you read a copy effect, look for the word `nontoken` first.** It tells you in a single
> word which lattice you are in. `nontoken` ⇒ the copies cannot feed the engine ⇒ **no loop is
> possible, ever.** No `nontoken` ⇒ check for a loop immediately.
>
> This is the fastest combo read in the game and it is one word long.

Kiki-Jiki (Extension 1) has no `nontoken` clause — which is exactly why it loops, and why the
untapper is a *separate* card. These engines are the deliberate opposite.

## Slots of the multiplicative lattice

| Slot | Job | Example here |
|---|---|---|
| **TRIGGER SOURCE** | converts an event into a resource | Thorin (Dwarf enters → Treasure) |
| **BODY multiplier** | more creatures entering | Molten Echoes, Flameshadow Conjuring, Cadric |
| **TOKEN multiplier** | more tokens per creation event | Xorn (+1), Anointed Procession (×2), Mondrak (×2), Academy Manufactor (×3 *types*) |
| **TRIGGER multiplier** | the trigger itself fires more often | Roaming Throne (name Dwarf → Thorin triggers twice) |
| **PAYOFF** | turns the pile into a win | Thorin's own anthem (+1/+0 per artifact token), **Terror of the Peaks** |

**Check the payoff for the same gate.** Terror of the Peaks reads *"Whenever another creature
you control enters"* with **no** `nontoken` clause — so it *does* see every token copy. A payoff
that is nontoken-gated while your multipliers are not (or vice versa) is a dead card in the deck.

## Why the multipliers are NOT interchangeable

They apply at **different points in the chain**, so they compose multiplicatively rather than
additively. One nontoken Dwarf cast, with Thorin + Roaming Throne (Dwarf) + Molten Echoes
(Dwarf) + Xorn + Anointed Procession on board:

1. Dwarf enters → Thorin triggers, **doubled by Roaming Throne** = 2 Treasure events
2. Molten Echoes copies it (free) → the token is a Dwarf entering → Thorin triggers, doubled
   again = **2 more events**. Molten Echoes does *not* re-trigger — the copy is a token.
3. Each of the 4 events: create 1 Treasure → **Xorn +1** → **Procession ×2**

**= 16 Treasures from one Dwarf**, and every other Dwarf gets **+16/+0**. That is the "crazy
amounts." It is exponential in the number of multipliers and strictly **finite**.

**Play tip — order your replacement effects.** With Xorn and Anointed Procession both out you
choose the order, and it is not symmetric: `(1+1)×2 = 4` beats `(1×2)+1 = 3`. Apply Xorn
**first**. (Standard replacement-effect choice — the affected object's controller picks the
order. **Uncited:** the Comprehensive Rules are unreachable from the sandbox; confirm the rule
number with `rules.py` on the player's PC before quoting one.)

## This CORRECTS Extension 1

Extension 1 said *"doublers are multipliers, not combo pieces — infinity × 2 is still infinity."*
That is true **only on an infinite engine**. The full rule is:

- **Infinite lattice** → a doubler is a **dead card**. It adds nothing to ∞.
- **Multiplicative lattice** → doublers **are the deck**. They are the win condition.

So the first question about any token doubler is *"is this deck's engine infinite or finite?"*
The same card is a dead draw in one and the payoff in the other. Never evaluate a doubler
without answering that first.

## Why no rows were added to `combos.csv` for this deck

**`combos.csv` is for combos, and this deck does not contain one.** Adding "Thorin + Molten
Echoes" as a combo row would be exactly the census inflation Extension 1 warns about. A
multiplicative engine belongs in a deck's `.notes.md` game plan, not in the combo KB.

## Collection verdict (counted 2026-08-19)

**30 of 80 non-basic slots owned — and none of the engine.** Everything owned is generic
(Sol Ring, Arcane Signet, Path to Exile, Swords to Plowshares, duals). **Zero** Seven Dwarves,
no Thorin, no Cadric, no Molten Echoes, no Flameshadow Conjuring, no Academy Manufactor, no
Anointed Procession, no Mondrak, no Xorn, no Magda, no Goldspan Dragon, no Dwarven Recruiter.
The one real overlap is **Roaming Throne** (owned ×1, uncommitted) — a trigger multiplier
looking for a tribal deck that does not exist in this collection yet. **Not buildable; do not
start here.**
