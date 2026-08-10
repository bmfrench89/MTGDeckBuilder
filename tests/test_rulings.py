"""Per-card Scryfall rulings — resolution, caching, and honest degradation.

Fully offline: `_get_json` is monkeypatched everywhere, and every cache lives in
`tmp_path`. Scryfall is proxy-blocked in this sandbox, so a test that reached the
network would not be slow — it would be a failure disguised as one.
"""
import json
import os
import time

import pytest

import rulings

SOL_RING = {"name": "Sol Ring", "oracle_id": "oid-sol-ring",
            "rulings_uri": "https://api.scryfall.com/cards/sol/rulings"}
SOL_RULINGS = {"object": "list", "has_more": False, "data": [
    {"published_at": "2004-10-04", "comment": "Sol Ring is a colorless artifact."},
    {"published_at": "2021-03-19", "comment": "The mana is colorless."},
]}


@pytest.fixture
def api(monkeypatch):
    """A canned Scryfall. `calls` records every URL so the tests can prove what was
    requested (and that a cache hit requested nothing)."""
    pages = {"https://api.scryfall.com/cards/sol/rulings": SOL_RULINGS}
    calls = []

    def fake(url, timeout=25):
        calls.append(url)
        if url in pages:
            return pages[url]
        if url.startswith(rulings.NAMED_URL):
            return SOL_RING
        raise AssertionError("unexpected URL " + url)

    monkeypatch.setattr(rulings, "_get_json", fake)
    fake.calls = calls
    fake.pages = pages
    return fake


@pytest.fixture
def dead_api(monkeypatch):
    def boom(url, timeout=25):
        raise OSError("network unreachable (test)")
    monkeypatch.setattr(rulings, "_get_json", boom)
    return boom


def test_fetches_resolves_and_caches(api, tmp_path):
    r = rulings.rulings_for("Sol Ring", cache_dir=str(tmp_path), delay=0)
    assert r["error"] is None and r["source"] == "scryfall"
    assert r["name"] == "Sol Ring" and r["requested"] == "Sol Ring"
    assert r["oracle_id"] == "oid-sol-ring"
    assert [x["date"] for x in r["rulings"]] == ["2004-10-04", "2021-03-19"]
    assert "colorless artifact" in r["rulings"][0]["comment"]
    written = os.listdir(str(tmp_path))
    assert written == ["sol-ring.json"]
    entry = json.loads((tmp_path / "sol-ring.json").read_text(encoding="utf-8"))
    assert entry["key"] == "sol ring"          # the true key, stored inside the file


def test_second_call_is_served_from_cache(api, dead_api, tmp_path, monkeypatch):
    monkeypatch.setattr(rulings, "_get_json", api)
    rulings.rulings_for("Sol Ring", cache_dir=str(tmp_path), delay=0)
    n = len(api.calls)
    monkeypatch.setattr(rulings, "_get_json", dead_api)   # network dies afterwards
    r = rulings.rulings_for("Sol Ring", cache_dir=str(tmp_path), delay=0)
    assert r["error"] is None and r["source"] == "cache"
    assert len(r["rulings"]) == 2 and len(api.calls) == n


def test_stale_cache_beats_an_error_and_says_it_is_stale(api, dead_api, tmp_path,
                                                         monkeypatch):
    monkeypatch.setattr(rulings, "_get_json", api)
    rulings.rulings_for("Sol Ring", cache_dir=str(tmp_path), delay=0)
    entry = json.loads((tmp_path / "sol-ring.json").read_text(encoding="utf-8"))
    entry["fetched"] = time.time() - 200 * 86400      # the age lives in the file
    (tmp_path / "sol-ring.json").write_text(json.dumps(entry), encoding="utf-8")
    monkeypatch.setattr(rulings, "_get_json", dead_api)
    r = rulings.rulings_for("Sol Ring", cache_dir=str(tmp_path), delay=0)
    assert r["error"] is None and len(r["rulings"]) == 2
    assert r["source"].startswith("cache (stale")


def test_cold_cache_plus_dead_network_is_an_error_payload(dead_api, tmp_path, capsys):
    r = rulings.rulings_for("Sol Ring", cache_dir=str(tmp_path), delay=0)
    assert r["error"] and "unverified" in r["error"]
    assert r["rulings"] == [] and r["requested"] == "Sol Ring"
    rulings.print_rulings(r)
    assert 'UNVERIFIED "Sol Ring"' in capsys.readouterr().out


def test_resolved_name_differing_from_requested_is_surfaced(api, tmp_path, capsys):
    r = rulings.rulings_for("Sol Rng", cache_dir=str(tmp_path), delay=0)
    assert r["requested"] == "Sol Rng" and r["name"] == "Sol Ring"
    rulings.print_rulings(r)
    out = capsys.readouterr().out
    assert "!! asked for" in out and "Confirm this is the card you meant" in out


def test_split_card_names_are_not_naively_split(api, tmp_path):
    name = "SP//dr, Piloted by Peni"
    assert rulings._key(name) == "sp//dr, piloted by peni"    # front_face keeps it all
    rulings.rulings_for(name, cache_dir=str(tmp_path), delay=0)
    assert "fuzzy=SP//dr" in api.calls[0]                    # not "fuzzy=SP"
    assert os.listdir(str(tmp_path)) == ["sp-dr-piloted-by-peni.json"]


def test_paginated_rulings_are_joined(api, tmp_path, monkeypatch):
    api.pages["https://api.scryfall.com/cards/sol/rulings"] = {
        "has_more": True, "next_page": "https://api.scryfall.com/cards/sol/rulings?page=2",
        "data": [{"published_at": "2004-10-04", "comment": "page one"}]}
    api.pages["https://api.scryfall.com/cards/sol/rulings?page=2"] = {
        "has_more": False, "data": [{"published_at": "2021-03-19", "comment": "page two"}]}
    r = rulings.rulings_for("Sol Ring", cache_dir=str(tmp_path), delay=0)
    assert [x["comment"] for x in r["rulings"]] == ["page one", "page two"]


def test_cli_exits(api, dead_api, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rulings, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(rulings, "_get_json", api)
    assert rulings.main(["Sol", "Ring", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "Sol Ring"
    assert rulings.main([]) == 2                                    # usage
    monkeypatch.setattr(rulings, "_get_json", dead_api)
    monkeypatch.setattr(rulings, "CACHE_DIR", str(tmp_path / "cold"))
    assert rulings.main(["Sol Ring"]) == 1                          # degraded
    assert "UNVERIFIED" in capsys.readouterr().out
