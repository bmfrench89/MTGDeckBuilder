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

## The Fable review (2026-10-15) — FIXED

An independent review (Fable) found two real bugs and several precision issues. All are
fixed in the follow-up PR:
1. **101-card drafts (high):** an engine spec naming a land the land pass skipped gave a
   101-card draft, because the basics were sized before seeding. `auto_build` now recounts
   lands after seeding (test: a seeded land replaces a basic).
2. **Trades stripping a donor's protection (high):** Smuggler's Surprise, the hexproof
   answer in Beorn's wipe plan, was offered with Fog as the "backfill".
   - Notes-named cards are now core on every deck, matching the optimizer's cut
     protection.
   - `## Earmarked for other decks` releases a named card on purpose (the Ur-Dragon's
     Consecrated Sphinx).
   - Backfills need a functional role (ramp, draw, removal, wipe, counter).
   - Pins are respected, and a failing trades lane now warns instead of going silent.
3. **Lift precision (medium):** the baseline is now stored to one decimal. The wording
   "EDHREC's own definition" was corrected in spec-optimizer-judgment Phase D.
4. **The motivating case at build time (medium):** trades moved to `scripts/trades.py`,
   and `auto_build` now lists them on the draft. A fresh Kami draft is offered Consecrated
   Sphinx (earmarked) before any deck file exists. `## Protected cards` (Dina's heading)
   now counts.
5. **Audit burden (medium):** cards the commander's field runs in ≥10% of decks need no
   keep reason, and `--keep-many "<why>" A B C` covers a group.
6. **Low:** clamped spec aims are reported (`aims_clamped`), and `engine_missing` names
   banned and pinned cards precisely.
7. **The margin decision (low):** `GENERIC_MARGIN` reverses a Phase C note that a lower
   margin lengthens the tick list. The player asked for every Gemini bundle, and the
   measured cost was two extra proposals across 11 decks, so the reversal stands.
   Revisit if the ⚡ lists grow.
8. **Latent, not fixed:** `Card.is_land` would read a full "Sorcery // Land" type line as a
   land. Enriched data stores front faces only (0 of 57 live DFCs affected), so it can't
   bite today.

Fable confirmed the verdicts on Gemini's notes 4 (Ob Nixilis is a white Angel), 5 (no
overlap gate exists) and 8 (handled for enriched data).

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

## B. AI verdicts on the phone — SHIPPED

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

## C. Engine-first builds — SHIPPED

**Measured (Giada, same pool, spec taken from her notes' protected engine):** the draft
without a spec already held 58 of the final deck's 78 non-basic cards; with it, 61. So the
hand pass changes 23 cards instead of 26. That's a modest gain, because the scorer already
liked most of Giada's engine. The larger lever is the audit: none of the 23 can stay
without a written reason.

**Keyword reads, live:** an Ur-Dragon spec with the keyword "noncombat damage" puts
Niv-Mizzet, Visionary and Smaug the Impenetrable at the top of the field-silent reads. That
was the find a session made by hand on 2026-10-14. Coverage grows with each enrichment,
which now keeps every owned card's text in the local cache (opt-in in `enrich_api`, on for
the CLI and the server's background enrichment, off in tests).

**First full run: the Ur-Sphinx (2026-10-15).** The spec named 8 engine cards and 2
packages, and the draft seeded all 20 before any quota. The hand pass then changed 7
spells and 9 lands. The audit wanted reasons for 11 cards, and the field's 10% exemption
covered the rest. The run found two gaps, both fixed:
- **Writing a spec:** the CLI could only `--init` and `--keep`, though the docstring says
  specs are never hand-written. It gained `--commander` (init before the deck file
  exists), `--keyword`, `--aim` (roles checked against `auto_build.ROLE_QUOTA` by a
  tripwire test) and `--package`. A bad argument writes nothing.
- **Pins:** the `auto_build` CLI never told `build()` which deck it was drafting, so
  Consecrated Sphinx, pinned to the-ur-sphinx before the draft, came back "pinned to
  another deck". The CLI now passes `skip_deck` as Build Next does: `--stem`, defaulting
  to the `--engine` spec's filename.

### The original design

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

## D. Trades between decks — SHIPPED

**The cross-check changed the design twice:**
- **Donor protection:** "not core there" is not enough. The first run offered Talisman of
  Conviction out of Captain America (75% of its field) with no backfill, so an offer now
  needs a free same-role backfill, or a gain over the donor's field % of 15+
  (`TRADE_GAP`).
- **What counts as "matters here":** a generic rock worth 42 here is a shuffle, not a
  trade. It now means engine, ≥2.5× lift, or value 60+. The first run was mostly
  Fellwar Stones; the second offers Bugenhagen, Wise Elder (Tifa, from Beorn, 0% of the
  field there) and Elemental Bond (the Ur-Dragon, from Beorn).

**The tests caught two bugs:** another deck's commander could be offered, and hand-added
cards weren't read as core (the change-log rows are keyed `key`/`name`, not `Card`).

### The original design

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
