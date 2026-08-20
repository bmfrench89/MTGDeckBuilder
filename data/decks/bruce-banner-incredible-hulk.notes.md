# Bruce Banner // The Incredible Hulk — "Don't Make Him Angry"

## The card (VERIFIED against Scryfall 2026-08-14, MSH 49)

Scryfall and EDHREC are both egress-blocked from the build sandbox, so `carddb.py --verify`
returned UNVERIFIED there. The check was run instead on a GitHub runner
(`.github/workflows/deck-verify.yml`), which has real internet. Verbatim result:

```
Bruce Banner // The Incredible Hulk  {U} // {2}{R}{R}{G}{G}
Legendary Creature — Human Scientist Hero // Legendary Creature — Gamma Berserker Hero
identity: G R U · commander-legal: yes · MSH 49
| {X}{X}, {T}: Draw X cards. Activate only as a sorcery.
| {2}{R}{R}{G}{G}: Transform Bruce Banner. Activate only as a sorcery. // Reach, trample
| Enrage — Whenever The Incredible Hulk is dealt damage, put a +1/+1 counter on him.
  If he's attacking, untap him and there is an additional combat phase after this phase.
```

This matches the player's photographs of both faces exactly, and settles the one detail the
photos could not show — the front face's mana cost was hidden behind EDHREC's "+" overlay in
both shots.

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
- **Shang-Chi, Master of Kung Fu** — replaced Roaming Throne (2026-08-20): the one copy
  is pinned to the Ur-Dragon deck. Shang-Chi is on-engine here — you may activate
  creature abilities as though they had haste, so a pinger cast this turn pings the
  Hulk this turn, and his `{T}: add two mana of any one color, creature abilities only`
  pays for Brash Taunter's `{2}{R}` fight.
- **Godo, Bandit Warlord** — an extra combat every turn he attacks, no damage required,
  plus he tutors an Equipment straight onto the battlefield.
- **Savage Ventmaw** — attacking adds `{R}{R}{R}{G}{G}{G}`. With extra combats it pays for
  the flip, the pings and the protection in the same turn.
- **Fiery Emancipation** — triples all damage you deal. An 8/8 trampler becomes 24.
- **World War Hulk** — chapter II puts three +1/+1 counters on him, chapter III doubles his
  power and toughness. The finisher.
- **Barbed Field** — enchant a land; that land gains "{T}: deals 1 damage to any target."
  A *free*, repeatable, instant-speed ping that needs no creature and dodges creature
  removal entirely. Four mana once, then a ping every combat forever.
- **Goblin Medics** — "whenever this creature becomes tapped, it deals 1 damage to any
  target." Declaring it as an attacker taps it, which pings the Hulk *while he is
  attacking* — a free extra combat every turn just for attacking alongside him.
- **Hard-Won Jitte** — double strike for {1}{R}, equip {2}. An 8/8 trampler hits for 16;
  with Fiery Emancipation out, 48.
- **Red Hulk** — verified Enrage: "put a +1/+1 counter on him. When you do, he deals damage
  equal to the number of +1/+1 counters on him **to any other target**." He is a *relay*,
  not just a body: ping Red Hulk, and he converts it into a much larger point of damage
  which you aim at The Incredible Hulk for the extra combat.
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
- **Warmonger is out, and it was close.** Verified text: "{2}: This creature deals 1 damage
  to each creature without flying and each player. **Any player may activate this ability.**"
  The Hulk has reach, not flying, so it *does* hit him — a repeatable extra combat for {2},
  which is exactly what this deck wants. It was rejected for two reasons: it kills our own
  Prodigal Sorcerer and mana dorks, and "any player may activate" hands every opponent at
  the table a repeatable machine gun for the rest of the game. The player owns three; if he
  wants the faster engine and accepts the symmetry, this is the first card to try.
- **Squallmonger looks like the same card and is not.** Its version reads "each creature
  **with** flying" — the Hulk has reach, so Squallmonger misses him completely. Verified,
  and the reason it is not in here.
- **Hulkbuster Armor is an anti-synergy trap.** It sets base power/toughness to 9/9 (only
  +1 over an 8/8) and grants **flying** — which would make the Hulk *dodge* the sweeper-style
  pings that this deck relies on. Owned, verified, deliberately excluded.

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

## Validated against the field (2026-08-14, real EDHREC data)

`data/reference/field/bruce-banner.json` was fetched on a GitHub runner, so the field checks
finally ran. **Top-25 overlap: 13/25 = 52%**, above the ~50% floor that means something is
wrong. Independent confirmations worth knowing:

- The field plays **Swiftfoot Boots at 53% and does not run Lightning Greaves in its top 30
  at all.** That is the shroud-vs-hexproof argument above, arrived at independently.
- **Caltrops is the field's most-played nonland card at 68%** — i.e. the field builds this
  commander as an *infinite-combat* deck. That is the single clearest signal that Bracket 3
  is a deliberate choice here, not an accident of collection depth.
- **Moonmist (58%)** is the tech this collection is missing: `{1}{G}`, transforms all
  Humans, and Bruce Banner is a **Human** Scientist Hero — so it flips him for two mana
  instead of six, at instant speed. Top of the buy list.
- World War Hulk (56%), Red Hulk (54%), Heroic Intervention (61%), Rhythm of the Wild (46%)
  and HULK SMASH! (44%) were all picked here before the field data existed.

**`optimize.py` was deliberately NOT applied.** With real field data it proposed cutting
**Barbed Field** — a verified engine piece — for **Blasphemous Act**, which deals 13 damage
to each creature and kills our own 8/8 commander in a deck that is one creature deep. It
also proposed Counterspell and Rhystic Study, both of which are `[shared]`: they would pull
physical copies out of the player's own decks, which defeats the point of a gift deck. The
engine pieces are named in this file precisely so a future optimizer run leaves them alone.

## Bracket

**Bracket 3 (Upgraded), power 71/100** by `power.py`. One Game Changer — **Crop Rotation** —
which is inside Bracket 3's cap of three. There is no infinite combo in the 99: the three
pingers all tap, so each is worth one extra combat per turn.

`combo_detector.py` flags that **Godo + Helm of the Host is infinite combats**, and Helm of
the Host is **not owned**. If it is ever bought, this deck stops being Bracket 3 — that is a
deliberate line not to cross, not an oversight.

## Physical copies

Built almost entirely from the **uncommitted** pool so that nothing has to be pulled out of
the player's own six decks — this is a gift deck that should sleeve up standalone. The
commander itself is the brother's card and is not in the player's collection, which is why
`deck_stats.py` reports one card "not owned"; that is correct and expected.

## Ownership: the commander is the BROTHER'S card (player-confirmed 2026-08-15)
`Bruce Banner // The Incredible Hulk` is in NO collection export — old or new — and is
deliberately absent from `owned_additions.txt`. That is correct and must stay that way:
the player is **building this deck for his brother, who owns the commander**. The `BUY`
badge on the commander tile is therefore RIGHT, not a data bug.

Do not "fix" it by adding the card to `owned_additions.txt` — that file means *the
player* owns it and the export missed it (grounding rule #6), which is not the case
here. A future session that re-notices the badge should read this paragraph and stop.
The other 99 are the player's own cards and are checked against his collection normally.
