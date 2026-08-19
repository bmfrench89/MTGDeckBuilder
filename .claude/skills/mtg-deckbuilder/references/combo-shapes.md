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
