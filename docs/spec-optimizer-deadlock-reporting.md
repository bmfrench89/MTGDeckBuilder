# Spec: the optimizer must say "frozen", never "aligned", when a role band deadlocks it

**Status:** ☐ ratified 2026-08-18 (player commissioned this spec after the defect was
surfaced by the landfall adversarial review) · not started · implementer: the next
Claude session — follow this document exactly; where it conflicts with the code you
find, STOP and say so rather than improvising.

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

## Acceptance

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

## Appendix — companion defect, documented here so it has a home. NOT ratified; do
## not implement without the player's go-ahead.

**Split-card pins are stored and read asymmetrically.** Both pin-writing routes
(`deck_pin` at `webapp/app.py:~1010`, `pins_move` at `~1113`) store under
`mtglib._norm(name)`, which for a split card keeps the FULL `"a // b"` string. The
readers disagree:

- front-face aware (find the pin either way): `edhrec._pinned_elsewhere`,
  `deck_conflicts._pin_of`, `card_api.card_payload` — all resolve via
  `mtglib.name_keys`.
- exact-key only: `optimize`'s add filter (`reserved = deckcore.pinned_elsewhere(stem)`
  at ~line 323, consulted as `k in reserved` at ~line 390 where `k` is a FRONT-FACE
  field key) and `optimize`'s keep-set (~line 280), plus `auto_build`'s pool filter.

So a pin created from a panel showing `"Murderous Rider // Swift End"` is stored
under the full string and **is invisible to the optimizer's reserved check**, whose
keys are front faces. The engines that enforce pins are the ones that can't see it.

Proposed fix direction (one line, at the chokepoint): expand keys inside
`deckcore.pinned_elsewhere` and `load_pins`' consumers via `mtglib.name_keys` — or
normalise to `front_face` at SAVE time in `save_pins` (with a one-shot migration of
the existing `pins.csv`, which today holds no split-card rows, so the migration is a
no-op in practice). Deciding between read-side and write-side normalisation is the
implementing session's first task — write-side is simpler but changes stored data;
read-side matches how `name_keys` fixed the same trap in `carddb` (PR #122 lineage).
