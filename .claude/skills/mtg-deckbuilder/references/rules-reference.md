# Rules Reference — ask the CR, don't recall it

## Ask the CR, don't recall it

There is a tool for this now. Rules answers come from **retrieved text**, not memory —
that is the whole reason `scripts/rules.py` exists.

```bash
python3 scripts/rules.py 903.1                    # a rule by number (subrules included)
python3 scripts/rules.py "commander tax"          # glossary first, then full-text search
python3 scripts/rules.py --search "deathtouch trample" --limit 5
python3 scripts/rules.py --gloss "Deathtouch"
python3 scripts/rulings.py "Sol Ring"             # Scryfall's rulings for ONE card
python3 scripts/carddb.py --verify "Sol Ring"     # what the card actually says
```

The order matters: **retrieve → READ → cite.**

1. **Retrieve.** Search is a shortlist ranked by word overlap; it is not an answer and
   it does not know what you meant.
2. **Read.** Look the winning rule up by number and read its actual text, including its
   subrules. A snippet is not a rule.
3. **Cite.** Quote the rule number *from the text you just retrieved* — never a number
   you remember. A confidently wrong rule number is worse than no citation, because it
   looks checked.

Card-specific questions take two lookups, not one: `carddb.py --verify "<card>"` for the
verbatim oracle text and `rulings.py "<card>"` for WotC's clarifications, then the CR for
the general rule underneath. First-ever run of `rules.py` downloads the Comprehensive
Rules (~1 MB) into `data/cache/rules/`; it is never committed and never auto-refreshes —
`--refresh` when a new set drops.

**When it degrades** (the CR is reachable from the player's PC only — not from the hosted
server, not from a sandbox), `rules.py` prints a manual-download note and exits 1. Then,
and only then, fall back to a web search of Scryfall/Gatherer — **and say the answer is
uncited**: "I couldn't reach the Comprehensive Rules, so this is from a web source rather
than the rule text." Never silently substitute memory for the retrieval that failed.

## Known traps

Each item below is a real correction from this project — a place where the confident
answer was the wrong one. They are traps, not a rules index: when a question touches one,
go look the rule up anyway.

## X spells and mana value on the stack
While an X spell is **on the stack**, X equals the value chosen, so its mana value includes X.
Example: **Exsanguinate** or **Profane Command** cast for X ≥ 1 has mana value 3+ on the stack,
so it **does** trigger "whenever you cast a spell with mana value 3 or greater" (e.g. Y'shtola).
Everywhere *other than* the stack (hand, graveyard, battlefield), X = 0.

## "Cast" triggers resolve even if the spell is countered
An ability that triggers on **casting** a spell (e.g. Y'shtola's "whenever you cast a noncreature
spell with MV 3+, deal 2 to each opponent and gain 2") still resolves even if that spell is later
countered. The trigger is independent of the spell resolving. Don't shy away from these triggers
against counter-heavy tables.

## Exile-based wipes anti-synergize with graveyard payoffs
Board wipes that **exile** (Final Judgment, Extinction Event, Farewell's exile modes) remove
creatures from the game, starving reanimator, graveyard-cast, and aristocrats/death-trigger
payoffs. In a deck with graveyard synergy, **prefer destroy-based wipes** (Toxic Deluge,
Blasphemous Act, Damnation, Cleansing Nova) so your creatures land in the yard where you want them.

## Mana value: flashback and MDFCs
- **Flashback** does not change a card's mana value — it's the same spell cast from the graveyard
  for its flashback cost; MV is still the card's normal MV.
- **Modal double-faced cards (MDFCs):** each face has its **own** mana value. The back-face spell's
  MV is whatever is printed on that face — it is not the front's MV. Check the exact half you mean.

## Life loss vs. life "gain" for drain triggers
"Whenever a player loses 4 or more life this turn" cares about **life lost**, which includes both
damage and life-payment/drain, not lifegain. Effects that make an opponent lose life (drain) count;
your own lifegain does not make *you* the one who lost life. Amplifiers that convert lifegain into
opponent life loss (Vito, Defiling Daemogoth) are how a lifegain shell feeds a "lost life" trigger.

## General verification habit
For anything from a post-2025 set, or any interaction you're not certain of, get the current
oracle text (`carddb.py --verify`) and the card's rulings (`rulings.py`) before building around
it, and the rule underneath from `rules.py`. A wrong reading of one engine piece can invalidate
a whole deck plan.
