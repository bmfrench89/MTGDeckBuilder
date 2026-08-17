# Tifa Lockhart — Doubling Down

Mono-green landfall **voltron**. You win with commander damage: 21 trample damage,
usually in two swings, sometimes one.

## The one idea that runs this deck

Tifa's landfall ability **doubles her power** — it does not add to it. Doubling is
multiplicative, so every point of *permanent* base power you give her first is worth
2x, 4x, or 8x by the time you attack.

    Tifa alone, one land drop:              1 -> 2      (embarrassing)
    Tifa + Hero's Blade (+3/+2):            4 -> 8
    Tifa + Hero's Blade + 4 counters:       8 -> 16 -> 32 with a second land drop

Scryfall's own reminder on the ability is the proof: it gives "+X/+0, where X is
Tifa Lockhart's power **when the landfall ability resolves**." Power is read on
resolution, which is exactly why the ordering below wins.

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

The "cast a green spell" half is the real workhorse — most of the nonland cards are green,
so it ticks up most turns even when you miss a land drop. The Forest half is gravy, and it
is why the manabase is 30 basic Forests rather than a pile of utility lands.

**What the field actually says (snapshot 2026-08-17, 291 cards):** Necklace of Girion sits
at **12% inclusion** — it is not a Tifa staple. Treat that as a prior, not a verdict: the
card released 2026-08-14, three days before this snapshot, so 12% is a recency artifact
rather than a rejection (card-review-method §3). The engine read above is the reason it is
in the deck. But be honest that the field's real priorities for Tifa are **land-to-battlefield
ramp and extra land drops** — Harrow 76%, Cultivate 72%, Azusa 71%, Entish Restoration 66% —
not counters. This deck owns almost none of that, which is the buylist's whole first tier.

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
- **Terrain Generator is a second land drop.** `{2}, {T}: put a BASIC land from hand onto
  the battlefield tapped` — verified as *not* using your land play for the turn. On a
  Forest that is a landfall trigger plus a Necklace counter, every turn, for mana.
- **Hero's Heirloom grants trample AND haste** while Tifa is legendary — it is the
  deck's second haste enabler, not just a stat stick.
- **Brass Knuckles is the kill.** Double strike once two Equipment are attached: a
  doubled, trampling Tifa hitting twice ends a player from a very long way back.
- **Trample is the whole point.** Do not chase unblockable effects — a doubled Tifa runs
  over any chump block. Push power, not evasion.

## Protected cards (do not let the optimizer cut these)

Tifa Lockhart, Necklace of Girion, Hero's Blade, Hero's Heirloom, Champion's Helm,
Brass Knuckles, Adventuring Gear, Explorer's Scope, Crop Rotation, Horn of Greed,
Baloth Woodcrasher, Rancor, Terrain Generator, Wood Elves.

## Cards that are NOT what they look like (verified 2026-08-17)

- **Saber-Tooth Moose-Lion and Balamb T-Rexaur have Forest*cycling*** — they search a
  Forest **to hand**, not onto the battlefield. They trigger neither Tifa's landfall nor
  the Necklace. Both were cut for exactly this reason; do not re-add them as "Forest
  fetchers". The `fetch:forest` flag in the attrs data does not distinguish
  to-hand from to-battlefield, and that is the trap.
- **Land Grant** is the same shape (Forest to hand). It stays only as a free land-drop
  enabler, not as a trigger.

## Known weaknesses (honest)

- **Almost no extra-land-drop effects.** Terrain Generator is the only one owned, and it
  costs `{2}` per activation. Zero Azusa / Exploration / Burgeoning / Wayward Swordtooth /
  Ancient Greenwarden. This is the single biggest upgrade path.
- **No +1/+1 counter payoffs.** Zero Hardened Scales / Branching Evolution / Doubling
  Season / The Ozolith owned, so Necklace's counters are linear rather than exponential.
- **Ramp runs long on purpose** — 19 against the voltron template's 9-13. Land-to-battlefield
  ramp is this deck's *payoff*, so `deck_stats`' "high" flag is expected here, not a defect.
  The proper fix is a `landfall` entry in `deckcore._ARCHETYPE_ROLE_RANGE`; that is
  proposed, not shipped, because widening a shared template to silence a warning about
  one deck needs ratifying first.
- **Removal is mostly green removal** — it answers artifacts, enchantments and fliers.
  **Beast Within** (53% field) is the exception and the reason it is here: it answers *any*
  permanent, which is the hole green normally cannot cover.

## Shared with other decks — by design, not an accident

Six cards here are also in other decks and carry the **⇄** badge in the decklist and a row
in the **Shared Across Decks** panel: **Swiftfoot Boots**, **Snakeskin Veil**, **Heroic
Intervention**, **Beast Within**, **Fabled Passage**, **Rogue's Passage**.

That is the intended behaviour, not a conflict to resolve (grounding rule #8 — mark, don't
block). Sharing is ON by default in the optimizer precisely because two decks legitimately
want the same card, and **you decide which one gets the physical copy at sleeving time**.
The shortfall is already on `data/wishlist.md` under "shared copies to buy"; nothing was
removed from Bruce Banner, Cloud, Cosmic Spider-Man or Ur-Dragon to build this list.

If you want a copy permanently reserved for one deck, **pin it** — 📌 on the card panel of
any deck page, or the **Pins** tab. A pinned card is skipped as an add candidate by every
other deck (`optimize`, `auto_build`, `edhrec`), while unpinned cards stay freely shared.
Nothing in this deck is pinned.

These three arrived as shared adds and fixed the deck's worst hole — it previously had
**no protection at all** for a 1/2 commander whose counters die with her:
Swiftfoot Boots (haste + hexproof), Snakeskin Veil (protection *and* a permanent counter
the doubling then multiplies), Heroic Intervention (saves the board from a wrath).
