#!/usr/bin/env python3
"""Draft grounded "why it's good" notes for every card in your decks.

`card_notes.csv` is the hand-written knowledge base behind the click-a-card panel, but it
only covers a few dozen cards. This drafts the rest **from verifiable sources only** —
Scryfall oracle text (what the card actually does), the card's role, and EDHREC's
inclusion/synergy for the commanders that run it. Nothing is invented: if a card's oracle
text can't be fetched, it's skipped rather than guessed at (grounding rule #3).

Output goes to `card_notes.generated.csv`, a SEPARATE file. `deckcore.load_card_notes`
merges it underneath the curated one, so a hand-written note always wins and you can
promote any generated line into `card_notes.csv` by hand.

Usage:
  python3 gen_card_notes.py --collection data/collection/collection.csv          # dry run
  python3 gen_card_notes.py --collection <coll> --write
"""
import argparse
import csv
import glob
import json
import os
import re
import sys
import time
import urllib.request

import mtglib
import deckcore
import deck_fit

REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "reference")
_HEADERS = {"User-Agent": "MTGDeckBuilder/1.0 (personal collection tool)",
            "Accept": "application/json"}

# role -> the job this card is doing, in plain language
_ROLE_JOB = {
    "ramp": "accelerates your mana",
    "draw": "keeps your hand full",
    "removal": "answers a problem permanent",
    "wipe": "resets the board",
    "counter": "protects your turn on the stack",
    "land": "fixes your mana",
}

# oracle patterns -> what the card DOES. Ordered: first match wins, most specific first.
_MECHANICS = [
    (r"extra turn", "takes an extra turn"),
    (r"win the game", "can just win the game outright"),
    (r"search your library", "tutors up exactly the piece you need"),
    (r"counter target", "counters a spell"),
    (r"destroy all|exile all|each creature|all creatures", "sweeps the board"),
    (r"(destroy|exile) target", "removes a problem permanent"),
    (r"draw (a card|\w+ cards)", "draws you cards"),
    (r"add \{|mana of any", "produces mana"),
    (r"return .*from .*graveyard", "rebuys cards from your graveyard"),
    (r"create .*token", "makes tokens"),
    (r"whenever .*(attacks|deals combat damage)", "pays you off for attacking"),
    (r"whenever .*(dies|is put into a graveyard)", "turns deaths into value"),
    (r"hexproof|indestructible|protection from|\bward\b", "protects your board"),
    (r"can't be countered", "makes your spells uncounterable"),
    (r"double|copy target|for each", "scales or doubles your effects"),
    (r"\bhaste\b", "gives haste, so threats attack immediately"),
    (r"\bflying\b|\btrample\b|can't be blocked", "pushes damage through"),
]


def _fetch_oracle(names, sleep=0.25):
    """{normalized name: (oracle_text, type_line, mana_cost)} via /cards/collection."""
    out = {}
    for i in range(0, len(names), 75):
        batch = names[i:i + 75]
        body = json.dumps({"identifiers": [{"name": n} for n in batch]}).encode()
        req = urllib.request.Request("https://api.scryfall.com/cards/collection", data=body,
                                     headers={**_HEADERS, "Content-Type": "application/json"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    j = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code not in (429, 503) or attempt == 3:
                    raise
                time.sleep((5, 15, 30, 60)[attempt])
        else:
            continue
        for c in j.get("data", []):
            txt = c.get("oracle_text") or ""
            if not txt and c.get("card_faces"):
                txt = " // ".join(f.get("oracle_text", "") for f in c["card_faces"])
            rec = (txt, c.get("type_line", ""), c.get("mana_cost", ""))
            out[mtglib._norm(c.get("name", ""))] = rec
            front = (c.get("name") or "").split("//")[0].strip()
            if front:
                out.setdefault(mtglib._norm(front), rec)
        print(f"  …oracle for {len(out)}/{len(names)}", file=sys.stderr)
        time.sleep(sleep)
    return out


def _mechanic(oracle):
    low = (oracle or "").lower()
    for pat, phrase in _MECHANICS:
        if re.search(pat, low):
            return phrase
    return None


def compose(name, ref, oracle, type_line, mana_cost, field, synergy, commanders):
    """Build one grounded note. Returns None when there's nothing verifiable to say."""
    if not oracle:
        return None
    bits = []
    mv = f"{ref.mana_value:g}" if (ref and ref.mana_value is not None) else None
    kind = (type_line or "").split("—")[0].strip().replace("Legendary ", "").lower() or "card"
    art = "An" if (mv is None and kind[:1] in "aeiou") else "A"
    lead = f"{art} {mv}-mana {kind}" if mv else f"{art} {kind}"
    mech = _mechanic(oracle)
    role = deck_fit.primary_role(ref) if ref else None
    job = _ROLE_JOB.get(role)
    # Don't say the same thing twice ("produces mana — it accelerates your mana").
    overlap = {"mana", "cards", "permanent", "board"}
    same = bool(mech and job and (set(mech.split()) & set(job.split()) & overlap))
    if mech and job and not same:
        bits.append(f"{lead} that {mech} — it {job} for the deck.")
    elif mech:
        bits.append(f"{lead} that {mech}.")
    elif job:
        bits.append(f"{lead} that {job}.")
    else:
        bits.append(f"{lead}.")

    # the field's verdict, per commander that actually runs it
    best = None
    for cmd, inc_map in field.items():
        inc = inc_map.get(mtglib._norm(name), 0)
        syn = synergy.get(cmd, {}).get(mtglib._norm(name), 0)
        if inc and (best is None or inc > best[1]):
            best = (cmd, inc, syn)
    if best:
        cmd, inc, syn = best
        if syn >= 30:
            bits.append(f"A signature pick for {cmd} — {inc}% of those decks run it, "
                        f"far above its rate elsewhere (+{syn} synergy).")
        elif inc >= 60:
            bits.append(f"A core inclusion for {cmd} ({inc}% of decks).")
        elif inc >= 25:
            bits.append(f"Commonly played in {cmd} decks ({inc}%).")
    # A note that says only "A 3-mana creature." is noise — the panel already shows type
    # and cost. Only keep a draft that carries a real mechanic or a field verdict.
    if not mech and len(bits) < 2:
        return None
    return " ".join(bits)


def main():
    ap = argparse.ArgumentParser(description="Draft grounded card notes for your decks.")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--decks-dir", default="data/decks")
    ap.add_argument("--write", action="store_true", help="write card_notes.generated.csv")
    ap.add_argument("--limit", type=int, default=0, help="only do N cards (for a quick test)")
    args = ap.parse_args()

    coll = mtglib.load_collection(args.collection)
    idx = mtglib.index_by_name(coll)
    curated = deckcore.load_card_notes(include_generated=False)
    staples = deck_fit.load_role_staples()

    # every distinct card across the decks, minus basics and anything already curated
    basics = {"plains", "island", "swamp", "mountain", "forest", "wastes"}
    wanted, commanders = {}, {}
    for dp in sorted(glob.glob(os.path.join(args.decks_dir, "*.txt"))):
        text = open(dp, encoding="utf-8").read()
        m = re.search(r"^#\s*Commander\s*:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
        cmd = re.split(r"\s{2,}|\(", m.group(1))[0].strip() if m else ""
        if cmd:
            commanders[cmd] = True
        for c in mtglib.parse_deck(text):
            k = mtglib._norm(c.name)
            if k in basics or k in curated:
                continue
            wanted.setdefault(k, c.name)

    names = list(wanted.values())
    if args.limit:
        names = names[:args.limit]
    print(f"{len(names)} cards need a note "
          f"({len(curated)} already curated, {len(commanders)} commanders)")

    field = {c: deck_fit.load_field(c, idx) for c in commanders}
    synergy = {c: deck_fit.load_synergy(c, idx) for c in commanders}
    oracle = _fetch_oracle(names)

    rows, skipped = [], 0
    for name in names:
        k = mtglib._norm(name)
        o = oracle.get(k)
        if not o:
            skipped += 1                      # no verifiable text -> say nothing
            continue
        ref = mtglib.lookup(idx, name)
        why = compose(name, ref, o[0], o[1], o[2], field, synergy, commanders)
        if not why:
            skipped += 1
            continue
        role = deck_fit.primary_role(ref) if ref else None
        alts = [s["name"] for s in staples.get(role, [])[:3]
                if mtglib._norm(s["name"]) != k]
        rows.append({"Name": name, "Why": why, "Alternatives": "; ".join(alts)})

    print(f"drafted {len(rows)} notes, skipped {skipped} (no verifiable oracle text)")
    for r in rows[:5]:
        print(f"\n  {r['Name']}\n    {r['Why']}")
    if args.write:
        out = os.path.join(REF, "card_notes.generated.csv")
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["Name", "Why", "Alternatives"])
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {out} — curated card_notes.csv still takes precedence.")
    else:
        print("\n(dry run — pass --write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
