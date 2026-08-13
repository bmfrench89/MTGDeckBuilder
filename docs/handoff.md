# Session Handoff — current state

**Purpose:** everything a new session needs to continue this project without
re-deriving it. This file describes the **current state only**; the full history lives
in git (`git log` — commit messages in this repo are deliberately substantial).
Architecture: `docs/codemap.md`. Working rules: `CLAUDE.md`. Grounding rules
(canonical): `.claude/skills/mtg-deckbuilder/references/grounding-rules.md`.

_Last updated: 2026-08-12._

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
  **Self-heals from squash-merge conflicts (2026-08-11):** PR #104's squash rewrote
  deck files the server had local commits on and wedged the pull (seen live on the
  player's phone). The script now parks local state on a PUSHED `server-rescue-<date>`
  branch before resetting to upstream; the status line shows "synced — RECOVERED"
  naming the branch, and **a session must merge that branch back** when it appears.
  **Hardened 2026-08-12:** the rescue branch only ever held COMMITTED state — an
  app save landing during the pull window was destroyed by the reset (reproduced,
  then fixed). Uncommitted work is now stashed before the pull and restored
  after; a conflicted restore stays parked in `git stash list` with a warning;
  a still-dirty tree refuses the self-heal entirely. The wider network/attrs
  plan (allowlist, committed attrs snapshot, remaining sync races) lives in
  `docs/spec-network-and-attrs.md` — the live tracker. **Phase 2 SHIPPED
  2026-08-12** (player approved dropping the Scryfall column): the
  attrs-snapshot Action enriches the committed name-only snapshot into an
  8-column `collection_attrs.snapshot.csv` on GitHub runners, five-guarded
  (refuse-beside-private, `--min-match 95`, plausibility gate, shared
  concurrency group, regenerate-not-rebase retry), with carddb's guarded fuzzy
  (spelling repairs only, never substitutions), the sync push-retry/flock/TTL
  hardening, and the goldfish + /collection consumers updated. **First live run PASSED
  2026-08-12** (99% resolution, all guards green, committed as `5fe3a16`) —
  every clone now loads typed data, and power re-scored on it (yshtola 78).
  ⚠ **Do not run the optimizer with `--apply`/⚡/`refresh --optimize` until
  the typed-data role-repair churn filed in `docs/spec-optimizer-hardening.md`
  is fixed** — the archetype-blind template now proposes cutting
  field-superior deliberate keeps (four decks carry notes churn guards, but
  the pass moves to new victims). Phase 1 (the environment allowlist) remains
  the player's five-minute flip and is NOT needed by the Action.
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
  over-committed copy); Thriving Isle added as the 100th card. Ownership
  RESOLVED (2026-08-11): the player owns none of the twelve snapshot-absent
  cards (but does own 2× the Cosmic Spider-Man commander itself →
  owned_additions.txt); all twelve were replaced with owned substitutes and
  buylisted — details in the deck's .notes.md. The player DELETED
  captain-america-first-avenger via the
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
  yshtola took Krile Baldesion, Contaminated Aquifer, and a 4th Plains; the
  eight hand-built spiders followed on player confirmation of non-ownership
  (see the deck's `.notes.md` for the full mapping). Every deck is 100 cards,
  singleton-clean, **zero unowned cards anywhere**. Cloud's stray duplicate
  commander line (same bug as yshtola's) was also removed.
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
- **Six decks total, and every one is Bracket 3** (fresh-export scoring,
  2026-08-11 post-optimizer-sweep — the owner's "Bracket 3/4 where possible" aim
  is MET across the board — scores below are TYPED-data, 2026-08-12, the first
  scoring on real curve/role counts): Y'shtola 78 · Iron Man 72 · Cloud 71 ·
  Team Leader
  69 · Cosmic Spider-Man 64 · Ur-Dragon 53. No deck can reach B4 from the owned
  pool (4 unique Game Changers owned, total). The server re-scores on the full
  enriched CSV after each sync — expect small number shifts, not bracket changes.
- **Fresh collection export installed 2026-08-11** (Sorted CSV: 2,621 unique /
  3,773 copies after the owned_additions merge; was 2,518/3,602). The committed
  name-only snapshot was regenerated from it in the same session.
  `owned_additions.txt` dropped Vito and Force of Will — the new export carries
  both, so the overrides would double-count; the player-confirmed 2x Cosmic
  Spider-Man stays (export still lists 1). **Player to-do:** upload the same
  export via the app's `/collection/upload` so the server's private CSV matches,
  then the daily sync re-enriches (Scryfall was egress-blocked in the sandbox
  this landed in).
- **Painful Truths revert (2026-08-11):** an 8/11 manual replace had put the
  never-owned Painful Truths into yshtola over Read the Bones — the only unowned
  card across all six decks against the fresh export. Read the Bones is back
  (optimizer advisory: 70/100 strong fit), Painful Truths is buylisted with
  Replaces=Read the Bones, and the revert is logged in `.changes.csv`.
- **2026-08-11 optimizer sweep on the fresh export (all six decks, applied):**
  Iron Man took 9 spell swaps (0%-field big-blue filler → 26–68% field staples:
  Pensive Professor, Kid Loki⇄, Laboratory Maniac, Reconnaissance Mission⇄,
  Bident of Thassa, Professor Hulk⇄, Fellwar Stone⇄, Loki God of Mischief,
  Lightning Greaves⇄) + Bonders' Enclave → Reliquary Tower, and rose 70 → 73
  (tied #1). Cosmic Spider-Man: To the Rescue → Spider-Punk (83%), Plaza of
  Heroes → Vibrant Cityscape (resolves the own-1-committed-2 Plaza conflict;
  team-leader keeps it; 55 → 54 is the raw-card-quality cost, field overlap
  +1). Ur-Dragon: Dragonhawk → Dragonspeaker Shaman (57%), Gilded Goose →
  Savage Ventmaw (34%). Team Leader: Hero's Blade → Avengers Assemble! (54%).
  Cloud and Y'shtola: already aligned, buylist refresh only. **The single owned
  Reliquary Tower went to Iron Man by decision** — Y'shtola's Ash Barrens is
  protected in its `.notes.md` so the optimizer stops re-proposing that swap.
  The ⇄ swaps deepen shared-copy shortfalls (Fellwar Stone and Lightning
  Greaves are now short 2) — priced in `data/wishlist.md` per mark-don't-block.
- **The sleeper audit is now a ratified process (2026-08-11, player request):**
  `.claude/skills/mtg-deckbuilder/references/card-review-method.md`, wired into
  SKILL.md and CLAUDE.md. Field % is a prior; the verified card text read against
  the deck's engine is the verdict. Born from Wizard's Staff: 4% field, but it
  DOUBLES the equipped creature's triggers — on Y'shtola that's drain-4/gain-4
  per big spell. The audit's first full pass walked all 705 two-week arrivals
  (124 unplaced rares/mythics card-by-card) and produced **19 verified swaps**
  across the six decks, every text checked against Scryfall/Gatherer via web
  search (API egress-blocked): Y'shtola took Wizard's Staff; Iron Man took
  Valeria Richards, Wizard's Staff #2 (on Archmage), Riddles in the Dark, Myriad
  Landscape; Cap took Mjölnir (doubles Cap's damage, equip worthy {1}),
  Captain Mar-Vell, Silver Sable; Cloud took Forge Anew (the buylist arrival —
  Hojo pulled as recorded), Inventory Management, Raubahn; Cosmic took
  Sensational Spider-Man, Web Up, Villainous Wrath (its first wipe); Ur-Dragon
  took Dragon Broodmother, Sylvia Brightspear, Kaalia, Deserted Beach. All are
  `Source=manual-replace` in `.changes.csv` (optimizer-protected — verified: all
  six re-previews say "already aligned"), documented in each `.notes.md`, and
  the verified-role cards were added to `mtglib.py`'s curated DRAW/REMOVAL/WIPES
  lists so the power score can read them (full test suite green after). Post-
  audit ranking on TYPED data (2026-08-12): Y'shtola 78 · Iron Man 72 · Cloud
  71 · Cap 69 · Cosmic 64 · Ur-Dragon 53 — the name-only scores had
  under-read Cloud/Cap/Cosmic by 10-13 points, and Ur-Dragon's
  interaction-for-threats trade (rebuild path in its notes) costs ~5 real
  points, not the 8 the name-only scorer showed. Benched-with-reasons and the Hobbit
  verdict (zero of 96 uniques beat an incumbent; Thorin/Thranduil/Gandalf/
  Radagast are future commander seeds) live in the audit notes sections.
- **Deep-research re-review of the sleeper audit (2026-08-11, 12-agent web
  sweep incl. YouTube/Reddit/deck-tech coverage): 18 of 19 swaps CONFIRMED with
  sources; 5 corrections applied** — Laboratory Maniac OUT of iron-man (TRAP:
  Demonic Consultation/Tainted Pact are color-illegal in mono-U and zero owned
  enablers; Falcon, Winged Wonder in, own 2); Vibrant Cityscape → Fabled
  Passage in cosmic (Cityscape is an Evolving Wilds clone, deck ran two
  already); Chaos Warp (0% here, own 6) → Lost in the Maze in cosmic (the only
  owned mass stun generator — Sensational fuel + post-alpha hexproof); Think
  Twice → Thor, Asgard's Avenger in team-leader (45% field, own 2, was in NO
  deck); Dragonhawk, Fate's Tempest REINSTATED in ur-dragon over Opportunity
  (the 8/11 optimizer cut was a 0%-field recency artifact; community rates it
  4.5/5 in dragon shells). Rules findings logged in each deck's notes: Kaalia-
  cheated creatures are never declared attackers (no Ur-Dragon draw, no attack
  triggers, incl. Ventmaw's mana); Broodmother tokens don't trigger Lathliss/
  Miirym; Mjölnir's discard mode is symmetric and only equips worthy; Mar-Vell's
  flash needs an opponent's spell first; Spider-Punk blanks our own counters and
  nonbos with Arachnogenesis's fog; Forge Anew equips your turn only; Raubahn
  attach resolves before Cloud's draw if stacked right; iron-man grants flying
  only to attacking MODIFIED creatures. Ur-Dragon interaction concern settled:
  field average is ~4-5 interaction slots, this deck keeps ~10. Stale buylist
  Replaces cells refreshed (yshtola x2, cloud x1). Bench queue in notes:
  Ur-Dragon's next wave (Atsushi, Ao, Hraesvelgr, Niv-Mizzet Visionary,
  Beledros, kicked Rite of Replication line), Cloud's Bloodforged Battle-Axe,
  Cap's Quicksilver/Jocasta/Dismantling Wave tier.
- **Commander candidates ranked (same sweep; owned-support grep-counted):**
  BUILD_NOW: **Helga, Skittish Seer** (Bant, EDHREC #67 — the one green
  commander whose engine matches this UB-heavy big-creature pool; ramp core
  owned) and near-BUILD_NOW **Hulk, Gamma Goliath** (22-card owned Hulk-orbit
  cluster + owned staples; RG identity checks needed at build time).
  BUILD_WITH_BUYS: **Thranduil, the Elvenking** (consensus best Hobbit
  commander, cEDH-article-worthy; ~$15-25 of bulk elf staples; Sultai NOT
  green; Sindarin Liege x2 is the auto-include second legendary Elf);
  **Kaalia of the Vast** (~$40-60 payload — big A/D/D + reanimation; do NOT
  dismantle ur-dragon, she stays in its 99 meanwhile); **Tifa Lockhart**
  (~$15-30 + ~20 basic Forests; the fetch-land instant-speed doubling core is
  already owned; sandbox auto_build saw her as colorless — enrich first);
  **Thorin, Mountain-king** (mono-R equipment voltron, NOT dwarf tribal; the
  good equipment is committed to cloud; buying Thorin King of Durin's Folk
  would unlock the owned Boros dwarf pool instead). SKIP: Selvala (zero
  engine pieces owned — her best home IS ur-dragon's 99), Gandalf Wandering
  Wizard (draft common, no engine), Radagast (no green fatty base yet),
  Sindarin Liege as helm, Vadmir/Neriv/Renet (not green — verified B/RWB/U).
- **Field-overlap validation post-sweep (fresh, larger snapshots): PASSED** —
  Team Leader 25/25 · Cloud 24/25 · Y'shtola 21/25 · Ur-Dragon 21/25 · Cosmic
  Spider-Man 18/25 · Iron Man 14/25. Iron Man and Spider-Man sit lower because
  their fields' top-25 are majority unowned Marvel cards (11 and 7 not owned) —
  above the ~50% revert threshold, gaps are buylisted, not silently shipped.
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

**0. Optimizer role-repair churn — THE next engineering session.**
`docs/spec-optimizer-hardening.md` (2026-08-12 section) has the full finding:
the first attrs snapshot armed the archetype-blind `ROLE_RANGE` template
(iron-man's typed counts read counter:15 vs max 6) and the repair path ignores
the ≥25-point field margin, so previews now propose cutting field-superior
deliberate keeps (e.g. Wall Crawl 41% → Masked Meower 18%). **Do not run
`--apply` / ⚡ / `refresh --optimize` until it lands.** Four decks carry
notes-file churn guards for the first-round victims; the pass moves to new
ones, so guards are a tourniquet, not the fix. Three fix directions are in the
spec. Concrete exhibit if anyone doubts castability matters: Mana Drain's
{U}{U} is on-curve castable ~35% in ur-dragon (manabase.py, typed) vs
effectively always in iron-man — the template wanted it moved anyway.

**1. Phase 1 network allowlist — the player's five-minute flip.**
`docs/spec-network-and-attrs.md` §2: five hosts, then the verification
checklist and the PC-only doc sweep (verified file:line list is in §2).
Nothing else depends on it; every future sandbox session benefits.

**2. Player physicals (unchanged, still worth doing):**
   - Upload the fresh Sorted export via `/collection/upload` — the SERVER's
     private CSV is still the pre-2026-08-11 one; sandboxes have typed data
     now, so the hosted app is the last stale surface.
   - ~6 spare basic Islands for iron-man (deck wants 29, export counts 23).

**3. Standing card-placement plans (owned-only, decided, waiting on arrivals):**
   - 2nd Mana Drain → yshtola, cutting **Misdirection** (the old plan said
     Absorb, which has since become Wizard's Staff). Field 27/20/15 across
     iron-man/ur-dragon/yshtola and the castability math keep copy #1 in
     iron-man.
   - 2nd Reliquary Tower → yshtola (46% field there; ~$3 — cheapest wishlist win).
   - Commander shortlist ranked and grounded (see the sweep bullet above):
     Helga and Hulk, Gamma Goliath are BUILD_NOW from owned cards whenever the
     player wants a seventh deck.

**4. Attrs-snapshot follow-ups (small, from the first live run):**
   - Retry split-name misses by FRONT FACE through the guarded fuzzy — the 17
     unmatched are all "Front // Back" names; the fold guard already compares
     front faces (`spec-network-and-attrs.md` §7).
   - The ~30-card flag audit (engine-season item below) got MORE load-bearing:
     flags now ship to every clone via the committed snapshot.

**1b. Placement principle (standing):** new arrivals → per-deck verdict →
place or dismiss, per the ratified sleeper audit
(`.claude/skills/mtg-deckbuilder/references/card-review-method.md`);
`deckcore.new_arrivals()` + `advise_card()` compute it, and with the attrs
snapshot live, `new_arrivals`' identity-matched `fits` now works in every
sandbox. The one-screen walk of that flow remains open
(`docs/spec-repo-hardening.md` Phase 4 item 1).
- **Cloud rebuild note:** cloud-ex-soldier is a protected voltron build
  (typed-data 71/100, B3, `.notes.md` names the engine and the 2026-08-12
  churn guards). Buy any of its four buylisted cards and `.buylist.csv`'s
  Replaces says what to pull (Forge Anew already arrived and was pulled in,
  2026-08-11).

1c. **Next-features research (2026-08-13): `docs/research-competitive-landscape.md`** —
   a six-agent competitive-landscape sweep (deck builders, the AI-tool wave, playtest/
   sim, brackets, collection tools, coaching/UX). Verdict: the app already holds the
   market's most-demanded positions (owned-only building, copy-conflict tracking,
   grounded AI, deck-aware math, optimizer restraint; `power.py` bracket rules confirmed
   current) — the ranked build list is §4 there: goldfish "clock" mapped to the official
   bracket turn anchors, a Rule-0 table card, declared-bracket compliance (advisory, with
   a Scryfall `game_changer` sync check), a game log feeding tuning, a mulligan trainer.
   Sequencing in §6; still gated behind open item 0 where optimizer-adjacent.

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
