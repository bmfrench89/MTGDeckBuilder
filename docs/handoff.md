# MTG Commander Deckbuilding — Session Handoff

**Purpose:** This file lets a new Claude session continue building/tuning these Commander decks *without repeating the mistakes made along the way*. Read the "Rules for staying grounded" section first — it is the most important part.

**Player context:** Building EDH decks primarily from an existing collection (minimal buying unless asked). Two decks are complete. The player values honesty about limitations over confident guessing.

---

## ⚠️ RULES FOR STAYING GROUNDED (read first)

These come from real errors made this project. Follow them.

1. **The collection CSV is the source of truth — ask the player to re-upload it.** A new session will NOT have the file. Request the Archidekt collection export (a CSV). It has columns: `Quantity, Name, Mana Value, Colors, Identities, Mana cost, Types, Sub-types, Super-types, Rarity, Scryfall ID`. Everything should be verified against it.

2. **COUNT the pool; never spot-check staples.** The biggest errors came from assuming a card was owned or that an archetype had support because a few key pieces existed. Example failures: recommended **Ur-Dragon** (player owns only **10 dragons**), recommended **Squirrel Girl** (player owns **2 squirrels**), listed six "staple" creatures for Cloud that the player **didn't own**. Always filter the CSV and count actual cards before claiming support exists.

3. **Verify card text for anything past the Jan 2025 knowledge cutoff.** Post-cutoff sets in this collection: **Marvel Super Heroes, Marvel's Spider-Man, Secrets of Strixhaven, Lorwyn Eclipsed, Final Fantasy (+ Commander), Avatar: The Last Airbender.** Web-search the oracle text (Scryfall/Gatherer) — do NOT trust memory. Real errors: assumed the wrong half of an MDFC, mis-stated mana values, mis-read abilities.

4. **Rules facts that were gotten wrong and corrected:**
   - **X spells count X on the stack.** Exsanguinate / Profane Command cast for X≥1 have mana value 3+, so they DO trigger "MV3+" abilities. (Outside the stack, X=0.)
   - **"Cast" triggers resolve even if the spell is countered.** (Y'shtola's damage/lifegain still happens.)
   - **Exile-based wipes anti-synergize with graveyard payoffs.** Final Judgment/Extinction Event exile creatures, starving reanimator/graveyard-cast effects. Prefer destroy-based wipes when the deck has graveyard synergy.
   - **Flashback/MDFC mana value:** flashback doesn't change MV; an MDFC's back-face spell has its own MV.

5. **Do the math on the manabase against actual pip demand.** Count colored pips across the nonland cards; count double-pip cards; cut lands that make zero colored mana (creature-type "any color" lands are traps if the player runs ~1 of that type).

6. **Photos from the player are higher-signal than any search.** Several fixes came from the player photographing cards. Trust them.

7. **Be honest about tool limits (below) rather than fabricate.** If you can't verify a price or a card, say so.

---

## TOOLING CONSTRAINTS (known blockers)

- **Scryfall API and bulk-data downloads are BLOCKED** in the code sandbox (network firewall) and via `web_fetch` (bot detection). You cannot script bulk card lookups.
- **`web_fetch` only accepts URLs that already appeared in a prior search/fetch result.** URLs built from memory are rejected.
- **What works:** (a) the collection CSV, which has MV / color identity / types / **Scryfall ID** per card; (b) `web_search` one card at a time for oracle text; (c) Scryfall *image* hotlinking works: `https://cards.scryfall.io/normal/front/<id[0]>/<id[1]>/<id>.jpg` using the Scryfall ID from the CSV.
- **Card-art HTML won't render in the chat's preview pane** (external images blocked). It only displays in a real browser (Chrome/Safari). Always warn the player.
- **Price sites (TCGplayer/Card Kingdom/MTGGoldfish) are login-walled.** Give clearly-labeled *estimate ranges*, not fake live quotes.

---

## DECK 1 — Y'shtola, Night's Blessed (Esper WUB control/drain) — COMPLETE

**Current file:** `yshtola-deck-v19-FINAL.html` (dashboard). Also `yshtola-synergy-chart.html`.

**Commander (verified oracle text):** {1}{W}{U}{B}, 2/4 Cat Warlock, Vigilance.
- "At the beginning of each end step, if a player lost 4 or more life this turn, you draw a card."
- "Whenever you cast a noncreature spell with mana value 3 or greater, Y'shtola deals 2 damage to each opponent and you gain 2 life."
- **Ruling:** the cast trigger resolves even if the spell is countered.

**The engine:** cast MV3+ noncreature → 2 dmg each opp + gain 2 → "amplifiers" convert lifegain into damage → any player losing 4+ triggers card draw. ~53% of nonland cards trigger the commander.

**Key amplifiers (lifegain → damage):** Vito Thorn of the Dusk Rose, Defiling Daemogoth (mono-black, end-step drain = life gained), Witch of the Moors (repeating edict on lifegain), The Kingpin of Crime (Extort), Blood Artist, Bastion of Remembrance, True Conviction.
**Free spells (0-mana triggers on others' turns):** Force of Will, Misdirection, Snuff Out, Reverent Mantra (exile a white card instead of paying).
**Graveyard payoffs (want DESTROY wipes, not exile):** Sepulchral Primordial, Diluvian Primordial (casts opponents' instants/sorceries → re-triggers Y'shtola), Sun Titan + Serra Paragon + Sevinne's Reclamation (rebuy ~61% of the deck, all MV≤3 permanents + lands).
**Finisher:** Exsanguinate (each opp loses X, you gain the TOTAL across the table — Vito/Daemogoth convert it).

**Nonland (62):** Blood Artist, Baleful Strix, Murderous Rider, The Kingpin of Crime, Archmage Emeritus, Emet-Selch of the Third Seat, Fandaniel, Telophoroi Ascian, Vito, Thorn of the Dusk Rose, Solemn Simulacrum, Defiling Daemogoth, Serra Paragon, Witch of the Moors, Archfiend of Depravity, Sun Titan, Diluvian Primordial, Sepulchral Primordial, Torrential Gearhulk, Mystical Tutor, Swords to Plowshares, Counterspell, Infernal Grasp, Absorb, Sphinx's Revelation, Void Rend, Soul Shatter, Snuff Out, Lethal Scheme, Reverent Mantra, Force of Will, Misdirection, Sublime Epiphany, Dig Through Time, Exsanguinate, Profane Command, Syphon Soul, Toxic Deluge, Vindicate, Sevinne's Reclamation, Ambition's Cost, Extinction Event, Rite of Replication, Time Wipe, Rhystic Syphon, Cleansing Nova, Construct a Cosmic Cube, Authority of the Consuls, Staggering Insight, Rhystic Study, Bastion of Remembrance, Propaganda, The Death of Gwen Stacy, True Conviction, Sol Ring, Commander's Sphere, Arcane Signet, Talisman of Dominance, Talisman of Hierarchy, Fellwar Stone, Thought Vessel, Lightning Greaves, Archaeomancer's Map, Relic of Legends

**Lands (37):** Command Tower, Path of Ancestry, Exotic Orchard, Arcane Sanctum, Plaza of Heroes, Spire of Industry, Choked Estuary, Darkwater Catacombs, Drowned Catacomb, Glacial Fortress, Isolated Chapel, Underground River, Port Town, Sunken Hollow, Prairie Stream, Skycloud Expanse, Fetid Heath, Sunken Ruins, Desolate Mire, Shineshadow Snarl, Contaminated Aquifer, Sunlit Marsh, Idyllic Beachfront, Fabled Passage, Terramorphic Expanse, Ash Barrens, Bojuka Bog, Irrigated Farmland, High Market, Island x3, Swamp x3, Plains x2

**Manabase note:** pip demand ≈ B43 / U33 / W24; ~26 double-pip cards; sources W22 / U25 / B25. High Market added as a sac outlet (feeds Blood Artist / saves Y'shtola from exile). Emeria the Sky Ruin was rejected (needs 7 Plains; deck has 5 Plains-typed).

---

## DECK 2 — Cloud, Ex-SOLDIER (Naya RGW equipment) — COMPLETE

**Current file:** `cloud-deck.html` (dashboard), `cloud-deck-visual.html` (card images), `cloud-synergy-chart.html`, `cloud-buy-list.html`.

**Commander (verified oracle text):** {2}{R}{G}{W}, 4/4 Human Soldier Mercenary, Haste.
- "When Cloud enters, attach up to one target Equipment you control to it."
- "Whenever Cloud attacks, draw a card for each equipped attacking creature you control. Then if Cloud has power 7 or greater, create two Treasures."

**The engine:** arm the board → swing → draw a card per equipped attacker → reload off Treasure. Puresteel Paladin (metalcraft = free equip) is the multiplier. Colossus Hammer + free-equip + evasion = one-shot commander kill.

**Known weakness (already flagged to player):** thin on dedicated equip-carriers (owns only Puresteel Paladin + Armory Automaton) and card draw (3 engines). Leans on Cloud himself. Buy list addresses this.

**Equipment (14):** Colossus Hammer, Hard-Won Jitte, Sword of the Animist, Behemoth Sledge, Conqueror's Flail, Champion's Helm, Darksteel Plate, Mask of Memory, Lightning Greaves, Trailblazer's Boots, Mjölnir, Hammer of Thor, Hero's Blade, Bitterthorn, Nissa's Animus, Hero's Heirloom

**Equipment support (4):** Puresteel Paladin, Armory Automaton, Inspiring Statuary, Steelshaper's Gift

**Creatures (21):** Llanowar Elves, Elvish Mystic, Gilded Goose, Sakura-Tribe Elder, Priest of Titania, Selfless Spirit, Skyclave Apparition, Solemn Simulacrum, Sun Titan, Emeria Angel, Tectonic Giant, Combustible Gearhulk, Bronze Guardian, Karmic Guide, Ohran Frostfang, Thor, Asgard's Avenger, Hercules, Olympian Hero, Tendershoot Dryad, Hellkite Tyrant, Storm, Windrider, Guardian Scalelord

**Ramp (9):** Sol Ring, Arcane Signet, Commander's Sphere, Fellwar Stone, Cultivate, Farseek, Rampant Growth, Nature's Lore, Relic of Legends

**Removal & wraths (10):** Swords to Plowshares, Path to Exile, Generous Gift, Beast Within, Chaos Warp, Blasphemous Act, Vandalblast, Cleansing Nova, Austere Command, Vanquish the Horde

**Card draw (3):** Skullclamp, Tome of Legends, Staff of the Storyteller

**Anthems & finish (2):** Rancor, True Conviction

**Lands (36):** Command Tower, Path of Ancestry, Exotic Orchard, Sacred Peaks, Jungle Shrine, Rugged Prairie, Battlefield Forge, Clifftop Retreat, Sunpetal Grove, Rootbound Crag, Game Trail, Fortified Village, Furycalm Snarl, Frostboil Snarl, Sungrass Prairie, Canopy Vista, Cinder Glade, Prairie Stream, Fabled Passage, Terramorphic Expanse, Evolving Wilds, Ash Barrens, Myriad Landscape, Radiant Grove, Wooded Ridgeline, Forest x6, Mountain x2, Plains x3

**IMPORTANT — deck separation:** Player wanted Cloud built WITHOUT taking single copies from the Y'shtola deck. The ~11 shared staples (Sol Ring, Swords to Plowshares, Arcane Signet, Sun Titan, Solemn Simulacrum, Lightning Greaves, Commander's Sphere, Fellwar Stone, Relic of Legends, Cleansing Nova, True Conviction) are covered by the player's **2nd copies** (they own multiples of all precon commons/staples). Confirmed OK.

**Buy list (in `cloud-buy-list.html`):** tiers of upgrades, cap of $50/card. Headliners: Buster Sword (Cloud's card, +3/+2 + draw + free spell on hit), Sword of Fire and Ice, Sword of Feast and Famine, Sram Senior Edificer, Sigarda's Aid. Prices are early-2026 ESTIMATES.

---

## FILE INVENTORY (in /mnt/user-data/outputs, but a new session starts empty)

A new session will NOT have these files. The player has them saved. If they want edits, they may need to re-share a file or you rebuild from the lists in THIS document.

- Y'shtola: `yshtola-deck-v19-FINAL.html` (current), `yshtola-synergy-chart.html`, plus superseded v2–v18 + buy list.
- Cloud: `cloud-deck.html`, `cloud-deck-visual.html`, `cloud-synergy-chart.html`, `cloud-buy-list.html`.

**Visual style used:** Y'shtola = dark FFXIV Esper aesthetic (void #0B0E1A, aether cyan #5BE0D4, blood #C2415C, gold #D9B26A; fonts Cormorant Garamond / Barlow Condensed / IBM Plex Mono). Cloud = "Mako" Naya aesthetic (steel #0E1214, mako green #39E0B0, fire #E86A3A, gold #E8B84B; fonts Oswald / Rajdhani / JetBrains Mono). Dashboards are self-contained single HTML files, no external images except the explicit "visual deck" files.

---

## OTHER DECKS THE COLLECTION SUPPORTS (verified by counting)

Ranked by actual support depth, not vibes:
1. **Cloud / Tifa — Naya equipment** (32 equipment owned) — DONE (Cloud).
2. **Kaervek the Merciless — Rakdos punisher** (336 BR creatures; owns Dictate of the Twin Gods, Fiery Emancipation, Spiteful Visions, Theater of Horrors).
3. **Isperia — Azorius fliers/control** (deep, but only ~5 counterspells owned — counter-light).
4. **Yahenni — mono-black aristocrats** (owns Blood Artist/Zulaport/Bastion but only ~5 sac outlets + 3 drain payoffs — engine needs topping up).
- **NOT well supported without buying:** anything mono-green or Squirrel Girl (green depth is old commons; ~2 squirrels; 2 token doublers; almost no finishers). Ur-Dragon (only 10 dragons).

---

## SUGGESTED NEXT STEPS / OPEN ITEMS

- If continuing Cloud: apply the buy-list swaps once cards are acquired; regenerate dashboard + chart as v2.
- If starting a new deck: **first re-request the collection CSV, then COUNT the relevant pool before recommending anything.**
- One unresolved card from the Y'shtola audit: **Mysterio's Mirage** text was never verified (search failed). Excluded rather than guessed. Revisit only if the player asks.
