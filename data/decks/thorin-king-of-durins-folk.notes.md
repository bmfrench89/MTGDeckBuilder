# Thorin, King of Durin's Folk — game plan

**R/W Dwarf tribal, multiplicative.** Built 2026-08-20 from owned cards the day the
collection export added him. Every card text below is quoted from
`data/reference/hobbit-verified-2026-08-20.txt` — the verbatim Scryfall output of
deck-verify run 32322609093 — not from memory.

## The engine, and the one word that makes it multiply

**Thorin, King of Durin's Folk** {3}{R}{W}:

> Whenever Thorin or another Dwarf you control enters, create a Treasure token.
> Other Dwarves you control get +1/+0 for each artifact token you control.

Read those two lines together: Treasures are artifact tokens, so every Dwarf that
enters both *makes* the pump and *is* pumped by it. Nine Dwarves deep, the team is
swinging for absurd numbers off cards that individually do nothing.

**Fíli the Pathfinder** is the multiplier, and the reason is a single word:

> Whenever Fíli or another **nontoken** Dwarf you control enters, create a 2/2 red
> Dwarf creature token.

Fíli is gated on *nontoken*. **Thorin is not.** So one real Dwarf cast:

1. triggers Thorin → Treasure,
2. triggers Fíli → 2/2 Dwarf **token**,
3. that token entering triggers Thorin again → second Treasure.

Two Treasures and a 2/2 body per Dwarf, and every Dwarf on board gets +2/+0 from the
pair of Treasures. It does **not** loop — Fíli ignores its own tokens, which is
exactly the gate that keeps this multiplicative rather than infinite. Do not go
looking for a sacrifice loop here; this deck wins by stacking, not by cycling.

## Protected cards (do not let the optimizer cut these)

- **Fíli the Pathfinder** — the doubler above. Without it the deck is a pile of
  small Dwarves.
- **Kíli the Resourceful** — *"Whenever another Dwarf or Equipment you control
  enters, draw a card. This ability triggers only once each turn."* The card
  advantage that makes a go-wide deck not run out of gas.
- **Dáin's Company** — ETB digs four for a Dwarf or Equipment. Redundancy is this
  deck's consistency mechanism; it has one tutor.
- **Thorin Oakenshield** — {R}{W} 2-drop, *"As long as you have an enduring story,
  artifacts and creatures you control have ward {1}."* The deck's only real
  protection, and it is cheap.
- **The Lonely Mountain** — a land that makes 2/2 Dwarf tokens, cheaper per
  Equipment. A mana sink that feeds Thorin directly.

## Storied turns on almost immediately

Several Dwarves (Fíli, Kíli, Thorin Oakenshield) read *"Storied — if you control
three or more artifacts, legendaries, and/or Sagas, you have an enduring story for
the rest of the game."* Treasures are artifacts and the deck is thick with
legendary Dwarves, so the condition is usually met on the turn Thorin lands and is
permanent thereafter. Sequence to hit three sooner rather than later: it switches on
Fíli's +1/+1, Kíli's free equip, and Oakenshield's ward all at once.

## Piloting

- Thorin is the engine, not the payoff — cast him early, expect him to eat removal,
  and hold a rebuild rather than dumping the hand behind him.
- Treasures are ramp *and* pump. Spending them to cast another Dwarf is usually
  right early; holding them as +1/+0 is right once the board is wide.
- The deck has **0 counterspells** and **0 recursion** (see the Resilience axis).
  It rebuilds by casting more Dwarves, which means holding two or three back
  through a likely board wipe is the correct default, not greed.

## Known weaknesses (measured, not guessed)

- **Resilience 0 protection · 0 recursion** — below both researched bands. Thorin
  Oakenshield's ward {1} is the entire defence.
- **1 tutor.** Consistency is redundancy-led: 29 of the 30 R/W-legal Dwarves owned
  are in this list, so the deck finds *a* Dwarf reliably and a *specific* one never.
- **Bracket 2 (Core), first lethal ~turn 9** in 77% of goldfish games.
- The optimizer's buy list has 11 field staples this deck wants but the collection
  lacks — Fíli and Kíli, Joyous (88% of field decks), Glóin, Dwarf Emissary (82%),
  Magda, Brazen Outlaw (80%) at the top. See `.buylist.csv`.
