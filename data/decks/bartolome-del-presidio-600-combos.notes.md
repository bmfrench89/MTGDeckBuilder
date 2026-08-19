# Bartolomé del Presidio — "600 Infinite Combos"

Study copy of the deck from the YouTube deck tech **"1 Deck, 27 Dollars, 600 Infinite
COMBOS"** (`youtu.be/1Yusxsud5BE`). **Not built from this collection** — the ownership
check flags 56 of the 100 cards as not owned. It is here so the repo's engines can
score a real combo deck and so `combos.csv` learns the lattice.

## The one idea

**Bartolomé del Presidio** — `{W}{B}`, Legendary Creature — Vampire Knight, 2/1, *"Sacrifice
another creature or artifact: Put a +1/+1 counter on Bartolomé del Presidio."* — is a **free,
unlimited sacrifice outlet that starts in the command zone**. It costs no mana and has no
once-per-turn clause. Everything else in the deck is built to abuse that one line.

The deck is not 99 cards of "sacrifice matters." It is a **lattice**: two interchangeable
card *classes* that combo with each other in any pairing.

### Class A — recursion that returns the creature the moment it dies

| Card | MV | Type | Note |
|---|---|---|---|
| Kaya's Ghostform | 1 | Aura | cheapest half of the engine |
| Angelic Renewal | 2 | Enchantment (**not** an Aura) | sacrifices itself to return the creature |
| Fungal Fortitude | 2 | Aura | returns it tapped — irrelevant, you only sacrifice it |
| Changing Loyalty | 2 | Aura | flash + replicate |
| Necrogen Communion | 2 | Aura | also grants toxic 2 — an alternate poison kill |
| Minion's Return | 3 | Aura | flash |
| Gift of Immortality | 3 | Aura | creature returns **immediately**; only the Aura waits for end step |

### Class B — a creature whose enter trigger returns that permanent from the graveyard

| Card | MV | Can return |
|---|---|---|
| Brotherhood Outcast | 3 | Aura/Equipment, MV ≤ 3 |
| Redemption Choir | 4 | any permanent MV ≤ 3 — **Coven-gated** |
| Danitha, Benalia's Hope | 5 | Aura/Equipment, any MV, from hand **or** graveyard |
| Sun Titan | 6 | any permanent MV ≤ 3 |
| Angel of Indemnity | 6 | any permanent MV ≤ 4 |
| Shepherd of the Cosmos | 6 | any permanent MV ≤ 2 |
| Boonweaver Giant | 7 | Aura, any MV, from graveyard/hand/**library** |

**The loop:** sacrifice the Class B creature to Bartolomé → the Class A aura returns it →
its enter trigger returns the aura from the graveyard, attached again → repeat. **Zero mana
per iteration**, so it never stops: infinite deaths, infinite enter triggers, and a +1/+1
counter on Bartolomé every time around.

**44 legal Class A × Class B pairings exist in this list** (see `combos.csv`; Shepherd can't
reach the MV-3 auras, and Brotherhood Outcast / Danitha / Boonweaver are Aura-only so they
miss Angelic Renewal, which is a plain enchantment).

**Boonweaver Giant is a one-card engine** — it searches the *library* for its own aura, so
commander + Boonweaver is the entire combo. Seven mana is the only thing wrong with it.

### Class C — payoffs that turn the loop into a win

- **Zulaport Cutthroat**, **Bastion of Remembrance** — each opponent loses 1 per death
- **Marionette Apprentice** — each opponent loses 1 per creature *or artifact* death
- **Agent of the Iron Throne** — a Background that grants the drain to Bartolomé himself
- **Ninja Teen** (level 1) — triggers on *leaves the battlefield*, not just death
- **Scavenger's Talent** (level 2) — every sacrifice mills 2: mill the table out instead
- **Rogue's Passage** — Bartolomé is arbitrarily large after the loop; make him unblockable

44 engines × 6 kill payoffs = **264 distinct three-card infinite wins**, all with the
commander. **Dimir House Guard** ("Sacrifice a creature: Regenerate this creature") is a
*second* free sacrifice outlet, which doubles the enumeration. That is how the video's
counter reaches ~600.

## Assembly

Tutors: **Final Parting** (creature to the graveyard + aura to hand — the perfect setup card),
**Demonic Bargain**, **Dimir House Guard**'s transmute (MV 4 → Redemption Choir), and
Boonweaver's own aura search. Self-mill (Stitcher's Supplier, Crow of Dark Tidings, Undead
Butler, Paramecia Coloniex, Millikin, the three surveil lands) fills the yard; reanimation
(Dread Return, Unburial Rites, Summon Undead, Body Snatcher, Valgavoth's Faithful, Memorial
to Folly, Sevinne's Reclamation) buys the halves back.

## Honest weaknesses

- **Graveyard hate is a hard stop.** Rest in Peace, Grafdigger's Cage and Soulless Jailer
  turn off every one of the 44 engines, because every Class B trigger reads the graveyard.
  The deck has no answer to an enchantment-based static beyond Disenchant.
- **The basics are inverted.** Verified colored pip demand is **W 28 / B 37** (8 double-W
  cards vs 4 double-B), but the list runs **12 Plains / 9 Swamp**. Cross-checked both ways
  (2026-08-19): the graveyard-side costs my count omits are white (Unburial Rites flashback
  {3}{W}, Dawn {3}{W}{W} → effective ~31/37), yet the white pips sit disproportionately on
  reanimation *targets* you rarely hard-cast, while nearly every black card is a tutor,
  mill or recursion spell cast from hand on curve. Both refinements still land B ≥ W:
  swap two to three Plains for Swamps.
- **Four "any colour" lands charge {1}** (Conduit Pylons, Hidden Grotto, Surveillance Room,
  Great Hall of the Citadel) and four more make only colourless (Mariposa Military Base,
  Myriad Landscape, Rogue's Passage, Ash Barrens). The raw 21-source count per colour is
  flattering; untapped free black is closer to 12. Great Hall earns its slot anyway: its
  {1} → two-mana mode is restricted to legendary spells, which in this deck is a commander-
  tax ritual for a commander who will die to removal repeatedly — a smart budget pick.
- **Demonic Bargain exiles 13 cards** — but the lattice's redundancy (14 interchangeable
  halves) means 13 random exiles rarely disable an engine. A real cost, not a dealbreaker;
  the worst case is exiling Dusk // Dawn, whose Dawn half is graveyard value.
- ~~Dusk // Dawn kills its own engine~~ — **retracted on cross-check** (2026-08-19). Dusk
  destroys power ≥3: the seven returners plus Corpse Augur. But this deck *wants* its
  returners in the graveyard — they are the reanimation targets — and Dusk **spares every
  drain payoff and all the fodder** (all power ≤2). It is destroy-based, not exile-based
  (grounding rule #5), and the Dawn half casts **from the graveyard regardless of how it
  got there** (aftermath ruling), so milling it is value: a mass rebuy of every payoff.
  This is a deliberately asymmetric wipe, correctly chosen. The one real caveat: Bartolomé
  himself grows past power 2 and dies to your own Dusk — spend his counters knowingly.
- **Corpse Augur and Gnawing Vermin are not loop payoffs** — Augur dies once, and Vermin's
  trigger needs a creature you don't control to target.
- No counterspells, no protection, no fast mana. The cheapest engine is Brotherhood Outcast
  (3) + Kaya's Ghostform (1) on top of the commander (2) — realistically turn 5–6.

## Verification

Every card whose text this analysis leans on was checked against Scryfall by lookup this
session (network to `api.scryfall.com` is blocked in the sandbox, so `carddb.py --verify`
could not run; web search against Scryfall was used instead — see the session transcript).
The Teenage Mutant Ninja Turtles set (Ninja Teen, Paramecia Coloniex) is post-cutoff and
was verified, not recalled.

The 600 figure itself is **not reproducible here** — Commander Spellbook's `find-my-combos`
endpoint is blocked in the sandbox, so `spellbook.py` cannot be run against this list. 264
kill combos are counted by hand above and 45 rows are written into `combos.csv`; the rest
of the gap to 600 is the second sacrifice outlet and Spellbook's finer-grained enumeration.
