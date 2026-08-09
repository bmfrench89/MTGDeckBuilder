# MTG Commander Deckbuilding — Session Handoff

**Purpose:** This file lets a new Claude session continue building/tuning these Commander decks *without repeating the mistakes made along the way*. Read the "Rules for staying grounded" section first — it is the most important part.

**Player context:** Building EDH decks primarily from an existing collection (minimal buying unless asked). The player values honesty about limitations over confident guessing.

> **NOTE (2026-07-21):** The sections immediately below (original grounding rules, deck
> summaries, "file inventory") are the ORIGINAL pre-repo handoff, kept for history. This
> project is now a full **GitHub repo + Claude skill + local web app**. Read the
> **"🧭 START HERE — CURRENT STATE"** section next for the accurate, up-to-date picture.
> The grounding rules are now canonical in `.claude/skills/mtg-deckbuilder/references/`.

---

## 🚀 START HERE — THE APP IS HOSTED NOW (updated 2026-08-09, through PR #69)

> **This block supersedes everything below it, including the 2026-07-24 block.** The single
> biggest change: **the app no longer runs on the player's PC.** It is hosted, and the phone
> and PC both use the same URL and the same data.

**Live at:** <https://bmfrench89.pythonanywhere.com> — installed as a PWA on the player's
phone (home-screen icon, full-screen). `webapp/run.sh` / `run.bat` still work for offline
local dev, but are no longer how the player reaches the app day to day.

### Server facts (verified live, 2026-08-09)
- **Host:** PythonAnywhere **free tier**, account `bmfrench89`. Chosen because it is the one
  free host with a **persistent** filesystem — Render's free tier was verified (primary source)
  to wipe all filesystem writes on every redeploy/restart/spin-down, which would destroy this
  app's read-write flat-file data model.
- **Repo:** `~/MTGDeckBuilder`, tracking **`main`** (not a feature branch).
- **Python 3.13**, virtualenv **`mtg`** (`/home/bmfrench89/.virtualenvs/mtg`). Only Flask
  installed, plus pytest. Suite runs clean on the server.
- **WSGI:** `/var/www/bmfrench89_pythonanywhere_com_wsgi.py` is three lines that put
  `~/MTGDeckBuilder/webapp` on `sys.path` and import `application` from `webapp/pa_wsgi.py`.
- **⚠ "Static files" on the Web tab is deliberately EMPTY — do not fill it in.**
  `/static/tokens.css` is a Flask *route* serving `scripts/assets/tokens.css`; a directory
  mapping would shadow it and silently 404 the shared design scales on every page.
  `tests/test_deploy.py` guards this.
- **Verified working:** `/health` 200 · deck dashboards render · **card images load** (browser
  hotlinks to Scryfall's CDN, unaffected by any server-side network limits) · **a deck edit
  survived a full app reload** (the persistence property that disqualified Render).
- **Keepalive:** free web apps need "Run until 3 months from today" clicked every ~3 months.
  Missing it sleeps the app; **no data is lost**.

### ⚠ THE SERVER IS NOW SOURCE OF TRUTH FOR `data/decks/`
Deck files are git-tracked but are rewritten **on the server** by the card panel, the deck
editor and the optimizer. The server clone therefore drifts from GitHub, and a `git pull` for
a code update will eventually conflict. `sync_server.sh` (repo root) resolves this: it commits
only the runtime-edited paths, rebases, and pushes.

### 🔧 PENDING — pick this up first next session
1. **GitHub push credentials are NOT set up yet** — and they are now the key to FULL
   automation: once the PAT is in place, ONE PythonAnywhere daily Scheduled Task
   (free tier includes exactly one) running `~/MTGDeckBuilder/sync_server.sh` gives a
   complete daily cycle — deck edits push up, code + field snapshots pull down, and
   the script now ends by touching the WSGI file, which IS PythonAnywhere's reload
   trigger. Set it at Tasks tab → new daily task → command:
   `~/MTGDeckBuilder/sync_server.sh`. (The PAT itself only grants push; pulling was
   never blocked — the Scheduled Task is what automates the pull+reload.)
   Steps 2–4 below were deferred by the player:
   - Create a **fine-grained PAT** on GitHub: resource owner `bmfrench89`, *only* the
     `MTGDeckBuilder` repo, permission **Contents: Read and write**.
   - On the server: `cd ~/MTGDeckBuilder && git remote set-url origin
     https://bmfrench89:<TOKEN>@github.com/bmfrench89/MTGDeckBuilder.git`
   - Run `~/MTGDeckBuilder/sync_server.sh`.
   - **Never ask the player to paste the token into chat, and warn them off screenshotting the
     console once it is in the remote URL** — `git remote -v` and some git errors print it in full.
   - Git identity IS already configured on the server (`bmfrench89@gmail.com` / "Brendan French").
2. **One deck edit currently exists only on the server:** **Mystic Remora was removed from
   `cosmic-spider-man`.** It is not in git yet. The first `sync_server.sh` run will push it.
   Do not "restore" it locally thinking it was lost.
3. **Collection upload status unconfirmed.** As of the last `/health` check the server was still
   serving the name-only `collection_snapshot.txt` (6 decks found). If the player has not yet
   uploaded the full CSV via `/collection`, the rich color/type/tribe/curve analysis is not
   available server-side. Uploading rebinds the `COLLECTION` global in-process — no reload needed.
4. **✅ SHIPPED 2026-08-09 — deck subtabs + add-card advisor.** Both player-requested
   features are implemented, tested (**suite 127 → 153**) and on `main`; the specs
   (`docs/spec-deck-subtabs.md`, `docs/spec-add-card-advisor.md`) carry a "deviations
   and why" block each. **The hosted server needs a `git pull` + Web-tab Reload to
   pick them up.** Prior-art survey behind the design: `docs/research-prior-art.md`.
   Things a next session should know rather than rediscover:
   - The deck page is now **six CSS-only tabs**; inactive panels are hidden, never
     removed, because both card-panel hook systems bind across the whole page.
   - `＋ Add card` renders **only when `editable=True`** — a CLI dashboard has no
     server to POST to.
   - `.changes.csv` gained a meaningful **`Source`** column: `manual-add` /
     `manual-replace` = the player, anything else = the optimizer. That distinction is
     what the advisor keys off.
   - **The advisor never acts.** `optimize` prints an advisory review of manual adds
     and still never cuts them. Don't "helpfully" wire it into the swap logic.
   - A post-ship review pass fixed 8 findings (crash on missing reference data,
     split-card and snow-basic singleton bugs, a dead reason branch, N× redundant
     loads in the advisor loop, synthetic 'Cards' in the section picker, duplicated
     section parsing, HTML-500 from a JSON route) — each with a regression test.
   - **Review round 2 (full-file) fixed 11 more** — see
     `docs/spec-optimizer-hardening.md` for the list. Highlights a next session must
     not undo: the optimizer's adds and cuts now share ONE `value_of()` (sort AND
     margin gate — the ≥25 margin is value-vs-value); `singleton_violations`
     aggregates by front-face key; `_tidy` preserves in-section comments and parses
     `1x Name` lines; manabase pass 2 emits 3-tuples. Canonical helpers:
     `mtglib.name_keys()` (every membership test), `mtglib.is_basic()`,
     `mtglib._QTY_RE` (every qty-line parse), `deckcore.section_label()`.
     **⚠ Still owed, live:** the top-25 overlap check on real EDHREC data after the
     ranking change — preview→apply→re-run `optimize --all` from the PC or server;
     one `git revert` if a deck drops below ~50% overlap.
5. **ANSWERED empirically (2026-08-09): server-side network reality.** The live deck page
   showed "No EDHREC field data was reachable" — PythonAnywhere free accounts reach only
   sites with official public API docs, which `json.edhrec.com` is not and never will be.
   **Fix shipped: committed field snapshots** — `data/reference/field/<slug>.json`, written
   by `python3 scripts/edhrec.py --snapshot-all --collection <csv>` on the PC, read as the
   fallback by `edhrec.inclusion_map/synergy_map/field_names`. See codemap's "deployment
   reality" table. **AUTOMATED (same day):** the field-snapshot GitHub Action
   (`.github/workflows/field-snapshots.yml`, spec: `docs/spec-field-snapshot-action.md`)
   refreshes snapshots weekly + on new decks + on a manual phone-friendly button and
   commits them to `main` — the PC is out of the loop. Check the Action's FIRST run:
   if red, EDHREC is blocking GitHub runner IPs and the PC fallback below applies.
   (a) *(fallback only)* run `--snapshot-all` on the PC, commit
   `data/reference/field/`, push, pull on the server → field data lights up everywhere;
   (b) upload the collection CSV via `/collection` — the screenshot's "avg MV unavailable
   (add attrs)" means the server is still on the name-only snapshot; `api.scryfall.com` IS
   allowlisted (documented public API), so upload-time enrichment should work server-side.
   Also shipped same day: `deckcore.buy_signals()` — the Buy tab now merges curated buylist
   + unowned one-away combo pieces + BUY-badged decklist cards with provenance (the
   "Exquisite Blood was in Combo Watch but not in Buy" bug).

### What shipped in PR #69
`webapp/pa_wsgi.py` (self-locating WSGI entry — no hardcoded home directory, so the checkout
needs no per-user edit) · `tests/test_deploy.py` (5 tests: the entry point boots and serves
`/health` with **no env vars set**, and the `/static/` mapping trap fails loudly) ·
`sync_server.sh` · `docs/plan-pythonanywhere-deploy.md` (the full runbook, with every
PythonAnywhere platform detail flagged as unverified-until-confirmed) · `CLAUDE.md`.
Suite: **127 tests** (122 + 5 new).

---

## 🧭 PREVIOUS STATE (updated 2026-07-24, through PR #39) — superseded by the block above

> **2026-07-24 — the fast-moving facts (authoritative; the subsections below this block are
> older and partly superseded — kept as history):**
> - **6 decks now** (was 4). Power ranking: Captain America, Team Leader **B3/71** · The Ur-Dragon
>   **B3/68** · Y'shtola **B3/68** · Cosmic Spider-Man **B3/57** · Cloud **B2/56** · Kaervek **B2/56**.
>   (The Ur-Dragon is 5-color goodstuff under a dragon commander — the collection owns few dragons.)
> - **Collection is enriched** — `data/collection/collection.csv` (~2,040 cards) + `collection_attrs.csv`,
>   so curves / pips / roles / power color-scores / fit run on real colors/types/MV/ids collection-wide.
> - **Scryfall is reachable on the player's machine** — the old "firewalled" notes applied to the CI
>   sandbox only. `carddb.py` enriches via the **`/cards/collection` API by default** (no 40 MB download;
>   `--download-bulk` is the offline path). The **EDHREC** and **Commander Spellbook** clients work too.
> - **New since PR #14:** hypergeometric manabase/consistency engine; interactive Collection; full
>   auto-built "Build Next" decks + "build any commander" (with Scryfall typeahead); a site-wide card
>   panel with a generated **Strategy** blurb + **alternatives** for every card; **EDHREC staples**
>   (own→add / missing→buy); **Commander Spellbook** combos (present + one-away) in the assess packet +
>   build view; an **in-panel Remove/Replace deck editor**; auto-enrich on collection upload; the
>   coaching skill + assess packet.
> - **Authoritative current map:** [`docs/codemap.md`](codemap.md) + feature tracker
>   [`docs/spec-interactive-analytics-ai.md`](spec-interactive-analytics-ai.md). Grounding rules are
>   canonical in `.claude/skills/mtg-deckbuilder/references/`.
> - **Player preference:** re-optimizing decks = **recommend, don't auto-rewrite** the curated
>   `data/decks/*.txt`; the player applies swaps via the in-panel editor.

### What this project is now
A complete, grounded MTG Commander (EDH) deckbuilding system in this repo
(`bmfrench89/MTGDeckBuilder`). It has three layers, all sharing one code path:
1. **A Claude skill** — `.claude/skills/mtg-deckbuilder/` (40-yr-veteran/World-Champion
   persona + grounding rules + EDH principles + bracket rubric). Triggers on deckbuilding asks.
2. **A stdlib-only Python toolkit** — `scripts/` (parsing, analysis, dashboards, rankings).
3. **A local Flask web app** — `webapp/` (front end over the scripts; phone-ready, PWA).

### Git state
Everything is merged to **`main`** (HEAD `3061573`; PRs #1–#14 merged). Active dev branch:
**`claude/mtg-commander-deck-builder-ncuswp`** (kept synced to `main` after each merge via
`git reset --hard origin/main` + force-with-lease). Workflow used all session: commit → push to
that branch → open PR → **squash-merge** to `main` → re-sync the branch. Keep doing that.
NOTE: squash-merging means the branch's pre-merge commits differ from `main`'s squashed commit —
always re-sync the branch to `origin/main` before starting new work, or the next PR conflicts.

### Repo map (the important bits)
- `scripts/` — `mtglib.py` (shared parsing/pip-math/heuristics + `load_collection`),
  `analyze_collection.py`, `deck_stats.py`, `power.py` (bracket 1–5 + 0–100 score),
  `combo_detector.py` (infinite / 2-card combo detection → feeds the bracket + a dashboard panel),
  `deck_conflicts.py` (shared cards / buy-doubles / available pool),
  `wishlist.py`, `staples_crossref.py`, `similar_commanders.py` ("would also work"),
  `commander_finder.py` ("build next"), `carddb.py` (collection enrichment via the Scryfall
  `/cards/collection` API), `edhrec.py` (community staples vs your collection), `spellbook.py`
  (Commander Spellbook combos), `deckcore.py` (analysis hub), `auto_build.py` (full 99),
  `manabase.py` (hypergeometric), `card_api.py`, `deck_fit.py`,
  `build_dashboard.py` (`generate()` is the shared renderer), `refresh.py` (rebuild everything),
  `card_image.py`.
- `data/decks/` — **6 decks** as `<stem>.txt` with `# Title/# Theme/# Archetype/# Colors/# Commander`
  headers, plus optional companions `<stem>.notes.md` / `.buylist.csv` / `.attrs.csv`.
- `data/collection/` — `collection_snapshot.txt` (committed, name-only, **2,040 cards**),
  `owned_additions.txt` (committed; player-confirmed cards the export missed — currently Vito +
  Force of Will), and `collection.csv` + `collection_attrs.csv` (BOTH gitignored; you provide
  the CSV, carddb generates the attrs — **now including subtypes**, which is what makes tribal
  detection work).
- `data/reference/` — `game_changers.txt` (verified 53-card list) + tutors/fast-mana/extra-turns/
  mass-land-denial/combo-pieces; `combos.csv` (curated 2–3 card combo *definitions* — pieces,
  result, color identity, early/Bracket-4 flag); `card_notes.csv` (curated "why it works" +
  alternatives behind the click-a-card panel); `commanders.csv` (curated commander DB) +
  `archetype_support.csv`.
- `data/wishlist.md` (generated). `docs/power-and-brackets.md` (rubric). `build/` (gitignored).
- `webapp/` — `app.py`, `templates/`, `static/` (manifest+icon), `run.sh`, README.

### The 6 decks (all 100 cards, built from owned cards; power ranking as of 2026-07-24)
1. **The Ur-Dragon** — 5c dragons — auto-built, rebuilt as real tribal (10 dragons) — **B3, 73**.
2. **Y'shtola, Night's Blessed** — Esper WUB control/drain — CURATED — **B3, 72**.
   (3 Game Changers: Mystical Tutor, Force of Will, Rhystic Study — at the B3 ceiling.)
3. **Captain America, Team Leader** — Jeskai WUR **Hero tribal** — auto-built — **B3, 70**.
4. **Cosmic Spider-Man** — 5c Spider typal — CURATED, has `attrs.csv` + `notes.md` — **B3, 62**.
5. **Cloud, Ex-SOLDIER** — Naya RGW equipment/Voltron — CURATED — **B2, 63**.
6. **Kaervek the Merciless** — Rakdos B/R group-slug — CURATED — **B2, 60**.

**Deck tiers matter for shared cards:** the four CURATED decks outrank the two AUTO-BUILT
drafts (Ur-Dragon, Captain America) when a single copy is contested — the draft yields.

### How to run
- Analyze/rank: `python3 scripts/power.py --rank --collection data/collection/collection.csv`
- Rebuild all dashboards + wishlist: `python3 scripts/refresh.py --collection data/collection/collection.csv`
- Web app: `python3 webapp/app.py` → localhost:5000 (or `webapp/run.sh` to reach it from a phone).
- **Load the collection:** the tools want `data/collection/collection.csv` (the player's pricing
  export — has quantity/name/set/prices but NO colors/types/MV). It's gitignored; ask the player
  to drop it in. `load_collection` auto-merges `owned_additions.txt` and (if present)
  `collection_attrs.csv`.

### Card-detail panel & fit engine (PRs #8–#14, this session)
Big additions since the base repo (all merged). New/changed code lives in `build_dashboard.py`,
`deck_fit.py`, `export_manapool.py`, `carddb.py`, plus data files:
- **Click-a-card bottom sheet** (`build_dashboard.py` → `card_modal_css` / `card_modal_block`).
  Click any card in a dashboard → a bottom sheet slides up with: enlarged image; **live Scryfall
  data fetched in the browser** (type line, mana cost, oracle text, keywords, MV, color identity,
  EDHREC rank, ~price — degrades gracefully offline); a **deck-fit score** (see below); a curated
  "why it's good"; and **alternatives / stronger options** tagged owned/buy + `upgrade`.
- **Deck-fit score** (`deck_fit.py`, `assess_card`) — 0–100 heuristic + band (Core/Strong/Solid/
  Filler/Off-plan) from countable signals: color-identity vs commander, role-need vs the deck's
  ramp/removal/draw/counter ratios, curve, staple/Game-Changer status, tribal/theme. Uses the
  deck's own `# --- Section ---` headers as a role hint on name-only lists. Sets `nameonly` so the
  UI shows an honest "limited data" banner. It's a GUIDE — labeled as such, never invented facts.
- **Curated data files:** `data/reference/card_notes.csv` (Name,Why,Alternatives — the "why it's
  good" + hand-picked alternatives; ~20 staples seeded) and `data/reference/role_staples.csv`
  (role→staples w/ required colors — the fallback alternative pool when a card has no note).
- **ManaPool export** (`export_manapool.py`) — plain `<qty> <name>` text for ManaPool's importer;
  `--deck` (full 100) or `--wishlist` (buy list). Web routes `/export/wishlist.txt` +
  `/export/deck/<stem>.txt`; Copy/Download buttons on Wishlist; per-deck link on the decks list;
  `refresh.py` also writes static `data/manapool-wishlist.txt`.
- **Image throttle** — dashboards load card images via a throttled `data-src` queue (Scryfall
  /named is ~10 req/s) so the tail no longer 429s; enriched decks use the non-rate-limited CDN.
- **Windows:** `update.bat` now offers to relaunch the app; new **`enrich.bat`** (below).

### The key data limitation & its fix  (fix now one-click — DONE this session)
The pricing export is effectively **name-only** (no colors/types/MV), so curves/pips/tribal/
color-compat/fit-score are limited unless the collection is enriched (only Cosmic has a per-deck
`attrs.csv`). **The fix is `carddb.py`, now auto-download:**
`python3 scripts/carddb.py --collection data/collection/collection.csv` (no `--bulk` needed — it
downloads Scryfall "Oracle Cards" itself, ~40 MB, cached & gitignored). Or double-click
**`enrich.bat`** (download → enrich → rebuild). Writes `collection_attrs.csv` (gitignored) which
`load_collection` overlays (colors/types/MV **and** `scryfall_id`) → every tool works
collection-wide. The **Collection page shows a "Card DB: enriched / not" banner** with coverage %.
Scryfall is FIREWALLED in the build env, so the download only runs on the player's machine — the
enrich→overlay chain is verified here against a fixture, but the player must run it for real once.

### Environment constraints (current)
- **Scryfall is reachable** from the player's machine (enrichment, EDHREC + Commander Spellbook
  clients all work server-side). In a locked-down CI sandbox they may be proxy-blocked — fall back
  to `carddb.py --download-bulk`. Card **images** always load client-side in the browser.
- Card images render only in a real browser; they stay blank in the chat preview / claude.ai panel.
- "Prices" are the player's export MARKET values (some obscure rows are mispriced). No live pricing.
- The in-app browser blocks programmatic `localhost` navigation, so web UAT is server-side
  (fetch the rendered HTML + check markers) rather than visual.

### Open threads / next steps (where we stopped)
**THE live issue — shared cards (2026-07-24).** With 6 decks on a mostly single-copy collection,
**50 card-copies are committed beyond what's owned**, so all six can't be sleeved at once. Split:
- **36 cheap copies (~$29 total, all <$3)** — just buy them; that clears ~72% of the conflicts.
- **14 pricier contested cards (~$148)** — deserve a per-card decision. Headliner: **Rhystic Study
  (~$72, own 2, wanted by 3 decks)**. See "deck tiers" above: the auto-built drafts should yield.
- Careful: a mechanical "highest fit keeps it" pass proposes cutting **Exsanguinate / Sun Titan /
  High Market / Toxic Deluge out of Y'shtola** — those are that deck's engine. The fit score does
  not know deck identity. Always sanity-check separation proposals against the deck's game plan.

**Also open:**
- **Dragons in the wrong decks:** Hellkite Tyrant (own 1) sits in BOTH Cloud and Kaervek;
  Two-Headed Dragon + Guardian Scalelord are in non-dragon decks while The Ur-Dragon wants them.
- Grow `data/reference/card_notes.csv` (51 entries) — the panel now generates a fallback blurb for
  every card, so this is polish rather than a gap.

**Backlog:**
- Grow `commanders.csv` / `archetype_support.csv` (more owned legends → richer Build-Next/similar).
- EDHREC "Lift"/inclusion chip on the Collection grid (the EDHREC client exists — `scripts/edhrec.py`).
- R3 (optional): split `build_dashboard.py` (~1,400 lines) renderers. It's cohesive, just big.
- Always-on deploy (gunicorn + auth + HTTPS + PNG icon) so the phone app doesn't need the PC on.

**Session log:** PRs #8 (image throttle), #9 (click panel), #10 (ManaPool export), #11 (update.bat
relaunch), #12 (deck-fit score + alternatives), #13 (bottom sheet + live Scryfall + clearer roles),
#14 (carddb auto-download + status banner). All squash-merged to `main`.

---

## ⚠️ RULES FOR STAYING GROUNDED (read first)

These come from real errors made this project. Follow them.

1. **The collection CSV is the source of truth — ask the player to re-upload it.** A new session will NOT have the file. Request the Archidekt collection export (a CSV). It has columns: `Quantity, Name, Mana Value, Colors, Identities, Mana cost, Types, Sub-types, Super-types, Rarity, Scryfall ID`. Everything should be verified against it.

2. **COUNT the pool; never spot-check staples.** The biggest errors came from assuming a card was owned or that an archetype had support because a few key pieces existed. Example failures: recommended **Ur-Dragon** (player owns only **10 dragons**), recommended **Squirrel Girl** (player owns **2 squirrels**), listed six "staple" creatures for Cloud that the player **didn't own**. Always filter the CSV and count actual cards before claiming support exists.

3. **Verify card text for anything past the Jan 2025 knowledge cutoff.** Post-cutoff sets in this collection: **Marvel Super Heroes, Marvel's Spider-Man, Secrets of Strixhaven, Lorwyn Eclipsed, Final Fantasy (+ Commander), Avatar: The Last Airbender.** Web-search the oracle text (Scryfall/Gatherer) — do NOT trust memory. Real errors: assumed the wrong half of an MDFC, mis-stated mana values, mis-read abilities.

4. **Rules facts that were gotten wrong and corrected:**
   - **X spells count X on the stack.** Exsanguinate / Profane Command cast for X≥1 have mana value 3+, so they DO trigger "MV3+" abilities. (Outside the stack, X=0.)
   - **"Cast" triggers resolve even if the spell is countered.** (Y'shtola's damage/lifegain still happens.)
   - **Exile-based wipes anti-synergize with graveyard payoffs.** Final Judgment/Extinction Event exile creatures, starving reanimator/graveyard-cast effects. Prefer destroy-based wipes when the deck has graveyard synergy.
   - **Flashback/MDFC mana value:** flashback doesn't change MV; an MDFC's back-face spell has its own MV.

5. **Do the math on the manabase against actual pip demand.** Count colored pips across the nonland cards; count double-pip cards; cut lands that make zero colored mana (creature-type "any color" lands are traps if the player runs ~1 of that type).

6. **Photos from the player are higher-signal than any search.** Several fixes came from the player photographing cards. Trust them.

7. **Be honest about tool limits (below) rather than fabricate.** If you can't verify a price or a card, say so.

---

## TOOLING CONSTRAINTS (known blockers)

- **Scryfall API and bulk-data downloads are BLOCKED** in the code sandbox (network firewall) and via `web_fetch` (bot detection). You cannot script bulk card lookups.
- **`web_fetch` only accepts URLs that already appeared in a prior search/fetch result.** URLs built from memory are rejected.
- **What works:** (a) the collection CSV, which has MV / color identity / types / **Scryfall ID** per card; (b) `web_search` one card at a time for oracle text; (c) Scryfall *image* hotlinking works: `https://cards.scryfall.io/normal/front/<id[0]>/<id[1]>/<id>.jpg` using the Scryfall ID from the CSV.
- **Card-art HTML won't render in the chat's preview pane** (external images blocked). It only displays in a real browser (Chrome/Safari). Always warn the player.
- **Price sites (TCGplayer/Card Kingdom/MTGGoldfish) are login-walled.** Give clearly-labeled *estimate ranges*, not fake live quotes.

---

## DECK 1 — Y'shtola, Night's Blessed (Esper WUB control/drain) — COMPLETE

**Current file:** `yshtola-deck-v19-FINAL.html` (dashboard). Also `yshtola-synergy-chart.html`.

**Commander (verified oracle text):** {1}{W}{U}{B}, 2/4 Cat Warlock, Vigilance.
- "At the beginning of each end step, if a player lost 4 or more life this turn, you draw a card."
- "Whenever you cast a noncreature spell with mana value 3 or greater, Y'shtola deals 2 damage to each opponent and you gain 2 life."
- **Ruling:** the cast trigger resolves even if the spell is countered.

**The engine:** cast MV3+ noncreature → 2 dmg each opp + gain 2 → "amplifiers" convert lifegain into damage → any player losing 4+ triggers card draw. ~53% of nonland cards trigger the commander.

**Key amplifiers (lifegain → damage):** Vito Thorn of the Dusk Rose, Defiling Daemogoth (mono-black, end-step drain = life gained), Witch of the Moors (repeating edict on lifegain), The Kingpin of Crime (Extort), Blood Artist, Bastion of Remembrance, True Conviction.
**Free spells (0-mana triggers on others' turns):** Force of Will, Misdirection, Snuff Out, Reverent Mantra (exile a white card instead of paying).
**Graveyard payoffs (want DESTROY wipes, not exile):** Sepulchral Primordial, Diluvian Primordial (casts opponents' instants/sorceries → re-triggers Y'shtola), Sun Titan + Serra Paragon + Sevinne's Reclamation (rebuy ~61% of the deck, all MV≤3 permanents + lands).
**Finisher:** Exsanguinate (each opp loses X, you gain the TOTAL across the table — Vito/Daemogoth convert it).

**Nonland (62):** Blood Artist, Baleful Strix, Murderous Rider, The Kingpin of Crime, Archmage Emeritus, Emet-Selch of the Third Seat, Fandaniel, Telophoroi Ascian, Vito, Thorn of the Dusk Rose, Solemn Simulacrum, Defiling Daemogoth, Serra Paragon, Witch of the Moors, Archfiend of Depravity, Sun Titan, Diluvian Primordial, Sepulchral Primordial, Torrential Gearhulk, Mystical Tutor, Swords to Plowshares, Counterspell, Infernal Grasp, Absorb, Sphinx's Revelation, Void Rend, Soul Shatter, Snuff Out, Lethal Scheme, Reverent Mantra, Force of Will, Misdirection, Sublime Epiphany, Dig Through Time, Exsanguinate, Profane Command, Syphon Soul, Toxic Deluge, Vindicate, Sevinne's Reclamation, Ambition's Cost, Extinction Event, Rite of Replication, Time Wipe, Rhystic Syphon, Cleansing Nova, Construct a Cosmic Cube, Authority of the Consuls, Staggering Insight, Rhystic Study, Bastion of Remembrance, Propaganda, The Death of Gwen Stacy, True Conviction, Sol Ring, Commander's Sphere, Arcane Signet, Talisman of Dominance, Talisman of Hierarchy, Fellwar Stone, Thought Vessel, Lightning Greaves, Archaeomancer's Map, Relic of Legends

**Lands (37):** Command Tower, Path of Ancestry, Exotic Orchard, Arcane Sanctum, Plaza of Heroes, Spire of Industry, Choked Estuary, Darkwater Catacombs, Drowned Catacomb, Glacial Fortress, Isolated Chapel, Underground River, Port Town, Sunken Hollow, Prairie Stream, Skycloud Expanse, Fetid Heath, Sunken Ruins, Desolate Mire, Shineshadow Snarl, Contaminated Aquifer, Sunlit Marsh, Idyllic Beachfront, Fabled Passage, Terramorphic Expanse, Ash Barrens, Bojuka Bog, Irrigated Farmland, High Market, Island x3, Swamp x3, Plains x2

**Manabase note:** pip demand ≈ B43 / U33 / W24; ~26 double-pip cards; sources W22 / U25 / B25. High Market added as a sac outlet (feeds Blood Artist / saves Y'shtola from exile). Emeria the Sky Ruin was rejected (needs 7 Plains; deck has 5 Plains-typed).

---

## DECK 2 — Cloud, Ex-SOLDIER (Naya RGW equipment) — COMPLETE

**Current file:** `cloud-deck.html` (dashboard), `cloud-deck-visual.html` (card images), `cloud-synergy-chart.html`, `cloud-buy-list.html`.

**Commander (verified oracle text):** {2}{R}{G}{W}, 4/4 Human Soldier Mercenary, Haste.
- "When Cloud enters, attach up to one target Equipment you control to it."
- "Whenever Cloud attacks, draw a card for each equipped attacking creature you control. Then if Cloud has power 7 or greater, create two Treasures."

**The engine:** arm the board → swing → draw a card per equipped attacker → reload off Treasure. Puresteel Paladin (metalcraft = free equip) is the multiplier. Colossus Hammer + free-equip + evasion = one-shot commander kill.

**Known weakness (already flagged to player):** thin on dedicated equip-carriers (owns only Puresteel Paladin + Armory Automaton) and card draw (3 engines). Leans on Cloud himself. Buy list addresses this.

**Equipment (14):** Colossus Hammer, Hard-Won Jitte, Sword of the Animist, Behemoth Sledge, Conqueror's Flail, Champion's Helm, Darksteel Plate, Mask of Memory, Lightning Greaves, Trailblazer's Boots, Mjölnir, Hammer of Thor, Hero's Blade, Bitterthorn, Nissa's Animus, Hero's Heirloom

**Equipment support (4):** Puresteel Paladin, Armory Automaton, Inspiring Statuary, Steelshaper's Gift

**Creatures (21):** Llanowar Elves, Elvish Mystic, Gilded Goose, Sakura-Tribe Elder, Priest of Titania, Selfless Spirit, Skyclave Apparition, Solemn Simulacrum, Sun Titan, Emeria Angel, Tectonic Giant, Combustible Gearhulk, Bronze Guardian, Karmic Guide, Ohran Frostfang, Thor, Asgard's Avenger, Hercules, Olympian Hero, Tendershoot Dryad, Hellkite Tyrant, Storm, Windrider, Guardian Scalelord

**Ramp (9):** Sol Ring, Arcane Signet, Commander's Sphere, Fellwar Stone, Cultivate, Farseek, Rampant Growth, Nature's Lore, Relic of Legends

**Removal & wraths (10):** Swords to Plowshares, Path to Exile, Generous Gift, Beast Within, Chaos Warp, Blasphemous Act, Vandalblast, Cleansing Nova, Austere Command, Vanquish the Horde

**Card draw (3):** Skullclamp, Tome of Legends, Staff of the Storyteller

**Anthems & finish (2):** Rancor, True Conviction

**Lands (36):** Command Tower, Path of Ancestry, Exotic Orchard, Sacred Peaks, Jungle Shrine, Rugged Prairie, Battlefield Forge, Clifftop Retreat, Sunpetal Grove, Rootbound Crag, Game Trail, Fortified Village, Furycalm Snarl, Frostboil Snarl, Sungrass Prairie, Canopy Vista, Cinder Glade, Prairie Stream, Fabled Passage, Terramorphic Expanse, Evolving Wilds, Ash Barrens, Myriad Landscape, Radiant Grove, Wooded Ridgeline, Forest x6, Mountain x2, Plains x3

**IMPORTANT — deck separation:** Player wanted Cloud built WITHOUT taking single copies from the Y'shtola deck. The ~11 shared staples (Sol Ring, Swords to Plowshares, Arcane Signet, Sun Titan, Solemn Simulacrum, Lightning Greaves, Commander's Sphere, Fellwar Stone, Relic of Legends, Cleansing Nova, True Conviction) are covered by the player's **2nd copies** (they own multiples of all precon commons/staples). Confirmed OK.

**Buy list (in `cloud-buy-list.html`):** tiers of upgrades, cap of $50/card. Headliners: Buster Sword (Cloud's card, +3/+2 + draw + free spell on hit), Sword of Fire and Ice, Sword of Feast and Famine, Sram Senior Edificer, Sigarda's Aid. Prices are early-2026 ESTIMATES.

---

## FILE INVENTORY (in /mnt/user-data/outputs, but a new session starts empty)

A new session will NOT have these files. The player has them saved. If they want edits, they may need to re-share a file or you rebuild from the lists in THIS document.

- Y'shtola: `yshtola-deck-v19-FINAL.html` (current), `yshtola-synergy-chart.html`, plus superseded v2–v18 + buy list.
- Cloud: `cloud-deck.html`, `cloud-deck-visual.html`, `cloud-synergy-chart.html`, `cloud-buy-list.html`.

**Visual style used:** Y'shtola = dark FFXIV Esper aesthetic (void #0B0E1A, aether cyan #5BE0D4, blood #C2415C, gold #D9B26A; fonts Cormorant Garamond / Barlow Condensed / IBM Plex Mono). Cloud = "Mako" Naya aesthetic (steel #0E1214, mako green #39E0B0, fire #E86A3A, gold #E8B84B; fonts Oswald / Rajdhani / JetBrains Mono). Dashboards are self-contained single HTML files, no external images except the explicit "visual deck" files.

---

## OTHER DECKS THE COLLECTION SUPPORTS (verified by counting)

Ranked by actual support depth, not vibes:
1. **Cloud / Tifa — Naya equipment** (32 equipment owned) — DONE (Cloud).
2. **Kaervek the Merciless — Rakdos punisher** (336 BR creatures; owns Dictate of the Twin Gods, Fiery Emancipation, Spiteful Visions, Theater of Horrors).
3. **Isperia — Azorius fliers/control** (deep, but only ~5 counterspells owned — counter-light).
4. **Yahenni — mono-black aristocrats** (owns Blood Artist/Zulaport/Bastion but only ~5 sac outlets + 3 drain payoffs — engine needs topping up).
- **NOT well supported without buying:** anything mono-green or Squirrel Girl (green depth is old commons; ~2 squirrels; 2 token doublers; almost no finishers). Ur-Dragon (only 10 dragons).

---

## SUGGESTED NEXT STEPS / OPEN ITEMS

- If continuing Cloud: apply the buy-list swaps once cards are acquired; regenerate dashboard + chart as v2.
- If starting a new deck: **first re-request the collection CSV, then COUNT the relevant pool before recommending anything.**
- One unresolved card from the Y'shtola audit: **Mysterio's Mirage** text was never verified (search failed). Excluded rather than guessed. Revisit only if the player asks.

---

## SESSION NOTE — 2026-07-18 (program build + Kaervek v1)

**What changed:** This repo now IS the end-to-end program (skill + scripts + data),
not just notes. See README.md and `.claude/skills/mtg-deckbuilder/`.

**Collection:** Imported from the Google Drive doc `collection_list` →
`data/collection/collection_snapshot.txt` (1,805 unique cards, name-only). The full
Archidekt CSV is still the goal — drop it at `data/collection/collection.csv` to unlock
color/type/tribe/pip analysis and card images.

**Grounding catches this session (verify on CSV load):**
- The "complete" Y'shtola list references 4 cards NOT in the current collection export:
  **The Kingpin of Crime, Vito Thorn of the Dusk Rose, Force of Will, Extinction Event.**
  Either the export predates them or they're tracked elsewhere.
- Handoff claimed **Fiery Emancipation** owned for Kaervek — NOT in the current export.
- Kaervek oracle re-verified: **{5}{B}{R} 5/4**, "Whenever an opponent casts a spell,
  Kaervek deals damage equal to that spell's mana value to any target." (Earlier memory
  of a cheaper 3/3 was wrong.)

**New deck:** `data/decks/kaervek-punisher.txt` — Kaervek Rakdos punisher **v1 draft**,
100% owned cards, ratios ok (37 land / 10 ramp / 10 removal / 3 wipe / ~9 draw). Plays as
group-slug midrange; buy-list to sharpen into a true punisher lives in
`data/staples/kaervek-the-merciless.txt` (owned 39/68; ~29 missing).
Off-color cards excluded during build: **Vindicate (WB), Crush Contraband (W)**.

**New tool:** `scripts/staples_crossref.py` — diff a curated staples list against the
collection → owned vs. missing (buy-list). NOTE: EDHREC/Scryfall direct fetch is
403-blocked here; staples lists are curated from knowledge + web-search summaries, not
live scrapes. Web *search* works; page *fetch* of those sites does not.

**Next steps:** (1) load the CSV and re-run deck_stats on Kaervek to confirm 0 off-color
and get real curve/pips; (2) acquire ~10 punisher engines from the buy-list; (3) explore
the Spider-Man typal idea (needs per-card oracle verification — all post-2025).

---

## SESSION NOTE — 2026-07-18b (pricing CSV wired in)

Player uploaded a **collection + pricing CSV** (`all_my_cards_2.csv`, 2,763 rows,
one per printing, Excel `sep=,` preamble). Installed at `data/collection/collection.csv`
(gitignored — contains purchase prices).

- **Format:** `Folder Name, Quantity, Card Name, Set Code, Set Name, Card Number,
  Condition, Printing, Price Bought, Date Bought, LOW, MID, MARKET`. Has ownership +
  set + prices; **no color/type/mana-value/Scryfall-ID** columns. So it unlocks value
  and per-deck pricing, NOT color/curve/tribe math. For that, still need the
  card-attribute export (Mana Value/Colors/Types/Scryfall ID).
- **Tools upgraded:** mtglib aggregates printings by name and reads prices;
  `analyze_collection.py --value` gives collection value + top cards;
  `deck_stats.py` prints deck MARKET value.
- **Collection value (MARKET):** ~$2,985.74 across 1,916 unique / 2,607 copies.
  Note: some obscure rows are clearly mispriced (e.g. Vine Trellis ~$30) — treat prices
  as rough. Priciest: Rhystic Study (MB1) ~$72, The Mind Stone (MSH) ~$68, Scorched
  Ruins (WTH) ~$66.
- **Deck values:** Y'shtola ~$307, Kaervek v1 ~$94.
- **Discrepancy update:** vs this fresher export, Y'shtola "missing" dropped 4 -> 2.
  **The Kingpin of Crime** and **Extinction Event** now show owned; still missing
  **Vito, Thorn of the Dusk Rose** and **Force of Will**.

---

## SESSION NOTE — 2026-07-18c (Cosmic Spider-Man built)

Player picked **Cosmic Spider-Man** (5-color Spider typal) after a collection-wide
"what commanders should I buy" review.

**Key review finding:** for the deepest themes the player ALREADY OWNS the ideal
commander — Cosmic Spider-Man (Spiders, 57 copies owned), Captain America Team Leader +
Director Nick Fury (Hero typal), Doctor Doom (Grixis villains). Best *buys* are cheap
singles that unlock owned pools: **Teysa Karlov** (~$6, aristocrats — 11/11 sac outlets
owned) and **Alesha** (~$3, Mardu reanimator — 22 recursion pieces owned). Precon buy:
**Doom Prevails** for the villain slice.

**New deck:** `data/decks/cosmic-spider-man.txt` — v1 draft, 100% owned, ~$265 deck value,
37 lands. Verified Spider engine (Scryfall/EDHREC): Silk Web Weaver, Spiders-Man Heroic
Horde (web-slinging → Spider tokens), Ezekiel Sims (+2/+2 a Spider each combat), Sun-Spider,
Spider-UK, SP//dr, Madame Web. Owned typal support: Roaming Throne (doubles a type's
triggers), Kindred Discovery, Door of Destinies, Patchwork Banner, Metallic Mimic, plus
Path of Ancestry / Secluded Courtyard / Unclaimed Territory fixing.
**Caveat:** SPM creature type-lines are reasoned/spot-verified, not fully confirmed — load
the card-attribute CSV to confirm every included card is actually a Spider.
**Buy-list (top Spiders not owned):** Gwenom, Remorseless; Superior Spider-Man.

**Tool tweaks:** added a `spider` dashboard theme; broadened the name-only land heuristic
again (monastery/courtyard/territory/plaza/shrine/peaks/orchard/sanctum...). All four saved
decks now report correct land counts.

---

## SESSION NOTE — 2026-07-18d (dashboards evolved)

`build_dashboard.py` upgraded from a flat page to a sectioned tool:
- Stat tiles now include **deck value**.
- **Game Plan / Player Notes** section (from `<deck>.notes.md`, markdown-lite).
- **Mana Curve (MV spread)** driven by an optional `<deck>.attrs.csv`
  (Name,Type,MV,Colors) — so curve works without the full attribute collection CSV;
  cards lacking MV are honestly noted, not hidden.
- **Buy & Replace** panel with interactive **price-threshold toggle buttons**
  (All / <=$5 / <=$10 / <=$20 / <=$50), running total, from `<deck>.buylist.csv`
  (Card,Price,Tier,Replaces,Reason).
- **Decklist grouped by the deck file's own `# --- Section ---` headers.**
All three companion files auto-detect next to `<deck>.txt`. Cosmic Spider-Man has all
three authored (notes + 13-card buylist + 52-card attrs → curve peaks at MV2).
Other decks render fine without companions (those sections just omit).

---

## SESSION NOTE — 2026-07-18e (Cosmic Spider-Man MV curve completed)

Verified all 31 remaining Spider/equipment mana values from Scryfall (one card per web
search; EDHREC/Scryfall/Draftsim page fetches are 403-blocked, but web SEARCH returns the
Scryfall data snippet reliably). Filled `cosmic-spider-man.attrs.csv` to 83/83 cards →
dashboard curve now "covers all 63 nonland cards" (peaks at MV2 with 22).

**Type findings — 3 included cards are NOT Spiders (won't get Cosmic's combat buff):**
- **Madame Web, Clairvoyant** — Mutant Advisor (still great: casts Spiders off the top).
- **Agent Venom** — Symbiote Soldier Hero (death-draw value, but not a Spider).
- **Flash Thompson, Spider-Fan** — Human Citizen (tap/untap utility, not a Spider).
Note **Spider-Suit** makes its equipped creature a Spider Hero, so it can turn a non-Spider
into a buff target. v2 idea: swap the 3 non-Spiders for owned/bought Spiders (Superior
Spider-Man, Gwenom) to raise Cosmic's hit rate.

---

## SESSION NOTE — 2026-07-18f (bracket, power ranking, conflicts, card images)

Four features added (a research workflow verified the bracket rules + Game Changers list):

- **Card images in the decklist** — `build_dashboard.py` "Decklist by Section" now renders
  Scryfall image-by-name thumbnails (browser-only, as always).
- **Cross-deck conflict checker** — `deck_conflicts.py`: sums each card's usage across all
  `data/decks/*.txt` and flags cards committed to more decks than owned copies (basics exempt).
  Surfaced as a "Cross-Deck Conflicts" dashboard section. NOTE: with 4 decks there are ~37 real
  conflicts (e.g. Solemn Simulacrum owned 1, used in 3 decks). **Run this when building new decks.**
- **Bracket + power ranking** — `power.py`: WotC Commander Bracket (1–5) from Game-Changers count
  + guardrails (tutors are NOT a bracket factor post-Oct-2025), plus a 0–100 power score.
  `--rank` ranks all decks. Reference lists in `data/reference/*.txt`; rubric in
  `docs/power-and-brackets.md`. Current ranking: Y'shtola B3/67, Cosmic B3/57, Kaervek B2/55,
  Cloud B2/51. Y'shtola is AT the 3-Game-Changer ceiling (Mystical Tutor, Force of Will,
  Rhystic Study) — a 4th would make it Bracket 4.
- Game Changers list is the verified 53-card set (2026-02-09; added Farewell + Biorhythm).
  Mana Crypt / Jeweled Lotus are banned, not on it.

Note: `data/collection/collection.csv` (pricing export) has no per-card MV, so only Cosmic
(which has a `.attrs.csv`) gets curve-based power components; others renormalize those out.

---

## SESSION NOTE — 2026-07-18g (no-share rule + buy-doubles / available pool)

HARD RULE added (grounding-rules #8): a card may appear in N decks only if the player owns
≥ N copies. Enforced via `deck_conflicts.py`:
- `--buy-doubles`: priced shopping list to buy the extra copies (keeps all decks optimal).
  Current 4 decks: **42 extra copies, ~$81 total** (mostly <$1 staples; priciest Lightning
  Greaves ~$9.16/2, Plaza of Heroes ~$8.80). Force of Will + Vito are unowned (separate buy).
- `--available [--deck X]`: the buildable pool (owned minus committed elsewhere) — use this
  when building a NEW deck so it never reuses a committed single.

Decision left to the player: BUY the ~$81 of doubles (recommended — no deck degraded) vs.
SWAP shared cards out of the two draft decks (Kaervek/Cosmic) for owned bench cards (would
downgrade those drafts; the collection bench is deep but mostly weaker). Deck files NOT edited
yet — awaiting the player's choice.

---

## SESSION NOTE — 2026-07-18h (surface shared cards + wishlist, not block)

Player preferred surfacing over blocking. Reframed rule #8 from "hard block" to "mark & wishlist":
- **Dashboard**: every card shared with another deck gets a `⇄N` badge in the decklist
  (accent = own enough, warn = need more), and the old "Cross-Deck Conflicts" section is now an
  informational **"Shared Across Decks"** panel (✓ covered / ⚠ need copies). Nothing is blocked.
- **`wishlist.py`** → `data/wishlist.md`: consolidated, priced checklist — shared copies to buy
  (~$80.69 / 40 copies), cards not owned (now 0), and buy-list upgrades (~$173, all from Cosmic).
- Vito + Force of Will confirmed owned via `owned_additions.txt` (merged by load_collection).
Skill/grounding updated to "surface, don't deny." Deck files still unedited.

---

## SESSION NOTE — 2026-07-18i (one-command refresh + buy-lists for all decks)

- **`scripts/refresh.py`**: one command regenerates every deck's dashboard (+ visual gallery,
  themed) and the wishlist. Decks are auto-discovered; title/theme/commander read from
  `# Title:` / `# Theme:` / `# Commander:` headers in each deck .txt. New decks are picked up
  automatically. HTML lands in `build/` (gitignored).
  `python3 scripts/refresh.py --collection data/collection/collection.csv`
- **Buy-lists for all four decks** (`<deck>.buylist.csv`): Cosmic 13, Kaervek 10, Y'shtola 8,
  Cloud 7 = 38 upgrade items (~$402). Wishlist upgrade section now spans all four. Cloud pulls
  the handoff's sword package (SoFF, SoFI, Buster Sword, Sram, Sigarda's Aid); Y'shtola gets
  Cyclonic Rift / Esper Sentinel / Smothering Tithe (noting the Game-Changer bracket bump);
  Kaervek gets the punisher engines (Torment of Hailfire, Fiery Emancipation, Sulfuric Vortex…).
- Added a **rakdos** dashboard theme (Kaervek). Themes now: default / yshtola / cloud / rakdos /
  spider.

---

## SESSION NOTE — 2026-07-18j (local web front end)

Built a Flask web app in `webapp/` over the existing scripts (imported, not duplicated).
- `build_dashboard.generate()` extracted so CLI + app render identical dashboards.
- Pages: Decks (power leaderboard), live per-deck dashboard + visual + inline editor,
  Wishlist, Shared, Collection (value/top cards, upload export, add owned_additions).
- Run: `pip install -r webapp/requirements.txt && python3 webapp/app.py` -> localhost:5000.
  Local-only by design (collection/prices stay on the machine). Verified all routes 200 and
  screenshotted with the pre-installed Chromium.
- Fixed a data bug: kaervek/cloud buy-lists used `\,` to escape commas (invalid CSV) which
  mangled card names — rewrote with proper double-quote quoting.
Flask note: this container's Debian blinker blocks a plain `pip install flask`; a venv (as in
webapp/README) avoids it.

---

## SESSION NOTE — 2026-07-18k (phone access)

Made the web app phone-ready:
- `MTG_HOST` env (default 127.0.0.1); set 0.0.0.0 to allow LAN devices. App prints the
  phone URL (LAN IP) on startup.
- `webapp/run.sh`: one-command venv bootstrap + bind 0.0.0.0 + serve.
- PWA: manifest + spider SVG icon + apple-mobile meta + safe-area insets → installable
  "Add to Home Screen", full-screen.
- Rebuilt the Decks leaderboard as responsive cards (the table clipped action links at
  phone width). Verified at 390px with Chromium screenshots.
- webapp/README documents 3 phone paths: same-Wi-Fi LAN (recommended), tunnel
  (cloudflared/ngrok), deploy (gunicorn+auth+HTTPS; keep collection.csv private).

---

## SESSION NOTE — 2026-07-18l ("this commander would also work")

New feature: `scripts/similar_commanders.py` + `data/reference/commanders.csv` (curated
commander DB: colors + archetype tags). For a deck it ranks alternate commanders that share
the archetype and classifies the COLOR fit honestly:
  drop-in (your 99 stay legal) · tighter (trim off-color) · partial (keep overlap+colorless,
  rebuild rest) · reskin (same idea, new shell). Owned candidates are flagged from the
  collection; where a deck has attrs it shows exact "% of cards stay in color".
Decks tagged with `# Archetype:` / `# Colors:` headers. Surfaced as a "Commanders That Also
Fit This Shell" dashboard section (build_dashboard.generate now returns it; visible in the
web app deck pages too).
Flagship: Cloud (Naya equipment) → The Invincible Iron Man (Izzet) = PARTIAL (shares R);
also surfaces owned Iron Man Armored Avenger + Captain America. Grow commanders.csv over time.

---

## SESSION NOTE — 2026-07-18m ("what should I build next?" reverse matcher)

`scripts/commander_finder.py` + `data/reference/archetype_support.csv`: ranks every commander
in commanders.csv by how many of its archetype's SUPPORT cards the collection owns (universal
staples like Sol Ring excluded), with a light color-depth (basics) tiebreak. Flags owned
commanders. Webapp page **/build-next** ("Build Next" nav tab) with archetype filter chips +
support bars. Current top: Breya (41, buy), Judith (39, buy), Syr Gwyn (38, buy), then owned
Y'shtola / Iron Man Armored Avenger / Mazirek (34). Grow the two reference CSVs to sharpen.
Merged similar-commanders as PR #2 → main (aedc375).

---

## SESSION NOTE — 2026-07-18n (card DB enrichment; the "do we need a DB" answer)

Decision: NO database for the app's own data (tiny, read-mostly, files stay source of truth).
DuckDB introduced ONLY as an optional ingestion/analytics layer over a Scryfall card DB —
the real fix for the name-only limitation.

- `scripts/carddb.py`: streams a Scryfall bulk JSON (via DuckDB; stdlib-json fallback), joins
  the collection, writes `data/collection/collection_attrs.csv` (Name,Type,MV,Colors,Cost).
- `mtglib.load_collection` now overlays `collection_attrs.csv` onto the whole collection, so
  every tool gets colors/types/MV/mana-cost collection-wide (curves, pip demand, tribal counts,
  power color-scores, similar-commander color-fit %) with NO per-deck attrs.csv.
- `similar_commanders.find` now derives per-card identities from the collection overlay (falls
  back to deck attrs), so the color-compat % benefits automatically.
- collection_attrs.csv is gitignored (derived + personal). Scryfall bulk is firewalled in this
  env; verified end-to-end with a 32-card sample (Kaervek curve + pip demand + Cloud compat %
  all populated). SQLite noted as the future choice only if we add write-heavy user state.

---

## SESSION NOTE — 2026-07-21 (combo detector + card_notes growth)

**Two deliverables built.**

**1. Curated combo engine.**
- `data/reference/combos.csv` — 22 verified 2- and 3-card combo *definitions*
  (`Name,Pieces,Result,ColorIdentity,Early,Category,Notes`). `Pieces` is
  `;`-separated because card names contain commas (e.g. "Kiki-Jiki, Mirror Breaker");
  every text field is double-quoted (the same CSV-escaping care as the buy-lists).
  The `Early` flag = a cheap two-card infinite, the WotC Bracket-4 red line.
- `scripts/combo_detector.py` — detects **complete** combos in a deck, **one-piece-away**
  combos (tagged owned/buy vs. the collection), and a **collection-wide** "what can I
  assemble" scan. Stdlib-only, `mtglib` helpers, argparse, `--json`. Modes: `--deck`,
  `--all`, `--collection-combos`.
- `scripts/power.py` — real detection now supersedes the old loose "N combo pieces
  present, verify" heuristic: a **complete + Early** combo forces Bracket 4; the
  piece-count note survives only as a fallback when no full combo is assembled. New
  `signals.combos_complete` / `combos_near`.
- `scripts/build_dashboard.py` — a **Combo Watch** section on every dashboard (renders
  via `refresh.py`; threaded through `render_dashboard(..., combos=)`).

**Grounding finding (verified against the deck files + snapshot):** NONE of the four
decks contains a complete infinite combo — a correct, useful result (confirms they're
not accidentally Bracket 4). **Y'shtola is one card — Exquisite Blood — away** from an
infinite-drain win via the Vito it already runs (Exquisite Blood shows *not owned* in the
snapshot). Power ranking unchanged: Y'shtola B3/67, Cosmic B3/57, Kaervek B2/55, Cloud
B2/51. The combo list is CURATED (Scryfall / Commander Spellbook are firewalled here),
so it is a starting point, not exhaustive.

**2. Grew `data/reference/card_notes.csv`** 20 → 51 entries (+31): high-impact
**pre-2025** staples actually in the four decks (Blood Artist, Vito, Exsanguinate, Toxic
Deluge, Colossus Hammer, Puresteel Paladin, Night's Whisper, Terminate, Chaos Warp,
Skullclamp, …), each with a grounded blurb + real alternatives. Deliberately **skipped the
post-2025 Marvel/FF cards** (Spiders, Emet-Selch, Mjölnir…) — oracle text isn't verifiable
offline (grounding rule #3).

**Notes.**
- Added a UTF-8 console guard in `combo_detector.py`: the other scripts were written on
  Linux and crash on Windows `cp1252` when printing `→`/`⚠` (pre-existing; not fixed
  repo-wide this session).
- **Grounding/honesty:** the request cited an "Open threads → Agreed next" section that
  spells out both tasks. No such section exists (the actual heading is "Open threads /
  next steps (where we stopped)", and it lists neither). Built from the direct
  instruction; did not treat the doc as pre-agreeing a spec it doesn't contain.
- README + this handoff's repo map / reference list updated to include the new tool and
  the two reference CSVs.
