# The Plan
A **theory deck** (in the Lab), built 2026-10-16 from the combo comb: "theory based, so
any card, even in decks, is free reign". It counts every card the player owns and
claims no copies.

**Commander (verified):** Smaug the Impenetrable — {5}{B}{R}, Legendary Creature —
Dragon, 8/7. *"Flying, indestructible, haste. Whenever Smaug is dealt noncombat damage,
create that many Treasure tokens."*

Smaug can't die to damage, so the deck points its own damage at him: every point
becomes a Treasure. **Draconic Visitor** — *"If one or more artifact tokens would be
created under your control, that many 5/5 red Dragon creature tokens with flying are
created instead"* — turns those Treasures into Dragons.

# How it wins: the combos (Commander Spellbook confirms all of them)
1. **Smaug + Draconic Visitor + Dragon Tempest.**
   - Dragon Tempest: *"Whenever a creature you control with flying enters, it gains
     haste until end of turn. Whenever a Dragon you control enters, it deals X damage
     to any target, where X is the number of Dragons you control."*
   - Aim a Tempest trigger at Smaug: X damage makes X Treasures, which Visitor turns
     into X Dragons. Each new Dragon deals X more.
   - The board grows exponentially. Point the later triggers at opponents, and every
     Dragon has haste.
2. **Smaug + Stone-Giant of High Pass.** Stone-Giant: *"{2}{R}, Sacrifice an artifact:
   This creature deals 4 damage to any target."*
   - Aim it at Smaug for 4 Treasures. Three pay for the next activation and the fourth
     is the artifact you sacrifice, so it loops forever.
   - Three cards turn the loop into a kill: **Mirkwood Bats** (*"Whenever you create or
     sacrifice a token, each opponent loses 1 life"*), **Marionette Apprentice** (an
     artifact going to the graveyard drains each opponent for 1) and **The
     Sackville-Bagginses** (sacrificing a token drains).
   - With **Fiery Emancipation** out, every activation deals 12. It nets 8 Treasures, so
     the spare activations can go at opponents' faces.
   - Mirkwood Bats sees 4 Treasures made and 4 sacrificed each loop: 8 life from each
     opponent, so five loops is 40.
   - **Not with Draconic Visitor out:** Smaug's Treasures would arrive as Dragons, and
     the loop needs Treasures.
3. **Ganax, Astral Hunter + Draconic Visitor.** Ganax: *"Whenever Ganax or another Dragon
   you control enters, create a Treasure token."* Each Treasure becomes a Dragon, which
   triggers Ganax again.
   - **The loop is mandatory.** With Dragon Tempest or Mirkwood Bats out it kills the
     table. With neither, an unbreakable mandatory loop is a DRAW (Commander Spellbook
     lists it as "Draw the game").
   - **Never put the second of Ganax and Visitor onto the battlefield without Tempest or
     the Bats already out.** Visitor is a Dragon itself, so casting it with Ganax out
     starts the loop.
   - **Order the triggers.** Each new Dragon triggers both Ganax and the payoff, and you
     choose the order (CR 603.3b). Put the payoff's trigger on top so it resolves first.
     If Ganax's trigger always goes on top, the damage never resolves and it's still a
     draw.

# The bursts (no combo needed)
- **Blasphemous Act** ({8}{R}, costs {1} less per creature on the battlefield): 13
  damage to each creature. That's 13 Treasures off Smaug, or 13 Dragons with Visitor
  out.
- **Brash Taunter** (indestructible) deals the damage it's dealt to target opponent.
  **Wrathful Red Dragon** turns damage dealt to any of your Dragons into damage to a
  non-Dragon target.
- **Fiery Emancipation** triples damage from your sources. Blasphemous Act deals 39:
  Brash Taunter hits an opponent for 117, and Smaug makes 39 Treasures.
- **Self-Destruct** on Smaug: 8 damage to any other target and 8 to Smaug, so 8
  Treasures, or 24 and 24 with Fiery Emancipation.
- **Crypt Rats** ({X}, black mana only): X damage to each creature and each player,
  you included. Smaug makes X Treasures.
- **Hellkite Tyrant:** *"At the beginning of your upkeep, if you control twenty or more
  artifacts, you win the game."* Smaug's Treasures are artifacts, so one Blasphemous Act
  goes most of the way.

**Tutors:** Diabolic Tutor, Grim Tutor, Final Parting.

# Mulligan for
- 2-4 lands with both colours plus a rock: Sol Ring, Arcane Signet, Talisman of
  Indulgence, Rakdos Signet, Fellwar Stone, Mind Stone, Thought Vessel.
- Smaug costs 7; Dragonspeaker Shaman discounts every other Dragon by {2}, and
  Desolation of Smaug adds four mana for Dragon spells.

# Weaknesses to respect
- **Draconic Visitor eats your mana.** While it's out, Treasures arrive as Dragons, not
  mana. Cast it when you want bodies or the combo, not when you need the Treasures.
- **The Ganax trap (above):** a mandatory loop with no payoff draws the game.
- **Symmetric damage:** Crypt Rats and Blasphemous Act hit your other creatures, and
  Crypt Rats hits you.
- **Artifact and graveyard hate** slows the Treasure plan; Smaug's indestructibility
  doesn't stop exile or bounce.

# Grounding note
- **Field:** Smaug the Impenetrable, 6,938 EDHREC decks (snapshot 2026-10-16). The
  field's own top cards are mostly direct-damage engines the player doesn't own
  (Pyrohemia, Pestilence, Mayhem Devil). This build leans on the owned ones and the
  combos.
- **Verified text:** every combo piece was read with `carddb.py --verify` on
  2026-10-16, and Commander Spellbook lists all three combos.
- **Deck UAT** (2,000 games): every gate passes. Keepable 81%, screwed 15%, engine
  online 78%.

## Protected engine (the infinite, the damage sources, the Treasure makers, the tutors)
- Draconic Visitor
- Dragon Tempest
- Stone-Giant of High Pass
- Ganax, Astral Hunter
- Mirkwood Bats
- Fiery Emancipation
- Wrathful Red Dragon
- Brash Taunter
- Blasphemous Act
- Self-Destruct
- Crypt Rats
- Hellkite Tyrant
- Smaug the Magnificent
- Diabolic Tutor
- Grim Tutor
- Final Parting
