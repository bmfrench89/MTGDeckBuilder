# The Ur-Dragon — blind update (study copy)

Claude's fresh pass on 2026-10-12. It started from the logged Ur-Dragon list and was made
without seeing the player's upgraded deck, so the two can be compared. This is a study copy:
it reserves no cards, and the sleeved deck stays `the-ur-dragon`.

## Six swaps

| In | Out | Why |
|---|---|---|
| **Ureni of the Unwritten** | Pet Avengers | In 47% of Ur-Dragon decks. When it enters or attacks, it looks at the top eight cards and puts a Dragon onto the battlefield. |
| **Scourge of the Throne** | Parapet Thrasher | Its extra combat means a second Ur-Dragon attack trigger (draw, then drop a permanent) and a second Ureni trigger. |
| **Mana Drain** | Dragonlord Ojutai | From Y'shtola. A counterspell that also pays for next turn's dragon. |
| **Grim Tutor** | Seal of Cleansing | From Y'shtola. Finds Ureni, Scourge or a board wipe. |
| **Insatiable Avarice** | Zurgo and Ojutai | Puts any card on top for 3 mana, draws three for 3, or does both for 5. |
| **Reflecting Pool** | Cinder Glade | Cinder Glade usually enters tapped in this deck. |

Mana Drain, Grim Tutor and Insatiable Avarice are also the three cards the player moved into
their real Ur-Dragon, so on those the blind pass and the player agree.

## Caveats

- **Goldfish blind spot.** Goldfish scores Ureni and Scourge as slightly slower: +0.04 and
  +0.03 turns to the first kill. It counts printed power and mana cost, but it does not
  model attack or ETB triggers or extra combats. The verdict comes from the verified text.
- **Reflecting Pool is modeled as a five-colour land.** That is Scryfall's own production
  data (W U B R G), carried by the attrs snapshot since 2026-10-12. The real card makes only
  what your other lands could make, so the model is slightly generous when Pool is your only
  land. Re-run with that data, swapping Pool back to Cinder Glade over 4,000 identical
  shuffles makes the first kill +0.04 turns slower and costs about 1 damage. So the swap
  stands.
- **The automatic rebuild did worse.** `auto_build` from the pool cut notes-protected engine
  pieces (Dragon Broodmother and the cost-reducer dragons) and added filler. That is why
  this is an update of the logged list, not a rebuild.
