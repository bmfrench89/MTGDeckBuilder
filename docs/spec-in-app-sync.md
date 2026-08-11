# Spec — In-app GitHub sync (the delivery leg, without a paid Scheduled Task)

**Status:** ☑ shipped 2026-08-10 · code: `webapp/sync.py` + `POST /sync` + a
`before_request` hook · UI: the maintenance card at the bottom of the Decks page ·
script: `sync_server.sh` (still the single source of truth for the git logic) ·
tests: `tests/test_sync.py`

This doc is both the spec and the user manual. It replaces the "PythonAnywhere daily
Scheduled Task" plan wherever older docs mention it.

---

## 1. Why the plan changed

The original design ran `sync_server.sh` from a PythonAnywhere **daily Scheduled
Task** — free tier was believed to include one. Checked live on 2026-08-10: the
Tasks tab now says *"They are only enabled for paid accounts"* (both Scheduled and
Always-on tasks). That leg of the automation was dead on arrival.

The replacement observation: **the web app itself is the one thing that's always
running on the server** — and the player opens it most days. So the app becomes its
own scheduler ("poor-man's cron"): on the first request of the day it syncs itself
in a background thread, and a manual **⇅ Sync now** button covers the
want-it-immediately case. Cost: $0, a few CPU-seconds a day, no new accounts, no
new credentials — it reuses the PAT already in the server's git remote.

## 2. How it works

```
Any page request
  └─ before_request: synced in the last 24 h?  ──yes──▶ nothing (one os.stat)
       └─ no, and sync is enabled ──▶ daemon thread:
            bash sync_server.sh  (SYNC_SKIP_RELOAD=1)
              ├─ commit data/decks + owned_additions.txt + pins.csv
              ├─ git pull --rebase   (abort + restore on conflict)
              └─ git push
            HEAD moved? ──▶ touch /var/www/*_wsgi.py  (app reloads itself)
            write data/cache/sync_status.json  {when, ok, reason, detail}

⇅ Sync now (button, Decks page)
  └─ same run, synchronously in the request; the WSGI touch is DEFERRED a few
     seconds so the redirect lands before the reload begins
```

Design decisions, each deliberate:

- **`sync_server.sh` stays the single source of truth.** The app shells out to the
  same script the console path uses — there is exactly one definition of "what gets
  committed" (the three runtime-edited paths, never `git add -A`, private CSV
  physically impossible to sweep in). A change to sync behavior lands in one file.
- **Enabled by detection, not configuration.** `sync.enabled()` is true on
  PythonAnywhere (the platform sets `PYTHONANYWHERE_SITE`/`PYTHONANYWHERE_DOMAIN`
  in web-app processes) and false everywhere else. `MTG_AUTO_SYNC=1|0` overrides
  either way (force-on to test locally; force-off to silence the server). On the
  PC, dev machines, CI: feature invisible, app unchanged.
- **The reload can't eat the response.** `sync_server.sh` ends by touching the WSGI
  file, which reloads the app — fine from a console, but from *inside* a request it
  would kill the response mid-flight. So the app runs the script with
  `SYNC_SKIP_RELOAD=1` and handles the reload itself: only when `git rev-parse
  HEAD` actually moved (code or snapshots were pulled), and for the button path on
  a short delay so the redirect completes first. No changes pulled → no reload →
  no daily blip.
- **A failed pull can't wedge the repo.** `git pull --rebase` hitting a conflict
  used to leave the clone mid-rebase with `set -e` bailing out — every later run
  would fail worse. The script now aborts the rebase on failure, restoring the
  clone, and exits 1 honestly. (This also fixes the console path.)
- **Status is a file, not a log.** `data/cache/sync_status.json` (gitignored) holds
  the last outcome; the Decks page renders it as one line. A "running" entry older
  than ten minutes is shown as a failure — a killed worker can't fake success.
- **Failures are shown, never retried in a loop.** One attempt per day plus the
  button. The status line carries the script's last error line; the console
  fallback is always available and always was.

## 3. The UI decision (uniformity pass)

One placement was considered against the app's existing patterns:

- **Not the nav** — the nav is navigation; it already carries six tabs plus the
  brand and wraps on phones. Actions don't live there anywhere in the app.
- **Not a new page** — this is one button and one status line.
- **The maintenance card on the Decks page** (`id="maint"`), next to
  "↻ Rebuild wishlist + static dashboards" — which is *exactly* this kind of
  action: a form-POST `.btn ghost` with a muted explainer, redirecting back. The
  sync row copies that pattern verbatim: no new CSS, no JS, same button class,
  same `.muted fs-xs` explainer, `.good`/`.warn` for the status line (all
  pre-existing classes). `POST /sync` redirects to `/#maint` so a phone lands
  scrolled to the result, status freshly written.
- When sync is disabled (every non-server machine), the row is simply absent and
  the card renders exactly as before — the feature cannot disturb any other
  surface, and `tests/test_design_tokens.py` is untouched because no style was
  added.

## 4. What the player does

**Nothing, usually.** Open the app like normal; the first visit each day syncs
deck edits up and pulls code/snapshot updates down within ~15 seconds,
reloading only if something changed. The button is there for "I want today's
snapshots *now*" or "I just edited on my phone and want it in git before I
close the tab."

If the status line ever shows a failure: open a PythonAnywhere console and run
`~/MTGDeckBuilder/sync_server.sh` — same logic, full output visible.

If it shows **"synced — RECOVERED"**: the sync worked, code came down, and your
in-app edits were parked on the named `server-rescue-<date>` branch on GitHub.
Nothing is lost — tell a Claude session to merge that branch back into main.

## 5. Failure modes, honestly

| Failure | What you see | State of the repo |
|---|---|---|
| Push rejected (PAT expired) | warn status: push failed | Deck edits stay safely committed locally; renew the PAT, next sync delivers them. |
| Rebase conflict (squash-merged PR rewrote files the server has local commits on — seen live 2026-08-11) | warn-styled "synced — RECOVERED" status naming the rescue branch | **Self-heals.** Local state is pushed to `server-rescue-<date>` FIRST, then the clone resets to upstream — edits are provably on GitHub before anything is discarded. A session merges the rescue branch back. Guarded by `test_script_recovers_from_a_squash_rewritten_upstream`. |
| Rebase conflict AND the rescue push fails (dead PAT + conflict) | warn status: pull failed, rebase aborted | Clone restored to pre-pull state, local commit intact — nothing is ever reset that isn't already saved remotely. Resolve once from a console. |
| Thread killed mid-run (reload/restart race) | stale "running" → shown as failed | Git operations are atomic-ish and idempotent — the next run picks up whatever finished. |
| `bash`/git missing (Windows PC with `MTG_AUTO_SYNC=1`) | warn status immediately | Nothing ran. The feature targets the server; use `update.bat` locally. |
| PythonAnywhere stops setting its env vars | feature silently off | Set `MTG_AUTO_SYNC=1` in the WSGI file — the documented override. |

## 6. What this does NOT do

- It does not replace the GitHub Action (`field-snapshots.yml`) — that still
  *produces* fresh snapshots on GitHub's side; this closes the *delivery* to the
  server, which the Action alone never could.
- It does not sync the private collection CSV — gitignored, travels only via the
  app's upload page, exactly as before.
- It does not touch decks, run the optimizer, or rebuild anything — it is git
  plumbing only.
- It does not poll or busy-wait — zero cost between requests; a day with no
  visits is a day with no sync (and nothing to sync).
