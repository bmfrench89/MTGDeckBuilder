# The Plan
A **theory copy** of the player's real Tinybones deck (`tinybones-bauble-burglar`,
Bracket 3), built 2026-10-16. Same engine, plus the two two-card combos the combo comb
found in black, plus three tutors. That pushes it to Bracket 4. It claims no copies.
The real deck's notes hold the full plan: the stash, the punishers, the creative lines.

**Commander (verified):** Tinybones, Bauble Burglar — {1}{B}, Legendary Creature —
Skeleton Rogue, 1/3. *"Whenever an opponent discards a card, exile it from their
graveyard with a stash counter on it. During your turn, you may play cards you don't
own with stash counters on them from exile, and mana of any type can be spent to cast
those spells. {3}{B}, {T}: Each opponent discards a card. Activate only as a sorcery."*

# What changed from the real deck
- **In:** The Master of Lake-town, Bloodchief Ascension, Pox Plague, Archfiend of
  Despair, Diabolic Tutor, Grim Tutor, Final Parting.
- **Out:** Stony-Voiced Goblins, Rank Rat, Night's Whisper, Village Rites, Mind Rake,
  Let's Play a Game, Liliana's Specter.

# The two combos (Commander Spellbook confirms both)
1. **The Master of Lake-town + Bloodchief Ascension.**
   - The Master: *"Whenever a player loses life, that player mills that many cards."*
   - The Ascension takes a quest counter at each end step where an opponent lost 2 or
     more life; the punishers do that every turn.
   - At three counters, every card put into an opponent's graveyard costs them 2 life.
     Each loss mills them, and each milled card costs 2 more. It ends when their life
     or their library runs out, usually life first: 20 milled cards are 40 life.
   - A discarded card passes through the graveyard before Tinybones exiles it, so every
     discard counts for the Ascension.
2. **Pox Plague + Archfiend of Despair.**
   - Pox Plague: each player loses half their life, discards half their hand and
     sacrifices half their permanents.
   - Archfiend: at each end step, each opponent loses the life they lost this turn.
     They lose half, rounded down, then the same amount again: all of an even life
     total, or down to 1 from an odd one (31 → 16 → 1).
   - Any other point lost that turn finishes an odd total. Every punisher counts,
     including Megrim, Liliana's Caress and Pox's own discards.
   - Every opponent discards half their hand into your stash. You lose half your life
     and half your permanents too, so cast it with Archfiend out.

**Tutors:** Diabolic Tutor, Grim Tutor, Final Parting. Final Parting puts one card in
your hand and one in the graveyard.

# Grounding note
- Every card listed above was verified with `carddb.py --verify` on 2026-10-16.
- The real deck stays Bracket 3 and untouched. This copy is in the Lab so the two can be
  compared side by side.
- Deck UAT and combos for this copy are on its page.

## Protected engine (the real deck's engine, plus the combos and tutors)
- Waste Not
- Megrim
- Liliana's Caress
- Geth's Grimoire
- Tergrid, God of Fright
- Gonti, Night Minister
- Tinybones, Pocket Nuisance
- Bandit's Talent
- The Raven Man
- Painful Quandary
- Dark Deal
- Syphon Mind
- The Master of Lake-town
- Bloodchief Ascension
- Pox Plague
- Archfiend of Despair
- Diabolic Tutor
- Grim Tutor
- Final Parting
