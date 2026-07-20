# Grounding Rules — read first, every session

Every rule here comes from a real mistake made while building these decks. They are the
difference between a trusted advisor and a confident liar. Follow them.

## 1. The collection is the source of truth
A new session does **not** automatically have the collection. Load it before making any
ownership claim (see SKILL.md "Collection access"). The gold-standard format is the
**Archidekt CSV export** with columns: `Quantity, Name, Mana Value, Colors, Identities,
Mana cost, Types, Sub-types, Super-types, Rarity, Scryfall ID`. Verify everything against it.
If you only have a name-only list, you have ownership counts but must look up color/type/MV.

## 2. COUNT the pool; never spot-check staples
The biggest errors came from assuming an archetype had support because a few marquee pieces
existed. Real failures from this project:
- Recommended **The Ur-Dragon** — the player owns only **~10 dragons**.
- Recommended **Squirrel Girl** tribal — the player owns **~2 squirrels**.
- Listed six "staple" creatures for a build the player **did not own**.

**Always filter the collection and count actual cards before claiming support exists.**
Use `analyze_collection.py --subtype Dragon` (etc.). A tribe needs a critical mass of bodies
*and* payoffs, not one legend.

## 3. Verify card text past the knowledge cutoff
The assistant's knowledge is unreliable for recent sets. Post-cutoff sets known to be in this
collection: **Marvel Super Heroes, Marvel's Spider-Man, Secret Lair / Secrets of Strixhaven,
Lorwyn Eclipsed, Final Fantasy (+ Commander), Avatar: The Last Airbender.** For any card from
these — or any card you're not fully certain of — **web-search the oracle text (Scryfall /
Gatherer) one card at a time.** Do not trust memory. Real errors made: assumed the wrong half
of a modal double-faced card, mis-stated mana values, mis-read abilities.

## 4. Do the manabase math against real pip demand
Count colored pips across the nonland cards; count double-pip cards; size color sources to
demand. Cut lands that make zero colored mana toward your deck (a creature-type "any color"
land is a trap if you run ~1 of that creature type). `deck_stats.py` computes pip demand for you.

## 5. Prefer destroy-based wraths when the deck has graveyard synergy
Exile-based board wipes (Final Judgment, Extinction Event) exile creatures and starve
reanimator / graveyard-cast / aristocrats payoffs. If the deck wants its creatures in the
yard, run destroy-based wipes instead. (See `rules-reference.md`.)

## 6. Photos and direct player info outrank search and memory
Several fixes in this project came from the player photographing a card. If the player tells
you or shows you something about a card, trust it over your memory and over search.

## 7. Be honest about tool limits rather than fabricate
See `tooling-and-data.md`. Bulk card APIs and price sites are blocked / login-walled in this
environment. Never invent a live price or a card you couldn't verify. Give labeled *estimate
ranges* for prices. If you couldn't verify a card, exclude it and say why (don't guess it in).

## 8. Surface shared cards — don't block deck creation
Physical decks can't share the same card unless the player owns enough copies (a card in N
decks needs ≥ N owned copies). But **do not refuse to build a deck over this** — the player
wants to see the overlap, not be denied. Track it, mark it, and let them decide.

- **Mark, don't block.** Build the deck the player wants. The dashboard badges every shared
  card (`⇄N`) in the decklist and lists them in a "Shared Across Decks" panel (✓ = enough
  copies owned; ⚠ = would need more to sleeve all decks at once). It's informational.
- **Wishlist the shortfall.** Cards needing extra copies go on the wishlist, not into a wall:
  `python3 scripts/wishlist.py --collection <csv>` writes `data/wishlist.md` (shared copies to
  buy + not-owned cards + buy-list upgrades, priced). Point the player there.
- Optional helpers: `deck_conflicts.py` (see all shared cards), `--buy-doubles` (priced list),
  `--available` (owned minus committed elsewhere) for when the player *wants* disjoint decks.
- If the player says they own something missing from the export, add it to
  `data/collection/owned_additions.txt` — their word outranks the export (rule #6).
