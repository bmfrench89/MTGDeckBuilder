# CLAUDE.md

Guidance for Claude Code (and any AI assistant) working in this repository.

## What this project is

A grounded **Magic: The Gathering Commander (EDH) deckbuilder** built around one player's
real collection. Three layers, one shared code path:

1. **A Claude skill** — `.claude/skills/mtg-deckbuilder/` — a 40-year-veteran / World
   Champion persona plus the grounding rules and build/coach workflows. It *runs the CLIs*;
   it never reimplements their logic. (`.claude/skills/mtg-mobile/` covers phone/PWA setup.)
2. **A stdlib-only Python toolkit** — `scripts/` — parsing, analysis, optimization,
   dashboards, rankings. No third-party imports (CI enforces this).
3. **A local Flask web app** — `webapp/` — a front end over the same scripts (imported,
   not duplicated). Runs on localhost so the collection and prices stay on the machine.

## The prime directive: stay grounded

This is the project's whole reason for existing, and the rule set exists because each item
was gotten wrong before. Full text: `.claude/skills/mtg-deckbuilder/references/grounding-rules.md`.

- **The collection is the source of truth.** Never claim a card is owned, or that an
  archetype has support, without checking the collection data.
- **Count the pool; never spot-check staples.** "You own 10 dragons" is an answer;
  "dragons look supported" is how you recommend Ur-Dragon to someone who can't cast it.
- **Verify card text you aren't certain of** — especially post-2025 sets (Marvel,
  Spider-Man, Final Fantasy, Avatar, Lorwyn Eclipsed, newer Strixhaven). One card at a time.
- **Label estimates as estimates.** No live price feed is reachable; prices are estimates.
- **Never invent a card.** Adds/cuts come from the collection, saved decks, curated
  references, `auto_build.py`'s candidate pool, or a verified Scryfall lookup.
- **Reviewing cards against decks follows the sleeper audit** —
  `.claude/skills/mtg-deckbuilder/references/card-review-method.md` (player-ratified
  2026-08-11): field % is a prior, the verified text read against the deck's engine is
  the verdict; every candidate gets swap/wishlist/bench/skip, never a silent drop, and
  manual swaps are logged `Source=manual-replace` so the optimizer never churns them.

## Layout

```
scripts/          The engine — stdlib-only Python 3 (see Architecture below)
  assets/         Dashboard front-end assets, inlined at render time
                  (tokens.css, card_panel.html/.css, card_images.html)
webapp/           Flask app: app.py + templates/ + static/
tests/            pytest — offline, hermetic (everything in tmp_path)
data/
  collection/     collection_snapshot.txt (committed, name-only) · collection.csv +
                  collection_attrs.csv (gitignored, private) · owned_additions.txt · pins.csv
  decks/          <stem>.txt + optional .notes.md / .buylist.csv / .attrs.csv / .changes.csv
                  / .clips.json
  reference/      game_changers, tutors, combos.csv, card_notes.csv, commanders.csv, …
docs/             codemap.md (architecture) · handoff.md (session history) ·
                  spec-interactive-analytics-ai.md (feature tracker) · research-roadmap.md ·
                  power-and-brackets.md · card-images.md · mobile.md · SETUP-windows.md
.claude/
  skills/         The mtg-deckbuilder and mtg-mobile skills
  agents/         card-verifier · collection-auditor (Bash+Read, read-only subagents
                  the deckbuilder skill delegates verification / pool scans to)
```

Root helpers: `update.bat` (pull + rebuild), `enrich.bat` (Scryfall enrichment),
`webapp/run.sh` / `webapp/run.bat` (venv + launch, LAN-bound).

## Architecture — hub and spoke

Two **hubs** feed a ring of **analysis engines**, which feed **presentation spokes**,
consumed by the web app, the CLIs, and the skill. `docs/codemap.md` has the full map and
per-module table — read it before any structural change.

- **Hubs:** `mtglib` (data: `Card`, deck/collection parsing, `classify`, pip math,
  `load_collection`) → `deckcore` (analysis: shared loaders, card-notes KB,
  `analyze_deck()` / `analyze_cards()` — the one pipeline every consumer calls).
- **Engines:** `deck_stats`, `power`, `manabase`, `combo_detector`, `deck_fit`,
  `deck_conflicts`, `analyze_collection`, `similar_commanders`, `commander_finder`,
  `card_image`, `oracle_flags` (dict-in/set-out oracle derivation; `re` only — it
  imports nothing else in the repo), `goldfish` (seeded Monte Carlo for *sequenced*
  play — the questions `manabase`'s exact-but-unconditional closed forms cannot reach;
  `deck_stats`/`deckcore` are imported inside its loader only), `clips` (the Watch tab's
  storyboard gate — every card a clip shows must be in the deck; mtglib only), `intake`
  (card intake + deck import: parse a pasted list or CSV, resolve every line through
  `carddb.verify_cards`, write a dated batch to `owned_additions.txt`, reconcile a new
  export against the batches, the Upload guard), `narration` (the Watch tab's recorded
  narration: which scenes still need a take in the chosen voice, content-hashed files,
  scene timing; the synthesis itself runs only on a runner — `narrate.yml`),
  `engine_spec` (a deck's `<stem>.engine.json`: engine cards, packages, role aims and
  engine keywords, written by a session BEFORE the draft; `auto_build --engine` seeds it
  ahead of every quota, and `engine_spec.py --audit` exits 3 until every other non-land
  card is kept with a reason or cut; deck-flow review bundle C; mtglib only),
  `collection_query` (the Collection page's search language — one string that filters,
  sorts and counts the pool: a Scryfall subset plus `free>0`, `decks=0`, `deck:`, `for:`,
  `is:pinned`, `added>=`; true/false/UNKNOWN per row, unknown rows skipped and counted,
  typos warned never zeroed; `analyze_collection.py --query` is its CLI —
  `docs/spec-collection-rebuild.md`).
- **Spokes:** `build_dashboard` (HTML dashboard + card panel), `card_api` (panel JSON),
  `auto_build` (assemble a full 99), plus `optimize`.
- **The collection database:** `store` (SQLite, stdlib) writes the player's collection on the server (`data/collection/collection.db`, gitignored); `mtglib.load_collection` reads it, so engines never know. Seeded once by the sync (`webapp/collection_db.py`), then it IS the collection — see Data formats.
- **Network-touching, disk-cached, degrade gracefully:** `carddb` (Scryfall
  `/cards/collection`), `edhrec`, `spellbook`, `rules` (WotC's Comprehensive Rules txt —
  **zero repo imports**, a first for the ring: rule text has no card names in it),
  `rulings` (Scryfall rulings for one card).

**The dependency rule: dependencies point inward.** Engines and spokes depend on the hubs,
never the reverse; spokes do not import each other. No analysis module may import
`build_dashboard` (the old circular imports were removed in refactor R1 — don't reintroduce
them).

Scripts import siblings as flat top-level modules (`import mtglib`). Running
`python3 scripts/foo.py` works because Python puts the script's directory on the path;
other consumers do `sys.path.insert(0, <root>/scripts)` (see `webapp/app.py`, `tests/conftest.py`).

## Commands

```bash
# Tests (the only dev dependency is pytest)
pip install -r requirements-dev.txt && pytest          # ~990 tests, ~40s, offline

# Web app
python3 -m venv .venv && source .venv/bin/activate
pip install -r webapp/requirements.txt
python3 webapp/app.py                                  # -> http://127.0.0.1:5000
./webapp/run.sh                                        # same, but bound to 0.0.0.0 for phones

# Core analysis (COLL = data/collection/collection.csv, or the snapshot on a fresh clone)
python3 scripts/analyze_collection.py $COLL --subtype Dragon --list
python3 scripts/analyze_collection.py $COLL --query "t:dragon free>0" [--group deck] [--json]
                                             # the Collection page's search; --query-help
python3 scripts/deck_stats.py --deck data/decks/<stem>.txt --collection $COLL
python3 scripts/power.py --rank --collection $COLL
python3 scripts/manabase.py --deck data/decks/<stem>.txt --collection $COLL
python3 scripts/combo_detector.py --deck data/decks/<stem>.txt --collection $COLL
python3 scripts/deck_conflicts.py --collection $COLL [--available]
python3 scripts/goldfish.py --deck data/decks/<stem>.txt --collection $COLL [--games 5000]
python3 scripts/goldfish.py --deck data/decks/<stem>.txt --collection $COLL \
    --ab "Out Card=In Card"          # swap one card, replay the identical games

# Build / tune / render
python3 scripts/auto_build.py "<commander>" --collection $COLL [--txt|--json]
python3 scripts/optimize.py --deck data/decks/<stem>.txt --collection $COLL [--json] # proposals + reads
python3 scripts/optimize.py --deck data/decks/<stem>.txt --collection $COLL     --approve "spell|Out|In"            # write ONLY what the player approved, after a session's read
python3 scripts/build_dashboard.py --deck data/decks/<stem>.txt --collection $COLL \
    --title "…" --commander "…" --theme <default|yshtola|cloud|rakdos|spider> --out x.html
python3 scripts/refresh.py --collection $COLL [--optimize]   # rebuild all dashboards + wishlist
                                                             # (--optimize prints proposals only)
python3 scripts/deck_sections.py --all --collection $COLL --apply   # regroup decks into type sections
python3 scripts/deck_sections.py --all --collection $COLL --check   # exit 3 on misfiled cards (CI runs this)
python3 scripts/clips.py --deck data/decks/<stem>.txt               # a deck's Watch-tab clips: outline + warnings
python3 scripts/clips.py --all --check                              # exit 3 on a stale card or lint (CI runs this)
python3 scripts/carddb.py --collection $COLL --stats         # enrich via Scryfall API
python3 scripts/carddb.py --verify "Sol Ring" --verify "Rejoinder" [--json]
                                                             # verify named cards' oracle text

# Rules — retrieve, then read, then cite (player's PC only: wizards.com is blocked elsewhere)
python3 scripts/rules.py 903.1                    # a CR rule by number, subrules in context
python3 scripts/rules.py "commander tax"          # glossary first, then full-text search
python3 scripts/rules.py --search "deathtouch trample" --limit 5 [--json]
python3 scripts/rules.py 903.1 --refresh          # re-download the CR (the only refresh)
python3 scripts/rulings.py "Sol Ring" [--json]    # Scryfall's rulings for ONE card
```

Every script takes `--help`. `deck_stats`, `power`, `combo_detector`, `deck_conflicts`,
`goldfish` and `auto_build` also take `--json` — prefer that when consuming output programmatically.

## Working rules for this repo

### Tools are non-negotiable — read `tool-contract.md` first
`.claude/skills/mtg-deckbuilder/references/tool-contract.md` maps every question to the
tool that answers it, and names the anti-patterns that cost real corrections. A
SessionStart hook (`.claude/settings.json`) injects it into context, and
`tests/test_tool_contract.py` fails if a script, workflow or agent exists that the
contract never explains. **The sandbox has no network, but GitHub Actions does** — queue
card names in `data/reference/verify-queue.txt` and push a `claude/**` branch;
`deck-verify.yml` returns verbatim Scryfall text and refreshes the field data. Verifying
more than three cards by web search is a defect, not a workaround.

### The PC is out of the loop
Do not defer follow-up work to "run this on the player's PC." The automation loop
covers it: a merged deck push triggers the field-snapshot GitHub Action (network on
the runner), the hosted app's daily/on-demand sync pulls code + snapshots down, and
the server re-enriches (Scryfall is reachable there) and re-scores everything on the
full private CSV. A sandbox session's job ends at *merge*, plus an honest note of
what the loop will finish. The one true PC-only task is `rules.py`'s Comprehensive
Rules download (wizards.com is blocked everywhere else). Physical tasks (sleeving,
buying, pulling basics) are for the player, not a machine. Note that *pulling* basics
is a physical task; *buying* them is not a thing — see the basics rule under Data formats.

### Privacy — the hard line
`data/collection/collection.csv` and `collection_attrs.csv` are **gitignored and private**
(a priced export of someone's real collection). Never commit them, and never print their full
contents into a PR body. An upload never writes the tracked snapshot:
`/collection/upload` writes the private CSV only (this closed a real price leak).
The committed `collection_snapshot.txt` is name + quantity only. It is the ownership
fallback for a fresh clone and for every Action. Exactly one thing rewrites it: the server
sync's `webapp/sync_snapshot.py`. It reads the private CSV, writes names and quantities only,
never folds in `owned_additions.txt` (that would count added cards twice), and runs **only
while an anonymous read of the repo is refused**. A public repo, or one whose privacy can't
be proven, gets nothing.

### scripts/ is stdlib-only
CI uninstalls Flask and imports every module in `scripts/` with no third-party packages
present. Adding a dependency there breaks the build — and the design. Flask belongs in
`webapp/requirements.txt`; `duckdb` is genuinely optional (`scripts/requirements-optional.txt`).

### Tests are offline and hermetic
Every deck/collection a test touches is written into pytest's `tmp_path`; the suite never
reads or writes the player's real `data/`. Keep it that way. Coverage targets the code that
can *destroy data or lie*: `test_deck_edit` (in-place deck rewrites), `test_mtglib`
(parsing/normalization/classification), `test_manabase` (hypergeometric math),
`test_auto_build` (exactly 100 cards, color legality, singleton), `test_optimize`,
`test_dashboard` (self-contained HTML, editable only in-app), `test_design_tokens`,
`test_goldfish` (Monte Carlo convergence against the exact hypergeometrics, seeded
determinism, the A/A-exact-zero common-random-numbers tripwire, cache invalidation),
`test_carddb_verify` (`--verify`'s positional batch reconciliation, the fuzzy retry, and
that an unreachable Scryfall reports UNVERIFIED instead of guessing), `test_rules`
(the CR parser against a `SAMPLE_CR` that replicates the official layout *including its
duplicated Contents headings*, the cp1252 round-trip, and the blocked-network degrade),
`test_rulings` (fuzzy-resolution surfacing, stale-okay cache, pagination),
`test_collection_query` (the search language: "sol" ranks Sol Ring first, `t:dragon`
counts every Dragon and the rows it had to skip, both readings of "free green ramp", a
typo warns instead of zeroing, basics unlimited, study lists hold no copies), `test_clips`
(a scene that shows or names a card the deck doesn't play is skipped and flagged, featured
cards are protected from the optimizer, a broken storyboard costs the Watch tab and never
the page, captions can't break out of their script tag) and `test_agents`
(the `.claude/agents/` prompts nothing else executes — names, the Bash+Read tool limit,
the grounding-rules path).
CI (`.github/workflows/tests.yml`) runs pytest on Python 3.11 and 3.13.

### One design system, two surfaces
`scripts/assets/tokens.css` is the single source of truth for the type scale, 4px spacing
scale, radii, elevation and the 44 px touch target (`--target`). It deliberately contains **no colours and no fonts** — those
are the only things a surface may differ on. The web app links it (`/static/tokens.css`);
generated dashboards **inline** it so the file stays self-contained/offline.
`tests/test_design_tokens.py` fails if `app.css` redefines a scale token, if `tokens.css`
starts hardcoding a colour, or if the two surfaces resolve a token differently. Don't add
ad-hoc font sizes or spacing values — use a token.

### The optimizer PROPOSES; the player (or a Claude session's read) decides
**Player decision 2026-10-14** (`docs/spec-optimizer-judgment.md`): "I want more AI
intelligent decisions … EDHREC … should not be the golden choice." So field % is
evidence, never the verdict, and nothing in the app applies swaps on its own:
- **⚡** (`GET /deck/<stem>/optimize`) shows the suggested swaps with their evidence; the
  player ticks the ones they want and `POST` applies only those (`optimize.apply_chosen`
  recomputes the proposals server-side, so a stale form can't write anything else).
- **Build Next** saves the draft as built and opens that same review.
- **`refresh.py --optimize`** prints every deck's proposals and writes nothing.
- **A Claude session** is the judgment layer: it reads each proposal's verified text —
  and the `reads`, owned cards EDHREC doesn't list, which can never be proposed —
  against the deck's engine (the sleeper audit, `card-review-method.md`), presents the
  table, and applies with `optimize.py --deck … --approve "<kind>|<out>|<in>"` for
  exactly what the player says go to. `--json` and the assess packet's "FOR A CLAUDE
  READ" block are the feeds. The AI
  read runs in sessions only — no API calls from the app (player decision, same day).
It never runs after a manual edit — the card panel's Remove/Replace and the deck editor
save the player's choice as-is. Never second-guess a deliberate swap. The optimizer is
idempotent: a second run on a tuned deck changes nothing, and that property is worth
preserving.
**Every edit is undoable** (2026-10-14, `docs/spec-ux-refresh.md` Wave 1.1): a toast after
each edit, an Undo on each row of the deck's Changes page, and a whole approved ⚡ run in
one tap. An undo is a NEW inverse change logged `Source=manual-undo:<row>` — manual, so the
optimizer treats the result as the player's choice and never swaps it back.

Its guardrails each exist because a naive pass got it wrong: a spell swap needs a ≥25-point
EDHREC inclusion gain; a card is valued at `max(field %, (fit−60)×2)`; the commander,
basics, `card_notes.csv` entries and anything named in the deck's `.notes.md` or featured in
its `.clips.json` are never cut; role counts must stay in template range; lands only swap for lands; with no field data
the deck is left alone. **Specificity is lift, not synergy** (2026-10-15, Phase D):
`deck_fit.commander_lift` computes EDHREC's lift (their 2025-12 replacement for synergy)
for commander pages from the inclusion and synergy every snapshot already holds, with a
1% baseline floor and 100-deck small-sample shrinkage. It sets the fit score's specificity
points, ranks the rarely-listed reads, and rides on every proposal as `cut_lift`/`add_lift`.
A `trades_specific` flag marks a ≥4× card cut for one under 2×, as evidence and never a
veto. An approved ⚡ run re-files only the cards it added, so its Undo all gives back the
same list. **Lands are valued by mana function, not field %** (Phase A,
2026-10-14): `manabase.land_mana_score` credits the deck's colours a land makes (weighted
by the spells' pip demand, two colours at most), subtracts for entering tapped, and adds
for land types the deck's fetchers want; a swap needs +0.6. There is **no basics quota** —
basics' 98-99% inclusion means nearly every deck runs some, never how many, and the old
quota traded untapped duals for basics in five-colour decks. A land with no produced data,
or making none of the deck's colours (utility lands), is never judged; a land the field
runs in ≥25% of decks is kept (an ability the score can't see); only free lands listing
≤2 colours are brought in (Rhystic Cave, Crossroads Village and filter lands list every
colour). Notes protection matches FOLDED text, so a name wrapped across lines counts. **Buy candidates never enter the 99** (2026-08-11, player
request): decks are built from owned cards only, and each buy is instead appended to the
deck's `.buylist.csv` with `Replaces` = the in-deck card to pull when it arrives —
existing buylist rows are never removed, only their `Replaces` refreshed. Which pass *owns* a card (land vs spell) is layered like
`classify()`: real type data first (collection CSV / deck `.attrs.csv`), then the deck
file's own type-exclusive section for cards already in the deck, then the field snapshot's
`lands` key (EDHREC's own Lands sections) for incoming candidates, and the name heuristic
only last — because on a name-only snapshot the spell pass once cut Hidden Lair (a real
land the hints miss) and proposed Hallowed Fountain as a spell BUY. Untyped counts are
reported in the CLI/report (`untyped`), never silently guessed around. Validate a tuned deck by
its **owned top-25 coverage** (`optimize.field_coverage`, printed as "field top-25: … of the N
you own, M in"; 2026-10-15). Raw overlap counts cards nobody owns, which is a buylist
fact, not a build fault. Every owned-but-out card needs a reason in the deck's notes. Raw
overlap far below ~50% still deserves a sentence, but it is a warning, never a gate.
Spell swaps between two GENERIC cards (both under 2× lift) need only a 15-point gain, and
only when the field shows it in inclusion % (`GENERIC_MARGIN`): role-template pressure
never moves inclusion, so the anti-churn guarantee holds. auto_build's role aims follow
the archetype and colour (`auto_build.role_quota`): no counterspell quota without blue,
whose slots go to verified protection (`resilience_staples.csv`).
**Trades between decks** (`trades.trade_offers`, bundle D; a library both `optimize` and
`auto_build` call, so a fresh draft sees them too) are offered, never applied. After the
Fable review (2026-10-15): every card a donor's notes NAME is core (the optimizer's cut
protection says the same), unless its notes list it under `## Earmarked for other decks`;
backfills must share a FUNCTIONAL role (ramp, draw, removal, wipe, counter), never just a
type; pinned cards are never offered.
- **What qualifies:** a card another deck holds every copy of, that is NOT that deck's
  core (`trades.deck_core`: its engine spec, else its `## Protected engine` / `## Protected
  cards` list, plus clip-featured cards, hand-added cards, its commander and every card its
  notes name), and that matters here (engine, ≥2.5× lift, or value 60+).
- **The backfill:** each offer carries a free same-role backfill for the donor, or
  appears only when the gain beats the donor's field % by 15+.

### UI changes get UAT'd before merge — `webapp/uat/`
Unit tests and fresh-browser screenshots passed the Arcane Ledger redesign (2026-10-11),
and the player's installed phone still rendered the new page with the **old** stylesheet.
Before merging anything that touches templates, CSS, JS or the service worker, run
`webapp/uat/upgrade.js` (an installed app receiving the deploy — must PASS),
`webapp/uat/sweep.js` (every main page at phone / Fold / tablet / desktop, the open card
panel included; exits 1 on page overflow or a tap target under 24 px, warns under 44 px),
then read the screenshots. Anything that touches an edit flow also runs
`webapp/uat/flows.js` against a scratch copy: replace, add, ⚡, mulligan, the table card,
undo through the screens a player taps (the toast, ⚡ Undo all, the Changes page, an
earlier version), the keyboard path (skip link, panel focus in and back) and the phone
deck page (tabs on the first screen, the list by default, filter, panel, zoom), a timed
Collection sort (F13: a quadratic observer once froze every sort for 4-6 s while every
other flow passed) and the Collection's search (F14: first card on the first screen, live
search, a scope chip, a chip removing itself, the Filters sheet's count matching the page,
Load more kept through Back, the sub-tabs, help giving focus back), each read back from the
deck FILES (must PASS). `tests/test_a11y.py` fails on any form control
without an accessible name. The sweep photographs pages; the
2026-10-14 audit found every damaging bug in flows it never ran. `webapp/uat/README.md`
has the commands.

### Network access degrades, never crashes
Scryfall / EDHREC / Commander Spellbook are reachable from the player's machine but may be
proxy-blocked in a sandbox. Those clients are disk-cached (`data/cache/`, gitignored) and
must degrade gracefully. Card images are always **browser hotlinks**, never server-side
fetches — see `docs/card-images.md`. When delivering a dashboard, warn that card images only
render in a real browser.

## Data formats

**Deck** — `data/decks/<stem>.txt`: `# Key: value` headers (`Title`, `Commander`, `Colors`,
`Archetype`, and optionally `Theme`, `Source`, `Deck`, `Note`, `Study`), then `# --- Section ---`
groups of `<qty> <card name>` lines. Section names are free-form to the parser, but the
**convention (2026-08-11) is EDHREC-style type sections** — Commander, Creatures, Instants,
Sorceries, Artifacts, Enchantments, Planeswalkers, Lands, Basics — kept in shape by
`deck_sections.py` (regroup; idempotent; unknown types go to an explicit `Unsorted`
section, never guessed). Role/power info is NOT in the sections: `mtglib.classify` roles
plus `deckcore.load_power_tags` labels (Game Changer, Fast mana, Tutor, Extra turns, Mass
land denial) ride along in the card details on both surfaces. The dashboard groups the
decklist by the file's own sections, so **preserve them when editing**. Edits rewrite the
file in place and must keep quantity, section, and comment lines intact (that's what
`test_deck_edit.py` guards).

**Study copies** — `# Study: yes` marks a deck kept for review, not sleeved from the
collection (the Tergrid options; the Bartolomé deck tech was one until the player bought its
cards on 2026-10-12). It commits no physical copies:
`deck_conflicts.scan`, the free pool, the wishlist and `optimize --all` skip it
(`deck_conflicts.is_study_deck`). Name it with `--deck` to analyze it on purpose.

**Deck companions** (auto-detected next to `<stem>.txt`):
`.notes.md` (game plan — markdown-lite; cards named here are protected from the optimizer),
`.buylist.csv` (`Card,Price,Tier,Replaces,Reason`), `.attrs.csv`
(`Name,Type,MV,Colors[,Produced,Flags]` — curve without the full CSV; the two optional
columns are the same contract as the collection file, carried by
`deckcore.load_attrs`/`apply_attrs` under the same empty-vs-absent rule, which is what
lets the goldfish sim run its enriched mana model on a fresh clone), `.changes.csv` (`Card,Added,Replaced,Source[,By]` — appended by
each applying optimizer run and every app edit, editor saves included, always through
`deckcore.append_changes`; `By` appears once named members exist; the dashboard badges
anything from the last 14 days as `NEW`. A row's POSITION is its identity — undo names rows
by position, so the file is append-only: never reorder or delete a row, and never hand-write
one (an unquoted comma in a card name breaks the columns; CI's change-log check fails on it)),
`.clips.json` (the **Watch tab**: 30-60s animated how-to-play clips, scenes of the deck's own
cards in zones with captions — validated by `clips.py` against the CURRENT list on every
render. Captions name cards as `[[Card Name]]` (or `[[Card Name|shown text]]`), and a scene
that shows OR names a card that left the deck is skipped while the tab says the clips are out
of date. Every card a clip features is protected from the optimizer like a notes-named card,
so automatic tuning never strands a scene. **When you change a deck that has clips, rewrite
the stale scenes in the same change** — CI's `clips.py --all --check` fails until you do.
Opponents' cards are `ph` placeholders, never named; nothing is rendered to a video file),
`.verdicts.json` (a Claude session's read of the optimizer's proposals and reads, written
only by `optimize.py --verdict "<key>" <swap|skip|bench|wishlist> "<why>"`, which refuses
any key the optimizer isn't proposing right now. The ⚡ page shows each verdict beside
the SAME swap and hides stale ones with a count. This is how the AI read reaches the phone
while the app makes no AI calls. Deck-flow review bundle B, `docs/spec-deck-flow-review.md`),
`.engine.json` (the deck's engine spec, written through `engine_spec.py` only: its core
cards are protected from the optimizer like notes-named ones, and its keywords rank the
field-silent reads against oracle text cached by enrichment and `--verify`, which `carddb`
keeps in `data/cache/scryfall/`).

**Collection database (server, 2026-10-13+)** — `data/collection/collection.db`, gitignored, never synced. The server sync seeds it ONCE as the union of every record (private export, the committed August list, every `owned_additions.txt` block, every sleeved deck: `store.seed`, report on the Collection page) and from then on it is the collection: app adds/edits go straight to it (every change in its `ledger`), an Upload only MERGES (never lowers a count), and batches a session commits to `owned_additions.txt` are ingested once each by the next sync. A `[floor]` line in a batch's comments means "own at least this many" (raise, don't add) in both the database and the file loader. Sessions still add cards exactly as before (`intake.py` → a dated batch); never write the database from a session, and never re-seed one. **Decks and pins live there too (Phase 1b, 2026-10-14):** the database keeps every deck file (`<stem>.txt` and its companions) and `pins.csv` with every revision (`files` + `file_revisions`). The deck folder stays the working copy every engine reads; `store.capture` records it after every successful app write and every sync (so a session's committed deck edit becomes a revision with the next pull), and `store.restore` rebuilds the folder only when it is missing (a new host) or one file on request. Edit decks exactly as before. **So do members and the activity log (Phase 1b, 2026-10-14):** in database mode `users.py` keeps the member store in the database (`members` + the owner's settings in `meta`; it takes `data/private/users.json` in on its first read and renames it `users.json.moved-to-db`, and the database is chmod 0600 because it now holds the hashes), and deck-level actions go to its `activity` table instead of `data/activity.csv` (the sync and the Activity page take in any rows still in that file, each once). No download ever includes the `members` table. **Backups (2026-10-14):** the sync's first act each day is `store.daily_backup` — a consistent copy in `data/collection/backups/collection-<date>.db` (gitignored, 0600, newest `MTG_BACKUPS_KEEP`=7 kept), taken BEFORE that sync ingests or captures anything; the owner's **Download a backup** (`/export/backup.db`) is the same copy with the `members` table emptied and the file rebuilt (VACUUM), so no hash leaves the server. Undo a bad day from a console: copy a dated file over `collection.db`, then reload the web app.

**Collection** — rich Archidekt/ManaPool CSV (`Quantity, Name, Mana Value, Colors,
Identities, Mana cost, Types, Sub-types, Super-types, Rarity, Scryfall ID`) unlocks
color/type/tribe/curve/pip analysis; the name-only snapshot answers ownership only.
`collection_attrs.csv` (written by `carddb.py`) is
`Name,Type,MV,Colors,Cost,Sub-types,Scryfall,Produced,Flags,Power,FlagsVer` —
`Produced` is space-joined WUBRGC letters for what the card actually taps for,
`Flags` is `;`-joined oracle-derived tokens (`oracle_flags.py`'s vocabulary —
v1: `etb-tapped`, `etb-tapped-cond`, `rock`, `dork`, `ramp`, `draw`,
`mana2`/`mana3`, `removal`, `wipe`, `counter`; v2 adds `fetch:*` and
`mana-restricted`; v3 adds the cost-reduction tokens `discount-cmd:<type>:<n>`,
`discount:<type>:<n>`, `discount-first:<type>:<n>` — see
`docs/spec-cost-reduction.md`; v4 reads edicts ("each opponent sacrifices a
creature") as `removal` and adds black's mana engines for the goldfish sim —
`ritual:<n>`, `scale:[basic-]<type>:<cost>` (Cabal Coffers/Stronghold),
`devotion:<cost>` (Nykthos), `extra:<type>` (Crypt Ghast), `lands-are:<type>`
(Urborg)), `Power` is the front face's printed power verbatim, and
`FlagsVer` is the vocabulary version that produced the Flags cell — flags and
their version are ONE write, so a file whose Flags column arrives without a
FlagsVer reads as version 1 (pre-v2), never as verified-current. **The
empty-vs-absent rule is load-bearing:** an *empty cell* means enriched and produces
nothing (Maze of Ith → `Card.produced == set()`), while an *absent column* means
unknown (`Card.produced is None`) and every consumer must fall back to color identity
**and say so**. Conflating the two is a bug, not a rounding error.
`load_collection` auto-merges `collection_attrs.csv` (derived) and `owned_additions.txt`
(player-confirmed cards the export missed — the player's word beats the export). Its rows
sit in dated blocks (`# --- Batch 2026-10-12 · <what> · N cards ---`, written by
`intake.py` or the app's Add a batch); `mtglib.parse_additions` dates each row from the
block above it, which is what the New arrivals review reads. A batch a later export
carries is retired by commenting its rows out (`# retired <date> (in export): …`), never by
deleting them — and never through the site's Upload, which replaces the whole collection.
`pins.csv` (`Card,Deck`) reserves a physical copy for one deck; other decks treat it as
unavailable.

**Basic lands are always owned, in unlimited quantity** (player-ratified 2026-08-17). The
player has hundreds of each and deliberately does not track them in the export, so the
snapshot's basic counts are an artifact, not a limit. Any number of `Forest` / `Island` /
`Swamp` / `Mountain` / `Plains` / `Wastes` (and Snow-Covered printings) in a decklist is
satisfied; basics never go on a buy list, a wishlist or a shortfall report, and never
constrain a manabase or a cross-deck conflict. `mtglib.is_basic` is the repo-wide test and
every consumer honours it — `deck_conflicts`, `optimize` and `deck_stats.owned_enough()`
(`tests/test_basics_unlimited.py`). Full rule: `grounding-rules.md` #9.

**Reference** — `data/reference/*.csv|.txt` are hand-editable knowledge: `combos.csv`
(`Pieces` are `;`-separated so card-name commas survive), `card_notes.csv` (curated "why it
works" — always beats `card_notes.generated.csv`), `game_changers.txt` (the verified 53-card
WotC list), `commanders.csv`, `role_staples.csv`, `archetype_support.csv`,
`pronunciations.csv` (`Word,Say as` for the Watch tab's narrator — empty on purpose; add a
row only when the player hears a name said wrong, never a guessed pronunciation).

## Web app notes

`webapp/app.py` is the primary spoke consumer: routes call engines/spokes and render Jinja
templates. Config via env: `MTG_COLLECTION`, `MTG_DECKS_DIR`, `MTG_PORT`, `MTG_HOST`
(`0.0.0.0` for phone access — noted as a LAN exposure in the README).

Key routes: `/` decks leaderboard · `/deck/<stem>` live dashboard · `/deck/<stem>/card`
(remove/replace) · `/deck/<stem>/optimize` · `/deck/<stem>/pin` · `/deck/<stem>/assess[.txt]`
(coaching packet) · `/build-next` (+ `/…/deck`, `/…/save`) · `/collection` — three sub-tabs
(docs/spec-collection-rebuild.md): **Cards** (`?q=` the one query language + `scope`, `order`,
`dir`, `group`, `view`, `n`; `/collection/results` live search, `/collection/rows` Load more,
`/api/collection/count` the Filters sheet's live count), **Add** (`GET /collection/add`; the
POST of the same path adds one card; `/upload`) and **Manage** (`/collection/manage`:
downloads, backups, set a count, history, card data, the reconcile offer) · `/wishlist` · `/shared` · `/api/card/<name>` · `/api/collection/search` ·
`/api/edhrec/<commander>` · `/api/combos/build/<commander>` · `/mobile` · `/sw.js` · `/health` ·
`/collection/batch` (+ `/confirm`: paste → preview → write a dated batch) ·
`/export/additions.txt` (the added cards as `qty name` lines to import into Archidekt/ManaPool,
so the next export carries them and the upload's reconcile retires the rows) · `/collection/upload/decide`
(the Upload guard's second tap) · `/collection/reconcile` · `/collection/arrivals[.txt]` ·
`/decks/import` (+ `/confirm`: the player's own list → a new deck or a new list for one) ·
`/people` (owner only: named members) · `/activity` · `/deck/<stem>/changes` (+ `/undo`:
reverse logged rows; `/restore`: an earlier stored version, database mode) ·
`/narration/<stem>/<file>` (a deck's recorded narration — manifest-listed takes only,
immutable caching; the service worker never touches it).

**Named members** (docs/spec-second-login.md): `webapp/users.py` keeps member accounts in
the collection database once the app runs on one (see Data formats), else in
`data/private/users.json` — gitignored, mode 0600, never synced. The owner still signs in
with `MTG_PASSWORD`; a member signs in with a name and their own password and can do
everything except the People page and (unless allowed) replacing the collection. Once a
member store exists, every change the app writes carries `By` (`.changes.csv`'s optional
fifth column, written through `deckcore.append_changes`) and deck-level actions go to the
activity log: the database's `activity` table, or `data/activity.csv` (which the sync
commits) on files. With no store, none of that happens — the app is the single-password app
it always was.

The saved-deck dashboard is editable (`build_dashboard.generate(..., editable=True)`);
CLI-rendered dashboards keep `editable=False`. Both surfaces share `generate()`, so a change
to the renderer changes the CLI output and the app identically — check both.

## Known traps

- **`" // "` with spaces is the split-card separator.** A bare `//` can be part of a real
  card name (`SP//dr, Piloted by Peni`). `mtglib.front_face()` handles this; a naive
  `split("//")` once produced a bogus alias that let the optimizer add six copies of a
  singleton. Any new name-normalization must go through `front_face` / `_norm` / `lookup`.
- **Role/category counts are heuristic.** `classify()` reads three layers in strict
  precedence: curated name lists, then the oracle-derived `Card.flags` `carddb` writes
  (`rock`/`dork`/`ramp`, `draw`, `removal`, `wipe`, `counter` — consulted **only where the
  curated lists are silent**, which is what keeps a hand-verified card from being
  overruled by a regex), then card types. A collection that has never been enriched has
  `flags == set()`, so the flag layer no-ops and counts are unchanged. Strong first pass;
  eyeball the result before asserting it — and a wrong flag is invisible to the honesty
  labels, which fire when data is *absent*, not when it is *wrong*.
- **`optimize.singleton_violations()` runs after every write** and the CLI prints
  `!! ILLEGAL`. Keep that check — this class of bug was silent for four commits.
- **Templates reference static files only through `{{ asset('name') }}`.** It emits a
  content-hashed URL (`/static/app.css?v=<hash>`); the service worker serves those
  cache-first and plain `/static/` URLs network-first. A bare `/static/...` link is how a
  deploy painted new markup with yesterday's CSS; `test_ui_ledger` fails on one.
- **A dashboard must stay one self-contained file.** Assets in `scripts/assets/` are read by
  `_asset()` and inlined at render time; don't turn them into external links.
- **The two surfaces open the card panel from different hooks.** App templates use
  `data-card="<name>"` (`webapp/static/cardpanel.js`); generated dashboards wire their own
  inlined panel to `figure.mc[data-key], .cardlink[data-key], .dl-row[data-key]` (a Deck-tab
  list row is the same card as its tile). A selector that works on one
  surface will silently no-op on the other — check both when touching panel wiring.
- **The goldfish A/B pairs positionally.** `compile_deck` expands copies in deck-file
  order and `simulate_ab` replaces the outgoing card *at the same library indices*, so
  both arms replay identical shuffles (common random numbers). Re-sorting a compiled
  deck anywhere breaks the pairing **silently** — the numbers stay plausible, the
  confidence intervals just stop meaning anything. `test_goldfish`'s A/A-exact-zero
  test is the tripwire; if it fails, that's what happened.
- **The Comprehensive Rules file repeats its own headings.** Its Contents listing names
  every chapter and section and *ends with the words "Glossary" and "Credits"*. Slice the
  body on the FIRST "Glossary" and you get a parsed-looking dict with **zero rules** in it —
  a silent failure, not a crash. `rules._slice_body` uses first-Credits / last-Glossary /
  last-Credits, and `test_rules.py`'s `SAMPLE_CR` carries the duplication so the guard bites.
- **`docs/handoff.md` is current-state only** (rewritten 2026-08-10; the layered history
  moved to git). Keep it that way — update it in place, don't append dated layers. For
  architecture, trust `docs/codemap.md` over the handoff.

## Git workflow

Develop on the assigned feature branch, never directly on `main`. PRs are **squash-merged**,
so re-sync the branch to `origin/main` before starting new work or the next PR conflicts.

Commit messages in this repo are substantial: a one-line subject describing the user-visible
outcome, then a body explaining the root cause, the fix in layers, and what was verified
(test counts, deck totals, before/after field overlap). Match that style — see
`git log` for examples.

When a session produces or materially changes a deck, update `docs/handoff.md` so the next
session starts grounded instead of re-deriving, and tick the tracker in
`docs/spec-interactive-analytics-ai.md` when a spec'd feature lands.
