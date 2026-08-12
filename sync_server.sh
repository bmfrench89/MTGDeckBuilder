#!/usr/bin/env bash
# Sync deck edits made in the HOSTED web app back to GitHub, then pull code updates.
#
# Why this exists: on a hosted deploy the SERVER is the source of truth for
# data/decks/. The web app rewrites those files in place (card panel Remove/Replace,
# the deck editor, and the optimizer's .changes.csv appends), and they are git-tracked
# — so the server clone drifts from origin, and a later `git pull` for a code update
# would land in conflict. Run this before pulling, or on whatever cadence suits you.
#
# Private data never moves: data/collection/collection.csv and collection_attrs.csv are
# gitignored, so the explicit `git add` below cannot pick them up.
#
# One-time setup on the server (push needs credentials — a GitHub fine-grained PAT
# with Contents: read/write on this repo):
#   git remote set-url origin https://<user>:<token>@github.com/bmfrench89/MTGDeckBuilder.git
#
# Usage, from a PythonAnywhere bash console:
#   ~/MTGDeckBuilder/sync_server.sh
set -euo pipefail

cd "$(dirname "$0")"

# Exactly the paths the running app edits. Never `git add -A` — that would sweep in
# generated dashboards, caches, and anything else written at runtime.
# wishlist.md / manapool-wishlist.txt ARE runtime-edited (the ↻ Rebuild button runs
# refresh.py): leaving them unstaged dirtied the tree and made every subsequent
# `git pull --rebase` fail, wedging the daily sync until a console cleanup.
TRACKED_DATA=(
  data/decks
  data/collection/owned_additions.txt
  data/collection/pins.csv
  data/wishlist.md
  data/manapool-wishlist.txt
)

present=()
for p in "${TRACKED_DATA[@]}"; do
  [ -e "$p" ] && present+=("$p")
done

if [ ${#present[@]} -gt 0 ]; then
  git add -- "${present[@]}"
fi

if git diff --cached --quiet; then
  echo "sync: no deck changes to commit"
else
  git commit -m "Deck edits from the hosted app"
  echo "sync: committed deck edits"
fi

# --- Park uncommitted work before anything can destroy it ----------------------
# The self-heal below ends in `git reset --hard`, and `git branch -f` captures HEAD
# ONLY — so anything uncommitted is absent from the rescue branch when the reset
# runs, and is gone for good. Two real ways that bites:
#   * the app saves a deck during the seconds this script spends in `git pull`,
#     leaving an unstaged change to a tracked file (that also makes the pull itself
#     fail with "cannot pull with rebase: You have unstaged changes" — and in THAT
#     mode git aborts before fetching, so `@{u}` is stale too);
#   * an untracked file sits where a new upstream file is about to land.
# A stash ref survives both the rebase and the reset, so nothing uncommitted can
# reach them. Both cases were verified unrecoverable before this guard existed.
autostash=0
if [ -n "$(git status --porcelain)" ]; then
  if git stash push -u -q -m "sync-autostash $(date -u +%Y-%m-%dT%H:%M:%SZ)"; then
    autostash=1
    echo "sync: parked uncommitted work in a stash for the duration"
  else
    echo "sync: could not stash uncommitted work — aborting rather than risk it" >&2
    exit 1
  fi
fi

# Restore on EVERY exit path, including the failure ones `set -e` takes: a stash
# left behind would look to the next run like a clean tree with missing edits.
restore_autostash() {
  [ "$autostash" = "1" ] || return 0
  autostash=0
  if git stash pop -q 2>/dev/null; then
    echo "sync: restored uncommitted work"
  else
    # A conflicted pop writes conflict MARKERS into the working tree and keeps the
    # stash entry. Markers in a deck file would be served to the app as if they were
    # card names, so undo the pop and leave the work parked for a human instead.
    git reset --hard -q HEAD 2>/dev/null || true
    echo "sync: WARNING — uncommitted work did not re-apply cleanly; it is SAFE in \`git stash list\` — apply it from a console" >&2
  fi
}
trap restore_autostash EXIT

# Rebase BEFORE pushing: replays local deck commits on top of any new upstream code,
# so a code update and a deck edit never race into a non-fast-forward rejection.
# A conflict must not leave the clone mid-rebase (with `set -e`, every later run
# would then fail worse) — abort restores the pre-pull state, local commit intact.
echo "sync: pulling code updates (rebase)…"
if ! git pull --rebase; then
  git rebase --abort 2>/dev/null || true
  # Self-heal (added after this bit live, 2026-08-11): main is squash-merged, so a
  # session's PR can rewrite the very files the server has local commits on — the
  # rebase then conflicts every day forever and the loop is wedged until a human
  # opens a console. Recovery: park the local state on a rescue branch and PUSH it,
  # then reset to upstream. The push comes first — local edits are provably on
  # GitHub before a single byte is discarded; a session merges the rescue branch
  # back. If the rescue push itself fails (dead PAT, network), fall back to the
  # old honest abort: nothing is ever reset that isn't already saved remotely.
  # Belt and braces: the stash above should have emptied the tree, so if anything
  # uncommitted is STILL here the assumption behind this block is broken — take the
  # honest abort rather than reset over state no rescue branch can hold.
  if [ -n "$(git status --porcelain)" ]; then
    echo "sync: PULL FAILED with uncommitted changes still present — refusing to self-heal (nothing is discarded); resolve from a console" >&2
    exit 1
  fi
  rescue="server-rescue-$(date +%Y%m%d)"
  git branch -f "$rescue"
  if git push -f origin "$rescue"; then
    # Re-fetch before trusting @{u}: the unstaged-changes failure mode aborts the
    # pull BEFORE fetching, which would otherwise reset the clone to a stale
    # upstream — discarding local work to land on an old commit.
    git fetch origin || true
    git reset --hard "@{u}"
    echo "sync: RECOVERED — local edits parked on $rescue (pushed to GitHub); clone reset to upstream. A session should merge $rescue back."
  else
    git branch -D "$rescue" 2>/dev/null || true
    echo "sync: PULL FAILED — rebase aborted, clone restored; resolve from a console" >&2
    exit 1
  fi
fi

echo "sync: pushing…"
git push

echo
echo "sync: done."

# On the hosted server a pulled change only takes effect after a web-app reload,
# and touching the WSGI file is PythonAnywhere's documented reload trigger — so
# every sync ends by reloading, and "pull happened but the app is stale" can't
# occur. On any machine without /var/www (the PC, CI) the loop simply no-ops.
# SYNC_SKIP_RELOAD=1 hands the reload decision to the caller: the web app runs
# this script from INSIDE a request, where an immediate reload would kill the
# response mid-flight — it touches the WSGI file itself, only if HEAD moved.
if [ "${SYNC_SKIP_RELOAD:-0}" != "1" ]; then
  for w in /var/www/*_wsgi.py; do
    [ -e "$w" ] && touch "$w" && echo "sync: touched $(basename "$w") — web app reloading"
  done
fi
