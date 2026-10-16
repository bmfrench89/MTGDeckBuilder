# UAT harness — run before merging any UI change

Unit tests and a fresh-browser screenshot did not catch the 2026-10-11 deploy that
rendered the new page with the **old** stylesheet on the player's installed phone.
These two scripts reproduce what the player actually experiences. Both need Node,
Playwright and Chromium (preinstalled in Claude Code cloud sessions).

**1. The upgrade path** — an installed app receiving a deploy:

```bash
git worktree add /tmp/uat-before origin/main      # what the phone has now
node webapp/uat/upgrade.js /tmp/uat-before . data/decks
```

PASS means the very first open after the deploy applied the server's current
stylesheets, rule for rule. FAIL names the stale sheet.

**2. The device sweep** — every main page at phone, Fold, tablet and desktop widths,
plus the deck-card menu, phone More sheet and card panel, the Lab and a theory deck's page
(when one exists), and the Collection's three
tabs with its grid, Filters sheet and help sheet open:

```bash
MTG_PORT=5000 MTG_PASSWORD=uat-pass python3 webapp/app.py &
UAT_PASSWORD=uat-pass node webapp/uat/sweep.js http://127.0.0.1:5000
```

It FAILS (exit 1) on page overflow or a tap target under 24 px (WCAG 2.5.8) and WARNS on
targets under 44 px, controls only reachable by scrolling a table sideways, and clipped
text — the open card panel included. Then **read the screenshots** — the flags are a
floor, not the review. Card images are blank in a sandbox with no internet; that is
expected.

**3. Player flows** — what pages DO, not how they look. Point a server at a SCRATCH
copy (the script edits decks, then puts every file back), with the committed attrs
overlay beside the database so colour checks have data:

```bash
S=$(mktemp -d); cp data/collection/collection_attrs.snapshot.csv $S/; cp -r data/decks $S/decks
# + a seeded, captured collection.db in $S, so F10 has earlier versions to restore:
python3 -c "import sys; sys.path.insert(0,'scripts'); import store; \
  store.seed('$S/c.db', None, 'data/collection/collection_snapshot.txt', \
             'data/collection/owned_additions.txt', '$S/decks', write=True); \
  store.capture('$S/c.db', '$S/decks', None, action='seed')"
MTG_COLLECTION=$S/c.db MTG_DECKS_DIR=$S/decks MTG_PORT=5001 MTG_PASSWORD=uat-pass python3 webapp/app.py &
UAT_PASSWORD=uat-pass node webapp/uat/flows.js http://127.0.0.1:5001 $S/decks
```

It runs replace (off-colour must be refused, the replace search in-colour only), the
commander guard, Add with no section (filed by type, with the size warning), ⚡ (its
report on the deck page), the mulligan trainer (one hand counts once), the table card
(no raw markdown) and compression. PASS / FAIL / SKIP per flow; exit 1 on any FAIL.
Every one of those failed on the code before 2026-10-14 (docs/spec-ux-refresh.md §3).
Then undo, through the screens a player taps (Wave 1.1):
- F7: Replace from the card panel, then the toast's Undo.
- F8: ⚡ then "Undo all".
- F9: Undo on a Changes-page row, which then reads "Undone".
- F10: Restore an earlier version (database mode; SKIP on files).
- F11: Keyboard only: Tab reaches a visible skip link that moves focus to main; a card
  name opens the panel with focus inside; Escape returns focus to the card (both panels).
- F12: The phone deck page: tabs on the first screen, the list by default, the filter, a
  row opening the panel, zoom.
- F13: Three Collection sorts, each timed to the new page's first frame (a sort is a
  server round trip since the rebuild); FAIL over 2.5 s or when the URL loses the order.
  The accessibility batch's card-name observer once made every sort take 4-6 s.
- F14: The Collection rebuild on a phone (docs/spec-collection-rebuild.md §4): the first
  card on the first screen, live search rewriting the URL, the Free scope chip, a chip
  removing only its own term, the Filters sheet's "Show N cards" equal to the page it
  opens, Load more kept through a visit to Add and Back, Manage marked current, and the
  help sheet handing focus back on Escape.
- F15: The Lab (docs/spec-lab.md):
  1. Move to the Lab from the phone menu. The file changes by exactly one header line.
  2. Find the deck in the Lab (the tab current), open it on its Lab tab, and make it a
     real deck again. The file comes back byte for byte.

Each must give back the same list, compared section by section.

Clean up afterwards: `git worktree remove /tmp/uat-before`.
