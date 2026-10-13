# Thorin, King of Durin's Folk — best build (study, 2026-10-13)

Built from the collection for comparison with the player's own Thorin. It is a study copy
(`# Study: yes`), so it commits no physical cards. It was built as a set with the Ur-Dragon
and Giada study builds, so no card is used more often than the collection owns it.

## The engine

**Verified commander text** (Scryfall, deck-verify run 38456497906):

> Thorin, King of Durin's Folk — {3}{R}{W} — Legendary Creature — Dwarf Noble
> Whenever Thorin or another Dwarf you control enters, create a Treasure token.
> Other Dwarves you control get +1/+0 for each artifact token you control.

Every Dwarf is a Treasure, and every Treasure is +1 power on every other Dwarf. The deck runs
**30 Dwarves**, plus Dwarf tokens from An Unexpected Party's At the Door half and Dwarven
Shortsword. Treasures are the ramp, which is why the classifier's ramp count (5) reads low:
the real ramp is the commander.

**Keep the Treasures.** Spend them only for a big turn, because each one is power on the
board. Draconic Visitor was rejected for this reason: it replaces every artifact token with a
Dragon, which kills both the mana and the pump.

## What the hand pass added (field % from the Thorin snapshot)
- **An Unexpected Party // At the Door** (80%). The Adventure makes X 2/2 Dwarves, so X
  Treasures. Then the enchantment is a +2/+2 anthem for the type you name (Dwarf).
- **The Arkenstone // Seek the Heart** (67%). The Adventure tutors a legendary creature, and
  the deck is full of legendary Dwarves. Then the artifact is +1/+1 to the team and a card
  every end step.
- **Smaug the Magnificent** (58%). Moved here from the Ur-Dragon build, which plays it at 14%.
- **The Misty Mountains Cold** (56%). A Treasure each chapter, then a 6/6 Dragon at four
  Treasures.
- **The Reaver Cleaver** (54%), **Dwarven Shortsword** (37%), **Sting, Bilbo's Sword** (34%):
  equipment for a deck whose Dwarves already carry equipment synergies.
- **Boros Charm** (41%), **Lightning Greaves** (40%), **Big Score** (38%),
  **Blasphemous Act** (48%) and **Celebrate the Mountain-king** (15%). Celebrate exiles a
  nonland permanent from each opponent and recruits.

## What went out
auto_build's filler, all 0-12% in this field: Tremor, Cartographer's Hawk, Endrider
Catalyzer, Explorer's Scope, Giant's Boulder, Spectacular Tactics, Key to the Side-Door,
Thought Vessel, Troop of Ponies, Belladonna Took, Disenchant, Steelshaper's Gift.

## Validation
- 100 cards, singleton clean, sections clean.
- 21 of the field's top 25. The other 4 aren't owned.
- Bracket 2.
- The optimizer's only suggestion is Gleaming Splendor (53%). That copy is in the Giada
  build: the player said their own Giada runs it.
