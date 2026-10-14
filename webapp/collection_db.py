"""The sync's collection-database step (docs/spec-target-architecture.md, Phase 1).

Run by sync_server.sh after every pull. Two jobs, and it never fails the sync:

  * **First run: seed.** No database yet → build it once from every record of the
    player's cards: the server's private export (when there is one), the committed
    August list, every block in owned_additions.txt, and every sleeved deck. The
    union rules and the report live in `store.seed`. From then on the app reads and
    writes the database, and exports become merges.
  * **Every later run: ingest.** Batches a Claude session committed to
    owned_additions.txt arrive with the pull; each new block is applied once.

Then, every run, **decks and pins** (Phase 1b): if the deck folder is gone (a new
host, or a repo that no longer carries data) it is rebuilt from the database;
otherwise every deck file and pins.csv that changed (a session's committed edit,
arriving with the pull) is recorded as a revision. App edits are captured as they
happen, by the app itself.

And **the activity log**: rows an app still running on files appended to
data/activity.csv (the seconds between a deploy's pull and its reload) move into the
database's `activity` table, each exactly once. MEMBERS are deliberately not touched
here: the app takes users.json in on its own first read after the reload, so the
app that is still running during this sync never finds its member file gone.

And FIRST, before any of that changes the database: **the daily backup**, a
consistent copy in data/collection/backups/ (gitignored, owner-only, the newest
MTG_BACKUPS_KEEP kept, 7 by default). To undo a bad day, put a copy back from a
console (`cp data/collection/backups/collection-<date>.db data/collection/collection.db`)
and reload the web app.

`MTG_COLLECTION` set to anything but the database means the operator chose another
source on purpose: this step then does nothing.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

COLL_DIR = os.path.join(ROOT, "data", "collection")
DB = os.path.join(COLL_DIR, "collection.db")
EXPORT = os.path.join(COLL_DIR, "collection.csv")
AUGUST = os.path.join(COLL_DIR, "collection_snapshot.txt")
ADDITIONS = os.path.join(COLL_DIR, "owned_additions.txt")
DECKS = os.environ.get("MTG_DECKS_DIR", os.path.join(ROOT, "data", "decks"))
PINS = os.path.join(COLL_DIR, "pins.csv")
# Beside the deck folder, exactly where the app writes it (app._activity_path).
ACTIVITY = os.path.join(os.path.dirname(os.path.abspath(DECKS)), "activity.csv")
BACKUPS = os.path.join(COLL_DIR, "backups")


def _keep():
    try:
        return max(1, int(os.environ.get("MTG_BACKUPS_KEEP", "7")))
    except ValueError:
        return 7


def backup_step(db, backups=None):
    """Today's copy, taken before the sync changes anything. -> a phrase, or "".
    A failed backup is reported, and never stops the sync."""
    import store
    try:
        made = store.daily_backup(db, backups or BACKUPS, keep=_keep())
    except Exception as e:                       # noqa: BLE001
        return f"backup: FAILED ({type(e).__name__}: {e})"
    return f"backup: saved {os.path.basename(made)}" if made else ""


def decks_step(db, decks=DECKS, pins=PINS):
    """Rebuild a missing working copy, else capture what changed. -> a phrase."""
    import store
    if store.deck_working_copy_missing(decks) and store.stored_files(db):
        written = store.restore(db, decks, pins, by="sync")
        return f"decks: RESTORED {len(written)} file(s) from the database"
    r = store.capture(db, decks, pins, action="sync", by="sync")
    if r["added"] or r["changed"] or r["removed"]:
        return (f"decks: saved {r['added']} new, {r['changed']} changed, "
                f"{r['removed']} removed file(s)")
    return "decks: up to date"


def activity_step(db, activity=None):
    """Take in activity.csv rows the database hasn't seen. -> a phrase, or "".
    A bad file costs this phrase, never the rest of the sync's line."""
    import store
    try:
        n = store.import_activity(db, activity or ACTIVITY)
    except Exception as e:                       # noqa: BLE001
        return f"activity: skipped ({type(e).__name__}: {e})"
    return f"activity: took in {n} row(s) from activity.csv" if n else ""


def run(db=DB, export=EXPORT, august=AUGUST, additions=ADDITIONS, decks=DECKS, pins=PINS,
        activity=None, backups=None):
    """-> one line for the sync log. `activity` and `backups` resolve to the module's
    paths when CALLED, so the test suite can point them at tmp once (conftest)."""
    import store
    env = os.environ.get("MTG_COLLECTION")
    if env and os.path.abspath(env) != os.path.abspath(db):
        return f"collection db: skipped (MTG_COLLECTION points at {os.path.basename(env)})"
    saved = backup_step(db, backups) if store.exists(db) else ""
    line = _collection_step(db, export, august, additions, decks)
    parts = [line, decks_step(db, decks, pins), activity_step(db, activity), saved]
    return " · ".join(p for p in parts if p)


def _collection_step(db, export, august, additions, decks):
    import store
    if not store.exists(db):
        report = store.seed(db, export if os.path.exists(export) else None,
                            august if os.path.exists(august) else None,
                            additions, decks, write=True)
        lines = report.splitlines()
        return ("collection db: SEEDED — " + (lines[2] if len(lines) > 2 else "") +
                " The full report is on the Collection page.")
    blocks, copies = store.ingest(db, additions)
    if blocks:
        return f"collection db: ingested {blocks} new batch(es), {copies} cop(ies)"
    return "collection db: up to date"


def main():
    try:
        print("sync: " + run())
    except Exception as e:                       # never fail the sync
        print(f"sync: collection db skipped ({type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
