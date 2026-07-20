# Commander (EDH) Deckbuilding Principles

Format basics: 100-card singleton, one legendary commander, deck's color identity = the
commander's. 40 starting life, command zone, commander damage (21 from one commander).
These are the working ratios and roles a champion tunes toward. They're guidelines, not
laws — the archetype and commander bend them.

## The template (a solid baseline for a ~99-card deck)

| Role | Count | Notes |
|------|-------|-------|
| Lands | 36–38 | 37 is the default. Go 38 for a top-heavy curve, 35–36 only with lots of cheap ramp / low curve. |
| Ramp (mana rocks, dorks, ramp spells) | 10–12 | Includes Sol Ring, signets, Cultivate, dorks. More for higher curves. |
| Card advantage / draw engines | 10–12 | Repeatable draw beats one-shot cantrips. Aim for several engines. |
| Targeted removal | 8–10 | Answers to a problem permanent (creature/artifact/enchantment/planeswalker). |
| Board wipes | 3–5 | At least a couple. Mind exile-vs-destroy with your own synergies. |
| Synergy / payoff / win-cons | ~30 | The actual deck — the engine and finishers. |

These overlap (a card can be ramp *and* a body). The point is to hit **every** role. A deck
missing removal or draw feels bad no matter how strong its theme.

## Curve

- Most nonland cards should cost 1–4. A healthy curve peaks around 2–3 MV.
- Count your 5+ MV cards; if you have a dozen bombs, add ramp and a land, or cut some.
- "8x8 theory" (a beginner-friendly frame): pick ~8 roles, run ~8 cards each. Useful for
  making sure no role is starved.
- Ramp is what lets a top-heavy deck function; draw is what keeps a low deck from running out.

## Manabase (the part people skip and then lose to)

1. Count total **colored pips** in the mana costs of all nonland cards, per color.
2. Count **double-pip** cards (e.g. `{B}{B}`) — these demand many sources of that color early.
3. Provide sources roughly proportional to demand. A rough target: a color you're double-pipped
   in wants ~14+ sources; a light splash can live on ~8–10.
4. Fixing: Command Tower, Exotic Orchard, Path of Ancestry, signets/Talismans, dual/tri lands,
   fetch-to-basics (Fabled Passage, Terramorphic, Ash Barrens), Cultivate/Farseek effects.
5. Utility lands (High Market, Bojuka Bog, Rogue's Passage) earn slots but each one that makes
   colorless-only mana is a small tax on your colored consistency — don't overload.
6. `deck_stats.py` prints pip demand and source counts. Use it; don't eyeball.

## Roles, defined

- **Ramp**: accelerates or fixes mana (rocks, dorks, land-ramp spells, Treasure makers).
- **Card advantage**: net-positive card generation, ideally repeatable (Rhystic Study, Mystic
  Remora, Tome of Legends, Skullclamp, "draw a card" attack/ETB triggers).
- **Targeted removal**: Swords, Path, Beast Within, Chaos Warp, Generous Gift, counterspells.
- **Board wipe**: Blasphemous Act, Toxic Deluge, Cleansing Nova, Austere Command, Time Wipe.
- **Protection**: Heroic Intervention, Lightning Greaves, Selfless Spirit, counterspells.
- **Payoff / win-con**: the cards that actually end the game. Every deck needs a clear one.

## Power level & the Commander Brackets

WotC's official bracket system (2025) — match the deck to the table:
- **Bracket 1 – Exhibition:** ultra-casual, precon-below, no fast combos.
- **Bracket 2 – Core:** upgraded precon level. Most kitchen-table pods live here.
- **Bracket 3 – Upgraded:** tuned, efficient, some strong cards; still not cEDH.
- **Bracket 4 – Optimized:** high power, best cards, fast; no rules restrictions.
- **Bracket 5 – cEDH:** competitive metagame, turbo combos, fast mana, the Game Changers list.
Ask the player which pod the deck is for; build to that bracket. Don't drop a Bracket-4 combo
into a Bracket-2 table without flagging it.

## Reading a collection for archetypes

To answer "what can I build?", count support depth per archetype and rank by *actual* numbers:
- **Tribal**: count bodies of the type AND the tribal payoffs (lords, "whenever a X enters").
  A tribe needs both. 10 dragons is not a dragon deck.
- **Aristocrats**: count sac outlets + death payoffs (Blood Artist effects) + fodder/tokens.
  All three or it stalls.
- **Equipment/Voltron**: count equipment + equip-cost reducers/carriers + evasion + protection.
- **Spellslinger**: count instants/sorceries + payoffs (Archmage Emeritus, magecraft, Guttersnipe).
- **Control**: count counterspells + removal + card advantage + a slow win.
- **+1/+1 counters, tokens, reanimator, lifegain, Voltron, group hug, stax** — same method:
  enumerate the engine pieces and count them before you commit.
Report the top few honestly, including what each is *missing*, and note archetypes that are
NOT supported without buying.
