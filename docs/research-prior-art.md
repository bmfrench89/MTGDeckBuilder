# Prior Art — Collection-Grounded Commander Deckbuilders (research, 2026-08-09)

**Question:** do other repos exist that do what this project does? Are they doing it
better? What ideas are worth taking?

**Answer in one paragraph:** yes, a small ecosystem exists, and it validates this
project's design choices more than it threatens them. Nothing found combines this
repo's specific stack — collection-grounded building + coaching + deterministic
stdlib analytics + one code path serving CLI/web/skill + a $0 hosted PWA on a phone.
The closest neighbors each do ONE slice deeper (a trained per-commander model, a
smarter synergy metric, simulation feedback), and three concrete ideas are worth
adopting (§5).

---

## 1. Method (and its honesty constraints)

Per the player's instruction after the r/ClaudeAI "WebFetch is unreliable" thread:
**discovery and reading were kept separate.** Discovery used WebSearch; **all
substantive reading was `curl` of raw page text** (`raw.githubusercontent.com`
READMEs), quoted verbatim below — no fetch-and-summarize layer between the source
and this document.

- Queries run: `open source MTG commander deck builder collection-aware github` ·
  `github LLM AI commander deck builder EDHREC optimizer python` ·
  `"deck builder" mtg "from your collection" site:github.com stars`
- Fetched raw and read (9 repos): CyberBelligerent/MTGDeckBuilder ·
  flegars/mtg-deckbuilder · joliverson/mtg_deck_rec · KoalaTrapLord/commander-ai-lab ·
  DredBaron/OpenMTG · NikolayXHD/Mtgdb · nicho92/MtgDesktopCompanion ·
  reecevela/cardcognition · eboyden42/mtg-commander-ai
- **Blocked in this sandbox, disclosed rather than guessed:** GitHub's search API and
  per-repo metadata API are session-scoped away, so **star counts / last-push dates
  could not be verified** — popularity claims are deliberately absent below. Only
  README content (fetched verbatim) is cited.

---

## 2. The direct analogs

### CyberBelligerent/MTGDeckBuilder — the same mission, ML-first
> "Builds the best Commander deck from the cards you already own. Point it at your
> collection, pick a commander, and it uses machine learning trained on real
> community decks to recommend the strongest 99-card list from what you have."

Desktop Python GUI. Per commander it "scrapes 100 community decks … from
MTGGoldfish and trains a card-inclusion model on them," then "Score[s] every card
you own against the model," greedily fills toward target curve, and — notably —
"Use[s] NLP similarity search to find owned replacements for any missing cards."
Has **"Deck Targets" sliders** ("more creatures, lower curve, etc.", pre-fillable
from "community averages") and a **"collection coverage summary"** in the output.

*vs us:* same collection-first philosophy, heavier machinery (300 MB data download,
minutes of training per commander, Windows-exe distribution). Our `auto_build` is
deterministic and instant; theirs adapts to each commander's real meta. Their
sliders and coverage summary are borrowable ideas (§5).

### joliverson/mtg_deck_rec — our optimizer's closest cousin
> "Compare your Magic: The Gathering Commander deck against EDHREC recommendations.
> Paste a Moxfield deck URL, and get data-driven suggestions for cards to add,
> cards to cut, and AI-powered analysis."

Flask + EDHREC JSON, same pairing as ours. Two details matter:
1. Its thresholds are **user-tunable CLI flags** (`--add-threshold 0.30
   --cut-threshold 0.15`) where ours is a fixed ≥25-point rule.
2. It ships **exactly the feature the player just asked for**: "**Card
   Evaluation** — Evaluate candidate cards via image upload, file upload, or text
   input with **weighted scoring (synergy, inclusion rate, strategic fit, mana
   efficiency)**." That is independent validation of the add-card-advisor design in
   `docs/spec-add-card-advisor.md` — and our `deck_fit.assess_card()` already
   computes an equivalent component breakdown (color/role/curve/staple/theme).
3. Its web UI uses "**tabbed results**" — validation for the subtabs spec.

### flegars/mtg-deckbuilder — the philosophy twin (Electron + Claude)
> "AI where it adds value, not as a gimmick. Three focused workflows — Doctor,
> Suggestions, Synergy — that take the full deck context (commander, strategy
> notes, current 99, color identity, mana curve, known combos) and produce
> structured, explainable advice instead of vague 'this card is good' replies."

Local-first ("Everything lives in a local SQLite database. No account, no cloud
sync… You can use it on a plane"), Commander-first, Spellbook combo detection,
"Strategy notes attached to the deck … fed to the AI for every analysis." Its
**Deck Doctor** "flags weaknesses by severity (mana base, win conditions,
interaction, redundancy)" and **Synergy Analysis** "identifies anchor cards, and
surfaces **dead weight** (cards that don't synergise with anything else)."

*vs us:* strikingly convergent with this repo's design (notes-fed analysis =
our `.notes.md`; combo detection = our `spellbook.py`; local-first = our privacy
stance). Differences: BYOK Anthropic API with per-run cost display (ours uses the
skill on the subscription — our locked decision, still right); Electron desktop
(no phone story at all — we win there). **Dead-weight detection** is the one
analysis we don't have (§5).

### KoalaTrapLord/commander-ai-lab — the maximalist
> "Run thousands of simulated games, train neural networks on the outcomes, build
> decks with AI that learns from simulation data, get LLM-powered coaching, and
> play live 4-player battles — all from a single unified system."

Forge (rules-complete Java) + Monte Carlo engines, PPO training, ChromaDB RAG over
30k cards, Unity client. Its 7-step build pipeline "Filter[s] by color identity,
**collection**, and ban list," so it is collection-aware too.

*vs us:* different galaxy of scope and ops burden (JVM, Ollama, vector DB, GPU
training). Our spec explicitly locked "no playtesting/simulation of any kind" —
this repo is what the other side of that decision looks like. One line of theirs
worth stealing as a *principle*, since it mirrors our degrade-gracefully rule:
"Graceful fallback — RAG failures never block coaching or deck building."

---

## 3. Adjacent: collection managers (not builders)

- **DredBaron/OpenMTG** — "Self-hosted MTG card inventory server with multi-account
  support, collection tracking, deck building, statistics, wishlist, public
  Showroom display, card trading, loan tracking." Its **wishlist** tracks "current
  price, 90-day price history, and alerts when cards dip below target prices."
  Deck analysis is basic (CMC/curve/colors) — the building intelligence isn't there.
- **NikolayXHD/Mtgdb** and **nicho92/MtgDesktopCompanion** — mature desktop
  collection managers (search-scoped-to-collection, price providers). No Commander
  brain.
- **eboyden42/mtg-commander-ai** — natural-language deck *search* over ~2,000
  EDHREC decks via embeddings. Different problem.

## 4. Adjacent: a better synergy metric

**reecevela/cardcognition** computes synergy as a ratio, not a raw inclusion rate:
> "How many times more frequently is {selected card} included in a deck helmed by
> {specific commander}, compared to that card's rate of inclusion in commander
> decks of the exact same color identity?"

This controls for format staples: Sol Ring's 90% inclusion says nothing about
*this* commander, and a color-identity-baseline ratio filters that out. Our
optimizer's ≥25-point EDHREC-inclusion gain and `deck_fit`'s staple component both
use raw rates today.

---

## 5. What to adopt (ranked), and what to skip

> **⚠ Corrected 2026-08-09 after reading our own source.** The first version of this
> section recommended three things we had already built. Corrections are kept visible
> rather than quietly deleted, because "the field does X and we don't" was the whole
> claim being made. Verified against the code, not memory:
>
> - **Synergy vs. a baseline was NOT missing.** `deck_fit._staple_component` already
>   consumes EDHREC's `synergy_map` — defined exactly as cardcognition defines it
>   ("how much more THIS commander plays it than the format"), with the code's own
>   example being Command Tower at 93% inclusion but ~5 synergy. The original claim
>   that we "use raw rates today" was wrong for `deck_fit`.
> - **Tunable thresholds already exist**: `optimize.py` ships `--margin`,
>   `--buy-threshold` and `--max-swaps`.
> - **A collection-coverage summary already exists**: `pool_report` prints
>   "N in deck · N free to add · N in another deck · N not owned".

**Adopted — shipped:**
1. ☑ **Card-add advisor with component-scored verdicts** (joliverson's "Card
   Evaluation", flegars' structured Doctor output) — shipped in PR #72;
   `deckcore.advise_card()` over the existing `assess_card()` components.
2. ☑ **Dead-weight surfacing** (flegars: "cards that don't synergise with anything
   else") — `deck_fit.dead_weight()` + a "Pulling the Least Weight" section in the
   Power tab. Implementation note worth keeping: the first attempt used an absolute
   score cutoff and **never fired offline**, because with no EDHREC data an ordinary
   on-colour creature still scores in the 60s. It is now measured **relative to the
   deck's own median fit**, which behaves identically with and without field data.

**The one real remaining gap (needs live data to land safely):**
3. ☑ *(shipped in the hardening round — see `spec-optimizer-hardening.md` §C;
   live top-25 overlap check still owed)* **The optimizer's ADD ranking was
   popularity-only.** `optimize.py` sorts add
   candidates by raw EDHREC inclusion (`adds.sort()` on `inc`), while its CUT side
   uses `value_of = max(inc, (fit-60)*2)` — and `fit` already includes synergy. So the
   two halves disagree: a 93%-inclusion generic (Command Tower) outranks a
   77%/69-synergy archetype payoff (Dragon Tempest) as an add. Making adds use the
   same `value_of` the cuts use would make the optimizer internally consistent.
   **Not implemented, deliberately.** EDHREC is unreachable from the dev sandbox
   (403 at the egress proxy, empty cache), and CLAUDE.md requires validating a tuned
   deck against EDHREC top-25 overlap (~50% floor). Changing the ranking blind would
   be exactly the "ship quietly" the rule forbids. Land it from a machine that can
   reach EDHREC, with before/after overlap recorded.

**Consider later:** "deck targets" overrides for `auto_build`'s `ROLE_QUOTA`
(CyberBelligerent's sliders) — currently hardcoded at ramp 11 / draw 10 / removal 9 /
wipe 3 / counter 4, and safely testable offline since `test_auto_build` already
asserts exactly-100, colour legality and singleton. Price-dip alerts on the buylist
(OpenMTG) conflict with the locked "no live price feed" decision — estimates-only if ever.

**Skip deliberately:** simulation/ML training loops (commander-ai-lab) — re-affirms
an existing locked decision; per-commander scraped model training
(CyberBelligerent) — minutes-long builds and a scraping dependency against our
instant, deterministic, cache-friendly pipeline; Electron/desktop packaging
(flegars, Mtgdb) — our PWA already covers phone + desktop from one deploy.

## 6. Where we stand (validation)

Confirmed differentiators no analog matched: **hypergeometric manabase math** ·
**bracket/power scoring with a verified game-changers list** · **idempotent
optimizer with protection guardrails** (notes/curated cards never cut) · **one
`generate()` serving an editable app page and a self-contained offline dashboard
file** · **stdlib-only engine with CI enforcement and a 127-test hermetic suite** ·
**hosted PWA at $0 with the collection staying in flat files**. The field's common
stack (Flask/FastAPI + Scryfall + EDHREC + optional LLM) is exactly ours — the
architecture is normal; the grounding discipline and the deployment story are the
moat.
