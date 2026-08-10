"""The two subagents in `.claude/agents/` are prompts, not code — nothing executes
them in CI, so nothing catches a rename, a widened tool list, or a grounding-rules
path that quietly stopped resolving after a file move.

These are the same kind of structural guard `test_design_tokens.py` is: six
invariants over the files themselves, in stdlib only. The frontmatter is parsed with
a regex on purpose — pyyaml is not a dependency of this repo and adding one for a
test would break the stdlib discipline `scripts/` lives under.

**Widening an agent's tools means deliberately editing this file.** That friction is
the point: `tools: Bash, Read` is what keeps a read-only auditor read-only, and a
verifier answering from Scryfall rather than from a web-search dump.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(ROOT, ".claude", "agents")
SKILL_MD = os.path.join(ROOT, ".claude", "skills", "mtg-deckbuilder", "SKILL.md")

EXPECTED = ["card-verifier", "collection-auditor"]
GROUNDING_RULES = ".claude/skills/mtg-deckbuilder/references/grounding-rules.md"


def _read(path):
    return open(path, encoding="utf-8").read()


def _split(text):
    """(frontmatter dict, body). Top-level `key: value` only — enough for name /
    description / tools, and blind to the folded description's continuation lines,
    which is exactly what we want."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, "agent file must start with a --- frontmatter block"
    fm = dict(re.findall(r"^([a-z_]+):[ \t]*(.*)$", m.group(1), re.M))
    return fm, m.group(2)


def _agents():
    return {n: _split(_read(os.path.join(AGENTS_DIR, n + ".md"))) for n in EXPECTED}


def test_the_expected_agent_files_exist():
    for name in EXPECTED:
        path = os.path.join(AGENTS_DIR, name + ".md")
        assert os.path.isfile(path), f"missing agent definition: {path}"


def test_every_agent_declares_name_description_and_tools():
    for name, (fm, _body) in _agents().items():
        for key in ("name", "description", "tools"):
            assert key in fm, f"{name}.md frontmatter is missing '{key}'"
        assert fm["description"].strip(), f"{name}.md has an empty description"


def test_the_declared_name_matches_the_filename():
    """Claude Code addresses an agent by its frontmatter name; a mismatch makes the
    file findable and the agent uninvokable."""
    for name, (fm, _body) in _agents().items():
        assert fm["name"] == name, f"{name}.md declares name: {fm['name']}"


def test_both_agents_are_limited_to_bash_and_read():
    """No Write/Edit (the auditor is read-only) and no WebSearch/WebFetch (the
    verifier answers from the Scryfall CLI, not from a search dump — the ratified
    decision Q-D1). Widening this is an edit to this test, on purpose."""
    for name, (fm, _body) in _agents().items():
        tools = {t.strip() for t in fm["tools"].split(",") if t.strip()}
        assert tools == {"Bash", "Read"}, f"{name}.md declares tools: {sorted(tools)}"


def test_every_agent_points_at_the_grounding_rules_and_the_file_is_there():
    """The rules are single-sourced: each agent Reads them rather than carrying a copy
    that drifts. A path that no longer resolves silently un-grounds the agent."""
    assert os.path.isfile(os.path.join(ROOT, GROUNDING_RULES))
    for name, (_fm, body) in _agents().items():
        assert GROUNDING_RULES in body, (
            f"{name}.md does not name {GROUNDING_RULES} — it would run ungrounded")


def test_the_skill_names_both_agents():
    """Automatic delegation is probabilistic; SKILL.md's delegation section is the
    deterministic path. If the skill stops naming an agent, that path is gone."""
    skill = _read(SKILL_MD)
    for name in EXPECTED:
        assert name in skill, f"SKILL.md never mentions the {name} subagent"
