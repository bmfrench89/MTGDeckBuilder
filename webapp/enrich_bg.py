"""Background collection enrichment — the upload path's long pole, moved off the
request.

`/collection/upload` used to save the CSV and then run `carddb.enrich_api`
**synchronously**: minutes of Scryfall round-trips (~1 request per 75 cards) with
the browser holding an open connection and the host's CPU budget draining into
one request. That was the standing known-deferred item in
`spec-repo-hardening.md`, and on PythonAnywhere it is a live timeout risk, not a
theoretical one.

This is deliberately the **same pattern `webapp/sync.py` already uses** on this
exact host — daemon thread, JSON status file, one-at-a-time guard, stale-status
honesty — rather than a third way of doing background work in one small app.
Read that module first if you are changing this one.

Two things it does NOT do, on purpose:

  * **No resumption.** PythonAnywhere kills daemon threads on app reload (a
    deploy, the daily sync's own reload, the WSGI touch). A run that dies
    mid-flight leaves a `running` status that will never advance, so anything
    older than `STALE_RUNNING` renders as *interrupted — re-upload to retry*.
    That is the same honest-stale approach `sync.status_view` takes, and it is
    cheaper and more truthful than a checkpointing scheme nobody asked for.
  * **No partial-file window.** The attrs file is written atomically by
    `carddb.write_attrs_csv` (tmp + `os.replace`). That fix lives in carddb, not
    here, so every caller — this thread, the CLI, the bulk path — is safe.

While a run is in flight the collection is simply *not yet enriched*, which the
app already labels everywhere it matters (the identity-approximation notes, the
`color_sources_basis` fallback). Enrichment lighting up progressively is the
existing degrade story, not a new one.
"""
import json
import os
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS = os.path.join(ROOT, "data", "cache", "enrich_status.json")

STALE_RUNNING = 30 * 60      # a `running` entry older than this is a dead thread

_lock = threading.Lock()     # one enrichment at a time within this process


def _write_status(d):
    try:
        os.makedirs(os.path.dirname(STATUS), exist_ok=True)
        tmp = STATUS + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, STATUS)
    except OSError:
        pass          # a full disk must not take a page render down with it


def status():
    try:
        with open(STATUS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def running(now=None):
    """True while a run is live *and* young enough to still be believable."""
    st = status()
    if not st or st.get("state") != "running":
        return False
    now = time.time() if now is None else now
    return (now - st.get("when", 0)) < STALE_RUNNING


def _run(csv_path, attrs_path, enrich=None):
    """The thread body. Never raises — a failure becomes a status, not a
    traceback in a log nobody reads."""
    import sys
    scripts = os.path.join(ROOT, "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        if enrich is None:
            import carddb
            enrich = carddb.enrich_api
        matched, total, unmatched = enrich(csv_path, attrs_path)
        _write_status({"when": time.time(), "state": "done", "matched": matched,
                       "total": total,
                       "detail": (f"{len(unmatched)} card(s) Scryfall could not match"
                                  if unmatched else "")})
    except Exception as e:
        _write_status({"when": time.time(), "state": "error", "matched": 0,
                       "total": 0, "detail": f"{type(e).__name__}: {e}"[:300]})
    finally:
        # Phase 1's memo cache is holding the PRE-enrichment collection: its key
        # covers collection_attrs.csv, so the mtime change alone would evict it —
        # but this thread and the request that reads next are racing, and the
        # explicit call costs nothing. Runs on the error path too: a failed run
        # may still have replaced the attrs file before it died.
        try:
            import memo
            memo.invalidate()
        except Exception:
            pass


def start(csv_path, attrs_path, enrich=None, thread=True):
    """Kick off enrichment in the background. Returns a message for the flash.

    Refuses (without starting anything) while a run is live — a second upload
    would have two threads writing one attrs file, and `os.replace` makes that
    non-corrupting but still arbitrary."""
    with _lock:
        if running():
            return "Enrichment is already running — this upload's colors and types " \
                   "will be picked up by the run in progress."
        _write_status({"when": time.time(), "state": "running", "matched": 0,
                       "total": 0, "detail": "contacting Scryfall"})
    if not thread:                      # tests drive the body directly
        _run(csv_path, attrs_path, enrich)
        return "Enrichment finished."
    t = threading.Thread(target=_run, args=(csv_path, attrs_path, enrich), daemon=True)
    t.start()
    return ("Upload saved — enrichment is running in the background. Colors, types "
            "and mana values appear as it completes; until then the analytics label "
            "what they are approximating.")


def status_view(now=None):
    """One template-ready line about the last/current run. None → render nothing."""
    st = status()
    if not st:
        return None
    now = time.time() if now is None else now
    age = now - st.get("when", 0)
    state = st.get("state")
    if state == "running":
        if age < STALE_RUNNING:
            return {"cls": "muted",
                    "text": "enrichment running — colors/types appear as it completes"}
        # The daemon thread died with the app reload that killed it. Saying
        # "running" forever would be a lie with a spinner on it.
        return {"cls": "warn",
                "text": "enrichment was interrupted (the app restarted) — "
                        "re-upload the CSV to retry"}
    mins = int(age // 60)
    when = ("just now" if mins < 1 else f"{mins} min ago" if mins < 60
            else f"{mins // 60} h ago" if mins < 48 * 60 else f"{mins // 1440} d ago")
    if state == "done":
        matched, total = st.get("matched", 0), st.get("total", 0)
        extra = f" · {st['detail']}" if st.get("detail") else ""
        return {"cls": "good",
                "text": f"enriched {when} — {matched}/{total} cards matched{extra}"}
    if state == "error":
        return {"cls": "warn",
                "text": f"enrichment failed {when} — {st.get('detail', '')}"}
    return None
