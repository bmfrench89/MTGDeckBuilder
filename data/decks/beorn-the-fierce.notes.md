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

**Natural Bears** speed this up: Goreclaw, Terror of Qal Sisma; Little Bear; Ordinary Bear;
Beorn, Reluctant Host; Surrak and Goreclaw; Gigantic Big Bear; Studious First-Year. Dancing from
Dark to Dawn makes a 2/2 Bear token on every land, which is a 4/4 next to Beorn.

**Speed:** three cost reducers stack on generic mana. Goreclaw takes {2} off power-4+ creatures,
Radagast of Rhosgobel takes {2} off the first creature each turn and gives it flash, and
Rhonas's Monument takes {1} off green creatures. Beorn himself costs {1}{G}{G} with Goreclaw out.

## Piloting

- Mulligan hands with no ramp and only two lands. Keep Goreclaw or Radagast with lands, since
  either one makes Beorn cost three.
- Use Radagast's flash to cast Beorn at an opponent's end step, after they've had their chance
  to wipe the board.
- Convert your biggest attacker, or a creature you're about to bite with (Terrific Team-Up,
  It's Clobberin' Time!). Trample sends the extra damage to their face.
- **Never add shroud.** Lightning Greaves and Steely Resolve stop Beorn targeting your own
  creature. Swiftfoot Boots (hexproof) is safe.
- Hulk, Brutal Brawler must attack every combat. Don't cast him into a board that eats him.
- Little Bear untaps Llanowar Tribe for three more green.
- Verdant Kraken makes a Forest land creature on every player's upkeep, so it triggers Dancing
  from Dark to Dawn, Beorn's Hospitality and Tireless Tracker about four times a round.

## Wipe plan

Selfless Safewright naming Bear protects every natural and converted Bear. Heroic Intervention,
Tyvar's Stand (X=0 for one green: hexproof + indestructible on Beorn) and Collective
Resistance (hexproof + indestructible on one creature; escalate {G} to also destroy an artifact
and/or enchantment) are the others. Both save ONE creature, so lean on Safewright and Heroic
Intervention against a wipe. Keep
two mana up after a big turn. Ezuri's Predation is the deck's only wipe, and it only hits their side.

## Bracket path (target 3, room for 4)

As built, the deck has no Game Changers, so the bracket rules put it at **Bracket 2**. In play
it's a strong 2 or a light 3. The header declares **3** as the intent. The buy list's tiers are
the path:
- **Bracket 3** (1-3 Game Changers): Natural Order, Worldly Tutor, Biorhythm.
- **Bracket 4** (4+): add Survival of the Fittest, Gaea's Cradle, Ancient Tomb.
Crop Rotation is a Game Changer you already own (2 free copies). It's weak here on its own,
but it fetches Gaea's Cradle at instant speed if you buy that.

## Sideboard

- **Flourishing Grapple** ({G} instant: a red or white creature/planeswalker loses all abilities,
  then your creature deals damage equal to its power to it). Swap it in for Elephant Grass when
  the table is heavy on red or white.

## Elephant Grass

Black creatures can't attack you; everyone else pays {2} per attacker. It buys time while the Bear
board builds, but cumulative upkeep grows by {1} every turn (1, 2, 3…). Pay it for a few turns,
then let it go once Beorn's board can block.

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
