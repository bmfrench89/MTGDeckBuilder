"""Multi-app collection imports — the loader's alias table IS the format adapter.

Real export headers, verified against either a real file (Sorted) or the format's
own documented columns (ManaBox, Moxfield, Deckbox, TCGplayer, Dragon Shield).
What matters: names+quantities always land, the best available price column is
chosen (live market beats what-you-paid), exact printings survive for enrichment,
and a multi-game export can never leak another TCG into the pool.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import mtglib


def _load(text):
    return {c.name: c for c in mtglib.parse_collection(text)}


# --------------------------------------------------------------------------- #
# Sorted (Dragon Shield's successor) — the shape of a real export
# --------------------------------------------------------------------------- #
SORTED_CSV = '''"sep=,"
List Type,List Name,Collection,Format,Board,Quantity,Card Name,Set Code,Set Name,Card Number,Condition,Printing,Rarity,Language,Price Bought,Date Bought,Parent List Type,Parent List Name,Current Price (tcgplayer_marketsellprice),List Cover Image,Parent List Cover Image
,,mtg,,,1,Abundant Growth,PIP,Fallout,194,NearMint,Normal,common,en,0.00,2026-08-10,,,0.36,,
,,mtg,,,2,Command Tower,PIP,Fallout,259,NearMint,Normal,common,en,0.00,2026-08-10,,,0.41,,
,,mtg,,,1,Command Tower,MSH,Marvel Super Heroes,301,NearMint,Foil,common,en,0.10,2026-08-09,,,0.25,,
,,pokemon,,,4,Pikachu,SVI,Scarlet & Violet,25,NearMint,Normal,common,en,0.00,2026-08-10,,,1.99,,
,,mtg,,,1,"Bilbo Baggins, Burglar // Take a Glance",LTR,Lord of the Rings,404,NearMint,Surge Foil,rare,en,0.00,2026-08-10,,,2.10,,
'''


def test_sorted_export_loads_names_quantities_and_printings():
    cards = _load(SORTED_CSV)
    ct = cards["Command Tower"]
    assert ct.quantity == 3, "rows per printing must aggregate"
    assert ct.set_code == "PIP" and ct.collector_number == "259", \
        "first printing's set+number survive for exact Scryfall enrichment"
    assert "Bilbo Baggins, Burglar // Take a Glance" in cards, \
        "double-faced names pass through untouched (front_face handles them later)"


def test_sorted_price_comes_from_the_live_market_column_not_price_bought():
    """'Price Bought' is exported as 0.00 for scanned cards — using it would value
    the whole collection at nothing. The tcgplayer market column is the truth."""
    cards = _load(SORTED_CSV)
    assert cards["Abundant Growth"].price == 0.36
    ct = cards["Command Tower"]
    assert ct.price == 0.41, "max unit price across printings is the representative"
    assert abs(ct.value - (2 * 0.41 + 1 * 0.25)) < 1e-9


def test_multi_game_exports_cannot_leak_other_tcgs():
    cards = _load(SORTED_CSV)
    assert "Pikachu" not in cards, "Sorted exports every game; only mtg rows may load"


def test_excel_sep_preamble_is_stripped():
    assert "Abundant Growth" in _load(SORTED_CSV), \
        "the leading sep=, line must not eat the header row"


# --------------------------------------------------------------------------- #
# The other documented app formats (headers verbatim from each app's export)
# --------------------------------------------------------------------------- #
def test_manabox_headers_load_with_exact_printing_id():
    cards = _load(
        "Scryfall ID,Quantity,Name,Set code,Set name,Collector number,Foil,Condition,Language,Purchase price\n"
        "abc-123,3,Sol Ring,C21,Commander 2021,263,normal,near_mint,en,1.50\n")
    c = cards["Sol Ring"]
    assert c.quantity == 3 and c.scryfall_id == "abc-123" and c.price == 1.50


def test_moxfield_headers_load():
    cards = _load(
        "Count,Name,Edition,Collector Number,Foil,Condition,Language,Purchase Price\n"
        "2,Arcane Signet,cmr,297,,NM,en,0.90\n")
    c = cards["Arcane Signet"]
    assert c.quantity == 2 and c.set_code == "cmr" and c.price == 0.90


def test_deckbox_headers_prefer_the_code_over_the_set_name():
    cards = _load(
        "Scryfall ID,Count,Name,Edition Code,Edition,Card Number,Foil,Condition,Language,My Price\n"
        ",1,Counterspell,mh2,Modern Horizons 2,267,,Near Mint,English,1.25\n")
    c = cards["Counterspell"]
    assert c.set_code == "mh2", "Edition Code (the set code) beats Edition (the set NAME)"
    assert c.price == 1.25


def test_tcgplayer_headers_load_via_simple_name():
    cards = _load(
        "Quantity,Simple Name,Set Code,Set,Card Number,Printing,Condition,Language\n"
        "4,Lightning Bolt,2XM,Double Masters,381,Normal,Near Mint,English\n")
    assert cards["Lightning Bolt"].quantity == 4


def test_dragonshield_legacy_headers_load():
    cards = _load(
        "Folder Name,Quantity,Trade Quantity,Card Name,Set Code,Set Name,Card Number,Printing,Condition,Language,Price Bought,Date Bought\n"
        "Binder,1,0,Swords to Plowshares,STA,Strixhaven Mystical Archive,10,Normal,NearMint,en,2.00,2025-01-01\n")
    c = cards["Swords to Plowshares"]
    assert c.quantity == 1 and c.set_code == "STA"
    assert c.price == 2.00, "with no market column, Price Bought is the honest last resort"


def test_native_market_column_still_wins(collection_file):
    """Regression: the app's own canonical CSV (MARKET column) is unchanged."""
    coll = mtglib.load_collection(collection_file)
    sol = next(c for c in coll if c.name == "Sol Ring")
    assert sol.price == 1.50
