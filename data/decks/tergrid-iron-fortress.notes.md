# Tergrid — Iron Fortress (option 1 of 3)

**Study copy — not built from the collection.** Research build, 2026-10-11. Every card's
text was verified on GitHub runners (deck-verify runs 38138722782, 38139031278,
38139999873, 38140217987 and the attrs run). Field % = share of 12,840 Tergrid decks
on EDHREC (snapshot 2026-10-11).

## The commander (verified)

> Tergrid, God of Fright — {3}{B}{B} — Legendary Creature — God — 4/5
> Menace. Whenever an opponent sacrifices a nontoken permanent or discards a permanent
> card, you may put that card from a graveyard onto the battlefield under your control.

She is on WotC's **Game Changer** list, so every Tergrid deck starts in Bracket 3+.
This deck carries one more Game Changer (Opposition Agent), for two in total.

## The plan: make her the hardest thing at the table to answer

Three layers, in the order they matter:

1. **Strip their answers before she lands.** Duress, Thoughtseize, Dark Deal, Mindslicer,
   Necrogen Mists, Bottomless Pit, Liliana of the Veil and Opposition Agent all do this.
   Every permanent card they discard is already a Tergrid trigger waiting to happen.
2. **Cover the turn she enters.** Cavern of Souls (name *God*) makes her uncounterable.
   Defense Grid adds {3} to any spell cast outside its controller's turn. Then equip:
   - Commander's Plate: protection from white, blue, red and green.
   - Champion's Helm and Mask of Avacyn: hexproof.
   - Swiftfoot Boots: hexproof and haste.
   - Mithril Coat: has **flash** and attaches when it enters, making her indestructible
     in response to a wrath.
3. **Make removal not stick.** Return effects:
   - Kaya's Ghostform: covers exile as well as dying.
   - Unholy Indenture.
   - Demonic Gifts and Undying Evil: she returns **untapped**.
   - Feign Death, Not Dead After All and Malakir Rebirth: she returns tapped.
   - Imp's Mischief: redirects single-target removal onto their own creature.
   - Tyrite Sanctum: puts an indestructible counter on her.

## Finding the pieces
- **Tutors:** Diabolic Tutor, Profane Tutor and Cruel Tutor. Beseech the Mirror with
  bargain casts any found card costing 4 or less for free, including Mithril Coat,
  Commander's Plate or Swiftfoot Boots.
- **Urza's Saga:** chapter III puts Commander's Plate (or Sol Ring) straight onto the
  battlefield.
- **Recursion:** Myr Retriever returns a lost equipment when it dies. Codex Shredder
  returns any card, including the instants.

## Protecting you, not just her
- **Player hexproof:** Witchbane Orb.
- **Combat deterrents:** No Mercy destroys any creature that damages you. Crawlspace
  limits attacks on you to two creatures per combat. Darkness is a one-mana fog.
- **Shrinking their boards:** Phyrexian Obliterator punishes anyone who damages it.
  Archfiend of Depravity cuts every opponent to two creatures each turn, and Tergrid can
  take every nontoken creature they sacrifice.
- **Life:** Sangromancer gains 3 every time an opponent discards or loses a creature.

## Traps (all from the verified text)
- **Lightning Greaves is left out on purpose.** Shroud also blocks *your* auras, return
  spells and Mithril Coat's attach trigger. Hexproof only blocks opponents.
- **Undying Evil fails if she already has a +1/+1 counter.** Feign Death and Unholy
  Indenture both leave one, so use Demonic Gifts or Kaya's Ghostform on the second death.
- **Leave her card where it went.** If she goes to the command zone, the return effects
  can't find her *(rules point, uncited — the CR is unreachable from the runners)*.
- **Hold your edicts until she's on the battlefield.** Smallpox, Sheoldred's Edict and the
  rest steal nothing before she resolves. She only takes nontoken permanents, so prefer
  Accursed Marauder and Sheoldred's Edict's nontoken mode.

## Pilot
1. Turns 1–3: a rock or ritual, plus discard.
2. Turn 3–4: Tergrid, with Cavern mana and one black mana held for a return spell.
3. Equip Commander's Plate or Swiftfoot Boots immediately.
4. Then edicts, Smallpox and Liliana of the Veil.

**Mulligan** hands without black mana or a ramp piece.

## Optimizer review (2026-10-11, preview only — not applied)
`optimize.py` proposed **Geth's Verdict → Lightning Greaves** (54% field). Rejected: Greaves'
shroud blocks this deck's own Mithril Coat, Kaya's Ghostform, Unholy Indenture, Tyrite
Sanctum and return spells. **Geth's Verdict** stays as the instant-speed edict. It also
suggested buying Oppression over Damnation. Oppression is in option 3; this deck keeps
**Damnation** as its second wipe.

**Fixed the same day (oracle_flags v4, goldfish schema 5):** edicts now count as removal
(the dashboard shows 8 removal and 2 wipes; Interaction scores 15.0, up from 3.0). The
goldfish now models Dark Ritual, Cabal Ritual, Cabal Coffers, Cabal Stronghold, Nykthos,
Crypt Ghast, Urborg and Jet Medallion. Tergrid by turn 4 rose from 22% to 30%, by turn 5
from 50% to 57%, and the mean landing turn from 5.8 to 5.5.

## Card roles (every nonland card, for review)
- **Ramp:** Sol Ring, Arcane Signet, Jet Medallion, Mind Stone, Charcoal Diamond, Thought Vessel, Fellwar Stone, Dark Ritual, Cabal Ritual, Crypt Ghast
- **Protect Tergrid:** Swiftfoot Boots, Champion's Helm, Commander's Plate, Mithril Coat, Mask of Avacyn, Kaya's Ghostform, Unholy Indenture, Imp's Mischief, Demonic Gifts, Undying Evil, Feign Death, Not Dead After All, Malakir Rebirth, Defense Grid
- **Protect you:** Witchbane Orb, No Mercy, Crawlspace, Darkness, Sangromancer, Phyrexian Obliterator
- **Find / rebuy pieces:** Diabolic Tutor, Profane Tutor, Beseech the Mirror, Cruel Tutor, Codex Shredder, Myr Retriever
- **Discard (feeds Tergrid):** Waste Not, Dark Deal, Duress, Thoughtseize, Opposition Agent, Rankle, Master of Pranks, Burglar Rat, Elderfang Disciple, Mindslicer, Necrogen Mists, Bottomless Pit, Liliana of the Veil
- **Edicts (feed Tergrid):** Sheoldred's Edict, Liliana's Triumph, Accursed Marauder, Plaguecrafter, Smallpox, Mire in Misery, Vona's Hunger, Geth's Verdict, Archfiend of Depravity
- **Card draw:** Syphon Mind, Night's Whisper, Sign in Blood, Phyrexian Arena, Geth's Grimoire
- **Wipes:** Toxic Deluge, Damnation
