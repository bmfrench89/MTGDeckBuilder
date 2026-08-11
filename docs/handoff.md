# Session Handoff — current state

**Purpose:** everything a new session needs to continue this project without
re-deriving it. This file describes the **current state only**; the full history lives
in git (`git log` — commit messages in this repo are deliberately substantial).
Architecture: `docs/codemap.md`. Working rules: `CLAUDE.md`. Grounding rules
(canonical): `.claude/skills/mtg-deckbuilder/references/grounding-rules.md`.

_Last updated: 2026-08-11._

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

- **Deck sections are now EDHREC-style TYPE sections (2026-08-11)** — Commander /
  Creatures / Instants / Sorceries / Artifacts / Enchantments / Lands / Basics —
  across all decks, kept by the new `scripts/deck_sections.py` (idempotent;
  `--all --apply`). `auto_build` emits the same shape for future decks. Roles +
  power-list tags (Game Changer, Tutor, …) now show in card details on both
  surfaces via `deckcore.load_power_tags`. The migration fixed real misfiles
  (Rhystic Study and Lightning Greaves sat under "Lands" in ur-dragon). ~15 cards
  across the decks sit in explicit `Unsorted` sections pending enrichment — the
  server can re-run deck_sections after a sync to resolve them. **cosmic-spider-man repaired 2026-08-11**: the 99-card mystery was a corrupted
  commander block (annotated name + stray duplicate line) — cleaned; Ezekiel
  Sims, Spider-Totem (24% field) in over 0%-field Tome of Legends (freeing an
  over-committed copy); Thriving Isle added as the 100th card. NEW FINDING:
  eight of its hand-built spiders are absent from the snapshot (likely sleeved,
  never exported) — list in the deck's .notes.md; player to confirm →
  owned_additions.txt. The player DELETED captain-america-first-avenger via the
  app (2026-08-11); five decks + iron-man remain. Iron Man, Armored Avenger's
  single copy is both a commander and in team-leader's 99 (⇄ badged).
  **yshtola repaired 2026-08-11**: `Observed Stasis` (verified: {3}{U} flash
  Enchantment — Aura, FIC #40 — NOT a land) sat in the Lands section because the
  2026-08-09 optimizer run, typeless on the snapshot, cut Hidden Lair (a real MSH
  land that misses `_LAND_HINTS`) through the *spell* pass and the writer kept the
  section. Moved to Enchantments, typed in the deck `.attrs.csv` so a regroup
  holds, and a duplicate loose commander line (a real singleton violation flagged
  by `singleton_violations`) removed — deck is 100 cards, 38 real lands (24
  nonbasic + 14 basics; name-only heuristics undercount until the server
  re-enriches). Hidden Lair (owned ×1) is back in the available pool. The
  guardrail hole is CLOSED end-to-end: pass assignment is layered — real type
  data (CSV / `.attrs.csv`) → the deck file's own type-exclusive section (deck
  cards) → the field snapshot's `lands` key, i.e. EDHREC's own Lands sections
  (candidates) → name heuristic last — the CLI reports the untyped count instead
  of guessing silently, and the field-snapshot Action has regenerated every
  active snapshot WITH the `lands` key (verified: the Hallowed-Fountain-for-
  Absorb spell proposal corrected to a land-for-land swap on live data).

- **Decks are owned-only as of 2026-08-11 (player request), and the optimizer now
  keeps them that way.** Buy candidates never enter a 99: `optimize()` pairs each
  buy with an in-deck card and APPENDS it to `.buylist.csv` with Replaces = that
  card ("when this arrives, pull that"); existing buylist rows are never removed,
  only their Replaces refreshed (`append_buylist`). The migration pulled every
  provenance-confirmed BUY out of the five affected decks and swapped in owned,
  field-ranked, web-verified substitutes: cosmic-spider-man restored the four
  cards its 2026-08-10 buy run had displaced (Willowrush Verge, University
  Campus, Scarlet Spider Kaine, Spider-Girl Legacy Hero — two of those "buys"
  had cut LANDS through the same typeless-spell-pass hole fixed above);
  team-leader took Avengers Quinjet + Spectacular Spider-Man; cloud took
  Wrecking Ball Arm, Cid Freeflier Pilot, Professor Hojo, Bugenhagen; ur-dragon
  took Zurgo and Ojutai, Kolaghan the Storm's Fury, Broodcaller Scourge, Lozhan;
  yshtola took Krile Baldesion, Contaminated Aquifer, and a 4th Plains. Every
  deck is 100 cards, singleton-clean, zero unowned — EXCEPT cosmic-spider-man's
  eight hand-built spiders still pending the player's owned_additions
  confirmation (list in its `.notes.md`). Cloud's stray duplicate commander
  line (same bug as yshtola's) was also removed.
- **Seventh deck NEW (2026-08-11): `iron-man-armored-avenger`** — mono-blue draw-go
  control, hand-built in a sandbox session (network blocked) from the name-only
  snapshot as the "strongest possible new deck". Power **70/100, Bracket 3** at the
  3-Game-Changer cap (Rhystic Study, Force of Will, Mystical Tutor — all shared
  copies, badged). Finally places the free **Mana Drain** (ex-open-item riser).
  Ships with a hand-written `.attrs.csv` (70 rows covering 99 of the deck's 100
  copies, certain pre-2025 knowledge; commander row deliberately absent — its
  oracle text is **UNVERIFIED** offline, functional role taken from
  `commanders.csv`). Follow-ups route through the
  automation loop, NOT the player's PC: the merge's deck push triggers the
  field-snapshot Action (adds this commander's EDHREC data), the server's daily
  sync pulls it, and the app re-verifies/re-enriches/re-scores on the full CSV.
  The only physical to-do: pull ~25 spare basic Islands (23 owned, 18 sleeved
  elsewhere).
- **Six decks total, and every one is Bracket 3** (name-only snapshot scoring,
  2026-08-11 — the owner's "Bracket 3/4 where possible" aim is MET across the
  board): Y'shtola 73 · Iron Man 70 · Cloud 63 · Team Leader 58 · Cosmic
  Spider-Man 58 · Ur-Dragon 56. Cloud reached B3 via the voltron rebuild + the
  owned-only migration (the old open item is closed). No deck can reach B4 from
  the owned pool (4 unique Game Changers owned, total). The server re-scores on
  the full enriched CSV after each sync — expect small number shifts, not
  bracket changes.
- **The server runs on the full Sorted collection** (uploaded via the app; 2,518
  unique / 3,602 copies, enriched). The committed name-only snapshot was
  regenerated from the same export (PR #88) — grounding is consistent everywhere.
- **Field-overlap validation of the optimizer ranking: PASSED** — every deck sits
  at 24–25 of its field's top 25 (the ~50% revert threshold is nowhere close).
- Test suite: **480 passing**, offline and hermetic; CI runs Python 3.11 and 3.13.
- **Engine advisors** (PR #90, `docs/spec-engine-advisors.md`): the loader keeps the
  export's acquisition date; `deckcore.new_arrivals()` surfaces recently bought cards
  that are in no deck (Decks-page card, identity-matched to decks); `optimize()`
  reports **field risers** — owned cards the ≥25 anti-churn margin gate suppressed —
  in the CLI preview, `report["risers"]`, and the coaching packet. Both are strictly
  advisory: they never write. They exist because three good owned cards (Codsworth,
  Mana Drain, Smaug) sat unused while every deck reported "already aligned" — see
  open item 1.
- **Enrichment is production-aware** (engine-season workstream A): `collection_attrs.csv`
  now carries `Produced` (what a card actually taps for) and `Flags` (oracle-derived —
  `etb-tapped`/`-cond`, `rock`, `dork`, `ramp`, `draw`, `mana2`/`mana3`), derived by the
  new `scripts/oracle_flags.py`. Colored-source counts use real production where it exists
  and print "identity approx." where it doesn't. **The player's own attrs file is still the
  old 7-column shape until `enrich.bat` is re-run** — until then every manabase surface will
  correctly show the identity-approximation label. The one-time Scryfall-schema check of the
  `test_oracle_flags.py` fixture shapes is **DONE** (16/16 against the live API, 2026-08-10 —
  open item 5); the ~30-random-card flag audit after the first real enrichment run remains.
- **Role/category counts read those flags too** (engine-season follow-up A-F):
  `oracle_flags` also derives `removal` / `wipe` / `counter`, and `mtglib.classify()`
  consults `Card.flags` **only where its curated name lists are silent** — curated always
  wins, first-writer-wins, the same shape `deckcore.load_card_notes` uses. So a card from a
  set newer than the lists lands in the right bucket instead of the generic type bucket,
  and a hand-verified card can never be overruled by a regex. The mana-shape tokens
  (`etb-tapped`, `mana2`, `mana3`) map to no role — they are goldfish inputs. Proven on
  landing rather than assumed: the fixture deck's `deck_stats --json` categories are
  byte-identical without flags present (an unenriched collection has `flags == set()`, so
  the layer no-ops), and optimizer idempotency was re-run **with** flag-bearing attrs — the
  second pass proposes nothing. **Consequence to remember:** the flag audit in open item 5
  is now a category-count guard, not just a mana-model one.
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
- **The skill delegates the heavy work** (engine-season workstream D): `.claude/agents/`
  now holds **card-verifier** (batched card-text verification) and **collection-auditor**
  (full-pool scans), both read-only `Bash, Read`; SKILL.md sends >~3 uncertain cards to the
  first and any full-pool scan to the second, doing the same work inline where no Agent
  tool exists. They are fed by `carddb.py --verify "<card name>"` — a new second mode that
  verifies *named* cards against Scryfall (batched, positionally reconciled, one fuzzy
  retry, 30-day cache in `data/cache/scryfall/`) and prints verbatim oracle text or an
  honest `UNVERIFIED`. Owner-machine follow-up: run `python3 scripts/carddb.py --verify
  "Sol Ring"` once on a networked machine — Scryfall is egress-blocked from the sandbox
  this landed in, so every test is monkeypatched and the live path is unproven.
- **Rules questions have a tool now** (engine-season workstream B): `scripts/rules.py`
  downloads WotC's Comprehensive Rules txt once into the gitignored `data/cache/rules/`,
  parses it, and answers by rule number (`rules.py 903.1` — subrules and section/chapter
  context included), by phrase (`--search`) or by glossary term (`--gloss`); refresh is
  manual (`--refresh`) and any cached copy is used with an honest `fetched <date>` label.
  `scripts/rulings.py "<card>"` adds Scryfall's per-card rulings (30-day cache, stale-okay
  when the network is down, resolved-vs-requested name always surfaced). The skill's
  `rules-reference.md` now leads with **"Ask the CR, don't recall it"** — retrieve → READ →
  cite, and on a degrade fall back to web search *and say the answer is uncited*.
  **Player's-PC feature:** magic.wizards.com is unreachable from the hosted server (not a
  documented public API) and from CI, which is also why there is no `/api/rules` route.
  Back-compat: this added two gitignored cache directories and touched no existing format.
  **Real-CR acceptance: DONE (2026-08-10, from a GitHub runner — the `live-checks`
  workflow on the `claude/live-network-checks` branch):** fetched and parsed the real CR —
  **3,161 rules, 739 glossary entries, effective August 7, 2026** — and answered 903.1 with
  the genuine text. The gate earned its keep: the live page turned out to carry a **literal
  space** in the CR href (`MagicCompRules 20260807.txt`) which the original `_RE_TXT_URL`'s
  `\s`-excluding class truncated at — `--refresh` reported "no link found" with the link in
  plain sight. Fixed (span the space, percent-encode before fetching) and pinned by a test
  against the real 2026 page shape.

## Open items

**1. The placement pass — ONE CARD REOPENED (2026-08-11 review).** Placed and
done: `Crop Rotation` → cloud-ex-soldier (the B2→B3 move), `Mana Drain` → the new
iron-man-armored-avenger deck, `Smaug, Wicked Worm` → the-ur-dragon, Dark Ritual →
yshtola, Hero's Blade + Metallic Mimic → team-leader. **REOPENED: `Codsworth,
Handy Helper` is in NO deck** — its recorded placement was
captain-america-first-avenger, which the player deleted; the card (owned ×1)
silently fell out of every list and only the hardening review caught it. Place it
on the next pass. The principle stands: placing a new card should be a routine
pass over every arrival — and deleting a deck should trigger the same pass over
everything it releases.
- **Cloud rebuild note:** cloud-ex-soldier is now a protected voltron build
  (63/100, B3, `.notes.md` names the engine). A 2026-08-11 `optimize --apply` had
  churned the kill package out for field-popular FF cards (the field builds Cloud
  precon-adjacent); the rebuild restored it as a deliberate manual edit and kept the
  optimizer's three genuine upgrades (Bastion Protector, Summoning Materia, Bonders'
  Enclave). Its four unowned buylist cards left the 99 in the 2026-08-11 owned-only
  migration (see the Current-data bullet): Buster Sword → Wrecking Ball Arm,
  Sram → Bugenhagen, Forge Anew → Professor Hojo, Cloud Midgar Mercenary → Cid,
  Freeflier Pilot — buy any of them and `.buylist.csv`'s Replaces says what to pull.
Cloud's B3 is CONFIRMED (`power.py --rank` 2026-08-11: 63/100, Bracket 3 — every
deck is B3 now). **Then generalize:** the recurring flow should be "new arrivals →
per-deck verdict → place or dismiss". `deckcore.new_arrivals()` already produces the
list and `deckcore.advise_card()` already produces the verdict — the missing piece is
one screen that walks them (`docs/spec-repo-hardening.md` Phase 4 item 1).

2. **Repo hardening (2026-08-11 review): `docs/spec-repo-hardening.md`** — a
   37-agent adversarially-verified sweep produced a three-phase fix tracker
   (safety bugs, data hygiene, front-face/webapp/cache correctness) and the
   ranked Phase-4 improvement roadmap. That spec is the live tracker; tick it
   there, not here.
2b. **Bracket-filtered field data (experiment, not started).** EDHREC publishes
   bracket-specific average decks; the owner builds toward Bracket 3, but snapshots
   use the all-brackets page. `json.edhrec.com` is egress-blocked from every sandbox
   path, so the probe must run **in a GitHub Action** (the `live-checks` pattern
   above proved this works): teach `edhrec.py --snapshot-all` to try bracket-variant
   endpoints and commit whatever answers. See `docs/spec-engine-advisors.md` §3.
3. **PAT renewal when due** (see GitHub token settings) and the quarterly
   keepalive click (above). Auth gate is ON (verified live); collection upload is
   DONE; ranking validation is DONE.
4. **Known UI gap:** dashboard Buy-tab rows for cards not in the deck are plain
   text, not panel-clickable (`docs/codemap.md`, "still open").
5. **Engine season: COMPLETE (2026-08-10).** `docs/spec-engine-upgrades.md` was
   ratified with four workstreams and one follow-up, and **all five PRs have landed** —
   A production-aware enrichment, C goldfish Monte Carlo, D subagents, B the
   Comprehensive Rules layer, and A-F `classify()` consuming the oracle flags (all
   described above). Nothing in that spec is outstanding. The four network-gated acceptance steps were
   run 2026-08-10 **from a GitHub Actions runner** — GitHub runners have the open
   egress the dev sandboxes lack (the codemap's deployment matrix now says so
   explicitly; blurring the two is the blind spot that parked these checks here in
   the first place). The harness is institutionalized as
   **`.github/workflows/recertify.yml`** (`workflow_dispatch` — one click re-certifies
   every live path after a new CR release, a new set, or a Scryfall schema change;
   its first full pass also ran `rulings.py` live and verified the ManaPool/Card
   Kingdom buy-link schemes 4/4). Three of the four steps are DONE:
   1. ☑ **Scryfall schema check of the A1 fixtures** — every `test_oracle_flags.py`
      fixture validated against real Scryfall JSON, 16/16 (produced sets, all flags
      including the A-F `removal`/`wipe`/`counter` tokens against real wordings, the
      MDFC schema shape, and Blasphemous Act confirmed as the documented wipe-regex miss).
   2. ☐ **~30-card flag audit after the first real `enrich.bat` run** — the ONE step
      that still needs the player's machine, because the private collection never leaves
      it. **More important since A-F landed:** flags feed `classify()`, so a wrong flag
      miscategorizes a card in every role count downstream (power, dashboard, optimizer
      role guardrails). The honesty labels fire when data is *absent*, never when a
      derived flag is *wrong* — this audit is the only guard for that case.
   3. ☑ **`carddb.py --verify "Sol Ring"` live** — found, verbatim `{T}: Add {C}{C}.`,
      commander-legal, via the real Scryfall API.
   4. ☑ **`rules.py --refresh` against the real CR** — 3,161 rules / 739 glossary
      entries parsed, effective August 7, 2026, 903.1 answered. This gate also caught a
      real bug (the literal-space href — see the rules-layer bullet above), fixed the
      same day.

## Session workflow reminders

- PRs are **squash-merged**; after every merge, rebuild the feature branch on
  `origin/main` before new work or the next PR conflicts.
- When a session materially changes a deck or ships a feature, update this file and
  tick `docs/spec-interactive-analytics-ai.md` if a tracked feature landed.
- The optimizer never touches manual edits; a second optimizer run on a tuned deck
  must change nothing (idempotence is tested).
