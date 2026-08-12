# Spec: Sandbox network unblocking + committed attrs snapshot

**Status: DRAFT — awaiting player ratification of the two decisions in §6.**
Written 2026-08-12 from the network review in session `ystola-deck-review`
(PR #107/#108 era). Implementer: a future session ("Opus"). This file is the
live tracker — tick boxes here, not in the handoff.

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
- [ ] Then update the "PC-only" claims: CLAUDE.md (rules.py line in "The PC is
      out of the loop" + Commands comment), `scripts/rules.py` docstring,
      `.claude/skills/mtg-deckbuilder/SKILL.md` + `references/rules-reference.md`
      and `references/tooling-and-data.md` — the degrade paths STAY (other
      sandboxes exist); only the "player's PC only" phrasing changes to
      "any environment whose policy allows wizards.com".

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
  - **The shrinkage guard must be BUILT, not inherited** (2026-08-12 review
    finding). `field-snapshots.yml` can rely on a bare commit-if-diff because
    its guard lives in Python — `edhrec.save_snapshot` refuses to write
    non-live data (`edhrec.py:200-206`). `carddb` has **no equivalent**: a run
    where Scryfall is reachable but many names fail to resolve writes a short
    file and exits 0, which a copied YAML would cheerfully commit over a good
    one. Implement explicitly: compare the new file's row count against the
    checked-out version and refuse to commit below ~90%, failing the run
    instead. (A total network failure is already safe — `enrich_api` raises
    before the out file is opened, so the previous file survives untouched.)

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

- [ ] Action writes `data/collection/collection_attrs.snapshot.csv`
      (committed; same `ATTRS_HEADER` columns — verified as exactly the 9 in
      `carddb.py:57`; name-based enrichment). Verified committable: no
      `.gitignore` pattern catches the new path (line 26 pins the exact
      `collection_attrs.csv` string).
- [x] **No `carddb.py` change needed** — `--out` already exists
      (`carddb.py:558`, resolved at `:589`) and both `enrich()` and
      `enrich_api()` take an out path. The Action just passes
      `--out data/collection/collection_attrs.snapshot.csv`, leaving the
      private file's default untouched.
- [ ] `mtglib.load_collection` **layers** both files rather than choosing:
      overlay `collection_attrs.snapshot.csv` first when present, then the
      private sibling `collection_attrs.csv` on top. `overlay_attrs` applies
      per-column and keys `Produced`/`Flags` off column presence
      (`mtglib.py:346-353`), so the sibling still wins wherever it speaks —
      and a sibling written before enrichment learned those columns (the
      handoff records the player's real file is exactly that old 7-column
      shape) no longer erases the snapshot's production data. Insert at
      `mtglib.py:373`, after the `owned_additions` merge, so merge order and
      the empty-vs-absent contract are untouched.

### Known, accepted limitation

Name-based enrichment resolves *a* printing, not the player's printing:
`Scryfall` ids (→ card-image hotlinks) may show a different frame than the
owned copy. Type/MV/Colors/Cost/Sub-types/Produced/Flags — everything the
analysis pipeline consumes — are printing-independent (rare exceptions like
alt-frame subtypes are noise). The private sibling file still wins wherever it
exists, so the server/PC keep exact printings.

### Tests (offline, hermetic, as always)

- [ ] `test_mtglib`: snapshot-attrs layering — snapshot alone enriches;
      sibling alone unchanged from today; **both present → sibling wins
      per-column BUT a 7-column sibling keeps the snapshot's Produced/Flags**
      (the regression the layering exists to prevent); neither →
      `produced is None` degraded path intact (all in `tmp_path`).
- [ ] `test_agents`-style guard not needed; workflow YAML gets the same
      light-touch review as field-snapshots (no test harness for Actions).
- [ ] CI stdlib-only import check must still pass — no new imports.

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

1. **Commit derived card attributes?** `collection_attrs.snapshot.csv` holds
   Name/Type/MV/Colors/Cost/Sub-types/Scryfall-id/Produced/Flags for names
   already public in `collection_snapshot.txt`. No prices, no quantities, no
   acquisition dates. Strictly less revealing than the snapshot it derives
   from — but it is a new committed file derived from collection data, so the
   privacy hard-line owner (you) signs off, not a session.
2. **Flip the allowlist?** Phase 1 is entirely yours — sessions cannot change
   an environment's network policy.

Say yes to both and Phase 2 lands in one session — **smaller than first
scoped**: workflow YAML (with the row-count guard) + the loader layering +
tests. No `carddb.py` change at all.

**Splittable if decision 1 is a "not yet":** the loader layering and its tests
are safe and inert on their own (they read a file that simply won't exist), so
they can land immediately; only the workflow — the thing that actually
publishes derived collection data — waits on the privacy ruling.

## 7. Review status

- **Grounding lane (2026-08-12): COMPLETE**, findings folded in above. It
  killed the original §1 headline claim (server enrichment DOES exist, on
  upload), found `carddb --out` already shipped, proved the shrinkage guard
  was inherited-by-assumption rather than real, re-dated the wedge hazard to
  the post-self-heal data-destruction symptom, and upgraded the loader from
  either/or to layering. Every finding was re-verified by hand before edit.
- **Red-team lane: INTERRUPTED, never returned.** Still unexamined, and worth
  a rerun before or during implementation: commit races between the three bots
  that push to `main` (field-snapshots, attrs-snapshot, the server sync);
  whether `overlay_attrs` on a stale snapshot can conjure phantom cards or
  merely skips unknown names; `carddb`'s handling of names Scryfall cannot
  resolve (Marvel/Hobbit oddities, `owned_additions` entries); and an
  adversarial read of whether any `ATTRS_HEADER` column leaks more than the
  already-committed name list.
