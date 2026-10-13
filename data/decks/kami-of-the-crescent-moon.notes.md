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
deck runs 24 basic Islands plus Theorist's Sanctum (also an Island), so each +1 is big.

**The line:** cast Jace with ~7 Islands and +1 (Jace 6, token 7 = 13). Next turn +1 with 8
Islands (Jace 7, token 15 = 22). Theorist's Proxy (flash, empower 3) or Theorist's Sanctum
({2}{U}, T: empower 2) gets it past 25. Then use the 0. Each opponent keeps one card, and Kami
makes them draw two at their next draw step, so they lose to an empty library.
- Jace's −3 doubles as a Propaganda-style shield while the counters build.
- Theorist's Proxy's other mode ({U}, sacrifice: your next spell can't be countered) protects
  the turn you go for it.

## The rest of the audit (2026-10-13)
- **Geist of Saint Thalia**: noncreature spells cost {1} less. Nearly the whole deck is
  noncreature (rocks, punishers, counters), so this is ramp in practice.
- **Theorist's Sanctum** replaced one basic Island. It enters untapped if you reveal or
  control a Jace, otherwise tapped.
