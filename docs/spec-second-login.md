# Spec — A second login: a named member whose edits are labeled

**Status:** ☑ shipped 2026-10-12 — `webapp/users.py` (the store, scrypt hashes, lockout,
sign-out-everywhere via `ver`) · `webapp/app.py` (member sign-in, `_session_valid`, `_me` /
`_by`, `/people`, `/activity`, `/deck/<stem>/changes`, Replace/reconcile owner-only, the
`_note` → `data/activity.csv` writer, editor-save diffs) · `deckcore.append_changes` (THE
`.changes.csv` writer: optional `By`, atomic header migration) · `optimize(..., by=)` ·
`webapp/sync_summary.py` + `sync_server.sh` (activity.csv synced, per-person commit body;
`data/private/` gitignored and never in the path list) · tests `tests/test_members.py`.
As built: `By` and the activity log are written only once `users.json` exists (the
back-compat promise); editor saves are diffed into manual-add/-remove rows for everyone.
**Moved 2026-10-14** (spec-target-architecture Phase 1b): once the app runs on its
collection database, the member store and the activity log live there (`members`,
`activity`); users.json is taken in once and renamed `users.json.moved-to-db`, and
`data/activity.csv` stops growing, so the log is no longer committed. Everything below
still describes the behaviour; only where it is stored changed.

**Player ask (2026-10-12):** "I want to create a user login for my brother when he uses
the site."
**Decision (player, 2026-10-12): edit too, labeled.**

- The member gets the same powers as the owner, under their own name.
- Every deck change is labeled with who made it.
- The member's access can be revoked without touching the owner's.

---

## 1. What exists today

**The login.**

- One shared password, `MTG_PASSWORD` in the PythonAnywhere WSGI file, gives a 90-day
  session cookie.
- Anyone with the password *is* the player. There is no notion of who someone is.
- The session secret is derived from the password, so changing the password signs
  everyone out.

**What edits leave behind.**

- The card panel's Add, Remove and Replace append to `<deck>.changes.csv`, which has the
  columns `Card,Added,Replaced,Source`. The optimizer appends its swaps to the same file.
- **The deck editor's full-text save records nothing.**
- Deck-level actions (new deck, delete, pin, bracket, optimize, collection add or upload,
  sync) leave no record. The only trace is the generic sync commit "Deck edits from the
  hosted app".

## 2. Accounts

**Who signs in, and how.**

- There are two kinds of people: the **owner**, and named **members**.
- The owner keeps signing in with `MTG_PASSWORD`, so there is nothing to migrate.
- A member signs in with their name and their own password.

**Where accounts live: on the server, never in git.**

- The store is `data/private/users.json`, mode 0600.
- Each member has a `name`, `display`, `role`, `hash`, `ver` and `disabled` field. The
  owner's display name is stored in the same file.
- Hashes use Werkzeug's `generate_password_hash` (scrypt). The web app already has
  Werkzeug through Flask, and `scripts/` is untouched.
- `sync_server.sh` commits only its explicit paths, so it can never sweep this file into
  a push. `.gitignore` gains `data/private/` anyway.

**The People page (owner only).**

- The owner can add a member: a name and a password the owner chooses, shown once.
- The owner can reset a member's password, sign a member out everywhere, or disable the
  account.
- "Sign out everywhere" bumps the member's `ver`. The session stores (name, `ver`), so an
  old cookie fails on its next request. The owner's sessions are unaffected.

**The login page.**

- It gains a "Name" field.
- A blank name, or the owner's name, plus `MTG_PASSWORD` signs in the owner.
- **Nobody is signed out by the deploy.** An existing cookie that has `authed` but no
  name is read as the owner.

**Single-password mode stays.**

- With no `users.json`, the app behaves exactly as it does today.
- With no password at all (local dev, tests, CI), there is still no gate.
- Changing `MTG_PASSWORD` still signs *everyone* out, member included, because the
  session secret derives from it. The People page says so.

**Limits on guessing.**

- The existing 0.6 s delay on a failed sign-in stays.
- Add a lockout per name: 10 failures in 15 minutes locks that name out. It is kept in
  memory and resets on reload, which is fine for one worker.

## 3. What a member can do

A member can do everything the owner can, with two exceptions:

- **The People page** (managing accounts) is owner-only by definition.
- **Replacing the collection** (Upload) is *proposed* owner-only.
  - Upload swaps the owner's entire private collection for whatever file the member
    picks.
  - A backup is kept, but restoring it isn't a button.
  - One setting lets members upload too, if the owner wants that.

Everything else is open to a member, and labeled: editing decks, Add/Remove/Replace,
optimize, pins, brackets, saving a deck from Build Next, deleting decks, adding cards
(including batches, see `docs/spec-card-intake.md`) and sync.

## 4. Labels: who changed what

**`.changes.csv` gains an optional fifth column, `By`.**

- The columns become `Card,Added,Replaced,Source,By`.
- Every app edit fills `By`: the card panel's Add, Remove and Replace, and the ⚡
  optimize button through `optimize.record_changes(..., by=)`.
- CLI and session runs leave it empty.
- Every reader already uses `csv.DictReader`, so a missing or extra column parses safely.
- The first labeled write to an old four-column file rewrites the header in place, with
  an atomic replace. Old rows get an empty `By`, so a five-value row never sits under a
  four-name header.

**Deck-editor saves are diffed and logged.**

- The old list is compared with the new one. Each difference is logged as a
  `manual-add` or `manual-remove` row with `By`, closing today's gap.
- This has an intended side effect: a card added through the editor becomes protected
  from the optimizer, like any other manual add. CLAUDE.md: "Never second-guess a
  deliberate swap."

**An activity log covers deck-level actions.**

- The file is `data/activity.csv`, with columns `When,By,Action,Deck,Detail`.
- It records:
  - new deck, delete deck and notes edits;
  - pin, unpin and pin moves;
  - bracket changes and optimize runs;
  - collection add, batch and upload;
  - sync runs.
- Sign-ins are **not** logged here.
- It is added to `sync_server.sh`'s explicit path list, so the sync commits it and
  Claude sessions can read it.

**Where the labels show.**

- The NEW badge's tooltip reads "added by <name>, <date>".
- Each deck gets a "Changes" list showing who, what and when.
- An owner-only Activity view lists the last 100 actions.
- The sync commit's body summarises changes per person, e.g. "<owner>: 3 changes ·
  <member>: 2".

**The display name ends up in committed files** (`.changes.csv`, `activity.csv`). Pick
one you're happy to see in the repo.

## 5. One-time setup after it ships

1. Sync the app so the new code arrives.
2. Sign in as yourself, open People and choose Add member. Enter your brother's name
   and a password.
3. Give your brother the password in person or by text. Never put it in a chat or a screenshot.
4. Your brother opens the site, signs in with that name and password, and installs it
   to the home screen. The session then lasts 90 days.
5. To revoke the member later: People → Sign out everywhere, or Disable.

## 6. Tests (extending `tests/test_auth.py` and `tests/test_sync.py`)

**Back-compat**

- With no `users.json`, behaviour is identical to today, and every existing auth test
  passes unchanged.

**Owner**

- The owner can sign in with a blank name or the owner's name.
- An old cookie (`authed`, no name) is read as the owner.

**Member sign-in**

- A member signs in with the right password.
- A wrong password is delayed.
- 10 failures lock the name out.
- A disabled member is refused.
- Bumping `ver` sends the member back to the login page on the next request, without
  touching the owner's session.

**Member powers**

- The People page returns 403.
- Upload returns 403 while it is owner-only.
- Every other write route works.

**Labels**

- Add, Remove, Replace and optimize write `By`.
- An editor save writes diff rows with `By`.
- An old four-column `.changes.csv` still works everywhere: the dashboard's NEW badge,
  optimizer protection and `deck_fit`'s manual-add read.
- The header migration keeps every existing row.

**Activity**

- Each deck-level action writes one `activity.csv` row.
- `sync_server.sh`'s path list includes `activity.csv` and can never include
  `data/private/`.

## 7. Boundaries

- This is a privacy fence for a two-person hobby app, as `spec-auth-gate.md` says. It is
  not multi-tenant: there is one collection and one set of decks, and both people edit
  the same decks.
- If the member later wants their own decks and collection, that's a separate, bigger spec.
