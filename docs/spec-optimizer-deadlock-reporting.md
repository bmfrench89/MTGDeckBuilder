# Spec: honest deadlock reporting + canonical pin keys

**Status:** ☑ **SHIPPED 2026-08-19** — both phases. This file is now a RECORD, not a
work item: read it to understand why the deadlock message and the pin-key
canonicalisation are shaped the way they are, and do not re-implement from it.

Two deviations from the text below, both discovered while implementing and both
recorded here rather than left to rot:

1. **`optimize` probes `reserved` with the FIELD key but scores with
   `value_of(resolved_name)`.** For a split card those spellings differ, so a
   split-card add is margin-blocked before the pin logic is observable end to end.
   The reserved fix is still correct and necessary (it is the difference between
   "never offered" and "offered, then blocked for an unrelated reason"), but the
   tripwire for it asserts at the `pinned_elsewhere` level, where the contract
   actually lives. The `value_of` front-face gap is REAL, pre-existing, unspecced and
   NOT fixed here — it deserves its own ratification.
2. **The keep-set test had to use a role-NEUTRAL split name.** A realistic one
   (`Murderous Rider // Swift End`) classifies as `removal`, and with removal below
   its band the BAND protects the card from cuts — which made the first version of
   that test pass for the wrong reason. Both keep probes are now covered by tests
   verified to fail when the probe is reverted.

Line numbers below are anchors **as of `main` = `8b40903`** — resolve every reference
by the named symbol, and treat a drifted line number as expected, not as a conflict.

---

## Session rules (unchanged from the landfall spec; they all bit recently)

1. Read `CLAUDE.md` and the grounding rules first. Rules #8 (sharing) and #9 (basics)
   are settled.
2. Re-sync the branch to `origin/main` before starting; PRs are squash-merged.
3. The deck-verify Action pushes to your branch mid-session. On a rejected push,
   prefer rebase; if GitHub reports phantom conflicts from pre-squash lineage,
   rebuild the branch as `origin/main` + your commits and `--force-with-lease`.
4. Any `.attrs.csv` you regenerate carries `FlagsVer`
   (`Name,Type,MV,Colors,Produced,Flags,Power,FlagsVer`).
5. Full pytest before every push; CI green before merging.
6. On landing: update `docs/handoff.md` in place, mark this file ☑ SHIPPED with the
   PR number, and — the lesson of the landfall spec — **edit any instruction this
   session amends in place**, don't append a correction below it and leave the stale
   instruction live.

---

# PHASE A — deadlock reporting

## The defect, with its receipts

`scripts/optimize.py` prints (line 1152) and the webapp flashes (`_flash_optimize`,
`webapp/app.py:1463`):

> `already aligned with the field — no changes`

whenever `r["swaps"]` and `r["land_swaps"]` are both empty. But empty has two causes,
and the message is only true for one of them:

1. **Genuinely aligned** — no candidate cleared the anti-churn margin and field veto.
2. **Deadlocked** — candidates cleared both, then died at the role-band gate because a
   role's count is already outside its template band.

The gate (the `for role, (lo, hi) in ranges.items()` check inside the swap loop,
~line 505–512) requires the **post-trial** count to sit fully inside `[lo, hi]`. So a
role already out of band can never be touched:

- **Above the ceiling** (the case that happened): `tifa-lockhart` at ramp 19 against
  the default 9–13. Ramp-for-ramp keeps the count at 19 (outside), ramp-for-nonramp
  goes to 20 or 18 (outside). Every ramp-touching swap was rejected and the deck
  printed "already aligned" **while sitting at 10/25 field top-25 overlap** — six
  field-superior swaps (Cultivate 72%, Sword of the Animist 57%, …) invisibly frozen
  until the `landfall` archetype entry widened the band and released them.
- **Below the floor** (the same bug, other direction, not yet observed in a real
  deck): a role more than one step under `lo` can never be repaired either — adding
  one card moves the count toward the band but still lands outside it, so the trial
  is rejected. A deck at removal 3 against (8, 11) reads "aligned" forever.

Either way, the deck reads as finished when it is actually stuck. That is the exact
inversion of this repo's honesty labels, which exist to fire when data is absent or a
gate is doing the deciding.

## What must NOT change — the freeze is a feature, the lie is the bug

**Do not soften the gate.** The tempting "fix" — accept a swap when it moves the role
*strictly closer* to the band ("monotone improvement") — is wrong, and the tifa
history proves it: before the `landfall` entry existed, monotone improvement would
have let template pressure churn the player's hand-ratified 19-ramp deck down toward
the blind 9–13 band, cutting ramp the deck's engine depends on. The deadlock is what
*protected* that deck until a human ratified the right band. The correct escape hatch
for a legitimately out-of-band deck already exists and was just exercised: an
archetype entry in `deckcore._ARCHETYPE_ROLE_RANGE`, ratified by the player.

This spec is therefore **reporting-only**. The optimizer's behaviour — which swaps it
makes — must be byte-identical before and after. A test pins that.

---

## Change 1 — detect and count, in the swap loop (`scripts/optimize.py`)

Two additions inside `optimize()`:

**(a) Out-of-band roles**, computed right after `ranges` (from
`role_ranges_with_unknown`, ~line 480) and BEFORE the loop mutates `cats`
(initialised at line 325):

```python
    # Roles whose CURRENT count sits outside the template. The band gate below can
    # never move such a role (every post-trial count is still outside), so swaps
    # touching it are structurally impossible — the deck is frozen there, and the
    # summary must say FROZEN, never "aligned". The escape hatch is an archetype
    # entry (_ARCHETYPE_ROLE_RANGE), ratified by the player — see the landfall row.
    out_of_band = {role: (cats.get(role, 0), lo, hi)
                   for role, (lo, hi) in ranges.items()
                   if not (lo <= cats.get(role, 0) <= hi)}
```

**(b) Blocked candidates.** In the swap loop, the band check is the LAST gate — a
pair reaching it has already cleared the margin and the field veto. When `ok` comes
back `False`, record which add was blocked and by which role(s):

```python
            if not ok:
                for role in {cut_role, add_role} & set(out_of_band):
                    band_blocked.setdefault(role, set()).add(add_name)
                continue
```

(`band_blocked = {}` initialised beside `swaps` at ~line 486.) Note the intersection
with `out_of_band`: a rejection where the band is doing its NORMAL job — the trial
would push an in-band role out — is not a deadlock and must not be counted. After
the loop, drop any add that ultimately landed in `used_add` (it found another cut).

## Change 2 — carry it in the report (both return sites)

Add ONE key to **both** report dicts — the early no-field return (~line 562) and the
main `result` (~line 769); the report dict is the machine interface every consumer
imports, so the key must exist with the same shape on every path:

```python
    "role_deadlock": {
        "out_of_band": [{"role": r, "count": n, "lo": lo, "hi": hi}
                        for r, (n, lo, hi) in sorted(out_of_band.items())],
        "blocked": [{"role": r, "adds": sorted(names)}
                    for r, names in sorted(band_blocked.items())],
    },
```

On the early-return path there are no field candidates, so `blocked` is `[]` there —
but `out_of_band` is still computable and still true. Additive only: no existing key
changes, so the consumers that read `manual_holds`/`risers` (`webapp/app.py:872`,
`:985`) need no edit.

## Change 3 — the CLI summary (`scripts/optimize.py` `main`, ~line 1151)

Replace the flat conditional:

```python
        if not r["swaps"] and not r["land_swaps"]:
            print("   already aligned with the field — no changes")
```

with the honest split:

```python
        if not r["swaps"] and not r["land_swaps"]:
            dl = r.get("role_deadlock") or {}
            blocked = dl.get("blocked") or []
            if blocked:
                for b in blocked:
                    role = b["role"]
                    cur, lo, hi = next((o["count"], o["lo"], o["hi"])
                                       for o in dl["out_of_band"] if o["role"] == role)
                    print(f"   no changes — {len(b['adds'])} candidate(s) blocked by "
                          f"the {role} band (current {cur}, template {lo}-{hi})")
                print("   the band freezes this role on purpose; if the count is "
                      "deck-correct, ratify an archetype entry "
                      "(deckcore._ARCHETYPE_ROLE_RANGE) instead of forcing swaps")
            else:
                print("   already aligned with the field — no changes")
        if (r.get("role_deadlock") or {}).get("out_of_band"):
            for o in r["role_deadlock"]["out_of_band"]:
                print(f"   note: {o['role']} {o['count']} sits outside the template "
                      f"{o['lo']}-{o['hi']} — swaps touching it are frozen")
```

The trailing `note:` prints even when swaps DID happen elsewhere (a deck can be
deadlocked on one role and still improve on another) and even when no candidate was
blocked this run — an out-of-band role is a standing fact about the deck, same class
of label as `untyped` and `archetype_unknown`, and it prints beside the numbers like
every other honesty label in this block.

## Change 4 — the webapp flash (`webapp/app.py`, `_flash_optimize`, ~line 1451)

Mirror it — invariant 10, every surface. When `n == 0` and `blocked` is non-empty,
flash the deadlock message instead of "already aligned":

```python
    dl = (r.get("role_deadlock") or {})
    blocked = dl.get("blocked") or []
    if n:
        flash(f"Optimizer: {n} change(s) applied.", "info")
    elif blocked:
        parts = ", ".join(f"{len(b['adds'])} by the {b['role']} band" for b in blocked)
        flash(f"Optimizer: no changes — candidates blocked: {parts}. The role count "
              "sits outside the template; see the deck notes / archetype header.",
              "info")
    else:
        flash("Optimizer: already aligned with the field — no changes.", "info")
```

Keep the existing widened-template disclosure below it untouched.

## Change 5 — tests (`tests/test_optimize.py`, house style: docstrings say WHY)

Model fixtures on `_counter_deck` (~line 950), which already builds exactly the
needed shape in `tmp_path`. At minimum:

1. **The tripwire from the finding.** A deck one over a band with a field-superior
   same-role swap available: `role_deadlock["blocked"]` names that add under that
   role, `swaps == []`, and the report's `out_of_band` carries (count, lo, hi).
   Docstring: this is the tifa freeze in miniature — six field-superior swaps sat
   invisible behind "already aligned" for the deck's whole life.
2. **Below the floor deadlocks too.** A role more than one step under `lo` with an
   in-role candidate: blocked, not "aligned".
3. **Genuinely aligned decks are unchanged.** An existing aligned fixture:
   `role_deadlock == {"out_of_band": [], "blocked": []}` and the CLI still prints
   the old message (capsys).
4. **Reporting-only — behaviour is frozen.** The same fixture run before/after must
   produce identical `swaps`, `land_swaps`, `buy_swaps`. (In practice: assert the
   deadlocked fixture still proposes NO swaps — the gate still holds — and the
   aligned fixture's swaps are unchanged.)
5. **Normal band protection is not counted.** A rejection where the trial would push
   an IN-band role out must leave `blocked` empty — the deadlock label fires only
   when the current count is already outside.
6. **The flash mirrors.** Within `app.test_request_context()` +
   `get_flashed_messages()`: a deadlocked report flashes the blocked message, an
   aligned one flashes the old text (the pattern `tests/test_panel_pin.py` uses for
   session inspection is adjacent).

## Phase A acceptance

```bash
# A real-deck smoke: tifa-lockhart is now IN band, so it must read genuinely aligned
python3 scripts/optimize.py --deck data/decks/tifa-lockhart.txt \
    --collection data/collection/collection_snapshot.txt
# -> "already aligned with the field — no changes", NO deadlock notes

python3 -m pytest -q   # full suite green, 820+ tests
```

Then reproduce the historical case as a one-off check (read-only, in /tmp): copy
tifa-lockhart.txt, revert its header to `# Archetype: voltron`, run optimize against
it — it must now print the blocked-candidates message naming `ramp` and the
`(current 19, template 9-13)` numbers, where the old code printed "already aligned".
Paste both outputs in the PR body.

---

# PHASE B — canonical pin keys (ratified 2026-08-19)

## The defect, measured — a full census, not the two sites the first report named

A pin is stored as `{key: deck stem}` where every writer computes the key as
`mtglib._norm(name)` — which **keeps the full string for a split card**
(`_norm("Murderous Rider // Swift End")` → `"murderous rider // swift end"`), while
`front_face` would give `"Murderous Rider"`. Readers then probe with keys of whatever
spelling THEIR data source uses. The system only works when writer and reader happen
to share a spelling — and the sources genuinely differ: **deck files and the
collection carry full names; the EDHREC field snapshot carries front faces; the two
card panels post whatever spelling their `data-card`/form value happens to hold.**

Writers (both store `_norm(name)`, either spelling):
- `deck_pin` (`webapp/app.py:~1012`) — posted from the dashboard panel (deck spelling).
- `pins_move` (`~1121`, both form and `json=1` paths) — posted from `/pins` or the
  site-wide panel.
- (`deck_delete`, `~1154`, filters pins by VALUE only — unaffected either way.)
- Hand edits to the tracked `data/collection/pins.csv`.

Readers already front-face aware via `mtglib.name_keys` (correct today, and still
correct after this fix — `name_keys(probe)` always contains the front-face key):
- `edhrec._pinned_elsewhere` (`scripts/edhrec.py:129`)
- `deck_conflicts._pin_of` (`scripts/deck_conflicts.py:38`)
- `card_api.card_payload` (`scripts/card_api.py:116`)
- `pins_page` staleness (`webapp/app.py:~1090`) — its `runs` map is built under BOTH
  keys of every deck card, so it matches either stored spelling.

Readers that probe by EXACT key — the broken set, with each probe's key provenance:

| site | probe key comes from | breaks when |
|---|---|---|
| `optimize.py:~323/390` `reserved` filter | EDHREC field keys (front faces) | pin stored under full name → **the optimizer offers a card that is pinned elsewhere** |
| `optimize.py:~280/440` keep-set (`pinned here = keep`) | deck-file spelling (full) | pin stored under front face → **the optimizer may CUT a card pinned to this very deck** |
| `auto_build.py:~146` pool filter | collection spelling (full) | pin stored under front face → auto-build claims a reserved copy |
| `build_dashboard.py:~1685` panel `pinned` | panel detail keys (deck spelling) | pin stored under the other spelling → dashboard shows "Pin to this deck" on a pinned card |
| `webapp/app.py:567` `_validate_add` warning | collection spelling (full) | pin stored under front face → no "spoken for" warning on a manual add |
| `webapp/app.py:1136` `pins_move` JSON echo | `_norm` of the posted string | echo key must match whatever the store canonicalises to |

Note the second row: the asymmetry cuts BOTH directions. This is not only "the
optimizer can't see a full-name pin" (the original report) — a front-face pin (which
is exactly what the new site-wide panel writes when opened from an EDHREC-sourced
element) makes the keep-set miss, so the enforcement failure includes **cutting a
card the player explicitly reserved for that deck**.

Today `pins.csv` holds no split-card rows, which is why nothing has visibly broken
yet; the site-wide panel (PR #129) makes split-card pins routine to create.

## The design — one canonical key, minted in one place

**The invariant after this phase: every key in the pin map is
`_norm(front_face(name))`.** One new helper in `scripts/deckcore.py`, beside
`load_pins` (~line 199):

```python
def pin_key(name):
    """THE key a pin is stored and probed under: normalized FRONT face.

    A pin reserves a physical card, and the physical card is one object however its
    name is spelled — deck files and the collection write "A // B", EDHREC and the
    panels often write "A". Storing under the front face makes every spelling of the
    same object collide onto one pin. `front_face` splits only on " // " with spaces,
    so "SP//dr, Piloted by Peni" survives intact (the bare-slash trap)."""
    return mtglib._norm(mtglib.front_face(name))
```

Canonicalisation happens at the STORE, in both directions, so hand-edited and legacy
rows are migrated implicitly on first read — no migration script:

- `load_pins` (~line 202): build the map with `out[pin_key(card)] = deck` instead of
  `out[mtglib._norm(card)] = deck`.
- `save_pins` (~line 225): write `pin_key(card)` for each key (belt and braces — an
  in-memory dict built with a raw key still lands canonical on disk).

The current `pins.csv` (one row, `force of will`, no " // ") is already canonical, so
the on-disk change is a no-op until a split card is pinned.

## The probe fixes, per site

With the store canonical, front-face probes already hit. Each exact-key probe that
uses another spelling switches to `pin_key` (when it has a raw name) or a
`name_keys` intersection (when it only has a normed key string — `name_keys` accepts
those, and `front ∈ name_keys(anything)`):

1. `optimize.py` keep-set (~280): no change to the build (its keys are now canonical
   from `load_pins`), but keep has **two** exact probes, and both must widen — this
   census itself missed the second on the first pass, which is exactly why the
   implementer greps `in keep` rather than trusting this list:
   - the cut loop, ~440: `k = _norm(c.name)`; change the test to
     `if (mtglib.name_keys(c.name) & keep) or mtglib.is_basic(c.name)`.
   - the land pass, ~643: `mtglib._norm(c.name) not in keep` inside the `weak_lands`
     comprehension; change to `not (mtglib.name_keys(c.name) & keep)` — otherwise a
     pinned split LAND (MDFC lands exist and this collection has DFCs) is offered as
     a weak-land cut.
   Both are strict widenings: every current match still matches (same-spelling keys
   are in `name_keys`), and canonical pin keys now match deck-spelled split cards.
2. `optimize.py` reserved probe (~390): **no change** — field keys are front faces
   and the store is now canonical. Say so in the PR body rather than touching it.
3. `auto_build.py:~147`: `if pin_key(n) not in _reserved` (it holds the raw pool
   name; `import deckcore as _dc` is already in scope).
4. `build_dashboard.py:~1688`:
   `d["pinned"] = next((pins[x] for x in mtglib.name_keys(k) if x in pins), None)`
   — mirrors `card_api`, which is the same payload for the other surface.
5. `webapp/app.py:567` `_validate_add`: probe with
   `next((pins[x] for x in mtglib.name_keys(card.name) if x in pins), None)`.
6. `webapp/app.py` `deck_pin` (~1012) and `pins_move` (~1121): compute the mutation
   key with `deckcore.pin_key(...)` instead of `mtglib._norm(...)` so the in-memory
   dict, the JSON echo (`pins.get(k)`), and the saved file agree within the request.
7. `card_api.card_payload`, `edhrec`, `deck_conflicts`, `pins_page`: **no change** —
   verify by test, not by edit.

`pins_page` display note: rows now surface front-face keys; its `mtglib.lookup(idx,
key)` already resolves front faces against full-name collection rows (that is
`lookup`'s documented job), so `name`/`owned` keep working — but ADD the acceptance
check below rather than assuming.

## What must NOT change

- `name_keys` and `front_face` themselves — they are the repo-wide traps' fix and
  other subsystems depend on their exact behaviour.
- `pinned_elsewhere(stem, pins)`: unchanged. When called with explicit `pins` (tests
  do this), keys pass through as given; canonicalisation is the store's job.
- The `/pins` page contract, the panel JSON contract (`test_panel_pin.py` pins both).

## Phase B tests (`tests/test_pins_v2.py` extension or a new file; hermetic)

1. **`pin_key` itself**: identity for plain names; front face for `"A // B"`;
   `"SP//dr, Piloted by Peni"` unchanged (the bare-slash trap, straight from
   CLAUDE.md's Known Traps).
2. **Legacy rows migrate on read**: write a pins.csv containing
   `Murderous Rider // Swift End,gamma`; `load_pins` returns
   `{"murderous rider": "gamma"}`; a `save_pins` round-trip writes the canonical key.
3. **The enforcement tripwire — reserved direction** (the original bug): a pin
   stored under the FULL split name, a field snapshot offering that card's front
   face to another deck → `optimize` must NOT propose it as an add. This fails
   before the fix.
4. **The keep direction** (the bug the census found): a deck listing
   `"A // B"` (full spelling), the pin on that deck stored canonically → the card
   must not appear in `cuts`. Fails before the fix when the spellings differ.
5. **`auto_build` honours it**: a pinned-elsewhere split card is absent from the
   candidate pool whichever spelling the collection uses.
6. **`build_dashboard` payload**: a deck-spelled split key gets `pinned` set from a
   canonical pin.
7. **`_validate_add` warns**: adding `"A // B"` when the front face is pinned to
   another deck produces the warning.
8. **The land pass honours a pinned land**: a pinned-here nonbasic land (use a
   split/MDFC-style name) never appears in `weak_lands` whichever spelling the deck
   file uses — the ~643 probe this spec's own first census missed.
9. **Nothing regressed for the aware readers**: the existing
   `test_pins_v2.py::_pinned_elsewhere` cases, `test_changes.py`'s explicit-dict
   `pinned_elsewhere` cases, and all of `test_panel_pin.py` pass unmodified.

## Phase B acceptance

```bash
python3 -m pytest -q          # green, including the unmodified panel/pin suites
```

Then end-to-end in /tmp (read-only against the real repo): copy the decks dir, pin
`"Murderous Rider // Swift End"`-style card to one deck via a raw full-name pins.csv
row, run `optimize.py` (no --apply) on ANOTHER deck whose field offers that card, and
show it is not proposed; run the `/pins` page via the test client and show the row
resolves name/owned/stale correctly from the canonical key. Paste both in the PR body.
