# Spec — UX refresh: a phone edit loop the household can trust

**Status: Wave 0 SHIPPED 2026-10-14; Wave 1 next.** This file is the live tracker; tick its boxes.
**Player ask (2026-10-14):** "What about general app improvements or UI/UX updates. Perform
deep research and spec out and implement what you think could be best for this site."
**Evidence:** [`research-ux-2026-10.md`](research-ux-2026-10.md): five research passes (the
leading deck-building sites, collection apps, mobile/PWA practice, player pain points) and
a hands-on audit of every page of the running app at phone and desktop sizes. Competitor and
player evidence is from search extracts (the sandbox could not open those sites); the audit
is first-hand (screenshots, timings, axe-core, scripted flows).

## 1. The finding in one paragraph

The most valuable work is not a new feature but a phone edit loop the household can trust:
every one-tap edit validated and undoable, every deck opening on a searchable list instead
of fifteen screens of card art, and one ownership line ("2 owned · 1 in Iron Fortress ·
1 free") wherever a card appears. Players' loudest unmet wishes on Moxfield and Archidekt
(which deck holds each copy, real undo, one pool shared by several people) are things this
app's database already models; the gap is presentation. Meanwhile the audit found edit
flows that silently damage decks, and every one of them passed the existing UAT gate,
because that gate photographs pages and never runs a flow.

## 2. Guardrails (every wave)

- **Keep what works** (each item records a past incident): the Arcane Ledger contrast
  system (axe found zero contrast failures) and its rule that a status colour always
  travels with a word; the universal focus ring; 44 px primary controls; `asset()`
  fingerprinting with the service worker's cache-first/network-first split (`upgrade.js`);
  preview-before-write intake; honest "estimate / unknown / unreachable" labels; the card
  panel as a sheet on phones and a drawer on desktop; the Watch tab; the mulligan
  trainer's decide-first design; a generated dashboard stays ONE self-contained file.
- **Change the phone layout in slices**: keep the old path reachable for one release, keep
  Add one tap from the deck, never bury a primary feature under More, and count taps per
  core flow against the baseline in §6.
- **Words for people, not for the repo**: no file names, engine codes or "run X on your PC"
  in anything the player reads.

## 3. Wave 0 — stop the damage (each XS–S)

| # | Change | Acceptance |
|---|---|---|
| 0.1 | [x] **Replace is validated.** The replace route runs the add route's checks (colour identity, duplicates, the commander); the panel's replace search only offers cards in the deck's colours | Replacing into an off-colour card is refused with a message; search results for replace are in-colour |
| 0.2 | [x] **Add card files by type.** The section picker defaults to "By card type" (the deck-sections rules); a write that leaves the deck at other than 100 cards or other than its commander count says so | Cultivate lands under Sorceries; "Deck is now 101 cards" warning |
| 0.3 | [x] **The ⚡ report reaches the player.** The deck page renders flash messages (app surface only); an optimizer failure is logged and shown, never swallowed | After ⚡ the dashboard shows the summary; a failing run shows an error |
| 0.4 | [x] **`[hidden]` always hides** (app + dashboard CSS); **Assess uses the same clock** as the rest of the app | Mulligan: one hand logs once; Assess shows "combat T9" where the deck card does |
| 0.5 | [x] **One markdown-lite renderer** for the Plan tab and the table card: paragraphs join wrapped lines, lists, headings, bold, italic | No `**` or `*` on either screen; one sentence stays one bullet |
| 0.6 | [x] **Wishlist checkboxes work** (labelled "Got it", remembered on this device) and **unknown prices say unknown**, never "~$0.00" | |
| 0.7 | [x] **Copy pass:** hosted-app wording (footer, offline page, delete confirm, batch preview in database mode); deck titles instead of file slugs (Wishlist, Shared, Pins, Activity, card panel); plain words for change sources and activity verbs | No "run.bat", "your machine", `owned_additions.txt` or `manual-replace` in player-facing text in database mode |
| 0.8 | [x] **gzip** text responses ≥ 1 KB when the browser accepts it | `/collection` transfers ~117 KB instead of 1.23 MB |
| 0.9 | [x] **UAT that behaves like a player:** `sweep.js` fails below 24 px and warns below 44 px, overlays and scrollers included; a new `flows.js` runs replace, add, optimize and mulligan and reads the results back | Every Wave 0 bug fails `flows.js` on the old code and passes on the new |

**Wave 0 as built:** also guarded the commander from one-tap swaps; named every ⚡ swap
in its report; the notes reader handles tables, quotes and strikethrough (two decks' notes
carry tables); a trimmed table-card point never leaves a `**` open; deck lists use " · "
because titles contain commas. `flows.js` failed 5 checks on the old code and passes all
9 on the new; the stricter sweep found one real sub-24 px target (the panel's score
toggle, fixed) and warns on the Pins Apply buttons and the chip rows (Wave 1).

## 4. Wave 1 — a safe, findable deck (M each)

| # | Change |
|---|---|
| 1.1 | [ ] **Undo.** A toast after each panel edit ("Replaced Hulking Raptor with Cultivate · Undo", ≥10 s, paused on focus, `role=status`); a permanent Undo on each row of the deck's Changes page; "Restore this version" over stored revisions; a ⚡ run undone as one batch. Each undo is a new inverse edit through `deckcore.append_changes` with a manual source, so the optimizer never churns it. The Optimize confirm stops promising what doesn't exist until then |
| 1.2 | [ ] **Phone deck page.** Tab bar inside the first screen (a one-line summary that expands into the tiles); every tab visible (short labels or an edge fade); the Deck tab defaults to a text list (48–56 px rows with a small thumbnail, name, cost, ownership mark) under collapsible section headers with counts; an in-deck filter box; client-side group (section, role, mana value, colour) and sort; the chosen view remembered per device; the image grid one tap away; tap the panel image for a full-screen zoom; tap a curve bar to filter |
| 1.3 | [ ] **Card panel on `<dialog>`:** name, ownership line and actions first, then text, then art; 44 px close; deck titles as links; a visible "Simulate first" button (no Shift-click); Back closes the sheet; focus moves in and returns |
| 1.4 | [ ] **The dashboard inside the shell:** bottom bar and rail on deck pages, one "⋯" menu, titles and back links on deck sub-pages; Activity, Import, New arrivals in the More sheet; "Phone" setup out of it |
| 1.5 | [ ] **Accessibility batch:** labels on every control, focusable card names, underlined links in text, `main` landmark and a skip link, `color-scheme: dark`, `scroll-padding` under sticky bars, a `--target` size token, the smallest type token raised to 12–13 px, inputs at 16 px |

## 5. Waves 2 and 3 — collection, speed, differentiators

| # | Change |
|---|---|
| 2.1 | [ ] **Collection rebuild:** search first; server-side filtering with a real "Load more" link; `content-visibility: auto`; location chips (free / in a deck / pinned / claimed twice); filters in the URL; downloads, uploads and status behind "Manage"; "Every change is logged · last backup <time>" |
| 2.2 | [ ] **Ownership everywhere:** ✓ free / ◐ claimed by another deck / ✗ not owned on every deck row; "97/100 owned · 3 shared" in the deck header; "add all missing to the wishlist" |
| 2.3 | [ ] **Global search** sheet from the header, with the ownership line and deck links on each result |
| 2.4 | [ ] **Batch preview:** "already own 2 · in Ur-Dragon" per row, merged duplicates, a quantity stepper, fix a ✗ row in place, drafts kept on the device |
| 2.5 | [ ] **Speed and offline:** self-hosted fonts through `asset()`; navigation preload; a saved copy of each page served when offline under a "Saved copy from 14:02" banner; Speculation Rules prefetch (moderate, side-effect links excluded); cross-document view transitions; `width`/`height`/`srcset` on card images; card text from the server, not a live Scryfall call from the phone; warm the deck analyses after each sync; a self-hosted `web-vitals` beacon |
| 3.1 | [ ] **Table mode:** full-screen "Show the pod" card leading with the declared bracket and its evidence; "Keep screen on" (Screen Wake Lock) |
| 3.2 | [ ] **Game log:** one tap per deck — won/lost, turn, against whom, how it felt |
| 3.3 | [ ] **Mulligan trainer polish:** images in a 4+3 grid, big Keep/Mulligan, tap-to-bottom, land count, a link back to the deck |
| 3.4 | [ ] **Android extras:** Share Target into the import preview, manifest shortcuts, Web Share |
| 3.5 | [ ] Per-deck **proxy** and dated **"lent to"** states beside pins |

## 6. Baseline to beat (audit, 412 px)

| Core flow | Today | Target after Waves 0–1 |
|---|---|---|
| Open a deck and read one card | 2 taps + 1.7–11.9 screens of scrolling; text needs a live Scryfall call | 2 taps + a few letters in the deck filter |
| Swap one card | 4 taps; instant, off-colour allowed, no undo | 4 taps; colour-checked; Undo toast |
| Find which deck holds a card | 2 taps, 3.3 screens to the search box, ~1.2 screens in the sheet; answer as slugs | search icon, a few letters, read the row |
| Paste three cards into the collection | 4 taps after 1.36 screens of scrolling | 4 taps, no scrolling |
| Check the wishlist | 1 tap, then 19.7 screens of tables | 1 tap; grouped by deck and collapsed |

## 7. Decisions for the player

- **D1. Optimizer preview sheet.** Today ⚡ applies its swaps (a deliberate, documented
  design). Players asked Moxfield for "propose, then approve". Wave 0/1 make a run visible
  and undoable; a preview sheet (each swap with its reason, field % and fit, approved or
  skipped) is the next step if the player wants it. Same question as the target
  architecture's D4.
- **D2. Watch the household use it.** Half an hour of the two members building, swapping and
  playing outranks any further desk research, and should come before Wave 3.

## 8. Declined on purpose

Camera scanning, printings/foil/condition, physical binders, value-over-time charts and price
alerts (no price history; prices are estimates by rule), a life counter (a crowded field),
and "AI builds your deck" framing (players treat "AI generated" as an insult; the app's
wording is "suggestions from field data and your collection").
