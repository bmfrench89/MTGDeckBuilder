# Collection rebuild: sub-tabs and one search language (spec, 2026-10-14)

The player asked: "The collection page is cluttered with too many tiles before you
actually get to collection. Maybe we add in sub tabs or another way to organize things.
I also want the connection [collection] filter to be upgraded to match competitors."

The research is `docs/research-collection-2026-10.md`. It covers nine rival apps,
Scryfall's syntax, mobile filter studies, what players ask for, and a timed phone audit
of this page. This spec replaces Wave 2.1 of `docs/spec-ux-refresh.md`.

## 1. What the audit measured (412 px phone, 3,294 cards, 12 decks)

- **The first card was 3.9 screens down**, or 4.55 once Recent changes filled. Six
  blocks of admin and intake sat above the search box.
- **The page was 11,003 elements and 1.23 MB**, and the grid was 98.5% of it.
- **Every sort froze the page for 4–6 s** (17–29 s with the CPU throttled).
  - Cause: a document-wide observer (fixed in #194).
- **Search matched names only.**
  - "dragon" found 12 of the 53 Dragons.
  - "sol" put Sol Ring 13th.
  - "solring" and "ur dragon" found nothing.
- **The colour buttons silently meant "fits this identity".** Colourless and unknown
  cards passed every pick.
- **"In a deck" counted study lists** (fixed in #194).
- **There was no "free copy" filter at all.**
  - That filter is the most requested collection feature on Moxfield and Archidekt.
  - None of the nine rivals has it.
  - This app already computes it (`deck_conflicts.available_pool`).
- **Filters reset on Back**, and a search that found nothing showed a bare "0 cards".

## 2. Decisions

1. **Three sub-tabs, each with its own URL.**
   - Tabs: **Cards** (`/collection`, the default), **Add** (`/collection/add`) and
     **Manage** (`/collection/manage`).
   - They are ordinary links. The current tab is marked by underline and weight, not
     colour alone.
   - Why links: Back, reload, bookmarks and the planned share target keep working.
   - Why not in-page tabs: NN/g's warning about mixing navigation with view switching.
   - Why not a "Manage" disclosure under the cards: it still ships the admin markup and
     gives intake no address.
2. **One query string carries every filter.**
   - Chips write terms into it, and typed terms become chips.
   - The URL carries it, and the CLI and the skill take the same text.
   - The forms stay the front door; the syntax is the layer underneath, never a test the
     household must pass.
3. **The engine lives in `scripts/`, evaluated on the server.**
   - It is `collection_query.py`, stdlib only.
   - A JavaScript copy would drift from the parser the skill uses.
   - Sending the whole collection to the page is what made it heavy.
4. **Honest about missing data.**
   - Every condition is true, false or unknown.
   - Unknown rows are left out and counted ("12 skipped: no type data yet").
   - A typo warns and is ignored; it is never a silent zero.
5. **Basics are unlimited, and study lists hold no physical cards.** The repo's own rules
   (CLAUDE.md, grounding rule 9) apply to search exactly as they apply to the conflict
   scan.

## 3. Part B1: the query engine (`scripts/collection_query.py`)

### Grammar

The grammar is a Scryfall-compatible subset:
- Implicit AND; `or`; parentheses.
- A leading `-` negates, and `not:x` means `-is:x`.
- `"phrase"`, `!"Exact Name"` and `/regex/`.
- **AND binds tighter than OR**, as on Scryfall (Cockatrice reverses it).
- iOS smart quotes are folded.

Half-typed input is closed or dropped quietly: a dangling `or`, an open quote or
parenthesis, or an empty `t:`.

### Keywords

The table is `collection_query.KEYWORDS`, and the help sheet is generated from it.

| Keyword (aliases) | Means | Notes |
|---|---|---|
| words | All words in the name; `solring` matches by compact form | Ranked best match first: exact, then a phrase prefix, then whole-word prefixes |
| `t:` `type:` | A word on the type line | See "Type lines" below |
| `c:` `color:` | Colours: `:`/`>=` at least, `=` exactly, `<=` within, `c:c` colourless, `c:m` multicolour, guild/shard names, counts | Read from the **mana cost** |
| `id:` `ci:` `identity:` `commander:` | Colour identity: `:`/`<=` within (Scryfall's coverage reading), `>=` includes, `=` exactly | Unknown on name-only rows |
| `mv` `cmc` | Mana value, `even`, `odd` | |
| `pow` | Printed power | Vehicles too; a `*` power is unknown |
| `r:` `s:` `cn:` | Rarity (ordered), set, collector number | Only where the export supplies them |
| `usd` `value` | Estimated price per copy, and copies × price | Labelled estimates |
| `produces:` | Mana the card taps for | Unknown before production enrichment |
| `is:` | commander, legendary, gamechanger, fastmana, tutor, extraturns, mld, spell, permanent, basic, multicolor, mono, colorless, **new**, **free**, **pinned**, **shared**, banned | |
| `has:` | types, price, date, production | Always known; `-has:price` finds the unpriced |
| `role:` | ramp, rock, dork, fetch, draw, removal, wipe, counter, tutor | Heuristic (`classify`, flags, power tags) |
| `qty` | Copies owned | Basics: unlimited |
| `free` | Copies outside every sleeved deck and pin | Basics: unlimited |
| `decks` | Sleeved decks using it; `decks=0` means in no deck | `in:deck` is an alias |
| `deck:` | In one saved deck, by file name, title or commander | Study lists included: it asks what a list contains |
| `for:` | Fits that deck's `Colors` line | |
| `added` | `2026-10-01`, `2026-10` or `2026`, with comparisons | Undated rows are unknown |
| `f:` `legal:` `banned:` | Commander legality (`banned.txt`) | Other formats warn |
| `o:` `oracle:` | — | Warns: rules text isn't stored; suggests `role:` |
| `order:` `direction:` | name, mv, color, type, rarity, set, usd, value, qty, free, decks, added, power | Unknown values always sort last |

### Where the engine departs from the research report

- **`is:new` uses 30 days, not 14.** That is the window the Add tab's New arrivals review
  already uses, so the two can't disagree.
  - Undated cards count as older. The arrivals review already treats them that way.
  - `added` comparisons, by contrast, report undated rows as unknown.
- **`is:shared` follows this app's Shared page**: in more sleeved decks than copies owned.
- **A pin reserves one copy.** It is subtracted from `free` only when the pinned deck
  doesn't already list the card; otherwise the deck's own line already counts it.

### Type lines (tri-state)

carddb writes ONE main type per enriched card: the first of land, creature,
planeswalker, battle, artifact, enchantment, instant, sorcery. On such a row:
- a main type **earlier** in that order is known absent;
- a **later** one may have been dropped, so it reads as unknown ("only the main type is
  known");
- supertypes are unknown.

A row has its **whole** type line when any of these holds:
- it carries a supertype;
- it lists two or more main types;
- the collection carries supertypes at all and the row has a rarity (a rich-export row).

On the server that covers the export's rows. Batch-added rows, and every row in a
sandbox on the committed snapshot, are "main type only".

`t:legendary` on a collection with no supertypes says it can't be answered, instead of
answering 0.

### Colours come from the mana cost

`Card.colors` can't be trusted for this. The attrs overlay fills an empty export Colors
cell with the identity, so every dual land read as white and blue.

The engine therefore reads colours as follows:
- **From the front face's cost.** Split cards count their first half; devoid cards are
  the known miss.
- **A costless land** is colourless.
- **A costless nonland** takes its identity, which is its colour indicator.

### Other behaviour

- **Records are memoised by the app** and rebuilt when any input file changes. On 3,294
  cards the build takes 180 ms, and queries take 1–10 ms.
- **CLI:**
  - `analyze_collection.py <coll> --query "…" [--order X] [--group type|color|mv|role|deck|added] [--list|--json]`
  - `--query-help` lists every keyword.
  - The CLI now also reads the collection database.
- **Tests:** `tests/test_collection_query.py` pins the measured cases:
  - `sol` ranks Sol Ring first; `solring` and `ur dragon` find their cards;
  - `t:dragon` counts every Dragon and counts what it skipped;
  - free green ramp is reachable both ways (`id<=g` and `id>=g`);
  - colours come from the cost;
  - study lists, pins and basics;
  - precedence, half-typed input, typos;
  - order and direction, chips, help examples, the CLI.

On the audit's copy of the collection: `t:dragon` gives 53 (47 rows skipped: no card
data). `id<=g role:ramp free>0` gives 70 and `id>=g role:ramp free>0` gives 47, the
research's two answers.

## 4. Part B2: the page

### Cards (`/collection`)

**Layout, top to bottom (target: the first row on the first screen):**
- **A sticky search bar:**
  - a field that takes the query;
  - a "Filters (n)" button that opens a full-height `<dialog>`;
  - a "?" help button that opens a sheet generated from `KEYWORDS`.
- **One row of single-select scope chips:** All · Free · In decks · Not in a deck ·
  Pinned · Shared. These are query terms, so they compose with everything.
- **Applied-term chips:**
  - Each is a server-built link that removes its own text (`Result.chips`).
  - An OR group is one chip.
- **One summary line, the page's only `role="status"`:**
  - It reads like "70 cards · identity within G · role ramp · free copies > 0 ·
    3 skipped: …".
  - Warnings sit beneath it.
- **Sort** (with a direction toggle), **Group** (type, colour identity, mana value,
  role, deck, month added) and **List | Grid**.
- **The list:**
  - The default view on phones.
  - Rows show a thumbnail, the name, qty and free count, cost pips, the type and deck
    chips.
  - Group headers carry their count, copies and free copies.
- **Paging:** 100 rows, then a real `?n=200` "Load more" link. Script upgrades it to
  append in place and rewrite the URL, so Back returns to the same depth. The page shows
  "Showing 100 of N".
- **No results:** the summary says why, offers a "did you mean" on names, a link that
  clears the filters, and a link to search Scryfall.
- **The foot of the page:** "Every change is logged · last backup <date> · History"
  links to Manage.

**The filter dialog:**
- Its form fields compose into the query **on the server** (`/collection?…&f_*=`).
- A live "Show N cards" button uses `/api/collection/count`.
- It closes on Escape, ×, or the back gesture. Focus moves to its title on open and back
  to Filters on close.

**Styling:**
- `content-visibility: auto` on rows.
- Every chip and control is at least 44 px (`--target`).
- Colour buttons carry text names and `aria-pressed`.

### Add (`/collection/add`)

Moved here unchanged:
- Add a batch.
- Add one card.
- Merge (database) or Replace (files) an export.
- The New arrivals review.

The existing `POST /collection/add` keeps its URL; a `GET` on the same path now renders
the tab.

### Manage (`/collection/manage`)

Moved here:
- "Your collection lives here": the downloads, the start-up report and the backup.
- "Change a card's count".
- Recent changes.
- The card-database status.
- The reconcile offer. The Manage tab wears a badge while it waits, so the offer is
  never buried.

Every form here redirects back to Manage. The card panel's quantity stepper is a Wave 2
extra.

### Removed

- **The 3,294-tile all-at-once grid.** The grid view now pages like the list.
- **"Most valuable cards"**, replaced by `order:value`.
- **The "Most played (EDHREC)" sort.** It fired 44 Scryfall POSTs on every visit. It
  returns once enrichment stores the rank (see Later).

### UAT

- **`flows.js` F13:** the timed sort now drives the new Sort control, and fails over
  2.5 s.
- **New `F14`:** query, scope chip, Load more, Back keeps depth and filters, sub-tabs,
  filter dialog.
- **`sweep.js`:** covers the three tabs.
- **`upgrade.js`:** must PASS.

### As built (2026-10-14)

Measured on a 412 × 915 phone against a scratch copy of the same 3,294 cards:

| | Before | After |
|---|---|---|
| First card | 3,572 px down (3.9 screens) | 426–478 px (the first screen) |
| Page | 11,003 elements, 1.23 MB | about 1,870 elements, about 90 KB for 100 rows |
| Sort | 4.4–6.6 s (after #194: about 0.6 s) | 115–145 ms, a server round trip |
| Query | — | 1–10 ms; the records are rebuilt after a write (about 180 ms) |

Details that differ from the plan above, or that it left open:

- **Status messages.**
  - The summary line is plain text inside the results.
  - A visually hidden `role="status"` region announces live-search and Load-more
    results, so a re-rendered region never steals or loses the announcement.
- **Live search.**
  - Typing swaps in `/collection/results` after 300 ms. That is the same partial a
    reload renders.
  - The URL is replaced, never pushed, so Back never shows a URL whose results aren't on
    screen.
- **The Filters sheet:**
  - It reads the query's sheet-shaped top-level terms back into its fields and carries
    every other term through untouched as `q_rest`. If that rest is an OR, it is
    wrapped in parentheses before the sheet's terms are added.
  - It shows a live "Show N cards" or "No cards match".
  - Its history entry is popped before the form navigates, so Back never lands on a
    duplicate page.
  - Without JavaScript, `?filters=1` / `?help=1` render the sheet open.
- **List and Grid are one markup.** CSS lays the same rows out as card images.
  - The choice is remembered per device and applied before paint.
  - Images resolve by name in batches of 75, only near the screen.
  - Rows with a Scryfall id skip that and use the CDN URL directly.
- **On a phone:**
  - The six scope chips are compact and wrap rather than scroll, so Shared is never
    hidden past the edge.
  - A row hides its cost pips and keeps the name, type line and counts.
- **Sorting.**
  - "Most played (EDHREC)" is gone until enrichment stores the rank.
  - "Most valuable cards" is `order:value`.
  - A new sort key resets the direction.
- **Every POST lands on its tab:**
  - add one card, a batch, or an upload → Add;
  - set a count or reconcile → Manage;
  - a replace that leaves a reconcile offer → `Manage#reconcile`. The Manage tab wears a
    badge while that offer waits.

## 5. Later (Wave 2 extras)

- **Saved household views** in the database: named query strings, such as "Free green
  ramp".
- **"Download these results"** on any query.
- **Enrichment stores:**
  - the EDHREC rank, which brings back "Most played" as a server sort;
  - the full type line, so batch-added rows stop being "main type only";
  - oracle text, so `o:` can work.
- **In the card panel:** a quantity stepper and a "4 owned · 3 in decks · 1 free" line.
- **A real-phone web-vitals beacon**, to confirm a server round trip feels instant.

## 6. Tracker

| Part | Status |
|---|---|
| Hotfix: observer + study decks (#194) | [x] merged 2026-10-14 |
| B1: `collection_query.py` + `analyze_collection.py --query` + tests + tool contract | [x] 2026-10-14 |
| B2: Cards / Add / Manage sub-tabs, server-side query, chips, dialog, paging, UAT | [x] 2026-10-14 (see "As built") |
| Wave 2 extras (§5) | [ ] |
