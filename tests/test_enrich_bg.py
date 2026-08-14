"""Background upload enrichment — the standing known-deferred item, closed.

What matters here is not speed, it is the four ways backgrounding a long job can
lie to the player: a request that claims to have finished work it only started; a
second upload racing the first; a thread that dies with the app reload and leaves
a spinner running forever; and a reader that catches the attrs file half-written
and reports the missing half as *unenriched* — a wrong answer wearing an honest
label. One test each.

Offline and hermetic: the enrich function is always injected, so nothing here
goes near Scryfall.
"""
import csv
import json
import os
import threading
import time

import pytest

import carddb
import enrich_bg


@pytest.fixture(autouse=True)
def _status_in_tmp(tmp_path, monkeypatch):
    """The status file lives under the real `data/cache/` in production. Point it
    at tmp for every test here — the suite never writes into the player's data."""
    monkeypatch.setattr(enrich_bg, "STATUS", str(tmp_path / "enrich_status.json"))


def test_start_returns_before_the_work_finishes(tmp_path):
    """The whole point: the request comes back while Scryfall is still being
    asked. A synchronous enrichment of a real collection is minutes long."""
    release = threading.Event()
    finished = threading.Event()

    def slow(_csv, _out):
        release.wait(5)
        finished.set()
        return 3, 3, []

    msg = enrich_bg.start("c.csv", str(tmp_path / "attrs.csv"), enrich=slow)
    assert "background" in msg
    assert not finished.is_set(), "start() waited for the enrichment"
    assert enrich_bg.running() is True
    release.set()
    for _ in range(200):                       # let the daemon thread land
        if enrich_bg.status().get("state") == "done":
            break
        time.sleep(0.01)
    st = enrich_bg.status()
    assert st["state"] == "done" and st["matched"] == 3


def test_a_second_upload_is_refused_while_one_is_live(tmp_path):
    """Two threads writing one attrs file is non-corrupting (the write is atomic)
    but arbitrary — whichever finishes last wins, which is not a decision anyone
    made."""
    release = threading.Event()
    started = []

    def slow(_csv, _out):
        started.append(1)
        release.wait(5)
        return 1, 1, []

    enrich_bg.start("c.csv", str(tmp_path / "a.csv"), enrich=slow)
    msg = enrich_bg.start("c.csv", str(tmp_path / "a.csv"), enrich=slow)
    assert "already running" in msg
    release.set()
    time.sleep(0.05)
    assert len(started) == 1


def test_a_failure_is_recorded_as_a_status_not_a_traceback(tmp_path):
    def boom(_csv, _out):
        raise OSError("scryfall unreachable")

    enrich_bg.start("c.csv", str(tmp_path / "a.csv"), enrich=boom, thread=False)
    st = enrich_bg.status()
    assert st["state"] == "error" and "unreachable" in st["detail"]
    view = enrich_bg.status_view()
    assert view["cls"] == "warn" and "failed" in view["text"]


def test_a_dead_thread_renders_as_interrupted_not_running(tmp_path):
    """PythonAnywhere kills daemon threads on app reload — a deploy, the daily
    sync's own reload, the WSGI touch. The status file is all that is left, and
    it still says `running`. Past the TTL that has to read as what it is."""
    enrich_bg._write_status({"when": time.time() - 60, "state": "running",
                             "matched": 0, "total": 0, "detail": ""})
    assert enrich_bg.status_view()["cls"] == "muted"
    assert "running" in enrich_bg.status_view()["text"]

    old = time.time() - enrich_bg.STALE_RUNNING - 1
    enrich_bg._write_status({"when": old, "state": "running", "matched": 0,
                             "total": 0, "detail": ""})
    view = enrich_bg.status_view()
    assert view["cls"] == "warn"
    assert "interrupted" in view["text"] and "re-upload" in view["text"]
    assert enrich_bg.running() is False, "a stale run must not block a new upload"


def test_no_status_file_renders_nothing(tmp_path):
    assert enrich_bg.status_view() is None
    assert enrich_bg.running() is False


def test_the_run_invalidates_the_memo_cache(tmp_path, collection_file):
    """Phase 1's cache is holding the PRE-enrichment collection. The mtime key
    would notice on its own, but the thread and the next reader are racing."""
    import memo
    import mtglib
    mtglib.load_collection(collection_file)
    assert memo.size() > 0
    enrich_bg.start(collection_file, str(tmp_path / "a.csv"),
                    enrich=lambda *a: (1, 1, []), thread=False)
    assert memo.size() == 0


# --------------------------------------------------------------------------- #
# The atomic write — fixed in carddb, so every caller inherits it
# --------------------------------------------------------------------------- #
def test_attrs_are_written_atomically(tmp_path):
    """A reader must see the OLD file or the NEW one, never a truncated one.

    The window is not theoretical: enrichment now runs for minutes in a thread
    while the app serves pages, and a plain `open(…, "w")` truncates the real
    path for the whole of it. `load_collection` would then merge half an overlay
    and report the missing half as unenriched."""
    out = tmp_path / "collection_attrs.csv"
    out.write_text("Name,Type\nOld Card,Artifact\n", encoding="utf-8")

    seen = []

    class Rows:
        """Yields rows slowly, checking what a reader would see mid-write."""
        def __iter__(self):
            for i in range(3):
                seen.append(out.read_text(encoding="utf-8"))
                yield [f"New Card {i}", "Creature", "2", "G", "{1}{G}", "", "", "", "", ""]

    carddb.write_attrs_csv(str(out), carddb.ATTRS_HEADER, Rows())

    assert all(s == "Name,Type\nOld Card,Artifact\n" for s in seen), \
        "a reader saw the file mid-write — the write was not atomic"
    assert "New Card 2" in out.read_text(encoding="utf-8")
    assert not os.path.exists(str(out) + ".part"), "the tmp file must be renamed away"


def test_both_enrichment_paths_use_the_atomic_writer():
    """One fix, every caller safe — the spec's instruction, pinned. A future
    edit that re-opens the destination directly in either path fails here."""
    src = open(carddb.__file__, encoding="utf-8").read()
    body = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
    assert body.count("write_attrs_csv(") >= 3, \
        "expected the definition plus both enrich paths calling it"
    assert 'open(out_path, "w"' not in body, \
        "an enrichment path is writing the attrs file non-atomically again"


def test_the_enriched_file_is_still_correct_csv(tmp_path):
    out = tmp_path / "a.csv"
    carddb.write_attrs_csv(str(out), carddb.ATTRS_HEADER,
                           [["Sol Ring", "Artifact", "1", "", "{1}", "", "id", "C",
                             "rock;ramp", ""]])
    with open(out, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == list(carddb.ATTRS_HEADER)
    assert rows[1][0] == "Sol Ring" and rows[1][8] == "rock;ramp"


# --------------------------------------------------------------------------- #
# The route
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(tmp_path, monkeypatch, collection_file):
    import app as appmod
    decks = tmp_path / "decks"
    decks.mkdir()
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", collection_file)
    monkeypatch.setattr(appmod, "COLLECTION_CSV", str(tmp_path / "uploaded.csv"))
    monkeypatch.setattr(appmod, "COLLECTION_ATTRS", str(tmp_path / "uploaded_attrs.csv"))
    monkeypatch.setattr(appmod, "PASSWORD", None)
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def test_upload_saves_the_csv_and_hands_enrichment_to_the_background(client, tmp_path,
                                                                     monkeypatch):
    import io
    started = []
    monkeypatch.setattr(enrich_bg, "start",
                        lambda csv_path, attrs, **k: started.append((csv_path, attrs))
                        or "Upload saved — enrichment is running in the background.")
    from conftest import COLLECTION_CSV as CSV_TEXT
    r = client.post("/collection/upload", data={
        "csv": (io.BytesIO(CSV_TEXT.encode()), "export.csv")},
        content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    assert (tmp_path / "uploaded.csv").exists(), "the export must still be saved"
    assert started == [(str(tmp_path / "uploaded.csv"),
                        str(tmp_path / "uploaded_attrs.csv"))]
    assert b"background" in r.data


def test_upload_never_writes_the_tracked_snapshot(client, tmp_path, monkeypatch):
    """CLAUDE.md's hard line, re-pinned while this route was being changed: the
    private CSV is the only destination. This closed a real leak once."""
    import io
    monkeypatch.setattr(enrich_bg, "start", lambda *a, **k: "ok")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    snapshot = os.path.join(root, "data", "collection", "collection_snapshot.txt")
    before = open(snapshot, encoding="utf-8").read() if os.path.exists(snapshot) else None
    client.post("/collection/upload", data={
        "csv": (io.BytesIO(b"Quantity,Name\n1,Sol Ring\n"), "export.csv")},
        content_type="multipart/form-data")
    after = open(snapshot, encoding="utf-8").read() if os.path.exists(snapshot) else None
    assert after == before, "an upload touched the committed name-only snapshot"


def test_the_collection_page_renders_the_enrichment_status(client, tmp_path):
    enrich_bg._write_status({"when": time.time(), "state": "done", "matched": 7,
                             "total": 9, "detail": ""})
    body = client.get("/collection").get_data(as_text=True)
    assert "7/9 cards matched" in body
    assert json.loads(open(enrich_bg.STATUS, encoding="utf-8").read())["state"] == "done"
