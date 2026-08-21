# Dina, Essence Brewer — game plan

## The engine

**Verified commander text** (Scryfall, deck-verify run 32442182052, 2026-08-21):

> Dina, Essence Brewer — {1}{B}{G} — Legendary Creature — Dryad Druid
> Whenever you sacrifice a creature, draw a card. **This ability triggers only once each turn.**
> {2}, {T}, Sacrifice another creature: You gain X life and put X +1/+1 counters on
> target creature you control, where X is the sacrificed creature's power.

This is a **metronome, not a bomb**. The draw trigger caps at one per turn, so the deck does
not want a turn where nine bodies die at once — it wants *one* sacrifice every turn, forever,
and it wants that sacrifice to cost nothing. That is why recurring fodder outranks fat bodies:
Beledros Witherbloom makes a Pest at **each** upkeep (four per turn cycle at a four-player
table), Jadar and Ophiomancer remake a body every turn, and Bloodghast and Nether Traitor
climb out of the graveyard by themselves. Feed one to a free outlet each turn; Dina pays a
card while Blood Artist, Zulaport Cutthroat and Mazirek tax the table.

The second ability is a **ratchet**. Sacrifice a 2-power body, put the two counters on
Bloodghast, and Bloodghast is the 4-power body you sacrifice next turn for X=4. Each
activation loads the next one. Point the counters at something that comes *back* — never at
something that will die and take them with it.

**One structural honesty note.** Dina, Soul Steeper in the 99 reads "Whenever you gain life,
each opponent loses 1 life" — **one trigger per lifegain event, regardless of size** (also
verified in the same run). Gaining 5 life off a fat sacrifice drains exactly 1. Output scales
with the *number* of gain and death events, not their magnitude. Build turns accordingly.

## Piloting

- **Mulligan rule:** keep 3–4 lands; keep 2 only with acceleration (Sol Ring, Arcane Signet,
  Elvish Mystic, Gilded Goose); ship everything else. Measured: keepable 81%, ≥3 lands 52%,
  screw 15%, **flood 0%**, commander down mean turn 3.5. You cannot flood out; you can
  absolutely screw out.
- **Prefer the outlet over the payoff.** Blood Artist with nothing to sacrifice is a 0/1.
  Viscera Seer with anything is an engine.
- **One sacrifice per turn** to bank the draw. Dumping five bodies into one turn draws one
  card and hands a sweeper a free two-for-five.
- **Against a known wrath, sacrifice the board in response.** You keep the drains, the
  graveyard fill and the cards.

## Protected cards — do not let the optimizer cut these

The optimizer values a card at `max(field %, (fit−60)×2)`, so a low-field card that is here on
purpose gets churned out on the next run unless it is named here. These are deliberate:

- **Seal of Doom**, **Nameless Inversion** — added 2026-08-21 to close a counted deficit:
  removal was 7 against the template band 8–11. With them the deck reports 12
  removal/counter/wipe and Interaction scores a full 18.0/18. Both are on `mtglib.REMOVAL`'s
  hand-verified curated list. Neither has field presence on this commander; that is the point.
- **Evolving Wilds** — replaced Villainous Hideout, which `manabase.py` refuses to count
  because its mana is spend-restricted (`mana-restricted` in the enrichment flags). Evolving
  Wilds joins the fetch census instead. B/G source counts are unchanged at 25/24.
- **Beledros Witherbloom**, **Dina, Soul Steeper**, **Mazirek, Kraul Death Priest** — the
  three engines that make the commander's once-per-turn draw worth building around.
- **Bloodghast**, **Nether Traitor**, **Jadar, Ghoulcaller of Nephalia**, **Ophiomancer** —
  free recurring fodder. The deck's whole tempo is one of these dying every turn.
- **Blood Artist**, **Zulaport Cutthroat** — the death-trigger drains the goldfish sim cannot
  see and therefore always undervalues.
- **Crop Rotation** — the deck's one Game Changer; absent from the field snapshot entirely.

## Round-2 verification verdicts (run 32450437172, 2026-08-21)

All 20 queued names came back verified — full verbatim text in
`data/reference/dina-verified-2026-08-21.txt`. The two risk items both resolved in the
deck's favor, and the text audit *upgraded* several cards the counters undervalue:

- **Final Act — KEEP.** Modal, "choose one or more", and the creature mode is **Destroy
  all creatures** — so every death payoff (Blood Artist, Zulaport, Mazirek, Morbid
  Opportunist, Moldervine Reclamation) triggers off your own wipe. The exile mode is
  *graveyards only* and optional. **Pilot note:** do not pick "Exile all graveyards"
  while your own recursion (Bloodghast, Nether Traitor, Teacher's Pest, Sage of the
  Fang's Renew) is loaded — it hits every graveyard, yours included.
- **Feral Appetite — KEEP, but the honest count changes.** Its `removal` flag is a false
  positive: the text is "{1}{G}: Exile target card from a graveyard" — repeatable
  graveyard hate that mints a Pest (fodder + a lifegain body), *not* board removal. So
  the deck's true board-removal count is **8, not 9** — still inside the 8–11 band, so
  no further swap is forced. The reported "12 removal/counter/wipe" includes this card.
- **Vito, Thorn of the Dusk Rose — buy rec confirmed.** "Whenever you gain life, target
  opponent loses **that much** life." Magnitude-aware, exactly as claimed.
- **Recursion 0 is now disproven by text, not just suspected:** Veinwitch Coven ("whenever
  you gain life, pay {B}: return a creature card from your graveyard to hand" — repeatable,
  triggered by the commander's own activation), Teacher's Pest ({B}{G}: return to the
  battlefield), Sage of the Fang (Renew), plus Bloodghast/Nether Traitor. The counted 0 is
  purely `resilience_staples.csv` having no green rows.
- **The free sacrifice outlet the metronome wants exists and is verified:** Umbral Collar
  Zealot — "Sacrifice another creature or artifact: Surveil 1", no mana cost, no tap. Also
  Viscera Seer and High Market. Merchant of Venom is an ETB edict that feeds Mazirek.
- **The ten 0%-field Druids, read on text (sleeper-audit verdicts, no silent drops):**
  Great Forest Druid (any-color dork — keep), Gwenna (two mana, creature-spend-only; 41
  creatures here — keep), Merchant of Venom / Umbral Collar Zealot / Ribtruss Roaster /
  Gorma / Teacher's Pest / Trystan (all real engine pieces on text — keep),
  **Environmental Scientist, Mindful Biomancer, Old-Growth Educator — BENCH**: fine
  bodies, weakest verified text in the 99, and the first cuts if the player wants slots.

## Known limits

- **Verified coverage:** 26 of the 88 unique cards now have verbatim text on disk (the 6
  from round 1 + the 20 from round 2). The rest ride on enrichment flags — by design
  (`oracle_flags.py`: the flags *are* the storage), but it bounds any audit.
- **`auto_build` selected on the type line.** The commander is a *Dryad Druid*, so
  `_tribe_and_support` read "druid", cleared `_TRIBAL_MIN`, and seeded on-tribe creatures;
  `deck_fit` then pays +15 for "on-tribe (Druid)". Sixteen of 41 creature slots are Druids and
  ten of them have under ~2% field presence. That is type-line selection, not measured engine
  fit — it is where the next round of cuts should come from, **after** those cards are verified.
- **Protection 0 is real; recursion 0 is mostly a display artifact.** `power.py` counts
  recursion only from `resilience_staples.csv`, whose recursion role has zero green rows, so a
  Golgari deck's ceiling on that axis is 2. Protection was left alone deliberately: every
  curated option is either committed to another deck or scores *negative* fit here, and with
  the drain suite out a wrath drains rather than simply losing.
- **The goldfish sim is blind to this deck.** It models no sacrifice outlets, tokens, drain or
  lifegain, so its median-turn-9 clock understates the deck. Trust it for lands, curve and
  commander timing only.

## Wishlist, not a silent pull

**Vito, Thorn of the Dusk Rose** is the single best add available and the only owned copy is
load-bearing in `yshtola-nights-blessed` (named in that deck's notes as its drain payoff).
It is the one card here worth *buying* — it is the magnitude-aware lifegain payoff this deck
otherwise lacks. Do not take it off the other deck without deciding which one sleeves it.
