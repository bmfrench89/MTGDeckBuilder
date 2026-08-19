#!/usr/bin/env bash
# SessionStart hook — put the non-negotiable tool contract in context BEFORE the
# session acts. Prose in CLAUDE.md/SKILL.md demonstrably did not survive a long
# session (see the header of the contract file); this does, because the harness
# injects it rather than trusting the model to go read it.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTRACT="$ROOT/.claude/skills/mtg-deckbuilder/references/tool-contract.md"
[ -f "$CONTRACT" ] || exit 0
python3 - "$CONTRACT" <<'PY'
import json, sys
text = open(sys.argv[1], encoding="utf-8").read()
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": (
        "MTGDeckBuilder TOOL CONTRACT (non-negotiable; enforced by "
        "tests/test_tool_contract.py). The sandbox has no network — GitHub Actions "
        "is the network arm. If a tool answers the question, the tool answers the "
        "question.\n\n" + text),
}}))
PY
