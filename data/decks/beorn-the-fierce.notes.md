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

As built, the deck has no Game Changers, so the bracket rules put it at **Bracket 2**. In play
it's a strong 2 or a light 3. The header declares **3** as the intent. The buy list's tiers are
the path:
- **Bracket 3** (1-3 Game Changers): Natural Order, Worldly Tutor, Biorhythm.
- **Bracket 4** (4+): add Survival of the Fittest, Gaea's Cradle, Ancient Tomb.
Crop Rotation is a Game Changer you already own (2 free copies). It's weak here on its own,
but it fetches Gaea's Cradle at instant speed if you buy that.

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

The field data can't see these cards, so the optimizer proposes cutting them for Grizzly Bears or
Fog. Those would be clear downgrades.
