# Spec — The access gate (shared-password login)

**Status:** ☑ shipped 2026-08-10 · code: the "access gate" block in `webapp/app.py`
(`_require_login`, `/login`, `/logout`) + `webapp/templates/login.html` ·
tests: `tests/test_auth.py`

## 1. The problem

The hosted deploy is a public URL with, previously, **no authentication**: anyone who
found it could read the collection, edit or delete decks, upload a CSV over the
private one, and trigger the GitHub sync (which pushes with the server's stored
credentials). The repo no longer prints the URL, but PythonAnywhere URLs are
`<username>.pythonanywhere.com` and the username is guessable — obscurity is not
protection.

## 2. The design

One shared password, set server-side, session cookie afterwards. Single-user app →
no accounts, no user table, no password storage (the env var *is* the credential).

- **Off unless configured.** `MTG_PASSWORD` unset → the gate does not exist; local
  dev, tests, and CI behave exactly as before. Same pattern as the sync feature.
- **Everything is gated.** With a password set, every route redirects to `/login`
  except the login page itself and the shell assets it needs (`/static/*`,
  `/sw.js`, `/static/tokens.css`). `/health` is deliberately **not** exempt — it
  reveals server paths. Anonymous **POSTs get a hard 401**, never a redirect.
- **Sessions survive the daily reload.** The Flask secret key derives from the
  password (`sha256("mtg-auth-v1:" + password)`), not `os.urandom` — a random key
  would sign every device out at each WSGI-touch reload. Sessions are permanent
  with a 90-day lifetime, so the installed PWA stays signed in.
- **Login safety:** constant-time comparison (`hmac.compare_digest`), a 0.6 s delay
  on failure (a blunt but real brake on guessing), and the `next` parameter only
  ever redirects within the app (no open redirect).
- **Sign out** is a POST (nav link, shown only when the gate is on) that clears the
  session on that device.

## 3. Server setup (one time)

In the PythonAnywhere WSGI file (Web tab → WSGI configuration file), **above** the
import lines, add:

```python
import os
os.environ["MTG_PASSWORD"] = "<a strong password>"
```

then Reload. The password lives only in that file (outside the repo, not in git).
Each device signs in once and stays signed in ~90 days. To change the password:
edit the line, Reload — all sessions are invalidated automatically (the cookie key
changes with it).

Do not commit the password anywhere, and don't paste it into chats or screenshots.

## 4. Boundaries, honestly

- This is a **privacy fence for a single-user hobby app**, not hardened multi-user
  auth: one shared secret, no lockout counter, no audit log, no 2FA. For "keep
  strangers from editing my decks," that is the right size.
- Transport security comes from the host (PythonAnywhere serves HTTPS).
- The GitHub PAT is unaffected — it never transits the app; it lives in the server
  clone's git remote.
- If the password is forgotten, edit the WSGI line to a new one and Reload —
  nothing is lost.
