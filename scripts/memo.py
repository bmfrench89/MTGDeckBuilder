"""A process-level memo cache keyed on file identity — the one place the repo is
allowed to skip work it has already done.

Why this exists: the app moved from "render precomputed things" to "run engines
inline per request", and the two hot loaders became the whole load profile.
Measured 2026-08-13 on 2,621 cards: `mtglib.load_collection` ≈ 54 ms,
`deckcore.analyze_deck` ≈ 48 ms — and a single deck page can pay both several
times over (the dashboard, the singleton check, the optimizer preview the assess
packet runs). On PythonAnywhere's free tier, which is 2–4× slower, that is the
difference between a page and a wait.

The contract, in three lines:

  * **Keys are file identity, never time.** `stat_key` fingerprints
    `(path, mtime_ns, size)` for every file a build actually reads — the same
    semantics as `goldfish._stat`, including `(path, None)` for a file that does
    not exist, so that *creating* it later is a miss rather than a silent stale
    hit. Nothing here expires on a clock; there is no TTL to tune.
  * **Cached values are shared and must be treated as frozen.** A hit hands back
    the very object a previous caller got. Deep-copying would cost more than the
    build it replaces (2,621 `Card`s per hit), so the discipline lives in the
    callers instead: `deckcore.analyze_deck` returns a shallow copy of its dict,
    and `tests/test_memo.py`'s byte-identical tripwire is what proves no consumer
    mutates what it was lent.
  * **Belt AND suspenders.** mtime granularity is a filesystem property, not a
    guarantee; a same-second, same-size edit (replacing a card with an
    equal-length name) is a real scenario in the card panel, which redirects
    straight into a re-render. Every app write path therefore calls
    `invalidate()` explicitly. The mtime key is the cheap common case; the
    explicit call is the correctness one.

Stdlib only, and it imports nothing from this repo: `mtglib` and `deckcore`
import *it*, so it sits below the hubs in the dependency order and can never
become part of a cycle.
"""
import os
import threading

# Small on purpose. The working set is "the decks and collections one process
# actually touches" — six decks × (collection + analysis) fits comfortably, and a
# cap this size keeps a pathological caller (a CLI sweeping 200 files) from
# holding every enriched card list it ever built. Insertion-ordered dicts make
# oldest-first eviction one `next(iter(...))`; an LRU library would be a
# dependency, and `scripts/` is stdlib-only.
MAX_ENTRIES = 32

_LOCK = threading.Lock()
_CACHE = {}


def stat_key(*paths):
    """`(path, mtime_ns, size)` per path — `(path, None)` when it does not exist.

    Nanoseconds, not whole seconds: two edits inside one second are exactly the
    case where a stale entry would look fresh. The missing-file form is
    load-bearing — `load_collection` merges optional overlay files, and one
    appearing must invalidate every key that was built without it."""
    out = []
    for p in paths:
        try:
            st = os.stat(p)
        except OSError:
            out.append((p, None))
        else:
            out.append((p, st.st_mtime_ns, st.st_size))
    return tuple(out)


def _key(key_parts):
    """The stored key: `repr` of whatever the caller passed.

    A string key means unhashable parts (a list of paths) can't blow up at the
    call site, and it gives `invalidate(substr)` an exact, obvious meaning —
    substring of this repr. Every key here embeds real file paths, so
    `invalidate("ur-dragon")` reaches every entry that read that deck."""
    return repr(key_parts)


def get(key_parts, build):
    """Cached `build()` for `key_parts`, computing it at most once per key.

    `build` runs OUTSIDE the lock deliberately. Holding a global lock across a
    54 ms parse would serialize every request in the process — the exact cost
    this module exists to remove — so two threads racing the same cold key may
    both build, and the later one wins. That is harmless because every builder
    here is a pure function of the files in its key: the two results are equal,
    and neither is wrong."""
    k = _key(key_parts)
    with _LOCK:
        if k in _CACHE:
            return _CACHE[k]
    val = build()
    with _LOCK:
        _CACHE[k] = val
        while len(_CACHE) > MAX_ENTRIES:
            _CACHE.pop(next(iter(_CACHE)))          # oldest inserted
    return val


def invalidate(substr=None):
    """Drop cached entries. `None` drops everything; a string drops every entry
    whose key repr contains it (a deck stem, a collection path).

    Returns the number of entries dropped, which is what makes an invalidation
    testable rather than a hopeful no-op."""
    with _LOCK:
        if substr is None:
            n = len(_CACHE)
            _CACHE.clear()
            return n
        doomed = [k for k in _CACHE if substr in k]
        for k in doomed:
            del _CACHE[k]
        return len(doomed)


def size():
    """Entry count — for tests and for anyone debugging a suspected stale hit."""
    with _LOCK:
        return len(_CACHE)
