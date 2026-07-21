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

---

## SESSION NOTE — 2026-07-18 (program build + Kaervek v1)

**What changed:** This repo now IS the end-to-end program (skill + scripts + data),
not just notes. See README.md and `.claude/skills/mtg-deckbuilder/`.

**Collection:** Imported from the Google Drive doc `collection_list` →
`data/collection/collection_snapshot.txt` (1,805 unique cards, name-only). The full
Archidekt CSV is still the goal — drop it at `data/collection/collection.csv` to unlock
color/type/tribe/pip analysis and card images.

**Grounding catches this session (verify on CSV load):**
- The "complete" Y'shtola list references 4 cards NOT in the current collection export:
  **The Kingpin of Crime, Vito Thorn of the Dusk Rose, Force of Will, Extinction Event.**
  Either the export predates them or they're tracked elsewhere.
- Handoff claimed **Fiery Emancipation** owned for Kaervek — NOT in the current export.
- Kaervek oracle re-verified: **{5}{B}{R} 5/4**, "Whenever an opponent casts a spell,
  Kaervek deals damage equal to that spell's mana value to any target." (Earlier memory
  of a cheaper 3/3 was wrong.)

**New deck:** `data/decks/kaervek-punisher.txt` — Kaervek Rakdos punisher **v1 draft**,
100% owned cards, ratios ok (37 land / 10 ramp / 10 removal / 3 wipe / ~9 draw). Plays as
group-slug midrange; buy-list to sharpen into a true punisher lives in
`data/staples/kaervek-the-merciless.txt` (owned 39/68; ~29 missing).
Off-color cards excluded during build: **Vindicate (WB), Crush Contraband (W)**.

**New tool:** `scripts/staples_crossref.py` — diff a curated staples list against the
collection → owned vs. missing (buy-list). NOTE: EDHREC/Scryfall direct fetch is
403-blocked here; staples lists are curated from knowledge + web-search summaries, not
live scrapes. Web *search* works; page *fetch* of those sites does not.

**Next steps:** (1) load the CSV and re-run deck_stats on Kaervek to confirm 0 off-color
and get real curve/pips; (2) acquire ~10 punisher engines from the buy-list; (3) explore
the Spider-Man typal idea (needs per-card oracle verification — all post-2025).

---

## SESSION NOTE — 2026-07-18b (pricing CSV wired in)

Player uploaded a **collection + pricing CSV** (`all_my_cards_2.csv`, 2,763 rows,
one per printing, Excel `sep=,` preamble). Installed at `data/collection/collection.csv`
(gitignored — contains purchase prices).

- **Format:** `Folder Name, Quantity, Card Name, Set Code, Set Name, Card Number,
  Condition, Printing, Price Bought, Date Bought, LOW, MID, MARKET`. Has ownership +
  set + prices; **no color/type/mana-value/Scryfall-ID** columns. So it unlocks value
  and per-deck pricing, NOT color/curve/tribe math. For that, still need the
  card-attribute export (Mana Value/Colors/Types/Scryfall ID).
- **Tools upgraded:** mtglib aggregates printings by name and reads prices;
  `analyze_collection.py --value` gives collection value + top cards;
  `deck_stats.py` prints deck MARKET value.
- **Collection value (MARKET):** ~$2,985.74 across 1,916 unique / 2,607 copies.
  Note: some obscure rows are clearly mispriced (e.g. Vine Trellis ~$30) — treat prices
  as rough. Priciest: Rhystic Study (MB1) ~$72, The Mind Stone (MSH) ~$68, Scorched
  Ruins (WTH) ~$66.
- **Deck values:** Y'shtola ~$307, Kaervek v1 ~$94.
- **Discrepancy update:** vs this fresher export, Y'shtola "missing" dropped 4 -> 2.
  **The Kingpin of Crime** and **Extinction Event** now show owned; still missing
  **Vito, Thorn of the Dusk Rose** and **Force of Will**.

---

## SESSION NOTE — 2026-07-18c (Cosmic Spider-Man built)

Player picked **Cosmic Spider-Man** (5-color Spider typal) after a collection-wide
"what commanders should I buy" review.

**Key review finding:** for the deepest themes the player ALREADY OWNS the ideal
commander — Cosmic Spider-Man (Spiders, 57 copies owned), Captain America Team Leader +
Director Nick Fury (Hero typal), Doctor Doom (Grixis villains). Best *buys* are cheap
singles that unlock owned pools: **Teysa Karlov** (~$6, aristocrats — 11/11 sac outlets
owned) and **Alesha** (~$3, Mardu reanimator — 22 recursion pieces owned). Precon buy:
**Doom Prevails** for the villain slice.

**New deck:** `data/decks/cosmic-spider-man.txt` — v1 draft, 100% owned, ~$265 deck value,
37 lands. Verified Spider engine (Scryfall/EDHREC): Silk Web Weaver, Spiders-Man Heroic
Horde (web-slinging → Spider tokens), Ezekiel Sims (+2/+2 a Spider each combat), Sun-Spider,
Spider-UK, SP//dr, Madame Web. Owned typal support: Roaming Throne (doubles a type's
triggers), Kindred Discovery, Door of Destinies, Patchwork Banner, Metallic Mimic, plus
Path of Ancestry / Secluded Courtyard / Unclaimed Territory fixing.
**Caveat:** SPM creature type-lines are reasoned/spot-verified, not fully confirmed — load
the card-attribute CSV to confirm every included card is actually a Spider.
**Buy-list (top Spiders not owned):** Gwenom, Remorseless; Superior Spider-Man.

**Tool tweaks:** added a `spider` dashboard theme; broadened the name-only land heuristic
again (monastery/courtyard/territory/plaza/shrine/peaks/orchard/sanctum...). All four saved
decks now report correct land counts.

---

## SESSION NOTE — 2026-07-18d (dashboards evolved)

`build_dashboard.py` upgraded from a flat page to a sectioned tool:
- Stat tiles now include **deck value**.
- **Game Plan / Player Notes** section (from `<deck>.notes.md`, markdown-lite).
- **Mana Curve (MV spread)** driven by an optional `<deck>.attrs.csv`
  (Name,Type,MV,Colors) — so curve works without the full attribute collection CSV;
  cards lacking MV are honestly noted, not hidden.
- **Buy & Replace** panel with interactive **price-threshold toggle buttons**
  (All / <=$5 / <=$10 / <=$20 / <=$50), running total, from `<deck>.buylist.csv`
  (Card,Price,Tier,Replaces,Reason).
- **Decklist grouped by the deck file's own `# --- Section ---` headers.**
All three companion files auto-detect next to `<deck>.txt`. Cosmic Spider-Man has all
three authored (notes + 13-card buylist + 52-card attrs → curve peaks at MV2).
Other decks render fine without companions (those sections just omit).

---

## SESSION NOTE — 2026-07-18e (Cosmic Spider-Man MV curve completed)

Verified all 31 remaining Spider/equipment mana values from Scryfall (one card per web
search; EDHREC/Scryfall/Draftsim page fetches are 403-blocked, but web SEARCH returns the
Scryfall data snippet reliably). Filled `cosmic-spider-man.attrs.csv` to 83/83 cards →
dashboard curve now "covers all 63 nonland cards" (peaks at MV2 with 22).

**Type findings — 3 included cards are NOT Spiders (won't get Cosmic's combat buff):**
- **Madame Web, Clairvoyant** — Mutant Advisor (still great: casts Spiders off the top).
- **Agent Venom** — Symbiote Soldier Hero (death-draw value, but not a Spider).
- **Flash Thompson, Spider-Fan** — Human Citizen (tap/untap utility, not a Spider).
Note **Spider-Suit** makes its equipped creature a Spider Hero, so it can turn a non-Spider
into a buff target. v2 idea: swap the 3 non-Spiders for owned/bought Spiders (Superior
Spider-Man, Gwenom) to raise Cosmic's hit rate.

---

## SESSION NOTE — 2026-07-18f (bracket, power ranking, conflicts, card images)

Four features added (a research workflow verified the bracket rules + Game Changers list):

- **Card images in the decklist** — `build_dashboard.py` "Decklist by Section" now renders
  Scryfall image-by-name thumbnails (browser-only, as always).
- **Cross-deck conflict checker** — `deck_conflicts.py`: sums each card's usage across all
  `data/decks/*.txt` and flags cards committed to more decks than owned copies (basics exempt).
  Surfaced as a "Cross-Deck Conflicts" dashboard section. NOTE: with 4 decks there are ~37 real
  conflicts (e.g. Solemn Simulacrum owned 1, used in 3 decks). **Run this when building new decks.**
- **Bracket + power ranking** — `power.py`: WotC Commander Bracket (1–5) from Game-Changers count
  + guardrails (tutors are NOT a bracket factor post-Oct-2025), plus a 0–100 power score.
  `--rank` ranks all decks. Reference lists in `data/reference/*.txt`; rubric in
  `docs/power-and-brackets.md`. Current ranking: Y'shtola B3/67, Cosmic B3/57, Kaervek B2/55,
  Cloud B2/51. Y'shtola is AT the 3-Game-Changer ceiling (Mystical Tutor, Force of Will,
  Rhystic Study) — a 4th would make it Bracket 4.
- Game Changers list is the verified 53-card set (2026-02-09; added Farewell + Biorhythm).
  Mana Crypt / Jeweled Lotus are banned, not on it.

Note: `data/collection/collection.csv` (pricing export) has no per-card MV, so only Cosmic
(which has a `.attrs.csv`) gets curve-based power components; others renormalize those out.

---

## SESSION NOTE — 2026-07-18g (no-share rule + buy-doubles / available pool)

HARD RULE added (grounding-rules #8): a card may appear in N decks only if the player owns
≥ N copies. Enforced via `deck_conflicts.py`:
- `--buy-doubles`: priced shopping list to buy the extra copies (keeps all decks optimal).
  Current 4 decks: **42 extra copies, ~$81 total** (mostly <$1 staples; priciest Lightning
  Greaves ~$9.16/2, Plaza of Heroes ~$8.80). Force of Will + Vito are unowned (separate buy).
- `--available [--deck X]`: the buildable pool (owned minus committed elsewhere) — use this
  when building a NEW deck so it never reuses a committed single.

Decision left to the player: BUY the ~$81 of doubles (recommended — no deck degraded) vs.
SWAP shared cards out of the two draft decks (Kaervek/Cosmic) for owned bench cards (would
downgrade those drafts; the collection bench is deep but mostly weaker). Deck files NOT edited
yet — awaiting the player's choice.

---

## SESSION NOTE — 2026-07-18h (surface shared cards + wishlist, not block)

Player preferred surfacing over blocking. Reframed rule #8 from "hard block" to "mark & wishlist":
- **Dashboard**: every card shared with another deck gets a `⇄N` badge in the decklist
  (accent = own enough, warn = need more), and the old "Cross-Deck Conflicts" section is now an
  informational **"Shared Across Decks"** panel (✓ covered / ⚠ need copies). Nothing is blocked.
- **`wishlist.py`** → `data/wishlist.md`: consolidated, priced checklist — shared copies to buy
  (~$80.69 / 40 copies), cards not owned (now 0), and buy-list upgrades (~$173, all from Cosmic).
- Vito + Force of Will confirmed owned via `owned_additions.txt` (merged by load_collection).
Skill/grounding updated to "surface, don't deny." Deck files still unedited.

---

## SESSION NOTE — 2026-07-18i (one-command refresh + buy-lists for all decks)

- **`scripts/refresh.py`**: one command regenerates every deck's dashboard (+ visual gallery,
  themed) and the wishlist. Decks are auto-discovered; title/theme/commander read from
  `# Title:` / `# Theme:` / `# Commander:` headers in each deck .txt. New decks are picked up
  automatically. HTML lands in `build/` (gitignored).
  `python3 scripts/refresh.py --collection data/collection/collection.csv`
- **Buy-lists for all four decks** (`<deck>.buylist.csv`): Cosmic 13, Kaervek 10, Y'shtola 8,
  Cloud 7 = 38 upgrade items (~$402). Wishlist upgrade section now spans all four. Cloud pulls
  the handoff's sword package (SoFF, SoFI, Buster Sword, Sram, Sigarda's Aid); Y'shtola gets
  Cyclonic Rift / Esper Sentinel / Smothering Tithe (noting the Game-Changer bracket bump);
  Kaervek gets the punisher engines (Torment of Hailfire, Fiery Emancipation, Sulfuric Vortex…).
- Added a **rakdos** dashboard theme (Kaervek). Themes now: default / yshtola / cloud / rakdos /
  spider.

---

## SESSION NOTE — 2026-07-18j (local web front end)

Built a Flask web app in `webapp/` over the existing scripts (imported, not duplicated).
- `build_dashboard.generate()` extracted so CLI + app render identical dashboards.
- Pages: Decks (power leaderboard), live per-deck dashboard + visual + inline editor,
  Wishlist, Shared, Collection (value/top cards, upload export, add owned_additions).
- Run: `pip install -r webapp/requirements.txt && python3 webapp/app.py` -> localhost:5000.
  Local-only by design (collection/prices stay on the machine). Verified all routes 200 and
  screenshotted with the pre-installed Chromium.
- Fixed a data bug: kaervek/cloud buy-lists used `\,` to escape commas (invalid CSV) which
  mangled card names — rewrote with proper double-quote quoting.
Flask note: this container's Debian blinker blocks a plain `pip install flask`; a venv (as in
webapp/README) avoids it.

---

## SESSION NOTE — 2026-07-18k (phone access)

Made the web app phone-ready:
- `MTG_HOST` env (default 127.0.0.1); set 0.0.0.0 to allow LAN devices. App prints the
  phone URL (LAN IP) on startup.
- `webapp/run.sh`: one-command venv bootstrap + bind 0.0.0.0 + serve.
- PWA: manifest + spider SVG icon + apple-mobile meta + safe-area insets → installable
  "Add to Home Screen", full-screen.
- Rebuilt the Decks leaderboard as responsive cards (the table clipped action links at
  phone width). Verified at 390px with Chromium screenshots.
- webapp/README documents 3 phone paths: same-Wi-Fi LAN (recommended), tunnel
  (cloudflared/ngrok), deploy (gunicorn+auth+HTTPS; keep collection.csv private).

---

## SESSION NOTE — 2026-07-18l ("this commander would also work")

New feature: `scripts/similar_commanders.py` + `data/reference/commanders.csv` (curated
commander DB: colors + archetype tags). For a deck it ranks alternate commanders that share
the archetype and classifies the COLOR fit honestly:
  drop-in (your 99 stay legal) · tighter (trim off-color) · partial (keep overlap+colorless,
  rebuild rest) · reskin (same idea, new shell). Owned candidates are flagged from the
  collection; where a deck has attrs it shows exact "% of cards stay in color".
Decks tagged with `# Archetype:` / `# Colors:` headers. Surfaced as a "Commanders That Also
Fit This Shell" dashboard section (build_dashboard.generate now returns it; visible in the
web app deck pages too).
Flagship: Cloud (Naya equipment) → The Invincible Iron Man (Izzet) = PARTIAL (shares R);
also surfaces owned Iron Man Armored Avenger + Captain America. Grow commanders.csv over time.
