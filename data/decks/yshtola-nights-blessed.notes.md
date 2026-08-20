# Y'shtola, Night's Blessed — Night's Blessed Control

## Game plan (updated 2026-08-20 — Bracket 4, player-ratified)
Esper drain-control behind a pillowfort. Y'shtola turns the deck's constant small
life-loss triggers into cards, Vito and Blood Artist turn drains into damage, and
two lines close: the Viscera Seer + Sun Titan + Angelic Renewal zero-mana loop, or
Exsanguinate off Dark Ritual and Mana Drain mana. Ghostly Prison and Norn's Annex
tax anyone who comes at us while the engine assembles; Teferi keeps our sorcery-
speed pieces uncounterable; Bloodchief Ascension turns the drains the deck already
makes into a second, compounding engine. Counter what matters, tax the rest, and
let the drain grind the table out — then present the loop.

## Engine pieces (do not cut — this is the strongest deck in the stable; the
## optimizer must never churn its core for field-average FF cards)
- Force of Will / Counterspell / Mystical Tutor / Dig Through Time — the blue core.
- Ash Barrens — stays: the single owned Reliquary Tower is committed to Iron Man
  (2026-08-11 call), and Barrens' basic fetch fixes Esper pips on a 3-color base.
- Rhystic Study — the draw engine.
- Vito, Thorn of the Dusk Rose — the drain payoff (player-confirmed copy).
- Blood Artist — drain on every death, fuels the commander.
- Exsanguinate — the finisher; X scales with Dark Ritual and Toxic Deluge turns.
- Dark Ritual — ritual into an early engine or a bigger Exsanguinate (22% field).
- Toxic Deluge — the wipe that keeps our life total as a resource.
- Archmage Emeritus — every counterspell and drain instant cantrips.
- Sun Titan — recurs the cheap engine (Blood Artist, Vito, removal seals).

## Physical copies
Force of Will (pinned here via pins.csv), Rhystic Study, Counterspell, Mystical
Tutor, Dig Through Time, Sublime Epiphany, Archmage Emeritus and Sun Titan are
shared with other decks — dashboard badges them; wishlist tracks extra copies.

## Pilot notes
Mulligan for 3 lands + either a draw engine or two pieces of interaction. Don't
tap out into open blue mana after turn 4 unless the play wins or stabilizes.
Exsanguinate math: count opponents' life ÷ 3 before calling it lethal.

## 2026-08-11 sleeper audit adds (manual — do not cut)
- Wizard's Staff — equips Y'shtola ({3}, she's a Cat Warlock, not a Wizard) and her
  triggered abilities trigger TWICE: every MV3+ noncreature spell drains each
  opponent 4 and gains 4, and the end-step draw doubles. Verified HOB #59. In over
  Absorb (7% field) — the deck's designated weakest counter, with two better ones
  already queued on the buylist.

# Delney, Streetwise Lookout (sleeper audit 2026-08-15 — text runner-verified)
Engine piece, do not cut. Delney doubles triggered abilities of your power-2-or-less
creatures — and this deck's whole engine lives on exactly those bodies: **Y'shtola
herself is printed power 2** (both triggers double: the end-step draw becomes draw 2,
and every MV≥3 noncreature spell becomes 4 damage to each opponent + 4 life), **Blood
Artist (0/1)** drains twice per death, and **Vito (1/3)** doubles every drain his
lifegain trigger converts. Field agrees: 39% of Y'shtola decks run her. Replaced Read
the Bones (6%) — a one-shot draw the doubled end-step trigger out-draws over any game
longer than two turns.

## 2026-08-19 — the win button (manual, Source=manual-replace, do not cut)
Player-ratified from the Bartolomé lattice study (combo-shapes.md). **Viscera Seer +
Sun Titan + Angelic Renewal is a zero-mana infinite:** sacrifice Sun Titan to the Seer
(scry 1), Angelic Renewal sacrifices itself to return him, and his enter trigger
returns Angelic Renewal (MV 2 ≤ 3) from the graveyard. Every pass through the loop is
a death — **Blood Artist and Bastion of Remembrance drain the table to 0, and Vito
converts Bastion's life gain into a second drain.** Delney does not double the loop
(Sun Titan is power 6) but doubles Blood Artist's payoff. The detector's verdict is
*deterministic but not a cheap 2-card line* — the deck **stays Bracket 3** (still 3
Game Changers, no early 2-card combo), power 78 unchanged. It gained a clean kill,
not a bracket jump.

- In: **Viscera Seer** (over Commander's Sphere — the 11th and weakest mana rock;
  ramp stays in band) and **Angelic Renewal** (over Soul Shatter, 8% field, the 10th
  removal spell). Renewal is live outside the combo too: it resurrects whichever
  engine creature dies first, and it is *optional* ("may"), so it never mis-fires.
- Both new cards also feed Y'shtola herself: the loop trivially clears the "a player
  lost 4 or more life this turn" check, and outside the combo the Seer turns spare
  bodies (a dying Baleful Strix, a spent Solemn Simulacrum) into scry + drain triggers.
- Pilot: assemble as Seer early (1 mana, unassuming) → Renewal turn N → Sun Titan
  turn N+1 with the loop online at once; or reanimate/recur Titan with the Renewal
  already down. Hold the loop until you can win through open mana — a kill spell on
  Sun Titan **in response to the Renewal trigger** breaks the chain.
- Bench (owned, uncommitted, one swap each if the table hates it or wants more
  redundancy): Woe Strider / Fanatical Devotion / Martyr's Cause (more free outlets —
  Martyr's Cause also prevents one damage source per iteration), Gift of Immortality
  (2nd copy free; second loop half), Angel of Indemnity (returner #2, MV≤4 reach),
  Zulaport Cutthroat (payoff #4).
- The whole lattice reads the graveyard: **Rest in Peace / Grafdigger's Cage turn it
  off.** The deck's answer is its counter suite, plus Vindicate/Void Rend on sight.

## 2026-08-20 — the purchase package lands (8 cards, player-directed; do not cut)
Bought specifically for this deck (Mana Pool order #468964) and placed by the cut
ranking — every outgoing card was unprotected and bottom-of-field. All eight texts
are runner-verified in `data/reference/hobbit-verified-2026-08-20.txt` except Mana
Drain (queued for verification; its text is common knowledge but gets confirmed on
the next runner push). **Bracket 4 is player-ratified** — the `# Bracket: 4` header
records it, and the assess surfaces show it beside the detected estimate.

- **Bloodchief Ascension** (in over Observed Stasis) — the deck's own commander
  advances it: every MV≥3 noncreature spell drains each opponent 2, and "an
  opponent lost 2 or more life this turn" is exactly the quest condition, so it is
  usually online in two-three turns without playing differently. Once live, every
  point of opponent life loss doubles into 2 more plus 2 mill — Blood Artist,
  Vito, Bastion and Y'shtola herself all feed it, and the Seer loop with it on
  board drains the table twice as fast.
- **Ghostly Prison + Norn's Annex** (in over Eye of Nidhogg / White Auracite) —
  the pillowfort. Attackers pay 2 generic (Prison) and {W/P} — 2 life if they
  have no white — per creature (Annex). A go-wide board paying life to attack
  feeds the end-step draw AND Bloodchief. We cut a wipe (Cleansing Nova) on the
  theory that taxed attackers mostly don't come; Toxic Deluge stays.
- **Teferi, Time Raveler** (in over Risky Shortcut) — opponents can only cast at
  sorcery speed: the loop cannot be interrupted by an instant-speed kill spell on
  the Seer, and our own wipes and tutors resolve clean. His -3 bounces a problem
  permanent and draws. MV 3, so casting him drains the table.
- **Grim Tutor** (in over Syphon Mind) — any card to hand for 3 life, and at MV 3
  it triggers Y'shtola on the way. Finds the missing loop piece; second
  unconditional tutor alongside Mystical Tutor.
- **Mana Drain** (in over Cleansing Nova) — Counterspell that banks the countered
  spell's mana for our next main phase: a countered 5-drop pays for Exsanguinate
  or double-spell turns. The counter core is now FoW / Counterspell / Mana Drain /
  Sublime Epiphany.
- **Talion, the Kindly Lord** (in over Dancer's Chakrams) — name a number (3 is
  usually right here); every opponent spell with that MV/power/toughness costs
  them 2 life and draws us a card. Table-wide tax that feeds the end-step draw
  and Bloodchief from OTHER people's turns.
- **Lotho, Corrupt Shirriff** (in over Lethal Scheme) — a Treasure whenever any
  player casts their second spell each turn, including opponents. Quiet ramp that
  banks toward Exsanguinate and keeps counter mana open.

Removal after the swaps: Swords, Infernal Grasp, Snuff Out, Void Rend, Dismember,
Murderous Rider, Vindicate, plus Toxic Deluge. One wipe is deliberate — see
Ghostly Prison above.
