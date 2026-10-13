#!/usr/bin/env python3
"""Keep the repo's copy of the collection current: rewrite the committed name-only
list (`data/collection/collection_snapshot.txt`) from the server's private export, so
sessions and the GitHub Actions read the collection the app reads.

Run by `sync_server.sh` just before it stages, and it only ever writes that one file.
It writes nothing unless all three hold:

  1. **The repo is provably private.** An anonymous `git ls-remote` of origin, with
     credentials stripped from the URL and every credential helper switched off, has
     to be REFUSED for want of a login. If it succeeds, the repo is public; if it fails
     any other way (network, an ssh remote), that is unknown. Both mean skip, so a
     public repo, or a repo made public again later, never receives a fresh copy of
     the collection.
  2. **The export looks like a whole collection.** That is the Upload guard's own
     judgement (`intake.upload_looks_partial`) against the list already committed.
     A file that would make every deck read as unowned is refused here as well.
  3. **The cards actually changed.** The comparison is of (name, quantity) pairs, so
     an unchanged export makes no commit and no attrs-snapshot run.

What it writes is names and quantities only: no prices, printings, conditions, dates
or sellers, however rich the export. The added-cards file (`owned_additions.txt`) is
not folded in. `load_collection` adds those quantities on top of this list, so
including them would count every added card twice.

Never raises into the sync: it prints one `sync: …` line and exits 0 whatever happens.
"""
import datetime
import os
import subprocess
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
SNAPSHOT = os.path.join(ROOT, "data", "collection", "collection_snapshot.txt")
if SCRIPTS not in sys.path:      # run as a plain script from sync_server.sh
    sys.path.insert(0, SCRIPTS)

# What GitHub's anonymous refusal looks like once prompts and helpers are off. A
# private repo and a missing one answer identically, which is fine: either way
# nothing public is reading it.
_AUTH_REFUSED = ("could not read username", "terminal prompts disabled",
                 "authentication failed", "repository not found")

HEADER = """\
# MTG Collection snapshot (name-only): the repo's copy of the player's collection.
# Date captured: {date}. Format: '<quantity> <card name>' per line.
# Written by the server sync from the private collection.csv: names and quantities only
# (no prices, printings, dates or sellers), and only while the repo is private.
# Cards added in the app live in owned_additions.txt and are NOT repeated here.
# Grounding: this is the source of truth for OWNERSHIP counts (Rule #1).
"""


def anonymous_url(url):
    """origin's URL with any `user:token@` removed, or None when it can't be tested
    anonymously (an ssh or file remote)."""
    try:
        p = urllib.parse.urlsplit((url or "").strip())
    except ValueError:
        return None
    if p.scheme not in ("https", "http") or not p.hostname:
        return None
    host = p.hostname + (f":{p.port}" if p.port else "")
    return urllib.parse.urlunsplit((p.scheme, host, p.path, "", ""))


def _git(args, root, env=None, timeout=30):
    return subprocess.run(["git", *args], cwd=root, env=env, capture_output=True,
                          text=True, timeout=timeout)


def repo_visibility(root=ROOT, run=_git):
    """"private", "public" or "unknown", from what an anonymous reader is allowed."""
    try:
        url = run(["remote", "get-url", "origin"], root).stdout
    except Exception:
        return "unknown"
    anon = anonymous_url(url)
    # Only GitHub's own answer means anything: a mirror or proxy that demands a login
    # from everyone would read as "private" while the real repo sits public.
    if not anon or urllib.parse.urlsplit(anon).hostname != "github.com":
        return "unknown"
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "",
           "SSH_ASKPASS": "", "GCM_INTERACTIVE": "never"}
    try:
        r = run(["-c", "credential.helper=", "ls-remote", "--heads", anon], root,
                env=env)
    except Exception:
        return "unknown"
    if r.returncode == 0:
        return "public"
    err = (r.stderr or "").lower()
    return "private" if any(s in err for s in _AUTH_REFUSED) else "unknown"


def _private_export():
    """The private export the app reads (same precedence as webapp/sync.py), or None
    when there isn't one. The committed list itself is never its own source."""
    env = os.environ.get("MTG_COLLECTION")
    path = env or os.path.join(ROOT, "data", "collection", "collection.csv")
    if not os.path.isfile(path) or os.path.abspath(path) == os.path.abspath(SNAPSHOT):
        return None
    return path


def name_counts(cards):
    """[(name, qty)] summed per card (an export has a row per printing), sorted the
    way the committed list always has been: by name, case-insensitively."""
    import mtglib
    agg = {}
    for c in cards:
        name = (c.name or "").strip()
        if not name or c.quantity <= 0:
            continue
        k = mtglib._norm(name)
        if k in agg:
            agg[k][1] += c.quantity
        else:
            agg[k] = [name, c.quantity]
    return sorted(((n, q) for n, q in agg.values()), key=lambda x: (x[0].lower(), x[0]))


def snapshot_text(counts, date):
    return HEADER.format(date=date) + "".join(f"{q} {n}\n" for n, q in counts)


def refresh(export_path, snapshot_path=SNAPSHOT, today=None):
    """Rewrite the committed list from the export when the cards differ.
    -> (changed?, message). The visibility gate is the caller's job (`main`)."""
    import intake
    import mtglib
    with open(export_path, encoding="utf-8-sig") as f:
        new_cards = mtglib.parse_collection(f.read())
    old_cards = []
    if os.path.exists(snapshot_path):
        with open(snapshot_path, encoding="utf-8") as f:
            old_cards = mtglib.parse_collection(f.read())
    new, old = name_counts(new_cards), name_counts(old_cards)
    if not new:
        return False, "the private export has no cards; left the collection list alone"
    partial, facts = intake.upload_looks_partial(old_cards, new_cards)
    if partial:
        return False, (f"the private export looks partial ({facts['file_unique']} cards "
                       f"against {facts['current_unique']} in the list); left it alone")
    if new == old:
        return False, "collection list already current"
    date = today or datetime.date.today().isoformat()
    tmp = snapshot_path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(snapshot_text(new, date))
    os.replace(tmp, snapshot_path)
    added = {n for n, _ in new} - {n for n, _ in old}
    gone = {n for n, _ in old} - {n for n, _ in new}
    return True, (f"collection list refreshed: {len(new)} cards, "
                  f"{sum(q for _, q in new)} copies (+{len(added)} new, "
                  f"-{len(gone)} gone)")


def main():
    try:
        export = _private_export()
        if not export:
            print("sync: no private export on this machine; collection list unchanged")
            return 0
        vis = repo_visibility()
        if vis != "private":
            why = ("the repo is public" if vis == "public"
                   else "could not confirm the repo is private")
            print(f"sync: {why}, so the collection list was not refreshed")
            return 0
        _, msg = refresh(export)
        print(f"sync: {msg}")
    except Exception as e:                     # never block the sync
        print(f"sync: collection list refresh skipped ({type(e).__name__})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
