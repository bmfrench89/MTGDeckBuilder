"""In-app GitHub sync — the delivery leg of the automation loop, without a paid
Scheduled Task (PythonAnywhere made those paid-only; checked live 2026-08-10).

The web app is the one process that's always running on the server, so it schedules
itself: the first request of the day kicks `sync_server.sh` in a background thread
(deck edits go up, code + field snapshots come down), and `POST /sync` runs the same
thing on demand. The script stays the single source of truth for the git logic —
this module only decides WHEN to run it and HOW to reload afterwards.

Spec + failure modes: docs/spec-in-app-sync.md.
"""
import json
import os
import subprocess
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "sync_server.sh")
STATUS = os.path.join(ROOT, "data", "cache", "sync_status.json")

TTL = 24 * 3600          # one auto-sync per day is the whole design
STALE_RUNNING = 600      # a "running" entry older than this is a dead worker
RELOAD_DELAY = 4.0       # button path: let the redirect land before reloading
RELOAD_SHOWN = 120       # "app reloading" is only true this long; after that the
                         # reload finished ages ago and the label would read as stuck

_lock = threading.Lock()  # one sync at a time within this process


def enabled():
    """On by detection (PythonAnywhere sets these in web-app processes), overridable
    both ways with MTG_AUTO_SYNC=1|0. Everywhere else — PC, CI, tests — the feature
    is invisible and the app behaves exactly as before."""
    flag = os.environ.get("MTG_AUTO_SYNC")
    if flag is not None:
        return flag == "1"
    return bool(os.environ.get("PYTHONANYWHERE_SITE")
                or os.environ.get("PYTHONANYWHERE_DOMAIN"))


def _head():
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip() or None
    except Exception:
        return None


def _touch_wsgi():
    """PythonAnywhere's documented reload trigger. No-ops anywhere without /var/www."""
    try:
        import glob
        for w in glob.glob("/var/www/*_wsgi.py"):
            os.utime(w, None)
    except Exception:
        pass


def _write_status(d):
    try:
        os.makedirs(os.path.dirname(STATUS), exist_ok=True)
        with open(STATUS, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except OSError:
        pass  # a full disk must not take a page render down with it


def status():
    try:
        with open(STATUS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def run(reason, reload_delay=0.0):
    """Run sync_server.sh once and record the outcome. The script is called with
    SYNC_SKIP_RELOAD=1 and the reload happens HERE, only if HEAD actually moved —
    delayed on the button path so the response isn't killed mid-flight."""
    with _lock:
        _write_status({"when": time.time(), "ok": None, "reason": reason,
                       "detail": "running"})
        before = _head()
        try:
            r = subprocess.run(["bash", SCRIPT], cwd=ROOT, capture_output=True,
                               text=True, timeout=420,
                               env={**os.environ, "SYNC_SKIP_RELOAD": "1"})
            ok = r.returncode == 0
            # The last non-blank line is the script's own summary ("sync: done." /
            # "sync: PULL FAILED …") — one honest line for the status display.
            lines = [ln for ln in (r.stdout + "\n" + r.stderr).splitlines() if ln.strip()]
            detail = lines[-1] if lines else ""
        except Exception as e:                      # bash/git missing, timeout
            ok, detail = False, f"{type(e).__name__}: {e}"
        # A lock-contention skip exits 0 having done NOTHING (a console sync held
        # the flock) — recording it ok:True would burn the day's TTL on a no-op
        # whose real work happened in a process that never writes this file.
        if "another sync is already running" in detail:
            ok = False
        # Independent of ok, deliberately: a pull-succeeded-push-failed run HAS
        # changed the code on disk, and skipping the reload leaves the app serving
        # the old code all day — the stale-serve bug found 2026-08-12. A total
        # failure never moves HEAD, so this stays False exactly when it should.
        pulled = _head() != before
        st = {"when": time.time(), "ok": ok, "reason": reason,
              "pulled": pulled, "detail": detail[-300:]}
        _write_status(st)
    if pulled:
        if reload_delay > 0:
            t = threading.Timer(reload_delay, _touch_wsgi)
            t.daemon = True
            t.start()
        else:
            _touch_wsgi()
    return st


def maybe_start(now=None):
    """The before_request hook: cost is one file read; a sync starts only when
    enabled, none succeeded in the last 24 h, and none is currently running."""
    if not enabled():
        return False
    now = time.time() if now is None else now
    st = status()
    if st:
        age = now - st.get("when", 0)
        if st.get("detail") == "running" and age < STALE_RUNNING:
            return False
        # Only a SUCCESSFUL sync consumes the daily TTL. `ok is not None` here
        # let one failed run (a lost push race, an expired PAT) burn the whole
        # day's budget — the app then served stale code for up to 24 h with a
        # fix one request away. A failure now retries on the next request.
        if st.get("ok") and age < TTL:
            return False
    t = threading.Thread(target=run, args=("auto",), daemon=True)
    t.start()
    return True


def status_view(now=None):
    """One template-ready line about the last sync. None → render nothing."""
    st = status()
    if not st:
        return None
    now = time.time() if now is None else now
    age = now - st.get("when", 0)
    if st.get("detail") == "running":
        if age < STALE_RUNNING:
            return {"cls": "muted", "text": "sync running…"}
        return {"cls": "warn", "text": "last sync never finished — try again or use a console"}
    mins = int(age // 60)
    when = ("just now" if mins < 1 else f"{mins} min ago" if mins < 60
            else f"{mins // 60} h ago" if mins < 48 * 60 else f"{mins // 1440} d ago")
    if st.get("ok"):
        # A recovered sync is a success with homework: local edits were parked on
        # a pushed rescue branch that a session still has to merge. Green would
        # bury that — keep the warn styling and the script's own line until the
        # next fully-clean sync overwrites it.
        if "RECOVERED" in st.get("detail", ""):
            return {"cls": "warn", "text": f"synced {when} — {st['detail'][:200]}"}
        # `pulled` stays in the status file until the NEXT sync (up to 24 h), but
        # the reload itself takes seconds — cap the "reloading" claim or the page
        # reads as stuck all day.
        extra = ""
        if st.get("pulled"):
            extra = (" · updates pulled, app reloading" if age < RELOAD_SHOWN
                     else " · updates pulled")
        return {"cls": "good", "text": f"synced {when}{extra}"}
    return {"cls": "warn", "text": f"sync failed {when} — {st.get('detail', '')}".rstrip(" —")}
