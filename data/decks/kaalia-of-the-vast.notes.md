# READ THIS FIRST — the verdict, before the game plan

**This deck exists as evidence, not as a recommendation.** You asked (2026-08-23) whether
the Ur-Dragon should become Kaalia of the Vast. The honest answer, measured across the
whole collection, is **not yet — and not for the reason you expected.**

Kaalia fixes the two things you *feel* every game and makes the two things you *don't see*
worse. Every number below is from this repo's own tools on the committed snapshot:

| | the-ur-dragon (today) | this deck |
|---|---|---|
| **commander on the battlefield** | **36.1%** of games | **97.3%** |
| power score (the scorer's own axes) | 51.5 / 100 | **66.1 / 100** |
| cards risky to cast on curve | 52 of 64 | **42** |
| colours below Karsten's ~23 target | 5 of 5 | 3 of 3, but far closer (W 19 · B 17 · R 21) |
| field top-25 the deck actually runs | **20/25** | 12/25 |
| kill rate, no disruption | **78.5%** | 58.4% |
| kill rate, after one board wipe | **11.9%** | 4.1% |
| resilience | prot 2 · rec 0 | **prot 3 · rec 2** |
| bracket | **3 Upgraded** | 2 Core |

Read that first row twice. **You have been playing a deck whose engine turns on in about a
third of games.** The Ur-Dragon costs {4}{W}{U}{B}{R}{G} and reaches the battlefield in
36.7% of 5,000 simulated games, mean turn 8.30. Everything the deck is *named* after — draw
a card per attacking Dragon, then free-drop a permanent — is switched off in the other 63%.
Eminence still works from the command zone, so the deck is not broken, but the *fun part* is
a coin flip you lose twice out of three. Kaalia costs four mana and lands on turn 4 in 42%
of games and by turn 10 in 97%. That is almost certainly what "I'm not a big fan of it"
actually is.

## Why the answer is still "not yet"

**The pool has no top end.** Kaalia's trigger converts a card in hand into a free attacker,
so its value is the mana you *didn't* pay. Every Angel, Demon and Dragon you own that fits
Mardu, by mana value:

```
MV 2  #                     MV 5  ####################   (20)
MV 3  #                     MV 6  #######                 (7)
MV 4  #################(17) MV 7  ####                    (4)
                            MV 8+  (none)
```

**Zero cards above mana value 7 in the entire 50-card pool.** 37 of 50 sit at MV 4–5, where
cheating saves four or five mana — a tempo swing, not a game. The cards Kaalia decks are
built to cheat are the ones you don't own: Gisela 79% of the field, Aurelia 73%,
Rune-Scarred Demon 71%, Avacyn 67%, Liesa 60%, Master of Cruelties 59%. You own **none** of
the fifteen highest-inclusion non-land cards you're missing.

Graded against verified oracle text rather than field %, the 50 break down as
**5 genuine bombs, 16 solid, 21 filler, 8 that should not be in the deck.** A real Kaalia
list runs 25–33 Angels/Demons/Dragons. This build runs 31, of which **9 cost 6 or more** —
that took hand-tuning, because `auto_build`'s curve template took only 4 of the 10 free
MV6+ bodies on its own.

**Three cards are worse than they look**, and only reading the text catches it:

- **Hellkite Courser** — its ETB returns a commander *from the command zone*. Kaalia has to
  be on the battlefield attacking for her trigger to happen at all, so cheating in the
  Courser finds an empty command zone and does nothing. Cast it to rebuild after removal;
  never cheat it.
- **Guardian Scalelord, Rakshasa Debaser, Smaug the Magnificent, Decadent Dragon,
  Desert Were-Worm** — all "whenever this attacks" cards. A creature Kaalia puts onto the
  battlefield attacking was never *declared* as an attacker, so those triggers never fire.
  Their whole card goes blank on the turn they arrive. (Ratified in the Ur-Dragon notes,
  2026-08-11. The underlying CR rule could not be retrieved from this sandbox —
  wizards.com is PC-only — so treat the rule *number* as uncited and the ruling as this
  repo's own verified prior.)
- **Smaug, the Great Calamity // Spew Flame** — casting the Adventure half exiles the card.
  Kaalia only cheats from *hand*, so the removal mode permanently removes it from the pool.

**The mana is genuinely better, but not as much as it first looked.** A flag-based count
claimed all three colours clear once "any colour" lands are counted back in. The verbatim
text (`data/reference/kaalia-lands-verified-2026-08-23.txt`) says otherwise: Avengers Tower
is Hero-only, Villainous Hideout Villain-only, Castle Doom artifact-only, Jasmine Dragon
Tea Shop Ally-only. In a Kaalia deck all four are colourless lands. Real numbers:
W 19 · B 17 · R 21 against a ~23 target. Better than five-colour by a mile, still short.
And it costs tempo: 12 of these 37 lands enter tapped against the Ur-Dragon's 3 of 36.

**About "work well at bracket 3" specifically — this deck arithmetically cannot get
there.** `power.py` assigns the bracket purely on Game Changer count: 0 is Bracket 2, 1–3
is Bracket 3. You own exactly **four** of WotC's 53 Game Changers — Crop Rotation, Force of
Will, Mystical Tutor, Rhystic Study — and **not one of them is Mardu-legal**. They are all
green or blue. So no Kaalia deck built from your collection can be labelled Bracket 3 until
you buy one, regardless of how good it is.

Two honest caveats on that. It cuts the other way too: the Ur-Dragon's entire Bracket 3
status is its single copy of Rhystic Study — and `deck_conflicts` says you own 2 and four
decks want it, so the deck that earns the bracket may not be the deck that's sleeved. And
the repo's own source concedes the mapping is a heuristic; the official system also weighs
deck intent, which no script can read. Treat "Bracket 3" here as a proxy for power, not the
thing itself.

**The wipe problem does not go away — it gets worse.** The largest single number in this
analysis is the Ur-Dragon's collapse from a 78.5% kill rate to 12.8% against one modeled
board wipe. That is what 36 creatures with zero recursion does. Kaalia is *more* exposed:
she is a 2/2 the wipe also kills, and this build measures 4.1%.

## Where the goldfish number is wrong, and why it was overruled

One thing to hold on to when reading the kill-rate rows above: **the simulator models the
Ur-Dragon's engine and not Kaalia's.** `goldfish.py` pays eminence discounts by name — the
cost-reduction model shipped for this exact deck in August — while grepping it for "cheat"
or "onto the battlefield" returns nothing. Every head-to-head clock number is therefore
measured with one deck's engine switched on and the other's switched off, and the bias runs
against the pivot. The Ur-Dragon still wins those rows; just don't read the margin as real.

This build's kill rate (58.4%) reads *below* the straight auto-build's (68.8%), and that is
an instrument artifact, not a verdict — the same class already documented at length in the
Ur-Dragon notes. `goldfish.py` casts highest-mana-value-first, so it rewards a low curve;
it models no abilities; and **it does not model Kaalia's trigger at all.** Nine free bombs
is the entire point of the commander and the simulator cannot see one of them. The
engine-read wins, exactly as it did for Radagast and Ureni. Use `--ab` for like-for-like
swaps here, never the absolute clock.

## What would actually make this deck good

Six cards. The optimizer reached this list on its own; it lives in
`kaalia-of-the-vast.buylist.csv`:

| buy | field |
|---|---|
| Gisela, Blade of Goldnight | 79% |
| Aurelia, the Warleader | 73% |
| Rune-Scarred Demon | 71% |
| Avacyn, Angel of Hope | 67% |
| Liesa, Forgotten Archangel | 60% |
| Master of Cruelties | 59% |

**Ignore the buy list's `Replaces` column.** The optimizer refreshed it to name
Brainstealer Dragon and Smaug the Impenetrable — two of the five bombs — because those are
Universes Beyond cards the field has no data for, so it scores them at 0%. Pull the filler
instead: Fiendish Panda, Kardur, Tragedy Feaster, Serra Paragon, Emeria Angel, Fallen Angel.

No prices — the private priced `collection.csv` isn't in this clone, so anything quoted
would be invented. Six cards is a short list for turning a Bracket 2 pile into a real deck,
and it is the *only* path: the optimizer's verdict on the owned pool is verbatim
**"this deck can't improve from your collection: buy the gaps."**

## Do not cut (the optimizer will try)

Named here because `.notes.md` is what protects a card from `optimize.py`. Every one is a
deliberate, verified choice:

- **Brainstealer Dragon, Smaug the Impenetrable, Smaug the Great Calamity, Lathliss
  Dragon Queen, Hellkite Tyrant, Two-Headed Dragon, Scourge of Valkas, Scalelord Reckoner,
  Rakshasa Debaser** — the MV 6–7 top end, hand-added because the builder's curve template
  refused them. Cutting these turns the deck back into a pile of four-drops.
- **Indulgent Tormentor** — the optimizer proposed cutting it for a *shared* Talisman of
  Conviction on a 45%-vs-0% field read. Reverted: it is a Demon (a cheat target) that draws
  a card every upkeep unless an opponent pays, and the Talisman is committed to
  captain-america.
- **Karmic Guide, Serra Paragon** — Angels *and* recursion, the deck's answer to the wipe.
- **Dragon Tempest** — gives every cheated flier haste. Its 35% field number badly
  understates it here.

## If you sleeve this

**This deck and the Ur-Dragon cannot both exist.** It shares cards with it and
`deck_conflicts.py` reports the shortfalls. Worth knowing: dismantling the Ur-Dragon takes
the collection from 115 cross-deck conflicts to 98, and adding this deck back brings it to
105 — a **net reduction of 10** against today.

**Game plan.** Ramp on two and three, Kaalia on four, protect her, swing on five. She does
nothing the turn she lands, so hold the removal that keeps her alive rather than trading it
early. Every cheated body arrives tapped and attacking: attack the opponent who can't block
fliers, not the one at the lowest life.

**Mulligan for** two lands making two of W/B/R plus a rock, or Kaalia plus fixing. A hand
with three cheat targets and no way to cast her is a mulligan — the trigger is the deck.

**Sequencing.** Lathliss before the other Dragons: every nontoken Dragon Kaalia cheats in
afterwards makes a 5/5. Hellkite Tyrant is the one cheat target whose trigger survives
arrival — it keys on *combat damage*, not on attacking.

**Never cheat**: Hellkite Courser (cast it), Guardian Scalelord, Rakshasa Debaser,
Decadent Dragon, Desert Were-Worm, Smaug the Magnificent. Their triggers do not fire.

## Provenance

Every card in the 99 is owned and has a free physical copy with the Ur-Dragon dismantled;
nothing was invented. All 50 Mardu Angels/Demons/Dragons and 43 candidate lands were
verified verbatim against Scryfall on the GitHub runner, 2026-08-23 (109 cards, 0
UNVERIFIED — `kaalia-verified-2026-08-23.txt`, `kaalia-lands-verified-2026-08-23.txt`).
Field data: EDHREC snapshot of 38,818 Kaalia decks. Built with `auto_build.py` →
`deck_sections.py` → `optimize.py --apply`, then 12 hand swaps for the top end and three
land swaps made on verified text (Villainous Hideout → Sunbillow Verge, Temple of the False
God → Foreboding Ruins, Rocky Roads → Crossroads Village). 100 cards, singleton clean,
sections clean, all inside {W,B,R}.
