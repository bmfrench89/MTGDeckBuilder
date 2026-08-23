# Session Handoff — current state

**Purpose:** everything a new session needs to continue this project without
re-deriving it. This file describes the **current state only**; the full history lives
in git (`git log` — commit messages in this repo are deliberately substantial).
Architecture: `docs/codemap.md`. Working rules: `CLAUDE.md`. Grounding rules
(canonical): `.claude/skills/mtg-deckbuilder/references/grounding-rules.md`.

_Last updated: 2026-08-23._

## Kaalia of the Vast pivot — researched, built, and NOT recommended yet (2026-08-23)

The player played the Ur-Dragon for the first time, did not enjoy it, and asked whether
pivoting the commander to Kaalia of the Vast would run better on the owned cards. The deck
is built and committed (`data/decks/kaalia-of-the-vast.*`); the verdict in its `.notes.md`
is **not yet**, and the reasoning matters more than the answer.

**The diagnosis the player did not make.** Their hypothesis was "lacking the big cards and
lands". The lands half is confirmed and worse than it sounds — 52 of 64 nonland cards are
flagged risky-to-cast-on-curve, all five colours sit below Karsten's ~23-source target, and
only 11 of 36 lands enter untapped producing 2+ unrestricted colours. But the biggest
number in the whole analysis is one nobody named: **against one modeled board wipe the
Ur-Dragon's kill rate collapses 78.5% -> 12.8%** (mean damage −44.9, CI excludes zero).
36 creatures, zero recursion. The second is that **the commander lands in 36.1% of games**,
so the attack trigger the deck is named after is off in nearly two games in three. That,
not the top end, is almost certainly what "not a big fan" is.

**Why Kaalia is not the fix.** She solves exactly the two felt problems — commander on the
battlefield 36.1% -> **97.8%**, risky-to-cast 52 -> **40** — and makes the measured ones
worse: field top-25 in deck 20/25 -> 12/25, kill rate 78.1% -> 68.5%, and under a wipe
11.9% -> **4.1%** (she is a 2/2 the wipe also kills). Bracket 3 -> 2.

**The pool census is the hard constraint.** 50 owned Mardu-legal Angel/Demon/Dragon
creatures — but the MV histogram is {2:1, 3:1, 4:17, 5:20, 6:7, 7:4} and there is **not one
card above MV 7**. Kaalia's trigger is worth the mana you skip; 37 of 50 sit at MV 4-5.
Graded on verified text: 5 bombs, 16 solid, 21 filler, 8 unplayable. Every marquee payoff is
unowned (Gisela 79%, Aurelia 73%, Rune-Scarred Demon 71%, Avacyn 67%, Liesa 60%, Master of
Cruelties 59%). The optimizer's own verdict on the owned pool: *"this deck can't improve
from your collection: buy the gaps."* Those six cards are in the deck's `.buylist.csv`.

**Third options tested and rejected.** Miirym, Sentinel Wyrm (Temur) looked strictly better
on shard analysis — 27 dragons, 14 at MV 6+ against Mardu's 8, field top-25 18/25 — but
building it refuted that: **59 cards risky to cast, worse than the Ur-Dragon's 52**, because
the good Temur lands are committed elsewhere, and Temur has **zero** of the repo's 19
curated recursion staples. Vaevictis Asmadi (Jund) is symmetric and hands opponents
permanents. Field snapshots for both are now committed.

**The finding worth keeping.** Of the 19 curated resilience staples, **all 19 are owned**,
and 15 are Mardu-legal (7 protection, 8 recursion) against Temur's 7/0 and Jund's 7/2. The
Ur-Dragon's `rec 0` is a build choice, not a collection gap — Karmic Guide, Serra Paragon,
Haunted Crossroads and Along the Crooked Way are all free right now. **The cheapest fix for
the deck the player already owns is recursion, not a new commander.**

**Two repo defects found and fixed on the way:**

1. **`auto_build` could not build Kaalia at all.** `commanders.csv` gave her
   `tribal-hero` — Captain America's tag, copied — so the builder scored Hero (the
   player's deepest tribe) as her tribe on merit and returned a legal, tuned, Bracket-2
   deck containing **zero** Angels, Demons or Dragons, with no warning. Same family as the
   old `tribal-spiders` bug but worse: that one matched nothing, this matched the wrong
   cards. Fixed in data (her three real tribes) and in code — authored `tribal-` tags now
   UNION (a commander can care about several tribes), while subtypes read off the
   commander's own type line still compete. `ctx["tribal"]` is a frozenset now;
   `deck_fit._theme_component` and `build_deck.html` handle both shapes. Four tests.
2. **CI had been red on main since 2026-08-21T17:04**, on "Check deck section integrity",
   not on pytest. Hosted-app deck edits had accumulated 17 typed cards under contradicting
   sections (9 sorceries in dina under Instants, 7 in ur-dragon, Roaming Throne under
   Creatures). Fixed with `deck_sections.py --all --apply`; card multisets are provably
   identical. **Note for next time:** `optimize.py --apply` misfiles its swap-ins the same
   way, so the CLAUDE.md pipeline needs a second `deck_sections --apply` after optimizing.

**A claim that was tested and refuted.** An intermediate analysis held that the free Mardu
pool clears Karsten in all three colours once "any colour" lands are counted back in. The
verbatim text says no: Avengers Tower is Hero-only, Villainous Hideout Villain-only, Castle
Doom artifact-only, Jasmine Dragon Tea Shop Ally-only — colourless lands in a Kaalia deck,
and the exact trap the 2026-08-20 Ur-Dragon mana audit already caught. Real numbers
W 19 · B 17 · R 21.

**Evidence on disk** (109 cards, 0 UNVERIFIED, runner runs 32611590788 / 32612450375):
`data/reference/kaalia-verified-2026-08-23.txt` (all 50 cheat targets + Kaalia's verbatim
trigger + owned Mardu support) and `data/reference/kaalia-lands-verified-2026-08-23.txt`
(43 candidate lands). New field snapshots: `kaalia-of-the-vast` (refreshed),
`miirym-sentinel-wyrm`, `vaevictis-asmadi-the-dire`.

**The decision is the player's and it is still open.** The Kaalia deck and the Ur-Dragon
share 35 cards (26 `deck_conflicts` shortfalls) and cannot both be sleeved.

## Treasure deck scouting — commander shortlist, 2026-08-21

The player asked to build a Treasures deck. No deck file exists yet; this is the grounded
scouting that precedes the build, and the commander choice is **with the player**.

**The census is the finding.** A name-grep of `collection_snapshot.txt` for
`gold|treasure|riches|plunder|hoard` returns 13 cards and supports the wrong verdict — that
the collection has no treasure support. So every one of the **2,776 non-basic cards** went
through `carddb.py --verify` on the runner (`deck-verify.yml`, six runs; the full-collection
run's log is bounded so it was re-run in ~520-card chunks). Verbatim text is in
**`data/reference/treasure-verified-2026-08-21.txt`**: **57 owned Treasure producers**,
3 alternate win conditions, 25 artifact-count/sacrifice payoffs, 4 symmetric pingers.
The ones a name search cannot find are the ones that matter — Relic Retriever, Stark
Industries Executive, Currency Converter, The Misty Mountains Cold, HYDRA Assault Robot.

The classic pool is genuinely absent: no Goldspan Dragon, Dockside, Prosper, Xorn, Academy
Manufactor, Magda, Old Gnawbone, Brass's Bounty, Revel in Riches, Mechanized Production.

Field snapshots pulled this branch (basics excluded):

| commander | decks | top-25 | top-50 | top-100 | producers legal |
|---|---:|---:|---:|---:|---:|
| **Thorin, King of Durin's Folk** (RW) | 3,588 | **20 (80%)** | 36 (72%) | 63 (63%) | 37 |
| Smaug, Wicked Worm (BR) | 1,866 | 11 (44%) | 21 (42%) | 36 (36%) | 42 |
| Smaug the Impenetrable (BR) | 3,821 | 11 (44%) | 18 (36%) | 35 (35%) | 42 |
| Smaug the Magnificent (R) | 2,859 | 10 (40%) | 18 (36%) | 28 (28%) | 33 |
| Atsushi, the Blazing Sky (R) | 198 | 7 (28%) | 16 (32%) | 25 (25%) | 33 |

**Thorin is the recommendation and it is not close** — 32 Dwarves / 68 copies, and *every
card in the package is uncommitted*. Its engine is Dwarf-ETB Treasures (Fíli turns each
nontoken Dwarf into a token Dwarf, which triggers Thorin again; Bifur doubles every Dwarf
trigger once Storied is on, which two Treasures does). Win con: Balin, Loremaster's X damage
to each opponent, plus Hellkite Tyrant at twenty artifacts. Honest caveat recorded for the
player: it is Dwarf tribal *running on* Treasure, not a Treasure-theme deck.

**Two traps worth keeping.**

1. **The Smaug builds cannibalise the Ur-Dragon.** Smaug the Magnificent and Smaug the
   Impenetrable are single copies already sleeved there; Fiery Emancipation's only copy is in
   the brother's Bruce Banner gift deck. Smaug, Wicked Worm is the exception — 4 copies, 1
   committed.
2. **Smaug the Impenetrable's infinite does NOT assemble today.** Indestructible +
   damage-into-Treasure loops with any repeatable symmetric pinger, but all four owned
   pingers fail: Crypt Rats is a 1/1 that dies to its own activation, Warmonger cannot hit a
   flier, Thermo-Alchemist only hits opponents, Noxious Field taps. Pestilence or Pyrohemia
   (a couple of dollars) closes it. Buy list, not a combo claim.

**Revalidated 2026-08-21 by a second model, independently:** every number above
reproduced — the census counts (57 / 33 / 42 / 37), the field table digit-for-digit,
both Smaug rebuilds under the same 8-deck baseline (13-in-deck/12-unowned and
11-in-deck/14-unowned, both ending in the optimizer's "can't improve from your
collection"), Thorin's deck (100 cards, singleton clean, optimizer idempotent,
goldfish identical at seed 0). Three corrections from the recount, none changing
the verdict: the Thorin 99 carries **11** Treasure producers, not 10 — Dori,
Bearer of Friends was missed because GitHub Actions log-masking garbled its name
in the census corpus (repaired in the reference file); the census corpus was
missing the 7 chunk-5 texts (Skirmish Rhino…Skycoach Conductor, none
treasure-relevant, re-harvested); and the Impenetrable-loop check now covers six
pinger candidates, not four — Cave-In (one-shot sorcery) and Gangrenous Zombies
(self-sacrifice) also fail, so Pestilence/Pyrohemia remains the one missing card.

Shortlist published as an artifact for the player; the deck build waits on their pick.

## New deck — Dina, Essence Brewer (Witherbloom aristocrats), 2026-08-21

The player asked whether the collection supports "Dina or Witherbloom". It holds **four**
cards answering to those names, not two, and two are Secrets of Strixhaven (post-2025), so
the choice was made on verbatim Scryfall text pulled by `deck-verify.yml` (run 32442182052)
rather than memory — which had **Dina, Soul Steeper's second ability backwards** (it pumps
Dina; it does not shrink a blocker) and Beledros at `{3}{B}{B}{G}{G}` instead of `{5}{B}{G}`.

Ownership of each candidate's field, counted from four EDHREC snapshots this branch pulled
down (basics excluded):

| commander | decks | top-25 | top-50 | top-100 |
|---|---:|---:|---:|---:|
| **Dina, Essence Brewer** | 10,113 | **25 (100%)** | 49 (98%) | 81 (81%) |
| Beledros Witherbloom | 4,628 | 20 (80%) | 31 (62%) | 51 (51%) |
| Dina, Soul Steeper | 9,346 | 16 (64%) | 30 (60%) | 47 (47%) |
| Witherbloom, the Balancer | 15,702 | 10 (40%) | 18 (36%) | 28 (28%) |

Soul Steeper looks like the build and is not: its own engine is unowned (Essence Warden 69%,
Marauding Blight-Priest 67%, Prosperous Innkeeper 53%, Deathgreeter 51%, Witherbloom
Apprentice 45%). Essence Brewer's highest *missing* staple is Cauldron of Essence at 55%.
Both Soul Steeper and Beledros ended up in the 99 anyway.

**State:** `data/decks/dina-essence-brewer.txt` + `.notes.md` / `.attrs.csv` / `.changes.csv`.
100 cards, singleton clean, sections clean, **25/25 field top-25**, optimizer idempotent.
37 lands · B 25 sources vs Karsten 23, G 24 vs 19 · keepable 81% · commander mean T3.63 ·
screw 15% · flood 0% · Bracket 3, one Game Changer (Crop Rotation) · ramp 11 / draw 8 /
**removal 9** / Interaction 18.0/18.

**Two process findings worth keeping:**

1. **`deck_sections.py` must run AFTER `optimize.py`, not before.** The optimizer appends its
   adds to whatever section it finds, so a regroup done before tuning is stale by the time
   the deck is finished. The build pipeline is `auto_build -> deck_sections -> optimize
   --apply -> deck_sections`.
2. **`auto_build` selected this deck on the commander's TYPE LINE.** Dina is a *Dryad Druid*,
   so `_tribe_and_support` read "druid", cleared `_TRIBAL_MIN = 12`, and ran the on-tribe
   seeding pass; `deck_fit._theme_component` then pays +15 for "on-tribe (Druid)", worth up
   to ~16 valuation points to a card with 0% field presence — enough to survive a pass that
   otherwise demands a 25-point inclusion gain. Sixteen of 41 creature slots are Druids and
   ten have under ~2% field presence. **This is not a defect to fix blind** — the deck still
   scores 25/25 — but it is where the next round of cuts comes from, once those ten are
   verified. They are queued in `data/reference/verify-queue.txt`.

**Open, deliberately:** protection counts 0 and was left there (every curated option is
committed elsewhere or scores negative fit on this commander). Recursion counts 0 largely as
a display artifact — `resilience_staples.csv`'s recursion role has **zero green rows**, so a
Golgari deck's ceiling on that axis is 2, and `resilience_axis` bands on `prot` alone.
**Vito, Thorn of the Dusk Rose** is the one card worth buying: the only owned copy is
load-bearing in `yshtola-nights-blessed`, and it is the magnitude-aware lifegain payoff this
deck lacks (Soul Steeper drains 1 per lifegain *event*, regardless of size).

**Round-2 verify queue: answered** (run 32450437172; text in
`data/reference/dina-verified-2026-08-21.txt`, verdicts in the deck's `.notes.md`).
**Final Act is a KEEP** — modal, and the creature mode *destroys*, so the deck's own death
payoffs trigger off it; only an optional mode exiles graveyards (pilot note recorded).
**Feral Appetite's `removal` flag is a false positive** (graveyard exile, not board
removal), so true board removal is 8 — still in band, no swap forced. Verified text also
confirms real recursion the counter can't see (Veinwitch Coven, Teacher's Pest, Sage of
the Fang) and the free sac outlet (Umbral Collar Zealot). Three bench candidates named:
Environmental Scientist, Mindful Biomancer, Old-Growth Educator. Queue is back to steady
state (cleared).

## Ur-Dragon mana audit: six lands upgraded on verified text; ramp package confirmed (2026-08-20)

The player asked to be certain every mana card in the Ur-Dragon is the best the
collection offers. Grounding caveat first: **the PC's private `collection.csv` is
stale** — 2,289 uniques vs the committed snapshot's 2,782, a strict subset, and it
lacks twelve cards the deck already runs (Wood Elves, Radagast, the Smaugs, Deserted
Beach, Sheltered Thicket, Scattered Groves, Dragonspeaker Shaman, Savage Ventmaw,
Dragonlord Silumgar, Desolation of Smaug). Every count below used
`collection_snapshot.txt` + `collection_attrs.snapshot.csv` (FlagsVer 3, 100%
produced-known); the PC export needs refreshing before it is trusted again.

- **Pool counted**: 206 owned nonbasic lands, 141 owned 5c-legal rocks/dorks/ramp,
  joined to free copies via `deck_conflicts.available_pool` (Roaming Throne pin
  honoured). **128 texts verified** in one `carddb.py --verify` batch (0 unverified;
  Scryfall is reachable from the PC).
- **Ramp (10) unchanged** — it is the field's package (Sol Ring 89% … Rampant Growth
  22%); nothing owned-and-free outranks any slot. Kodama's Reach / Dragon's Hoard /
  Orbs of Dragonkind are the unowned gaps (buylist).
- **Six land swaps, all `Source=manual-replace`**: Villainous Hideout (any colour only
  for *Villain* spells — the deck has one) -> Clifftop Retreat; Study Hall ({1} filter
  tax) -> Horizon of Progress (Reflecting Pool + extra land drop + cash-in draw);
  Fields of Strife -> Sunbillow Verge; Forum of Amity -> Hidden Lair (B->U: U was 10 src
  / 16 pips, B 11/11); Tranquil Cove -> Prairie Stream (typed: Farseek 14->15 targets);
  Fire Nation Palace -> Spectator Seating (untapped with 2+ opponents). Sources W 14 ·
  U 11 · B 11 · R 18 · G 15 (+4 Dragon-only); always-tapped lands 10 -> 7; keepable
  79%, screw 16%, field overlap 21/25, optimizer "already aligned", sections clean.
- **Sim honesty**: goldfish fairly measures two of the six (Fields->Sunbillow -0.027
  turns, Forum->Hidden Lair -0.012, both CI-significant), ties two (both arms modelled
  identically), and mis-scores two as downgrades — it ignores Villainous Hideout's
  spend restriction, and **`oracle_flags._mana_added` reads Fire Nation Palace's
  firebending reminder text as the land tapping for RRR** (`mana3`). That false
  positive is a follow-up: scope `_mana_added` to the card's own mana abilities
  (strip parenthetical reminder text / "whenever ... attacks" clauses) and regenerate
  the attrs snapshot. Until then any sim touching Fire Nation Palace overrates it.
- Still open, out of scope here: Unclaimed Territory and Secluded Courtyard are one
  copy each committed to three decks (cap, spider, ur-dragon).

## Roaming Throne pinned to the Ur-Dragon; two decks swapped off it (2026-08-20)

One physical copy was committed to **three** decks (`deck_conflicts.py`: own 1,
committed 3, short 2). Adjudicated on trigger density, not tribe headcount, with
every candidate's oracle text batch-verified through `carddb.py --verify` (77 cards,
0 unverified):

| Deck | tribe pool | members with triggers | field % |
|---|---|---|---|
| **the-ur-dragon** (Dragon) | **31** | **28/31** | **31%** |
| cosmic-spider-man (Spider) | 27 | 18/27 | 11% |
| bruce-banner (Hero) | 4 | 2/4 | not in field |

The Ur-Dragon wins on the engine read, not just the counts: the Throne naming Dragon
doubles the commander's *own* attack trigger (draw twice, **two** free permanents),
plus four ETB-per-Dragon payoffs (Lathliss, Miirym, Scourge of Valkas, Ganax), and
named Dragon it is itself a Dragon for Sylvia's double strike and Valkas's X.

- `data/collection/pins.csv` — `roaming throne,the-ur-dragon`, written via
  `deckcore.save_pins()` so it lands under the canonical front-face key.
- **cosmic-spider-man**: Roaming Throne -> **Sun-Spider, Nimble Webber** (25% field,
  +25 synergy, 4 free copies; Spider body whose ETB fetches Skullclamp or Lightning
  Greaves — the deck holds 3 Aura/Equipment targets).
- **bruce-banner-incredible-hulk**: -> **Shang-Chi, Master of Kung Fu** (13% field, but
  the engine read decides it: activate creature abilities as though hasted, so a pinger
  cast this turn pings the Hulk this turn, and his creature-ability mana pays Brash
  Taunter's `{2}{R}`). Both logged `Source=manual-replace`; both decks 100 cards, no
  singleton violations, sections clean.
- **Rules correction:** the Spider notes claimed the Throne "doubles Cosmic's trigger."
  It does not do anything — Cosmic's trigger *grants keywords*, and granting the same
  keywords twice is a no-op. Corrected in the notes file.
- `deck_conflicts.py` now loads the pins: `conflicts()` has built a `pinned_to` field
  since pins v2, but `main()` never passed any, so the CLI printed a shortfall while the
  repo already knew which deck won the copy. Covered by
  `test_pins_v2.py::test_cli_report_names_the_pin_holding_the_copy`.
- **Not measurable by `goldfish.py`** — its assumptions block models mana, curve and an
  unblocked clock; trigger doubling is not modeled, so a sim A/B would price the Throne
  as a 4-mana 4/3 and say nothing about the actual question.

## Ur-Dragon: sim-tuned, engine-read revalidated; eminence model hole exposed AND closed (2026-08-20)

The player asked for the mathematically best Ur-Dragon tested end-to-end in
goldfish, then challenged whether eminence was accounted for. It was not — and the
challenge unravelled exactly the right thread. Final state:

**Net deck changes** (all manual-replace, all dragon-for-dragon-or-better):
Smaug, the Great Calamity → **Neriv, Heart of the Storm** (kept: Smaug GC verified a
vanilla 6/6 whose only text is a 5-damage Adventure, cast in 0% of 5,000 games);
Niv-Mizzet, Visionary → **Radagast of Rhosgobel** (via an intermediate Hraesvelgr
step, reverted); Ureni, the Song Unending **stays** (an intermediate Lorehold swap,
reverted on engine-read: Ureni is 10/10 with protection from W AND B plus a
lands-scaled one-sided sweep — the sim saw none of it).

**Three model holes, all documented in the deck's .notes.md, all now with receipts:**
1. Goldfish models no land-ramp (its own assumptions say so).
2. Goldfish models no cost reduction — `grep -cin "cost reduc|cheaper|reduce"
   scripts/goldfish.py` = 0 — while this deck's commander IS a cost reducer:
   eminence (verified, run 32367856797) works FROM THE COMMAND ZONE, so the -1 is
   on from turn one. Avg dragon MV 5.29 printed → 4.29 effective; MV6+ dragons
   12 → 3. "Commander cast in 31% of games" and "too top-heavy" were both retracted.
3. Goldfish sees no abilities — so it voted against Radagast (+0.016), against
   restoring Ureni (+0.019), FOR cutting Sylvia Brightspear-class statics. Every
   such vote is recorded in the notes and overruled with the reason.

**The revalidation's own finding:** the first tuning pass cut Ureni and Niv-Mizzet
without their text ever being on disk — the A/B measured printed bodies only. Ten
texts (three swap-ins, three swap-outs, four cut candidates) are now verified in
`hobbit-verified-2026-08-20.txt`, and the notes carry a do-not-cut list: Sylvia
Brightspear ("Dragons your team controls have double strike" — a 3-mana board
doubler the sim can't see), Wood Elves (fetches the deck's typed duals), Sarkhan
Soul Aflame (second dragon discount), Roaming Throne (naming Dragon doubles the
commander's attack trigger).

**BUILT same day** (PR #155, `docs/spec-cost-reduction.md`): `oracle_flags` v3
derives `discount-cmd:<type>:<n>` / `discount:<type>:<n>` / `discount-first:<type>:<n>`
from oracle text; goldfish pays them at cast time (generic portion only, pip
floor, eminence always-on and never self-applied, statics off `board`, first-per-
turn consumed positionally; A/A exact-zero holds WITH discounts on; REPORT_SCHEMA
3→4; dual honesty label). Attrs snapshot regenerated on main (FlagsVer 3, 12
discount rows — the four Ur-Dragon reducers all derive to spec). The collection
sweep exposed one v1 defect: type-word tokens (`artifact`, `noncreature`) matched
nothing while the label claimed them modeled — fixed same day: `_disc_matches`
now resolves subtype AND type words via `SimCard.typewords` plus an explicit
`noncreature` rule, pinned by test. Three other decks carry reducers, all now
labeled truthfully: Captain America (Nick Fury, 25 Hero spells), Y'shtola (Lyse
Hext, 40 noncreature spells), Cloud (Cid — zero vehicles in deck, so inert).
No retroactive deck verdicts to unwind — goldfish A/Bs had only ever driven
Ur-Dragon decisions; the schema bump already invalidated every cached sim.
Re-measured at 5,000 games: first-kill median **stays T9** but **lethal-by-T8
19% → 37%**, commander lands in **41%** of games (was 31%), mean turn 8.23. The
Radagast override is now vindicated by the fixed instrument (cutting him measures
commander_by_t6 −0.009, CI excludes zero); Ureni's override still rests on the
engine-read (abilities remain unmodeled). Model holes remaining: land-ramp,
abilities/attack-trigger — hole #2 (cost reduction) is closed.

## Y'shtola goes Bracket 4: the purchase package lands; Tifa and Smaug retired (2026-08-20)

The player bought 8 cards specifically for Y'shtola (Mana Pool order #468964),
ratified **Bracket 4** for her, asked for Mana Drain, and deleted the Tifa and
Smaug decks. All executed:

**Eight swaps, all through the sanctioned edit path** (logged `manual-replace`,
so the optimizer holds them; cuts chosen by `optimize.cut_candidates` — every
outgoing card unprotected and bottom-of-field):
Ghostly Prison←Eye of Nidhogg · Norn's Annex←White Auracite · Bloodchief
Ascension←Observed Stasis · Teferi, Time Raveler←Risky Shortcut (new
Planeswalkers section) · Grim Tutor←Syphon Mind · Mana Drain←Cleansing Nova ·
Talion←Dancer's Chakrams · Lotho←Lethal Scheme. Section checker clean; deck
exactly 100, singleton-clean; the Viscera Seer + Sun Titan + Angelic Renewal
loop is intact and Bloodchief now compounds it.

**The strategy is rewritten in the .notes.md**: pillowfort drain-control —
Prison/Annex tax attackers while the engine assembles, Teferi locks opponents to
sorcery speed so the loop can't be interrupted at instant speed, Bloodchief's
quest counters are advanced by Y'shtola's own MV≥3 drains, Talion/Lotho tax and
ramp off opponents' turns, Grim Tutor is the second unconditional tutor, Mana
Drain banks counter-mana into Exsanguinate. One wipe (Toxic Deluge) is
deliberate. All 8 marked do-not-cut.

**`# Bracket: 4` header set — this one is legitimately declared** (unlike the
Resilience header removed earlier today): the player said "she is allowed to be
bumped to bracket 4" in so many words. Every surface shows it as
"Bracket 4 — Optimized (your setting), detected 3". The --rank Bracket column was
widened 14→20 chars because the mismatch suffix collided with Speed.

**Tifa and Smaug deck files deleted** (all companions + their field snapshots).
8 decks remain. Grim Tutor was freed by Smaug's deletion and went to Y'shtola.
Conflicts 117→100; wishlist regenerated (~$1,038 total, down from ~$1,377).
Mana Drain is queued for runner verification (its text is cited in the notes).

Suite steady at **909**.

## Phone screenshots exposed 19 misfiled cards and two render bugs — all fixed (2026-08-20)

The player's phone showed a Sorcery under Artifacts, "9 Blasphemous Act" in a
singleton deck, and "redundancy-led" clipped to "redunda / led". Spec:
`docs/spec-mobile-ui-and-sections.md`. What each actually was:

1. **19 typed cards sat in contradicting type sections across 7 of 10 decks.**
   Three writers could misfile: the optimizer writes swap-ins at the outgoing
   card's line and `_tidy` only ran when THAT pass made changes (Grim Tutor sat
   under Creatures through two "already aligned" applies); the webapp's replace
   wrote in place; and adds made pre-enrichment stuck forever. Fixed in layers:
   `deck_sections.py --check` (exit 3 on misfiles; untyped reported, never failed
   — a fresh export must not break CI), run as a CI step in tests.yml and in
   refresh.py because pytest deliberately never reads data/; all 10 decks
   repaired (`--all --apply`, checker now 0, every deck still 100/singleton-clean,
   `--rank` byte-identical); `_tidy` runs on EVERY apply; the webapp replace
   re-files by the incoming card's type (custom sections and unknown types stay
   in place — never guess).
2. **"9 Blasphemous Act" was the MANA VALUE**, rendered as an accent-coloured
   bare number before the name. Grid figcaptions now show name + price only (the
   card art shows the cost; qty is the separate `N×` badge); the list view's .mv
   gutter is muted — quantity there is an explicit `N× `.
3. **CRISPI tiles clipped on phones** because `tile-val` is `--fs-2xl` display
   type sized for "100"/"$462". `stat_tile()` now applies `tile-val--text`
   (`--fs-lg`, word wrap) to any value with a space or >6 chars. Tokens only;
   `test_design_tokens` green. Verified with headless Chromium at 390×844 —
   screenshots sent to the player.

Also shipped (carry-over from the same day's audit review): `load_power_tags`
and `deck_fit`'s Game Changer checks now match both `name_keys` of a split name,
so the dashboard labels can no longer disagree with `power.py`'s counts
(`Boom // Bust` was a live case); and Thorin's agent-written `# Resilience: low`
header is REMOVED — that header records the PLAYER's judgement, and nobody had
declared it. Thorin reads `prot 2 · rec 0` again (Interaction 11 after the An
Unexpected Party swap). Still with the player: confirm the physical
Bruce Banner // The Incredible Hulk copy behind the owned_additions line.

Suite 895 -> **909**.

## TENTH DECK: Thorin, King of Durin's Folk — and a fresh export (2026-08-20)

The player uploaded a new collection export. **2,691 -> 2,781 distinct names,
3,890 -> 4,083 copies**: 90 new names, 50 quantity increases, nothing removed. The
haul is overwhelmingly the Hobbit set (HOB/HOC), and it is not random — it tracks
the EDHREC Thorin list almost card for card, which is what made the build obvious.

**All 90 new names were runner-verified before any of them was reasoned about**
(deck-verify run 32322609093: 90/90 resolved, zero UNVERIFIED, DFC probe 46/46).
The verbatim output is committed at `data/reference/hobbit-verified-2026-08-20.txt`
— read that file for any of these cards rather than trusting memory, and note the
set codes are HOB/HOC, i.e. squarely in post-2025 territory.

**The deck** (`data/decks/thorin-king-of-durins-folk.txt`, tuned and sectioned):
Bracket 2 Core, combat T9 (77% of games), prot 0 · rec 0, redundancy-led, Inter 12.
Field overlap **20 of the field's top 25 in the deck**, 1 free to add, 4 unowned —
well above the ~50% health line. **29 of the 30 R/W-legal Dwarves owned are in it**,
so the archetype is not "supported" by vibes; it is nearly exhausted by this list.

**The engine, and the one word that carries it** (both quoted from the verified
file): Thorin reads *"Whenever Thorin **or another Dwarf** you control enters,
create a Treasure token"* — with **no nontoken clause**. Fíli the Pathfinder reads
*"Whenever Fíli or another **nontoken** Dwarf you control enters, create a 2/2 red
Dwarf creature token."* So one real Dwarf yields Treasure (Thorin) + 2/2 token
(Fíli) + a second Treasure (the token triggering Thorin), and every Dwarf gets
+2/+0 from the pair — **multiplicative, and deliberately not a loop**, because Fíli
ignores its own tokens. That asymmetry is the whole deck; it is written up in the
deck's `.notes.md`, which also protects the five engine cards from the optimizer.

**Two real bugs the refresh exposed, both fixed:**

1. **`auto_build` built a colorless pile for an unenriched commander.** Thorin was
   in the pool but not yet enriched, so identity resolved to `set()`, `_color_legal`
   admitted only colorless cards, and the builder returned a plausible 84-card deck
   with 43 artifacts and 0 basics — no error. `Card.identity` has no None-vs-empty
   distinction (unlike `produced`/`flags`), so `types` is now the enrichment tell:
   empty identity + no types raises `UnknownIdentity`, naming both fixes. A new
   `--identity` CLI flag exposes what only the webapp's `?ci=` could reach before.
2. **`tribal-spiders` in commanders.csv matched zero cards.** Tribal tags are
   matched against card SUBTYPES, which Magic spells singular ("Spider"). The bug
   was masked because a commander's own subtypes are candidates too, so Spider
   commanders found their tribe by accident. Renamed to `tribal-spider`; a test now
   reads the real commanders.csv and fails on any plural tribal tag.

**The automation loop closed inside the session, exactly as designed:** merge fired
`attrs-snapshot.yml` on main, which re-enriched all 2,781 names (untyped 90 -> 0) and
pushed the attrs back; pulling that down is what let the Thorin build see the new
Dwarves as creatures at all. The first build attempt, made before enrichment landed,
was legal but blind — worth remembering as the reason the ordering matters.

**Cost of a tenth deck:** cross-deck conflicts 112 -> 117. Exotic Orchard is now
own 6 / committed 9, Rogue's Passage own 1 / committed 4. The study deck
(bartolome) still inflates this count and is still not sleeved.

**A 36-agent audit of the refresh then found four more bugs, all of the same family
— a curated list or a heuristic silently matching the wrong thing:**

3. **`power._match` did no front-face folding.** A curated row spelled
   `Bofur, Reliable Guardian` matched nothing while the deck line read
   `Bofur, Reliable Guardian // Concerted Care`, so a hand-verified protection card
   scored zero. This backs the Game Changer, tutor, fast-mana, extra-turn,
   mass-land-denial and combo-piece lists too — a Game Changer that fails to match
   silently mis-brackets a deck. Now compares on `name_keys`, and both ref loaders
   store both keys. Thorin's deck went prot 0 -> 2 on the fix alone.
4. **The optimizer could cut a card the player added by hand.** `cut_ranking`'s
   advisory surface has unioned manual adds since Phase 9, but the path that actually
   rewrites the deck never did — so the same run printed "manual adds (advisory — the
   optimizer never cuts these): Grim Tutor" AND proposed pulling Grim Tutor for a
   bought Goldspan Dragon, with two more candidates held off it only by the 25-point
   margin. `_manual_add_keys()` now feeds `keep`.
5. **A buylist `Replaces` target that left the deck was never revisited.** Drown in
   the Loch still pointed at Misdirection two swaps after Misdirection was cut. Stale
   targets are blanked (never the row) on every applying run, including runs that
   propose no buys — which was a hole in the first version of the fix.
6. **The name heuristic outvoted the field's own Lands sections.** "Gimli of the
   Glittering Caves" — a creature the field lists and does not file under Lands — was
   classified a land on the word "Caves", and the buylist told the player to pull a
   real land for it. The field's silence now decides when it HAS a row and a lands key
   to be absent from; the heuristic stays the last resort it was documented to be.

**Two swaps applied by hand** (logged `manual-replace`, so the optimizer holds them):
Grim Tutor <- Goblin Recruiter in smaug-wicked-worm (its first tutor; the deck runs 7
Goblins and zero Goblin payoffs), and Dismember <- Misdirection in yshtola (the
optimizer proposes it unprompted, +38 field). `Dismember` was also added to
`mtglib.REMOVAL`: `oracle_flags` can never derive it, because `_REMOVAL_RE` reads the
destroy/exile verb and Dismember says "gets -5/-5".

**`resilience_staples.csv` gained 5 rows** (Bofur, Thorin Oakenshield, Old Fat Spider
Can't See Me, Lake-town Mariners, Along the Crooked Way) and, more importantly, a
recorded DECISION: **attack taxation is deliberately excluded.** Ghostly Prison and
Norn's Annex protect a life total, not a permanent; admitting them would take Thorin
from prot 0 to prot 5 and flip its verdict to "meets the 5-8 band" while it holds one
real protection spell. Ward belongs; bounce does not. The file also now warns that
comma names MUST be quoted or `csv.DictReader` truncates them into rows that match
nothing — the Hobbit set is full of them.

**One data defect fixed, one still open.** `Bruce Banner // The Incredible Hulk` — the
commander of a sleeved deck — was in no export, so every tool read the deck's own
commander as own 0 / committed 1; it is now recorded in `owned_additions.txt` with a
note to delete the line if the physical card isn't there. Still open: 26 of the 86
nonbasic cards in the Thorin deck are HOB/HOC printings whose text is not on disk
(round 1 covered new *names*, not all post-2025 cards), and eight decision-bearing
cards are queued in `verify-queue.txt` for the next runner push — An Unexpected Party
first, because it is 79% of the Thorin field, owned x2 free, and whether it makes
TOKEN or NONTOKEN Dwarves decides if it is filler or a second multiplier.

**Round-2 verification came back and settled the biggest open question.** Runner run
32330821297 resolved all 8 queued cards. The decisive one: **An Unexpected Party //
At the Door** creates *"X 2/2 red **Dwarf creature tokens**"* — TOKEN Dwarves, so
Fíli ignores them and **Thorin does not**. Casting it for X=4 is four Dwarves, four
Thorin triggers, four Treasures and +4/+0 on the spot, with the enchantment half
still in exile as a later +2/+2 anthem. Swapped into the Thorin deck over Super
Villain Lockup (verified `{1}{W}`, exiles only a TAPPED creature), which drops
Interaction 12 -> 11 — worth it for a 79% field card that is a second multiplier.

The other seven, for the record: **Magda, Brazen Outlaw** makes a Treasure whenever a
Dwarf becomes tapped and sacrifices five for an artifact/Dragon tutor — the 80% buy
is confirmed good. **Thorin, Mountain-king** is `{3}{R}` mono-red Equipment payoff:
commanding it would strip white and cut Fíli, Kíli, Dáin and Bofur, so it is a 99
card, never the commander. **Y'shtola**'s own text finally exists on disk and
confirms the MV>=3 noncreature drain the notes always claimed — which makes Dismember
(MV 3) a trigger as well as removal. **Mindcrank** mills on any opponent life loss,
so the Bloodchief Ascension line is real but needs a card the player does not own.
**Krile Baldesion** is a Dwarf, but W/U — illegal in Thorin.

Suite 884 -> **894**.

## CRISPI COMPLETE — four axes, composite retired (2026-08-20)

Phases B, C and D shipped; the spec is now a record, not a work item.

**The defect is dead and unrepresentable.** `power.py --rank` no longer prints a
0-100 or a tier adjective anywhere — deleted outright, no `legacy_power`, per the
player's call ("kill it all now"). `test_crispi_axes.test_composite_is_gone_from_the
_payload` fails if a roll-up ever returns. Raw component counts SURVIVE; they were
never the bug.

**The stable now reads** (bracket → speed → interaction sort):

| # | deck | bracket | speed | resilience | consistency |
|---|---|---|---|---|---|
| 1 | bartolome | 4 | combo (early) | prot 0 · rec 4 | redundancy-led |
| 2 | yshtola | 3 | combo (setup) | prot 1 · rec 2 | redundancy-led |
| 3-5 | cloud / spider / ur-dragon | 3 | combat T9 | — | redundancy-led |
| 7-8 | bruce / tifa | 3 | slow (9%) / slow (16%) | prot 4 / prot 3 | redundancy-led |

Bartolomé now ranks **first** rather than last — a twelve-infinite deck at the top,
which is what the bracket always said and the composite always denied.

**Resilience** is counted from `data/reference/resilience_staples.csv`, every row
runner-verified (deck-verify runs 32319382690 + 32319519924) — 7 protection, 7
recursion. Empty list yields "unmeasured", never "0 protection". A `# Resilience:
low|medium|high` deck header mirrors `# Bracket:` for the judgement the data cannot
make ("does it work if the commander dies twice?").

**Consistency** reports the MECHANISM, not a score: tutor-led (7+ tutors) vs
redundancy-led (roles at the 5-8 / 8-12 bands). This matters here because the stable
runs 0-1 tutors everywhere — an axis counting only tutors would call all nine decks
inconsistent, which the research explicitly contradicts.

**Two-surfaces trap caught twice more this session**: the dashboard's stat tile and
bracket line still read `power`/`tier` after the CLI was done (memo byte-identical
tests caught it), and the webapp leaderboard sort + assess packet needed the new
`power.rank_key_for` so CLI and app cannot drift into different orders.

**B.3 answered (2026-08-20): printed experiment, never score.** The player ratified
keeping the disruption delta out of the Resilience score permanently under the
current phantom model — Phase 10's own caveat ("a crude stand-in for opponents")
disqualifies it as a score input, and scoring it would smuggle the backlogged pod sim
(player decision 2026-08-13) in through a side door. What shipped instead is the
spec's sanctioned experiment line: `goldfish.py --disruption standard` now replays
the identical games undisrupted (common random numbers — the disruption stream is
its own Random, so both arms share shuffles) and prints paired standard-vs-none
deltas with 95% CIs under the PHANTOM DISRUPTION block: commander cast rate, cast
turn (censored at horizon+1, same reasoning as `_censored_kill`), first-kill turn,
damage dealt. `simulate_disrupted()` is CLI-only and outside `sim_for_deck`'s cache,
so no surface can serve disrupted numbers as goldfish ones —
`test_the_cached_surface_never_sees_the_delta` is the firewall test. Ratification of
score-feeding is revisited only if the printed delta proves predictive in real games.
Real-deck readout: Y'shtola loses ~22 damage/game to the phantom and its first-kill
turn slips +0.33 (significant), while its commander line is untouched — exactly the
"can it rebuild" cost the counted `prot/rec` layers can't see.

Suite 861 → 874 → **880**.

## Phase A revalidation: two fixes (2026-08-20)

Post-merge re-audit of #143 found two real gaps, both fixed:

1. **Latent crash in `speed_axis`** — a clock dict missing `kill_rate` hit
   `rate * 100` with None in both the combat and slow branches. Unreachable via
   `clock_for_deck` (goldfish always emits the key) but the function is public and
   pure; missing rate now reads as 0.0 with an honest "0%" slow label. Test added.
2. **Webapp leaderboard passed no collection path** to `build_for_deck`, so every
   webapp row's speed silently read "unmeasured" while the CLI showed real values —
   exactly the two-surfaces trap. `COLLECTION` now rides along; webapp speed for
   Y'shtola verified as `combo (setup)`.

Suite 860 → **861**. Everything else in #143 held up under re-audit.

## CRISPI Phase A SHIPPED — the Speed axis (2026-08-20)

`power.py` now carries a **Speed** axis, from `docs/spec-crispi-axes.md`. Combo evidence
outranks the combat clock, because `goldfish`'s clock is combat-only and would otherwise
call a sacrifice-loop deck slow. Live readings across the stable:

| deck | Speed |
|---|---|
| bartolome (12 early infinites) | `combo (early)` |
| yshtola (#135 line, not early) | `combo (setup)` |
| smaug / cloud / spider / ur-dragon | `combat T9` · captain-america `combat T10` |
| bruce-banner / tifa-lockhart | `slow (9%)` / `slow (16%)` |

**The spec was wrong by one state and the implementation caught it.** It collapsed
"slow" into "unmeasured". `goldfish._clock` nulls the median when `kill_rate < 0.5`, so
a real-but-slow creature deck arrives with `have_data` **True** and no median — measured,
and the answer is *slow*. Bruce (9% lethal by T10) and Tifa (16%) are the live cases.
"unmeasured" is now reserved for decks with no clock at all. Spec amended to match.

Design notes worth not re-deriving: `power.clock_for_deck` lazy-imports `goldfish` so the
engine ring stays acyclic (`grep "^import goldfish" scripts/power.py` → 0, and goldfish
only reaches back for `apply_attrs`/`load_attrs`, so there is no recursion); `bracket_hint`
is taken verbatim from the clock rather than re-derived, to avoid two mappings drifting;
the clock's UNDERSTATED caveat rides along even when the combo branch wins. Cost is a
disk-cached sim (~0.3s uncached, ~0s after).

**Still open:** Phases B (Resilience), C (redundancy) and D (retire the composite) are
NOT started. D is why `--rank` still prints `31/100 Casual` beside `Bracket 4` — removing
it is gated on the player question "does the legacy 0-100 die now or live one release?".

## Spec amended: the Speed axis is a pair, with anchors confirmed (2026-08-20)

A "any concerns" review caught a defect in the just-merged spec: the goldfish clock
measures unblocked COMBAT only, so a bare clock-based Speed axis would mislabel exactly
the combo decks that motivated the work (Bartolomé: 22 creatures, mediocre combat clock,
real speed = zero-mana loop). Amended in place: **Speed resolves combo-first** — early
complete combo → "combo (early)"; complete non-early → "combo (setup)" (Y'shtola's #135
line lands here, NOT "unmeasured"); else the combat clock; else the honest label. The
combo half needs zero plumbing: `power.assess` already receives `detected` with
`early`/`category` per complete combo.

The regrounding also nailed the anchors so the implementer never re-derives them: the
dashboard already renders the clock (`build_dashboard.py` ~838 via cached
`goldfish.sim_for_deck`, seed=0); deckcore does NOT expose the sim today; `signals.
combos_complete` is names-only — read `detected`; and Phase D has THREE composite-print
sites (`power.py` print_one/--rank, `webapp/app.py` ~333 leaderboard sort, ~806 flash).
First uncached `--rank` pays 9 sims — disk-cached after, say so in output.

## Revalidated the CRISPI audit; spec written and READY (2026-08-20)

Re-checked every #140 claim against the code instead of memory. Two were wrong, both
UNDERSTATING the repo, both now corrected in `strategy-shapes.md`:

1. **Speed is closer than reported**: `goldfish.py`'s `clock` block already computes
   `median_first_kill` / `median_table_kill` / `kill_rate` — the fundamental-turn number
   exists and `power.py` simply never reads it.
2. **Resilience is not "unmeasured with nothing to build on"**: `goldfish.py
   --disruption standard` (Table-Ready Phase 10, EXPERIMENT, off by default) already
   models a wipe + periodic removal + commander tax. What is missing is protection
   COUNTING and any scoring of the delta.

Also confirmed the binding boundary: `docs/spec-pod-simulation.md` is BACKLOGGED by
player decision 2026-08-13 — any axis work builds on shipped goldfish machinery only.

**The handoff artifact: `docs/spec-crispi-axes.md` — status READY FOR IMPLEMENTATION.**
Four phases (A: Speed via the existing clock through deckcore, never engine→engine
imports; B: Resilience as counted protection/recursion + a `# Resilience:` declared
header + the disruption delta as a labelled experiment only; C: Consistency gains
redundancy-cluster counting against the 5-8/8-12 bands; D: presentation — four axes +
bracket, the contradictory composite row becomes a regression test). Contains the house
session rules, receipts, FlagsVer trap, memo/CRN tripwires, acceptance criteria, and two
player questions (disruption-in-score? legacy 0-100 lifespan?). Y'shtola's "Speed:
unmeasured (no combat clock)" honesty label is specified explicitly so the axis never
calls a drain deck slow.

## Strategy research: six shapes + CRISPI, and a live flaw in power.py (2026-08-19)

Deep web research into high-level MTG strategy, written up as
`.claude/skills/mtg-deckbuilder/references/strategy-shapes.md` — the companion to
`combo-shapes.md`. That file answers "how do two cards loop"; this one answers "what is
the deck's theory of winning". Six shapes, each with a one-question identifying test:
resource denial (**is it asymmetric?**), life/library as fuel (**is my curve low enough
to survive my own payoff?**), spell velocity (**is this card mana-POSITIVE?**), toolbox
(**is the tutor the engine?**), inevitability (**who wins on turn 20?**), pillowfort
(**am I a worse target than the other two?**).

**The finding that matters for our tooling: DeckCheck retired single-number power levels
in 2026** and replaced them with **CRISPI — Consistency, Resilience, Interaction, Speed**,
because "power levels were competing with brackets, and the number was opaque."

**That exact flaw is live in our output.** `power.py --rank` currently prints
`bartolome-del-presidio-600-combos  Bracket 4 Optimized  31/100 Casual` — bracket and
power contradicting each other in one row, because the bracket sees two-card infinites
while the score sees no tutors/fast mana/draw. Both are right about what they measure; the
row is nonsense. Treat 0-100 as a component readout, never a headline.

**Audit of power.py against the four CRISPI axes:** Interaction counted; Consistency
partial (lands + tutors, no redundancy); **Speed not scored though `goldfish.py` already
simulates it and just is not wired in**; **Resilience not measured at all** (no protection
count, no commander-dependence). The cheapest real upgrade available is Speed — the
simulator exists.

**Counted profile of the whole stable** (all nine decks, `deckcore.analyze_deck`):
interaction **10-14** (healthy — low end of the cEDH 12-18 band), tutors **0-1**, fast mana
**0-1**, draw 7-15, avg MV 2.42-3.03 except **the-ur-dragon at 4.22** (real outlier).
The signature is tutor-less and fast-mana-less by design, which per the literature is a
valid consistency posture *provided* redundancy carries it — so the lever here is
**redundancy (5-8 copies of an effect; 8 gets it in hand by turn 3), never "buy tutors."**
Researched targets now quotable: protection 5-8 if commander-dependent / 2-4 if resilient;
cEDH composition interaction 12-18 incl. 3 free, tutors 7-12, fast mana 8-14, lands 28-31.

## Tool contract is now ENFORCED, not documented (2026-08-19)

The player's call, and it was correct: this session missed `deck-verify.yml` for six
merged PRs while verifying ~40 cards one at a time by web search — with CLAUDE.md,
SKILL.md and grounding-rules.md all loaded. **The lesson is structural: prose the session
has to remember is not a control.** Three layers replace it.

1. **`references/tool-contract.md`** — every question mapped to the tool that answers it,
   plus the "NEVER do this instead" column and six named anti-patterns that each cost a
   real correction this session.
2. **A SessionStart hook** — `.claude/settings.json` (the repo had NO settings.json and no
   hooks before this) runs `.claude/hooks/tool-contract.sh`, which emits the contract as
   `hookSpecificOutput.additionalContext`. The harness injects it before the session acts,
   so it cannot be skipped the way a reference file can.
3. **`tests/test_tool_contract.py`** (9 tests) — enumerates `scripts/*.py`,
   `.github/workflows/*.yml` and `.claude/agents/*.md` and FAILS if the contract never
   names one. Adding a tool now forces you to say when to reach for it.

**The guard immediately earned its keep**: it caught two tools the hand-written contract
had already missed — **`spellbook.py`** (the actual tool for "how many combos does this
deck have", which this session answered by hand-counting) and **`field-snapshots.yml`**.
A negative control confirms it bites: deleting the `deck-verify.yml` reference fails three
tests. Suite 840 -> **849**.

If a genuinely non-session-facing script is added, put it in `NOT_SESSION_FACING` in the
test — deliberately, with the same friction `test_agents.py` uses for widening agent tools.

## Smaug, Wicked Worm BUILT — and two review corrections (2026-08-19)

The player asked two questions that both landed: *"can't GHA reach out online?"* and
*"did you miss the different Smaugs and their treasures?"* Yes and yes.

**GHA is the network arm, and the machinery already existed.** `deck-verify.yml` runs
`carddb.py --verify` + the field refresh on a GitHub runner, triggered by pushing a
`claude/**` branch that touches `data/decks/*.txt` or `data/reference/verify-queue.txt`,
and pushes results back to that branch. This session had been web-searching cards one at
a time while that workflow sat there. The queue is now refilled with the 12 cards this
session verified only by search (the Smaugs, Ninja Teen, Paramecia Coloniex, …) so the
runner confirms them verbatim. wizards.com (rules.py) remains the one true PC-only fetch.

**The treasure verdict in #136/#137 was wrong, and the instrument was the bug: a generic
staples list is not how you measure archetype support.** The player owns **Smaug, Wicked
Worm x2** — already verified in commanders.csv (2026-08-15), already field-snapshotted
(saved 2026-08-17, 1375 decks) — plus Smaug the Magnificent, Smaug the Impenetrable (in
Ur-Dragon), Hellkite Tyrant, The Reaver Cleaver, The Sackville-Bagginses. 27 of the field
top-60 owned. combo-shapes.md Extension 1 now carries the correction and the rule: count
support against the pool AND the owned-commander pages, never a staples list alone.

**The deck: `data/decks/smaug-wicked-worm.txt`** — auto_build from the owned uncommitted
pool, then optimize --apply (4 fit swaps incl. Smaug the Magnificent in for the Great
Calamity, 2 land upgrades, 14 buylist rows led by Goldspan 82% / Mirkwood Bats 76% /
Xorn 74%). Final: 100 cards, 37 lands, power **72/100 Optimized, Bracket 2**, roles all
in band, field top-25 **13/25** (12 of the missing are buylist rows — the honest ceiling
of the owned pool). Sections normalized; notes carry the engine protections, pilot lines,
and the one physical decision: **Smaug the Impenetrable + Blasphemous Act banks 13
Treasures through your own wipe**, but the copy is sleeved in The Ur-Dragon — pull it or
wishlist a second; it is deliberately NOT in the 99 until the player decides.

Known noise, unchanged: the Bartolomé study copy still inflates deck_conflicts
(Bojuka Bog "short 1" etc.). Real new conflict worth knowing: Blasphemous Act own 3,
now committed 4.

**Runner round-trip closed the loop (run 32309549585):** all 12 queued cards verified
verbatim on the GitHub runner — every claim this session made from web search held, with
ONE addition the searches missed: **Smaug, Wicked Worm's ETB Treasures enter TAPPED**
(notes fixed), and The Warring Triad's mana ability is "Activate only as an instant."
Queue cleared back to its steady state. New known wart: the field-snapshot step reports
`FAIL Bartolomé del Presidio (EDHREC unreachable)` on every run — likely the accented
slug; the other 8 commanders snapshot fine. Worth a look if anyone ever wants field data
for the study deck; harmless otherwise.

## Multiplicative lattice added — and it CORRECTS the doubler rule (2026-08-19)

The player supplied the decklist for the unreachable second video: **Thorin, King of Durin's
Folk** Boros Dwarf tribal (99 + commander, 20 lands). Reviewed from the list; every card
verified against Scryfall.

**The deck has no infinite combo, and that is deliberate.** All three copy engines — Molten
Echoes, Flameshadow Conjuring, Cadric — are gated on the word **`nontoken`**, so their copies
can never feed the engine. That yields the fastest combo read there is, now written into
`combo-shapes.md`: **read a copy effect for the word `nontoken` first; one word tells you
whether a loop is possible at all.** Kiki-Jiki lacks the clause, which is exactly why it loops.

**This corrects Extension 1's doubler rule.** "Doublers are not combo pieces, infinity x 2 is
infinity" holds only on an *infinite* engine. On a *multiplicative* engine doublers ARE the
deck. The same card is a dead draw in one and the win condition in the other, so the first
question about any doubler is which engine you are in.

Worked math recorded: one Dwarf cast under Thorin + Roaming Throne + Molten Echoes + Xorn +
Anointed Procession = **16 Treasures** and +16/+0 on every other Dwarf. Also a real play tip —
Xorn before Anointed Procession, because (1+1)x2 = 4 beats (1x2)+1 = 3. The replacement-effect
ordering rule is labelled **uncited**: wizards.com is blocked, `rules.py` degraded as designed.

**No `combos.csv` rows were added, on purpose** — the file is for combos and this deck has
none; adding "Thorin + Molten Echoes" would be the census inflation the reference warns about.
**No study deck was added to `data/decks/` either**, deliberately avoiding a repeat of the
`deck_conflicts` wart the Bartolomé study copy introduced.

Collection verdict: **30 of 80 non-basic slots owned and none of the engine** — all generic
staples. Zero Seven Dwarves, no Thorin/Cadric/Molten Echoes/Flameshadow/Manufactor/Procession/
Mondrak/Xorn. Only real overlap is Roaming Throne (owned x1, uncommitted), a trigger multiplier
with no tribal deck to live in. Not buildable.

## Token / treasure / copy lattices — knowledge added, collection does NOT support it (2026-08-19)

A second deck-tech was requested (video `j37Rsj4mqhU`, "crazy amounts of copies and treasure
tokens"). **It could not be reviewed** — YouTube is egress-blocked here and the ID does not
resolve through web search. The shape was therefore derived from verified card text and
first principles, NOT from that creator's list. If the video's specific tech matters, the
title or the decklist is needed.

`combo-shapes.md` gained an extension covering four things worth not re-deriving:

1. **PAYOFF sub-types.** The zero-mana death lattice is the same; what you bolt on sets the
   ceiling. death→drain wins outright; **death→mana (Ashnod's Altar, Pitiless Plunderer) is
   NOT a win — it is a resource, and the sink must be named in the same breath.**
2. **Dual-slot cards.** Ashnod's Altar is outlet AND mana payoff at once, which shortens
   every combo in the deck by a piece. Weight dual-slot cards above single-slot upgrades.
3. **The COPY lattice** (Kiki-Jiki + an ETB-untapper) with the two gates people miss:
   nonlegendary-only targets, and tokens die at the next end step, so it MUST win that turn.
4. **Doublers are multipliers, not combo pieces.** infinity × 2 = infinity. Counting
   Doubling Season/Parallel Lives as a combo piece inflates a census with non-combos.
   Academy Manufactor is different — a *transmuter* that converts one infinite resource
   into three, and it decks you unless you have an out.

**Counted verdict: this collection does not support the shape.** death→mana outlets 2/15
(both one-shot spells, not repeatable), copy engines 1/16 (Rite of Replication, one-shot),
token doublers 0 real ones — the three "doublers" owned (Roaming Throne, Wizard's Staff,
Delney) double TRIGGERS, not tokens. No Ashnod's Altar, Phyrexian Altar, Pitiless Plunderer,
Dockside, Kiki-Jiki or Doubling Season. Do not build toward it today.

**The one actionable buy: Ashnod's Altar**, now on `yshtola-nights-blessed.buylist.csv`.
She already runs Sun Titan + Angelic Renewal (loop) and Exsanguinate (sink), so the Altar
alone is a second independent infinite kill that survives Blood Artist being removed.
`combos.csv` 92 → 98; the detector surfaces it as a one-away line on her page.

Fixed in passing: Smothering Tithe's buylist `Replaces` still pointed at Commander's Sphere,
which #135 cut — retargeted to Fellwar Stone.

## Y'shtola upgrade APPLIED — the collection's first live infinite (2026-08-19)

Player-ratified. `yshtola-nights-blessed` now runs **Viscera Seer + Sun Titan +
Angelic Renewal** — a zero-mana infinite death loop with Blood Artist / Bastion /
Vito converting it into a table kill. In over **Commander's Sphere** (11th rock) and
**Soul Shatter** (8% field, 10th removal); logged `Source=manual-replace`; notes
carry the do-not-cut block, pilot line and bench list.

**Honest bracket call: the deck STAYS Bracket 3, power 78 unchanged.** The detector
rules the line "deterministic, but not a cheap 2-card line" — three pieces, none
tutorable for free — so it is a clean win condition, not a bracket jump. An earlier
in-session claim that this makes her Bracket 4 was wrong and is corrected here.

Final sweep also surfaced two MORE owned free outlets, both white enchantments,
committed nowhere: **Fanatical Devotion** (x2) and **Martyr's Cause** (verified;
Martyr's Cause makes the loop also prevent one damage source per iteration).
`combos.csv` 82 → **92**; `--collection-combos` now reports **25 of 92 owned** (was
0 of 22 at session start). Karmic Guide is the one owned returner left on the bench
with no loop partner (MV 5 puts her above every returner's cap — she needs
Reveillark, not owned).

## The lattice generalises — collection can build 15 infinites (2026-08-19)

Follow-up to #133. The 45 rows merged there named **Bartolomé** in every Pieces cell, so
the KB had learned the *instance*, not the *pattern* — and could not see the identical
engine sitting in the player's own decks. Fixed by adding 15 rows for the three **owned,
uncommitted free sac outlets** (Viscera Seer, Woe Strider, **Yahenni, Undying Partisan**),
crossed with the owned loop/returner halves (Angelic Renewal, Gift of Immortality x2 x
Sun Titan, Angel of Indemnity, Brotherhood Outcast).

**`--collection-combos` went 0 of 22 → 15 of 82.** Before this session the pool could
assemble no curated combo at all; the 22 rows were all UB Thassa's Oracle lines whose
pieces are not owned.

**The live finding for an existing deck: `yshtola-nights-blessed` is TWO owned,
uncommitted cards from an infinite.** She is WUB, already runs **Sun Titan** (returner),
**Blood Artist**, **Bastion of Remembrance** and **Vito, Thorn of the Dusk Rose**
(payoffs), and has **no free sac outlet and no loop card**. Add **Angelic Renewal** (owned
x1, in no deck) + **Viscera Seer** or **Woe Strider** (both owned, in no deck) and the deck
has a three-card infinite drain. NOT APPLIED — it moves a hand-tuned Bracket-3 control deck
to Bracket 4, which is the player's call, not the optimizer's.

**Yahenni, Undying Partisan is the only owned commander-legal free outlet** ({2}{B} legend,
"Sacrifice another creature: Yahenni gains indestructible"). Mono-black is the catch: every
owned loop/returner half is WHITE, so a Yahenni deck cannot legally run them. A WB/Esper
host is required — which is why Y'shtola, not a new Yahenni deck, is the cheap win.

Method written up as `.claude/skills/mtg-deckbuilder/references/combo-shapes.md` (read cards
for the SLOT they fill — outlet / loop / returner / payoff) and linked from SKILL.md.

⚠ **Known wart:** the study deck `bartolome-del-presidio-600-combos` lives in `data/decks/`,
so `deck_conflicts` now counts it as a real deck (Generous Gift reads "committed 3"). It is
a reference list, not a sleeved deck. If that noise matters, move it or teach
`deck_conflicts` to skip decks whose `# Source:` marks them as study copies.

## Combo KB taught the Bartolomé lattice (2026-08-19)

`data/reference/combos.csv` went 22 → 67 rows. The 45 new rows are the **Bartolomé del
Presidio sacrifice lattice**, added while reviewing the deck from the YouTube tech
*"1 Deck, 27 Dollars, 600 Infinite COMBOS"* (`youtu.be/1Yusxsud5BE`). Study copy lives at
`data/decks/bartolome-del-presidio-600-combos.txt` (+ `.attrs.csv`, `.notes.md`) — it is
**not** built from the collection (56 of 100 cards unowned) and exists so the engines have
a real combo deck to score.

**The generalisable shape, so it is not re-derived:** Bartolomé is a *free, unlimited*
sacrifice outlet in the command zone. Pair any **Class A** card (aura/enchantment that
returns the creature the instant it dies — Kaya's Ghostform, Angelic Renewal, Fungal
Fortitude, Changing Loyalty, Necrogen Communion, Minion's Return, Gift of Immortality) with
any **Class B** card (creature whose enter trigger returns that permanent from the
graveyard — Brotherhood Outcast, Redemption Choir, Danitha, Sun Titan, Angel of Indemnity,
Shepherd of the Cosmos, Boonweaver Giant) and the two loop for zero mana forever. **44 legal
pairings**, gated only by each returner's MV cap and by Aura-vs-enchantment (Angelic Renewal
is not an Aura, so the three Aura-only returners miss it). Boonweaver searches the *library*,
so commander + Boonweaver is a one-card engine.

**Gift of Immortality is infinite here and it is easy to get wrong.** Its creature returns
*immediately*; only the Aura waits for the next end step — and the returner's enter trigger
brings the Aura back at once, skipping the delay. On a sac outlet alone it is once per turn.

**Two traps caught in the process:**
- `mtglib._norm` does **not** fold accents. `combos.csv` pieces written as "Bartolome"
  silently degraded 45 complete combos into "one piece away — add Bartolomé (not owned)".
  Reference data must use the canonical accented name.
- `deck_stats.py` does **not** read a deck's `.attrs.csv`; only `deckcore.analyze_deck()`
  does. A deck whose types live in the companion file reads as 31 lands / empty curve
  through the old CLI and 37 lands / real curve through the hub. Prefer the hub.

Also worth knowing: the deck `.attrs.csv` contract has **no `Cost` column**, so pip demand
cannot be computed from a companion file — `manabase.py` reported W 9 / B 2 for a deck whose
real demand is **W 28 / B 37**. Any pip claim from a deck without the full collection CSV
behind it has to be computed separately and labelled.

With the KB taught, `power.py` moves this deck **Bracket 2 → Bracket 4** on the early
two-card combos, which is the correct read.

## Phase A of the landfall spec SHIPPED — and it was not cosmetic (2026-08-17)

`deckcore._ARCHETYPE_ROLE_RANGE` now carries `"landfall": {"ramp": (9, 19)}`, and
`tifa-lockhart`'s header reads `# Archetype: voltron landfall`.

**The thing to not re-derive:** the default 9-13 band was not merely mislabelling ramp 19
as "high". At 19, *every* ramp-touching swap falls outside the band in both directions, so
`optimize.py`'s accept filter rejected all of them and printed **"already aligned with the
field"** while the deck sat at **10/25** field top-25 overlap. The deck was frozen, not
aligned. Widening released six field-superior swaps → **15/25**.

**The ceiling is the MEASURED count (19), not one higher, and that is load-bearing.** A
swept comparison: `hi=19` and `hi=20` unblock the identical six swaps and reach the
identical 15/25 — but applied ramp equals the ceiling at every value 19-22. The ceiling is
a target the optimizer FILLS, not a tolerance, so `hi=20` buys zero field alignment and
spends a draw slot (draw 10→8, its band floor, instead of 10→9). A ceiling above a measured
count is an add licence. This was caught by adversarial review after `(9, 20)` was first
shipped in `460438a`; do not "restore headroom for consistency" with the other rows.

Applied state (supervised, `.changes.csv` logged): 100 cards, ramp 19, draw 9, removal 10,
Bracket 3, **field top-25 15/25**, second optimizer run reports "already aligned" so
idempotence is genuine now. Power 67 → **64** — the dip is card advantage (−1.5, draw 10→9)
and curve shape (−0.6) on a scorer that has no concept of landfall payoff, so it reads five
land-to-battlefield ramp spells as generic ramp. Mana consistency unchanged (keepable 83%,
screw 13%, commander T3 94%).

⚠ **The 60% is paper.** Every card producing the 10/25 → 15/25 gain is a copy committed to
another deck (Cultivate, Sakura-Tribe Elder, Nature's Lore, Rampant Growth, Sword of the
Animist); only Planar Engineering was free. Shared cards went 6 → 11, 17 copies short,
lending from Bruce Banner, Cloud, Cosmic Spider-Man and Ur-Dragon. Grounding rule #8
working as designed — but never quote the 60% without this qualification.

**Follow-up worth its own spec:** `optimize.py` prints "already aligned with the field"
whenever no swap survives the filter, *including* when the filter is deadlocked by an
out-of-band role count — so any deck outside a role band reads as aligned forever. A
truthful message would name the gate.

## Optimizer honesty + canonical pin keys SHIPPED (2026-08-19)

Both phases of `docs/spec-optimizer-deadlock-reporting.md` are in; that file is now a
record, not a work item. Nothing is queued for the next session.

**Phase A — "frozen", never "aligned".** `optimize` used to print "already aligned with
the field" whenever no swap survived, including when the role-band gate froze candidates
that had already cleared the anti-churn margin and the field veto. It now names the gate:
`no changes — N candidate(s) blocked by the ramp band (current 19, template 9-13)`, plus a
standing `note:` for any out-of-band role even when other roles did swap, mirrored to the
webapp flash. New additive `role_deadlock` key on both report return sites.
**Reporting-only** — the freeze itself is deliberate and a test pins that swaps are
unchanged; softening the gate would churn a hand-ratified deck toward the blind band.
Verified against the real history: tifa with its header reverted to `voltron` now prints
the blocked-candidate line where it used to claim alignment.

**Phase B — one canonical pin key.** `deckcore.pin_key` = `_norm(front_face(name))`,
applied in `load_pins` AND `save_pins`, so legacy/hand-edited rows migrate on first read
(no migration script; the live `pins.csv` was already canonical). Six probe sites fixed:
BOTH `keep` probes in `optimize` (cut loop and land pass), `auto_build`'s pool filter,
`build_dashboard`'s panel payload, `_validate_add`'s warning, and both writing routes.
The bug was two-sided — a full-name pin was invisible to the reserved filter (optimizer
OFFERS a reserved card) and a front-face pin was invisible to the keep-set (optimizer
CUTS a card pinned to that deck).

⚠ **Two things found while implementing, neither fixed, both recorded in the spec's
header:**
1. **`optimize` scores with `value_of(resolved_name)` but probes `reserved` with the
   FIELD key.** For a split card those spellings differ, so a split-card add is
   margin-blocked before the pin logic is even reachable. Pre-existing, unspecced, and
   the next real thing to ratify in this area.
2. A realistic split card (`Murderous Rider // Swift End`) classifies as `removal`, so
   with removal below its band the BAND protects it from cuts — which made the first
   version of the keep test pass for the wrong reason. The shipped tests use a
   role-neutral split name and were each verified to FAIL when their fix is reverted.

Suite is 840 tests (was 820).

## Basic lands are always owned (player-ratified 2026-08-17)

The player owns hundreds of every basic and **will not** add them to the collection
export. Treat the supply as unlimited: any basic count in a decklist is satisfied, basics
never go on a buy list or an ownership-gap report, and a manabase is never sized to the
snapshot's recorded count. Canonical statement lives in
`.claude/skills/mtg-deckbuilder/references/grounding-rules.md` **#9**, echoed in
`CLAUDE.md`, `SKILL.md`, `deckbuilding-principles.md`, `data/collection/README.md` and
`docs/collection-formats.md`.

**The tooling now agrees (fixed 2026-08-17).** `deck_stats.owned_enough()` was the last
holdout — it had no basics guard, so a 30-Forest manabase printed
`Forest: deck wants 30, you own 16` under "Ownership check" and `build_dashboard`'s
`ownership_block` rendered the same row under **Buy-list candidates**. It now skips
`mtglib.is_basic` names like `deck_conflicts` and `optimize` always did.
`tests/test_basics_unlimited.py` covers the function, the rendered dashboard block, all
six basics plus Snow-Covered printings, and asserts the exemption stays surgical (a real
shortfall on a non-basic still reports). Verified to fail without the guard.

## Tifa took the shared green cards (2026-08-17, later same day)

**Kaalia is gone too** — the player deleted it in the hosted app, and the app's own sync
pushed the deletion (`343dfb5`), removing `data/decks/kaalia-of-the-vast.*` **and** its
`pins.csv` row. Nothing was left for a session to clean up but a stale "Pinned to
kaalia-of-the-vast" note in `commanders.csv`, now removed. **The stable is SEVEN decks.**
Its `data/reference/field/kaalia-of-the-vast.json` is left alone — generated data the
Action owns.

**The correction that drove this:** the previous session refused to apply the optimizer's
`[shared]` swaps to Tifa, claiming they would "break Bruce Banner and Cosmic Spider-Man."
That was invented. `optimize`'s own docstring: *"Sharing is ON by default: two decks in the
same archetype legitimately want the same cards, and the player decides which one gets the
physical copy at sleeving time."* Grounding rule #8 says mark, don't block. Refusing to
share is the failure that rule exists to prevent — do not re-introduce it.

Applied with sharing at default (**not** `--owned-only`). **Nothing was removed from any
other deck** — this is additive. Six cards now carry the ⇄ badge (Swiftfoot Boots,
Snakeskin Veil, Heroic Intervention, Beast Within, Fabled Passage, Rogue's Passage) and the
shortfall is on `data/wishlist.md`.

- **Field top-25 overlap: 4/25 → 10/25 (16% → 40%).** Still under the ~50% line, and still
  structural: 5 of the remainder are in other decks (cloud 5, bruce-banner 4) and 10 are
  unowned. The optimizer's own verdict is unchanged — *"this deck can't improve from your
  collection: buy the gaps."*
- Power 66 → **67/100**, interaction 9 → 10, Bracket 3. Second run proposes no swaps
  (idempotent). All 14 protected engine pieces survived.
- Deleting Kaalia freed **Evolving Wilds** (81% field), which came in as a *free* add rather
  than a shared one.
- `deck_sections.py --apply` was needed afterwards: the optimizer's re-file merged the
  Sorceries block into Instants. Regrouped, 0 unsorted.
- Buylist pruned of the seven rows for cards now in the deck (their shared-copy need is
  tracked by `wishlist.py` instead), and three `Replaces` targets repointed after their
  original targets were cut.

**Nothing in this deck is pinned.** Pinning is the manual, human-in-the-loop reservation —
📌 on the card panel of any deck page (`POST /deck/<stem>/pin`) or the **Pins** tab
(`/pins`, one-action move via `/pins/move`). A pin is honoured as "spoken for" by
`optimize` (`pinned_elsewhere`), `auto_build` and `edhrec`; a manual add in the app only
*warns*, because the player's word beats their own earlier reservation. Unpinned cards stay
freely shareable. ⚠ Known gap: the pin button exists only on the **dashboard** card panel
(`scripts/assets/card_panel.html`); the site-wide panel (`webapp/templates/_cardpanel.html`,
used on collection/shared/wishlist pages) has no pin control — **spec'd as Phase B of
`docs/spec-landfall-template-and-panel-pins.md`, ratified, awaiting implementation.**

## The deck stable was EIGHT decks (2026-08-17) — see above, Kaalia brings it to SEVEN

The player **dismantled Smaug, Wicked Worm and Doctor Doom** physically, so
`data/decks/smaug-wicked-worm.*` and `data/decks/doctor-doom.*` were deleted (recoverable
from git history; no pins referenced either). That freed their copies back into the pool —
which is why the Tifa build below could claim cards the earlier conflict scans showed as
committed.

Current stable (7): `bruce-banner-incredible-hulk`, `captain-america-team-leader`,
`cloud-ex-soldier`, `cosmic-spider-man`, `the-ur-dragon`, `yshtola-nights-blessed`,
**`tifa-lockhart`**. (Kaalia was deleted later the same day — see the section above.)

### tifa-lockhart — "Doubling Down" (mono-G landfall voltron, Bracket 3, power 65/100)

Built 2026-08-17 from the name-only snapshot + `collection_attrs.snapshot.csv`.
100 cards, 38 lands (30 Forest), singleton-clean, no color-identity violations.
Goldfish (3,000 games): commander on board T2 86% / T3 97%, keepable 83%, screw 13%,
flood 0%. Green sources 29 vs Karsten target 23.

**Card text WAS verified** — via `WebSearch` against Scryfall/Gatherer, which reaches
the network even though `api.scryfall.com` and `json.edhrec.com` are 403 at this
sandbox's gateway (`carddb.py --verify` and `edhrec.py` both fail here;
`edhrec.com`/`gatherer.wizards.com` are also blocked for `WebFetch`, but WebSearch
result snippets are not). That fallback is documented in
`references/tooling-and-data.md` and is a required step of the sleeper audit — the
first pass of this build skipped it and shipped three wrong claims.

**The build thesis, and it is worth not re-deriving:** Tifa's landfall **doubles** her
power rather than adding to it, so the deck maximizes *permanent base power* first and
treats land drops as the multiplier. Necklace of Girion is the engine — its counters are
permanent and its trigger and Tifa's landfall trigger go on the stack together, so you
order the Necklace counter to resolve **first** and the doubling then applies to the
bigger number. Getting that order backwards halves the damage.

**`fetch:forest` DOES NOT MEAN LANDFALL — the trap this build fell into.** The flag is
oracle-derived but does not distinguish *search to hand* from *search to battlefield*.
Verified 2026-08-17: **Saber-Tooth Moose-Lion** (`{4}{G}{G}` 7/7 reach) and **Balamb
T-Rexaur** (`{4}{G}{G}` 6/6 trample) both carry **Forest*cycling* {2}** — Forest to
**hand**. Neither triggers landfall or the Necklace. Both were in the first draft of the
99 and named in the notes as protected engine pieces; both are now cut. **Land Grant** is
the same shape and stays only as a land-drop enabler. Of the four `fetch:forest` cards in
the pool, **only Wood Elves** actually puts the Forest onto the battlefield. Count the
targets before crediting an ability (card-review-method §3).

**Caveats a future session must not paper over:**
- **Almost no extra-land-drop effects.** Corrected from the first draft's "zero":
  **Terrain Generator** is one — verified that its `{2}, {T}` basic-land drop does *not*
  use your land play. It is the only one owned. Still zero Azusa / Exploration /
  Burgeoning / Wayward Swordtooth / Ancient Greenwarden, and **zero +1/+1 counter
  payoffs**. This is a voltron deck wearing a landfall coat. The buylist is ordered
  accordingly, headed by **Traverse the Outlands** (X = greatest power, so it compounds
  with the doubling — the community's headline Tifa card, unowned).
- **Ramp is 19, and the `landfall` template entry now covers it (SHIPPED).**
  `deckcore._ARCHETYPE_ROLE_RANGE` carries `"landfall": {"ramp": (9, 19)}` and the deck's
  header reads `# Archetype: voltron landfall`, so the count reads `(ok)`. The ceiling is
  the MEASURED count on purpose — it behaves as a target the optimizer fills, so a higher
  one is an add licence. Full reasoning in the code comment and in the section at the top
  of this file.
- **Field top-25 overlap is 15/25 (60%)**, up from 10/25 — but every card that produced
  the gain is a copy committed to another deck (Cultivate, Sakura-Tribe Elder, Nature's
  Lore, Rampant Growth, Sword of the Animist); only Planar Engineering was free. It is a
  **paper 60%** until those copies are bought or the lending decks release them. Shared
  cards went 6 → 11 (17 copies short), lending from Bruce Banner, Cloud, Cosmic
  Spider-Man and Ur-Dragon. The un-share path is `data/wishlist.md`'s "shared copies to
  buy" section, NOT the deck's `.buylist.csv` (a buy row names a card not in the 99).
- **The optimizer's swaps WERE applied**, deliberately and supervised, in two rounds: the
  four protection/land shares on 2026-08-17 (Swiftfoot Boots 67%, Snakeskin Veil 64%,
  Heroic Intervention 53%, Beast Within 53%, plus Evolving Wilds / Fabled Passage /
  Rogue's Passage), then the six the landfall widening un-deadlocked. Sharing is ON by
  default (`optimize.py`'s docstring) and grounding rule 8 is mark-don't-block; refusing
  to share was an invented rule, corrected by the player. Nothing was removed from any
  other deck — all of it is additive.
- **Current measurements** (re-derived 2026-08-18, replacing every superseded figure that
  used to sit here): 100 cards, 38 lands (30 Forest), ramp 19 / draw 9 / removal 10 all in
  band, Bracket 3, power **64/100** (the dip from 67 is card advantage and curve shape on a
  scorer with no concept of landfall payoff), green sources 30 vs Karsten target 23,
  goldfish keepable 83% / screw 13% / commander T3 94%, optimizer idempotent
  ("already aligned"), ownership check clean.
- **Field %s that corrected earlier claims:** `Traverse the Outlands` is **15%**, not the
  headline card an article made it sound like; `Adventuring Gear` **51%** and
  `Crop Rotation` **49%** are the deck's genuinely field-endorsed picks; `Horn of Greed`
  **12%**, `Wood Elves` **10%**, `Explorer's Scope` **8%** are engine-read holds, not
  field-backed ones.

`Tifa, Martial Artist` is also owned ×1 and is a *different card* — it is not in this
deck and has not been evaluated.

## Double-faced cards never enriched (FIXING 2026-08-16, `docs/spec-dfc-enrichment.md`)

Root cause, **measured on a GitHub runner** rather than inferred: Scryfall's
`/cards/collection` `name` identifier matches a **single face**, so submitting the
collection's `"Front // Back"` spelling missed. Only 14 of the player's 40 owned
double-faced cards were resolving, and the ones that fell through landed on the name
heuristic — which read the verified Dragon creatures `Scavenger Regent // Exude Toxin`
and `Marang River Regent // Coil and Catch` as **lands**.

Shipping in slices, each validated before the next:

- **Slice 1 — the cure (done).** `carddb._best_identifier` submits `front_face(name)`
  and `_response_keys` maps the single-face response back onto every row that answers
  to it, so two rows sharing a front face both resolve. UAT is a probe step in
  `.github/workflows/deck-verify.yml` that enriches every `" // "` name in the
  committed snapshot against live Scryfall on each branch push — it lives there, not
  in `attrs-snapshot.yml`, because that workflow ends in a hardcoded push to `main`.
  **Live result: 40/40 resolved, 0 untyped, PROBE VERDICT: PASS** (was 14/40), and the
  step now runs in ~1s, which is how you can tell the fuzzy fallback went quiet.
- **Slice 2 — land hints (done).** `_LAND_HINTS` matched bare substrings, so "cave"
  matched inside "S-**cave**-nger". Now whole-word with a tolerated plural. Measured on
  the collection: lands recognized 105 → 126, non-lands misread 49 → 26, nothing lost
  either way. Spec §8 has the table and the honest limits.
- **Slice 3 — hardening (done).** `_request_json` is the one path to Scryfall's JSON
  API, carrying the `(5,15,30,60)` ladder for 429/503 only — a blocked proxy fails now
  rather than after 110s. `_fetch_named_fuzzy` is **three-way** (card / `None` for a
  real 404 / **raises** on transport failure); it used to swallow everything into
  `None`, which is how "the proxy blocked us" and "no such card" became one answer.
  `enrich_api` now raises **before writing** if any card could not be looked up at all
  — a partial attrs file reads downstream as "not enriched yet". Misses print
  unconditionally, the fuzzy pass paces at 0.7s and uses the 30-day
  `VERIFY_CACHE_DIR`, and `--min-match` applies **per category**: DFC coverage is
  measured on its own, because 26/40 missing still left the old run at 99% overall.
  `gen_card_notes._fetch_oracle` was a third copy of the ladder carrying both original
  bugs (full-name identifiers, bare `split("//")`) — it now calls
  `carddb._post_collection`.

**⚠ The fuzzy cache is opt-in** (`fuzzy_cache_dir=None`), not defaulted to
`VERIFY_CACHE_DIR`. The convenient default made the test suite write into the real
`data/cache/scryfall`. `main()` passes the real path; a library function does not pick
one under `data/`. There is a test guarding this — don't "simplify" it back.

- **Phase F — the backfill (done).** PR #122 squash-merged, then one
  `workflow_dispatch` of `attrs-snapshot` on `main` (run `31985056545`, commit
  `17ecc12`). `collection_attrs.snapshot.csv` now carries **2,691 rows — all 40
  double-faced cards present and typed, zero untyped**, and no deck reports an
  untyped card on the name-only snapshot any more.

**What the backfill actually recovered:** `Scavenger Regent // Exude Toxin` and
`Marang River Regent // Coil and Catch` now read `Creature / Dragon` instead of *land*.
Both are **owned ×1 and in no deck** — they were invisible to every Dragon pool scan
while the heuristic called them lands, so the Ur-Dragon audits done before 2026-08-16
never saw them. The owned Dragon pool now counts **47 unique / 54 copies**. Neither has
been run through the sleeper audit
(`.claude/skills/mtg-deckbuilder/references/card-review-method.md`) — that is open work,
not a decision already taken.

Post-merge state of the nine decks: no optimizer swaps proposed (everything held by the
gate), field top-25 overlap Ur-Dragon 21/25, Y'shtola 21/25, Smaug 13/25 (a new build,
12 of its gaps unowned).

`download_bulk()` is **deferred by the player** ("leave the bulk for now"); the API
path is the default and works.

## Where the app runs

- **Hosted:** a PythonAnywhere **free-tier** web app (Python 3.13, virtualenv with
  Flask only, WSGI entry `webapp/pa_wsgi.py`), used from every device — phone as an
  installed PWA, PC through the same URL. Chosen over Render because PythonAnywhere's
  filesystem is **persistent** — this app's flat-file data model requires that. The
  hosted URL is deliberately not written in this repo; treat it as sensitive.
- **Local:** `webapp/run.sh` / `run.bat` still work for offline development.
- **⚠ On the host, "Static files" on the Web tab must stay EMPTY** — `/static/tokens.css`
  is a Flask *route* serving `scripts/assets/tokens.css`; a directory mapping would
  shadow it and silently 404 the shared design tokens. `tests/test_deploy.py` guards this.
- **Keepalive:** free web apps need "Run until 3 months from today" clicked every ~3
  months. Missing it sleeps the app; no data is lost. **The paid tier was offered
  and declined 2026-08-14** (`spec-infra-hot-paths.md` Phase 4): the free tier
  stays, this keepalive stays, and the in-app sync thread stays instead of a
  Scheduled Task. Don't re-propose it unless one of those actually starts hurting.

## Card-panel Replace/Remove: the " // " trap reached the editor (FIXED 2026-08-15)

Live bug report: "I tried to replace a card in the Smaug deck and it did not work."
Root cause: `webapp/app.py`'s `_edit_deck_card` matched the outgoing card by raw
`_norm` equality while the panel's `data-key` can carry EITHER form of a DFC name —
decklist figures key the deck file's own form, EDHREC/field rows key what the
snapshot emits (often the front face alone). `Smaug, the Great Calamity // Spew
Flame` vs `Smaug, the Great Calamity` therefore no-opped. Worse, BOTH failure paths
(`would duplicate` refusal and edit-found-nothing) returned a bare redirect, and the
panel reloads on any redirect — failure was pixel-identical to success. Fixed: the
editor now matches `name_keys()` (front-face-aware, same test the route's singleton
guard already used), refusals return 409/404 with a reason, and the panel alerts the
server's text instead of reloading. Regression tests cover both DFC directions, the
`SP//dr` no-split guard, and the two error responses (`test_deck_edit`,
`test_add_card`).

## 2026-08-15: Hobbit import, the Smaug package, Delney, proxy sheets

**Collection:** the new Sorted export is live — 2,691 unique / 3,890 total, 70 new
uniques, 42 quantity bumps, nothing lost. The Hobbit (HOB) is now 116 uniques in the
pool. **⚠ A sandbox import does NOT reach the server, and this bites every time.**
`collection.csv` is gitignored (the privacy hard line), so an export handed to a
session in chat lands in that sandbox only — no merge, sync or field-snapshot job can
carry it. The server keeps serving its OWN older CSV (`_default_collection()` prefers
it over the tracked snapshot whenever it exists), so **every newly-bought card renders
with a phantom `BUY` badge** until the player uploads the same export through
`/collection/upload`. Confirmed live 2026-08-15: 12 phantom BUY badges across five
decks, all of them 2026-08-15 pickups. The fix is the player's one action — upload —
after which the background enrichment runs and the badges clear. **Do NOT paper over
it with `owned_additions.txt`:** `mtglib.merge_collection` ADDS quantities, so those
rows double-count the moment the real export lands (that is exactly why Vito and
Force of Will were deleted from that file on 2026-08-11). Say the upload step out
loud whenever a session imports a collection. **Iron Man is retired at the player's direction** ("for now") — all five
deck files deleted in one commit, recoverable verbatim from git history; no pins
referenced it; its field snapshot stays for a future rebuild.

**Sleeper audit (both verify rounds on the deck-verify runner, 84 cards, 0 unverified):**
- **The Ur-Dragon got the Smaug package** — Smaug the Magnificent IN for Reconnaissance
  Mission (0%), Desolation of Smaug IN for Thought Vessel (5%, colorless-only rock in a
  "fixing above all" deck), Smaug the Impenetrable IN for Kolaghan, the Storm's Fury
  (15%, dash fights eminence). Engine reasons in the deck notes. Dragons 30 → 31.
  **Lozhan stays on purpose** (verified: every Dragon cast deals its MV in damage —
  removal stapled to the plan; its 14% underrates this deck). Draw dips 8→7 against
  template — the commander IS the draw engine, said openly in the audit. Desolation of
  Smaug is curated into mtglib WIPES. Tiamat's buylist row re-pointed.
- **Y'shtola got Delney, Streetwise Lookout** (39% field!) for Read the Bones (6%):
  Y'shtola is printed power 2, so Delney doubles BOTH her triggers — and Blood Artist's
  and Vito's. The compounding is written up in the deck notes as a protected engine piece.
- **Cosmic Spider-Man got Skyward Spider** (21% field, on-tribe ward body) for Relic of
  Legends (10%).
- **Benched with reasons:** Glamdring (Banner's 23 spells are cheap + pip-heavy, and no
  equipment shell), The Reaver Cleaver, Bard the Bowman, My Precious, An Unexpected
  Party, Lord of the Eagles. **Commander seeds noticed, not built:** Tom Bombadil
  (needs a Saga package), Mimeoplasm Revered One, a Beorn bear kernel and an
  Azog/Bolg goblin kernel from HOB. Terrian and Tyrox returned "(no oracle text)"
  from the verify runner — treated as unverified, judged nowhere.

**Kaalia of the Vast is reserved (2026-08-15, player direction):** she left the
Ur-Dragon 99 (Smaug, the Great Calamity // Spew Flame took the slot — fourth Smaug,
31st dragon, and a removal adventure in the thinnest role) and is **pinned in
`data/collection/pins.csv` to the future stem `kaalia-of-the-vast`** — that pin is
what machine-blocks the optimizer/auto-builder from re-seating her copy anywhere.
Dry-run says the deck is real when the player wants it: **34 uncommitted
Angel/Demon/Dragon bodies in Mardu** (13 angels, 9 demons, 12 dragons — auto_build
fills a legal 100 but its generic template can't see her cheat-into-play engine, so
build her by hand from that pool when the time comes).

**Proxy sheets shipped** (`scripts/proxy_sheet.py` + `/deck/<stem>/proxies`): 63×88mm
cells, nine per page, exact printings from the export's set+number, Chromium-measured
geometry. The index links each deck's **buylist** proxies — decks are owned-only by
rule, so what's worth printing is the upgrade you're deciding whether to buy.

## Three new decks built 2026-08-15 (scout session -> builds, same day)

The stable is NINE decks. Build order was deliberate — each claims physical copies:

1. **smaug-wicked-worm — "Dragon Sickness"** (Rakdos treasures, power 71, Bracket 2).
   Commands the SECOND owned copy of Smaug, Wicked Worm; the first stays in Ur-Dragon.
   Engine: ETB Treasures scale with opponents' artifacts; every Treasure-funded spell
   draws. Hellkite Tyrant is the win; Sackville/Lake-town sac shell grinds;
   Dragon-Cursed Halls and Reckless Lackey verified in. Field: 292 cards, 1,223 decks.
2. **doctor-doom — "All According to Plan"** (mono-B, power 73 — #2 IN THE STABLE at
   birth, Bracket 2). The mono-B MSH card we own, not the Grixis "Rules All". Doombots
   + Castle Doom + Doom Reigns Supreme keep him indestructible; The Masters of Evil
   TUTORS PLANS (verified). Top-25 overlap 13/25 with 12 not owned — his buylist is
   the growth path, said honestly by the optimizer itself.
3. **kaalia-of-the-vast — "Open the Gates"** (Mardu, power 67, Bracket 2). The pin
   resolves here. **24 A/D/D bodies** after the density repair: the first optimizer
   pass took ten bodies for staples while nineteen generic Hero fillers survived —
   the support was right, the room was wrong, so eight bodies came back OVER filler
   (logged manual-replace, notes name them). Neriv (entered-this-turn damage DOUBLES)
   and Rakshasa Debaser (drops attacking -> immediate reanimate trigger) are her
   verified bombs. Dragons went to Smaug first; her dragon buys are the buylist.

All three: auto_build skeletons + hand-placed engines, four verify-runner rounds total
(103 cards, 0 unverified), sections regrouped, notes protect every engine piece,
optimizer applied then re-previewed "already aligned", wishlist regenerated (the
[share] land upgrades created real shortfalls -> priced rows). commanders.csv gained
all three with verified identities.

## Deck export: HTML report + PDF via the browser (NEW 2026-08-15)

Spec: `docs/spec-deck-export.md`. Player asked for "export a deck as an html/pdf
report". Scoping found the HTML report already existed — `build_dashboard.generate()`
has always emitted a self-contained single file — so the work was two real gaps, not a
new feature.

- **`GET /export/deck/<stem>.html`** downloads that file as an attachment
  (`editable=False`, so nothing posts into the void; no singleton banner, which is a
  live-surface alarm). Sits beside `/export/deck/<stem>.txt`, takes the same `?raw`.
  The decks list now offers **`.txt`** and **`Report`**, and the Report link's title
  carries the honesty label: images need a connection, Ctrl+P for a PDF.
- **Print actually works now.** Every theme is dark; browsers drop backgrounds but keep
  text colour, so the dashboard printed near-white on white. The `@media print` block
  was rewritten to repaint ink-on-paper and **moved to the end of the `<style>`** —
  `@media` adds no specificity, so sitting above the inlined `add_card.css` /
  `card_panel.css` meant any print rule could be silently outranked (the old
  `.ac { display:none }` worked only because `add_card.css` never sets `display`).
- **There is deliberately no PDF generator**, and shouldn't be: `scripts/` is
  stdlib-only, card images are browser hotlinks a server-side renderer can't fetch, and
  the host is a free tier with no cairo/pango. The browser's print dialog is the export.
- **Two live bugs found and fixed on the way.** `shared_html` never closed its
  `<div class='tablewrap'>` (10 opens / 9 closes in a real render). And the explainer
  print rule was a **no-op**: `<details>` is emitted closed, and a closed `<details>`
  hides children through the UA's `::details-content` box, not the child's `display` —
  so every "what this means" caveat was missing from paper while a test passed on the
  substring. Verified in headless Chromium: the paragraph's `checkVisibility()` goes
  `False → True`. `tests/conftest.py` now has `print_block()` so print tests assert
  against the whole brace-matched block instead of a fixed `[:200]` window.
- **Backlog, not built:** proxy sheets (3×3 grid at 63×88 mm) — the one genuinely
  print-geometry-shaped thing missing. Own spec, own player decision.

## deck-verify: the sandbox's way out of the egress block (NEW 2026-08-14)

`.github/workflows/deck-verify.yml` runs the two **network-dependent grounding steps** on a
GitHub runner, because a Claude Code sandbox cannot reach Scryfall or EDHREC (the egress
proxy answers **403 to CONNECT** — `carddb.py --verify` returns UNVERIFIED, `optimize.py`
sees 0 field cards). Card Kingdom, Draftsim and Gatherer are blocked too; only `WebSearch`
resolves, and a search summary is not verbatim oracle text.

- **Triggers on push to `claude/**`**, not just `workflow_dispatch` — a dispatch-only
  workflow is undispatchable until the file reaches the DEFAULT branch, which is no use to
  the session authoring it. Dispatch inputs (`commander`, `cards`, `commit`) are kept for
  manual runs.
- **It pushes only to the ref it ran on** (`HEAD:${{ github.ref_name }}`). This is the whole
  reason it is a separate file: `field-snapshots.yml` ends in a hardcoded
  `git pull --rebase origin main` + `git push origin main`, so **dispatching THAT on a
  feature branch would rebase the branch's commits onto main and push them there — a silent
  merge with no review.** Do not "simplify" the two into one.
- The card list lives in **`data/reference/verify-queue.txt`** (reviewable in the diff, and
  a place to queue work for the next run). Results go to the job log *and* an artifact.
- **First run (31852039320) verified 55/55 cards, 0 UNVERIFIED, in 13 seconds** and
  committed `data/reference/field/bruce-banner.json` back to the branch. It corrected real
  errors: **Squallmonger** hits creatures *with* flying (so it misses a reach commander) —
  it had been shortlisted on memory; **Hulkbuster Armor** grants flying, which would make
  the Hulk dodge our own sweeper pings; **Warmonger** does work but lets *any player*
  activate it. Read a session's exclusions as provisional until this has run.

## The automation loop (all legs verified on real events)

```
GitHub Action (weekly + on deck pushes + manual)          the hosted app (daily,
  refreshes data/reference/field/*.json  ──▶  main  ◀──   in-app sync: deck edits up,
  (EDHREC field snapshots)                                code + snapshots down)
```

- **Field snapshots** (`.github/workflows/field-snapshots.yml`, spec:
  `docs/spec-field-snapshot-action.md`): EDHREC is permanently unreachable from the
  host (free-tier allowlist), so per-commander inclusion/synergy is committed to
  `data/reference/field/` and refreshed by the Action. Read precedence: live fetch →
  disk cache → snapshot → `{}`.
- **In-app sync** (`webapp/sync.py`, spec: `docs/spec-in-app-sync.md`): the app runs
  `sync_server.sh` in a background thread on the first request of each day, plus a
  "⇅ Sync with GitHub" button on the Decks page. This replaced the planned
  PythonAnywhere Scheduled Task, which became **paid-only** (checked live 2026-08-10).
  Auto-detects the host via `PYTHONANYWHERE_SITE`; `MTG_AUTO_SYNC=1|0` overrides.
  **Self-heals from squash-merge conflicts (2026-08-11):** PR #104's squash rewrote
  deck files the server had local commits on and wedged the pull (seen live on the
  player's phone). The script now parks local state on a PUSHED `server-rescue-<date>`
  branch before resetting to upstream; the status line shows "synced — RECOVERED"
  naming the branch, and **a session must merge that branch back** when it appears.
  **Hardened 2026-08-12:** the rescue branch only ever held COMMITTED state — an
  app save landing during the pull window was destroyed by the reset (reproduced,
  then fixed). Uncommitted work is now stashed before the pull and restored
  after; a conflicted restore stays parked in `git stash list` with a warning;
  a still-dirty tree refuses the self-heal entirely. The wider network/attrs
  plan (allowlist, committed attrs snapshot, remaining sync races) lives in
  `docs/spec-network-and-attrs.md` — the live tracker. **Phase 2 SHIPPED
  2026-08-12** (player approved dropping the Scryfall column): the
  attrs-snapshot Action enriches the committed name-only snapshot into an
  8-column `collection_attrs.snapshot.csv` on GitHub runners, five-guarded
  (refuse-beside-private, `--min-match 95`, plausibility gate, shared
  concurrency group, regenerate-not-rebase retry), with carddb's guarded fuzzy
  (spelling repairs only, never substitutions), the sync push-retry/flock/TTL
  hardening, and the goldfish + /collection consumers updated. **First live run PASSED
  2026-08-12** (99% resolution, all guards green, committed as `5fe3a16`) —
  every clone now loads typed data, and power re-scored on it (yshtola 78).
  ⚠ **The role-repair churn is FIXED in code (2026-08-13, Phase 8) but the
  `--apply`/⚡/`refresh --optimize` freeze stays until one live preview run
  confirms it against the full private CSV — see open item 0.** Phase 1 (the
  environment allowlist) remains the player's five-minute flip and is NOT
  needed by the Action.
- **Push credentials:** a fine-grained GitHub PAT (Contents: read/write, this repo
  only) lives in the server clone's remote URL. Fine-grained PATs **expire** — when
  pushes start failing, mint a new one and re-run `git remote set-url` (a calendar
  reminder ahead of the expiry date shown in GitHub's token settings avoids the
  surprise). Never ask for the token in chat or a screenshot — `git remote -v`
  prints it in full.

## The server is the source of truth for `data/decks/`

Deck files are git-tracked but rewritten **on the server** by the card panel, the deck
editor, and the optimizer. `sync_server.sh` (repo root) reconciles: commits only the
three runtime-edited paths (never `git add -A`), rebases before pushing (aborting
cleanly on conflict), and reloads the app via the WSGI touch unless told not to.

## Current data (season closed 2026-08-10)

- **NEW DECK 2026-08-14: `bruce-banner-incredible-hulk` — Temur (U/R/G), Bracket 3,
  power 71/100.** Built for the player's *brother*, whose card it is — the commander is
  deliberately NOT in the collection, so `deck_stats` reporting one card "not owned" is
  correct, not a defect. **The trap this deck exists to document: Bruce Banner costs
  `{U}`.** The `{2}{R}{R}{G}{G}` printed on the card is the *transform* cost, so the
  color identity is **Temur, not Gruul** — a Gruul build would have been the wrong deck
  entirely. Oracle text came from the player's photographs (grounding rule #6) because
  Scryfall, EDHREC, Card Kingdom and Draftsim are ALL egress-blocked in the sandbox
  (`carddb.py --verify` → UNVERIFIED, proxy 403); `WebSearch` still resolves and
  corroborated the `{U}` front-face cost across three independent sources.
  Engine: flip to an 8/8 reach/trample, then damage him **while he is attacking** —
  Enrage untaps him and adds a combat phase. Pingers are Prodigal Sorcerer, Thornwind
  Faeries and Brash Taunter (fight your own Hulk: he takes 1, the indestructible Taunter
  takes 8 and throws it at a face); Roaming Throne naming **Hero** doubles every Enrage
  trigger. Built from the **uncommitted** pool so it sleeves standalone without pulling
  cards out of the player's six decks. Two exclusions are deliberate and documented in
  the deck's `.notes.md`: **Lightning Greaves** (shroud would stop you targeting your own
  Hulk — Swiftfoot Boots/Champion's Helm grant hexproof instead, which does not) and
  **Basilisk Collar** (deathtouch on a Tim kills your own commander). `combo_detector`
  flags Godo + Helm of the Host as infinite combats; Helm is unowned and is buylisted
  under an explicit "Bracket 4 — DO NOT ADD" tier alongside Caltrops and Aggravated
  Assault. **Both network gaps are now CLOSED — see the deck-verify workflow below.**
  Final: Bracket 3, power **72/100**, top-25 field overlap **13/25 = 52%** (above the ~50%
  floor). `optimize.py` was run on real field data and **deliberately not applied**: it
  proposed cutting the verified engine piece Barbed Field for Blasphemous Act (13 damage
  kills our own 8/8 commander in a one-creature deck) and pulling `[shared]` Counterspell /
  Rhystic Study out of the player's other decks. The engine pieces are named in the deck's
  `.notes.md`, which is what protects them from the next optimizer run.
  `Bruce Banner // The Incredible Hulk` was added to `data/reference/commanders.csv`
  (G R U, `voltron counters ramp`) — note `auto_build.py`'s CLI has **no `--identity`
  flag** despite SKILL.md documenting an `identity=` syntax; `build()` takes the kwarg but
  nothing exposes it, so an unknown commander auto-builds as colorless until it is added
  to `commanders.csv`.

- **Deck sections are now EDHREC-style TYPE sections (2026-08-11)** — Commander /
  Creatures / Instants / Sorceries / Artifacts / Enchantments / Lands / Basics —
  across all decks, kept by the new `scripts/deck_sections.py` (idempotent;
  `--all --apply`). `auto_build` emits the same shape for future decks. Roles +
  power-list tags (Game Changer, Tutor, …) now show in card details on both
  surfaces via `deckcore.load_power_tags`. The migration fixed real misfiles
  (Rhystic Study and Lightning Greaves sat under "Lands" in ur-dragon). ~15 cards
  **All `Unsorted` sections are GONE as of 2026-08-13** (Phase 0): the typed
  attrs snapshot resolved every one, and the server now re-runs the regroup
  itself after a sync that brings fresh attrs (skipping any deck with
  in-section comments, which a regroup would drop). **cosmic-spider-man repaired 2026-08-11**: the 99-card mystery was a corrupted
  commander block (annotated name + stray duplicate line) — cleaned; Ezekiel
  Sims, Spider-Totem (24% field) in over 0%-field Tome of Legends (freeing an
  over-committed copy); Thriving Isle added as the 100th card. Ownership
  RESOLVED (2026-08-11): the player owns none of the twelve snapshot-absent
  cards (but does own 2× the Cosmic Spider-Man commander itself →
  owned_additions.txt); all twelve were replaced with owned substitutes and
  buylisted — details in the deck's .notes.md. The player DELETED
  captain-america-first-avenger via the
  app (2026-08-11); five decks + iron-man remain. Iron Man, Armored Avenger's
  single copy is both a commander and in team-leader's 99 (⇄ badged).
  **yshtola repaired 2026-08-11**: `Observed Stasis` (verified: {3}{U} flash
  Enchantment — Aura, FIC #40 — NOT a land) sat in the Lands section because the
  2026-08-09 optimizer run, typeless on the snapshot, cut Hidden Lair (a real MSH
  land that misses `_LAND_HINTS`) through the *spell* pass and the writer kept the
  section. Moved to Enchantments, typed in the deck `.attrs.csv` so a regroup
  holds, and a duplicate loose commander line (a real singleton violation flagged
  by `singleton_violations`) removed — deck is 100 cards, 38 real lands (24
  nonbasic + 14 basics; name-only heuristics undercount until the server
  re-enriches). Hidden Lair (owned ×1) is back in the available pool. The
  guardrail hole is CLOSED end-to-end: pass assignment is layered — real type
  data (CSV / `.attrs.csv`) → the deck file's own type-exclusive section (deck
  cards) → the field snapshot's `lands` key, i.e. EDHREC's own Lands sections
  (candidates) → name heuristic last — the CLI reports the untyped count instead
  of guessing silently, and the field-snapshot Action has regenerated every
  active snapshot WITH the `lands` key (verified: the Hallowed-Fountain-for-
  Absorb spell proposal corrected to a land-for-land swap on live data).

- **Decks are owned-only as of 2026-08-11 (player request), and the optimizer now
  keeps them that way.** Buy candidates never enter a 99: `optimize()` pairs each
  buy with an in-deck card and APPENDS it to `.buylist.csv` with Replaces = that
  card ("when this arrives, pull that"); existing buylist rows are never removed,
  only their Replaces refreshed (`append_buylist`). The migration pulled every
  provenance-confirmed BUY out of the five affected decks and swapped in owned,
  field-ranked, web-verified substitutes: cosmic-spider-man restored the four
  cards its 2026-08-10 buy run had displaced (Willowrush Verge, University
  Campus, Scarlet Spider Kaine, Spider-Girl Legacy Hero — two of those "buys"
  had cut LANDS through the same typeless-spell-pass hole fixed above);
  team-leader took Avengers Quinjet + Spectacular Spider-Man; cloud took
  Wrecking Ball Arm, Cid Freeflier Pilot, Professor Hojo, Bugenhagen; ur-dragon
  took Zurgo and Ojutai, Kolaghan the Storm's Fury, Broodcaller Scourge, Lozhan;
  yshtola took Krile Baldesion, Contaminated Aquifer, and a 4th Plains; the
  eight hand-built spiders followed on player confirmation of non-ownership
  (see the deck's `.notes.md` for the full mapping). Every deck is 100 cards,
  singleton-clean, **zero unowned cards anywhere**. Cloud's stray duplicate
  commander line (same bug as yshtola's) was also removed.
- **Seventh deck NEW (2026-08-11): `iron-man-armored-avenger`** — mono-blue draw-go
  control, hand-built in a sandbox session (network blocked) from the name-only
  snapshot as the "strongest possible new deck". Power **70/100, Bracket 3** at the
  3-Game-Changer cap (Rhystic Study, Force of Will, Mystical Tutor — all shared
  copies, badged). Finally places the free **Mana Drain** (ex-open-item riser).
  Ships with a hand-written `.attrs.csv` (70 rows covering 99 of the deck's 100
  copies, certain pre-2025 knowledge; commander row deliberately absent — its
  oracle text is **UNVERIFIED** offline, functional role taken from
  `commanders.csv`). Follow-ups route through the
  automation loop, NOT the player's PC: the merge's deck push triggers the
  field-snapshot Action (adds this commander's EDHREC data), the server's daily
  sync pulls it, and the app re-verifies/re-enriches/re-scores on the full CSV.
  The only physical to-do: pull ~25 spare basic Islands (23 owned, 18 sleeved
  elsewhere).
- **Six decks total, and every one is Bracket 3** (fresh-export scoring,
  2026-08-11 post-optimizer-sweep — the owner's "Bracket 3/4 where possible" aim
  is MET across the board — scores below are TYPED-data, 2026-08-12, the first
  scoring on real curve/role counts): Y'shtola 78 · Iron Man 72 · Cloud 71 ·
  Team Leader
  69 · Cosmic Spider-Man 64 · Ur-Dragon 53. No deck can reach B4 from the owned
  pool (4 unique Game Changers owned, total). The server re-scores on the full
  enriched CSV after each sync — expect small number shifts, not bracket changes.
- **Fresh collection export installed 2026-08-11** (Sorted CSV: 2,621 unique /
  3,773 copies after the owned_additions merge; was 2,518/3,602). The committed
  name-only snapshot was regenerated from it in the same session.
  `owned_additions.txt` dropped Vito and Force of Will — the new export carries
  both, so the overrides would double-count; the player-confirmed 2x Cosmic
  Spider-Man stays (export still lists 1). **Player to-do:** upload the same
  export via the app's `/collection/upload` so the server's private CSV matches,
  then the daily sync re-enriches (Scryfall was egress-blocked in the sandbox
  this landed in).
- **Painful Truths revert (2026-08-11):** an 8/11 manual replace had put the
  never-owned Painful Truths into yshtola over Read the Bones — the only unowned
  card across all six decks against the fresh export. Read the Bones is back
  (optimizer advisory: 70/100 strong fit), Painful Truths is buylisted with
  Replaces=Read the Bones, and the revert is logged in `.changes.csv`.
- **2026-08-11 optimizer sweep on the fresh export (all six decks, applied):**
  Iron Man took 9 spell swaps (0%-field big-blue filler → 26–68% field staples:
  Pensive Professor, Kid Loki⇄, Laboratory Maniac, Reconnaissance Mission⇄,
  Bident of Thassa, Professor Hulk⇄, Fellwar Stone⇄, Loki God of Mischief,
  Lightning Greaves⇄) + Bonders' Enclave → Reliquary Tower, and rose 70 → 73
  (tied #1). Cosmic Spider-Man: To the Rescue → Spider-Punk (83%), Plaza of
  Heroes → Vibrant Cityscape (resolves the own-1-committed-2 Plaza conflict;
  team-leader keeps it; 55 → 54 is the raw-card-quality cost, field overlap
  +1). Ur-Dragon: Dragonhawk → Dragonspeaker Shaman (57%), Gilded Goose →
  Savage Ventmaw (34%). Team Leader: Hero's Blade → Avengers Assemble! (54%).
  Cloud and Y'shtola: already aligned, buylist refresh only. **The single owned
  Reliquary Tower went to Iron Man by decision** — Y'shtola's Ash Barrens is
  protected in its `.notes.md` so the optimizer stops re-proposing that swap.
  The ⇄ swaps deepen shared-copy shortfalls (Fellwar Stone and Lightning
  Greaves are now short 2) — priced in `data/wishlist.md` per mark-don't-block.
- **The sleeper audit is now a ratified process (2026-08-11, player request):**
  `.claude/skills/mtg-deckbuilder/references/card-review-method.md`, wired into
  SKILL.md and CLAUDE.md. Field % is a prior; the verified card text read against
  the deck's engine is the verdict. Born from Wizard's Staff: 4% field, but it
  DOUBLES the equipped creature's triggers — on Y'shtola that's drain-4/gain-4
  per big spell. The audit's first full pass walked all 705 two-week arrivals
  (124 unplaced rares/mythics card-by-card) and produced **19 verified swaps**
  across the six decks, every text checked against Scryfall/Gatherer via web
  search (API egress-blocked): Y'shtola took Wizard's Staff; Iron Man took
  Valeria Richards, Wizard's Staff #2 (on Archmage), Riddles in the Dark, Myriad
  Landscape; Cap took Mjölnir (doubles Cap's damage, equip worthy {1}),
  Captain Mar-Vell, Silver Sable; Cloud took Forge Anew (the buylist arrival —
  Hojo pulled as recorded), Inventory Management, Raubahn; Cosmic took
  Sensational Spider-Man, Web Up, Villainous Wrath (its first wipe); Ur-Dragon
  took Dragon Broodmother, Sylvia Brightspear, Kaalia, Deserted Beach. All are
  `Source=manual-replace` in `.changes.csv` (optimizer-protected — verified: all
  six re-previews say "already aligned"), documented in each `.notes.md`, and
  the verified-role cards were added to `mtglib.py`'s curated DRAW/REMOVAL/WIPES
  lists so the power score can read them (full test suite green after). Post-
  audit ranking on TYPED data (2026-08-12): Y'shtola 78 · Iron Man 72 · Cloud
  71 · Cap 69 · Cosmic 64 · Ur-Dragon 53 — the name-only scores had
  under-read Cloud/Cap/Cosmic by 10-13 points, and Ur-Dragon's
  interaction-for-threats trade (rebuild path in its notes) costs ~5 real
  points, not the 8 the name-only scorer showed. Benched-with-reasons and the Hobbit
  verdict (zero of 96 uniques beat an incumbent; Thorin/Thranduil/Gandalf/
  Radagast are future commander seeds) live in the audit notes sections.
- **Deep-research re-review of the sleeper audit (2026-08-11, 12-agent web
  sweep incl. YouTube/Reddit/deck-tech coverage): 18 of 19 swaps CONFIRMED with
  sources; 5 corrections applied** — Laboratory Maniac OUT of iron-man (TRAP:
  Demonic Consultation/Tainted Pact are color-illegal in mono-U and zero owned
  enablers; Falcon, Winged Wonder in, own 2); Vibrant Cityscape → Fabled
  Passage in cosmic (Cityscape is an Evolving Wilds clone, deck ran two
  already); Chaos Warp (0% here, own 6) → Lost in the Maze in cosmic (the only
  owned mass stun generator — Sensational fuel + post-alpha hexproof); Think
  Twice → Thor, Asgard's Avenger in team-leader (45% field, own 2, was in NO
  deck); Dragonhawk, Fate's Tempest REINSTATED in ur-dragon over Opportunity
  (the 8/11 optimizer cut was a 0%-field recency artifact; community rates it
  4.5/5 in dragon shells). Rules findings logged in each deck's notes: Kaalia-
  cheated creatures are never declared attackers (no Ur-Dragon draw, no attack
  triggers, incl. Ventmaw's mana); Broodmother tokens don't trigger Lathliss/
  Miirym; Mjölnir's discard mode is symmetric and only equips worthy; Mar-Vell's
  flash needs an opponent's spell first; Spider-Punk blanks our own counters and
  nonbos with Arachnogenesis's fog; Forge Anew equips your turn only; Raubahn
  attach resolves before Cloud's draw if stacked right; iron-man grants flying
  only to attacking MODIFIED creatures. Ur-Dragon interaction concern settled:
  field average is ~4-5 interaction slots, this deck keeps ~10. Stale buylist
  Replaces cells refreshed (yshtola x2, cloud x1). Bench queue in notes:
  Ur-Dragon's next wave (Atsushi, Ao, Hraesvelgr, Niv-Mizzet Visionary,
  Beledros, kicked Rite of Replication line), Cloud's Bloodforged Battle-Axe,
  Cap's Quicksilver/Jocasta/Dismantling Wave tier.
- **Commander candidates ranked (same sweep; owned-support grep-counted):**
  BUILD_NOW: **Helga, Skittish Seer** (Bant, EDHREC #67 — the one green
  commander whose engine matches this UB-heavy big-creature pool; ramp core
  owned) and near-BUILD_NOW **Hulk, Gamma Goliath** (22-card owned Hulk-orbit
  cluster + owned staples; RG identity checks needed at build time).
  BUILD_WITH_BUYS: **Thranduil, the Elvenking** (consensus best Hobbit
  commander, cEDH-article-worthy; ~$15-25 of bulk elf staples; Sultai NOT
  green; Sindarin Liege x2 is the auto-include second legendary Elf);
  **Kaalia of the Vast** (~$40-60 payload — big A/D/D + reanimation; do NOT
  dismantle ur-dragon, she stays in its 99 meanwhile); **Tifa Lockhart**
  (~$15-30; basics are free and untracked — grounding rule #9 — so the old
  "+ ~20 basic Forests" line here was never a real cost; the fetch-land instant-speed doubling core is
  already owned; sandbox auto_build saw her as colorless — enrich first);
  **Thorin, Mountain-king** (mono-R equipment voltron, NOT dwarf tribal; the
  good equipment is committed to cloud; buying Thorin King of Durin's Folk
  would unlock the owned Boros dwarf pool instead). SKIP: Selvala (zero
  engine pieces owned — her best home IS ur-dragon's 99), Gandalf Wandering
  Wizard (draft common, no engine), Radagast (no green fatty base yet),
  Sindarin Liege as helm, Vadmir/Neriv/Renet (not green — verified B/RWB/U).
- **Field-overlap validation post-sweep (fresh, larger snapshots): PASSED** —
  Team Leader 25/25 · Cloud 24/25 · Y'shtola 21/25 · Ur-Dragon 21/25 · Cosmic
  Spider-Man 18/25 · Iron Man 14/25. Iron Man and Spider-Man sit lower because
  their fields' top-25 are majority unowned Marvel cards (11 and 7 not owned) —
  above the ~50% revert threshold, gaps are buylisted, not silently shipped.
- Test suite: **480 passing**, offline and hermetic; CI runs Python 3.11 and 3.13.
- **Engine advisors** (PR #90, `docs/spec-engine-advisors.md`): the loader keeps the
  export's acquisition date; `deckcore.new_arrivals()` surfaces recently bought cards
  that are in no deck (Decks-page card, identity-matched to decks); `optimize()`
  reports **field risers** — owned cards the ≥25 anti-churn margin gate suppressed —
  in the CLI preview, `report["risers"]`, and the coaching packet. Both are strictly
  advisory: they never write. They exist because three good owned cards (Codsworth,
  Mana Drain, Smaug) sat unused while every deck reported "already aligned" — see
  open item 1.
- **Enrichment is production-aware** (engine-season workstream A): `collection_attrs.csv`
  now carries `Produced` (what a card actually taps for) and `Flags` (oracle-derived —
  `etb-tapped`/`-cond`, `rock`, `dork`, `ramp`, `draw`, `mana2`/`mana3`), derived by the
  new `scripts/oracle_flags.py`. Colored-source counts use real production where it exists
  and print "identity approx." where it doesn't. **The player's own attrs file is still the
  old 7-column shape until `enrich.bat` is re-run** — until then every manabase surface will
  correctly show the identity-approximation label. The one-time Scryfall-schema check of the
  `test_oracle_flags.py` fixture shapes is **DONE** (16/16 against the live API, 2026-08-10 —
  open item 5); the ~30-random-card flag audit after the first real enrichment run remains.
- **Role/category counts read those flags too** (engine-season follow-up A-F):
  `oracle_flags` also derives `removal` / `wipe` / `counter`, and `mtglib.classify()`
  consults `Card.flags` **only where its curated name lists are silent** — curated always
  wins, first-writer-wins, the same shape `deckcore.load_card_notes` uses. So a card from a
  set newer than the lists lands in the right bucket instead of the generic type bucket,
  and a hand-verified card can never be overruled by a regex. The mana-shape tokens
  (`etb-tapped`, `mana2`, `mana3`) map to no role — they are goldfish inputs. Proven on
  landing rather than assumed: the fixture deck's `deck_stats --json` categories are
  byte-identical without flags present (an unenriched collection has `flags == set()`, so
  the layer no-ops), and optimizer idempotency was re-run **with** flag-bearing attrs — the
  second pass proposes nothing. **Consequence to remember:** the flag audit in open item 5
  is now a category-count guard, not just a mana-model one.
- **The engine can goldfish** (engine-season workstream C): `scripts/goldfish.py` is a
  seeded, stdlib, offline Monte Carlo — shuffle, London mulligan, land drops, greedy
  casting — reporting P(commander by turn N), keepable / screw / flood **with their
  definitions printed beside them**, mean lands by turn, and which cards actually land
  late. It answers the *sequenced*-play questions `manabase.py`'s exact-but-unconditional
  hypergeometrics structurally cannot, and the two are deliberately shown side by side in
  the dashboard's Mana tab, on `/deck/<stem>/assess`, and in the coaching packet.
  `--ab "Out=In"` re-runs the identical shuffles with one card swapped (common random
  numbers) and prints paired confidence intervals. **On the current data the honesty gate
  fires on the name-only snapshot** — over 25% of nonlands have no mana value there, so
  the surfaces print the note instead of numbers; the server, running the enriched
  collection, gets real numbers, and they will jump from the fallback tier to the
  production-aware tier the first time `enrich.bat` is re-run. Everything goes through one
  cached entry point (`goldfish.sim_for_deck` → `data/cache/goldfish/`), so a page view
  after a deck edit costs one simulation across all three surfaces (~0.1–0.3s cold,
  a file read warm).
- **The skill delegates the heavy work** (engine-season workstream D): `.claude/agents/`
  now holds **card-verifier** (batched card-text verification) and **collection-auditor**
  (full-pool scans), both read-only `Bash, Read`; SKILL.md sends >~3 uncertain cards to the
  first and any full-pool scan to the second, doing the same work inline where no Agent
  tool exists. They are fed by `carddb.py --verify "<card name>"` — a new second mode that
  verifies *named* cards against Scryfall (batched, positionally reconciled, one fuzzy
  retry, 30-day cache in `data/cache/scryfall/`) and prints verbatim oracle text or an
  honest `UNVERIFIED`. Owner-machine follow-up: run `python3 scripts/carddb.py --verify
  "Sol Ring"` once on a networked machine — Scryfall is egress-blocked from the sandbox
  this landed in, so every test is monkeypatched and the live path is unproven.
- **Rules questions have a tool now** (engine-season workstream B): `scripts/rules.py`
  downloads WotC's Comprehensive Rules txt once into the gitignored `data/cache/rules/`,
  parses it, and answers by rule number (`rules.py 903.1` — subrules and section/chapter
  context included), by phrase (`--search`) or by glossary term (`--gloss`); refresh is
  manual (`--refresh`) and any cached copy is used with an honest `fetched <date>` label.
  `scripts/rulings.py "<card>"` adds Scryfall's per-card rulings (30-day cache, stale-okay
  when the network is down, resolved-vs-requested name always surfaced). The skill's
  `rules-reference.md` now leads with **"Ask the CR, don't recall it"** — retrieve → READ →
  cite, and on a degrade fall back to web search *and say the answer is uncited*.
  **Player's-PC feature:** magic.wizards.com is unreachable from the hosted server (not a
  documented public API) and from CI, which is also why there is no `/api/rules` route.
  Back-compat: this added two gitignored cache directories and touched no existing format.
  **Real-CR acceptance: DONE (2026-08-10, from a GitHub runner — the `live-checks`
  workflow on the `claude/live-network-checks` branch):** fetched and parsed the real CR —
  **3,161 rules, 739 glossary entries, effective August 7, 2026** — and answered 903.1 with
  the genuine text. The gate earned its keep: the live page turned out to carry a **literal
  space** in the CR href (`MagicCompRules 20260807.txt`) which the original `_RE_TXT_URL`'s
  `\s`-excluding class truncated at — `--refresh` reported "no link found" with the link in
  plain sight. Fixed (span the space, percent-encode before fetching) and pinned by a test
  against the real 2026 page shape.

## Performance & background work (`docs/spec-infra-hot-paths.md`, Phases 1–3 shipped 2026-08-14)

The app now runs engines inline per request, so three things were made cheap. Know
these before touching the analysis path:

- **`scripts/memo.py`** memoizes `mtglib.load_collection` and `deckcore.analyze_deck`
  on **file identity** (`(path, mtime_ns, size)` per input; `(path, None)` for a
  missing file, so creating it invalidates). A warm dashboard render of the-ur-dragon
  went 377 ms → 25 ms. **The cached values are SHARED — treat them as frozen.**
  `analyze_deck` copies only the outer dict; `coll`, `idx`, `enriched`, `report` and
  `assessment` are the same objects every caller holds. `tests/test_memo.py`
  fingerprints them across every consumer, and a real mutator injected into
  `build_dashboard` fails that test — if it ever fails, find the mutator, don't relax
  the assertion. Unfingerprintable inputs (a preloaded collection list,
  caller-supplied `refs`) bypass the cache by design. Every webapp write path calls
  `_invalidate(stem)`, and an `after_request` backstop drops the cache on any
  state-changing method.
- **`goldfish.ab_for_deck`** disk-caches the paired A/B behind the Replace flow's
  shift-click (and the CLI's `--ab`). Errors are never cached.
- **`webapp/enrich_bg.py`** runs post-upload Scryfall enrichment in a daemon thread —
  same pattern as `sync.py`, including the *interrupted* status a reload-killed thread
  gets instead of a permanent spinner. `carddb.write_attrs_csv` made the attrs write
  atomic for every caller.
- **`spellbook.FAIL_TTL`**: an unreachable Commander Spellbook used to cost a fresh
  network attempt on **every deck-page view** (315 ms measured, 25 s ceiling). A
  failure is now remembered for five minutes — never served as data.

## Mana intelligence (`docs/spec-mana-intelligence.md` — **Phases A–G ALL SHIPPED 2026-08-14**)

**The rollout legs are the only open items, and they are data, not code (H2):**

1. **Dispatch the attrs-snapshot Action** (workflow_dispatch button, or wait for
   Monday's cron) — regenerates the committed snapshot with v2 flags + FlagsVer.
2. **Re-enrich the server's private CSV** — a PythonAnywhere console
   `python3 scripts/carddb.py --collection data/collection/collection.csv`, or a
   fresh `/collection/upload`. **Leg 2 is not optional if leg 1 ran**: the stale
   private file's Flags column overwrites the snapshot's per card (the overlay
   trap the FlagsVer coupling rule guards — v1 flags then correctly read as v1).

Until both legs: every surface shows pre-vocabulary labels ("fetch census
unavailable — re-enrich to unlock"), numbers unchanged. After both: run H3's
acceptance — `manabase.py --deck data/decks/the-ur-dragon.txt --collection
data/collection/collection.csv` should show Wood Elves with 5 targets, Farseek
~10, a restricted bucket ≥3 (count what enrichment finds), and per-color sources
LOWER than the current 17/15/15/21/17 — then `carddb.py --audit-flags` and
eyeball ~30 rows. The goldfish REPORT_SCHEMA bump (2→3) means the first view of
each deck after deploy re-simulates once.

What shipped (details in the spec + commit messages):

Born from the player's ur-dragon question ("why Wood Elves with only 2 Forests?"
— the deck has 5 Forest cards, but nothing could say so). The spec was
adversarially verified by three lenses before implementation; Phase A is on the
branch:

- **Vocabulary v2** (`oracle_flags`): `fetch:land` / `fetch:basic` /
  `fetch:<type>` / `fetch:basic-<type>` / `mana-restricted`, read from the
  search CLAUSE — Demonic Tutor stays silent, Krosan Verge unions two types,
  Expedition Map fetches without being ramp. This fixed a live miss: the v1
  regex needs the literal word "land" and `"island"` doesn't match `\bland`, so
  Farseek / Nature's Lore / Wood Elves carried NO flags at all (Wood Elves not
  even `ramp`).
- **`FlagsVer`** (11th attrs column = `oracle_flags.VOCAB_VERSION`): flags and
  their version are ONE write — a Flags column arriving without FlagsVer resets
  the card to version 1. Mutation-proved against the real rollout window (v2
  snapshot under a stale private CSV must not read as verified-unrestricted).
- **Proven inert**: 0/2,621 cards change classify() roles, 0/6 decks change
  power/bracket/categories. v2 tokens map to no `FLAG_ROLES` entry on purpose.
- **B: the census + restricted split** — `manabase.fetch_census` ("Wood Elves:
  N targets in THIS deck"), spend-restricted lands out of the Karsten pool into
  their own bucket; pre-vocabulary data degrades to today's numbers + labels.
- **C: five surfaces** — dashboard Mana tab (= the app deck page), assess page,
  Build-Next, assess packet, manabase CLI; the card panel shows "Fetches: N
  legal target(s)" on the fetcher itself.
- **D: the standing Mana-health banner** — computed at render time from the
  memoized analysis, so every manual edit re-evaluates on the panel's own
  reload; ur-dragon shows "33 lands (floor 36)", the other five decks show
  nothing. `advise_card` adds a `mana_note` at add-time for thin/no-target
  fetchers.
- **E: the optimizer cannot strand a fetcher** — a running ledger across both
  land passes + the buy pairing (refusals reported as `land_guard`/CLI/⚡
  flash); basics repair is pip-proportional via the shared
  `deckcore.basics_by_demand` (round-robin gone); inert on pre-vocabulary data
  (all six real-deck previews byte-identical).
- **F: auto_build tie-breaks toward fetchable lands** (take-loop only — never
  in `assess_card`, whose score feeds the optimizer); basics can no longer leak
  into the nonbasic pass.
- **G: the goldfish admits fetch effects are unmodeled** (assumptions line
  naming the cards) — REPORT_SCHEMA 2→3.

## Open items

**0. Optimizer role-repair churn — FREEZE LIFTED 2026-08-14.** The acceptance
step is done: `optimize.py --all` ran as a preview against the **full private
CSV** from a PythonAnywhere Bash console. All six decks returned **"already
aligned with the field — no changes"** — zero swaps proposed anywhere, so an
`--apply` would have written nothing. Every `buy` line was field-superior
(Herald's Horn 83% over Visions of Beyond 0%, Curiosity 63% over Misdirection
13%, Tiamat 68% over Reconnaissance Mission 0%, …), and all six expected
`manual_holds` fired: Hojo, Vibrant Cityscape, Nature's Lore, Frantic Search,
Laboratory Maniac, Absorb. **`--apply` / ⚡ / `refresh --optimize` are cleared for
use.** The CLAUDE.md top-25-overlap check governs the first real `--apply`.

Phase 8's fixes are what got it there: the **field veto** (a swap may never cut a
card the field plays MORE than the incoming one) and an **archetype-aware role
template** (`role_ranges` reads the deck's `# Archetype:` header, so iron-man's
counter:15 is correct rather than nine over budget). Phase 12 added the fit
scorer reading THE same template, the role-point swing capped below the margin
(spread ×2 = 24 < 25, tripwire-tested), and the symmetric never-re-add rule.

**The run found three live bugs that no sandbox preview could have — keep this in
mind before trusting a snapshot-only result again:**

1. **The field veto guarded what the optimizer DID, not what it ADVISED.**
   cosmic-spider-man offered Sun-Spider (25%) and Spider-Man, To the Rescue (29%)
   as "1 pt short of auto-swap" over **Wall Crawl (41%)** — the exact card and
   inversion the original churn finding was about. The tool refused the swap, then
   recommended the player make it by hand. The riser gate now applies the same
   `inc_add >= inc_cut` comparison. One rule, both surfaces.
2. **The Cuts surface never protected manual adds.** `cut_candidates` passed the
   deck `.txt` to `deckcore.manual_adds` (which wants the `.changes.csv`) and
   iterated its list-of-rows as if it were a dict of names. Neither fault could
   raise, so the protected set was silently **always empty** and hand-picked cards
   were ranked with no "your call, not the tool's" flag. Note the second half:
   `cut_candidates`'s `stem` is a BASENAME for report labelling, so the companion
   path needs its own full-path stem or the lookup goes relative to cwd.
3. **The manual-adds advisory listed cards no longer in the deck.**
   `.changes.csv` is append-only, so y'shtola's Painful Truths — added and
   reverted the same day — was still printed under "the optimizer never cuts
   these", as "(no opinion — not resolvable in the collection)". Filtered to
   cards actually in the 99.

**0b. The original finding, for reference.**
`docs/spec-optimizer-hardening.md` (2026-08-12 section) has the full finding:
the first attrs snapshot armed the archetype-blind `ROLE_RANGE` template
(iron-man's typed counts read counter:15 vs max 6) and the repair path ignores
the ≥25-point field margin, so previews now propose cutting field-superior
deliberate keeps (e.g. Wall Crawl 41% → Masked Meower 18%). **Do not run
`--apply` / ⚡ / `refresh --optimize` until it lands.** Four decks carry
notes-file churn guards for the first-round victims; the pass moves to new
ones, so guards are a tourniquet, not the fix. Three fix directions are in the
spec. Concrete exhibit if anyone doubts castability matters: Mana Drain's
{U}{U} is on-curve castable ~35% in ur-dragon (manabase.py, typed) vs
effectively always in iron-man — the template wanted it moved anyway.

**1. Phase 1 network allowlist — the player's five-minute flip.**
`docs/spec-network-and-attrs.md` §2: five hosts, then the verification
checklist and the PC-only doc sweep (verified file:line list is in §2).
Nothing else depends on it; every future sandbox session benefits.

**2. Player physicals (unchanged, still worth doing):**
   - Upload the fresh Sorted export via `/collection/upload` — the SERVER's
     private CSV is still the pre-2026-08-11 one; sandboxes have typed data
     now, so the hosted app is the last stale surface.
   - ~6 spare basic Islands for iron-man (deck wants 29, export counts 23).

**3. Standing card-placement plans (owned-only, decided, waiting on arrivals):**
   - 2nd Mana Drain → yshtola, cutting **Misdirection** (the old plan said
     Absorb, which has since become Wizard's Staff). Field 27/20/15 across
     iron-man/ur-dragon/yshtola and the castability math keep copy #1 in
     iron-man.
   - 2nd Reliquary Tower → yshtola (46% field there; ~$3 — cheapest wishlist win).
   - Commander shortlist ranked and grounded (see the sweep bullet above):
     Helga and Hulk, Gamma Goliath are BUILD_NOW from owned cards whenever the
     player wants a seventh deck.

**4. Attrs-snapshot follow-ups (small, from the first live run):**
   - Retry split-name misses by FRONT FACE through the guarded fuzzy — the 17
     unmatched are all "Front // Back" names; the fold guard already compares
     front faces (`spec-network-and-attrs.md` §7).
   - The ~30-card flag audit (engine-season item below) got MORE load-bearing:
     flags now ship to every clone via the committed snapshot.

**1b. Placement principle (standing):** new arrivals → per-deck verdict →
place or dismiss, per the ratified sleeper audit
(`.claude/skills/mtg-deckbuilder/references/card-review-method.md`);
`deckcore.new_arrivals()` + `advise_card()` compute it, and with the attrs
snapshot live, `new_arrivals`' identity-matched `fits` now works in every
sandbox. The one-screen walk of that flow remains open
(`docs/spec-repo-hardening.md` Phase 4 item 1).
- **Cloud rebuild note:** cloud-ex-soldier is a protected voltron build
  (typed-data 71/100, B3, `.notes.md` names the engine and the 2026-08-12
  churn guards). Buy any of its four buylisted cards and `.buylist.csv`'s
  Replaces says what to pull (Forge Anew already arrived and was pulled in,
  2026-08-11).

1b-season. **The "Table-Ready" season SHIPPED COMPLETE (2026-08-13):
   `docs/spec-table-ready.md`.** Twelve phases from the competitive-landscape
   research plus player direction. Suite **507 → 602**, offline, exit 0;
   `scripts/` still stdlib-only.
   - **Phase 8** optimizer gate: archetype-aware `ROLE_RANGE` + a **field veto**
     (a swap may never cut a card the field plays more than the incoming one).
     See open item 0 — the freeze lifts on one live preview run.
   - **Phase 0** deck hygiene: all six decks regrouped on typed data (Y'shtola's
     misfiles and its split Plains pair fixed, `Unsorted` gone repo-wide,
     idempotent); the add AND Replace paths can no longer manufacture split
     basics; the server auto-regroups after a sync, skipping decks with
     in-section comments.
   - **Phase 1** a `Power` column through enrichment → `Card.power` → the clock.
   - **Phase 2 (flagship)** the **goldfish clock**: median turn this deck
     presents lethal, mapped onto the brackets' own turn anchors. Combat-only
     and labelled UNDERSTATED for drain decks; no clock at all without power
     data. `--ab` now reports clock deltas over the same paired games.
   - **Phase 3** `# Bracket:` header — your setting headlines, the detected
     verdict and reasons always stay visible. `recertify.yml` gained a Game
     Changers diff against Scryfall's `is:gamechanger` (the canonical list).
   - **Phase 4** the **Rule-0 table card** (`/deck/<stem>/table-card`): one
     phone/print screen — bracket, Game Changers, MLD/extra turns/combos, clock,
     game plan, with its source labelled.
   - **Phase 5** the **mulligan trainer** (`/deck/<stem>/mulligan`): real hands,
     your call first, then the sim's verdict; `goldfish.keep_verdict` is now the
     one shared rule. Stats in localStorage.
   - **Phase 6** **pins v2**: EDHREC/Build-Next label a card reserved elsewhere,
     `/pins` manages every reservation with one-tap move, conflict rows name the
     pin. (Found: `load_pins`/`save_pins` bound their path as a default arg, so
     tests wrote the REAL pins.csv — fixed.)
   - **Phase 7** **Mana-tab explainers** shipped as data from `manabase.analyze`,
     with the honesty caveats moved beside the numbers they qualify.
   - **Phase 9** the **cut surface** ("If You Must Cut"), ranked by the
     optimizer's own `deck_fit.card_value`; protected cards shown flagged, never
     hidden; writes nothing.
   - **Phase 10** **phantom disruption** (`--disruption standard`, EXPERIMENT):
     a wipe, periodic removal and commander tax on a SECOND RNG stream, so the
     A/A-exact-zero tripwire still reads 0.0. Off by default and byte-identical
     when off; CLI/assess only.
   - **Phase 11** gap sweep: Buy-tab rows are panel-clickable, shift-click a
     replacement candidate to simulate the swap first, `carddb --audit-flags`
     closes the standing flag-audit item, and **sw.js's cache version is derived
     from git HEAD** instead of hand-pinned.
   The 4-player pod simulator is specced and BACKLOGGED in
   `docs/spec-pod-simulation.md` (three tiers costed; Forge-on-a-runner is the
   cheap experiment if it is ever promoted).

1c. **Next-features research (2026-08-13): `docs/research-competitive-landscape.md`** —
   a six-agent competitive-landscape sweep (deck builders, the AI-tool wave, playtest/
   sim, brackets, collection tools, coaching/UX). Verdict: the app already holds the
   market's most-demanded positions (owned-only building, copy-conflict tracking,
   grounded AI, deck-aware math, optimizer restraint; `power.py` bracket rules confirmed
   current) — the ranked build list is §4 there: goldfish "clock" mapped to the official
   bracket turn anchors, a Rule-0 table card, declared-bracket compliance (advisory, with
   a Scryfall `game_changer` sync check), a game log feeding tuning, a mulligan trainer.
   Sequencing in §6; still gated behind open item 0 where optimizer-adjacent.

2. **Repo hardening (2026-08-11 review): `docs/spec-repo-hardening.md`** — a
   37-agent adversarially-verified sweep produced a three-phase fix tracker
   (safety bugs, data hygiene, front-face/webapp/cache correctness) and the
   ranked Phase-4 improvement roadmap. That spec is the live tracker; tick it
   there, not here.
2b. **Bracket-filtered field data (experiment, not started).** EDHREC publishes
   bracket-specific average decks; the owner builds toward Bracket 3, but snapshots
   use the all-brackets page. `json.edhrec.com` is egress-blocked from every sandbox
   path, so the probe must run **in a GitHub Action** (the `live-checks` pattern
   above proved this works): teach `edhrec.py --snapshot-all` to try bracket-variant
   endpoints and commit whatever answers. See `docs/spec-engine-advisors.md` §3.
3. **PAT renewal when due** (see GitHub token settings) and the quarterly
   keepalive click (above). Auth gate is ON (verified live); collection upload is
   DONE; ranking validation is DONE.
4. **Known UI gap:** dashboard Buy-tab rows for cards not in the deck are plain
   text, not panel-clickable (`docs/codemap.md`, "still open").
5. **Engine season: COMPLETE (2026-08-10).** `docs/spec-engine-upgrades.md` was
   ratified with four workstreams and one follow-up, and **all five PRs have landed** —
   A production-aware enrichment, C goldfish Monte Carlo, D subagents, B the
   Comprehensive Rules layer, and A-F `classify()` consuming the oracle flags (all
   described above). Nothing in that spec is outstanding. The four network-gated acceptance steps were
   run 2026-08-10 **from a GitHub Actions runner** — GitHub runners have the open
   egress the dev sandboxes lack (the codemap's deployment matrix now says so
   explicitly; blurring the two is the blind spot that parked these checks here in
   the first place). The harness is institutionalized as
   **`.github/workflows/recertify.yml`** (`workflow_dispatch` — one click re-certifies
   every live path after a new CR release, a new set, or a Scryfall schema change;
   its first full pass also ran `rulings.py` live and verified the ManaPool/Card
   Kingdom buy-link schemes 4/4). Three of the four steps are DONE:
   1. ☑ **Scryfall schema check of the A1 fixtures** — every `test_oracle_flags.py`
      fixture validated against real Scryfall JSON, 16/16 (produced sets, all flags
      including the A-F `removal`/`wipe`/`counter` tokens against real wordings, the
      MDFC schema shape, and Blasphemous Act confirmed as the documented wipe-regex miss).
   2. ☐ **~30-card flag audit after the first real `enrich.bat` run** — the ONE step
      that still needs the player's machine, because the private collection never leaves
      it. **More important since A-F landed:** flags feed `classify()`, so a wrong flag
      miscategorizes a card in every role count downstream (power, dashboard, optimizer
      role guardrails). The honesty labels fire when data is *absent*, never when a
      derived flag is *wrong* — this audit is the only guard for that case.
   3. ☑ **`carddb.py --verify "Sol Ring"` live** — found, verbatim `{T}: Add {C}{C}.`,
      commander-legal, via the real Scryfall API.
   4. ☑ **`rules.py --refresh` against the real CR** — 3,161 rules / 739 glossary
      entries parsed, effective August 7, 2026, 903.1 answered. This gate also caught a
      real bug (the literal-space href — see the rules-layer bullet above), fixed the
      same day.

## Session workflow reminders

- PRs are **squash-merged**; after every merge, rebuild the feature branch on
  `origin/main` before new work or the next PR conflicts.
- When a session materially changes a deck or ships a feature, update this file and
  tick `docs/spec-interactive-analytics-ai.md` if a tracked feature landed.
- The optimizer never touches manual edits; a second optimizer run on a tuned deck
  must change nothing (idempotence is tested).
