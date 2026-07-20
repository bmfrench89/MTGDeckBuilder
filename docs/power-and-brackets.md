# Power & Bracket rubric (how `power.py` scores a deck)

Grounded in WotC's official **Commander Bracket system** (beta Feb 2025; updated
Oct 21 2025 and Feb 9 2026), cross-checked across the official articles + Scryfall
`is:gamechanger` + EDHREC / MTG Wiki / aggregators. Card lists live in
`data/reference/*.txt` and can be edited without touching code.

## Brackets (1–5)

The **number of "Game Changers"** a deck runs is the hard numeric lever; a few
gameplay "guardrails" do the rest. Tutors are **no longer** a bracket determinant
(removed Oct 2025 — the Game Changers list now flags the most efficient ones).

| Bracket | Name | Game Changers | Mass land denial | Extra turns | Early 2-card combo |
|--------|------|------|------|------|------|
| 1 | Exhibition | 0 | No | none | none — *and not trying to win* (intent) |
| 2 | Core | 0 | No | few, not chained | none |
| 3 | Upgraded | **up to 3** | No | few, not chained | only if late/expensive (~turn 6+) |
| 4 | Optimized | **4+ / unlimited** | Allowed | chainable | allowed, any turn |
| 5 | cEDH | unlimited | Allowed | chainable | allowed — *metagame-tuned* (intent) |

`power.py` classifier (deterministic from detectable signals):
- `4+ Game Changers`, **or** any mass-land-denial card, **or** `2+ extra-turn` spells → **Bracket 4**.
- `1–3 Game Changers` → **Bracket 3**.
- otherwise → **Bracket 2** (Core, the default).
- Bracket 1 (intent) and Bracket 5 (metagame intent) are never asserted from card
  names alone — they're flagged as "verify intent", because 1-vs-2 and 4-vs-5 are
  intent/metagame distinctions, not different card restrictions.
- `≥2` known combo pieces adds a **caveat** ("if these form a cheap early two-card
  combo, that's Bracket 4") rather than auto-reclassifying — name matching can't
  prove the pieces actually combo.

## Game Changers (53 cards, current as of 2026-02-09)

Full list in `data/reference/game_changers.txt`. The 2026-02-09 update added
**Farewell** and **Biorhythm**. **Mana Crypt** and **Jeweled Lotus** are *banned* in
Commander and are NOT Game Changers.

## Power score (0–100)

A finer estimate than the bracket, from countable qualities. Weights (sum ≈100):

| Component | Weight | Direction |
|---|---|---|
| Interaction density (removal + counters + wipes) | 16–18 | higher |
| Ramp | 13–15 | higher |
| Card advantage | 13–15 | higher |
| Average mana value / curve efficiency | ~14 | lower MV = higher power |
| Tutors | 11–12 | higher |
| Game Changers count | 10 | higher |
| Fast mana (Sol Ring excluded; net-positive only) | 8–9 | higher |
| Consistency (land-count fit, ~37) | 3–8 | contextual |

Tier labels: **Casual** (<32) · **Focused** (<55) · **Optimized** (<75) ·
**High / cEDH** (≥75). Board wipes are deliberately *not* treated as "more = stronger"
(heavy mass removal usually marks a slower, grindier casual deck). The score is a
guide, not a verdict — the real arbiter is the deck's fastest reliable, protected
win line.

## Caveats
- Curve/average-MV components need per-card mana values (a `<deck>.attrs.csv` or the
  attribute collection CSV); they renormalize out when MV is unavailable.
- All lists are name-matched, so they're only as complete as `data/reference/*.txt`.
  Update those files as WotC revises the Game Changers list.
