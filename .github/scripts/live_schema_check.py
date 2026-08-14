"""The A1 acceptance step, run where the network exists: validate the
`tests/test_oracle_flags.py` fixture SHAPES against real Scryfall JSON, and audit
`oracle_flags` against real oracle text for every card the fixtures model.

The offline tests prove the code matches the fixtures; this proves the fixtures
match reality — the two together close the loop the spec left open
(docs/spec-engine-upgrades.md §4.3: "the MDFC fixture shape rests on the
documented schema, so validate it once against reality"). First proven green
2026-08-10 (16/16); kept for on-demand recertification after new sets or a
Scryfall schema change.

Run from the repo root (GitHub Actions does): exits non-zero on any mismatch,
prints one line per card either way. Blasphemous Act is informational only — its
active-voice wording is a DOCUMENTED miss for the `wipe` regex (the curated
WIPES list catches it), so we pin that it still misses rather than fail on it.
"""
import json
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, "scripts")
import oracle_flags  # noqa: E402

# Scryfall rejects requests missing EITHER header with a 400 — same pair
# carddb._HEADERS sends (carddb.py:61-63 documents the requirement).
UA = {"User-Agent": "MTGDeckBuilder-live-check/1.0 (github.com/bmfrench89/MTGDeckBuilder)",
      "Accept": "application/json"}

# name -> (expected produced, expected flags) — the exact values the offline
# fixtures assert, so a mismatch here means fixture-vs-reality drift.
EXPECT = [
    ("Command Tower",                   {"W", "U", "B", "R", "G"}, set()),
    ("Sol Ring",                        {"C"},                     {"rock", "ramp", "mana2"}),
    ("Llanowar Elves",                  {"G"},                     {"dork", "ramp"}),
    ("Malakir Rebirth // Malakir Mire", {"B"},                     {"etb-tapped"}),
    ("Azorius Guildgate",               {"W", "U"},                {"etb-tapped"}),
    ("Glacial Fortress",                {"W", "U"},                {"etb-tapped-cond"}),
    ("Hallowed Fountain",               {"W", "U"},                {"etb-tapped-cond"}),
    ("Maze of Ith",                     set(),                     set()),
    ("Divination",                      set(),                     {"draw"}),
    ("Cultivate",                       set(),                     {"ramp", "fetch:basic"}),
    # the three A-F tokens against real wordings
    ("Swords to Plowshares",            set(),                     {"removal"}),
    ("Banishing Light",                 set(),                     {"removal"}),
    ("Damnation",                       set(),                     {"wipe"}),
    ("Toxic Deluge",                    set(),                     {"wipe"}),
    ("Counterspell",                    set(),                     {"counter"}),
    # v2 fetch/restriction tokens against real wordings. The typed class is the
    # reason the vocabulary grew: the v1 search regex needs the literal word
    # "land", and "island" does not match `\bland`, so every one of these read
    # as flagless until 2026-08-14.
    ("Wood Elves",                      set(),                     {"ramp", "fetch:forest"}),
    ("Farseek",                         set(),                     {"ramp", "fetch:plains",
                                                                    "fetch:island", "fetch:swamp",
                                                                    "fetch:mountain"}),
    ("Evolving Wilds",                  set(),                     {"ramp", "fetch:basic"}),
    ("Expedition Map",                  set(),                     {"fetch:land"}),
    ("Demonic Tutor",                   set(),                     set()),
    ("Unclaimed Territory",             {"W", "U", "B", "R", "G", "C"}, {"mana-restricted"}),
]


def fetch(name):
    url = ("https://api.scryfall.com/cards/named?exact="
           + urllib.parse.quote(name))
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                timeout=30) as r:
        return json.load(r)


def main():
    failures = 0
    for name, want_prod, want_flags in EXPECT:
        card = fetch(name)
        time.sleep(0.15)  # Scryfall courtesy delay
        got_prod = oracle_flags.produced_of(card)
        got_flags = oracle_flags.derive_flags(card)
        ok = got_prod == want_prod and got_flags == want_flags
        mark = "ok  " if ok else "FAIL"
        print(f"{mark} {name:35s} produced={sorted(got_prod)!r:30s} "
              f"flags={sorted(got_flags)!r}")
        if not ok:
            failures += 1
            print(f"     expected produced={sorted(want_prod)!r} "
                  f"flags={sorted(want_flags)!r}")
            print(f"     oracle: {oracle_flags.oracle_text_of(card)!r}")

    # The MDFC schema shape the fixture models: card-level produced_mana,
    # per-face type_line + oracle_text, Land back face with its own etb text.
    mdfc = fetch("Malakir Rebirth // Malakir Mire")
    time.sleep(0.15)
    faces = mdfc.get("card_faces") or []
    shape_ok = (isinstance(mdfc.get("produced_mana"), list)
                and len(faces) == 2
                and all("type_line" in f and "oracle_text" in f for f in faces)
                and "Land" in faces[1]["type_line"])
    print(("ok  " if shape_ok else "FAIL") + " MDFC schema shape "
          "(card-level produced_mana, 2 faces w/ type_line+oracle_text, Land back)")
    if not shape_ok:
        failures += 1
        print("     got: " + json.dumps(
            {k: mdfc.get(k) for k in ("produced_mana", "layout")},
            default=str))

    # Informational: the documented wipe-regex miss stays a miss.
    blas = fetch("Blasphemous Act")
    bflags = oracle_flags.derive_flags(blas)
    print(f"info Blasphemous Act derive_flags={sorted(bflags)!r} "
          f"(active-voice sweeper: expected NOT to carry 'wipe' — "
          f"curated WIPES list covers it) "
          f"{'[still a miss, as documented]' if 'wipe' not in bflags else '[now MATCHES — wording changed, update the docs note]'}")

    print(f"\n{len(EXPECT) + 1} checks, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
