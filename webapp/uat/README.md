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
plus the deck-card menu, phone More sheet and card panel:

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
# + a seeded collection.db in $S (see store.py seed), or MTG_COLLECTION=<a collection file>
MTG_COLLECTION=$S/c.db MTG_DECKS_DIR=$S/decks MTG_PORT=5001 MTG_PASSWORD=uat-pass python3 webapp/app.py &
UAT_PASSWORD=uat-pass node webapp/uat/flows.js http://127.0.0.1:5001 $S/decks
```

It runs replace (off-colour must be refused, the replace search in-colour only), the
commander guard, Add with no section (filed by type, with the size warning), ⚡ (its
report on the deck page), the mulligan trainer (one hand counts once), the table card
(no raw markdown) and compression. PASS / FAIL / SKIP per flow; exit 1 on any FAIL.
Every one of those failed on the code before 2026-10-14 (docs/spec-ux-refresh.md §3).

Clean up afterwards: `git worktree remove /tmp/uat-before`.
