# READ THIS FIRST — the verdict, before the game plan

**This deck exists as evidence, not as a recommendation.** You asked (2026-08-23) whether
the Ur-Dragon should become Kaalia of the Vast. The honest answer measured across the whole
collection is **not yet — and not for the reason you expected.**

Kaalia fixes the two things you *feel* every game and makes the two things you *don't see*
worse. The numbers, all from this repo's own tools on the committed snapshot:

| | the-ur-dragon (today) | this deck |
|---|---|---|
| **commander on the battlefield** | **36.1%** of games | **97.8%** |
| cards risky to cast on curve | 52 of 64 | **40** |
| colours below Karsten's ~23 target | 5 of 5 | 3 of 3, but far closer (W 19 · B 17 · R 21) |
| field top-25 the deck actually runs | **20/25** | 12/25 |
| kill rate, no disruption | **78.1%** | 68.5% |
| kill rate, one board wipe | **11.9%** | 4.1% |
| bracket | **3 Upgraded** | 2 Core |

Read that first row twice. **You have been playing a deck whose engine only turns on in
about a third of games.** The Ur-Dragon costs {4}{W}{U}{B}{R}{G} and lands by turn 10 in
36.7% of 5,000 simulated games. Everything the deck is *named* after — draw a card per
attacking Dragon, then free-drop a permanent — is switched off in the other 63%. Eminence
still works from the command zone, so the deck is not broken, but the *fun part* is a coin
flip you lose twice out of three. Kaalia costs four mana and shows up 97.8% of the time.
That is almost certainly what "I'm not a big fan of it" actually is.

## Why the answer is still "not yet"

**The pool has no top end.** Kaalia's trigger converts a card in hand into a free attacker,
so its value is the mana you *didn't* pay. Every Angel, Demon and Dragon you own that fits
Mardu, by mana value:

```
MV 2  #                     MV 5  ####################   (20)
MV 3  #                     MV 6  #######                 (7)
MV 4  #################(17) MV 7  ####                    (4)
                            MV 8+ (none)
```

**Zero cards above mana value 7 in the entire 50-card pool.** 37 of 50 sit at MV 4–5, where
cheating saves four or five mana — a tempo swing, not a game. The cards Kaalia decks are
built to cheat are the ones you don't own: Gisela 79% of the field, Aurelia 73%,
Rune-Scarred Demon 71%, Avacyn 67%, Liesa 60%, Master of Cruelties 59%. You own **none** of
the fifteen highest-inclusion non-land cards you're missing.

Graded against verified oracle text rather than field %, the 50 break down as
**5 genuine bombs, 16 solid, 21 filler, 8 that should not be in the deck.** A real Kaalia
list runs 25–33 Angels/Demons/Dragons. Getting to 30 means playing nine cards from the
filler tier.

**Three cards in the pool are actively worse than they look**, and only reading the text
catches it:

- **Hellkite Courser** — its ETB returns a commander *from the command zone*. Kaalia has to
  be on the battlefield attacking for her trigger to happen at all, so cheating in the
  Courser finds an empty command zone and does nothing. Cast it, never cheat it.
- **Guardian Scalelord, Rakshasa Debaser, Smaug the Magnificent, Decadent Dragon,
  Desert Were-Worm** — all "whenever this attacks" cards. A creature Kaalia puts onto the
  battlefield attacking was never *declared* as an attacker, so those triggers never fire.
  Their whole card goes blank on the turn they arrive. (This ruling is already ratified in
  the Ur-Dragon notes, 2026-08-11.)
- **Smaug, the Great Calamity // Spew Flame** — using the Adventure half exiles the card.
  Kaalia only cheats from *hand*, so the removal mode permanently removes it from the pool.

**The mana is genuinely better, but not as much as it first looked.** A flag-based count
said all three colours clear the Karsten target once "any colour" lands are counted. The
verbatim text (`data/reference/kaalia-lands-verified-2026-08-23.txt`) says otherwise:
Avengers Tower is Hero-only, Villainous Hideout is Villain-only, Castle Doom is
artifact-only, Jasmine Dragon Tea Shop is Ally-only. In a Kaalia deck all four are
colourless lands. The real numbers are W 19 · B 17 · R 21 against a ~23 target — better
than five-colour by a mile, still short. And it costs tempo: 12 of these 37 lands enter
tapped, against 3 of the Ur-Dragon's 36.

**The wipe problem does not go away — it gets worse.** The largest single number in this
whole analysis is the Ur-Dragon's collapse from a 78.5% kill rate to 12.8% against one
modeled board wipe. That is what a 36-creature deck with zero recursion does. Kaalia is
*more* exposed, not less: she is a 2/2 the wipe also kills, and this build measures 4.1%.

## What would actually make this deck good

Six cards. The optimizer wrote them to `kaalia-of-the-vast.buylist.csv` on its own, each
replacing a 0%-field card already in the 99:

| buy | field | replaces |
|---|---|---|
| Gisela, Blade of Goldnight | 79% | Serra Paragon |
| Aurelia, the Warleader | 73% | Sustainer of the Realm |
| Rune-Scarred Demon | 71% | Tragedy Feaster |
| Avacyn, Angel of Hope | 67% | Vanguard Seraph |
| Liesa, Forgotten Archangel | 60% | Voice of Grace |
| Master of Cruelties | 59% | Voice of Truth |

No prices — the private priced `collection.csv` isn't in this clone, so anything quoted
would be invented. Six cards is a short list for turning a Bracket 2 pile into a real deck,
and it is the *only* path: the optimizer's verdict on the owned pool is verbatim
**"this deck can't improve from your collection: buy the gaps."**

**Mardu is also the only three-colour shard that solves the wipe problem**, which is worth
more than the field percentages suggest. Of the repo's 19 curated resilience staples, 15
are Mardu-legal (7 protection, 8 recursion). Temur is 7 with **zero** recursion; Jund is 7
with two. Karmic Guide, Serra Paragon, Haunted Crossroads and Along the Crooked Way are all
free right now — and the first two are Angels, so they are cheat targets *and* recursion.

## If you sleeve this

**This deck and the Ur-Dragon cannot both exist.** It borrows 35 cards from it and
`deck_conflicts.py` reports 26 shortfalls. Pull one to build the other.

**Game plan.** Ramp on two and three, Kaalia on four, protect her, swing on five. She does
nothing the turn she lands, so hold the removal that keeps her alive rather than trading it
early. Every cheated body arrives tapped and attacking: pick the opponent who can't block
fliers, not the one at the lowest life.

**Mulligan for** two lands that make two of W/B/R plus a rock, or Kaalia plus fixing. A hand
with three cheat targets and no way to cast her is a mulligan — the trigger is the deck.

**Sequencing.** Lathliss before the other Dragons: every nontoken Dragon Kaalia cheats in
afterwards makes a 5/5. Dragon Tempest gives every cheated flier haste, which matters far
more here than its 35% field number suggests. Hellkite Tyrant is the one cheat target whose
trigger survives arrival — it keys on *combat damage*, not on attacking.

**Never cheat**: Hellkite Courser (cast it), Guardian Scalelord, Rakshasa Debaser,
Decadent Dragon, Desert Were-Worm, Smaug the Magnificent. Their triggers do not fire.

## Provenance

Every card in the 99 is owned; nothing was invented. All 50 Mardu Angels/Demons/Dragons and
43 candidate lands were verified verbatim against Scryfall on the GitHub runner, 2026-08-23
(`kaalia-verified-2026-08-23.txt`, `kaalia-lands-verified-2026-08-23.txt`, 109 cards, 0
UNVERIFIED). Field data: EDHREC snapshot of 38,818 Kaalia decks. Built with
`auto_build.py` → `deck_sections.py` → `optimize.py --apply`, then three land swaps made on
the verified text (Villainous Hideout → Sunbillow Verge, Temple of the False God →
Foreboding Ruins, Rocky Roads → Crossroads Village), which cut risky-to-cast from 45 to 40.
100 cards, singleton clean, sections clean, all inside {W,B,R}.
