"""The tool contract is a control, not a suggestion — so CI enforces it.

On 2026-08-19 a session verified ~40 cards one at a time with web search while
`.github/workflows/deck-verify.yml` did exactly that against Scryfall on a runner
with real internet. CLAUDE.md, SKILL.md and grounding-rules.md were all loaded.
The lesson is structural: **prose the session has to remember is not a control.**

Two mechanisms replace the prose, and this file guards both:

  * `.claude/settings.json` wires a SessionStart hook that injects
    `references/tool-contract.md` into context before the session acts.
  * These tests fail when a script, workflow or agent exists but the contract
    never names it — so adding a tool forces you to say when to reach for it.

Same shape as `test_agents.py` and `test_design_tokens.py`: invariants over the
files themselves, stdlib only.
"""
import json
import os
import re
import stat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT = os.path.join(ROOT, ".claude", "skills", "mtg-deckbuilder",
                        "references", "tool-contract.md")
SETTINGS = os.path.join(ROOT, ".claude", "settings.json")
HOOK = os.path.join(ROOT, ".claude", "hooks", "tool-contract.sh")
SKILL_MD = os.path.join(ROOT, ".claude", "skills", "mtg-deckbuilder", "SKILL.md")
CLAUDE_MD = os.path.join(ROOT, "CLAUDE.md")

# Libraries and helpers a session never invokes as "the tool for a question".
# Keep this list SHORT — every entry is a tool the contract does not have to
# explain, so a lazy addition here is how the guard rots.
NOT_SESSION_FACING = {
    "deckcore.py",    # named in the contract as the analytics hub, but as an import
    "mtglib.py", "deck_fit.py", "memo.py", "oracle_flags.py", "card_api.py",
    "card_image.py", "make_icons.py", "gen_card_notes.py", "staples_crossref.py",
}
# Workflows that are plumbing rather than a session-callable capability.
NOT_SESSION_FACING_WORKFLOWS = {"tests.yml", "recertify.yml"}


def _read(path):
    return open(path, encoding="utf-8").read()


def test_contract_exists_and_says_it_is_non_negotiable():
    text = _read(CONTRACT)
    assert "NON-NEGOTIABLE" in text
    # The standing order is the whole point — it must survive edits.
    assert "if a tool answers the question, the tool answers the question" in text.lower()


def test_every_session_facing_script_is_in_the_contract():
    """Add a script -> you must say when a session should reach for it."""
    text = _read(CONTRACT)
    scripts = {f for f in os.listdir(os.path.join(ROOT, "scripts"))
               if f.endswith(".py")} - NOT_SESSION_FACING
    missing = sorted(s for s in scripts if s not in text and s[:-3] not in text)
    assert not missing, (
        "these scripts exist but the tool contract never says when to use them: "
        + ", ".join(missing))


def test_every_session_facing_workflow_is_in_the_contract():
    """The failure that created this file: a workflow nothing pointed at."""
    text = _read(CONTRACT)
    wf_dir = os.path.join(ROOT, ".github", "workflows")
    workflows = {f for f in os.listdir(wf_dir)
                 if f.endswith((".yml", ".yaml"))} - NOT_SESSION_FACING_WORKFLOWS
    missing = sorted(w for w in workflows if w not in text)
    assert not missing, (
        "these workflows exist but the tool contract never says when to use them "
        "(this is the exact defect the contract was written for): "
        + ", ".join(missing))


def test_every_agent_is_in_the_contract():
    text = _read(CONTRACT)
    agents = [f[:-3] for f in os.listdir(os.path.join(ROOT, ".claude", "agents"))
              if f.endswith(".md")]
    missing = sorted(a for a in agents if a not in text)
    assert not missing, "agents missing from the tool contract: " + ", ".join(missing)


def test_deck_verify_routing_is_spelled_out():
    """The specific miss. The contract has to name the queue AND the trigger,
    because knowing the workflow exists was never the hard part — knowing it
    fires on a branch push touching the queue file was."""
    text = _read(CONTRACT)
    assert "deck-verify.yml" in text
    assert "verify-queue.txt" in text
    assert "claude/**" in text, "the contract must say what triggers the runner"


def test_named_antipatterns_are_kept():
    """Each of these cost a real correction; a future edit must not quietly drop
    them to tidy the file up."""
    text = _read(CONTRACT).lower()
    for probe in ("staples list", "deck_stats.py", "_norm", "uncited"):
        assert probe in text, f"anti-pattern dropped from the contract: {probe}"


def test_session_start_hook_is_wired_and_executable():
    settings = json.loads(_read(SETTINGS))
    entries = settings["hooks"]["SessionStart"]
    cmds = [h["command"] for e in entries for h in e["hooks"]
            if h.get("type") == "command"]
    assert any("tool-contract.sh" in c for c in cmds), \
        "SessionStart must inject the tool contract"
    assert os.path.exists(HOOK)
    assert os.stat(HOOK).st_mode & stat.S_IXUSR, "hook must be executable"


def test_hook_emits_valid_sessionstart_json_containing_the_contract():
    """A hook that silently emits nothing is worse than no hook."""
    import subprocess
    out = subprocess.run([HOOK], input="{}", capture_output=True, text=True,
                         timeout=30)
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "deck-verify.yml" in ctx and "NON-NEGOTIABLE" in ctx


def test_contract_is_linked_from_the_docs_a_session_actually_reads():
    for path in (SKILL_MD, CLAUDE_MD):
        assert "tool-contract.md" in _read(path), \
            f"{os.path.basename(path)} must point at the tool contract"
