# Spec — section integrity and mobile rendering (fix the causes, then guard them)

**Status: ✅ SHIPPED 2026-08-20 (all phases; C4 awaits the player).** Written from the player's phone screenshots of
2026-08-20 (The Ur-Dragon dashboard + deck list), which surfaced three defects. Each
was diagnosed to a root cause before this spec was written; nothing here fixes a
symptom whose cause is untouched.

## What the player saw, and what it actually was

1. **"Desolation of Smaug is a sorcery"** — filed under **Artifacts** in the
   Ur-Dragon deck, with Smaug the Magnificent (a Creature) under **Enchantments**.
   A full scan against the enriched collection found **18 mis-filed cards across 7
   of the 10 decks** (list in §A2). The deck FILES are wrong, not the renderer.
2. **"Cards are in the wrong locations"** with what looks like broken quantities
   ("9 Blasphemous Act", "4 Roaming Throne" in a singleton deck) — the deck files
   are singleton-clean; the leading number is the **mana value**, rendered by
   `.mv` as an accent-coloured bare number directly before the name. MV 9 on
   Blasphemous Act reads exactly like "quantity 9". A presentation defect that
   successfully misled the player *and* the session that reviewed the screenshot.
3. **Text cut off on mobile** — the CRISPI stat tiles put words ("redundancy-led",
   "prot 2 · rec 0", "combat T9") into `tile-val`, a slot styled `--fs-2xl` for
   values like "100" and "$462". On a phone, "redundancy-led" clips to
   "redunda / led".

## Root causes

**A. Three writers file cards into deck sections without consulting their type:**

- `optimize.py --apply` writes a swap-in **at the outgoing card's line** — a
  Sorcery replacing an Artifact lands under Artifacts. `_tidy` exists to fix
  exactly this, but it **only runs when the pass made changes** — so a manual swap
  followed by a "no changes" apply is never tidied (reproduced live: Grim Tutor,
  swapped by hand into smaug-wicked-worm on 2026-08-20, still sat under
  *Creatures* after two subsequent `--apply` runs printed "already aligned").
- The webapp's `_edit_deck_card` replace writes in place and never refiles.
- Historical adds made **while a card was untyped** (pre-enrichment) stuck
  permanently, because nothing revisits filing when type data arrives. This is the
  empty-vs-absent rule biting in a new place: absent type data at write time must
  not become a silent permanent misfile.

**B.** The grid figcaption renders `{mv}{name}{price}`. The card image already
shows the real mana cost, the qty badge is a separate top-right `N×` chip — the MV
number adds nothing in grid view and reads as a count.

**C.** `stat_tile()` has one value style. The CRISPI axes (shipped #145) put short
*phrases* into it; nothing adapts the type scale, and the tile grid's minimum
column width clips them on a phone. All styling must stay on `tokens.css` tokens —
`test_design_tokens` forbids ad-hoc sizes.

## Phase A — section integrity

- **A1. A checker, not a pytest data-test.** `deck_sections.py --check [--all]`:
  exit 3 listing every typed card whose type-exclusive section contradicts it
  (Artifact/Enchantment creatures legitimately live under Creatures; untyped cards
  are reported as `untyped`, never guessed). Tests stay hermetic (tmp_path
  fixtures for the checker itself); the REAL decks are guarded by running the
  checker as a CI step in `tests.yml` against the committed snapshot attrs, and
  in `refresh.py`. (A pytest that reads the player's `data/` would break the
  suite's hermetic rule — this is the same split as the tool contract's
  enumeration guard.)
- **A2. Repair.** `deck_sections.py --all --apply` now that all 2,781 names carry
  types; verify the checker reports 0; the 18 known: Bruce ×9 (Sorceries under
  Instants), cosmic-spider-man ×2, smaug ×1 (Grim Tutor), ur-dragon ×3,
  thorin ×2, yshtola ×1 (Delney under Sorceries).
  Note: regrouping rewrites deck-file line order, which re-seeds the goldfish
  compile order — clocks may wiggle within their confidence intervals. Expected;
  say so in the PR rather than letting it look like drift.
- **A3. Self-heal.**
  - `_tidy` runs on **every** `--apply`, not only when the pass changed something
    (it is idempotent and cheap).
  - `_edit_deck_card`'s replace refiles the incoming card when its known type
    contradicts the section it would inherit (falls back to in-place when type is
    unknown — never guess). Preserves quantity/comments per `test_deck_edit`.
- **A4. Tests:** checker unit tests (violation → exit 3 + named card; clean → 0;
  untyped → reported not guessed); `_tidy`-on-no-change regression (manual swap
  into wrong section, no-change apply, card refiled); webapp replace-refile test.

## Phase B — dashboard rendering (one renderer, both surfaces)

- **B1. Grid figcaption drops the MV number.** The card image shows the cost; the
  card panel shows details; the `N×` qty badge is already separate. List view
  (no images) keeps `.mv` — its rows also carry an explicit `N× ` for quantity, so
  the ambiguity is grid-specific — but restyle `.mv` muted, not accent, so it
  reads as metadata rather than a count there too.
- **B2. `stat_tile()` gains a text variant.** Value containing a space or longer
  than 6 chars → `tile-val--text`: `--fs-lg` (token), normal word wrap, no
  clipping; tile min-width relaxed so the tiles grid wraps to 2 columns on narrow
  viewports. Applies to CRISPI tiles, goldfish tiles, manabase tiles alike.
- **B3. Validation:** unit tests (long value → variant class; numeric value →
  unchanged; grid figcaption carries no `.mv`), `test_design_tokens` green, and a
  **real mobile check**: headless Chromium at 390×844 screenshots of two
  dashboards, sent to the player. Both surfaces checked (webapp `/deck/<stem>`
  serves the same `generate()`).

## Phase C — carry-over from the 2026-08-20 audit review

- **C1.** `deckcore.load_power_tags` registers both `name_keys`, so the
  dashboard/card-panel power tags agree with `power.py`'s counts (live case:
  `Boom // Bust` in mass_land_denial.txt labels nothing if a deck spells "Boom").
- **C2.** `deck_fit`'s Game Changer membership tests use `name_keys & set`
  (symmetry with `power._match`; latent, no live miss today).
- **C3.** Drop the agent-written `# Resilience: low` header from the Thorin deck:
  that header's contract is the **player's** declared judgement, and nobody
  declared it. The counted `prot 2 · rec 0` shows again until the player says
  otherwise.
- **C4 (player, not code).** Confirm the physical Bruce Banner // The Incredible
  Hulk is in the sleeved deck — the `owned_additions.txt` line stands on your
  word, not the session's inference.

## Non-goals

- No redesign of the tile grid or figcaption beyond the defects named here.
- No new tokens in `tokens.css`; no colours or fonts moved between surfaces.
- No changes to analysis results: section repair must leave every deck's 100
  cards and singleton status identical, and `power.py --rank` identical apart
  from the C3 header removal and goldfish CI wiggle noted in A2.

## Done when

- Checker exists, is CI-wired, and reports 0 on the repaired decks.
- The three writers can no longer produce a misfile the checker would catch.
- Mobile screenshots show unclipped tiles and an unambiguous deck list.
- Suite green; both surfaces verified; handoff updated.
