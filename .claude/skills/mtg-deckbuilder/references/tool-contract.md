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
| Fresh EDHREC field data | same push — `deck-verify.yml` also snapshots every commander in `data/decks/` | hand-roll a field analysis, or call a deck "unsupported" on stale data |
| Enrich the whole collection | **`attrs-snapshot.yml`** (weekly + on snapshot change) | commit a hand-built attrs file |
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
| "is archetype X supported?" | `analyze_collection.py` **+ `commanders.csv` + `data/reference/field/*.json`** | measure against a staples list. This produced a wrong "treasures unsupported" verdict while the player owned **Smaug, Wicked Worm ×2** |
| "what infinite can I assemble today?" | `combo_detector.py --collection-combos` | reason about combos from memory |
| "which decks share cards?" / what is free | `deck_conflicts.py [--available]` | assume a card is uncommitted |
| "what does the field run that I lack?" | `edhrec.py` | guess at inclusion rates |
| "what should I build next?" | `commander_finder.py`, `similar_commanders.py` | |

## 3. DECKS — the build loop is a pipeline, not a vibe

**`auto_build.py` → `deck_sections.py` → `optimize.py --apply` → validate.** Run it in that
order every time. It assembled a tuned 100-card Smaug deck in one command after a session
had spent its effort hand-reasoning.

| Job | Tool | NEVER |
|---|---|---|
| Assemble a 99 | `auto_build.py` | hand-pick 99 cards |
| Regroup into type sections | `deck_sections.py` | hand-edit section headers |
| Tune against the field | `optimize.py --apply` — **mandatory after any build or rebuild** | ship an untuned deck |
| Full deck analytics | **`deckcore.analyze_deck()`** | `deck_stats.py` on a deck with an `.attrs.csv` — it does **not** read the companion and reports 31 lands / empty curve where the hub reports 37 / real |
| Mana math | `manabase.py` | hypergeometrics by hand |
| Sequenced play, mulligans, A/B a swap | `goldfish.py` | assert a swap is better without replaying it |
| Power / bracket | `power.py` | assign a bracket by feel |
| Combos present or one-away | `combo_detector.py` | |
| Dashboard | `build_dashboard.py`, or `refresh.py` for all | hand-write HTML |
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
