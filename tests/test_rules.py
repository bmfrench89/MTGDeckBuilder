"""The Comprehensive Rules layer — parse, query, degrade.

Everything here is offline. `SAMPLE_CR` below replicates the official text file's
*layout*, not its contents: title, effective-date line, an Introduction, a Contents
listing that repeats every heading (and ends with the words "Glossary" and
"Credits"), the body, the real glossary, and the closing credits.

That duplication is the point. Slicing the body on the FIRST "Glossary" — the one
inside the Contents listing — yields a file with zero rules in it, and the failure
is silent: you get a parsed-looking dict that simply can't answer anything.
`test_contents_headings_do_not_shadow_body` is the tripwire.
"""
import json
import os
import time

import pytest

import rules

SAMPLE_CR = """\
Magic: The Gathering Comprehensive Rules

These rules are effective as of November 8, 2024.

Introduction

This document is the ultimate authority for Magic: The Gathering competitive game play.

Contents

1. Game Concepts

100. General
101. The Magic Golden Rules

6. Spells, Abilities, and Effects

601. Casting Spells

9. Casual Variants

903. Commander

Glossary

Credits

1. Game Concepts

100. General

100.1. These Magic rules apply to any Magic game with two or more players.

100.1a A two-player game is a game that begins with only two players.

100.2. To play, each player needs their own deck of traditional Magic cards.

101. The Magic Golden Rules

101.1. Whenever a card's text directly contradicts these rules, the card takes precedence.

6. Spells, Abilities, and Effects

601. Casting Spells

601.1. Previously, the action of casting a spell was referred to on cards as "playing" that spell.

601.2. To cast a spell is to take it from where it is, put it on the stack, and pay its costs.

601.2a To propose the spell, the player moves it from where it is to the stack.

601.2b If the spell is modal, the player announces the mode choice.
Example: A player casting a modal spell announces the chosen mode before targets are chosen.

9. Casual Variants

903. Commander

903.1. The Commander variant was created and popularized by fans.

903.2. Commander games can be played as either two-player games or multiplayer games.

Glossary

Deathtouch
A keyword ability that causes damage dealt by an object to be especially deadly. See rule 702.2, "Deathtouch."

Dies
A creature or planeswalker "dies" if it is put into a graveyard from the battlefield. See rule 700.4.

Credits

Magic: The Gathering Comprehensive Rules is maintained by Wizards of the Coast.
"""


@pytest.fixture
def cr():
    return rules.parse_cr(SAMPLE_CR)


@pytest.fixture
def cr_file(tmp_path):
    p = tmp_path / "MagicCompRules.txt"
    p.write_text(SAMPLE_CR, encoding="utf-8")
    return str(p)


@pytest.fixture
def no_network(monkeypatch):
    """Any attempt to reach the network fails the way a proxy-blocked box does."""
    def boom(*a, **k):
        raise OSError("network unreachable (test)")
    monkeypatch.setattr(rules.urllib.request, "urlopen", boom)


# ── B2: parser ───────────────────────────────────────────────────────────────

def test_parses_every_rule_and_only_the_rules(cr):
    assert cr["error"] is None
    assert sorted(cr["rules"]) == ["100.1", "100.1a", "100.2", "101.1", "601.1",
                                   "601.2", "601.2a", "601.2b", "903.1", "903.2"]
    assert list(cr["rules"])[0] == "100.1"          # document order preserved


def test_contents_headings_do_not_shadow_body(cr):
    """The guard: with naive first-'Glossary' slicing this dict would be empty."""
    assert cr["rules"]["100.1"].startswith("These Magic rules apply")
    assert cr["sections"]["100"] == "General"
    assert cr["chapters"]["9"] == "Casual Variants"


def test_rule_text_and_effective_date(cr):
    assert cr["rules"]["601.2a"].startswith("To propose the spell")
    assert cr["effective"] == "November 8, 2024"


def test_children_map_both_levels(cr):
    assert cr["children"]["601.2"] == ["601.2a", "601.2b"]
    assert cr["children"]["601"] == ["601.1", "601.2"]


def test_example_attaches_to_its_rule_and_is_not_a_rule(cr):
    assert "Example: A player casting a modal spell" in cr["rules"]["601.2b"]
    assert not [r for r in cr["rules"] if "example" in r.lower()]


def test_glossary_blocks_parse(cr):
    assert set(cr["glossary"]) == {"Deathtouch", "Dies"}
    assert cr["glossary"]["Deathtouch"].startswith("A keyword ability")


def test_zero_rule_parse_is_an_explicit_error():
    cr = rules.parse_cr("Some other document entirely.\n\nWith no rules in it.\n")
    assert cr["error"] and "parsed 0 rules" in cr["error"]
    assert "magic.wizards.com" in cr["error"]        # the manual-download note


def test_parses_without_a_contents_listing_or_glossary():
    body = "100. General\n\n100.1. These Magic rules apply to any Magic game.\n"
    cr = rules.parse_cr(body)
    assert cr["error"] is None
    assert cr["rules"]["100.1"].startswith("These Magic rules")
    assert cr["glossary"] == {}


# ── B3: query surface ────────────────────────────────────────────────────────

def test_normalize_ref():
    assert rules.normalize_ref("601.2A.") == "601.2a"
    assert rules.normalize_ref(" rule 903.1 ") == "903.1"
    assert rules.is_ref("903.1") and rules.is_ref("601.2a") and rules.is_ref("100")
    assert not rules.is_ref("commander tax")


def test_lookup_rule_carries_children_and_context(cr):
    hit = rules.lookup(cr, "601.2")
    assert hit["kind"] == "rule"
    assert hit["text"].startswith("To cast a spell")
    assert [c[0] for c in hit["children"]] == ["601.2a", "601.2b"]
    assert hit["section_title"] == "Casting Spells"
    assert hit["chapter_title"] == "Spells, Abilities, and Effects"


def test_lookup_bare_section_and_miss(cr):
    sec = rules.lookup(cr, "903")
    assert sec["kind"] == "section" and sec["title"] == "Commander"
    assert sec["rule_numbers"] == ["903.1", "903.2"]
    assert rules.lookup(cr, "999.9") is None


def test_error_payloads_pass_through_every_query_path():
    bad = rules.parse_cr("not the rules")
    assert rules.lookup(bad, "100.1")["error"]      # passes through, doesn't raise
    assert rules.search(bad, "anything") == []
    assert rules.glossary_lookup(bad, "Deathtouch") is None


def test_search_scores_terms_then_all_terms_then_phrase(cr):
    hits = rules.search(cr, "modal spell")
    assert hits[0]["ref"] == "601.2b"               # 2+2 terms, +5 all, +10 phrase
    assert hits[0]["score"] == 19
    assert "modal" in hits[0]["snippet"]
    assert all(h["score"] == 2 for h in hits[1:])   # one term, no phrase


def test_search_ties_break_by_document_order(cr):
    hits = rules.search(cr, "two-player game")
    assert [h["score"] for h in hits[:2]] == [21, 21]
    assert hits[0]["ref"] == "100.1a"               # earlier = more fundamental
    assert rules.search(cr, "   ") == []


def test_search_does_not_match_terms_mid_word(cr):
    assert not [h for h in rules.search(cr, "ropose") if h["ref"] == "601.2a"]
    assert [h for h in rules.search(cr, "propose") if h["ref"] == "601.2a"]


def test_glossary_lookup_tiers_and_see_rules(cr):
    exact = rules.glossary_lookup(cr, "deathtouch")
    assert exact["term"] == "Deathtouch" and exact["see_rules"] == ["702.2"]
    assert rules.glossary_lookup(cr, "Death")["term"] == "Deathtouch"      # prefix
    assert rules.glossary_lookup(cr, "ie")["term"] == "Dies"               # substring
    assert rules.glossary_lookup(cr, "banding") is None


# ── B1: fetch / cache / load ─────────────────────────────────────────────────

def test_load_from_an_explicit_file_never_touches_the_network(cr_file, no_network):
    cr = rules.load_cr(path=cr_file)
    assert cr["error"] is None and len(cr["rules"]) == 10
    assert cr["fetched"].startswith("fetched ")


def test_load_memoizes_by_path_and_mtime(cr_file, monkeypatch):
    calls = []
    real = rules.parse_cr
    monkeypatch.setattr(rules, "parse_cr", lambda t: (calls.append(1), real(t))[1])
    rules.load_cr(path=cr_file)
    rules.load_cr(path=cr_file)
    assert len(calls) == 1
    os.utime(cr_file, (time.time() + 5, time.time() + 5))     # an edit invalidates
    rules.load_cr(path=cr_file)
    assert len(calls) == 2


def test_empty_cache_plus_blocked_network_degrades_without_raising(tmp_path, no_network):
    cr = rules.load_cr(cache_dir=str(tmp_path))
    assert cr["error"] and "could not download" in cr["error"]
    assert "--file" in cr["error"] and rules.LANDING in cr["error"]
    assert cr["rules"] == {} and cr["glossary"] == {}


def test_stale_cache_loads_with_its_date_label(tmp_path, no_network):
    cache = tmp_path / "MagicCompRules.txt"
    cache.write_text(SAMPLE_CR, encoding="utf-8")
    old = time.time() - 200 * 86400
    os.utime(str(cache), (old, old))
    cr = rules.load_cr(cache_dir=str(tmp_path))
    assert cr["error"] is None and len(cr["rules"]) == 10        # no TTL, by design
    assert cr["fetched"] == "fetched " + time.strftime("%Y-%m-%d", time.localtime(old))
    # …and a --refresh that can't reach the network still answers from it.
    assert rules.load_cr(cache_dir=str(tmp_path), refresh=True)["error"] is None


def test_cp1252_file_round_trips(tmp_path):
    text = SAMPLE_CR.replace("903.1. The Commander variant",
                             "903.1. The “Commander” variant — the one")
    p = tmp_path / "MagicCompRules.txt"
    p.write_bytes(text.encode("cp1252"))
    cr = rules.load_cr(path=str(p))
    assert cr["error"] is None
    assert "“Commander” variant — the one" in cr["rules"]["903.1"]


def test_find_txt_url_from_a_landing_snippet():
    html = ('<a href="https://media.wizards.com/2024/downloads/MagicCompRules%20'
            '20241108.txt">Text</a> <a href="/other.pdf">PDF</a>')
    assert rules._find_txt_url(html).endswith("MagicCompRules%2020241108.txt")
    assert rules._find_txt_url("<html>no link here</html>") is None


# ── B4: CLI ──────────────────────────────────────────────────────────────────

def test_cli_rule_lookup_json(cr_file, capsys):
    assert rules.main(["601.2", "--file", cr_file, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "rule"
    assert payload["result"]["text"].startswith("To cast a spell")
    assert payload["effective"] == "November 8, 2024"


def test_cli_autodetects_glossary_then_search(cr_file, capsys):
    assert rules.main(["Deathtouch", "--file", cr_file]) == 0
    assert "See rule 702.2" in capsys.readouterr().out
    assert rules.main(["put it on the stack", "--file", cr_file]) == 0
    out = capsys.readouterr().out
    assert "601.2" in out and "read it before citing it" in out


def test_cli_miss_and_usage_and_degrade(cr_file, tmp_path, capsys, monkeypatch, no_network):
    assert rules.main(["999.9", "--file", cr_file]) == 1
    assert rules.main([]) == 2                                   # nothing asked
    assert rules.main(["--search", "--gloss", "x", "--file", cr_file]) == 2
    monkeypatch.setattr(rules, "CACHE_DIR", str(tmp_path / "empty-cache"))
    assert rules.main(["903.1"]) == 1
    assert "--file" in capsys.readouterr().err                   # the manual note
