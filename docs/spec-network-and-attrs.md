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
- A checked assumption died during review: **nothing on the hosted server
  re-enriches.** `grep` finds no `carddb` invocation in `webapp/`,
  `sync_server.sh`, or any workflow. CLAUDE.md's automation-loop line "the
  server re-enriches" is aspirational — enrichment only ever happened via
  `enrich.bat` on the player's PC. The PC is supposed to be out of the loop;
  today it is the loop.

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
- [ ] `json.edhrec.com` **and** `edhrec.com` — `edhrec.py` live fetch
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
    collection input and an explicit out path (see below). ~2,600 unique names
    ≈ ~35 batched `/cards/collection` POSTs — trivial load, keep the client's
    existing politeness delay.
  - Commits only on diff, as `attrs-snapshot-bot`; a partial failure keeps the
    previous good file (never commit a shrunken file over a full one — same
    guard philosophy as `edhrec.save_snapshot`); red only on total failure.

### The wedge hazard, and why the file gets a NEW name

`data/collection/collection_attrs.csv` stays **gitignored and server-local**.
Committing that exact path would recreate a documented failure:
`sync_server.sh` stages only its five `TRACKED_DATA` paths, and its header
comment records that a dirty tracked file outside that list *wedged the daily
`git pull --rebase`* until a console cleanup. If the server (or the player's
PC via `enrich.bat`) ever writes a tracked `collection_attrs.csv`, the sync
wedges again. A committed attrs file must therefore be a path **no runtime
ever writes**:

- [ ] Action writes `data/collection/collection_attrs.snapshot.csv`
      (committed; same `ATTRS_HEADER` columns; name-based enrichment).
- [ ] `mtglib.load_collection` overlay precedence becomes:
      sibling `collection_attrs.csv` (private, exact printings) **wins**;
      else `collection_attrs.snapshot.csv`; else none (current degraded path,
      honesty labels unchanged). The empty-cell-vs-absent-column contract is
      untouched — the snapshot file carries the full column set.
- [ ] `carddb.py` grows an `--out` flag (or reuses its existing dest param) so
      the Action can target the snapshot path without touching the private
      file's default.

### Known, accepted limitation

Name-based enrichment resolves *a* printing, not the player's printing:
`Scryfall` ids (→ card-image hotlinks) may show a different frame than the
owned copy. Type/MV/Colors/Cost/Sub-types/Produced/Flags — everything the
analysis pipeline consumes — are printing-independent (rare exceptions like
alt-frame subtypes are noise). The private sibling file still wins wherever it
exists, so the server/PC keep exact printings.

### Tests (offline, hermetic, as always)

- [ ] `test_mtglib`: snapshot-attrs fallback — sibling wins over snapshot;
      snapshot used when sibling absent; neither → `produced is None` degraded
      path intact (all in `tmp_path`).
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
- A server-side enrich hook (making CLAUDE.md's "server re-enriches" TRUE):
  smallest honest version is `sync_server.sh` running carddb against the
  private CSV after a successful pull, output staying gitignored-local.
  Decide only after the snapshot attrs prove out — it may be unnecessary.

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

Say yes to both and Opus can land Phase 2 in one session (workflow + carddb
`--out` + loader precedence + tests), with Phase 1 verification whenever the
allowlist is live.
