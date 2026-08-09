# Spec — The Field-Snapshot Action (automated EDHREC refresh)

**Status:** ☑ shipped 2026-08-09 · workflow: `.github/workflows/field-snapshots.yml` ·
data: `data/reference/field/<slug>.json` · consumers: everything behind
`edhrec.inclusion_map / synergy_map / field_names / recommendations` (the fit engine,
the optimizer, add verdicts, Buy staples, panel alternatives, Build Next).

This doc is both the spec and the user manual. The architecture it completes is in
`docs/codemap.md` ("Where each signal works — the deployment reality").

---

## 1. The problem it solves, in one paragraph

The app's field signal — per-commander inclusion % and synergy — comes from
`json.edhrec.com`, which the hosted server can **never** reach: PythonAnywhere free
accounts are allowlisted to documented public APIs only, and EDHREC's JSON is an
internal feed with no docs. The committed-snapshot mechanism (PR #76) made the data
*deliverable* via git; this Action makes the delivery *automatic*, because the player
is phone-first and "run this on your PC weekly" is a chore that quietly stops
happening. No reachable substitute source exists — the alternatives survey (Scryfall,
MTGJSON, cardcognition, Archidekt/Moxfield corpora) found nothing that carries
per-commander inclusion + synergy first-hand.

## 2. How it works

```
GitHub runner (unrestricted internet)
  └─ python3 scripts/edhrec.py --snapshot-all --collection <name-only snapshot>
       └─ per deck commander: fetch json.edhrec.com → distill {inclusion, synergy,
          names} → data/reference/field/<slug>.json   (a few KB each)
  └─ commit only if files changed → push to main (built-in GITHUB_TOKEN)

Hosted server                 Phone
  └─ git pull (or               └─ uses the app; every field-backed
     sync_server.sh)               feature now has real numbers,
     picks the files up            labeled "Snapshot (saved DATE)"
```

Key properties, each deliberate and each tested in `tests/test_card_flow.py`:

- **Commander list is self-updating** — read from the deck files' own
  `# Commander:` headers at run time. A new deck pushed to `main` triggers the
  Action (path filter) and gets its snapshot within minutes.
- **Nothing private is involved.** Snapshots store inclusion/synergy/names — never
  ownership. The `--collection` argument is satisfied by the committed name-only
  snapshot.
- **A failed fetch never writes an empty file**, and a snapshot-sourced read can
  never re-save itself as fresh. Worst case of a bad run is *stale-but-good* data.
- **Partial success commits.** Five commanders fetched + one failed = five updated
  files land, with a warning annotation on the run.
- **Total failure turns the run red** (and commits nothing) — the signal that
  EDHREC is blocking runner IPs and the PC fallback is needed.
- **Precedence at read time is unchanged:** live fetch → disk cache → snapshot →
  `{}`. A machine that CAN reach EDHREC (the PC) never reads stale data.

## 3. Triggers and cadence

| Trigger | Fires | Rationale |
|---|---|---|
| `schedule` | Mondays 09:23 UTC | Weekly matches the app's own `CACHE_TTL` (7 days) — the codebase already encodes "inclusion rates drift slowly". Off-peak minute because GitHub cron is best-effort and :00 slots run late. |
| `push` on `data/decks/*.txt` | when a deck lands on `main` | New commander → snapshot exists before you next open the deck. Note: decks built on the SERVER reach `main` only via `sync_server.sh` — one more reason to finish the PAT setup. |
| `workflow_dispatch` | on demand | **The phone path:** github.com → repo → Actions → field-snapshots → "Run workflow". Use before a big building session if you want today's numbers. |

Loop safety: the Action's own commits touch only `data/reference/field/`, which does
not match the push trigger's path filter — and pushes made with the built-in
`GITHUB_TOKEN` don't trigger workflows anyway. Two independent guards, no loop.

## 4. Cost

- **GitHub:** free on a public repo (unlimited standard-runner minutes); on a private
  repo the free tier is 2,000 min/month and this job uses ~1 min/run → ~5–10
  min/month. Storage: a few KB per commander.
- **EDHREC:** 6-ish polite requests weekly with the client's identifying User-Agent —
  less than one human page view. The weekly cadence is deliberately respectful.
- **Maintenance:** none in steady state. Two known GitHub quirks: scheduled workflows
  auto-disable after ~60 days of repo inactivity (one click re-enables), and cron can
  slip during busy hours (irrelevant at weekly cadence).

## 5. Failure modes, honestly

| Failure | What you see | What happens to the app |
|---|---|---|
| EDHREC blocks GitHub runner IPs (Cloudflare) | red run, "::error:: none fetchable" | Nothing changes — existing snapshots keep serving. Fallback: run `--snapshot-all` on the PC and push, exactly the pre-Action workflow. |
| EDHREC changes its JSON shape | red/partial runs | Same — old snapshots keep serving. Fix the parser in `edhrec.py`; consumers are untouched (three-tier fallback is the interface). |
| One commander 404s (renamed/misspelled header) | warning annotation, that file skipped | Other commanders refresh normally. |
| A deck sync pushes to `main` mid-run | none | The commit step rebases before pushing. |
| Snapshot data is somehow bad | — | `git revert` the refresh commit; the app can't crash on it (degrades to fit-only, tested). |

**The first live run is the Cloudflare experiment.** It was dispatched manually the
day this shipped — see the run history for the verdict. A red first run costs
nothing; a green one closes the loop permanently.

## 6. What this does NOT do

- It does not run the optimizer, rebuild dashboards, or touch decks — it only
  refreshes reference data. (The server renders dashboards live; CLI-rendered files
  refresh via `refresh.py` as before.)
- It does not remove the live-fetch path: a machine with EDHREC access still gets
  the freshest data directly, snapshot untouched.
- It does not deliver the data to the server by itself — GitHub cannot reach into
  PythonAnywhere. The delivery leg is a **PythonAnywhere daily Scheduled Task**
  (free tier includes one) running `sync_server.sh`, which now ends by touching the
  WSGI file — PythonAnywhere's documented reload trigger — so pull and reload are
  one step. Until that task (and the PAT it wants) exist, delivery is a manual
  `git pull` + Reload.
- It does not solve the collection CSV upload; that remains in `handoff.md`.
