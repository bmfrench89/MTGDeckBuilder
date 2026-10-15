# Tifa, Martial Artist — "Seventh Heaven"

Built 2026-10-14 by a session at the player's request ("be creative … create 2 brand new
decks from cards I own … bracket 3/4 … something you would like to play"). Every card is a
FREE copy: no conflicts with any other deck, so it sleeves today.

**2026-10-15:** Giada and Thorin, the player's own commanders, took priority for shared
copies, so this deck swapped out nine spells and five lands (each logged `manual-replace`
in `.changes.csv`): Avacyn, Firemane Commando, Inspiring Overseer, Lightning Greaves,
Swiftfoot Boots, Flawless Maneuver, Swords to Plowshares, Generous Gift, Austere Command.
The replacements are below, each one read against the engine.

## The engine

**Verified commander text** (Scryfall, 2026-10-14):

> Tifa, Martial Artist — {1}{R}{G}{W} — Legendary Creature — Human Monk — 4/4
> Melee (Whenever this creature attacks, it gets +1/+1 until end of turn for each opponent
> you attacked this combat.)
> Whenever one or more creatures you control with power 7 or greater deal combat damage to
> a player, untap all creatures you control. If it's the first combat phase of your turn,
> there is an additional combat phase after this phase.

**Get to power 7 and connect, then fight again.**
- **Melee makes Tifa her own enabler.** Rulings (Scryfall, 2025-06-06): melee counts each
  opponent you attacked with at least one creature, whichever creature it was. Attack all
  three opponents and Tifa is 7/7. Bastion Protector (commander creatures get +2/+2 and
  indestructible) makes her 6/6, so attacking just ONE opponent makes her 7/7. Champion's
  Helm (+2/+2) does the same. (Corrected 2026-10-14; an earlier line said "two
  opponents".)
- **Annie Joins Up is the best card in the deck.** "If a triggered ability of a legendary
  creature you control triggers, that ability triggers an additional time." Melee
  triggers twice, so Tifa gets +6/+6 attacking three opponents. Her combat-damage trigger
  triggers twice, and both instances resolve during the first combat. CR 500.8
  (retrieved): "If multiple extra phases are created after the same phase, the most
  recently created phase will occur first." That makes **three combats**. Goreclaw's and
  Vincent's attack triggers double too, because both are legendary.
- **Equipment:**
  - Wrecking Ball Arm: base 7/7, can't be blocked by power 2 or less, "Equip legendary
    creature {3}".
  - Colossus Hammer: +10/+10. Puresteel Paladin makes equip {0} with three artifacts out.
  - Leyline Axe: double strike and trample.
  - Champion's Helm: hexproof on a legendary.
  - Hero's Blade: +3/+2, and it attaches itself whenever a legendary creature you control
    enters. Tifa arrives as a 7/6 without paying equip {4}.
  - Darksteel Plate: indestructible, equip {2}.
  - Conqueror's Flail: opponents can't cast spells during your turn.
  - Red XIII gives modified creatures trample and vigilance.
- **The fat:**
  - Terrian, World Tyrant (9/7 for five).
  - Carnage Tyrant, Coliseum Behemoth, Savage Land Dinosaur, Saber-Tooth Moose-Lion.
  - Balamb T-Rexaur, Spider-Rex, Rhino, Gladiolus, Hellkite Tyrant, Combustible Gearhulk,
    Akroma Angel of Fury.
  - Goreclaw: power 4+ creatures cost {2} less and get +1/+1 and trample when it attacks,
    so every 6-power body is a 7.
  - Moonshaker Cavalry: your creatures gain flying and +X/+X, X = creatures you control.
    It's the finisher.
- **Cards that scale with power:** Lifestream's Blessing (draw X, X = greatest power),
  Colossal Majesty (draw in upkeep with power 4+), Rhino (attacks after a 4+ MV spell:
  draw), Garruk's Packleader (another power 3+ creature enters: draw), Thickest in the
  Thicket (X +1/+1 counters where X is the creature's power, so Tifa goes from 4 to 8, and
  it draws two at your end step if you control the creature with the greatest power),
  Professional Face-Breaker (combat damage: Treasure).
- **Removal that scales with power:** Quarrel (your creature deals damage equal to its
  power) and Monstrous Onslaught (X damage divided, X = greatest power you control).

## Protected engine (don't cut; the optimizer has no field data for most of these)
- Annie Joins Up
- Wrecking Ball Arm
- Colossus Hammer
- Leyline Axe
- Champion's Helm
- Puresteel Paladin
- Goreclaw, Terror of Qal Sisma
- Bastion Protector
- Moonshaker Cavalry
- Terrian, World Tyrant
- Carnage Tyrant
- Coliseum Behemoth
- Savage Land Dinosaur
- Saber-Tooth Moose-Lion
- Balamb T-Rexaur
- Challenger Troll
- Hellkite Tyrant
- Hero's Blade
- Thickest in the Thicket
- Gladiolus Amicitia
- Lifestream's Blessing
- Colossal Majesty
- Akroma's Will

## Protection and interaction
- Surrak, the Hunt Caller gives haste: at the start of combat, if your creatures have total
  power 8 or more (two bodies here), target creature gains haste. Heroic Intervention,
  Ultimate Magic: Holy (foretell it; cast from exile it also prevents all damage to you),
  Clever Concealment (convoke), Darksteel Plate and Selfless Spirit protect.
- Akroma's Will: with a commander out, choose both modes. That's flying, vigilance and
  double strike, plus lifelink, indestructible and protection from each colour. It's the
  kill turn.
- Removal: Path to Exile, Quarrel, Monstrous Onslaught, Banishing Light, Beast Within,
  Chaos Warp, Stroke of Midnight, Krosan Grip, Vandalblast, Fiery Confluence.

## Pilot notes
- Mulligan for 3 lands plus ramp. Tifa comes down on turn 4 (goldfish: 49% by turn 4,
  mean 4.66).
- Attack every opponent with something: melee counts opponents, not creatures.
- Hold Akroma's Will or Heroic Intervention for the Annie turn.

## The numbers (2026-10-14)
- **Bracket 3, declared** (`# Bracket: 3`, the player's request). The detector reads **2**
  from card signals: no Game Changers are free in these colours except Crop Rotation, and
  it isn't worth a slot. The intent and tuning are Upgraded: three combats a turn, 11
  interaction, 12 ramp, 10 draw.
- **Field:** 20 of EDHREC's top 25 for Tifa, Martial Artist (7,936 decks). Of the other 5:
  Garruk's Uprising and Nature's Lore are in Beorn, Rhythm of the Wild is in the Ur-Dragon,
  and Kutzil and Adriana aren't owned.
- **Optimizer read (2026-10-14):** it proposed cutting the fat for small Equipment (Hero's
  Blade, Explorer's Scope, Trailblazer's Boots) because EDHREC has no rows for those
  creatures. All rejected: the fat is the engine.
- **Mana:** 37 lands (5 Forest, 3 Mountain, 5 Plains), G 21 / W 20 / R 18 sources,
  keepable 80%.
- **Goldfish:** lethal median turn 9, but it models none of Tifa's extra combats, melee or
  Annie. Read it as a floor.

## After the 2026-10-15 reallocation
- **Field:** 15 of the top 25 (60%). Swords to Plowshares and Lightning Greaves went to
  Giada and Thorin; the other eight missing are in Beorn, in the Ur-Dragon, or not owned.
- **Mana:** 37 lands. G 22 / W 18 / R 16 sources, keepable 80%. Red and white run below
  Karsten's targets; a dual for either is the first buy.
- **Interaction 9, ramp 12, draw 10** (detector). Bracket 3 declared, 2 detected.
