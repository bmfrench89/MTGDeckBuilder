# Kami of the Crescent Moon — game plan

## The engine

**Verified commander text** (Scryfall, deck-verify run 38447893724, 2026-10-13):

> Kami of the Crescent Moon — {U}{U} — Legendary Creature — Spirit
> At the beginning of each player's draw step, that player draws an additional card.

Everyone draws two a turn. The deck turns that into damage and pressure: Howling Mine and
Temple Bell pile on more cards, while Black Vise, Iron Maiden, Viseling, Psychosis Crawler and
Ebony Owl Netsuke punish the full hands. Windfall and Prosperity refill on our terms, and
Propaganda plus the counterspells keep the table off us while it happens.

## Second win: Jace, Reality Sculptor (2026-10-13 sleeper audit — do not cut)

**Verified text** (deck-verify run 38447413487; loyalty 5 from the card):
- +1: Empower Jace X, where X is the number of Islands you control.
- −3: Until your next turn, whenever a creature attacks you or a planeswalker you control,
  it gets -5/-0 until end of turn.
- 0: Exile all but the bottom card of each opponent's library. Activate only if there are
  twenty-five or more loyalty counters among Jaces you control.

"Empower Jace X" puts X loyalty on a Jace token you control (it makes one first if needed).
The 0 counts loyalty across **every** Jace you control: Jace himself plus the token. This
deck runs 26 basic Islands (two more since 2026-10-14), plus Theorist's Sanctum and
Mystic Sanctuary, which are both "Land — Island": 28 Islands, so each +1 is big.

**The line:** cast Jace with ~7 Islands and +1 (Jace 6, token 7 = 13). Next turn +1 with 8
Islands (Jace 7, token 15 = 22). Theorist's Proxy (flash, empower 3) gets it to 25.
Theorist's Sanctum ({2}{U}, T: empower 2) alone only reaches 24, so it needs one more +1
turn or Proxy too. (Corrected 2026-10-14: an older line said "Proxy or Sanctum".) Then
use the 0. Each opponent keeps one card, and Kami
makes them draw two at their next draw step, so they lose to an empty library.
- Jace's −3 doubles as a Propaganda-style shield while the counters build.
- Theorist's Proxy's other mode ({U}, sacrifice: your next spell can't be countered) protects
  the turn you go for it.

## The rest of the audit (2026-10-13)
- **Geist of Saint Thalia**: noncreature spells cost {1} less. Nearly the whole deck is
  noncreature (rocks, punishers, counters), so this is ramp in practice.
- **Theorist's Sanctum** replaced one basic Island. It enters untapped if you reveal or
  control a Jace, otherwise tapped.

## 2026-10-14 approved swaps (from a session's read of the optimizer's proposals)
- **Archetype header set to `control draw-engine`.** It was blank, so the optimizer judged
  this counter and draw deck by the default template.
- **Teferi's Ageless Insight** (over Skysovereign, Consul Flagship, whose crew 3 is hard to
  pay here). Verified: "If you would draw a card except the first one you draw in each of
  your draw steps, draw two cards instead." Kami's extra draw-step card is not the first,
  so it becomes two, and every Temple Bell, Windfall or Prosperity draw doubles.
- **Jace's Archivist** (over Thopter Fabricator). Verified: "{U}, {T}: Each player discards
  their hand, then draws cards equal to the greatest number of cards a player discarded
  this way." A repeatable wheel: the full hands it hands out feed Black Vise, Iron Maiden,
  Viseling and Ebony Owl Netsuke, and the cards you draw feed Psychosis Crawler.
- **Halimar Depths and Lonely Sandbar to Islands.** Each Island is +1 empower for Jace.
