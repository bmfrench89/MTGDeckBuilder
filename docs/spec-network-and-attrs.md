# Spec: Sandbox network unblocking + committed attrs snapshot

**Status: Phase 2 IMPLEMENTED 2026-08-12** (player approved §6.1 with the
Scryfall column dropped; awaiting the merge that gives the Action its first
run). **Phase 1 (§2, the environment allowlist) remains open** — it is the
player's flip and nothing in Phase 2 depends on it. Written 2026-08-12 from
the network review in session `ystola-deck-review`. This file is the live
tracker — tick boxes here, not in the handoff.

## 1. Why this exists

Two full audit sessions (2026-08-11) ran with Scryfall/EDHREC egress-blocked.
Everything still shipped, but the cost was real and recurring:

- Card-text verification ran through web-search snippets, 3–4 cards per query,
  instead of one `carddb.py --verify` batch. (~30 searches across the day.)
- `collection_attrs.csv` has **never existed in a sandbox session** — every
  deck showed "N cards have no type data", role counts under-read verified
  swaps until names were hand-curated into `mtglib.py`, goldfish/manabase ran
  at their honesty-gated fallback tier, and `auto_build` once read a mono-green
  commander as colorless.
- **Enrichment is upload-triggered only, never sync-triggered.** (This bullet
  originally claimed "nothing on the server re-enriches" — the 2026-08-12
  review proved that FALSE and the correction is the point: `/collection/upload`
  runs `carddb.enrich_api` inline, `webapp/app.py:1009`, documented as shipped
  in `docs/codemap.md:388`.) The real gap is narrower and still real: enrichment
  fires only when the player uploads a fresh export. A daily sync that pulls new
  code and deck edits never re-enriches, and **no non-server machine ever gets
  typed data at all** — a fresh clone and every sandbox session start name-only,
  which is exactly the degradation catalogued above.

**Decision recorded — MCP servers: NO.** Third-party Scryfall MCP servers
exist, but the egress block is a per-domain network-policy wall (verified:
`CONNECT tunnel failed, 403` for scryfall/edhrec from any process; github 200).
An MCP server in the same container hits the same wall, and even unblocked it
would be a second Scryfall client that returns text into chat and writes
nothing into the `collection_attrs.csv → oracle_flags → classify()` pipeline.
The repo's own rule stands: run the CLIs, don't reimplement them. Do not
relitigate this without new facts.

## 2. Phase 1 — environment allowlist (player action, no code)

Add to the Claude Code environment's network policy (Environment settings →
network; see code.claude.com/docs/en/claude-code-on-the-web):

- [ ] `api.scryfall.com` — `carddb.py` (enrich + `--verify`), `rulings.py`
- [ ] `json.edhrec.com` — `edhrec.py`'s only fetch host (`edhrec.py:23`).
      `edhrec.com` itself is optional: it appears solely as a commander-page
      link handed to the browser, which the server never follows
- [ ] `backend.commanderspellbook.com` — `spellbook.py` find-my-combos
- [ ] `magic.wizards.com` **and** `media.wizards.com` — `rules.py` (the CR
      landing page is on `magic.`; the linked `.txt` has historically been
      served from `media.` — allowlist both or the download dies halfway)

Explicitly NOT requested: `cards.scryfall.io` (card images are browser
hotlinks by design — the server must never fetch them), fonts, price sites.

Verification once flipped (Opus, one session):
- [ ] `python3 scripts/carddb.py --verify "Sol Ring"` → verbatim oracle text
- [ ] `python3 scripts/rules.py 903.1 --refresh` → real CR, cited answer
- [ ] `python3 scripts/rulings.py "Sol Ring"` → live rulings
- [ ] `python3 scripts/edhrec.py` fetch for one commander → `source: live`
- [ ] Also allowlist the Scryfall **bulk CDN host** if `--download-bulk` is
      ever wanted: `carddb.py:84-92` fetches `entry["download_uri"]`, a host
      returned at runtime that appears in no source literal. Resolve it at
      flip time with
      `python3 -c "import urllib.request,json;print(json.loads(urllib.request.urlopen('https://api.scryfall.com/bulk-data').read())['data'][0]['download_uri'])"`.
      Not needed for the API path the Action uses.
- [ ] Then update the "PC-only" claims. The original list here was incomplete
      and misdescribed one file; the verified file:line list is: `CLAUDE.md:129`
      and `:148-149`; `scripts/rules.py:28`;
      `.claude/skills/mtg-deckbuilder/SKILL.md:259`;
      `references/rules-reference.md:33`;
      `references/tooling-and-data.md:1-3,15-16,48` (which contains no
      "player's PC" string at all — its stale claims are about sandbox
      blocking); `docs/codemap.md:126-138`, the deployment matrix at
      `:141-151`, and `:226`; `docs/handoff.md:303`. The degrade paths STAY
      (other sandboxes exist); only the "player's PC only" phrasing changes.

## 3. Phase 2 — attrs snapshot via GitHub Action (the real prize)

### Design

Same delivery pattern as `field-snapshots.yml`: GitHub runners have open
egress (proven live 2026-08-10 by `recertify.yml`: Scryfall + wizards.com both
reached); results arrive via git.

- New workflow `.github/workflows/attrs-snapshot.yml`:
  - Triggers: weekly cron + push on `data/collection/collection_snapshot.txt`
    + `workflow_dispatch`. Concurrency-grouped like field-snapshots.
  - Runs `carddb.py` with the **committed name-only snapshot** as the
    collection input (verified: `detect_format` reads it as a namelist and
    `enrich_api` needs only names) and `--out` pointed at the snapshot path.
    ~2,622 names ≈ ~35 batched `/cards/collection` POSTs — trivial load, keep
    the client's existing politeness delay.
  - Commits only on diff, as `attrs-snapshot-bot`; red only on total failure.
  - **`concurrency: {group: field-snapshots, cancel-in-progress: false}` —
    deliberately SHARING field-snapshots' group name.** Groups are repo-scoped
    strings, so sharing serializes attrs-vs-attrs *and* attrs-vs-field in one
    line. Its own private group would only fix the first. Red-team reproduced
    the failure this prevents: two concurrent runs rewriting the same CSV
    either conflict on rebase, or — worse — line-merge into a hybrid file
    containing rows from two different runs that no guard ever validated.
  - **The guard must be BUILT, not inherited, and the first draft of it here
    was wrong twice over** (2026-08-12 red team). `field-snapshots.yml` can use
    a bare commit-if-diff because its guard lives in Python
    (`edhrec.save_snapshot` refuses non-live data). `carddb` has no equivalent.
    The originally specced guard — new row count vs the checked-out file, ~90%
    floor — fails both ways: it **permanently blocks a legitimate shrink**
    (sell half the collection, regenerate the snapshot, and every future run
    is refused because it compares against history), and it **misses the
    failure it was written for** (the 2026-08-12 stub had a perfect row count).
    Correct guard: **resolution rate against the run's own input, never
    against history.** Add `--min-match PCT` to `carddb.py` and fail the run
    when `matched / total` falls below it (~95). `carddb.py:334` already
    returns `(len(resolved), len(coll), unmatched)` — the number is computed
    and currently thrown away. Keep the §6a plausibility check too (the stub
    would have passed a rate check as well, since it "resolved" everything).
  - Guard placement: the rate check runs pre-commit, but a rebase can change
    what actually lands. Either re-assert on the post-rebase file before
    pushing, or regenerate after checkout so no merge is possible.
  - Push retry: `for i in 1 2 3 4 5; do git pull --rebase origin main && git
    push origin main && exit 0; sleep $((3*i)); done` then fail loudly.
    `field-snapshots.yml:68-71` has no retry today and goes red on a lost
    race — see §8.
  - **Absolute floor, not just a rate.** "A total network failure is already
    safe" is true but the hazard needed renaming twice: `_post_collection`
    raises on `URLError` AND on 429/503 exhaustion (the implementation review
    proved the old `return [], []` at the loop's end was dead code — it is now
    an explicit assertion). The REAL header-only hazard is **mass `not_found`
    on a clean 200** — unresolvable names written short with exit 0. So
    require BOTH: the resolution rate above, AND a hard floor of
    more than one data row — which also covers the very first run, when there
    is no checked-out file to compare against. Fail red; never skip silently.
  - Do **not** copy `field-snapshots.yml:44-58`'s `set +e` / `exit 0` wrapper.
    That exists because a partial EDHREC fetch is still worth committing;
    here it would swallow `carddb`'s non-zero exit — the one signal that
    something went wrong.

### The wedge hazard, and why the file gets a NEW name

`data/collection/collection_attrs.csv` stays **gitignored and server-local**.
Committing that exact path would recreate a documented failure:
`sync_server.sh` stages only its five `TRACKED_DATA` paths
(`sync_server.sh:28-34`), and its header comment records that a dirty tracked
file outside that list once *wedged the daily `git pull --rebase`*. Since the
2026-08-11 self-heal (`sync_server.sh:59-77`) the symptom is **worse, not
gone**: a failed pull now parks local state on a rescue branch and
`git reset --hard`s to upstream — so a tracked `collection_attrs.csv`, rewritten
server-side by every `/collection/upload`, would have the server's fresh
enrichment silently discarded on each sync and spawn rescue-branch churn
forever. Same conclusion, sharper teeth: a committed attrs file must be a path
**no runtime ever writes**:

- [x] Action writes `data/collection/collection_attrs.snapshot.csv`
      (committed; **8 columns — `ATTRS_HEADER` minus `Scryfall`**, dropped per
      the privacy mitigation via `--no-ids`; name-based enrichment).
      `.github/workflows/attrs-snapshot.yml`, landed 2026-08-12. Committable once the TEMPORARY
      `.gitignore` line for this exact path is removed — added 2026-08-12
      after the stub incident (§6a), and removing it is the Action's first
      step. The permanent ignore at line 26 pins only the private
      `collection_attrs.csv` and does not catch the snapshot path.
- [x] **No `carddb.py` change needed** — `--out` already exists
      (`carddb.py:558`, resolved at `:589`) and both `enrich()` and
      `enrich_api()` take an out path. The Action just passes
      `--out data/collection/collection_attrs.snapshot.csv`, leaving the
      private file's default untouched.
- [x] (landed in PR #109) `mtglib.load_collection` **layers** both files rather than choosing:
      overlay `collection_attrs.snapshot.csv` first when present, then the
      private sibling `collection_attrs.csv` on top. `overlay_attrs` applies
      per-column and keys `Produced`/`Flags` off column presence
      (`mtglib.py:346-353`), so the sibling still wins wherever it speaks —
      and a sibling written before enrichment learned those columns (the
      handoff records the player's real file is exactly that old 7-column
      shape) no longer erases the snapshot's production data. Insert at
      `mtglib.py:373`, after the `owned_additions` merge, so merge order and
      the empty-vs-absent contract are untouched.

### Prerequisites in `carddb.py` — land these BEFORE the Action

Both found by the 2026-08-12 red team; both would put **wrong data in git** on
the first green run, and neither is visible in the output (exit 0 either way).

- [x] (fixed 2026-08-12, `tests/test_carddb_enrich.py`) **`enrich_api` silently drops unresolvable names.** `carddb.py:313` binds
      Scryfall's `not_found` list as `_nf` and never reads it; `:329-332` emits
      no row for a miss — omitted, not blank. The fuzzy retry that would catch
      apostrophe/em-dash/Universes-Beyond naming variants exists only in
      `--verify`. On a collection full of post-2025 Marvel/Hobbit/Avatar names
      this drops exactly the cards the project most needs typed. Fix: share the
      fuzzy retry (`_fetch_named_fuzzy`, `carddb.py:441-450`) after round 2,
      and stop discarding `_nf` so the count feeds `--min-match`.
      **Unattended-fuzzy guard (2026-08-12 revalidation):** `--verify` labels a
      fuzzy hit `"fuzzy"` so a HUMAN judges it (`carddb.py:514`); the Action has
      no human, and a fuzzy match can land on a different card entirely (the
      warning `rulings.py` already carries). In `enrich_api`, accept a fuzzy hit
      only when the resolved name normalizes to the queried name —
      `_norm(front_face(hit)) == _norm(front_face(queried))` — i.e. fuzzy may
      repair punctuation/diacritics/casing, never substitute a card. A hit that
      fails the check counts as unmatched (feeds `--min-match`, listed on
      stderr) rather than silently enriching the wrong card into git.
- [x] (fixed 2026-08-12, one line + test) **Faces-only cards enrich with EMPTY Sub-types.** `carddb.py:280`
      computes a `card_faces` fallback for `type_line` (added after
      `Scavenger Regent // Exude Toxin` enriched with an empty Type) but
      `:290-291` passes the RAW object to `subtypes_of`, so adventure/omen/DFC
      cards land with no subtypes. `overlay_attrs` only writes non-empty cells,
      so they stay `[]` — and subtypes are what tribal detection reads
      (`analyze_collection --subtype Dragon`, `deck_fit`, `auto_build`). For a
      dragon-tribal deck in this collection that is not academic. Fix is one
      line: pass the already-computed `type_line` local. Add the hermetic test.

### Consumers that must learn about the new file

- [x] (fixed 2026-08-12 + invalidation test) `goldfish.cache_key` (`goldfish.py:719-726`) stats only
      `collection_attrs.csv`, so the snapshot's arrival does **not** invalidate
      the goldfish disk cache — the server would keep serving
      identity-approximation simulations, labelled as if enriched, until some
      other input changed. Add a `_stat` on the snapshot path; extend
      `test_goldfish`'s invalidation set.
- [x] (fixed 2026-08-12 + two tile tests; the tile now names its source)
      `/collection`'s enrichment tile (`webapp/app.py:965-976`) keys "on" off
      the private file's existence alone, so a fresh clone served by the
      snapshot shows enrichment OFF beside a 2,621/2,621 coverage count. A
      session reading that concludes enrichment is unavailable and starts
      hand-curating names — the exact waste §1 catalogues. Make `on` reflect
      either source, ideally naming which.

### PRIVACY: the guarantee is conditional, and must be enforced

**The "strictly less revealing" argument in §6.1 was wrong as originally
written, and the owner's sign-off was given on it.** It is not the name-only
*input* that keeps the player's printings out of the file — it is the *absence
of the private sibling*. Mechanism, verified end to end by the 2026-08-12 red
team:

`load_collection` overlays `collection_attrs.csv` onto **any** collection path
in that directory, including `collection_snapshot.txt` (`mtglib.py:373-376`);
that overlay sets `card.scryfall_id` (`:344-345`); `_best_identifier` then
submits `{"id": sid}` in preference to `{"name": …}` (`carddb.py:245-247`); and
`carddb.py:292` writes that id straight into the output row. So **anyone who
runs the Action's own command on a machine that has the private file — the
server, the player's PC, or a session copy-pasting it to test — produces a file
naming the exact printing of every card owned** (set + collector number). That
is strictly MORE revealing than the committed name list, not less.

On a GitHub runner the private file does not exist, so the property holds — but
by accident of environment, which is not a guarantee. Enforce it:

- [x] (in the YAML + locked by the workflow text-test) The workflow asserts the sibling is absent before enriching:
      `test ! -f data/collection/collection_attrs.csv || { echo '::error::private attrs sibling present — refusing to enrich'; exit 1; }`
- [x] (DONE — `--no-ids`, player-approved 2026-08-12) **Dropped the `Scryfall`
      column from the snapshot file entirely.** Nothing in the analysis pipeline consumes it; the private
      sibling still supplies exact ids on the machines that have it; and
      card images are browser hotlinks that fall back to a self-correcting
      by-name URL. Removing the column makes the privacy property
      unconditional instead of enforced-by-guard — the strictly safer design.
- [x] (landed in PR #109) Extend `tests/test_collection_produced.py:111`
      (`test_upload_never_writes_the_tracked_snapshot`) to also assert
      `/collection/upload` never writes `collection_attrs.snapshot.csv`, and
      rename it to cover every tracked collection path.

### Known, accepted limitation

Everything the analysis pipeline consumes is printing-invariant, confirmed
column by column against `carddb.py:271-294`: MV from `cmc`, Colors from
`color_identity`, Cost from `mana_cost`, Type from `type_line`, Produced and
Flags from `oracle_flags`. **The one genuinely printing-dependent column is
`Scryfall`** — see the privacy section above, which is the stronger reason to
drop it. (Sub-types is invariant too, but is currently *wrong* for faces-only
cards — see the prerequisite blockers.)

### Tests (offline, hermetic, as always)

- [ ] `test_mtglib`: snapshot-attrs layering — snapshot alone enriches;
      sibling alone unchanged from today; **both present → sibling wins
      per-column BUT a 7-column sibling keeps the snapshot's Produced/Flags**
      (the regression the layering exists to prevent); neither →
      `produced is None` degraded path intact (all in `tmp_path`).
- [ ] **There IS a workflow test harness — this spec previously said there
      wasn't.** `tests/test_card_flow.py:396-409`
      (`test_snapshot_workflow_matches_the_cli_it_drives`) reads
      `field-snapshots.yml` as text and asserts it drives the name-only
      snapshot and nothing private. Copy it: add
      `test_attrs_snapshot_workflow_is_name_only` asserting the new workflow
      contains `collection_snapshot.txt`, does **not** contain the string
      `collection.csv`, contains the `--out` snapshot path, the sibling-absence
      check, the row floor, and `contents: write`. **This is the cheapest
      available lock on the privacy guarantee** — it fails the suite if anyone
      ever points the Action at the private CSV.
- [ ] `goldfish.cache_key` invalidation case (see consumers above).
- [ ] CI stdlib-only import check must still pass — no new imports.
- [x] **CI verified safe, 2026-08-12:** a realistic 2,622-row file was placed
      at the new path and the FULL suite run — green; no test globs
      `data/collection/`. (The only ignore matching the path is the TEMPORARY
      line from §6a, removed when the Action lands.)
      *Unresolved oddity, logged not diagnosed:* in 2 of 4 runs the planted
      file was gone after pytest finished, unreproducible under bisection.
      Before merging, place the real file, run pytest three times, and `ls`
      after each; if it vanishes, bisect with `-p no:cacheprovider` and
      `strace -e trace=unlink,unlinkat`. Do not assume it is benign.

### Follow-on effects to verify after first green run

- [ ] Fresh-clone `deck_stats` shows near-zero "no type data" cards; the
      "untyped" count in optimizer output drops accordingly.
- [ ] Goldfish/manabase surfaces move from the honesty-gate tier to real
      numbers on a fresh clone (labels should say enriched, not "identity
      approx." — except for cards the snapshot lookup missed, which must
      still degrade honestly).
- [ ] Open item 5.2 (the ~30-card flag audit) gets MORE load-bearing once
      flags ship to every session — schedule it on the player's next PC day.
- [ ] Re-verify the four UNVERIFIED Marvel texts from the 2026-08-11 audits
      (`Pet Avengers` creature types above all — dragon-density claims lean
      on it).

## 4. Phase 3 — nice-to-haves unlocked (do not start before 1–2 land)

- Bracket-filtered field snapshots (existing open item 2b) — same Action
  pattern, now with the allowlist making local experiments possible too.
- A **sync-cadence** enrich hook (upload-time already exists — see §1):
  smallest honest version is `sync_server.sh` running carddb against the
  private CSV after a successful pull, output staying gitignored-local.
  Decide only after the snapshot attrs prove out — it may be unnecessary,
  since new cards reach the server via upload anyway.

## 5. Acceptance

Phase 1: all five §2 verification boxes green in one sandbox session.
Phase 2: Action green on a manual dispatch; a fresh `git clone` +
`deck_stats.py` on any deck reports full type coverage with zero network; full
pytest suite green; the six decks' role counts match the server's within
curated-list differences.

## 6. Player decisions required before implementation

1. **Commit derived card attributes?** — **APPROVED 2026-08-12, but the basis
   was partly wrong and needs re-confirming.** As pitched: the file holds
   Name/Type/MV/Colors/Cost/Sub-types/Scryfall-id/Produced/Flags for names
   already public in `collection_snapshot.txt`; no prices, quantities or
   dates; "strictly less revealing than the snapshot it derives from."
   **That last clause does not hold unconditionally** — see the PRIVACY
   subsection in §3. The `Scryfall` id column can carry the player's exact
   printings whenever the file is generated on a machine holding the private
   sibling, which is every machine except a clean CI runner. The approval
   stands for the file as it will actually ship *if* the recommended
   mitigation lands (drop the `Scryfall` column, plus the workflow's
   sibling-absence guard); if the column is kept, the owner should
   re-confirm knowing it can encode which physical printings are owned.
2. **Flip the allowlist?** Phase 1 is entirely yours — sessions cannot change
   an environment's network policy. *(Still open as of 2026-08-12 — the Action
   does not need it; runners have open egress.)*

Say yes to both and Phase 2 lands in one session — **smaller than first
scoped**: workflow YAML (with the row-count guard) + the loader layering +
tests. No `carddb.py` change at all.

**Splittable if decision 1 is a "not yet":** the loader layering and its tests
are safe and inert on their own (they read a file that simply won't exist), so
they can land immediately; only the workflow — the thing that actually
publishes derived collection data — waits on the privacy ruling.

## 6a. Incident, 2026-08-12 — read this before implementing

While the loader half was landing, a stub `collection_attrs.snapshot.csv` (2,621
identical rows: `Creature / MV 3 / G / {2}{G} / Elf / deadbeef`, generated by a
review subagent probing loader behaviour) was committed and pushed via
`git add -A`, then reverted in `1a046e4`. Two lessons the implementer inherits:

1. **`git add -A` is banned in this repo** — `sync_server.sh` says so in a
   comment and this is now the second incident it predicted. Stage explicit
   paths.
2. **A malformed attrs file fails LOUDLY WRONG, not safely absent.** Because
   the snapshot overlays first, garbage in it silently overrode reality on
   exactly the machines the file exists to help. Measured: the-ur-dragon read
   as curve `{'3': 100}` — all 100 cards at MV 3 — with the `land` category
   absent entirely, i.e. a 21-land deck reporting zero lands. Nothing warned;
   the honesty labels fire when data is *missing*, never when it is *wrong*
   (the known trap in CLAUDE.md, now demonstrated).

Implementation consequences:
- [x] The Action is the **only** writer of this path (temporary gitignore
      removed with the Action's landing, 2026-08-12).
- [x] (DONE with the Action) **FIRST STEP of implementing the Action: delete the temporary
      `data/collection/collection_attrs.snapshot.csv` line from `.gitignore`**
      (added 2026-08-12 with a matching comment). It is there because the stub
      kept regenerating as subagent scratch output; leaving it in place would
      make the Action's commit step silently no-op, which is a worse failure
      than the one it prevents. The `.gitignore` comment says the same thing —
      both must be removed together.
- [x] (both live in the YAML: `--min-match 95` + the Type-spread gate)
      The row-count guard (§3) is necessary but **not sufficient** — the stub
      had a perfect row count. Add a plausibility check the Action must pass
      before committing: e.g. the file must show a spread of `Type` values
      (a real collection is never >90% one type) and more than a handful of
      distinct `Scryfall` ids. Cheap, and it catches exactly this.

## 7. Review status

- **Grounding lane (2026-08-12): COMPLETE**, findings folded in above. It
  killed the original §1 headline claim (server enrichment DOES exist, on
  upload), found `carddb --out` already shipped, proved the shrinkage guard
  was inherited-by-assumption rather than real, re-dated the wedge hazard to
  the post-self-heal data-destruction symptom, and upgraded the loader from
  either/or to layering. Every finding was re-verified by hand before edit.
- **Red-team lanes A (races) + B (data correctness): COMPLETE 2026-08-12**,
  rerun after the first attempt was interrupted. Findings folded into §3, §6a
  and the new §8. They reproduced their claims with real git repos and
  monkeypatched network calls rather than reasoning about them, which is why
  §8 exists at all.
  - **CLEARED, so nobody re-investigates:** `overlay_attrs` cannot conjure
    phantom cards from a stale snapshot — it is match-only (`mtglib.py:328-330`,
    verified empirically). The reverse direction degrades honestly. A total
    network failure leaves the previous out file untouched. The new path is
    genuinely committable. `owned_additions.txt` is tracked and sits beside the
    snapshot so the runner merges it — **zero cards are stranded today** (its
    one entry is already in the snapshot).
  - **Killed my own guard design:** the row-count-vs-history floor was wrong in
    both directions. Replaced with a resolution-rate check against the run's
    own input (§3).
- **Lane C (privacy / CI / allowlist): COMPLETE 2026-08-12.** It answered its
  own headline question in the worst way: the `Scryfall` id column CAN encode
  the player's exact printings, and the privacy argument §6.1 was approved on
  is conditional rather than absolute (§3 PRIVACY). It also found the
  header-only-file hazard the guard now covers, corrected this spec's claim
  that no workflow test harness exists (one does, and it is the cheapest lock
  on the privacy property), listed the real file:line set for the PC-only doc
  sweep, and CLEARED CI — full suite green with a realistic 2,622-row file
  present, no test globs `data/collection/`.
- **All three lanes are now in.** Nothing in this spec is unexamined; the
  open items are decisions and implementation, not unknowns. The one loose
  thread is the unreproducible vanishing-file observation recorded in §3
  Tests — logged deliberately as an oddity rather than dressed up as a defect
  or quietly dropped.

### Implementation review (2026-08-12, two lanes over the full diff)

No blockers. Every priority behavior was mutation-checked by the reviewers —
each reverted in a scratch copy and caught by its test — the YAML's shell was
executed step by step in checkout@v4-faithful throwaway repos (regenerate-
retry loop walked through win/loss/five-loss branches; plausibility gate
refused the stub signature verbatim), and the planted-snapshot vanishing-file
oddity from §3 Tests resolved: four full-suite runs, file present after each.
Its three FIX findings are folded in: the workflow text-test now asserts
against comment-stripped code (its flag checks were mutation-proven satisfiable
by comments), the no-network tripwire now traps the fuzzy layer (whose bare
except swallowed the booby-trap), and this tracker's boxes are ticked. Accepted
NOTEs, implemented: fetch-leg guard in the retry loop, the pending-supersede
concurrency comment, bulk-path flag refusal (`--no-ids`/`--min-match` are
API-only and now error instead of silently no-opping), the lock-contention
skip no longer consumes the sync TTL, subprocess timeout widened to 420s, tile
tests added. Accepted NOTEs, documented only: the shared concurrency group can
supersede a pending attrs run (grey, not red — waits for its next trigger).

### First live run (2026-08-12): PASSED, all guards green

Run #1 (workflow_dispatch, 90s): privacy assert passed; **2,604/2,621 resolved
(99%)** over the 95% floor; the guarded fuzzy repaired 20 split-card names with
zero substitutions; plausibility reported 7 types, top Creature 49%; committed
and pushed first attempt (`5fe3a16`). The 17 unmatched are all full
"Front // Back" names that even fuzzy rejects — they degrade honestly (deck
lookups still resolve via front-face indexing). Follow-up for a future pass:
retry split-name misses by their FRONT FACE via the same guarded fuzzy — the
fold already compares front faces, so it stays substitution-proof. Downstream
effects verified in-sandbox: zero "no type data" warnings, typed power scores
(yshtola 78), oracle flags agreeing with every overlapping hand-curated role
and contradicting none. One NEW issue was exposed and filed in
`docs/spec-optimizer-hardening.md`: typed data armed the archetype-blind role
template and the repair pass churns against field-superior incumbents — do not
run the optimizer with `--apply`/⚡ until that lands.

## 8. Pre-existing bugs the red team surfaced (NOT caused by this spec)

These are live in `main` today and were found while tracing what a third
committer would collide with. They are listed here because this spec's Action
makes several of them **more likely to fire**, but every one can and should be
fixed independently — and #1 is a data-loss bug that deserves fixing before
anything in this spec ships.

1. ~~**`sync_server.sh`'s rescue self-heal destroys uncommitted work.**~~
   **FIXED 2026-08-12** — stash-around-the-pull + re-fetch before trusting
   `@{u}` + refuse-to-self-heal-when-dirty. Reproduced first in a scratch-repo
   harness (both cases unrecoverable), then re-run after the fix: the tracked
   case is preserved in the working tree, the untracked case lands safely in a
   stash with a warning, and the two regression cases (the self-heal's original
   job, and the clean happy path) still pass. Original diagnosis retained
   below for context.

   **`sync_server.sh`'s rescue self-heal destroys uncommitted work, and its
   safety comment is inverted.** `:64-66` claims "the push comes first — local
   edits are provably on GitHub before a single byte is discarded." True for
   *committed* edits. `git branch -f` (`:68`) captures HEAD only, so anything
   in the working tree is **not** on the rescue branch when `:70` runs
   `git reset --hard`. Concrete loss: the player saves a deck in the web app
   during the seconds the sync spends in `git pull --rebase`; that unstaged
   change to a tracked file makes the pull fail `128` — and the red team
   confirmed the fetch never happens in that mode, so `@{u}` is *stale* too.
   The self-heal then parks a rescue branch that does not contain the save and
   hard-resets over it. Fix: refuse to self-heal when `git status --porcelain`
   is non-empty (fall back to the honest abort already at `:73-76`), and/or
   stash before the pull; re-fetch before trusting `@{u}`.
2. ~~**No push retry in `sync_server.sh`.**~~ **FIXED 2026-08-12** (bounded rebase-and-retry; test-locked). Original: A lost race costs a full
   day of sync AND leaves the app serving stale code, because the pull already
   succeeded but the WSGI touch never runs. Bounded rebase-and-retry.
3. ~~**No cross-process lock on the sync.**~~ **FIXED 2026-08-12** (flock on gitignored data/cache/sync.lock; skip no longer consumes the TTL). Original: `webapp/sync.py:28`'s lock is
   per-process by its own comment, and `maybe_start` is a check-then-act on a
   status file. A console run during the auto-sync interleaves two
   `add`/`commit`/`pull --rebase`/`reset --hard` sequences in one working tree.
   `flock` at the top of `sync_server.sh`; `data/cache/` is already gitignored.
4. ~~**`field-snapshots.yml` has no push retry either**~~ **FIXED 2026-08-12** (same bounded retry; its spec's failure table corrected). Original: — one attempt, red
   on a non-fast-forward, and nothing retries for 7 days. Its own spec
   (`docs/spec-field-snapshot-action.md:88`) claims a mid-run deck sync is
   harmless; the rebase closes the *conflict* window, not the *push* window.
5. **First landing of the snapshot file breaks any clone holding an untracked
   file at that path** *(mitigated: the server now stashes untracked state
   around the pull; sandbox clones should not keep scratch at that path)* — `git pull` refuses to overwrite it, which on the
   server escalates into the self-heal above. Note: this already happened in
   this session (§6a). Land the first commit via a normal PR, and have the
   sync handle dirty/untracked state explicitly.

