# Spec — Deck Page Subtabs

**Status:** ☐ specced 2026-08-09, not implemented ·
**Player ask:** "incorporate subtabs on the Decks page for all of the content we have.
it'll be easier to process being able to block through things like 'cards to buy'"
**Prior-art validation:** joliverson/mtg_deck_rec ships its results UI the same way
("Dark-themed interface with card imagery from Scryfall, **tabbed results**") — see
`docs/research-prior-art.md`.

## 1. Problem

A deck page is one long scroll of ~12 `<section>` blocks (verified in
`build_dashboard.py`, lines ~729–890): summary tiles · Decklist by Section · Mana
Curve · Ownership · Power & Bracket · Combo Watch · Game Plan & Player Notes ·
Color / Pip Demand · Consistency & Manabase · Buy & Replace · Commanders That Also
Fit This Shell · Shared Across Decks. On a phone (now the primary surface — the app
is hosted and PWA-installed) reaching "Buy & Replace" means scrolling past
everything else, every time.

## 2. Design

### Tab grouping (6 tabs, mapping every existing section — nothing dropped)

| Tab | Sections it shows | Why grouped |
|---|---|---|
| **Deck** *(default)* | tiles · Decklist by Section · Ownership | "what's in it" |
| **Mana** | Mana Curve · Color/Pip Demand · Consistency & Manabase | one mana story |
| **Power** | Power & Bracket · Combo Watch | "how strong / how it wins" |
| **Buy** | Buy & Replace (+ NEW-badge changes recap) | the player's named use case |
| **Plan** | Game Plan & Player Notes | reading mode |
| **More** | Similar Commanders · Shared Across Decks | occasional-use |

Decision (not open): tabs are a **presentation regrouping only** — section HTML,
generators, and their tests keep working unchanged. No content is moved between
generators.

### Mechanism — CSS-only, self-contained

Radio inputs + labels + `:checked` sibling selectors, **inlined in the existing
`<style>` block**. No JS required for switching; a ~10-line inline script adds two
progressive enhancements: (a) deep links — `#tab-buy` in the URL opens Buy, and
clicking a tab pushes the hash, giving the player a bookmarkable "cards to buy"
link per deck; (b) remembering the last tab per deck in `localStorage`.

Why not JS-driven tabs: the dashboard must stay a **single self-contained file**
(`test_dashboard` enforces: no external links) and must render sanely wherever a
saved .html lands. CSS tabs degrade to "everything visible" if anything breaks.

### Hard constraints (each maps to an existing repo rule)

1. **One `generate()`, two surfaces.** Tabs render in both the editable app page
   and the CLI-rendered file. `editable=False` changes nothing about tabs.
2. **Hidden ≠ removed.** Inactive tabs hide via CSS (`display:none` on the
   *panel*, content kept in DOM) — so both surfaces' card-panel hooks
   (`data-card=` in the app / `figure.mc[data-key]` in dashboards) keep their
   targets, and in-panel Remove/Replace keeps working. **Check both surfaces** —
   the known trap from CLAUDE.md.
3. **Print shows everything.** `@media print { all panels display:block }` — a
   printed/PDF'd dashboard is the full report, tabs collapse to headings.
4. **Design tokens only.** Tab bar spacing/type from `tokens.css` vars; colors
   from the theme's existing surface vars (tokens.css must stay color-free —
   `test_design_tokens` enforces).
5. **Phone ergonomics.** Sticky tab bar (`position:sticky; top:0`), horizontal
   scroll on overflow, ≥44px touch targets, active tab visibly distinct in all
   5 themes (default/yshtola/cloud/rakdos/spider).
6. **No service-worker interaction.** Deck pages are network-only by design
   (`test_pwa` guards this); tabs are pure markup, nothing new to cache.

## 3. Implementation sketch

All in `scripts/build_dashboard.py` (the app inherits automatically):

- Wrap each emitted `<section>` group in `<div class="tabpanel" id="tab-<key>">`.
- Emit `<nav class="tabs">` of radio+label pairs right after `<header>`.
- Add tab CSS to the inlined stylesheet; add the small hash/localStorage script
  next to the existing inlined panel JS.
- The section-emitting code already builds the page as an ordered list of
  `*_sec` strings (`power_sec`, `combo_sec`, `buy_sec`, …) — regroup those
  variables; no generator function changes.

## 4. Tests (extend `tests/test_dashboard.py`)

- Every pre-tab `<h2>` heading still present in output (nothing lost).
- Still self-contained: no external stylesheet/script links added.
- Exactly one default-checked tab; every `tabpanel` id matches a nav target.
- Print CSS block present and covers all panels.
- Editable flag still gates the edit affordances and nothing about tabs.
- All 5 themes render the tab bar (reuse the theme loop in `test_design_tokens`).

## 5. Acceptance criteria

- On the phone PWA, "Buy" is reachable in one tap from deck open, no scrolling.
- `https://…/deck/<stem>#tab-buy` opens directly to Buy & Replace.
- A CLI-rendered dashboard file opened from disk shows identical tabs; printing
  it yields the full multi-section report.
- Card panel opens from a card in any tab, on both surfaces.
- Suite green; no new failures in `test_dashboard`, `test_design_tokens`, `test_pwa`.

## 6. Open questions (small; decide at implementation)

- Tab labels/order above are a proposal — player may want "Buy" second.
- Should the changes/NEW recap live in Buy or Deck? (Spec says Buy; cheap to move.)
- `localStorage` last-tab memory: per-deck or global? (Spec says per-deck.)
