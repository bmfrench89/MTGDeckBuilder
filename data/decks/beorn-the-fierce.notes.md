# Beorn the Fierce — game plan

## The engine

**Verified commander text** (Scryfall, deck-verify run 37654666265, 2026-10-07):

> Beorn the Fierce — {3}{G}{G} — Legendary Creature — Bear Shapeshifter Warrior — 6/6
> Trample. Other Bears you control get +2/+2.
> At the beginning of combat on your turn, put a trample counter on up to one target creature
> you control. It becomes a Bear in addition to its other types. Then if you control three or
> more Bears, draw two cards.

Every combat, Beorn turns one creature into a Bear for good. It gets +2/+2 from the anthem and a
trample counter, and the type change has no duration, so it survives Beorn dying. At three Bears
he draws two cards **every** combat. "Up to one" means you can pick no target and still get the
draw. Beorn himself counts as a Bear, so two conversions are enough even with no natural Bears.

**Natural Bears** speed this up: Goreclaw, Terror of Qal Sisma; Little Bear; Ayula, Queen Among
Bears; Rampaging Yao Guai; Beorn, Reluctant Host; Surrak and Goreclaw; Gigantic Big Bear;
Studious First-Year. The Earth King brings a 4/4 Bear token, and Dancing from Dark to Dawn makes
a 2/2 Bear token on every land. Next to Beorn those tokens are 6/6s and 4/4s.

**Ayula is the second engine (2026-10-13).** Whenever ANOTHER Bear you control enters, choose:
two +1/+1 counters on a Bear, or a Bear you control fights a creature you don't control. Every
Dancing token, The Earth King's token and every natural Bear is a trigger, so a landfall turn
is removal. Beorn's conversion makes a creature a Bear without it entering, so it does not
trigger Ayula. A converted creature IS a Bear you control, though, so it can be the fighter.

**The Earth Crystal doubles the counters.** Every +1/+1 counter placed on your creatures is
doubled:
- Ayula's two become four.
- Hulk's attack gives everything else two.
- Dancing's "X counters on cast" becomes 2X.
- Beorn's Hospitality, Managorger Hydra and Yao Guai's X are doubled too.
Beorn's trample counter is not a +1/+1 counter and is not doubled.

**Ramp off the attack.** The Earth King fetches a basic land for each power-4+ creature that
attacks, and next to Beorn every Bear is power 4+. Each land is a Dancing Bear and a Hospitality
counter. Hexhaven Invigorator fetches a land for each point of damage it is dealt (a block, or a
fight). Convert it with Beorn and let Ayula make it fight.

**Kogla, the Titan Ape** fights when it enters and destroys an artifact or enchantment every
attack. Its {1}{G} returns a Human you control to hand, and The Earth King is a Human, so
replaying him makes another 4/4 Bear token (and Kogla is indestructible that turn).

**Speed:** three cost reducers stack on generic mana. Goreclaw takes {2} off power-4+ creatures,
Radagast of Rhosgobel takes {2} off the first creature each turn and gives it flash, and
The Earth Crystal takes {1} off every green spell, not just creatures. Beorn himself costs
{G}{G} with Goreclaw and the Crystal out.

## Protected engine (don't cut; the Bears, the Ayula/Crystal counters engine and the picks field data can't see)
- Goreclaw, Terror of Qal Sisma
- Little Bear
- Ayula, Queen Among Bears
- Rampaging Yao Guai
- Beorn, Reluctant Host // Till and Tend
- Surrak and Goreclaw
- Gigantic Big Bear
- Studious First-Year // Rampant Growth
- The Earth King
- Dancing from Dark to Dawn
- The Earth Crystal
- Beorn's Hospitality
- Hexhaven Invigorator
- Kogla, the Titan Ape
- Radagast of Rhosgobel
- Last March of the Ents
- Overwhelming Stampede
- Unnatural Growth
- Secret Tunnel
- Cosmic Cube
- Ghalta the Unstoppable
- Earth's Mightiest Heroes
- Crop Rotation

## Piloting

- Mulligan hands with no ramp and only two lands. Keep Goreclaw or Radagast with lands, since
  either one makes Beorn cost three.
- Use Radagast's flash to cast Beorn at an opponent's end step, after they've had their chance
  to wipe the board.
- Convert your biggest attacker, or a creature you're about to bite with (Ram Through, Terrific
  Team-Up, It's Clobberin' Time!). Trample sends the extra damage to their face.
- **Never add shroud.** Lightning Greaves and Steely Resolve stop Beorn targeting your own
  creature. Swiftfoot Boots (hexproof) is safe.
- Hulk, Brutal Brawler must attack every combat. Don't cast him into a board that eats him.
- Little Bear untaps Selvala, Heart of the Wilds for a second big mana activation.
- Verdant Kraken makes a Forest land creature on every player's upkeep, so it triggers Dancing
  from Dark to Dawn, Beorn's Hospitality and Tireless Tracker about four times a round.

## Wipe plan

Selfless Safewright naming Bear protects every natural and converted Bear. Heroic Intervention,
Tyvar's Stand (X=0 for one green: hexproof + indestructible on Beorn) and Smuggler's Surprise (the {1} mode: power 4+ gets hexproof and indestructible) are the others. Keep
two mana up after a big turn. Ezuri's Predation is the deck's only wipe, and it only hits their side.

## Bracket path (target 3, room for 4)

**Crop Rotation is the deck's one Game Changer** (2026-10-15, the player's call, in for
Ilysian Caryatid), so the bracket rules now put it at **Bracket 3**, matching the header.
- **What it does here:** {G}, instant, sacrifice a land: put any land from your library onto
  the battlefield. A land entering is a Dancing Bear and a Hospitality trigger, so this is
  both at instant speed.
- **With Roiling Canopy out:** fetching a basic Forest gives a creature +3/+3, as a combat
  trick after blocks. That needs five other Forests still out after the sacrifice.
- **Other targets:** Secret Tunnel makes two Bears unblockable, and Gaea's Cradle if you buy
  it.

The buy list's tiers are the rest of the path:
- **Bracket 3** (up to 3 Game Changers) has room for two of Natural Order, Worldly Tutor and
  Biorhythm.
- **Bracket 4** (4+): add Survival of the Fittest, Gaea's Cradle, Ancient Tomb.

## Win

Last March of the Ents (2026-10-09) is the refuel: it draws cards equal to your greatest
toughness (Beorn alone is 6, a Bear-anthemed Ghalta far more), then puts any number of creatures
from hand onto the battlefield, uncounterable. Cast it with Beorn out so the toughness is there.


Overwhelming Stampede or Unnatural Growth on a wide board of converted Bears. Rogue's Passage and
Secret Tunnel push damage through (Beorn and any converted creature share the Bear type).

## Deliberate picks the field data can't see

- **Cosmic Cube**: every attack, cast a spell from the top six for free if its mana value is no
  more than your biggest attacker's power. With 6-12 power attackers that's nearly any spell.
- **Ghalta the Unstoppable**: costs {8}{G} minus your biggest power, so {2}{G} next to Beorn and
  {G} with Goreclaw too. It gives the whole team trample. The fit score only sees the printed 9.
- **Earth's Mightiest Heroes**: tap 5 power (teamwork) to put every creature from the top eight
  onto the battlefield.
- **Vaultborn Tyrant**: "Whenever this creature or another creature you control with power 4 or
  greater enters, you gain 3 life and draw a card." With Beorn out, 21 of the deck's other 34
  creatures enter with power 4 or more, and so do Dancing from Dark to Dawn's and The Earth
  King's Bear tokens: each one is a card and 3 life. When it dies, if it's not a token, it comes
  back as a token copy. EDHREC's Beorn page doesn't list it, so on 2026-10-16 the optimizer
  scored it 0 and proposed cutting it for Quarrel. The player: "Vaultborn tyrant is a very
  powerful card".

The field data can't see these cards, so the optimizer proposes cutting them for Grizzly Bears,
Fog or Quarrel. Those would be clear downgrades.

## 2026-10-15 arrivals (manual — do not cut)
- **Ordinary Bear**: a vanilla 4/5 Bear for {3}{G}, so a 6/7 next to Beorn. It is a
  natural Bear toward Beorn's three-Bear draw, and it triggers Ayula as it enters. In over
  Whiptongue Hydra, which only answers fliers. Scrapshooter and Bugenhagen still do.
- **Springleaf Parade**: {X}{G}{G} enchantment. "When this enchantment enters, create X 1/1
  colorless Shapeshifter creature tokens with changeling." Changelings are every creature
  type, so each one is a Bear: a 3/3 with Beorn, and an Ayula trigger as it enters. Its
  second line, "Creature tokens you control have '{T}: Add one mana of any color'", turns
  every token into a mana dork, including Dancing from Dark to Dawn's Bears and The Earth
  King's. In over Wood Elves. The ramp counter drops from 18 to 17 because it can't see
  token mana.

## 2026-10-16: Elephant Grass (the player's pick — do not cut)
- **Elephant Grass**: {G} enchantment. "Cumulative upkeep {1}. Black creatures can't attack
  you. Nonblack creatures can't attack you unless their controller pays {2} for each creature
  they control that's attacking you." Your own attacks aren't taxed. In over Mirkwood
  Pathmaker, a {2}{G} creature with no abilities whose power and toughness equal your land
  count. The deck already has a hexproof creature that does that job for the same cost.
- **The upkeep is rent.** Each upkeep adds an age counter, and you pay {1} per counter or
  sacrifice it: 1, then 2, then 3, then 4, so 10 mana for four turns. The average share of
  that turn's mana it takes (goldfish, 2,000 games):

  | Cast on | 1st upkeep | 2nd | 3rd | 4th |
  |---|---|---|---|---|
  | Turn 2 | 1 (32%) | 2 (51%) | 3 (64%) | 4 (75%) |
  | Turn 4 | 1 (22%) | 2 (39%) | 3 (53%) | 4 (63%) |
  | Turn 6 | 1 (18%) | 2 (32%) | 3 (44%) | 4 (54%) |

  Hold it for two or three turns, then stop paying and let it go. Cast early, it covers the
  turns before Beorn's board can block. Cast late, the same rent is a smaller share.
- **Paired A/B** (4,000 games, Pathmaker out, Elephant Grass in): no measurable change.
  Keepable stays 80% and screwed 15%, engine online moves +0.1% and the commander on time
  +0.2%. The goldfish has no opponents, so it can't see what the tax saves you.

## 2026-10-16: Ancient Adamantoise (the player's pick — do not cut)
- **Ancient Adamantoise**: a {5}{G}{G}{G} 8/20 Turtle. "Vigilance, ward {3}. Damage isn't
  removed from this creature during cleanup steps. All damage that would be dealt to you
  and other permanents you control is dealt to this creature instead. When this creature
  dies, exile it and create ten tapped Treasure tokens." In over Ghalta, Primal Hunger, so
  the 7+ mana slots stay at seven.
- **Your fights become one-sided.** Ayula's fight on every Bear that enters, Kogla's enter
  fight and Ezuri's Predation's Beasts deal their damage and take none back. Your attackers
  survive any block until the Turtle has soaked 20.
- **Cost:** Goreclaw, Radagast and The Earth Crystal together bring it down to {G}{G}{G}.
- **Payoffs:** its power 8 draws off Vaultborn Tyrant, Elemental Bond and Garruk's Uprising.
  Last March of the Ents draws 20 off its toughness, or 22 as a Beorn Bear.
- **Watch out:**
  - While it's out, Hexhaven Invigorator is never dealt damage, so its land fetch stops.
  - Deathtouch damage dealt to anything of yours is dealt to the Turtle, and kills it.
  - Its damage stays marked, so 20 in total over the game kills it. Then you get ten
    tapped Treasures.
- **Paired A/B** (4,000 games, Ghalta, Primal Hunger out): no measurable change.
