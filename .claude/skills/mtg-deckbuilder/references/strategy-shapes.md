# Strategy Shapes — the axes above card choice

Companion to `combo-shapes.md`. That file answers *"how do two cards make a loop?"*
This one answers *"what is the deck's theory of winning, and what numbers express it?"*
Researched 2026-08-19 from published strategy sources (linked at the bottom); every
number below is quoted from a source, not estimated.

**The sandbox has no network for card data — but strategy literature is not card data.**
`deck-verify.yml` verifies oracle text; it cannot read strategy articles, so web search
is the correct channel here. Any *card* named as a recommendation still goes through the
verify queue.

---

## Part 1 — Six shapes, and the test that identifies each

| Shape | The resource it attacks | The one-question test |
|---|---|---|
| **Resource denial** (stax / tax / hatebears) | opponents' mana, untaps, casts | **"Is it asymmetric?"** A piece that slows you as much as them is a bad piece |
| **Life / library as fuel** | your own life total or library | **"Is my curve low enough to survive my own payoff?"** |
| **Spell velocity** (storm) | the one-spell-per-turn convention | **"Is this card mana-POSITIVE?"** |
| **Toolbox / silver bullet** | variance | **"Is the tutor the engine, or just a search?"** |
| **Inevitability / attrition** | time | **"If nothing changes, who wins on turn 20?"** |
| **Pillowfort / politics** | opponents' *attention* | **"Am I a worse target than the other two?"** |

### Resource denial — the asymmetry test is the whole skill
Stax is *"resource denial as a core game plan"*. The literature is unanimous that the
distinguishing property is **asymmetry**: a good piece taxes the table and exempts you,
usually because your deck was built not to care (Smothering Tithe taxes opponents and pays
you; Drannith Magistrate shuts off their commanders while yours works).

**Three tiers, often conflated — they are not the same shape:**
- **Taxes** — "sure, but it'll cost you." Speed bumps that leave a choice.
- **Hatebears** — cheap creatures that tax *and* carry a clock. Denial with a body.
- **Prison/stax proper** — permanent-based restrictions that aim to make opponents unable
  to function.

Standing rule from every source: **a stax deck must carry a win condition and close
promptly.** A lock with no kill is a draw you inflicted on the table.

### Life / library as fuel
Ad Nauseam works because Commander is a 40-life format — decks built for it *"frequently
draw upwards of 30 cards."* The constraint is arithmetic: each card costs its mana value
in life, so **the payoff sets a hard ceiling on your curve** (Naus shells target an average
MV well below 2). This is the purest example of a card that *rewrites your entire build*.

The library version is the same idea inverted: **empty-library wins** (Thassa's Oracle,
Laboratory Maniac, Jace, Wielder of Mysteries) turn your library from a resource into a
countdown you *want* to hit zero. `combos.csv` already carries these rows.

### Spell velocity — "is it mana-positive?"
A ritual is *"a spell that gives you mana equal to or greater than the amount used to cast
it."* The whole storm build is a chain of cards that each leave you with more than you had.
**Cost reducers are the multiplier**: Goblin Electromancer / medallion effects *"upgrade
spell efficiency by making spells that would be neutral into positive ones."* Graveyard
recasting (Past in Flames, Underworld Breach) is what makes 10-15 spells in a turn viable.

**Underworld Breach + Lion's Eye Diamond + Brain Freeze** is the modern reference engine —
it produces near-infinite mana, storm count and mill off three cards, by escaping the same
two spells repeatedly. Note the family resemblance to our lattices: *a loop whose fuel is
the graveyard, gated by an escape cost rather than by "nontoken."*

### Toolbox — the tutor IS the engine
*"A suite of silver bullets to answer all manner of threats with a tutor package to find
them at the perfect time."* The discipline: **Birthing Pod is a tutor to hit answers, not
a means to flood the board.** A toolbox deck's power is the *breadth* of its one-of
answers, so evaluating one card in isolation always undersells it.

### Inevitability — the long-game question
*"If one player is virtually guaranteed to win the game if it goes long enough, that player
has inevitability."* Control decks run **few** win conditions but very resilient ones,
chosen precisely to grant it. The strategic consequence is directional: **if you have
inevitability, don't take risks — just don't die.** If your opponent has it, you must
change the course of the game before time runs out.

### Pillowfort / politics — the only shape whose resource is other people
Pillowfort *"shelters itself and distracts opponents… while they're busy attacking each
other, you search for a way to win."* Taxing attackers (Ghostly Prison, Propaganda) stacks
multiplicatively. The political layer is real strategy, not flavour: **"the table usually
aligns against whoever is ahead, even if nobody says it out loud. If you look like the
archenemy, you become the archenemy."**

---

## Part 2 — The numbers (quote these, don't estimate)

**cEDH composition targets** — the ceiling, useful as a direction even for Bracket 3:
`interaction 12–18 (including at least 3 FREE counterspells) · tutors 7–12 ·
fast mana 8–14 · win conditions 4–8 · lands 28–31 with zero ETB-tapped.`
*"Not running enough free counterspells is the single most common mistake new cEDH
builders make."*

**Redundancy math** — the alternative to tutors:
`5–8 copies of an effect is the standard band; 8–12 when the deck stalls without it.`
**8 copies is the number that gets an effect into your hand by turn 3.** Crucially:
*"a deck with heavy redundancy and strong draw engines can be extremely consistent without
a single traditional tutor."*

**Protection counts** — scale to commander-dependence:
`5–8 protection spells if the commander or a key engine must stay on the battlefield;
2–4 when the deck has recursion, redundancy or several ways to rebuild.`
The test: **"if your commander gets removed twice, does the deck still function?"**

**The Fundamental Turn** (Zvi Mowshowitz) — *the turn your deck actually wins*. The core of
interactive Magic: **either have a faster fundamental turn than the table, or use disruption
to push theirs later than yours.** For a control deck it is the turn its plan comes online,
not the turn it kills.

**The four resources** — cards, mana, tempo, life. Trades between them are the substance of
play: *"you make sacrifices in tempo to gain card advantage, or sacrifices in card advantage
to gain tempo."* **Virtual card advantage** is the underrated one — running few or no
creatures makes opponents' removal dead, which is card advantage without drawing a card.

---

## Part 3 — CRISPI: the framework that replaced power levels

DeckCheck **retired single-number power levels in 2026** and replaced them with **CRISPI —
Consistency, Resilience, Interaction, Speed**, each 1–10, averaged into a Performance Index.
Their stated reason is directly relevant to this repo: *"power levels were competing with
brackets, and the number was opaque."* CRISPI *"tells you not how powerful your deck is, but
how it plays"* — it can express **fast-but-fragile** and **slow-but-resilient**, which one
number cannot.

Their implementation note is worth copying: **Consistency and Interaction are pure counting**
against a rubric; only **Speed** (the fundamental turn) and **Resilience** (commander-
dependence) need judgement.

### What this repo measures today, audited 2026-08-19

| CRISPI axis | `power.py` status |
|---|---|
| **Interaction** | ✅ counted (`signals.interaction`) |
| **Consistency** | ◐ partial — lands and tutors counted, redundancy **not** |
| **Speed** | ❌ not scored — **but `goldfish.py` already simulates it**, just isn't wired in |
| **Resilience** | ❌ **not measured at all** — no protection count, no commander-dependence |

**And the flaw CRISPI was invented to fix is live in our output.** `power.py --rank` prints:

```
bartolome-del-presidio-600-combos   Bracket 4 Optimized   31/100 Casual
```

**"Bracket 4" and "31/100 Casual" in the same row.** The bracket sees two-card infinites;
the power score sees no tutors, no fast mana, no draw. Both are right about what they
measure and the row as a whole is nonsense — which is exactly *"the number was competing
with the bracket."* Treat the 0–100 as a component readout, never as a headline, and
prefer the four axes.

---

## Part 4 — What this says about THIS collection (counted, not guessed)

Signals across all nine decks, via `deckcore.analyze_deck`:

| | interaction | tutors | fast mana | draw | avg MV |
|---|---|---|---|---|---|
| range across 9 decks | **10–14** | **0–1** | **0–1** | 7–15 | 2.42–**4.22** |
| cEDH reference | 12–18 | 7–12 | 8–14 | — | — |

1. **Interaction is already healthy** — 10–14 sits at the low end of the cEDH band on decks
   that are not trying to be cEDH. This is not a weakness; stop treating it as one.
2. **Tutors are ~zero and fast mana is ~zero across the entire stable.** That is the single
   structural signature of this collection. It is bracket-appropriate — but it means the
   consistency lever available here is **redundancy (5–8 copies), not tutors.** Draw is
   strong (7–15), which is exactly the profile the literature says makes a tutor-less deck
   work.
3. **`the-ur-dragon` avg MV 4.22** against a stable that otherwise runs 2.42–3.03. A real
   outlier worth a look — dragons are expensive, but that gap is where a deck stalls.
4. **Resilience has never been measured on any of these decks.** Given tutor-light,
   redundancy-based builds, the protection question ("does it work if the commander dies
   twice?") is the most valuable unmeasured number in the repo.

## Sources
cEDH archetype taxonomy — [EDHREC Turbo guide](https://edhrec.com/guides/edhrec-guide-to-cedh-turbo),
[cEDH Wiki](https://cedh.fandom.com/wiki/Introduction_to_cEDH) ·
stax — [Commander's Herald](https://commandersherald.com/lets-talk-about-stax-in-cedh/),
[Goonhammer resource denial](https://www.goonhammer.com/commander-102-resource-disparity-and-denial/) ·
interaction density — [EDHREC interaction guide](https://edhrec.com/guides/edhrec-guide-to-interaction-in-cedh) ·
storm — [Card Kingdom archetype inspection](https://blog.cardkingdom.com/commander-archetype-inspection-storm/) ·
Breach line — [Commander Spellbook](https://commanderspellbook.com/combo/1368-3518-4856/) ·
inevitability — [TCGplayer](https://www.tcgplayer.com/content/article/What-is-Inevitability-in-MTG/b03d58db-bc03-4a18-90cc-5eace46da349/) ·
fundamental turn — [CoolStuffInc](https://www.coolstuffinc.com/a/examining-the-fundamental-turn) ·
resources — [WotC tempo & card advantage](https://magic.wizards.com/en/news/feature/tempo-card-advantage-delicate-balance-2014-11-17) ·
CRISPI — [DeckCheck deep dive](https://deckcheck.co/blog/crispi-deep-dive),
[removing power levels](https://deckcheck.co/blog/performance-index/) ·
threat assessment — [Draftsim](https://draftsim.com/mtg-commander-threat-assessment/) ·
pillowfort — [EDHMeta](https://edhmeta.com/pillowfort-archetype-guide/)
