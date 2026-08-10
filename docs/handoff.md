# Session Handoff — current state

**Purpose:** everything a new session needs to continue this project without
re-deriving it. This file describes the **current state only**; the full history lives
in git (`git log` — commit messages in this repo are deliberately substantial).
Architecture: `docs/codemap.md`. Working rules: `CLAUDE.md`. Grounding rules
(canonical): `.claude/skills/mtg-deckbuilder/references/grounding-rules.md`.

_Last updated: 2026-08-10._

## Where the app runs

- **Hosted:** a PythonAnywhere **free-tier** web app (Python 3.13, virtualenv with
  Flask only, WSGI entry `webapp/pa_wsgi.py`), used from every device — phone as an
  installed PWA, PC through the same URL. Chosen over Render because PythonAnywhere's
  filesystem is **persistent** — this app's flat-file data model requires that. The
  hosted URL is deliberately not written in this repo; treat it as sensitive.
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
  only) lives in the server clone's remote URL. Fine-grained PATs **expire** — when
  pushes start failing, mint a new one and re-run `git remote set-url` (a calendar
  reminder ahead of the expiry date shown in GitHub's token settings avoids the
  surprise). Never ask for the token in chat or a screenshot — `git remote -v`
  prints it in full.

## The server is the source of truth for `data/decks/`

Deck files are git-tracked but rewritten **on the server** by the card panel, the deck
editor, and the optimizer. `sync_server.sh` (repo root) reconciles: commits only the
three runtime-edited paths (never `git add -A`), rebases before pushing (aborting
cleanly on conflict), and reloads the app via the WSGI touch unless told not to.

## Current data (season closed 2026-08-10)

- **Six decks** in `data/decks/`, all re-optimized against the field snapshots and
  idempotent (a fresh `optimize.py --all` proposes nothing). Bracket state vs the
  owner's stated aim of **Bracket 3/4 where possible**: four decks at B3 (Y'shtola
  71 · Team Leader 58 · Ur-Dragon 58 · Cosmic Spider-Man 55); Cloud (B2, 50) and
  First Avenger (B2, 32) below. Cloud has an approved-path fix (Crop Rotation, the
  one FREE owned Game Changer in its colors, notably fetching its Slayers'
  Stronghold at instant speed); First Avenger **cannot** reach B3 from the owned
  pool — every blue Game Changer is committed elsewhere (Force of Will ×2,
  Mystical Tutor, Rhystic Study ×2-across-4-decks) — only a purchase gets it there.
  No deck can reach B4 from the owned pool (4 unique Game Changers owned, total).
- **The server runs on the full Sorted collection** (uploaded via the app; 2,518
  unique / 3,602 copies, enriched). The committed name-only snapshot was
  regenerated from the same export (PR #88) — grounding is consistent everywhere.
- **Field-overlap validation of the optimizer ranking: PASSED** — every deck sits
  at 24–25 of its field's top 25 (the ~50% revert threshold is nowhere close).
- Test suite: **375 passing**, offline and hermetic; CI runs Python 3.11 and 3.13.
- **Enrichment is production-aware** (engine-season workstream A): `collection_attrs.csv`
  now carries `Produced` (what a card actually taps for) and `Flags` (oracle-derived —
  `etb-tapped`/`-cond`, `rock`, `dork`, `ramp`, `draw`, `mana2`/`mana3`), derived by the
  new `scripts/oracle_flags.py`. Colored-source counts use real production where it exists
  and print "identity approx." where it doesn't. **The player's own attrs file is still the
  old 7-column shape until `enrich.bat` is re-run** — until then every manabase surface will
  correctly show the identity-approximation label. Two owner-machine checks are outstanding:
  a one-time Scryfall-schema sanity check on the `test_oracle_flags.py` fixture shapes, and
  a ~30-random-card audit of derived flags after the first real enrichment run.
- **The engine can goldfish** (engine-season workstream C): `scripts/goldfish.py` is a
  seeded, stdlib, offline Monte Carlo — shuffle, London mulligan, land drops, greedy
  casting — reporting P(commander by turn N), keepable / screw / flood **with their
  definitions printed beside them**, mean lands by turn, and which cards actually land
  late. It answers the *sequenced*-play questions `manabase.py`'s exact-but-unconditional
  hypergeometrics structurally cannot, and the two are deliberately shown side by side in
  the dashboard's Mana tab, on `/deck/<stem>/assess`, and in the coaching packet.
  `--ab "Out=In"` re-runs the identical shuffles with one card swapped (common random
  numbers) and prints paired confidence intervals. **On the current data the honesty gate
  fires on the name-only snapshot** — over 25% of nonlands have no mana value there, so
  the surfaces print the note instead of numbers; the server, running the enriched
  collection, gets real numbers, and they will jump from the fallback tier to the
  production-aware tier the first time `enrich.bat` is re-run. Everything goes through one
  cached entry point (`goldfish.sim_for_deck` → `data/cache/goldfish/`), so a page view
  after a deck edit costs one simulation across all three surfaces (~0.1–0.3s cold,
  a file read warm).

## Open items

1. **Cloud → B3 swap awaiting the owner's yes/no:** Evolving Wilds → Crop Rotation
   (owned ×3, free). Apply via the app's card panel or a deck-file edit; the
   optimizer will respect it as a manual edit either way.
2. **First Avenger bracket:** stays B2 unless a Game Changer in R/U/W is bought
   (estimates only — no live prices): e.g. Drannith Magistrate or Smothering
   Tithe class cards. The deck also still lists 21 cards to buy — bracket is not
   its binding constraint.
3. **PAT renewal when due** (see GitHub token settings) and the quarterly
   keepalive click (above). Auth gate is ON (verified live); collection upload is
   DONE; ranking validation is DONE.
4. **Known UI gap:** dashboard Buy-tab rows for cards not in the deck are plain
   text, not panel-clickable (`docs/codemap.md`, "still open").
5. **Engine season is spec'd and RATIFIED (2026-08-10):**
   `docs/spec-engine-upgrades.md` — four workstreams (production-aware
   enrichment, a Comprehensive Rules layer, goldfish Monte Carlo, subagents).
   The owner accepted every §9 recommendation; implementation proceeds one
   workstream per session/PR in order A → C → D → B → A-F. **A and C have landed**
   (production-aware enrichment and the goldfish simulator, both above).
   **Next up: D** (subagents, §7), then **B** (the Comprehensive Rules layer, §5),
   then **A-F** (`classify()` consuming the oracle flags, §4.5 — that one owes a
   before/after categories diff and an explicit re-proof of optimizer idempotency).

## Session workflow reminders

- PRs are **squash-merged**; after every merge, rebuild the feature branch on
  `origin/main` before new work or the next PR conflicts.
- When a session materially changes a deck or ships a feature, update this file and
  tick `docs/spec-interactive-analytics-ai.md` if a tracked feature landed.
- The optimizer never touches manual edits; a second optimizer run on a tuned deck
  must change nothing (idempotence is tested).
