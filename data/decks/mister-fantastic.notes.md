# The Plan
A **theory deck** (in the Lab), built 2026-10-16 from the combo comb: "theory based, so
any card, even in decks, is free reign". It counts every card the player owns and
claims no copies.

**Commander (verified):** Mister Fantastic — {2}{U}, Legendary Creature — Human Scientist
Hero, 2/4. *"Reach, vigilance. At the beginning of combat on your turn, if you've cast a
noncreature spell this turn, draw a card. {R}{G}{W}{U}, {T}: Copy target triggered
ability you control twice. You may choose new targets for the copies."*

The Fantastic Four's triggers feed each other. **Annie Joins Up** — *"If a triggered
ability of a legendary creature you control triggers, that ability triggers an
additional time"* — doubles every one of them, since all four are legendary. Cheap
noncreature spells keep the cards flowing in between.

# The Four (all verified)
- **Mister Fantastic, Reed Richards:** whenever one or more tokens you control enter,
  you may draw a card.
- **Invisible Woman, Sue Storm:** whenever you put +1/+1 counters on one or more OTHER
  Heroes, you may create a 0/4 Wall token with defender.
- **The Thing, Ben Grimm:** whenever one or more Heroes you control deal damage to a
  player, put two +1/+1 counters on The Thing.
- **Human Torch, Johnny Storm:** whenever you draw a card, if you control another Hero,
  he deals 1 damage to target opponent.

# How it wins: the loops (Commander Spellbook confirms each)
1. **The Four together:**
   1. A draw makes Torch deal 1.
   2. A Hero dealt damage, so The Thing gets two counters.
   3. Counters on another Hero, so Sue makes a Wall.
   4. A token entered, so Reed draws, and the loop goes again.

   Reed's draw is optional, so you stop when you choose. Each pass is 1 damage (2 with
   Annie), and The Thing ends up enormous, with trample.
2. **Reed + Sue + a counter-on-draw Hero:** Iron Man, Armored Avenger (*"Whenever you
   draw a card, put a +1/+1 counter on target creature"*), Shang-Chi and the Ten Rings,
   or The Astonishing Ant-Man. Draw, counter, Wall, draw: an infinite draw loop, with
   Torch turning every card into damage.
3. **Pensive Professor + Iron Man:** each draw puts a counter on the Professor, which
   draws again. Target another creature to stop.
4. **Mister Fantastic + Unstoppable Plan:** at your end step the Plan untaps all your
   nonland permanents.
   - Tap your rocks for mana, then pay {R}{G}{W}{U} and tap Mister Fantastic to copy the
     Plan's trigger twice. Each copy untaps everything again.
   - It nets mana only if your nonland permanents make MORE than {R}{G}{W}{U} across two
     untaps. Exactly that breaks even. Three any-colour rocks (Chromatic Lantern, Arcane
     Signet, Commander's Sphere) make 6 across the two untaps for every 4 an activation
     costs, so 2 are kept each round: infinite mana and untaps.
   - Mana stays in your pool for the whole end step (CR 106.4, 500.5).
   - **The finish:** cast Brainstorm while Mister Fantastic is untapped, putting three
     Human Torch triggers on the stack. Alternate his copies between the Plan's trigger
     (two more untaps) and a Torch trigger (two more pings): endless damage at instant
     speed.

**Not in this list: Niv-Mizzet, Visionary.** Spellbook lists Human Torch + Niv-Mizzet as
a combo, but here it's a trap.
- Niv draws one card per point of damage, so each point Torch deals costs you a card.
  Fiery Emancipation triples the draws along with the damage.
- The chain is mandatory and starts on ANY draw, your draw step included, once both are
  out with another Hero.
- It decks you before it deals 120 to a full table. It was cut on 2026-10-16 for
  Talisman of Creativity, another rock for the Plan.

**Multipliers:** Annie Joins Up (legendary triggers twice), Fiery Emancipation (triple
damage), and Mister Fantastic's own copy ability.

# Draw engines and tutors
- **Draw:** Valeria Richards (noncreature spells cost {1} less; the first one each turn
  draws), Whirlwind of Thought, The Vision, Rhystic Study, Mystic Remora, Consecrated
  Sphinx, King T'Challa. Each card drawn is a Human Torch ping.
- **Tutors:** Enlightened Tutor and Idyllic Tutor (Annie Joins Up, Fiery Emancipation,
  Whirlwind, Unstoppable Plan), Mystical Tutor.
- **Protection:** Clever Concealment (phase your board out), Heroic Intervention,
  Lightning Greaves, Swan Song, Force of Will, Counterspell, Arcane Denial, Mana Drain,
  An Offer You Can't Refuse.

# Mulligan for
- Lands in at least three colours plus a rock or dork: Sol Ring, Arcane Signet,
  Chromatic Lantern, Birds of Paradise, Farseek, Nature's Lore.
- One cheap noncreature spell turns on Mister Fantastic's combat draw.

# Weaknesses to respect
- **The loops take three or four pieces.** Tutors find the enchantments; the creatures
  come from card flow.
- **Never add Niv-Mizzet, Visionary** (see "Not in this list" above).
- **Enchantment removal** hits Annie, Fiery Emancipation, Whirlwind and Unstoppable Plan.
- **Wipes** kill the Four. Clever Concealment and Heroic Intervention answer them.

# Grounding note
- **Field:** Mister Fantastic, 2,124 EDHREC decks (snapshot 2026-10-16). It's a
  noncreature-spells deck with the Four. 20 of the Heroes the first draft picked from
  the commander's type line were 0% in the field; they were cut.
- **Verified text:** every combo piece was read with `carddb.py --verify` on
  2026-10-16. Commander Spellbook's combo count is on the deck page. Niv-Mizzet's combo
  left with Niv-Mizzet.
- **Deck UAT** (2,000 games): every gate passes. Keepable 81%, screwed 15%, engine
  online 75%, commander out by turn 4 in 71% of games.
- **Damage per card drawn with Human Torch out** (from the clip work, CR 603.2c and
  603.2d):

  | Out | Damage per card | Cards to deal 120 |
  |---|---|---|
  | Human Torch alone | 1 | 120 |
  | + Annie Joins Up | 2 | 60 |
  | + Fiery Emancipation | 3 | 42 |
  | + both | 6 | 21 |

  The Four loop's draws are optional, so you take only the cards you need.

## Protected engine (the Four, the doublers, the draw engine, the tutors)
- Mister Fantastic, Reed Richards
- The Thing, Ben Grimm
- Invisible Woman, Sue Storm
- Human Torch, Johnny Storm
- The Astonishing Ant-Man
- Iron Man, Armored Avenger
- Shang-Chi and the Ten Rings
- Pensive Professor
- Annie Joins Up
- Fiery Emancipation
- Unstoppable Plan
- Valeria Richards, Precocious
- Whirlwind of Thought
- Enlightened Tutor
- Idyllic Tutor
- Mystical Tutor
