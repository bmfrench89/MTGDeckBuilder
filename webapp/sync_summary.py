#!/usr/bin/env python3
"""One line for the sync commit's body: how many labelled changes each person made.

Reads the STAGED diff (`git diff --cached`) of the files the app labels — every deck's
`.changes.csv` (`By` is its fifth column) and `data/activity.csv` (`By` is its second)
— and prints e.g. `Ben: 3 changes · Sam: 2 changes`. Prints nothing when no added row
carries a name (single-password mode, or only CLI/session rows). Never raises into
sync_server.sh: the commit must happen whether or not a summary can be made.

Once the app runs on its collection database (Phase 1b, 2026-10-14) the activity log
lives there, not in git, so the line counts the decks' `.changes.csv` rows only.
"""
import csv
import subprocess
import sys


def summarize(diff_text):
    counts, order, path = {}, [], ""
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        row = next(csv.reader([line[1:]]), [])
        if path.endswith(".changes.csv"):
            who = row[4].strip() if len(row) > 4 and row[0] != "Card" else ""
        elif path.endswith("activity.csv"):
            who = row[1].strip() if len(row) > 1 and row[0] != "When" else ""
        else:
            continue
        if who:
            if who not in counts:
                order.append(who)
                counts[who] = 0
            counts[who] += 1
    return " · ".join(f"{w}: {counts[w]} change{'s' if counts[w] != 1 else ''}"
                      for w in order)


def main():
    try:
        diff = subprocess.run(
            ["git", "diff", "--cached", "-U0", "--", "data/activity.csv",
             "data/decks/*.changes.csv"],
            capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return 0
    out = summarize(diff)
    if out:
        print("Changes by person: " + out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
