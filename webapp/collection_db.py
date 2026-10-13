"""The sync's collection-database step (docs/spec-target-architecture.md, Phase 1).

Run by sync_server.sh after every pull. Two jobs, and it never fails the sync:

  * **First run: seed.** No database yet → build it once from every record of the
    player's cards: the server's private export (when there is one), the committed
    August list, every block in owned_additions.txt, and every sleeved deck. The
    union rules and the report live in `store.seed`. From then on the app reads and
    writes the database, and exports become merges.
  * **Every later run: ingest.** Batches a Claude session committed to
    owned_additions.txt arrive with the pull; each new block is applied once.

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


def run(db=DB, export=EXPORT, august=AUGUST, additions=ADDITIONS, decks=DECKS):
    """-> one line for the sync log."""
    import store
    env = os.environ.get("MTG_COLLECTION")
    if env and os.path.abspath(env) != os.path.abspath(db):
        return f"collection db: skipped (MTG_COLLECTION points at {os.path.basename(env)})"
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
