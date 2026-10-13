"""The sync's refresh of the repo's collection list (webapp/sync_snapshot.py).

What is pinned here is what keeps it safe to run unattended on the server:
  * it writes only while an anonymous read of the repo is REFUSED, so a public repo
    never receives a fresh copy, and anything it can't prove counts as public;
  * the token in origin's URL never reaches the anonymous probe;
  * the file holds names and quantities only, however rich the export;
  * the added-cards file is never folded in, which would double-count every added card;
  * a partial export, or an unchanged one, writes nothing;
  * it never fails the sync.
"""
import os
import subprocess
import types

import pytest

import mtglib
import sync_snapshot as ss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXPORT = """\
Quantity,Name,Mana Value,Colors,Identities,Mana cost,Types,Sub-types,Rarity,Scryfall ID,Price,Date Bought,Seller
1,Sol Ring,1,,,{1},Artifact,,uncommon,aaaa1111,3.48,2026-09-01,Some Shop
2,Sol Ring,1,,,{1},Artifact,,uncommon,bbbb2222,4.10,2026-09-02,Other Shop
1,Arcane Signet,2,,,{2},Artifact,,common,cccc3333,0.90,2026-09-03,Some Shop
1,Fire // Ice,2,R U,R U,{1}{R},Instant,,uncommon,dddd4444,0.50,2026-09-04,Some Shop
"""


def _done(rc=0, out="", err=""):
    return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)


# --------------------------------------------------------------------------- #
# The privacy gate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url,anon", [
    ("https://bob:ghp_SECRET@github.com/o/r.git\n", "https://github.com/o/r.git"),
    ("https://github.com/o/r.git", "https://github.com/o/r.git"),
    ("https://x:y@git.example.com:8443/o/r", "https://git.example.com:8443/o/r"),
    ("git@github.com:o/r.git", None),
    ("/srv/origin.git", None),
    ("", None),
])
def test_the_probe_url_never_carries_credentials(url, anon):
    assert ss.anonymous_url(url) == anon


def _runner(ls_result, url="https://bob:ghp_SECRET@github.com/o/r.git\n", calls=None):
    def run(args, root, env=None, timeout=30):
        if calls is not None:
            calls.append((args, env))
        if args[:2] == ["remote", "get-url"]:
            return _done(out=url)
        if isinstance(ls_result, Exception):
            raise ls_result
        return ls_result
    return run


def test_a_refused_anonymous_read_means_private_and_the_token_stays_home():
    calls = []
    refused = _done(128, err="fatal: could not read Username for 'https://github.com': "
                             "terminal prompts disabled\n")
    assert ss.repo_visibility(run=_runner(refused, calls=calls)) == "private"
    args, env = calls[-1]
    assert "ghp_SECRET" not in " ".join(args), "the probe must be anonymous"
    assert args[:2] == ["-c", "credential.helper="], "stored credentials must be off"
    assert env["GIT_TERMINAL_PROMPT"] == "0"


@pytest.mark.parametrize("result,expected", [
    (_done(0, out="abc123\trefs/heads/main\n"), "public"),
    (_done(128, err="fatal: unable to access: Could not resolve host: github.com"),
     "unknown"),
    (subprocess.TimeoutExpired("git", 30), "unknown"),
])
def test_anything_short_of_a_refusal_is_not_private(result, expected):
    assert ss.repo_visibility(run=_runner(result)) == expected


def test_an_ssh_remote_cannot_be_probed_so_it_is_unknown():
    assert ss.repo_visibility(run=_runner(_done(0), url="git@github.com:o/r.git")) \
        == "unknown"


def test_only_githubs_own_refusal_counts():
    """A mirror or proxy that asks everyone to log in proves nothing about GitHub."""
    refused = _done(128, err="fatal: could not read Username: terminal prompts disabled")
    url = "https://u:t@git-proxy.internal/o/r.git"
    assert ss.repo_visibility(run=_runner(refused, url=url)) == "unknown"


# --------------------------------------------------------------------------- #
# What gets written
# --------------------------------------------------------------------------- #
@pytest.fixture
def files(tmp_path):
    export = tmp_path / "collection.csv"
    export.write_text(EXPORT, encoding="utf-8")
    snap = tmp_path / "collection_snapshot.txt"
    snap.write_text("# old list\n1 Sol Ring\n1 Arcane Signet\n1 Fire // Ice\n",
                    encoding="utf-8")
    return export, snap


def test_names_and_quantities_only_summed_across_printings(files):
    export, snap = files
    changed, msg = ss.refresh(str(export), str(snap), today="2026-10-13")
    text = snap.read_text(encoding="utf-8")
    body = [ln for ln in text.splitlines() if not ln.startswith("#")]
    assert changed and body == ["1 Arcane Signet", "1 Fire // Ice", "3 Sol Ring"]
    for private in ("3.48", "4.10", "Shop", "2026-09-0", "aaaa1111", "uncommon"):
        assert private not in text, f"{private!r} must never reach the committed list"
    assert "Date captured: 2026-10-13" in text
    assert "3 cards, 5 copies" in msg


def test_the_written_list_reads_back_as_the_same_collection(files):
    export, snap = files
    ss.refresh(str(export), str(snap))
    got = {c.name: c.quantity for c in mtglib.parse_collection(snap.read_text("utf-8"))}
    assert got == {"Sol Ring": 3, "Arcane Signet": 1, "Fire // Ice": 1}


def test_an_unchanged_export_writes_nothing(files):
    export, snap = files
    ss.refresh(str(export), str(snap), today="2026-10-13")
    before = snap.read_text(encoding="utf-8")
    changed, msg = ss.refresh(str(export), str(snap), today="2026-10-14")
    assert not changed and "already current" in msg
    assert snap.read_text(encoding="utf-8") == before, "no new date, no commit"


def test_added_cards_are_never_folded_in(files):
    export, snap = files
    (export.parent / "owned_additions.txt").write_text("4 Sol Ring\n1 Rhystic Study\n",
                                                       encoding="utf-8")
    ss.refresh(str(export), str(snap))
    text = snap.read_text(encoding="utf-8")
    assert "Rhystic Study" not in text and "3 Sol Ring" in text, \
        "load_collection adds owned_additions on top; folding them in counts them twice"


def test_a_partial_export_is_refused(files):
    export, snap = files
    snap.write_text("".join(f"1 Card {i}\n" for i in range(40)), encoding="utf-8")
    before = snap.read_text(encoding="utf-8")
    changed, msg = ss.refresh(str(export), str(snap))
    assert not changed and "looks partial" in msg
    assert snap.read_text(encoding="utf-8") == before


def test_an_empty_export_is_refused(files):
    export, snap = files
    export.write_text("Quantity,Name\n", encoding="utf-8")
    changed, msg = ss.refresh(str(export), str(snap))
    assert not changed and "no cards" in msg


# --------------------------------------------------------------------------- #
# The entry point the sync calls
# --------------------------------------------------------------------------- #
@pytest.fixture
def wired(files, monkeypatch):
    export, snap = files
    monkeypatch.setattr(ss, "SNAPSHOT", str(snap))
    monkeypatch.setattr(ss, "_private_export", lambda: str(export))
    real = ss.refresh
    monkeypatch.setattr(ss, "refresh", lambda p: real(p, str(snap)))
    return snap


@pytest.mark.parametrize("vis,said", [("public", "the repo is public"),
                                      ("unknown", "could not confirm")])
def test_a_repo_not_proven_private_gets_nothing(wired, monkeypatch, capsys, vis, said):
    before = wired.read_text(encoding="utf-8")
    monkeypatch.setattr(ss, "repo_visibility", lambda: vis)
    assert ss.main() == 0
    assert said in capsys.readouterr().out
    assert wired.read_text(encoding="utf-8") == before


def test_a_private_repo_gets_the_refresh(wired, monkeypatch, capsys):
    monkeypatch.setattr(ss, "repo_visibility", lambda: "private")
    assert ss.main() == 0
    assert "collection list refreshed" in capsys.readouterr().out
    assert "3 Sol Ring" in wired.read_text(encoding="utf-8")


def test_no_private_export_means_nothing_to_do(monkeypatch, capsys):
    monkeypatch.setattr(ss, "_private_export", lambda: None)
    monkeypatch.setattr(ss, "repo_visibility",
                        lambda: pytest.fail("no export, so no probe"))
    assert ss.main() == 0 and "no private export" in capsys.readouterr().out


def test_it_never_fails_the_sync(monkeypatch, capsys):
    monkeypatch.setattr(ss, "_private_export", lambda: "/x.csv")
    monkeypatch.setattr(ss, "repo_visibility", lambda: "private")

    def boom(p):
        raise OSError("disk")
    monkeypatch.setattr(ss, "refresh", boom)
    assert ss.main() == 0 and "skipped (OSError)" in capsys.readouterr().out


def test_the_snapshot_is_never_its_own_source(monkeypatch, tmp_path):
    monkeypatch.setenv("MTG_COLLECTION", ss.SNAPSHOT)
    assert ss._private_export() is None


def test_the_sync_script_refreshes_before_it_stages():
    src = open(os.path.join(ROOT, "sync_server.sh"), encoding="utf-8").read()
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert "data/collection/collection_snapshot.txt" in code.split("TRACKED_DATA=(")[1] \
        .split(")")[0], "the refreshed list must be staged with the other app data"
    call = code.find("python3 webapp/sync_snapshot.py || true")
    assert call != -1, "the refresh must run, and must never fail the sync"
    assert code.find("flock -n 9") < call < code.find("git add"), \
        "under the lock, before staging"
