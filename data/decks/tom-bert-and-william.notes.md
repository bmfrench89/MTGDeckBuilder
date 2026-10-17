# Tom, Bert, and William — "Big Bodies, Big Draws"

A **theory deck** (in the Lab), built 2026-10-17 so the player can compare two commanders
for the same card. The player: "Go ahead and make both decks with vaevictis and tom bert and
William as commander in the lab and let's see how they compare." Its twin is Vaevictis
Asmadi, the Dire, also in the Lab.
- **Same footing as Vaevictis:** free copies only. Either deck can be sleeved without taking
  a card from another deck.
- **The upgrades other decks hold** are listed under Grounding.

## The engine

**Commander (verified):** Tom, Bert, and William — {3}{B}{G}, Legendary Creature. "{1},
Sacrifice another creature: Draw cards equal to the sacrificed creature's power, then
discard a card. When Tom, Bert, and William die, if they were a creature, return them to
the battlefield. They're an artifact. (They're no longer a creature.)"
- When they die, they come straight back as an artifact. The outlet keeps working, and
  creature removal can no longer touch them.

**The returner (verified):** Avacyn, Angel of Horror — {5}{B}{B}{B}. "Flying, deathtouch.
Whenever Avacyn or another nontoken creature you control dies, return that card to the
battlefield under your control at the beginning of the next end step."
- Sacrifice a big creature to the commander: draw cards equal to its power, and it's back at
  end step, ready to be sacrificed again next turn.

**Why this seat was tried.** A scan of every owned legendary creature with black in its
identity ranked Tom, Bert, and William first on its own text as an Avacyn partner: a
{1} outlet with no timing limit, and a payoff that scales with power. In the command zone
the engine is there every game.

## How it plays: three packages

### 1. Big bodies, big draws
- **The bodies:**

  | Creature | Power | Note |
  |---|---|---|
  | Ghalta, Primal Hunger | 12 | costs {X} less for your creatures' total power |
  | Gigantic Big Bear | 10 | hexproof, haste, can't be countered |
  | Yargle, Glutton of Urborg | 9 | {4}{B}, vanilla |
  | Saber-Tooth Moose-Lion | 7 | forestcycling {2} when you need a land |
  | Carnage Tyrant | 7 | |

- Goreclaw cuts {2} off every creature spell with power 4 or more.
- Mazirek puts a counter on every creature you control whenever anyone sacrifices
  another permanent, so every sacrifice draws more.
- **The discard** is a feature: bin a fatty you can't cast yet, then bring it back with
  Evil Reawakened, Junji's death mode or Sepulchral Primordial (from opponents' graveyards).

### 2. What dies comes back
The same aristocrats core as the Vaevictis twin:
- **Free outlets:** Carrion Feeder, Woe Strider, Yahenni. Also Unrooted Ancestor, Deadly
  Dispute and Phyrexian Vault.
- **Enter triggers that repeat on every return:** Gray Merchant, Archon of Cruelty,
  Fleshbag Marauder, God-Eternal Bontu, Grave Titan and Sepulchral Primordial.
- **Bone Shredder:** removal every turn through unpaid echo.
- **Twilight Diviner** copies one returning creature a turn.
- **Ayara drains each opponent for 1** whenever a black creature enters, so every return of
  a black creature drains.
- **Part in Friendship:** when a nontoken creature dies, it reveals cards until a creature and
  puts it onto the battlefield if its mana value is no more than your land count.

### 3. The drain finish
- Gray Merchant, Massacre Girl and Ayara drain on every loop.
- **Archfiend of Despair** makes each opponent lose again, at each end step, the life they
  lost that turn.
- **Archfiend of Depravity** makes each opponent sacrifice all but two creatures at their
  end step.

### One-sided wipes
Villainous Wrath and Deadly Tempest destroy, so with Avacyn out only your nontoken creatures
come back.

## Rules that decide games (CR retrieved 2026-10-16)
- **"Dies" means put into a graveyard from the battlefield (CR 700.4).** Sacrifice a target in
  response to exile and it comes back.
  - Woe Strider, Yahenni, Unrooted Ancestor and the commander sacrifice only ANOTHER
    creature. To save the outlet itself, use Carrion Feeder, Deadly Dispute or
    Phyrexian Vault.
- **A card that changes zones is a new object (CR 400.7).** Graveyard exile before the end
  step means it never comes back.
- **A creature that dies during an end step** returns at the next turn's end step (CR 513.2).
- **Order your own simultaneous triggers (CR 603.3b).**

## Piloting
- **Early:** ramp, then a free outlet and a value creature. The deck is an aristocrats
  deck before Avacyn arrives.
- **Mid-game:** land a big body and sacrifice it to the commander at the end of an
  opponent's turn. Draw, discard the card you can least use, and untap to cast it all.
- **With Avacyn out:** sacrifice each big body once per turn, since it returns at every end
  step. Mind your hand size: the commander can draw 12 at once, and the discard is to 7 at
  your cleanup.

## Mulligan
- **Keep:** 3-4 lands with both colours plus a ramp piece, or 2 lands with two ramp pieces.
- **A hand of fatties and no ramp is a mulligan.** Ghalta needs a board.

## Weaknesses to respect
- **Graveyard and exile hate:** Bojuka Bog, Rest in Peace, Swords to Plowshares.
- **Top-heavy:** 17 cards cost 5 or more. Ramp and Goreclaw carry it.

## Grounding
- **Field:** Tom, Bert, and William, 1,886 EDHREC decks (snapshot 2026-10-17). Ghalta, Primal
  Hunger is in 66% of them.
- **Upgrades held by other decks:** Psychosis Crawler (63%, in Kami), Woodland Cemetery,
  Llanowar Wastes, Assassin's Trophy, Twilight Mire, Deathcap Glade and Culling Ritual
  (all in Dina), Selvala (Beorn), Sakura-Tribe Elder (Dina) and Birds (Ur-Dragon).
  - Psychosis Crawler would be the finisher: each opponent loses 1 for every card you draw,
    and a sacrificed Ghalta draws 12.
- **No tutor finds Avacyn.** The three black tutors the player owns are all in sleeved decks:
  Grim Tutor (Ur-Dragon), Diabolic Tutor (Y'shtola), Final Parting (Bartolomé). In 4,000
  goldfish games she was cast by turn 10 in only 3%. The commander's draws dig for her in
  real play, which the goldfish doesn't model, but the deck has to win as an aristocrats
  deck first.
- **Against Vaevictis on the same 4,000 games,** the commander is cast by turn 6 in 56% (56%
  against 35%) and by turn 8 in 77% (against 62%).
- **Orcish Bowmasters is left out** while the player re-reviews it.
- **Verified text:** every card was read from Scryfall's cache or `carddb.py --verify` on
  2026-10-16/17. Yargle, Glutton of Urborg has no rules text: it's a vanilla 9/3.

## Protected engine (don't cut)
- Avacyn, Angel of Horror
- Carrion Feeder
- Woe Strider
- Yahenni, Undying Partisan
- Ghalta, Primal Hunger
- Gigantic Big Bear
- Yargle, Glutton of Urborg
- Gray Merchant of Asphodel
- Archon of Cruelty
- Fleshbag Marauder
- Bone Shredder
- God-Eternal Bontu
- Grave Titan
- Sepulchral Primordial
- Junji, the Midnight Sky
- Twilight Diviner
- Mazirek, Kraul Death Priest
- Part in Friendship
- Archfiend of Despair
