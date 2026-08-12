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
    assert v["cls"] == "good" and "2 h ago" in v["text"] and "updates pulled" in v["text"]
    sync._write_status({"when": now - 120, "ok": False, "detail": "sync: PULL FAILED"})
    v = sync.status_view(now)
    assert v["cls"] == "warn" and "PULL FAILED" in v["text"]
    sync._write_status({"when": now - sync.STALE_RUNNING - 1, "ok": None,
                        "detail": "running"})
    assert sync.status_view(now)["cls"] == "warn", "a dead run must not read as success"


def test_status_view_stops_claiming_a_reload_that_finished(clean_env):
    """`pulled` lives in the status file until the NEXT sync — up to 24 h — but the
    reload takes seconds. The 'app reloading' label must be time-bounded or the
    Decks page reads as stuck syncing all day (seen live on the phone)."""
    now = 1_000_000.0
    sync._write_status({"when": now - 30, "ok": True, "pulled": True, "detail": ""})
    assert "app reloading" in sync.status_view(now)["text"], \
        "right after the pull the reload really is in flight — say so"
    sync._write_status({"when": now - sync.RELOAD_SHOWN - 1, "ok": True,
                        "pulled": True, "detail": ""})
    v = sync.status_view(now)
    assert "updates pulled" in v["text"] and "reloading" not in v["text"], \
        "minutes later the reload is long done — keep the fact, drop the claim"


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


def test_script_pushes_the_rescue_branch_before_resetting_anything():
    """The self-heal order is the whole safety argument: local edits must be ON
    GITHUB before reset --hard discards them locally. Seen live 2026-08-11 —
    a squash-merged PR rewrote deck files the server had local commits on, and
    the old abort-only path wedged the daily sync until a console visit."""
    code = [ln for ln in _script_src().splitlines() if not ln.lstrip().startswith("#")]
    src = "\n".join(code)
    push = src.find('git push -f origin "$rescue"')
    # Target the SELF-HEAL's reset by its argument, not the first `reset --hard`
    # in the file. The autostash restore added 2026-08-12 contains its own
    # `reset --hard HEAD` — undoing a conflicted stash pop, which discards nothing
    # (the stash entry survives a failed pop) — and it sits earlier in the script,
    # so a bare first-occurrence search now measures the wrong statement.
    reset = src.find('reset --hard "@{u}"')
    assert push != -1 and reset != -1, "the rescue path must exist"
    assert push < reset, "reset before the rescue push would discard unsaved edits"


def test_script_parks_uncommitted_work_before_it_can_be_reset_away():
    """The self-heal's `git branch -f` captures HEAD only, so anything uncommitted
    is NOT on the rescue branch when reset --hard runs. Verified destroyed before
    the 2026-08-12 fix. A stash survives both the rebase and the reset."""
    code = "\n".join(ln for ln in _script_src().splitlines()
                     if not ln.lstrip().startswith("#"))
    stash = code.find("git stash push -u")
    pull = code.find("git pull --rebase")
    reset = code.find('reset --hard "@{u}"')
    assert stash != -1, "uncommitted work must be parked before the pull"
    assert stash < pull < reset, "the stash must precede the pull and the reset"
    assert "trap restore_autostash EXIT" in code, \
        "the stash must be restored on every exit path, including set -e failures"
    assert "git fetch origin" in code, \
        "@{u} is stale when the pull aborts before fetching — re-fetch before reset"


def test_script_refuses_to_self_heal_over_a_dirty_tree():
    code = "\n".join(ln for ln in _script_src().splitlines()
                     if not ln.lstrip().startswith("#"))
    heal = code.find('git branch -f "$rescue"')
    guard = code.find("refusing to self-heal")
    assert guard != -1 and guard < heal, \
        "a dirty tree must take the honest abort, never a reset no branch can hold"


def _git_env(tmp_path):
    """Hermetic git: identity via env, HOME redirected so no user config leaks in."""
    return {**os.environ, "SYNC_SKIP_RELOAD": "1", "HOME": str(tmp_path),
            "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"),
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


@pytest.mark.skipif(os.name == "nt", reason="the script targets the bash-equipped server")
def test_script_recovers_from_a_squash_rewritten_upstream(tmp_path):
    """End to end in throwaway repos: upstream history rewritten under the server's
    local deck commit (exactly what a squash-merged PR does), sync must (1) push
    the local state to a rescue branch, (2) reset the clone to upstream, (3) exit
    0 with RECOVERED in its summary — and the edit must be readable on origin."""
    env = _git_env(tmp_path)

    def g(cwd, *args):
        r = subprocess.run(["git", *args], cwd=str(cwd), env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0, f"git {args}: {r.stderr}"
        return r.stdout

    origin = tmp_path / "origin.git"
    origin.mkdir()
    g(origin, "init", "--bare", "--initial-branch=main", ".")

    seed = tmp_path / "seed"
    g(tmp_path, "clone", str(origin), "seed")
    (seed / "data" / "decks").mkdir(parents=True)
    (seed / "data" / "decks" / "a.txt").write_text("1 Foo\n", encoding="utf-8")
    (seed / "sync_server.sh").write_text(_script_src(), encoding="utf-8")
    g(seed, "add", "-A")
    g(seed, "commit", "-m", "seed")
    g(seed, "push", "-u", "origin", "main")

    server = tmp_path / "server"
    g(tmp_path, "clone", str(origin), "server")

    # Upstream rewrites the deck file (the squash-merged PR)…
    (seed / "data" / "decks" / "a.txt").write_text("1 Bar\n", encoding="utf-8")
    g(seed, "commit", "-am", "pr rewrite")
    g(seed, "push")
    # …while the server holds an uncommitted local edit to the same file.
    (server / "data" / "decks" / "a.txt").write_text("1 Baz\n", encoding="utf-8")

    r = subprocess.run(["bash", "sync_server.sh"], cwd=str(server), env=env,
                       capture_output=True, text=True)
    out = r.stdout + r.stderr
    assert r.returncode == 0, f"recovery must succeed: {out}"
    assert "RECOVERED" in out and "server-rescue-" in out

    rescue = g(origin, "for-each-ref", "--format=%(refname:short)",
               "refs/heads/server-rescue-*").strip()
    assert rescue, "the local edit must be parked on a pushed rescue branch"
    assert "1 Baz" in g(origin, "show", f"{rescue}:data/decks/a.txt"), \
        "the rescued commit must carry the server's edit"
    assert (server / "data" / "decks" / "a.txt").read_text(encoding="utf-8") == "1 Bar\n", \
        "the clone must end on upstream's content"
    assert g(server, "status", "--porcelain").strip() == "", "and be clean"
    assert g(server, "rev-parse", "HEAD") == g(origin, "rev-parse", "main"), \
        "HEAD must equal origin/main so tomorrow's sync fast-forwards"


def test_status_view_keeps_a_recovered_sync_visible(clean_env):
    """RECOVERED is a success with homework (a rescue branch awaits merging) —
    it must render as warn with the script's own line, not a green 'synced'."""
    now = 1_000_000.0
    sync._write_status({"when": now - 60, "ok": True, "pulled": True,
                        "detail": "sync: RECOVERED — local edits parked on "
                                  "server-rescue-20260811 (pushed to GitHub)"})
    v = sync.status_view(now)
    assert v["cls"] == "warn" and "server-rescue-20260811" in v["text"]


def test_uncommitted_work_outside_the_tracked_paths_survives_a_self_heal(tmp_path):
    """The 2026-08-12 data-loss bug, end to end. The app saves a file the sync does
    NOT stage (anything outside TRACKED_DATA) while the pull is failing. The old
    script parked a rescue branch that could not contain it — `git branch -f` is
    HEAD-only — then reset --hard over it. Reproduced as unrecoverable before the
    fix: present in no branch, no stash, and not on disk."""
    env = _git_env(tmp_path)

    def g(cwd, *args):
        r = subprocess.run(["git", *args], cwd=str(cwd), env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0, f"git {args}: {r.stderr}"
        return r.stdout

    origin = tmp_path / "origin.git"
    origin.mkdir()
    g(origin, "init", "--bare", "--initial-branch=main", ".")
    seed = tmp_path / "seed"
    g(tmp_path, "clone", str(origin), "seed")
    (seed / "data" / "decks").mkdir(parents=True)
    (seed / "data" / "decks" / "a.txt").write_text("1 Foo\n", encoding="utf-8")
    (seed / "app.py").write_text("v1\n", encoding="utf-8")   # tracked, NOT in TRACKED_DATA
    (seed / "sync_server.sh").write_text(_script_src(), encoding="utf-8")
    g(seed, "add", "-A")
    g(seed, "commit", "-m", "seed")
    g(seed, "push", "-u", "origin", "main")

    server = tmp_path / "server"
    g(tmp_path, "clone", str(origin), "server")

    # Upstream rewrites the deck file (squash-merged PR) so the rebase will conflict…
    (seed / "data" / "decks" / "a.txt").write_text("1 Bar\n", encoding="utf-8")
    g(seed, "commit", "-am", "pr rewrite")
    g(seed, "push")
    # …the server has its own committed deck edit on that same file…
    (server / "data" / "decks" / "a.txt").write_text("1 Baz\n", encoding="utf-8")
    g(server, "add", "-A")
    g(server, "commit", "-m", "server deck edit")
    # …and the app writes an UNCOMMITTED file the sync never stages.
    (server / "app.py").write_text("PRECIOUS-UNCOMMITTED\n", encoding="utf-8")

    r = subprocess.run(["bash", "sync_server.sh"], cwd=str(server), env=env,
                       capture_output=True, text=True)
    out = r.stdout + r.stderr

    on_disk = (server / "app.py").read_text(encoding="utf-8")
    stashed = "PRECIOUS" in g(server, "stash", "list")
    assert "PRECIOUS" in on_disk or stashed, (
        "uncommitted work was destroyed by the self-heal — it must be restored to "
        f"the tree or preserved in a stash. output:\n{out}"
    )
