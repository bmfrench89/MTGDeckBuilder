# Spec: the `landfall` role template + pinning from the site-wide card panel

**Status:** ☑ **SHIPPED 2026-08-18.** Phase A landed as `20b6a65` (with `460438a`
superseded — see the Change 1 correction), Phase B as `ac18786`. This file is now a
RECORD, not a work item: read it to understand why the `landfall` band and the panel
pin control are shaped the way they are, and do not re-implement from it. Anything
below that reads as an instruction has been executed; the corrections marked
"**Corrected**"/"**AMENDED**" are what actually shipped and outrank the text above them.

Line numbers cited below are anchors **as of `main` = `e9dc44f`** — `main` moves
constantly (the deck-verify Action and the hosted app's sync both push), so resolve
every reference by the named symbol/route, and treat a drifted line number as
expected, not as a conflict.

Two independent workstreams, shippable as two PRs or one. Phase A is a data-table
change with tests; Phase B is a small full-stack feature. Neither invents anything:
A extends an existing table by one row, B ports an existing control to the one
surface that lacks it.

---

## Session rules (read before touching anything)

1. Read `CLAUDE.md` and `.claude/skills/mtg-deckbuilder/references/grounding-rules.md`
   first, as always. Rule #9 (basics always owned) and the sharing default
   (rule #8, `optimize.py` docstring) are settled — do not relitigate them.
2. **Re-sync the branch to `origin/main` before starting** (`git fetch origin main &&
   git checkout -B <branch> origin/main`). PRs are squash-merged; stale branch
   history will conflict.
3. **The deck-verify Action pushes to your branch mid-session** (field snapshots).
   If your push is rejected: `git fetch`, then check whether the remote tip is
   content-identical to a squash merge (`git diff --stat <remote-tip> <merge-sha>`
   empty). If the Action's commit descends from *pre-squash* lineage, GitHub will
   report merge conflicts that content-diffing says shouldn't exist — the fix that
   worked on 2026-08-17: rebuild the branch as `origin/main` + your commits
   (`git checkout -B <branch> origin/main`, re-apply via `git checkout <sha> -- <files>`
   or cherry-pick), then `--force-with-lease`.
4. **Any `.attrs.csv` you write or regenerate MUST carry the `FlagsVer` column**
   copied from the snapshot. Flags-without-FlagsVer reads as vocabulary v1 and
   silently downgrades the mana model (this bug shipped and was fixed same-day —
   PR #126). Header: `Name,Type,MV,Colors,Produced,Flags,Power,FlagsVer`.
5. Run the full pytest suite before every push. Wait for CI green before merging.
6. On landing: update `docs/handoff.md` in place (current-state only, no dated
   layers) and tick this spec's line in `docs/spec-interactive-analytics-ai.md` if
   you add one there; mark this file's Status ☑ with the PR number.

---

## Phase A — `landfall` entry in the archetype role template

### Why

`tifa-lockhart` runs **19 ramp** against the default band of 9–13, deliberately:
in a landfall deck, land-to-battlefield ramp IS the payoff, not just acceleration.
Today `deck_stats` prints `ramp: 19 (high; aim 9-13)` and the dashboard tile shows
the same "high" flag — a warning that is wrong for this archetype, exactly like the
draw-go control deck that read as "nine excess counterspells" before the `control`
entry existed (see the block comment above `_ARCHETYPE_ROLE_RANGE` in
`scripts/deckcore.py`, ~line 261). The widening was proposed on 2026-08-17 and
deliberately NOT shipped by the session that would have benefited; the player has
now ratified it by commissioning this spec.

### Change 1 — the table (`scripts/deckcore.py`)

Add ONE entry to `_ARCHETYPE_ROLE_RANGE` (~line 277), following the existing
comment style (state the measured deck and the reason):

```python
    "landfall": {"ramp": (9, 19)},   # the MEASURED count — see the comment in the code
```

**Corrected 2026-08-17 during implementation** (this spec originally said `(9, 20)` and
described the flag as "noise"). Both were wrong, and the implementation proved it — see
the amended acceptance criteria below. The ceiling must be the **measured** count: a swept
comparison shows `hi=19` and `hi=20` unblock the *identical* six field-superior swaps and
reach the *identical* 15/25 field overlap, but applied ramp equals the ceiling at every
value 19–22, so a ceiling above the measured count is an **add licence, not a tolerance** —
at 20 the optimizer spends the extra point converting a draw slot into a ramp slot
(draw 10→8, the floor of its band, instead of 10→9).

Rules you must not break (they are what the existing tests pin):
- **Widen only.** Merged via `min(lo), max(hi)` — never narrow another entry.
- **One role only.** Draw/removal/wipe/counter measured fine on the landfall deck;
  do not widen what wasn't measured.
- Do NOT touch the shims (`optimize.ROLE_RANGE` etc.) — they alias this table.

### Change 2 — the deck header (`data/decks/tifa-lockhart.txt`)

Change `# Archetype: voltron` → `# Archetype: voltron landfall`.
`deckcore.archetype_words` splits on whitespace/commas/slashes; both words resolve.
Edit the header line ONLY — the deck body was tuned and validated on 2026-08-17;
do not "improve" the 99. ⚠ **RETRACTED — see the AMENDED acceptance section below.**
Widening the band un-deadlocked the optimizer, and the six swaps it then proposed
were applied deliberately as Phase A's consequence; leaving them would only have
deferred them to an unsupervised automatic run. Then update the deck's `.notes.md`: the
"Ramp runs long on purpose" bullet currently says the fix is "proposed, not
shipped" — rewrite it to say the `landfall` template entry now covers it.

### Change 3 — tests

Extend `tests/test_optimize.py` (near
`test_default_role_ranges_are_unchanged_for_unknown_archetypes`, ~line 885) or
`tests/test_fit_single_source.py` — whichever file you judge closer to the
existing coverage — with, at minimum:

1. `role_ranges(["landfall"])["ramp"] == (9, 19)` and every other role equals the
   default.
2. Stacking: `role_ranges(["voltron", "landfall"])` yields ramp `(9, 19)`,
   removal `(6, 11)`, wipe `(0, 5)` — widenings from both words, no narrowing.
3. The unknown-word reporting still works:
   `role_ranges_with_unknown(["landfall", "zzz"])` returns `["zzz"]` as unknown.

Note `tests/test_fit_single_source.py:103` iterates every table entry — your new
entry is automatically covered there; make sure that test still passes unmodified.

### Acceptance (run all; paste results in the PR body)

```bash
python3 scripts/deck_stats.py --deck data/decks/tifa-lockhart.txt \
    --collection data/collection/collection_snapshot.txt
# -> ramp line reads a bare "(ok)", NOT "(high; aim 9-13)". deck_stats._flag prints
#    an "aim lo-hi" string ONLY when a count is OUT of band, so no aim range appears here.

python3 scripts/optimize.py --deck data/decks/tifa-lockhart.txt \
    --collection data/collection/collection_snapshot.txt
# -> "template: widened by archetype (voltron landfall) -> ramp 9-19, removal 6-11, wipe 0-5"

python3 -m pytest -q   # full suite green
```

**AMENDED 2026-08-17 — the original "already aligned … (idempotence must survive)"
criterion was unsatisfiable by construction and has been removed.** It asked for two
mutually exclusive things: widen the band so ramp 19 stops reading "high", *and* have the
optimizer propose nothing. One table feeds both surfaces (a test exists to guarantee
exactly that), so widening the band necessarily un-deadlocks the optimizer's accept filter.

The deck was never "aligned" — at ramp 19 against 9-13, every ramp-touching swap fell
outside the template in both directions, so the filter rejected all of them and
`optimize.py` printed "already aligned with the field" while the deck sat at 10/25 field
overlap. **The replacement criterion:** the widening will unblock previously-filtered ramp
swaps — enumerate them, decide explicitly, apply the decision, and confirm that a *second*
run then reports "already aligned with the field — no changes". At `(9, 19)` that end state
is: 100 cards, ramp 19, draw 9, removal 10, field top-25 15/25, second run clean.

Consequently "edit the header line ONLY — do not improve the 99" no longer holds for this
phase: the six swaps ARE Phase A's consequence, not a separate improvement, and leaving
them unapplied only defers them to an unsupervised automatic run (CLAUDE.md lists four
triggers). They were applied deliberately, validated, and logged in `.changes.csv`.

**Follow-up worth its own spec (out of scope here):** `optimize.py` prints "already aligned
with the field — no changes" whenever no swap survives the filter, *including* when the
filter is deadlocked by an out-of-band role count. Any deck sitting outside a role band
reads as aligned forever. A truthful message would name the gate: "no changes — N
candidate(s) blocked by the <role> band (current X, template lo-hi)".

Also open the deck dashboard (`build_dashboard.py`) once and confirm the role tile
no longer flags ramp — `build_dashboard.py:1726` reads the same `role_ranges`, so
this should be automatic; the check is that it IS.

---

## Phase B — pin control on the site-wide card panel

### Why

Pinning is the player's manual human-in-the-loop reservation (a pinned card is
"spoken for": skipped as an add candidate by `optimize`/`auto_build`/`edhrec`;
unpinned cards stay freely shared). The control exists ONLY on the generated
dashboard's panel (`scripts/assets/card_panel.html:68`, wired at ~299–323 to
`POST /deck/<stem>/pin`). The **site-wide** panel — `webapp/templates/_cardpanel.html`,
included by `base.html`, opened by any `data-card="…"` element via
`webapp/static/cardpanel.js` on the collection / shared / wishlist / index pages —
has **zero** pin references, even though `pins.html`'s empty-state text tells the
player to pin "from its panel". This is the two-surfaces trap `CLAUDE.md` warns
about, live.

Design constraint that makes this NOT a copy-paste of the dashboard button: the
site-wide panel opens on pages with **no deck context**, so "Pin to this deck" is
meaningless there. The control is therefore a **deck picker**, matching the
`/pins` page's one-action-move semantics.

### Change 1 — payload (`scripts/card_api.py`)

In `card_payload(...)` (~line 98), add one key:

```python
    "pinned": deckcore.load_pins().get(mtglib._norm(name)),   # deck stem or None
```

Wrap in try/except returning None on failure, matching how `build_dashboard.py`
(~1685) treats pins as best-effort. `card_api` already imports the hubs; a spoke
depending on `deckcore` is the architecture working as designed. Do NOT put the
all-decks list here — deck enumeration is a webapp concern (next change), and
`card_api` stays deck-agnostic.

### Change 2 — route addition (`webapp/app.py`)

`pins_move` (~line 1111) only. Keep the redirect behaviour for the `/pins` page
untouched, but return JSON when the caller asks for it — **and skip the `flash()`
calls on that path**, or the queued message pops as a stale toast on whatever full
page the player loads next:

```python
    wants_json = bool(request.form.get("json"))
    # ... perform the pop / assignment as today, but only flash() when not wants_json
    if wants_json:
        return jsonify({"ok": True, "pinned": pins.get(k)})
```

The panel will POST with `json=1`. (`pins.pop`/`pins[k] =` already ran; `pinned`
reflects the new state.) Do NOT add an `all_decks` payload or enumerate decks in
`api_card` — see Change 3 for why the existing payload already suffices.

### Change 3 — the panel itself

`webapp/templates/_cardpanel.html`: add a pin block (suggested: below the
"decks using this card" area — find the existing sections and slot it where the
layout reads naturally):

```html
<div id="cp-pin" class="cp-pin" hidden>
  <span id="cp-pin-state"></span>
  <select id="cp-pin-deck"></select>
  <button id="cp-pin-btn" type="button">📌 Pin</button>
</div>
```

`webapp/static/cardpanel.js`, where the `/api/card/` payload is applied:
- **The picker is sourced from `payload.decks`** — the stems that actually RUN the
  card, which `card_payload` already returns via `_decks_using` (that is why
  Change 2 adds no `all_decks`). If `payload.decks` is empty → keep the whole
  block hidden: a pin on a card no deck runs is definitionally the "stale" state
  the `/pins` page exists to flag, so the panel must not offer to create one.
  (The `/pins` page itself still allows arbitrary moves; that stays the escape
  hatch for pre-building.)
- Populate the select with `— not pinned —` (value `none`) + each stem from
  `payload.decks`; preselect `payload.pinned` or `none`. Edge case: if
  `payload.pinned` names a deck NOT in `payload.decks` (an existing stale pin),
  show the block anyway with that stem in the list, labeled `(stale)` — the player
  must be able to see and release a stale pin from here, not only from `/pins`.
- Set the state text: `Pinned to <stem> — other decks treat this copy as spoken
  for` / `Not pinned — freely shared`.
- On click: `fetch('/pins/move', {method:'POST', body: FormData(card=<name>,
  deck=<selected>, json=1)})`, then re-fetch the card payload and re-render, so
  the state text confirms what the server actually stored.
- **Handle the auth gate.** The whole app sits behind the shared-password session
  (`_require_login`, spec-auth-gate.md); an expired session answers this fetch
  with a redirect to the login page — HTML, not JSON. If the response is not JSON
  (or not `ok:true`), show a visible "session expired — reload and log in" state
  on the button; never fail silently.
- Card name: use the exact name the panel was opened with (the `data-card` value)
  — `/pins/move` norms it server-side via `mtglib._norm`; do not pre-normalize in JS.

Deployment note, for confidence rather than action: `data/collection/pins.csv` is
**tracked**, and the hosted app's sync pushes pin changes back to git (commit
`343dfb5` removed a deleted deck's pin exactly this way) — so pins made through
this panel on the hosted app round-trip into the repo with no extra work.

Styling: use existing tokens/classes from `tokens.css` and the panel's own CSS —
**no ad-hoc font sizes or spacing values** (`test_design_tokens` will fail you).

**Do not touch `scripts/assets/card_panel.html`.** The dashboard surface already
works; after your change, spot-check BOTH surfaces (app page panel + a generated
dashboard's panel) because a selector fix on one silently no-ops on the other.

### Change 4 — tests (hermetic — everything under `tmp_path`)

New `tests/test_panel_pin.py` (or extend `tests/test_pins_v2.py` if its fixtures
fit), covering at minimum:

1. `card_payload` carries `pinned`: monkeypatch `deckcore.PINS` to a `tmp_path`
   CSV pinning a card, assert the payload's `pinned` equals that stem, and equals
   `None` for an unpinned card. (`load_pins` reads `deckcore.PINS` at call time
   specifically so tests can do this — see the comment at `deckcore.py:202`.)
2. `/api/card/<name>` response includes `pinned` (and the pre-existing `decks`
   list the picker sources from — assert it survives, since the picker now
   depends on it).
3. `POST /pins/move` with `json=1` returns `{"ok": true, "pinned": <stem>}` on
   pin, `{"ok": true, "pinned": null}` on release (`deck=none`), the pins CSV
   on disk reflects it, and **no flash message is queued** (assert the session's
   `_flashes` is empty / the next page render carries no toast). Without `json`
   it still redirects AND still flashes (the `/pins` page contract, already
   covered by existing tests — do not break them).
4. `_cardpanel.html` contains the `cp-pin` ids (a cheap render/string test in the
   style of the existing template tests), so the control can't be silently lost.

### Acceptance

- From the collection page, opening a card's panel shows pin state and the picker;
  pinning moves/releases and survives a reload; the `/pins` page shows the result.
- The generated dashboard's own pin button still works (both-surfaces check).
- `python3 -m pytest -q` green, including `test_design_tokens` and the existing
  `test_pins_v2` unchanged.

---

## When both phases land

- `docs/handoff.md`: replace the "Still open" items (landfall entry proposed /
  panel pin gap) with one line each saying they shipped, PR number(s) included.
- This file: Status ☑ shipped, PR number(s).
- The buylist/wishlist need no changes from either phase.
