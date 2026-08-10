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
                               text=True, timeout=300,
                               env={**os.environ, "SYNC_SKIP_RELOAD": "1"})
            ok = r.returncode == 0
            # The last non-blank line is the script's own summary ("sync: done." /
            # "sync: PULL FAILED …") — one honest line for the status display.
            lines = [ln for ln in (r.stdout + "\n" + r.stderr).splitlines() if ln.strip()]
            detail = lines[-1] if lines else ""
        except Exception as e:                      # bash/git missing, timeout
            ok, detail = False, f"{type(e).__name__}: {e}"
        pulled = ok and _head() != before
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
        if st.get("ok") is not None and age < TTL:
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
        extra = " · updates pulled, app reloading" if st.get("pulled") else ""
        return {"cls": "good", "text": f"synced {when}{extra}"}
    return {"cls": "warn", "text": f"sync failed {when} — {st.get('detail', '')}".rstrip(" —")}
