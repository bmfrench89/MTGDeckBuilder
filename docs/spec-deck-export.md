# Spec — Deck export: printable HTML report, PDF via the browser

**Status: ☐ Not started.** Written 2026-08-15 by a scoping session (Fable 5) for an
implementing session (Opus 5) to follow explicitly. Player request, same day:
*"add the ability to export a deck as an html report/pdf report."*

**Branch:** `claude/deck-export-html-pdf-ofyd6d` · one PR, squash-merged.

---

## 0. For the implementing session — read this before writing any code

This spec was written by a different session than the one executing it. Nothing below
is optional, and the **Corrections** in §1 exist because the scoping session got them
wrong first — do not re-derive them.

**Read first, in order:** `CLAUDE.md` · `docs/codemap.md` · this spec end to end ·
`scripts/build_dashboard.py` lines ~1190–1360 (the CSS block you will extend) ·
`webapp/app.py` lines ~54, ~121–160, ~713–730 (`_txt`, the auth gate, the sibling
export routes).

**Repo-wide invariants that apply here** (the full list is in
`docs/spec-table-ready.md` §0; these are the ones this work can break):

1. `scripts/` stays **stdlib-only** — CI uninstalls Flask and imports every module bare.
2. Generated dashboards stay **one self-contained file**; no new external assets.
3. `tokens.css` carries **no colours and no fonts** — but see §2 for why literal
   colours are *correct* inside the print block specifically.
4. Tests are **offline and hermetic** — everything in `tmp_path`, network clients
   monkeypatched; never touch the real `data/`.
5. New webapp routes are **auth-gated by default** (`app.before_request` +
   `_PUBLIC_ENDPOINTS` allowlist at `webapp/app.py:121`). Do NOT add the new
   endpoint to `_PUBLIC_ENDPOINTS`.
6. Card images are **browser hotlinks, never server-side fetches**
   (`docs/card-images.md`). Nothing in this spec fetches an image server-side.
7. Substantial commit messages (subject = user-visible outcome; body = root cause,
   fix in layers, what was verified — see `git log`). Update `docs/handoff.md` when
   this lands.

---

## 1. The decision, and the corrections that shaped it

### 1a. No server-side PDF generation. This is settled — do not revisit.

Three repo constraints all point the same way:

- **stdlib-only `scripts/`** rules out WeasyPrint / reportlab / pdfkit in the engine;
  putting PDF only in `webapp/` would break the one-shared-code-path property
  (`build_dashboard.generate()` serves both the CLI and the app identically).
- **Images are browser hotlinks only.** A server-side renderer would produce PDFs
  with no card images unless it violated that rule.
- **The hosted app runs on PythonAnywhere's free tier** — no cairo/pango, no
  headless Chrome.

The browser already solves all three: it has the images, it paginates properly, and
"Save as PDF" is in every print dialog including iOS. **PDF export = a print
stylesheet that actually works + Ctrl+P.** That reframes the whole feature as two
small gaps in things that already exist.

### 1b. What already exists (verified against source, 2026-08-15)

- `build_dashboard.generate()` already emits a **self-contained single-file HTML
  report** — `tokens.css` and the card panel are inlined via `_asset()`;
  `tests/test_dashboard.py::test_dashboard_renders_and_is_self_contained` enforces it.
  The CLI writes it with `--out`; `refresh.py` batch-renders every deck.
- A `@media print` block exists at `scripts/build_dashboard.py:1340`. It already does
  four correct things: hides the tab bar, forces every `.tabpanel` to
  `display:block !important`, hides `.ac`, and forces collapsed `.explain` `<details>`
  open ("the caveat is part of the number").
  `test_dashboard.py::test_printing_restores_every_tab` pins the first two.
- `/export/deck/<stem>.txt` exists (`webapp/app.py:722`) with the `_txt` helper
  (`app.py:54`) setting `Content-Disposition: attachment`, and a `?raw` escape hatch.
- The index page (`webapp/templates/index.html:51–60`) has a per-deck actions row:
  Images · Export · Assess · Mulligan · 🃏 Table card · Edit · ⚡.

### 1c. What is actually broken/missing (the two gaps this spec closes)

- **Print is illegible.** Every theme is dark (`THEMES` at `build_dashboard.py:41` —
  `void: #0d1117` etc., light `--text`). Browsers drop dark *backgrounds* when
  printing but keep the *text colour*, so Ctrl+P today produces pale-grey-on-white.
  The existing print block never inverts colours. (`table_card.html:101` already
  solved this exact problem for its own page — that's the model.)
- **The app can't hand you the file.** `/deck/<stem>` renders the dashboard live;
  there is no downloadable `.html` sibling to `/export/deck/<stem>.txt`.

### 1d. Corrections — the scoping session's own wrong first guesses

- **The table card is already linked** from `index.html:58` and already prints
  ink-on-paper correctly. Change **nothing** about the table card.
- **No `sw.js` cache-version bump is needed.** The service worker
  (`webapp/static/sw.js`) is network-first for all pages and API responses; only the
  static shell is cached. A new export *route* touches neither.
- **No auth-gate registration step exists.** The gate is deny-by-default via
  `before_request`; a new route is protected simply by not being in
  `_PUBLIC_ENDPOINTS`. There is nothing to add — only something to not do.

### 1e. Non-goals (out of scope, decided)

- Server-side PDF (§1a).
- **Proxy sheets** (3×3 grid of card images at exact 63×88 mm) — the one genuinely
  print-geometry-shaped feature this collection lacks. Worth its own spec and its own
  player decision; note it in `docs/handoff.md` as a backlog candidate, build nothing.
- Any change to the assess packet, table card, or `.txt`/ManaPool exports.

---

## 2. Phase 1 — a print stylesheet that produces a real paper report

**Where:** extend the existing `@media print` block inside the f-string CSS in
`scripts/build_dashboard.py` (currently at line 1340). One block, no new files.
Because both surfaces call `generate()`, this single change fixes the CLI-rendered
dashboards, `refresh.py` output, and the hosted app's `/deck/<stem>` page at once.

**Requirements, each testable:**

1. **Ink-on-paper inversion.** `body` (and any element carrying `--void`/`--panel`
   backgrounds — panels, tiles, tables, the sticky header) go to white background,
   black text. Muted/secondary text may stay dark grey (≥ `#444`, per the table
   card's precedent). Accent-coloured text must not stay in its screen colour if
   that colour fails on white — force it to black or `#444`. Follow
   `table_card.html:101`'s pattern: `background:#fff !important; color:#000 !important`.
2. **Literal colours are correct here — do not tokenise them.** `tokens.css`
   deliberately contains no colours; colour is exactly what surfaces may differ on,
   and "printed paper" is a surface. Do not add print colours to `tokens.css`
   (`test_design_tokens.py` will fail if you try). Spacing inside the print block
   still uses the spacing tokens.
3. **Keep the four existing print behaviours** (tabs hidden, tabpanels expanded,
   `.ac` hidden, `.explain > p` forced open). They are correct and partially pinned
   by tests.
4. **Hide the interactive chrome.** In print, none of the following may render:
   the add-card picker (`add_card_block`), the bracket form (`bracket_form`), the
   card-panel modal (`card_modal_block`), and any buttons/forms the editable surface
   adds. **Read those three functions and enumerate their actual top-level
   class/element names** — do not guess selectors. A printed *editable* dashboard and
   a printed *read-only* one should contain the same content.
5. **Pagination hygiene.** `section { break-inside: avoid; }` where sensible (long
   sections like the decklist must still be allowed to break internally — apply
   avoid to headings-plus-first-content or to tiles/tables, not to a 100-card list),
   plus a sane `@page { margin: ... }`. The deck title `<header>` already leads the
   document; no running header machinery is required.
6. **The curve SVG must survive white paper.** `curve_svg()` takes the theme `t` —
   check what fills/strokes it emits and add print overrides if any of them are
   light-on-dark.
7. **Self-containment is unchanged.** No new assets, no external links
   (`test_tabs_add_no_external_assets` guards the tab CSS; keep the whole page clean).

---

## 3. Phase 2 — `GET /export/deck/<stem>.html` + the link to reach it

**Route** (in `webapp/app.py`, directly beside `export_deck` at ~line 722):

- Resolve via `deck_meta(stem)`; `abort(404)` on miss — same shape as siblings.
- Body: `bd.generate(m["path"], COLLECTION, title=..., commander=..., theme=...,
  decks_dir=DECKS_DIR, editable=False)["dashboard"]` — the same call
  `deck_visual` makes, minus `want_visual`, and explicitly **`editable=False`**:
  a downloaded file's edit buttons would POST to a server that isn't there.
- Response: `text/html` with
  `Content-Disposition: attachment; filename=<stem>.html`. Match `_txt`'s style
  (a `_html_download` helper beside it is fine); support `?raw=1` returning the
  bare page inline, for parity with every sibling export.
- **Skip the singleton-banner injection** that `/deck/<stem>` does — that banner is
  a live-surface alarm. The exported report already carries its own analysis.
- Auth: nothing to do (§1d) — just do not touch `_PUBLIC_ENDPOINTS`.

**UI link** (`webapp/templates/index.html` actions row, ~line 53): the row already
has `Export` (the `.txt`). Disambiguate: relabel the existing link **`.txt`** (title:
"ManaPool-ready list, qty + name per line") and add **`Report`** →
`url_for('export_deck_html', stem=d.stem)` with title
"Self-contained HTML report — open anywhere; card images need an internet
connection; print it (Ctrl+P) for a PDF". That title line is the honesty label for
the hotlink-images caveat — it must ship.

---

## 4. Phase 3 — tests

Offline, hermetic, `tmp_path` only. Follow the fixture pattern in
`tests/test_table_card.py` (monkeypatched `DECKS_DIR`/`COLLECTION`/`PASSWORD`,
`test_client`).

**Extend `tests/test_dashboard.py`** (print regression — the part that was silently
wrong until now):

- The `@media print` block contains the white-background inversion
  (assert `background:#fff` — or the exact literal you shipped — appears *inside*
  the print block, sliced the way `test_printing_restores_every_tab` slices; widen
  its `[:200]` window if needed rather than weakening the assertion).
- An `editable=True` render hides the add-card picker and bracket form in print:
  assert the print block references their real top-level selectors.
- Every theme in `THEMES` gets the same print block (loop, like
  `test_every_theme_renders_the_tab_bar`).
- Existing print/tab tests stay green untouched.

**New `tests/test_export_html.py`** (route behaviour):

- `GET /export/deck/d.html` → 200, `text/html`,
  `Content-Disposition` contains `attachment` and `d.html`.
- Body is the self-contained dashboard: contains a deck card name and the inlined
  tokens (e.g. `--sp-4`), contains **no** `/static/` references.
- Body has no edit affordances (assert the add-card picker's marker absent —
  mirror `test_add_card_picker_only_on_the_editable_surface`).
- Unknown stem → 404.
- With `PASSWORD` set and no session → redirected to login (pattern:
  `tests/test_auth.py`).
- `?raw=1` → 200 with no `Content-Disposition: attachment`.

---

## 5. Acceptance & landing

- `pytest` exit 0, offline; suite count grows (record before/after in the commit
  body, per house style).
- Sandbox verification: render `generate()` output for at least one theme and
  visually inspect the print block's computed effect (a headless-Chromium
  print-to-PDF via the pre-installed Playwright browser is a fine smoke check —
  in the *sandbox*, as a dev check; it is not a product feature).
- The automation-loop note for the PR: real-paper verification (an actual Ctrl+P on
  the hosted app) is the player's, post-merge — say so honestly in the PR body
  rather than claiming it was done.
- Update `docs/handoff.md` in place (current-state only): the export route, the
  print fix, and the proxy-sheets backlog note.
- One PR from `claude/deck-export-html-pdf-ofyd6d`; squash-merge; substantial
  commit message.
