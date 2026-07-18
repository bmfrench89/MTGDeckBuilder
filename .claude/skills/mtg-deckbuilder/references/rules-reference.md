# Rules Reference — facts that were gotten wrong and corrected

Keep this handy while building. Each item is a real correction from this project.

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
For anything from a post-2025 set, or any interaction you're not certain of, search Scryfall/
Gatherer for the current oracle text and any relevant rulings before building around it. A wrong
reading of one engine piece can invalidate a whole deck plan.
