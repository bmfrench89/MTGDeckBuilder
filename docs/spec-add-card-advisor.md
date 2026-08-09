# Spec — Add a Card to a Deck + Optimizer Opinion on Manual Adds

**Status:** ☑ **SHIPPED 2026-08-09.** `deckcore.advise_card()` / `deckcore.manual_adds()`
· `webapp/app.py` (`_insert_deck_card`, `_validate_add`, `/deck/<stem>/add`,
`/api/deck/<stem>/advise`, `/api/deck/<stem>/sections`) ·
`scripts/assets/add_card.{html,css}` · `optimize.manual_adds_review()` ·
tests in `tests/test_add_card.py` + `tests/test_deck_edit.py`.

> **Deviations from this spec, and why:**
> 1. **The advisor lives in `deckcore` (the hub), not `deck_fit`.** `deck_fit` is a pure
>    scoring engine that imports only `mtglib`; orchestrating a full deck analysis from
>    inside it would have inverted the dependency rule. `advise_card()` sits next to
>    `analyze_deck()` and imports engines locally, exactly like its neighbours.
> 2. **The picker is its own asset pair** (`add_card.html` / `add_card.css`) rendered into
>    the Decklist section, rather than living in the card panel. The panel is per-card;
>    Add is a deck-level action.
> 3. **Added `/api/deck/<stem>/sections`** — not in the spec, but the picker needs the
>    deck's own free-form section labels, and hardcoding a list would have violated the
>    data-format rule.
> 4. `advise_card()` accepts a **pre-computed `analysis=`** so the optimizer's review can
>    score N manual adds against one deck analysis instead of N.

·
**Player ask:** "I need a way to add a card if one is removed from a deck, and then
I want the optimizer to check manually added cards and see how they fit into the
deck with an opinion like current cards in the deck."
**Prior-art validation:** joliverson/mtg_deck_rec ships candidate-card evaluation
"with weighted scoring (synergy, inclusion rate, strategic fit, mana efficiency)";
flegars/mtg-deckbuilder returns "structured, explainable advice instead of vague
'this card is good' replies" — see `docs/research-prior-art.md`. Our
`deck_fit.assess_card()` already computes an equivalent component breakdown; this
feature is **wiring, not new engine work**.

## 1. Problem

The card panel supports **Remove** and **Replace** (`POST /deck/<stem>/card`,
`webapp/app.py:218`), but there is no **Add**. Once a card is removed, the only
way to refill the slot is a full-file edit. And when the player does add a card by
hand, nothing tells them how it fits — the optimizer deliberately never
second-guesses manual edits (a rule this spec **keeps**), but silence isn't the
same as respect: the player asked for an *opinion*.

## 2. Part A — Add a card

### Entry point
An **"＋ Add card"** control on the deck page (editable surface only — the app;
CLI-rendered dashboards stay read-only, same as Remove/Replace today). Opens a
sheet in the existing card-panel style: search box → owned-card autocomplete →
section picker → Add.

### Search
Reuse **`/api/collection/search`** (`webapp/app.py:232`) — it already does
owned-card autocomplete with `ci=` color-identity-first ordering. Pass the deck's
identity so in-color cards sort first. Off-identity cards still appear (the API
returns them) but render disabled with the reason.

### Section picker
Populated from **the deck file's own `# --- Section ---` labels** (free-form
sections are a data-format rule — never hardcode a section list). Preselect a
suggestion via `deck_fit.primary_role(card)` → `section_role` mapping; the player
can override.

### Validation (server-side, in order)
1. **Ownership** — name resolves in the collection (incl. `owned_additions.txt`).
   Uses `mtglib` normalization (`front_face`/`_norm`/`lookup`) — never a naive
   string compare (the `//` split-card trap, CLAUDE.md).
2. **Singleton** — reject if already in the deck, unless basic land.
3. **Color identity** — **hard block** off-identity adds (it's an illegal deck,
   not a style choice), with the offending pips in the message.
4. **Pins** — if `pins.csv` reserves the card for another deck, warn-and-confirm
   (soft): the player's word beats the reservation, but they should know.
5. **Deck size** — warn (not block) when the add pushes past 100.

### Write path
Extend `_edit_deck_card` (`webapp/app.py:191`) with `action="add"`: insert
`1 <name>` as the last line of the chosen section, preserving every other line,
comment, and quantity byte-for-byte (the `test_deck_edit` contract). After the
write, run **`optimize.singleton_violations()`** and surface any hit immediately —
the repo's known-trap rule: this check runs after *every* write.

### Logging
Append to `<stem>.changes.csv` — schema already `Card,Added,Replaced,Source` —
with **`Source=manual-add`**. Two things fall out for free: the dashboard's
14-day **NEW badge** already renders from this file, and the advisor (Part B)
gets its trigger. Replaces via the existing panel should start logging
`Source=manual-replace` in the same PR (one-line change, gives the advisor
coverage of both manual paths).

## 3. Part B — The advisor (an opinion, never an action)

### The invariant, stated first
**The optimizer still never cuts or reverts a manual add.** `optimize.py`'s
protection model is untouched. The advisor is a read-only verdict attached to the
card. (This is the line flegars draws too — advice, structured, not enforcement.)

### Verdict engine — already exists
`deck_fit.assess_card(card, rep, ctx, refs, section_label)` returns the component
breakdown (color / role / curve / staple / theme), `band_for(score)` the tier, and
`better_alternatives()` the "consider instead" list. `card_api` already serves
per-card panel JSON. The advisor = calling what exists, for the cards
`.changes.csv` marks `manual-*`, and rendering three ways:

1. **Immediately on add** — the add-sheet's success state shows the verdict card:
   band + score, one context line (the existing `_context_line`), field inclusion
   % when EDHREC data is cached, and up to 3 alternatives. The player gets the
   opinion at the moment it's actionable.
2. **Persistently in the dashboard** — manual adds already get the NEW badge; add
   a small fit-band chip next to it (e.g. `NEW · fit B+`). Tapping opens the card
   panel, which gains an "Advisor" line for manual adds. Both surfaces share the
   panel — **check both hook systems** (`data-card=` app / `figure.mc[data-key]`
   dashboard), the CLAUDE.md trap.
3. **In the optimizer's preview** — `optimize.py --preview` (and `--json`) gains a
   read-only **"Manual adds review"** section: per manual add, the verdict and
   whether the optimizer *would have* preferred an alternative — explicitly
   labeled advisory. CLI parity keeps the skill's build/coach workflows honest.

### Grounding rules that bind the advisor
- Opinions come only from computed components + cached EDHREC field data — no
  invented synergy claims. If EDHREC data is missing, the verdict renders from
  fit components alone and **says so** ("no field data — fit-only opinion").
- Alternatives come from `better_alternatives()` (collection/curated/candidate
  pool) — never a free-text suggestion (the never-invent-a-card rule).

## 4. Tests

**Part A (`test_deck_edit.py` extensions — this file guards the riskiest code):**
add inserts under the right section preserving all other lines/comments ·
add of an existing nonbasic is rejected; basic land accepted · off-identity
rejected · unknown/unowned name rejected · `changes.csv` row appended with
`Source=manual-add` · singleton check runs post-write.

**Part B:** advisor verdict for a known-good add lands in a high band and a
known-off-plan add lands low (fixture decks in `tmp_path`) · with no EDHREC cache
the verdict renders with the fit-only disclaimer (offline-hermetic rule — no
network in tests) · `optimize --preview` output contains the review section and
**the tuned decklist is unchanged by its presence** (idempotence regression) ·
panel JSON includes the advisor block only for `manual-*` cards.

## 5. Acceptance criteria

- Remove a card on the phone → tap ＋ → search → pick section → Add → verdict
  shown, all without leaving the deck page.
- The deck file diff is exactly one inserted line plus one `changes.csv` row.
- `optimize --all --apply` after a manual add: the add survives, verdict appears
  in preview, second run still changes nothing.
- Suite green: existing `test_deck_edit` untouched tests unmodified and passing.

## 6. Open questions

- Should the advisor also score *pre-existing* cards on demand (a "rate this
  card" panel button for any card)? Cheap once wired — but scope-creep; default no.
- Verdict thresholds for the band chip (reuse `band_for` cutoffs as-is?).
- Where ＋ lives on the phone: floating button vs. a row in the Decklist header
  (decide with the subtabs layout, `docs/spec-deck-subtabs.md`).
