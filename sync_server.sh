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
  rescue="server-rescue-$(date +%Y%m%d)"
  git branch -f "$rescue"
  if git push -f origin "$rescue"; then
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
