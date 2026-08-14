"""The memo cache — and, more importantly, the proof that memoizing the analysis
pipeline did not turn shared objects into a correctness bug.

Two classes of test live here:

  * the module's own contract (keys are file identity, eviction, invalidation,
    the lock), and
  * the **tripwire**: two dashboard renders of the same deck must be
    byte-identical, including after an interleaved optimizer preview and cut
    ranking. `analyze_deck` hands every caller the same `report` dict and the
    same enriched `Card` list; if any consumer mutates what it was lent, the
    second render diverges and this file is where that shows up. A failure here
    means "find the mutator", never "loosen the assertion".
"""
import os
import threading
import time

import pytest

import build_dashboard as bd
import deckcore
import memo
import mtglib
import optimize


# --------------------------------------------------------------------------- #
# The module contract
# --------------------------------------------------------------------------- #
def test_get_builds_once_then_hits():
    calls = []

    def build():
        calls.append(1)
        return {"n": len(calls)}

    a = memo.get(("k",), build)
    b = memo.get(("k",), build)
    assert calls == [1]
    assert a is b, "a hit must return the very object that was stored"


def test_stat_key_tracks_touch_delete_and_create(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("one", encoding="utf-8")
    k1 = memo.stat_key(str(p))
    time.sleep(0.01)
    p.write_text("two", encoding="utf-8")          # same size, new mtime
    k2 = memo.stat_key(str(p))
    assert k1 != k2, "an in-place edit of identical length must still change the key"

    p.write_text("longer text", encoding="utf-8")
    assert memo.stat_key(str(p)) != k2

    missing = str(tmp_path / "nope.txt")
    kmiss = memo.stat_key(missing)
    assert kmiss == ((missing, None),), "a missing file keys as (path, None)"
    (tmp_path / "nope.txt").write_text("x", encoding="utf-8")
    assert memo.stat_key(missing) != kmiss, "creating the file must invalidate"


def test_eviction_is_oldest_first(monkeypatch):
    monkeypatch.setattr(memo, "MAX_ENTRIES", 3)
    for i in range(5):
        memo.get((f"key-{i}",), lambda i=i: i)
    assert memo.size() == 3
    rebuilt = []
    memo.get(("key-0",), lambda: rebuilt.append(1) or 0)
    assert rebuilt == [1], "the oldest entry should have been evicted"


def test_invalidate_substring_and_all():
    memo.get(("deck", "/decks/ur-dragon.txt"), lambda: 1)
    memo.get(("deck", "/decks/yshtola.txt"), lambda: 2)
    assert memo.invalidate("ur-dragon") == 1
    assert memo.size() == 1
    assert memo.invalidate() == 1
    assert memo.size() == 0


def test_a_lock_exists():
    """Pinned deliberately: the hosted app serves requests while the daily sync
    thread runs, so an unguarded dict here is a live race. A refactor that
    'simplifies' the lock away should fail a test, not a request."""
    assert isinstance(memo._LOCK, type(threading.Lock()))


# --------------------------------------------------------------------------- #
# load_collection: the key is the MERGED input set, not just the CSV
# --------------------------------------------------------------------------- #
def test_load_collection_parses_once(collection_file, monkeypatch):
    calls = []
    real = mtglib.parse_collection
    monkeypatch.setattr(mtglib, "parse_collection",
                        lambda text: calls.append(1) or real(text))
    a = mtglib.load_collection(collection_file)
    b = mtglib.load_collection(collection_file)
    assert len(calls) == 1, "the second load must not re-parse"
    assert a is b


def test_owned_additions_invalidate_the_collection(collection_file, monkeypatch):
    """The part a naive implementation gets wrong: keying on the CSV alone would
    ignore the overlay files `load_collection` merges, and the player's own
    'I do own this' file would never take effect until the export changed."""
    calls = []
    real = mtglib.parse_collection
    monkeypatch.setattr(mtglib, "parse_collection",
                        lambda text: calls.append(1) or real(text))
    first = mtglib.load_collection(collection_file)
    assert mtglib.lookup(mtglib.index_by_name(first), "Rhystic Study") is None

    add = os.path.join(os.path.dirname(collection_file), "owned_additions.txt")
    with open(add, "w", encoding="utf-8") as f:
        f.write("1 Rhystic Study\n")
    second = mtglib.load_collection(collection_file)
    assert len(calls) > 1, "creating owned_additions.txt must invalidate the load"
    assert mtglib.lookup(mtglib.index_by_name(second), "Rhystic Study") is not None


def test_attrs_overlay_is_in_the_key(collection_file):
    inputs = mtglib.collection_inputs(collection_file)
    names = {os.path.basename(p) for p in inputs}
    assert names >= {"owned_additions.txt", "owned_additions.csv",
                     "collection_attrs.csv", "collection_attrs.snapshot.csv"}
    assert inputs[0] == collection_file


# --------------------------------------------------------------------------- #
# analyze_deck: cached on paths, bypassed on unfingerprintable inputs
# --------------------------------------------------------------------------- #
def test_analyze_deck_cached_on_paths(deck_file, collection_file):
    a = deckcore.analyze_deck(deck_file, collection_file)
    b = deckcore.analyze_deck(deck_file, collection_file)
    assert a is not b, "the outer dict is copied per call"
    assert a["report"] is b["report"], "…but the analysis itself is reused"
    assert a["enriched"] is b["enriched"]


def test_list_collection_and_refs_bypass_the_cache(deck_file, collection_file):
    import power
    coll = mtglib.load_collection(collection_file)
    before = memo.size()
    deckcore.analyze_deck(deck_file, coll)
    assert memo.size() == before, "a loaded list cannot be fingerprinted — no entry"
    deckcore.analyze_deck(deck_file, collection_file, refs=power.load_refs())
    assert memo.size() == before, "caller-supplied refs cannot be fingerprinted either"


def test_deck_edit_invalidates_analysis(deck_file, collection_file):
    a = deckcore.analyze_deck(deck_file, collection_file)
    n = len(a["deck"])
    time.sleep(0.01)
    with open(deck_file, "a", encoding="utf-8") as f:
        f.write("1 Serra Angel\n")
    b = deckcore.analyze_deck(deck_file, collection_file)
    assert len(b["deck"]) == n + 1


def test_reference_edit_invalidates_analysis(deck_file, collection_file, tmp_path,
                                             monkeypatch):
    """A bracket verdict moves when `game_changers.txt` moves. Keying only on the
    deck and the collection would cache straight through a reference edit."""
    refdir = tmp_path / "reference"
    refdir.mkdir()
    (refdir / "game_changers.txt").write_text("# none\n", encoding="utf-8")
    monkeypatch.setattr(deckcore, "REF_DIR", str(refdir))
    k1 = deckcore._reference_key()
    time.sleep(0.01)
    (refdir / "game_changers.txt").write_text("Sol Ring\n", encoding="utf-8")
    assert deckcore._reference_key() != k1


# --------------------------------------------------------------------------- #
# The tripwire — shared values must survive every consumer that borrows them
# --------------------------------------------------------------------------- #
def _render(deck_file, collection_file):
    return bd.generate(deck_file, collection_file, title="T", commander="Test Commander",
                       sim=None)["dashboard"]


def test_two_renders_are_byte_identical(deck_file, collection_file):
    assert _render(deck_file, collection_file) == _render(deck_file, collection_file)


def test_render_survives_interleaved_optimizer_and_cut_ranking(deck_file,
                                                               collection_file):
    """Warm cache, run the read-only surfaces that borrow the same analysis, then
    render again — and compare against a render from a COLD cache. A consumer
    that mutates `report`, `enriched` or a collection `Card` shows up here as a
    diff, which is the only cheap way to detect it."""
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    decks_dir = os.path.dirname(deck_file)

    _render(deck_file, collection_file)                 # warm
    try:
        optimize.optimize(deck_file, coll, idx, decks_dir, apply=False)
    except Exception:
        pass                                            # offline field data is fine
    try:
        optimize.cut_candidates(deck_file, collection_file, idx, decks_dir)
    except Exception:
        pass
    warm = _render(deck_file, collection_file)

    memo.invalidate()
    cold = _render(deck_file, collection_file)
    assert warm == cold, (
        "a consumer mutated a cached analysis — find the mutator; do not relax "
        "this assertion (see docs/spec-infra-hot-paths.md §1b)")


def _fingerprint(a):
    """Everything a consumer could scribble on, flattened to a comparable string.

    The byte-identical render above only catches mutations that reach the HTML —
    a mutated `quantity` on a borrowed `Card` sails straight past it (verified:
    it does). This looks at the cached objects themselves, so ANY mutation of a
    shared value is a diff, rendered or not."""
    cards = [(c.name, c.quantity, c.mana_value, sorted(c.identity or []),
              tuple(c.types or []), sorted(c.produced or []), sorted(c.flags or []),
              c.power)
             for c in a["enriched"]]
    return repr((cards, sorted((a["report"] or {}).items(), key=repr),
                 sorted((a["assessment"] or {}).items(), key=repr),
                 sorted((a["mana"] or {}).items(), key=repr),
                 len(a["coll"]), len(a["idx"])))


def test_consumers_do_not_mutate_the_shared_analysis(deck_file, collection_file):
    """The audit, executed. Warm the cache, then run every read-only surface that
    borrows the analysis, and assert the cached objects came back untouched.

    A failure names a mutator: fix the CALLER to copy what it needs. Deep-copying
    inside the cache is not the answer — 2,621 `Card`s per hit costs more than
    the analysis it replaces."""
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    decks_dir = os.path.dirname(deck_file)

    a = deckcore.analyze_deck(deck_file, collection_file)
    before = _fingerprint(a)

    _render(deck_file, collection_file)
    for run in (lambda: optimize.optimize(deck_file, coll, idx, decks_dir, apply=False),
                lambda: optimize.cut_candidates(deck_file, collection_file, idx, decks_dir),
                lambda: deckcore.advise_card(deck_file, collection_file, "Sol Ring")):
        try:
            run()
        except Exception:
            pass                        # offline field data is a degrade, not a fail
    _render(deck_file, collection_file)

    assert _fingerprint(deckcore.analyze_deck(deck_file, collection_file)) == before


def test_analysis_dict_copy_isolates_callers(deck_file, collection_file):
    a = deckcore.analyze_deck(deck_file, collection_file)
    a["sim"] = "mine"
    b = deckcore.analyze_deck(deck_file, collection_file)
    assert "sim" not in b, "a top-level key added by one caller must not leak"


# --------------------------------------------------------------------------- #
# The coarse-clock host: why explicit invalidation exists at all
# --------------------------------------------------------------------------- #
def test_same_mtime_same_size_edit_is_not_served_stale(tmp_path, monkeypatch):
    """PythonAnywhere's filesystem may report mtimes coarser than a card-panel
    edit takes, and the panel redirects straight into a re-render. Forcing the
    mtime back simulates that exactly: the stat key is IDENTICAL, so only the
    write path's explicit `_invalidate` can save the reader.

    This is the test that justifies those calls existing; delete them and it
    fails."""
    import app as appmod        # conftest puts webapp/ on the path — the repo's
                                # one import form for it (`webapp.app` resolves
                                # locally as a namespace package and NOT on CI)
    p = tmp_path / "collection.csv"
    from conftest import COLLECTION_CSV
    p.write_text(COLLECTION_CSV, encoding="utf-8")
    first = mtglib.load_collection(str(p))
    st = os.stat(str(p))

    swapped = COLLECTION_CSV.replace("Serra Angel", "Serra Angle")   # same length
    p.write_text(swapped, encoding="utf-8")
    os.utime(str(p), ns=(st.st_atime_ns, st.st_mtime_ns))            # coarse clock
    assert memo.stat_key(str(p)) == memo.stat_key(str(p))
    stale = mtglib.load_collection(str(p))
    assert stale is first, "precondition: the mtime key genuinely cannot see this"

    appmod._invalidate()                       # what every write route calls
    fresh = mtglib.load_collection(str(p))
    assert fresh is not first
    assert mtglib.lookup(mtglib.index_by_name(fresh), "Serra Angle") is not None


def test_post_requests_drop_the_cache(tmp_path, monkeypatch):
    """The backstop: a write route someone forgets to annotate still cannot serve
    stale analysis past the end of its own request."""
    import app as appmod
    memo.get(("sentinel",), lambda: 1)
    client = appmod.app.test_client()
    with appmod.app.test_request_context("/", method="POST"):
        appmod._invalidate_after_write(appmod.app.response_class())
    assert memo.size() == 0
    assert client is not None
