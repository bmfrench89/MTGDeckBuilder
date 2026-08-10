"""In-app GitHub sync (webapp/sync.py + POST /sync) — docs/spec-in-app-sync.md.

What can go wrong here is worse than a broken page: a bad trigger could run git
push from a test, a CI runner, or the player's PC. So the coverage priorities are
(1) the feature is OFF everywhere it wasn't explicitly turned on, (2) nothing in
this suite ever executes the real script, (3) the script itself keeps the
guarantees the app now leans on (skip-reload env, rebase abort, no `git add -A`).
Hermetic: the status file is redirected into tmp_path everywhere it could be read
or written.
"""
import os
import subprocess
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import sync


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """No sync-related env, status file in tmp_path — the feature's ground state."""
    for var in ("MTG_AUTO_SYNC", "PYTHONANYWHERE_SITE", "PYTHONANYWHERE_DOMAIN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(sync, "STATUS", str(tmp_path / "sync_status.json"))
    return tmp_path


# --------------------------------------------------------------------------- #
# enabled() — the switch that keeps this server-only
# --------------------------------------------------------------------------- #
def test_disabled_by_default(clean_env):
    """PC, CI, tests: no env vars → feature invisible. This is the safety line."""
    assert sync.enabled() is False


def test_pythonanywhere_is_autodetected(clean_env, monkeypatch):
    monkeypatch.setenv("PYTHONANYWHERE_SITE", "www.pythonanywhere.com")
    assert sync.enabled() is True


def test_explicit_flag_overrides_detection_both_ways(clean_env, monkeypatch):
    monkeypatch.setenv("MTG_AUTO_SYNC", "1")
    assert sync.enabled() is True
    monkeypatch.setenv("PYTHONANYWHERE_SITE", "www.pythonanywhere.com")
    monkeypatch.setenv("MTG_AUTO_SYNC", "0")
    assert sync.enabled() is False, "MTG_AUTO_SYNC=0 must silence even a detected server"


# --------------------------------------------------------------------------- #
# run() — outcome recording and the reload decision
# --------------------------------------------------------------------------- #
def _fake_script(monkeypatch, rc=0, out="sync: done.", err="", heads=("aaa", "aaa")):
    """Stub the two subprocess touchpoints: the bash script and git rev-parse."""
    calls = {"env": None, "touched": 0}
    it = iter(heads)

    def fake_run(cmd, **kw):
        calls["env"] = kw.get("env")
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr=err)

    monkeypatch.setattr(sync.subprocess, "run", fake_run)
    monkeypatch.setattr(sync, "_head", lambda: next(it))
    monkeypatch.setattr(sync, "_touch_wsgi",
                        lambda: calls.__setitem__("touched", calls["touched"] + 1))
    return calls


def test_run_success_records_status_and_skips_reload_when_head_unchanged(clean_env, monkeypatch):
    calls = _fake_script(monkeypatch)
    st = sync.run("manual")
    assert st["ok"] is True and st["pulled"] is False and st["reason"] == "manual"
    assert st["detail"] == "sync: done."
    assert calls["touched"] == 0, "nothing pulled → no reload → no daily blip"
    assert sync.status()["ok"] is True, "outcome must survive in the status file"


def test_run_always_defers_the_scripts_own_reload(clean_env, monkeypatch):
    """The script must never touch the WSGI file from inside a request — the app
    passes SYNC_SKIP_RELOAD=1 and makes the reload decision itself."""
    calls = _fake_script(monkeypatch)
    sync.run("manual")
    assert calls["env"]["SYNC_SKIP_RELOAD"] == "1"


def test_run_reloads_only_when_pull_moved_head(clean_env, monkeypatch):
    calls = _fake_script(monkeypatch, heads=("aaa", "bbb"))
    st = sync.run("auto")
    assert st["pulled"] is True
    assert calls["touched"] == 1


def test_run_failure_is_recorded_honestly_and_never_reloads(clean_env, monkeypatch):
    calls = _fake_script(monkeypatch, rc=1, heads=("aaa", "bbb"),
                         err="sync: PULL FAILED — rebase aborted")
    st = sync.run("manual")
    assert st["ok"] is False
    assert "PULL FAILED" in st["detail"]
    assert calls["touched"] == 0, "a failed run must not reload the app"


def test_run_survives_a_missing_bash(clean_env, monkeypatch):
    """Windows PC with MTG_AUTO_SYNC=1: the subprocess call itself explodes.
    That must become a warn status, not a 500."""
    monkeypatch.setattr(sync, "_head", lambda: None)
    def boom(*a, **k):
        raise FileNotFoundError("bash")
    monkeypatch.setattr(sync.subprocess, "run", boom)
    st = sync.run("auto")
    assert st["ok"] is False and "FileNotFoundError" in st["detail"]


# --------------------------------------------------------------------------- #
# maybe_start() — once a day, never twice at once, off unless enabled
# --------------------------------------------------------------------------- #
def _thread_recorder(monkeypatch):
    started = []
    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            started.append((target, args))
        def start(self):
            pass
    monkeypatch.setattr(sync.threading, "Thread", FakeThread)
    return started


def test_maybe_start_is_a_noop_when_disabled(clean_env, monkeypatch):
    started = _thread_recorder(monkeypatch)
    assert sync.maybe_start() is False and started == []


def test_maybe_start_fires_once_then_respects_the_ttl(clean_env, monkeypatch):
    monkeypatch.setenv("MTG_AUTO_SYNC", "1")
    started = _thread_recorder(monkeypatch)
    now = 1_000_000.0
    assert sync.maybe_start(now) is True
    assert started[0][0] is sync.run and started[0][1] == ("auto",)
    sync._write_status({"when": now, "ok": True, "reason": "auto", "pulled": False,
                        "detail": "sync: done."})
    assert sync.maybe_start(now + 3600) is False, "synced an hour ago — stay quiet"
    assert sync.maybe_start(now + sync.TTL + 1) is True, "a day later it's due again"
    assert len(started) == 2


def test_maybe_start_wont_stack_on_a_live_run_but_ignores_a_dead_one(clean_env, monkeypatch):
    monkeypatch.setenv("MTG_AUTO_SYNC", "1")
    started = _thread_recorder(monkeypatch)
    now = 1_000_000.0
    sync._write_status({"when": now, "ok": None, "reason": "auto", "detail": "running"})
    assert sync.maybe_start(now + 60) is False, "a running sync must not be doubled"
    assert sync.maybe_start(now + sync.STALE_RUNNING + 1) is True, \
        "a 'running' entry from a killed worker must not wedge the feature forever"
    assert len(started) == 1


# --------------------------------------------------------------------------- #
# The route and the button
# --------------------------------------------------------------------------- #
def _client(tmp_path, monkeypatch, collection_file):
    import app
    monkeypatch.setattr(app, "DECKS_DIR", str(tmp_path))
    monkeypatch.setattr(app, "COLLECTION", collection_file)
    # Belt and suspenders: no test may ever reach the real script or spawn a run.
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    return app.app.test_client()


def test_sync_route_runs_manual_and_redirects_to_the_card(clean_env, monkeypatch,
                                                          tmp_path, collection_file):
    ran = []
    monkeypatch.setattr(sync, "run",
                        lambda reason, reload_delay=0.0: ran.append((reason, reload_delay)))
    r = _client(tmp_path, monkeypatch, collection_file).post("/sync")
    assert r.status_code == 302 and r.headers["Location"].endswith("/#maint")
    assert ran == [("manual", sync.RELOAD_DELAY)], \
        "the button path must defer the reload past the redirect"


def test_sync_route_rejects_get(clean_env, monkeypatch, tmp_path, collection_file):
    assert _client(tmp_path, monkeypatch, collection_file).get("/sync").status_code == 405


def test_button_shows_only_where_sync_is_enabled(clean_env, monkeypatch,
                                                 tmp_path, collection_file):
    c = _client(tmp_path, monkeypatch, collection_file)
    html = c.get("/").get_data(as_text=True)
    assert "Sync with GitHub" not in html, "PC/CI: the Decks page is unchanged"

    monkeypatch.setattr(sync, "enabled", lambda: True)
    monkeypatch.setattr(sync, "status_view",
                        lambda now=None: {"cls": "good", "text": "synced just now"})
    html = c.get("/").get_data(as_text=True)
    assert "Sync with GitHub" in html and "synced just now" in html
    assert 'id="maint"' in html, "the redirect target must exist on the page"


# --------------------------------------------------------------------------- #
# status_view() — the one honest line
# --------------------------------------------------------------------------- #
def test_status_view_humanizes_ok_fail_and_stale_running(clean_env):
    assert sync.status_view() is None, "no status file → render nothing"
    now = 1_000_000.0
    sync._write_status({"when": now - 7200, "ok": True, "pulled": True, "detail": ""})
    v = sync.status_view(now)
    assert v["cls"] == "good" and "2 h ago" in v["text"] and "reloading" in v["text"]
    sync._write_status({"when": now - 120, "ok": False, "detail": "sync: PULL FAILED"})
    v = sync.status_view(now)
    assert v["cls"] == "warn" and "PULL FAILED" in v["text"]
    sync._write_status({"when": now - sync.STALE_RUNNING - 1, "ok": None,
                        "detail": "running"})
    assert sync.status_view(now)["cls"] == "warn", "a dead run must not read as success"


# --------------------------------------------------------------------------- #
# sync_server.sh — the guarantees the app now leans on
# --------------------------------------------------------------------------- #
def _script_src():
    return open(os.path.join(ROOT, "sync_server.sh"), encoding="utf-8").read()


def test_script_honors_the_skip_reload_contract():
    src = _script_src()
    assert "SYNC_SKIP_RELOAD" in src, \
        "the app calls with SYNC_SKIP_RELOAD=1 expecting the touch loop to be skipped"


def test_script_aborts_a_failed_rebase():
    assert "rebase --abort" in _script_src(), \
        "a conflicted pull must restore the clone, not leave it mid-rebase for every later run"


def test_script_still_adds_only_the_named_paths():
    src = _script_src()
    code = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
    assert not any("git add -A" in ln or "git add ." in ln for ln in code), \
        "sweeping adds could commit the private collection CSV's neighbors and runtime junk"
    for p in ("data/decks", "data/collection/owned_additions.txt", "data/collection/pins.csv"):
        assert p in src
