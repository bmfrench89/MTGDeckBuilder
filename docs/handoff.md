# Session Handoff — current state

**Purpose:** everything a new session needs to continue this project without
re-deriving it. This file describes the **current state only**; the full history lives
in git (`git log` — commit messages in this repo are deliberately substantial).
Architecture: `docs/codemap.md`. Working rules: `CLAUDE.md`. Grounding rules
(canonical): `.claude/skills/mtg-deckbuilder/references/grounding-rules.md`.

_Last updated: 2026-08-15._

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
  months. Missing it sleeps the app; no data is lost. **The paid tier was offered
  and declined 2026-08-14** (`spec-infra-hot-paths.md` Phase 4): the free tier
  stays, this keepalive stays, and the in-app sync thread stays instead of a
  Scheduled Task. Don't re-propose it unless one of those actually starts hurting.

## Card-panel Replace/Remove: the " // " trap reached the editor (FIXED 2026-08-15)

Live bug report: "I tried to replace a card in the Smaug deck and it did not work."
Root cause: `webapp/app.py`'s `_edit_deck_card` matched the outgoing card by raw
`_norm` equality while the panel's `data-key` can carry EITHER form of a DFC name —
decklist figures key the deck file's own form, EDHREC/field rows key what the
snapshot emits (often the front face alone). `Smaug, the Great Calamity // Spew
Flame` vs `Smaug, the Great Calamity` therefore no-opped. Worse, BOTH failure paths
(`would duplicate` refusal and edit-found-nothing) returned a bare redirect, and the
panel reloads on any redirect — failure was pixel-identical to success. Fixed: the
editor now matches `name_keys()` (front-face-aware, same test the route's singleton
guard already used), refusals return 409/404 with a reason, and the panel alerts the
server's text instead of reloading. Regression tests cover both DFC directions, the
`SP//dr` no-split guard, and the two error responses (`test_deck_edit`,
`test_add_card`).

## 2026-08-15: Hobbit import, the Smaug package, Delney, proxy sheets

**Collection:** the new Sorted export is live — 2,691 unique / 3,890 total, 70 new
uniques, 42 quantity bumps, nothing lost. The Hobbit (HOB) is now 116 uniques in the
pool. Enrichment for the ~88 new cards happens server-side on the next sync (Scryfall
is egress-blocked in sandboxes); until then those cards ride on deck attrs + verified
type lines. **Iron Man is retired at the player's direction** ("for now") — all five
deck files deleted in one commit, recoverable verbatim from git history; no pins
referenced it; its field snapshot stays for a future rebuild.

**Sleeper audit (both verify rounds on the deck-verify runner, 84 cards, 0 unverified):**
- **The Ur-Dragon got the Smaug package** — Smaug the Magnificent IN for Reconnaissance
  Mission (0%), Desolation of Smaug IN for Thought Vessel (5%, colorless-only rock in a
  "fixing above all" deck), Smaug the Impenetrable IN for Kolaghan, the Storm's Fury
  (15%, dash fights eminence). Engine reasons in the deck notes. Dragons 30 → 31.
  **Lozhan stays on purpose** (verified: every Dragon cast deals its MV in damage —
  removal stapled to the plan; its 14% underrates this deck). Draw dips 8→7 against
  template — the commander IS the draw engine, said openly in the audit. Desolation of
  Smaug is curated into mtglib WIPES. Tiamat's buylist row re-pointed.
- **Y'shtola got Delney, Streetwise Lookout** (39% field!) for Read the Bones (6%):
  Y'shtola is printed power 2, so Delney doubles BOTH her triggers — and Blood Artist's
  and Vito's. The compounding is written up in the deck notes as a protected engine piece.
- **Cosmic Spider-Man got Skyward Spider** (21% field, on-tribe ward body) for Relic of
  Legends (10%).
- **Benched with reasons:** Glamdring (Banner's 23 spells are cheap + pip-heavy, and no
  equipment shell), The Reaver Cleaver, Bard the Bowman, My Precious, An Unexpected
  Party, Lord of the Eagles. **Commander seeds noticed, not built:** Tom Bombadil
  (needs a Saga package), Mimeoplasm Revered One, a Beorn bear kernel and an
  Azog/Bolg goblin kernel from HOB. Terrian and Tyrox returned "(no oracle text)"
  from the verify runner — treated as unverified, judged nowhere.

**Proxy sheets shipped** (`scripts/proxy_sheet.py` + `/deck/<stem>/proxies`): 63×88mm
cells, nine per page, exact printings from the export's set+number, Chromium-measured
geometry. The index links each deck's **buylist** proxies — decks are owned-only by
rule, so what's worth printing is the upgrade you're deciding whether to buy.

## Deck export: HTML report + PDF via the browser (NEW 2026-08-15)

Spec: `docs/spec-deck-export.md`. Player asked for "export a deck as an html/pdf
report". Scoping found the HTML report already existed — `build_dashboard.generate()`
has always emitted a self-contained single file — so the work was two real gaps, not a
new feature.

- **`GET /export/deck/<stem>.html`** downloads that file as an attachment
  (`editable=False`, so nothing posts into the void; no singleton banner, which is a
  live-surface alarm). Sits beside `/export/deck/<stem>.txt`, takes the same `?raw`.
  The decks list now offers **`.txt`** and **`Report`**, and the Report link's title
  carries the honesty label: images need a connection, Ctrl+P for a PDF.
- **Print actually works now.** Every theme is dark; browsers drop backgrounds but keep
  text colour, so the dashboard printed near-white on white. The `@media print` block
  was rewritten to repaint ink-on-paper and **moved to the end of the `<style>`** —
  `@media` adds no specificity, so sitting above the inlined `add_card.css` /
  `card_panel.css` meant any print rule could be silently outranked (the old
  `.ac { display:none }` worked only because `add_card.css` never sets `display`).
- **There is deliberately no PDF generator**, and shouldn't be: `scripts/` is
  stdlib-only, card images are browser hotlinks a server-side renderer can't fetch, and
  the host is a free tier with no cairo/pango. The browser's print dialog is the export.
- **Two live bugs found and fixed on the way.** `shared_html` never closed its
  `<div class='tablewrap'>` (10 opens / 9 closes in a real render). And the explainer
  print rule was a **no-op**: `<details>` is emitted closed, and a closed `<details>`
  hides children through the UA's `::details-content` box, not the child's `display` —
  so every "what this means" caveat was missing from paper while a test passed on the
  substring. Verified in headless Chromium: the paragraph's `checkVisibility()` goes
  `False → True`. `tests/conftest.py` now has `print_block()` so print tests assert
  against the whole brace-matched block instead of a fixed `[:200]` window.
- **Backlog, not built:** proxy sheets (3×3 grid at 63×88 mm) — the one genuinely
  print-geometry-shaped thing missing. Own spec, own player decision.

## deck-verify: the sandbox's way out of the egress block (NEW 2026-08-14)

`.github/workflows/deck-verify.yml` runs the two **network-dependent grounding steps** on a
GitHub runner, because a Claude Code sandbox cannot reach Scryfall or EDHREC (the egress
proxy answers **403 to CONNECT** — `carddb.py --verify` returns UNVERIFIED, `optimize.py`
sees 0 field cards). Card Kingdom, Draftsim and Gatherer are blocked too; only `WebSearch`
resolves, and a search summary is not verbatim oracle text.

- **Triggers on push to `claude/**`**, not just `workflow_dispatch` — a dispatch-only
  workflow is undispatchable until the file reaches the DEFAULT branch, which is no use to
  the session authoring it. Dispatch inputs (`commander`, `cards`, `commit`) are kept for
  manual runs.
- **It pushes only to the ref it ran on** (`HEAD:${{ github.ref_name }}`). This is the whole
  reason it is a separate file: `field-snapshots.yml` ends in a hardcoded
  `git pull --rebase origin main` + `git push origin main`, so **dispatching THAT on a
  feature branch would rebase the branch's commits onto main and push them there — a silent
  merge with no review.** Do not "simplify" the two into one.
- The card list lives in **`data/reference/verify-queue.txt`** (reviewable in the diff, and
  a place to queue work for the next run). Results go to the job log *and* an artifact.
- **First run (31852039320) verified 55/55 cards, 0 UNVERIFIED, in 13 seconds** and
  committed `data/reference/field/bruce-banner.json` back to the branch. It corrected real
  errors: **Squallmonger** hits creatures *with* flying (so it misses a reach commander) —
  it had been shortlisted on memory; **Hulkbuster Armor** grants flying, which would make
  the Hulk dodge our own sweeper pings; **Warmonger** does work but lets *any player*
  activate it. Read a session's exclusions as provisional until this has run.

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
  ⚠ **The role-repair churn is FIXED in code (2026-08-13, Phase 8) but the
  `--apply`/⚡/`refresh --optimize` freeze stays until one live preview run
  confirms it against the full private CSV — see open item 0.** Phase 1 (the
  environment allowlist) remains the player's five-minute flip and is NOT
  needed by the Action.
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

- **NEW DECK 2026-08-14: `bruce-banner-incredible-hulk` — Temur (U/R/G), Bracket 3,
  power 71/100.** Built for the player's *brother*, whose card it is — the commander is
  deliberately NOT in the collection, so `deck_stats` reporting one card "not owned" is
  correct, not a defect. **The trap this deck exists to document: Bruce Banner costs
  `{U}`.** The `{2}{R}{R}{G}{G}` printed on the card is the *transform* cost, so the
  color identity is **Temur, not Gruul** — a Gruul build would have been the wrong deck
  entirely. Oracle text came from the player's photographs (grounding rule #6) because
  Scryfall, EDHREC, Card Kingdom and Draftsim are ALL egress-blocked in the sandbox
  (`carddb.py --verify` → UNVERIFIED, proxy 403); `WebSearch` still resolves and
  corroborated the `{U}` front-face cost across three independent sources.
  Engine: flip to an 8/8 reach/trample, then damage him **while he is attacking** —
  Enrage untaps him and adds a combat phase. Pingers are Prodigal Sorcerer, Thornwind
  Faeries and Brash Taunter (fight your own Hulk: he takes 1, the indestructible Taunter
  takes 8 and throws it at a face); Roaming Throne naming **Hero** doubles every Enrage
  trigger. Built from the **uncommitted** pool so it sleeves standalone without pulling
  cards out of the player's six decks. Two exclusions are deliberate and documented in
  the deck's `.notes.md`: **Lightning Greaves** (shroud would stop you targeting your own
  Hulk — Swiftfoot Boots/Champion's Helm grant hexproof instead, which does not) and
  **Basilisk Collar** (deathtouch on a Tim kills your own commander). `combo_detector`
  flags Godo + Helm of the Host as infinite combats; Helm is unowned and is buylisted
  under an explicit "Bracket 4 — DO NOT ADD" tier alongside Caltrops and Aggravated
  Assault. **Both network gaps are now CLOSED — see the deck-verify workflow below.**
  Final: Bracket 3, power **72/100**, top-25 field overlap **13/25 = 52%** (above the ~50%
  floor). `optimize.py` was run on real field data and **deliberately not applied**: it
  proposed cutting the verified engine piece Barbed Field for Blasphemous Act (13 damage
  kills our own 8/8 commander in a one-creature deck) and pulling `[shared]` Counterspell /
  Rhystic Study out of the player's other decks. The engine pieces are named in the deck's
  `.notes.md`, which is what protects them from the next optimizer run.
  `Bruce Banner // The Incredible Hulk` was added to `data/reference/commanders.csv`
  (G R U, `voltron counters ramp`) — note `auto_build.py`'s CLI has **no `--identity`
  flag** despite SKILL.md documenting an `identity=` syntax; `build()` takes the kwarg but
  nothing exposes it, so an unknown commander auto-builds as colorless until it is added
  to `commanders.csv`.

- **Deck sections are now EDHREC-style TYPE sections (2026-08-11)** — Commander /
  Creatures / Instants / Sorceries / Artifacts / Enchantments / Lands / Basics —
  across all decks, kept by the new `scripts/deck_sections.py` (idempotent;
  `--all --apply`). `auto_build` emits the same shape for future decks. Roles +
  power-list tags (Game Changer, Tutor, …) now show in card details on both
  surfaces via `deckcore.load_power_tags`. The migration fixed real misfiles
  (Rhystic Study and Lightning Greaves sat under "Lands" in ur-dragon). ~15 cards
  **All `Unsorted` sections are GONE as of 2026-08-13** (Phase 0): the typed
  attrs snapshot resolved every one, and the server now re-runs the regroup
  itself after a sync that brings fresh attrs (skipping any deck with
  in-section comments, which a regroup would drop). **cosmic-spider-man repaired 2026-08-11**: the 99-card mystery was a corrupted
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

## Performance & background work (`docs/spec-infra-hot-paths.md`, Phases 1–3 shipped 2026-08-14)

The app now runs engines inline per request, so three things were made cheap. Know
these before touching the analysis path:

- **`scripts/memo.py`** memoizes `mtglib.load_collection` and `deckcore.analyze_deck`
  on **file identity** (`(path, mtime_ns, size)` per input; `(path, None)` for a
  missing file, so creating it invalidates). A warm dashboard render of the-ur-dragon
  went 377 ms → 25 ms. **The cached values are SHARED — treat them as frozen.**
  `analyze_deck` copies only the outer dict; `coll`, `idx`, `enriched`, `report` and
  `assessment` are the same objects every caller holds. `tests/test_memo.py`
  fingerprints them across every consumer, and a real mutator injected into
  `build_dashboard` fails that test — if it ever fails, find the mutator, don't relax
  the assertion. Unfingerprintable inputs (a preloaded collection list,
  caller-supplied `refs`) bypass the cache by design. Every webapp write path calls
  `_invalidate(stem)`, and an `after_request` backstop drops the cache on any
  state-changing method.
- **`goldfish.ab_for_deck`** disk-caches the paired A/B behind the Replace flow's
  shift-click (and the CLI's `--ab`). Errors are never cached.
- **`webapp/enrich_bg.py`** runs post-upload Scryfall enrichment in a daemon thread —
  same pattern as `sync.py`, including the *interrupted* status a reload-killed thread
  gets instead of a permanent spinner. `carddb.write_attrs_csv` made the attrs write
  atomic for every caller.
- **`spellbook.FAIL_TTL`**: an unreachable Commander Spellbook used to cost a fresh
  network attempt on **every deck-page view** (315 ms measured, 25 s ceiling). A
  failure is now remembered for five minutes — never served as data.

## Mana intelligence (`docs/spec-mana-intelligence.md` — **Phases A–G ALL SHIPPED 2026-08-14**)

**The rollout legs are the only open items, and they are data, not code (H2):**

1. **Dispatch the attrs-snapshot Action** (workflow_dispatch button, or wait for
   Monday's cron) — regenerates the committed snapshot with v2 flags + FlagsVer.
2. **Re-enrich the server's private CSV** — a PythonAnywhere console
   `python3 scripts/carddb.py --collection data/collection/collection.csv`, or a
   fresh `/collection/upload`. **Leg 2 is not optional if leg 1 ran**: the stale
   private file's Flags column overwrites the snapshot's per card (the overlay
   trap the FlagsVer coupling rule guards — v1 flags then correctly read as v1).

Until both legs: every surface shows pre-vocabulary labels ("fetch census
unavailable — re-enrich to unlock"), numbers unchanged. After both: run H3's
acceptance — `manabase.py --deck data/decks/the-ur-dragon.txt --collection
data/collection/collection.csv` should show Wood Elves with 5 targets, Farseek
~10, a restricted bucket ≥3 (count what enrichment finds), and per-color sources
LOWER than the current 17/15/15/21/17 — then `carddb.py --audit-flags` and
eyeball ~30 rows. The goldfish REPORT_SCHEMA bump (2→3) means the first view of
each deck after deploy re-simulates once.

What shipped (details in the spec + commit messages):

Born from the player's ur-dragon question ("why Wood Elves with only 2 Forests?"
— the deck has 5 Forest cards, but nothing could say so). The spec was
adversarially verified by three lenses before implementation; Phase A is on the
branch:

- **Vocabulary v2** (`oracle_flags`): `fetch:land` / `fetch:basic` /
  `fetch:<type>` / `fetch:basic-<type>` / `mana-restricted`, read from the
  search CLAUSE — Demonic Tutor stays silent, Krosan Verge unions two types,
  Expedition Map fetches without being ramp. This fixed a live miss: the v1
  regex needs the literal word "land" and `"island"` doesn't match `\bland`, so
  Farseek / Nature's Lore / Wood Elves carried NO flags at all (Wood Elves not
  even `ramp`).
- **`FlagsVer`** (11th attrs column = `oracle_flags.VOCAB_VERSION`): flags and
  their version are ONE write — a Flags column arriving without FlagsVer resets
  the card to version 1. Mutation-proved against the real rollout window (v2
  snapshot under a stale private CSV must not read as verified-unrestricted).
- **Proven inert**: 0/2,621 cards change classify() roles, 0/6 decks change
  power/bracket/categories. v2 tokens map to no `FLAG_ROLES` entry on purpose.
- **B: the census + restricted split** — `manabase.fetch_census` ("Wood Elves:
  N targets in THIS deck"), spend-restricted lands out of the Karsten pool into
  their own bucket; pre-vocabulary data degrades to today's numbers + labels.
- **C: five surfaces** — dashboard Mana tab (= the app deck page), assess page,
  Build-Next, assess packet, manabase CLI; the card panel shows "Fetches: N
  legal target(s)" on the fetcher itself.
- **D: the standing Mana-health banner** — computed at render time from the
  memoized analysis, so every manual edit re-evaluates on the panel's own
  reload; ur-dragon shows "33 lands (floor 36)", the other five decks show
  nothing. `advise_card` adds a `mana_note` at add-time for thin/no-target
  fetchers.
- **E: the optimizer cannot strand a fetcher** — a running ledger across both
  land passes + the buy pairing (refusals reported as `land_guard`/CLI/⚡
  flash); basics repair is pip-proportional via the shared
  `deckcore.basics_by_demand` (round-robin gone); inert on pre-vocabulary data
  (all six real-deck previews byte-identical).
- **F: auto_build tie-breaks toward fetchable lands** (take-loop only — never
  in `assess_card`, whose score feeds the optimizer); basics can no longer leak
  into the nonbasic pass.
- **G: the goldfish admits fetch effects are unmodeled** (assumptions line
  naming the cards) — REPORT_SCHEMA 2→3.

## Open items

**0. Optimizer role-repair churn — FREEZE LIFTED 2026-08-14.** The acceptance
step is done: `optimize.py --all` ran as a preview against the **full private
CSV** from a PythonAnywhere Bash console. All six decks returned **"already
aligned with the field — no changes"** — zero swaps proposed anywhere, so an
`--apply` would have written nothing. Every `buy` line was field-superior
(Herald's Horn 83% over Visions of Beyond 0%, Curiosity 63% over Misdirection
13%, Tiamat 68% over Reconnaissance Mission 0%, …), and all six expected
`manual_holds` fired: Hojo, Vibrant Cityscape, Nature's Lore, Frantic Search,
Laboratory Maniac, Absorb. **`--apply` / ⚡ / `refresh --optimize` are cleared for
use.** The CLAUDE.md top-25-overlap check governs the first real `--apply`.

Phase 8's fixes are what got it there: the **field veto** (a swap may never cut a
card the field plays MORE than the incoming one) and an **archetype-aware role
template** (`role_ranges` reads the deck's `# Archetype:` header, so iron-man's
counter:15 is correct rather than nine over budget). Phase 12 added the fit
scorer reading THE same template, the role-point swing capped below the margin
(spread ×2 = 24 < 25, tripwire-tested), and the symmetric never-re-add rule.

**The run found three live bugs that no sandbox preview could have — keep this in
mind before trusting a snapshot-only result again:**

1. **The field veto guarded what the optimizer DID, not what it ADVISED.**
   cosmic-spider-man offered Sun-Spider (25%) and Spider-Man, To the Rescue (29%)
   as "1 pt short of auto-swap" over **Wall Crawl (41%)** — the exact card and
   inversion the original churn finding was about. The tool refused the swap, then
   recommended the player make it by hand. The riser gate now applies the same
   `inc_add >= inc_cut` comparison. One rule, both surfaces.
2. **The Cuts surface never protected manual adds.** `cut_candidates` passed the
   deck `.txt` to `deckcore.manual_adds` (which wants the `.changes.csv`) and
   iterated its list-of-rows as if it were a dict of names. Neither fault could
   raise, so the protected set was silently **always empty** and hand-picked cards
   were ranked with no "your call, not the tool's" flag. Note the second half:
   `cut_candidates`'s `stem` is a BASENAME for report labelling, so the companion
   path needs its own full-path stem or the lookup goes relative to cwd.
3. **The manual-adds advisory listed cards no longer in the deck.**
   `.changes.csv` is append-only, so y'shtola's Painful Truths — added and
   reverted the same day — was still printed under "the optimizer never cuts
   these", as "(no opinion — not resolvable in the collection)". Filtered to
   cards actually in the 99.

**0b. The original finding, for reference.**
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

1b-season. **The "Table-Ready" season SHIPPED COMPLETE (2026-08-13):
   `docs/spec-table-ready.md`.** Twelve phases from the competitive-landscape
   research plus player direction. Suite **507 → 602**, offline, exit 0;
   `scripts/` still stdlib-only.
   - **Phase 8** optimizer gate: archetype-aware `ROLE_RANGE` + a **field veto**
     (a swap may never cut a card the field plays more than the incoming one).
     See open item 0 — the freeze lifts on one live preview run.
   - **Phase 0** deck hygiene: all six decks regrouped on typed data (Y'shtola's
     misfiles and its split Plains pair fixed, `Unsorted` gone repo-wide,
     idempotent); the add AND Replace paths can no longer manufacture split
     basics; the server auto-regroups after a sync, skipping decks with
     in-section comments.
   - **Phase 1** a `Power` column through enrichment → `Card.power` → the clock.
   - **Phase 2 (flagship)** the **goldfish clock**: median turn this deck
     presents lethal, mapped onto the brackets' own turn anchors. Combat-only
     and labelled UNDERSTATED for drain decks; no clock at all without power
     data. `--ab` now reports clock deltas over the same paired games.
   - **Phase 3** `# Bracket:` header — your setting headlines, the detected
     verdict and reasons always stay visible. `recertify.yml` gained a Game
     Changers diff against Scryfall's `is:gamechanger` (the canonical list).
   - **Phase 4** the **Rule-0 table card** (`/deck/<stem>/table-card`): one
     phone/print screen — bracket, Game Changers, MLD/extra turns/combos, clock,
     game plan, with its source labelled.
   - **Phase 5** the **mulligan trainer** (`/deck/<stem>/mulligan`): real hands,
     your call first, then the sim's verdict; `goldfish.keep_verdict` is now the
     one shared rule. Stats in localStorage.
   - **Phase 6** **pins v2**: EDHREC/Build-Next label a card reserved elsewhere,
     `/pins` manages every reservation with one-tap move, conflict rows name the
     pin. (Found: `load_pins`/`save_pins` bound their path as a default arg, so
     tests wrote the REAL pins.csv — fixed.)
   - **Phase 7** **Mana-tab explainers** shipped as data from `manabase.analyze`,
     with the honesty caveats moved beside the numbers they qualify.
   - **Phase 9** the **cut surface** ("If You Must Cut"), ranked by the
     optimizer's own `deck_fit.card_value`; protected cards shown flagged, never
     hidden; writes nothing.
   - **Phase 10** **phantom disruption** (`--disruption standard`, EXPERIMENT):
     a wipe, periodic removal and commander tax on a SECOND RNG stream, so the
     A/A-exact-zero tripwire still reads 0.0. Off by default and byte-identical
     when off; CLI/assess only.
   - **Phase 11** gap sweep: Buy-tab rows are panel-clickable, shift-click a
     replacement candidate to simulate the swap first, `carddb --audit-flags`
     closes the standing flag-audit item, and **sw.js's cache version is derived
     from git HEAD** instead of hand-pinned.
   The 4-player pod simulator is specced and BACKLOGGED in
   `docs/spec-pod-simulation.md` (three tiers costed; Forge-on-a-runner is the
   cheap experiment if it is ever promoted).

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
