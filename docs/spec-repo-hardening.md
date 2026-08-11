# Spec — Repo hardening & improvement roadmap

Status: ☑ ratified 2026-08-11 — from a full adversarially-verified review (37-agent sweep
across hubs, engines, network ring, webapp, tests, docs, data). Every Phase 1–3 item below
was CONFIRMED against the actual code/data before it entered this spec; nothing here is
speculative. Tick boxes as items land; this file is the tracker.

## Phase 1 — Safety (data loss / destructive-action bugs)

- [ ] **deck_sections.py silently deletes cards** (`deck_sections.py:41`). Its local `_QTY`
  regex accepts only `<digits> <name>`; `1x Name` and bare-name lines — both accepted by
  `mtglib.parse_deck` — fall through and are DISCARDED on `--apply`. Fix: parse section
  card lines with `mtglib._QTY_RE` + the bare-name qty=1 fallback, same as `parse_deck`.
  Test: a deck using both forms survives a regroup with quantities intact.
- [ ] **Snow-Covered basics are invisible to optimize.py** (`optimize.py:46`). `BASICS`
  holds six plain names; `mtglib._looks_like_land_by_name` also misses the `Snow-Covered `
  prefix. The spell pass can cut `Snow-Covered Island` (manabase destruction + N-copy
  line). Fix: route every basics check through `mtglib.is_basic()`, and teach
  `_looks_like_land_by_name` to strip the prefix. Test: snow basic on a name-only
  collection is never cut and counts as a basic in manabase pass 2.
- [ ] **Delete-deck confirm() never fires** (`webapp/templates/index.html:62`). A raw
  newline inside the single-quoted onsubmit string breaks the handler; the browser nulls
  it and the form submits unguarded — one click deletes the deck + companions. Fix:
  single-line the handler. Test: template contains no newline inside the onsubmit value.
- [ ] **pytest runs a real git sync** (`tests/test_auth.py:72`). `/sync` POSTs with
  `sync.run` unstubbed → real `sync_server.sh` (git add/commit/pull/push) on every run.
  Fix: stub `sync.run` in the auth tests. Test: the stub asserts it was called instead.

## Phase 2 — Data hygiene

- [ ] **cloud-ex-soldier.attrs.csv rows corrupt** (lines 47/50): `Godo, Bandit Warlord`
  and `Sram, Senior Edificer` written with unquoted commas → both parse as garbage. Fix:
  re-quote.
- [ ] **Stale buylist Replaces across four decks** (ur-dragon 17/27 rows, cosmic 9/14,
  cloud 5/8, yshtola 1). Also 9 ur-dragon rows recommend cards ALREADY owned and in the
  99 (satisfied — remove; the never-remove contract binds the optimizer, not a
  player-directed cleanup). Fix: drop satisfied rows; re-point stale Replaces at a
  current in-deck card via the optimizer's buy pairing where available, else blank the
  cell (blank = "no current mapping", honest).
- [ ] **data/wishlist.md references two deleted decks** — regenerate via `wishlist.py`.
- [ ] **handoff.md is layered/stale**: deleted First Avenger still listed with its own
  open item; Codsworth's recorded placement was the deleted deck (the card is now in NO
  deck — reopen the placement item); "snapshots predate the lands key" (now false);
  12-vs-8 spider counts; stale bracket table; Mana Drain/Smaug leftovers; stale
  Last-updated. Rewrite in place, current-state only.
- [ ] **codemap.md "Availability tiers"** still documents buys entering the 99 badged
  BUY. Update to the owned-only + buylist-Replaces contract.
- [ ] **SKILL.md scripts index** omits `goldfish.py` and `deck_sections.py`. Add.

## Phase 3 — Correctness cluster

**Front-face (` // `) blind spots** — same root cause, five sites; all must use
`mtglib.name_keys`/`front_face` semantics:
- [ ] `mtglib.classify()` curated lookup (`mtglib.py:590`) — joined names never match
  curated role lists (Murderous Rider // Swift End classifies as plain creature).
- [ ] `deckcore.advise_card()` in-deck set (`deckcore.py:460`) — can recommend a card
  already in the deck under its joined name.
- [ ] `deck_conflicts.scan()` (`deck_conflicts.py:52`) — aggregates by raw spelling, so
  the same physical card under two spellings splits into two "covered" entries.
- [ ] `optimize` `enriched_by_key` (`optimize.py:223`) — front-face deck line misses its
  own type data; `untyped` over-reports.
- [ ] `optimize` buy passes lack the add-side `name_keys` dedup the owned land pass has —
  a DFC buy can hit the buylist twice under two names.

**Webapp / infra**:
- [ ] Surface `singleton_violations` from the ⚡ Optimize and Build-Next-save routes
  (`app.py:874,888`) instead of discarding the report.
- [ ] `/refresh` wedges the hosted sync loop: it dirties git-tracked wishlist files that
  `sync_server.sh` never stages → `git pull --rebase` fails until manual cleanup. Fix:
  stage `data/wishlist.md` + `data/manapool-wishlist.txt` in sync_server.sh.
- [ ] `pa_wsgi.py` deploy notes claim "no env vars, no secret key" — following them
  deploys with auth OFF. Document `MTG_PASSWORD` in the stub.
- [ ] `_safe_next` (`app.py:122`) blocks `//host` but not `/\host` (browser-normalized
  open redirect). Normalize backslashes before the check.
- [ ] `spellbook.py` cache: unguarded `json.load` (crashes on corrupt cache — degrade
  contract violation) + non-atomic write. Guard read as cache-miss; write tmp+`os.replace`.
- [ ] `edhrec._fetch` + `save_snapshot`: non-atomic writes; corrupt-but-fresh cache
  pins snapshot-fallback for the full TTL. Guard read; write atomically (match
  carddb/rulings/rules/goldfish, which already do this right).

**Small confirmed items**:
- [ ] `refresh.py:77` IndexError when a child fails with whitespace-only stderr.
- [ ] `optimize` stale text: `--no-buys`/`--buy-threshold` help still say buys are
  "added"; dead `[BUY]` printer branch for swaps/land_swaps.
- [ ] `deckcore.BASIC_LAND_NAMES` missing `snow-covered wastes` (hubs disagree with
  `mtglib.is_basic`); same omission in `deck_conflicts.BASICS`.
- [ ] `carddb._index_keys` uses the banned naive `split("//")` — use `front_face`.
- [ ] `append_buylist` against a buylist lacking a `Replaces` column silently drops every
  mapping and is never idempotent. Add missing columns on write.

## Phase 4 — Improvement roadmap (future sessions; ranked)

1. [ ] **New-arrivals "place or dismiss" screen** (medium) — handoff open item 1;
   `deckcore.new_arrivals()` + `advise_card()` exist, only the screen is missing.
2. [ ] **Ownership-confirm flow for pending unowned deck cards** (small) — the eight
   cosmic-spider-man spiders; one-click confirm → `owned_additions.txt`.
3. [ ] **Buylist price estimates** (small) — fill `append_buylist`'s empty Price cells
   from the Scryfall data `carddb` already fetches (labeled estimates).
4. [ ] **Bracket-filtered field snapshots** (medium) — spec-engine-advisors §3 / handoff
   open item 2b; tune toward the player's actual Bracket-3 target.
5. [ ] **Goldfish A/B deltas in the card-panel Replace flow** (medium) — surface
   `simulate_ab` confidence intervals in the app.
6. [ ] **Buy-tab rows panel-clickable** (small) — known UI gap; reuse `.cardlink` markup.
7. [ ] **CSB one-away combos on saved-deck dashboards** (medium) — client exists, wire in.
8. [ ] **`--audit-flags` helper** (small) — closes the flag-recertification open item.
9. [ ] **Auto-resolve Unsorted sections after server enrichment** (small) — re-run
   deck_sections in the sync path once types land.
10. [ ] **Card-panel Rules tab** (medium) — rulings + curated trap notes.

Known-but-deferred (documented, not scheduled): PWA service-worker cache version is
hand-pinned (`sw.js` `mtgdb-v1`) so installed phones can hold stale assets; and
`/collection/upload` runs full enrichment synchronously in-request (host timeout risk) —
both need a deploy-side decision before code changes.
