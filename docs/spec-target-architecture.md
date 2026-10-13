# Spec — Target architecture: code in git, data in a database, network at the server

**Status: PROPOSED 2026-10-13. Nothing here is built.** Written because the player asked
to revisit the whole app: *"I don't want my cards in the repo… No data should ever live in
a repo. We also need a better way to check Scryfall other than GitHub… I also want to
ensure our deck building workflows make sense."* The decisions for the player are in §10.
This file is the live tracker, so tick its boxes, not the handoff's.

---

## 1. Why: what the current shape costs

The app grew from "a skill that reads a CSV" into a hosted, multi-user, phone-first app,
but it still keeps every piece of state as files in the git repo. Git is a code-review
tool, and using it as the database is behind most of this week's friction.

**Where the data lives today (2026-10-13 inventory):**
- About 150 tracked data files.
  - 49 deck files (13 decks).
  - 5 collection files, including the full added-cards list.
  - 54 reference files: 27 EDHREC field snapshots, precon lists, verify dumps.
  - 35 narration files (2.1 MB).
  - The wishlist.
- The repo is **public**, so all of it is world-readable, and git history keeps every
  earlier version.

**Who writes data, and through what:**
- The hosted app writes deck edits, batches, pins and activity. `sync_server.sh` commits
  them back to git, with rescue branches, an autostash, flock and a rebase-retry loop. All
  of that exists only to merge data through git.
- Five GitHub workflows commit data: `deck-verify`, `field-snapshots`, `attrs-snapshot`,
  `narrate` and `narrate-audition`.
- Claude sessions change data by commit, then PR, then CI, then squash-merge, then a
  re-sync. Every deck swap costs a full code-review cycle.

**Incidents from the last two days that are architecture, not bad luck:**
1. **Two copies of the collection drifted.** The server's private CSV and the repo's
   name-only snapshot disagreed. 51 Kami cards read as unowned in sessions, and the fix
   (`sync_snapshot.py`) only works if the repo is private.
2. **A data refresh erased curation.** Re-enriching Beorn's `.attrs.csv` replaced 18
   hand-written role flags, so removal fell 9→6 and the only wipe vanished. Derived data
   and curated data shared one file.
3. **Scryfall goes through GitHub.** Verifying a card means dispatching a workflow,
   waiting, downloading the job log, parsing it with a scratch script and then writing a
   file. It is the slowest and most fragile step in every deck session, and it is the
   reason "make the repo private" looked unsafe.
4. **Ownership is ambiguous at intake.** Nothing at intake time could say "you already
   own one: it's in your export / in yesterday's batch / sleeved in Kami". Three cards
   were nearly counted twice.
5. **The app lags.** The player sees a session's changes only after the next daily sync.

## 2. Principles

1. **Code in git; data in a database.** The repo holds code, specs, tests and generic MTG
   knowledge. No collection, deck, batch, log, cache or audio file is ever committed.
2. **One system of record.** The hosted app's database is the only place a card count or
   a deck list lives. Everything else reads it or asks it to change something.
3. **The network lives at the server.** The app talks to Scryfall, EDHREC and Commander
   Spellbook and caches the answers. Nothing routes card lookups through GitHub.
4. **Derived data and curated data never share storage.** A refresh can overwrite a
   cache. It can never touch a human decision.
5. **Every change has one write path.** That covers the player's taps, the optimizer and
   Claude. Each change is logged with source and who, and the app shows it immediately.

## 3. The target picture

```
                 ┌──────────────────────── hosted app (PythonAnywhere) ───────────────────────┐
  Player ──────▶ │  Flask web app  ──▶  store.py (stdlib sqlite3)  ──▶  mtg.db  (outside repo) │
  (phone, PC)    │       │                    ▲                                                │
                 │       ▼                    │                    data/ dir: narration audio,  │
                 │  engines (scripts/, stdlib, unchanged logic)     nightly db backups          │
                 │       │                                                                     │
                 │  fetchers ──▶ Scryfall · EDHREC · Spellbook   (cached in mtg.db, refreshed  │
                 │                                                 by the app's daily trigger) │
                 │  JSON API  /api/v1/*  (token auth)   ·   later: MCP connector (OAuth)       │
                 └──────────▲───────────────────────────────────────────▲─────────────────────┘
                            │ HTTPS + token                              │ upload audio (token)
                 Claude session (`mtg` CLI, stdlib urllib)        GitHub Actions: CI + narration
                 runs engines locally on data it fetched           compute only, commits nothing
```

**The repo after the move:** `scripts/` (the engines plus `store.py`), `webapp/`,
`tests/`, `docs/`, `.claude/` (the skill, agents and tool contract), and generic
reference knowledge (see §4). No `data/` tree at all; `.gitignore` covers it.

## 4. Data: what lives where

| Data | Today | Target |
|---|---|---|
| Full collection export (priced) | server `collection.csv` (gitignored) | `mtg.db`: `collection_rows` (source = export, upload id) |
| Added cards (batches) | repo `owned_additions.txt` | `mtg.db`: `collection_rows` (source = batch, `batches` table with date + label) |
| Name-only collection list | repo `collection_snapshot.txt` | **gone**. A session asks the API |
| Decks, sections, notes, buy lists, change logs, clips | repo `data/decks/*` | `mtg.db`: `decks`, `deck_cards`, `deck_notes`, `buylist`, `deck_changes`, `clips` |
| Pins, members, activity | repo / `data/private/users.json` | `mtg.db`: `pins`, `members`, `activity` |
| Wishlist, ManaPool exports | repo `wishlist.md` (generated) | computed on request, never stored |
| Scryfall card data (types, text, production, flags, prices) | repo attrs snapshot + per-deck `.attrs.csv` + server attrs CSV | `mtg.db`: `card_cache` (refreshable; fetched_at per card) |
| **Curated role overrides** (today's `mtglib` RAMP/DRAW/REMOVAL lists) | `mtglib.py` | stays in code as generic knowledge, **or** `card_roles` table (D3). Either way, never in the cache table |
| EDHREC field snapshots, precon lists, Spellbook combos | repo `data/reference/field/*`, `precons/*` (Action commits) | `mtg.db`: `field_cache`, `precon_cache`, `combo_cache` |
| Narration audio | repo `data/narration/*` (runner commits) | server `data/narration/` dir; the runner uploads through the API |
| Generic MTG knowledge (Game Changers list, combos.csv, card_notes.csv, tutors, banned list…) | repo | **stays in the repo (recommended, D3)**. It's a rulebook, not anyone's cards, and changes to it deserve code review |

**Why SQLite:**
- It's Python stdlib (`sqlite3`), so `scripts/` stays dependency-free and the tests stay
  hermetic (`:memory:` or `tmp_path`).
- It is one file on the app's persistent disk, with transactions, so a swap set lands
  whole or not at all.
- It is fast enough for one player plus one member by orders of magnitude.

**Why not hosted Postgres:**
- PythonAnywhere's free tier only lets the app call an allowlist of outside websites, so
  it can't reach a database on another host.
- It would put a third party between the player and their data.

**Backups:**
- Nightly `sqlite3 .backup` to a dated file on the server (protects against bugs).
- A **Download backup** button (protects against losing the host). If unattended
  off-host backup is wanted, add it later.

## 5. The network: who talks to Scryfall, EDHREC and Spellbook

- **The app server is the network arm.**
  - The app already enriches through Scryfall on upload. That becomes a general fetcher
    with a `card_cache`.
  - Field snapshots and precon lists move from GitHub Actions to the same fetchers, run
    by the app's existing "first request of the day" trigger (`webapp/sync.py`'s
    pattern; PythonAnywhere free has no scheduled tasks).
  - A verify request answers from the cache instantly, or fetches once and caches.
- **Claude sessions reach the data through the app.** Card lookups go through
  `mtg cards verify …` against the API (§6), so a session needs exactly one allowed
  domain: the app's.
- **Optionally, sessions can also reach the sources directly.** Add `api.scryfall.com`,
  `json.edhrec.com` and `backend.commanderspellbook.com` to the cloud environment's
  *Allowed domains* (environment settings → Network access → Limited → Allowed domains).
  This is `spec-network-and-attrs.md` Phase 1, open since 2026-08-12. It takes minutes,
  needs no code, and ends the GitHub round trip **today**, before any of this is built.
- **To verify:**
  - [ ] Whether PythonAnywhere free's outbound allowlist includes `json.edhrec.com` and
    `backend.commanderspellbook.com`. Scryfall is already used from the server. Check
    from the server console during Phase 2. If either is blocked, the options are:
    PythonAnywhere's paid tier (unrestricted outbound and scheduled tasks; check the
    current price), a request to add the site to their allowlist, or moving the host
    (D1).
- **GitHub Actions keeps two jobs only:**
  1. CI (pytest).
  2. Narration synthesis. The Kokoro model needs more CPU than the free server allows,
     so the runner pulls the clip text from the API and uploads the audio back. It
     commits nothing.

## 6. How Claude works with the app

**Phase A: a token API and a small CLI (recommended first).**
- `/api/v1/…` JSON endpoints with a per-session token, stored as an environment secret in
  the Claude cloud environment and revocable on the People page. Every write is logged
  `By = claude`.
- `scripts/mtg.py`, a stdlib `urllib` client:
  - `mtg collection search Dragon --json`
  - `mtg cards verify "Sol Ring" "Rejoinder"` (server-side Scryfall, cached)
  - `mtg deck pull beorn-the-fierce` writes a temp dir in the **current formats** (txt,
    attrs, notes…), so every existing engine runs unchanged in the session. That includes
    goldfish, whose CPU should not come out of the server's small allowance.
  - `mtg deck propose beorn-the-fierce swaps.json` creates a proposal (§7).
  - `mtg deck apply <proposal>` only after the player says go.
  - `mtg batch preview list.txt`, then `mtg batch confirm <token>`.
- The skill and the tool contract are rewritten around these commands. The rule "if a
  tool answers the question, the tool answers it" stays; the tools change.

**Phase B: an MCP connector (optional, later).**
- The same operations, as a remote MCP server on the app (claude.ai → Customize →
  Connectors). Claude in a plain chat or on the phone could then read decks and propose
  swaps with no repo and no session setup.
- **The cost:** the connector needs a real OAuth login flow on the app, the largest single
  build item here, which is why it comes second.
- The 2026-08-12 "MCP servers: NO" decision was about third-party Scryfall MCPs inside
  the blocked container. A connector to the player's own app is a different question and
  doesn't relitigate it.

## 7. Deck-building workflows, end to end

**The loop:** one cycle, the same whether the player or Claude drives it.

| Step | What happens | Who | Today's pain it removes |
|---|---|---|---|
| 1. Collect | Cards arrive (photos, order export, paste, full export). **Add a batch** verifies every line at the server, and the preview says *"you already own 1: in your export / in batch 2026-10-12 / sleeved in Kami"* before anything is saved | player in app, or Claude via `mtg batch` | GitHub verify round trip; near-double-counting (incident 4) |
| 2. Discover | "What can I build?": commander finder and pool counts, read straight from the DB | app or Claude | stale session snapshot (incident 1) |
| 3. Build | auto_build plus Claude's engine read produce a **draft deck** in the app, not a file in a PR | Claude or Build Next | PR per deck |
| 4. Review | Every change not made by the player's own hand arrives as a **proposal**: Out → In, field %, verified text, engine reason, role-count impact, goldfish deltas. It shows on the deck page as *Proposed changes (6)* with Approve / Reject per row | Claude, optimizer → player | swap tables living only in chat |
| 5. Apply | One transaction: deck cards, change log (source, who), buy-list status, notes. Optimizer protections read the log, exactly as `manual-replace` works today | app | six files hand-edited per swap set |
| 6. Play | Dashboard, Watch tab, mulligan trainer, table card (later: a games log) | player | n/a |
| 7. Re-tune | New arrivals produce a review packet (sleeper audit), then proposals, then back to step 4 | Claude via `mtg`, or a button | photos → session → PR → sync |

**Rules that carry over unchanged:**
- The sleeper audit method.
- Verified text before any judgement.
- Owned cards only in the 99, with buys in the buy list.
- Study decks commit no copies.
- Basics are unlimited.
- Clips must match the list.
- The ≥25-point optimizer gate.

**What changes in how a deck gets edited:**
- Claude never edits a deck file or opens a PR for deck data again.
- "Present swaps before applying" becomes an object in the app, not just chat text. The
  player can approve it on the phone with no session open.
- **(D4)** The optimizer becomes a proposal source like Claude. ⚡ and `refresh --optimize`
  show proposals instead of applying them. Build Next keeps auto-applying, because its
  output is already a fresh draft. This changes CLAUDE.md's "automatic in four places"
  rule, so it's the player's call.

## 8. Migration: phases, each shippable on its own

Each phase leaves the app working. Phases 1–3 keep the files as a read-only fallback until
Phase 4 deletes them.

- **Phase 0, player, minutes, no code**
  - [ ] Allowed domains in the Claude environment (§5). Sessions stop routing Scryfall
    through GitHub.
  - [ ] Decide D1–D5 (§10).
- **Phase 1: the store**
  - [ ] `scripts/store.py` (stdlib sqlite3): schema, migrations, typed accessors returning
    the existing `Card` / deck objects, so the engines barely change.
  - [ ] A one-time importer that reads today's files (`collection.csv`, owned_additions,
    decks and their companions, pins, members, activity) into `mtg.db`. It's idempotent,
    with a dry-run report of row counts per table.
  - [ ] The app reads and writes through `store`, and file formats become import/export
    only. Tests: hermetic, in-memory DB.
  - *Exit:* every page renders from the DB, and the files are untouched and still
    importable.
- **Phase 2: network at the server**
  - [ ] Fetchers write to `card_cache` / `field_cache` / `precon_cache`, refreshed by the
    daily trigger.
  - [ ] Curated roles kept apart from the cache (D3).
  - [ ] Verify the PythonAnywhere allowlist (§5).
  - *Exit:* `deck-verify`, `field-snapshots` and `attrs-snapshot` are deleted.
- **Phase 3: Claude through the API**
  - [ ] `/api/v1` plus the token on the People page.
  - [ ] `scripts/mtg.py`.
  - [ ] Proposals (§7) in the app.
  - [ ] The skill, tool contract and agents rewritten.
  - [ ] `narrate.yml` pulls text and uploads audio.
  - *Exit:* a full sleeper audit and swap set runs with zero commits.
- **Phase 4: data out of the repo**
  - [ ] Delete `data/`.
  - [ ] `.gitignore` covers it.
  - [ ] `sync_server.sh` shrinks to "pull code, reload". Rescue branches, the autostash,
    the tracked-data list and `sync_snapshot.py` all retire.
  - [ ] The history decision (D2), then private.
  - *Exit:* `git ls-files data` is empty, and the app and a session both work.
- **Phase 5: optional**
  - [ ] MCP connector (§6 B).
  - [ ] Off-host backups.
  - [ ] Games log.

**Rough size:** about 35 modules touch data paths today, out of about 21.7k lines of
Python. Most engines already take parsed cards (`deckcore.analyze_cards`), so the heavy
work is `store.py`, the importer and `webapp/app.py`'s roughly 40 file opens. Phase 1 is
the big one; Phases 2–4 are mostly deletion.

## 9. What becomes obsolete (honestly)

- **Retired:**
  - `sync_server.sh`'s data half, and the rescue-branch machinery.
  - `webapp/sync_snapshot.py` (merged 2026-10-13 in #179; the DB replaces the snapshot it
    protects).
  - The name-only snapshot and the attrs snapshot.
  - `verify-queue.txt`.
  - Five data-committing workflows.
  - The tool contract's whole "§1 NETWORK: GitHub is the network arm" section.
- **Kept:**
  - Every engine.
  - The skill's persona and methods.
  - The Download added cards button (#179); it still round-trips cards to Archidekt.

## 10. Decisions for the player

- **D1: Host.** Stay on PythonAnywhere free (recommended) unless Phase 2 finds EDHREC or
  Spellbook blocked. If so, move to their paid tier or another host with a persistent
  disk.
- **D2: Git history.** Today's history holds every card list ever committed.
  1. Make the repo private and keep the history.
  2. Start a **fresh repo** from the cleaned tree (recommended). It loses the PR history
     but nothing else, and it's the only clean way to get the data out of history.
  3. Rewrite history with `git filter-repo` and force-push. Not recommended: it breaks
     the server's clone and gains nothing over option 2.
- **D3: Generic knowledge.** Keep the Game Changers list, combos, card notes and curated
  role lists in the repo as code (recommended). Or put them in the DB too, if "no data"
  is absolute.
- **D4: Proposals gate.** Optimizer runs outside Build Next produce proposals instead of
  auto-applying (recommended).
- **D5: Claude access.** Token API and CLI first, MCP connector later (recommended), or
  the connector first.

## 11. Risks

- **Host loss:** SQLite on one server is a single point of failure. Nightly on-host
  backups plus the Download backup button cover bugs and the player's own safety copy.
  Unattended off-host backup waits for Phase 5.
- **Server CPU:** PythonAnywhere free has a small daily CPU allowance. Heavy engines
  (goldfish at thousands of games) run in the session on pulled data, or in the app only
  on demand, never in the daily trigger.
- **API security:** a token that can write decks is a credential. Scope it (read / propose
  / apply), store it only as an environment secret, show its last use on the People page,
  and make it revocable in one tap.
- **Migration correctness:** the importer's dry run must reproduce today's numbers before
  the switch. Per-deck card counts, role counts, owned counts and the EDHREC overlap
  checks are the acceptance test.
