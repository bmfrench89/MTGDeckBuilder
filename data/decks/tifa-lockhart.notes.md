# Tifa Lockhart — Doubling Down

Mono-green landfall **voltron**. You win with commander damage: 21 trample damage,
usually in two swings, sometimes one.

## The one idea that runs this deck

Tifa's landfall ability **doubles her power** — it does not add to it. Doubling is
multiplicative, so every point of *permanent* base power you give her first is worth
2x, 4x, or 8x by the time you attack.

    Tifa alone, one land drop:              1 -> 2      (embarrassing)
    Tifa + Hero's Blade (+3/+3):            4 -> 8
    Tifa + Hero's Blade + 4 counters:       8 -> 16 -> 32 with a second land drop

So the deck is not really "make lots of land drops." It is **raise the floor, then
double it.** Every equipment slot and every +1/+1 counter is a multiplier, not an add.

## Necklace of Girion is the engine

`{2}{G}` Legendary Artifact — *"Whenever you cast a green spell and whenever a Forest
you control enters, put a +1/+1 counter on target creature you control. {T}: Add {G}."*

Three reasons it is the best non-commander card in the deck:

1. **It fixes Tifa's actual problem.** Her doubling resets every turn and her base power
   is 1. Counters are permanent, so each turn's doubling starts from a bigger number.
2. **The triggers stack in your favour.** When a Forest enters, Necklace's trigger and
   Tifa's landfall trigger go on the stack at the same time and **you choose the order**.
   Put the landfall (doubling) trigger on the stack FIRST and the Necklace trigger on top
   — the counter then resolves first and gets doubled. Never let them resolve the other
   way round; it costs you exactly half your damage.
3. **It is never a dead draw.** It taps for `{G}`, so on an empty board it is a mana rock
   that ramps toward the turn you actually kill someone.

The "cast a green spell" half is the real workhorse — roughly 55 of the 64 nonland cards
are green, so it ticks up most turns even when you miss a land drop. The Forest half is
gravy, and it is why the manabase is 28 basic Forests rather than a pile of utility lands.

## Piloting

- **Mulligan for:** two lands + a mana creature, or any hand with a cheap equipment.
  You do *not* need Tifa in the opener — she is a 2-drop and lands by turn 2-3 in ~86% of games.
- **Do not overextend her.** She is a 1/2. Hold Champion's Helm (hexproof) or a protection
  spell before you commit a big equipment suite. Losing Tifa loses every counter on her.
- **Crop Rotation is a combat trick.** It is an instant that puts a land onto the
  battlefield — cast it after blockers are declared to double her power mid-combat.
  Fetching a Forest also triggers Necklace first. This is the deck's best surprise kill.
- **Fetch effects are two triggers, not one.** Terramorphic Expanse enters (landfall #1),
  then fetches a Forest (landfall #2 + a Necklace counter). Myriad Landscape is three.
- **Trample is the whole point.** Do not chase unblockable effects — a doubled Tifa runs
  over any chump block. Push power, not evasion.

## Protected cards (do not let the optimizer cut these)

Tifa Lockhart, Necklace of Girion, Hero's Blade, Hero's Heirloom, Champion's Helm,
Adventuring Gear, Explorer's Scope, Crop Rotation, Horn of Greed, Baloth Woodcrasher,
Rancor, Terrain Generator, Wood Elves, Saber-Tooth Moose-Lion, Balamb T-Rexaur.

## Known weaknesses (honest)

- **No extra-land-drop effects.** The collection contains zero Azusa / Exploration /
  Burgeoning / Wayward Swordtooth / Ancient Greenwarden. That caps landfall at one
  trigger per turn outside of fetch effects, and it is the single biggest upgrade path.
- **No +1/+1 counter payoffs.** Zero Hardened Scales / Branching Evolution / Doubling
  Season / The Ozolith owned, so Necklace's counters are linear rather than exponential.
- **One haste enabler and no protection from wraths.** Tifa is a glass cannon.
- **Removal is green removal** — it answers artifacts, enchantments and fliers, not the
  creature that is actually killing you.
