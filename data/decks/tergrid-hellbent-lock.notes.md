# Tergrid — Hellbent Lock (option 3 of 3)

**Study copy — not built from the collection.** Research build, 2026-10-11. Every card's
text was verified on GitHub runners (deck-verify runs 38138722782, 38139031278,
38139999873, 38140217987 and the attrs run). Field % = share of 12,840 Tergrid decks
on EDHREC (snapshot 2026-10-11).

## The commander (verified)

> Tergrid, God of Fright — {3}{B}{B} — Legendary Creature — God — 4/5
> Menace. Whenever an opponent sacrifices a nontoken permanent or discards a permanent
> card, you may put that card from a graveyard onto the battlefield under your control.

She is a **Game Changer**, and the only one in this deck (Bracket 3).

## The plan: the deck most Tergrid players actually run

Empty every hand, punish the empty hand, and keep every permanent card they drop.

**Repeating discard, with field %:**
- Waste Not (77%)
- Oppression (61%)
- Rankle, Master of Pranks (67%)
- Burglar Rat (57%)
- Elderfang Disciple (56%)
- Liliana of the Veil (53%)
- Mindslicer (45%)
- Virus Beetle (45%)
- Bottomless Pit (42%)
- The Raven Man (39%)
- Necrogen Mists (32%)
- Tourach, Dread Cantor (31%)
- Tinybones, Trinket Thief (31%)

**One-shot discard:** Dark Deal (71%), Duress, Thoughtseize, Hymn to Tourach, Mind Twist.

**Punishing empty hands:**
- Painful Quandary (50%)
- Megrim and Liliana's Caress (each discard costs them 2 life)
- Torment of Hailfire (45%)
- Vicious Rumors (41%)
- Gray Merchant and Sangromancer to drain and gain

**The Pox family** (Smallpox 72%, Pox, Pox Plague) makes everyone discard and sacrifice
creatures and lands at once. Each nontoken permanent an opponent loses can come to you.

## Protection (lean, because their hands are empty)
- **Equipment:** Swiftfoot Boots, Champion's Helm, Mithril Coat.
- **Return effects:** Kaya's Ghostform, Demonic Gifts, Undying Malice, Malakir Rebirth.
- **Redirect:** Imp's Mischief.
- **Lands:** Cavern of Souls and Tyrite Sanctum.
- **You:** Witchbane Orb (player hexproof), No Mercy and Phyrexian Obliterator against
  combat.

## Traps (all from the verified text)
- **Oppression is symmetric.** Every spell *you* cast costs you a card too. Deploy it
  after Tergrid and your rocks, not before.
- **Pox and Pox Plague hit you as hard as anyone.** Cast them when your board is built to
  shrug it off: Tergrid protected, permanents you don't mind losing.
- **Mind Twist and Hymn take random cards.** They're stronger when Tergrid is already out,
  because any permanent card they hit becomes yours.
- **Tergrid only takes permanent cards from discards.** Instants and sorceries discarded
  just go to the graveyard. Waste Not and Geth's Grimoire still pay you for those.

## Pilot
1. Discard on turns 1–3.
2. Tergrid on turn 3–4 with protection.
3. Then the locks: Necrogen Mists, Bottomless Pit, Oppression.
4. Finish with Torment of Hailfire or Gray Merchant once they're hellbent.

## Optimizer review (2026-10-11, preview only — not applied)
`optimize.py` proposed **Beseech the Mirror → Lightning Greaves**. Rejected: Beseech is a
core tutor, and Greaves' shroud blocks your own Kaya's Ghostform and return spells. It also
noted Death Cloud (37%) over **Profane Tutor**. Profane Tutor stays as the cheapest any-card
tutor.

**Fixed the same day (oracle_flags v4, goldfish schema 5):** edicts now count as removal
(8 removal plus 1 wipe; Interaction scores 13.5, up from 3.0). The goldfish now models the
rituals, Coffers, Stronghold, Nykthos, Crypt Ghast, Urborg and Jet Medallion. Tergrid by
turn 4 rose from 22% to 31%, by turn 5 from 51% to 59%, and the mean landing turn from 5.8
to 5.4.

## Card roles (every nonland card, for review)
- **Ramp:** Sol Ring, Arcane Signet, Jet Medallion, Mind Stone, Charcoal Diamond, Thought Vessel, Fellwar Stone, Dark Ritual, Cabal Ritual, Crypt Ghast
- **Protect Tergrid:** Swiftfoot Boots, Champion's Helm, Mithril Coat, Kaya's Ghostform, Imp's Mischief, Demonic Gifts, Undying Malice, Malakir Rebirth
- **Repeating discard:** Waste Not, Oppression, Necrogen Mists, Bottomless Pit, Rankle, Master of Pranks, Liliana of the Veil, Mindslicer, The Raven Man, Tourach, Dread Cantor
- **One-shot discard:** Dark Deal, Duress, Thoughtseize, Hymn to Tourach, Mind Twist, Burglar Rat, Elderfang Disciple, Virus Beetle, Syphon Mind
- **Punish empty hands:** Painful Quandary, Megrim, Liliana's Caress, Torment of Hailfire, Vicious Rumors, Tinybones, Trinket Thief, Gray Merchant of Asphodel, Sangromancer
- **Edicts (feed Tergrid):** Smallpox, Pox, Pox Plague, Plaguecrafter, Accursed Marauder, Sheoldred's Edict, Liliana's Triumph, Mire in Misery, Vona's Hunger, Archfiend of Depravity
- **Tutors & draw:** Diabolic Tutor, Profane Tutor, Beseech the Mirror, Night's Whisper, Geth's Grimoire, Phyrexian Arena
- **Protect you:** Witchbane Orb, No Mercy, Phyrexian Obliterator, Toxic Deluge
