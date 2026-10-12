# Spec — Card intake: batch entry, card data, and review against the decks

**Status:** ☐ spec'd 2026-10-12, not started · code today: `webapp/app.py`
(`/collection/add`, `/collection/upload`, `_install_upload`), `webapp/enrich_bg.py`,
`mtglib._parse_namelist` / `merge_collection`, `deckcore.new_arrivals`,
`.github/workflows/attrs-snapshot.yml`

**Player ask (2026-10-12):** "I've also added a lot of cards that need cataloging."

**Decisions (player, 2026-10-12):**

- The player will paste the big list into a session.
- "Cataloging" here means three things:
  1. **fill in card data**;
  2. **review the cards against the decks**;
  3. **a faster bulk entry** for next time.
- Tracking where each card is stored (binder or box) is **not** wanted.

---

## 1. How cards get in today

- **Upload** (Collection page) replaces the private CSV with a new export. That file
  (`collection.csv`) is gitignored and stays on the server. A background Scryfall
  enrichment fills in card data. It is never synced, so Claude sessions don't see it.
- **Add** (Collection page) takes one card at a time, with a quantity of 1–99, and writes
  it to `owned_additions.txt`. That file is committed, and the daily sync pushes it.
- **Sessions** read the committed name-only `collection_snapshot.txt`, refreshed from the
  Google Drive doc, plus `owned_additions.txt`.
- **The list parser** (`mtglib._parse_namelist`) already accepts `4 Sol Ring`,
  `4x Sol Ring` and a bare `Sol Ring` (counted as 1). It also strips a trailing
  `(SET) 123`.

**Two gaps:**

1. **There is no batch entry.** A big pickup goes in either one Add at a time or as a
   whole new export.
2. **Additions are counted on top of the export.** `mtglib.merge_collection` *adds*
   quantities. Once a later export includes those same cards, they are counted twice and
   nothing warns about it. Ownership figures that lie are the one thing this project
   can't have (grounding rule #1).

## 2. Now: this batch (a session, no new code)

The player pastes the list into the session, and the session does the following.

1. **Parse** with the existing list parser.
   - Also strip the markers it doesn't know yet: foil and etched tags (`*F*`, `*E*`,
     `Foil`), bracketed set codes (`[SET]`), and condition words.
   - Merge duplicates, drop basic lands (always owned and never tracked, rule #9), and
     report the counts.
2. **Verify every name on the runner.** Add the names to `verify-queue.txt` and run
   `deck-verify.yml` to get each card's:
   - canonical name;
   - type, colors and mana value;
   - estimated price.

   Misspelled or unknown names come back as a short list to fix. Nothing unverified gets
   added.
3. **Write a dated batch block** at the end of `owned_additions.txt`:
   ```
   # --- Batch 2026-10-12 · pasted list · 214 cards ---
   1 Sol Ring
   …
   ```
   The list is read as *new copies* on top of what the site already counts. That is what
   "added" means today.
4. **Fill in card data.** Dispatch the attrs refresh so types, colors and mana value
   appear for sessions. The hosted app re-enriches on its next sync.
5. **Review against the decks** with the sleeper audit
   (`.claude/skills/mtg-deckbuilder/references/card-review-method.md`):
   - Build the pool, verify the text, then read each card against each deck's engine.
   - Give every card a verdict for each deck: swap, wishlist, bench or skip. **No card is
     silently dropped.**
   - Show the swaps as a table **before** anything changes.
   - Log accepted swaps as `Source=manual-replace`.
   - Rewrite any clip scene left stale by a swap in the same change.
   - Validate with field overlap.

## 3. Next time: batch entry in the app

**"Add a batch"** goes on the Collection page. It accepts a pasted list, or a CSV of just
the new cards. The fastest way to catalog paper cards is to scan them with the phone
camera in a free app such as ManaBox, then export the session as a CSV. This spec does
not build a scanner.

**The flow is paste → preview → confirm → write.**

- **Preview.** This runs on the server, which can reach Scryfall.
  - Each line is resolved to a canonical name: exact match first, then fuzzy.
  - Each line shows one of: ✓ resolved, ? "did you mean …", or ✗ not found.
  - It also shows quantities, estimated prices and totals.
  - Lines that don't resolve are **not added** until they're fixed.
- **Accepted formats.**
  - Everything the list parser takes.
  - Moxfield and Arena lines (`1 Sol Ring (C21) 263 *F*`) and `Sol Ring x2`.
  - Any CSV the collection loader already recognises (ManaBox, Moxfield, TCGplayer,
    Sorted…).
  - Basic lands are dropped, with a note saying so.
  - Real card names that contain parentheses (e.g. "B.F.M. (Big Furry Monster)") must
    survive intact. Only a trailing `(SET) <number>` is stripped.
- **Write.**
  1. Append the dated batch block from §2 to `owned_additions.txt`.
  2. Invalidate the caches.
  3. Start `enrich_bg` so types, colors and mana value show up within minutes.
  4. The daily sync then carries the batch to GitHub.
  5. `attrs-snapshot.yml` gains `data/collection/owned_additions.txt` in its push
    `paths`, so sessions get the card data the same day. Today it only watches the
    snapshot, so additions wait for Monday's cron.
- **Reconcile on upload** (fixes gap 2).
  - When a new export is uploaded, compare it against the batch rows.
  - A batch row counts as covered when *new export qty ≥ previous export qty + batch qty*.
  - The app then asks: "These 37 batch cards are in your new export — retire them so
    they aren't counted twice?" One tap retires them.
  - A retired row is commented out with the date, never deleted:
    `# retired 2026-10-20 (in export): 1 Sol Ring`.
  - A row that is only partly covered keeps the remaining quantity.
  - Nothing changes without the tap.

## 4. Review against the decks, in the app

A **"New arrivals"** panel goes on the Collection page and into the coaching packet. It
covers the latest batch, plus anything newer than N days.

- **Per new card:**
  - which decks can legally run it, by color identity;
  - for each of those decks, two signals: the field % from
    `data/reference/field/<commander>.json` and the deck-fit score.
- Top candidates come first, and the panel labels these numbers as **a prior**. The
  method's rule is that field % is a prior and the engine read is the verdict.
- **"Copy review packet"** is a text export, like `/deck/<stem>/assess.txt`. It holds:
  - the batch;
  - the candidates for each deck;
  - each deck's engine summary from its notes.

  It is for a Claude session to do the engine read and return verdicts.
- **Accepting a swap** in the app uses the existing Replace. It is logged as
  `manual-replace` and labeled with who did it (`docs/spec-second-login.md`).
- **`deckcore.new_arrivals` learns batch headers.** Rows under a dated batch block count
  as arrivals on that date, just as an export's `Date Bought` column does today.
  - On a name-only collection there is no color data, so the deck list stays empty and
    the panel says why. It never guesses.

## 5. Tests

**Batch parser**

- Each accepted format parses.
- Foil and condition markers are stripped.
- Real names with parentheses are left intact.
- Basic lands are dropped, quantity bounds hold, and duplicates are merged.

**Preview and write**

- Preview never writes anything.
- Confirm writes exactly the previewed rows, and never an unresolved line.

**Reconcile**

- Covered rows are offered for retirement.
- Nothing is retired without confirmation.
- A retired row is no longer counted.
- A partly covered row keeps its remainder.

**`new_arrivals`**

- It reads batch dates.
- On a name-only collection it degrades with a label and never guesses.

**Privacy**

- Batch writes go only to `owned_additions.txt`, with names and quantities only.
- Prices stay in the private files.
- An upload still never touches the tracked snapshot.

## 6. Open questions

- Should "New arrivals" also look at cards that sat unplaced for a long time? Proposed
  no: the full-pool sleeper audit already covers those, on request.
