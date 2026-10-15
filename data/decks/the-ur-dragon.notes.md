# The Ur-Dragon — game plan

Rebuilt from scratch on 2026-10-14 against the **full collection database** (the app's
export: 3,315 unique cards, 4,632 copies, enriched 3,314/3,315 from Scryfall the same day).
The old list was built on an incomplete collection and was deleted, not upgraded.

## The engine

**Verified commander text** (Scryfall, `carddb.py --verify`, 2026-10-14):

> The Ur-Dragon — {4}{W}{U}{B}{R}{G} — Legendary Creature — Dragon Avatar — 10/10
> Eminence — As long as The Ur-Dragon is in the command zone or on the battlefield, other
> Dragon spells you cast cost {1} less to cast.
> Flying
> Whenever one or more Dragons you control attack, draw that many cards, then you may put a
> permanent card from your hand onto the battlefield.

The deck does not need to cast the commander. Eminence works **from the command zone**, so
every dragon is a mana cheaper from turn one. Stack it with Dragonspeaker Shaman (-2) and
Sarkhan, Soul Aflame (-1) and a five-drop dragon costs two. Once any dragons attack while the
Ur-Dragon is out, each attacker is a card, and the free permanent drop puts the best dragon in
hand into play.

**Roaming Throne (pinned to this deck) names Dragon.** The Ur-Dragon's attack trigger is the
Ur-Dragon's own triggered ability, so the Throne makes it trigger twice: draw twice, and drop
two permanents. Miirym, Dragon Tempest, Scourge of Valkas, Ganax and Lathliss all double too.

**Ganax, Astral Hunter** makes a Treasure whenever a Dragon enters: ramp that pays for the
next dragon. Brainstealer Dragon, Dragon Broodmother (a 1/1 Dragon every upkeep, each
player's), Lathliss's 5/5 tokens and Miirym's token copies widen the attack, and every extra
attacker is one more card off the Ur-Dragon.

**Draconic Visitor is deliberately OUT.** Next to Ganax it is a mandatory loop: Ganax's
Treasure becomes a 5/5 Dragon, that Dragon entering triggers Ganax again, and neither
ability has a "may". Commander Spellbook lists the pair as a combo whose results include
"Draw the game", and CR 104.4b agrees (retrieved 2026-10-14): a loop of mandatory actions
"with no way to stop" is a draw (also 732.4). It is also a two-card infinite, which Bracket 3
does not allow. Do not add it back while Ganax is in the deck.

**Extra combats:** Scourge of the Throne untaps everything for a second combat when it
attacks the player with the most life. That is a second Ur-Dragon trigger.

**Damage on entry:** Scourge of Valkas (damage equal to dragons you control when a dragon
enters), Lathliss, Dragon Queen (a 5/5 token whenever a nontoken Dragon enters), Lozhan,
Dragons' Legacy (damage equal to the mana value of each Dragon you cast, to any target that
isn't a commander), Hellkite Courser (puts the commander in play from the command zone with
haste until the end step: an Ur-Dragon attack trigger without paying 9). Neriv doubles
the damage of creatures that entered this turn; with Samut, Rhythm of the Wild or Lightning Greaves
granting haste, that is the turn's attack.

**Dragonlord Kolaghan gives every Dragon haste** (2026-10-15, the player's call; it replaced
Niv-Mizzet, Visionary, which the player had approved on 2026-10-14). Verified text: "Flying,
haste. Other creatures you control have haste. Whenever an opponent casts a creature or
planeswalker spell with the same name as a card in their graveyard, that player loses 10
life."

The Ur-Dragon draws when Dragons attack, so haste is card draw here.
- **Same-turn attacks:** every Dragon that lands can attack the same turn, so the trigger
  (draw that many, then put a permanent onto the battlefield) fires a turn earlier.
- **It's a Dragon itself:**
  - Eminence makes it cost {3}{B}{R}.
  - Lozhan deals 6 as you cast it.
  - Lathliss makes a 5/5 token, and the token gets haste from Kolaghan.
  - Dragon Tempest and Scourge of Valkas fire when it enters.
  - Neriv doubles the damage of Dragons that entered this turn, and Dragon Tempest's
    damage comes from the entering Dragon (Scryfall ruling, 2017-11-17).
- **Haste from more than one card:** Samut, Temur Ascendancy, Rhythm of the Wild, Lightning
  Greaves and Dragon Tempest also give it. Kolaghan is the one that survives a Samut kill and
  counts as a Dragon.
- **Its last ability:** rarely matters in singleton Commander. The opponent needs a second
  card with the same name in their graveyard.
- **The cost:** Niv-Mizzet turned Lozhan's, Tempest's and Scourge's face damage into cards.
  That damage still happens, but no longer draws. The classifier's draw count fell 6 → 5,
  and Consecrated Sphinx is earmarked for the player's planned Ur-Sphinx deck. When it
  leaves, the replacement should be a draw piece, ideally a Dragon.

**Win conditions:** a wide flying board, plus **Call the Spirit Dragons** — dragons become
indestructible, and an upkeep with five dragons, one of each colour, all getting a counter wins
the game. Its five pips are why the manabase leans on any-colour lands.

## Protected engine (don't cut; discounts, trigger doublers, haste, Dragon payoffs and the alt win)
- Dragonspeaker Shaman
- Sarkhan, Soul Aflame
- Roaming Throne
- Miirym, Sentinel Wyrm
- Dragon Tempest
- Scourge of Valkas
- Ganax, Astral Hunter
- Lathliss, Dragon Queen
- Brainstealer Dragon
- Dragon Broodmother
- Scourge of the Throne
- Lozhan, Dragons' Legacy
- Hellkite Courser
- Neriv, Heart of the Storm
- Dragonlord Kolaghan
- Samut, Hazoret's Champion
- Rhythm of the Wild
- Temur Ascendancy
- Tiamat
- Call the Spirit Dragons

## Interaction (read from verified text, not the role counter)

The optimizer's classifier counts 6 removal and 1 wipe. That undercounts, because the
creature-based answers are invisible to it:
- **Spot removal:** Swords to Plowshares, Path to Exile, Beast Within, Chaos Warp,
  Assassin's Trophy, Anguished Unmaking.
- **On a body:** Steel Hellkite (X: destroy each nonland permanent with MV X of a player it hit),
  Dragonlord Silumgar (steals a creature or planeswalker), Ureni, the Song Unending (X damage
  divided, X = your lands), Vaevictis Asmadi (each player sacrifices a permanent you target),
  Scalelord Reckoner (punishes targeting a Dragon), Marang River Regent (bounces two).
- **One-sided wipes:** Crux of Fate (choose non-Dragons) and Scavenger Regent's Omen,
  Exude Toxin (each non-Dragon creature gets -X/-X).
- **Counters:** Counterspell, Mana Drain.
- **Protection:** Heroic Intervention, Boros Charm, Lightning Greaves, and Call the Spirit
  Dragons' indestructible.

## Manabase — protected

The optimizer values a land by its EDHREC inclusion, and EDHREC lists basics at 76-85% and
these duals at 0%, so on its own it would trade nine of them for basics. In a five-colour deck
that is backwards. These are deliberate and stay:

- Command Tower
- Exotic Orchard
- Path of Ancestry
- Reflecting Pool
- Haven of the Spirit Dragon
- Maelstrom of the Spirit Dragon — also tutors a Dragon
- Horizon of Progress — any colour a land of yours could make
- Rumble Arena
- Jungle Shrine
- Thriving Bluff
- Cinder Glade
- Canopy Vista
- Prairie Stream
- Smoldering Marsh
- Rootbound Crag
- Sunpetal Grove
- Sulfur Falls
- Sheltered Thicket
- Thundering Falls
- Willowrush Verge
- Sunbillow Verge
- Battlefield Forge
- Sulfurous Springs
- Underground River
- Caves of Koilos
- Turbulent Fen
- Turbulent Shore
- Turbulent Wetlands
- Turbulent Crater

The battle lands, the Turbulent lands, Sheltered Thicket, Thundering Falls and Smoldering Marsh
carry basic land types, so **Farseek finds 15 lands** and Nature's Lore 7. The Turbulent lands
enter untapped once opponents control eight or more lands.

**Rejected on verified text:** Avengers Tower (Hero spells only), Castle Doom (artifact spells
only), Jasmine Dragon Tea Shop (Allies only), Villainous Hideout (Villains only). Each looks like
an any-colour land and is not one for this deck.

## Card choices worth knowing

- **Dragonhawk, Fate's Tempest over Hellkite Tyrant:** Dragonhawk exiles X cards to play, where
  X is your creatures with power 4 or more, which is nearly every creature here. Tyrant's
  artifact theft does little in this deck.
- **Samut, Hazoret's Champion over Dragonlord Ojutai:** {1}{R}, "Creatures you control have
  haste." Every dragon attacks the turn it lands (an Ur-Dragon trigger right away), and it turns
  on Neriv's double damage. A Reality Fracture card, so ~0% field: a coverage gap, not a verdict.
- **Thriving Bluff as the 37th land** (it went in over Lozhan, which came back for Draconic
  Visitor). A/B over 3,000 paired games: screw 15.6% -> 14.1%, keepable 79.6% -> 80.5%, clock
  unchanged.
- **Mana Drain, Grim Tutor and Insatiable Avarice:** the player moved these into the Ur-Dragon
  box (2026-10-12). Y'shtola gave up her two in exchange for Absorb and Diabolic Tutor
  (2026-10-14), so no conflict remains.
- **Tiamat (68% field; the player owns one, confirmed 2026-10-14):** cast, not cheated in, it
  fetches up to five different Dragons into hand. Cast it for the "if you cast it" trigger —
  Ureni's or the Ur-Dragon's free put-into-play does NOT trigger it. Good five: whatever closes
  the game this turn (Scourge of the Throne, Lathliss, Miirym, Atarka, Dromoka) or rebuilds after
  a wipe. It came in over Breaching Dragonstorm (12%) on the optimizer's own swap.
- **Grim Tutor / Insatiable Avarice targets:** Dragon Tempest early, Call the Spirit Dragons or
  Roaming Throne once the board is up, Crux of Fate when behind.
- **Enlightened Tutor: not here, by the player's choice (2026-10-14).** It would be strong
  (finds Dragon Tempest, Call the Spirit Dragons or Roaming Throne for {W}). But the player's
  one copy is sleeved in their Giada deck and stays there. Don't propose it again unless they
  buy a second (~$32, estimate).
- **2026-10-14 reads, judged:**
  - Bench: Stubborn Denial (ferocious is nearly always on, but the counter suite is full),
    Smaug Wicked Worm (Treasure draw with Ganax), Majestic Genesis (reveals 9 off the
    commander's MV, but 8 mana and not a dragon), Lorehold the Historian, Abrade.
  - Skip: Crop Rotation (a Game Changer for a land), Shimmer Dragon (no artifact count),
    Blasphemous Act (kills our own dragons; Crux of Fate is the one-sided wipe), Hellkite
    Tyrant, Clear, Cloud's Limit Break.

## What the numbers say (2026-10-14)

- **Bracket 3.** One Game Changer (Consecrated Sphinx), two tutors plus Tiamat, no fast mana,
  no two-card infinites (Commander Spellbook, re-checked 2026-10-15 with Dragonlord Kolaghan in: 0 present).
- **Field:** 22 of EDHREC's top 25 for The Ur-Dragon (51,370 decks). The three missing are not
  owned: Terror of the Peaks, Old Gnawbone, Goldspan Dragon. They are the buy list.
- **Goldfish** (3,000 games): keepable 81%, screw 14%, first combat lethal median turn 9 (25% by turn 8).
  It **understates** this deck: it does not model fetch effects (Farseek, Nature's Lore,
  Rampant Growth and Cultivate find no land in the sim), Ganax Treasures, Lathliss
  tokens, the Ur-Dragon's draw, or Roaming Throne. The deleted old list simmed slightly faster
  (35% vs 25% lethal by turn 8) on cheap vanilla bodies; this list traded those for interaction
  the goldfish cannot credit.
- **Colour:** red carries the deck (19+ sources; Scourge of Valkas and Dragon Broodmother want
  RRR). The UU and BB spells are late-game cards here, not turn-two plays.
