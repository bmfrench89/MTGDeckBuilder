# Spec — whole-app audit, 2026-10-11

**Status:** IN PROGRESS. The tracker is the checkbox list at the bottom.
**Origin:** the Tergrid study decks exposed two silent undercounts: edicts read as 0
removal, and goldfish ignored black's mana engines. Both were fixed in `60e8a47`. The player
then asked for the same audit across the whole app. Four read-only auditors each covered
one area: simulation and mana, roles and optimizer, the web app, and data and docs. **Every
finding below was reproduced** — the auditor ran code and saw the wrong output. Suspected
items that weren't reproduced are listed separately and are not scheduled.

The bar is the project's prime directive: a tool that prints a wrong number with a
confident label is worse than one that says "unknown". Severity follows that bar:

- **high:** a user-visible wrong number or claim, data loss, or a security hole.
- **med:** wrong on a realistic edge case.
- **low:** cosmetic, or a rare edge case.

---

## S — simulation and mana math (goldfish, manabase, deck_stats, deckcore)

| ID | Sev | Defect | Fix |
|---|---|---|---|
| S1 | high | Split, adventure and MDFC costs `"{1}{B}{B} // {1}{B}{B}"` are summed across faces. Murderous Rider is scored as needing B×4 by turn 3, and Miles Morales (MV 2) compiles to 4 pips + 4 generic. Hits `goldfish.parse_cost`, `mtglib.pip_counts`/`is_double_pip` and manabase. | Read only the front face (`front_face`-style split on `" // "`) everywhere a cost is parsed. |
| S2 | high | The clock "median first kill" is taken over the games that *did* kill only. Beorn prints "median T8" beside "by T8 48%". The table-kill median has no ≥50% gate. These feed power.py and the tiles. | Median over all games, counting non-kills as +∞; None when that median is +∞. Same rule for the table kill. |
| S3 | high | `deckcore.load_attrs` drops the `Cost` and `Sub-types` columns that carddb writes. A study deck's pip demand reads B 12 instead of B 70, and goldfish compiles Cabal Ritual as 2 generic. The Jet Medallion discount then eats a coloured pip, which breaks "colored pips are a floor". | Read `Cost` / `Sub-types` when present. `apply_attrs` sets `mana_cost` / `subtypes` when non-empty. |
| S4 | high | The `deck_stats.py` CLI never applies `<deck>.attrs.csv`, so it reports 27–28 lands on a 35-land deck. CLAUDE.md shows this command with no warning. | Apply the companion in the CLI, as `manabase.__main__` does. |
| S5 | high | manabase flags colours with **zero** demand as LOW (mono-B Tergrid shows "W: 1 src · demand 0.0 · <-- LOW"). | Colours with no demand are skipped or shown as n/a, never LOW. |
| S6 | med | The goldfish disk-cache key ignores `owned_additions.txt`, so a player-confirmed card's data never reaches a cached sim. | Key on every collection input file. |
| S7 | med | Disruption reports "commander recasts" that never happen. `commander_tax` is defined but never read. | Recast for real, adding +2 tax per removal, or rename the metric and drop the dead knob. |
| S8 | med | An attrs overlay replaces the full type list with one primary type (`Artifact Creature` → `Creature`). Artifact discounts then never match artifact creatures, though the assumptions say they do. | Never downgrade a richer existing type list. Parse multi-type cells. |
| S9 | med | A hybrid pip counts as a full requirement for *each* colour (Creakwood Liege `{B/G}×3` flagged "2×G risky"). | A hybrid pip is satisfied by the union of its colours' sources. |
| S10 | med | Basics the export omits (Snow-Covered, Wastes) produce no colour, and are mislabelled "enriched before the restriction vocabulary". | Synthesize a basic land with its type and produced colour when the lookup misses. |
| S11 | low | Three small defects: zero-cost spells are never cast on a turn with no mana; A/B metrics are bogus when `--turns` < 4; manabase's docstring describes an identity model the code no longer uses. | Drop the early `continue`. Refuse turn-gated A/B metrics below turn 4. Fix the docstring. |

## R — roles, optimizer, power, finders (mtglib, oracle_flags, optimize, deck_fit, power, combo_detector, commander_finder)

| ID | Sev | Defect | Fix |
|---|---|---|---|
| R1 | high | Notes protection and field-% lookups miss DFC names. `deck_fit` field lookups use the bare `_norm` key, and optimize's notes check uses `c.name.lower()`. Studious First-Year // Rampant Growth (78% field) is valued 16, and a notes-protected card was paired as a buy-swap's `Replaces`. | Use `name_keys` for every field lookup and for the notes check. |
| R2 | high | Treasure **reminder text** makes 22 cards `dork`/`rock`: `(It's an artifact with "{T}, Sacrifice this token: Add…")` matches `_TAP_ADD_RE`. Goldfish models a one-shot treasure as a permanent producer, and auto_build filled Thorin's ramp quota with them. | Strip parenthesized reminder text before the regexes run. The same fix covers cycling reminder text reading as `draw` (R12). |
| R3 | high | The optimizer's role gate (`role_of`) reads the raw collection row, not the enriched card. 30 mismatches on Beorn, and about 50 per study deck. | Resolve through the enriched card first, as the cuts loop does. |
| R4 | med | The buy pairing has no role-band gate. Cosmic Spider-Man's ramp sits at its floor (9 in a 9–13 band), yet a buy proposes cutting Farseek. | Same trial-band check the owned pass uses. |
| R5 | med | Curated lists override correct flags: Skyscanner (ramp, draws), Misstep (counter, but it's a sorcery that taps), Syphon Soul (draw, but it doesn't draw), Pilgrim's Eye (ramp, but it puts a land in hand), Casualties of War (wipe, but it's spot removal). | Fix those entries. |
| R6 | med | Tutors are undercounted. Profane Tutor, Beseech the Mirror and Cruel Tutor are missing from `tutors.txt`. All are runner-verified tutors. | Add them. |
| R7 | med | Bracket reasons contradict the verdict. 3-piece "Early" combos are announced as "early **two-card** combo ⇒ Bracket 4", and the stale "estimated B2" reason stays in the list. | Label by real piece count. Drop superseded reasons. |
| R8 | med | Cuts protection differs between surfaces. The webapp's `protected` flag drops notes-named cards (25 of 28 on Beorn); the dashboard skips card_notes, pins and manual adds. | One shared protected-set helper. |
| R9 | med | Missing flag data reads as a measured zero. An attrs file with no Flags column makes signets, diamonds and talismans count as "artifact". | Curate the signet, talisman and diamond cycles as RAMP. |
| R10 | med | The Resilience axis says the protection deck has "1 protection" because the verified protection pieces aren't in `resilience_staples.csv`. | Add the runner-verified pieces. |
| R11 | med | Study copies pollute cross-deck logic. Conflicts read 197 with study decks vs 24 without, and Sol Ring, Arcane Signet and Mind Stone drop out of auto_build's free pool. Optimizer, wishlist and the app all read the same scan. | An explicit `# Study: yes` deck header. Conflicts, wishlist, the free pool and `optimize --all` skip study decks. |
| R12 | low | More oracle_flags misreads: cycling reminder text reads as `draw`; damage sweepers ("deals N damage to each creature") aren't `wipe`; Ephemerate ("exile target creature you control, then return it") reads as `removal`. | Strip reminder text; add the damage-sweeper form; don't flag an exile that returns the card. |
| R13 | low | `_norm` folds neither curly apostrophes nor accents. An iOS-typed `Nature’s Lore` misses every lookup. | Fold `’`→`'` and strip diacritics in `_norm` (symmetric, so every key stays consistent). |
| R14 | high | `commander_finder` counts **off-colour** support. Mono-B Doctor Doom is credited with Counterspell and Swords to Plowshares, across 29 of 31 commanders. | Only count cards whose identity fits inside the commander's. |
| R15 | med | Smothering Tithe is curated as DRAW only, but it is ramp. | Move it to RAMP. |
| R16 | low | `make_icons.py` has no argument parsing, so running it with `--help` overwrites the tracked icons. This happened twice during this audit. | Real argparse: `--help` does nothing, and writing needs an explicit run. |

## W — web app (webapp/app.py)

| ID | Sev | Defect | Fix |
|---|---|---|---|
| W1 | high | `<stem>` accepts `\`. On Windows, `/deck/..%5C..%5Ccollection%5Cowned_additions/delete` deletes files outside `data/decks/`, and the default `run.bat` binds 0.0.0.0. | `deck_meta` accepts only `[A-Za-z0-9][A-Za-z0-9._-]*`, and the resolved path must stay under `DECKS_DIR`. |
| W2 | high | Remove or Replace on a basic deletes the whole line: Remove Swamp takes `21 Swamp` to nothing. Replacing gives the incoming card the old quantity (`21 Unknown Card`). | Decrement a multi-copy line and insert exactly one copy. |
| W3 | high | Build Next "Save" overwrites an existing hand-tuned deck, keeping the old notes, changes and buylist attached to the new list. | Save to `<slug>-2`, `-3`, … when the stem exists, as the docstring already promises. |
| W4 | med | No CSRF protection when no password is set. A cross-origin POST deletes or overwrites decks. | A `before_request` rejects unsafe methods whose `Origin` or `Sec-Fetch-Site` is cross-site. |
| W5 | med | Open redirect: `next=/%09/evil.example` survives `_safe_next`, and a newline causes a 500. | Reject control and whitespace characters, and require an empty scheme and netloc. |
| W6 | med | Replace-with-basic adds the basic even when the outgoing card isn't in the deck (100 → 101). | No insert unless the outgoing card was found. |
| W7 | med | A non-UTF-8 or garbage upload replaces the private CSV and then 500s every page, with no backup. | Parse a temp copy first; require at least one card; keep a `.bak`; then atomic replace. |
| W8 | med | The basics-unlimited rule is broken in the app. The leaderboard counts Forest as "to buy", and the Add picker rejects `Swamp` as unowned. | `is_basic` exemptions in both places. |
| W9 | low | A newline in a form value injects extra lines into the deck file or `owned_additions.txt` (`99 Mana Crypt`), and a non-numeric quantity creates a phantom card. | Reject `\r` and `\n` in names; quantity must be digits. |
| W10 | low | `/refresh` redirects to whatever the Referer says. | Redirect through `_safe_next` on the referrer's path. |
| W11 | low | A `10000 Swamp` line takes 12 s to render, and `1e20` OOMs the process. `/api/deck/<stem>/hand?mulls=abc` returns 500. | Clamp quantities on read and in the editor; parse `mulls` inside the try. |

## D — reference data, deck data, docs

| ID | Sev | Defect | Fix |
|---|---|---|---|
| D1 | high | Banned cards are recommended: Dockside Extortionist in `role_staples.csv`, and Jeweled Lotus and Dockside as card_notes alternatives. Nothing filters bans. | Remove the rows. Add a runner-verified `banned.txt` that the recommenders filter on. |
| D2 | high | The Buy view lists cards the player owns, three of them already in the 99. | `buy_signals` and `append_buylist` drop owned and in-deck rows. |
| D3 | high | `cosmic-spider-man.attrs.csv` writes Colors as `WUBRG` / `BG` / `BR`, which `_parse_colorish` reads as **colourless**. | Accept a run of WUBRG letters, and fix the three cells. |
| D4 | med | `card_notes.generated.csv` says "sweeps the board" for 12 non-sweepers and "draws you cards" for cycling lands. | Tighten the `gen_card_notes` patterns and regenerate. |
| D5 | med | Doc drift: CLAUDE.md says 820 tests (950 now). codemap omits `proxy_sheet`/`make_icons`. Two docs point at the deleted Smaug, Wicked Worm deck. `build_dashboard --help` lists 3 of 5 themes. | Fix each. |
| D6 | low | Duplicate rows in `tutors.txt`, `extra_turns.txt` and `archetype_support.csv`. Priest of Titania is listed as aristocrats support. | Dedupe; remove Priest of Titania. |
| D7 | low | Empty `ColorIdentity` on five white `combos.csv` rows; stale deck `.attrs.csv` rows; blank-Card `.changes.csv` rows; an 11-snapshot field-data age. | Data hygiene; field data refreshes through the loop. |

---

## Deliberately NOT scheduled (with reasons)

- **`docs/handoff.md` length (2,138 lines vs the "current state only" rule).** This is a
  documentation rewrite, not a defect a tool acts on. It's left for a dedicated pass so the
  history isn't lost in a drive-by edit.
- **Unproven suspicions** — combo_detector's bare-key matching, non-atomic concurrent
  writes, `/pins/move` accepting any string, wishlist.md publishing prices. Each needs a
  reproduction before it gets a fix.
- **D7's stale attrs rows and old field snapshots.** They're harmless: lookups key by deck
  membership, and field data refreshes through the existing loop.

## Implementation plan

The work runs in three parallel tracks, split by file ownership so no two touch the same
module. Each lands with tests that fail without the fix.

1. **Track S (engines):** goldfish, manabase, deck_stats, deckcore — S1–S11, plus D2's
   `buy_signals` filter. S1's `mtglib.pip_counts` half sits in track R, because mtglib is
   owned there.
2. **Track W (web app):** webapp/app.py — W1–W11.
3. **Track R (roles and data):** mtglib, oracle_flags, optimize, deck_fit, power,
   combo_detector, commander_finder, deck_conflicts, wishlist, make_icons, reference data,
   docs — R1–R16, D1, D3–D6.

Then: full suite, a before/after sweep of every committed deck (role counts, goldfish,
optimizer preview), and Tergrid attrs re-enrichment if oracle_flags output changed.

## Tracker

- [ ] Track S — S1–S11, D2
- [ ] Track W — W1–W11
- [ ] Track R — R1–R16, D1, D3–D6
- [ ] Integration: suite green, deck sweep reviewed, docs updated
