# Bruce Banner // The Incredible Hulk — "Don't Make Him Angry"

## The card (verified 2026-08-14)

Scryfall and EDHREC are both egress-blocked from this sandbox, so `carddb.py --verify`
returned UNVERIFIED. The text below is taken from the **player's own photographs of the
card** (grounding rule #6 — a photo outranks memory and search) and was corroborated by
two independent web sources for the one detail the photos did not show: the front face's
mana cost.

- **Bruce Banner** — `{U}` — Legendary Creature — Human Scientist Hero — **1/1**
  - `{X}{X}, {T}: Draw X cards. Activate only as a sorcery.`
  - `{2}{R}{R}{G}{G}: Transform Bruce Banner. Activate only as a sorcery.`
- **The Incredible Hulk** — Legendary Creature — Gamma Berserker Hero — **8/8**
  - Reach, trample
  - *Enrage* — Whenever The Incredible Hulk is dealt damage, put a +1/+1 counter on him.
    If he's attacking, untap him and there is an additional combat phase after this phase.

**Color identity is Temur (U/R/G), not Gruul.** The `{2}{R}{R}{G}{G}` on the card face is
the *transform* cost; Bruce himself costs a single blue mana. Getting this wrong would have
built the deck in the wrong two colours.

## Game plan

1. **Turn 1–2: play Bruce.** He costs `{U}`. He is not a threat — he is a mana sink that
   draws cards (`{X}{X}, {T}: Draw X`) while the deck ramps. Six mana draws three.
2. **Turn 4–6: flip him.** `{2}{R}{R}{G}{G}` is six mana and it is sorcery-speed, so the
   ramp package exists to make that happen on schedule, not to be greedy.
3. **Attack, then make him angry.** An 8/8 reach trample is a real clock on its own. The
   deck's job is to deal damage *to your own Hulk while he is attacking* — every point
   untaps him and hands you another combat phase, and the +1/+1 counters mean he only
   gets bigger each time.

**The timing rule that matters:** the extra combat only happens if he is **attacking** when
the damage is dealt. A sorcery-speed fight in your first main phase gives you the +1/+1
counter and nothing else. Ping him **during combat**, after attackers are declared.

## Engine pieces (do not cut)

- **Prodigal Sorcerer** and **Thornwind Faeries** — the two classic "Tims". `{T}: 1 damage
  to any target`, pointed at your own Hulk mid-combat. One extra combat per turn, each.
- **Brash Taunter** — the best one in the deck. `{2}{R}, {T}: fights another target
  creature.` Fight your own Hulk: Hulk takes 1 (Taunter is a 1/1) and hands you a combat
  phase, the Taunter takes 8 and — being indestructible — survives and throws that 8
  straight at an opponent's face. Repeatable every turn.
- **Roaming Throne** — name **Hero** as it enters. Enrage is a triggered ability, so it
  triggers *twice*: two +1/+1 counters and **two** extra combat phases per ping.
- **Godo, Bandit Warlord** — an extra combat every turn he attacks, no damage required,
  plus he tutors an Equipment straight onto the battlefield.
- **Savage Ventmaw** — attacking adds `{R}{R}{R}{G}{G}{G}`. With extra combats it pays for
  the flip, the pings and the protection in the same turn.
- **Fiery Emancipation** — triples all damage you deal. An 8/8 trampler becomes 24.
- **World War Hulk** — chapter II puts three +1/+1 counters on him, chapter III doubles his
  power and toughness. The finisher.
- **Coastal Piracy**, **Laelia, the Blade Reforged**, **Ohran Frostfang**, **Sword of the
  Animist** — every one of these triggers *per combat*, so extra combats compound them.

## Two deliberate exclusions (both are traps here)

- **Lightning Greaves is NOT in this deck**, despite being a Commander staple and despite
  the player owning three. It grants **shroud** — you could no longer target your own Hulk
  with your own pings, which switches the engine off. **Swiftfoot Boots** and **Champion's
  Helm** grant *hexproof* instead: opponents can't touch him, you still can. That
  distinction is the whole reason those two cards are here and Greaves is not.
- **Basilisk Collar is NOT in this deck.** Deathtouch on a Tim means your own 1-damage ping
  destroys your own commander. If it ever gets added, it goes on the Hulk, never on a pinger.
- Board wipes are deliberately small — **Pyroclasm** and **Fiery Confluence** kill the
  utility creatures and blockers while *pinging your own Hulk for a counter*. **Blasphemous
  Act** was considered and rejected: 13 damage kills your own 8/8 commander, and this deck
  is one creature deep.

## Piloting and mulligans

- Keep any hand with 2–5 lands and either a green ramp spell or a mana rock. You are trying
  to hit six mana on turn five; a hand with no acceleration is a slow hand.
- Bruce is safe to deploy on turn one against most tables — he is a 1/1 nobody wants to
  spend removal on, and he starts drawing you cards immediately.
- Do **not** flip him into an open red or white mana with no protection up. He is your whole
  deck. Hold Heroic Intervention / Snakeskin Veil, or flip him with Swiftfoot Boots already
  on the battlefield.
- Sequence your combat like this: declare Hulk as an attacker → let blocks happen (a blocker
  damaging him is a *free* extra combat) → *then* ping him with Shock / a Tim / Brash Taunter
  → new combat phase → repeat with your next damage source.
- Green is the tightest colour in the manabase (32.5 pips of demand against 19 sources).
  Nature's Lore, Wood Elves, Rampant Growth and Crop Rotation are the fixers — lead with
  them when the hand is green-light.

## Bracket

**Bracket 3 (Upgraded), power 71/100** by `power.py`. One Game Changer — **Crop Rotation** —
which is inside Bracket 3's cap of three. There is no infinite combo in the 99: the three
pingers all tap, so each is worth one extra combat per turn (two with Roaming Throne out).

`combo_detector.py` flags that **Godo + Helm of the Host is infinite combats**, and Helm of
the Host is **not owned**. If it is ever bought, this deck stops being Bracket 3 — that is a
deliberate line not to cross, not an oversight.

## Physical copies

Built almost entirely from the **uncommitted** pool so that nothing has to be pulled out of
the player's own six decks — this is a gift deck that should sleeve up standalone. The
commander itself is the brother's card and is not in the player's collection, which is why
`deck_stats.py` reports one card "not owned"; that is correct and expected.
