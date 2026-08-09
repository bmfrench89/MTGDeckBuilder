# Plan: Deploy the deckbuilder to PythonAnywhere (free tier)

**Goal:** one hosted copy of the web app at `https://<username>.pythonanywhere.com`, used
from every device — installed as the PWA on the phone, plain browser (or installed PWA) on
PC. The home PC stops being the server. Total cost: $0.

**Audience:** this plan is written to be executed by a Claude Code agent working in this
repo, with the account-creation and dashboard-clicking steps clearly marked **[HUMAN]**.
Everything else is **[AGENT]** or **[CONSOLE]** (commands the human pastes into a
PythonAnywhere bash console, or the agent walks them through live).

**Why PythonAnywhere:** it is the one free host whose filesystem **persists** — it's a
long-lived shared server, not an ephemeral container. Render's free tier was verified
(primary source) to lose all filesystem writes on every redeploy/restart/spin-down, which
destroys this app's data model (deck rewrites, `.changes.csv` appends, collection
uploads). PythonAnywhere free includes one web app at `<username>.pythonanywhere.com`,
HTTPS by default, ~512 MB persistent disk.

> **Facts flagged as unverified:** PythonAnywhere specifics in this plan (free-tier
> limits, whitelist behavior, keepalive interval, available Python versions) come from
> prior knowledge — pythonanywhere.com was egress-blocked from the research sandbox.
> They have been stable for years, but the executing agent should verify each one against
> the live site during Phase 1 and adjust. Nothing in this plan is expected to change
> architecturally if a detail differs.

---

## Repo facts the deploy depends on (verified in-repo, current as of this plan)

These were checked against `webapp/app.py` on branch `claude/claude-md-docs-67vnq0`;
re-verify quickly if the file has moved on.

1. **WSGI-clean import.** `app.run()` sits behind `if __name__ == "__main__":`
   (`webapp/app.py:690`). Importing `app` from `webapp/app.py` starts nothing. No
   `SECRET_KEY` is needed — the app uses no `flask.session`/`flash`.
2. **No env vars required.** `MTG_COLLECTION`, `MTG_DECKS_DIR`, `MTG_HOST`, `MTG_PORT`
   are all optional with sane defaults resolved relative to the repo root
   (`webapp/app.py:49–67`). Leave them all unset on the server.
3. **Collection fallback is built in.** On a fresh clone with no private CSV, the app
   serves from the committed name-only `collection_snapshot.txt`
   (`webapp/app.py:49–58`). Rich analysis unlocks after the first upload.
4. **Upload self-heals the config.** `/collection/upload` writes the private
   `data/collection/collection.csv` and rebinds the module-level `COLLECTION` global
   (`webapp/app.py:594–596`) — no web-app reload needed after the first upload. (Free
   tier runs a single worker, so the in-process global update is sufficient.)
5. **⚠ THE STATIC-MAPPING TRAP.** `/static/tokens.css` is a Flask **route**
   (`webapp/app.py:665–669`) serving `scripts/assets/tokens.css` — the file is NOT in
   `webapp/static/`. A PythonAnywhere "Static files" mapping of URL `/static/` →
   directory `webapp/static/` would intercept the URL and 404 the design tokens,
   breaking every page's type/spacing scale (and the service worker's precache list,
   `webapp/static/sw.js:17`). **Do not configure any static-files mapping.** Let Flask
   serve everything; single-user traffic makes the performance difference irrelevant.
6. **Service worker scope is already correct.** `/sw.js` is served from the app root via
   a route (`webapp/app.py:657–661`) precisely so its scope covers the whole app. HTTPS
   on pythonanywhere.com makes it a secure context — the PWA will install cleanly
   (better than the current LAN-IP setup).
7. **Card images are browser hotlinks to Scryfall's CDN** (`docs/card-images.md`),
   fetched by the phone/PC browser — server-side egress restrictions do not affect them.
8. **Network clients degrade gracefully by design** (`carddb`, `edhrec`, `spellbook` are
   disk-cached and tolerate being unreachable). This matters because of the free-tier
   whitelist (Phase 5).

---

## Phase 0 — [AGENT] Repo prep (do before touching PythonAnywhere)

0.1. **Create `webapp/pa_wsgi.py`** — a committed, documented WSGI entry template:

```python
"""PythonAnywhere WSGI entry template.

Paste (or import) this from the auto-generated
/var/www/<username>_pythonanywhere_com_wsgi.py, replacing <username>.
webapp/app.py handles the scripts/ sys.path insertion itself.
"""
import sys

PROJECT_WEBAPP = "/home/<username>/MTGDeckBuilder/webapp"
if PROJECT_WEBAPP not in sys.path:
    sys.path.insert(0, PROJECT_WEBAPP)

from app import app as application  # noqa: E402,F401
```

   Keep it import-inert (nothing at module scope beyond the above). It must not break
   the test suite or the stdlib-only CI check (it's under `webapp/`, so Flask-adjacent
   is fine, but it imports nothing third-party anyway).

0.2. **Run the full test suite** (`pip install -r requirements-dev.txt && pytest`) —
   confirm green before deploying, so any server-side breakage is known to be
   environmental, not a regression.

0.3. **Do NOT commit private data.** `data/collection/collection.csv`,
   `collection_attrs.csv`, and `data/cache/` are gitignored and must stay that way. The
   private CSV travels to the server via the app's own upload page (Phase 4), never via
   git.

0.4. Commit and push these prep changes to the working branch so the server clone
   includes them.

## Phase 1 — [HUMAN] Account

1.1. Create a free "Beginner" account at pythonanywhere.com. **The username becomes the
   URL** (`<username>.pythonanywhere.com`) — pick accordingly.
1.2. **[AGENT verify]** While signed up, confirm against the live site: free-tier disk
   quota, available Python versions (want ≥ 3.11; CI tests 3.11 and 3.13 — pick the
   newest offered in that range), the outbound-whitelist policy, and the web-app
   expiry/keepalive interval (believed: click "Run until 3 months from today" each
   ~3 months).

## Phase 2 — [CONSOLE] Clone + virtualenv

Open a **Bash console** on PythonAnywhere:

```bash
git clone https://github.com/bmfrench89/MTGDeckBuilder.git
# github.com is reachable from free accounts (git-over-HTTPS is whitelisted)

mkvirtualenv mtg --python=python3.13   # or newest available ≥3.11
pip install -r ~/MTGDeckBuilder/webapp/requirements.txt   # Flask only — small, fast
```

Optional sanity check (the suite is offline/hermetic, so it runs fine there):

```bash
pip install -r ~/MTGDeckBuilder/requirements-dev.txt && cd ~/MTGDeckBuilder && pytest
```

## Phase 3 — [HUMAN, agent-guided] Web app configuration

On the **Web** tab:

3.1. "Add a new web app" → `<username>.pythonanywhere.com` → **Manual configuration**
   (NOT the "Flask" quickstart — it scaffolds its own app) → the Python version chosen
   in Phase 2.
3.2. **Virtualenv** section: enter `mtg` (or the full path it resolves to).
3.3. **Code** section → WSGI configuration file (opens
   `/var/www/<username>_pythonanywhere_com_wsgi.py` in their editor): delete the
   generated contents and paste the body of `webapp/pa_wsgi.py`, replacing
   `<username>`.
3.4. **Static files: leave EMPTY** (repo fact #5 — a `/static/` mapping breaks
   `tokens.css`).
3.5. Click **Reload**. Then verify from any browser:
   - `https://<username>.pythonanywhere.com/health` → 200
   - `/` → decks leaderboard renders (from the committed snapshot + committed decks)
   - `/static/tokens.css` → 200 and returns CSS (proves the trap was avoided)
   - `/sw.js` → 200

   On error: check the **error log** linked from the Web tab (import errors land there).

## Phase 4 — [HUMAN] Data

4.1. From any device, open `https://<username>.pythonanywhere.com/collection` → upload
   the full ManaPool/Archidekt CSV export via the upload control (`/collection/upload`).
   It writes the private CSV server-side and takes effect immediately (repo fact #4).
4.2. Decks arrived with the git clone (they're committed). Nothing to do.
4.3. Optional, later: `data/collection/owned_additions.txt` and `data/reference/*` are
   hand-editable via the **Files** tab, same as locally.

## Phase 5 — [AGENT] Enrichment & the outbound whitelist

Free accounts route outbound HTTP(S) through a proxy restricted to a whitelist of sites
with public API docs.

5.1. Test from a PythonAnywhere console:
   `python3 ~/MTGDeckBuilder/scripts/carddb.py --collection data/collection/collection.csv --stats`
   - If `api.scryfall.com` is whitelisted (likely — it's a documented public API):
     enrichment works server-side. Done.
   - If not: request whitelist addition via their forums (they add documented public
     APIs on request), and/or use the fallback below.
5.2. **Fallback that always works:** run enrichment on the PC
   (`python3 scripts/carddb.py --collection data/collection/collection.csv --stats`,
   then `enrich.bat` flow), and upload the resulting
   `data/collection/collection_attrs.csv` to the same path on the server via the Files
   tab. EDHREC/Spellbook lookups simply degrade if unreachable — the app is built for
   that (repo fact #8); card images are unaffected (repo fact #7).

## Phase 6 — [HUMAN] Install on devices

6.1. **Phone:** open the URL in Chrome → ⋮ menu → "Add to Home Screen" / "Install app".
   Full-screen PWA, home-screen icon.
6.2. **PC:** bookmark, or install as a windowed PWA from the address-bar install icon in
   Chrome/Edge. Same URL, same data, every device.
6.3. Retire the LAN setup: stop running `webapp/run.sh` / `run.bat` at home. (Keep them
   in the repo — they still work for offline dev.)

## Phase 7 — [AGENT] Verification checklist (run through once, from the phone)

- [ ] `/health` 200; leaderboard lists all decks
- [ ] Open a deck dashboard: sections render, card panel opens on tap
  (`data-card` hooks — app surface), card images load (browser hotlinks)
- [ ] Edit a deck (remove/replace a card) → reload the page → **the edit survived**
- [ ] Reload the web app from the Web tab → **the edit STILL survived** (this is the
  persistence property Render free fails; if this fails, stop and reassess the host)
- [ ] `/collection` shows the uploaded row count, not the snapshot
- [ ] ⚡ optimize button runs and `!! ILLEGAL`/singleton checks stay clean
- [ ] PWA installed on phone launches full-screen with no address bar

## Ongoing maintenance (small, but real)

- **Keepalive:** log in and click "Run until 3 months from today" when nudged
  (calendar reminder recommended). If missed, the app sleeps until clicked — data is
  NOT lost.
- **Code updates:** from a PythonAnywhere console:
  `cd ~/MTGDeckBuilder && git pull`, then **Reload** on the Web tab (or
  `touch /var/www/<username>_pythonanywhere_com_wsgi.py`).
- **⚠ Deck edits diverge from git.** Deck `.txt`/companion files are git-tracked, and
  the web app now edits them **on the server**, so the server clone will show
  uncommitted changes and a future `git pull` can conflict. Adopt one rule:
  **the server is the source of truth for `data/decks/`**. Set up push access once
  (a GitHub fine-grained PAT for this repo, stored via
  `git remote set-url origin https://<user>:<token>@github.com/bmfrench89/MTGDeckBuilder.git`
  or a credential helper), then periodically — and always before pulling code changes:
  ```bash
  cd ~/MTGDeckBuilder
  git add data/decks data/collection/owned_additions.txt data/collection/pins.csv
  git commit -m "Deck edits from hosted app"
  git push
  git pull --rebase
  ```
  The executing agent should make this a tiny documented script (e.g.
  `scripts/sync_server.sh`, stdlib/shell only) rather than folklore.
- **Disk:** venv + repo + caches fit comfortably in 512 MB (Flask is the only
  dependency; `data/cache/` is a few MB of JSON). If quota bites, clear `data/cache/`.

## Failure modes / fallbacks

- **Free tier materially different than described** (no persistent disk, no free web
  app): stop; do not pay. Fall back to the Termux-on-phone path (fully offline, $0):
  F-Droid Termux → `pkg install python git` → `pip install flask` → clone → run →
  browse `http://localhost:5000` on-phone; Termux:Widget for a one-tap start script.
- **Whitelist blocks Scryfall and the forum request stalls:** live with Phase 5.2
  permanently — enrichment via PC upload, everything else unaffected.
- **Performance is unacceptable** (unlikely for one user; dashboards are pre-rendered
  HTML): profile before concluding anything; the free tier throttles CPU only after
  sustained heavy use.

## Explicit non-goals (this deploy)

- No APK / TWA wrapping — the origin now satisfies TWA's requirements
  (`https` + controllable `/.well-known/` path, servable by adding one Flask route),
  so it can be layered on later; the installed PWA already delivers the same UX.
- No auth. The user has explicitly accepted a public deck/collection app (no prices
  beyond estimates, no personal data beyond card names). If that changes, Flask
  basic-auth or PythonAnywhere's password-protection option (paid) are the levers.
- No changes to `scripts/` (stdlib-only rule untouched), no dashboard/renderer changes.
