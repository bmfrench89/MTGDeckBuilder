# Deck-flow review (2026-10-15)

**Source.** The player had Gemini review the build workflow (the "How a Deck Gets Built"
page) and asked for every bundle: "i think all of these are good but cross check them too
to be sure". Each note was checked against the code and the live data before anything was
built. This file is the tracker and the design note for the bundles still to come.

## The cross-check

| # | Note | Verdict | Evidence |
|---|---|---|---|
| 1 | Read the engine before auto_build; every drafted card needs a keep verdict | Agree | Consecrated Sphinx entered the Ur-Dragon as draft filler and survived because nothing argued it out |
| 2 | Archetype- and colour-aware role quotas | Agree, confirmed | `auto_build.ROLE_QUOTA` was fixed (4 counters even in mono-W) and filled before tribal seeding. Both the Giada and Thorin drafts pulled in Rebuff the Wicked as a "counter" |
| 3 | Name 2-3 packages before judging cards (2nd-order synergy) | Agree | Shattered Angel was cut card-vs-commander and restored once the each-end-step package was named |
| 4 | "Ob Nixilis can't be in mono-white Giada" | **Wrong** | Ob Nixilis, the Ascended is {5}{W}{W}, a white Angel (Scryfall-verified). The proposed notes-name check is low value: a phantom name protects nothing, because protection applies only to cards in the deck |
| 5 | The top-25 overlap is a hard fail | Partly wrong | It was never a CI gate; the rule was "below ~50%, say so". The denominator point is right: measure coverage of what the player OWNS |
| 6 | Smaller swap margin for generic slots | Agree, done safely | A flat 15 would let role-template pressure (worth up to 24) invent swaps again. The lower bar applies only between two generic cards (both under 2x lift), and only on a gain the field shows in inclusion % |
| 7 | Rank reads by Scryfall oracle tags | Partly | Oracle tags exist only as a Scryfall search filter, not in any card data we can store. Reads are already capped (3 per role, fit floor) and lift-ranked. Keyword overlap between the engine notes and verified oracle text is the feasible version (bundle C) |
| 8 | Utility lands and MDFCs in land swaps | Already handled | Lands making none of the deck's colours are never judged; lands the field runs in ≥25% of decks are kept; notes-named lands are protected; MDFCs with a spell front are spells and never enter the land pass |
| 9 | Soft vs hard claims, and a Trades lane | Agree, with a correction | The core tier must be a deck's explicit `## Protected engine` list, not any mention in its notes. The Ur-Dragon's notes name Consecrated Sphinx only to explain its bracket. Only 5 of 11 decks have that list today |
| 10 | Pre-computed AI verdicts for the phone app | Agree | Fits the 2026-10-14 decision: no AI calls from the app |

## A. Quick wins — SHIPPED (this PR)

- `auto_build.role_quota(identity, archetype)`:
  - Archetype aims are clamped into each archetype's acceptance band (a tripwire test
    covers every archetype word × identity).
  - When two archetype words disagree, interaction (removal, wipe) takes the lower aim
    and engine roles take the higher.
  - No counterspell quota without blue. Those slots (`PROTECTION_AIM` = 3) go to
    protection drawn only from the verified `resilience_staples.csv`.
  - Live: the Giada and Thorin drafts no longer contain Rebuff the Wicked or Mana
    Tithe. They take Swiftfoot Boots, Clever Concealment, Bofur and Thorin Oakenshield.
- `optimize.GENERIC_MARGIN` = 15, applied between two generic cards (lift under
  `GENERIC_LIFT` = 2.0), on an inclusion gain only. Unmeasured lift gets no discount.
  - Live, all 11 decks: two new proposals. Dina gets Cultivate (in for Feed the Swarm);
    Kami gets Mana Drain (in for Archaeomancer).
  - The tuned decks (Giada, Thorin, Ur-Dragon, Tifa, Sephiroth) are unchanged.
- `optimize.field_coverage`: the top 25 split into in / owned-but-out (free, or held by
  which decks) / not owned. It's printed by the CLI, in `--json`, and in the assess
  packet. Raw overlap becomes a warning; owned coverage is the validation number.
- Packages: card-review-method step 3 now names 2-3 packages before judging any card,
  and notes carry a `## Packages` section.

## B. AI verdicts on the phone — NEXT

- **The data:** a session records its read of each proposal and read in
  `data/decks/<stem>.verdicts.json` through a CLI (`optimize.py --verdict "<key>"
  <swap|skip|bench|wishlist> "<why>"`), never hand-written JSON.
- **Keys:** proposal keys for swaps, card names for reads.
- **On the phone:** the ⚡ page shows "Claude's read (date): Skip — reason" beside a
  proposal whose key is still current. Verdicts whose proposal is gone are hidden and
  counted, never shown against a different swap.
- **The rule it keeps:** the app still makes no AI calls. Verdicts arrive with the
  repo sync.
- **Cross-check:** the server recomputes proposals on the full private collection, so a
  key can differ from the session's. Matching on the key means a verdict appears only
  for the exact swap it judged.

## C. Engine-first builds

- **The engine spec:** a session writes it before auto_build:
  - the named engine cards (verified text, counted pool);
  - 2-3 packages;
  - optional role-aim overrides;
  - engine keywords, regexes over oracle text.
- **The draft:** `auto_build --engine <spec>` seeds the engine cards before any quota,
  applies the aims, and labels every other non-land card *filler: needs a keep
  verdict*. The hand pass must give each one a verdict. A check reports filler left
  without one.
- **Data gap found in the cross-check:** keyword matching needs oracle text, and the
  collection stores derived flags only. The spec's engine-card list works today. The
  keyword ranking (note 7's feasible version) needs an oracle-text cache written at
  enrichment time (gitignored, like `data/cache/`).

## D. Trades between decks

- **The core tier:** a deck's explicit `## Protected engine` list. Clip-featured cards
  and `manual-replace` adds also count as core. A deck with no list treats every
  notes-named card as core (conservative).
- **Prerequisite:** write `## Protected engine` lists for the six decks without one
  (Bartolomé, Beorn, Captain America, Kami, the Ur-Dragon, Y'shtola). Until then
  their cards can't be offered.
- **The lane:** for deck X, a card held by deck Y that isn't core in Y and is valuable
  in X (field-listed, lift ≥ 2.5, or in X's engine spec). Each offer is paired with a
  free backfill for Y in the same role. It's shown in X's review as a trade and never
  applied without the player's approval for both decks.
- **Expected first result:** once the Ur-Dragon's engine list exists without the
  Sphinx, the Ur-Sphinx build gets Consecrated Sphinx offered as a trade automatically.
