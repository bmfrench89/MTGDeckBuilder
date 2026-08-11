# Iron Man, Armored Avenger — Arc Reactor Online

## Game plan
Draw-go control that turns card draw into a clock. Iron Man, Armored Avenger
converts draws into +1/+1 counters and gives the team flying (functional text per
`data/reference/commanders.csv`; Scryfall verification unavailable in this build
session — network blocked, re-verify with `carddb.py --verify` from the PC).
Hold up Counterspell, Mana Drain and Force of Will; refill with Rhystic Study and
Mystic Remora; every draw makes the commander bigger. Windreader Sphinx,
Favorable Winds and Gravitational Shift weaponize the all-fliers board; Rogue's
Passage and Phantom Warrior close via commander damage when the air is contested.

## Engine pieces (do not cut)
- Mana Drain — the free counter that banks mana for Torrential Gearhulk turns.
- Force of Will — protects the engine with zero mana open.
- Rhystic Study / Mystic Remora — the draw engines that fuel the armor.
- Torrential Gearhulk — flashbacks Dig Through Time, Bribery answers, counters.
- Archmage Emeritus — every counterspell cantrips.
- Bribery — steals the best thing in the deck that beat us last game.
- Sharding Sphinx — thopter swarm; each token raises the artifact count for
  Inspiring Statuary and Gearseeker Serpent.

## Physical copies
Shared with other decks (dashboard badges them): Force of Will, Rhystic Study,
Counterspell, Mystical Tutor, Dig Through Time, Mystic Remora, Archmage Emeritus,
Sky Diamond, Thought Vessel, Swiftfoot Boots, Propaganda, Sublime Epiphany.
Islands: 23 owned, 18 sleeved elsewhere — pull ~25 spare Islands from the bulk
box (basics are exempt from conflict tracking by convention).

## Mulligan guide
Keep: 3+ lands with a rock or a draw engine (Remora/Rhystic) or 2 counters.
Ship: hands with zero interaction, or 5-land hands with no draw.
The deck mulligans well — Brainstorm/Frantic Search/Accumulated Knowledge dig.

## 2026-08-11 sleeper audit adds (manual — do not cut)
- Valeria Richards, Precocious — noncreature spells cost {1} less; first noncreature
  spell EACH turn draws a card (triggers on opponents' turns in draw-go). Verified
  MSC #38. In over Coveted Jewel (0% field, gift-wraps 3 cards to an attacker).
- Wizard's Staff (copy #2) — equip Archmage Emeritus for {1} (Wizard): magecraft
  triggers twice, two cards per instant. Verified HOB #59. In over Essence Scatter.
- Riddles in the Dark — {2}{U} instant, 4-card Fact-or-Fiction piles; instant-speed
  selection that also fuels Dig Through Time. Verified HOB #53. In over the deck's
  lone Accumulated Knowledge (draw 1 for 2 with no other copies).
- Myriad Landscape — ramp in mono-blue; also shrinks the Islands-owed count by one.
