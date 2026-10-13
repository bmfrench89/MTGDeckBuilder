"""The web side of card intake and deck import (docs/spec-card-intake.md §3-§5, and
the player's 2026-10-12 ask to "mass import a simple list of cards for the deck list").

Each test drives the real routes against a tmp collection, tmp decks and a tmp
owned_additions.txt; Scryfall is the stand-in `_verify_names`. What they pin:
the preview writes nothing; the confirm writes exactly the previewed rows; a small
file sent to Replace stops and asks; a covered batch row is only retired on a tap;
and an import never overwrites a deck it wasn't pointed at.
"""
import io
import os
import re

import pytest

DECK = """\
# Title: Other Deck
# Commander: Test Commander
# Colors: W U
# Archetype: control

# --- Commander ---
1 Test Commander

# --- Artifacts ---
1 Sol Ring

# --- Basics ---
10 Island
"""

SCRYFALL = {
    "sol ring": ("Sol Ring", "Artifact", "", "1.50"),
    "counterspell": ("Counterspell", "Instant", "U", "0.75"),
    "serra angel": ("Serra Angel", "Creature — Angel", "W", "0.30"),
    "test commander": ("Test Commander", "Legendary Creature — Human Wizard", "W U", "1.00"),
    "mana crypt": ("Mana Crypt", "Artifact", "", "150.00"),
    "lightning bolt": ("Lightning Bolt", "Instant", "R", "1.00"),
    "path to exile": ("Path to Exile", "Instant", "W", "3.00"),
}


def _verify(names):
    out = []
    for n in names:
        key = n.lower()
        if key == "sol rng":
            out.append({"found": True, "name": "Sol Ring", "source": "fuzzy",
                        "price_usd": "1.50", "type_line": "Artifact", "color_identity": ""})
        elif key in SCRYFALL:
            name, tl, ci, price = SCRYFALL[key]
            out.append({"found": True, "name": name, "source": "scryfall",
                        "price_usd": price, "type_line": tl, "color_identity": ci})
        else:
            out.append({"found": False, "reason": "no Scryfall match (exact or fuzzy)"})
    return out


@pytest.fixture
def env(tmp_path, monkeypatch, collection_file):
    import app as appmod
    import deckcore
    import enrich_bg
    import sync
    decks = tmp_path / "decks"
    decks.mkdir()
    (decks / "other-deck.txt").write_text(DECK, encoding="utf-8")
    coll_dir = tmp_path / "coll"
    coll_dir.mkdir()
    csv_path = coll_dir / "collection.csv"
    csv_path.write_text(open(collection_file, encoding="utf-8").read(), encoding="utf-8")
    adds = coll_dir / "owned_additions.txt"
    monkeypatch.setattr(appmod, "DECKS_DIR", str(decks))
    monkeypatch.setattr(appmod, "COLLECTION", str(csv_path))
    monkeypatch.setattr(appmod, "COLLECTION_CSV", str(csv_path))
    monkeypatch.setattr(appmod, "COLLECTION_ATTRS", str(coll_dir / "collection_attrs.csv"))
    monkeypatch.setattr(appmod, "ADDITIONS", str(adds))
    monkeypatch.setattr(appmod, "PASSWORD", None)
    monkeypatch.setattr(appmod, "_verify_names", _verify)
    monkeypatch.setattr(deckcore, "PINS", str(tmp_path / "pins.csv"))
    monkeypatch.setattr(sync, "maybe_start", lambda now=None: False)
    started = []
    monkeypatch.setattr(enrich_bg, "start",
                        lambda *a, **k: started.append(a) or "enrichment started")
    appmod.app.config["TESTING"] = True

    class E:
        app = appmod
        client = appmod.app.test_client()
        root = tmp_path
    E.decks, E.coll_dir, E.csv, E.adds, E.started = decks, coll_dir, csv_path, adds, started
    return E


def _token(html):
    return re.search(r'name="token" value="([^"]+)"', html).group(1)


def _preview(env, text):
    r = env.client.post("/collection/batch", data={"text": text})
    assert r.status_code == 200
    return r.get_data(as_text=True)


# --------------------------------------------------------------------------- #
# Batch: paste -> preview -> confirm
# --------------------------------------------------------------------------- #
def test_preview_writes_nothing(env):
    html = _preview(env, "1 Mana Crypt\n1 Sol rng\n1 Nope Card\n20 Island\n")
    assert "Mana Crypt" in html and "Nope Card" in html
    assert "basic land" in html
    assert not env.adds.exists()
    assert env.started == []


def test_confirm_writes_exactly_the_resolved_rows(env):
    html = _preview(env, "2 Mana Crypt\n1 Sol rng\n1 Nope Card\n20 Island\n")
    r = env.client.post("/collection/batch/confirm", data={"token": _token(html)})
    assert r.status_code == 302
    text = env.adds.read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    assert rows == ["2 Mana Crypt"], "unticked suggestion, unresolved line and basics stay out"
    assert re.search(r"# --- Batch \d{4}-\d{2}-\d{2} · pasted list · 2 cards", text)
    assert "$" not in text and "150" not in text, "prices never reach the tracked file"
    assert env.started, "enrichment starts so the new cards get types and colours"


def test_a_ticked_suggestion_is_written_under_its_real_name(env):
    html = _preview(env, "1 Sol rng\n")
    take = re.search(r'name="take" value="(\d+)"', html).group(1)
    env.client.post("/collection/batch/confirm", data={"token": _token(html), "take": take})
    assert "1 Sol Ring" in env.adds.read_text(encoding="utf-8")


def test_a_token_is_single_use_and_cannot_traverse(env):
    html = _preview(env, "1 Mana Crypt\n")
    tok = _token(html)
    env.client.post("/collection/batch/confirm", data={"token": tok})
    before = env.adds.read_text(encoding="utf-8")
    r = env.client.post("/collection/batch/confirm", data={"token": tok})
    assert r.status_code == 302 and env.adds.read_text(encoding="utf-8") == before
    for bad in ("../../etc/passwd", "a/b", ""):
        assert env.client.post("/collection/batch/confirm",
                               data={"token": bad}).status_code == 302
    assert env.adds.read_text(encoding="utf-8") == before


def test_new_batch_cards_show_up_as_arrivals(env):
    html = _preview(env, "1 Mana Crypt\n")
    env.client.post("/collection/batch/confirm", data={"token": _token(html)})
    page = env.client.get("/collection").get_data(as_text=True)
    assert "Review new arrivals" in page and "latest batch" in page
    assert env.client.get("/collection/arrivals").status_code == 200
    packet = env.client.get("/collection/arrivals.txt").get_data(as_text=True)
    assert "Mana Crypt" in packet and "PRIOR" in packet


# --------------------------------------------------------------------------- #
# Upload guard
# --------------------------------------------------------------------------- #
def _upload(env, data):
    return env.client.post("/collection/upload", data={"csv": (io.BytesIO(data), "x.csv")},
                           content_type="multipart/form-data")


def test_a_small_file_sent_to_replace_stops_and_asks(env):
    before = env.csv.read_text(encoding="utf-8")
    r = _upload(env, b"Quantity,Name,MARKET\n1,Mana Crypt,150.00\n")
    assert r.status_code == 200
    assert "full replacement" in r.get_data(as_text=True)
    assert env.csv.read_text(encoding="utf-8") == before, "unchanged until the second tap"
    pend = env.coll_dir / "pending-upload.private.csv"
    assert pend.exists(), "kept, gitignored, for the second tap"


def test_add_as_batch_previews_the_file_and_never_touches_the_csv(env):
    before = env.csv.read_text(encoding="utf-8")
    _upload(env, b"Quantity,Name,MARKET\n1,Mana Crypt,150.00\n")
    r = env.client.post("/collection/upload/decide", data={"choice": "batch"})
    assert r.status_code == 200 and "Mana Crypt" in r.get_data(as_text=True)
    assert env.csv.read_text(encoding="utf-8") == before
    assert not (env.coll_dir / "pending-upload.private.csv").exists()
    env.client.post("/collection/batch/confirm", data={"token": _token(r.get_data(as_text=True))})
    assert "1 Mana Crypt" in env.adds.read_text(encoding="utf-8")
    assert "150" not in env.adds.read_text(encoding="utf-8")


def test_replace_after_the_question_goes_ahead(env):
    _upload(env, b"Quantity,Name\n1,Mana Crypt\n")
    r = env.client.post("/collection/upload/decide", data={"choice": "replace"})
    assert r.status_code == 302
    assert env.csv.read_text(encoding="utf-8") == "Quantity,Name\n1,Mana Crypt\n"


def test_a_full_export_replaces_with_no_question(env):
    from conftest import COLLECTION_CSV
    bigger = COLLECTION_CSV + "1,Mana Crypt,0,,,{0},Artifact,,mythic,abcd,150.00\n"
    r = _upload(env, bigger.encode("utf-8"))
    assert r.status_code == 302
    assert "Mana Crypt" in env.csv.read_text(encoding="utf-8")


def test_upload_never_touches_the_tracked_snapshot(env):
    import app as appmod
    snap = os.path.join(appmod.ROOT, "data/collection/collection_snapshot.txt")
    before = os.path.getmtime(snap) if os.path.exists(snap) else None
    _upload(env, b"Quantity,Name\n1,Mana Crypt\n")
    env.client.post("/collection/upload/decide", data={"choice": "replace"})
    after = os.path.getmtime(snap) if os.path.exists(snap) else None
    assert before == after


# --------------------------------------------------------------------------- #
# Reconcile on upload
# --------------------------------------------------------------------------- #
def _upload_with_mana_crypt(env):
    from conftest import COLLECTION_CSV
    full = COLLECTION_CSV + "1,Mana Crypt,0,,,{0},Artifact,,mythic,abcd,150.00\n"
    return _upload(env, full.encode("utf-8"))


def test_covered_rows_are_offered_and_retired_only_on_a_tap(env):
    env.adds.write_text("# --- Batch 2026-10-12 · pasted list · 2 cards (2 distinct) ---\n"
                        "1 Mana Crypt\n1 Lightning Bolt\n", encoding="utf-8")
    _upload_with_mana_crypt(env)
    page = env.client.get("/collection").get_data(as_text=True)
    assert "Retire them" in page
    assert "1 Mana Crypt\n" in env.adds.read_text(encoding="utf-8"), "nothing retired yet"
    env.client.post("/collection/reconcile", data={"action": "retire"})
    text = env.adds.read_text(encoding="utf-8")
    assert "(in export): 1 Mana Crypt" in text and "\n1 Lightning Bolt" in text
    import mtglib
    coll = {c.name: c.quantity for c in mtglib.load_collection(str(env.csv))}
    assert coll["Mana Crypt"] == 1, "counted once — the export's copy, not the export's + the batch's"
    assert "Retire them" not in env.client.get("/collection").get_data(as_text=True)


def test_keep_dismisses_the_offer_and_changes_nothing(env):
    body = "# --- Batch 2026-10-12 · pasted list · 1 cards (1 distinct) ---\n1 Mana Crypt\n"
    env.adds.write_text(body, encoding="utf-8")
    _upload_with_mana_crypt(env)
    env.client.post("/collection/reconcile", data={"action": "keep"})
    assert env.adds.read_text(encoding="utf-8") == body
    assert "Retire them" not in env.client.get("/collection").get_data(as_text=True)


# --------------------------------------------------------------------------- #
# Deck import
# --------------------------------------------------------------------------- #
IMPORT = ("Commander\n1 Test Commander\n\nDeck\n1 Sol Ring\n1 Counterspell\n"
          "1 Mana Crypt\n1 Lightning Bolt\n1 Nope Card\n30 Island\n\nSideboard\n1 Path to Exile\n")


def _import(env, text, **form):
    r = env.client.post("/decks/import", data=dict(form, text=text))
    assert r.status_code == 200
    return r.get_data(as_text=True)


def test_import_form_and_preview_write_nothing(env):
    assert env.client.get("/decks/import").status_code == 200
    html = _import(env, IMPORT, title="My Deck")
    assert "Test Commander" in html
    assert "Outside the commander" in html and "Lightning Bolt" in html
    assert "aren't in your collection" in html and "Mana Crypt" in html
    assert "shared with other decks" in html          # Sol Ring is in other-deck
    assert "Path to Exile" in html and "left out" in html
    assert sorted(os.listdir(env.decks)) == ["other-deck.txt"]


def test_import_saves_a_new_sectioned_deck(env):
    html = _import(env, IMPORT, title="My Deck")
    r = env.client.post("/decks/import/confirm", data={"token": _token(html)})
    assert r.status_code == 302 and r.headers["Location"].endswith("/deck/my-deck")
    text = (env.decks / "my-deck.txt").read_text(encoding="utf-8")
    import deckcore
    import mtglib
    assert "# Commander: Test Commander" in text and "# Colors: W U" in text
    labels = [deckcore.section_label(ln) for ln in text.splitlines() if deckcore.section_label(ln)]
    assert labels == ["Commander", "Instants", "Artifacts", "Basics"]
    names = {c.name for c in mtglib.parse_deck(text)}
    assert "Path to Exile" not in names, "the sideboard is not the deck"
    assert "Nope Card" not in names, "an unresolved line is never written"
    assert not env.adds.exists(), "unowned cards are only added when ticked"
    assert env.client.get("/deck/my-deck").status_code == 200


def test_import_never_overwrites_a_deck_with_the_same_name(env):
    html = _import(env, IMPORT, title="Other Deck")
    r = env.client.post("/decks/import/confirm", data={"token": _token(html)})
    assert r.headers["Location"].endswith("/deck/other-deck-2")
    assert (env.decks / "other-deck.txt").read_text(encoding="utf-8") == DECK


def test_i_own_these_adds_only_the_shortfall_as_a_batch(env):
    html = _import(env, IMPORT, title="My Deck")
    env.client.post("/decks/import/confirm", data={"token": _token(html), "add_unowned": "1"})
    rows = [ln for ln in env.adds.read_text(encoding="utf-8").splitlines()
            if ln and not ln.startswith("#")]
    assert sorted(rows) == ["1 Lightning Bolt", "1 Mana Crypt"], \
        "owned cards and basics are not re-added"


def test_replacing_an_existing_list_keeps_its_headers_and_logs_the_diff(env):
    html = _import(env, "1 Test Commander\n1 Counterspell\n1 Serra Angel\n", target="other-deck")
    assert "replaces the cards in" in html
    env.client.post("/decks/import/confirm", data={"token": _token(html)})
    text = (env.decks / "other-deck.txt").read_text(encoding="utf-8")
    assert "# Archetype: control" in text and "# Title: Other Deck" in text
    import mtglib
    assert {c.name for c in mtglib.parse_deck(text)} == {
        "Test Commander", "Counterspell", "Serra Angel"}
    log = (env.decks / "other-deck.changes.csv").read_text(encoding="utf-8")
    assert "Counterspell" in log and "Serra Angel" in log and "manual-add" in log
    assert ",Sol Ring,manual-remove" in log
    assert "Island" not in log, "basics are never logged as decisions"


def test_no_commander_means_no_save(env):
    html = _import(env, "1 Sol Ring\n1 Counterspell\n")
    assert "No commander yet" in html
    env.client.post("/decks/import/confirm", data={"token": _token(html)})
    assert sorted(os.listdir(env.decks)) == ["other-deck.txt"]


def test_a_new_import_for_a_commander_you_have_offers_the_replace(env):
    html = _import(env, "1 Test Commander\n1 Counterspell\n")
    assert "You already have a deck for Test Commander" in html
    r = env.client.post("/decks/import/confirm",
                        data={"token": _token(html), "replace_stem": "other-deck"})
    assert r.headers["Location"].endswith("/deck/other-deck")
    assert sorted(os.listdir(env.decks)) == ["other-deck.changes.csv", "other-deck.txt"]


def test_replace_stem_is_limited_to_what_the_preview_offered(env):
    (env.decks / "unrelated.txt").write_text(DECK.replace("Test Commander", "Someone Else"),
                                             encoding="utf-8")
    before = (env.decks / "unrelated.txt").read_text(encoding="utf-8")
    html = _import(env, "1 Test Commander\n1 Counterspell\n")
    env.client.post("/decks/import/confirm",
                    data={"token": _token(html), "replace_stem": "unrelated"})
    assert (env.decks / "unrelated.txt").read_text(encoding="utf-8") == before


def test_a_leading_legendary_creature_is_offered_as_the_commander(env):
    """Nothing names the commander: the first card is used ONLY when it's a
    legendary creature, and the preview says where it came from."""
    html = _import(env, "1 Test Commander\n1 Counterspell\n")
    assert "Commander:</b>" in html and "Taken from the first line" in html
    html = _import(env, "1 Counterspell\n1 Test Commander\n")
    assert "No commander yet" in html, "a nonlegendary first line is never promoted"


# --------------------------------------------------------------------------- #
# Download added cards — the round trip to the player's own collection site
# --------------------------------------------------------------------------- #
ADDS = """\
# Player-confirmed ownership not in the export yet.

# --- Batch 2026-10-12 · the player's card orders · 5 cards (4 distinct) ---
2 Rhystic Study
1 Sol Ring
1 Forest
# retired 2026-10-13 (in export): 1 Mana Crypt
1 Fire // Ice

# --- Batch 2026-10-13 · one more · 1 card ---
1 Rhystic Study
"""


def test_added_cards_download_as_an_import_list(env):
    env.adds.write_text(ADDS, encoding="utf-8")
    r = env.client.get("/export/additions.txt")
    assert r.status_code == 200 and r.mimetype == "text/plain"
    assert "attachment" in r.headers["Content-Disposition"]
    assert "added-cards-" in r.headers["Content-Disposition"]
    lines = r.get_data(as_text=True).strip().splitlines()
    assert lines == ["1 Fire // Ice", "3 Rhystic Study", "1 Sol Ring"], \
        "summed per card, sorted; a retired row and a basic never appear"
    assert not any(ln.startswith("#") for ln in lines), "importers choke on comments"


def test_no_additions_file_is_an_empty_list_not_an_error(env):
    r = env.client.get("/export/additions.txt")
    assert r.status_code == 200 and r.get_data(as_text=True).strip() == ""


def test_the_download_button_shows_only_when_there_is_something_to_download(env):
    assert "Download added cards" not in env.client.get("/collection").get_data(as_text=True)
    env.adds.write_text(ADDS, encoding="utf-8")
    html = env.client.get("/collection").get_data(as_text=True)
    assert "Download added cards" in html and "/export/additions.txt" in html


def test_the_cli_writes_the_same_list(env, capsys, monkeypatch):
    import export_manapool as ex
    env.adds.write_text(ADDS, encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["export_manapool.py", "--additions", str(env.adds)])
    assert ex.main() == 0
    assert capsys.readouterr().out.strip().splitlines() == \
        ["1 Fire // Ice", "3 Rhystic Study", "1 Sol Ring"]
