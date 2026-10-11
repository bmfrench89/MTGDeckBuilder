# Tergrid — Grave Pact Engine (option 2 of 3)

**Study copy — not built from the collection.** Research build, 2026-10-11. Every card's
text was verified on GitHub runners (deck-verify runs 38138722782, 38139031278,
38139999873, 38140217987 and the attrs run). Field % = share of 12,840 Tergrid decks
on EDHREC (snapshot 2026-10-11).

## The commander (verified)

> Tergrid, God of Fright — {3}{B}{B} — Legendary Creature — God — 4/5
> Menace. Whenever an opponent sacrifices a nontoken permanent or discards a permanent
> card, you may put that card from a graveyard onto the battlefield under your control.

She is a **Game Changer**, and Braids, Cabal Minion is the second, for two in total
(Bracket 3).

## The plan: turn every one of your deaths into a steal

**Engines** (each makes opponents sacrifice whenever your creature dies, or on a clock):
- Grave Pact (36%)
- Dictate of Erebos (21%, has flash)
- Butcher of Malakir (18%)
- Braids, Cabal Minion: every player sacrifices each upkeep
- Sheoldred, Whispering One: opponents sacrifice at their upkeep, and you return a
  creature at yours, Tergrid included if she died there
- Archfiend of Depravity: opponents keep two creatures and sacrifice the rest

**Free sacrifice outlets:** Viscera Seer, Carrion Feeder, Ashnod's Altar, Phyrexian Tower
and Village Rites.

**Fodder that comes back or pays you:**
- Myr Retriever and Junk Diver return an artifact when they die. That artifact can be
  protection, such as Swiftfoot Boots or Mithril Coat.
- Scrap Trawler chains artifacts back to hand.
- Bitterblossom and Waste Not make tokens.
- Phyrexian Reclamation and Grim Discovery rebuy creatures.

**The core loop:** with Tergrid and Grave Pact out, sacrifice Myr Retriever to Viscera
Seer.
1. Every opponent sacrifices a creature.
2. Tergrid takes each nontoken one.
3. Myr Retriever returns an artifact to your hand.

**Sidisi, Undead Vizier** does the same with a tutor attached: sacrifice a creature, then
search for any card.

## Symmetric edicts are on purpose
Fleshbag Marauder, Merciless Executioner, Demon's Disciple, Plaguecrafter, Innocent Blood
and Barter in Blood make you sacrifice too. With a Pact out, your sacrifice triggers
another round. Keep a token or a Myr around so Tergrid is never your only creature.

## Protection (lighter than option 1)
- **Equipment:** Swiftfoot Boots, Champion's Helm, Commander's Plate, Mithril Coat.
- **Return effects:** Kaya's Ghostform, Demonic Gifts, Undying Evil, Feign Death.
- **Redirect:** Imp's Mischief.
- **Lands:** Tyrite Sanctum, Cavern of Souls.
- **Emergencies:** Darkness (fog) and Toxic Deluge (wipe). Tergrid is a 4/5, so X=4
  leaves her standing.

## Traps (all from the verified text)
- **Sacrifice ignores indestructible and hexproof.** If Tergrid is your only creature,
  your own symmetric edict takes her.
- **Opponents choose what they sacrifice, and tokens give Tergrid nothing.** Accursed
  Marauder and Sheoldred's Edict's first mode force a nontoken creature.
- **Braids, Cabal Minion hits you too.** Each upkeep you sacrifice an artifact, creature
  or land, so have fodder before casting her.

## Pilot
1. Ramp and discard first.
2. Tergrid on turn 3–4, protected.
3. Then an engine (Pact or Dictate), then the outlets.
4. Hold Dictate of Erebos to flash in at end of turn.

## Optimizer review (2026-10-11, preview only — not applied)
`optimize.py` proposed **Beseech the Mirror → Lightning Greaves**. Rejected: Beseech is the
deck's best tutor (bargain a token or Treasure to cast the find free), and Greaves' shroud
blocks your own Kaya's Ghostform and return spells. It also suggested buying Oppression,
Geth's Grimoire and Elderfang Disciple over **Archon of Cruelty**, **Chainer's Edict** and
**Codex Shredder**. Those three stay: they're the repeatable edict, the flashback edict and
the any-card recursion this build depends on.

**Fixed the same day (oracle_flags v4, goldfish schema 5):** edicts now count as removal
(14 removal plus 1 wipe; Interaction scores 18.0, up from 3.0). The goldfish now models the
rituals, Coffers, Stronghold, Nykthos, Crypt Ghast, Urborg and Jet Medallion. Tergrid by
turn 4 rose from 20% to 30%, by turn 5 from 49% to 57%, and the mean landing turn from 5.8
to 5.45.

## Card roles (every nonland card, for review)
- **Ramp:** Sol Ring, Arcane Signet, Jet Medallion, Mind Stone, Charcoal Diamond, Thought Vessel, Ashnod's Altar, Dark Ritual, Cabal Ritual, Crypt Ghast
- **Protect Tergrid:** Swiftfoot Boots, Champion's Helm, Commander's Plate, Mithril Coat, Kaya's Ghostform, Imp's Mischief, Demonic Gifts, Undying Evil, Feign Death
- **Pact engines:** Grave Pact, Dictate of Erebos, Butcher of Malakir, Braids, Cabal Minion, Sheoldred, Whispering One, Archfiend of Depravity
- **Sacrifice outlets:** Viscera Seer, Carrion Feeder, Village Rites, Ashnod's Altar
- **Fodder & recursion:** Myr Retriever, Junk Diver, Scrap Trawler, Bitterblossom, Waste Not, Phyrexian Reclamation, Grim Discovery, Codex Shredder
- **Tutors:** Diabolic Tutor, Profane Tutor, Beseech the Mirror, Sidisi, Undead Vizier
- **Edicts (feed Tergrid):** Accursed Marauder, Fleshbag Marauder, Plaguecrafter, Demon's Disciple, Merciless Executioner, Sheoldred's Edict, Liliana's Triumph, Innocent Blood, Barter in Blood, Chainer's Edict, Smallpox, Archon of Cruelty
- **Discard (feeds Tergrid):** Dark Deal, Duress, Rankle, Master of Pranks, Burglar Rat
- **Card draw:** Syphon Mind, Night's Whisper, Sign in Blood, Phyrexian Arena
- **Protect you / life:** Sangromancer, Gray Merchant of Asphodel, Darkness, Toxic Deluge
