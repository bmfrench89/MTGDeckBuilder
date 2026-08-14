# Spec — Mana Intelligence: fetch targets, restricted sources, and honest manabase re-evaluation

**Status: ☑ PHASES A–G ALL SHIPPED 2026-08-14** (player approved and drove the
season in-session; adversarially verified by three lenses before implementation).
Suite 685 → 713, offline, exit 0; `scripts/` stdlib-only throughout. **What
remains is Phase H's data rollout — two re-enrichment legs (H2), neither of them
code:** dispatch the attrs-snapshot Action, then re-enrich the server's private
CSV. Until both legs run, every surface shows the pre-vocabulary honesty labels
and all numbers are unchanged — the designed degrade, not a bug. H3's live
acceptance closes the loop after the legs.

**Why this exists (live findings, 2026-08-14, the-ur-dragon review):** the player
asked why Wood Elves and Llanowar Elves are in a deck with "only 2 Forests." The
grounded answer exposed a class of blindness, not one bad card:

- The deck actually has **5 Forest cards** (2 basics + 3 typed duals) — but no tool
  can say so. Nothing links a fetcher to its targets.
- **The typed-fetch class is invisible today — verified against the committed
  snapshot, not inferred.** `_SEARCH_LAND_RE` is `search your library for [^.]*\bland`,
  and `\b` means "island" does not match it (tested directly). Live rows:

  ```
  Farseek,Sorcery,2,G,{1}{G},,,          <- no flags
  Nature's Lore,Sorcery,2,G,{1}{G},,,    <- no flags
  Wood Elves,Creature,3,G,{2}{G},Elf;Scout,,   <- no flags, not even `ramp`
  Cultivate,Sorcery,3,G,{2}{G},,,ramp    <- says "basic land", so it hits
  ```

  Every typed fetcher in the collection is flagless. The miss is broader than a
  granularity gap: Wood Elves does not even register as ramp.
- **Rainbow-looking lands are overcounted.** Five ur-dragon lands are enriched as
  `Produced='W U B R G C'` with empty Flags — Unclaimed Territory, Secluded
  Courtyard, Haven of the Spirit Dragon, Maelstrom of the Spirit Dragon, Study
  Hall — so each counts as a full source of all five colors in `deck_stats`,
  `manabase`, and the goldfish sim. At least some of them can only spend that
  mana on a chosen/creature type. This is an **overcount to be subtracted**, not
  missing data to be filled.
  **Which of the five are genuinely restricted is UNVERIFIED here** — Scryfall is
  unreachable from the sandbox, and this repo does not guess oracle text. The
  implementer derives it from the real text at enrichment time; H3's acceptance
  says "count what enrichment finds", never a forced number.
- The optimizer's basics repair converts low-inclusion typed duals into basics
  **round-robin by alphabetical identity letter** (optimize.py:597-611) — no pip
  awareness, no subtype awareness. It can convert the deck's only Forest-typed
  dual while Wood Elves is in the 99, and pass 1 can swap it away on inclusion
  numbers alone. (Basics themselves can never be cut — that fear is impossible —
  but the *typed-nonbasic* stranding vectors are real and unguarded.)
- After a manual swap, nothing re-evaluates: the player can cut their last typed
  Forest and no surface says a word.

**The verdict this spec implements:** teach the enrichment pipeline what fetchers
fetch and which mana is restricted; count both honestly in the one place per-color
sources are already counted; surface the census everywhere mana is already
surfaced; guard the optimizer's land passes; and give the deck page a standing,
render-time mana-health advisory so every manual edit re-evaluates for free (the
memo cache makes a re-render ~25 ms). **Advisory, never auto-rewrite: manual
edits stay untouched, per the standing rule.**

---

## 0. For the implementing session (Opus 5) — binding contract

**Read first, in order:** `CLAUDE.md` · `docs/codemap.md` (dependency rule,
card-knowledge-flow, the module table) · this spec end to end ·
`scripts/oracle_flags.py`'s docstring contract table · the empty-vs-absent rule
in CLAUDE.md's Data formats section (it is load-bearing in three places below) ·
`docs/spec-table-ready.md` §0 invariants (ALL still bind) ·
`tests/test_color_sources.py` (the additive-key pattern Phase B copies).

**Execution order:** A → B → C → D; E and F independently after B; G any time;
H (rollout) last. One commit per phase on the assigned feature branch (same
deviation from one-PR-per-phase as `spec-infra-hot-paths.md` recorded: sessions
are confined to their assigned branch). Suite green at every commit,
offline/hermetic, `scripts/` stdlib-only.

**CHECKPOINT — Phase A is already SHIPPED (2026-08-14).** The vocabulary, the
`FlagsVer` column and its coupling rule, the enrichment/overlay plumbing, the
recertify `EXPECT` rows, the attrs-snapshot gate column, the widened audit
display and the docstring updates are all on the branch, with tests. **Baseline
is now 684 tests, exit 0** — start at Phase B. Phase A's own acceptance is met
and was proven rather than asserted: stashing the change and diffing showed 0 of
2,621 cards changing `classify()` roles and 0 of 6 decks changing power, bracket
or category counts. Two pins were updated deliberately (the eleven-column header
test; Cultivate's exact flag set), and the coupling rule is mutation-proved —
reverting it yields Unclaimed Territory with `flags=set(), flags_ver=2`, the
verified-unrestricted lie.

**Rules of engagement:** every number a surface shows carries its honesty label
when derived from absent or pre-vocabulary data; label-don't-hide; never guess a
subtype from a card name; the optimizer never runs after a manual edit; the
Cuts/dead-weight land exclusion stays. If a decision below is wrong against the
real code, implement the closest correct thing and record the deviation in the
commit message — never silently reinterpret.

---

## Phase A — Vocabulary v2: fetch + restriction tokens, and a version the data admits to

### A1. New tokens (emitted by `oracle_flags.derive_flags` — the ONLY emitter)

| Token | Fires when a face's text has a "search your library for …" clause naming | Example |
|---|---|---|
| `fetch:land` | "… land card(s)" with no basic/type qualifier | Sylvan Scrying, Hour of Promise |
| `fetch:basic` | "… basic land card(s)" | Rampant Growth, Cultivate, Evolving Wilds |
| `fetch:plains` / `fetch:island` / `fetch:swamp` / `fetch:mountain` / `fetch:forest` | "… <Type> card" — typed, basics **and** typed duals qualify | Wood Elves (`fetch:forest`), Farseek (four tokens), Windswept Heath (two) |
| `fetch:basic-plains` … `fetch:basic-forest` | "… basic <Type> card(s)" — basics of that type only | Nissa's Pilgrimage (`fetch:basic-forest`) |
| `mana-restricted` | a mana ability with "spend this mana only" in the same face | Unclaimed Territory, Secluded Courtyard, Haven of the Spirit Dragon, Cavern of Souls |

Binding semantics:

- **Multiple `fetch:` tokens are a UNION** of target sets ("a Forest or Plains
  card" → either satisfies it). The basic-restricted typed case gets its own
  `fetch:basic-<type>` token precisely so no AND/OR ambiguity ever exists between
  independent tokens.
- **Fetch tokens are NOT gated on destination or card type.** They fire on lands
  (fetchlands), creatures (Wood Elves), and sorceries (Farseek) alike, and
  regardless of battlefield-vs-hand destination — the census question is "does
  this card's search have targets", which is the same question for Expedition
  Map as for Wood Elves. The existing `ramp` derivation (search+onto the
  battlefield) is **unchanged**; the tokens coexist (Evolving Wilds already
  carries `ramp` today and will carry `ramp;fetch:basic`).
- **The typed-fetch regex must match land-type NAMES, not the word "land"** —
  that miss is why Farseek has no flags today. Scan the search clause (sentence-
  scoped, up to the period, matching the module's existing conventions) for
  `plains|island|swamp|mountain|forest` case-insensitively, with `basic`
  detection deciding `fetch:X` vs `fetch:basic-X`. "Snow-Covered" and Wastes are
  OUT OF SCOPE (note it in the docstring; `fetch:basic` already covers snow
  basics since they are basics).
- `mana-restricted` is deliberately ONE token with no payload. Restrictions vary
  ("of the chosen type", "Dragon spells", "colorless spells") and the chosen
  type is unknowable from oracle text. Consumers count restricted sources in a
  separate bucket and say what it means; they never guess the restriction's
  scope. Emit on any face whose text contains a "spend this mana only" clause —
  land or not (only lands are counted downstream today, but the token is honest
  wherever it fires).
- `fetch:*` and `mana-restricted` map to **NO classify() role** — do NOT touch
  `mtglib.FLAG_ROLES`. Farseek/Wood Elves/Llanowar Elves are already curated
  RAMP (mtglib.py:638-641); lands short-circuit to role `land` before the flag
  layer (mtglib.py:733-735). Role counts, power scores, and optimizer guardrails
  must be byte-identical before/after this phase (test it: classify() output
  unchanged on a fixture set with the new tokens present).
- `_parse_flags` needs **zero changes** — verified: `:` and `-` round-trip
  through the ';'-join → CSV → split pipeline untouched.

### A2. `FlagsVer` — the column that makes staleness detectable

The trap three independent code-reads converged on: **Flags has no None state**
(`Card.flags` defaults to `set()`, unlike `produced`'s `None`), and a new token
in the existing column defeats the repo's append-a-column staleness mechanism.
An attrs file enriched *before* this vocabulary shows Unclaimed Territory with
empty Flags — indistinguishable from *verified unrestricted*. Treating stale
files as verified would be the exact silent lie this repo exists to prevent.

So the vocabulary version rides the existing mechanism by BECOMING a column:

- `oracle_flags.VOCAB_VERSION = 2` (module constant, documented in the contract
  table; bump on any future vocabulary change).
- `carddb.ATTRS_HEADER` appends **`FlagsVer`** strictly LAST, after `Power`
  (append-at-end is the repo's whole back-compat story: positional-append +
  read-by-name). Every written row carries the integer. The `--no-ids` path pops
  `Scryfall` by name-derived index and is unaffected.
  **This is NOT a free append — it breaks a pin that must be updated in the same
  commit:** `tests/test_carddb.py::test_header_is_the_ten_pinned_columns_in_order`
  asserts the exact ten-name list AND `header[-1] == "Power"` (verified at
  test_carddb.py:109-116). Update it to the eleven-column list, change the tail
  pin to `header[-1] == "FlagsVer"` / `header[-2] == "Power"`, and rename the
  test. `tests/test_collection_produced.py:117-121` compares against
  `carddb.ATTRS_HEADER` itself and its `[7]`/`[8]` index checks survive
  append-at-end untouched.
- `mtglib.Card` gains `flags_ver: int = 1`. **The version must be written by the
  SAME file-application that writes the flags** — this is the phase's subtlest
  rule and two independent reviewers found the same hole in the naive version:

  > `ATTRS_OVERLAYS` layers snapshot-then-private (mtglib.py:456) and
  > overwrites `card.flags` whenever the LATER file has a Flags column
  > (mtglib.py:428-429). In the exact window H2 creates — snapshot regenerated
  > by Monday's cron (leg 1), private CSV not yet re-enriched (leg 2) — the
  > snapshot sets `flags_ver=2`, then the stale private file overwrites `flags`
  > with v1 tokens while `flags_ver` **stays 2**. Unclaimed Territory would then
  > read as *verified unrestricted at v2* while carrying v1 flags: precisely the
  > silent lie A2 exists to prevent, produced by A2 itself.

  So in `overlay_attrs` (and `deckcore.apply_attrs`): whenever a file's Flags
  column is applied to a card, set `flags_ver` from THAT file's `FlagsVer` cell
  if the column is present, and otherwise **reset it to 1** — the writing file's
  implied vocabulary. Flags and their version are one write, never two.
  **Test:** a v2 snapshot layered under a FlagsVer-less private file yields
  `flags_ver == 1`, not 2.
- `deck_stats.analyze`'s explicit Card copy list gains `flags_ver=ref.flags_ver`
  — **the codemap calls that list "the ONLY route a Card attribute takes to
  deck-level analysis"; a field omitted there is silently invisible everywhere**
  (this bit the Power column once already). `mtglib.Card(...)` is constructed
  with keyword arguments at both sites (mtglib.py:276, deck_stats.py:51), so a
  new defaulted dataclass field is safe.
- Deck-level `.attrs.csv` does NOT gain the column (those companions don't even
  carry Sub-types; the census runs on collection-level enrichment, and the
  fresh-clone story rests on the committed snapshot — see H2).
- The attrs-snapshot Action's plausibility gate hard-codes its required-column
  list (attrs-snapshot.yml:113-115): add `FlagsVer` there, keeping every
  load-bearing string in NON-comment lines (`tests/test_card_flow.py:473-505`
  checks comment-stripped code).

### A3. Tests and contract updates (this phase's blast radius, enumerated)

- **Fix the `ramp` miss the same way, deliberately:** `_SEARCH_LAND_RE` requires
  the literal word "land" (`\bland`; "island" does NOT match — verified by
  running the compiled pattern against the four wordings), so no typed fetcher
  has ever earned `ramp` — Farseek, Nature's Lore and Wood Elves are all
  flagless in the committed snapshot. New rule: when any `fetch:*` token fires
  AND "onto the battlefield" appears in the same face's clause, also emit
  `ramp`. Scope it per FACE, matching the v1 rule it extends (`"onto the
  battlefield" in t`), not per clause. Those three are curated RAMP by name
  (mtglib.py:638-641) so
  `classify()` never noticed, but any UNCURATED typed fetcher is invisible to
  the flag layer today. This is a one-line consequence of the typed regex, not
  a separate feature — and it means `test_carddb`-style round-trip fixtures for
  those cards change flags from `''` to a real set.
- `tests/test_oracle_flags.py` asserts EXACT set equality throughout. Update
  deliberately: `CULTIVATE` becomes `{'ramp', 'fetch:basic'}`. Add fixtures with
  real oracle wordings: FARSEEK (`ramp` + its four typed tokens — battlefield
  destination), WOOD_ELVES (`ramp`, `fetch:forest`),
  EVOLVING_WILDS (`ramp`, `fetch:basic`), NISSAS_PILGRIMAGE
  (`ramp`, `fetch:basic-forest`), UNCLAIMED_TERRITORY (`mana-restricted`, and
  `produced_of` still all six letters — the token OVERRIDES nothing at
  derivation time), EXPEDITION_MAP (`fetch:land`, no `ramp` — to-hand
  destination), HOUR_OF_PROMISE (`fetch:land`, `ramp`). Sol Ring / Guildgate /
  Command Tower / Maze of Ith pins must come out UNCHANGED. **Write a NEW test**
  `test_the_new_tokens_do_not_disturb_the_mana_vocabulary` asserting exactly
  that (it does not exist yet — the current pins are separate per-card tests at
  test_oracle_flags.py:75, :178); it is the tripwire for the whole phase.
- `.github/scripts/live_schema_check.py`'s hardcoded EXPECT list: update
  Cultivate's entry and add the new fixture cards. **This fails at the next
  manual recertify run, not in CI — do it in the same commit or it is a time
  bomb.**
- Docstring tables to extend in the same commit: `oracle_flags.py:21-42` (the
  ratified contract — note the amendment against
  `docs/spec-engine-upgrades.md` §4.2), `goldfish.py:23`, `mtglib.py:7-10`.
- `carddb --audit-flags`: no structural change (it prints whatever flags exist),
  but its display truncates the flags column at 27 chars — widen to 48 so a
  multi-token fetch list is legible in the human audit.
- New tokens are **inert everywhere by construction** (verified):
  `classify()` ignores unknown tokens via `FLAG_ROLES.get`; goldfish reads
  flags by explicit membership only; `_parse_flags` has no whitelist. State
  this in the commit message with the three file:line cites so the reviewer
  doesn't re-derive it.

---

## Phase B ☑ SHIPPED — Count what's actually there: restricted sources + the fetch census

### B1. Restricted sources — a SUBTRACTION from today's numbers (deck_stats)

Per-color source counting lives in `deck_stats.build_report`'s lands loop
(deck_stats.py:109-125) — **not** in manabase, whose own docstring misdescribes
this (manabase.py:12 says identity; the code counts lands' produced). The
change, mirroring the `color_sources_basis` pattern commit-for-commit:

- In the counting loop: a land with `'mana-restricted' in c.flags` AND
  `c.flags_ver >= 2` contributes its letters to a NEW `rep['color_sources_restricted']`
  dict instead of `rep['color_sources']`, and `basis` gains
  `'restricted_lands': <qty>`.
- A land with `flags_ver == 1` (pre-vocabulary enrichment) counts exactly as
  today — into the unrestricted pool — and bumps
  `basis['restriction_unknown_lands']`. **Unknown is not restricted and not
  verified-clean; it is unknown, and the label downstream says so.** (This is
  the empty-vs-absent rule applied one level up.)
- Quantities, not rows (`c.quantity` — the existing loop already does this).
- **Shape decisions, all binding** (the shape pin asserts both directions AND
  identical shape on enriched vs legacy bases, so "present only when nonzero"
  fails it):
  * `rep['color_sources_restricted']` — ALWAYS present, `{}` when nothing is
    restricted; both new basis keys always present, `0` on legacy data.
  * each `colors[]` row's `'restricted'` — always present, `0` when none.
  * `fetch['total_fetchers']` — the SUM OF QUANTITIES, not a row count (a deck
    can run two copies of a fetcher; the census counts copies everywhere else).
  * each census row's `'target_names'` — a list of **at most 6** names; the
    row's `'targets'` int carries the true total, the same cap+total convention
    `analyze()['risky']` / `['risky_total']` already uses.
- **Test blast radius (larger than one key-set pin — enumerate it or the commit
  is red):** `test_the_json_report_gains_exactly_one_key`'s `pre_a` set AND the
  three EXACT-dict-equality basis assertions at `tests/test_color_sources.py:76`,
  `:99`, `:107` (`== {"produced_lands": 9, "identity_lands": 0}` etc., all
  verified). Every existing fixture's attrs CSV lacks a FlagsVer column, so
  after A2 every land is `flags_ver == 1` and the unconditional
  `restriction_unknown_lands` bump changes the basis dict in all three.
  Everything must stay `json.dumps`-able: **lists, never sets** (auto_build
  `--json` dumps the whole mana payload).
- Expected consequence, stated so nobody "fixes" it: **Karsten source counts
  DROP on decks running Territory-class lands** once re-enriched, and some
  `ok` statuses flip to `low`. That is the correction working. The ur-dragon
  live case: W/U/B/R/G each lose ~4 sources' worth of dragons-only mana for
  non-dragon casting purposes.

### B2. The fetch census (manabase — it already receives `enriched`)

New pure function in `scripts/manabase.py` (imports stay `math` + `mtglib`):

```python
fetch_census(enriched)  # -> {"rows": [...], "total_fetchers": int,
                        #     "unknown": None | "pre-vocabulary" | "no-subtype-data"}
```

- A fetcher = any enriched card with ≥1 `fetch:*` token. Per row:
  `{"name", "qty", "spec": sorted(tokens), "targets": int,
    "target_names": first 6 + count, "state": "ok"|"thin"|"none"}` —
  `thin` below **3** targets, `none` at 0 (constants `FETCH_THIN = 3`, module
  level, documented).
- Target resolution (UNION across the card's tokens):
  `fetch:land` → all lands; `fetch:basic` → `mtglib.is_basic` lands;
  `fetch:<type>` → lands whose `subtypes` contain the Type (basics carry their
  subtype from the collection CSV / attrs snapshot, so they qualify naturally);
  `fetch:basic-<type>` → is_basic AND subtype match. Count `c.quantity`.
  The fetcher itself is not its own target; no name matching is needed anywhere
  (this works on Card objects — the `//` trap does not apply).
- Honesty gates, in order: if NO enriched card in the deck has `flags_ver >= 2`
  → `unknown: "pre-vocabulary"` and rows empty (the surface renders "fetch data
  unavailable — re-enrich to unlock", the produced-model pattern). If typed
  tokens exist but ≥1 nonbasic land has no subtype data (name-only collection)
  → census still counts what it can, and `unknown: "no-subtype-data"` rides
  along so surfaces append "counts may be low: N land(s) have no type data".
- `manabase.analyze()` gains top-level key `'fetch'` = that dict, and each
  `colors[]` row gains `'restricted': int` (from
  `rep['color_sources_restricted']`; 0 when absent). analyze() has NO shape
  lock (verified — test_manabase.py pins only the hypergeometrics), so these
  are free additions; the per-color skip when demand==sources==0
  (manabase.py:139-140) means **not all five rows exist — never index by
  color**.
- Two new `_explain` entries — `'fetch'` and `'restricted'` — following the
  what/why/healthy shape. `tests/test_explainers.py` iterates a HARDCODED key
  list; extend it by hand or the new entries are silently untested. Wording for
  `restricted`: "N land(s) here make mana with a spend restriction (e.g. 'the
  chosen creature type only'). They're counted separately: for spells that
  match, add them back in." Wording must be number-free or passed into
  `_explain` (it is rebuilt per call — see manabase.py:180).
- CLI: `manabase.py`'s `__main__` prints the census (rows + states) and the
  restricted line after the existing color table. deck_stats' CLI identity
  warning block gains the restricted/unknown sibling lines.

### B3. Tests (Phase B)

- Census unit tests with a hand-built enriched list: typed union (Farseek-style
  4-token spec vs a deck with 1 Mountain + Sheltered Thicket → 2 targets),
  basic-only vs typed (Nissa's Pilgrimage does NOT count Sheltered Thicket;
  Wood Elves DOES), `fetch:land` counts everything, quantity math (4 Mountains
  = 4 targets), thin/none thresholds, the two `unknown` gates, fetcher-not-own-
  target.
- Restricted counting: a `mana-restricted`+`flags_ver=2` land moves from
  `color_sources` to `color_sources_restricted` (both directions asserted);
  a `flags_ver=1` land stays put and bumps `restriction_unknown_lands`;
  Karsten `status` flips `ok→low` when restriction subtraction crosses the
  target (the acceptance-shaped test).
- JSON round-trip: `json.dumps` the whole report and the whole mana payload.
- Fixture note: conftest's `collection_file` has no attrs sibling (everything
  `produced=None`, `flags_ver=1`) — enriched-state tests write their own attrs
  CSV beside a tmp collection, the `test_color_sources.py:29-35` pattern.

---

## Phase C ☑ SHIPPED — Surface it everywhere mana already surfaces (five render sites, count them)

The Mana tab is ONE renderer (the app deck page IS `build_dashboard.generate`
output — there is no deck.html), but the mana dict renders in FIVE places total.
A census that skips one violates the codemap's no-knowledge-dies-in-its-section
rule on day one:

1. **`build_dashboard.manabase_html`** (dashboard Mana tab, both app + CLI):
   census table (name · spec · targets · state chip) + restricted line in the
   colors table (render `restricted` beside `sources` as "17 (+4 restricted)"),
   each with its `explain_html` entry. Append AFTER the existing manabase
   section content. **Window-based test landmines:** do not insert anything
   between `@media print` and its first 200/400 chars
   (test_dashboard.py:98-102, test_explainers.py:66-69), and nothing inside the
   3000-char window after 'Worst-sequenced cards' (test_dashboard.py:185-188 —
   different tab, but stay aware). Card links: emit **both** `data-card` and
   `data-key`, which is what every existing `.cardlink` does
   (build_dashboard.py:488-500, :559, :841; test_dashboard.py:188 asserts both
   are present) — the dashboard panel binds `[data-key]` and the app panel
   binds `[data-card]`, and matching the sibling markup keeps one convention
   instead of two.
2. **`webapp/templates/assess.html`** — hand-rendered Karsten table gains the
   restricted column + a census block; every new `<table>` needs `tablewrap`
   within 200 chars before it (test_assess_page.py:52-56).
3. **`webapp/templates/build_deck.html`** — same additions to ITS hand-rendered
   table (it also hardcodes the identity caveat in template prose today — move
   that string to the explain dict while there, or at minimum don't add a
   second hardcoded caveat).
4. **`_assess_packet`** (webapp/app.py:743-752) — text lines:
   `restricted sources: ...` and a `FETCH CENSUS` block with the same states.
5. **`manabase.py` CLI** (done in B2).

Plus the per-card note: `build_card_details` (per-deck panel payload inside the
dashboard) gains `fetch_targets: {n, state}` for fetcher cards, rendered in the
inlined `scripts/assets/card_panel.html`. The site-wide `/api/card` panel is
deck-agnostic by design — it does NOT get this (state why in the commit:
`card_api.card_payload` has no deck context, and the deck-scoped read that
exists is `/api/deck/<stem>/advise`).

Tests: census text present on dashboard render (both editable modes), assess
page, packet; identity/pre-vocabulary labels fire ONLY in their conditions
(copy `tests/test_collection_produced.py:194-204`'s enriched-vs-legacy pair);
existing tab-structure invariants stay green.

---

## Phase D ☑ SHIPPED — Re-evaluation on manual edits: a standing banner, not a flash

**Flask flashes DO NOT render on deck pages** — `/deck/<stem>` returns raw
generated HTML with no `get_flashed_messages` (the ⚡ flashes already suffer
this: they appear late, on the next base.html page). And the after_request memo
backstop evicts any "before" analysis a diff would need. So feature 4 is NOT a
flash and NOT a diff:

- **A render-time Mana-health banner**, computed in `generate()` from the same
  memoized analysis the page already holds (~free): shown when the census has
  any `none` row, or any color's post-restriction status is `low` AND
  `lands < LAND_RANGE[0]`. One line, warn-styled, linking to the Mana tab:
  "⚠ Mana health: Wood Elves has 0 fetch targets · 33 lands (template floor
  36) — see Mana tab." Because it is computed at GET time from current state,
  **every manual edit re-evaluates it automatically on the reload the panel
  already performs** — idempotent, always current, no state carried between
  requests. Cap it: one line, top 2 findings + "+N more".
- The Mana tab's label gets a warn marker under the same condition. **Text
  only** — `tabs_block` renders `<label …>{esc(lab)}</label>`
  (build_dashboard.py:957), so any `<span class='chip'>` markup would render as
  literal escaped text. Use a character: `"⚠ Mana"`.
- `deck_add`'s JSON verdict gains an optional `"mana_note"` string when the
  added card is a fetcher with `thin`/`none` targets — the panel already
  renders verdict JSON, so the note appears at the moment of the add.
  **Compute it in `deckcore.advise_card`**, which already loads the deck and the
  collection and already owns the verdict shape; the route stays dumb (it has no
  analysis in hand after `_invalidate`, and re-deriving one there would pay for
  a second pipeline run).
- `LAND_RANGE` comes from deckcore. `build_dashboard` already imports deckcore
  (spoke→hub, legal). Do NOT add the floor check to manabase unless you also
  add the deckcore import there — precedent exists (deck_stats imports deckcore
  top-level, cycle-free because deckcore imports engines only inside
  functions), but the smaller change is computing the banner in
  build_dashboard where both dicts are in hand.
- **Never** auto-run the optimizer from these paths; the banner is read-only
  advice. The singleton-ILLEGAL banner injection (webapp/app.py:347-358) stays
  separate and unchanged.

Tests: banner appears for a deck with a stranded fetcher and NOT for a healthy
one; appears after a simulated manual edit through the app client (write deck →
GET → edit via `/deck/<stem>/card` → GET again, assert the banner state
changed); `mana_note` in the add-route JSON for a thin fetcher.

---

## Phase E ☑ SHIPPED — Optimizer guards: the land passes may not strand a fetcher

Scope: `optimize.py` pass 1 (weak-nonbasic upgrades, :568-588), pass 2 (basics
repair, :590-611), and the buy-land pairing (:633-644). All three consume the
same `weak_lands` list and share state only through `used_land` — so the guard
needs a **running ledger**, not per-swap checks against the original deck
(pass 1 can schedule one Swamp-typed cut and pass 2 convert the other in the
same run, each individually "leaving one").

- **Ledger:** before the passes, compute `type_counts` = {basic-type:
  total qty of deck lands carrying that subtype (basics count via name)} and
  `demanded` = union of typed-fetch demands across the deck's `fetch:<type>` /
  `fetch:basic-<type>` tokens (spells, creatures, AND lands — a fetchland's
  demand counts). Every accepted land action updates the ledger.
- **Guard rule (v1, deliberately minimal):** an action may not take a demanded
  type's count to **zero**. Thin-target advisories are the census's job; the
  optimizer only refuses to *strand*. Applies to: pass 1 cuts (skip that victim,
  try the next), pass 2 victim selection (skip), pass 2's *incoming* basic
  choice (see below), and the buy-pairing's `Replaces` target (advice must obey
  the same rule the writes obey — the exact lesson the riser-veto fix of
  2026-08-14 taught: **advice the tool would not take itself is worse than
  none**).
- **Pass 2's basic chooser drops the alphabetical round-robin** for
  pip-proportional selection: move `_basics_by_demand` from `auto_build` to
  `deckcore` (hub; both spokes consume it — spokes may not import each other),
  leave a shim in auto_build, and have pass 2 pick the basic type the deck's
  pips (and, tie-breaking, the fetch demand) most need. Deterministic and
  stable — **idempotency is a stated invariant**: a second run must find
  `n_basic >= want_basic` and no-op, and a guard that oscillates basics between
  types breaks it. The two basics-COUNT formulas (auto_build's floor-6 vs
  optimize's actual-lands scaling) stay separate — only the apportionment
  helper unifies.
- **Degrade honestly:** on a name-only collection the cut land's subtypes are
  unknown — follow the same layered precedence as pass ownership (real type
  data → deck section signal → nothing) and when a land's types are unknown,
  **skip the guard for that land and count it in the report's existing
  `untyped` note** — never guess (the Hidden Lair rule). Both passes already
  skip entirely without field data; the guard lives inside them and inherits
  that gate.
- **Report, don't mutate shapes:** `land_swaps` stays a 3-tuple (positional
  consumers). Add a parallel `land_guard` list to the report dict
  (`{"kept", "type", "for": [fetcher names]}`) + CLI lines
  (`   ~ kept <land>: last <Type> for <fetcher>`) + a `_flash_optimize` line.
- Tests: ledger-across-passes (the two-Swamp case above — pass 1 takes one,
  pass 2 must refuse the other); guard skips on unknown types with `untyped`
  bumped; pip-proportional basics deterministic + idempotent (run twice,
  second run no-ops byte-identical); buy-pairing obeys the rule; **mutation
  test the ledger:** revert it to per-swap original-deck checks and the
  two-Swamp test must fail.

---

## Phase F ☑ SHIPPED — auto_build: prefer lands the deck can actually fetch

- The weight goes in the **land-take re-rank at auto_build.py:218-221 — NOT in
  `deck_fit.assess_card`**. The scorer is shared with the optimizer's
  `value_of` and the Cuts ranking; a land-fit component there silently moves
  swap values everywhere and re-opens the calibrated fit-swing budget
  ((shortage−depth)×2 < margin, tripwire-tested). The sublist re-sort is the
  zero-blast-radius slot.
- Fetch demand at land-pick time (lands are chosen BEFORE spells — step 1
  precedes step 2): derive it from the candidate POOL — the land sublist's own
  `fetch:` tokens plus the top `spell_budget` nonland candidates in the already-
  sorted `cands` (a projection of what step 2 will take). Weight = a stable
  sort-key tiebreak `(score, fetchable_bonus, original_index)`; it may reorder
  the land sublist but **must not change how many lands are taken** (the
  exactly-100 / section-count tests pin the arithmetic).
- Fix the latent basics leak while there: filter `mtglib.is_basic` out of the
  step-1 nonbasic sublist explicitly (today only sort-stability keeps 40x
  Island out of the "nonbasic" pass in the decks_dir=None path).
- The census itself reaches Build-Next output for free (auto_build already
  routes through `deckcore.analyze_cards` → `mana`).
- Tests: a custom collection with a typed dual + an equal-scored tapland + a
  Farseek-class candidate → the dual is taken first; without the fetcher, the
  original order holds; land count unchanged in both; basics never enter the
  nonbasic pass.

---

## Phase G ☑ SHIPPED — Goldfish: one honest sentence, one schema bump, NO game-logic changes

The sim's model gaps are real but out of scope (spend-restriction payment needs
a `_pay` redesign + data SimCard doesn't carry; fetch modeling touches the draw
stream, RNG-stream separation, file-order CRN pairing, and the cards_seen
convergence invariant — four silent-failure modes at once). v1 ships exactly:

- An `_assumptions()` line when the deck contains enriched `produces==set()`
  lands or `fetch:`-flagged nonland cards: "fetch effects are not modeled:
  fetchlands add no mana here, and fetch creatures/sorceries don't find lands."
  (Enriched fetchlands are ALREADY dead lands in the sim, and enrichment makes
  Wood Elves strictly WORSE — a working identity-fallback dork becomes a
  zero-mana body. The label stops that from being a silent surprise.)
  **Mechanism, because the naive version is not computable:** `_assumptions`
  receives only `compiled`, and `SimCard` has NO flags slot — `compile_card`
  reads `card.flags` for amount/etb/rock/dork and drops them
  (goldfish.py:139-141, :210). The land half is derivable (`is_land` +
  `model=='exact'` + empty `produces`); the fetch-flagged-nonland half is not.
  So `compile_deck` records a **data-only** key on the compiled dict —
  `compiled['fetch_flagged'] = [names]` — populated where it already inspects
  each card. No SimCard slot, no game logic, no reordering (the file-order CRN
  pairing must not move). Note `recompute_model` (goldfish.py:284) cannot
  rederive it, so any path that rebuilds a compiled dict must carry the key
  forward — check `simulate_ab`'s arm-B construction.
- **`REPORT_SCHEMA` 2 → 3 in the same commit** — assumptions text is part of
  the cached report; without the bump, cached decks keep the old list until an
  unrelated mtime change. One bump, batched with nothing else pending; it
  flushes sim AND A/B caches (shared key base) — on the server, the first view
  of each deck after deploy re-simulates once. Say so in the commit message.
- BACKLOG note (in this spec, not code): fetch modeling would copy the
  disruption pattern — a second `random.Random(seed ^ CONST)` stream so the
  shuffle stream is untouched — and must keep tutored cards out of
  `cards_seen`. Not now.

---

## Phase H — Rollout: the data lags the code, on purpose; make the lag honest

### H1. What happens at merge (nothing, and that's correct)

New tokens exist only when enrichment RE-RUNS — flags are the storage, there is
no oracle text at rest. Until then every surface shows the `pre-vocabulary`
honesty label from B2 and all numbers are unchanged. No coordination bug is
possible **because** of A2's FlagsVer gate. State this in the PR body.

### H2. The three re-enrichment legs, in order

1. **Committed snapshot:** the attrs-snapshot Action deliberately does NOT
   trigger on carddb/oracle_flags edits — after merge, trigger
   `workflow_dispatch` manually (or wait for Monday's cron). The gate's required-column list must gain
   `FlagsVer` — **not** because an un-updated gate would block the new snapshot
   (it only exits on columns that are MISSING; extra ones pass), but for the
   opposite direction: once `FlagsVer` is required, a runner still on an old
   carddb REFUSES to commit a pre-vocabulary snapshot instead of doing it
   silently. This is what lights up fresh
   clones and sandboxes. (The committed snapshot is currently one generation
   behind ALREADY — 8 columns, no Power — live proof consumers tolerate old
   shapes indefinitely; the dispatch also heals that.)
2. **Server private CSV:** a PythonAnywhere console run —
   `python3 scripts/carddb.py --collection data/collection/collection.csv` —
   or a fresh `/collection/upload` (background enrichment). Until this leg, the
   server census reads pre-vocabulary. **Overlay trap, verified in code:** the
   private file's Flags column wholesale overwrites the snapshot's per card
   (later-wins keyed on column presence), so a stale private file EATS the
   snapshot's new tokens for owned cards — leg 2 is not optional if leg 1 ran.
3. **Player PC** (if a local attrs file exists there): same command, whenever
   convenient; the app works honestly either way.

### H3. Post-rollout acceptance (the ur-dragon case, closed-loop)

On the server after legs 1–2: `manabase.py --deck data/decks/the-ur-dragon.txt
--collection data/collection/collection.csv` shows (a) Wood Elves census row
with **5 targets** (2 Forest + Festering Thicket + Sheltered Thicket +
Scattered Groves), state `ok`/`thin` per the threshold; (b) Farseek with ~10;
(c) a restricted bucket of **≥ 3 lands** (Unclaimed Territory, Secluded
Courtyard, Haven of the Spirit Dragon; likely Maelstrom + Study Hall — count
what enrichment finds, don't force 5); (d) per-color sources visibly lower than
today's 17/15/15/21/17 with `low` flags accordingly. Then `carddb.py
--audit-flags` and eyeball ~30 rows. If any of these read wrong, the data is
wrong — fix derivation, re-enrich, re-check; do not paper over in the surface.

---

## Explicitly NOT in scope (do not implement)

- Goldfish fetch/restriction *modeling* (G ships the label only; backlogged).
- Snow-specific or Wastes fetch tokens; artifact/creature tutors (Stoneforge);
  any non-land search.
- Mapping `fetch:*`/`mana-restricted` into `FLAG_ROLES` or classify() — role
  counts must not move.
- Restriction *payloads* (what the mana is restricted TO) — one bucket, labeled.
- Auto-rewriting any manabase, auto-adding lands, or changing the optimizer's
  land COUNT behavior — floors are advisory (the banner), the guard only
  refuses strandings.
- The Cuts/dead-weight land exclusion stays; the census is the land-critique
  surface now.
- deck-level `.attrs.csv` schema changes (no Sub-types, no FlagsVer there).

## Acceptance (spec-level)

- Farseek, Wood Elves, Evolving Wilds, Unclaimed Territory each carry the
  documented tokens after enrichment (fixture-level in CI; live via H3).
- `classify()` role output and `power.py` scores byte-identical pre/post Phase
  A on the full committed snapshot (write the comparison test; this is the
  "vocabulary is inert outside its consumers" proof).
- Ur-dragon's census shows 5 Forest targets for Wood Elves; restricted sources
  render as "+N restricted" beside every affected color on all five surfaces.
- A deck whose enrichment predates v2 shows the pre-vocabulary label — never
  zeros, never silence — on every surface that would have shown the census.
- The two-Swamp ledger test proves the optimizer cannot strand a fetcher across
  passes; the basics chooser is pip-proportional, deterministic, idempotent.
- The Mana-health banner reflects a manual edit on the very next page load with
  no optimizer involvement.
- Suite green throughout; `scripts/` stdlib-only; no `spec-table-ready.md` §0
  invariant weakened; every new number ships with its explain entry and honesty
  label.
