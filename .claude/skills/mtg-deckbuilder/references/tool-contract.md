# The Tool Contract — NON-NEGOTIABLE

**Why this file exists.** On 2026-08-19 a session verified ~40 cards one at a time with
web search while `.github/workflows/deck-verify.yml` — which does exactly that against
Scryfall, on a runner with real internet — sat unused for six merged PRs. CLAUDE.md,
SKILL.md and grounding-rules.md were all loaded at the time. **Prose the session has to
remember is not a control.** This file is printed into context by a SessionStart hook and
enforced by `tests/test_tool_contract.py`, which fails if any script, workflow or agent is
missing from the table below.

**The rule in one line: if a tool answers the question, the tool answers the question.**
Reaching for WebSearch, a scratch Python snippet, or your own memory when a listed tool
covers the job is a defect, not a shortcut.

---

## 1. NETWORK — the sandbox has none; GitHub Actions does

The egress proxy answers 403 to Scryfall, EDHREC, Commander Spellbook and YouTube.
**That is not a dead end. It is a routing instruction.**

| Need | Do this | NEVER |
|---|---|---|
| Verbatim oracle text for any card | append names to `data/reference/verify-queue.txt`, commit, push the `claude/**` branch → **`deck-verify.yml`** runs `carddb.py --verify` on a runner and pushes results back; read them with `get_job_logs` | web-search cards one at a time. Past **3** cards this is a defect |
| Card data (type/MV/production) for a deck of cards the collection lacks | dispatch **`deck-verify.yml`** with `deck_attrs: <stem> …` — the runner enriches `data/decks/<stem>.txt` into `<stem>.attrs.csv` and commits it to the branch | hand-write an `.attrs.csv`, or ship a study deck with an empty curve |
| Fresh EDHREC field data | same push — `deck-verify.yml` also snapshots every commander in `data/decks/` | hand-roll a field analysis, or call a deck "unsupported" on stale data |
| Enrich the whole collection | **`attrs-snapshot.yml`** (weekly + on a snapshot or `owned_additions.txt` change) | commit a hand-built attrs file |
| What's in a precon the player bought | dispatch **`deck-verify.yml`** with `precons: Name \| Name` → **`precon.py`** fetches MTGJSON's official list into `data/reference/precons/<slug>.txt`, the same run verifies every non-basic card (text + price) and writes `<slug>.attrs.csv`; then add the cards to `owned_additions.txt` as a dated batch with **`intake.py`** (`docs/spec-card-intake.md`) | name a new product's cards from memory or from web summaries of the list — they disagree on the counts |
| The repo's `collection_snapshot.txt` is behind the app (cards in a real deck read as unowned in the sandbox) | nothing in a session: the server sync's **`webapp/sync_snapshot.py`** rewrites it from the private CSV (names + quantities) once the repo is private, and `attrs-snapshot.yml` then types it. Until then, a type gap in ONE deck is closed with `deck-verify.yml`'s `deck_attrs` | regenerate it from deck lists or memory; add `owned_additions.txt` rows for cards the export already has (they'd count twice) |
| Where the collection lives on the server (2026-10-13+) | **`store.py`**: the SQLite collection database (`data/collection/collection.db`, gitignored). The server sync seeds it ONCE (`webapp/collection_db.py`, the union of the export, the August list, every `owned_additions.txt` block and every sleeved deck), then ingests each new batch a session commits. A session still adds cards the same way, as a dated batch in `owned_additions.txt` via **`intake.py`**: the sync applies it. `store.py seed … ` (dry run by default) shows what a seed would do. Decks and `pins.csv` are kept there too with every revision (`store.py history decks/<stem>.txt`; `restore --file … --rev …` brings one back) — sessions still edit the deck FILES, the sync records them. Member accounts and the activity log live there too (server only; `store.py activity` prints the newest actions on the server console). Daily copies sit in `data/collection/backups/` on the server (`store.py backup` makes one by hand) | write to the database from a session, re-seed a database that already holds cards (it refuses: every count would double), or tell the player to re-upload an export to fix ownership once the database exists (an upload now only merges up) |
| The player wants the added cards in their own Archidekt/ManaPool | Collection → **Download added cards** (`/export/additions.txt`), or **`export_manapool.py --additions`** | hand-copy `owned_additions.txt` (its comments and retired rows break importers) |
| The player pastes or attaches a list of NEW cards | queue the names for **`deck-verify.yml`**, save the run's `carddb.py --verify --json` output, then **`intake.py <list> --verified <json>`** (preview: ✓ / ? / ✗ per line) and `--write --label "…"` to append ONE dated batch to `owned_additions.txt` — names and quantities only. In the app the player does the same from Collection → **Add a batch** | write `owned_additions.txt` rows by hand or a scratch script; route a partial list through the site's Upload (it replaces the whole collection); put a price, seller, order number or file name in the batch label |
| "where do my new cards fit?" | the sleeper audit (**`card-review-method.md`**) over **`/collection/arrivals.txt`**'s packet: every sleeved deck AND every Lab deck the card is legal in gets a verdict. List the Lab with `grep -l "^# Study: yes" data/decks/*.txt` | review only the sleeved decks. A theory deck claims no copies, so it can take a card its sleeved home also takes; a review of three arrivals missed all four Lab decks this way (2026-10-16) |
| "how many combos does this deck have?" | **`spellbook.py`** — Commander Spellbook's FULL combo DB, present and one-away | count combos by hand. A session hand-counted a deck's 44 engines because this was never consulted; it is blocked in the sandbox, so **run it where network exists and say so** |
| Scheduled weekly field refresh (main) | **`field-snapshots.yml`** | dispatch it on a feature branch — it pushes to `main`. Use `deck-verify.yml` from a branch |
| Comprehensive Rules | **`rules.py`** — retrieve, then read, then cite | quote a rule number you did not just retrieve. If it degrades, say **uncited** |
| One card's rulings | **`rulings.py`** | infer an interaction from the card text alone |

**A push IS the network call.** Queue the work, push, read the log. One round trip beats
thirty searches, and it is the only channel that produces *verbatim* text.

## 2. THE COLLECTION — count it, never characterise it

| Question | Tool | NEVER |
|---|---|---|
| "what can I build?" / "how many X do I own?" | `analyze_collection.py`, or the **`collection-auditor`** agent | eyeball the snapshot |
| Any filtered count of the pool — "free green ramp", "Dragons in no deck", "what's in that list I own", "cards added this month" | **`analyze_collection.py --query "…"`**: the Collection page's own search language (**`collection_query.py`**: `t:` `id<=` `role:` `free>0` `decks=0` `deck:` `for:` `added>=` …; `--query-help` lists every keyword). Quote its summary line, skipped count included: a skipped row is missing data, not a "no" | write a scratch filter over `load_collection`, or report a count without its skipped rows. The page, the CLI and the skill must give the player ONE number |
| "is archetype X supported?" | `analyze_collection.py` **+ `commanders.csv` + `data/reference/field/*.json`** | measure against a staples list. This produced a wrong "treasures unsupported" verdict while the player owned **Smaug, Wicked Worm ×2** |
| "what infinite can I assemble today?" | `combo_detector.py --collection-combos` | reason about combos from memory |
| "which decks share cards?" / what is free | `deck_conflicts.py [--available]` | assume a card is uncommitted |
| "what does the field run that I lack?" | `edhrec.py` | guess at inclusion rates |
| "what should I build next?" | `commander_finder.py`, `similar_commanders.py` | |

## 3. DECKS — the build loop is a pipeline, not a vibe

**`auto_build.py` → `deck_sections.py` → `optimize.py` (proposals) → your engine read → `--apply` on the player's go → validate.** Run it in that
order every time. It assembled a tuned 100-card Smaug deck in one command after a session
had spent its effort hand-reasoning.

| Job | Tool | NEVER |
|---|---|---|
| Assemble a 99 | `auto_build.py` | hand-pick 99 cards |
| Log a deck the PLAYER built (their own list) | in the app: Decks → **Import a list** (`/decks/import`: ownership + shared-card check, type sections, an existing deck's list replaced with the diff logged as manual adds/removals). In a session: verify the names (`deck-verify.yml`), write `data/decks/<stem>.txt`, run `deck_sections.py --apply` | run `optimize.py --apply` on it — the player's own list is a set of deliberate choices; offer swaps instead |
| Regroup into type sections | `deck_sections.py` | hand-edit section headers |
| Tune against the field | `optimize.py` proposals, **read against the deck's engine**, each verdict saved with `--verdict` (the ⚡ page shows it on the phone), then `--approve` what the player approves — **mandatory after any build or rebuild**. Read the trades too (`trades.py`, a library both `optimize` and `auto_build` call): a deck releases a notes-named card for another deck only through its notes' `## Earmarked for other decks` | ship an untuned deck, or apply proposals on field % alone (EDHREC is evidence, not the verdict — player, 2026-10-14) |
| Full deck analytics | **`deckcore.analyze_deck()`** | `deck_stats.py` on a deck with an `.attrs.csv` — it does **not** read the companion and reports 31 lands / empty curve where the hub reports 37 / real |
| Mana math | `manabase.py` | hypergeometrics by hand |
| Sequenced play, mulligans, A/B a swap | `goldfish.py` | assert a swap is better without replaying it |
| Does this deck pass its UAT (consistency, engine online by turn 6, commander on time)? What does a swap do to it? | `deck_uat.py --deck … --collection …` (exit 3 on a failed gate; `--all` for every deck; `--ab "Out=In"` paired deltas); `optimize.py --json --ab` puts that A/B on every proposal | call a deck finished, or a swap good, without running the gates. Field % says what others play; the A/B says what the swap does to THIS deck |
| Power / bracket | `power.py` | assign a bracket by feel |
| How do the decks do against EACH OTHER (the household pod, and the matchups the player asks about)? | `forge_pod.py` on the player's PC: `--install` once (Forge 2.0.15, Java 17+), `--check` for cards Forge can't play, then a run (`--games-per-deck 16 --workers 2`). Results go to `data/reference/pod/<date>.json`, the app's **Matchups** page reads the newest, and `--report <file>` prints the standings | call a win share a verdict (Forge's AI pilots combo and control badly; 16 games is ±11 points); count a timed-out game as a win (Forge names every survivor a winner); run it in the sandbox or on a runner (not built: a game is a 2 GB JVM, ~1 min) |
| Combos present or one-away | `combo_detector.py` | |
| Dashboard | `build_dashboard.py`, or `refresh.py` for all | hand-write HTML |
| Build a deck ENGINE-FIRST | read the commander and the counted pool, then write the deck's engine spec: `engine_spec.py --deck <path> --init` (seeds from the notes' `## Protected engine` list; `--commander` before the deck exists), add packages, aims and keywords with `--package`, `--aim` and `--keyword`, then `auto_build.py "<commander>" --engine <stem>.engine.json` (engine cards go in before any quota; every other card is FILLER). Give each filler card a reason with `engine_spec.py --keep "<card>" "<why>"` or cut it; `engine_spec.py --audit` exits 3 until every non-land card is engine, package or kept with a reason | let a drafted card stay because nothing argued it out (the Consecrated Sphinx lesson); hand-edit the JSON |
| Watch-tab clips (animated how-to-play) | write `<deck>.clips.json` (name cards in captions as `[[Card]]` so they're checked), then `clips.py --deck <path>` for the outline + warnings; `clips.py --all --check` runs in CI — after changing a deck with clips, rewrite the stale scenes it reports | show a card the deck doesn't play, or name an opponent's real card (use a `ph` placeholder); render a video file |
| Choosing the Watch tab's narrator voice (recorded, free) | dispatch **`narrate-audition.yml`** on the working branch — a runner records the same Iron Fortress scenes in six open-source voices (Kokoro-82M, Piper) into `data/narration/audition/` for the player to pick by ear; spoken text comes from `clips.spoken` | pick the voice for the player, synthesize audio in the sandbox, use a paid voice API, or let `data/narration/audition/` reach main |
| Recording a deck's clips in the chosen voice | write the pick to `data/reference/narration.json` (`engine`, `model`, `voice`, `speed`); **`narrate.yml`** records only the scenes with no take (content-hashed by **`narration.py`**: text + voice) into `data/narration/<stem>/` + its manifest, prunes stale takes, commits back. `narration.py --plan` shows what it would record | hand-place MP3s or edit a manifest; fail CI on a missing take (it is a note — the device voice covers it) |
| Buy list | `wishlist.py`, `<deck>.buylist.csv` | put an unowned card in the 99 |
| Proxies / export | `proxy_sheet.py`, `export_manapool.py` | |

## 4. VERIFICATION — delegate the bulk

| Situation | Tool |
|---|---|
| More than ~3 cards to verify | **`card-verifier`** agent (one batched `carddb.py --verify`) — *unless the session instructions forbid subagents, in which case queue them for `deck-verify.yml` instead* |
| Any full-pool scan | **`collection-auditor`** agent |
| A single card, inline | `carddb.py --verify "<name>"` |

## 5. NAMED ANTI-PATTERNS — every one of these actually happened

1. **Web search as the verification channel** while `deck-verify.yml` existed. Six PRs.
2. **A staples list used to measure archetype support.** Count the pool and the owned
   commander pages instead.
3. **`deck_stats.py` on an `.attrs.csv` deck** — silently wrong land count and curve.
4. **A scratch Python one-off where a CLI existed** (hand-rolled field-% ranking instead
   of `edhrec.py`).
5. **Accented names in reference data** — `mtglib._norm` does **not** fold accents, so
   `Bartolome` silently degraded 45 combo rows to "one piece away".
6. **A rule number quoted without retrieval.** If `rules.py` degrades, write *uncited*.
7. **A sim verdict accepted over a verified-text read without asking what the sim
   cannot see.** `goldfish.py` paid printed mana costs for months while the Ur-Dragon
   IS a cost reducer — three wrong verdicts in one day (2026-08-20) before the model
   learned eminence. When a simulation contradicts the card text, check the report's
   **assumptions block** first: the mechanism may simply not be modeled. The number is
   only as good as what the model covers, and the assumptions say what that is.

## 6. THE STANDING ORDER

Before reaching for WebSearch, a scratch script, or memory, ask: **does a row above cover
this?** If yes, use it. If a tool is missing, blocked or wrong, say so explicitly and name
the fallback you used — an honest degrade is fine, a silent one is not.
