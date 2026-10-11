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

It flags page overflow and small tap targets automatically, then **read the
screenshots** — the flags are a floor, not the review. Card images are blank in a
sandbox with no internet; that is expected.

Clean up afterwards: `git worktree remove /tmp/uat-before`.
