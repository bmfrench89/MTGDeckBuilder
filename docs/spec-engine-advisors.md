# Spec — Engine advisors: new arrivals + field risers

**Status:** ☑ shipped 2026-08-10 · code: `mtglib` (Date Bought column),
`deckcore.new_arrivals()`, riser capture in `optimize.optimize()` ·
surfaces: Decks page card, assess packet, CLI preview · tests:
`tests/test_engine_advisors.py`

## 1. The failure that motivated this

Three genuinely good, recently-acquired cards sat unused while every deck reported
"already aligned with the field":

- **Codsworth, Handy Helper** — 30% inclusion for the equipment commander it fits;
  the deck's weakest incumbents sat at 11–14%. Gain: 19 points. The optimizer's
  **anti-churn margin gate requires ≥25**, so it was silently skipped.
- **Mana Drain** — only 15% on a young commander's page: new-commander fields skew
  toward what early adopters built, so *commander-page inclusion undervalues
  universally powerful staples*.
- **Smaug, Wicked Worm** — 12% and climbing; the field lags new printings.

Root cause, stated honestly: **the optimizer is a follower.** Field inclusion is a
trailing indicator, and the margin gate — which exists for the good reason that
decks shouldn't churn — also suppresses information the deck's owner would act on.

## 2. What shipped (advisory, never automatic)

1. **New arrivals** (`deckcore.new_arrivals`): the collection loader now keeps the
   export's `Date Bought`/`Date Added` column (newest date across printings).
   Cards acquired in the last 30 days that are in **no** deck surface on the Decks
   page, each tagged with the decks whose color identity can run it. Degrades to
   nothing on a name-only snapshot — it never guesses. Basics never surface.
2. **Field risers** (in every `optimize()` report, shown in the CLI preview and
   the assess packet): owned cards with a free copy that would beat the deck's
   current weakest cut but fall inside the margin gate — reported as
   *"own it, gate held it: X (30%) over Y (11%) — 19 pts short of auto-swap"*.
   The gate still refuses the swap; the player stops losing the information.

Both are read-only. Acting on either goes through the app's normal add/replace
flow, which records the change as **manual** — permanently protected from the
optimizer. That division of labor is deliberate: the machine follows the field
conservatively; the human out-builds the field; the machine then defends the
human's calls.

## 3. Planned next: bracket-filtered field data (needs an Action run to verify)

EDHREC now publishes bracket-filtered pages (the owner builds toward the Bracket-3
average deck, not the all-brackets average). Whether `json.edhrec.com` exposes
bracket-specific JSON cannot be probed from this sandbox (egress-blocked) — but
the **field-snapshots GitHub Action runs with open internet**, so the experiment
is: extend `edhrec.py --snapshot-all` to attempt bracket-variant endpoints and
commit whatever succeeds, exactly how the original snapshot mechanism was proven.
Until then, snapshots remain the all-brackets commander page.
