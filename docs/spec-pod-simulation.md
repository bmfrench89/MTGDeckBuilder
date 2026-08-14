# Spec — 4-Player Pod Simulation

**Status: ⊘ BACKLOG — player decision 2026-08-13** ("I also like the 4 player ai
simulator but that seems like a massive undertaking. let's create a spec for it but
backlog it for now"). **No phase of this spec is scheduled.** It exists so the idea has
a shape, an honest cost estimate, and promotion criteria — instead of resurfacing every
few months as a vague "what about opponents?".

**Prior scope decisions this spec must respect** (`research-simulation.md`, ratified
2026-08-10): tier-1 goldfishing is in scope (shipped — `goldfish.py`); tier-2 scripted
opponents were **deferred**; tier-3 full game simulation was **rejected**. The
Table-Ready season's Phase 10 (phantom disruption) is the narrow tier-2 probe. This
spec describes what lies beyond it, and why the full version stays parked.

---

## 1. What "4-player AI simulation" would actually mean — three tiers, honestly costed

### Tier A — Statistical pod (the ceiling of the current architecture) · weeks
Extend `goldfish.py`'s model: three opponents as *statistical processes*, not agents —
each with a clock (damage-per-turn curve drawn from field-data archetype averages), a
disruption budget (counterspells/removal/wipes per game, timed like Phase 10's
schedule), and a threat-response bias (the sim's board draws removal proportional to
its clock). Your deck is still the only one actually piloted.

- **Answers:** "does my deck win the race?", "how does my clock hold up under
  realistic pressure?", "which build survives a wipe better?" — with CRN A/B intact.
- **Doesn't answer:** politics, targeting choices, combo-vs-combo races, anything
  requiring opponents to hold real cards.
- **Feasible in-repo:** stdlib, seeded, honest-labels; the natural v2 of Phase 10 if
  its v1 earns its keep. This is the cEDH community's own compromise (Krarkaplayer
  models the pod as inert 160 life; Playgroup.gg's phantom opponents are timers, not
  minds).

### Tier B — Scripted-policy agents on a simplified rules subset · months
Four real decklists, each piloted by a hand-written policy (play land, ramp, cast
biggest castable, attack lowest life, hold interaction for X) over a simplified rules
engine (no stack nuance, no triggers beyond a whitelist, no replacement effects).

- **The honest problem:** Magic's rules complexity is the whole cost. Every card in
  the 100 needs either a hand-written behavior or a "vanilla" fallback that silently
  misplays it — and a simulator that misplays most cards produces *plausible-looking
  win rates that mean nothing*. That failure mode (numbers that look like data but
  aren't) is exactly what this project's grounding rules exist to prevent.
- **Verdict:** not buildable to this repo's honesty standard at hobby scale. Parked.

### Tier C — Full rules engine · rejected (unchanged)
Forge is 20+ years of work and its own wiki concedes the AI "can be easy to overcome"
and is "pretty bad for most combo decks"; XMage carries a decade of open multiplayer-AI
pathologies (threat assessment, targeting). Re-implementing is out of the question;
embedding is impossible (`scripts/` is stdlib-only) — which leaves…

### Tier C′ — Forge-as-external-oracle, on a GitHub runner · the one cheap experiment
Runners have open egress and can run Java. `forge.exe sim -d d1 d2 d3 d4 -f Commander
-n N` plays full-rules 4-deck pods headlessly. A `workflow_dispatch` Action (the
`recertify.yml` pattern) could export the player's six decks, run an all-pairs pod
tournament, and commit a small JSON of results to `data/reference/` — surfaced as
labeled, low-confidence evidence ("Forge AI, known-weak pilot, N games").

- **Costs:** deck-format conversion; card-support gaps in Forge (Universes Beyond
  coverage must be checked — Marvel/FF sets may not be scripted); the AI pilots all
  four decks badly *symmetrically*, which is the one thing that keeps relative results
  meaningful-ish.
- **This, not Tier B, is the first thing to try if the backlog ever unfreezes** —
  zero code in `scripts/`, zero rules-engine work, results arrive as a committed
  reference artifact like field snapshots do.

## 2. Promotion criteria — what would un-backlog this

Promote (Tier A or C′ first) only when **all** of:
1. Table-Ready Phase 10 shipped and the player actually uses `--disruption` output
   (an unused experiment doesn't earn a sequel);
2. the goldfish clock (Phase 2) proved its bracket-anchor mapping useful in practice;
3. a concrete decision the player faces needs pod-level evidence that the statistical
   tiers can't fake (e.g. "which of two decks should I bring to a specific pod");
4. for C′: a spot-check confirms Forge scripts the six decks' cards (especially
   Marvel/FF Universes Beyond) at acceptable coverage.

## 3. If promoted — v1 shape (Tier A sketch, to be re-specced then)

- Opponent processes parameterized from committed field snapshots (archetype →
  clock/disruption profiles), definitions shipped as data, assumptions printed.
- One new report block beside the goldfish clock: win-race % vs. three profile
  opponents, with CI; CRN preserved (opponent streams seeded independently, same
  pattern as Phase 10's second RNG).
- Same cached entry point (`sim_for_deck` parameters), same honesty gates, no new
  dependencies, no UI until the CLI output earns it.

## 4. What this spec deliberately does not promise

No politics, no bluffing, no rules Q&A from simulation, no "your deck wins 43% of
pods" as a headline number — any surfaced figure carries its tier's label and caveat
inline, per the grounding rules. The moment a number here would read as authoritative
without being defensible, the feature is out of spec.
