# Research — The Competitive Landscape & What Players Want (2026-08-13)

**Question:** if a Commander player were choosing between this app and everything else on
the market, what would they miss here — and what should be built next to make this the
definitive grounded AI deckbuilder?

**Method:** six parallel research agents (~120 web searches, ~30 full page reads where the
proxy allowed) across six angles: mainstream deck builders, the AI-builder wave,
playtesting/simulation, brackets/power tooling, collection-driven building, and
coaching/UX. **Honesty constraint:** the sandbox egress proxy blocked most direct page
fetches (reddit.com entirely), so much of the evidence is search-backend page extracts
rather than hand-read pages — quotes below are near-verbatim relayed text, and every
claim carries its URL. Reddit sentiment arrives secondhand (via feedback boards, essays,
and tools built in response to those threads). Findings that need a networked recheck are
flagged. Predecessor docs: `research-prior-art.md` (2026-08-09, GitHub repos only),
`research-roadmap.md` (2026-07-22, executed).

---

## 1. The verdict in one paragraph

The market split three ways — **Moxfield won deck building/sharing, ManaBox won mobile
collection scanning, EDHREC won data** — and no incumbent has unified them; a 2025–26
gold rush of collection-first AI challengers (Farseek, ManaTap, MTG Agents, KrakenTheMeta,
ScrollVault, Arcanis, GrimdDeck/BinderBrew/ManaForge…) is aiming at exactly that seam, and
none has community trust yet. The features players ask for most — build from what I own,
which deck is this copy in, honest bracket evidence, automated consistency numbers,
verified-card AI with visible reasoning — are, almost line for line, this repo's existing
design decisions. **The app is not behind the market; it is ahead of it on grounding and
analytics and behind it only on surfaces** — the engines exist but several of the
most-demanded experiences (a rule-0 packet, a mulligan trainer, a goldfish clock mapped
to the bracket turn-counts, a game log that feeds tuning) are one thin layer away.

## 2. Positions this app already holds that the market wants (validated, not to-do)

Each of these is a top-ranked demand in the research **and already shipped here**:

- **Owned-cards-only building with a priced buylist bridge.** The single most-demanded
  feature across ~8 independent sources; Moxfield's own board asks for a "My Collection"
  filter (moxfield.nolt.io/1467) and collection-filtered EDHREC recs (/988, /2095), and
  Archidekt's devs said server-side collection-aware recommendations are infeasible at
  their scale (archidekt.com/forum/thread/8339713) — the structural opening for a
  local-first tool. The market's winning framing is "owned-first plus a ranked buylist,"
  not a hard no-buy wall — exactly the `.buylist.csv` + `Replaces` contract.
- **Physical-copy conflict tracking across decks.** "Almost completely unserved by every
  tool surveyed": Moxfield users want an "amber check — you own it but every copy is in
  another deck" (moxfield.nolt.io/1433, /1027); Archidekt threads ask for used-in-deck
  filters and unassembled-deck exclusion (threads 20475798, 5220688). This repo's
  `deck_conflicts`, `pins.csv`, and ⇄ shared-copy badges are that feature.
- **Anti-hallucination grounding.** The #1 stated adoption blocker for AI builders —
  invented cards, 83-card "100-card" decks, color-identity violations (TappedOut's
  AI-builder challenge; Star City Games's brew tests; Farseek's whole content strategy).
  Every credible 2025–26 tool leads with "verified against Scryfall" — this repo's
  grounding rules, `carddb --verify`, and the card-verifier agent are that, enforced.
- **Deck-aware probability math.** Every hypergeometric calculator on the market is a
  generic K-of-N widget the player must frame; none auto-answers "can I cast my commander
  on curve" from the actual list. `manabase.py` + `goldfish.py` already do, seeded and
  offline — no surveyed tool (including the cEDH Rust simulator Krarkaplayer) ships
  common-random-numbers A/B.
- **Optimizer restraint.** No surveyed tool distinguishes deliberate player swaps from
  optimizer churn or promises idempotent tuning. The manual-edit protections and the
  ≥25-point margin gate are a genuine differentiator — invisible in marketing terms, but
  it is exactly the "respect my deck's spirit" complaint Moxfield's bracket auto-labels
  get (moxfield.nolt.io/1850).
- **Bracket rules currency.** `power.py` and `docs/power-and-brackets.md` already encode
  the Oct 21 2025 rework (tutors removed as a determinant, B2 detached from precons) and
  the Feb 9 2026 additions (Farewell, Biorhythm; 53 cards). Several shipped competitor
  calculators still count tutors — this repo is *more* current than part of the market.

**Implication:** the marketing story ("the definitive grounded AI deck builder") is
already true at the engine layer. What follows is the gap list.

## 3. The market map, compressed

- **Moxfield** — default builder; best editor + playtester; collection an afterthought
  (no scanning, no restrict-to-owned, no copy-availability); no official API; playtester
  requests pile up: AI opponent (nolt 1443, top playtest ask), PvP (1523), commander
  damage (1396), free mulligans. Bracket auto-labels resented (1850/1853): players want
  to *declare* a bracket and be *warned* about violations, not be assigned one.
- **Archidekt** — closest to collection-integrated building (owned-card filter to exact
  printing); EDHREC recs not collection-aware; playtester "clunky"; sync/data-loss bugs;
  shipped a deliberately-humble bracket estimator (refuses to output 1 or 5 — intent).
- **EDHREC** — the data moat (Moxfield/Archidekt decks feed it, which pulls users back);
  criticized for homogenizing ("average deck" builds); Salt Score is annoyance, not
  power; its only "AI" was an April Fools joke — the biggest data player has shipped none.
- **TappedOut** dying (one-man ops, outages); **Deckstats** frozen ~2021; **MTGGoldfish**
  builder vestigial (its premium SuperBrew does owned-cards deck finding).
- **AI wave (~18 tools, 2024–26)** — all market the same four trust levers: verified
  cards, visible reasoning, community-data-with-caveats, collection/budget respect.
  Essentially zero organic community discussion of any of them; the one organic thread
  found (EDHGen, mtgzone.com/post/7052) is skeptical: "does it give you any explanation
  for a card being included? Half the joy of the format is the puzzle." Academic datum:
  GPT-4o zero-shot is measurably weak at card evaluation (43% draft-pick accuracy,
  arXiv 2508.08382) — grounding isn't optional.
- **Playtest/sim** — solitaire playtesters are saturated and undifferentiated; the
  upvotes go to what's layered on top: automated keep-rates (ManaTap, EDHcheck's
  running-average-lands with thresholds), mulligan trainers with scoring
  (mtg-mulligan.com), phantom-opponent disruption (Playgroup.gg "Sparring": counters and
  wipes timed from real game data), and win tracking. **Nobody closes the loop from game
  results back to deck changes** — every tracker stops at dashboards.
- **Brackets/power** — at least seven competing calculators; the emerging standard is
  Commander Spellbook's `estimate-bracket` API (bracket tag + evidence: GC count, MLD,
  extra turns, per-combo bracket floors). Players' #1 ask: advisory labels with shown
  evidence. Sharpest unmet idea: since Oct 2025 the brackets are *defined by expected
  game length* (B2 ≈ T8+, B3 ≈ T6+, B4 ≈ T4+), yet **no tool measures what turn a deck
  actually presents a win — calculators still count cards.**
- **Collection tools** — scanning apps won entry (ManaBox de facto standard; accuracy on
  foils/reprints/odd frames is the complaint everywhere); the canonical pipeline is
  scanner → CSV → web builder, which this app's `/collection/upload` already terminates.

## 4. Ranked candidates — what to build next

Ranked by (demand evidence × fit to this app's identity × feasibility on the current
stack). Effort in this repo's usual sizing.

### 4.1 BUILD — the goldfish clock: "what turn does this deck present lethal?" (flagship, medium-large)
The official brackets are now *defined* by game-length expectations, and no tool on the
market measures it — they count cards. This repo owns the only seeded, deck-aware Monte
Carlo in the field; extending `goldfish.py` with an honest **damage-on-board clock**
(creatures cast → attack each turn → cumulative damage vs. 40-life opponents; commander
damage tracked; no blocks, stated as such) yields "median turn this deck goldfishes a
kill," mapped directly onto the B2/B3/B4 turn anchors beside the card-count bracket
estimate. Combined with `power.py` this is a bracket verdict grounded in *both* official
axes (contents + speed) — something literally no competitor has. Definitions ship as
data like screw/flood; the A/B CRN harness extends for free ("does this swap speed up
your clock?"). Honest limits: voltron/combo/alt-win decks need labeling (combo lines can
cite CSB data), and the no-interaction assumption is printed with the number.

### 4.2 BUILD — the Rule-0 packet: a one-screen "what my deck does" table card (small-medium)
Bracket 1's GC exception literally requires cards be "discussed pregame"; WotC frames the
bracket as a conversation aid; assessment tools are converging on evidence-first reports.
Nobody generates the artifact players actually need at the table. Everything it contains
already exists in engines: declared bracket + detected signals (`power.py` reasons), Game
Changers named, MLD/extra-turns disclosure, combos present + one-away (`spellbook.py`),
goldfish speed (4.1 makes it official-shaped), win conditions and game plan (`.notes.md`),
top synergy engine. One new route + a print-friendly, phone-showable render (the PWA is
already at the table for life tracking-adjacent use). This is the social/etiquette layer
no AI tool addresses.

### 4.3 BUILD — declared bracket + compliance check, not assignment (small)
The clearest UX finding in the bracket research (moxfield.nolt.io/1850/1853): the player
declares, the tool flags. Add an optional `# Bracket: 3` deck header; `power.py` gains
"declared vs. detected" — *"Declared Bracket 3: OK — 3/3 Game Changers, no MLD, no early
2-card combo; goldfish clock T7 vs. the ~T6+ expectation."* Violations are warnings with
evidence, never a relabel. Feeds 4.2 directly. Also: cross-check our bracket verdict
against CSB's `estimate-bracket` endpoint in the assess packet (client exists; one call),
and add a recertify.yml step diffing `game_changers.txt` against Scryfall's
`game_changer` field — the list revs on WotC's cadence and Scryfall syncs it
(machine-readable canonical source, confirmed).

### 4.4 BUILD — the game log that feeds tuning (medium)
The unoccupied space in the entire playtest/tracking market: "no evidence found of any
tool that closes the loop automatically — every product stops at dashboards." Flat-file
fit is perfect: `data/games.csv` (Date, Deck, Result, TurnEnded, Bracket-at-table,
StrandedCards, Notes) + a 30-second phone-friendly log form in the PWA + per-deck
win/loss and turn-length on the Decks page. The tuning leg: logged stranded cards become
a *prior* into `deck_fit.dead_weight()` and the optimizer's advisory output (never an
auto-cut — same advisory contract as risers). EDHRECast tracked a year of games in a
spreadsheet to get exactly this; Commander's Herald frames memory as the blocker. The
player's six physical decks make the loop real here in a way no mass tool can assume.

### 4.5 BUILD — mulligan trainer on the deck's real hands (medium)
A visible 2025–26 wave (mtg-mulligan.com's scored keep/mull with accuracy tracking,
ManaTap keep-rate sim, ScrollVault, PVDDR's quiz series) — and every one of them is
deck-generic or online-only. `goldfish.py` already compiles the deck, deals London
mulligans, and knows keepability; a webapp screen deals a real hand, takes keep/ship,
then shows the sim's verdict with the *why* (lands, color sources on curve, ramp
density, P(commander on time)) and tracks the player's agreement rate per deck. Offline,
grounded, uses the enriched mana model. Pairs naturally with the coaching skill's
pilot/mulligan guides.

### 4.6 EXPERIMENT — phantom disruption in the goldfish (medium, scope-gated)
The demand for "an opponent" is real (Moxfield's top playtest request at 32 upvotes) but
the evidence says players accept cheap approximations: Playgroup.gg's Sparring counters
spells and wipes boards on a timer; Krarkaplayer models the pod as inert 160 life. A
seeded disruption model (a wipe at ~T5–6, spot removal every N turns, tax on the
commander's recasts) slots into the existing turn loop and answers "how does my deck
rebuild?" — the question the pure goldfish structurally can't. This intersects the
standing tier-2 deferral (`research-simulation.md`): recommend a **small spike behind a
flag** (`--disruption standard`), definitions shipped as data, before any UI. If the
spike muddies the CRN A/B contract, stop there — the tripwire test decides.

### 4.7 SMALL — "what do I cut" as a first-class surface (small)
The single most-articulated coaching pain across the ecosystem (EDHREC/Card Kingdom/
MTGSalvation all run standing content on it; Farseek markets "help you make every cut").
The engines exist (`dead_weight`, fit-vs-median, optimizer preview's value ranking,
protected-cards awareness); what's missing is one view that answers it directly: a
ranked "if you must cut, start here" list with per-card evidence and the protections
honored. Mostly assembly; the coaching packet and Power tab get it for free.

### 4.8 SKIP — with reasons, so they read as decisions
- **Full pod/AI opponent simulation** — Forge's own wiki concedes its AI is weak; XMage
  carries a decade of multiplayer-AI pathologies; the tier-3 rejection stands. 4.6 is
  the scoped answer.
- **Scanning** — ManaBox → CSV → `/collection/upload` is the canonical pipeline already;
  building a scanner competes with the one tool that won its niche.
- **Social/sharing/community features, public API, Moxfield-import interop** — table
  stakes *for public multi-tenant tools*; this is a single-player app whose moat is the
  opposite (local, private, grounded). Revisit only if the app ever goes multi-user.
- **Live price feeds / upgrade-ROI math** — re-affirmed: buy-links + labeled estimates
  (decided 2026-07-22; nothing in the research overturns it — EchoMTG owns that niche).
- **Embedded LLM API in the webapp** — re-affirmed; the AI layer stays the skill on the
  subscription. The research adds a reason: base-LLM card judgment is quantifiably weak
  (arXiv 2508.08382), so the grounded-skill architecture is the defensible one.

## 5. Corrections & confirmations for internal docs

- **`power.py` bracket logic: CONFIRMED current** (Oct 2025 + Feb 2026 rules). No fix
  needed — several shipped competitors are staler than we are.
- **Game Changers machine-readable source: RESOLVED** (open question in
  `research-roadmap.md` and `spec-interactive-analytics-ai.md` §5): Scryfall's
  `game_changer` boolean / `is:gamechanger` search is the canonical syncable list;
  CSB's `estimate-bracket` is the machine-readable bracket *ruleset*. Action in 4.3.
- **EDHREC "Lift":** the formula article exists
  (edhrec.com/articles/from-synergy-to-lift-the-math-behind-edhrecs-new-era) —
  fetchable from a GitHub runner; the §5 open question can be closed by a recertify-style
  read, not more searching. **[Needs a networked session.]**
- **Bracket-count arithmetic gap [UNVERIFIED]:** the researched WotC changelog
  (40 + 18 − 2 − 10 + 2) doesn't sum to 53, so the Oct 2025 update likely also added
  cards the extracts didn't name. Doesn't matter for the app (the 53-card list itself is
  verified); matters only if we ever document list history. Resolve via Scryfall diff
  in the 4.3 recertify step.

## 6. Suggested sequencing

The optimizer role-repair churn (`spec-optimizer-hardening.md`, handoff open item 0)
remains **the** blocking engineering item before any optimizer-adjacent work. After it:

1. **4.3** declared-bracket compliance + GC sync check (small; unlocks the packet's
   framing) →
2. **4.1** goldfish clock (the flagship; its number feeds everything) →
3. **4.2** Rule-0 packet (assembles 4.1 + 4.3 + existing engines into the visible win) →
4. **4.4** game log, **4.5** mulligan trainer (independent; either order) →
5. **4.7** cut surface alongside any of the above; **4.6** as a gated spike when the
   simulation appetite returns.

Items 4.1–4.3 together produce something no competitor has: a bracket verdict grounded
in both official axes with the evidence shown, rendered as the artifact players actually
use at a table.
