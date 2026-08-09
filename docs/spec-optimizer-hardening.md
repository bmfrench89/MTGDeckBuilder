# Spec — Optimizer & Edit-Path Hardening (review round 2)

**Status:** ☑ implemented 2026-08-09, same session as the review ·
**Source:** full-file code review of `optimize.py`, `deckcore.py`, `deck_fit.py`,
`mtglib.py`, `webapp/app.py` (10 findings), plus the add-ranking inconsistency
carried from `research-prior-art.md` §5.3. One PR fixes all eleven.

The findings cluster into four stories, worst first. Each item lists the failure it
caused and the shape of the fix; regression tests pin every one.

---

## A. The optimizer could corrupt or crash mid-write (4 findings)

**A1 · Manabase pass 2 crashed AFTER rewriting the deck.** Pass 2 (swap weak lands
for basics) appended 2-tuples to `land_swaps` while `record_changes` and the CLI
unpack 3-tuples. With `--apply` the order is write → log → tidy → legality-check, so
the crash fired after `_write` but before `_tidy` and `singleton_violations`: a
half-applied, unvalidated, unlogged deck file — and the webapp's optimize route
swallowed the exception entirely. *Fix:* pass 2 emits `(land, basic, "free")`.
*Test:* a deck short on basics with a weak land now round-trips `--apply` and logs.

**A2 · `_tidy` deleted every comment inside a section.** The rebuild loop skipped
non-card items, so hand-written annotations under a section header were destroyed on
every applying run — violating the CLAUDE.md contract that edits "keep quantity,
section, and comment lines intact" (only comments above the first header survived).
*Fix:* comment lines are re-emitted in position; stored blank lines are normalized
(the rebuild already manages its own spacing). *Test:* a comment under `# --- Ramp
---` survives `_tidy`.

**A3 · The `1x Name` format corrupted decks.** `mtglib._QTY_RE` (the parser) accepts
`1x Sol Ring`, but `_tidy`, `_write`, and the webapp's `_edit_deck_card` each carried
their own stricter `^(\d+)\s+` regex. A pasted Arena/MTGO-style line parsed fine,
then the next applying run rewrote it as `1 1x Sol Ring` — a nonexistent card, with
the real one gone. *Fix:* all three sites (plus `deckcore.load_deck_sections`) now
use `mtglib._QTY_RE`. One parser, everywhere, same as the section-label rule.
*Test:* a `2x` line survives `_tidy` with quantity intact.

**A4 · `str.title()` mangled card names.** Unowned adds fell back to `k.title()` and
`write_buylist` title-cased every name: `"Urza'S Saga"` written into deck files and
buylists (title() capitalizes after apostrophes). *Fix:* `_display_name()` —
capitalize word starts only, never after an apostrophe. EDHREC's proper casing is
still preferred when reachable.

## B. The " // " trap, round three: alias duplicates (3 findings)

The webapp add path was fixed in #74; the review found the optimizer has the same
class of hole in three places. EDHREC deliberately emits BOTH full-name and
front-face keys, so these are not theoretical.

**B1 · The optimizer's own `in_deck` check.** Built from raw `_norm` only, so a deck
line `1 Fire` didn't block the field's `fire // ice` key from swapping the same card
in as a "new" add. *Fix:* new `mtglib.name_keys(name)` returns the full-name AND
front-face norms; every membership set in `optimize()` and `pool_report()` now uses
it (and `_validate_add` switched to it too — one helper, not three inline copies).

**B2 · `singleton_violations` couldn't see alias duplicates.** It only flagged
`qty > 1` on a single aggregated name — but `1 Fire` + `1 Fire // Ice` parse as two
names, each qty 1, so the post-write ILLEGAL guard stayed silent for exactly the bug
class it was written for. *Fix:* aggregate quantities by front-face key (basics
exempt via `mtglib.is_basic`, which also fixes snow basics being flaggable).

**B3 · The land pass could add the same land twice.** Pass 1 guarded cuts
(`used_land`) but not adds, so a DFC land reachable via two field keys swapped in
twice → `_tidy` merged them into an illegal `2 <land>`. *Fix:* adds are deduplicated
by resolved front-face key.

## C. The add/cut ranking asymmetry (carried from §5.3 — now unblocked)

Adds were ranked by raw EDHREC inclusion and gated by `inc_add - val_cut ≥ margin` —
**mixed units**, since the cut side is the fit-blended `value_of()` (which already
folds in synergy). A 93%-inclusion generic beat a high-synergy archetype payoff
twice: in the queue and at the gate.

*Fix:* adds are scored with the same `value_of()` as cuts, sorted by it, and gated
value-vs-value. Two invariants hold by construction: where the fit-blend doesn't
exceed raw inclusion the behavior is identical to before, and with no field data
there are no candidates at all (unchanged offline behavior).

*Testing without live EDHREC:* the suite monkeypatches `deck_fit.load_field` /
`load_synergy` (the pattern `test_optimize.py` already uses) to build an A/B case —
a lower-inclusion, high-synergy, shortage-filling card must now outrank a
higher-inclusion generic, and a swap that clears the margin on value but not on raw
inclusion must go through. Idempotence is re-asserted on the new ranking.

**Still owed (live, can't run from this sandbox):** the CLAUDE.md field check —
`optimize --all` preview on real EDHREC data, eyeball the swaps, apply, confirm each
deck's top-25 overlap stays ≥ ~50%, run again to confirm idempotence. One `git
revert` undoes it if a deck looks wrong.

## D. Webapp edit-path gaps (3 findings)

**D1 · Replace had none of Add's guards.** The panel's replace wrote any name
verbatim: replacing A with a card already elsewhere in the deck silently produced a
duplicate that Add would have rejected. *Fix:* replace now runs the same
front-face-aware duplicate check (excluding the card being replaced) and skips the
write on a duplicate. Deliberately NOT added: an ownership hard-block — deck files
legitimately contain unowned BUY cards, and panel alternatives are already
identity-filtered.

**D2 · Hybrid-Phyrexian pips counted double.** `{G/W/P}` added 1.0 to BOTH letters
(2.0 pips from one symbol), inflating pip-demand and Karsten source math for every
deck running hybrid-Phyrexian cards. *Fix:* every multi-letter symbol splits
`1/len(letters)`; the branch collapse also simplifies the function.

**D3 · The add route parsed the collection three times per click.** Validation,
advisor, and analysis each re-loaded the CSV. *Fix:* one `collection_index()` call
per request, threaded through `_validate_add(idx=…)` and `advise_card(collection=
<loaded list>)` (which always accepted a loaded list).

---

## Verification summary

- Every finding has a named regression test; suite grows accordingly, still offline.
- The A1 crash and A3 corruption were reproduced before fixing.
- `scripts/` remains stdlib-only (CI-simulated locally).
- Deliberately unchanged: the optimizer still never cuts manual adds or
  notes-protected cards; `_tidy` still merges duplicate lines and re-files by
  role/type; the ≥`margin` guardrail keeps its meaning under the new units.
