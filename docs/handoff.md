# Session Handoff — current state

**Purpose:** everything a new session needs to continue this project without
re-deriving it. This file describes the **current state only**; the full history lives
in git (`git log` — commit messages in this repo are deliberately substantial).
Architecture: `docs/codemap.md`. Working rules: `CLAUDE.md`. Grounding rules
(canonical): `.claude/skills/mtg-deckbuilder/references/grounding-rules.md`.

_Last updated: 2026-08-10._

## Where the app runs

- **Hosted:** a PythonAnywhere **free-tier** web app (Python 3.13, virtualenv with
  Flask only, WSGI entry `webapp/pa_wsgi.py`). The player uses it from a phone as an
  installed PWA and from the PC through the same URL. Chosen over Render because
  PythonAnywhere's filesystem is **persistent** — this app's flat-file data model
  requires that. The hosted URL is deliberately not written in this repo; the app has
  no authentication (see "Open items").
- **Local:** `webapp/run.sh` / `run.bat` still work for offline development.
- **⚠ On the host, "Static files" on the Web tab must stay EMPTY** — `/static/tokens.css`
  is a Flask *route* serving `scripts/assets/tokens.css`; a directory mapping would
  shadow it and silently 404 the shared design tokens. `tests/test_deploy.py` guards this.
- **Keepalive:** free web apps need "Run until 3 months from today" clicked every ~3
  months. Missing it sleeps the app; no data is lost.

## The automation loop (all legs verified on real events)

```
GitHub Action (weekly + on deck pushes + manual)          the hosted app (daily,
  refreshes data/reference/field/*.json  ──▶  main  ◀──   in-app sync: deck edits up,
  (EDHREC field snapshots)                                code + snapshots down)
```

- **Field snapshots** (`.github/workflows/field-snapshots.yml`, spec:
  `docs/spec-field-snapshot-action.md`): EDHREC is permanently unreachable from the
  host (free-tier allowlist), so per-commander inclusion/synergy is committed to
  `data/reference/field/` and refreshed by the Action. Read precedence: live fetch →
  disk cache → snapshot → `{}`.
- **In-app sync** (`webapp/sync.py`, spec: `docs/spec-in-app-sync.md`): the app runs
  `sync_server.sh` in a background thread on the first request of each day, plus a
  "⇅ Sync with GitHub" button on the Decks page. This replaced the planned
  PythonAnywhere Scheduled Task, which became **paid-only** (checked live 2026-08-10).
  Auto-detects the host via `PYTHONANYWHERE_SITE`; `MTG_AUTO_SYNC=1|0` overrides.
- **Push credentials:** a fine-grained GitHub PAT (Contents: read/write, this repo
  only) lives in the server clone's remote URL. **It expires 2026-11-07** — pushes
  start failing then; mint a new one and re-run `git remote set-url`. Never ask the
  player to paste the token into chat or screenshot a console where `git remote -v`
  could print it.

## The server is the source of truth for `data/decks/`

Deck files are git-tracked but rewritten **on the server** by the card panel, the deck
editor, and the optimizer. `sync_server.sh` (repo root) reconciles: commits only the
three runtime-edited paths (never `git add -A`), rebases before pushing (aborting
cleanly on conflict), and reloads the app via the WSGI touch unless told not to.

## Current data

- **Six decks** in `data/decks/`: Y'shtola Night's Blessed, Captain America Team
  Leader, The Ur-Dragon, Cosmic Spider-Man, Cloud Ex-SOLDIER, Captain America First
  Avenger.
- The server still runs on the committed **name-only snapshot** — the rich collection
  CSV has not been uploaded there yet (see "Open items").
- Test suite: **231 passing**, offline and hermetic; CI runs Python 3.11 and 3.13.

## Open items

1. **Auth gate shipped — needs one server-side step to turn ON.** The app now
   supports a shared-password login (`docs/spec-auth-gate.md`); until the player
   adds `os.environ["MTG_PASSWORD"] = "…"` to the PythonAnywhere WSGI file and
   reloads, the hosted app is still open to anyone who finds the URL. That env
   line is the whole setup. Never ask for or handle the actual password in chat.
2. **Collection CSV upload.** Until the player uploads the rich export via the app's
   Collection page, server-side analysis runs name-only (no curve/color/tribe data).
   Uploading rebinds the collection in-process — no reload needed.
3. **Optimizer ranking validation.** The `value_of()` ranking change shipped without
   live EDHREC top-25 overlap validation (unreachable from the sandbox that wrote it).
   From any EDHREC-reachable machine: run `optimize.py --all` preview, check overlap;
   below ~50% on any deck means revert the ranking commit.
4. **PAT renewal by 2026-11-07** and the quarterly keepalive click (above).
5. **Known UI gap:** dashboard Buy-tab rows for cards not in the deck are plain text,
   not panel-clickable (`docs/codemap.md`, "still open").

## Session workflow reminders

- PRs are **squash-merged**; after every merge, rebuild the feature branch on
  `origin/main` before new work or the next PR conflicts.
- When a session materially changes a deck or ships a feature, update this file and
  tick `docs/spec-interactive-analytics-ai.md` if a tracked feature landed.
- The optimizer never touches manual edits; a second optimizer run on a tuned deck
  must change nothing (idempotence is tested).
