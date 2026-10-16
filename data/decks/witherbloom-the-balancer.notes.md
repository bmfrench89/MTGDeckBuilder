# The Plan
A **theory deck** (in the Lab), built 2026-10-16 when the player asked for a Bracket 4
combo deck besides Bartolomé. It is "theory based, so any card, even in decks, is free
reign". The list counts every card the player owns, sleeved or not. It claims no
copies: the Lab tab shows where each card lives today.

**Commander (verified):** Witherbloom, the Balancer — {6}{B}{G}, Legendary Creature —
Elder Dragon. *"Affinity for creatures. Flying, deathtouch. Instant and sorcery spells
you cast have affinity for creatures."*

Witherbloom makes every instant and sorcery cost {1} less per creature you control.
With a wide board the big sorceries cost only their coloured pips, and one of them
loops forever.

# How it wins: four combos, all confirmed by Commander Spellbook
1. **Witherbloom + Sprout Swarm.** Sprout Swarm ({1}{G} instant): convoke, buyback {3},
   create a 1/1 Saproling.
   - With four creatures out, the buyback cast costs {G}. Convoke pays it by tapping the
     Saproling the last cast made, and buyback returns the card to your hand.
   - That's infinite Saprolings, cast triggers and storm, at instant speed. Do it at the
     end of the last opponent's turn.
   - Ways to finish:
     - **Mirkwood Bats**: "Whenever you create or sacrifice a token, each opponent loses
       1 life." No sacrifice outlet needed.
     - **Zulaport Cutthroat or Blood Artist** plus a free sacrifice outlet: Viscera Seer,
       Carrion Feeder, Woe Strider, Yahenni or Umbral Collar Zealot.
     - **Exsanguinate**: X is generic mana, so affinity pays it. With 30 Saprolings, X=30
       costs {B}{B}. Stensian Sanguinist's prepared copy works the same way.
     - **Inside Information**, X paid by affinity: exile an opponent's whole library.
     - **Damnable Pact** aimed at an opponent: they draw X and lose X.
   - Chatterfang doubles every token with a Squirrel, so the Bats drain twice per cast.
     Sedgemoor Witch's magecraft adds an untapped Pest per cast, and those can attack.
2. **The Master of Lake-town + Bloodchief Ascension.** The Master: "Whenever a player
   loses life, that player mills that many cards."
   - Once the Ascension has three quest counters, every card put into an opponent's
     graveyard costs them 2 life.
   - That life loss mills them, and the milled cards cost more life. It ends when their
     life or their library runs out, usually life first: 20 milled cards are 40 life.
     An empty library loses at their next draw.
   - A quest counter goes on at any end step where an opponent lost 2+ life, so the
     drains charge it.
3. **Pox Plague + Archfiend of Despair.** Pox Plague: each player loses half their life,
   discards half their hand and sacrifices half their permanents. Archfiend: "At the
   beginning of each end step, each opponent loses life equal to the life that player
   lost this turn." Opponents lose half, rounded down, then the same amount again at
   the end step.
   - At an even life total that's all of it.
   - At an odd total it leaves them at 1 (31 → 16 → 1), and any other point they lose
     that turn finishes it. Zulaport Cutthroat does it when Pox makes you sacrifice
     creatures.
   - You lose half your life too.
4. **Grievous Wound + Archfiend of Despair.** Grievous Wound (on a player): "Whenever
   enchanted player is dealt damage, they lose half their life, rounded up." One point
   of damage takes half their life, and the end step repeats it.

**Tutors:** Diabolic Tutor, Grim Tutor, Final Parting (one card to hand, one to the
graveyard; pair it with Rise of the Dark Realms).

# The discount engine
Affinity reduces only generic mana; coloured pips stay. With 7 creatures out:
- **In Garruk's Wake** ({7}{B}{B}, a one-sided wipe), **Rise of the Dark Realms**
  ({7}{B}{B}: every creature card from every graveyard onto your battlefield) and
  **Army of the Damned** ({5}{B}{B}{B}) cost their pips.
- **Up the Beanstalk** still draws off each one, because a discount doesn't change a
  spell's mana value.
- **Shamanic Revelation**, **For the Common Good**, **Pest Infestation** and
  **Animist's Awakening** scale with X or the board.

# Mulligan for
- 2-4 lands plus a mana dork: Llanowar Elves, Elvish Mystic, Fyndhorn Elves, Birds of
  Paradise, Noxious Newt or Twitching Doll.
- Witherbloom costs {1} less for each creature you control, so dorks and token makers
  bring it down early. The goldfish can't model that discount, so its commander timing
  is too slow.

# Weaknesses to respect
- **Graveyard and token hate:** the loop is on the battlefield; Bojuka Bog is ours.
- **Witherbloom is the engine.** Protect it with Swiftfoot Boots, Lightning Greaves,
  Heroic Intervention and Collective Resistance. If it dies, the other three combos
  don't need it.
- **Symmetric cards:** Pox Plague hurts you too. Cast it only with Archfiend out, or
  when you're far ahead.
- **Bracket 4.** This list has four two-card combos and is built to win with them.

# What it would take to build for real (the Lab tab has the full list)
As of 2026-10-16:
- 44 of its cards are in other decks today.
- 42 are spare copies.
- The player owns every card.

Most of the 44 come from **Dina, Essence Brewer**: 27 cards, her sacrifice-and-drain
core and her black-green lands. Y'shtola gives up Exsanguinate, Bloodchief Ascension
and Diabolic Tutor. Other single key cards:
- Grim Tutor (the Ur-Dragon);
- Final Parting (Bartolomé);
- Tergrid (Tinybones);
- Grievous Wound (Eriette);
- Rise of the Dark Realms (the Ur-Sphinx).

# Grounding note
- **Field:** 17,955 EDHREC decks. All 19 of the field's top-25 cards that the player
  owns are in the list. The six not owned head the buylist.
- **Commander Spellbook:** 4 combos present (deck run 2026-10-16).
- **Bracket:** power.py reads 3 from Game Changers alone (Tergrid). Its curated combo
  list doesn't include these combos. Four two-card combos make it Bracket 4 by WotC's
  definition, and the header says 4.
- **Deck UAT** (2,000 games): every gate passes.
  - Keepable 80%, screwed 16%.
  - 2+ engine cards cast by turn 6 in 68% of games.
- **Verified text:** every combo piece and finisher was checked with `carddb.py --verify`
  on 2026-10-16.

## Protected engine (the loop, the payoffs, the second and third combos, the tutors)
- Sprout Swarm
- Mirkwood Bats
- Zulaport Cutthroat
- Blood Artist
- Viscera Seer
- Carrion Feeder
- Exsanguinate
- Stensian Sanguinist
- Chatterfang, Squirrel General
- The Master of Lake-town
- Bloodchief Ascension
- Archfiend of Despair
- Pox Plague
- Grievous Wound
- Diabolic Tutor
- Grim Tutor
- Final Parting
- Tergrid, God of Fright
