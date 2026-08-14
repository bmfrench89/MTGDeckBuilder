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


def _collection_path():
    """The collection the post-pull regroup reads types from.

    Same precedence as the app's `_default_collection` (env → private CSV →
    committed name-only snapshot), re-derived here rather than imported because
    `app` imports THIS module — importing back would be a cycle. The snapshot
    fallback still types cards, since `mtglib.load_collection` merges
    `collection_attrs.snapshot.csv` beside it."""
    env = os.environ.get("MTG_COLLECTION")
    if env:
        return env
    csv_path = os.path.join(ROOT, "data", "collection", "collection.csv")
    if os.path.exists(csv_path):
        return csv_path
    return os.path.join(ROOT, "data", "collection", "collection_snapshot.txt")


def regroup_unsorted(decks_dir=None, collection=None):
    """Re-file decks that still carry an `Unsorted` section, after a pull.

    The pull is also how fresh `collection_attrs` reach the server, so a card
    that was untypeable when a session last regrouped is typeable now. Running
    the regroup here drains those sections without anybody opening a session.

    Deliberately narrow and defensive: only decks whose Unsorted section is
    non-empty are rewritten (every other deck is already in shape and must not
    be churned), each deck is wrapped on its own, and the caller wraps this —
    a regroup problem must never turn a good sync into a failed one. Returns a
    one-line summary, or None when there was nothing to do."""
    import glob as _glob
    import sys as _sys
    scripts = os.path.join(ROOT, "scripts")
    if scripts not in _sys.path:
        _sys.path.insert(0, scripts)
    import deck_sections

    decks_dir = decks_dir or os.environ.get("MTG_DECKS_DIR",
                                            os.path.join(ROOT, "data", "decks"))
    collection = collection or _collection_path()
    done, failed, skipped, left = [], [], [], 0
    for path in sorted(_glob.glob(os.path.join(decks_dir, "*.txt"))):
        try:
            if not deck_sections.has_unsorted(path):
                continue
            if deck_sections.has_section_comments(path):
                # A regroup drops comment lines that sit inside a section. Doing
                # that unattended on the server would break CLAUDE.md's
                # "edits keep comment lines intact" contract against a file the
                # player may have hand-annotated. Skip loudly instead.
                skipped.append(os.path.basename(path))
                continue
            text, st = deck_sections.regroup(path, collection)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            done.append(os.path.basename(path))
            left += st.get("unsorted", 0)
        except Exception as e:                      # one bad deck, not a bad sync
            failed.append(f"{os.path.basename(path)}: {type(e).__name__}")
    if not done and not failed and not skipped:
        return None
    parts = []
    if done:
        parts.append(f"regrouped {len(done)} deck(s): {', '.join(done)}")
        # Honest about what is NOT resolved: cards the refreshed attrs still
        # cannot type stay in Unsorted, and saying so is the whole point.
        parts.append(f"{left} card(s) still unsorted" if left else "all Unsorted drained")
    if skipped:
        parts.append("skipped (in-section comments, regroup would drop them): "
                     + ", ".join(skipped))
    if failed:
        parts.append("regroup failed for " + "; ".join(failed))
    return " · ".join(parts)


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
        if pulled:
            # A pull rewrites decks, collection attrs and reference lists under a
            # live process. The memo cache keys on mtimes and would notice, but
            # git can restore a file with a size and a coarse mtime that match —
            # and this is the one code path that changes many files at once with
            # nobody watching. Say it outright instead of trusting stat().
            try:
                import sys as _sys
                scripts = os.path.join(ROOT, "scripts")
                if scripts not in _sys.path:
                    _sys.path.insert(0, scripts)
                import memo
                memo.invalidate()
            except Exception:
                pass                  # a cache miss is never worth failing a sync
        # Post-pull hygiene: a pull can bring fresh collection attrs down, which
        # is exactly when a deck's Unsorted section becomes resolvable. Wrapped
        # whole — a regroup error is reported in the status line, never allowed
        # to fail the sync it rode in on.
        regroup = None
        if pulled and enabled():
            # `enabled()` scopes this to the hosted server — the one process that
            # pulls attrs it did not author. It is also the switch that keeps a
            # deck-file WRITE out of every other environment (PC, CI, tests),
            # which is the safer default for a path nobody is watching.
            try:
                regroup = regroup_unsorted()
            except Exception as e:
                regroup = f"regroup skipped: {type(e).__name__}: {e}"
            if regroup:
                print(f"sync: {regroup}")
        # `detail` stays the SCRIPT's own line, never concatenated with the
        # regroup summary. Appending used to push the word RECOVERED out of the
        # 300-char tail — and `status_view` keys the rescue-branch warning off
        # that word, so a self-heal silently rendered plain green (found by the
        # Phase 0 verifier, reproduced end-to-end). The regroup rides in its own
        # field and `recovered` is stored as a BOOLEAN, so the warning no longer
        # depends on a substring surviving truncation at all.
        st = {"when": time.time(), "ok": ok, "reason": reason,
              "pulled": pulled, "detail": detail[-300:],
              "recovered": "RECOVERED" in detail}
        if regroup:
            st["regroup"] = regroup
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


def _regroup_suffix(st):
    """The post-pull regroup summary, rendered from its OWN field.

    It is never folded into `detail`: that is what truncated the RECOVERED
    warning away. Capped separately so a long deck list cannot crowd out the
    line it is appended to.
    """
    r = (st.get("regroup") or "").strip()
    return f" · {r[:120]}" if r else ""


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
        # `recovered` is the boolean written since the truncation fix; the
        # substring check stays for status files written before it.
        if st.get("recovered") or "RECOVERED" in st.get("detail", ""):
            return {"cls": "warn",
                    "text": f"synced {when} — {st['detail'][:200]}{_regroup_suffix(st)}"}
        # `pulled` stays in the status file until the NEXT sync (up to 24 h), but
        # the reload itself takes seconds — cap the "reloading" claim or the page
        # reads as stuck all day.
        extra = ""
        if st.get("pulled"):
            extra = (" · updates pulled, app reloading" if age < RELOAD_SHOWN
                     else " · updates pulled")
        return {"cls": "good", "text": f"synced {when}{extra}{_regroup_suffix(st)}"}
    return {"cls": "warn", "text": f"sync failed {when} — {st.get('detail', '')}".rstrip(" —")}
