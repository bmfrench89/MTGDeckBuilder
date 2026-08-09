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
TRACKED_DATA=(
  data/decks
  data/collection/owned_additions.txt
  data/collection/pins.csv
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
echo "sync: pulling code updates (rebase)…"
git pull --rebase

echo "sync: pushing…"
git push

echo
echo "sync: done. If the pull brought code changes, hit Reload on the"
echo "      PythonAnywhere Web tab to put them live."
