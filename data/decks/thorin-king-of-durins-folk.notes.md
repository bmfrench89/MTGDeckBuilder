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
- **Bofur, Reliable Guardian // Concerted Care** — {W} lifelink Dwarf whose
  Adventure half reads *"Target artifact or creature you control gains hexproof and
  indestructible until end of turn."* The deck's best protection, and it costs one
  white mana. Hold it for Thorin.
- **Thorin Oakenshield** — {R}{W} 2-drop, *"As long as you have an enduring story,
  artifacts and creatures you control have ward {1}."* Blanket ward on the whole
  board once Storied is on; the second protection effect, not the only one.
- **The Lonely Mountain** — a land that makes 2/2 Dwarf tokens, cheaper per
  Equipment. A mana sink that feeds Thorin directly.

## Storied turns on almost immediately

Several Dwarves (Fíli, Kíli, Thorin Oakenshield) read *"Storied — if you control
three or more artifacts, legendaries, and/or Sagas, you have an enduring story for
the rest of the game."* Treasures are artifacts and the deck is thick with
legendary Dwarves, so the condition is usually met on the turn Thorin lands and is
permanent thereafter. Sequence to hit three sooner rather than later: it switches on
Fíli's +1/+1, Kíli's free equip, and Oakenshield's ward all at once.

## An Unexpected Party is a second multiplier, and for the same reason

Verified 2026-08-20 (runner run 32330821297), `{2}{W}{W} // {X}{2}{W}`:

> As this enchantment enters, choose a creature type.
> Creatures you control of the chosen type get +2/+2.
> // **Create X 2/2 red Dwarf creature tokens.**

Apply the one-word test again. Those are **token** Dwarves, so Fíli ignores them —
but **Thorin does not**, because his trigger has no nontoken clause. Casting the
Adventure half for X=4 therefore makes four Dwarves, four Thorin triggers, **four
Treasures**, and +4/+0 across the board on the spot. Then the enchantment half is
still in exile to cast later as a +2/+2 Dwarf anthem. It is in 79% of the field's
decks, and the second copy is still free if another R/W deck ever wants one.

## Belladonna Took is a sleeper — do not let the field prior cut her

Verified: *"Whenever a token you control enters, you gain 1 life if this is the first
time this ability has resolved this turn. If it's the second time, draw a card. If
it's the third time, put a +1/+1 counter on each creature you control."* Her field
share is only 12%, but this deck makes tokens in threes without trying — Thorin's
Treasure, Fíli's Dwarf, and that Dwarf's own Thorin trigger — so the third tier
(a board-wide +1/+1 counter, every turn) is the normal case here, not the ceiling.

## Piloting

- Thorin is the engine, not the payoff — cast him early, expect him to eat removal,
  and hold a rebuild rather than dumping the hand behind him.
- Treasures are ramp *and* pump. Spending them to cast another Dwarf is usually
  right early; holding them as +1/+0 is right once the board is wide.
- The deck has **0 counterspells** and **0 recursion** (see the Resilience axis).
  It rebuilds by casting more Dwarves, which means holding two or three back
  through a likely board wipe is the correct default, not greed.

## Known weaknesses (measured, not guessed)

- **Resilience 2 protection · 0 recursion.** Bofur and Thorin Oakenshield are the
  two, and until 2026-08-20 the axis reported **0** — not because the deck lacked
  them, but because `power._match` compared bare normalized names and the curated row
  spelled Bofur without its Adventure half. Recursion is genuinely zero: nothing in
  this list returns a permanent from the graveyard, so a wipe costs the whole board.
- **1 tutor.** Consistency is redundancy-led: 29 of the 30 R/W-legal Dwarves owned
  are in this list, so the deck finds *a* Dwarf reliably and a *specific* one never.
- **Bracket 2 (Core), first lethal ~turn 9** in 77% of goldfish games.
- The optimizer's buy list has 11 field staples this deck wants but the collection
  lacks — Fíli and Kíli, Joyous (88% of field decks), Glóin, Dwarf Emissary (82%),
  Magda, Brazen Outlaw (80%) at the top. See `.buylist.csv`.
