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
  `deck_stats`/`deckcore` are imported inside its loader only).
- **Spokes:** `build_dashboard` (HTML dashboard + card panel), `card_api` (panel JSON),
  `auto_build` (assemble a full 99), plus `optimize`.
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
pip install -r requirements-dev.txt && pytest          # 480 tests, ~120s, offline

# Web app
python3 -m venv .venv && source .venv/bin/activate
pip install -r webapp/requirements.txt
python3 webapp/app.py                                  # -> http://127.0.0.1:5000
./webapp/run.sh                                        # same, but bound to 0.0.0.0 for phones

# Core analysis (COLL = data/collection/collection.csv, or the snapshot on a fresh clone)
python3 scripts/analyze_collection.py $COLL --subtype Dragon --list
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
python3 scripts/optimize.py --deck data/decks/<stem>.txt --collection $COLL          # preview
python3 scripts/optimize.py --all --collection $COLL --apply                        # write
python3 scripts/build_dashboard.py --deck data/decks/<stem>.txt --collection $COLL \
    --title "…" --commander "…" --theme <default|yshtola|cloud|rakdos|spider> --out x.html
python3 scripts/refresh.py --collection $COLL [--optimize]   # rebuild all dashboards + wishlist
python3 scripts/deck_sections.py --all --collection $COLL --apply   # regroup decks into type sections
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
(a priced export of someone's real collection). Never commit them, never print their full
contents into a PR body, and never write uploads to the tracked name-only snapshot —
`/collection/upload` deliberately writes to the private CSV only (this closed a real leak).
The committed `collection_snapshot.txt` is name + quantity only and is the ownership
fallback for a fresh clone.

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
`test_rulings` (fuzzy-resolution surfacing, stale-okay cache, pagination) and `test_agents`
(the `.claude/agents/` prompts nothing else executes — names, the Bash+Read tool limit,
the grounding-rules path).
CI (`.github/workflows/tests.yml`) runs pytest on Python 3.11 and 3.13.

### One design system, two surfaces
`scripts/assets/tokens.css` is the single source of truth for the type scale, 4px spacing
scale, radii and elevation. It deliberately contains **no colours and no fonts** — those
are the only things a surface may differ on. The web app links it (`/static/tokens.css`);
generated dashboards **inline** it so the file stays self-contained/offline.
`tests/test_design_tokens.py` fails if `app.css` redefines a scale token, if `tokens.css`
starts hardcoding a colour, or if the two surfaces resolve a token differently. Don't add
ad-hoc font sizes or spacing values — use a token.

### Optimization is automatic in four places, and deliberately NOT in a fifth
It runs when a deck is saved from Build Next, via the ⚡ button (`POST /deck/<stem>/optimize`),
via `refresh.py --optimize`, and as step 5 of the skill's build workflow. It does **not**
run after a manual edit — the card panel's Remove/Replace and the deck editor save the
player's choice as-is. Never second-guess a deliberate swap. The optimizer is idempotent:
a second run on a tuned deck changes nothing, and that property is worth preserving.

Its guardrails each exist because a naive pass got it wrong: a swap needs a ≥25-point
EDHREC inclusion gain; a card is valued at `max(field %, (fit−60)×2)`; the commander,
basics, `card_notes.csv` entries and anything named in the deck's `.notes.md` are never
cut; role counts must stay in template range; lands only swap for lands; with no field data
the manabase is left alone. **Buy candidates never enter the 99** (2026-08-11, player
request): decks are built from owned cards only, and each buy is instead appended to the
deck's `.buylist.csv` with `Replaces` = the in-deck card to pull when it arrives —
existing buylist rows are never removed, only their `Replaces` refreshed. Which pass *owns* a card (land vs spell) is layered like
`classify()`: real type data first (collection CSV / deck `.attrs.csv`), then the deck
file's own type-exclusive section for cards already in the deck, then the field snapshot's
`lands` key (EDHREC's own Lands sections) for incoming candidates, and the name heuristic
only last — because on a name-only snapshot the spell pass once cut Hidden Lair (a real
land the hints miss) and proposed Hallowed Fountain as a spell BUY. Untyped counts are
reported in the CLI/report (`untyped`), never silently guessed around. Validate a tuned deck with EDHREC top-25 overlap — below ~50%
means something is wrong, so say so rather than shipping quietly.

### Network access degrades, never crashes
Scryfall / EDHREC / Commander Spellbook are reachable from the player's machine but may be
proxy-blocked in a sandbox. Those clients are disk-cached (`data/cache/`, gitignored) and
must degrade gracefully. Card images are always **browser hotlinks**, never server-side
fetches — see `docs/card-images.md`. When delivering a dashboard, warn that card images only
render in a real browser.

## Data formats

**Deck** — `data/decks/<stem>.txt`: `# Key: value` headers (`Title`, `Commander`, `Colors`,
`Archetype`, and optionally `Theme`, `Source`, `Deck`, `Note`), then `# --- Section ---`
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

**Deck companions** (auto-detected next to `<stem>.txt`):
`.notes.md` (game plan — markdown-lite; cards named here are protected from the optimizer),
`.buylist.csv` (`Card,Price,Tier,Replaces,Reason`), `.attrs.csv`
(`Name,Type,MV,Colors[,Produced,Flags]` — curve without the full CSV; the two optional
columns are the same contract as the collection file, carried by
`deckcore.load_attrs`/`apply_attrs` under the same empty-vs-absent rule, which is what
lets the goldfish sim run its enriched mana model on a fresh clone), `.changes.csv` (`Card,Added,Replaced,Source` — appended by
each applying optimizer run; the dashboard badges anything from the last 14 days as `NEW`).

**Collection** — rich Archidekt/ManaPool CSV (`Quantity, Name, Mana Value, Colors,
Identities, Mana cost, Types, Sub-types, Super-types, Rarity, Scryfall ID`) unlocks
color/type/tribe/curve/pip analysis; the name-only snapshot answers ownership only.
`collection_attrs.csv` (written by `carddb.py`) is
`Name,Type,MV,Colors,Cost,Sub-types,Scryfall,Produced,Flags,Power,FlagsVer` —
`Produced` is space-joined WUBRGC letters for what the card actually taps for,
`Flags` is `;`-joined oracle-derived tokens (`oracle_flags.py`'s vocabulary —
v1: `etb-tapped`, `etb-tapped-cond`, `rock`, `dork`, `ramp`, `draw`,
`mana2`/`mana3`, `removal`, `wipe`, `counter`; v2 adds `fetch:*` and
`mana-restricted`), `Power` is the front face's printed power verbatim, and
`FlagsVer` is the vocabulary version that produced the Flags cell — flags and
their version are ONE write, so a file whose Flags column arrives without a
FlagsVer reads as version 1 (pre-v2), never as verified-current. **The
empty-vs-absent rule is load-bearing:** an *empty cell* means enriched and produces
nothing (Maze of Ith → `Card.produced == set()`), while an *absent column* means
unknown (`Card.produced is None`) and every consumer must fall back to color identity
**and say so**. Conflating the two is a bug, not a rounding error.
`load_collection` auto-merges `collection_attrs.csv` (derived) and `owned_additions.txt`
(player-confirmed cards the export missed — the player's word beats the export).
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
WotC list), `commanders.csv`, `role_staples.csv`, `archetype_support.csv`.

## Web app notes

`webapp/app.py` is the primary spoke consumer: routes call engines/spokes and render Jinja
templates. Config via env: `MTG_COLLECTION`, `MTG_DECKS_DIR`, `MTG_PORT`, `MTG_HOST`
(`0.0.0.0` for phone access — noted as a LAN exposure in the README).

Key routes: `/` decks leaderboard · `/deck/<stem>` live dashboard · `/deck/<stem>/card`
(remove/replace) · `/deck/<stem>/optimize` · `/deck/<stem>/pin` · `/deck/<stem>/assess[.txt]`
(coaching packet) · `/build-next` (+ `/…/deck`, `/…/save`) · `/collection` (+ `/add`,
`/upload`) · `/wishlist` · `/shared` · `/api/card/<name>` · `/api/collection/search` ·
`/api/edhrec/<commander>` · `/api/combos/build/<commander>` · `/mobile` · `/sw.js` · `/health`.

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
- **A dashboard must stay one self-contained file.** Assets in `scripts/assets/` are read by
  `_asset()` and inlined at render time; don't turn them into external links.
- **The two surfaces open the card panel from different hooks.** App templates use
  `data-card="<name>"` (`webapp/static/cardpanel.js`); generated dashboards wire their own
  inlined panel to `figure.mc[data-key], .cardlink[data-key]`. A selector that works on one
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
